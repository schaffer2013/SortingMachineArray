from __future__ import annotations

import json
from pathlib import Path

from sorter.adapters.integrations.collection_service import HttpCollectionServiceAdapter


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_collection_service_status_includes_health_collections_and_summary(monkeypatch):
    calls: list[str] = []

    def fake_urlopen(request, timeout):
        calls.append(request.full_url)
        if request.full_url.endswith("/health"):
            return _Response({"status": "ok"})
        if request.full_url.endswith("/collections"):
            return _Response([{"collection_id": "collection-1", "name": "Main"}])
        return _Response(
            {
                "collection_id": "collection-1",
                "unprocessed_count": 2,
                "machine_recognized_count": 3,
                "trusted_collection_card_count": 7,
            }
        )

    monkeypatch.setattr("sorter.adapters.integrations.collection_service.urlopen", fake_urlopen)
    adapter = HttpCollectionServiceAdapter(
        base_url="http://localhost:8080/",
        collection_id="collection-1",
    )

    status = adapter.system_status()

    assert status["available"] is True
    assert status["summary"]["machine_recognized_count"] == 3
    assert status["ui_url"] == "http://localhost:8080/ui/collections"
    assert status["review_url"].endswith("/ui/collections/collection-1/queue")
    assert calls == [
        "http://localhost:8080/health",
        "http://localhost:8080/collections",
        "http://localhost:8080/collections/collection-1/summary",
    ]


def test_submit_unverified_card_uses_current_multipart_contract(monkeypatch, tmp_path: Path):
    captured = {}
    image_path = tmp_path / "card.png"
    image_path.write_bytes(b"png-image")

    def fake_urlopen(request, timeout):
        captured["request"] = request
        return _Response({"unverified_card_id": "card-1"})

    monkeypatch.setattr("sorter.adapters.integrations.collection_service.urlopen", fake_urlopen)
    adapter = HttpCollectionServiceAdapter(
        base_url="http://localhost:8080",
        collection_id="collection-1",
    )

    adapter.submit_unverified_card(
        run_id="run-1",
        sequence=4,
        payload={
            "raw_image_path": str(image_path),
            "sorter_expected_scryfall_id": "printing-1",
            "bounding_box": [[1, 2], [3, 4], [5, 6], [7, 8]],
        },
    )

    request = captured["request"]
    assert request.full_url.endswith("/collections/collection-1/unverified-cards")
    assert request.method == "POST"
    assert request.headers["Content-type"].startswith("multipart/form-data; boundary=")
    assert b'name="raw_image"; filename="card.png"' in request.data
    assert b'name="sorter_expected_scryfall_id"' in request.data
    assert b"printing-1" in request.data
    assert b"png-image" in request.data
