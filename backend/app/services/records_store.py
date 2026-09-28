"""In-memory record store (prototype-grade persistence).

Records live in a JSON file on disk so reseeding and restarts behave sanely.
Production deployments would replace this with a real database + auth.
"""
from __future__ import annotations

import json
import logging
import threading
from dataclasses import fields
from pathlib import Path
from typing import Optional

from app.models import Conflict, MedicalRecord, Patient

logger = logging.getLogger("lifeline.store")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
STORE_FILE = DATA_DIR / "store.json"

_lock = threading.Lock()


def _load() -> dict:
    if STORE_FILE.exists():
        try:
            return json.loads(STORE_FILE.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not parse store file (%s); starting empty", exc)
    return {"patients": {}, "records": {}, "conflicts": {}}


def _save(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STORE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")


# ------------------------------------------------------------------ patients

def upsert_patient(patient: Patient) -> Patient:
    with _lock:
        state = _load()
        state["patients"][patient.patient_id] = patient.__dict__
        _save(state)
    return patient


def get_patient(patient_id: str) -> Optional[Patient]:
    raw = _load().get("patients", {}).get(patient_id)
    return Patient(**raw) if raw else None


def list_patients() -> list[Patient]:
    return [Patient(**raw) for raw in _load().get("patients", {}).values()]


# ------------------------------------------------------------------ records

def upsert_records(records: list[MedicalRecord]) -> int:
    with _lock:
        state = _load()
        for record in records:
            state["records"][record.record_id] = record.to_dict()
        _save(state)
    return len(records)


def get_records(patient_id: str) -> list[MedicalRecord]:
    raw = [r for r in _load().get("records", {}).values() if r.get("patient_id") == patient_id]
    records = [MedicalRecord(**r) for r in raw]
    records.sort(key=lambda r: r.date)
    return records


def get_record(record_id: str) -> Optional[MedicalRecord]:
    raw = _load().get("records", {}).get(record_id)
    return MedicalRecord(**raw) if raw else None


def clear_patient_data(patient_id: str) -> None:
    with _lock:
        state = _load()
        state["records"] = {k: v for k, v in state.get("records", {}).items()
                            if v.get("patient_id") != patient_id}
        # Conflicts are scoped by their source records: a conflict survives only
        # if its record A still belongs to a remaining patient (conflicts never
        # span patients, so checking record A is sufficient).
        remaining = {r["record_id"] for r in state["records"].values()}
        state["conflicts"] = {k: v for k, v in state.get("conflicts", {}).items()
                              if v.get("record_a_id") in remaining}
        _save(state)


def get_conflicts_for_patient(patient_id: str) -> list[Conflict]:
    """Conflicts owned by one patient, derived from its stored records."""
    record_ids = {r.record_id for r in get_records(patient_id)}
    return [c for c in get_conflicts()
            if c.patient_id == patient_id or c.record_a_id in record_ids]


# ------------------------------------------------------------------ conflicts

# Legacy store rows may predate the patient_id field on Conflict; tolerate them
# instead of crashing (migrated lazily on read).
_CONFLICT_FIELDS = {f.name for f in fields(Conflict)}


def _conflict_from_row(raw: dict) -> Conflict:
    """Build a Conflict from a stored row, tolerating legacy/unknown keys."""
    return Conflict(**{k: v for k, v in raw.items() if k in _CONFLICT_FIELDS})


def upsert_conflicts(conflicts: list[Conflict]) -> int:
    with _lock:
        state = _load()
        for conflict in conflicts:
            state["conflicts"][conflict.conflict_id] = conflict.__dict__
        _save(state)
    return len(conflicts)


def get_conflicts(patient_id: Optional[str] = None) -> list[Conflict]:
    """Stored conflicts, optionally scoped to one patient (patient isolation)."""
    conflicts = [_conflict_from_row(raw) for raw in _load().get("conflicts", {}).values()]
    if patient_id:
        conflicts = [c for c in conflicts if c.patient_id == patient_id]
    return conflicts


def reset_store() -> None:
    with _lock:
        _save({"patients": {}, "records": {}, "conflicts": {}})
