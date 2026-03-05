from __future__ import annotations

from pathlib import Path
import json

from sorter.domain.models import CardMeta


class FileCardCatalog:
    def __init__(self, catalog_path: Path):
        self.catalog_path = catalog_path
        self._cards = self._load()

    def _load(self) -> dict[str, CardMeta]:
        if not self.catalog_path.exists():
            return {}
        with self.catalog_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        cards: dict[str, CardMeta] = {}
        for item in raw.get("cards", []):
            card = CardMeta(
                name=item["name"],
                rarity=item.get("rarity", "OTHER"),
                card_type=item.get("card_type", "other"),
                color=item.get("color", "default"),
                sort_rank=int(item.get("sort_rank", 99999)),
            )
            cards[card.name] = card
        return cards

    def get_card_meta(self, name: str) -> CardMeta | None:
        return self._cards.get(name)

    def all_cards(self) -> list[CardMeta]:
        return list(self._cards.values())
