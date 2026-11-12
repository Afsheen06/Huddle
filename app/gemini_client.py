"""Shared Google GenAI client configuration for chat and structured extraction."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types


PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def get_gemini_client() -> tuple[genai.Client, str]:
    """Read Gemini settings from .env and use a bounded request timeout."""
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "").strip()
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in the project-root .env file.")
    if not model:
        raise RuntimeError("Missing GEMINI_MODEL in the project-root .env file.")
    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=45_000),
    )
    return client, model
