from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from sorter.adapters.recognition.fuzzy_enigma_recognizer import FuzzyEnigmaRecognizerAdapter
from sorter.domain.models import PileId
from sorter.ports.camera import Frame


def test_fuzzy_enigma_recognizer_uses_frame_path_and_translates_result(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    class FakeRecognizer:
        def __init__(self, *, config=None, auto_track_results=False):
            seen["config"] = config
            seen["auto_track_results"] = auto_track_results

        def recognize_top_card(self, image, **kwargs):
            seen["image"] = image
            seen["kwargs"] = kwargs
            return SimpleNamespace(
                card_name="Opt",
                confidence=0.88,
                scryfall_id="opt-scryfall-id",
                oracle_id="opt-oracle-id",
                bbox=(1, 2, 3, 4),
                ocr_lines=["Opt"],
                top_k_candidates=[
                    SimpleNamespace(
                        name="Opt",
                        score=0.88,
                        scryfall_id="opt-scryfall-id",
                        oracle_id="opt-oracle-id",
                        set_code="XLN",
                        collector_number="65",
                    )
                ],
                active_roi="standard",
                tried_rois=["standard", "set_symbol"],
                debug={"mode": {"effective": "greenfield"}},
            )

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(
        project_root=tmp_path,
        config_path=tmp_path / "engine.json",
        mode="greenfield",
        auto_track_results=True,
        prefer_visual_small_pool=True,
    )
    frame = Frame(
        frame_id="frame-1",
        path=str(tmp_path / "card.jpg"),
        pile_id=PileId(x_index=0, y_index=0),
        metadata={"mode": "sim"},
    )

    result = adapter.recognize_top_card(frame)

    assert seen["config"] == {"path": str(tmp_path / "engine.json")}
    assert seen["auto_track_results"] is True
    assert seen["image"] == str(tmp_path / "card.jpg")
    assert seen["kwargs"]["mode"] == "greenfield"
    assert seen["kwargs"]["detailed"] is True
    assert seen["kwargs"]["prefer_visual_small_pool"] is True
    assert result.card_name == "Opt"
    assert result.confidence == 0.88
    assert result.backend == "fuzzy_enigma"
    assert result.scryfall_id == "opt-scryfall-id"
    assert result.oracle_id == "opt-oracle-id"
    assert result.requested_mode == "greenfield"
    assert result.effective_mode == "greenfield"
    assert result.mode_features == ("prefer_visual_small_pool",)
    assert result.alternatives[0]["set_code"] == "XLN"
    assert result.debug["active_roi"] == "standard"


def test_fuzzy_enigma_recognizer_returns_empty_result_when_frame_has_no_image_or_card(monkeypatch, tmp_path):
    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(
            SortingMachineRecognizer=lambda **kwargs: SimpleNamespace(recognize_top_card=lambda *args, **kwargs: None)
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path)
    frame = Frame(frame_id="frame-2", path=None, pile_id=None, metadata={"mode": "sim"})

    result = adapter.recognize_top_card(frame)

    assert result.card_name is None
    assert result.confidence == 1.0
    assert result.requested_mode == "greenfield"
    assert result.effective_mode == "greenfield"


def test_fuzzy_enigma_recognizer_requires_image_path_for_non_empty_card(monkeypatch, tmp_path):
    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(
            SortingMachineRecognizer=lambda **kwargs: SimpleNamespace(recognize_top_card=lambda *args, **kwargs: None)
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=Path(tmp_path))
    frame = Frame(
        frame_id="frame-3",
        path=None,
        pile_id=PileId(x_index=0, y_index=0),
        metadata={"card_name": "Opt", "mode": "sim"},
    )

    try:
        adapter.recognize_top_card(frame)
    except RuntimeError as exc:
        assert "requires a frame image path" in str(exc)
    else:
        raise AssertionError("Expected missing frame path to raise for non-empty recognition")


def test_fuzzy_enigma_recognizer_requires_ocr_backend(monkeypatch, tmp_path):
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: False)

    try:
        FuzzyEnigmaRecognizerAdapter(project_root=tmp_path)
    except RuntimeError as exc:
        assert "requires an OCR backend" in str(exc)
    else:
        raise AssertionError("Expected missing OCR backend to raise")


def test_fuzzy_enigma_recognizer_returns_review_result_when_small_pool_has_no_tracked_pool(monkeypatch, tmp_path):
    class FakeRecognizer:
        def __init__(self, **kwargs):
            pass

        def recognize_top_card(self, image, **kwargs):
            raise ValueError("No tracked pool is available for constrained recognition.")

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path, mode="small_pool")
    frame = Frame(
        frame_id="frame-4",
        path=str(tmp_path / "card.jpg"),
        pile_id=PileId(x_index=0, y_index=0),
        metadata={"card_name": "Opt"},
    )

    result = adapter.recognize_top_card(frame)

    assert result.card_name is None
    assert result.needs_review is True
    assert result.requested_mode == "small_pool"
    assert result.debug["engine_error_code"] == "missing_tracked_pool"
