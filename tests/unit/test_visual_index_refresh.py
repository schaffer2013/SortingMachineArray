from __future__ import annotations

import json
import time
from pathlib import Path

import cv2
import numpy as np
import pytest

from sorter.application import visual_index_refresh as refresh_module


def _write_png(path: Path, color: tuple[int, int, int] = (0, 255, 0)) -> None:
    image = np.zeros((24, 24, 3), dtype=np.uint8)
    image[:] = color
    if not cv2.imwrite(str(path), image):  # pragma: no cover - cv2.imwrite returns a bool
        raise RuntimeError(f"Unable to write test image to {path}")


def test_visual_index_policy_round_trip(tmp_path):
    config_path = tmp_path / "engine.json"
    config_path.write_text(json.dumps({"recognition_backend": "visual_retrieval"}, indent=2), encoding="utf-8")

    assert refresh_module.load_visual_index_policy(config_path) == 7

    refresh_module.save_visual_index_policy(config_path, 30)
    payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert payload["recognition_backend"] == "visual_retrieval"
    assert payload["visual_index_refresh_days"] == 30
    assert refresh_module.load_visual_index_policy(config_path) == 30


def test_build_visual_index_from_catalog_uses_project_root_and_builds_index(tmp_path, monkeypatch):
    project_root = tmp_path
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Alpha",
                    "id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "set": "alp",
                    "collector_number": "1",
                    "image_uris": {"png": "https://example.invalid/alpha.png"},
                },
                {
                    "name": "Beta",
                    "id": "bbbbbbbb-0000-0000-0000-000000000002",
                    "set": "bet",
                    "collector_number": "2",
                    "image_uris": {"png": "https://example.invalid/beta.png"},
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"

    progress_calls: list[tuple[int, int, str | None]] = []

    def fake_download(image_url: str, output_path: Path) -> None:
        _write_png(output_path, (255, 0, 0) if "alpha" in image_url else (0, 0, 255))

    monkeypatch.setattr(refresh_module, "_download", fake_download)

    result = refresh_module.build_visual_index_from_catalog(
        project_root=project_root,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
        overwrite_downloads=True,
        progress_callback=lambda current, total, message=None: progress_calls.append((current, total, message)),
    )

    assert result.card_count == 2
    assert result.index_path == index_path
    assert result.metadata_path == metadata_path
    assert index_path.is_file()
    assert metadata_path.is_file()
    assert len(metadata_path.read_text(encoding="utf-8").splitlines()) == 2
    assert (project_root / "data/index/reference_images").is_dir()
    assert progress_calls[0] == (0, 2, "Preparing 2 cards")
    assert progress_calls[-1][0] == 2
    assert progress_calls[-1][1] == 2


def test_refresh_visual_index_from_catalog_appends_new_cards(tmp_path, monkeypatch):
    project_root = tmp_path
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Alpha",
                    "id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "set": "alp",
                    "collector_number": "1",
                    "image_uris": {"png": "https://example.invalid/alpha.png"},
                },
                {
                    "name": "Beta",
                    "id": "bbbbbbbb-0000-0000-0000-000000000002",
                    "set": "bet",
                    "collector_number": "2",
                    "image_uris": {"png": "https://example.invalid/beta.png"},
                },
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"
    reference_dir.mkdir(parents=True, exist_ok=True)

    existing_index = refresh_module.VisualIndex(
        np.array([[1.0]], dtype=np.float32),
        [
            {
                "name": "Alpha",
                "scryfall_id": "aaaaaaaa-0000-0000-0000-000000000001",
                "oracle_id": "oracle-alpha",
                "set_code": "alp",
                "collector_number": "1",
                "image_url": "https://example.invalid/alpha.png",
                "image_path": "data/index/reference_images/alpha.png",
                "crop_type": "full_card",
            }
        ],
    )
    existing_index.save(index_path, metadata_path)

    class FakeEmbedder:
        def embed(self, image):
            return np.array([float(image.mean())], dtype=np.float32)

    monkeypatch.setattr(refresh_module, "create_embedder", lambda model, model_path: FakeEmbedder())

    def fake_download(image_url: str, output_path: Path) -> None:
        _write_png(output_path, (255, 0, 0) if "alpha" in image_url else (0, 0, 255))

    monkeypatch.setattr(refresh_module, "_download", fake_download)

    result = refresh_module.refresh_visual_index_from_catalog(
        project_root=project_root,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
        overwrite_downloads=False,
    )

    loaded = refresh_module.VisualIndex.load(index_path, metadata_path)
    assert result.card_count == 2
    assert result.downloaded_count == 1
    assert len(loaded.metadata) == 2
    assert [item["name"] for item in loaded.metadata] == ["Alpha", "Beta"]


