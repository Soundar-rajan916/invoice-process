from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

import numpy as np
from app.services.dedup import normalize_invoice_number
from rapidfuzz import fuzz

try:
    from scipy.optimize import linear_sum_assignment
except Exception:

    def linear_sum_assignment(cost_matrix: Any) -> tuple[list[int], list[int]]:
        """Greedy matching fallback if scipy linear_sum_assignment is unavailable."""
        n_rows = len(cost_matrix)
        n_cols = len(cost_matrix[0]) if n_rows > 0 else 0
        used_cols: set[int] = set()
        row_ind: list[int] = []
        col_ind: list[int] = []
        for r in range(n_rows):
            best_c = -1
            best_cost = float("inf")
            for c in range(n_cols):
                if c not in used_cols and cost_matrix[r, c] < best_cost:
                    best_cost = cost_matrix[r, c]
                    best_c = c
            if best_c != -1:
                used_cols.add(best_c)
                row_ind.append(r)
                col_ind.append(best_c)
        return row_ind, col_ind


def clean_string(s: str | None) -> str:
    if not s:
        return ""
    # Lowercase and remove all punctuation/whitespace
    return re.sub(r"[^\w\s]", "", s).lower().strip()


def decimal_match(
    a: Decimal | None, b: Decimal | None, tolerance: Decimal = Decimal("0.01")
) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    return abs(a - b) <= tolerance


@dataclass
class InvoiceEvalSample:
    file: str
    layout: str
    pages: int
    input_type: str  # clean_pdf | augmented_photo
    ground_truth: dict[str, Any]
    predicted: dict[str, Any] | None
    validation_issues: list[dict[str, Any]] = field(default_factory=list)
    extraction_path: str = "text"
    latency_ms: int = 0
    token_usage: dict[str, Any] = field(default_factory=dict)
    retries_used: int = 0
    repair_retries_used: int = 0
    error: str | None = None


def match_line_items(
    gt_lines: list[dict[str, Any]],
    pred_lines: list[dict[str, Any]],
) -> dict[str, Any]:
    """Matches ground truth line items to predicted line items using Hungarian algorithm on description similarity."""
    n_gt = len(gt_lines)
    n_pred = len(pred_lines)

    if n_gt == 0 and n_pred == 0:
        return {
            "count_match": True,
            "all_lines_correct": True,
            "desc_correct": 0,
            "qty_correct": 0,
            "rate_correct": 0,
            "amount_correct": 0,
            "total_gt_lines": 0,
        }

    count_match = n_gt == n_pred

    if n_gt == 0 or n_pred == 0:
        return {
            "count_match": False,
            "all_lines_correct": False,
            "desc_correct": 0,
            "qty_correct": 0,
            "rate_correct": 0,
            "amount_correct": 0,
            "total_gt_lines": n_gt,
        }

    # Build cost matrix based on negative description similarity
    cost_matrix = np.zeros((n_gt, n_pred))
    for i, gt in enumerate(gt_lines):
        gt_desc = clean_string(gt.get("description", ""))
        for j, pred in enumerate(pred_lines):
            pred_desc = clean_string(pred.get("description", ""))
            sim = fuzz.token_sort_ratio(gt_desc, pred_desc)
            cost_matrix[i, j] = 100.0 - sim

    row_ind, col_ind = linear_sum_assignment(cost_matrix)

    desc_correct = 0
    qty_correct = 0
    rate_correct = 0
    amount_correct = 0
    all_lines_correct = count_match

    matched_pairs = list(zip(row_ind, col_ind, strict=False))
    for i, j in matched_pairs:
        gt = gt_lines[i]
        pred = pred_lines[j]

        # Description fuzzy >= 90
        sim = 100.0 - cost_matrix[i, j]
        d_ok = sim >= 90.0

        # Numeric matches
        def to_dec(val: Any) -> Decimal | None:
            if val is None or val == "":
                return None
            try:
                return Decimal(str(val))
            except Exception:
                return None

        q_ok = decimal_match(to_dec(gt.get("quantity")), to_dec(pred.get("quantity")))
        r_ok = decimal_match(to_dec(gt.get("rate")), to_dec(pred.get("rate")))
        a_ok = decimal_match(to_dec(gt.get("amount")), to_dec(pred.get("amount")))

        if d_ok:
            desc_correct += 1
        if q_ok:
            qty_correct += 1
        if r_ok:
            rate_correct += 1
        if a_ok:
            amount_correct += 1

        if not (d_ok and q_ok and r_ok and a_ok):
            all_lines_correct = False

    return {
        "count_match": count_match,
        "all_lines_correct": all_lines_correct,
        "desc_correct": desc_correct,
        "qty_correct": qty_correct,
        "rate_correct": rate_correct,
        "amount_correct": amount_correct,
        "total_gt_lines": n_gt,
    }


