from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from rapidfuzz import fuzz

from app.core.config import settings
from app.schemas.extraction import InvoiceExtraction

GST_CHARS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GSTIN_FORMAT_REGEX = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


@dataclass
class ValidationIssueDto:
    code: str
    field: str | None
    severity: str  # error | warning
    message: str


def compute_gstin_check_char(first14: str) -> str:
    """Statutory Indian GSTIN checksum algorithm (mod 36 with weight 1 and 2)."""
    total = 0
    for i, ch in enumerate(first14.upper()):
        if ch not in GST_CHARS:
            return ""
        v = GST_CHARS.index(ch) * (1 if i % 2 == 0 else 2)
        total += v // 36 + v % 36
    return GST_CHARS[(36 - total % 36) % 36]


def is_valid_gstin_checksum(gstin: str) -> bool:
    if len(gstin) != 15:
        return False
    expected_char = compute_gstin_check_char(gstin[:14])
    return gstin[14].upper() == expected_char


def validate_gstin_checksum(gstin: str) -> bool:
    return is_valid_gstin_checksum(gstin)


def validate_gstin_format(gstin: str) -> bool:
    return bool(GSTIN_FORMAT_REGEX.match(gstin.strip().upper()))


def normalize_text_for_grounding(text: str) -> str:
    """Normalizes Indian number grouping, currency symbols, and whitespace."""
    t = text.lower()
    for symbol in ("₹", "rs.", "rs", "inr"):
        t = t.replace(symbol, " ")
    # Remove commas between digits (Indian format 1,23,456.78 -> 123456.78)
    t = re.sub(r"(\d),(\d)", r"\1\2", t)
    t = re.sub(r"\s+", " ", t)
    return t


def is_value_in_text(value_str: str, norm_text: str) -> bool:
    """Checks whether a string or formatted number appears in normalized text."""
    v = value_str.strip().lower()
    if not v:
        return True
    clean_v = re.sub(r"[, \-\/]", "", v)
    text_no_punct = re.sub(r"[, \-\/]", "", norm_text)
    return clean_v in text_no_punct


def validate_grounding(extraction: InvoiceExtraction, source_text: str) -> list[ValidationIssueDto]:
    """Safety net check for digital PDFs (R2).
    Verifies that every extracted amount, invoice number, and GSTIN actually appears in document text.
    Catches invented numbers before human reviewers see them.
    """
    issues: list[ValidationIssueDto] = []
    norm_text = normalize_text_for_grounding(source_text)

    # 1. Invoice Number
    if extraction.invoice_number and not is_value_in_text(extraction.invoice_number, norm_text):
        issues.append(
            ValidationIssueDto(
                "not_in_source",
                "invoice_number",
                "error",
                f"Extracted invoice number '{extraction.invoice_number}' not found in document text",
            )
        )

    # 2. Supplier GSTIN
    if extraction.supplier_gstin and not is_value_in_text(extraction.supplier_gstin, norm_text):
        issues.append(
            ValidationIssueDto(
                "not_in_source",
                "supplier_gstin",
                "error",
                f"Extracted supplier GSTIN '{extraction.supplier_gstin}' not found in document text",
            )
        )

    # 3. Key financial amounts
    amount_fields = [
        ("taxable_value", extraction.taxable_value),
        ("cgst", extraction.cgst),
        ("sgst", extraction.sgst),
        ("igst", extraction.igst),
        ("total", extraction.total),
    ]
    for field_name, amount in amount_fields:
        if amount is not None and amount > Decimal("0.00"):
            str_val_2dec = f"{amount:.2f}"
            str_val_0dec = f"{amount:.0f}"
            if not (is_value_in_text(str_val_2dec, norm_text) or is_value_in_text(str_val_0dec, norm_text)):
                issues.append(
                    ValidationIssueDto(
                        "not_in_source",
                        field_name,
                        "error",
                        f"Extracted {field_name} '₹{amount:.2f}' not found in document text",
                    )
                )

    # 4. Line item amounts
    for idx, item in enumerate(extraction.line_items):
        if item.amount is not None and item.amount > Decimal("0.00"):
            amt_str = f"{item.amount:.2f}"
            amt_str0 = f"{item.amount:.0f}"
            if not (is_value_in_text(amt_str, norm_text) or is_value_in_text(amt_str0, norm_text)):
                issues.append(
                    ValidationIssueDto(
                        "not_in_source",
                        f"line_items[{idx}].amount",
                        "error",
                        f"Line item {idx+1} amount '₹{item.amount:.2f}' not found in document text",
                    )
                )

    return issues


