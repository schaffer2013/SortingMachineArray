from __future__ import annotations

from pathlib import Path
import json


def build_catalog(image_dir: Path, output_path: Path) -> None:
    cards = []
    if image_dir.exists():
        for image in sorted(image_dir.glob("*.jpg")):
            name = image.stem.replace("_", " ")
            cards.append(
                {
                    "name": name,
                    "rarity": None,
                    "colors": [],
                    "color_identity": [],
                    "card_types": [],
                    "supertypes": [],
                    "is_land": False,
                    "is_basic_land": False,
                    "mana_value": None,
                    "market_price_usd": None,
                    "images": [str(image)],
                }
            )
    payload = {"cards": cards}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    build_catalog(
        image_dir=root / "data/card_catalog/images",
        output_path=root / "data/card_catalog/cards.json",
    )
