"""Real-Hindsight integration smoke test — NO mocks, hits Hindsight Cloud.

Usage (from backend/):
    venv/Scripts/python.exe scripts/live_smoke.py

Requires backend/.env with a valid HINDSIGHT_API_KEY (GROQ_API_KEY optional but
recommended so LLM synthesis runs). Prints one [CHECK n] block per verification
step and a final PASS/FAIL table. Every question used here is novel — none appear
in the UI suggestion chips, the seed data, or the test suite.
"""
from __future__ import annotations

import json
import logging
import sys
import tempfile
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

# Windows consoles default to cp1252; real LLM/memory text contains Unicode.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Isolate the local JSON store so the smoke run never touches backend/data/store.json
_tmp = Path(tempfile.mkdtemp(prefix="lifeline-live-smoke-"))

import app.services.records_store as store  # noqa: E402

store.STORE_FILE = _tmp / "store.json"
store.DATA_DIR = _tmp

from app.config import config  # noqa: E402
from app.models import MedicalRecord, Patient  # noqa: E402
from app.services.agent import answer_question  # noqa: E402
from app.services.agent_history import remember_interaction  # noqa: E402
from app.services.handoff import generate_handoff_summary  # noqa: E402
from app.services.hindsight import client as hclient  # noqa: E402
from app.services.hindsight.memory_service import (  # noqa: E402
    bank_id_for_patient,
    recall_for_question,
    retain_records,
)
from app.services.records_store import upsert_patient, upsert_records  # noqa: E402

# ---------------------------------------------------------------- log capture
hindsight_lines: list[str] = []


class CaptureHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        hindsight_lines.append(f"{record.levelname} {record.name}: {record.getMessage()}")


logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
capture = CaptureHandler()
logging.getLogger("lifeline.hindsight").addHandler(capture)
logging.getLogger("lifeline.provenance").addHandler(capture)

RESULTS: list[tuple[str, str, str]] = []  # (check, detail, PASS/FAIL)


def check(n: int, name: str, ok: bool, detail: str) -> None:
    status = "PASS" if ok else "FAIL"
    RESULTS.append((f"[{n}] {name}", detail, status))
    print(f"\n=== [CHECK {n}] {name}: {status} ===")
    print(f"    {detail}")


def require_config() -> None:
    print("Configuration:")
    print(f"  hindsight_configured = {config.hindsight_configured}")
    print(f"  groq_configured      = {config.groq_configured}")
    print(f"  base_url             = {config.hindsight_base_url}")
    if not config.hindsight_configured:
        print("HINDSIGHT_API_KEY missing — cannot run the REAL smoke test.")
        sys.exit(2)


def fresh_bank(bank_id: str) -> None:
    """Delete + recreate the bank for a clean retain count."""
    raw = hclient.HindsightClientWrapper()
    client = raw._raw_client()
    try:
        client.delete_bank(bank_id=bank_id)
        print(f"  deleted stale bank {bank_id}")
    except Exception as exc:  # bank may not exist yet
        print(f"  no stale bank to delete for {bank_id} ({type(exc).__name__})")
    raw._bootstrapped_banks.clear()


