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
    run_sim_recognition_benchmark,
    write_benchmark_artifacts,
)
from sorter.config.card_engine import resolve_card_engine_config_path
from sorter.config.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark the configured recognizer against simulated captures.")
    parser.add_argument("--backend", choices=["sim_truth", "fuzzy_enigma"], default=None)
    parser.add_argument("--include-empty", action="store_true")
    parser.add_argument("--pile", action="append", dest="piles", help="Limit benchmarking to one or more pile keys like 0,0")
    parser.add_argument("--card-engine-config", default=None, help="Optional parent-owned card-engine config path.")
    parser.add_argument("--json-out", default=None)
    parser.add_argument("--artifact-root", default=None, help="Optional directory for per-case debug artifacts.")
    args = parser.parse_args()

    settings = AppSettings.from_env(project_root=PROJECT_ROOT)
    if args.backend is not None:
        settings = replace(settings, recognizer_backend=args.backend)
    if settings.recognizer_backend == "fuzzy_enigma":
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
    )
    output_path = Path(args.json_out) if args.json_out else default_json_path(PROJECT_ROOT, summary.backend)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
    artifact_root = None
    if args.artifact_root is not None:
        artifact_root = Path(args.artifact_root)
    elif summary.backend == "fuzzy_enigma":
        artifact_root = default_artifact_path(PROJECT_ROOT, summary.backend)
    if artifact_root is not None:
        artifact_root = write_benchmark_artifacts(summary, artifact_root)

    print(f"backend={summary.backend}")
    print(f"scenario={summary.scenario_name}")
    print(f"cases={summary.scored_cases}")
    print(f"name_accuracy={summary.name_accuracy:.3f}")
    print(f"average_confidence={summary.average_confidence:.3f}")
    print(f"review_count={summary.review_count}")
    print(f"low_confidence_count={summary.low_confidence_count}")
    print(f"missing_prediction_count={summary.missing_prediction_count}")
    print(f"fallback_count={summary.fallback_count}")
    print(f"missing_image_count={summary.missing_image_count}")
    print(f"confidence_band_counts={json.dumps(summary.confidence_band_counts, sort_keys=True)}")
    print(f"review_reason_counts={json.dumps(summary.review_reason_counts, sort_keys=True)}")
    print(f"card_engine_config={settings.card_engine_config_path}")
    print(f"json_out={output_path}")
    if artifact_root is not None:
        print(f"artifact_root={artifact_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
