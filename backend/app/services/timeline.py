"""Timeline reconstruction: chronological, source-linked patient story."""
from __future__ import annotations

import re
from typing import Optional

from app.models import MedicalRecord, TimelineEvent
from app.services.records_store import get_records

_MED_PATTERN = re.compile(
    r"(started|initiated|began|switched to|discontinued|stopped|titrated|increased|decreased)"
    r"\s+([A-Z][A-Za-z0-9-]+(?:\s\d+(?:\.\d+)?\s?(?:mg|mcg|unit|units))?)",
    re.IGNORECASE,
)

_SYMPTOM_PATTERN = re.compile(
    r"(symptom|pain|dizziness|nausea|headache|rash|fatigue|dyspepsia|vertigo|palpitation"
    r"|swelling|breathless|itching|hives|fever|cough|vomiting|diarrhea)",
    re.IGNORECASE,
)


def _kind_for(record: MedicalRecord, detail: str) -> str:
    if record.record_type in ("emergency",):
        return "emergency"
    if record.record_type in ("prescription", "medication_change"):
        return "medication"
    if record.record_type == "lab":
        return "lab"
    if _SYMPTOM_PATTERN.search(detail or record.body):
        return "symptom"
    return "visit"


def _detail_from(record: MedicalRecord) -> str:
    """Pick the most informative single line for the timeline entry."""
    for line in record.body.splitlines():
        stripped = line.strip().lstrip("-•*").strip()
        if stripped and not stripped.endswith(":"):
            return stripped[:220]
    return (record.summary or record.title)[:220]


def build_timeline(patient_id: str, up_to: Optional[str] = None) -> list[TimelineEvent]:
    """Build the longitudinal timeline from stored records (chronological)."""
    events: list[TimelineEvent] = []
    for record in get_records(patient_id):
        if up_to and record.date > up_to:
            continue
        detail = _detail_from(record)
        events.append(
            TimelineEvent(
                date=record.date,
                record_id=record.record_id,
                record_type=record.record_type,
                title=record.title,
                kind=_kind_for(record, detail),
                detail=detail,
                highlight=False,
            )
        )
    events.sort(key=lambda e: e.date)
    return events


def events_from_memories(memories: list[dict[str, Any]]) -> list[TimelineEvent]:
    """Timeline events derived from recalled memories (used in chat answers)."""
    events: list[TimelineEvent] = []
    for memory in memories:
        text = memory.get("text", "")
        date = (memory.get("metadata") or {}).get("date", "")
        if not date:
            match = re.search(r"\b(20\d{2})-(\d{2})-(\d{2})\b", text)
            date = match.group(0) if match else ""
        if not date:
            continue
        events.append(
            TimelineEvent(
                date=date,
                record_id=next(iter(memory.get("record_ids") or []), ""),
                record_type="memory",
                title=text[:80],
                kind="symptom" if _SYMPTOM_PATTERN.search(text) else "visit",
                detail=text[:220],
                highlight=True,
            )
        )
    events.sort(key=lambda e: e.date)
    return events