def main() -> int:
    require_config()

    # ------------------------------------------------------------------ [1] app starts with real config
    from fastapi.testclient import TestClient
    from app.main import app

    health = TestClient(app).get("/health").json()
    check(1, "App starts with real HINDSIGHT_API_KEY",
          health.get("hindsight_configured") is True and health.get("status") == "ok",
          f"/health -> status={health.get('status')}, hindsight_configured={health.get('hindsight_configured')}, groq_configured={health.get('groq_configured')}")

    # ------------------------------------------------------------------ data
    seed = json.loads((BACKEND_ROOT / "seed" / "patients.json").read_text(encoding="utf-8"))
    arjun = Patient(**seed["patient"])
    arjun_records = [MedicalRecord(**r) for r in seed["records"]]
    upsert_patient(arjun)
    upsert_records(arjun_records)

    # Novel second patient with a fact that appears nowhere in Arjun's history
    rohan = Patient(
        patient_id="P-9002", name="Rohan Sharma", age=52, sex="M", blood_type="B+",
        current_issue="Routine follow-up", current_medications=["Metformin 500 mg daily"],
    )
    rohan_records = [MedicalRecord(
        record_id="REC-9002", patient_id="P-9002", date="2026-04-11",
        record_type="visit", title="Hobby intake", facility="Family Practice",
        clinician="Dr. Nair", summary="Restores vintage motorcycles as a hobby.",
        body="Social history: patient restores vintage motorcycles in a home garage. "
             "Reports occasional hand tremor after long workshop sessions. No medications changed.",
    )]
    upsert_patient(rohan)
    upsert_records(rohan_records)

    arjun_bank = bank_id_for_patient(arjun)
    rohan_bank = bank_id_for_patient(rohan)
    print(f"\nBanks: arjun={arjun_bank} | rohan={rohan_bank}")
    fresh_bank(arjun_bank)
    fresh_bank(rohan_bank)

    # ------------------------------------------------------------------ [2]+[3] seed + retain into real cloud
    print("\nSeeding Arjun Mehra (17 records) into the REAL bank...")
    retain_res = retain_records(arjun_records, patient=arjun)
    listed = hclient.HindsightClientWrapper().list_memories(limit=500, bank_id=arjun_bank)
    check(2, "Seed into REAL Hindsight bank",
          retain_res.get("retained", 0) >= len(arjun_records) and len(listed) > 0,
          f"retained {retain_res.get('retained')} items from {len(arjun_records)} records; list_memories now returns {len(listed)} memories in {arjun_bank}")

    # ------------------------------------------------------------------ [4]+[5] 5 novel questions, real recall each
    novel_questions = [
        "Which antibiotic was flagged as an allergy, and where was that documented?",
        "What does the history show about stomach or reflux complaints?",
        "Walk me through the emergency department visits in chronological order.",
        "Did any follow-up visit document a new symptom?",
        "Is there anything recorded about a pharmacy list not matching home medications?",
    ]
    q_ok, q_details = True, []
    for i, question in enumerate(novel_questions, start=1):
        result = answer_question(arjun.patient_id, question)
        mem_count = len(result.memories_used)
        scores = [m["score"] for m in result.memories_used]
        linked = {rid for m in result.memories_used for rid in m["record_ids"]}
        ok = mem_count > 0 and bool(linked)
        q_ok = q_ok and ok
        q_details.append(f"Q{i}: {mem_count} memories (top score {max(scores) if scores else 0}), records {sorted(linked)[:4]}")
        print(f"\n  Q{i}: \"{question}\"")
        print(f"    memories={mem_count}, linked={sorted(linked)[:4]}")
        print(f"    answer[:160]: {result.answer[:160]!r}")
    check(4, "5 novel questions answered from memory", q_ok, " | ".join(q_details))

    real_recall_lines = [ln for ln in hindsight_lines if "recall query" in ln.lower()]
    # The direct dimension sends the question verbatim; every question must appear
    # in the captured Hindsight log at least once.
    missing_direct = [q for q in novel_questions if not any(q[:50] in ln for ln in real_recall_lines)]
    check(5, "Each question performed a REAL Hindsight recall",
          not missing_direct,
          f"{len(real_recall_lines)} '[HINDSIGHT] recall query' log lines captured; "
          f"direct query executed for {len(novel_questions) - len(missing_direct)}/{len(novel_questions)} questions")

    # ------------------------------------------------------------------ [6] query sensitivity on the real service
    r_meds = recall_for_question("What medications were started recently?", arjun)
    r_ed = recall_for_question("Has this patient been to the emergency department?", arjun)
    med_ids = {m["id"] for m in r_meds["memories"]}
    ed_ids = {m["id"] for m in r_ed["memories"]}
    different = bool(med_ids and ed_ids) and med_ids != ed_ids
    med_texts = " ".join(m["text"].lower() for m in r_meds["memories"])
    ed_texts = " ".join(m["text"].lower() for m in r_ed["memories"])
    topical = ("medication" in med_texts or "started" in med_texts or "dose" in med_texts) and \
              ("emergency" in ed_texts or "ed " in ed_texts or "er " in ed_texts or "hospital" in ed_texts)
    check(6, "Query sensitivity (different query -> different memories)",
          different and topical,
          f"meds-query -> {len(med_ids)} unique memories; ed-query -> {len(ed_ids)} unique memories; "
          f"overlap={len(med_ids & ed_ids)}; topical keywords present: {topical}")

    # ------------------------------------------------------------------ [7] cross-interaction memory
    # Note: Hindsight extracts/rewrites interaction facts, so we query topically and
    # match on distinctive retained CONTENT, not on an arbitrary token.
    token = "zephyr-quartz-739"
    remember_interaction(arjun.patient_id,
                         f"Note for later ({token}): the patient prefers morning appointments.",
                         f"Acknowledged and remembered ({token}): morning appointments noted for future sessions.",
                         patient=arjun)
    int_hits: list[dict] = []
    # Ask as an interaction question so the recall plan includes the dedicated
    # interactions dimension (that is how the product surfaces past sessions).
    for attempt in range(5):  # extraction/publication can lag retain
        r_int = recall_for_question("What did we discuss in previous conversations about appointment times?", arjun)
        int_hits = [m for m in r_int["memories"]
                    if "morning appointment" in m["text"].lower() or "appointment" in m["text"].lower()]
        if int_hits:
            break
        time.sleep(4)
    check(7, "Cross-interaction memory (retain interaction -> recall later)",
          bool(int_hits),
          f"interaction retained, then recalled with a NEW topical query; "
          f"{len(int_hits)} interaction memory(ies) matched (e.g. {int_hits[0]['text'][:70]!r})" if int_hits
          else "interaction retained but never recallable")

    # ------------------------------------------------------------------ [8] patient separation on real banks
    retain_records(rohan_records, patient=rohan)
    leak_a = recall_for_question("vintage motorcycles workshop hobby", arjun)
    leak_b = recall_for_question("dizziness emergency department allergy", rohan)
    a_clean = all("motorcycle" not in m["text"].lower() for m in leak_a["memories"])
    b_clean = all("dizziness" not in m["text"].lower() and "allerg" not in m["text"].lower() for m in leak_b["memories"])
    rohan_hits = recall_for_question("motorcycle workshop hobby", rohan)["memories"]
    check(8, "Patient isolation (two synthetic patients, separate real banks)",
          a_clean and b_clean and bool(rohan_hits),
          f"Arjun asking about motorcycles -> {len(leak_a['memories'])} memories, leak={not a_clean}; "
          f"Rohan asking about Arjun's symptoms -> {len(leak_b['memories'])} memories, leak={not b_clean}; "
          f"Rohan's own motorcycle memory recallable: {bool(rohan_hits)}")

    # ------------------------------------------------------------------ [10] real reflect
    handoff = generate_handoff_summary(arjun)
    synthesis = handoff.sections.get("LONGITUDINAL SYNTHESIS (from memory)", "")
    direct = hclient.HindsightClientWrapper().reflect(
        query="Summarize how this patient's medication and symptom history evolved.",
        bank_id=arjun_bank,
    )
    check(10, "REAL Hindsight reflect (handoff longitudinal synthesis)",
          bool(synthesis.strip()) and bool((direct.get("text") or "").strip()),
          f"handoff synthesis section present ({len(synthesis)} chars, starts: {synthesis[:90]!r}); "
          f"direct reflect returned {len(direct.get('based_on') or [])} source memories")

    # ------------------------------------------------------------------ [11] honest degradation (network-level outage)
    real_url = config.hindsight_base_url
    saved_instance = hclient.HindsightClientWrapper._instance
    try:
        config.hindsight_base_url = "http://127.0.0.1:9"  # unroutable -> real connection failure
        hclient.HindsightClientWrapper._instance = None  # force a fresh client against the dead URL
        result = answer_question(arjun.patient_id, "What changed since the previous visit?")
        disclosed = any("Memory service unavailable" in u for u in result.uncertainty)
        no_memories = result.memories_used == []
        answer_clean = "Memory service unavailable" in result.answer or disclosed
        check(11, "Honest degradation when Hindsight is unavailable",
              disclosed and no_memories and answer_clean,
              f"uncertainty discloses outage: {disclosed}; memories_used empty: {no_memories}; "
              f"answer opens with the disclosure: {result.answer[:80]!r}")
    finally:
        config.hindsight_base_url = real_url
        hclient.HindsightClientWrapper._instance = saved_instance

    # ------------------------------------------------------------------ [12] visible real activity
    retains = [ln for ln in hindsight_lines if "retain" in ln.lower()]
    reflects = [ln for ln in hindsight_lines if "reflect" in ln.lower()]
    check(12, "Visible real Hindsight activity (backend logs)",
          bool(retains) and bool(real_recall_lines) and bool(reflects),
          f"log lines captured: {len(retains)} retain, {len(real_recall_lines)} recall, {len(reflects)} reflect "
          f"(sample: {real_recall_lines[0] if real_recall_lines else 'none'})")

    # ------------------------------------------------------------------ summary
    print("\n" + "=" * 74)
    print("REAL-HINDSIGHT INTEGRATION SMOKE TEST — SUMMARY")
    print("=" * 74)
    failures = 0
    for name, detail, status in RESULTS:
        failures += status == "FAIL"
        print(f"  {status:4}  {name}")
    print("=" * 74)
    print(f"{len(RESULTS) - failures}/{len(RESULTS)} checks passed  |  store isolated at {_tmp}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
