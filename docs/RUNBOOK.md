# InvoiceFlow: Operations & Maintenance Runbook

This runbook provides actionable procedures for operators and administrators maintaining InvoiceFlow in production.

---

## 1. Inspecting a Stuck Invoice

An invoice may become "stuck" if Celery workers lose network connectivity during processing, a process is killed abruptly, or the invoice remains in `PROCESSING` or `PUSHING` state without recent activity.

### 1.1 Identifying Stuck Invoices via Database
Connect to PostgreSQL and inspect invoices that have been in an active transient state for over 15 minutes:

```sql
-- Find invoices stuck in PROCESSING or PUSHING for > 15 minutes
SELECT id, status, supplier_gstin, normalized_invoice_number, updated_at
FROM invoices
WHERE status IN ('PROCESSING', 'PUSHING')
  AND updated_at < NOW() - INTERVAL '15 minutes'
ORDER BY updated_at ASC;
```

### 1.2 Inspecting the Audit Trail
Check the full history of the stuck invoice:

```sql
SELECT id, action, actor_id, payload, created_at
FROM review_events
WHERE invoice_id = '<INVOICE_UUID>'
ORDER BY created_at ASC;
```

### 1.3 Reviewing Push Attempts
If the invoice is in `PUSHING` or `PUSH_FAILED`, inspect the push attempt error logs:

```sql
SELECT attempt_no, http_status, error, response, created_at
FROM push_attempts
WHERE invoice_id = '<INVOICE_UUID>'
ORDER BY attempt_no ASC;
```

---

## 2. Retrying Failed Invoices

Invoices can fail during extraction (`FAILED`) or during accounting push (`PUSH_FAILED`).

### 2.1 Using the Admin REST API
Admins can trigger an explicit retry on any `FAILED` or `PUSH_FAILED` invoice using:

```bash
curl -X POST https://api.invoiceflow.example.com/api/v1/invoices/<INVOICE_UUID>/retry \
  -H "Cookie: access_token=<ADMIN_JWT>" \
  -H "X-Requested-With: XMLHttpRequest" \
  -H "Content-Type: application/json"
```

- If `FAILED`: The invoice transitions `FAILED -> PROCESSING` and enqueues a Celery extraction task (`process_invoice`).
- If `PUSH_FAILED`: The invoice transitions `PUSH_FAILED -> APPROVED` and re-enqueues the Celery push task (`push_invoice`).

### 2.2 Using Admin UI
1. Navigate to `/admin` in the web application.
2. Filter or search for invoices with status `FAILED` or `PUSH_FAILED`.
3. Click the **"Retry"** button on the respective row.
4. The system logs an audit event (`action: "retry"`) and triggers background re-execution.

---

## 3. Rotating the Groq API Key

Zero-downtime rotation of the Groq API key:

1. Generate a new API key in the [Groq Cloud Console](https://console.groq.com/keys).
2. Update the environment configuration:
   - In `.env` or Kubernetes Secret / Vault, update `GROQ_API_KEY=<new_key_value>`.
3. Perform a rolling restart of the backend API and worker instances:
   ```bash
   # Docker Compose:
   docker compose up -d --no-deps api worker
   
   # Or in Kubernetes:
   kubectl rollout restart deployment/invoiceflow-api deployment/invoiceflow-worker
   ```
4. Check startup logs (`docker compose logs -f api worker`):
   - Ensure the startup model validation check succeeds (`Available models verified on Groq`).
5. Revoke the old key in the Groq console once traffic confirms active processing.

---

## 4. Handling Groq Outages or Rate-Limit Storms

During month-end spikes (R4), upstream rate limits (HTTP 429) or transient provider outages (HTTP 5xx) may occur.

### 4.1 Symptoms
- Celery worker logs show `RateLimitError` or `APIStatusError: 503 Service Unavailable`.
- Invoices accumulate in `RECEIVED` queue without moving to `NEEDS_REVIEW`.
- `GET /metrics/summary` shows increasing `oldest_unreviewed_age_seconds`.

### 4.2 Built-in Mitigations
1. **Exponential Backoff & Jitter:** `GroqExtractor` automatically respects upstream `Retry-After` headers and applies exponential backoff with random jitter.
2. **Concurrency Limiting:** `GROQ_MAX_CONCURRENCY` caps simultaneous outbound requests per process.
3. **Celery Retries:** Tasks retry up to `CELERY_TASK_MAX_RETRIES` (default 5) with backoff before moving to `FAILED`.

### 4.3 Immediate Operational Interventions
- **Reduce Concurrency:** Lower `GROQ_MAX_CONCURRENCY` (e.g. from 10 to 4) to alleviate rate pressure:
  ```bash
  GROQ_MAX_CONCURRENCY=4 docker compose up -d --no-deps api worker
  ```
- **Scale Out Queue Consumers (Post-Outage Recovery):** Once the provider recovers, scale up Celery workers to clear the accumulated backlog:
  ```bash
  docker compose up -d --scale worker=8
  ```
- **Fallback to Mock Extractor for Disaster Recovery:** If Groq has an extended multi-hour outage, temporarily switch `EXTRACTOR=mock` (if running in test/sandbox) or pause the ingestion queue until service restoration.

---

## 5. Changing LLM Models Safely

Model availability evolves frequently on cloud providers. Never change `GROQ_TEXT_MODEL` or `GROQ_VISION_MODEL` directly in production without validation.

### 5.1 Verification Checklist
1. **Check Groq Console Documentation:** Verify the new model supports JSON mode (`response_format={"type": "json_object"}`) and vision input for image models.
2. **Run the Evaluation Harness:**
   Execute the evaluation pipeline against the candidate model:
   ```bash
   # Set candidate models in environment
   export GROQ_TEXT_MODEL="new-candidate-text-model"
   export GROQ_VISION_MODEL="new-candidate-vision-model"
   
   # Run evaluation on synthetic dataset
   python -m eval.run \
     --manifest data/synthetic/manifest.jsonl \
     --inputs data/synthetic/pdfs \
     --extractor groq \
     --limit 100 \
     --out eval/reports/
     
   # Validate scores against CI thresholds
   python -m eval.check --report eval/reports/report.json
   ```
3. **Threshold Gate Validation:**
   The check requires:
   - `invoice_number` accuracy >= 95%
   - `invoice_date` accuracy >= 95%
   - `supplier_gstin` accuracy >= 97%
   - `total` accuracy >= 97%
   - `line_item_amount` accuracy >= 93%
   - Flag recall for `total_mismatch`, `gstin_checksum`, `line_amount_mismatch` = 100%
   - Clean invoice false alarm rate <= 2%
4. **Deploy Configuration:**
   Update `.env` with the tested model IDs and restart containers.
5. **Verify Startup:**
   The API startup health check (`check_groq_models_at_startup`) will query Groq and fail fast if the model ID is unrecognized.

---

## 6. Database Health & Disk Space

- **MinIO Storage:** Page images (`pages/`) and immutable originals (`originals/`) are stored permanently. Monitor bucket utilization and configure S3 lifecycle policies if archiving older fiscal years.
- **Audit Table Trigger:** The `review_events` table is protected by a trigger blocking `UPDATE` and `DELETE`. Do not attempt administrative pruning of this table.
