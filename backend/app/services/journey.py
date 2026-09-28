"""Memory Journey: a live, deterministic demonstration that LifeLine improves
because it remembers.

The journey runs against a REAL, isolated scratch bank on the real Hindsight
service (never the patient's own bank, never a mock):

  Interaction 1 — the bank holds only visit 1 of the synthetic patient.
                  The question recalls almost nothing beyond that visit.
  Interaction 2 — visits 1–2 are retained. More history is recallable.
  Interaction 3 — visits 1–3. The same question now surfaces the medication
                  change and the symptom that followed it.
  Interaction N — the full history is in memory: the longitudinal arc
                  (change → complication → emergency) is recallable.

Every stage performs real retain + recall calls. Numbers shown in the UI come
from those calls. The scratch bank is deleted afterwards (and on failure), so
the demo leaves no residue and the patient's real bank is untouched.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from app.models import MedicalRecord, Patient
from app.services.hindsight import client as hindsight_client
from app.services.hindsight.memory_service import (
    recall_for_question,
    record_to_memory_items,
    retain_records,
)

logger = logging.getLogger("lifeline.journey")

# The journey question is generic by design — the SAME question at every stage,
# so the only thing that changes is how much memory exists behind it.
JOURNEY_QUESTION = "What is going on with this patient's dizziness and medications?"

_STAGES = (1, 3, 6, 12)
_SCRATCH_SUFFIX = "journey-scratch"


def _stage_banks(base: str) -> list[str]:
    return [f"{base}-{_SCRATCH_SUFFIX}-s{n}" for n in _STAGES]


def run_memory_journey(patient: Patient, records: list[MedicalRecord]) -> dict[str, Any]:
    """Run the staged retain→recall journey on real scratch banks."""
    hindsight = hindsight_client.get_hindsight()
    base = hindsight.ensure_bank(f"{_base_bank(patient)}")
    scratch_banks = _stage_banks(base)
    ordered = sorted(records, key=lambda r: (r.date, r.record_id))

    stages: list[dict[str, Any]] = []
    story_error: Optional[str] = None
    try:
        for stage_index, bank_id in enumerate(scratch_banks):
            n = _STAGES[stage_index]
            hindsight.delete_bank(bank_id)  # fresh scratch bank per stage
            hindsight.ensure_bank(bank_id)

            # Retain the first n records (chronological) — real retain calls.
            stage_records = ordered[: min(n, len(ordered))]
            retained = 0
            try:
                for record in stage_records:
                    result = hindsight.retain(
                        record_to_memory_items(record), bank_id=bank_id
                    )
                    retained += int(result.get("items_count", 0))

                # Same question at every stage — real recall calls.
                recall = recall_for_question(JOURNEY_QUESTION, patient, bank_id=bank_id)
                memories = recall.get("memories") or []
                record_ids = sorted({rid for m in memories for rid in (m.get("record_ids") or [])})
                dates = sorted({str((m.get("metadata") or {}).get("date", "")) for m in memories if m.get("metadata")})
                recall_failed = recall.get("failed", True)
            except Exception as exc:  # noqa: BLE001 — degrade honestly per stage
                logger.warning("[JOURNEY] stage %d failed: %s", n, exc)
                story_error = str(exc)
                stages.append({
                    "stage": stage_index + 1,
                    "interactions": n,
                    "records_in_memory": len(stage_records),
                    "memories_retained": retained,
                    "memories_recalled": 0,
                    "records_linked": [],
                    "record_count": 0,
                    "dates_covered": [],
                    "recall_available": False,
                    "preview": [],
                    "error": str(exc),
                })
                break

            stages.append({
                "stage": stage_index + 1,
                "interactions": n,
                "records_in_memory": len(stage_records),
                "memories_retained": retained,
                "memories_recalled": len(memories),
                "records_linked": record_ids,
                "record_count": len(record_ids),
                "dates_covered": dates,
                "recall_available": not recall_failed,
                "preview": [m.get("text", "")[:160] for m in memories[:3]],
            })
            logger.info(
                "[JOURNEY] stage %d: %d records in memory -> %d memories recalled, %d records linked",
                n, len(stage_records), len(memories), len(record_ids),
            )

        story = {
            "question": JOURNEY_QUESTION,
            "patient_id": patient.patient_id,
            "bank_base": base,
            "stages": stages,
            "note": (
                "Live demonstration: the same question at every stage, run against real "
                "Hindsight scratch banks. The only thing that changes is how much of the "
                "patient's history LifeLine remembers."
            ),
        }
        if story_error:
            story["error"] = story_error
            story["note"] += " The journey stopped early because the memory service reported an error."
        return story
    finally:
        for bank_id in scratch_banks:  # leave no residue, even on failure
            try:
                hindsight.delete_bank(bank_id)
            except Exception as exc:  # noqa: BLE001 — cleanup is best-effort
                logger.info("[JOURNEY] scratch bank cleanup skipped for %s: %s", bank_id, exc)


def _base_bank(patient: Patient) -> str:
    from app.services.hindsight.memory_service import bank_id_for_patient

    return bank_id_for_patient(patient)
