from __future__ import annotations

from dataclasses import asdict
from typing import Any

from sorter.ports.collection_service import CollectionEvent, CollectionRunRef, CollectionServicePort


class NullCollectionServiceAdapter(CollectionServicePort):
    """No-op adapter used when collection API integration is not configured."""

    def create_or_get_run(self, *, run_id: str, metadata: dict[str, Any]) -> CollectionRunRef:
        return CollectionRunRef(collection_id="unconfigured", external_run_id=run_id)

    def record_event(self, event: CollectionEvent) -> None:
        return None

    def submit_unverified_card(self, *, run_id: str, sequence: int, payload: dict[str, Any]) -> None:
        return None

    def finalize_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> None:
        return None


class HttpCollectionServiceAdapter(CollectionServicePort):
    """Scaffold HTTP adapter for magic-the-collecting API integration.

    This class intentionally documents call-shapes and payloads without enforcing
    a specific endpoint map yet.
    """

    def __init__(self, *, base_url: str, api_key: str | None = None, timeout_seconds: float = 5.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def create_or_get_run(self, *, run_id: str, metadata: dict[str, Any]) -> CollectionRunRef:
        _ = {
            "run_id": run_id,
            "metadata": metadata,
        }
        raise NotImplementedError("Wire to collection run registration endpoint.")

    def record_event(self, event: CollectionEvent) -> None:
        _ = asdict(event)
        raise NotImplementedError("Wire to collection event ingestion endpoint.")

    def submit_unverified_card(self, *, run_id: str, sequence: int, payload: dict[str, Any]) -> None:
        _ = {
            "run_id": run_id,
            "sequence": sequence,
            "payload": payload,
        }
        raise NotImplementedError("Wire to unverified-card/review endpoint.")

    def finalize_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> None:
        _ = {
            "run_id": run_id,
            "status": status,
            "summary": summary,
        }
        raise NotImplementedError("Wire to run-finalization endpoint.")
