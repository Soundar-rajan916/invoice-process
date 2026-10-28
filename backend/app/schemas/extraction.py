from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator


def format_money(val: Decimal | None) -> str | None:
    if val is None:
        return None
    return f"{Decimal(val).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"


def parse_money(val: Any) -> Decimal | None:
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return Decimal(str(val)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, str):
        # Strip currency symbols, spaces, commas (Indian grouping: 1,23,456.50 -> 123456.50)
        cleaned = val.replace("₹", "").replace("Rs.", "").replace("Rs", "").replace(",", "").strip()
        if not cleaned:
            return None
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if isinstance(val, Decimal):
        return val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return None


class LineItem(BaseModel):
    description: str | None = None
    quantity: Decimal | None = None
    rate: Decimal | None = None
    amount: Decimal | None = None

    @field_validator("quantity", "rate", "amount", mode="before")
    @classmethod
    def validate_amounts(cls, v: Any) -> Decimal | None:
        return parse_money(v)

    @field_serializer("quantity", "rate", "amount")
    def serialize_money(self, v: Decimal | None) -> str | None:
        return format_money(v)


class InvoiceExtraction(BaseModel):
    invoice_number: str | None = None
    invoice_date: date | None = None
    supplier_name: str | None = None
    supplier_gstin: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    taxable_value: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    total: Decimal | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    unreadable_fields: list[str] = Field(default_factory=list)

    @field_validator("taxable_value", "cgst", "sgst", "igst", "total", mode="before")
    @classmethod
    def validate_totals(cls, v: Any) -> Decimal | None:
        return parse_money(v)

    @field_serializer("taxable_value", "cgst", "sgst", "igst", "total")
    def serialize_money(self, v: Decimal | None) -> str | None:
        return format_money(v)
