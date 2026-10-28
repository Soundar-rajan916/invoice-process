from __future__ import annotations

import asyncio
import base64
import io
import json
import random
import time
from typing import Any

from groq import APIStatusError, AsyncGroq, RateLimitError
from PIL import Image
from pydantic import ValidationError

from app.core.config import settings
from app.core.errors import DomainError
from app.core.logging import logger
from app.extraction.base import ExtractionResult, PageInput
from app.extraction.preprocess import downscale_and_compress
from app.schemas.extraction import InvoiceExtraction

PROMPT_VERSION = "2026-10-28.v1"

EXTRACTION_SYSTEM_PROMPT = """You are a precise invoice extraction engine for Indian GST invoices.
Rules:
1. Read ONLY what is printed on the invoice. Never calculate, infer, or guess any values.
2. Return null for any field that is missing, cut off, or illegible.
3. Copy invoice numbers and GSTINs EXACTLY as printed, preserving hyphens, slashes, and original punctuation.
4. Format all dates as YYYY-MM-DD. Note that Indian invoices use day-first format (DD/MM/YYYY or DD-MM-YYYY). For example, '03/04/2026' is 2026-04-03.
5. Format all numbers as plain decimals without currency symbols (₹, Rs) or thousands separators. Normalize Indian digit grouping (e.g., '1,23,456.50' -> '123456.50').
6. Extract line items in exact printed order. Include description, quantity, rate, and amount per line item.
7. Provide a field_confidence map (values 0.0 to 1.0) for every top-level field as an indicator of legibility.
8. List any uncertain, faded, or unreadable fields in unreadable_fields.
9. You MUST output valid JSON conforming exactly to the requested schema.
"""


