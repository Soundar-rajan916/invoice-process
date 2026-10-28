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


def validate_extraction(
    extraction: InvoiceExtraction,
    known_suppliers: dict[str, str] | None = None,  # gstin -> supplier_name
    min_page_blur: float | None = None,
    current_date: date | None = None,
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

    # 2. GSTIN format & checksum
    if extraction.supplier_gstin:
        gstin = extraction.supplier_gstin.strip().upper()
        if not GSTIN_FORMAT_REGEX.match(gstin):
            issues.append(
                ValidationIssueDto(
                    "gstin_format", "supplier_gstin", "error", f"Invalid GSTIN structure '{gstin}'"
                )
            )
        elif not is_valid_gstin_checksum(gstin):
            issues.append(
                ValidationIssueDto(
                    "gstin_checksum",
                    "supplier_gstin",
                    "error",
                    f"GSTIN checksum verification failed for '{gstin}'",
                )
            )

    # 3. Line items and calculations
    sum_line_amounts = Decimal("0.00")
    for idx, item in enumerate(extraction.line_items):
        if not item.description:
            issues.append(
                ValidationIssueDto(
                    "missing_field",
                    f"line_items[{idx}].description",
                    "error",
                    f"Line item {idx + 1} has no description",
                )
            )
        if item.quantity is None:
            issues.append(
                ValidationIssueDto(
                    "missing_field",
                    f"line_items[{idx}].quantity",
                    "error",
                    f"Line item {idx + 1} has no quantity",
                )
            )
        if item.rate is None:
            issues.append(
                ValidationIssueDto(
                    "missing_field",
                    f"line_items[{idx}].rate",
                    "error",
                    f"Line item {idx + 1} has no rate",
                )
            )
        if item.amount is None:
            issues.append(
                ValidationIssueDto(
                    "missing_field",
                    f"line_items[{idx}].amount",
                    "error",
                    f"Line item {idx + 1} has no amount",
                )
            )
        elif item.quantity is not None and item.rate is not None:
            expected_amt = item.quantity * item.rate
            if abs(expected_amt - item.amount) > amount_tol:
                issues.append(
                    ValidationIssueDto(
                        "line_amount_mismatch",
                        f"line_items[{idx}].amount",
                        "error",
                        f"Line {idx + 1}: quantity ({item.quantity}) × rate ({item.rate}) = {expected_amt:.2f}, but amount is {item.amount:.2f}",
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
        if abs(calculated_total - extraction.total) > total_tol:
            issues.append(
                ValidationIssueDto(
                    "total_mismatch",
                    "total",
                    "error",
                    f"Taxable ({base_taxable:.2f}) + CGST ({cgst:.2f}) + SGST ({sgst:.2f}) + IGST ({igst:.2f}) = {calculated_total:.2f}, but extracted total is {extraction.total:.2f}",
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
        elif extraction.invoice_date < today - timedelta(days=730):
            issues.append(
                ValidationIssueDto(
                    "date_invalid",
                    "invoice_date",
                    "error",
                    f"Invoice date {extraction.invoice_date} is more than 2 years in the past",
                )
            )

    # 8. unknown_supplier & supplier_name_differs
    if extraction.supplier_gstin and known_suppliers is not None:
        gstin_clean = extraction.supplier_gstin.strip().upper()
        if gstin_clean not in known_suppliers:
            issues.append(
                ValidationIssueDto(
                    "unknown_supplier",
                    "supplier_gstin",
                    "warning",
                    f"Supplier GSTIN '{gstin_clean}' not found in supplier directory",
                )
            )
        elif extraction.supplier_name:
            known_name = known_suppliers[gstin_clean]
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

    return issues
