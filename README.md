# LifeLine

**Your medical history has a memory.**

LifeLine is a long-term memory layer that reconstructs a patient's evolving medical story
from fragmented records — visits, labs, prescriptions, discharge summaries, emergency
notes — and surfaces what changed, what connects, and what conflicts, with every answer
traceable to its source records.

> ⚠️ **SYNTHETIC DEMO DATA — NOT REAL PATIENT DATA.** LifeLine is a health-information
> assistant. It does not diagnose, prescribe, or treat, and it is not a clinical device.

---

## Problem

Medical information is fragmented across prescriptions, discharge summaries, lab reports,
doctor notes, and patient-entered data. The hard problem is not *finding a document* — it
is reconstructing the **longitudinal story**: what happened, when, what changed, what
happened after the change, and which entries contradict each other.

### Why existing approaches fall short

| Approach | What it does | What it misses |
|---|---|---|
| Document RAG | Retrieves chunks similar to the query | No notion of *change over time*, no provenance chains, treats a 2024 prescription and a 2026 ED note as interchangeable text |
| Chat history | Keeps the recent conversation | Knows nothing about records from before the session |
| Generic summarizer | Condenses one document | Cannot connect an allergy note from March to a pharmacy label from March next year |

**Document retrieval ≠ longitudinal memory.** LifeLine is built around that difference.

## Solution

