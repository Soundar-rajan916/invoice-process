from __future__ import annotations

import re
from dataclasses import dataclass

from app.extraction.preprocess import ProcessedPage

PAGE_X_OF_Y_REGEX = re.compile(r"page\s+(\d+)\s+(?:of|/)\s+(\d+)", re.IGNORECASE)
INVOICE_NUMBER_REGEX = re.compile(
    r"(?:invoice\s*(?:no|#|\.)|bill\s*no\.?|tax\s*invoice)\s*[:#]?\s*([A-Za-z0-9/-]{3,30})",
    re.IGNORECASE,
)


@dataclass
class InvoicePageGroup:
    pages: list[ProcessedPage]
    page_count: int
    detected_invoice_number: str | None = None


class PageGrouper:
    """Heuristic page grouping engine that detects multi-page invoices
    and splits multi-invoice batch documents into separate invoice records.
    """

    @classmethod
    def group_pages(cls, pages: list[ProcessedPage]) -> list[InvoicePageGroup]:
        if not pages:
            return []

        # If only 1 page, trivial single-page invoice
        if len(pages) == 1:
            inv_num = cls._find_invoice_number(pages[0].text)
            return [InvoicePageGroup(pages=pages, page_count=1, detected_invoice_number=inv_num)]

        # Check if digital text is available
        all_digital = all(p.is_digital for p in pages)
        if not all_digital:
            # For scanned / non-digital pages, assume single multi-page invoice
            return [InvoicePageGroup(pages=pages, page_count=len(pages))]

        groups: list[list[ProcessedPage]] = []
        current_group: list[ProcessedPage] = []
        current_inv_num: str | None = None

        for page in pages:
            inv_num = cls._find_invoice_number(page.text)
            page_match = PAGE_X_OF_Y_REGEX.search(page.text)

            is_new_invoice = False
            if page_match:
                current_p = int(page_match.group(1))
                if current_p == 1 and current_group:
                    is_new_invoice = True
            elif inv_num and current_inv_num and inv_num != current_inv_num:
                is_new_invoice = True

            if is_new_invoice:
                groups.append(current_group)
                current_group = [page]
                current_inv_num = inv_num
            else:
                current_group.append(page)
                if not current_inv_num and inv_num:
                    current_inv_num = inv_num

        if current_group:
            groups.append(current_group)

        return [
            InvoicePageGroup(
                pages=g,
                page_count=len(g),
                detected_invoice_number=cls._find_invoice_number(g[0].text),
            )
            for g in groups
        ]

    @staticmethod
    def _find_invoice_number(text: str) -> str | None:
        match = INVOICE_NUMBER_REGEX.search(text)
        if match:
            return match.group(1).strip()
        return None
