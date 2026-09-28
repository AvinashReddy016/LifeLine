"""Agent tests: behavior under memory available, memory failure, and LLM failure."""
from __future__ import annotations

import app.services.agent as agent_module
from app.services.agent import answer_question


class TestAgentWithMemory:
    def test_answer_includes_memory_evidence(self, mock_hindsight, seeded_store):
        result = answer_question("P-001", "What medications were changed recently?")
        assert result.memories_used, "expected recalled memories in answer"
        assert any(m["record_ids"] == ["REC-1002"] for m in result.memories_used)
        assert result.safety_note

    def test_source_records_are_linked(self, mock_hindsight, seeded_store):
        result = answer_question("P-001", "Have similar symptoms appeared before?")
        assert result.source_records
        assert all("record_id" in sr for sr in result.source_records)


class TestAgentDegradation:
    def test_hindsight_failure_is_disclosed(self, mock_hindsight, seeded_store, monkeypatch):
        mock_hindsight.fail_recall = True

        class FakeLLM:
            class LLMUnavailableError(RuntimeError):
                pass

            class LLMError(RuntimeError):
                pass

            @staticmethod
            def generate(*args, **kwargs):
                return "LLM fallback answer text."

        monkeypatch.setattr(agent_module.groq_service, "generate", lambda *a, **k: "ok")
        result = answer_question("P-001", "What happened at the emergency visit?")
        assert any("Memory service unavailable" in u for u in result.uncertainty)

    def test_llm_failure_returns_evidence_only(self, mock_hindsight, seeded_store, monkeypatch):
        def raise_llm(*args, **kwargs):
            raise agent_module.groq_service.LLMUnavailableError("Groq down")

        monkeypatch.setattr(agent_module.groq_service, "generate", raise_llm)
        result = answer_question("P-001", "What medications were changed recently?")
        assert "LLM" in " ".join(result.uncertainty) or "unavailable" in " ".join(result.uncertainty)
        # Evidence-only answer still contains recalled memory text
        assert "REC-" in result.answer or "historical item" in result.answer

    def test_unknown_patient_404s(self, mock_hindsight, seeded_store):
        import pytest

        with pytest.raises(ValueError):
            answer_question("P-999", "hello")


class TestSafety:
    def test_safety_note_always_present(self, mock_hindsight, seeded_store):
        result = answer_question("P-001", "What should I tell the doctor?")
        assert "verified by a clinician" in result.safety_note

    def test_conflicts_surface_in_structured_answer(self, mock_hindsight, seeded_store):
        result = answer_question("P-001", "Are there conflicting entries in the history?")
        assert isinstance(result.conflicts, list)
