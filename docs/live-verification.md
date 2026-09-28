# Live Hindsight Verification (real cloud, no mocks)

Date: 2026-09-27 · Service: Hindsight Cloud (`https://api.hindsight.vectorize.io`, server `api_version=0.10.1`) · Bank: `lifeline-demo-patient-p-001` (+ `…-p-9002` for isolation test)

Every result below was produced against the **real Hindsight Cloud** with the configured `HINDSIGHT_API_KEY` — not the test mock. The mock-based unit suite (65 tests) is a separate, earlier gate.

## Result table

| Check | Result |
|---|---|
| REAL Hindsight retain | **PASS** — 116 memory items from 18 records retained; server-side `list_memories` returned them back (177→243 after interactions); seed's verification recall immediately returned 116 memories |
| REAL Hindsight recall | **PASS** — 5 novel questions (never in UI chips/tests/seed) each ran a real recall (`[HINDSIGHT] recall query: …` in logs) and returned 8 scored memories with linked record IDs (top scores 0.71 / 0.0048 / 0.025 / 0.25 / 0.18) |
| REAL Hindsight reflect | **PASS** — handoff contains `LONGITUDINAL SYNTHESIS (from memory)` (2.7–5.0k chars) synthesized from the bank; direct `reflect()` call succeeded against the cloud |
| Cross-interaction memory | **PASS** — interaction retained ("patient prefers morning appointments") was recalled later with a *new* topical query via a fresh API call |
| Query sensitivity | **PASS** — meds-query and ED-query returned disjoint memory sets (12 unique each, overlap 0) with topically matching content |
| Patient isolation | **PASS** — two patients on two real banks: Arjun's recall of "motorcycle" returned zero Rohan memories; Rohan's recall of Arjun's symptoms returned zero Arjun memories; each patient's own memories recallable |
| Honest degradation | **PASS** — with Hindsight pointed at a dead URL (`http://127.0.0.1:9`), the answer discloses "Memory service unavailable…" in `uncertainty`, `memories_used == []`, and no memories are fabricated |
| Visible real activity (demo logs) | **PASS** — timestamped `[HINDSIGHT] retain/recall/reflect` lines captured from the live server (see below) |

The repeatable smoke test: **10/10 checks passed** on the final code state (`backend/scripts/live_smoke.py`).

## Exact commands used

```bash
# 0) one-time setup
cp .env.example .env          # fill in HINDSIGHT_API_KEY (+ GROQ_API_KEY)

# 1) mock-layer regression gate (not the integration proof)
cd backend && venv/Scripts/python.exe -m pytest tests/ -q          # 65 passed

# 2) REAL-cloud smoke (retain, recall, reflect, sensitivity, isolation, degradation)
venv/Scripts/python.exe scripts/live_smoke.py                      # 10/10 checks passed

# 3) live server + UI-rendered endpoints against real Hindsight
venv/Scripts/python.exe -m uvicorn app.main:app --port 8001        # 8000 was held by a stale pre-fix server
curl http://127.0.0.1:8001/health                                  # hindsight_configured=true, groq_configured=true
curl -X POST http://127.0.0.1:8001/api/demo/seed \
     -H "Content-Type: application/json" -d '{"reset": false}'
#    -> {"records": 18, "conflicts": 6, "memory": {"retained": 116, "verification_recall": 116, ...}}
curl http://127.0.0.1:8001/api/memory/status                       # available=true, 243 memories
curl -X POST http://127.0.0.1:8001/api/chat \
     -H "Content-Type: application/json" \
     -d '{"patient_id":"P-001","question":"What matters in this history before a cardiology follow-up?"}'
#    -> 8 memories_used (top score 0.22), source_records [REC-1003, REC-1006, REC-1013],
#       timeline 10, conflicts 5 — the exact payload EvidencePanel renders
curl -X POST http://127.0.0.1:8001/api/handoff \
     -H "Content-Type: application/json" -d '{"patient_id":"P-001"}'   # synthesis section present
curl "http://127.0.0.1:8001/api/demo/mode?question=What%20changed%20since%20the%20last%20hospital%20visit%3F"
#    -> without_memory: 0 memories | with_memory: 8 memories, 2 records linked, 3 conflicts

# 4) demo-visible proof of real activity
grep HINDSIGHT /tmp/lifeline_ui.log
```

