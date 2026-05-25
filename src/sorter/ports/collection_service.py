from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class CollectionRunRef:
    collection_id: str
    external_run_id: str


@dataclass(frozen=True)
class CollectionEvent:
    run_id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]


class CollectionServicePort(Protocol):
    """Port for collection/registration API integration.

    This is intentionally narrow and machine-oriented so the sorter can emit
    lifecycle and recognition events without coupling to HTTP details.
    """

    def create_or_get_run(self, *, run_id: str, metadata: dict[str, Any]) -> CollectionRunRef: ...

    def record_event(self, event: CollectionEvent) -> None: ...

    def submit_unverified_card(self, *, run_id: str, sequence: int, payload: dict[str, Any]) -> None: ...

    def finalize_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> None: ...
