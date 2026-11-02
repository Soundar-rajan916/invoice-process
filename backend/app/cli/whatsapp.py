from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx

from app.core.config import settings


async def setup_openwa(
    base_url: str | None = None,
    api_key: str | None = None,
    session_name: str | None = None,
    webhook_target_url: str | None = None,
    webhook_secret: str | None = None,
    dashboard_url: str | None = None,
    client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Idempotently sets up OpenWA session and webhooks."""
    base_url = (base_url or settings.OPENWA_BASE_URL).rstrip("/")
    api_key = api_key if api_key is not None else settings.OPENWA_API_KEY
    session_name = session_name or settings.OPENWA_SESSION_NAME or "invoiceflow"
    webhook_url = webhook_target_url if webhook_target_url is not None else settings.OPENWA_WEBHOOK_TARGET_URL
    webhook_secret = webhook_secret if webhook_secret is not None else settings.OPENWA_WEBHOOK_SECRET
    dashboard_url = dashboard_url or settings.OPENWA_DASHBOARD_URL

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["X-API-Key"] = api_key

    print(f"Connecting to OpenWA gateway at {base_url}...")

    manage_client = client is None
    http_client = client or httpx.AsyncClient(timeout=30.0)

    try:
        # 1. List sessions
        target_session = None
        try:
            resp = await http_client.get(f"{base_url}/sessions", headers=headers)
            if resp.status_code == 200:
                sessions_data = resp.json()
                sessions_list = sessions_data if isinstance(sessions_data, list) else sessions_data.get("sessions", [])
                for s in sessions_list:
                    if s.get("name") == session_name:
                        target_session = s
                        break
        except Exception as e:
            print(f"Error or missing /sessions endpoint: {e}")

        # 2. Create session if missing
        if not target_session:
            print(f"Session '{session_name}' not found. Creating session...")
            create_resp = await http_client.post(
                f"{base_url}/sessions",
                headers=headers,
                json={"name": session_name},
            )
            create_resp.raise_for_status()
            target_session = create_resp.json()
            print(f"Session '{session_name}' created successfully.")

        session_id = str(target_session.get("id") or target_session.get("sessionId") or session_name)

        # 3. Start session
        print(f"Starting session '{session_id}'...")
        try:
            start_resp = await http_client.post(
                f"{base_url}/sessions/{session_id}/start",
                headers=headers,
            )
            if start_resp.status_code not in (200, 201, 409):
                start_resp.raise_for_status()
        except Exception as e:
            print(f"Warning during session start: {e}")

        # 4. Check session status
        try:
            status_resp = await http_client.get(
                f"{base_url}/sessions/{session_id}",
                headers=headers,
            )
            status_resp.raise_for_status()
            status_data = status_resp.json()
            raw_state = str(status_data.get("status") or status_data.get("state") or "unknown").upper()
        except Exception:
            raw_state = "UNKNOWN"

        print(f"Session '{session_id}' status: {raw_state}")
        if raw_state in ("QR", "SCAN_QR_CODE", "NEEDS_QR", "UNPAIRED"):
            print("==========================================================================")
            print(f"ACTION REQUIRED: Open the OpenWA dashboard at {dashboard_url}")
            print(f"and scan the QR code for session '{session_name}' with your WhatsApp app.")
            print("==========================================================================")

        # 5. List and configure webhooks
        if webhook_url:
            print(f"Configuring webhook pointing to {webhook_url}...")
            webhook_payload = {
                "url": webhook_url,
                "events": ["message.received", "session.status"],
                "secret": webhook_secret,
            }
            try:
                wh_resp = await http_client.get(
                    f"{base_url}/sessions/{session_id}/webhooks",
                    headers=headers,
                )
                existing_webhooks = wh_resp.json() if wh_resp.status_code == 200 else []
                if not isinstance(existing_webhooks, list):
                    existing_webhooks = existing_webhooks.get("webhooks", [])

                matching_webhook = None
                for wh in existing_webhooks:
                    if wh.get("url") == webhook_url:
                        matching_webhook = wh
                        break

                if matching_webhook:
                    wh_id = matching_webhook.get("id") or matching_webhook.get("webhookId")
                    if wh_id:
                        update_resp = await http_client.put(
                            f"{base_url}/sessions/{session_id}/webhooks/{wh_id}",
                            headers=headers,
                            json=webhook_payload,
                        )
                        if update_resp.status_code not in (200, 204):
                            await http_client.delete(
                                f"{base_url}/sessions/{session_id}/webhooks/{wh_id}",
                                headers=headers,
                            )
                            await http_client.post(
                                f"{base_url}/sessions/{session_id}/webhooks",
                                headers=headers,
                                json=webhook_payload,
                            )
                    print("Webhook updated successfully.")
                else:
                    create_wh = await http_client.post(
                        f"{base_url}/sessions/{session_id}/webhooks",
                        headers=headers,
                        json=webhook_payload,
                    )
                    create_wh.raise_for_status()
                    print("Webhook created successfully.")
            except Exception as e:
                print(f"Warning configuring webhook: {e}")
        else:
            print("Notice: OPENWA_WEBHOOK_TARGET_URL is not set. Skipping webhook configuration.")

        print("==========================================================================")
        print("Setup completed successfully!")
        print(f"Session ID: {session_id}")
        print(f"Set OPENWA_SESSION_ID={session_id} in your .env file.")
        print("==========================================================================")
        return {"status": "ok", "session_id": session_id, "exit_code": 0}
    finally:
        if manage_client:
            await http_client.aclose()


run_setup_openwa = setup_openwa


def main() -> None:
    parser = argparse.ArgumentParser(description="WhatsApp management CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("setup-openwa", help="Set up OpenWA session and webhooks")

    args = parser.parse_args()

    if args.command == "setup-openwa" or len(sys.argv) == 1:
        import asyncio

        res = asyncio.run(setup_openwa())
        sys.exit(res.get("exit_code", 0))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
