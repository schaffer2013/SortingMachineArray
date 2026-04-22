from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
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
    operational_modes: ModuleType


def _load_card_engine_modules(project_root: Path) -> CardEngineModules:
    try:
        return CardEngineModules(
            config=importlib.import_module("card_engine.config"),
            sortingmachine=importlib.import_module("card_engine.adapters.sortingmachine"),
            operational_modes=importlib.import_module("card_engine.operational_modes"),
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
            operational_modes=importlib.import_module("card_engine.operational_modes"),
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


def _mode_features(
    *,
    mode_flags: dict[str, Any] | None,
    pipeline_summary: dict[str, Any] | None,
    prefer_visual_small_pool: bool,
) -> tuple[str, ...]:
    features: list[str] = []
    normalized_mode_flags = mode_flags if isinstance(mode_flags, dict) else {}
    if normalized_mode_flags.get("has_expected_card"):
        features.append("has_expected_card")
    if normalized_mode_flags.get("has_candidate_pool"):
        features.append("has_candidate_pool")
    if normalized_mode_flags.get("used_tracked_pool"):
        features.append("used_tracked_pool")
    if normalized_mode_flags.get("used_visual_small_pool"):
        features.append("used_visual_small_pool")
    if prefer_visual_small_pool:
        features.append("prefer_visual_small_pool")
    normalized_pipeline_summary = pipeline_summary if isinstance(pipeline_summary, dict) else {}
    for branch in normalized_pipeline_summary.get("branches_fired", []):
        if isinstance(branch, str) and branch.strip():
            features.append(branch.strip())
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
        card_engine_backend: str | None = None,
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
        if card_engine_backend is not None:
            config.recognition_backend = card_engine_backend
        self.sorter_backend = card_engine_backend or "fuzzy_enigma"
        self.card_engine_requested_backend = _configured_card_engine_backend(config)
        self.card_engine_backend_fallback = bool(getattr(config, "recognition_backend_fallback", True))
        self.card_engine_mode = mode
        self._mode = mode
        self._prefer_visual_small_pool = prefer_visual_small_pool
        self._expected_card_from_values = modules.operational_modes.expected_card_from_values
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
                    backend=self.card_engine_requested_backend,
                    requested_mode=self._mode,
                    effective_mode=self._mode,
                    mode_features=_mode_features(mode_flags=None, pipeline_summary=None, prefer_visual_small_pool=False),
                )
            raise RuntimeError(
                "Fuzzy Enigma recognizer requires a frame image path. "
                "Ensure the camera adapter persists or exposes the captured image."
            )

        request = frame.metadata.get("recognition_request")
        if not isinstance(request, dict):
            request = {}
        requested_mode = str(request.get("mode") or self._mode)
        prefer_visual_small_pool = bool(request.get("prefer_visual_small_pool", self._prefer_visual_small_pool))
        progress_callback = _progress_callback_from_value(request.get("progress_callback"))
        requested_backend = request.get("backend")
        if isinstance(requested_backend, str):
            requested_backend = requested_backend.strip().lower()
            if requested_backend in {"moss", "moss-machine"}:
                requested_backend = "moss_machine"
        else:
            requested_backend = None

        recognizer_config = getattr(self._recognizer, "config", None)
        if requested_backend and recognizer_config is not None and hasattr(recognizer_config, "recognition_backend"):
            setattr(recognizer_config, "recognition_backend", requested_backend)
            self.sorter_backend = requested_backend
            self.card_engine_requested_backend = requested_backend

        use_tracked_pool = request.get("use_tracked_pool")
        track_result = request.get("track_result")
        expected_card_payload = request.get("expected_card")
        expected_card = None
        if isinstance(expected_card_payload, dict):
            expected_card = self._expected_card_from_values(
                scryfall_id=expected_card_payload.get("scryfall_id"),
                oracle_id=expected_card_payload.get("oracle_id"),
                name=expected_card_payload.get("name"),
                set_code=expected_card_payload.get("set_code"),
                collector_number=expected_card_payload.get("collector_number"),
            )

        try:
            output = _recognize_card_engine_detailed(
                self._recognizer,
                frame.path,
                mode=requested_mode,
                expected_card=expected_card,
                use_tracked_pool=use_tracked_pool,
                track_result=track_result,
                prefer_visual_small_pool=prefer_visual_small_pool,
                progress_callback=progress_callback,
            )
        except ValueError as exc:
            error_message = str(exc)
            error_code = _engine_error_code(error_message)
            if error_code is None:
                raise
            return RecognitionResult(
                card_name=None,
                confidence=0.0,
                backend=requested_backend or self.card_engine_requested_backend,
                requested_mode=requested_mode,
                effective_mode=requested_mode,
                failure_code=error_code,
                review_reason=error_code,
                needs_review=True,
                mode_features=_mode_features(
                    mode_flags=None,
                    pipeline_summary={"resolution_path": "precondition_failed"},
                    prefer_visual_small_pool=prefer_visual_small_pool,
                ),
                pipeline_summary={"resolution_path": "precondition_failed"},
                debug={
                    "engine_error_code": error_code,
                    "engine_error": error_message,
                },
            )
        raw_debug = dict(_output_attr(output, "debug", {}))
        mode_flags = dict(_output_attr(output, "mode_flags", {}))
        pipeline_summary = dict(_output_attr(output, "pipeline_summary", {}))
        requested_mode = _output_attr(output, "requested_mode", requested_mode) or requested_mode
        effective_mode = _output_attr(output, "effective_mode", requested_mode) or requested_mode
        top_k_candidates = list(_output_attr(output, "top_k_candidates", []))
        alternatives = tuple(
            {
                "name": candidate.name,
                "score": float(candidate.score),
                "scryfall_id": candidate.scryfall_id,
                "oracle_id": candidate.oracle_id,
                "set_code": candidate.set_code,
                "collector_number": candidate.collector_number,
            }
            for candidate in top_k_candidates
        )
        best_candidate = top_k_candidates[0] if top_k_candidates else None
        return RecognitionResult(
            card_name=_output_attr(output, "card_name", _output_attr(output, "best_name")),
            confidence=float(_output_attr(output, "confidence", 0.0)),
            backend=_effective_card_engine_backend(raw_debug, default=self.card_engine_requested_backend),
            scryfall_id=_output_attr(output, "scryfall_id", getattr(best_candidate, "scryfall_id", None)),
            oracle_id=_output_attr(output, "oracle_id", getattr(best_candidate, "oracle_id", None)),
            requested_mode=str(requested_mode) if requested_mode is not None else self._mode,
            effective_mode=str(effective_mode) if effective_mode is not None else self._mode,
            mode_flags=mode_flags,
            mode_features=_mode_features(
                mode_flags=mode_flags,
                pipeline_summary=pipeline_summary,
                prefer_visual_small_pool=prefer_visual_small_pool,
            ),
            pipeline_summary=pipeline_summary,
            failure_code=_output_attr(output, "failure_code"),
            review_reason=_output_attr(output, "review_reason"),
            needs_review=_output_attr(output, "review_reason") is not None,
            alternatives=alternatives,
            debug={
                "backend": dict(raw_debug.get("backend", {})) if isinstance(raw_debug.get("backend"), dict) else {},
                "active_roi": _output_attr(output, "active_roi"),
                "tried_rois": list(_output_attr(output, "tried_rois", [])),
                "bbox": _output_attr(output, "bbox"),
                "ocr_lines": list(_output_attr(output, "ocr_lines", [])),
                "raw": raw_debug,
            },
        )


