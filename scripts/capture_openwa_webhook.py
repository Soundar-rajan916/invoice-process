#!/usr/bin/env python3
"""OpenWA Webhook Capture Tool.

Listens for incoming webhook events from a real or simulated OpenWA container,
prints the HTTP headers and payload, and saves them to
backend/tests/fixtures/openwa/captured/ with timestamped filenames.

Usage:
    python scripts/capture_openwa_webhook.py --port 2786
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


class WebhookCaptureHandler(BaseHTTPRequestHandler):
    output_dir: Path

    def do_POST(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_length) if content_length > 0 else b""
        now_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

        headers_dict = dict(self.headers)
        sig = headers_dict.get("x-openwa-signature", headers_dict.get("X-OpenWA-Signature", "none"))

        print("\n" + "=" * 60)
        print(f"[{datetime.now(timezone.utc).isoformat()}] INCOMING WEBHOOK POST")
        print(f"Path: {self.path}")
        print(f"Signature Header: {sig}")
        print("-" * 60)
        print("Headers:")
        for k, v in headers_dict.items():
            print(f"  {k}: {v}")

        body_preview = ""
        try:
            parsed = json.loads(raw_body.decode("utf-8"))
            body_preview = json.dumps(parsed, indent=2)
            # Mask media bytes in terminal output
            if isinstance(parsed, dict) and "data" in parsed:
                data = parsed["data"]
                if isinstance(data, dict) and "media" in data and isinstance(data["media"], dict):
                    if "data" in data["media"]:
                        parsed["data"]["media"]["data"] = f"<base64 data {len(data['media']['data'])} chars>"
                        body_preview = json.dumps(parsed, indent=2)
            print("-" * 60)
            print(body_preview)
        except Exception:
            print(f"Raw body ({len(raw_body)} bytes): {raw_body[:200]!r}...")

        # Persist to disk
        self.output_dir.mkdir(parents=True, exist_ok=True)
        dump_data = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "path": self.path,
            "headers": headers_dict,
            "raw_body_base64": raw_body.hex(),
        }
        if body_preview:
            try:
                dump_data["json"] = json.loads(raw_body.decode("utf-8"))
            except Exception:
                pass

        out_file = self.output_dir / f"webhook_{now_str}.json"
        out_file.write_text(json.dumps(dump_data, indent=2), encoding="utf-8")
        print(f"Saved capture to: {out_file}")
        print("=" * 60 + "\n")

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"status":"captured"}\n')

    def log_message(self, format: str, *args) -> None:
        # Suppress default server log lines to avoid noise
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture OpenWA incoming webhooks to fixture directory.")
    parser.add_argument("--port", type=int, default=2786, help="Port to listen on (default: 2786)")
    parser.add_argument(
        "--output-dir",
        type=str,
        default="backend/tests/fixtures/openwa/captured",
        help="Directory to save captures",
    )
    args = parser.parse_args()

    out_path = Path(args.output_dir).resolve()
    WebhookCaptureHandler.output_dir = out_path

    server = HTTPServer(("0.0.0.0", args.port), WebhookCaptureHandler)
    print(f"[*] OpenWA Webhook Capture Server listening on http://0.0.0.0:{args.port}")
    print(f"[*] Captures will be stored in: {out_path}")
    print("[*] Press Ctrl+C to stop.")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down capture server.")
        server.server_close()


if __name__ == "__main__":
    main()