def validate_extraction(
    extraction: InvoiceExtraction,
    known_suppliers: dict[str, str] | None = None,  # gstin -> supplier_name
    min_page_blur: float | None = None,
    current_date: date | None = None,
    source_text: str | None = None,
) -> list[ValidationIssueDto]:
    """Pure, deterministic validation engine enforcing R2 financial accuracy rules."""
    issues: list[ValidationIssueDto] = []
    today = current_date or date.today()

    amount_tol = Decimal(str(settings.AMOUNT_TOLERANCE))
    total_tol = Decimal(str(settings.TOTAL_ROUNDING_TOLERANCE))
    buyer_state = settings.BUYER_STATE_CODE

    # 1. missing_field
    if not extraction.invoice_number:
        issues.append(
            ValidationIssueDto(
                "missing_field", "invoice_number", "error", "Invoice number is missing or null"
            )
        )
    if not extraction.invoice_date:
        issues.append(
            ValidationIssueDto(
                "missing_field", "invoice_date", "error", "Invoice date is missing or null"
            )
        )
    if not extraction.supplier_name:
        issues.append(
            ValidationIssueDto(
                "missing_field", "supplier_name", "error", "Supplier name is missing or null"
            )
        )
    if not extraction.supplier_gstin:
        issues.append(
            ValidationIssueDto(
                "missing_field", "supplier_gstin", "error", "Supplier GSTIN is missing or null"
            )
        )
    if extraction.total is None:
        issues.append(
            ValidationIssueDto(
                "missing_field", "total", "error", "Invoice total amount is missing or null"
            )
        )
    if not extraction.line_items:
        issues.append(
            ValidationIssueDto(
                "missing_field", "line_items", "error", "Invoice contains no line items"
            )
        )

    # 2. gstin_checksum & format
    if extraction.supplier_gstin:
        gstin_clean = extraction.supplier_gstin.strip().upper()
        if not validate_gstin_format(gstin_clean):
            issues.append(
                ValidationIssueDto(
                    "gstin_format",
                    "supplier_gstin",
                    "error",
                    f"Supplier GSTIN '{gstin_clean}' does not match statutory format (2-digit state code + 10-char PAN + 3-char entity code)",
                )
            )
        elif not is_valid_gstin_checksum(gstin_clean):
            issues.append(
                ValidationIssueDto(
                    "gstin_checksum",
                    "supplier_gstin",
                    "error",
                    f"Supplier GSTIN '{gstin_clean}' checksum character '{gstin_clean[-1]}' is invalid",
                )
            )

    # 3. line_amount_mismatch
    sum_line_amounts = Decimal("0.00")
    for idx, item in enumerate(extraction.line_items):
        if item.quantity is not None and item.rate is not None and item.amount is not None:
            expected_amt = item.quantity * item.rate
            if abs(expected_amt - item.amount) > amount_tol:
                issues.append(
                    ValidationIssueDto(
                        "line_amount_mismatch",
                        f"line_items[{idx}].amount",
                        "error",
                        f"Line item {idx+1} amount ({item.amount:.2f}) != qty ({item.quantity:.2f}) * rate ({item.rate:.2f}) = {expected_amt:.2f}",
                    )
                )
        if item.amount is not None:
            sum_line_amounts += item.amount

    # 4. taxable_mismatch
    if extraction.taxable_value is not None:
        if abs(sum_line_amounts - extraction.taxable_value) > amount_tol:
            issues.append(
                ValidationIssueDto(
                    "taxable_mismatch",
                    "taxable_value",
                    "error",
                    f"Sum of line amounts ({sum_line_amounts:.2f}) does not match taxable value ({extraction.taxable_value:.2f})",
                )
            )

    # 5. total_mismatch
    base_taxable = (
        extraction.taxable_value if extraction.taxable_value is not None else sum_line_amounts
    )
    cgst = extraction.cgst or Decimal("0.00")
    sgst = extraction.sgst or Decimal("0.00")
    igst = extraction.igst or Decimal("0.00")
    calculated_total = base_taxable + cgst + sgst + igst

    if extraction.total is not None:
        diff = calculated_total - extraction.total
        if abs(diff) > total_tol:
            issues.append(
                ValidationIssueDto(
                    "total_mismatch",
                    "total",
                    "error",
                    f"Taxable ({base_taxable:.2f}) + CGST ({cgst:.2f}) + SGST ({sgst:.2f}) + IGST ({igst:.2f}) = {calculated_total:.2f}, but extracted total is {extraction.total:.2f} (diff: ₹{abs(diff):.2f})",
                )
            )

    # 6. tax_type_mismatch and cgst_sgst_unequal
    if extraction.supplier_gstin and len(extraction.supplier_gstin) >= 2:
        supplier_state = extraction.supplier_gstin[:2]
        if supplier_state == buyer_state:
            # Intra-state: CGST & SGST expected, IGST should be 0
            if igst > amount_tol:
                issues.append(
                    ValidationIssueDto(
                        "tax_type_mismatch",
                        "igst",
                        "warning",
                        f"Intra-state transaction (state {supplier_state}) should not charge IGST",
                    )
                )
        else:
            # Inter-state: IGST expected, CGST/SGST should be 0
            if cgst > amount_tol or sgst > amount_tol:
                issues.append(
                    ValidationIssueDto(
                        "tax_type_mismatch",
                        "cgst",
                        "warning",
                        f"Inter-state transaction (supplier state {supplier_state} vs buyer {buyer_state}) should charge IGST, not CGST/SGST",
                    )
                )

    if abs(cgst - sgst) > amount_tol:
        issues.append(
            ValidationIssueDto(
                "cgst_sgst_unequal",
                "cgst",
                "warning",
                f"CGST ({cgst:.2f}) and SGST ({sgst:.2f}) differ by more than tolerance",
            )
        )

    # 7. date_invalid
    if extraction.invoice_date:
        if extraction.invoice_date > today:
            issues.append(
                ValidationIssueDto(
                    "date_invalid",
                    "invoice_date",
                    "error",
                    f"Invoice date {extraction.invoice_date} is in the future",
                )
            )
        elif extraction.invoice_date < (today - timedelta(days=365)):
            issues.append(
                ValidationIssueDto(
                    "date_invalid",
                    "invoice_date",
                    "warning",
                    f"Invoice date {extraction.invoice_date} is more than 1 year in the past",
                )
            )

    # 8. unknown_supplier / supplier_name_differs
    if known_suppliers is not None and extraction.supplier_gstin:
        known_name = known_suppliers.get(extraction.supplier_gstin)
        if not known_name:
            issues.append(
                ValidationIssueDto(
                    "unknown_supplier",
                    "supplier_gstin",
                    "warning",
                    f"Supplier with GSTIN '{extraction.supplier_gstin}' is not registered in the supplier master",
                )
            )
        elif extraction.supplier_name:
            ratio = fuzz.ratio(extraction.supplier_name.lower(), known_name.lower())
            if ratio < 70:
                issues.append(
                    ValidationIssueDto(
                        "supplier_name_differs",
                        "supplier_name",
                        "warning",
                        f"Supplier name '{extraction.supplier_name}' differs from known name '{known_name}' (similarity {ratio:.0f}%)",
                    )
                )

    # 9. low_confidence
    low_conf_thresh = settings.LOW_CONFIDENCE_THRESHOLD
    for field_name, conf in extraction.field_confidence.items():
        if conf < low_conf_thresh:
            issues.append(
                ValidationIssueDto(
                    "low_confidence",
                    field_name,
                    "warning",
                    f"Field '{field_name}' extraction confidence is low ({conf:.2f})",
                )
            )
    if extraction.unreadable_fields:
        issues.append(
            ValidationIssueDto(
                "low_confidence",
                None,
                "warning",
                f"Document contains illegible or uncertain fields: {', '.join(extraction.unreadable_fields)}",
            )
        )

    # 10. low_image_quality
    if min_page_blur is not None and min_page_blur < settings.BLUR_REJECT_THRESHOLD * 1.5:
        issues.append(
            ValidationIssueDto(
                "low_image_quality",
                None,
                "warning",
                f"Page image quality is low (Laplacian variance {min_page_blur:.1f})",
            )
        )

    # 11. Grounding check (R2) for digital PDFs
    if source_text:
        grounding_issues = validate_grounding(extraction, source_text)
        issues.extend(grounding_issues)

    return issues
