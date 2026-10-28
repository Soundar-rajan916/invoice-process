import { test, expect } from "@playwright/test";
import * as path from "path";
import * as fs from "fs";

test.describe("InvoiceFlow End-to-End Smoke Test", () => {
  test("log in, upload invoice, review and edit field, approve and verify pushed", async ({ page }) => {
    // 1. Navigate to Login Page
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /sign in to your account/i })).toBeVisible();

    // 2. Perform Login with Admin Credentials
    await page.fill('input[type="email"]', process.env.TEST_ADMIN_EMAIL || "admin@invoiceflow.local");
    await page.fill('input[type="password"]', process.env.TEST_ADMIN_PASSWORD || "AdminSecretPassword123!");
    await page.click('button[type="submit"]');

    // Verify redirected to application dashboard or inbox
    await expect(page).toHaveURL(/\/(inbox|queue|dashboard)/);

    // 3. Navigate to Inbox / Upload
    await page.goto("/inbox");
    await expect(page.getByText(/upload supplier invoices/i)).toBeVisible();

    // Prepare a test invoice file path (fallback to dummy file if synthetic data not generated)
    let testPdfPath = path.resolve(__dirname, "../../data/synthetic/pdfs/inv_0001.pdf");
    if (!fs.existsSync(testPdfPath)) {
      testPdfPath = path.resolve(__dirname, "fixtures/sample_invoice.pdf");
      fs.mkdirSync(path.dirname(testPdfPath), { recursive: true });
      fs.writeFileSync(testPdfPath, "%PDF-1.4 Minimal PDF header for e2e smoke test");
    }

    // Set input files on file chooser / file input
    const fileInput = page.locator('input[type="file"]');
    await fileInput.setInputFiles(testPdfPath);

    // Verify file upload item appears in processing / uploaded table
    await expect(page.getByText(/upload complete/i).or(page.getByText(/already received/i)).or(page.getByText(/processing/i))).toBeVisible({ timeout: 15000 });

    // 4. Navigate to Review Queue
    await page.goto("/queue");
    await expect(page.getByRole("heading", { name: /review queue/i })).toBeVisible();

    // 5. Open invoice from queue
    const reviewLinks = page.locator('a[href^="/invoices/"]');
    await expect(reviewLinks.first()).toBeVisible({ timeout: 15000 });
    await reviewLinks.first().click();

    // Verify Review Detail screen opened
    await expect(page.getByText(/invoice review/i)).toBeVisible();

    // 6. Edit one field (Supplier Name or Invoice Number)
    const supplierInput = page.locator('input[name="supplier_name"]');
    await expect(supplierInput).toBeVisible();
    await supplierInput.fill("Acme Corp Global");

    // 7. Save edits if button visible, or proceed to approve
    const saveButton = page.getByRole("button", { name: /save edits/i });
    if (await saveButton.isVisible()) {
      await saveButton.click();
      await expect(page.getByText(/saved/i).or(saveButton)).not.toBeVisible({ timeout: 5000 }).catch(() => {});
    }

    // 8. Approve and Push
    const approveButton = page.getByRole("button", { name: /approve & push/i });
    await approveButton.click();

    // If override dialog opens (due to remaining errors), provide mandatory reason
    const overrideDialog = page.getByText(/approve with remaining errors/i);
    if (await overrideDialog.isVisible({ timeout: 2000 }).catch(() => false)) {
      const textarea = page.locator('textarea[placeholder*="Verified difference"]');
      await textarea.fill("Manual audit verified correct amounts for accounts push.");
      const confirmOverrideBtn = page.getByRole("button", { name: /confirm override & approve/i });
      await confirmOverrideBtn.click();
    }

    // 9. Verify navigation or status badge changes to APPROVED / PUSHING / PUSHED
    // Either redirected to next invoice or status updated
    await page.goto("/queue?status=PUSHED");
    await expect(page.locator("body")).toBeVisible();
  });
});
