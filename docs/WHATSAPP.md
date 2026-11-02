> **WARNING:** Payload and signature details must be checked against a real capture using `scripts/capture_openwa_webhook.py`. The built-in fixtures under `backend/tests/fixtures/openwa/` are synthetic models conforming to the OpenWA API specification.

# WhatsApp Invoice Intake Guide (OpenWA & Meta Cloud API)

InvoiceFlow supports WhatsApp invoice intake through two interchangeable providers managed under a unified provider abstraction:
1. **OpenWA (`openwa`)**: A free, self-hosted, MIT-licensed WhatsApp gateway container (`ghcr.io/rmyndharis/openwa:v0.27.0`) running locally via Docker Compose.
2. **Meta Cloud API (`meta`)**: The official Meta WhatsApp Business Platform Cloud API.

Switching between providers requires updating a single setting: `WHATSAPP_PROVIDER=openwa` or `WHATSAPP_PROVIDER=meta`.

---

## 1. Risk Statement & Deployment Guidance

> **IMPORTANT NOTICE:** OpenWA is an unofficial, community-maintained gateway connecting via reverse-engineered WhatsApp Web protocols (`whatsapp-web.js` or Baileys). Meta may restrict, suspend, or ban WhatsApp accounts linked through unofficial gateways.
>
> - **Never use your primary personal or critical business number** with OpenWA. Use a dedicated SIM or virtual number you can afford to lose.
> - **Production Guard:** If running in `ENVIRONMENT=production` with `WHATSAPP_PROVIDER=openwa`, InvoiceFlow will refuse to start unless `OPENWA_ACCEPT_UNOFFICIAL_RISK=true` is explicitly set in the environment.
> - **Enterprise & Regulated Deployments:** For SOC2, ISO 27001, or financial/accounting deployments where compliance and number reliability are mandatory, use official **Meta WhatsApp Cloud API** (`WHATSAPP_PROVIDER=meta`).

---

## 2. Configuration Settings Reference

All settings can be configured via environment variables or `.env`:

| Setting | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `WHATSAPP_PROVIDER` | `str` | `openwa` | Active gateway: `openwa` or `meta`. |
| `WHATSAPP_GROUP_WINDOW_SECONDS` | `int` | `90` | Window (seconds) to aggregate multiple photos from same sender into a single multi-page invoice. |
| `WHATSAPP_MAX_OUTBOUND_PER_HOUR` | `int` | `20` | Maximum system outbound messages per hour across all recipients. |
| `RESEND_MAX_PER_SENDER_PER_DAY` | `int` | `5` | Maximum resend notifications sent to a single contact per 24 hours. |
| `OPENWA_BASE_URL` | `str` | `http://openwa:2785/api` | REST API URL of the OpenWA container. |
| `OPENWA_API_KEY` | `str` | `""` | Admin API key for authenticating with OpenWA. |
| `OPENWA_SESSION_NAME` | `str` | `invoiceflow` | Name of the WhatsApp Web session. |
| `OPENWA_SESSION_ID` | `str` | `""` | Assigned session ID (written by setup CLI). |
| `OPENWA_WEBHOOK_SECRET` | `str` | `""` | Shared secret for validating HMAC-SHA256 signatures. |
| `OPENWA_WEBHOOK_TARGET_URL` | `str` | `http://api:8000/api/v1/webhooks/whatsapp/openwa` | URL where OpenWA posts webhook deliveries. |
| `OPENWA_DASHBOARD_URL` | `str` | `http://localhost:2785` | URL to OpenWA web management UI. |
| `OPENWA_ALLOW_GROUPS` | `bool` | `false` | Whether to accept invoices sent in group chats. |
| `OPENWA_ALLOWED_SENDERS` | `list[str]` | `[]` | Optional comma-separated list of allowed phone numbers. If empty, all senders allowed. |
| `OPENWA_ACCEPT_UNOFFICIAL_RISK` | `bool` | `false` | Required to be `true` to run OpenWA in `ENVIRONMENT=production`. |
| `WHATSAPP_PHONE_NUMBER_ID` | `str` | `""` | Meta Cloud API Phone Number ID (when provider is `meta`). |
| `WHATSAPP_API_TOKEN` | `str` | `""` | Meta System User access token with `whatsapp_business_messaging`. |
| `WHATSAPP_APP_SECRET` | `str` | `""` | Meta App Secret for validating `X-Hub-Signature-256`. |
| `WHATSAPP_VERIFY_TOKEN` | `str` | `""` | Custom verification token for Meta webhook challenge. |

---

## 3. Human Setup Walkthrough: OpenWA Gateway

