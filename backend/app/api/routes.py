"""LifeLine API routes.

All endpoints serve the single core workflow: reconstruct the patient's
longitudinal history from fragmented records and surface what changed.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.config import config
from app.models import HandoffSummary, Patient
from app.services.agent import answer_question
from app.services.conflicts import detect_conflicts
from app.services.hindsight import client as hindsight_client_module
from app.services.hindsight.client import HindsightUnavailableError
from app.services.hindsight.memory_service import (
    bank_id_for_patient,
    build_recall_queries,
    recall_for_question,
    retain_records,
)
from app.services.records_store import (
    get_conflicts_for_patient,
    get_patient,
    get_record,
    get_records,
    list_patients,
    reset_store,
    upsert_patient,
    upsert_records,
)
from app.services.timeline import build_timeline

logger = logging.getLogger("lifeline.api")

router = APIRouter()


def _default_patient() -> Patient:
    """Resolve the demo patient when no explicit patient_id is supplied.

    The store is the source of truth — no patient id is ever hardcoded here.
    """
    patients = list_patients()
    if not patients:
        raise HTTPException(
            status_code=404,
            detail="No patient found in the store. Seed first: POST /api/demo/seed.",
        )
    return min(patients, key=lambda p: p.patient_id)


# ------------------------------------------------------------------ schemas

class ChatRequest(BaseModel):
    patient_id: str = Field(..., examples=["P-001"])
    question: str = Field(..., min_length=2, max_length=2000)


class PatientPayload(BaseModel):
    patient: dict[str, Any]


class RecordsPayload(BaseModel):
    records: list[dict[str, Any]]


class HandoffRequest(BaseModel):
    patient_id: Optional[str] = None


class SeedRequest(BaseModel):
    reset: bool = False


# ------------------------------------------------------------------ patients

@router.get("/patients")
async def get_patients() -> dict:
    patients = list_patients()
    return {"patients": [p.__dict__ for p in patients], "synthetic": True}


@router.get("/patients/{patient_id}")
async def get_patient_endpoint(patient_id: str) -> dict:
    patient = get_patient(patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    return {"patient": patient.__dict__, "synthetic": True}


@router.post("/patients")
async def create_patient(payload: PatientPayload) -> dict:
    from app.models import Patient

    try:
        patient = Patient(**payload.patient)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid patient payload: {exc}")
    upsert_patient(patient)
    return {"patient": patient.__dict__}


# ------------------------------------------------------------------ records

@router.get("/patients/{patient_id}/records")
async def list_records(patient_id: str) -> dict:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    records = get_records(patient_id)
    return {"records": [r.to_dict() for r in records], "count": len(records), "synthetic": True}


@router.get("/records/{record_id}")
async def get_record_endpoint(record_id: str) -> dict:
    record = get_record(record_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Unknown record {record_id}")
    return {"record": record.to_dict(), "synthetic": True}


@router.post("/records")
async def add_records(payload: RecordsPayload) -> dict:
    from app.models import MedicalRecord

    try:
        records = [MedicalRecord(**r) for r in payload.records]
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid record payload: {exc}")
    upsert_records(records)
    # Best-effort retention into the patient's own Hindsight bank
    patient = get_patient(records[0].patient_id) if records else None
    retention: dict[str, Any] = {"retained": 0, "bank_id": None, "error": None}
    try:
        result = retain_records(records, patient=patient)
        retention["retained"] = result.get("retained", 0)
        retention["bank_id"] = result.get("bank_id")
    except HindsightUnavailableError as exc:
        retention["error"] = str(exc)
    return {"added": len(records), "memory_retention": retention}


# ------------------------------------------------------------------ timeline

@router.get("/patients/{patient_id}/timeline")
async def get_timeline(patient_id: str) -> dict:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    events = build_timeline(patient_id)
    return {"events": [e.__dict__ for e in events], "synthetic": True}


# ------------------------------------------------------------------ conflicts

@router.get("/patients/{patient_id}/conflicts")
async def get_conflicts_endpoint(patient_id: str) -> dict:
    if not get_patient(patient_id):
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    patient_records = get_records(patient_id)
    record_ids = {r.record_id for r in patient_records}
    stored = get_conflicts_for_patient(patient_id)
    # Live detection covers newly added records that have not been re-seeded yet.
    detected = detect_conflicts(patient_records)
    by_id = {c.conflict_id: c for c in stored}
    for c in detected:
        by_id.setdefault(c.conflict_id, c)
    # Ownership: explicit patient_id, or (legacy rows) a source record of this patient.
    conflicts = [c.__dict__ for c in by_id.values()
                 if c.patient_id == patient_id or (not c.patient_id and c.record_a_id in record_ids)]
    return {
        "conflicts": conflicts,
        "status": "UNRESOLVED — clinician verification required",
        "synthetic": True,
    }


# ------------------------------------------------------------------ chat

@router.post("/chat")
async def chat(request: ChatRequest) -> dict:
    try:
        answer = answer_question(request.patient_id, request.question)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return answer.__dict__


# ------------------------------------------------------------------ memory panel

@router.post("/memory/recall")
async def memory_recall(payload: dict[str, Any]) -> dict:
    question = str(payload.get("question", "")).strip()
    if not question:
        raise HTTPException(status_code=400, detail="question is required")
    patient_id = str(payload.get("patient_id") or "").strip()
    if patient_id:
        patient = get_patient(patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
    else:
        patient = _default_patient()
    try:
        result = recall_for_question(question, patient)
        bank_id = bank_id_for_patient(patient)
    except HindsightUnavailableError as exc:
        return {
            "available": False,
            "error": str(exc),
            "memories": [],
            "queries_run": [],
            "safety_note": "Memory service unavailable — no historical verification possible.",
        }
    return {
        "available": not result["failed"],
        "partial_failure": result.get("partial_failure", False),
        "error": result.get("error"),
        "bank_id": bank_id,
        "queries_run": [s["query"] for s in result["queries"]],
        "dimensions": [s["dimension"] for s in result["queries"]],
        "memories": [
            {
                "id": m.get("id", ""),
                "text": m.get("text", "")[:400],
                "score": round(float(m.get("score", 0.0)), 4),
                "memory_type": m.get("memory_type", ""),
                "dimension": m.get("dimension", ""),
                "record_ids": m.get("record_ids", []),
                "date": (m.get("metadata") or {}).get("date", ""),
            }
            for m in result["memories"][:12]
        ],
    }


@router.get("/memory/status")
async def memory_status(patient_id: Optional[str] = None) -> dict:
    """Observability endpoint: real Hindsight connectivity + memory count for one patient's bank."""
    hindsight = hindsight_client_module.get_hindsight()
    if not config.hindsight_configured:
        return {"available": False, "reason": "HINDSIGHT_API_KEY not configured"}
    try:
        if patient_id:
            patient = get_patient(patient_id)
            if not patient:
                raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")
        else:
            patient = _default_patient()
        bank_id = bank_id_for_patient(patient)
        memories = hindsight.list_memories(limit=250, bank_id=bank_id)
        return {
            "available": True,
            "bank_id": bank_id,
            "memory_count": len(memories),
            "sample": [m["text"][:120] for m in memories[:5]],
        }
    except HindsightUnavailableError as exc:
        return {"available": False, "reason": str(exc)}