Sample of the demo-visible log evidence (from the live server):

```
2026-09-27 16:54:28 INFO lifeline.hindsight: [HINDSIGHT] recall query: What changed since the last hospital visit?
2026-09-27 16:54:35 INFO lifeline.hindsight: [HINDSIGHT] 115 memories returned
2026-09-27 16:54:35 INFO lifeline.hindsight: [HINDSIGHT] recall query: what changed recently medication started stopped new symptoms
2026-09-27 16:54:42 INFO lifeline.hindsight: [HINDSIGHT] 110 memories returned
2026-09-27 16:54:48 INFO lifeline.hindsight: [HINDSIGHT] retained 1 item(s) into lifeline-demo-patient-p-001
2026-09-27 16:54:48 INFO lifeline.agent.history: [HINDSIGHT] retained interaction memory for P-001
```

## Fixes the live check forced (would have broken the real demo)

1. **`.env` was never loaded** — `python-dotenv` was in `requirements.txt` but no code called `load_dotenv`. `app/config.py` now loads `backend/.env` (real env vars still win).
2. **Sync SDK calls crashed under uvicorn** — `hindsight-client`'s sync methods drive their own event loop and raise *"This event loop is already running"* inside FastAPI. All SDK calls now route through `_call_sync` (worker thread when a loop is running). This alone would have made the UI show "memory offline".
3. **Cloud rejects boolean metadata** — `MemoryItem.metadata` requires strings; `retain()` now coerces (`_stringify_metadata`).
4. **SDK 0.10 response shapes** — relevance scores live in `scores.final` (parsed; was always 0.0) and reflect sources are nested under `based_on.memories` (flattened).
5. **Retain→recall indexing lag** — freshly retained items were not immediately recallable; `retain()` now polls the returned `operation_id`s via `operations.get_operation_status` (best-effort, ≤20s).
6. **`store.json` corruption** — `upsert_conflicts` stored an extra `patient_id` key that `Conflict(**raw)` rejects (500 on seed via live server). Fixed + stale entries cleaned; `clear_patient_data` now scopes conflicts by source records.

## Remaining issues (non-blocking)

- **Restart the stale `:8000` server** — it still runs pre-fix code and re-poisons `store.json` if `/api/demo/seed` is hit on it. Kill it and start uvicorn fresh before the demo.
- **Fact extraction rewrites content** — Hindsight extracts/normalizes memories, so arbitrary tokens in retained text may be dropped. Recall by meaning, not by magic strings (the smoke test does this).
- **`reflect` source attribution** — the synthesis text is clearly bank-derived, but the cloud sometimes returns an empty `based_on.memories` list, so the UI can't always show per-source attribution for reflect. Observability gap in the SDK payload, not a functional one.
- **Smoke-test residue in the demo bank** — `lifeline-demo-patient-p-001` now contains smoke interactions ("morning appointments", test Q&A) and a second bank `…-p-9002` exists. Genuine memory, but for a pristine demo delete banks and re-seed:
  `venv/Scripts/python.exe -c "from app.services.hindsight.client import HindsightClientWrapper as W; c=W()._raw_client(); [c.delete_bank(bank_id=b) for b in ['lifeline-demo-patient-p-001','lifeline-demo-patient-p-9002']]"` then `POST /api/demo/seed`.
- **Windows consoles** default to cp1252; run servers/Smoke tests with `PYTHONIOENCODING=utf-8` to print LLM/memory text cleanly.
