# LifeLine Architecture

## Components

```
┌─────────────────────────────┐
│ Frontend (React/Vite)       │  Home · Patient workspace · Chat · Evidence
│ :5173                       │  panels · Timeline · Conflicts · Handoff · Demo
└──────────────┬──────────────┘
               │ REST (JSON)
┌──────────────▼──────────────┐
│ FastAPI backend :8000       │
│ ┌────────────────────────┐  │
│ │ agent.py (orchestrator)│  │
│ └───┬───────────┬────────┘  │
│     │           │           │
│ ┌───▼────┐  ┌───▼────────┐  │
│ │Hindsight│ │Groq LLM    │  │
│ │memory   │ │gpt-oss-120b│  │
│ └────────┘  └────────────┘  │
│ records_store (JSON file)   │
│ conflicts · timeline        │
└─────────────────────────────┘
```

## Request flow (POST /api/chat)

1. **Intent & recall plan** — `memory_service.build_recall_queries` expands the question
   into up to 4 dimension queries (direct, medication, changes, similar events, conflicts…).
2. **Hindsight recall** — each dimension runs a real `recall()` call; results are merged,
   deduplicated, ranked by score.
3. **Provenance linking** — `provenance.link_memory_to_records` maps memory metadata
   (`record_id`) back to full stored records.
4. **Conflict detection** — rule-based scan over the record set (allergy-vs-medication,
   discontinued-vs-active, same-date value discrepancies). Conflicts whose records appear
   in the recalled memories are attached to the answer.
5. **LLM synthesis** — Groq `openai/gpt-oss-120b` receives chart context + recalled
   evidence + conflicts under a strict safety system prompt. Record IDs are cited inline.
6. **Interaction retention** — the Q/A is retained into Hindsight (best-effort) so future
   answers can build on the conversation.
7. **Structured response** — answer, memories_used, source_records, timeline_events,
   conflicts, uncertainty, safety_note.

## Failure modes (explicit, never silent)

| Failure | Behavior |
|---|---|
| Hindsight unreachable / unconfigured | Recall skipped; answer states "Memory service unavailable…" and falls back to loaded-record summary; `uncertainty` carries the note |
| Recall returns empty | LLM is told evidence is empty and instructed to say so plainly |
| Groq unreachable / rate-limited | Evidence-only answer assembled from recalled memories, with the failure noted |
| Malformed LLM JSON (JSON mode paths) | One repair retry, then `LLMError` → evidence fallback |
| Unknown patient | HTTP 404 |

## Observability

Log lines (keys are never logged):

```
[HINDSIGHT] retaining record REC-1042 ...
[HINDSIGHT] recall query: recent medication changes
[HINDSIGHT] 4 memories returned
[LLM] generating response (model=openai/gpt-oss-120b, json=False)
[PROVENANCE] linked 3 source record(s)
[CONFLICTS] 2 potential conflict(s) detected
```

`GET /api/memory/status` exposes live bank connectivity + memory count (the UI chip).
`GET /api/memory/recall-plan?question=...` shows how a question is decomposed.
