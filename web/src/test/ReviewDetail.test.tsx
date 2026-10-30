import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { ReviewDetail } from "../pages/ReviewDetail";
import * as apiModule from "../lib/api";

// Mock the API module
vi.mock("../lib/api", async () => {
  const actual = await vi.importActual("../lib/api");
  return {
    ...actual,
    apiRequest: vi.fn(),
  };
});

const mockInvoiceData = {
  id: "inv-123",
  status: "NEEDS_REVIEW",
  row_version: 1,
  current_extraction: {
    invoice_number: "INV-2026-001",
    invoice_date: "2026-04-15",
    supplier_name: "Acme Industrial Supplies",
    supplier_gstin: "27AAPFU0939F1ZV",
    taxable_value: "1000.00",
    cgst: "90.00",
    sgst: "90.00",
    igst: "0.00",
    total: "1180.00",
    line_items: [
      {
        description: "Widget Alpha",
        quantity: "10.00",
        rate: "100.00",
        amount: "1000.00",
      },
    ],
    field_confidence: {
      total: 0.99,
      invoice_number: 0.98,
    },
    unreadable_fields: [],
  },
  validation_issues: [
    {
      id: "iss-1",
      code: "line_amount_mismatch",
      field: "line_items.0.amount",
      severity: "error",
      message: "Quantity × rate does not equal amount",
      resolved_by_override: false,
    },
    {
      id: "iss-2",
      code: "low_confidence",
      field: "supplier_name",
      severity: "warning",
      message: "Supplier name confidence is low",
      resolved_by_override: false,
    },
  ],
  page_image_urls: [
    { page_number: 1, url: "https://example.com/page1.jpg" },
  ],
};

function renderComponent(invoiceData = mockInvoiceData) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  (apiModule.apiRequest as any).mockImplementation((url: string) => {
    if (url.includes("/api/v1/invoices/inv-123/audit")) {
      return Promise.resolve([]);
    }
    if (url.includes("/api/v1/invoices?status=NEEDS_REVIEW")) {
      return Promise.resolve({
        items: [{ id: "inv-123" }, { id: "inv-124" }],
        total: 2,
      });
    }
    if (url.includes("/api/v1/invoices/inv-123")) {
      return Promise.resolve(invoiceData);
    }
    return Promise.resolve({});
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/invoices/inv-123"]}>
        <Routes>
          <Route path="/invoices/:id" element={<ReviewDetail />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("ReviewDetail Component Tests", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders invoice fields and validation issues panel", async () => {
    renderComponent();

    // Verify invoice fields rendered
    await waitFor(() => {
      expect(screen.getByDisplayValue("INV-2026-001")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Acme Industrial Supplies")).toBeInTheDocument();
      expect(screen.getByDisplayValue("27AAPFU0939F1ZV")).toBeInTheDocument();
    });

    // Verify Issues panel shows both error and warning
    expect(screen.getByText(/1 Blocking Error/i)).toBeInTheDocument();
    expect(screen.getByText(/Quantity × rate does not equal amount/i)).toBeInTheDocument();
    expect(screen.getByText(/1 Warning/i)).toBeInTheDocument();
    expect(screen.getByText(/Supplier name confidence is low/i)).toBeInTheDocument();
  });

  it("handles adding and removing line items", async () => {
    const user = userEvent.setup();
    const { container } = renderComponent();

    await waitFor(() => {
      expect(screen.getByDisplayValue("Widget Alpha")).toBeInTheDocument();
    });

    // Add row
    const addRowBtn = screen.getByRole("button", { name: /add line/i });
    await user.click(addRowBtn);

    // Verify two description inputs exist
    let descInputs = container.querySelectorAll(
      'input[name^="line_items."][name$=".description"]'
    );
    expect(descInputs).toHaveLength(2);

    // Remove row
    const removeButtons = screen.getAllByTitle(/remove row/i);
    expect(removeButtons).toHaveLength(2);
    await user.click(removeButtons[1]);

    await waitFor(() => {
      descInputs = container.querySelectorAll(
        'input[name^="line_items."][name$=".description"]'
      );
      expect(descInputs).toHaveLength(1);
    });
  });

  it("live recalculates total and displays match/mismatch indicator using decimal.js", async () => {
    const { container } = renderComponent();

    await waitFor(() => {
      expect(screen.getByDisplayValue("1180.00")).toBeInTheDocument();
    });

    // Calculated sum: line amount (1000.00) + CGST (90.00) + SGST (90.00) = 1180.00
    expect(screen.getByText("₹1180.00")).toBeInTheDocument();
    expect(screen.getByText(/Matches/i)).toBeInTheDocument();

    // Edit CGST to 190.00
    const cgstInput = container.querySelector('input[name="cgst"]') as HTMLInputElement;
    expect(cgstInput).not.toBeNull();

    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(cgstInput, { target: { value: "190.00" } });

    // Calculated total should update to 1280.00 and show Mismatch
    await waitFor(() => {
      expect(screen.getByText("₹1280.00")).toBeInTheDocument();
      expect(screen.getByText(/Mismatch/i)).toBeInTheDocument();
    });
  });

  it("requires at least 10 chars override reason when approving with remaining errors (R2)", async () => {
    const user = userEvent.setup();
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText(/Approve & Push/i)).toBeInTheDocument();
    });

    // Click Approve button
    const approveBtn = screen.getByRole("button", { name: /approve & push/i });
    await user.click(approveBtn);

    // Because there is a blocking error issue, override dialog must appear
    expect(screen.getByText(/Approve with Remaining Errors/i)).toBeInTheDocument();
    expect(
      screen.getByText(/R2 policy requires an audit override reason/i)
    ).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", {
      name: /confirm override & approve/i,
    });
    expect(confirmBtn).toBeDisabled();

    // Type 5 characters: still disabled
    const textarea = screen.getByPlaceholderText(/e\.g\., Verified difference/i);
    await user.type(textarea, "Short");
    expect(confirmBtn).toBeDisabled();

    // Type 12 characters: becomes enabled
    await user.type(textarea, " override reason");
    expect(confirmBtn).toBeEnabled();

    // Click confirm
    await user.click(confirmBtn);

    // Verify approve API called with override_reason
    expect(apiModule.apiRequest).toHaveBeenCalledWith(
      "/api/v1/invoices/inv-123/approve",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          row_version: 1,
          override_reason: "Short override reason",
        }),
      })
    );
  });
});
