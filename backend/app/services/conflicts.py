"""Conflict detection: surface potential contradictions between records.

Rules are deliberately conservative and evidence-bound: each conflict cites the
two source records and always resolves to "UNRESOLVED — clinician verification
required". LifeLine never picks a winner between contradictory records.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from app.models import Conflict, MedicalRecord
from app.services.records_store import get_records

logger = logging.getLogger("lifeline.conflicts")

_ALLERGY_PATTERNS = [
    re.compile(r"allerg(?:y|ic)\s+to\s+([A-Z][A-Za-z-]+)", re.IGNORECASE),
    re.compile(r"([A-Z][A-Za-z-]+)\s+allergy", re.IGNORECASE),
]
_MED_ACTION = re.compile(
    r"\b(started|initiated|began|prescribed|switched to|discontinued|stopped|resumed)\b"
    r"\s+([A-Z][A-Za-z-]+)",
    re.IGNORECASE,
)
_STOP_WORDS = re.compile(r"\b(discontinued|stopped|held)\b", re.IGNORECASE)

# Medication-presence claims without an action verb (e.g. "pharmacy lists Penicillin V
# among home medications", "a bottle labeled Amoxicillin 500 mg"). Only drug names from
# the lexicon count, to avoid matching symptom words like "reports mild metallic taste".
_MED_PRESENCE = re.compile(
    r"\b(lists|listed|labeled|includes|included|taking|reconciliation|prescription)\b"
    r"[^.\n]{0,40}?\b([A-Z][A-Za-z-]+)(?:\s(?:V|500|250|100|50|40|20|10|5|2\.5))?\s?(?:mg)?\b",
    re.IGNORECASE,
)
_MED_CONTEXT_WORDS = re.compile(
    r"\b(medication|prescription|pharmacy|bottle|regimen|course|dose|mg|reconciliation|dispensed)\b",
    re.IGNORECASE,
)

# Curated drug lexicon for the synthetic demo dataset (documented in docs/memory-design.md).
DRUG_LEXICON = {
    "penicillin", "amoxicillin", "amlodipine", "losartan", "pantoprazole",
    "clarithromycin", "famotidine", "metformin", "atorvastatin", "ibuprofen",
}


def _allergy_drugs(record: MedicalRecord) -> dict[str, str]:
    """Return {drug -> matching snippet} for allergy claims in a record."""
    found: dict[str, str] = {}
    for pattern in _ALLERGY_PATTERNS:
        for match in pattern.finditer(record.body + " " + record.summary):
            drug = match.group(1).capitalize()
            if drug.lower() in {"no", "none", "unknown", "nkda"}:
                continue
            found.setdefault(drug, match.group(0))
    return found


def _med_events(record: MedicalRecord) -> list[tuple[str, str, bool]]:
    """Return [(drug, action_snippet, was_stopped)] medication events in a record."""
    events: list[tuple[str, str, bool]] = []
    for line in record.body.splitlines() + [record.summary]:
        for match in _MED_ACTION.finditer(line):
            drug = match.group(2).capitalize()
            if drug.lower() in {"the", "his", "her", "a", "an"}:
                continue
            events.append((drug, line.strip()[:180], bool(_STOP_WORDS.search(match.group(0)))))
    return events


def _med_presence(record: MedicalRecord) -> list[tuple[str, str, bool]]:
    """Return [(drug, snippet, False)] for passive medication-presence mentions."""
    events: list[tuple[str, str, bool]] = []
    for line in record.body.splitlines() + [record.summary]:
        if not _MED_CONTEXT_WORDS.search(line):
            continue
        for match in _MED_PRESENCE.finditer(line):
            drug = match.group(2).capitalize()
            if drug.lower() in DRUG_LEXICON:
                events.append((drug, line.strip()[:180], False))
    return events


def _all_med_events(record: MedicalRecord) -> list[tuple[str, str, bool]]:
    return _med_events(record) + _med_presence(record)


def detect_conflicts(records: Optional[list[MedicalRecord]] = None) -> list[Conflict]:
    """Scan records for potential contradictions."""
    records = records if records is not None else []
    if not records:
        return []
    conflicts: list[Conflict] = []

    for i, record_a in enumerate(records):
        # Rule 1: allergy claim in record A vs medication presence in record B.
        # Pairs are always within one patient — never compare across patients.
        for drug, snippet_a in _allergy_drugs(record_a).items():
            for record_b in records[i + 1:]:
                if record_b.record_id == record_a.record_id:
                    continue
                if record_b.patient_id != record_a.patient_id:
                    continue
                for drug_b, snippet_b, stopped in _all_med_events(record_b):
                    if drug_b.lower() == drug.lower() and not stopped:
                        conflicts.append(Conflict(
                            conflict_id=f"CF-{record_a.record_id}-{record_b.record_id}-{drug.lower()}",
                            patient_id=record_a.patient_id,
                            type="allergy_vs_medication",
                            description=(
                                f"{drug} is documented as an allergy in {record_a.record_id} "
                                f"({record_a.date}) but appears in a medication record in "
                                f"{record_b.record_id} ({record_b.date})."
                            ),
                            record_a_id=record_a.record_id,
                            record_a_date=record_a.date,
                            record_a_claim=snippet_a,
                            record_b_id=record_b.record_id,
                            record_b_date=record_b.date,
                            record_b_claim=snippet_b,
                        ))

    # Rule 2: same drug marked discontinued in one record, active in a later record
    med_events: list[tuple[MedicalRecord, str, str, bool]] = []
    for record in records:
        for drug, snippet, stopped in _med_events(record):
            med_events.append((record, drug, snippet, stopped))
    for drug in {drug for _, drug, _, _ in med_events}:
        drug_events = sorted(
            [event for event in med_events if event[1] == drug],
            key=lambda event: event[0].date,
        )
        for j, (record_a, _, snippet_a, stopped_a) in enumerate(drug_events):
            if not stopped_a:
                continue
            for record_b, _, snippet_b, stopped_b in drug_events[j + 1:]:
                if not stopped_b and record_b.date > record_a.date:
                    conflicts.append(Conflict(
                        conflict_id=f"CF-{drug.lower()}-{record_a.record_id}-{record_b.record_id}",
                        patient_id=record_a.patient_id,
                        type="discontinued_vs_active",
                        description=(
                            f"{drug} was discontinued in {record_a.record_id} ({record_a.date}) "
                            f"but appears as active again in {record_b.record_id} ({record_b.date})."
                        ),
                        record_a_id=record_a.record_id,
                        record_a_date=record_a.date,
                        record_a_claim=snippet_a,
                        record_b_id=record_b.record_id,
                        record_b_date=record_b.date,
                        record_b_claim=snippet_b,
                    ))
                    break  # one conflict per drug pair chain

    # Rule 3: exact duplicate claims with different values (same test, different result)
    lab_pattern = re.compile(r"(HbA1c|hemoglobin A1c):\s*([\d.]+)\s*%", re.IGNORECASE)
    lab_values: dict[str, list[tuple[MedicalRecord, str, str]]] = {}
    for record in records:
        for match in lab_pattern.finditer(record.body):
            lab_values.setdefault(match.group(1).upper(), []).append(
                (record, match.group(0), match.group(2))
            )
    for test, entries in lab_values.items():
        dates = {e[0].date for e in entries}
        values = {e[2] for e in entries}
        if len(dates) == 1 and len(values) > 1:
            record_a, snippet_a, _ = entries[0]
            record_b, snippet_b, _ = entries[1]
            conflicts.append(Conflict(
                conflict_id=f"CF-lab-{record_a.record_id}-{record_b.record_id}",
                patient_id=record_a.patient_id,
                type="value_discrepancy",
                description=(
                    f"Two records dated {record_a.date} report different {test} values."
                ),
                record_a_id=record_a.record_id,
                record_a_date=record_a.date,
                record_a_claim=snippet_a,
                record_b_id=record_b.record_id,
                record_b_date=record_b.date,
                record_b_claim=snippet_b,
            ))

    if conflicts:
        logger.info("[CONFLICTS] %d potential conflict(s) detected", len(conflicts))
    return conflicts
