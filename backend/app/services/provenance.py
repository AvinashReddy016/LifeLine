"""Provenance: link recalled memories back to their source records."""
from __future__ import annotations

import re
from typing import Any

from app.models import MedicalRecord

_REC_PATTERN = re.compile(r"REC-\d{3,4}")


def extract_record_ids(memory: dict[str, Any]) -> list[str]:
    """Best-effort provenance extraction: metadata first, then REC- ids in the text."""
    metadata = memory.get("metadata") or {}
    ids: list[str] = []
    for key in ("record_id", "record_ids", "source_record_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            ids.append(value)
        elif isinstance(value, list):
            ids.extend(v for v in value if isinstance(v, str))
    if not ids:
        ids = sorted(set(_REC_PATTERN.findall(memory.get("text", ""))))
    return sorted(set(ids))


def link_memory_to_records(
    memories: list[dict[str, Any]],
    record_lookup: dict[str, MedicalRecord],
) -> list[dict[str, Any]]:
    """Attach full source-record payloads to each memory for the evidence panel."""
    enriched: list[dict[str, Any]] = []
    for memory in memories:
        record_ids = extract_record_ids(memory)
        sources = []
        for record_id in record_ids:
            record = record_lookup.get(record_id)
            if record:
                sources.append(record.to_dict())
        enriched.append({
            "memory": memory,
            "record_ids": record_ids,
            "source_records": sources,
        })
    return enriched


def provenance_log(record_count: int) -> None:
    """Demo-friendly observability line."""
    import logging

    logging.getLogger("lifeline.provenance").info(
        "[PROVENANCE] linked %d source record(s)", record_count
    )
