from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.application.recognition_compare import compare_recognition_summaries


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare two saved recognition summary JSON files.")
    parser.add_argument("--baseline", required=True, help="Baseline summary JSON path.")
    parser.add_argument("--candidate", required=True, help="Candidate summary JSON path.")
    parser.add_argument("--json-out", default=None, help="Optional output path for the comparison JSON.")
    args = parser.parse_args()

    baseline_path = PROJECT_ROOT / args.baseline
    candidate_path = PROJECT_ROOT / args.candidate
    summary = compare_recognition_summaries(baseline_path, candidate_path)

    if args.json_out:
        output_path = PROJECT_ROOT / args.json_out
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary.to_dict(), indent=2), encoding="utf-8")
        print(f"json_out={output_path}")

    print(f"baseline_backend={summary.baseline_backend}")
    print(f"candidate_backend={summary.candidate_backend}")
    print(f"scenario={summary.scenario_name}")
    print(f"total_compared_cases={summary.total_compared_cases}")
    print(f"changed_prediction_count={summary.changed_prediction_count}")
    print(f"candidate_review_reduction={summary.candidate_review_reduction}")
    print(f"confidence_delta_average={summary.confidence_delta_average:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
