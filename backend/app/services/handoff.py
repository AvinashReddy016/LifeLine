"""Handoff summary: a compact clinician-facing brief, readable in under 30 seconds.

Assembled deterministically from the patient's stored records + detected
conflicts; optionally polished by the LLM when available. Never diagnoses.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.models import HandoffSummary, Patient
from app.prompts import BOUNDARIES
from app.services.conflicts import detect_conflicts
from app.services.records_store import get_records
from app.services.timeline import build_timeline

logger = logging.getLogger("lifeline.handoff")

_LLM_SYSTEM = f"""You write compact clinician-facing handoff briefs for LifeLine.
Use ONLY the provided structured facts. Do not add medical conclusions, do not
diagnose, do not recommend medication changes. Present documented changes in
chronological order. Mark conflicts as UNRESOLVED.

{BOUNDARIES}
"""


def _longitudinal_synthesis(patient: Patient) -> str:
    """Longitudinal synthesis via Hindsight reflect (memory-side, not LLM-side).

    Returns a synthesis string, or an empty string if Hindsight is unavailable
    (the deterministic sections below still carry the handoff).
    """
    try:
        from app.services.hindsight.client import get_hindsight
        from app.services.hindsight.memory_service import bank_id_for_patient

        hindsight = get_hindsight()
        result = hindsight.reflect(
            query=(
                "Longitudinal overview of this patient's documented history: how did "
                "medications, symptoms, encounters and documented reactions change over "
                "time? Which threads appear unresolved?"
            ),
            context=(
                f"Synthetic patient {patient.name}. Current issue: {patient.current_issue}. "
                "Source: stored longitudinal medical memories. This synthesis will be "
                "reviewed by a clinician and must stay descriptive, not diagnostic."
            ),
            bank_id=bank_id_for_patient(patient),
        )
        text = (result.get("text") or "").strip()
        if text:
            logger.info("[HINDSIGHT] reflect synthesis used in handoff (%d sources)", len(result.get("based_on") or []))
        return text
    except Exception as exc:  # noqa: BLE001 — reflect is an enhancement, never a dependency
        logger.info("[HINDSIGHT] reflect unavailable for handoff: %s", exc)
        return ""


def generate_handoff_summary(patient: Patient, use_llm: bool = True) -> HandoffSummary:
    records = get_records(patient.patient_id)
    conflicts = detect_conflicts(records)
    timeline = build_timeline(patient.patient_id)

    recent_records = records[-6:]
    med_changes = [
        event for event in timeline
        if event.kind == "medication"
    ][-4:]
    emergencies = [e for e in timeline if e.kind == "emergency"]

    sections: dict[str, str] = {
        "CURRENT CONTEXT": (
            f"{patient.current_issue}. Current meds per chart: "
            f"{'; '.join(patient.current_medications) if patient.current_medications else 'none documented'}."
        ),
        "RECENT HISTORY": "\n".join(
            f"- {r.date} ({r.record_id}) {r.title}: {r.summary}" for r in recent_records
        ),
        "RELEVANT MEDICATION CHANGES": (
            "\n".join(f"- {e.date} ({e.record_id}) {e.detail}" for e in med_changes)
            or "- None documented"
        ),
        "PRIOR RELATED EVENTS": "\n".join(
            f"- {e.date} ({e.record_id}) {e.title}: {e.detail}" for e in emergencies
        ) or "- None documented",
        "POTENTIAL CONFLICTS": (
            "\n".join(
                f"- ⚠ {c.description} Status: UNRESOLVED — verify against the current clinical record."
                for c in conflicts
            )
            or "- None detected by rule-based scan"
        ),
        "VERIFICATION NEEDED": "\n".join(
            [
                f"- Verify allergy status ({', '.join(sorted({c.type for c in conflicts}))})" if conflicts else "- Verify current medication list and allergy status",
                "- Confirm medication history across pharmacy switches",
                "- Review ED dispositions and follow-through",
            ]
        ),
    }

    summary = HandoffSummary(
        patient_id=patient.patient_id,
        generated_at=datetime.utcnow().isoformat() + "Z",
        sections=sections,
        records_reviewed=[r.record_id for r in recent_records],
    )

    # Longitudinal synthesis directly from Hindsight memories (reflect) — the
    # memory system's own cross-record view. Falls back to deterministic sections.
    synthesis = _longitudinal_synthesis(patient)
    if synthesis:
        sections["LONGITUDINAL SYNTHESIS (from memory)"] = synthesis

    # Optional LLM polish of the RECENT HISTORY narrative (facts stay fixed).
    if use_llm:
        try:
            from app.services.llm import groq_service

            facts = "\n".join(f"- {r.date} ({r.record_id}) {r.title}: {r.summary}" for r in recent_records)
            polished = groq_service.generate(
                system_prompt=_LLM_SYSTEM,
                user_prompt=(
                    "Rewrite this record list as one tight chronological narrative paragraph "
                    "for a clinician handoff. Keep every record ID and date. Add nothing.\n\n"
                    f"{facts}"
                ),
                temperature=0.2,
                max_tokens=400,
            )
            sections["RECENT HISTORY"] = polished
            logger.info("[HANDOFF] LLM narrative polish applied")
        except Exception as exc:  # noqa: BLE001 — deterministic sections are the fallback
            logger.info("[HANDOFF] LLM polish skipped: %s", exc)

    return summary
