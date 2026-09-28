# The Hard Part Wasn't Summarizing the Record. It Was Remembering What Came Before It.

*How LifeLine uses Hindsight to turn fragmented medical records into longitudinal memory — and what that changes about the answers an agent can give.*

## The problem that isn't retrieval

Ask any clinician what they actually do with a new patient's history and the answer is
rarely "search for a document." It's reconstruction: this antihypertensive was started in
September, the dose went up in October, the patient landed in the emergency department in
November, and the dose came down two weeks later. The facts are scattered across a
prescription log, a discharge summary, and an ED note — three systems, three formats,
eight months apart.

The interesting question is never "find me the discharge summary." It's **"what changed
since the last visit, and what happened after that change?"** That is a question about
relationships across time. It requires memory, not search.

That's the problem LifeLine addresses. It's a working prototype — one synthetic patient,
one narrow workflow — built as a memory layer over medical history, using
[Hindsight](https://github.com/vectorize-io/hindsight) as the memory system and Groq's
`openai/gpt-oss-120b` for synthesis.

## Why document RAG falls short here

The default architecture for "AI over documents" is retrieval-augmented generation:
chunk the documents, embed them, pull the top-k similar chunks, and generate. That
pipeline is well understood and easy to build. It's also structurally mismatched with
longitudinal questions.

- **Similarity isn't relevance.** "Have we seen this symptom before?" retrieves chunks
  that *mention* the symptom, ranked by text overlap. It won't connect a symptom note to
  the medication change that preceded it, or notice that the same pattern occurred twice,
  eight months apart, under different clinicians.
- **Chunks have no temporal identity.** A 2024 prescription and a 2026 ED note are just
  text. Nothing in the pipeline knows that "discontinued" in March beats "started" in
  January — or that a pharmacy label listing a drug contradicts an allergy note.
- **No consolidation.** Each query re-discovers the history from scratch. Nothing
  accumulates. Nothing gets stronger with evidence.

The distinction that shaped the whole build: **document retrieval is not longitudinal
memory.** They look similar in a demo and diverge the moment the question involves time.

## The architecture in one paragraph

LifeLine decomposes each medical record into single-fact memories — one clinically
meaningful statement per memory, each carrying the record date as its timestamp and
provenance metadata (`record_id`, `event_type`, `date`, `synthetic`) — and retains them
into a Hindsight bank with `retain_batch`. When a question arrives, it's expanded into a
multi-dimension recall plan (direct, medication history, recent changes, similar events,
conflicts), and each dimension runs a real `recall()` against Hindsight, which merges
semantic, keyword, graph and temporal retrieval. Recalled memories are linked back to
source records, rule-based detectors look for contradictions across the record set, and
the LLM synthesizes an answer that must cite record IDs and stays inside strict safety
boundaries: organize and surface, never diagnose, never resolve a conflict silently.

The response is structured — `answer`, `memories_used`, `source_records`,
`timeline_events`, `conflicts`, `uncertainty`, `safety_note` — so the UI can show the
evidence panel next to the prose, and the user can drill from any memory to the exact
source record it came from.

## What memory changes, concretely

**Without memory**, the same question — *"What changed since the last hospital visit?"* —
gets the generic-assistant answer: a polite instruction to review current symptoms,
medications, and allergies. Technically correct, clinically useless.

**With memory**, the answer is built from recalled facts:

> Since the previous recorded visit: a medication was reduced after an emergency visit
> (REC-1014), a new low-dose regimen was started (REC-1014, 2025-11-20), brief dizziness
> episodes persisted (REC-1015), and a second emergency visit was recorded (REC-1018,
> 2026-03-05). One conflicting medication entry was found and remains unresolved —
> clinician verification is required.

And on conflict questions, the system surfaces both claims side by side — an allergy
documented in one record, the same drug appearing in a later medication list — marked
**UNRESOLVED** with the required action: verify against the current clinical record.
LifeLine never picks a winner. That constraint is a feature, not a limitation; the
failure mode of "helpful" AI in healthcare is confident resolution of things only a
clinician can resolve.

## One lesson worth stealing: failures must be legible

The most useful engineering decision in this project was making every degradation
honest. If Hindsight is unreachable, the answer says "Memory service unavailable — I can
still summarize the loaded records, but I cannot verify historical context," and the UI
carries that note in the uncertainty panel. If the LLM fails, the response falls back to
the raw recalled memories with relevance scores rather than pretending. An assistant
whose value is *trustworthy context* loses everything if it silently answers without the
context. The fallback paths aren't error handling bolted on at the end — they're part of
the product.

A second lesson: **decompose before you retain.** Our first version retained whole
record summaries. Recall worked, but temporal queries were blunt — "what happened after
March" dragged in unrelated text because a summary is one blob. Splitting records into
dated single-fact memories (and skipping structural header lines) made temporal and
entity recall dramatically sharper. Memory quality is decided at write time, not query
time.

## Try it

The repository includes an idempotent seeding script, a demo patient with deliberately
planted contradictions, a before/after demo mode, and a test suite covering the memory
pipeline, agent behavior, and API contract.

- Hindsight: https://github.com/vectorize-io/hindsight
- Documentation: https://hindsight.vectorize.io/
- What agent memory is: https://vectorize.io/what-is-agent-memory

*All data in the project is synthetic. LifeLine is a health-information assistant, not a
medical device, and nothing it produces replaces clinician verification.*
