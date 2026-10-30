from __future__ import annotations

from app.core.config import settings
from app.extraction.base import Extractor
from app.extraction.groq_extractor import GroqExtractor
from app.extraction.mock_extractor import MockExtractor

_second_opinion_extractor: Extractor | None = None


def get_extractor() -> Extractor:
    if settings.EXTRACTOR == "groq":
        return GroqExtractor()
    return MockExtractor()


def get_second_opinion_extractor() -> Extractor:
    global _second_opinion_extractor
    if _second_opinion_extractor is not None:
        return _second_opinion_extractor
    if settings.EXTRACTOR == "groq":
        return GroqExtractor(model_id="llama-3.2-11b-vision-preview")
    return MockExtractor()


def set_second_opinion_extractor(extractor: Extractor | None) -> None:
    global _second_opinion_extractor
    _second_opinion_extractor = extractor