def evaluate_sample(sample: InvoiceEvalSample) -> dict[str, Any]:
    gt = sample.ground_truth
    pred = sample.predicted or {}

    # Exact field matches
    raw_inv_match = (gt.get("invoice_number") or "").strip() == (
        pred.get("invoice_number") or ""
    ).strip()
    norm_inv_match = normalize_invoice_number(gt.get("invoice_number")) == normalize_invoice_number(
        pred.get("invoice_number")
    )
    date_match = str(gt.get("invoice_date") or "") == str(pred.get("invoice_date") or "")
    gstin_match = (gt.get("supplier_gstin") or "").strip().upper() == (
        pred.get("supplier_gstin") or ""
    ).strip().upper()

    def to_dec(val: Any) -> Decimal | None:
        if val is None or val == "":
            return None
        try:
            return Decimal(str(val))
        except Exception:
            return None

    taxable_match = decimal_match(
        to_dec(gt.get("taxable_value")), to_dec(pred.get("taxable_value"))
    )
    cgst_match = decimal_match(to_dec(gt.get("cgst")), to_dec(pred.get("cgst")))
    sgst_match = decimal_match(to_dec(gt.get("sgst")), to_dec(pred.get("sgst")))
    igst_match = decimal_match(to_dec(gt.get("igst")), to_dec(pred.get("igst")))
    total_match = decimal_match(to_dec(gt.get("total")), to_dec(pred.get("total")))

    # Supplier name: clean exact + RapidFuzz ratio
    gt_name = clean_string(gt.get("supplier_name", ""))
    pred_name = clean_string(pred.get("supplier_name", ""))
    name_exact = gt_name == pred_name
    name_fuzzy_ratio = fuzz.ratio(gt_name, pred_name)

    # Line item evaluation
    gt_lines = gt.get("line_items") or []
    pred_lines = pred.get("line_items") or []
    lines_eval = match_line_items(gt_lines, pred_lines)

    # Invoice fully correct: all header fields, money fields, and line items correct
    fully_correct = (
        norm_inv_match
        and date_match
        and gstin_match
        and (name_fuzzy_ratio >= 90)
        and taxable_match
        and cgst_match
        and sgst_match
        and igst_match
        and total_match
        and lines_eval["all_lines_correct"]
    )

    # Flag detection
    expected_flags = set(gt.get("expected_flags") or [])
    predicted_flags = {
        issue.get("code") for issue in sample.validation_issues if issue.get("severity") == "error"
    }

    is_clean = len(expected_flags) == 0
    has_false_alarm = is_clean and len(predicted_flags) > 0

    return {
        "raw_invoice_number_match": raw_inv_match,
        "norm_invoice_number_match": norm_inv_match,
        "invoice_date_match": date_match,
        "supplier_gstin_match": gstin_match,
        "supplier_name_exact": name_exact,
        "supplier_name_ratio": name_fuzzy_ratio,
        "taxable_value_match": taxable_match,
        "cgst_match": cgst_match,
        "sgst_match": sgst_match,
        "igst_match": igst_match,
        "total_match": total_match,
        "lines_eval": lines_eval,
        "fully_correct": fully_correct,
        "expected_flags": list(expected_flags),
        "predicted_flags": list(predicted_flags),
        "is_clean": is_clean,
        "has_false_alarm": has_false_alarm,
    }


