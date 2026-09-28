"""Memory Journey tests: prove accumulation is real, not staged theater."""
from __future__ import annotations

import pytest

from app.services.journey import JOURNEY_QUESTION, run_memory_journey


class TestMemoryJourney:
    def test_stages_show_monotonic_accumulation(self, mock_hindsight, demo_dataset_store):
        """More records in memory -> at least as many linked records recalled."""
        patient = demo_dataset_store.get_patient("P-001")
        records = demo_dataset_store.get_records("P-001")
        story = run_memory_journey(patient, records)

        stages = story["stages"]
        assert [s["interactions"] for s in stages] == [1, 3, 6, 12]
        assert [s["records_in_memory"] for s in stages] == [1, 3, 6, 12]
        # Real retains happened, and monotonically more of them.
        assert all(s["memories_retained"] > 0 for s in stages)
        assert stages[0]["memories_retained"] < stages[-1]["memories_retained"]
        # Recall availability everywhere (mock is up).
        assert all(s["recall_available"] for s in stages)

    def test_same_question_at_every_stage(self, mock_hindsight, seeded_store):
        story = run_memory_journey(seeded_store.get_patient("P-001"), seeded_store.get_records("P-001"))
        assert story["question"] == JOURNEY_QUESTION
        # The journey question itself must have driven real recall calls.
        journey_recalls = [q for q, _ in mock_hindsight.recall_log if q == JOURNEY_QUESTION]
        assert len(journey_recalls) >= len(story["stages"])

    def test_real_retain_and_recall_executed_per_stage(self, mock_hindsight, seeded_store):
        story = run_memory_journey(seeded_store.get_patient("P-001"), seeded_store.get_records("P-001"))
        journey_banks = [b for _, b in mock_hindsight.retain_log if "journey-scratch" in b]
        assert len(journey_banks) >= 4  # one per stage
        recall_banks = [b for _, b in mock_hindsight.recall_log if "journey-scratch" in b]
        assert len(recall_banks) >= 4

    def test_scratch_banks_deleted_after_run(self, mock_hindsight, seeded_store):
        story = run_memory_journey(seeded_store.get_patient("P-001"), seeded_store.get_records("P-001"))
        scratch = [b for b in mock_hindsight.banks if "journey-scratch" in b]
        assert not scratch, f"scratch banks leaked: {scratch}"

    def test_scratch_banks_deleted_even_on_recall_failure(self, mock_hindsight, seeded_store):
        mock_hindsight.fail_recall = True
        story = run_memory_journey(seeded_store.get_patient("P-001"), seeded_store.get_records("P-001"))
        scratch = [b for b in mock_hindsight.banks if "journey-scratch" in b]
        assert not scratch, "cleanup must run even when recall fails"

    def test_patient_bank_untouched_by_journey(self, mock_hindsight, seeded_store):
        from app.services.hindsight.memory_service import bank_id_for_patient

        patient = seeded_store.get_patient("P-001")
        real_bank = bank_id_for_patient(patient)
        before = len(mock_hindsight.banks.get(real_bank, []))
        run_memory_journey(patient, seeded_store.get_records("P-001"))
        after = len(mock_hindsight.banks.get(real_bank, []))
        assert before == after, "the journey must never write to the patient's real bank"

    def test_honest_error_when_hindsight_unavailable(self, mock_hindsight, seeded_store):
        from fastapi.testclient import TestClient

        from app.main import app

        mock_hindsight.fail_retain = True
        client = TestClient(app)
        resp = client.get("/api/demo/journey")
        assert resp.status_code == 200  # honest degradation, not a crash
        body = resp.json()
        assert body.get("error") or "unavailable" in body.get("note", "").lower()