LifeLine stores each medically meaningful fact as a **dated, provenance-linked memory** in
[Hindsight](https://github.com/vectorize-io/hindsight), then answers questions by recalling
across the whole history — medication changes, prior similar events, temporal patterns, and
contradictions — and synthesizing an evidence-grounded response with the exact source
records attached.

- 🧠 **Memory-native**: every answer lists the memories used and the records behind them
- 📈 **Improves with use**: interaction 1 is generic; interaction 20 is a longitudinal brief
- ⚠️ **Contradiction-aware**: conflicting entries are surfaced as UNRESOLVED, never silently resolved
- 🩺 **Clinician-safe**: no diagnosis, no treatment advice, explicit verification requirements

## Architecture

```
backend/  FastAPI (Python)          frontend/  React + Vite (TypeScript)
├── app/api/routes.py               ├── src/pages/         Home, Patient workspace
├── app/services/                   ├── src/components/    Timeline, EvidencePanel, Chat, Modals
│   ├── hindsight/                  └── src/services/api.ts
│   │   ├── client.py               ← Hindsight SDK wrapper (retain/recall/reflect)
│   │   └── memory_service.py       ← record→memory decomposition, multi-dimension recall
│   ├── agent.py                    ← orchestrator: recall → provenance → conflicts → LLM
│   ├── conflicts.py                ← rule-based contradiction detection
│   ├── timeline.py                 ← chronological reconstruction
│   ├── handoff.py                  ← clinician-facing brief
│   └── llm/groq_service.py         ← Groq (openai/gpt-oss-120b)
├── seed/seed_patient.py            ← idempotent demo seeding
└── tests/                          ← 74 pytest tests
```

## Why Hindsight

[Hindsight](https://hindsight.vectorize.io/) is an agent memory system that learns — it
retains facts with entities, relationships and time, and recalls with four parallel
strategies (semantic, keyword, graph, temporal). That combination is exactly what
longitudinal medical history needs:

- **Temporal recall** — "what happened after March 2025" is a first-class query, not a hack
- **Entity graphs** — a medication name links its prescription, its discontinuation, and the symptom note in between
- **Observations** — repeated evidence consolidates into beliefs (e.g., a symptom seen after multiple medication changes)
- **Reflect** — synthesis across the whole history without dumping every record into the prompt

Hindsight is used through the official
[`hindsight-client`](https://docs.dev.hindsight.vectorize.io/python-sdk/) Python SDK — real
`retain`, `recall` and `reflect` calls, no simulation. Cloud and self-hosted both work (see
[Memory Design](docs/memory-design.md)).

## Memory design (short version)

Every record is decomposed into single-fact memories, each carrying provenance metadata:

```python
{
  "content": "[Record REC-1006, dated 2025-03-18] Discontinued Amlodipine 5 mg daily.",
  "context": "medication_change — Medication change at Lakeview Family Medicine",
  "timestamp": "2025-03-18T09:00:00Z",
  "metadata": {"record_id": "REC-1006", "event_type": "medication_change",
               "date": "2025-03-18", "synthetic": True}
}
```

Questions are expanded into a **multi-dimension recall plan** (direct, medication history,
recent changes, similar events, conflicts), executed against Hindsight, merged and ranked.
Recalled memories are linked back to source records for the evidence panel. Full details:
[docs/memory-design.md](docs/memory-design.md).

## Demo

The demo patient is **Arjun Mehra** (synthetic), with 18 records spanning Feb 2024 – Mar
2026. The story: dyspepsia → hypertension therapy → amlodipine switch → documented
penicillin allergy → H. pylori regimen chosen around the allergy → discharge summary that
*lists penicillin among home medications* → two ED visits for dizziness after antihypertensive
changes → a new pharmacy label for amoxicillin.

Planted, detectable conflicts include: **penicillin allergy vs. penicillin-family
prescriptions** and **amlodipine discontinued vs. re-started**.

## Run on Windows (PowerShell)

All commands below were verified against this repository on Windows (PowerShell).

### Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Python | 3.10+ (developed on 3.10) | `python --version` |
| Node.js + npm | Node 20+ | `node --version` && `npm --version` |
| Hindsight Cloud account | free tier works | [ui.hindsight.vectorize.io](https://ui.hindsight.vectorize.io) → API key |
| Groq API key | free tier works | [console.groq.com](https://console.groq.com) → API key |

### 1) Environment setup (backend)

```powershell
cd D:\Hackathon\backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create **`backend/.env`** (copy from the template and fill in your keys — never commit this file):

```powershell
copy .env.example .env
notepad .env
```

It must contain at least:

```ini
HINDSIGHT_API_KEY=<your key from ui.hindsight.vectorize.io>
HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
HINDSIGHT_BANK_ID=lifeline-demo
GROQ_API_KEY=<your key from console.groq.com>
GROQ_MODEL=openai/gpt-oss-120b
```

`GROQ_API_KEY` is optional — without it LifeLine still answers from recalled memory using the
honest evidence-only fallback (no synthesis). `HINDSIGHT_API_KEY` is required for long-term
memory; without it the app runs but discloses "memory unavailable" instead of pretending.

### 2) Seed the synthetic data

```powershell
# from D:\Hackathon\backend with the venv activated
python seed\seed_patient.py
```

This loads the 18 synthetic records into the local store, detects conflicts, and retains
116 memory items into the patient's Hindsight Cloud bank (with a verification recall at the
tend). Re-running is safe/idempotent.

Use `python seed\seed_patient.py --reset` only when you want to **wipe the local record
store first** (e.g. after editing `seed/patients.json`). `--reset` clears the local JSON
store; memories already in the Hindsight bank are additive and idempotent, so they do not
need wiping. First-time setup: plain (no `--reset`) is correct.

### 3) Start the backend

```powershell
# from D:\Hackathon\backend with the venv activated
python -m uvicorn app.main:app --reload --port 8000
```

(Entry point verified: `backend/app/main.py` exposes the FastAPI `app`.)

### 4) Start the frontend (second terminal)

```powershell
cd D:\Hackathon\frontend
npm install
npm run dev
```

(Scripts verified in `frontend/package.json`: `dev` runs Vite; `build` runs `tsc -b && vite build`.)

### URLs

| URL | What |
|---|---|
| http://localhost:5173 | Frontend (Vite dev server) |
| http://localhost:8000/health | Backend health (`hindsight_configured`, `groq_configured`) |
| http://localhost:8000/docs | Interactive API docs (FastAPI/Swagger) |

If your frontend runs on a different origin, add it to `CORS_ORIGINS` in `backend/.env`.
The frontend targets `http://localhost:8000` by default; override with `VITE_API_URL`
(e.g. `VITE_API_URL=http://localhost:9000 npm run dev`).

### Full startup procedure (copy/paste)

```powershell
# TERMINAL 1 — backend
cd D:\Hackathon\backend
.\venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload --port 8000

# TERMINAL 2 — frontend
cd D:\Hackathon\frontend
npm run dev
```

Then open http://localhost:5173. Run the **seed command** once before the first backend
start (and after any change to `seed/patients.json`, ideally with `--reset`). If the backend
was started before `.env` existed, restart it so it picks up the keys.

Or use the helper scripts (they check prerequisites, then start; errors stay visible):

```powershell
D:\Hackathon\run-backend.ps1     # terminal 1
D:\Hackathon\run-frontend.ps1    # terminal 2
```

### Troubleshooting

| Symptom | Fix |
|---|---|
| `python: command not found` / not recognized | Install Python 3.10+ from python.org and tick *Add to PATH*, or use the `py` launcher (`py -m venv venv`). Open a new terminal after install. |
| `npm: command not found` | Install Node.js LTS (nodejs.org). Open a new terminal after install. |
| `...cannot be loaded because running scripts is disabled` (PowerShell execution policy) | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then retry activation. |
| Port 8000 already in use | Kill the stale listener: `netstat -ano | findstr :8000` → `taskkill /PID <pid> /F`. Or start on another port (`--port 8001`) — but the frontend expects 8000 unless you set `VITE_API_URL`. |
| Port 5173 already in use | Another Vite instance is running. Close it, or `npm run dev -- --port 5174`. |
| Missing `.env` | `copy .env.example .env` in `backend/` and fill in keys, then **restart** the backend (config is read at startup). |
| Missing Hindsight API key | Backend starts, but memory is disabled and answers disclose it. Get a key at ui.hindsight.vectorize.io, put it in `backend/.env`, restart. |
| Missing Groq API key | Answers fall back to evidence-only summaries (honest, no synthesis). Add `GROQ_API_KEY` and restart to enable synthesis. |
| `Hindsight retain/recall failed` or `memory unavailable` | Check internet/key. Verify with `curl http://localhost:8000/health` and `GET /api/memory/status` for the exact error. A self-hosted server also works: set `HINDSIGHT_BASE_URL=http://localhost:8888` (no API key needed locally). |
| Seed fails | Run it with the venv activated (`.\venv\Scripts\Activate.ps1`) from `backend/`. If `store.json` was written by an older version, delete `backend/data/store.json` and re-run. |
| Frontend cannot connect to backend | Is the backend up (`curl http://localhost:8000/health`)? Same machine + ports? `CORS_ORIGINS` in `backend/.env` must include the frontend origin (default already covers `http://localhost:5173`). |

Get keys: [Hindsight Cloud](https://ui.hindsight.vectorize.io) · [Groq console](https://console.groq.com).
Self-hosted Hindsight also works: `docker run -p 8888:8888 ghcr.io/vectorize-io/hindsight:latest`
and set `HINDSIGHT_BASE_URL=http://localhost:8888`.

### Demonstrate the memory arc (Interaction 1 → 5 → 20)

1. **Interaction 1** — on a fresh bank, ask *"What should I tell the doctor?"* → generic
   guidance (the agent says what it lacks).
2. **Interaction 5** — after seeding, ask *"What medications were started recently?"* →
   recalled, dated medication events with record IDs.
3. **Interaction 20** — ask *"What changed since the last hospital visit?"* or
   *"Have similar symptoms appeared before?"* → chronological synthesis across ED visits,
   medication changes, and conflicts, each item traced to a record. Use the **Before /
   After** tab to run the same question with and without memory side by side.

## Environment variables

See [.env.example](.env.example). Never commit `.env`.

| Variable | Purpose |
|---|---|
| `HINDSIGHT_API_KEY` | Hindsight Cloud API key (optional for self-hosted) |
| `HINDSIGHT_BASE_URL` | `https://api.hindsight.vectorize.io` or local server |
| `HINDSIGHT_BANK_ID` | Memory bank id (default `lifeline-demo`) |
| `GROQ_API_KEY` | Groq API key |
| `GROQ_MODEL` | Default `openai/gpt-oss-120b` |
| `CORS_ORIGINS`, `LOG_LEVEL` | App settings |

## Synthetic data

All records in [`backend/seed/patients.json`](backend/seed/patients.json) are fictional.
Names, facilities, clinicians, dates, and values were invented for the demo. The UI labels
every screen with **SYNTHETIC DEMO DATA — NOT REAL PATIENT DATA**.

## Safety & limitations

- **Not a medical device.** No diagnosis, no prescriptions, no treatment recommendations.
- Contradictions are shown as **UNRESOLVED** with "verify against the current clinical record".
- Memory or LLM outages degrade **honestly**: the UI states what could not be verified.
- This prototype has no authentication, audit logging, or data-retention controls. A real
  healthcare deployment would require full security, privacy and compliance review
  (including HIPAA/GDPR obligations). **No compliance claim is made or implied.**

## Testing

```powershell
# backend (from backend/ with venv activated)
python -m pytest tests\ -q                          # 74 tests

# frontend (from frontend/)
npm run build                                       # typecheck (tsc -b) + production build
```

A repeatable real-cloud integration smoke test (not mocks) lives at
`backend/scripts/live_smoke.py` — see [docs/live-verification.md](docs/live-verification.md).

Covers: retain decomposition & provenance, recall planning/merge/outage handling, agent
grounding & honest degradation, conflict detection, API contract, handoff structure.

## Future work

- Clinician feedback loop that strengthens/weakens memories (Hindsight observations)
- Mental models for standing summaries ("current med list", "active problems")
- File ingestion (PDF/DOCX) for additional synthetic records
- Multi-patient banks with strict isolation and scoped recall
