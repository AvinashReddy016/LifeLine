"""Regression tests for the Conflict patient_id schema.

Covers:
- a Conflict carrying patient_id round-trips through the JSON store,
- legacy rows written BEFORE patient_id existed still load (graceful migration),
- conflicts belonging to Patient A never appear for Patient B (isolation),
- live conflict detection never pairs records from different patients.
"""
from __future__ import annotations

import json

from app.models import Conflict, MedicalRecord
from app.services.conflicts import detect_conflicts
from app.services.records_store import (
    get_conflicts,
    get_conflicts_for_patient,
    upsert_conflicts,
)


def _conflict(patient_id: str, suffix: str = "a") -> Conflict:
    return Conflict(
        conflict_id=f"CF-TEST-{patient_id}-{suffix}",
        patient_id=patient_id,
        type="allergy_vs_medication",
        description="Penicillin documented as an allergy but appears in a later medication record.",
        record_a_id=f"REC-{patient_id}-A",
        record_a_date="2025-03-18",
        record_a_claim="Penicillin allergy reported",
        record_b_id=f"REC-{patient_id}-B",
        record_b_date="2026-01-10",
        record_b_claim="Started Amoxicillin",
    )


class TestConflictRoundTrip:
    def test_conflict_with_patient_id_survives_store_cycle(self, seeded_store):
        upsert_conflicts([_conflict("P-001")])

        loaded = get_conflicts()
        match = [c for c in loaded if c.conflict_id == "CF-TEST-P-001-a"]
        assert match, "conflict with patient_id was not persisted"
        assert match[0].patient_id == "P-001"
        assert match[0].type == "allergy_vs_medication"
        assert match[0].record_a_id == "REC-P-001-A"

    def test_stored_row_is_serialized_with_patient_id(self, seeded_store):
        upsert_conflicts([_conflict("P-001")])
        raw = json.loads(seeded_store.STORE_FILE.read_text(encoding="utf-8"))
        row = raw["conflicts"]["CF-TEST-P-001-a"]
        assert row["patient_id"] == "P-001"

    def test_legacy_row_without_patient_id_loads_gracefully(self, seeded_store):
        """A row written by the OLD schema (extra or missing keys) must not crash."""
        legacy_row = {
            "conflict_id": "CF-LEGACY-1",
            # no patient_id — old schema
            "type": "allergy_vs_medication",
            "description": "Legacy conflict from previous schema",
            "record_a_id": "REC-1001",
            "record_a_date": "2025-03-18",
            "record_a_claim": "Penicillin allergy reported",
            "record_b_id": "REC-1003",
            "record_b_date": "2026-01-10",
            "record_b_claim": "Started Amoxicillin",
            "status": "UNRESOLVED",
            "required_action": "Verify against the current clinical record.",
            "resolved": False,
        }
        raw = json.loads(seeded_store.STORE_FILE.read_text(encoding="utf-8"))
        raw["conflicts"]["CF-LEGACY-1"] = legacy_row
        seeded_store.STORE_FILE.write_text(json.dumps(raw), encoding="utf-8")

        loaded = get_conflicts()  # must not raise TypeError
        legacy = [c for c in loaded if c.conflict_id == "CF-LEGACY-1"]
        assert legacy, "legacy row was dropped"
        assert legacy[0].patient_id == ""  # tolerated, ownership resolved at read time

    def test_legacy_row_with_extra_unknown_keys_loads(self, seeded_store):
        raw = json.loads(seeded_store.STORE_FILE.read_text(encoding="utf-8"))
        raw["conflicts"]["CF-FUTURE"] = {
            "conflict_id": "CF-FUTURE",
            "patient_id": "P-001",
            "type": "allergy_vs_medication",
            "description": "row written by a NEWER schema with extra fields",
            "record_a_id": "REC-1001", "record_a_date": "2025-03-18", "record_a_claim": "a",
            "record_b_id": "REC-1003", "record_b_date": "2026-01-10", "record_b_claim": "b",
            "some_future_field": {"nested": True},
        }
        seeded_store.STORE_FILE.write_text(json.dumps(raw), encoding="utf-8")
        assert any(c.conflict_id == "CF-FUTURE" for c in get_conflicts())


