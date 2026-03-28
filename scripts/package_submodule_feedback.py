from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.application.feedback_bundle import build_submodule_feedback_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Package the current submodule feedback doc and portable evidence into one zip.")
    parser.add_argument(
        "--output",
        default="data/recognition_reports/feedback_bundle/submodule_feedback_bundle.zip",
        help="Zip output path.",
    )
    args = parser.parse_args()

    output_path = PROJECT_ROOT / args.output
    manifest = build_submodule_feedback_bundle(PROJECT_ROOT, output_path)

    print(f"output_path={output_path}")
    print(f"entry_count={len(manifest.entries)}")
    for entry in manifest.entries:
        status = "present" if entry.exists else "missing"
        print(f"{status}: {entry.archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
