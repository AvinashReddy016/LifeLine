"""Shared pytest fixtures: offline Hindsight mock + seeded stores.

The mock is a real (tiny) memory engine, not a fixed corpus: retain() stores items
into per-patient banks, recall() scores stored memories by token overlap with the
query, and nothing is returned unless it was previously retained into THAT bank.
This makes the tests prove genuine retain->recall behavior instead of testing
against hardcoded memories.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Conflict, MedicalRecord, Patient  # noqa: E402

STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "was", "were",
    "is", "are", "what", "when", "how", "did", "do", "does", "with", "at", "by",
    "from", "this", "that", "it", "be", "been", "has", "have", "had", "i", "you",
    "we", "my", "your", "tell", "me", "should", "before", "after", "since",
    "last", "recent", "recently", "new", "any", "there",
}


def _tokens(text: str) -> set[str]:
    raw = {
        tok for tok in re.findall(r"[a-z0-9]+", text.lower())
        if tok not in STOPWORDS and len(tok) > 2
    }
    # Light stemming so plural/singular forms match (symptoms ~ symptom).
    return {tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok for tok in raw}


class MockHindsight:
    """Banked, query-sensitive stand-in for HindsightClientWrapper."""

    def __init__(self) -> None:
        self.banks: dict[str, list[dict]] = {}
        self.recall_log: list[tuple[str, str]] = []
        self.retain_log: list[tuple[int, str]] = []
        self.reflect_log: list[tuple[str, str]] = []
        self.delete_log: list[str] = []
        self.fail_retain = False
        self.fail_recall = False
        self.fail_only: set[str] = set()  # substring match on queries

    # ------------------------------------------------------------- lifecycle
    def ensure_bank(self, bank_id=None) -> str:
        bank_id = bank_id or "default"
        self.banks.setdefault(bank_id, [])
        return bank_id

    # ------------------------------------------------------------- operations
    def delete_bank(self, bank_id):
        self.delete_log.append(bank_id)
        self.banks.pop(bank_id, None)

    def retain(self, items, bank_id=None):
        if self.fail_retain:
            raise RuntimeError("Hindsight retain failed (simulated)")
        bank_id = self.ensure_bank(bank_id)
        stored = []
        for i, item in enumerate(items):
            stored.append({
                "id": f"{bank_id}-mem-{len(self.banks[bank_id]) + i}",
                "text": item["content"],
                "memory_type": "experience",
                "metadata": {**item.get("metadata", {}), "context": item.get("context", "")},
            })
        self.banks[bank_id].extend(stored)
        self.retain_log.append((len(items), bank_id))
        return {"success": True, "items_count": len(items)}

    def recall(self, query, limit=8, types=None, bank_id=None):
        if self.fail_recall or (self.fail_only and any(f in query for f in self.fail_only)):
            raise RuntimeError("Hindsight recall failed (simulated)")
        bank_id = bank_id or "default"
        self.recall_log.append((query, bank_id))
        query_tokens = _tokens(query)
        scored = []
        for memory in self.banks.get(bank_id, []):
            memory_tokens = _tokens(memory["text"] + " " + str(memory["metadata"].get("context", "")))
            overlap = query_tokens & memory_tokens
            if not overlap:
                continue  # no lexical relevance -> not returned (query-sensitive)
            score = min(0.99, 0.5 + 0.08 * len(overlap))
            record_id = memory["metadata"].get("record_id")
            scored.append({
                **memory,
                "score": round(score, 4),
                "record_ids": [record_id] if isinstance(record_id, str) and record_id else [],
            })
        scored.sort(key=lambda m: m["score"], reverse=True)
        return scored[:limit]

    def reflect(self, query, context=None, bank_id=None):
        if self.fail_recall:
            raise RuntimeError("Hindsight reflect failed (simulated)")
        bank_id = self.ensure_bank(bank_id)
        self.reflect_log.append((query, bank_id))
        memories = self.banks.get(bank_id, [])
        med = sum(1 for m in memories if "medication" in m["text"].lower())
        return {
            "text": (
                f"Longitudinal synthesis over {len(memories)} stored memories "
                f"({med} medication-related). No diagnosis implied."
            ),
            "based_on": [{"text": m["text"][:80]} for m in memories[:3]],
        }

    def list_memories(self, limit=200, bank_id=None):
        bank_id = self.ensure_bank(bank_id)
        return [
            {"id": m["id"], "text": m["text"], "memory_type": m["memory_type"], "created_at": ""}
            for m in self.banks[bank_id][:limit]
        ]

    # ------------------------------------------------------------- inspection
    def interaction_count(self) -> int:
        return sum(
            1 for bank in self.banks.values() for m in bank
            if m["metadata"].get("event_type") == "interaction"
        )


@pytest.fixture()
def mock_hindsight(monkeypatch):
    mock = MockHindsight()
    monkeypatch.setattr("app.services.hindsight.client.get_hindsight", lambda: mock)
    monkeypatch.setattr("app.services.agent_history.get_hindsight", lambda: mock)
    yield mock


def _install_store(tmp_path, monkeypatch):
    import app.services.records_store as store

    store.STORE_FILE = tmp_path / "store.json"
    store.DATA_DIR = tmp_path
    return store


def _seed(store, patient: Patient, records: list[MedicalRecord]):
    """Store records locally AND retain them into the patient's Hindsight bank."""
    from app.services.hindsight.memory_service import retain_records

    store.upsert_patient(patient)
    store.upsert_records(records)
    retain_records(records, patient=patient)