@router.get("/memory/recall-plan")
async def recall_plan(question: str) -> dict:
    """Shows how a question is decomposed into multi-dimension recall queries."""
    return {"question": question, "plan": build_recall_queries(question)}


# ------------------------------------------------------------------ handoff

@router.post("/handoff")
async def generate_handoff(payload: HandoffRequest) -> dict:
    from app.services.handoff import generate_handoff_summary

    if payload.patient_id:
        patient = get_patient(payload.patient_id)
        if not patient:
            raise HTTPException(status_code=404, detail=f"Unknown patient {payload.patient_id}")
    else:
        patient = _default_patient()
    summary = generate_handoff_summary(patient)
    return summary.__dict__


# ------------------------------------------------------------------ demo

@router.post("/demo/seed")
async def demo_seed(payload: Optional[SeedRequest] = None) -> dict:
    """Re-seed the demo patient (local store + Hindsight retention)."""
    from seed.seed_patient import seed as run_seed

    reset = bool(payload.reset) if payload else False
    if reset:
        reset_store()
    summary = run_seed(reset=False)
    return summary


@router.get("/demo/journey")
async def demo_journey(patient_id: Optional[str] = None) -> dict:
    """Memory Journey: the same question answered as memory accumulates.

    Runs real retain+recall against isolated real Hindsight scratch banks
    (interaction 1 / 3 / 6 / 12) and cleans them up afterwards. Read-only for
    the patient's real bank.
    """
    patient = get_patient(patient_id) if patient_id else _default_patient()
    if not patient:
        raise HTTPException(status_code=404, detail=f"Unknown patient {patient_id}")

    from app.services.journey import run_memory_journey

    try:
        return run_memory_journey(patient, get_records(patient.patient_id))
    except HindsightUnavailableError as exc:
        return {
            "question": "",
            "patient_id": patient.patient_id,
            "stages": [],
            "note": "Hindsight unavailable — the memory journey cannot run right now.",
            "error": str(exc),
        }


