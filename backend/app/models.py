"""LifeLine data models (strongly typed, serialization-friendly)."""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date
from typing import Any, Optional


@dataclass
class Patient:
    patient_id: str
    name: str
    age: int
    sex: str
    blood_type: str
    photo_color: str = "#0f766e"
    is_synthetic: bool = True
    baseline_allergies: list[str] = field(default_factory=list)
    baseline_conditions: list[str] = field(default_factory=list)
    current_medications: list[str] = field(default_factory=list)
    current_issue: str = ""
    current_context_note: str = ""


@dataclass
class MedicalRecord:
    record_id: str
    patient_id: str
    date: str  # ISO date string, e.g. "2024-02-14"
    record_type: str  # visit | lab | prescription | medication_change | specialist | discharge | emergency | followup
    title: str
    facility: str = ""
    clinician: str = ""
    summary: str = ""
    body: str = ""
    source_filename: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TimelineEvent:
    date: str
    record_id: str
    record_type: str
    title: str
    kind: str  # visit | lab | medication | symptom | emergency | conflict
    detail: str = ""
    highlight: bool = False


@dataclass
class MemoryReference:
    id: str
    text: str
    score: float = 0.0
    record_ids: list[str] = field(default_factory=list)
    memory_type: str = ""
    date: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Conflict:
    conflict_id: str
    patient_id: str = ""  # owning patient; derived from the source record
    type: str = ""  # allergy_vs_medication | value_discrepancy | ...
    description: str = ""
    record_a_id: str = ""
    record_a_date: str = ""
    record_a_claim: str = ""
    record_b_id: str = ""
    record_b_date: str = ""
    record_b_claim: str = ""
    status: str = "UNRESOLVED"
    required_action: str = "Verify against the current clinical record."
    resolved: bool = False


@dataclass
class HandoffSummary:
    patient_id: str
    generated_at: str
    sections: dict[str, str]
    records_reviewed: list[str] = field(default_factory=list)
    safety_note: str = (
        "Prepared from stored synthetic records. Every item requires verification "
        "against the current clinical record by a clinician."
    )


@dataclass
class ChatAnswer:
    answer: str
    memories_used: list[dict[str, Any]] = field(default_factory=list)
    source_records: list[dict[str, Any]] = field(default_factory=list)
    timeline_events: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    uncertainty: list[str] = field(default_factory=list)
    safety_note: str = (
        "LifeLine organizes documented history only. It does not diagnose or treat. "
        "All items must be verified by a clinician."
    )
