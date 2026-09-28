# Demo Flow (5 minutes)

Setup once before recording: backend running on :8000, frontend on :5173, demo seeded
(`python seed/seed_patient.py`), Hindsight bank populated (memory chip shows "Hindsight · N memories").

## 0:00 – 0:30 · What LifeLine is
- Show the **home page**: "Your medical history has a memory."
- Say: fragmented records in, longitudinal memory out — built on Hindsight.
- Click **Open Demo Patient**.

## 0:30 – 1:00 · The problem
- Point at the **Timeline**: two years of visits, labs, medication changes, two ED visits.
- Open the **Conflicts** tab: allergy documented in one record, the same drug appearing in
  a later medication record. Status: UNRESOLVED.
- Say: a generic chatbot sees documents; it cannot see this web of "what happened after what".

## 1:00 – 2:00 · Records become memory
- Show `GET /api/memory/status` (the chip already shows it) and `backend/seed/seed_patient.py`
  briefly — records decompose into dated, provenance-linked memories retained into Hindsight.
- Click the **Inside the memory bank** panel — real memories from the live bank.

## 2:00 – 3:00 · Memory changes the answer
- Ask: **"What changed since the last hospital visit?"**
  → chronological synthesis with record IDs; **Memories used** panel shows relevance scores.
- Ask: **"Have similar symptoms appeared before?"**
  → both ED visits surface, connected across eight months.
- Click a record chip (`REC-1018`) → full source record modal. That's provenance.

## 3:00 – 3:45 · Conflicts surface themselves
- Ask: **"Are there conflicting entries in the patient's history?"**
  → the penicillin allergy-vs-prescription conflict appears inline: both claims, both
  records, UNRESOLVED, "verify against the current clinical record".
- Emphasize: LifeLine never resolved it silently.

## 3:45 – 4:15 · Handoff
- Click **Generate Handoff** → the 30-second clinician brief: current context, medication
  changes, prior related events, conflicts, verification needed.

## 4:15 – 4:45 · Before / after
- Open the **Before / After** tab, run the comparison.
- Left: generic assistant, zero memories, zero provenance. Right: memories used, records
  linked, conflicts surfaced.

## 4:45 – 5:00 · Takeaway
- End on: **"LifeLine doesn't just retrieve a patient's records. It remembers how those
  records connect over time."**

## Fallbacks
- Memory offline? The chat still answers from loaded records and says memory couldn't be
  verified — that honesty is itself a feature to show.
- LLM offline? Evidence-only answers still list recalled memories with scores.