def compute_aggregate_metrics(samples: list[InvoiceEvalSample]) -> dict[str, Any]:
    n = len(samples)
    if n == 0:
        return {}

    eval_results = [evaluate_sample(s) for s in samples]

    # Field-level accuracies
    invoice_number_acc = sum(1 for r in eval_results if r["norm_invoice_number_match"]) / n
    raw_invoice_number_acc = sum(1 for r in eval_results if r["raw_invoice_number_match"]) / n
    invoice_date_acc = sum(1 for r in eval_results if r["invoice_date_match"]) / n
    supplier_gstin_acc = sum(1 for r in eval_results if r["supplier_gstin_match"]) / n
    supplier_name_ratio_avg = sum(r["supplier_name_ratio"] for r in eval_results) / n
    supplier_name_exact_acc = sum(1 for r in eval_results if r["supplier_name_exact"]) / n
    taxable_acc = sum(1 for r in eval_results if r["taxable_value_match"]) / n
    cgst_acc = sum(1 for r in eval_results if r["cgst_match"]) / n
    sgst_acc = sum(1 for r in eval_results if r["sgst_match"]) / n
    igst_acc = sum(1 for r in eval_results if r["igst_match"]) / n
    total_acc = sum(1 for r in eval_results if r["total_match"]) / n

    # Line item aggregate metrics
    total_gt_lines = sum(r["lines_eval"]["total_gt_lines"] for r in eval_results)
    line_amount_acc = (
        sum(r["lines_eval"]["amount_correct"] for r in eval_results) / total_gt_lines
        if total_gt_lines > 0
        else 1.0
    )
    line_desc_acc = (
        sum(r["lines_eval"]["desc_correct"] for r in eval_results) / total_gt_lines
        if total_gt_lines > 0
        else 1.0
    )
    line_qty_acc = (
        sum(r["lines_eval"]["qty_correct"] for r in eval_results) / total_gt_lines
        if total_gt_lines > 0
        else 1.0
    )
    line_rate_acc = (
        sum(r["lines_eval"]["rate_correct"] for r in eval_results) / total_gt_lines
        if total_gt_lines > 0
        else 1.0
    )
    all_lines_correct_rate = (
        sum(1 for r in eval_results if r["lines_eval"]["all_lines_correct"]) / n
    )
    fully_correct_rate = sum(1 for r in eval_results if r["fully_correct"]) / n

    # Flag detection metrics (precision & recall per flag)
    target_flags = ["total_mismatch", "gstin_checksum", "line_amount_mismatch", "duplicate"]
    flag_metrics = {}
    for flag in target_flags:
        tp = sum(
            1 for r in eval_results if flag in r["expected_flags"] and flag in r["predicted_flags"]
        )
        fp = sum(
            1
            for r in eval_results
            if flag not in r["expected_flags"] and flag in r["predicted_flags"]
        )
        fn = sum(
            1
            for r in eval_results
            if flag in r["expected_flags"] and flag not in r["predicted_flags"]
        )
        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
        flag_metrics[flag] = {
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
        }

    clean_samples = [r for r in eval_results if r["is_clean"]]
    false_alarm_rate = (
        sum(1 for r in clean_samples if r["has_false_alarm"]) / len(clean_samples)
        if clean_samples
        else 0.0
    )

    # Operational metrics
    latencies = [s.latency_ms for s in samples if s.latency_ms > 0]
    p50_latency = float(np.percentile(latencies, 50)) if latencies else 0.0
    p95_latency = float(np.percentile(latencies, 95)) if latencies else 0.0

    total_tokens = sum(s.token_usage.get("total_tokens", 0) for s in samples)
    avg_tokens = total_tokens / n if n > 0 else 0

    total_retries = sum(s.retries_used for s in samples)
    total_repairs = sum(s.repair_retries_used for s in samples)
    errors_count = sum(1 for s in samples if s.error is not None)
    error_rate = errors_count / n

    text_path_count = sum(1 for s in samples if s.extraction_path == "text")
    vision_path_count = sum(1 for s in samples if s.extraction_path == "vision")

    # Breakdowns by layout, pages, and input_type
    def compute_breakdown(key: str) -> dict[str, Any]:
        groups: dict[str, list[InvoiceEvalSample]] = {}
        for s in samples:
            val = str(getattr(s, key))
            groups.setdefault(val, []).append(s)
        out = {}
        for k, grp in groups.items():
            grp_res = [evaluate_sample(s) for s in grp]
            out[k] = {
                "count": len(grp),
                "fully_correct_rate": round(
                    sum(1 for r in grp_res if r["fully_correct"]) / len(grp), 4
                ),
                "invoice_number_acc": round(
                    sum(1 for r in grp_res if r["norm_invoice_number_match"]) / len(grp), 4
                ),
                "total_acc": round(sum(1 for r in grp_res if r["total_match"]) / len(grp), 4),
            }
        return out

    breakdowns = {
        "layout": compute_breakdown("layout"),
        "pages": compute_breakdown("pages"),
        "input_type": compute_breakdown("input_type"),
    }

    return {
        "sample_count": n,
        "accuracies": {
            "invoice_number": round(invoice_number_acc, 4),
            "raw_invoice_number": round(raw_invoice_number_acc, 4),
            "invoice_date": round(invoice_date_acc, 4),
            "supplier_gstin": round(supplier_gstin_acc, 4),
            "supplier_name_ratio": round(supplier_name_ratio_avg, 2),
            "supplier_name_exact": round(supplier_name_exact_acc, 4),
            "taxable_value": round(taxable_acc, 4),
            "cgst": round(cgst_acc, 4),
            "sgst": round(sgst_acc, 4),
            "igst": round(igst_acc, 4),
            "total": round(total_acc, 4),
            "line_item_amount": round(line_amount_acc, 4),
            "line_item_description": round(line_desc_acc, 4),
            "line_item_quantity": round(line_qty_acc, 4),
            "line_item_rate": round(line_rate_acc, 4),
            "all_lines_correct": round(all_lines_correct_rate, 4),
            "fully_correct": round(fully_correct_rate, 4),
        },
        "flags": flag_metrics,
        "clean_invoice_false_alarm_rate": round(false_alarm_rate, 4),
        "operational": {
            "p50_latency_ms": round(p50_latency, 1),
            "p95_latency_ms": round(p95_latency, 1),
            "avg_tokens": round(avg_tokens, 1),
            "retries_count": total_retries,
            "repair_retries_count": total_repairs,
            "error_rate": round(error_rate, 4),
            "text_path_share": round(text_path_count / n, 4) if n > 0 else 0,
            "vision_path_share": round(vision_path_count / n, 4) if n > 0 else 0,
        },
        "breakdowns": breakdowns,
    }
