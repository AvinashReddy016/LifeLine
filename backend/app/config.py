"""LifeLine configuration.

All secrets come from environment variables. Copy .env.example to .env and fill
in HINDSIGHT_API_KEY and GROQ_API_KEY. Never commit .env.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Load backend/.env so locally configured secrets actually reach the process.
# Real environment variables always take precedence over .env values.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
except ImportError:  # pragma: no cover — dotenv is in requirements.txt
    pass


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name, default)
    return value.strip() if value else default


@dataclass
class Config:
    # --- Hindsight (long-term memory) ---
    hindsight_base_url: str = field(default_factory=lambda: _env(
        "HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io"))
    hindsight_api_key: str = field(default_factory=lambda: _env("HINDSIGHT_API_KEY"))
    hindsight_bank_id: str = field(default_factory=lambda: _env(
        "HINDSIGHT_BANK_ID", "lifeline-demo"))

    # --- Groq LLM ---
    groq_api_key: str = field(default_factory=lambda: _env("GROQ_API_KEY"))
    groq_model: str = field(default_factory=lambda: _env("GROQ_MODEL", "openai/gpt-oss-120b"))
    groq_base_url: str = field(default_factory=lambda: _env(
        "GROQ_BASE_URL", "https://api.groq.com/openai/v1"))

    # --- App ---
    cors_origins: list[str] = field(default_factory=lambda: _env(
        "CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(","))
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # --- Safety / data labeling ---
    synthetic_banner: str = "SYNTHETIC DEMO DATA — NOT REAL PATIENT DATA"

    @property
    def hindsight_configured(self) -> bool:
        # A locally hosted (non-Cloud) Hindsight server does not require an API key.
        return bool(self.hindsight_base_url) and (
            bool(self.hindsight_api_key) or "api.hindsight.vectorize.io" not in self.hindsight_base_url
        )

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key)


config = Config()
