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
            return SimpleNamespace(card_name="Opt", confidence=0.88)

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )

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
    assert seen["kwargs"]["prefer_visual_small_pool"] is True
    assert result.card_name == "Opt"
    assert result.confidence == 0.88


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

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path)
    frame = Frame(frame_id="frame-2", path=None, pile_id=None, metadata={"mode": "sim"})

    result = adapter.recognize_top_card(frame)

    assert result.card_name is None
    assert result.confidence == 1.0


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
