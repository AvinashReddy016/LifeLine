# Memory Design

LifeLine's memory layer is the product. This document describes how medical history
becomes memory and how memory becomes answers.

## Banks

One Hindsight bank per patient (`HINDSIGHT_BANK_ID`, default `lifeline-demo` for the demo
patient). The bank `background` tells Hindsight what kind of memories live here:
longitudinal medical events with provenance metadata, for a health-information assistant.

## Retain strategy

### From records to memories

A raw record is not a memory. Each record is decomposed into **single-fact items** —
one clinically meaningful statement per memory — so temporal and entity recall can bind
precisely:

```python
# from app/services/hindsight/memory_service.py
{
  "content": "[Record REC-1013, dated 2025-11-02] ED vitals: BP 104/64 supine, 88/58 standing.",
  "context": "emergency — Emergency visit — dizziness at Mercy General Hospital",
  "timestamp": "2025-11-02T09:00:00Z",
  "metadata": {
    "record_id": "REC-1013",
    "event_type": "emergency",
    "date": "2025-11-02",
    "source_type": "emergency",
    "synthetic": True,
  },
}
```

Rules of thumb:
- **Preserve the original date** in both `timestamp` and content — temporal recall depends on it.
- **Record ID in the content** (not just metadata) so even a bare memory text is traceable.
- Fact lines shorter than 40 chars ending in `:` are treated as headers and skipped.
- Provenance metadata (`record_id`, `event_type`, `date`, `synthetic`) rides on every item.

### Interaction retention

Every chat Q/A is retained as a lightweight `interaction` memory (best-effort), so the
system's own explanations become recallable context later.

## Recall strategy

### Multi-dimension recall plan

A single semantic query is not enough. `build_recall_queries` expands the question:

| User language | Added dimension | Recall query |
|---|---|---|
| "medications / drugs / prescriptions" | `medication_history` | medications started discontinued switched doses |
| "changed / since / recent" | `recent_changes` | what changed recently medication started stopped new symptoms |
| "similar / before / again" | `similar_events` | similar symptoms documented in earlier records |
| "conflict / contradict / inconsistent" | `conflicts` | contradicting entries allergy medication discrepancy |
| "emergency / ER / hospital" | `emergencies` | emergency visits urgent hospital encounters |
| "tell the doctor / handoff / summarize" | `handoff` | most clinically relevant history … |

The plan is capped at 4 queries to keep latency demo-friendly. Each dimension runs a real
`client.recall(...)`. Results are merged, deduplicated by text, and ranked by Hindsight's
score.

### Provenance linking

`provenance.link_memory_to_records` maps each recalled memory back to full source records
via `record_id` metadata (falling back to `REC-####` patterns in text). The evidence panel
and every "why this record?" answer are built from this linkage.

## Reflection

Hindsight `reflect` is used for longitudinal synthesis questions — patterns across the
history, unresolved threads — never for medical conclusions. Reflection output is treated
as *evidence to present*, not as judgment.

## Conflicts × memory

Rule-based conflict detection (`conflicts.py`) runs over the record set:

1. **allergy_vs_medication** — an allergy claim in one record vs. the same drug appearing
   in a medication context in a later record (action verbs or explicit "lists/labeled"
   presence claims, gated by a curated drug lexicon to avoid false matches).
2. **discontinued_vs_active** — a drug discontinued in one record, active again in a later one.
3. **value_discrepancy** — same test, same date, different values.

Conflicts are always attached as **UNRESOLVED** with the required action: clinician
verification. When a question recalls memories touching a conflict's records, the conflict
is included in the structured answer automatically.
