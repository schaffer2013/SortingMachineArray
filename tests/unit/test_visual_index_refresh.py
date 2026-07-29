from __future__ import annotations

import json
import sqlite3
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
    reference_dir.mkdir(parents=True, exist_ok=True)
    _write_png(reference_dir / "stale.png", (12, 34, 56))

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
    assert not (project_root / "data/index/visual_index_checkpoint.sqlite3").exists()
    assert len(metadata_path.read_text(encoding="utf-8").splitlines()) == 2
    assert reference_dir.is_dir()
    assert not any(reference_dir.iterdir())
    assert progress_calls[0] == (0, 2, "Parsing catalog and preparing 2 cards")
    assert any("Downloading card" in (message or "") for _, _, message in progress_calls)
    assert any("Embedding card" in (message or "") for _, _, message in progress_calls)
    assert any("Saving checkpoint for" in (message or "") for _, _, message in progress_calls)
    assert any("Cleaning up reference images" in (message or "") for _, _, message in progress_calls)
    assert any("Finalizing cards index" in (message or "") for _, _, message in progress_calls)
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
    assert not (project_root / "data/index/visual_index_checkpoint.sqlite3").exists()


def test_build_visual_index_from_catalog_recovers_corrupted_cached_reference_image(tmp_path, monkeypatch):
    project_root = tmp_path
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text(
        json.dumps(
            [
                {
                    "name": "Gamma",
                    "id": "cccccccc-0000-0000-0000-000000000003",
                    "set": "gma",
                    "collector_number": "3",
                    "image_uris": {"png": "https://example.invalid/gamma.png"},
                }
            ],
            indent=2,
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"
    reference_dir.mkdir(parents=True, exist_ok=True)

    card = json.loads(source_catalog.read_text(encoding="utf-8"))[0]
    reference_path = reference_dir / refresh_module._reference_file_name(card, "https://example.invalid/gamma.png")
    reference_path.write_text("not an image", encoding="utf-8")

    class FakeEmbedder:
        def embed(self, image):
            return np.array([float(image.mean())], dtype=np.float32)

    monkeypatch.setattr(refresh_module, "create_embedder", lambda model, model_path: FakeEmbedder())

    download_calls: list[str] = []

    def fake_download(image_url: str, output_path: Path) -> None:
        download_calls.append(image_url)
        _write_png(output_path, (128, 64, 32))

    monkeypatch.setattr(refresh_module, "_download", fake_download)

    result = refresh_module.build_visual_index_from_catalog(
        project_root=project_root,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
        overwrite_downloads=False,
    )

    assert result.card_count == 1
    assert result.downloaded_count == 1
    assert download_calls == ["https://example.invalid/gamma.png"]
    assert not reference_path.exists()
    assert reference_dir.is_dir()
    assert not any(reference_dir.iterdir())


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


def test_build_visual_index_from_catalog_leaves_checkpoint_when_interrupted(tmp_path, monkeypatch):
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

    class FlakyEmbedder:
        def __init__(self):
            self.calls = 0

        def embed(self, image):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("sync interrupted")
            return np.array([float(image.mean())], dtype=np.float32)

    monkeypatch.setattr(refresh_module, "create_embedder", lambda model, model_path: FlakyEmbedder())

    def fake_download(image_url: str, output_path: Path) -> None:
        _write_png(output_path, (255, 0, 0) if "alpha" in image_url else (0, 0, 255))

    monkeypatch.setattr(refresh_module, "_download", fake_download)

    with pytest.raises(RuntimeError, match="sync interrupted"):
        refresh_module.build_visual_index_from_catalog(
            project_root=project_root,
            source_catalog_path=source_catalog,
            index_path=index_path,
            metadata_path=metadata_path,
            reference_dir=reference_dir,
            overwrite_downloads=True,
        )

    checkpoint_path = project_root / "data/index/visual_index_checkpoint.sqlite3"
    assert checkpoint_path.is_file()
    with sqlite3.connect(checkpoint_path) as conn:
        assert refresh_module._checkpoint_card_count(conn) == 1
    assert not index_path.exists()
    assert not metadata_path.exists()


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
    assert reference_dir.is_dir()
    assert not any(reference_dir.iterdir())
    assert manager.status(running=False, auto_start=False)["last_error"] is None


def test_visual_index_manager_auto_start_supplies_full_rebuild_flag(tmp_path, monkeypatch):
    project_root = tmp_path
    config_path = tmp_path / "config/card_engine/engine.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    refresh_module.save_visual_index_policy(config_path, 7)
    source_catalog = tmp_path / "data/catalog/default-cards.json"
    source_catalog.parent.mkdir(parents=True, exist_ok=True)
    source_catalog.write_text("[]", encoding="utf-8")
    index_path = tmp_path / "data/index/card_embeddings.npz"
    metadata_path = tmp_path / "data/index/card_embeddings.jsonl"
    reference_dir = tmp_path / "data/index/reference_images"

    seen_kwargs: list[dict[str, object]] = []

    def fake_start_background_refresh(**kwargs):
        seen_kwargs.append(dict(kwargs))

    manager = refresh_module.VisualIndexRefreshManager(
        project_root=project_root,
        config_path=config_path,
        source_catalog_path=source_catalog,
        index_path=index_path,
        metadata_path=metadata_path,
        reference_dir=reference_dir,
    )
    monkeypatch.setattr(manager, "_start_background_refresh", fake_start_background_refresh)

    manager.status(running=False, auto_start=True)

    assert seen_kwargs == [{"force": False, "reason": "missing", "full_rebuild": False}]


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
            progress_callback(0, 2, "Parsing catalog and preparing 2 cards")
            progress_callback(0, 2, "Downloading card 1/2: Alpha")
            progress_callback(0, 2, "Embedding card 1/2: Alpha")
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

    assert [call["progress_phase"] for call in progress_calls[:3]] == [
        "Warming up",
        "Warming up",
        "Warming up",
    ]
    assert any(call["progress_phase"] == "Actively indexing" for call in progress_calls)
    assert any(call["progress_stage"] == "Actively indexing" for call in progress_calls)
    assert progress_calls[-1]["progress_current"] == 1
    assert progress_calls[-1]["progress_phase"] == "Complete"