def _progress_callback_from_value(value: Any):
    if callable(value):
        return value
    update = getattr(value, "update", None)
    if callable(update):
        return update
    return None


def _recognize_card_engine_detailed(
    recognizer: Any,
    image_path: str,
    *,
    mode: str,
    expected_card: Any,
    use_tracked_pool: Any,
    track_result: Any,
    prefer_visual_small_pool: bool,
    progress_callback,
):
    session = getattr(recognizer, "session", None)
    if session is not None and hasattr(session, "recognize"):
        return session.recognize(
            image_path,
            mode=mode,
            expected_card=expected_card,
            use_tracked_pool=use_tracked_pool,
            track_result=track_result,
            progress_callback=progress_callback,
            prefer_visual_small_pool=prefer_visual_small_pool,
        )

    kwargs = {
        "mode": mode,
        "expected_card": expected_card,
        "use_tracked_pool": use_tracked_pool,
        "track_result": track_result,
        "detailed": True,
        "prefer_visual_small_pool": prefer_visual_small_pool,
    }
    if progress_callback is not None:
        try:
            return recognizer.recognize_top_card(
                image_path,
                progress_callback=progress_callback,
                **kwargs,
            )
        except TypeError as exc:
            if "progress_callback" not in str(exc):
                raise
    return recognizer.recognize_top_card(image_path, **kwargs)


def _output_attr(output: Any, name: str, default: Any = None) -> Any:
    return getattr(output, name, default)


def _engine_error_code(message: str) -> str | None:
    if "No tracked pool is available for constrained recognition." in message:
        return "missing_tracked_pool"
    if "requires an expected_card." in message:
        return "missing_expected_card"
    if "No catalog records found for expected card:" in message:
        return "expected_card_not_in_catalog"
    return None


def _configured_card_engine_backend(config: Any) -> str:
    configured = os.getenv("CARD_ENGINE_BACKEND") or getattr(config, "recognition_backend", None) or "fuzzy_enigma"
    normalized = str(configured).strip().lower()
    if normalized in {"moss", "moss_machine", "moss-machine"}:
        return "moss_machine"
    return "fuzzy_enigma"


def _effective_card_engine_backend(raw_debug: dict[str, Any], *, default: str) -> str:
    backend_debug = raw_debug.get("backend")
    if isinstance(backend_debug, dict):
        effective = backend_debug.get("effective")
        if isinstance(effective, str) and effective.strip():
            normalized = effective.strip().lower()
            if normalized in {"moss", "moss_machine", "moss-machine"}:
                return "moss_machine"
            if normalized in {"ours", "default", "native"}:
                return "fuzzy_enigma"
            return normalized
    return default
