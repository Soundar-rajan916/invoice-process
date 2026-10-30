from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.schemas.extraction import InvoiceExtraction, LineItem
from app.services.dedup import normalize_invoice_number
from app.services.validation import (
    compute_gstin_check_char,
    is_valid_gstin_checksum,
    validate_extraction,
)


def test_gstin_sample_validates():
    """R2 test: sample GSTIN 27AAPFU0939F1ZV must validate."""
    assert is_valid_gstin_checksum("27AAPFU0939F1ZV")
    assert compute_gstin_check_char("27AAPFU0939F1Z") == "V"


def test_normalize_invoice_number_rules():
    """R3 test: 'INV-0042', 'inv 42', and ' INV/042 ' all become 'INV42'."""
    assert normalize_invoice_number("INV-0042") == "INV42"
    assert normalize_invoice_number("inv 42") == "INV42"
    assert normalize_invoice_number(" INV/042 ") == "INV42"
    assert normalize_invoice_number("GST/2026/0010") == "GST202610"


def test_validation_rule_missing_fields():
    empty = InvoiceExtraction()
    issues = validate_extraction(empty)
    codes = [i.code for i in issues]
    assert "missing_field" in codes


def test_validation_rule_line_amount_mismatch():
    ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Item A",
                quantity=Decimal("2.00"),
                rate=Decimal("100.00"),
                amount=Decimal("250.00"),
            )
        ],
        taxable_value=Decimal("250.00"),
        total=Decimal("250.00"),
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "line_amount_mismatch" in codes


def test_validation_rule_taxable_mismatch():
    ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Item A",
                quantity=Decimal("2.00"),
                rate=Decimal("100.00"),
                amount=Decimal("200.00"),
            )
        ],
        taxable_value=Decimal("500.00"),
        total=Decimal("500.00"),
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "taxable_mismatch" in codes


def test_validation_rule_total_mismatch():
    ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Item A",
                quantity=Decimal("1.00"),
                rate=Decimal("100.00"),
                amount=Decimal("100.00"),
            )
        ],
        taxable_value=Decimal("100.00"),
        cgst=Decimal("9.00"),
        sgst=Decimal("9.00"),
        total=Decimal("200.00"),  # Expected: 118.00
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "total_mismatch" in codes


def test_validation_rule_total_mismatch_one_rupee_difference():
    # Real case from BAS25094: 9596.88 + 1151.63 = 10748.51, but total on invoice is 10747.51 (diff: 1.00)
    ext = InvoiceExtraction(
        invoice_number="BAS25094",
        invoice_date=date.today(),
        supplier_name="Bhasin and Sons",
        supplier_gstin="07UZHCB9097D7ZA",
        line_items=[
            LineItem(
                description="Steel Padlock 50 mm",
                quantity=Decimal("72.00"),
                rate=Decimal("133.29"),
                amount=Decimal("9596.88"),
            )
        ],
        taxable_value=Decimal("9596.88"),
        igst=Decimal("1151.63"),
        total=Decimal("10747.51"),
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "total_mismatch" in codes
    mismatch_issue = next(i for i in issues if i.code == "total_mismatch")
    assert "diff: ₹1.00" in mismatch_issue.message


def test_validation_rule_total_mismatch_one_paise_strict():
    # Real case from GST3496: 306260.22 + 18375.61 + 18375.61 = 343011.44, but total is 343011.43 (diff: 0.01)
    ext = InvoiceExtraction(
        invoice_number="GST3496",
        invoice_date=date.today(),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[
            LineItem(
                description="Test Item",
                quantity=Decimal("1.00"),
                rate=Decimal("306260.22"),
                amount=Decimal("306260.22"),
            )
        ],
        taxable_value=Decimal("306260.22"),
        cgst=Decimal("18375.61"),
        sgst=Decimal("18375.61"),
        total=Decimal("343011.43"),  # Expected: 343011.44 (diff: 0.01)
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "total_mismatch" in codes
    mismatch_issue = next(i for i in issues if i.code == "total_mismatch")
    assert "diff: ₹0.01" in mismatch_issue.message


def test_validation_rule_gstin_checksum():
    ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZX",  # Bad check character (should be V)
        line_items=[LineItem(description="Item A", quantity=1, rate=100, amount=100)],
        taxable_value=100,
        total=100,
    )
    issues = validate_extraction(ext)
    codes = [i.code for i in issues]
    assert "gstin_checksum" in codes


def test_validation_rule_date_invalid_future_and_past():
    # Future date
    future_ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today() + timedelta(days=5),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[LineItem(description="Item", quantity=1, rate=10, amount=10)],
        taxable_value=10,
        total=10,
    )
    issues_future = validate_extraction(future_ext)
    assert any(i.code == "date_invalid" for i in issues_future)

    # 3 years past date
    past_ext = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today() - timedelta(days=1200),
        supplier_name="Acme",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[LineItem(description="Item", quantity=1, rate=10, amount=10)],
        taxable_value=10,
        total=10,
    )
    issues_past = validate_extraction(past_ext)
    assert any(i.code == "date_invalid" for i in issues_past)


