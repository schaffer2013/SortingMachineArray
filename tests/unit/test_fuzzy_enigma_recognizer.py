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
                requested_mode="greenfield",
                effective_mode="greenfield",
                mode_flags={"has_candidate_pool": False, "used_visual_small_pool": False},
                pipeline_summary={"resolution_path": "title_only", "branches_fired": ["title_ocr"]},
                failure_code=None,
                review_reason=None,
                debug={"mode": {"effective": "greenfield"}, "backend": {"requested": "moss_machine", "effective": "moss_machine"}},
            )

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
        ),
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
    assert result.backend == "moss_machine"
    assert result.scryfall_id == "opt-scryfall-id"
    assert result.oracle_id == "opt-oracle-id"
    assert result.requested_mode == "greenfield"
    assert result.effective_mode == "greenfield"
    assert result.mode_flags == {"has_candidate_pool": False, "used_visual_small_pool": False}
    assert result.pipeline_summary["resolution_path"] == "title_only"
    assert "title_ocr" in result.mode_features
    assert "prefer_visual_small_pool" in result.mode_features
    assert result.alternatives[0]["set_code"] == "XLN"
    assert result.debug["backend"]["effective"] == "moss_machine"
    assert result.debug["active_roi"] == "standard"


def test_fuzzy_enigma_recognizer_returns_empty_result_when_frame_has_no_image_or_card(monkeypatch, tmp_path):
    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(
            SortingMachineRecognizer=lambda **kwargs: SimpleNamespace(recognize_top_card=lambda *args, **kwargs: None)
        ),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
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
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
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
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
        ),
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
    assert result.failure_code == "missing_tracked_pool"
    assert result.review_reason == "missing_tracked_pool"
    assert result.debug["engine_error_code"] == "missing_tracked_pool"


def test_fuzzy_enigma_recognizer_uses_frame_level_recognition_request(monkeypatch, tmp_path):
    seen: dict[str, object] = {}

    class FakeRecognizer:
        def __init__(self, **kwargs):
            pass

        def recognize_top_card(self, image, **kwargs):
            seen["image"] = image
            seen["kwargs"] = kwargs
            return SimpleNamespace(
                card_name="Alpha",
                confidence=0.73,
                scryfall_id="alpha-id",
                oracle_id="alpha-oracle",
                bbox=None,
                ocr_lines=[],
                top_k_candidates=[],
                active_roi=None,
                tried_rois=[],
                requested_mode="confirmation",
                effective_mode="confirmation",
                mode_flags={"has_expected_card": True, "used_visual_small_pool": False},
                pipeline_summary={"resolution_path": "title_only", "branches_fired": ["title_ocr", "confirmation_scoring"]},
                failure_code=None,
                review_reason=None,
                debug={"mode": {"requested": "confirmation", "effective": "confirmation", "has_expected_card": True}},
            )

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: {"expected": kwargs},
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path, mode="greenfield")
    frame = Frame(
        frame_id="frame-5",
        path=str(tmp_path / "card.jpg"),
        pile_id=PileId(x_index=0, y_index=0),
        metadata={
            "card_name": "Alpha",
            "recognition_request": {
                "mode": "confirmation",
                "expected_card": {
                    "scryfall_id": "alpha-printing-id",
                    "oracle_id": "alpha-oracle-id",
                    "name": "Alpha",
                    "set_code": "lea",
                    "collector_number": "1",
                },
                "use_tracked_pool": False,
                "track_result": True,
                "prefer_visual_small_pool": True,
            },
        },
    )

    result = adapter.recognize_top_card(frame)

    assert seen["image"] == str(tmp_path / "card.jpg")
    assert seen["kwargs"]["mode"] == "confirmation"
    assert seen["kwargs"]["expected_card"] == {
        "expected": {
            "scryfall_id": "alpha-printing-id",
            "oracle_id": "alpha-oracle-id",
            "name": "Alpha",
            "set_code": "lea",
            "collector_number": "1",
        }
    }
    assert seen["kwargs"]["use_tracked_pool"] is False
    assert seen["kwargs"]["track_result"] is True
    assert seen["kwargs"]["prefer_visual_small_pool"] is True
    assert result.requested_mode == "confirmation"
    assert result.effective_mode == "confirmation"
    assert result.mode_flags["has_expected_card"] is True
    assert result.pipeline_summary["resolution_path"] == "title_only"
    assert "has_expected_card" in result.mode_features


