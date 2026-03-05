from __future__ import annotations

import argparse
from pathlib import Path

from sorter.adapters.persistence.sim_image_sync import sync_simulated_images


def main() -> int:
    parser = argparse.ArgumentParser(description="Log simulated card list and rebuild missing images via Scrython when needed.")
    parser.add_argument("--pile-manager", default="pile_manager.py")
    parser.add_argument("--fixture", default="scenarios/fixtures/small_stack.json")
    parser.add_argument("--image-piles", default="image_piles.json")
    parser.add_argument("--image-dir", default="SimulatedCardImages")
    parser.add_argument("--log-file", default="data/logs/simulated_cards.log")
    parser.add_argument("--no-fetch", action="store_true", help="Do not download missing images")
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    pile_manager_path = root / args.pile_manager
    fixture_path = root / args.fixture
    image_piles_path = root / args.image_piles
    image_dir = root / args.image_dir
    log_path = root / args.log_file

    summary = sync_simulated_images(
        project_root=root,
        fixture_path=fixture_path,
        image_dir=image_dir,
        log_path=log_path,
        pile_manager_path=pile_manager_path,
        image_piles_path=image_piles_path,
        auto_fetch=not args.no_fetch,
    )
    print(f"Extracted {summary.total_cards} cards")
    print(f"Image folder: {image_dir}")
    print(f"Missing before sync: {summary.missing_before}")
    print(f"Downloaded: {summary.downloaded} Failed: {summary.failed}")
    print(f"Missing after sync: {summary.missing_after}")
    print(f"Log written: {summary.log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
