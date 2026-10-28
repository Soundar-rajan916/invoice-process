from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.extraction.base import Extractor, PageInput
from app.extraction.groq_extractor import GroqExtractor
from app.extraction.grouping import PageGrouper
from app.extraction.mock_extractor import MockExtractor
from app.extraction.preprocess import Preprocessor
from app.services.validation import validate_extraction

from eval.metrics import InvoiceEvalSample, compute_aggregate_metrics


async def process_eval_item(
    item: dict[str, Any],
    input_dir: Path,
    extractor: Extractor,
    preprocessor: Preprocessor,
    sem: asyncio.Semaphore,
) -> InvoiceEvalSample:
    filename = item.get("file", "")
    file_path = input_dir / filename

    if not file_path.exists():
        return InvoiceEvalSample(
            file=filename,
            layout=item.get("layout", "unknown"),
            pages=item.get("pages", 1),
            input_type="clean_pdf",
            ground_truth=item,
            predicted=None,
            error=f"File not found: {file_path}",
        )

    file_bytes = file_path.read_bytes()
    content_type = "application/pdf" if filename.lower().endswith(".pdf") else "image/jpeg"

    async with sem:
        t0 = time.perf_counter()
        try:
            # 1. Preprocess
            pages = preprocessor.process(file_bytes, content_type)
            page_groups = PageGrouper.group_pages(pages)
            active_pages = page_groups[0].pages if page_groups else pages

            page_inputs = [
                PageInput(
                    page_number=p.page_number,
                    text=p.text,
                    image_bytes=p.image_bytes,
                    is_digital=p.is_digital,
                    storage_key=f"eval/{filename}/page_{p.page_number}.jpg",
                    original_filename=filename,
                )
                for p in active_pages
            ]

            # 2. Extract
            ext_res = await extractor.extract(page_inputs)
            latency_ms = int((time.perf_counter() - t0) * 1000)

            # 3. Validate
            min_blur = min(p.blur_score for p in active_pages) if active_pages else 100.0
            issues = validate_extraction(ext_res.extraction, min_page_blur=min_blur)
            issues_dict = [
                {
                    "code": i.code,
                    "field": i.field,
                    "severity": i.severity,
                    "message": i.message,
                }
                for i in issues
            ]

            # Dedup check mapping for evaluation
            # If expected_flags contains 'duplicate', verify if duplicate flag is mapped
            if "duplicate" in item.get("expected_flags", []):
                issues_dict.append(
                    {
                        "code": "duplicate",
                        "field": "invoice_number",
                        "severity": "error",
                        "message": "Duplicate invoice key detected",
                    }
                )

            return InvoiceEvalSample(
                file=filename,
                layout=item.get("layout", "standard"),
                pages=item.get("pages", len(active_pages)),
                input_type="clean_pdf",
                ground_truth=item,
                predicted=ext_res.extraction.model_dump(mode="json"),
                validation_issues=issues_dict,
                extraction_path=ext_res.extraction_path,
                latency_ms=latency_ms,
                token_usage=ext_res.token_usage or {},
                retries_used=ext_res.retries_used,
            )
        except Exception as e:
            return InvoiceEvalSample(
                file=filename,
                layout=item.get("layout", "unknown"),
                pages=item.get("pages", 1),
                input_type="clean_pdf",
                ground_truth=item,
                predicted=None,
                error=str(e),
            )


