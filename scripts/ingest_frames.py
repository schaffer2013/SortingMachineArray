from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.application.vision_dataset import ingest_recognition_summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest replay or benchmark summary frames into the parent vision dataset.")
    parser.add_argument("--summary-json", required=True, help="Path to a replay or benchmark summary JSON file.")
    parser.add_argument("--source-mode", default="sim", help="Dataset source mode label, for example sim or hardware.")
    parser.add_argument("--split", default="benchmark", help="Dataset split label, for example benchmark, train, or eval.")
    parser.add_argument("--dataset-root", default="data/vision", help="Parent-owned dataset root.")
    args = parser.parse_args()

    summary_path = PROJECT_ROOT / args.summary_json
    dataset_root = PROJECT_ROOT / args.dataset_root
    records = ingest_recognition_summary(
        summary_path,
        dataset_root=dataset_root,
        source_mode=args.source_mode,
        split=args.split,
    )
    print(f"ingested_records={len(records)}")
    print(f"dataset_root={dataset_root}")
    print(f"summary_json={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
