from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from eval.augment import augment_image
from eval.metrics import (
    InvoiceEvalSample,
    compute_aggregate_metrics,
    decimal_match,
    evaluate_sample,
    match_line_items,
)


def test_decimal_match():
    assert decimal_match(Decimal("100.00"), Decimal("100.005"), Decimal("0.01")) is True
    assert decimal_match(Decimal("100.00"), Decimal("100.02"), Decimal("0.01")) is False
    assert decimal_match(None, None) is True
    assert decimal_match(Decimal("100"), None) is False


def test_line_item_matching_hungarian():
    gt_lines = [
        {"description": "Industrial Widget Type A", "quantity": 10, "rate": 50, "amount": 500},
        {"description": "Spare Washer Fasteners", "quantity": 20, "rate": 5, "amount": 100},
    ]

    # In reverse order and with slight description variation
    pred_lines = [
        {"description": "Spare Washer Fastener", "quantity": 20, "rate": 5, "amount": 100},
        {"description": "Industrial Widget Type-A", "quantity": 10, "rate": 50, "amount": 500},
    ]

    res = match_line_items(gt_lines, pred_lines)
    assert res["count_match"] is True
    assert res["all_lines_correct"] is True
    assert res["desc_correct"] == 2
    assert res["qty_correct"] == 2
    assert res["rate_correct"] == 2
    assert res["amount_correct"] == 2


def test_sample_evaluation_hand_built():
    sample = InvoiceEvalSample(
        file="test.pdf",
        layout="classic",
        pages=1,
        input_type="clean_pdf",
        ground_truth={
            "invoice_number": "INV/0042",
            "invoice_date": "2026-03-31",
            "supplier_name": "Acme Industrial Supplies Ltd",
            "supplier_gstin": "27AAPFU0939F1ZV",
            "taxable_value": 1000.00,
            "cgst": 90.00,
            "sgst": 90.00,
            "igst": 0.00,
            "total": 1180.00,
            "line_items": [
                {"description": "Widget", "quantity": 10, "rate": 100, "amount": 1000}
            ],
            "expected_flags": ["total_mismatch"],
        },
        predicted={
            "invoice_number": "INV-42",  # Normalizes to INV42
            "invoice_date": "2026-03-31",
            "supplier_name": "ACME INDUSTRIAL SUPPLIES LTD",
            "supplier_gstin": "27AAPFU0939F1ZV",
            "taxable_value": 1000.00,
            "cgst": 90.00,
            "sgst": 90.00,
            "igst": 0.00,
            "total": 1180.00,
            "line_items": [
                {"description": "Widget", "quantity": 10, "rate": 100, "amount": 1000}
            ],
        },
        validation_issues=[
            {
                "code": "total_mismatch",
                "field": "total",
                "severity": "error",
                "message": "Total mismatch error",
            }
        ],
    )

    ev = evaluate_sample(sample)
    assert ev["norm_invoice_number_match"] is True
    assert ev["supplier_gstin_match"] is True
    assert ev["total_match"] is True
    assert ev["fully_correct"] is True
    assert "total_mismatch" in ev["predicted_flags"]
    assert "total_mismatch" in ev["expected_flags"]

    agg = compute_aggregate_metrics([sample])
    assert agg["accuracies"]["invoice_number"] == 1.0
    assert agg["accuracies"]["total"] == 1.0
    assert agg["flags"]["total_mismatch"]["recall"] == 1.0
    assert agg["flags"]["total_mismatch"]["precision"] == 1.0


def test_augmentation_determinism():
    # Deterministic test: same seed gives identical output image array
    dummy_img = np.zeros((200, 200, 3), dtype=np.uint8)
    dummy_img[50:150, 50:150] = 255  # White box

    aug1 = augment_image(dummy_img, seed=12345)
    aug2 = augment_image(dummy_img, seed=12345)
    assert np.array_equal(aug1, aug2)

    # Different seed gives different result
    aug3 = augment_image(dummy_img, seed=99999)
    assert not np.array_equal(aug1, aug3)
