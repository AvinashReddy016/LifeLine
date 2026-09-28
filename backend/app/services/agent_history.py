"""Agent history retention: remember interactions as lightweight memories."""
from __future__ import annotations

import logging
from typing import Any

from datetime import datetime

from app.services.hindsight.client import HindsightUnavailableError, get_hindsight
from app.services.hindsight.memory_service import bank_id_for_patient

logger = logging.getLogger("lifeline.agent.history")


def remember_interaction(patient_id: str, question: str, answer: str, patient=None) -> dict[str, Any]:
    """Retain the Q/A interaction into the patient's own memory bank (best-effort)."""
    hindsight = get_hindsight()
    snippet_q = (question or "").strip()[:300]
    snippet_a = (answer or "").strip()[:800]
    try:
        result = hindsight.retain([
            {
                "content": (
                    f"During a LifeLine session for patient {patient_id}, the question "
                    f"\"{snippet_q}\" was answered with: {snippet_a}"
                ),
                "context": "LifeLine assistant interaction",
                "metadata": {
                    "record_id": f"SESSION-{datetime.utcnow().strftime('%Y%m%d')}",
                    "event_type": "interaction",
                    "date": datetime.utcnow().date().isoformat(),
                    "source_type": "assistant",
                    "synthetic": True,
                },
            }
        ],
        bank_id=bank_id_for_patient(patient),
    )
        logger.info("[HINDSIGHT] retained interaction memory for %s", patient_id)
        return result if isinstance(result, dict) else {"success": True}
    except HindsightUnavailableError:
        logger.info("[HINDSIGHT] interaction retention skipped (unavailable)")
        return {"success": False}
