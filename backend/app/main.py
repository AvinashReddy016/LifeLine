"""LifeLine API — FastAPI application entrypoint."""
from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import config

logging.basicConfig(
    level=getattr(logging, config.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("lifeline")

app = FastAPI(
    title="LifeLine API",
    version="0.1.0",
    description=(
        "Longitudinal medical-history memory demo powered by Hindsight. "
        "Synthetic data only — not for clinical use."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")


@app.on_event("startup")
async def startup() -> None:
    logger.info("LifeLine API starting — synthetic demo data only.")
    if config.hindsight_configured:
        logger.info("[HINDSIGHT] configured (bank=%s)", config.hindsight_bank_id)
    else:
        logger.warning("[HINDSIGHT] NOT configured — chat will degrade gracefully.")
    if config.groq_configured:
        logger.info("[LLM] configured (model=%s)", config.groq_model)
    else:
        logger.warning("[LLM] NOT configured — evidence-only fallback will be used.")


@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": "lifeline-api",
        "hindsight_configured": config.hindsight_configured,
        "groq_configured": config.groq_configured,
        "synthetic_data": True,
    }
