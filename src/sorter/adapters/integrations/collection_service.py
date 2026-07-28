from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import uuid

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
    """HTTP adapter for the vendored magic-the-collecting service."""

    def __init__(
        self,
        *,
        base_url: str,
        collection_id: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 2.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.collection_id = collection_id.strip() if collection_id else None
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def create_or_get_run(self, *, run_id: str, metadata: dict[str, Any]) -> CollectionRunRef:
        # The current collection contract intentionally has no run resource.
        _ = metadata
        return CollectionRunRef(collection_id=self.collection_id or "unconfigured", external_run_id=run_id)

    def record_event(self, event: CollectionEvent) -> None:
        # The current collection contract accepts card evidence, not sorter
        # lifecycle events. Keep this compatibility hook intentionally inert.
        _ = asdict(event)

    def submit_unverified_card(self, *, run_id: str, sequence: int, payload: dict[str, Any]) -> None:
        _ = (run_id, sequence)
        collection_id = str(payload.get("collection_id") or self.collection_id or "").strip()
        if not collection_id:
            raise ValueError("A collection_id is required to submit card evidence")
        image_path = Path(str(payload.get("raw_image_path") or payload.get("image_path") or ""))
        if not image_path.is_file():
            raise ValueError(f"Raw card image does not exist: {image_path}")
        fields: dict[str, str] = {}
        expected_id = payload.get("sorter_expected_scryfall_id") or payload.get("expected_scryfall_id")
        if expected_id:
            fields["sorter_expected_scryfall_id"] = str(expected_id)
        if payload.get("bounding_box") is not None:
            fields["bounding_box"] = json.dumps(payload["bounding_box"], separators=(",", ":"))
        body, content_type = _multipart_image_body(fields, image_path)
        self._request_json(
            f"/collections/{collection_id}/unverified-cards",
            method="POST",
            body=body,
            content_type=content_type,
        )

    def finalize_run(self, *, run_id: str, status: str, summary: dict[str, Any]) -> None:
        _ = (run_id, status, summary)

    def health(self) -> dict[str, Any]:
        return self._request_json("/health")

    def collections(self) -> list[dict[str, Any]]:
        payload = self._request_json("/collections")
        return payload if isinstance(payload, list) else []

    def collection_summary(self, collection_id: str | None = None) -> dict[str, Any] | None:
        selected_id = (collection_id or self.collection_id or "").strip()
        if not selected_id:
            return None
        payload = self._request_json(f"/collections/{selected_id}/summary")
        return payload if isinstance(payload, dict) else None

    def system_status(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "configured": True,
            "base_url": self.base_url,
            "collection_id": self.collection_id,
            "ui_url": f"{self.base_url}/ui/collections",
            "review_url": (
                f"{self.base_url}/ui/collections/{self.collection_id}/queue"
                if self.collection_id
                else f"{self.base_url}/ui/recognition-queue"
            ),
        }
        try:
            health = self.health()
            collections = self.collections()
            summary = self.collection_summary()
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            return {
                **payload,
                "available": False,
                "status": "unavailable",
                "message": _http_error_message(exc),
                "collections": [],
                "summary": None,
            }
        return {
            **payload,
            "available": health.get("status") == "ok",
            "status": str(health.get("status", "unknown")),
            "message": None,
            "collections": collections,
            "summary": summary,
        }

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        body: bytes | None = None,
        content_type: str | None = None,
    ) -> Any:
        headers = {"Accept": "application/json"}
        if content_type:
            headers["Content-Type"] = content_type
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        request = Request(f"{self.base_url}{path}", data=body, headers=headers, method=method)
        with urlopen(request, timeout=self.timeout_seconds) as response:
            raw = response.read()
        return json.loads(raw.decode("utf-8")) if raw else None


def _multipart_image_body(fields: dict[str, str], image_path: Path) -> tuple[bytes, str]:
    boundary = f"----sorting-machine-{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields.items():
        chunks.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                value.encode("utf-8"),
                b"\r\n",
            ]
        )
    suffix = image_path.suffix.lower()
    media_type = {".png": "image/png", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    chunks.extend(
        [
            f"--{boundary}\r\n".encode(),
            (
                f'Content-Disposition: form-data; name="raw_image"; '
                f'filename="{image_path.name}"\r\n'
            ).encode(),
            f"Content-Type: {media_type}\r\n\r\n".encode(),
            image_path.read_bytes(),
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _http_error_message(exc: BaseException) -> str:
    if isinstance(exc, HTTPError):
        try:
            payload = json.loads(exc.read().decode("utf-8"))
            return str(payload.get("error", {}).get("message") or exc.reason)
        except Exception:
            return str(exc.reason)
    return str(exc)