class GroqExtractor:
    _semaphore: asyncio.Semaphore | None = None

    def __init__(self) -> None:
        self.api_key = settings.GROQ_API_KEY
        self.text_model = settings.GROQ_TEXT_MODEL
        self.vision_model = settings.GROQ_VISION_MODEL
        self.max_images = settings.GROQ_MAX_IMAGES_PER_REQUEST
        self.max_bytes = settings.GROQ_MAX_REQUEST_BYTES
        self.repair_retries = settings.GROQ_REPAIR_RETRIES
        self.timeout = settings.GROQ_TIMEOUT_SECONDS

        if GroqExtractor._semaphore is None:
            GroqExtractor._semaphore = asyncio.Semaphore(settings.GROQ_MAX_CONCURRENCY)

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if GroqExtractor._semaphore is None:
            GroqExtractor._semaphore = asyncio.Semaphore(settings.GROQ_MAX_CONCURRENCY)
        return GroqExtractor._semaphore

    async def extract(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult:
        if not pages:
            raise DomainError("No Pages Provided", "Cannot extract invoice with 0 pages", 400)

        # Path Selection: text path if ALL pages are digital, vision path otherwise
        use_text_path = all(p.is_digital for p in pages)
        extraction_path = "text" if use_text_path else "vision"

        start_time = time.perf_counter()

        if use_text_path:
            result = await self._extract_text(pages, validation_feedback)
        else:
            result = await self._extract_vision(pages, validation_feedback)

        duration_ms = int((time.perf_counter() - start_time) * 1000)
        result.latency_ms = duration_ms
        result.extraction_path = extraction_path
        return result

    async def _extract_text(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult:
        content_parts = []
        for p in pages:
            content_parts.append(f"--- PAGE {p.page_number} ---\n{p.text}")
        doc_text = "\n\n".join(content_parts)

        prompt = f"Extract all fields from this invoice text:\n\n{doc_text}"
        if validation_feedback:
            feedback_str = "\n".join(f"- {f}" for f in validation_feedback)
            prompt += f"\n\nPRIOR EXTRACTION ERRORS DETECTED. PLEASE RE-READ CAREFULLY AND CORRECT:\n{feedback_str}"

        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]

        return await self._call_groq_with_retries(messages, model=self.text_model)

    async def _extract_vision(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult:
        # Multi-batch handling if pages exceed max_images
        if len(pages) > self.max_images:
            return await self._extract_vision_in_batches(pages, validation_feedback)

        user_content: list[dict[str, Any]] = []
        user_content.append(
            {"type": "text", "text": "Extract all fields from these invoice page images."}
        )

        if validation_feedback:
            feedback_str = "\n".join(f"- {f}" for f in validation_feedback)
            user_content.append(
                {
                    "type": "text",
                    "text": f"PRIOR EXTRACTION ERRORS DETECTED. PLEASE RE-READ AND CORRECT:\n{feedback_str}",
                }
            )

        # Compress images to guarantee they fit within max_bytes
        prepared_images = self._prepare_images_within_budget(pages)

        for _p_idx, b64_img in enumerate(prepared_images):
            user_content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{b64_img}",
                    },
                }
            )

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ]

        return await self._call_groq_with_retries(messages, model=self.vision_model)

    def _prepare_images_within_budget(self, pages: list[PageInput]) -> list[str]:
        """Encodes images to base64, re-compressing at lower quality/resolution if over byte cap."""
        b64_list: list[str] = []
        total_bytes = 0

        for p in pages:
            b64_str = base64.b64encode(p.image_bytes).decode("utf-8")
            total_bytes += len(b64_str)
            b64_list.append(b64_str)

        if total_bytes <= self.max_bytes:
            return b64_list

        # Re-compress at quality 60
        logger.info(
            "Payload exceeds max bytes, recompressing images at quality 60", total_bytes=total_bytes
        )
        b64_list = []
        total_bytes = 0
        for p in pages:
            img = Image.open(io.BytesIO(p.image_bytes))
            recompressed = downscale_and_compress(img, max_long_side=1200, quality=60)
            b64_str = base64.b64encode(recompressed).decode("utf-8")
            total_bytes += len(b64_str)
            b64_list.append(b64_str)

        if total_bytes <= self.max_bytes:
            return b64_list

        # Re-compress at resolution 1000 and quality 45
        logger.info(
            "Payload still exceeds max bytes, recompressing at resolution 1000",
            total_bytes=total_bytes,
        )
        b64_list = []
        for p in pages:
            img = Image.open(io.BytesIO(p.image_bytes))
            recompressed = downscale_and_compress(img, max_long_side=1000, quality=45)
            b64_str = base64.b64encode(recompressed).decode("utf-8")
            b64_list.append(b64_str)

        return b64_list

    async def _extract_vision_in_batches(
        self,
        pages: list[PageInput],
        validation_feedback: list[str] | None = None,
    ) -> ExtractionResult:
        """Splits multi-page document into batches of max_images and merges results."""
        batches: list[list[PageInput]] = []
        for i in range(0, len(pages), self.max_images):
            batches.append(pages[i : i + self.max_images])

        results: list[ExtractionResult] = []
        for b in batches:
            res = await self._extract_vision(b, validation_feedback)
            results.append(res)

        return self.merge_batch_extractions(results)

    @classmethod
    def merge_batch_extractions(cls, results: list[ExtractionResult]) -> ExtractionResult:
        """Merges batch results: headers from first batch, line items concatenated, totals from last batch."""
        if not results:
            raise ValueError("No results to merge")
        if len(results) == 1:
            return results[0]

        first = results[0].extraction
        last = results[-1].extraction

        merged_line_items = []
        for r in results:
            merged_line_items.extend(r.extraction.line_items)

        merged_confidences = dict(first.field_confidence)
        merged_confidences.update(last.field_confidence)

        merged_unreadable = list(set(first.unreadable_fields + last.unreadable_fields))

        merged_extraction = InvoiceExtraction(
            invoice_number=first.invoice_number,
            invoice_date=first.invoice_date,
            supplier_name=first.supplier_name,
            supplier_gstin=first.supplier_gstin,
            line_items=merged_line_items,
            taxable_value=last.taxable_value,
            cgst=last.cgst,
            sgst=last.sgst,
            igst=last.igst,
            total=last.total,
            field_confidence=merged_confidences,
            unreadable_fields=merged_unreadable,
        )

        total_prompt_tokens = sum((r.token_usage or {}).get("prompt_tokens", 0) for r in results)
        total_comp_tokens = sum((r.token_usage or {}).get("completion_tokens", 0) for r in results)

        return ExtractionResult(
            extraction=merged_extraction,
            extraction_path="vision",
            model_id=results[0].model_id,
            prompt_version=PROMPT_VERSION,
            raw_response={"merged_batches": len(results)},
            token_usage={
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_comp_tokens,
                "total_tokens": total_prompt_tokens + total_comp_tokens,
            },
            latency_ms=sum(r.latency_ms for r in results),
            retries_used=sum(r.retries_used for r in results),
        )

    async def _call_groq_with_retries(
        self,
        messages: list[dict[str, Any]],
        model: str,
    ) -> ExtractionResult:
        client = AsyncGroq(api_key=self.api_key)
        retries_used = 0

        async with self.semaphore:
            current_messages = list(messages)
            last_err: Exception | None = None

            for attempt in range(self.repair_retries + 1):
                try:
                    # Execute Groq completion with exponential backoff on 429/5xx
                    response = await self._execute_request_with_backoff(
                        client, model, current_messages
                    )
                    raw_content = response.choices[0].message.content or "{}"
                    raw_json = json.loads(raw_content)

                    # Validate with Pydantic
                    parsed_extraction = InvoiceExtraction.model_validate(raw_json)

                    usage = response.usage
                    token_usage = {
                        "prompt_tokens": usage.prompt_tokens if usage else 0,
                        "completion_tokens": usage.completion_tokens if usage else 0,
                        "total_tokens": usage.total_tokens if usage else 0,
                    }

                    return ExtractionResult(
                        extraction=parsed_extraction,
                        extraction_path="text",
                        model_id=model,
                        prompt_version=PROMPT_VERSION,
                        raw_response=raw_json,
                        token_usage=token_usage,
                        latency_ms=0,
                        retries_used=retries_used,
                    )

                except (ValidationError, json.JSONDecodeError) as e:
                    retries_used += 1
                    last_err = e
                    logger.warning(
                        "Groq output validation failed, attempting repair retry",
                        attempt=attempt + 1,
                        error=str(e),
                    )
                    if attempt < self.repair_retries:
                        # Append repair turn
                        error_detail = str(e)
                        current_messages.append(
                            {
                                "role": "assistant",
                                "content": raw_content if "raw_content" in locals() else "{}",
                            }
                        )
                        current_messages.append(
                            {
                                "role": "user",
                                "content": (
                                    f"Your previous response had validation errors:\n{error_detail}\n\n"
                                    f"Please fix the error and output ONLY the corrected JSON object matching the schema."
                                ),
                            }
                        )
                    else:
                        raise DomainError(
                            "Groq Extraction Failed",
                            f"Validation failed after repair retries: {e}",
                            422,
                        ) from e

            raise DomainError("Groq Extraction Failed", f"Exhausted retries: {last_err}", 422)

    async def _execute_request_with_backoff(
        self,
        client: AsyncGroq,
        model: str,
        messages: list[dict[str, Any]],
        max_attempts: int = 4,
    ) -> Any:
        delay = 1.0
        for attempt in range(max_attempts):
            try:
                return await asyncio.wait_for(
                    client.chat.completions.create(  # type: ignore[call-overload,arg-type]
                        model=model,
                        messages=messages,
                        temperature=0.0,
                        response_format={"type": "json_object"},
                    ),
                    timeout=self.timeout,
                )
            except RateLimitError as e:
                # Honour retry-after header if present
                retry_after = getattr(e, "response", None) and e.response.headers.get("retry-after")
                wait_time = float(retry_after) if retry_after else delay + random.uniform(0.1, 0.5)
                logger.warning(
                    "Groq rate limit encountered (429)", wait_time=wait_time, attempt=attempt + 1
                )
                await asyncio.sleep(wait_time)
                delay *= 2
            except APIStatusError as e:
                if e.status_code >= 500:
                    wait_time = delay + random.uniform(0.1, 0.5)
                    logger.warning(
                        "Groq 5xx error encountered",
                        status=e.status_code,
                        wait_time=wait_time,
                        attempt=attempt + 1,
                    )
                    await asyncio.sleep(wait_time)
                    delay *= 2
                else:
                    # 4xx client errors should never be retried
                    raise
            except TimeoutError as e:
                logger.warning("Groq request timed out", attempt=attempt + 1)
                if attempt == max_attempts - 1:
                    raise DomainError(
                        "Groq Timeout", f"Request timed out after {self.timeout}s", 504
                    ) from e
                await asyncio.sleep(delay)
                delay *= 2

        raise DomainError("Groq Service Unavailable", "Exhausted retries on 429/5xx errors", 503)
