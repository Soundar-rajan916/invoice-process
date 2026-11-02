from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

SessionStatus = Literal["connected", "needs_qr", "disconnected", "unknown"]


@dataclass
class MediaRef:
    """Reference to inbound media, either inline bytes or authenticated URL."""

    data: bytes | None = None
    url: str | None = None
    size_bytes: int = 0
    mimetype: str | None = None
    is_oversized: bool = False


@dataclass
class InboundWhatsAppMessage:
    """Normalised provider-agnostic inbound WhatsApp message."""

    external_id: str
    session_ref: str
    chat_id: str
    sender_id: str
    is_group: bool
    from_me: bool
    message_type: str
    timestamp: datetime
    caption: str | None = None
    filename: str | None = None
    mimetype: str | None = None
    media: MediaRef | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SessionStatusEvent:
    """Normalised session status event emitted by WhatsApp provider."""

    session_id: str
    status: SessionStatus
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProviderSendResult:
    """Result from sending a text or template message via provider."""

    success: bool
    message_id: str | None = None
    error: str | None = None
