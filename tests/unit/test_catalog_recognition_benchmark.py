from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from sorter.application.catalog_recognition_benchmark import (
    CatalogRecognitionBenchmarkManager,
    choose_benchmark_cards,
    eligible_catalog_cards,
)


def _write_catalog(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "id": "alpha",
                    "name": "Alpha Spell",
                    "set": "tst",
                    "collector_number": "1",
                    "type_line": "Instant",
                    "digital": False,
                    "image_uris": {"normal": "https://cards.scryfall.io/normal/alpha.jpg"},
                },
                {
                    "id": "beta",
                    "name": "Beta Dual",
                    "set": "tst",
                    "collector_number": "2",
                    "type_line": "Land",
                    "digital": False,
                    "image_uris": {"normal": "https://cards.scryfall.io/normal/beta.jpg"},
                },
                {
                    "id": "digital",
                    "name": "Digital Only",
                    "type_line": "Creature",
                    "digital": True,
                    "image_uris": {"normal": "https://cards.scryfall.io/normal/digital.jpg"},
                },
                {
                    "id": "basic",
                    "name": "Forest",
                    "type_line": "Basic Land — Forest",
                    "digital": False,
                    "image_uris": {"normal": "https://cards.scryfall.io/normal/forest.jpg"},
                },
                {
                    "id": "snow-basic",
                    "name": "Snow-Covered Island",
                    "type_line": "Basic Snow Land — Island",
                    "digital": False,
                    "image_uris": {"normal": "https://cards.scryfall.io/normal/island.jpg"},
                },
                {
                    "id": "no-image",
                    "name": "Missing Image",
                    "type_line": "Sorcery",
                    "digital": False,
                },
            ]
        ),
        encoding="utf-8",
    )


def _wait_for_completion(manager: CatalogRecognitionBenchmarkManager) -> dict:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = manager.status()
        if not status["running"]:
            return status
        time.sleep(0.01)
    raise AssertionError("Benchmark did not finish")


def test_catalog_selection_excludes_digital_basic_lands_and_missing_images(tmp_path):
    catalog_path = tmp_path / "cards.json"
    _write_catalog(catalog_path)

    eligible = eligible_catalog_cards(catalog_path)
    selected, eligible_count = choose_benchmark_cards(catalog_path, sample_size=2, seed=42)

    assert {card["name"] for card in eligible} == {"Alpha Spell", "Beta Dual"}
    assert {card["name"] for card in selected} == {"Alpha Spell", "Beta Dual"}
    assert eligible_count == 2


def test_catalog_benchmark_reuses_each_download_across_backends_and_persists_results(tmp_path):
    catalog_path = tmp_path / "cards.json"
    state_path = tmp_path / "benchmark.json"
    _write_catalog(catalog_path)
    downloads: list[str] = []
    temp_paths: list[Path] = []

    def download(url: str) -> bytes:
        downloads.append(url)
        return ("Alpha Spell" if "alpha" in url else "Beta Dual").encode()

    def recognize(image_path: Path, payload: dict) -> dict:
        temp_paths.append(image_path)
        card_name = image_path.read_bytes().decode()
        return {
            "card_name": card_name,
            "scryfall_id": "alpha" if card_name == "Alpha Spell" else "beta",
            "confidence": 0.9,
            "backend": payload["backend"],
        }

    manager = CatalogRecognitionBenchmarkManager(
        source_path=catalog_path,
        state_path=state_path,
        recognize_image=recognize,
        download_image=download,
    )
    started = manager.start(
        sample_size=2,
        backends=["fuzzy_enigma", "visual_retrieval"],
        seed=7,
    )
    finished = _wait_for_completion(manager)

    assert started["running"] is True
    assert finished["status"] == "completed"
    assert finished["progress_current"] == 4
    assert len(downloads) == 2
    assert len(temp_paths) == 4
    assert all(not path.exists() for path in temp_paths)
    assert finished["backend_results"]["fuzzy_enigma"]["accuracy"] == 1.0
    assert finished["backend_results"]["fuzzy_enigma"]["printing_accuracy"] == 1.0
    assert finished["backend_results"]["visual_retrieval"]["accuracy"] == 1.0
    assert len(finished["cases"]) == 4
    assert CatalogRecognitionBenchmarkManager(
        source_path=catalog_path,
        state_path=state_path,
        recognize_image=recognize,
        download_image=download,
    ).status()["status"] == "completed"


def test_catalog_benchmark_validates_sample_size_and_backends(tmp_path):
    catalog_path = tmp_path / "cards.json"
    _write_catalog(catalog_path)
    manager = CatalogRecognitionBenchmarkManager(
        source_path=catalog_path,
        state_path=tmp_path / "benchmark.json",
        recognize_image=lambda _path, _payload: {},
        download_image=lambda _url: b"",
    )

    with pytest.raises(ValueError, match="between 1 and 500"):
        manager.start(sample_size=501, backends=["fuzzy_enigma"])
    with pytest.raises(ValueError, match="Unsupported benchmark backend"):
        manager.start(sample_size=1, backends=["sim_truth"])
