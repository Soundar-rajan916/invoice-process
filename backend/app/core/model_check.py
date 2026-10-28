from __future__ import annotations

from groq import AsyncGroq

from app.core.config import settings
from app.core.logging import logger


async def check_groq_models_at_startup() -> None:
    """Verifies that GROQ_TEXT_MODEL and GROQ_VISION_MODEL are available on Groq.
    Fails startup if any model is missing, naming the missing model and available models.
    Skipped when EXTRACTOR == 'mock'.
    """
    if settings.EXTRACTOR == "mock":
        logger.info("EXTRACTOR=mock configured, skipping Groq startup model check")
        return

    if not settings.GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not configured but EXTRACTOR=groq is enabled.")

    client = AsyncGroq(api_key=settings.GROQ_API_KEY)
    try:
        models_page = await client.models.list()
        available_ids = [m.id for m in models_page.data]
    except Exception as e:
        logger.error("Failed to query Groq models API during startup", error=str(e))
        raise RuntimeError(f"Could not connect to Groq models API: {e}") from e

    missing: list[str] = []
    if settings.GROQ_TEXT_MODEL not in available_ids:
        missing.append(f"GROQ_TEXT_MODEL '{settings.GROQ_TEXT_MODEL}'")
    if settings.GROQ_VISION_MODEL not in available_ids:
        missing.append(f"GROQ_VISION_MODEL '{settings.GROQ_VISION_MODEL}'")

    if missing:
        msg = (
            f"Configured Groq model(s) not found on Groq API: {', '.join(missing)}. "
            f"Available models are: {sorted(available_ids)}"
        )
        logger.critical("Groq startup model check failed", error=msg)
        raise RuntimeError(msg)

    logger.info(
        "Groq models verified successfully",
        text_model=settings.GROQ_TEXT_MODEL,
        vision_model=settings.GROQ_VISION_MODEL,
    )
