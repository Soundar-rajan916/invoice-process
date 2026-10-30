# InvoiceFlow: Assumptions & Design Invariants

This document records all domain, technical, and operational assumptions made during the design and implementation of InvoiceFlow (Phases 0–3).

---

## 1. Business & Domain Assumptions

1. **Language & Script:**
   - Invoices are primarily in English (with standard Indian alphanumeric formats for GSTIN, PAN, dates, currency symbols, and item descriptions).
2. **Indian GST Rules:**
   - Buyer is registered in Tamil Nadu (`BUYER_STATE_CODE = "33"` by default, configurable).
   - Intra-state supplies (Supplier state == Buyer state) charge CGST and SGST equally (`cgst == sgst`).
   - Inter-state supplies (Supplier state != Buyer state) charge IGST (`cgst = 0`, `sgst = 0`).
   - Financial year in India runs from April 1 to March 31. For example, `2026-03-31` belongs to `2025-26`, while `2026-04-01` belongs to `2026-27`.
   - GSTIN is a 15-character alphanumeric string following the statutory checksum algorithm (MOD 36 weight 1 and 2 check character).
3. **Number & Date Formats:**
   - Dates on Indian invoices are printed in day-first format (e.g., `DD/MM/YYYY`, `DD-MM-YYYY`, `DD Mon YYYY`, `YYYY-MM-DD`).
   - Number strings may contain Indian digit grouping (e.g., `1,23,456.50`). The extraction and parsing pipelines normalize these to standard decimal strings (`123456.50`).
4. **Tolerance Limits:**
   - Fractional rounding differences up to ₹0.01 per line calculation (`abs(qty * rate - amount) <= 0.01`) and up to ₹1.00 on total invoice rounding (`abs(taxable + taxes - total) <= 1.00`) are acceptable in practice due to line-level rounding conventions.

---

## 2. System & Architecture Assumptions

1. **R1 (Multipage & Degraded Inputs):**
   - Invoices with clear text layers (digital PDFs with >= 80 characters per page) utilize the faster, cost-effective LLM text extraction route.
   - Scanned PDFs or photos utilize the vision extraction route.
   - Extremely blurry images (variance of the Laplacian below `BLUR_REJECT_THRESHOLD = 50.0`) are automatically routed to `RESEND_REQUESTED` to save token costs and prevent incorrect processing.
2. **R2 (Zero Unreviewed Financial Data):**
   - Under no circumstances can an invoice bypass human verification. The state machine strictly mandates that every invoice reaches `NEEDS_REVIEW` before any human transition to `APPROVED`.
   - The PostgreSQL database enforces this with a hard `CHECK` constraint: `status NOT IN ('PUSHING', 'PUSHED') OR (approved_by IS NOT NULL AND approved_extraction_id IS NOT NULL)`.
   - If an invoice is edited after being marked `APPROVED` (but prior to being pushed), its status automatically reverts to `NEEDS_REVIEW`.
   - Approvals of invoices containing remaining validation `error` issues require an explicit human override with an `override_reason` (minimum 10 characters), recorded immutably in the audit log.
3. **R3 (Deduplication):**
   - Three-tier duplicate defense:
     1. *Layer 1 (Byte-level):* Exact SHA-256 match on uploaded file halts processing immediately, registers a `duplicate_file_skipped` audit event, and references the existing invoice.
     2. *Layer 2 (Business Key):* Normalized invoice number (`INV-0042` -> `INV42`), supplier GSTIN, and Indian Financial Year form a partial unique index in PostgreSQL (`WHERE dup_of_id IS NULL AND status NOT IN ('REJECTED', 'REJECTED_DUPLICATE')`).
     3. *Layer 3 (Fuzzy Match):* Matching supplier GSTIN, identical total amount, and identical invoice date with distinct invoice numbers generate a `possible_duplicate` warning.
4. **R4 (Scale & Month-End Spikes):**
   - Celery workers use `acks_late=True` and `worker_prefetch_multiplier=1` to guarantee fair task distribution and prevent task starvation during 4x volume spikes.
   - LLM concurrency is guarded by a system-wide `asyncio.Semaphore` (`GROQ_MAX_CONCURRENCY`) to prevent rate-limit exhaustion.
   - Database updates on invoice status utilize compare-and-set queries (`UPDATE invoices SET status = :new_status WHERE id = :id AND status = :expected_status`) preventing race conditions across concurrent Celery workers.

---

## 3. Security & Operational Assumptions

1. **Authentication & Session:**
   - Reviewer and admin authentication uses Argon2id password hashing.
   - Sessions are managed via short-lived JWTs stored in `HttpOnly`, `SameSite=Strict` cookies.
   - State-changing API endpoints enforce a CSRF protection header (`X-Requested-With: XMLHttpRequest`).
