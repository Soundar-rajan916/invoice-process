# External Services & Cloud Setup Runbook

This document details the exact manual steps an operator must perform in external provider dashboards before deploying InvoiceFlow to staging and production environments.

---

## 1. Meta WhatsApp Business Cloud API Setup

1. **Create Meta Developer Account & App**
   - Navigate to [developers.facebook.com](https://developers.facebook.com) and sign in.
   - Click **My Apps** > **Create App** > Select **Business** type.
   - Under Add Products, select **WhatsApp** and click **Set up**.

2. **Configure WhatsApp Business Phone Number**
   - In WhatsApp > Quickstart, navigate to **Step 5: Add a phone number**.
   - Enter the dedicated company accounts payable phone number.
   - Verify ownership via SMS OTP or phone call.
   - Note down:
     - `WHATSAPP_PHONE_NUMBER_ID`
     - `WHATSAPP_BUSINESS_ACCOUNT_ID`

3. **Generate System User Permanent Access Token**
   - Go to Meta Business Suite > **Business Settings** > **System Users**.
   - Create a System User `invoiceflow-bot` with Admin role.
   - Assign the WhatsApp app asset with `whatsapp_business_messaging` and `whatsapp_business_management` permissions.
   - Click **Generate New Token**, select permanent expiration, and copy token to `WHATSAPP_API_TOKEN`.

4. **Submit Resend Message Template for Meta Approval**
   - In WhatsApp Manager > **Message Templates** > **Create Template**.
   - Category: `UTILITY`.
   - Name: `invoice_resend_request` (must match `WHATSAPP_RESEND_TEMPLATE`).
   - Languages: English (`en_US`).
   - Body format:
     ```text
     Dear Vendor, we received your invoice submission but could not process it due to: {{1}}. Please reply with a clear, full-page replacement PDF or image.
     ```
   - Submit for approval (typically approved in 5–15 minutes).

5. **Configure Inbound Webhook**
   - In App Dashboard > WhatsApp > **Configuration** > **Webhook**:
   - Callback URL: `https://<YOUR_DOMAIN>/api/v1/webhooks/whatsapp`
   - Verify Token: Enter your secret string matching `WHATSAPP_VERIFY_TOKEN`.
   - Click **Verify and Save**.
   - Under **Webhook fields**, click **Subscribe** to `messages`.
   - In App Settings > **Basic**, copy **App Secret** to `WHATSAPP_APP_SECRET` (used for X-Hub-Signature-256 HMAC verification).

---

## 2. Email IMAP & SMTP Setup

InvoiceFlow supports standard IMAP over TLS (Port 993) and SMTP over TLS (Port 587) with any mail provider (Google Workspace, Microsoft 365, Fastmail, self-hosted).

1. **Dedicated Service Mailbox**
   - Create a dedicated inbox: e.g. `invoices@company.com`.
   - Configure folders: Ensure `INBOX`, `Processed`, and `Failed` exist.

2. **App Password / OAuth Credentials**
   - **Google Workspace**:
     - Enable 2-Step Verification for the mailbox.
     - Go to Google Account > Security > App Passwords.
     - Create an app password named `InvoiceFlow-IMAP`.
     - Set `EMAIL_IMAP_SERVER=imap.gmail.com`, `EMAIL_IMAP_PORT=993`, `EMAIL_IMAP_USER=invoices@company.com`, `EMAIL_IMAP_PASSWORD=<16-char-app-password>`.
     - Set `EMAIL_SMTP_HOST=smtp.gmail.com`, `EMAIL_SMTP_PORT=587`, `EMAIL_SMTP_USER=invoices@company.com`, `EMAIL_SMTP_PASSWORD=<16-char-app-password>`.
   - **Microsoft 365**:
     - Create an App Registration in Microsoft Entra ID or configure an authenticated SMTP user.
     - Set `EMAIL_IMAP_SERVER=outlook.office365.com`, `EMAIL_IMAP_PORT=993`.
     - Set `EMAIL_SMTP_HOST=smtp.office365.com`, `EMAIL_SMTP_PORT=587`.

---

## 3. AWS Account & Infrastructure Bootstrap (ap-south-1)

1. **Prerequisites & Bootstrapping State Storage**
   - Create AWS Account and authenticate with AWS CLI: `aws configure`.
   - Target primary region: `ap-south-1` (Mumbai).
   - Create an encrypted S3 bucket for Terraform remote state:
     ```bash
     aws s3api create-bucket \
       --bucket invoiceflow-tfstate-ap-south-1 \
       --region ap-south-1 \
       --create-bucket-configuration LocationConstraint=ap-south-1
     
     aws s3api put-bucket-encryption \
       --bucket invoiceflow-tfstate-ap-south-1 \
       --server-side-encryption-configuration '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
     ```
   - Create DynamoDB lock table:
     ```bash
     aws dynamodb create-table \
       --table-name invoiceflow-tflock \
       --attribute-definitions AttributeName=LockID,AttributeType=S \
       --key-schema AttributeName=LockID,KeyType=HASH \
       --billing-mode PAY_PER_REQUEST \
       --region ap-south-1
     ```

2. **AWS Secrets Manager Keys**
   - Store sensitive application secrets in Secrets Manager (`/invoiceflow/prod/secrets`):
     - `SECRET_KEY`
     - `DATABASE_URL`
     - `GROQ_API_KEY`
     - `WHATSAPP_API_TOKEN`
     - `WHATSAPP_APP_SECRET`
     - `EMAIL_IMAP_PASSWORD`
     - `EMAIL_SMTP_PASSWORD`

---

## 4. Groq Vision API Setup

1. Sign in to [console.groq.com](https://console.groq.com).
2. Generate an API Key under **API Keys**.
3. Set `GROQ_API_KEY` in environment variables or `.env`.
4. Ensure access to Vision models: `llama-3.2-90b-vision-preview` and `llama-3.2-11b-vision-preview`.

---

## 5. ClamAV Antivirus Daemon (Optional)

When `ANTIVIRUS_ENABLED=true`:
- Ensure `clamav` container is running in `docker-compose.yml` on port 3310.
- ClamAV automatically updates virus signatures via `freshclam`.
