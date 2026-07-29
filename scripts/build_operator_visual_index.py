from __future__ import annotations

import argparse
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.application.visual_index_refresh import build_visual_index_from_catalog


def main() -> int:
    parser = argparse.ArgumentParser(description="Build the visual retrieval index from the bundled catalog.")
    parser.add_argument("--catalog", default=str(REPO_ROOT / "data" / "catalog" / "default-cards.json"))
    parser.add_argument("--output-dir", default=str(REPO_ROOT / "data" / "index"))
    parser.add_argument("--limit", type=int, default=None, help="Optional limit on the number of cards to index.")
    parser.add_argument("--overwrite", action="store_true", help="Redownload reference images and rebuild the index.")
    parser.add_argument("--refresh-days", type=int, default=7, choices=(1, 3, 7, 14, 30, 60, 90))
    parser.add_argument("--model", default="opencv_v1", choices=("opencv_v1", "onnx", "dinov2_onnx"))
    parser.add_argument("--model-path")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    result = build_visual_index_from_catalog(
        project_root=REPO_ROOT,
        source_catalog_path=args.catalog,
        index_path=output_dir / "card_embeddings.npz",
        metadata_path=output_dir / "card_embeddings.jsonl",
        reference_dir=output_dir / "reference_images",
        refresh_days=args.refresh_days,
        model=args.model,
        model_path=args.model_path,
        overwrite_downloads=args.overwrite,
        limit=args.limit,
    )
    print(f"Indexed {result.card_count} cards -> {result.index_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