2. **Accounting API Integration:**
   - The downstream accounting system expects `POST /api/invoices` with an `Idempotency-Key` header computed as `sha256(supplier_gstin|normalized_invoice_number|financial_year)`.
   - The mock accounting service simulates transient failures (`500` and `429`) to verify exponential backoff retries.
3. **Storage Retention:**
   - Original files in MinIO are immutable (`originals/{sha256[:2]}/{sha256}`).
   - Audit logs in PostgreSQL are append-only; an explicit database trigger prevents `UPDATE` or `DELETE` operations on `review_events`.


---

## 4. Phase 4 Assumptions (Real Intake & Extraction Safety)

1. **Email Poller (R1, R3):**
   - Inbound email polling uses IMAP over TLS with idempotent tracking on `Message-ID` in the `inbound_messages` table. Re-polling a folder never creates duplicate records or reprocesses attachments.
   - Attachments with inline disposition and size < `EMAIL_MIN_ATTACHMENT_BYTES` (5 KB), or dimensions < `EMAIL_MIN_IMAGE_PIXELS` (100 px), or matching `LOGO_PATTERN` (`image001.png`, `logo`, `signature`) are classified as non-invoice artifacts and ignored.
   - Corrupt or password-encrypted PDFs immediately transition to `RESEND_REQUESTED` without crashing the poller, and generate an outbound resend notification.
   - Successfully processed emails are moved to the `Processed` folder (or `Failed` on unrecoverable error).

2. **WhatsApp Intake (R1, R3):**
   - WhatsApp Cloud API webhooks verify the `X-Hub-Signature-256` HMAC header using constant-time comparison against `WHATSAPP_APP_SECRET`. Non-matching signatures are rejected with HTTP 401 before payload inspection.
   - Multiple photos sent within `WHATSAPP_GROUP_WINDOW_SECONDS` (90 s) from the same sender phone number are aggregated into a single multi-page invoice.
   - Reviewers can split grouped photo invoices via `POST /api/v1/invoices/{id}/split-pages`.

3. **Transactional Outbox & Resend Safety (R2):**
   - Outbound notifications for resend requests are inserted atomically in `outbound_messages` within the same database transaction as the status transition.
   - Notification text templates (`backend/app/templates/`) include only rejection reasons, guidance on photo quality/encryption, and support contact details. **Under no circumstances do outbound messages disclose extracted amounts or financial figures.**
   - Per-sender rate limiting (`RESEND_MAX_PER_SENDER_PER_DAY = 3`) prevents vendor notification spamming.

4. **Safety Net Grounding (R2):**
   - Digital PDFs with text streams run a strict grounding verification pass: all extracted financial amounts, invoice numbers, and GSTINs must appear in the normalized document text, or raise a blocking `not_in_source` error.
   - When `SECOND_OPINION_ENABLED=true`, disagreement on total amount between primary and secondary extraction models raises an `extractors_disagree` warning and preserves both models' outputs for human review.

---

## 5. Phase 5 Assumptions (Reliability, Scale, and Invariants)

1. **Review Leases (R4 Reviewer Isolation):**
   - Review leases default to 120 seconds TTL with a client heartbeat interval of 45 seconds.
   - Any concurrent write operation on an invoice claimed by another reviewer fails with HTTP 409 Conflict.
   - Reviewers may explicitly claim, release, or take over expired or active leases (with audit logging of takeovers).
   - The UI displays an `--accent-soft` warning banner when another user holds an active claim.

2. **Adaptive Limiter & Circuit Breaker (R4 Backpressure):**
   - Rate limiting uses AIMD (Additive Increase, Multiplicative Decrease): backs off by 50% on HTTP 429 and steps up capacity gradually upon sustained HTTP 200 responses.
   - Circuit breakers for external APIs (Groq, Accounting API) enter `OPEN` state after 5 consecutive failures, fast-failing downstream requests directly to `PUSH_FAILED` or `WAITING_PROVIDER` to prevent resource exhaustion.
   - Recovery follows half-open canary probes after a cooldown window (default 30 seconds).

3. **Queue Topology & Watchdog Recovery (R4 Resilience):**
   - Celery tasks are partitioned into isolated queues: `ingest`, `extract`, `push`, `notify`, `maintenance`.
   - The watchdog periodic task sweeps invoices stuck in `PROCESSING` (> 5 min) or `PUSHING` (> 2 min). It requeues up to 3 times before transitioning the invoice to `FAILED` with `status_reason="watchdog_timeout"`.

4. **Reconciliation & Dead-Letter Auditing (R2 Accounting Safety):**
   - Nightly reconciliation queries the accounting API and compares its ledger against local `PUSHED` invoices.
   - Discrepancies (unregistered pushes, amount mismatches, status divergences) produce persistent `reconciliation_findings` records.
   - Invoices in `PUSH_FAILED` and `FAILED` can be reviewed and retried or discarded from the Admin Dead-Letter interface with mandatory audit reasons.

