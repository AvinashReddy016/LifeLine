"""Hindsight client wrapper.

Thin wrapper around the official `hindsight-client` SDK with:
- lazy singleton initialization
- bank bootstrap (create if missing)
- timeout handling
- a clean "unavailable" signal so callers can degrade gracefully

Official docs: https://docs.dev.hindsight.vectorize.io/python-sdk/
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from app.config import config

logger = logging.getLogger("lifeline.hindsight")

_CALL_POOL = ThreadPoolExecutor(max_workers=2, thread_name_prefix="hindsight-sync")


def _call_sync(fn, /, **kwargs):
    """Run a sync SDK call, off the event loop when one is already running.

    The hindsight-client SDK's sync methods drive their own event loop
    (asyncio.run internally), which raises "This event loop is already running"
    when invoked from inside FastAPI/uvicorn. Delegating those calls to a worker
    thread gives scripts, TestClient and live servers identical behavior.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fn(**kwargs)  # no loop here — call directly
    return _CALL_POOL.submit(fn, **kwargs).result(timeout=120)


class HindsightUnavailableError(RuntimeError):
    """Raised when Hindsight cannot be reached or is not configured."""


class HindsightClientWrapper:
    """Singleton wrapper over hindsight_client.Hindsight."""

    _instance: Optional["HindsightClientWrapper"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self._client: Any = None
        self._init_error: Optional[str] = None
        self._bootstrap_lock = threading.Lock()
        self._bootstrapped_banks: set[str] = set()

    @classmethod
    def instance(cls) -> "HindsightClientWrapper":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------ core

    def _raw_client(self) -> Any:
        """Lazily construct the underlying SDK client. Raises HindsightUnavailableError."""
        if self._client is not None:
            return self._client
        if not config.hindsight_configured:
            raise HindsightUnavailableError(
                "Hindsight is not configured. Set HINDSIGHT_API_KEY (and optionally "
                "HINDSIGHT_BASE_URL / HINDSIGHT_BANK_ID) in .env."
            )
        try:
            from hindsight_client import Hindsight  # imported lazily so the API works without the SDK
        except ImportError as exc:  # pragma: no cover - depends on env
            raise HindsightUnavailableError(
                "hindsight-client package not installed. Run: pip install hindsight-client"
            ) from exc

        try:
            kwargs: dict[str, Any] = {
                "base_url": config.hindsight_base_url,
                "timeout": 60.0,
            }
            if config.hindsight_api_key:
                kwargs["api_key"] = config.hindsight_api_key
            self._client = Hindsight(**kwargs)
        except Exception as exc:  # construction failure (bad URL etc.)
            self._client = None
            raise HindsightUnavailableError(f"Could not initialize Hindsight client: {exc}") from exc
        return self._client

    def ensure_bank(self, bank_id: Optional[str] = None) -> str:
        """Create the memory bank if it doesn't exist yet. Idempotent."""
        bank_id = bank_id or config.hindsight_bank_id
        if bank_id in self._bootstrapped_banks:
            return bank_id
        client = self._raw_client()
        with self._bootstrap_lock:
            if bank_id in self._bootstrapped_banks:
                return bank_id
            try:
                _call_sync(
                client.create_bank,
                    bank_id=bank_id,
                    name="LifeLine — longitudinal medical memory",
                    background=(
                        "LifeLine stores a synthetic patient's fragmented medical history as "
                        "longitudinal memories: visits, medications, symptoms, labs, reactions "
                        "and procedures. Every memory carries provenance metadata (record_id, "
                        "event_type, date) and is used to reconstruct the patient's story over "
                        "time. This is a health-information assistant, not a diagnostic system."
                    ),
                )
                logger.info("[HINDSIGHT] created bank %s", bank_id)
            except Exception as exc:
                # Bank already existing (409) is fine; anything else we surface.
                message = str(exc)
                if "409" in message or "already" in message.lower():
                    logger.info("[HINDSIGHT] bank %s already exists", bank_id)
                else:
                    raise HindsightUnavailableError(f"Could not create memory bank: {exc}") from exc
            self._bootstrapped_banks.add(bank_id)
        return bank_id

    # ------------------------------------------------------------- operations

    def delete_bank(self, bank_id: str) -> None:
        """Delete a memory bank (used to clean up isolated scratch/demo banks)."""
        client = self._raw_client()
        try:
            _call_sync(client.delete_bank, bank_id=bank_id)
            self._bootstrapped_banks.discard(bank_id)
            logger.info("[HINDSIGHT] deleted bank %s", bank_id)
        except Exception as exc:
            message = str(exc)
            if "404" in message or "not found" in message.lower():
                self._bootstrapped_banks.discard(bank_id)
                return  # already gone — deletion is idempotent for our purposes
            raise HindsightUnavailableError(f"Could not delete memory bank: {exc}") from exc

    def retain(self, items: list[dict[str, Any]], bank_id: Optional[str] = None) -> dict[str, Any]:
        """Retain a batch of memory items.

        Each item: {content, context?, timestamp?, metadata?}. The SDK's retain
        accepts items with metadata via retain_batch; we route through retain_batch
        for provenance support.
        """
        bank_id = self.ensure_bank(bank_id)
        client = self._raw_client()
        payload = [
            {
                "content": item["content"],
                **({"context": item["context"]} if item.get("context") else {}),
                **({"timestamp": item["timestamp"]} if item.get("timestamp") else {}),
                **({"metadata": _stringify_metadata(item["metadata"])} if item.get("metadata") else {}),
            }
            for item in items
        ]
        try:
            result = _call_sync(client.retain_batch, bank_id=bank_id, items=payload, retain_async=False)
            logger.info("[HINDSIGHT] retained %d item(s) into %s", len(payload), bank_id)
        except HindsightUnavailableError:
            raise
        except Exception as exc:
            raise HindsightUnavailableError(f"Hindsight retain failed: {exc}") from exc

        # Bridge the server-side indexing lag: freshly retained items are not
        # immediately recallable. Poll the returned operations (best effort) so a
        # retain->recall sequence observes its own writes.
        operation_ids: list[str] = []
        raw_ids = (result.get("operation_ids") or result.get("operation_id")) if isinstance(result, dict) else (
            getattr(result, "operation_ids", None) or getattr(result, "operation_id", None)
        )
        if isinstance(raw_ids, str):
            operation_ids = [raw_ids]
        elif isinstance(raw_ids, list):
            operation_ids = [op for op in raw_ids if isinstance(op, str)]
        _await_operations(client, bank_id, operation_ids)

        return result if isinstance(result, dict) else {"success": True, "items_count": len(payload), "operation_ids": operation_ids}

    def recall(
        self,
        query: str,
        limit: int = 8,
        types: Optional[list[str]] = None,
        bank_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Recall memories relevant to a query. Returns normalized dicts.

        Raises HindsightUnavailableError on failure so callers can degrade gracefully.
        """
        bank_id = self.ensure_bank(bank_id)
        client = self._raw_client()
        logger.info("[HINDSIGHT] recall query: %s", query[:120])
        kwargs: dict[str, Any] = {"query": query, "max_tokens": 4096, "budget": "mid"}
        if types:
            kwargs["types"] = types
        try:
            result = _call_sync(client.recall, bank_id=bank_id, **kwargs)
        except HindsightUnavailableError:
            raise
        except Exception as exc:
            raise HindsightUnavailableError(f"Hindsight recall failed: {exc}") from exc

        memories: list[dict[str, Any]] = []
        raw_results = getattr(result, "results", None) or []
        for i, memory in enumerate(raw_results):
            text = getattr(memory, "text", "") or str(memory)
            metadata = getattr(memory, "metadata", None) or {}
            memories.append(
                {
                    "id": getattr(memory, "id", None) or f"mem_{i}",
                    "text": text,
                    "memory_type": getattr(memory, "type", "") or "",
                    "score": _parse_score(memory),
                    "metadata": metadata if isinstance(metadata, dict) else {},
                    "record_ids": _extract_record_ids(metadata, text),
                }
            )
        logger.info("[HINDSIGHT] %d memories returned", len(memories))
        return memories

    def reflect(self, query: str, context: Optional[str] = None, bank_id: Optional[str] = None) -> dict[str, Any]:
        """Reflection over stored memories (used for longitudinal synthesis)."""
        bank_id = self.ensure_bank(bank_id)
        client = self._raw_client()
        kwargs: dict[str, Any] = {"query": query, "budget": "high"}
        if context:
            kwargs["context"] = context
        try:
            response = _call_sync(client.reflect, bank_id=bank_id, **kwargs)
        except HindsightUnavailableError:
            raise
        except Exception as exc:
            raise HindsightUnavailableError(f"Hindsight reflect failed: {exc}") from exc

        based_on: list[dict[str, Any]] = []
        raw_based_on = getattr(response, "based_on", None)
        # SDK >= 0.10 nests sources under based_on.memories / .mental_models / .directives
        sources = raw_based_on
        if raw_based_on is not None and not isinstance(raw_based_on, list):
            sources = getattr(raw_based_on, "memories", None) or []
        for source in sources or []:
            text = getattr(source, "text", None) or getattr(source, "content", None) or str(source)
            based_on.append(
                {
                    "text": text,
                    "metadata": getattr(source, "metadata", None) or {},
                }
            )
        logger.info("[HINDSIGHT] reflect completed (%d sources)", len(based_on))
        return {"text": getattr(response, "text", "") or "", "based_on": based_on}

    def list_memories(self, limit: int = 200, bank_id: Optional[str] = None) -> list[dict[str, Any]]:
        bank_id = self.ensure_bank(bank_id)
        client = self._raw_client()
        try:
            result = _call_sync(client.list_memories, bank_id=bank_id, limit=limit)
        except HindsightUnavailableError:
            raise
        except Exception as exc:
            raise HindsightUnavailableError(f"Hindsight list_memories failed: {exc}") from exc
        items = []
        for i, memory in enumerate(getattr(result, "items", None) or []):
            items.append(
                {
                    "id": getattr(memory, "id", None) or f"mem_{i}",
                    "text": getattr(memory, "text", "") or str(memory),
                    "memory_type": getattr(memory, "type", "") or "",
                    "created_at": str(getattr(memory, "created_at", "") or ""),
                }
            )
        return items


def _parse_score(memory: Any) -> float:
    """Extract a float relevance score (SDK >= 0.10 nests it under scores.final)."""
    scores = getattr(memory, "scores", None)
    if scores is not None:
        for attr in ("final", "reranker", "semantic", "keyword"):
            value = getattr(scores, attr, None)
            if isinstance(value, (int, float)):
                return float(value)
    value = getattr(memory, "score", None)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _await_operations(client: Any, bank_id: str, operation_ids: list[str], timeout_s: float = 20.0) -> None:
    """Best-effort wait for retain operations to finish (bridges indexing lag).

    Never raises: if polling is unavailable or errors, retain simply returns
    without the wait (the caller degrades as it would have before).
    """
    if not operation_ids:
        return
    operations = getattr(client, "operations", None)
    if operations is None or not hasattr(operations, "get_operation_status"):
        return
    deadline = time.monotonic() + timeout_s
    pending = list(operation_ids)
    while pending and time.monotonic() < deadline:
        still_pending: list[str] = []
        for op_id in pending:
            try:
                status = _call_sync(operations.get_operation_status, bank_id=bank_id, operation_id=op_id)
                state = str(getattr(status, "status", "")).lower()
                if state == "failed":
                    logger.warning("[HINDSIGHT] retain operation %s failed: %s", op_id, getattr(status, "error_message", ""))
                elif state not in ("completed", "failed", "cancelled", "canceled"):
                    still_pending.append(op_id)
            except Exception as exc:  # noqa: BLE001 — polling is best-effort
                logger.info("[HINDSIGHT] operation poll skipped (%s)", exc)
                return
        pending = still_pending
        if pending:
            time.sleep(1.0)
    if pending:
        logger.info("[HINDSIGHT] %d retain operation(s) still processing after %.0fs", len(pending), timeout_s)


def _stringify_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    """Coerce metadata values to strings (Hindsight Cloud MemoryItem requires it)."""
    safe: dict[str, str] = {}
    for key, value in metadata.items():
        if isinstance(value, str):
            safe[key] = value
        elif isinstance(value, (list, dict)):
            safe[key] = json.dumps(value)
        else:
            safe[key] = str(value)
    return safe


def _extract_record_ids(metadata: dict[str, Any], text: str) -> list[str]:
    """Pull record ids from retained metadata, falling back to REC-#### patterns in text."""
    ids: list[str] = []
    for key in ("record_id", "record_ids", "source_record_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value:
            ids.append(value)
        elif isinstance(value, list):
            ids.extend([v for v in value if isinstance(v, str)])
    if not ids:
        import re

        ids = sorted(set(re.findall(r"REC-\d{3,4}", text)))
    return sorted(set(ids))


def get_hindsight() -> HindsightClientWrapper:
    return HindsightClientWrapper.instance()