class TestConflictPatientIsolation:
    def test_patient_a_conflicts_never_served_for_patient_b(self, seeded_store):
        upsert_conflicts([_conflict("P-001"), _conflict("P-002", "b")])

        a = get_conflicts(patient_id="P-001")
        b = get_conflicts(patient_id="P-002")
        assert {c.patient_id for c in a} == {"P-001"}
        assert {c.patient_id for c in b} == {"P-002"}
        assert not ({c.conflict_id for c in a} & {c.conflict_id for c in b})

    def test_get_conflicts_for_patient_derives_from_records(self, seeded_store):
        # seeded_store has REC-1001..1003 for P-001
        upsert_conflicts([_conflict("P-001"), _conflict("P-002", "b")])
        a = get_conflicts_for_patient("P-001")
        assert all(c.conflict_id == "CF-TEST-P-001-a" or c.patient_id == "P-001" for c in a)
        assert all("P-002" != c.patient_id for c in a)

    def test_detection_never_crosses_patients(self, mock_hindsight, seeded_store):
        """Two patients with the SAME allergy/drug pattern must not cross-conflict."""
        import pytest

        from app.services.records_store import upsert_patient, upsert_records

        shared_body = (
            "Intake note: patient reports Penicillin allergy (patient-reported). "
            "Medications: Pharmacy lists Penicillin V among home medications."
        )
        patient_b = seeded_store.Patient(  # type: ignore[attr-defined]
            patient_id="P-002", name="Patient B", age=60, sex="F", blood_type="A+",
            current_issue="", current_medications=[],
        ) if hasattr(seeded_store, "Patient") else None
        from app.models import Patient as PatientModel

        patient_b = PatientModel(
            patient_id="P-002", name="Patient B", age=60, sex="F", blood_type="A+",
            current_issue="", current_medications=[],
        )
        upsert_patient(patient_b)
        upsert_records([
            MedicalRecord(
                record_id="REC-B1", patient_id="P-002", date="2025-03-18",
                record_type="visit", title="Intake", facility="Clinic", clinician="Dr. B",
                summary="Allergy noted", body=shared_body,
            ),
            MedicalRecord(
                record_id="REC-B2", patient_id="P-002", date="2026-01-10",
                record_type="prescription", title="Rx", facility="Clinic", clinician="Dr. B",
                summary="Rx", body="Medications: Started Penicillin V 500 mg.",
            ),
        ])

        a_conflicts = detect_conflicts(seeded_store.get_records("P-001"))
        b_conflicts = detect_conflicts(seeded_store.get_records("P-002"))
        cross = detect_conflicts(seeded_store.get_records("P-001") + seeded_store.get_records("P-002"))

        assert all(c.patient_id == "P-001" for c in a_conflicts)
        assert all(c.patient_id == "P-002" for c in b_conflicts)
        # The deliberate mixed list is per-patient records concatenated; every pair
        # must still be same-patient.
        for c in cross:
            owner = c.patient_id
            assert owner in ("P-001", "P-002")
        # And no conflict id may reference records from both patients
        for c in cross:
            ids = {c.record_a_id, c.record_b_id}
            assert ids <= {"REC-1001", "REC-1002", "REC-1003"} or ids <= {"REC-B1", "REC-B2"}


class TestConflictDetectionNotWeakened:
    def test_seeded_dataset_still_yields_conflicts(self, seeded_store):
        from app.services.records_store import get_records

        conflicts = detect_conflicts(get_records("P-001"))
        assert conflicts, "conflict detection must keep firing on the seeded dataset"
        assert all(c.patient_id == "P-001" for c in conflicts)

    def test_api_scopes_conflicts_to_requested_patient(self, mock_hindsight, seeded_store):
        from fastapi.testclient import TestClient

        from app.main import app

        upsert_conflicts([_conflict("P-001"), _conflict("P-002", "b")])
        client = TestClient(app)
        body = client.get("/api/patients/P-001/conflicts").json()
        ids = {c["conflict_id"] for c in body["conflicts"]}
        assert "CF-TEST-P-001-a" in ids
        assert "CF-TEST-P-002-b" not in ids
        assert body["status"].startswith("UNRESOLVED")
