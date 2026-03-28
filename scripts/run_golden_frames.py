from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.adapters.recognition.fuzzy_enigma_recognizer import FuzzyEnigmaRecognizerAdapter
from sorter.application.recognition_benchmark import (
    RecognitionBenchmarkCase,
    default_artifact_path,
    summarize_recognition_cases,
    write_benchmark_artifacts,
    write_portable_report,
)
from sorter.application.recognition_reporting import (
    classify_review_reason,
    recommend_recovery_action,
    review_reason_family,
)
from sorter.config.card_engine import resolve_card_engine_config_path
from sorter.config.settings import AppSettings
from sorter.domain.models import PileId
from sorter.ports.camera import Frame
from sorter.ports.recognizer import RecognitionResult


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a recognizer against a fixed golden-frame manifest.")
    parser.add_argument(
        "--manifest",
        default="tests/golden_frames/runtime_small_stack_top_cards.json",
        help="Golden-frame manifest JSON path.",
    )
    parser.add_argument("--backend", choices=["fuzzy_enigma", "manifest_truth"], default="fuzzy_enigma")
    parser.add_argument("--card-engine-config", default=None, help="Optional parent-owned card-engine config path.")
    parser.add_argument("--card-engine-mode", choices=["greenfield", "small_pool", "reevaluation", "confirmation"], default=None)
    parser.add_argument("--use-expected-label", action="store_true", help="Pass the manifest expected label into the recognition request.")
    parser.add_argument("--use-tracked-pool", action="store_true", help="Force constrained modes to use the recognizer tracked pool.")
    parser.add_argument("--track-result", action="store_true", help="Force the recognizer to track successful results during the run.")
    parser.add_argument("--prefer-visual-small-pool", action="store_true", help="Ask the recognizer to prefer visual narrowing for small-pool requests.")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--artifact-root", default=None)
    parser.add_argument("--portable-out", default=None)
    args = parser.parse_args()

    settings = AppSettings.from_env(project_root=PROJECT_ROOT)
    settings = replace(settings, recognizer_backend=args.backend)
    if args.card_engine_mode is not None:
        settings = replace(settings, card_engine_mode=args.card_engine_mode)
    if args.backend == "fuzzy_enigma":
        override_path = None if args.card_engine_config is None else (PROJECT_ROOT / args.card_engine_config)
        settings = replace(
            settings,
            card_engine_config_path=resolve_card_engine_config_path(
                settings,
                for_benchmark=True,
                override_path=override_path,
            ),
        )

    manifest_path = PROJECT_ROOT / args.manifest
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest_name = str(manifest.get("name") or manifest_path.stem)
    recognizer = _build_recognizer(settings)
    cases: list[RecognitionBenchmarkCase] = []

    for index, case in enumerate(manifest.get("cases", []), start=1):
        if not isinstance(case, dict):
            continue
        frame = _build_manifest_frame(case, frame_index=index)
        frame = _apply_mode_request(
            frame,
            settings=settings,
            use_expected_label=args.use_expected_label,
            use_tracked_pool=True if args.use_tracked_pool else None,
            track_result=True if args.track_result else None,
            prefer_visual_small_pool=True if args.prefer_visual_small_pool else None,
        )
        result = recognizer.recognize_top_card(frame)
        review_reason = classify_review_reason(frame, result)
        review_family = review_reason_family(review_reason)
        recovery_action = recommend_recovery_action(frame, result)
        pile_key = str(case.get("pile_key") or "")
        cases.append(
            RecognitionBenchmarkCase(
                pile_key=pile_key,
                frame_id=frame.frame_id,
                frame_path=frame.path,
                expected_name=frame.metadata.get("card_name"),
                expected_scryfall_id=frame.metadata.get("scryfall_id"),
                expected_oracle_id=frame.metadata.get("oracle_id"),
                predicted_name=result.card_name,
                predicted_scryfall_id=result.scryfall_id,
                predicted_oracle_id=result.oracle_id,
                confidence=result.confidence,
                backend=result.backend,
                requested_mode=result.requested_mode,
                effective_mode=result.effective_mode,
                mode_flags=dict(result.mode_flags),
                mode_features=tuple(result.mode_features),
                pipeline_summary=dict(result.pipeline_summary),
                failure_code=result.failure_code,
                engine_review_reason=result.review_reason,
                needs_review=result.needs_review,
                review_reason=review_reason,
                review_family=review_family,
                recovery_action=recovery_action,
                fallback_used=result.fallback_used,
                matched_name=result.card_name == frame.metadata.get("card_name"),
                image_available=frame.path is not None,
                alternatives=tuple(result.alternatives),
                debug=dict(result.debug),
                mode_request=_serialize_mode_request(frame.metadata.get("recognition_request")),
            )
        )

    requested_mode = settings.card_engine_mode if args.backend == "fuzzy_enigma" else "manifest_truth"
    mode_request_options = _mode_request_options(
        settings,
        use_expected_label=args.use_expected_label,
        use_tracked_pool=True if args.use_tracked_pool else None,
        track_result=True if args.track_result else None,
        prefer_visual_small_pool=True if args.prefer_visual_small_pool else None,
    )
    summary = summarize_recognition_cases(
        cases,
        backend=args.backend,
        scenario_name=manifest_name,
        report_type="golden_frames",
        requested_mode=requested_mode,
        mode_request_options=mode_request_options,
    )

    summary_name = f"{args.backend}_{manifest_name}_golden"
    output_path = Path(args.json_out) if args.json_out else (PROJECT_ROOT / "data" / "recognition_reports" / f"{summary_name}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")

    artifact_root = Path(args.artifact_root) if args.artifact_root else default_artifact_path(PROJECT_ROOT, summary_name)
    artifact_root = write_benchmark_artifacts(summary, artifact_root)
    portable_out = Path(args.portable_out) if args.portable_out else (PROJECT_ROOT / "data" / "recognition_reports" / "portable" / f"{summary_name}.portable.json")
    portable_out = write_portable_report(
        summary,
        portable_out,
        artifact_root=artifact_root,
        card_engine_config_path=str(settings.card_engine_config_path) if settings.card_engine_config_path is not None else None,
        project_root=PROJECT_ROOT,
    )

    print(f"backend={summary.backend}")
    print(f"manifest={manifest_path}")
    print(f"requested_mode={summary.requested_mode}")
    print(f"mode_request_options={json.dumps(summary.mode_request_options, sort_keys=True)}")
    print(f"cases={summary.scored_cases}")
    print(f"name_accuracy={summary.name_accuracy:.3f}")
    print(f"average_confidence={summary.average_confidence:.3f}")
    print(f"review_count={summary.review_count}")
    print(f"review_reason_counts={json.dumps(summary.review_reason_counts, sort_keys=True)}")
    print(f"effective_mode_counts={json.dumps(summary.effective_mode_counts, sort_keys=True)}")
    print(f"json_out={output_path}")
    print(f"portable_out={portable_out}")
    print(f"artifact_root={artifact_root}")
    return 0