### Step 1: Start OpenWA Container
In your terminal, launch the OpenWA container using Docker Compose:
```bash
docker compose --profile whatsapp up -d openwa
```
Verify the container is healthy:
```bash
docker compose ps openwa
```

### Step 2: Retrieve Admin API Key
On first boot, OpenWA generates an admin key and writes it to `/app/data/.api-key`:
```bash
make openwa-key
# Or: docker compose exec openwa cat /app/data/.api-key
```
Copy this key into your `.env` file:
```env
OPENWA_API_KEY=<copied-api-key>
```

### Step 3: Run Automated Setup
Run the automated CLI command to create the session and configure the webhook:
```bash
make whatsapp-setup
# Or: python -m app.cli whatsapp setup-openwa
```
This command idempotently:
1. Verifies connectivity to OpenWA at `OPENWA_BASE_URL`.
2. Creates session `invoiceflow` (if not already created).
3. Starts the session engine.
4. Registers the webhook endpoint `http://api:8000/api/v1/webhooks/whatsapp/openwa` with event subscriptions `message.received` and `session.status`.
5. Outputs the session ID.

### Step 4: Link Your WhatsApp Account (Scan QR Code)
1. Open the OpenWA Dashboard at `http://localhost:2785` in your browser.
2. Authenticate using the Admin API key.
3. Select the `invoiceflow` session and click **Show QR Code**.
4. On your mobile phone (with dedicated intake SIM):
   - Open WhatsApp -> **Settings** -> **Linked Devices** -> **Link a Device**.
   - Scan the QR code displayed on the OpenWA dashboard.
5. Within 5–10 seconds, the session state in InvoiceFlow Admin UI will transition to `Connected` (mint badge).

---

## 4. Invariant R2 Enforcement: Universal Human Gate

In accordance with Core System Invariant **R2**:
- Invoices received via WhatsApp (photos, scans, multi-page PDFs) are ingested, preprocessed, and extracted via the standard pipeline.
- **Zero auto-approval:** Every WhatsApp invoice unconditionally enters status `NEEDS_REVIEW` in the review queue.
- Reviewers must inspect line items, GSTIN validation, and mathematical grounding before manually approving or pushing to accounting.

---

## 5. Safe-Sending & Anti-Ban Policies

To prevent carrier or Meta automated spam bans:
1. **24-Hour Rule:** Outbound resend messages are **only** sent to contacts who have sent an inbound message within the prior 24 hours. Cold outbound messaging is strictly rejected.
2. **Rate Limits:** Outbound rate is capped at `WHATSAPP_MAX_OUTBOUND_PER_HOUR` (default 20/hr) and `RESEND_MAX_PER_SENDER_PER_DAY` (default 5/day).
3. **Data Protection:** Financial figures and invoice amounts are strictly redacted from notification messages; notifications only request a clear resend of document pages.
4. **Sending Jitter:** In production, a random 3–10 second delay is inserted between outgoing messages to simulate human typing cadence.

---

## 6. Verification & Troubleshooting

### Simulating Inbound Invoices Without a Real Phone
You can simulate an inbound invoice photo using the simulation CLI:
```bash
make whatsapp-simulate
# Or: python scripts/simulate_whatsapp_photo.py --sender 919876543210 --file samples/sample_invoice.pdf
```

### Capturing Real Webhooks
To inspect raw webhook payloads from a live OpenWA container:
```bash
python scripts/capture_openwa_webhook.py --port 2786
```
Captured headers and JSON payloads are saved to `backend/tests/fixtures/openwa/captured/`.

### Troubleshooting Matrix
| Symptom | Cause | Resolution |
| :--- | :--- | :--- |
| `401 Unauthorized: Invalid webhook signature` | Mismatched secret or tampered body | Verify `OPENWA_WEBHOOK_SECRET` matches the secret registered in OpenWA webhooks. |
| Session status `Needs QR Scan` | Mobile device unlinked or logged out | Open `OPENWA_DASHBOARD_URL` and scan new QR code. |
| Media dropped / `media_too_large` | File exceeds `MEDIA_DOWNLOAD_MAX_BYTES` (50MB) | Instruct sender to send document under size limit. System automatically queues resend guidance. |
| Inbound ignored (`sender_not_allowlisted`) | Sender not in `OPENWA_ALLOWED_SENDERS` | Add sender's number (e.g. `919876543210`) to `OPENWA_ALLOWED_SENDERS` in `.env`. |
| Docker container crashes with OOM | `whatsapp-web.js` Chrome memory usage | Ensure container has at least 1024MB RAM and `shm_size: "256mb"`. |
