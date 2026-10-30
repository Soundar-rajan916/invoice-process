# Document Preprocessing & Quality Calibration (R1)

InvoiceFlow hardens preprocessing on all inbound documents (PDFs, mobile phone photos, and camera scans) to maximize OCR and LLM extraction accuracy while rejecting illegible inputs before human reviewers spend costly time.

---

## 1. Preprocessing Pipeline Stages

1. **Document Detection & Perspective Correction**
   - Detects the largest quadrilateral contour with high area relative to image canvas.
   - Computes four-point geometric perspective transformation (`cv2.getPerspectiveTransform` + `cv2.warpPerspective`) to flatten tilted or angled phone camera shots into a top-down planar scan.
   - Maintains aspect ratio and crops away irrelevant surface backgrounds (wooden desks, floor tiles, shadows).

2. **Shadow & Background Normalization**
   - Applies morphological dilation (`cv2.morphologyEx` with 7×7 ellipse structuring element) to estimate non-uniform background illumination.
   - Performs background division normalisation (`cv2.divide(gray, bg)`) followed by histogram stretch.
   - Evens out uneven smartphone flashlights and ambient lighting gradients across document folds.

3. **Auto-Rotation & Deskewing**
   - Hough line transform (`cv2.HoughLinesP`) computes dominant text line angles.
   - Compensates small skew angles within \([-15^\circ, +15^\circ]\).
   - Detects upside-down or 90/180/270 degree rotation orientation.

4. **Multi-Invoice PDF Boundary Splitting**
   - When a multi-page PDF contains distinct invoices, `PageGrouper` tracks changes in invoice numbers, supplier GSTINs, and "Invoice / Tax Invoice" header occurrences between consecutive pages.
   - Automatically splits batches into distinct invoice entities.

---

## 2. Page Quality Metrics & Calibrated Thresholds

Every page is scored across multiple visual quality dimensions before extraction:

| Metric | Measurement Technique | Acceptable Threshold | Action on Failure |
| :--- | :--- | :--- | :--- |
| **Blur Score** | Variance of Laplacian (`cv2.Laplacian(gray).var()`) | \(\ge 30.0\) | Mark `RESEND_REQUESTED` (blurry document) |
| **Brightness** | Mean 8-bit pixel intensity \(\mu\) | \(40.0 \le \mu \le 235.0\) | Flag warning in validation issues |
| **Contrast** | Standard deviation of pixel intensities \(\sigma\) | \(\sigma \ge 25.0\) | Flag warning in validation issues |
| **Resolution** | Minimum page pixel dimensions | \(\min(W, H) \ge 600\text{px}\) | Flag low resolution |
| **Composite Quality** | Weighted formula: \(0.5 \cdot \text{norm\_blur} + 0.3 \cdot \text{contrast} + 0.2 \cdot \text{brightness}\) | \(\ge 0.40\) | Threshold calibrated by eval harness |

---

## 3. Grounding Verification (Safety Net R2)

For digital PDFs with text streams, extracted values (invoice number, supplier GSTIN, line item amounts, taxable subtotal, CGST/SGST/IGST, total) are verified against the document's text:
- Indian number grouping (e.g. `1,23,456.78` vs `123456.78`) and currency symbols (`₹`, `Rs.`, `INR`) are normalized.
- Any extracted figure that does not appear in the source text generates an immediate `not_in_source` blocking error.
- Halts invented or hallucinated amounts before they ever reach human reviewers or accounting systems.
