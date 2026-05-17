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
                requested_mode="greenfield",
                effective_mode="greenfield",
                mode_flags={"has_candidate_pool": False},
                pipeline_summary={"resolution_path": "title_only", "branches_fired": ["title_ocr"]},
                failure_code=None,
                review_reason=None,
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
    assert output.requested_mode == "greenfield"
    assert output.effective_mode == "greenfield"
    assert output.mode_flags == {"has_candidate_pool": False}
    assert output.pipeline_summary["resolution_path"] == "title_only"
    assert output.top_k_candidates[0].set_code == "XLN"

    parent_result = ParentRecognitionResult(card_name=output.card_name, confidence=output.confidence)
    assert parent_result.card_name == "Opt"
    assert parent_result.confidence == 0.97


def test_vendored_submodule_can_route_to_moss_backend(monkeypatch, tmp_path):
    sortingmachine = _import_vendored_sortingmachine(monkeypatch)
    config_module = importlib.import_module("card_engine.config")
    api_module = importlib.import_module("card_engine.api")
    session_module = importlib.import_module("card_engine.session")

    image_path = tmp_path / "frame-1.jpg"
    image_path.write_bytes(b"fixture")
    seen: dict[str, object] = {}

    def fake_run_moss_backend(
        image,
        *,
        mode=None,
        candidate_pool=None,
        expected_card=None,
        unsupported_reason=None,
        progress_callback=None,
        config=None,
    ):
        seen["image"] = image
        seen["mode"] = mode
        seen["candidate_pool"] = candidate_pool
        seen["expected_card"] = expected_card
        seen["unsupported_reason"] = unsupported_reason
        seen["config"] = config
        return SimpleNamespace(
            bbox=None,
            best_name="Opt",
            confidence=0.98,
            ocr_lines=[],
            top_k_candidates=[
                SimpleNamespace(
                    name="Opt",
                    score=0.98,
                    scryfall_id=None,
                    oracle_id=None,
                    set_code="INV",
                    collector_number="64",
                )
            ],
            active_roi="moss_machine",
            tried_rois=["moss_machine"],
            requested_mode="greenfield",
            effective_mode="greenfield",
            mode_flags={},
            pipeline_summary={"resolution_path": "moss_machine"},
            failure_code=None,
            review_reason=None,
            debug={"backend": {"requested": "moss_machine", "effective": "moss_machine"}},
        )

    monkeypatch.setattr(api_module, "run_moss_backend", fake_run_moss_backend)
    monkeypatch.setattr(
        api_module,
        "_recognize_card_with_fuzzy_enigma",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("fuzzy backend should not be used")),
    )
    monkeypatch.setattr(session_module, "ensure_catalog_ready", lambda db_path: None)
    monkeypatch.setattr(
        session_module,
        "LocalCatalogIndex",
        SimpleNamespace(from_sqlite=lambda db_path: (_ for _ in ()).throw(AssertionError("catalog should not load for moss"))),
    )

    config = config_module.EngineConfig(recognition_backend="moss_machine")
    recognizer = sortingmachine.SortingMachineRecognizer(config=config)

    output = recognizer.recognize_top_card(str(image_path), mode="greenfield", detailed=True)

    assert output.card_name == "Opt"
    assert output.active_roi == "moss_machine"
    assert seen["image"] == str(image_path)
    assert seen["mode"] == "greenfield"
    assert seen["candidate_pool"] is None
    assert seen["expected_card"] is None
    assert seen["unsupported_reason"] is None
    assert seen["config"] is config
