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

from sorter.application.recognition_benchmark import default_json_path, run_sim_recognition_benchmark
from sorter.config.settings import AppSettings


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay the configured recognizer over simulated top-card captures.")
    parser.add_argument("--backend", choices=["sim_truth", "fuzzy_enigma"], default=None)
    parser.add_argument("--include-empty", action="store_true")
    parser.add_argument("--pile", action="append", dest="piles", help="Replay one or more pile keys like 0,0")
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args()

    settings = AppSettings.from_env(project_root=PROJECT_ROOT)
    if args.backend is not None:
        settings = replace(settings, recognizer_backend=args.backend)

    summary = run_sim_recognition_benchmark(
        settings,
        pile_keys=args.piles,
        include_empty=args.include_empty,
    )
    default_path = default_json_path(PROJECT_ROOT, f"{summary.backend}_replay")
    output_path = Path(args.json_out) if args.json_out else default_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")

    for case in summary.cases:
        print(
            f"{case.pile_key}: expected={case.expected_name!r} predicted={case.predicted_name!r} "
            f"confidence={case.confidence:.3f} review={case.needs_review} fallback={case.fallback_used} "
            f"path={case.frame_path}"
        )
    print(f"json_out={output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
