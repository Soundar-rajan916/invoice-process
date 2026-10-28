from __future__ import annotations

from app.core.config import settings
from app.extraction.base import Extractor
from app.extraction.groq_extractor import GroqExtractor
from app.extraction.mock_extractor import MockExtractor


def get_extractor() -> Extractor:
    if settings.EXTRACTOR == "groq":
        return GroqExtractor()
    return MockExtractor()
