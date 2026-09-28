# LifeLine — Demo Video Script (4:30 target)

Conventions: **NARRATION** = what you say. `ACTION` = what you do on screen.
Tone: an engineer showing something they built, not a product ad.

---

## 0:00 – 0:30 · What LifeLine is

`ACTION` Home page. Let the headline sit for a second: "Your medical history has a memory."

**NARRATION:** "This is LifeLine — a memory layer for medical history. Medical records
are fragmented: prescriptions here, discharge summaries there, ED notes somewhere else.
LifeLine stores that history as long-term memory with Hindsight, so an assistant can
answer the questions that actually matter — what changed, what connects, and what
contradicts — with the source records attached. Everything here is synthetic data."

`ACTION` Click **Open Demo Patient**.

---

## 0:30 – 1:00 · The problem

`ACTION` Patient workspace. Scroll the **Timeline** slowly.

**NARRATION:** "Two years of records: a dyspepsia visit, blood pressure therapy, a
medication switch, an allergy note, two emergency visits. A generic chatbot can
summarize any single one of these documents. What it can't do is tell you that the ED
visit in November came three weeks after a dose change — because that relationship
lives *across* documents, in time."

`ACTION` Open the **Conflicts** tab.

**NARRATION:** "And sometimes the records contradict each other. Penicillin documented
as an allergy here — appearing in a medication list there. LifeLine doesn't resolve
that. It surfaces it, unresolved, for a clinician."

---

## 1:00 – 1:45 · Records become memory (show Hindsight)

`ACTION` Briefly show `backend/seed/seed_patient.py` and the retain log output
(`[HINDSIGHT] retaining record REC-1006 (5 items)` …).

**NARRATION:** "Seeding decomposes every record into single-fact memories — one dated
statement each, carrying record ID and provenance metadata — and retains them into a
Hindsight bank. The date matters: temporal recall is a first-class feature of Hindsight,
and it's what makes 'what changed since March' a real query instead of a text search."

`ACTION` Show the **Inside the memory bank** panel with live memories from the bank.
Then open DevTools → Network, filter `/api/`.

**NARRATION:** "And this isn't simulated — every question triggers real recall calls
you can watch in the network tab."

---

## 1:45 – 2:45 · Memory changes the answer

`ACTION` Ask: **"What changed since the last hospital visit?"**

**NARRATION:** "Let's ask the question that requires actual memory."

`ACTION` Point at the answer, then the **Memories used** panel.

**NARRATION:** "The answer is chronological, every claim cites a record ID, and below
it is the evidence: the memories Hindsight recalled, with relevance scores. This one
scored 92%, from the November emergency record."

`ACTION` Click **"Have similar symptoms appeared before?"**

**NARRATION:** "Similar-event recall connects the two ED visits across eight months —
the kind of link that's invisible when you're staring at individual documents."

`ACTION` Click a record chip → source record modal.

**NARRATION:** "And any memory drills down to the exact source record. No evidence, no claim."

---

## 2:45 – 3:30 · Conflicts surface themselves

`ACTION` Ask: **"Are there conflicting entries in the patient's history?"**

**NARRATION:** "The conflict appears inline: claim A from March, claim B from the
discharge pharmacy list, both records cited, status unresolved — 'verify against the
current clinical record.' The system is allowed to organize history and flag
contradictions. It is not allowed to play doctor. That boundary is in the prompt, the
data model, and every response's safety note."

---

## 3:30 – 4:00 · Handoff + before/after

`ACTION` Click **Generate Handoff**.

**NARRATION:** "One click produces the clinician brief: current context, medication
changes, prior events, conflicts, and what needs verification. Readable in thirty
seconds."

`ACTION` Open the **Before / After** tab, run the comparison.

**NARRATION:** "Same question, two assistants. Without memory: generic advice, zero
provenance. With Hindsight: recalled events, linked records, flagged conflicts. That's
the whole difference between retrieval and longitudinal memory."

---

## 4:00 – 4:30 · Takeaway

`ACTION` Back to home page.

**NARRATION:** "LifeLine doesn't just retrieve a patient's records. It remembers how
those records connect over time — and it shows its work. The memory layer is Hindsight,
the synthesis is Groq, and the code is in the repo. Thanks for watching."

`ACTION` End card: repo URL + "Synthetic demo data — not real patient data."

---

## Recording notes

- Browser zoom 110–125%; dark OS theme off (the UI is light).
- Keep DevTools network tab pre-filtered to the API host for the recall-shot.
- If Hindsight is slow on first recall, that's bank consolidation — mention it, it's real.
- Fallback narrative if anything fails live: show the honest degradation note and say
  "this is the failure behavior working as designed."
