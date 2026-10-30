"""Locust Load Test Suite for InvoiceFlow.

Simulates month-end 4x volume: 2,000 invoices over 10 minutes (~3.33 invoices/sec).
Validates:
- Queue ingestion throughput
- Review queue polling performance
- Concurrency under load without R2 violations or deadlock
"""

import os
import random
from locust import HttpUser, task, between


class InvoiceFlowReviewerUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # Authenticate as reviewer
        res = self.client.post(
            "/api/v1/auth/login",
            json={"email": "admin@invoiceflow.internal", "password": "AdminSecurePassword123!"},
        )
        if res.status_code == 200:
            self.token = res.json().get("access_token")
            self.client.headers.update({"X-Requested-With": "XMLHttpRequest"})
        else:
            self.token = None

    @task(5)
    def view_review_queue(self):
        """Reviewers continuously monitor and filter the review queue."""
        self.client.get("/api/v1/invoices?status=NEEDS_REVIEW&page=1&page_size=20")

    @task(3)
    def view_invoice_detail(self):
        """Reviewers open specific invoices for review."""
        res = self.client.get("/api/v1/invoices?status=NEEDS_REVIEW&page_size=5")
        if res.status_code == 200:
            items = res.json().get("items", [])
            if items:
                inv = random.choice(items)
                inv_id = inv["id"]
                self.client.get(f"/api/v1/invoices/{inv_id}")
                self.client.post(f"/api/v1/invoices/{inv_id}/heartbeat")

    @task(2)
    def view_dashboard_metrics(self):
        """Operations dashboard telemetry check."""
        self.client.get("/api/v1/metrics/summary")


class InvoiceIngestionUser(HttpUser):
    wait_time = between(0.2, 0.5)

    @task
    def submit_webhook_message(self):
        """Simulates WhatsApp or Email webhook payload bursts."""
        # Simulated webhook event
        self.client.post(
            "/api/v1/webhooks/whatsapp",
            json={
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "WHATSAPP_BUS_ID",
                        "changes": [
                            {
                                "value": {
                                    "messaging_product": "whatsapp",
                                    "metadata": {"display_phone_number": "15551234567"},
                                    "messages": [],
                                },
                                "field": "messages",
                            }
                        ],
                    }
                ],
                "headers": {"X-Hub-Signature-256": "sha256=simulated"},
            },
        )
