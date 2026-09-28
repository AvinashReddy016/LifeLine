"""Agent knowledge assembly: LLM context building and evidence-only fallbacks."""
from __future__ import annotations

import logging
from typing import Any

from app.services.records_store import get_patient, get_records

logger = logging.getLogger("lifeline.agent.context")


def format_context(
    patient,
    question: str,
    enriched: list[dict[str, Any]],
    conflicts: list,
) -> str:
    """Build the user prompt for the LLM from patient context + recalled evidence."""
    parts: list[str] = []
    parts.append("CURRENT CHART CONTEXT (treat as the present situation):")
    parts.append(f"- Patient: {patient.name}, {patient.age}, {patient.sex}. Synthetic demo patient.")
    parts.append(f"- Current issue: {patient.current_issue}")
    if patient.current_medications:
        parts.append(f"- Current medications per chart: {'; '.join(patient.current_medications)}")
    parts.append("")

    if enriched:
        parts.append("RECALLED HISTORICAL EVIDENCE (from long-term memory; cite by record id):")
        for i, entry in enumerate(enriched[:8], start=1):
            memory = entry["memory"]
            score_pct = int(round(float(memory.get("score", 0.0)) * 100))
            record_ids = ", ".join(entry["record_ids"]) or "unlinked"
            date = (memory.get("metadata") or {}).get("date", "unknown date")
            dimension = memory.get("dimension", "direct")
            parts.append(
                f"[{i}] ({score_pct}% relevant, {dimension}, record {record_ids}, {date}) "
                f"{memory.get('text', '')[:400]}"
            )
    else:
        parts.append(
            "RECALLED HISTORICAL EVIDENCE: none. The memory system returned no relevant "
            "items for this question. Say so plainly; do not invent history."
        )
    parts.append("")

    if conflicts:
        parts.append("POTENTIAL CONFLICTS DETECTED (always UNRESOLVED, never pick a winner):")
        for conflict in conflicts:
            parts.append(
                f"⚠ {conflict.type}: {conflict.description} "
                f"A: ({conflict.record_a_id} {conflict.record_a_date}) \"{conflict.record_a_claim}\" | "
                f"B: ({conflict.record_b_id} {conflict.record_b_date}) \"{conflict.record_b_claim}\""
            )
    parts.append("")
    parts.append(f"QUESTION: {question}")
    parts.append("")
    parts.append(
        "TASK: Answer using ONLY the evidence above and the chart context. Cite record IDs. "
        "If presenting changes, use chronological order. If evidence is missing, say what "
        "is missing. Do not diagnose, do not recommend medication changes."
    )
    return "\n".join(parts)


def related_history_answer(patient_id: str, patient: Optional[Any] = None) -> str:
    """Direct-record fallback summary when no LLM and no memories are available."""
    patient = patient or get_patient(patient_id)
    records = get_records(patient_id)
    if not records:
        return (
            "No records are loaded for this demo patient. Seed the demo dataset first "
            "(see README: python seed_patient.py)."
        )
    lines = [f"Currently loaded records for {patient.name if patient else 'the demo patient'}:"]
    for record in records[-6:]:
        lines.append(f"- {record.date} {record.record_id}: {record.title} — {record.summary}")
    lines.append("Memory service is unavailable, so historical context beyond these loaded records cannot be verified.")
    return "\n".join(lines)


def format_context_from_records() -> str:
    """One-line hint used inside the evidence-only fallback."""
    return "No recalled memory evidence is available for this question."


def notes_to_uncertainty(uncertainty: list[str]) -> list[str]:
    """Pass uncertainty notes through (hook point for future normalization)."""
    return uncertainty