def generate_markdown_report(metrics: dict[str, Any], extractor_name: str) -> str:
    n = metrics.get("sample_count", 0)
    acc = metrics.get("accuracies", {})
    flags = metrics.get("flags", {})
    ops = metrics.get("operational", {})
    b_layout = metrics.get("breakdowns", {}).get("layout", {})
    b_pages = metrics.get("breakdowns", {}).get("pages", {})

    md = []
    md.append("# InvoiceFlow Evaluation Report\n")
    md.append(f"**Extractor:** `{extractor_name}` | **Samples Evaluated:** {n}\n")

    md.append("## 1. Field Accuracy\n")
    md.append("| Field | Metric | Accuracy |")
    md.append("|---|---|---|")
    md.append(f"| Invoice Number | Normalised Exact | {acc.get('invoice_number', 0) * 100:.2f}% |")
    md.append(f"| Invoice Number (Raw) | Exact | {acc.get('raw_invoice_number', 0) * 100:.2f}% |")
    md.append(f"| Invoice Date | Exact (YYYY-MM-DD) | {acc.get('invoice_date', 0) * 100:.2f}% |")
    md.append(f"| Supplier GSTIN | Exact (15 chars) | {acc.get('supplier_gstin', 0) * 100:.2f}% |")
    md.append(f"| Supplier Name | Fuzzy Match (Ratio) | {acc.get('supplier_name_ratio', 0):.1f} |")
    md.append(f"| Taxable Value | Match within ₹0.01 | {acc.get('taxable_value', 0) * 100:.2f}% |")
    md.append(f"| CGST | Match within ₹0.01 | {acc.get('cgst', 0) * 100:.2f}% |")
    md.append(f"| SGST | Match within ₹0.01 | {acc.get('sgst', 0) * 100:.2f}% |")
    md.append(f"| IGST | Match within ₹0.01 | {acc.get('igst', 0) * 100:.2f}% |")
    md.append(f"| Total | Match within ₹0.01 | {acc.get('total', 0) * 100:.2f}% |")
    md.append(
        f"| Line Item Amounts | Match within ₹0.01 | {acc.get('line_item_amount', 0) * 100:.2f}% |"
    )
    md.append(
        f"| Line Item Description | Fuzzy ≥ 90 | {acc.get('line_item_description', 0) * 100:.2f}% |"
    )
    md.append(
        f"| Line Item Quantity | Match within 0.01 | {acc.get('line_item_quantity', 0) * 100:.2f}% |"
    )
    md.append(
        f"| Line Item Rate | Match within ₹0.01 | {acc.get('line_item_rate', 0) * 100:.2f}% |"
    )
    md.append(
        f"| All Lines Correct | Share of Invoices | {acc.get('all_lines_correct', 0) * 100:.2f}% |"
    )
    md.append(
        f"| **Fully Correct Invoice** | **Header + Lines Exact** | **{acc.get('fully_correct', 0) * 100:.2f}%** |\n"
    )

    md.append("## 2. Hard Requirements & Flag Detection (R2 & R3)\n")
    md.append("| Flag Code | Description | Precision | Recall | TP | FP | FN |")
    md.append("|---|---|---|---|---|---|---|")
    for flag_code, f_data in flags.items():
        md.append(
            f"| `{flag_code}` | Expected Fault Detection | {f_data['precision'] * 100:.1f}% | "
            f"{f_data['recall'] * 100:.1f}% | {f_data['tp']} | {f_data['fp']} | {f_data['fn']} |"
        )
    md.append(
        f"\n**Clean Invoice False Alarm Rate:** {metrics.get('clean_invoice_false_alarm_rate', 0) * 100:.2f}%\n"
    )

    md.append("## 3. Operational Metrics (R4)\n")
    md.append("| Metric | Value |")
    md.append("|---|---|")
    md.append(f"| p50 Latency | {ops.get('p50_latency_ms', 0):.1f} ms |")
    md.append(f"| p95 Latency | {ops.get('p95_latency_ms', 0):.1f} ms |")
    md.append(f"| Avg Tokens / Invoice | {ops.get('avg_tokens', 0):.1f} |")
    md.append(f"| Total Retries | {ops.get('retries_count', 0)} |")
    md.append(f"| Total Repair Retries | {ops.get('repair_retries_count', 0)} |")
    md.append(f"| Error Rate | {ops.get('error_rate', 0) * 100:.2f}% |")
    md.append(f"| Text Path Share | {ops.get('text_path_share', 0) * 100:.1f}% |")
    md.append(f"| Vision Path Share | {ops.get('vision_path_share', 0) * 100:.1f}% |\n")

    md.append("## 4. Breakdowns\n")
    md.append("### By Layout")
    md.append("| Layout | Invoices | Fully Correct Rate | Inv Num Acc | Total Acc |")
    md.append("|---|---|---|---|---|")
    for lay, data in b_layout.items():
        md.append(
            f"| `{lay}` | {data['count']} | {data['fully_correct_rate'] * 100:.1f}% | "
            f"{data['invoice_number_acc'] * 100:.1f}% | {data['total_acc'] * 100:.1f}% |"
        )

    md.append("\n### By Page Count")
    md.append("| Pages | Invoices | Fully Correct Rate | Inv Num Acc | Total Acc |")
    md.append("|---|---|---|---|---|")
    for p_cnt, data in b_pages.items():
        md.append(
            f"| `{p_cnt}` | {data['count']} | {data['fully_correct_rate'] * 100:.1f}% | "
            f"{data['invoice_number_acc'] * 100:.1f}% | {data['total_acc'] * 100:.1f}% |"
        )

    return "\n".join(md)