@pytest.fixture()
def seeded_store(tmp_path, monkeypatch, mock_hindsight):
    """Small store (3 records) with records retained into the mock memory bank."""
    store = _install_store(tmp_path, monkeypatch)
    patient = Patient(
        patient_id="P-001", name="Test Patient", age=40, sex="Other", blood_type="O+",
        current_issue="Dizziness", current_medications=["Amlodipine 2.5 mg daily"],
    )
    records = [
        MedicalRecord(
            record_id="REC-1001", patient_id="P-001", date="2025-03-18",
            record_type="medication_change", title="Med change", facility="Clinic",
            clinician="Dr. Test", summary="Allergy noted",
            body="Intake note: patient reports Penicillin allergy (patient-reported). Medications: Discontinued Amlodipine 5 mg daily.",
        ),
        MedicalRecord(
            record_id="REC-1002", patient_id="P-001", date="2025-11-02",
            record_type="emergency", title="ED visit", facility="Emergency Department",
            clinician="Dr. Test", summary="Dizziness",
            body="Dizziness with near-syncope. Vitals low-normal. Symptom documented: dizziness on standing.",
        ),
        MedicalRecord(
            record_id="REC-1003", patient_id="P-001", date="2026-01-10",
            record_type="prescription", title="Rx", facility="Clinic",
            clinician="Dr. Test", summary="New rx",
            body="Medications: Started Amlodipine 2.5 mg daily.",
        ),
    ]
    _seed(store, patient, records)
    yield store


@pytest.fixture()
def demo_dataset_store(tmp_path, monkeypatch, mock_hindsight):
    """Full 17-record synthetic dataset (Arjun Mehra), retained into the mock bank."""
    store = _install_store(tmp_path, monkeypatch)
    data = json.loads((BACKEND_ROOT / "seed" / "patients.json").read_text(encoding="utf-8"))
    patient = Patient(**data["patient"])
    records = [MedicalRecord(**r) for r in data["records"]]
    _seed(store, patient, records)
    yield store


@pytest.fixture()
def sample_conflict() -> Conflict:
    return Conflict(
        conflict_id="CF-TEST",
        type="allergy_vs_medication",
        description="Penicillin documented as an allergy but appears in a later medication record.",
        record_a_id="REC-1001", record_a_date="2025-03-18", record_a_claim="Penicillin allergy reported",
        record_b_id="REC-1003", record_b_date="2026-01-10", record_b_claim="Started Amoxicillin",
    )
