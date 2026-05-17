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

from sorter.application.recognition_benchmark import (
    default_artifact_path,
    default_json_path,
    default_portable_report_path,
    run_sim_recognition_benchmark,
    write_benchmark_artifacts,
    write_portable_report,
)
from sorter.config.card_engine import resolve_card_engine_config_path
from sorter.config.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the configured recognizer over simulated top-card captures.")
    parser.add_argument("--backend", choices=["sim_truth", "fuzzy_enigma", "moss_machine"], default=None)
    parser.add_argument("--include-empty", action="store_true")
    parser.add_argument("--pile", action="append", dest="piles", help="Replay one or more piles by display number.")
    parser.add_argument("--card-engine-config", default=None, help="Optional parent-owned card-engine config path.")
    parser.add_argument("--card-engine-mode", choices=["greenfield", "small_pool", "reevaluation", "confirmation"], default=None)
    parser.add_argument("--use-expected-label", action="store_true", help="Pass the simulated expected top-card label into the recognition request.")
    parser.add_argument("--use-tracked-pool", action="store_true", help="Force constrained modes to use the recognizer tracked pool.")
    parser.add_argument("--track-result", action="store_true", help="Force the recognizer to track successful results during the run.")
    parser.add_argument("--prefer-visual-small-pool", action="store_true", help="Ask the recognizer to prefer visual narrowing for small-pool requests.")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--artifact-root", default=None, help="Optional directory for per-case debug artifacts.")
    parser.add_argument("--portable-out", default=None, help="Optional portable success/failure report JSON path.")
    args = parser.parse_args()

    settings = AppSettings.from_env(project_root=PROJECT_ROOT)
    if args.backend is not None:
        settings = replace(settings, recognizer_backend=args.backend)
    if args.card_engine_mode is not None:
        settings = replace(settings, card_engine_mode=args.card_engine_mode)
    if settings.recognizer_backend in {"fuzzy_enigma", "moss_machine"}:
        override_path = None if args.card_engine_config is None else (PROJECT_ROOT / args.card_engine_config)
        settings = replace(
            settings,
            card_engine_config_path=resolve_card_engine_config_path(
                settings,
                for_benchmark=True,
                override_path=override_path,
            ),
        )

    summary = run_sim_recognition_benchmark(
        settings,
        pile_keys=args.piles,
        include_empty=args.include_empty,
        report_type="replay",
        use_expected_label=args.use_expected_label,
        use_tracked_pool=True if args.use_tracked_pool else None,
        track_result=True if args.track_result else None,
        prefer_visual_small_pool=True if args.prefer_visual_small_pool else None,
    )
    default_path = default_json_path(PROJECT_ROOT, f"{summary.backend}_replay")
    output_path = Path(args.json_out) if args.json_out else default_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    artifact_root = None
    if args.artifact_root is not None:
        artifact_root = Path(args.artifact_root)
    elif summary.backend in {"fuzzy_enigma", "moss_machine"}:
        artifact_root = default_artifact_path(PROJECT_ROOT, f"{summary.backend}_replay")
    if artifact_root is not None:
        artifact_root = write_benchmark_artifacts(summary, artifact_root)
    portable_out = Path(args.portable_out) if args.portable_out else default_portable_report_path(PROJECT_ROOT, f"{summary.backend}_replay")
    portable_out = write_portable_report(
        summary,
        portable_out,
        artifact_root=artifact_root,
        card_engine_config_path=str(settings.card_engine_config_path) if settings.card_engine_config_path is not None else None,
        project_root=PROJECT_ROOT,
    )

    for case in summary.cases:
        pile_prefix = case.pile_label or (f"Pile {case.pile_number}" if case.pile_number is not None else case.pile_key)
        print(
            f"{pile_prefix}: expected={case.expected_name!r} predicted={case.predicted_name!r} "
            f"confidence={case.confidence:.3f} mode={case.requested_mode!r}->{case.effective_mode!r} "
            f"review={case.needs_review} reason={case.review_reason!r} "
            f"fallback={case.fallback_used} "
            f"path={case.frame_path}"
        )
    print(f"requested_mode={summary.requested_mode}")
    print(f"mode_request_options={json.dumps(summary.mode_request_options, sort_keys=True)}")
    print(f"card_engine_config={settings.card_engine_config_path}")
    print(f"json_out={output_path}")
    print(f"portable_out={portable_out}")
    if artifact_root is not None:
        print(f"artifact_root={artifact_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