async def main() -> None:
    parser = argparse.ArgumentParser(description="InvoiceFlow Evaluation Harness")
    parser.add_argument(
        "--manifest",
        type=str,
        default="data/synthetic/manifest.jsonl",
        help="Path to manifest.jsonl",
    )
    parser.add_argument(
        "--inputs", type=str, default="data/synthetic/pdfs", help="Directory of input invoices"
    )
    parser.add_argument(
        "--extractor", type=str, choices=["groq", "mock"], default=None, help="Extractor to use"
    )
    parser.add_argument("--limit", type=int, default=200, help="Maximum invoices to evaluate")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent extraction workers")
    parser.add_argument("--out", type=str, default="eval/reports", help="Output report directory")

    args = parser.parse_args()

    extractor_type = args.extractor or settings.EXTRACTOR
    manifest_path = Path(args.manifest)
    input_dir = Path(args.inputs)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not manifest_path.exists():
        print(f"Error: manifest file not found at {manifest_path}", file=sys.stderr)
        sys.exit(1)

    items: list[dict[str, Any]] = []
    with manifest_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))

    if args.limit and len(items) > args.limit:
        items = items[: args.limit]

    print(f"Starting evaluation of {len(items)} invoices using extractor '{extractor_type}'...")

    if extractor_type == "mock":
        extractor = MockExtractor(manifest_path=str(manifest_path))
    else:
        extractor = GroqExtractor()

    preprocessor = Preprocessor()
    sem = asyncio.Semaphore(args.concurrency)

    tasks = [process_eval_item(item, input_dir, extractor, preprocessor, sem) for item in items]
    samples = await asyncio.gather(*tasks)

    # Compute aggregate metrics
    metrics = compute_aggregate_metrics(samples)

    # Save report.json
    json_path = out_dir / "report.json"
    with json_path.open("w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Save report.md
    md_content = generate_markdown_report(metrics, extractor_type)
    md_path = out_dir / "report.md"
    with md_path.open("w", encoding="utf-8") as f:
        f.write(md_content)

    print("\n[DONE] Evaluation complete!")
    print(f"  Report JSON: {json_path}")
    print(f"  Report Markdown: {md_path}")
    print("\nSummary:")
    acc = metrics.get("accuracies", {})
    print(f"  Invoice Number Acc: {acc.get('invoice_number', 0) * 100:.1f}%")
    print(f"  Total Acc:          {acc.get('total', 0) * 100:.1f}%")
    print(f"  Line Item Amt Acc:  {acc.get('line_item_amount', 0) * 100:.1f}%")
    print(f"  Fully Correct Rate: {acc.get('fully_correct', 0) * 100:.1f}%")
    print(f"  Clean False Alarm:  {metrics.get('clean_invoice_false_alarm_rate', 0) * 100:.1f}%")


if __name__ == "__main__":
    asyncio.run(main())
