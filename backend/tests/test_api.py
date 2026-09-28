"""API tests using FastAPI TestClient with mocked Hindsight."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client():
    return TestClient(app)


class TestPatients:
    def test_get_patient(self, client, mock_hindsight, seeded_store):
        response = client.get("/api/patients/P-001")
        assert response.status_code == 200
        assert response.json()["patient"]["patient_id"] == "P-001"
        assert response.json()["synthetic"] is True

    def test_unknown_patient_404(self, client, mock_hindsight, seeded_store):
        assert client.get("/api/patients/NOPE").status_code == 404

    def test_create_patient(self, client, mock_hindsight, seeded_store):
        payload = {"patient": {
            "patient_id": "P-002", "name": "Demo Two", "age": 50, "sex": "F",
            "blood_type": "A+", "current_issue": "", "current_medications": [],
        }}
        assert client.post("/api/patients", json=payload).status_code == 200


class TestRecordsTimeline:
    def test_records_listed(self, client, mock_hindsight, seeded_store):
        response = client.get("/api/patients/P-001/records")
        assert response.status_code == 200
        assert response.json()["count"] == 3

    def test_timeline_chronological(self, client, mock_hindsight, seeded_store):
        response = client.get("/api/patients/P-001/timeline")
        assert response.status_code == 200
        dates = [e["date"] for e in response.json()["events"]]
        assert dates == sorted(dates)


class TestConflicts:
    def test_allergy_vs_medication_detected(self, client, mock_hindsight, seeded_store):
        response = client.get("/api/patients/P-001/conflicts")
        assert response.status_code == 200
        conflicts = response.json()["conflicts"]
        assert conflicts, "expected the planted allergy/medication conflict"
        assert conflicts[0]["status"] == "UNRESOLVED"


class TestChat:
    def test_chat_returns_structured_answer(self, client, mock_hindsight, seeded_store, monkeypatch):
        import app.services.agent as agent_module

        monkeypatch.setattr(agent_module.groq_service, "generate", lambda *a, **k: "Structured answer.")
        response = client.post("/api/chat", json={"patient_id": "P-001", "question": "What changed recently?"})
        assert response.status_code == 200
        body = response.json()
        for key in ("answer", "memories_used", "source_records", "timeline_events", "conflicts", "uncertainty", "safety_note"):
            assert key in body

    def test_chat_unknown_patient(self, client, mock_hindsight, seeded_store):
        response = client.post("/api/chat", json={"patient_id": "X", "question": "hi"})
        assert response.status_code == 404


class TestHandoff:
    def test_handoff_sections(self, client, mock_hindsight, seeded_store, monkeypatch):
        def fake_generate(*args, **kwargs):
            raise RuntimeError("LLM down — deterministic sections must still work")

        monkeypatch.setattr("app.services.llm.groq_service.generate", fake_generate)
        response = client.post("/api/handoff", json={"patient_id": "P-001"})
        assert response.status_code == 200
        sections = response.json()["sections"]
        for name in ("CURRENT CONTEXT", "RECENT HISTORY", "RELEVANT MEDICATION CHANGES",
                     "PRIOR RELATED EVENTS", "POTENTIAL CONFLICTS", "VERIFICATION NEEDED"):
            assert name in sections


class TestMemoryEndpoints:
    def test_memory_recall_endpoint(self, client, mock_hindsight, seeded_store):
        response = client.post("/api/memory/recall", json={"question": "medications", "patient_id": "P-001"})
        assert response.status_code == 200
        assert response.json()["available"] is True
        assert isinstance(response.json()["memories"], list)


class TestDefaultPatientResolution:
    """Endpoints that omit patient_id must resolve the patient from the store,
    never from a hardcoded default."""

    def test_memory_recall_without_patient_id(self, client, mock_hindsight, seeded_store):
        response = client.post("/api/memory/recall", json={"question": "medications"})
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["bank_id"].endswith("p-001")

    def test_memory_recall_unknown_explicit_patient_404(self, client, mock_hindsight, seeded_store):
        response = client.post("/api/memory/recall", json={"question": "medications", "patient_id": "NOPE"})
        assert response.status_code == 404

    def test_memory_status_without_patient_id(self, client, mock_hindsight, seeded_store, monkeypatch):
        from app.config import config
        monkeypatch.setattr(config, "hindsight_api_key", "test-key")
        response = client.get("/api/memory/status")
        assert response.status_code == 200
        body = response.json()
        assert body["available"] is True
        assert body["bank_id"].endswith("p-001")
        assert body["memory_count"] > 0

    def test_memory_status_unknown_patient_404(self, client, mock_hindsight, seeded_store, monkeypatch):
        from app.config import config
        monkeypatch.setattr(config, "hindsight_api_key", "test-key")
        response = client.get("/api/memory/status?patient_id=NOPE")
        assert response.status_code == 404

    def test_demo_mode_without_patient_id(self, client, mock_hindsight, seeded_store, monkeypatch):
        monkeypatch.setattr("app.services.llm.groq_service.generate", lambda *a, **k: "baseline")
        response = client.request("GET", "/api/demo/mode?question=What%20changed%3F")
        assert response.status_code == 200
        body = response.json()
        assert body["with_memory"]["memories_used"] >= 0
        assert body["without_memory"]["memories_used"] == 0

    def test_demo_mode_empty_store_404(self, client, mock_hindsight, tmp_path, monkeypatch):
        import app.services.records_store as store

        monkeypatch.setattr(store, "STORE_FILE", tmp_path / "empty.json")
        monkeypatch.setattr(store, "DATA_DIR", tmp_path)
        response = client.request("GET", "/api/demo/mode?question=What%20changed%3F")
        assert response.status_code == 404
        assert "seed" in response.json()["detail"].lower()

    def test_handoff_request_defaults_to_none(self, client, mock_hindsight, seeded_store, monkeypatch):
        monkeypatch.setattr("app.services.llm.groq_service.generate", lambda *a, **k: "polished")
        response = client.post("/api/handoff", json={})
        assert response.status_code == 200
        body = response.json()
        assert body["patient_id"] == "P-001"
        assert "CURRENT CONTEXT" in body["sections"]

    def test_demo_seed(self, client, mock_hindsight, seeded_store):
        response = client.post("/api/demo/seed", json={"reset": False})
        assert response.status_code == 200
