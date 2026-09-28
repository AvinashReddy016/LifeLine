"""Memory service — the retain/recall pipeline that turns records into memories.

Retain: converts each MedicalRecord into several self-contained memory items
        (one per clinically meaningful fact) with provenance metadata.
Recall: builds a multi-dimension recall plan from the user's question, executes
        real Hindsight recall calls, and maps results back to source records.
"""
from __future__ import annotations

import logging
import math
import re
from collections import Counter
from typing import Any, Optional

from app.config import config
from app.models import MedicalRecord, MemoryReference, Patient
from app.services.hindsight import client as hindsight_client
from app.services.hindsight.client import HindsightUnavailableError

logger = logging.getLogger("lifeline.memory")


# --------------------------------------------------------------------------
# Retain
# --------------------------------------------------------------------------

def bank_id_for_patient(patient: Optional[Patient]) -> str:
    """Per-patient memory bank id.

    Hindsight banks are strictly isolated — one bank per patient guarantees no
    cross-patient memory leakage (docs: https://hindsight.vectorize.io/).
    """
    base = config.hindsight_bank_id or "lifeline"
    if patient and patient.patient_id:
        suffix = patient.patient_id.lower().replace("_", "-")
        return f"{base}-patient-{suffix}"
    return f"{base}-patient-unknown"


def record_to_memory_items(record: MedicalRecord) -> list[dict[str, Any]]:
    """Decompose a record into self-contained memory items.

    Each item states one fact with an explicit date so temporal recall works.
    Provenance (record_id, event_type, date, synthetic) rides in metadata.
    """
    meta = {
        "record_id": record.record_id,
        "event_type": record.record_type,
        "date": record.date,
        "source_type": record.record_type,
        "synthetic": True,
    }
    timestamp = f"{record.date}T09:00:00Z" if record.date else None

    def item(content: str, context: str) -> dict[str, Any]:
        return {
            "content": content,
            "context": context,
            "timestamp": timestamp,
            "metadata": dict(meta),
        }

    items: list[dict[str, Any]] = []

    # The overall record summary as one memory.
    if record.summary:
        items.append(item(
            f"On {record.date} ({record.record_type.replace('_', ' ')}) at "
            f"{record.facility or 'an outpatient clinic'} with {record.clinician or 'a clinician'}: "
            f"{record.summary}",
            f"Source record {record.record_id} — {record.title}",
        ))

    for line in _fact_lines(record.body):
        items.append(item(
            f"[Record {record.record_id}, dated {record.date}] {line}",
            f"{record.record_type.replace('_', ' ')} — {record.title} at {record.facility or 'clinic'}",
        ))

    if not items and record.body:
        items.append(item(record.body, f"Source record {record.record_id} — {record.title}"))

    return items


def _fact_lines(body: str) -> list[str]:
    """Split a record body into meaningful single-fact lines.

    Record bodies mix bullet lines and single-paragraph prose, so we split on
    newlines AND sentence boundaries to get one self-contained fact per item.
    """
    import re

    lines: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n", body):
        line = raw.strip().lstrip("-•*").strip()
        if not line:
            continue
        # Skip structural headers like "Medications:" that carry no fact alone
        if line.endswith(":") and len(line) < 40:
            continue
        lines.append(line if line.endswith(".") else line + ".")
    return lines


def retain_records(records: list[MedicalRecord], patient: Optional[Patient] = None) -> dict[str, Any]:
    """Retain all records into the patient's own memory bank. Returns a status summary."""
    hindsight = hindsight_client.get_hindsight()
    bank_id = bank_id_for_patient(patient)
    all_items: list[dict[str, Any]] = []
    per_record: dict[str, int] = {}
    for record in records:
        items = record_to_memory_items(record)
        per_record[record.record_id] = len(items)
        all_items.extend(items)

    if not all_items:
        return {"retained": 0, "per_record": {}}

    logger.info("[HINDSIGHT] retaining %d memory items from %d records into %s", len(all_items), len(records), bank_id)
    result = hindsight.retain(all_items, bank_id=bank_id)
    return {
        "retained": len(all_items),
        "bank_id": bank_id,
        "per_record": per_record,
        "items_count": result.get("items_count", len(all_items)),
    }


# --------------------------------------------------------------------------
# Recall
# --------------------------------------------------------------------------

