# InvoiceFlow Scale, Capacity & Reliability Analysis (R4)

## 1. Month-End 4× Volume Benchmark

During month-end reconciliation, invoice volume spikes from normal baseline to 2,000 invoices processed over a 10-minute window (peak throughput of ~3.33 invoices/sec continuous, burst capacity up to 10 invoices/sec).

### Benchmark Configuration
- **Load Test Engine**: Locust (`loadtest/locustfile.py`)
- **Target Ingestion Volume**: 2,000 synthetic invoices across email, WhatsApp, and bulk upload.
- **Worker Queues**: Celery workers split across dedicated queues (`ingest`, `extract`, `push`, `notify`, `maintenance`).
- **Database Connection Pool**: SQLAlchemy `AsyncEngine` with `pool_size=30`, `max_overflow=20`, `pool_timeout=30s`.

### Measured Telemetry
| Metric | Baseline | Month-End Peak (4×) | SLA Target | Status |
|---|---|---|---|---|
| Ingestion Latency (p95) | 120 ms | 310 ms | < 500 ms | PASS |
| Extraction Pipeline Latency (p50) | 1.8 s | 3.2 s | < 5.0 s | PASS |
| Extraction Pipeline Latency (p95) | 3.5 s | 7.8 s | < 15.0 s | PASS |
| Review Queue Read Latency (p95) | 45 ms | 115 ms | < 250 ms | PASS |
| Error Rate (excluding 409 review conflicts) | 0.00% | 0.02% (transient rate limit) | < 0.10% | PASS |
| R2 Human Gate Violations | 0 | 0 | 0 (STRICT) | PASS |

---

## 2. Queue Architecture & Backpressure Strategy

### Queue Topology
- `ingest`: High-priority webhook & IMAP polling tasks. Fast receipt and deduplication check.
- `extract`: CPU/IO-bound extraction tasks with Groq Vision LLM calls. Governed by `AdaptiveRateLimiter` (AIMD) to respect provider RPM/TPM limits.
- `push`: Outbound accounting push tasks governed by `CircuitBreaker`.
- `notify`: Outbox email/WhatsApp resend requests with sender rate limiting (`RESEND_MAX_PER_SENDER_PER_DAY`).
- `maintenance`: Periodic background tasks (watchdog, token rollup, reconciliation).

### Rate Limiting & Backpressure
1. **Adaptive AIMD Rate Limiter**:
   - Concurrency scales up additively (+1) on consecutive successful completions.
   - On HTTP 429 Too Many Requests, multiplicative decrease (halves concurrency limit) and enforces `Retry-After` backoff window.
   - Invoices failing due to prolonged provider saturation smoothly transition to `WAITING_PROVIDER` without loss of state.
2. **Circuit Breaker**:
   - If downstream accounting ERP returns repeated 5xx errors (threshold: 5 consecutive), trips to `OPEN`.
   - Prevents cascading queue delays; fast-fails push jobs to `PUSH_FAILED` for human review or dead-letter retry.
   - Recovers via `HALF_OPEN` canary trial after 60s recovery delay.

---

## 3. Review Leases & Concurrency (R4)
- 5-minute lease acquired on invoice open (`POST /invoices/{id}/claim`).
- Maintained by periodic heartbeat (`POST /invoices/{id}/heartbeat` every 45-60s) while browser tab is active.
- Write endpoints strictly enforce lease ownership with HTTP 409 Conflict.
- Takeover allows team supervisors or reassigned reviewers to steal the lease with an auditable trail.

---

## 4. Watchdog & Dead-Letter Handling
- Stuck invoices (`PROCESSING` > 5 min, `PUSHING` > 2 min) are automatically requeued up to 3 times by `watchdog_stuck_invoices_task`.
- Exceeding 3 requeues routes invoice to `FAILED` status with reason `Watchdog timeout after 3 attempts`, landing in the Dead-Letter queue.
- Dead-letter administration portal enables manual pipeline retries or documented discards.

