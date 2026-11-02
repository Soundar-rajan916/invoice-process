from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.circuit_breaker import llm_circuit_breaker
from app.core.config import settings
from app.core.logging import logger
from app.core.rate_limiter import llm_rate_limiter
from app.core.storage import storage_service
from app.extraction.base import PageInput
from app.extraction.factory import get_extractor, get_second_opinion_extractor
from app.extraction.grouping import PageGrouper
from app.extraction.preprocess import Preprocessor
from app.models.entities import (
    Extraction,
    Invoice,
    ReviewEvent,
    SourceFile,
    Supplier,
    ValidationIssue,
)
from app.services.dedup import check_duplicates, get_financial_year, normalize_invoice_number
from app.services.validation import ValidationIssueDto, validate_extraction


async def process_invoice_pipeline(session: AsyncSession, invoice_id: uuid.UUID) -> Invoice | None:
    """Core invoice processing pipeline executed by Celery workers or async callers.
    R1: Handles degradation, blur rejection, and multipage.
    R2: Enforces deterministic validation; transitions to NEEDS_REVIEW (never auto-approves).
    R3: Handles business-key deduplication and concurrency races.
    R4: Idempotent compare-and-set state transitions, watchdog heartbeat, circuit breaker.
    """
    # 1. Compare-and-Set: RECEIVED / WAITING_PROVIDER -> PROCESSING (Idempotent, R4)
    now = datetime.now(UTC)
    stmt = (
        update(Invoice)
        .where(
            Invoice.id == invoice_id,
            Invoice.status.in_(["RECEIVED", "WAITING_PROVIDER"]),
        )
        .values(status="PROCESSING", heartbeat_at=now)
        .execution_options(synchronize_session=False)
    )
    res = await session.execute(stmt)
    if getattr(res, "rowcount", 0) == 0:
        logger.info(
            "Invoice is not in RECEIVED/WAITING_PROVIDER state, skipping duplicate execution",
            invoice_id=str(invoice_id),
        )
        return None

    # Audit status transition
    session.add(
        ReviewEvent(
            invoice_id=invoice_id,
            action="status_change",
            payload={
                "to_status": "PROCESSING",
                "reason": "worker_pipeline_start",
            },
        )
    )
    await session.commit()

    invoice = await session.get(Invoice, invoice_id, populate_existing=True)
    if not invoice:
        return None

    source_file = await session.get(SourceFile, invoice.source_file_id)
    if not source_file:
        invoice.status = "FAILED"
        invoice.status_reason = "Source file record missing"
        await session.commit()
        return invoice

    try:
        # 2. Download original file bytes
        file_bytes = storage_service.download_bytes(source_file.storage_key)

        # 3. Preprocessing (PyMuPDF / OpenCV / Blur detection) (R1)
        preprocessor = Preprocessor(invoice_id=str(invoice.id))
        pages = preprocessor.process(file_bytes, source_file.content_type)
        if not pages:
            invoice.status = "FAILED"
            invoice.status_reason = "No renderable pages found in document"
            await session.commit()
            return invoice

        # Check blur scores across pages (R1)
        min_blur = min(p.blur_score for p in pages)
        all_blurry = all(p.blur_score < settings.BLUR_REJECT_THRESHOLD for p in pages)
        if all_blurry:
            # Automatic reject with resend request to prevent bad data
            invoice.status = "RESEND_REQUESTED"
            invoice.status_reason = (
                f"Image too blurry to read accurately (blur score {min_blur:.1f} < threshold {settings.BLUR_REJECT_THRESHOLD}). "
                "Please upload a clearer document."
            )
            session.add(
                ReviewEvent(
                    invoice_id=invoice.id,
                    action="request_resend",
                    payload={"blur_score": min_blur, "reason": invoice.status_reason},
                )
            )
            await session.commit()
            return invoice

        # 4. Page grouping (R1)
        page_groups = PageGrouper.group_pages(pages)
        if len(page_groups) > 1:
            logger.info(
                "Multi-invoice document detected, splitting into separate invoices",
                groups=len(page_groups),
            )
            pages = page_groups[0].pages
            invoice.page_count = len(pages)
            for extra_group in page_groups[1:]:
                split_inv = Invoice(
                    id=uuid.uuid4(),
                    source_file_id=source_file.id,
                    status="RECEIVED",
                    page_count=len(extra_group.pages),
                )
                session.add(split_inv)
                await session.flush()
                session.add(
                    ReviewEvent(
                        invoice_id=split_inv.id,
                        action="status_change",
                        payload={"reason": f"split_from_parent_invoice_{invoice.id}"},
                    )
                )
        else:
            invoice.page_count = len(pages)

        # 5. Circuit Breaker Check before LLM Extraction (R4)
        if not await llm_circuit_breaker.is_allowed():
            logger.warning(
                "LLM circuit breaker is OPEN, transitioning to WAITING_PROVIDER",
                invoice_id=str(invoice.id),
            )
            invoice.status = "WAITING_PROVIDER"
            invoice.status_reason = "LLM provider temporarily unavailable (circuit breaker open)"
            session.add(
                ReviewEvent(
                    invoice_id=invoice.id,
                    action="status_change",
                    payload={"to_status": "WAITING_PROVIDER", "reason": "circuit_breaker_open"},
                )
            )
            await session.commit()
            return invoice

        # Extraction via Extractor (Groq or Mock)
        extractor = get_extractor()
        page_inputs = [
            PageInput(
                page_number=p.page_number,
                text=p.text,
                image_bytes=p.image_bytes,
                is_digital=p.is_digital,
                storage_key=p.storage_key,
                original_filename=source_file.original_filename,
            )
            for p in pages
        ]

        try:
            async with llm_rate_limiter:
                extraction_res = await extractor.extract(page_inputs)
            llm_rate_limiter.on_success()
            await llm_circuit_breaker.record_success()
        except Exception as llm_err:
            if "429" in str(llm_err):
                llm_rate_limiter.on_rate_limit()
            await llm_circuit_breaker.record_failure(llm_err)
            raise

        # 6. Deterministic Validation (R2)
        sup_stmt = select(Supplier).where(Supplier.is_active.is_(True))
        suppliers_list = (await session.execute(sup_stmt)).scalars().all()
        known_suppliers = {s.gstin: s.name for s in suppliers_list}

        source_text = "\n".join(p.text for p in pages if p.is_digital and p.text)

        val_issues = validate_extraction(
            extraction_res.extraction,
            known_suppliers=known_suppliers,
            min_page_blur=min_blur,
            source_text=source_text,
        )

        # Second opinion (config-gated, R2)
        if settings.SECOND_OPINION_ENABLED:
            try:
                second_extractor = get_second_opinion_extractor()
                second_res = await second_extractor.extract(page_inputs)
                from decimal import Decimal

                first_total = extraction_res.extraction.total or Decimal("0.00")
                second_total = second_res.extraction.total or Decimal("0.00")
                diff = abs(first_total - second_total)
                if diff > settings.TOTAL_ROUNDING_TOLERANCE:
                    val_issues.append(
                        ValidationIssueDto(
                            code="extractors_disagree",
                            field="total",
                            severity="warning",
                            message=f"Primary model total (₹{first_total:.2f}) differs from second opinion (₹{second_total:.2f}) by ₹{diff:.2f}",
                        )
                    )
                else:
                    for k in extraction_res.extraction.field_confidence:
                        extraction_res.extraction.field_confidence[k] = min(
                            1.0, extraction_res.extraction.field_confidence[k] + 0.1
                        )

                if isinstance(extraction_res.raw_response, dict):
                    extraction_res.raw_response["second_opinion"] = (
                        second_res.extraction.model_dump(mode="json")
                    )
                else:
                    extraction_res.raw_response = {
                        "primary": extraction_res.raw_response,
                        "second_opinion": second_res.extraction.model_dump(mode="json"),
                    }
            except Exception as e:
                logger.warning("Second opinion extraction failed", error=str(e))

        error_issues = [i for i in val_issues if i.severity == "error"]

        # Retry on validation failure (Single attempt with failed checks prompt, R2)
        if error_issues and settings.EXTRACTOR == "groq":
            logger.info(
                "Validation errors found, triggering one-time repair re-extraction",
                errors=[e.message for e in error_issues],
            )
            feedback = [e.message for e in error_issues]
            try:
                retry_res = await extractor.extract(page_inputs, validation_feedback=feedback)
                retry_issues = validate_extraction(
                    retry_res.extraction, known_suppliers=known_suppliers, min_page_blur=min_blur
                )
                retry_errors = [i for i in retry_issues if i.severity == "error"]
                if len(retry_errors) < len(error_issues):
                    extraction_res = retry_res
                    val_issues = retry_issues
            except Exception as e:
                logger.warning(
                    "Retry extraction encountered error, keeping original result", error=str(e)
                )

        # 7. Persist Extraction record (append-only)
        extraction_data = extraction_res.extraction.model_dump(mode="json")
        ext_row = Extraction(
            id=uuid.uuid4(),
            invoice_id=invoice.id,
            version=1,
            kind="model",
            data=extraction_data,
            confidences=extraction_res.extraction.field_confidence,
            model_id=extraction_res.model_id,
            prompt_version=extraction_res.prompt_version,
            raw_response=extraction_res.raw_response,
            token_usage=extraction_res.token_usage,
            latency_ms=extraction_res.latency_ms,
        )
        session.add(ext_row)
        await session.flush()

        # 8. Deduplication checks (R3 Layer 2 & 3)
        norm_inv_num = normalize_invoice_number(extraction_res.extraction.invoice_number)
        fin_year = get_financial_year(extraction_res.extraction.invoice_date)

        dup_of_id, dup_issues = await check_duplicates(
            session=session,
            invoice_id=invoice.id,
            supplier_gstin=extraction_res.extraction.supplier_gstin,
            normalized_inv_num=norm_inv_num,
            financial_year=fin_year,
            invoice_date=extraction_res.extraction.invoice_date,
            total=extraction_res.extraction.total,
        )

        # Update invoice business key columns
        raw_gstin = extraction_res.extraction.supplier_gstin
        clean_gstin = raw_gstin.strip() if raw_gstin else None
        invoice.current_extraction_id = ext_row.id
        invoice.extraction_path = extraction_res.extraction_path
        invoice.supplier_gstin = clean_gstin[:64] if clean_gstin else None
        invoice.normalized_invoice_number = norm_inv_num[:100] if norm_inv_num else None
        invoice.financial_year = fin_year[:10] if fin_year else None
        if dup_of_id:
            invoice.dup_of_id = dup_of_id

        # Check if this invoice fulfills an existing RESEND_REQUESTED invoice
        if clean_gstin and norm_inv_num and fin_year and not dup_of_id:
            resend_stmt = select(Invoice).where(
                Invoice.id != invoice.id,
                Invoice.supplier_gstin == clean_gstin[:64],
                Invoice.normalized_invoice_number == norm_inv_num[:100],
                Invoice.financial_year == fin_year[:10],
                Invoice.status == "RESEND_REQUESTED",
            )
            resend_match = (await session.execute(resend_stmt)).scalars().first()
            if resend_match:
                resend_match.status = "REJECTED_DUPLICATE"
                resend_match.dup_of_id = invoice.id
                resend_match.status_reason = f"Superseded by replacement invoice {invoice.id}"
                resend_match.row_version += 1
                session.add(
                    ReviewEvent(
                        invoice_id=resend_match.id,
                        action="resend_fulfilled",
                        payload={
                            "replacement_invoice_id": str(invoice.id),
                            "reason": "Replacement invoice uploaded and processed successfully",
                        },
                    )
                )
                session.add(
                    ReviewEvent(
                        invoice_id=invoice.id,
                        action="resend_fulfilled",
                        payload={
                            "previous_invoice_id": str(resend_match.id),
                            "previous_resend_reason": resend_match.status_reason,
                        },
                    )
                )

        try:
            # 9. Clear stale validation issues and persist fresh issues
            await session.execute(
                delete(ValidationIssue).where(ValidationIssue.invoice_id == invoice.id)
            )
            for issue in val_issues:
                v_row = ValidationIssue(
                    invoice_id=invoice.id,
                    extraction_id=ext_row.id,
                    code=issue.code,
                    field=issue.field,
                    severity=issue.severity,
                    message=issue.message,
                )
                session.add(v_row)

            for d_issue in dup_issues:
                d_row = ValidationIssue(
                    invoice_id=invoice.id,
                    extraction_id=ext_row.id,
                    code=d_issue["code"],
                    field=d_issue["field"],
                    severity=d_issue["severity"],
                    message=d_issue["message"],
                )
                session.add(d_row)

            # R2 Rule: Universal human gate - every invoice transitions to NEEDS_REVIEW
            invoice.status = "NEEDS_REVIEW"
            session.add(
                ReviewEvent(
                    invoice_id=invoice.id,
                    action="status_change",
                    payload={
                        "from_status": "PROCESSING",
                        "to_status": "NEEDS_REVIEW",
                        "issues_count": len(val_issues) + len(dup_issues),
                    },
                )
            )
            await session.commit()
        except IntegrityError:
            # Handle concurrent race on duplicate business key (R3 concurrency race)
            await session.rollback()
            logger.warning(
                "IntegrityError on business key unique index; marking duplicate",
                invoice_id=str(invoice_id),
            )
            norm_gstin = extraction_res.extraction.supplier_gstin
            orig_stmt = select(Invoice.id).where(
                Invoice.id != invoice_id,
                Invoice.supplier_gstin == norm_gstin,
                Invoice.normalized_invoice_number == norm_inv_num,
                Invoice.financial_year == fin_year,
                Invoice.dup_of_id.is_(None),
            )
            existing_id = (await session.execute(orig_stmt)).scalars().first()

            dup_invoice = await session.get(Invoice, invoice_id)
            if dup_invoice:
                dup_invoice.status = "NEEDS_REVIEW"
                dup_invoice.dup_of_id = existing_id
                dup_invoice.supplier_gstin = norm_gstin
                dup_invoice.normalized_invoice_number = norm_inv_num
                dup_invoice.financial_year = fin_year
                dup_invoice.current_extraction_id = ext_row.id
                session.add(
                    ValidationIssue(
                        invoice_id=dup_invoice.id,
                        extraction_id=ext_row.id,
                        code="duplicate",
                        field="invoice_number",
                        severity="error",
                        message="Duplicate invoice key detected concurrently by unique index constraint.",
                    )
                )
                await session.commit()
                return dup_invoice

        return invoice
    except Exception as e:
        logger.exception(
            "Pipeline failed while processing invoice", invoice_id=str(invoice_id), error=str(e)
        )
        try:
            await session.rollback()
            failed_inv = await session.get(Invoice, invoice_id)
            if failed_inv:
                is_encrypted_or_corrupt = any(
                    term in str(e).lower()
                    for term in ("encrypted", "password", "corrupt", "closed or encrypted")
                )
                if is_encrypted_or_corrupt:
                    failed_inv.status = "RESEND_REQUESTED"
                    failed_inv.status_reason = (
                        "PDF is password-protected or corrupt. Please resend an unencrypted document."
                    )
                    action = "request_resend"
                else:
                    failed_inv.status = "FAILED"
                    failed_inv.status_reason = f"Processing failed: {str(e)}"
                    action = "status_change"

                session.add(
                    ReviewEvent(
                        invoice_id=failed_inv.id,
                        action=action,
                        payload={
                            "from_status": "PROCESSING",
                            "to_status": failed_inv.status,
                            "error": str(e),
                        },
                    )
                )
                await session.commit()
                return failed_inv
        except Exception as rollback_err:
            logger.error(
                "Failed to persist FAILED status after pipeline exception", error=str(rollback_err)
            )
        return invoice
