Most "AI over medical records" demos answer one question well: "summarize this document."

The questions that matter are temporal:

- What changed since the last hospital visit?
- What happened *after* that medication was started?
- Have we seen this symptom before — and is any of the history contradictory?

I built LifeLine to answer those. It's a long-term memory layer over a synthetic
patient's fragmented history — 18 records across two years: visits, labs, prescriptions,
discharge summaries, ED notes.

Architecture in three moves:

1. **Retain** — each record is decomposed into single-fact memories with real timestamps
   and provenance metadata (record_id, event_type, date), stored in Hindsight.
2. **Recall** — questions expand into a multi-dimension recall plan (medications, recent
   changes, similar prior events, conflicts) and run real Hindsight recall calls, which
   fuse semantic, keyword, graph and temporal retrieval.
3. **Synthesize** — Groq's openai/gpt-oss-120b writes an evidence-grounded answer that
   must cite record IDs, under hard safety boundaries: no diagnosis, no medication
   advice, conflicts stay UNRESOLVED for clinician verification.

The before/after on one question — "What changed since the last hospital visit?":

Without memory: a generic list of what one *should* tell a doctor.

With memory: the medication reduction after the ED visit, the new low-dose regimen,
the recurring dizziness notes, the second ED visit — each item dated and traced to its
source record — plus a flagged contradiction: an allergy documented in one record, the
same drug appearing in a later medication list. Status: UNRESOLVED. The system never
picks a winner.

Two things I learned building it:

- Memory quality is decided at write time. Splitting whole-record summaries into dated
  single-fact memories improved temporal recall more than any query-side tuning.
- Degradation must be legible. When Hindsight is unreachable, the app says "memory
  unavailable, historical context not verified" instead of answering anyway. In a
  health-adjacent tool, an honest gap beats a confident guess.

All data is synthetic; the app is a health-information assistant, not a medical device.

Code and demo walkthrough: [GitHub repo link]

#AIAgents #AI #Hindsight #AgentMemory #AIMemory #LLM
