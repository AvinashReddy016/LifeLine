"""Groq LLM client (OpenAI-compatible chat completions API).

Docs: https://console.groq.com/docs/api-reference
Model is configurable via GROQ_MODEL (default: openai/gpt-oss-120b).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from app.config import config

logger = logging.getLogger("lifeline.llm")


class LLMUnavailableError(RuntimeError):
    """Raised when the LLM cannot be reached or is not configured."""


class LLMError(RuntimeError):
    """Raised when the LLM returns a malformed/unusable response."""


def generate(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
    max_tokens: int = 1200,
    json_mode: bool = False,
) -> str:
    """Call Groq chat completions. Raises LLMUnavailableError / LLMError."""
    if not config.groq_configured:
        raise LLMUnavailableError(
            "Groq is not configured. Set GROQ_API_KEY (and optionally GROQ_MODEL) in .env."
        )

    try:
        from openai import OpenAI  # the groq SDK is OpenAI-compatible; use openai client
        client = OpenAI(
            api_key=config.groq_api_key,
            base_url=config.groq_base_url,
            timeout=45.0,
            max_retries=1,
        )
    except ImportError as exc:  # pragma: no cover
        raise LLMUnavailableError("openai package not installed. Run: pip install openai") from exc

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    kwargs: dict[str, Any] = {
        "model": config.groq_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    logger.info("[LLM] generating response (model=%s, json=%s)", config.groq_model, json_mode)
    try:
        response = client.chat.completions.create(**kwargs)
    except Exception as exc:
        message = str(exc)
        if "rate" in message.lower() or "429" in message:
            raise LLMUnavailableError(f"LLM rate limit: {message}") from exc
        if "401" in message or "auth" in message.lower():
            raise LLMUnavailableError(f"LLM authentication failed: {message}") from exc
        raise LLMUnavailableError(f"LLM call failed: {message}") from exc

    content: Optional[str] = None
    try:
        choice = response.choices[0]
        content = choice.message.content
        # gpt-oss models can wrap the answer in a "final" channel marker
        if content and content.strip().startswith("<|channel|>final"):
            content = content.split("<|channel|>final<|message|>")[-1]
    except Exception as exc:
        raise LLMError(f"Malformed LLM response: {exc}") from exc

    if not content or not content.strip():
        raise LLMError("LLM returned an empty response")
    return content.strip()


def generate_json(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> dict[str, Any]:
    """Call Groq with JSON mode and parse the result. Raises LLMError on bad JSON."""
    raw = generate(system_prompt, user_prompt, temperature=temperature, json_mode=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        # One retry with a repair instruction
        logger.warning("[LLM] invalid JSON from model, retrying repair")
        repaired = generate(
            system_prompt + "\nRespond ONLY with valid JSON.",
            f"The following was supposed to be JSON but was not:\n{raw}\nReturn the corrected JSON only.",
            temperature=0.0,
            json_mode=True,
        )
        try:
            return json.loads(repaired)
        except json.JSONDecodeError:
            raise LLMError(f"LLM returned invalid JSON: {raw[:200]}") from exc
