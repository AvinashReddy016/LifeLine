"""Hindsight memory-layer tests (mocked SDK; real HTTP is exercised in smoke tests)."""
from __future__ import annotations

from app.models import MedicalRecord
from app.services.hindsight.memory_service import (
    build_recall_queries,
    recall_for_question,
    record_to_memory_items,
)
from app.services.hindsight.client import HindsightUnavailableError


def _record(**overrides) -> MedicalRecord:
    base = dict(
        record_id="REC-2001", patient_id="P-001", date="2025-03-18",
        record_type="medication_change", title="Med change",
        facility="Clinic", clinician="Dr. Test",
        summary="Therapy switched after side effect.",
        body="Medications: Discontinued Amlodipine 5 mg daily. Started Losartan 50 mg daily. Intake: Penicillin allergy noted.",
        source_filename="",
    )
    base.update(overrides)
    return MedicalRecord(**base)


class TestRetainDecomposition:
    def test_record_produces_multiple_items(self):
        items = record_to_memory_items(_record())
        assert len(items) >= 3  # summary + fact lines

    def test_provenance_metadata_present(self):
        items = record_to_memory_items(_record())
        for item in items:
            assert item["metadata"]["record_id"] == "REC-2001"
            assert item["metadata"]["date"] == "2025-03-18"
            assert item["metadata"]["synthetic"] is True

    def test_timestamp_carries_record_date(self):
        items = record_to_memory_items(_record())
        assert all(item["timestamp"] == "2025-03-18T09:00:00Z" for item in items)


class TestRecallPlanning:
    def test_medication_question_adds_dimension(self):
        plan = build_recall_queries("What medications were started recently?")
        dimensions = {step["dimension"] for step in plan}
        assert "medication_history" in dimensions

    def test_change_question_adds_temporal_dimension(self):
        plan = build_recall_queries("What changed since the last hospital visit?")
        assert "recent_changes" in {step["dimension"] for step in plan}

    def test_simple_question_stays_single_query(self):
        plan = build_recall_queries("Hello")
        assert len(plan) == 1


class TestRecallExecution:
    def test_recall_merges_and_ranks(self, mock_hindsight, seeded_store):
        result = recall_for_question("What medications changed recently?", seeded_store.get_patient("P-001"))
        assert result["failed"] is False
        assert mock_hindsight.recall_log  # real recall calls were made
        scores = [m["score"] for m in result["memories"]]
        assert scores == sorted(scores, reverse=True)
        assert any(m["record_ids"] == ["REC-1001"] or m["record_ids"] == ["REC-1003"]
                   for m in result["memories"])

    def test_empty_recall_is_handled(self, mock_hindsight, seeded_store):
        bank = "test-bank"
        for b in mock_hindsight.banks:
            mock_hindsight.banks[b] = []
        result = recall_for_question("anything at all", seeded_store.get_patient("P-001"))
        assert result["failed"] is False
        assert result["memories"] == []

    def test_hindsight_outage_reported_honestly(self, mock_hindsight, seeded_store):
        mock_hindsight.fail_recall = True
        result = recall_for_question("anything", seeded_store.get_patient("P-001"))
        assert result["failed"] is True
        assert result["error"]


class TestUnavailability:
    def test_wrapper_raises_clean_error_when_unconfigured(self, monkeypatch):
        from app.config import config
        from app.services.hindsight.client import HindsightClientWrapper

        monkeypatch.setattr(config, "hindsight_api_key", "")
        monkeypatch.setattr(config, "hindsight_base_url", "https://api.hindsight.vectorize.io")
        wrapper = HindsightClientWrapper()
        import pytest

        with pytest.raises(HindsightUnavailableError):
            wrapper._raw_client()
