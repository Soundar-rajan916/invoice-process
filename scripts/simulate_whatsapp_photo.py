#!/usr/bin/env python3
"""Simulate an OpenWA incoming WhatsApp invoice photo or document webhook.

Posts a signed message.received payload to the InvoiceFlow webhook endpoint.

Usage:
    python scripts/simulate_whatsapp_photo.py \
        --url http://localhost:8000/api/v1/webhooks/whatsapp/openwa \
        --sender 919876543210 \
        --file samples/sample_invoice.pdf
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import mimetypes
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


# 1x1 valid PNG image
DEFAULT_INVOICE_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def build_payload(
    sender: str,
    file_path: Path | None,
    caption: str,
    session_id: str,
) -> tuple[dict, str]:
    if not sender.endswith("@c.us") and not sender.endswith("@lid"):
        chat_id = f"{sender.strip()}@c.us"
    else:
        chat_id = sender.strip()

    if file_path and file_path.exists():
        data_bytes = file_path.read_bytes()
        b64_content = base64.b64encode(data_bytes).decode("ascii")
        guessed_type, _ = mimetypes.guess_type(str(file_path))
        mimetype = guessed_type or "application/octet-stream"
        filename = file_path.name
        msg_type = "document" if mimetype == "application/pdf" else "image"
    else:
        b64_content = DEFAULT_INVOICE_PNG_B64
        mimetype = "image/png"
        filename = "simulated_invoice.png"
        msg_type = "image"

    message_id = f"sim_{int(time.time())}_{os.urandom(4).hex()}"

    payload = {
        "event": "message.received",
        "sessionId": session_id,
        "data": {
            "id": message_id,
            "from": chat_id,
            "to": "invoiceflow_gateway@c.us",
            "fromMe": False,
            "isGroup": False,
            "type": msg_type,
            "timestamp": int(time.time()),
            "caption": caption,
            "filename": filename,
            "mimetype": mimetype,
            "media": {
                "mimetype": mimetype,
                "data": b64_content,
                "filename": filename,
            },
        },
    }
    return payload, filename


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulate WhatsApp invoice submission via OpenWA webhook")
    parser.add_argument(
        "--url",
        type=str,
        default=os.getenv("OPENWA_WEBHOOK_TARGET_URL", "http://localhost:8000/api/v1/webhooks/whatsapp/openwa"),
        help="Target webhook URL",
    )
    parser.add_argument(
        "--secret",
        type=str,
        default=os.getenv("OPENWA_WEBHOOK_SECRET", "test-openwa-webhook-secret"),
        help="OpenWA webhook HMAC secret",
    )
    parser.add_argument(
        "--sender",
        type=str,
        default="919876543210",
        help="Sender phone number or chat ID (e.g. 919876543210)",
    )
    parser.add_argument(
        "--session-id",
        type=str,
        default=os.getenv("OPENWA_SESSION_ID", "sim-session"),
        help="OpenWA session ID",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="Path to an image or PDF invoice file to upload",
    )
    parser.add_argument(
        "--caption",
        type=str,
        default="Tax invoice attached for processing",
        help="Message caption text",
    )

    args = parser.parse_args()

    payload, filename = build_payload(args.sender, args.file, args.caption, args.session_id)
    payload_bytes = json.dumps(payload).encode("utf-8")
    sig = compute_signature(payload_bytes, args.secret)

    print(f"[*] Posting simulated WhatsApp message ({filename})")
    print(f"    Target URL: {args.url}")
    print(f"    Sender:     {payload['data']['from']}")
    print(f"    Signature:  {sig[:20]}...")

    headers = {
        "Content-Type": "application/json",
        "X-OpenWA-Signature": sig,
    }

    req = urllib.request.Request(args.url, data=payload_bytes, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp_body = resp.read().decode("utf-8")
            print(f"[+] Response {resp.status} OK:")
            print(f"    {resp_body}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[-] HTTP Error {e.code}: {err_body}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[-] Connection failed: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
