from __future__ import annotations

from typing import Any, Protocol

from app.ingestors.whatsapp.models import (
    InboundWhatsAppMessage,
    ProviderSendResult,
    SessionStatus,
    SessionStatusEvent,
)


class MediaTooLargeError(Exception):
    """Raised when inbound media exceeds provider or system download limits."""

    def __init__(self, message: str = "Media exceeded size limit", size_bytes: int = 0) -> None:
        super().__init__(message)
        self.size_bytes = size_bytes


class UnrecognizedPayloadError(Exception):
    """Raised when an incoming webhook payload does not match expected schema."""

    def __init__(self, message: str = "Unrecognized webhook payload structure", payload_keys: list[str] | None = None) -> None:
        super().__init__(message)
        self.payload_keys = payload_keys or []


class WhatsAppProvider(Protocol):
    """Protocol governing all WhatsApp intake and messaging providers."""

    def verify_request(self, headers: dict[str, str], raw_body: bytes) -> None:
        """Verifies cryptographic signature against raw body bytes. Raises HTTPException(401) on failure."""
        ...

    def parse(self, payload: dict[str, Any]) -> list[InboundWhatsAppMessage] | SessionStatusEvent:
        """Parses webhook JSON payload into normalised messages or session status event."""
        ...

    async def fetch_media(self, msg: InboundWhatsAppMessage) -> bytes:
        """Decodes inline media or downloads authenticated URL, validating byte cap and magic bytes."""
        ...

    async def send_text(self, chat_id: str, text: str) -> ProviderSendResult:
        """Sends an outbound text message to a specific chat ID."""
        ...

    async def session_status(self) -> SessionStatus:
        """Returns the current operational session status (connected, needs_qr, disconnected, unknown)."""
        ...

    async def healthcheck(self) -> bool:
        """Returns True if the provider API/gateway is reachable and healthy."""
        ...
