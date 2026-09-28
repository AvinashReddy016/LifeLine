# Safety & Boundaries

## What LifeLine is

A health-information and history-assistance system: it organizes documented history,
reconstructs timelines, retrieves relevant historical context, summarizes documented
information, flags potential contradictions, and prepares clinician-facing summaries.

## What LifeLine is not

- Not a diagnostic system. It never names a condition as a conclusion.
- Not a prescriber. It never recommends starting/stopping/changing medication.
- Not a causal reasoner. It does not say "drug X caused symptom Y" — it can only say
  "a similar symptom was documented after a previous medication change; clinician
  verification is required."
- Not a source of truth. Where records disagree, both claims are shown and the conflict
  is marked UNRESOLVED. LifeLine never picks a winner.

## How boundaries are enforced

- The system prompt (`app/prompts/__init__.py`) bakes hard boundaries into every LLM call.
- Conflict objects carry `status: UNRESOLVED` and `required_action` at the data-model level.
- Every structured response ends with an explicit `safety_note`.
- Failure notes are honest: if Hindsight or the LLM is unavailable, the response says so
  rather than silently producing an unverified answer.

## Synthetic data policy

- All patients, clinicians, facilities, dates and values are fictional.
- The dataset is labeled synthetic in the seed file, the API responses (`synthetic: true`),
  and a persistent banner in the UI.
- No real PHI is used anywhere in the repository.

## Compliance

This prototype makes **no** HIPAA, GDPR, or any other compliance claim. A production
healthcare deployment would require — at minimum — authentication and authorization,
audit logging, encryption and data-retention controls, infrastructure review, and legal
assessment under applicable regulations.

## Known limitations

- Rule-based conflict detection uses a curated drug lexicon; it will miss drugs outside
  the demo dataset and could over-match in other domains.
- The record store is a JSON file (prototype-grade), not a database.
- Interaction retention grows the bank unboundedly; production use would need retention
  policies and bank lifecycle management.
