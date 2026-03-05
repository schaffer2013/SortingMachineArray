from __future__ import annotations

from sorter.domain.models import CardInstance


class SortPolicy:
    def compare(self, card1: CardInstance, card2: CardInstance) -> bool:
        return card1.sort_key() < card2.sort_key()

    def rank_mapping(self, cards: list[CardInstance]) -> dict[str, int]:
        ordered = sorted(cards, key=lambda card: card.sort_key())
        return {card.meta.name: index + 1 for index, card in enumerate(ordered)}
