"""Seed the LifeLine demo.

Usage (from backend/):
    python seed/seed_patient.py            # retain into Hindsight + local store
    python seed/seed_patient.py --reset    # wipe local store first (memory bank keeps history)

Idempotent: re-running updates the local store and re-retains into Hindsight
(Hindsight retains are idempotent up to re-extraction of the same facts).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("lifeline.seed")

SEED_FILE = Path(__file__).resolve().parent / "patients.json"


def load_seed() -> dict:
    return json.loads(SEED_FILE.read_text(encoding="utf-8"))


def seed(reset: bool = False) -> dict:
    from app.config import config
    from app.models import MedicalRecord, Patient
    from app.services.conflicts import detect_conflicts
    from app.services.records_store import (
        reset_store,
        upsert_conflicts,
        upsert_patient,
        upsert_records,
    )

    data = load_seed()
    patient = Patient(**data["patient"])
    records = [MedicalRecord(**r) for r in data["records"]]

    if reset:
        reset_store()
        logger.info("Local store reset.")

    upsert_patient(patient)
    upsert_records(records)
    logger.info("Local store: patient %s with %d records.", patient.patient_id, len(records))

    conflicts = detect_conflicts(records)
    if conflicts:
        from app.services.records_store import get_conflicts  # merge with any existing

        # Re-derive ownership from source records so stored rows always carry it
        # (also normalizes legacy rows loaded from an old store.json).
        record_owner = {r.record_id: r.patient_id for r in records}
        for c in conflicts:
            c.patient_id = record_owner.get(c.record_a_id, patient.patient_id)

        existing = {c.conflict_id for c in get_conflicts()}
        upsert_conflicts([c for c in conflicts if c.conflict_id not in existing])
    logger.info("Conflicts detected: %d", len(conflicts))
    for conflict in conflicts:
        logger.info("  ⚠ %s — %s", conflict.conflict_id, conflict.description)

    # ---------------------------------------------------------- Hindsight
    memory_result: dict = {"configured": False}
    if not config.hindsight_configured:
        logger.warning(
            "HINDSIGHT_API_KEY not set — records stored locally only. "
            "Set HINDSIGHT_API_KEY in backend/.env and re-run to populate long-term memory."
        )
        return {
            "patient_id": patient.patient_id,
            "records": len(records),
            "conflicts": len(conflicts),
            "memory": memory_result,
        }

    from app.services.hindsight.client import HindsightUnavailableError, get_hindsight
    from app.services.hindsight.memory_service import bank_id_for_patient, record_to_memory_items

    hindsight = get_hindsight()
    bank_id = hindsight.ensure_bank(bank_id_for_patient(patient))
    logger.info("Hindsight bank: %s", bank_id)

    items: list[dict] = []
    for record in records:
        record_items = record_to_memory_items(record)
        items.extend(record_items)
        logger.info("[HINDSIGHT] retaining record %s (%d items)", record.record_id, len(record_items))

    try:
        result = hindsight.retain(items, bank_id=bank_id)
        retained = result.get("items_count", len(items))
        logger.info("[HINDSIGHT] retained %d memory items total into %s.", retained, bank_id)

        # Verification recall — proves the round trip works end-to-end.
        verification = hindsight.recall(
            "medication changes dizziness emergency visit", bank_id=bank_id
        )
        logger.info("[HINDSIGHT] verification recall returned %d memories.", len(verification))
        memory_result = {
            "configured": True,
            "bank_id": bank_id,
            "retained": retained,
            "verification_recall": len(verification),
        }
    except HindsightUnavailableError as exc:
        logger.error("Hindsight retain failed: %s", exc)
        memory_result = {"configured": True, "error": str(exc)}

    return {
        "patient_id": patient.patient_id,
        "records": len(records),
        "conflicts": len(conflicts),
        "memory": memory_result,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the LifeLine synthetic demo patient.")
    parser.add_argument("--reset", action="store_true", help="Wipe the local record store first.")
    args = parser.parse_args()
    summary = seed(reset=args.reset)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