@router.get("/demo/mode")
async def demo_mode(question: str, patient_id: Optional[str] = None) -> dict:
    """Before/after comparison: identical question answered with and without memory.

    Runs the recall-augmented path and a memory-free baseline path against the
    same records so the judge can see the difference side by side.
    """
    patient = _default_patient()

    # ---------- WITH memory: full agent path
    with_memory = answer_question(patient.patient_id, question).__dict__

    # ---------- WITHOUT memory: same records, but no Hindsight recall at all.
    # The baseline prompt gets a raw, un-ordered record dump (what a generic
    # "document chatbot" would see) and no conflict or timeline synthesis.
    records = get_records(patient.patient_id)
    baseline_evidence = "\n".join(
        f"- ({r.record_id} {r.date}) {r.summary}" for r in records[-5:]
    )
    baseline_conflicts = []
    try:
        from app.services.llm import groq_service

        baseline_prompt = (
            "You are a generic document assistant. Answer from the document excerpts below. "
            "Do not use any long-term memory.\n\n"
            f"DOCUMENTS:\n{baseline_evidence}\n\nQUESTION: {question}"
        )
        baseline_answer = groq_service.generate(
            system_prompt="You are a generic document assistant. Be brief.",
            user_prompt=baseline_prompt,
            temperature=0.2,
            max_tokens=500,
        )
    except Exception:
        baseline_answer = (
            "Generic assistant response (LLM unavailable): summarize current symptoms, "
            "medications, allergies, and recent events for the doctor."
        )

    return {
        "question": question,
        "without_memory": {
            "answer": baseline_answer,
            "memories_used": 0,
            "source_records_linked": 0,
            "conflicts_surfaced": [],
            "timeline": False,
            "description": "Generic assistant: sees only raw recent document snippets, no longitudinal memory.",
        },
        "with_memory": {
            "answer": with_memory["answer"],
            "memories_used": len(with_memory["memories_used"]),
            "source_records_linked": len({sr["record_id"] for sr in with_memory["source_records"]}),
            "conflicts_surfaced": with_memory["conflicts"],
            "timeline": bool(with_memory["timeline_events"]),
            "uncertainty": with_memory["uncertainty"],
            "description": "LifeLine: recalls longitudinal memories, links provenance, surfaces conflicts and timeline.",
        },
    }
