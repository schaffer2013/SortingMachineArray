from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
from pathlib import Path
import sys
from types import ModuleType
from typing import Any

from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


@dataclass(frozen=True)
class CardEngineModules:
    config: ModuleType
    sortingmachine: ModuleType


def _load_card_engine_modules(project_root: Path) -> CardEngineModules:
    try:
        return CardEngineModules(
            config=importlib.import_module("card_engine.config"),
            sortingmachine=importlib.import_module("card_engine.adapters.sortingmachine"),
        )
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("card_engine"):
            raise RuntimeError(
                "Fuzzy Enigma recognizer dependencies are missing. Install the vendored submodule with "
                "`pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`."
            ) from exc

    submodule_src = project_root / "third_party" / "fuzzy-enigma-card-recognition" / "src"
    if not submodule_src.exists():
        raise RuntimeError(f"Vendored card_engine source not found at {submodule_src}")

    src_str = str(submodule_src)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    importlib.invalidate_caches()

    try:
        return CardEngineModules(
            config=importlib.import_module("card_engine.config"),
            sortingmachine=importlib.import_module("card_engine.adapters.sortingmachine"),
        )
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("card_engine"):
            raise RuntimeError(
                "Fuzzy Enigma recognizer dependencies are missing after loading the vendored source. "
                "Install the vendored submodule with "
                "`pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`."
            ) from exc
        raise RuntimeError("Unable to import the vendored fuzzy-enigma-card-recognition submodule.") from exc


def _card_engine_ocr_available() -> bool:
    return (
        importlib.util.find_spec("rapidocr_onnxruntime") is not None
        or importlib.util.find_spec("paddleocr") is not None
    )


def _mode_features(raw_debug: dict[str, Any], *, prefer_visual_small_pool: bool) -> tuple[str, ...]:
    features: list[str] = []
    raw_mode = raw_debug.get("mode")
    if isinstance(raw_mode, dict):
        if raw_mode.get("has_expected_card"):
            features.append("has_expected_card")
        if raw_mode.get("has_candidate_pool"):
            features.append("has_candidate_pool")
    if prefer_visual_small_pool:
        features.append("prefer_visual_small_pool")
    visual_debug = raw_debug.get("small_pool_visual")
    if isinstance(visual_debug, dict) and visual_debug:
        features.append("small_pool_visual_debug")
    return tuple(features)


class FuzzyEnigmaRecognizerAdapter:
    def __init__(
        self,
        *,
        project_root: Path,
        config_path: Path | None = None,
        mode: str = "greenfield",
        auto_track_results: bool = False,
        prefer_visual_small_pool: bool = False,
    ) -> None:
        if not _card_engine_ocr_available():
            raise RuntimeError(
                "Fuzzy Enigma recognizer requires an OCR backend. Install the vendored submodule with "
                "`pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`."
            )
        modules = _load_card_engine_modules(project_root)
        if config_path is not None:
            config = modules.config.load_engine_config(str(config_path))
        else:
            config = modules.config.load_engine_config()
        self._mode = mode
        self._prefer_visual_small_pool = prefer_visual_small_pool
        self._recognizer = modules.sortingmachine.SortingMachineRecognizer(
            config=config,
            auto_track_results=auto_track_results,
        )

    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        if frame.path is None:
            if frame.metadata.get("card_name") is None:
                return RecognitionResult(
                    card_name=None,
                    confidence=1.0,
                    backend="fuzzy_enigma",
                    requested_mode=self._mode,
                    effective_mode=self._mode,
                )
            raise RuntimeError(
                "Fuzzy Enigma recognizer requires a frame image path. "
                "Ensure the camera adapter persists or exposes the captured image."
            )

        try:
            output = self._recognizer.recognize_top_card(
                frame.path,
                mode=self._mode,
                detailed=True,
                prefer_visual_small_pool=self._prefer_visual_small_pool,
            )
        except ValueError as exc:
            if "No tracked pool is available for constrained recognition." not in str(exc):
                raise
            return RecognitionResult(
                card_name=None,
                confidence=0.0,
                backend="fuzzy_enigma",
                requested_mode=self._mode,
                effective_mode=self._mode,
                needs_review=True,
                mode_features=_mode_features({}, prefer_visual_small_pool=self._prefer_visual_small_pool),
                debug={
                    "engine_error_code": "missing_tracked_pool",
                    "engine_error": str(exc),
                },
            )
        raw_debug = dict(output.debug)
        raw_mode = raw_debug.get("mode") if isinstance(raw_debug.get("mode"), dict) else {}
        requested_mode = raw_mode.get("requested", self._mode)
        effective_mode = raw_mode.get("effective", requested_mode)
        alternatives = tuple(
            {
                "name": candidate.name,
                "score": float(candidate.score),
                "scryfall_id": candidate.scryfall_id,
                "oracle_id": candidate.oracle_id,
                "set_code": candidate.set_code,
                "collector_number": candidate.collector_number,
            }
            for candidate in output.top_k_candidates
        )
        return RecognitionResult(
            card_name=output.card_name,
            confidence=float(output.confidence),
            backend="fuzzy_enigma",
            scryfall_id=output.scryfall_id,
            oracle_id=output.oracle_id,
            requested_mode=str(requested_mode) if requested_mode is not None else self._mode,
            effective_mode=str(effective_mode) if effective_mode is not None else self._mode,
            mode_features=_mode_features(raw_debug, prefer_visual_small_pool=self._prefer_visual_small_pool),
            alternatives=alternatives,
            debug={
                "active_roi": output.active_roi,
                "tried_rois": list(output.tried_rois),
                "bbox": output.bbox,
                "ocr_lines": list(output.ocr_lines),
                "raw": raw_debug,
            },
        )