def _build_recognizer(settings: AppSettings):
    if settings.recognizer_backend == "manifest_truth":
        return _ManifestTruthRecognizer()
    return FuzzyEnigmaRecognizerAdapter(
        project_root=PROJECT_ROOT,
        config_path=settings.card_engine_config_path,
        mode=settings.card_engine_mode,
        auto_track_results=settings.card_engine_auto_track_results,
        prefer_visual_small_pool=settings.card_engine_prefer_visual_small_pool,
    )


def _build_manifest_frame(case: dict, *, frame_index: int) -> Frame:
    raw_path = str(case.get("frame_path") or "")
    absolute_path = _resolve_manifest_frame_path(raw_path)
    pile_key = str(case.get("pile_key") or "")
    pile_id = _pile_id_from_key(pile_key)
    metadata = {
        "card_name": case.get("expected_name"),
        "scryfall_id": case.get("expected_scryfall_id"),
        "oracle_id": case.get("expected_oracle_id"),
        "source": "golden_manifest",
        "set_code": _set_code_from_frame_path(raw_path),
    }
    return Frame(
        frame_id=f"golden-{frame_index:03d}",
        path=str(absolute_path),
        pile_id=pile_id,
        metadata=metadata,
        source_mode="golden_manifest",
    )


def _resolve_manifest_frame_path(raw_path: str) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / raw_path


