# InvoiceFlow: Operational Alert Rules & Runbook Thresholds

This document defines all Prometheus and AWS CloudWatch alert rules, evaluation windows, severities, and remediation procedures for InvoiceFlow.

---

## 1. Alert Summary Matrix

| Alert Name | Metric / Source | Condition & Threshold | Severity | Notification Channel | Remediation SLA |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **OldestUnreviewedInvoiceAge** | `invoiceflow_queue_age_seconds{queue="extract"}` | `> 14400s` (4 hours) | P2 - Warning | Slack `#alerts-ops` | 30 minutes |
| **QueueBacklogCritical** | `invoiceflow_queue_depth{queue=~"extract\|push"}` | `> 500` for 10m | P1 - Critical | PagerDuty + Slack | 15 minutes |
| **DeadLettersPresent** | `invoiceflow_invoices_by_status{status="PUSH_FAILED"}` | `> 0` for 15m | P2 - Warning | Slack `#alerts-ops` | 1 hour |
| **PushFailureRateHigh** | `rate(invoiceflow_push_attempts_total{result!="success"}[5m]) / rate(invoiceflow_push_attempts_total[5m])` | `> 0.05` (5%) | P1 - Critical | PagerDuty + Slack | 15 minutes |
| **CircuitBreakerOpenExtended** | `invoiceflow_circuit_breaker_state` | `== 2` (OPEN) for > 10m | P1 - Critical | PagerDuty + Slack | 15 minutes |
| **CriticalReconciliationFinding** | `invoiceflow_reconciliation_findings_total{severity="error"}` | `> 0` | P1 - Critical | PagerDuty + Accounting | Immediate |
| **DailyLLMCostOverBudget** | `invoiceflow_llm_cost_usd_total` | `> $50.00` in 24h | P2 - Warning | Slack `#finance-ops` | 4 hours |
| **OperationalInvariantViolation** | `invoiceflow_invariant_failures_total` | `> 0` | P1 - Critical (R2/R3) | PagerDuty (All hands) | Immediate |
| **HTTP5xxSpike** | `rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])` | `> 0.02` (2%) for 5m | P1 - Critical | PagerDuty + Slack | 15 minutes |
| **DatabaseSaturation** | `aws_rds_cpu_utilization` or connection pool | `> 80%` for 10m | P2 - Warning | Slack `#infra-ops` | 30 minutes |
| **RedisMemorySaturation** | `aws_elasticache_memory_utilization` | `> 80%` for 10m | P2 - Warning | Slack `#infra-ops` | 30 minutes |

---

## 2. Prometheus Alerting Rules Specification

```yaml
groups:
  - name: invoiceflow.alerts
    rules:
      - alert: OldestUnreviewedInvoiceAge
        expr: (time() - invoiceflow_oldest_waiting_timestamp_seconds) > 14400
        for: 15m
        labels:
          severity: warning
          team: ops
        annotations:
          summary: "Oldest unreviewed invoice age exceeds 4 hours"
          description: "Human review queue is starving or review capacity is saturated. Allocate additional reviewer capacity."

      - alert: QueueBacklogCritical
        expr: sum(invoiceflow_queue_depth{queue=~"extract|push"}) > 500
        for: 10m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Celery task backlog critical (>500 items)"
          description: "Celery task queues are backing up. Inspect worker auto-scaling and provider rate limits."

      - alert: DeadLettersPresent
        expr: sum(invoiceflow_invoices_by_status{status=~"PUSH_FAILED|FAILED"}) > 0
        for: 15m
        labels:
          severity: warning
          team: ops
        annotations:
          summary: "Invoices stuck in Dead Letter states"
          description: "There are invoices in PUSH_FAILED or FAILED states for over 15 minutes. Review in Admin Dead-Letters interface."

      - alert: PushFailureRateHigh
        expr: sum(rate(invoiceflow_push_attempts_total{result!="success"}[5m])) / sum(rate(invoiceflow_push_attempts_total[5m])) > 0.05
        for: 5m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Accounting API push failure rate > 5%"
          description: "Downstream accounting system is rejecting push payloads or experiencing 5xx server errors."

      - alert: CircuitBreakerOpenExtended
        expr: invoiceflow_circuit_breaker_state == 2
        for: 10m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "Circuit breaker has remained OPEN for > 10 minutes"
          description: "Upstream provider (Groq) or downstream accounting system is unavailable. Inspect network reachability."

      - alert: CriticalReconciliationFinding
        expr: invoiceflow_reconciliation_findings_total{severity="error"} > 0
        for: 1m
        labels:
          severity: critical
          team: finance-ops
        annotations:
          summary: "Critical divergence discovered during accounting reconciliation"
          description: "An invoice exists in PUSHED state in InvoiceFlow but is missing or altered in accounting system. Runbook: docs/RUNBOOK.md#reconciliation"

      - alert: DailyLLMCostOverBudget
        expr: invoiceflow_llm_cost_usd_total > 50
        for: 5m
        labels:
          severity: warning
          team: finance-ops
        annotations:
          summary: "Daily LLM extraction budget threshold exceeded ($50 USD)"
          description: "Token consumption spike detected. Check for high volume of complex multipage scans or repeated retries."

      - alert: OperationalInvariantViolation
        expr: invoiceflow_invariants_status == 0
        for: 1m
        labels:
          severity: page
          team: security-and-compliance
        annotations:
          summary: "INVOICEFLOW OPERATIONAL INVARIANT BREACHED"
          description: "CRITICAL: R2, R3, or audit-trail guarantee violated. Immediate investigation required."
```


      - alert: WhatsAppSessionDisconnected
        expr: invoiceflow_whatsapp_session_state == 2
        for: 5m
        labels:
          severity: warning
          team: ops
        annotations:
          summary: "WhatsApp gateway session disconnected or unlinked"
          description: "WhatsApp session is disconnected. Scan QR code or restart gateway session via Admin UI."

      - alert: WhatsAppSignatureFailuresHigh
        expr: rate(invoiceflow_whatsapp_signature_failures_total[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
          team: security
        annotations:
          summary: "Elevated WhatsApp webhook signature failure rate"
          description: "Potential webhook secret mismatch or unauthorized requests sent to WhatsApp webhook endpoint."