def test_fuzzy_enigma_recognizer_uses_progress_object_update_from_request(monkeypatch, tmp_path):
    seen: dict[str, object] = {}
    updates: list[str] = []

    class ProgressSink:
        def update(self, message: str) -> None:
            updates.append(message)

    class FakeSession:
        def recognize(self, image, **kwargs):
            seen["image"] = image
            seen["kwargs"] = kwargs
            progress_callback = kwargs.get("progress_callback")
            if progress_callback is not None:
                progress_callback("Preparing recognition...")
            return SimpleNamespace(
                best_name="Alpha",
                confidence=0.73,
                bbox=None,
                ocr_lines=[],
                top_k_candidates=[
                    SimpleNamespace(
                        name="Alpha",
                        score=0.73,
                        scryfall_id="alpha-id",
                        oracle_id="alpha-oracle",
                        set_code="LEA",
                        collector_number="1",
                    )
                ],
                active_roi=None,
                tried_rois=[],
                requested_mode="greenfield",
                effective_mode="greenfield",
                mode_flags={"has_candidate_pool": False},
                pipeline_summary={"resolution_path": "title_only", "branches_fired": ["title_ocr"]},
                failure_code=None,
                review_reason=None,
                debug={"backend": {"requested": "fuzzy_enigma", "effective": "fuzzy_enigma"}},
            )

    class FakeRecognizer:
        def __init__(self, **kwargs):
            self.session = FakeSession()

    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: {"path": path}),
        sortingmachine=SimpleNamespace(SortingMachineRecognizer=FakeRecognizer),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: {"expected": kwargs},
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path, mode="greenfield")
    frame = Frame(
        frame_id="frame-progress",
        path=str(tmp_path / "card.jpg"),
        pile_id=PileId(x_index=0, y_index=0),
        metadata={
            "recognition_request": {
                "progress_callback": ProgressSink(),
            },
        },
    )

    result = adapter.recognize_top_card(frame)

    assert seen["image"] == str(tmp_path / "card.jpg")
    assert callable(seen["kwargs"]["progress_callback"])
    assert updates == ["Preparing recognition..."]
    assert result.card_name == "Alpha"
    assert result.scryfall_id == "alpha-id"
    assert result.oracle_id == "alpha-oracle"


def test_fuzzy_enigma_recognizer_reports_configured_card_engine_backend(monkeypatch, tmp_path):
    fake_config = SimpleNamespace(recognition_backend="moss_machine", recognition_backend_fallback=False)
    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: fake_config),
        sortingmachine=SimpleNamespace(
            SortingMachineRecognizer=lambda **kwargs: SimpleNamespace(recognize_top_card=lambda *args, **kwargs: None)
        ),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(project_root=tmp_path, mode="greenfield")

    assert adapter.sorter_backend == "fuzzy_enigma"
    assert adapter.card_engine_requested_backend == "moss_machine"
    assert adapter.card_engine_backend_fallback is False
    assert adapter.card_engine_mode == "greenfield"


def test_fuzzy_enigma_recognizer_can_force_card_engine_backend_override(monkeypatch, tmp_path):
    fake_config = SimpleNamespace(recognition_backend="fuzzy_enigma", recognition_backend_fallback=True)
    fake_modules = SimpleNamespace(
        config=SimpleNamespace(load_engine_config=lambda path=None: fake_config),
        sortingmachine=SimpleNamespace(
            SortingMachineRecognizer=lambda **kwargs: SimpleNamespace(recognize_top_card=lambda *args, **kwargs: None)
        ),
        operational_modes=SimpleNamespace(
            expected_card_from_values=lambda **kwargs: dict(kwargs),
        ),
    )
    monkeypatch.setattr(
        "sorter.adapters.recognition.fuzzy_enigma_recognizer._load_card_engine_modules",
        lambda project_root: fake_modules,
    )
    monkeypatch.setattr("sorter.adapters.recognition.fuzzy_enigma_recognizer._card_engine_ocr_available", lambda: True)

    adapter = FuzzyEnigmaRecognizerAdapter(
        project_root=tmp_path,
        mode="greenfield",
        card_engine_backend="moss_machine",
    )

    assert adapter.sorter_backend == "moss_machine"
    assert adapter.card_engine_requested_backend == "moss_machine"
    assert fake_config.recognition_backend == "moss_machine"