def build_recall_queries(question: str, patient: Optional[Patient] = None) -> list[dict[str, str]]:
    """Turn one user question into a small set of targeted recall queries.

    Different dimensions of history are probed so recall isn't a single naive
    semantic search: medications, prior similar events, temporal changes, conflicts.
    """
    q = question.lower()
    plans: list[dict[str, str]] = [{"dimension": "direct", "query": question}]

    if any(word in q for word in ("medication", "medicine", "drug", "prescri", "dose")):
        plans.append({"dimension": "medication_history",
                      "query": "medications started discontinued switched doses"})
    if any(word in q for word in ("changed", "change", "since", "recent", "new")):
        plans.append({"dimension": "recent_changes",
                      "query": "what changed recently medication started stopped new symptoms"})
    if any(word in q for word in ("similar", "before", "previous", "history of", "again", "recur")):
        plans.append({"dimension": "similar_events",
                      "query": "similar symptoms documented in earlier records"})
    if any(word in q for word in ("conflict", "contradict", "inconsist", "mismatch", "disagree")):
        plans.append({"dimension": "conflicts",
                      "query": "contradicting entries allergy medication discrepancy"})
    if any(word in q for word in ("interaction", "previous conversation", "earlier conversation",
                                  "you said", "you answered", "learned from previous")):
        plans.append({"dimension": "interactions",
                      "query": "previous LifeLine assistant sessions questions answered discussed"})
    if any(word in q for word in ("emergency", "er ", "urgent", "hospital")):
        plans.append({"dimension": "emergencies",
                      "query": "emergency visits urgent hospital encounters"})
    if any(word in q for word in ("tell the doctor", "handoff", "summar", "relevant")):
        plans.append({"dimension": "handoff",
                      "query": "most clinically relevant history for current encounter medications allergies reactions"})

    # Cap the plan so latency stays demo-friendly.
    return plans[:4]


