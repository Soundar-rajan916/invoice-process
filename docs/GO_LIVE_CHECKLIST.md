# InvoiceFlow: Production Go-Live Verification Checklist

Before toggling `SHADOW_MODE=false` and initiating live accounting API pushes, the engineering, security, and finance operations leads must sign off on all items below.

---

## 1. Shadow Mode Exit Gate (Dual-Run Accuracy Criteria)

- [ ] **Dual-Run Duration:** InvoiceFlow has operated in shadow mode alongside the manual accounts team for a minimum of **14 consecutive calendar days**.
- [ ] **Extraction Agreement Rate:** The overall agreement percentage on `GET /api/v1/admin/shadow/report` has maintained **>= 95.0%** across the 14-day window.
- [ ] **Zero Unapproved Pushes (R2 Guarantee):** Exactly **zero** invoices have bypassed human review or been pushed without verified `approved_by` and `approved_extraction_id`.
- [ ] **Supplier Format Calibration:** Any supplier exhibiting >5% discrepancy rate has been calibrated in preprocessing or tagged for human review in master data.
- [ ] **Financial Lead Sign-Off:** Accounts Payable Manager has formally reviewed and signed off on the shadow comparison report.

---

## 2. Security & Compliance Sign-Off

- [ ] **Automated SAST & Secret Audits Clean:**
  - `pip-audit` reports zero high or critical CVE vulnerabilities.
  - `npm audit` reports zero high or critical frontend vulnerabilities.
  - Bandit Python SAST scan passes with zero high-severity findings.
  - Gitleaks scan confirms no credentials or API keys exist in git history.
- [ ] **Prompt Injection & Adversarial Tests Passing:**
  - `backend/tests/test_security.py` passes all prompt-injection, path-traversal, and HMAC-spoofing tests.
- [ ] **Clean Logging Verification:**
  - CloudWatch logs inspected; verified that no supplier tax numbers, invoice line item amounts, secrets, or presigned S3 URLs appear in application logs.
- [ ] **Two-Factor Authentication (TOTP):**
  - All administrator accounts have enabled RFC 6238 TOTP two-factor authentication.
- [ ] **Data Retention & Privacy Execution:**
  - Automated retention task verified against scratch dataset; Admin "Erase Invoice" action verified with immutable audit tombstone.

---

## 3. Reliability, Capacity & Operational Readiness

- [ ] **Load Test Execution (Month-End 4x Volume):**
  - Locust load test executed (`loadtest/locustfile.py`) with 2,000 invoices over 10 minutes (3.33 invoices/sec).
  - p95 pipeline completion latency remained `< 45.0 seconds`.
  - Queue backlog cleared completely without task starvation or memory leaks.
- [ ] **Nightly Chaos Suite Passing:**
  - `backend/tests/test_chaos.py` passes under simulated Groq 429 burst throttling, accounting 503 outages, and transient database disconnections.
- [ ] **Operational Invariants Passing:**
  - `python -m backend.app.cli.invariants` exits with code 0 and verifies all 4 invariants.

---

## 4. Disaster Recovery & Runbook Drills

- [ ] **Backup & Restore Drill Completed:**
  - Automated backup restore drill script (`tools/restore_drill.py`) executed against scratch database; RTO target (< 1 hour) and RPO target (< 15 minutes) verified.
- [ ] **CloudWatch Alerting & PagerDuty Fired:**
  - Synthetic test alert fired; SNS topic successfully dispatched notifications to Slack `#alerts-ops` and on-call engineer phone.
- [ ] **Rollback Rehearsal:**
  - Blue/green or ECS rolling rollback executed in staging; verified that previous container revision continues operating seamlessly with additive database migrations.

---

## 5. Sign-Off Approvals

| Role | Sign-Off Name | Date | Status |
| :--- | :--- | :--- | :--- |
| **Lead Platform Engineer** | ____________________ | ________ | `APPROVED` |
| **Security & Compliance Officer** | ____________________ | ________ | `APPROVED` |
| **Accounts Payable Operations Lead** | ____________________ | ________ | `APPROVED` |

