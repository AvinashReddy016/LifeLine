"""Agent orchestrator — the reasoning core of LifeLine.

Flow:
  question → recall plan → Hindsight recall → provenance linking → conflict
  detection → Groq synthesis → structured answer (answer + evidence + records +
  timeline + conflicts + uncertainty + safety note).

Failure modes are explicit:
  - Hindsight down → degrade to direct record summary, say so honestly.
  - LLM down → return evidence-only answer assembled from retrieved memories.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.models import ChatAnswer
from app.prompts import BOUNDARIES, MEMORY_UNAVAILABLE_NOTE, SAFETY_NOTE
from app.services.agent_history import remember_interaction
from app.services.agent_knowledge import related_history_answer
from app.services.agent_knowledge import notes_to_uncertainty
from app.services.conflicts import detect_conflicts
from app.services.hindsight.client import HindsightUnavailableError
from app.services.hindsight.memory_service import (
    build_recall_queries,
    memory_status_payload,
    recall_for_question,
)
from app.services.llm import groq_service
from app.services.provenance import link_memory_to_records, provenance_log
from app.services.records_store import get_patient, get_record, get_records
from app.services.timeline import build_timeline, events_from_memories

logger = logging.getLogger("lifeline.agent")

SYSTEM_PROMPT = f"""You are LifeLine, a medical-history memory assistant for clinicians and patients.

Your job is to reconstruct the patient's longitudinal story from stored memory
evidence — NOT to practice medicine. You are given evidence items retrieved from
a long-term memory system (Hindsight). Every claim you make must come from those
evidence items or from the current chart context.

{BOUNDARIES}

STYLE:
- Be concise and concrete. Cite record IDs inline like (REC-1013).
- When comparing across time, present changes in chronological order.
- Use plain language a clinician can scan quickly.
- End with one short line on what needs clinician verification, if anything.
- If the evidence is empty or generic, say plainly that no specific history is
  available rather than producing generic medical advice.
"""


def answer_question(patient_id: str, question: str) -> ChatAnswer:
    patient = get_patient(patient_id)
    if patient is None:
        raise ValueError(f"Unknown patient: {patient_id}")

    logger.info("[AGENT] question for %s: %s", patient_id, question[:120])

    # ---------------------------------------------------------- 1. recall
    recall_result: Optional[dict[str, Any]] = None
    try:
        recall_result = recall_for_question(question, patient)
    except HindsightUnavailableError as exc:
        logger.warning("[AGENT] recall unavailable: %s", exc)
    except Exception as exc:  # noqa: BLE001 — never let memory failure kill the answer
        logger.warning("[AGENT] recall failed unexpectedly: %s", exc)

    memories = (recall_result or {}).get("memories") or []
    memory_failed = (recall_result or {}).get("failed", True) if recall_result else True
    memory_partial = (recall_result or {}).get("partial_failure", False) if recall_result else False

    # ------------------------------------------------ 2. provenance linking
    record_lookup = {r.record_id: r for r in get_records(patient_id)}
    enriched = link_memory_to_records(memories, record_lookup) if memories else []
    provenance_log(len(enriched))

    # ------------------------------------------------ 3. conflicts
    conflicts = detect_conflicts(list(record_lookup.values()))
    relevant_conflicts = _relevant_conflicts(conflicts, memories)

    # ------------------------------------------------ 4. timeline context
    timeline_events = events_from_memories(memories)

    # ------------------------------------------------ 5. synthesis
    uncertainty: list[str] = []
    answer_text = ""
    llm_ok = True
    try:
        context = _build_llm_context(patient, question, enriched, relevant_conflicts)
        answer_text = groq_service.generate(
            system_prompt=SYSTEM_PROMPT,
            user_prompt=context,
            temperature=0.2,
            max_tokens=1100,
        )
    except groq_service.LLMUnavailableError as exc:
        llm_ok = False
        uncertainty.append(f"Language model unavailable: {exc}")
        answer_text = _evidence_only_answer(question, enriched, memory_failed, patient_id, patient)
    except groq_service.LLMError as except_exc:
        llm_ok = False
        uncertainty.append(f"Language model returned a malformed response: {except_exc}")
        answer_text = _evidence_only_answer(question, enriched, memory_failed, patient_id, patient)

    if memory_failed:
        uncertainty.insert(0, MEMORY_UNAVAILABLE_NOTE)
    elif memory_partial:
        uncertainty.insert(
            0,
            "Part of the memory search failed, so some historical context could not be "
            "verified. The recalled evidence below may be incomplete.",
        )

    # --------------------------------------- 6. retain this interaction
    try:
        remember_interaction(patient_id, question, answer_text, patient=patient)
    except Exception as exc:  # scoped to the patient's own bank; best-effort
        logger.info("[AGENT] interaction retention skipped: %s", exc)

    return ChatAnswer(
        answer=answer_text,
        memories_used=[
            {
                "id": m["memory"].get("id", ""),
                "text": m["memory"].get("text", "")[:400],
                "score": round(float(m["memory"].get("score", 0.0)), 4),
                "memory_type": m["memory"].get("memory_type", ""),
                "dimension": m["memory"].get("dimension", ""),
                "record_ids": m["record_ids"],
                "date": (m["memory"].get("metadata") or {}).get("date", ""),
            }
            for m in enriched[:8]
        ],
        source_records=[sr for m in enriched[:8] for sr in m["source_records"]],
        timeline_events=[e.__dict__ for e in timeline_events[:10]],
        conflicts=[c.__dict__ for c in relevant_conflicts],
        uncertainty=notes_to_uncertainty(uncertainty),
        safety_note=SAFETY_NOTE,
    )


# ------------------------------------------------------------------ helpers

def _relevant_conflicts(conflicts: list, memories: list[dict[str, Any]]) -> list:
    """Conflicts whose records appear in the recalled memories (plus all if few)."""
    if len(conflicts) <= 3:
        return conflicts
    memory_record_ids = set()
    for memory in memories:
        memory_record_ids.update(memory.get("record_ids") or [])
    return [c for c in conflicts if c.record_a_id in memory_record_ids or c.record_b_id in memory_record_ids]


def _build_llm_context(
    patient,
    question: str,
    enriched: list[dict[str, Any]],
    conflicts: list,
) -> str:
    from app.services.agent_knowledge import format_context  # local import to avoid cycles

    return format_context(patient, question, enriched, conflicts)


def _evidence_only_answer(
    question: str,
    enriched: list[dict[str, Any]],
    memory_failed: bool,
    patient_id: str,
    patient: Optional[Any] = None,
) -> str:
    """Fallback when the LLM is unavailable: present the raw evidence honestly."""
    parts = []
    if memory_failed:
        parts.append(MEMORY_UNAVAILABLE_NOTE)
    if enriched:
        parts.append(
            "The language model is unavailable, but the memory system returned "
            f"{len(enriched)} relevant historical item(s) for \"{question}\":"
        )
        for entry in enriched[:6]:
            record_ids = ", ".join(entry["record_ids"]) or "no record link"
            parts.append(f"- {entry['memory'].get('text', '')[:220]} ({record_ids})")
        parts.append("These items are surfaced directly from long-term memory and should be reviewed by a clinician.")
    elif patient is not None:
        related = related_history_answer(patient_id, patient=patient)
        if related:
            parts.append(related)
    return "\n\n".join(parts)
