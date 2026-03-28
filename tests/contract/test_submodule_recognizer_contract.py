from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import SimpleNamespace

from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult as ParentRecognitionResult


def _import_vendored_sortingmachine(monkeypatch):
    repo_root = Path(__file__).resolve().parents[2]
    submodule_src = repo_root / "third_party" / "fuzzy-enigma-card-recognition" / "src"
    assert submodule_src.exists()

    monkeypatch.syspath_prepend(str(submodule_src))
    importlib.invalidate_caches()

    for module_name in list(sys.modules):
        if module_name == "card_engine" or module_name.startswith("card_engine."):
            sys.modules.pop(module_name)

    return importlib.import_module("card_engine.adapters.sortingmachine")


def test_parent_can_call_vendored_submodule_recognizer(monkeypatch):
    sortingmachine = _import_vendored_sortingmachine(monkeypatch)
    seen: dict[str, object] = {}

    class FakeSession:
        def __init__(self, *, config=None, auto_track_results=False):
            seen["config"] = config
            seen["auto_track_results"] = auto_track_results

        def recognize(self, frame, **kwargs):
            seen["frame"] = frame
            seen["kwargs"] = kwargs
            return SimpleNamespace(
                best_name="Opt",
                confidence=0.97,
                bbox=(1, 2, 3, 4),
                ocr_lines=["Opt"],
                top_k_candidates=[
                    SimpleNamespace(
                        name="Opt",
                        score=0.97,
                        scryfall_id="opt-scryfall-id",
                        oracle_id="opt-oracle-id",
                        set_code="XLN",
                        collector_number="65",
                    )
                ],
                active_roi="standard",
                tried_rois=["standard"],
                debug={"mode": {"effective": "greenfield"}},
            )

    monkeypatch.setattr(sortingmachine, "RecognitionSession", FakeSession)

    recognizer = sortingmachine.SortingMachineRecognizer(auto_track_results=True)
    frame = Frame(
        frame_id="frame-1",
        path="C:/tmp/frame-1.jpg",
        pile_id=PileId(x_index=0, y_index=0),
        metadata={"source": "parent-test"},
    )

    output = recognizer.recognize_top_card(frame, mode="greenfield", detailed=True)

    assert seen["frame"] is frame
    assert seen["auto_track_results"] is True
    assert seen["kwargs"]["mode"] == "greenfield"
    assert output.card_name == "Opt"
    assert output.confidence == 0.97
    assert output.scryfall_id == "opt-scryfall-id"
    assert output.oracle_id == "opt-oracle-id"
    assert output.active_roi == "standard"
    assert output.top_k_candidates[0].set_code == "XLN"

    parent_result = ParentRecognitionResult(card_name=output.card_name, confidence=output.confidence)
    assert parent_result.card_name == "Opt"
    assert parent_result.confidence == 0.97
