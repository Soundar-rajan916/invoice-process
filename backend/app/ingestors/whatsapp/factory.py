from __future__ import annotations

from app.core.config import settings
from app.ingestors.whatsapp.meta import MetaCloudProvider
from app.ingestors.whatsapp.openwa import OpenWAProvider
from app.ingestors.whatsapp.provider import WhatsAppProvider

_active_provider: WhatsAppProvider | None = None


def get_whatsapp_provider(force_reload: bool = False) -> WhatsAppProvider:
    """Factory creating and caching the configured WhatsApp provider.
    Fails fast if chosen provider settings are missing. Unused provider settings may be absent.
    """
    global _active_provider
    if _active_provider is not None and not force_reload:
        return _active_provider

    provider_name = settings.WHATSAPP_PROVIDER.lower().strip()

    if provider_name == "openwa":
        if not settings.OPENWA_BASE_URL:
            raise ValueError(
                "WHATSAPP_PROVIDER is 'openwa' but OPENWA_BASE_URL is not configured."
            )
        if settings.ENVIRONMENT != "test" and not settings.OPENWA_WEBHOOK_SECRET:
            raise ValueError(
                "WHATSAPP_PROVIDER is 'openwa' but OPENWA_WEBHOOK_SECRET is not configured."
            )
        _active_provider = OpenWAProvider()
        return _active_provider

    elif provider_name == "meta":
        if not settings.WHATSAPP_PHONE_NUMBER_ID:
            raise ValueError(
                "WHATSAPP_PROVIDER is 'meta' but WHATSAPP_PHONE_NUMBER_ID is not configured."
            )
        if settings.ENVIRONMENT != "test":
            if not settings.WHATSAPP_API_TOKEN:
                raise ValueError(
                    "WHATSAPP_PROVIDER is 'meta' but WHATSAPP_API_TOKEN is not configured."
                )
            if not settings.WHATSAPP_APP_SECRET:
                raise ValueError(
                    "WHATSAPP_PROVIDER is 'meta' but WHATSAPP_APP_SECRET is not configured."
                )
        _active_provider = MetaCloudProvider()
        return _active_provider

    else:
        raise ValueError(
            f"Unsupported WHATSAPP_PROVIDER '{settings.WHATSAPP_PROVIDER}'. Must be 'openwa' or 'meta'."
        )
