# InvoiceFlow: Disaster Recovery (DR) & Business Continuity Plan

This document establishes the recovery objectives, architectural failover procedures, backup verification drills, and incident runbooks for InvoiceFlow.

---

## 1. Disaster Recovery Objectives

- **Recovery Point Objective (RPO):** `<= 15 minutes`
  - Automated continuous WAL archiving in RDS PostgreSQL with point-in-time recovery (PITR) enabled.
  - S3 versioning enabled on original documents and rendered page images.
- **Recovery Time Objective (RTO):** `<= 60 minutes`
  - Automated ECS Fargate task replacement.
  - Automated database restore drill verified via `tools/restore_drill.py`.

---

## 2. Failover Procedures by System Component

### 2.1 Amazon RDS PostgreSQL Failover
- In production (`prod`), the database is configured with **Multi-AZ Replication**.
- If the primary DB instance becomes unresponsive or hardware failure occurs, AWS RDS automatically switches to the standby replica within **60 to 120 seconds**.
- The database DNS endpoint remains identical; application connections will reconnect automatically using connection pool retries in SQLAlchemy and asyncpg.

### 2.2 Amazon ElastiCache Redis Failover
- In production (`prod`), ElastiCache is provisioned as a multi-node replication group with **Automatic Failover**.
- If the primary node fails, a read replica is elected as primary within **30 seconds**.
- Celery worker tasks will briefly retry with exponential backoff (`retry_backoff=True`) until the replica promotes.

### 2.3 Object Storage (Amazon S3) Disaster Recovery
- All buckets use versioning and multi-facility replication across availability zones in ap-south-1.
- Accidental object deletion or corruption can be rolled back using S3 version IDs.

---

## 3. Incident Runbooks

### 3.1 Upstream LLM Outage (Groq API 5xx / Extended 429)
1. **Symptoms:** LLM circuit breaker transitions to `OPEN`. Newly received invoices transition to `WAITING_PROVIDER`.
2. **Action:**
   - Verify Groq status page: `https://status.groq.com/`.
   - If Groq outage exceeds 30 minutes, switch to fallback model or secondary provider in `.env` / Secrets Manager:
     ```bash
     FALLBACK_LLM_BASE_URL="https://api.openai.com/v1"
     FALLBACK_LLM_API_KEY="sk-..."
     FALLBACK_LLM_MODEL="gpt-4o"
     ```
   - Restart Celery workers to pick up configuration.
   - When circuit breaker recovers to `CLOSED`, watchdog task automatically re-evaluates `WAITING_PROVIDER` invoices.

### 3.2 Downstream Accounting API Outage
1. **Symptoms:** Accounting circuit breaker transitions to `OPEN`. Push attempts fail and transition invoices to `PUSH_FAILED`.
2. **Action:**
   - Invoices remain safe in `APPROVED` or `PUSH_FAILED` states with locked `approved_extraction_id`. **Financial data is never lost.**
   - Once accounting API recovers, open **Admin > Dead Letters** (`/admin/dead-letters`).
   - Click **Retry** on affected invoices. System resends invoices with original deterministic `Idempotency-Key` headers.

### 3.3 Rotating Application & Database Secrets
1. **Generate New Secret:** Create high-entropy credentials in AWS Secrets Manager.
2. **Update Database User:**
   ```sql
   ALTER USER invoiceflow_admin WITH PASSWORD 'NewSecurePassword123!';
   ```
3. **Trigger ECS Rolling Update:** Update Secrets Manager ARN or trigger deployment in GitHub Actions. Tasks rotate gracefully without dropping inflight requests.

### 3.4 Changing LLM Extraction Models Safely
1. **Harness First:** Never change `GROQ_TEXT_MODEL` or `GROQ_VISION_MODEL` directly in production.
2. Run candidate model against the evaluation benchmark:
   ```bash
   python -m eval.run --manifest data/real/manifest.jsonl --inputs data/real/photos --extractor groq --model <CANDIDATE_MODEL> --out eval/reports/candidate/
   python -m eval.check --report eval/reports/candidate/report.json
   ```
3. Verify that extraction accuracy matches or exceeds existing baseline and false alarm rate is `< 2.0%`.
4. Update configuration in staging, verify shadow mode agreement, then promote to production.

### 3.5 Suspected Data Leak / Unauthorized Access
1. Immediately revoke all active sessions by truncating `revoked_tokens` or rotating `JWT_SECRET`.
2. Rotate AWS IAM roles and database passwords immediately.
3. Check CloudWatch logs for access to `/api/v1/files/raw/` and S3 access logs.
4. If an invoice requires statutory GDPR/DPDP erasure, invoke `POST /api/v1/admin/invoices/{id}/erase`.