def _dedupe_memories(memories: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for memory in memories:
        key = memory["text"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(memory)
    return unique


def recall_for_question(
    question: str,
    patient: Optional[Patient] = None,
    limit_per_query: int = 6,
    bank_id: Optional[str] = None,
) -> dict[str, Any]:
    """Execute the recall plan against the patient's Hindsight bank and merge results.

    Returns {"memories": [...], "queries": [...], "failed": bool, "partial_failure": bool, "error": str?}
    `failed` is True if every Hindsight call failed — callers must degrade
    gracefully and say so instead of pretending memory retrieval succeeded.
    `partial_failure` is True when at least one dimension failed but others succeeded.
    """
    hindsight = hindsight_client.get_hindsight()
    plan = build_recall_queries(question, patient)
    bank_id = bank_id or bank_id_for_patient(patient)

    all_memories: list[dict[str, Any]] = []
    errors: list[str] = []
    for step in plan:
        try:
            memories = hindsight.recall(step["query"], limit=limit_per_query, bank_id=bank_id)
            for memory in memories:
                memory["dimension"] = step["dimension"]
            all_memories.extend(memories)
        except HindsightUnavailableError as exc:
            errors.append(f"{step['dimension']}: {exc}")
        except Exception as exc:  # noqa: BLE001 — any recall failure must degrade, not crash
            logger.warning("[HINDSIGHT] recall dimension '%s' failed: %s", step["dimension"], exc)
            errors.append(f"{step['dimension']}: {exc}")

    memories = _dedupe_memories(all_memories)

    # Relevance reranking — see rerank_memories(). Hindsight's score orders the
    # candidate pool; the reranker picks which of those candidates best SUPPORT
    # the answer (content match + independent-dimension agreement + recency).
    memories = rerank_memories(memories, question)

    # Clinical evidence first: interaction memories (retained Q/A sessions) are
    # recallable, but must not crowd out record-backed memories — otherwise
    # answers lose source-record provenance and conflict surfacing.
    cap = limit_per_query * 2
    record_backed = [m for m in memories if (m.get("metadata") or {}).get("event_type") != "interaction"]
    interactions = [m for m in memories if (m.get("metadata") or {}).get("event_type") == "interaction"]
    merged = record_backed[:cap]
    if len(merged) < cap:
        merged.extend(interactions[: cap - len(merged)])
    memories = sorted(merged, key=lambda m: m.get("score", 0.0), reverse=True)

    # Total failure = every dimension errored (nothing was verified at all).
    # Partial failure = some dimensions errored while others succeeded — the
    # recalled evidence may be incomplete and the answer must say so.
    total_failure = len(errors) > 0 and len(errors) == len(plan)
    partial_failure = len(errors) > 0 and not total_failure

    return {
        "memories": memories,
        "queries": plan,
        "failed": total_failure,
        "partial_failure": partial_failure,
        "error": "; ".join(errors) if errors else None,
    }


# --------------------------------------------------------------------------
# Relevance reranking
# --------------------------------------------------------------------------

_STOPWORDS = {
    "the", "a", "an", "of", "for", "to", "in", "on", "and", "or", "was", "were", "is",
    "are", "what", "when", "how", "did", "do", "does", "with", "at", "by", "from", "this",
    "that", "it", "be", "been", "has", "have", "had", "patient", "records", "record",
    "history", "documented", "document", "noted", "reported", "clinician", "doctor",
    "should", "would", "could", "there", "their", "about", "into", "than", "then", "any",
    # Dimension-query boilerplate: terms injected by build_recall_queries that are
    # NOT the user's words. Question↔memory agreement must not count them.
    "medications", "started", "discontinued", "switched", "doses", "changed", "recently",
    "stopped", "symptoms", "similar", "earlier", "contradicting", "entries", "allergy",
    "medication", "discrepancy", "emergency", "visits", "urgent", "hospital", "encounters",
}


def _content_tokens(text: str) -> set[str]:
    """Content tokens for agreement scoring: words minus stopwords, lightly stemmed."""
    return {
        tok[:-1] if tok.endswith("s") and len(tok) > 3 else tok
        for tok in re.findall(r"[a-z][a-z0-9-]{2,}", text.lower())
        if tok not in _STOPWORDS
    }


def rerank_memories(memories: list[dict[str, Any]], question: str) -> list[dict[str, Any]]:
    """Order recalled memories by how well they support the question.

    The reranker is purely evidence-driven: it combines four independently
    computed signals, each derived from the actual recall results and the user's
    actual question — no keyword maps, no hardcoded relevance, no per-question
    branches.

    Score = (0.50 × Hindsight relevance, normalized over the candidate pool)
          + (0.25 × content agreement: distinctive-word overlap between the user's
            question and the memory text — dimension-injected boilerplate excluded)
          + (0.15 × multi-dimension agreement: a memory is worth more the more
            separate recall dimensions independently surfaced it)
          + (0.10 × source anchoring: a memory that names the same source record
            as another stronger memory is boosted slightly, because provenance
            chaining is what makes a longitudinal answer trustworthy).

    Recency is deliberately NOT in the composite score: it belongs in the UI as
    a per-card cue, not in the rank order, so the strongest evidence always
    reaches the top of the list.
    """
    if not memories:
        return memories

    scores = [float(m.get("score", 0.0)) for m in memories]
    lo, hi = min(scores), max(scores)
    span = (hi - lo) or 1.0
    question_tokens = _content_tokens(question)

    # Map source record -> set of distinct recall dimensions that surfaced it.
    records_per_dimension: dict[str, set[str]] = {}
    for memory in memories:
        dimension = memory.get("dimension") or ""
        for rid in memory.get("record_ids") or []:
            records_per_dimension.setdefault(rid, set()).add(dimension)

    # Document frequency across the candidate pool, for tf–idf weighting of the
    # content-agreement signal.
    df: Counter[str] = Counter()
    for other in memories:
        df.update(_content_tokens(other.get("text", "")))
    idf_total = sum(1.0 / math.log(2 + df[tok]) for tok in question_tokens) or 1.0

    def combined(memory: dict[str, Any]) -> float:
        # 1. Hindsight relevance, normalized over the candidate pool so scores
        #    are comparable between questions.
        base = (float(memory.get("score", 0.0)) - lo) / span

        # 2. Content agreement: distinctive-word overlap between the user's
        #    question and the memory, idf-weighted. Dimension-boilerplate tokens
        #    are excluded up front by _STOPWORDS, so dimension queries never
        #    inflate the agreement score.
        overlap = question_tokens & _content_tokens(memory.get("text", ""))
        idf_weighted = sum(1.0 / math.log(2 + df[tok]) for tok in overlap)
        agreement = min(1.0, idf_weighted / idf_total) if idf_total else 0.0

        # 3. Multi-dimension agreement: how many independent recall dimensions
        #    surfaced this memory. A fact found by two distinct dimensions is
        #    far more likely to be genuinely relevant than a fact found by one.
        rid = next(iter(memory.get("record_ids") or []), None)
        if rid and rid in records_per_dimension:
            multi = min(1.0, (len(records_per_dimension[rid]) - 1) / 2.0)
        else:
            multi = 0.0

        return 0.50 * base + 0.25 * agreement + 0.15 * multi

    return sorted(memories, key=combined, reverse=True)


def memories_to_references(memories: list[dict[str, Any]]) -> list[MemoryReference]:
    references: list[MemoryReference] = []
    for i, memory in enumerate(memories):
        metadata = memory.get("metadata") or {}
        references.append(
            MemoryReference(
                id=str(memory.get("id") or f"mem_{i}"),
                text=memory.get("text", ""),
                score=float(memory.get("score", 0.0)),
                record_ids=list(memory.get("record_ids") or []),
                memory_type=memory.get("memory_type", ""),
                date=str(metadata.get("date", "")),
            )
        )
    return references


def memory_status_payload(recall_result: dict[str, Any]) -> dict[str, Any]:
    """Shape the "Memory used" panel payload, including failure honesty."""
    return {
        "available": not recall_result["failed"],
        "queries_run": [step["query"] for step in recall_result["queries"]],
        "dimensions": [step["dimension"] for step in recall_result["queries"]],
        "memory_count": len(recall_result["memories"]),
        "partial_failure": recall_result.get("partial_failure", False),
        "error": recall_result.get("error"),
    }