def test_validation_rule_supplier_matching():
    known = {"27AAPFU0939F1ZV": "Reliable Industries Ltd"}

    # Unknown supplier
    ext_unknown = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Unknown Corp",
        supplier_gstin="33AAAAA0000A1Z5",
        line_items=[LineItem(description="Item", quantity=1, rate=10, amount=10)],
        taxable_value=10,
        total=10,
    )
    issues_unk = validate_extraction(ext_unknown, known_suppliers=known)
    assert any(i.code == "unknown_supplier" for i in issues_unk)

    # Known supplier with low fuzzy name match
    ext_mismatch = InvoiceExtraction(
        invoice_number="INV1",
        invoice_date=date.today(),
        supplier_name="Totally Different Title Inc",
        supplier_gstin="27AAPFU0939F1ZV",
        line_items=[LineItem(description="Item", quantity=1, rate=10, amount=10)],
        taxable_value=10,
        total=10,
    )
    issues_diff = validate_extraction(ext_mismatch, known_suppliers=known)
    assert any(i.code == "supplier_name_differs" for i in issues_diff)


def test_synthetic_dataset_flag_mapping():
    """Verifies that generated faulty invoices raise their exact expected flags,
    and clean invoices raise zero error-level issues.
    """
    manifest_path = Path("data/synthetic/manifest.jsonl")
    if not manifest_path.exists():
        pytest.skip("Synthetic manifest not found")

    with open(manifest_path, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            ext = InvoiceExtraction(
                invoice_number=rec["invoice_number"],
                invoice_date=date.fromisoformat(rec["invoice_date"]),
                supplier_name=rec["supplier_name"],
                supplier_gstin=rec["supplier_gstin"],
                line_items=[LineItem(**item) for item in rec["line_items"]],
                taxable_value=rec.get("taxable_value"),
                cgst=rec.get("cgst"),
                sgst=rec.get("sgst"),
                igst=rec.get("igst"),
                total=rec.get("total"),
                field_confidence={"invoice_number": 1.0, "total": 1.0},
            )
            issues = validate_extraction(ext)
            error_codes = [i.code for i in issues if i.severity == "error"]
            expected_flags = set(rec.get("expected_flags", []))

            # Discard 'duplicate' flag from local validation check as duplicate is checked at DB level
            expected_validation_flags = {f for f in expected_flags if f != "duplicate"}

            for flag in expected_validation_flags:
                assert flag in error_codes, (
                    f"Expected flag '{flag}' not found in errors for {rec['file']}"
                )

            if not expected_validation_flags:
                assert len(error_codes) == 0, (
                    f"Clean invoice {rec['file']} produced unexpected errors: {error_codes}"
                )
