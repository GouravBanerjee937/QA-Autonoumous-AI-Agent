"""Thin OpenAI wrapper that returns Pydantic models via structured outputs."""

from __future__ import annotations

import os
from typing import TypeVar

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

_MODEL = os.getenv("QA_AGENT_MODEL", "gpt-4.1-mini")
_client: OpenAI | None = None

T = TypeVar("T", bound=BaseModel)


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key or api_key.startswith("your-"):
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Edit .env in the project root."
            )
        _client = OpenAI(api_key=api_key)
    return _client


def structured(
    system: str,
    user: str,
    schema: type[T],
    *,
    temperature: float = 0.2,
) -> T:
    """Call the model and parse the response as `schema`."""
    response = _get_client().beta.chat.completions.parse(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
        temperature=temperature,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError(f"Model returned no parseable {schema.__name__}")
    return parsed


def text(system: str, user: str, *, temperature: float = 0.2) -> str:
    """Free-form text completion (for code generation)."""
    response = _get_client().chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
    )
    return response.choices[0].message.content or ""
