from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from pydantic import BaseModel, Field, field_serializer, field_validator, model_validator


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
    buyer_name: str | None = None
    buyer_gstin: str | None = None
    line_items: list[LineItem] = Field(default_factory=list)
    taxable_value: Decimal | None = None
    cgst: Decimal | None = None
    sgst: Decimal | None = None
    igst: Decimal | None = None
    total: Decimal | None = None
    field_confidence: dict[str, float] = Field(default_factory=dict)
    unreadable_fields: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def normalize_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        
        # Normalize supplier / seller aliases
        if not data.get("supplier_name"):
            data["supplier_name"] = data.get("seller_name") or data.get("vendor_name") or data.get("issuer_name")
        if not data.get("supplier_gstin"):
            data["supplier_gstin"] = data.get("seller_gstin") or data.get("vendor_gstin") or data.get("issuer_gstin")
            
        # Normalize buyer / customer aliases
        if not data.get("buyer_name"):
            data["buyer_name"] = data.get("customer_name") or data.get("recipient_name") or data.get("billed_to_name")
        if not data.get("buyer_gstin"):
            data["buyer_gstin"] = data.get("customer_gstin") or data.get("recipient_gstin") or data.get("billed_to_gstin")
            
        # Normalize invoice number aliases
        if not data.get("invoice_number"):
            data["invoice_number"] = data.get("invoice_no") or data.get("bill_no") or data.get("bill_number")
            
        return data

    @field_validator("taxable_value", "cgst", "sgst", "igst", "total", mode="before")
    @classmethod
    def validate_totals(cls, v: Any) -> Decimal | None:
        return parse_money(v)

    @field_serializer("taxable_value", "cgst", "sgst", "igst", "total")
    def serialize_money(self, v: Decimal | None) -> str | None:
        return format_money(v)