def _pile_id_from_key(value: str) -> PileId | None:
    if "," not in value:
        return None
    left, right = value.split(",", 1)
    try:
        return PileId(x_index=int(left), y_index=int(right))
    except ValueError:
        return None


def _set_code_from_frame_path(raw_path: str) -> str | None:
    path = Path(raw_path.replace("\\", "/"))
    parts = [part for part in path.parts if part]
    if "SimulatedCardImages" in parts:
        index = parts.index("SimulatedCardImages")
        if len(parts) > index + 2:
            return parts[index + 1].lower()
    return None


def _apply_mode_request(
    frame: Frame,
    *,
    settings: AppSettings,
    use_expected_label: bool,
    use_tracked_pool: bool | None,
    track_result: bool | None,
    prefer_visual_small_pool: bool | None,
) -> Frame:
    if settings.recognizer_backend != "fuzzy_enigma":
        return frame
    request: dict[str, object] = {"mode": settings.card_engine_mode}
    if use_expected_label and isinstance(frame.metadata.get("card_name"), str):
        expected_card = {"name": str(frame.metadata["card_name"])}
        scryfall_id = frame.metadata.get("scryfall_id")
        oracle_id = frame.metadata.get("oracle_id")
        if isinstance(scryfall_id, str) and scryfall_id.strip():
            expected_card["scryfall_id"] = scryfall_id.strip()
        if isinstance(oracle_id, str) and oracle_id.strip():
            expected_card["oracle_id"] = oracle_id.strip()
        set_code = frame.metadata.get("set_code")
        if isinstance(set_code, str) and set_code.strip():
            expected_card["set_code"] = set_code.strip()
        request["expected_card"] = expected_card
    if use_tracked_pool is not None:
        request["use_tracked_pool"] = use_tracked_pool
    elif settings.card_engine_mode == "small_pool" and use_expected_label:
        request["use_tracked_pool"] = False
    if track_result is not None:
        request["track_result"] = track_result
    if prefer_visual_small_pool is not None:
        request["prefer_visual_small_pool"] = prefer_visual_small_pool
    metadata = dict(frame.metadata)
    metadata["recognition_request"] = request
    return replace(frame, metadata=metadata)


def _mode_request_options(
    settings: AppSettings,
    *,
    use_expected_label: bool,
    use_tracked_pool: bool | None,
    track_result: bool | None,
    prefer_visual_small_pool: bool | None,
) -> dict[str, object]:
    if settings.recognizer_backend != "fuzzy_enigma":
        return {}
    options: dict[str, object] = {
        "mode": settings.card_engine_mode,
        "use_expected_label": use_expected_label,
    }
    if use_tracked_pool is not None:
        options["use_tracked_pool"] = use_tracked_pool
    elif settings.card_engine_mode == "small_pool" and use_expected_label:
        options["use_tracked_pool"] = False
    if track_result is not None:
        options["track_result"] = track_result
    if prefer_visual_small_pool is not None:
        options["prefer_visual_small_pool"] = prefer_visual_small_pool
    return options


def _serialize_mode_request(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, object] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, (str, int, float, bool)):
            out[str(key)] = item
            continue
        if isinstance(item, dict):
            nested: dict[str, object] = {}
            for nested_key, nested_item in item.items():
                if isinstance(nested_item, (str, int, float, bool)) and nested_item is not None:
                    nested[str(nested_key)] = nested_item
            out[str(key)] = nested
    return out


class _ManifestTruthRecognizer:
    def recognize_top_card(self, frame: Frame) -> RecognitionResult:
        return RecognitionResult(
            card_name=frame.metadata.get("card_name"),
            confidence=1.0,
            backend="manifest_truth",
            requested_mode="manifest_truth",
            effective_mode="manifest_truth",
            mode_features=("golden_truth",),
        )


if __name__ == "__main__":
    raise SystemExit(main())