def test_refresh_visual_index_from_catalog_requires_full_rebuild_for_removed_cards(tmp_path, monkeypatch):
    project_root = tmp_path
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Beta",
                    "id": "bbbbbbbb-0000-0000-0000-000000000002",
                    "set": "bet",
                    "collector_number": "2",
                    "image_uris": {"png": "https://example.invalid/beta.png"},
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"

    existing_index = refresh_module.VisualIndex(
        np.array([[1.0]], dtype=np.float32),
        [
            {
                "name": "Alpha",
                "scryfall_id": "aaaaaaaa-0000-0000-0000-000000000001",
                "oracle_id": "oracle-alpha",
                "set_code": "alp",
                "collector_number": "1",
                "image_url": "https://example.invalid/alpha.png",
                "image_path": "data/index/reference_images/alpha.png",
                "crop_type": "full_card",
            }
        ],
    )
    existing_index.save(index_path, metadata_path)

    with pytest.raises(refresh_module.FullVisualIndexRebuildRequired):
        refresh_module.refresh_visual_index_from_catalog(
            project_root=project_root,
            source_catalog_path=source_catalog,
            index_path=index_path,
            metadata_path=metadata_path,
            reference_dir=reference_dir,
            overwrite_downloads=False,
        )


def test_visual_index_manager_refreshes_in_background(tmp_path, monkeypatch):
    project_root = tmp_path
    config_path = tmp_path / "config/card_engine/engine.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_module.save_visual_index_policy(config_path, 7)
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Alpha",
                    "id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "set": "alp",
                    "collector_number": "1",
                    "image_uris": {"png": "https://example.invalid/alpha.png"},
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"

    def fake_build(**kwargs):
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback(1, 4, "Indexed 1/4 cards")
            time.sleep(0.1)
        kwargs["index_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["metadata_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["index_path"].write_bytes(b"npz")
        kwargs["metadata_path"].write_text("{\"name\": \"Alpha\"}\n", encoding="utf-8")
        return refresh_module.VisualIndexBuildResult(
            index_path=Path(kwargs["index_path"]),
            metadata_path=Path(kwargs["metadata_path"]),
            reference_dir=Path(kwargs["reference_dir"]),
            source_catalog_path=Path(kwargs["source_catalog_path"]),
            card_count=1,
            downloaded_count=1,
            reused_count=0,
            updated_at_utc="2026-07-29T00:00:00Z",
            refresh_days=7,
        )

    monkeypatch.setattr(refresh_module, "build_visual_index_from_catalog", fake_build)
    manager = refresh_module.VisualIndexRefreshManager(
        project_root=project_root,
        config_path=config_path,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
    )

    initial = manager.refresh(force=True)
    assert initial["ok"] is True
    assert initial["refreshing"] is True

    deadline = time.time() + 5.0
    status = initial
    while time.time() < deadline:
        status = manager.status(running=False, auto_start=False)
        if not status["refreshing"]:
            break
        time.sleep(0.05)

    assert status["ready"] is True
    assert status["progress_percent"] == 100.0
    assert status["progress_eta_text"] == "done"
    assert status["indexed_card_count"] == 1
    assert status["source_card_count"] == 1
    assert status["updated_at_utc"] == "2026-07-29T00:00:00Z"
    assert manager.status(running=False, auto_start=False)["last_error"] is None


def test_visual_index_manager_reports_every_progress_callback(tmp_path, monkeypatch):
    project_root = tmp_path
    config_path = tmp_path / "config/card_engine/engine.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_module.save_visual_index_policy(config_path, 7)
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Alpha",
                    "id": "aaaaaaaa-0000-0000-0000-000000000001",
                    "set": "alp",
                    "collector_number": "1",
                    "image_uris": {"png": "https://example.invalid/alpha.png"},
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"

    progress_calls: list[dict[str, object]] = []

    def fake_build(**kwargs):
        progress_callback = kwargs.get("progress_callback")
        if callable(progress_callback):
            progress_callback(0, 2, "Indexed 0/2 cards")
            progress_callback(1, 2, "Indexed 1/2 cards")
        kwargs["index_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["metadata_path"].parent.mkdir(parents=True, exist_ok=True)
        kwargs["index_path"].write_bytes(b"npz")
        kwargs["metadata_path"].write_text("{\"name\": \"Alpha\"}\n", encoding="utf-8")
        return refresh_module.VisualIndexBuildResult(
            index_path=Path(kwargs["index_path"]),
            metadata_path=Path(kwargs["metadata_path"]),
            reference_dir=Path(kwargs["reference_dir"]),
            source_catalog_path=Path(kwargs["source_catalog_path"]),
            card_count=1,
            downloaded_count=1,
            reused_count=0,
            updated_at_utc="2026-07-29T00:00:00Z",
            refresh_days=7,
        )

    monkeypatch.setattr(refresh_module, "build_visual_index_from_catalog", fake_build)
    manager = refresh_module.VisualIndexRefreshManager(
        project_root=project_root,
        config_path=config_path,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
    )
    original_write_state = manager._write_state

    def capture_write_state(payload):
        if isinstance(payload, dict) and payload.get("progress_current") is not None:
            progress_calls.append(dict(payload))
        return original_write_state(payload)

    monkeypatch.setattr(manager, "_write_state", capture_write_state)

    manager.refresh(force=True)

    deadline = time.time() + 5.0
    while time.time() < deadline:
        if not manager.status(running=False, auto_start=False)["refreshing"]:
            break
        time.sleep(0.05)

    assert [call["progress_current"] for call in progress_calls] == [0, 0, 1, 1]
