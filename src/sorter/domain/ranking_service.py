from __future__ import annotations

from dataclasses import dataclass

from sorter.domain.models import CardMeta
from sorter.domain.policy_evaluator import build_sort_key
from sorter.domain.sort_fields import derive_fields
from sorter.domain.sort_policy_config import SortPolicyConfig


@dataclass(frozen=True)
class CardRankingExplanation:
    card_id: str
    card_name: str
    factual_fields: dict[str, object]
    derived_fields: dict[str, object]
    sort_key: tuple
    ordinal_rank: int


@dataclass(frozen=True)
class CompiledRanking:
    card_id_to_sort_key: dict[str, tuple]
    card_id_to_rank: dict[str, int]
    explain_by_card_id: dict[str, CardRankingExplanation]

    def explain_card(self, card_id_or_name: str) -> CardRankingExplanation | None:
        if card_id_or_name in self.explain_by_card_id:
            return self.explain_by_card_id[card_id_or_name]

        normalized = card_id_or_name.strip().lower()
        matches = [
            explanation
            for explanation in self.explain_by_card_id.values()
            if explanation.card_name.strip().lower() == normalized
        ]
        if len(matches) == 1:
            return matches[0]
        return None


class RankingService:
    def __init__(self, policy_config: SortPolicyConfig):
        self.policy_config = policy_config

    def compile(self, card_by_id: dict[str, CardMeta]) -> CompiledRanking:
        card_id_to_sort_key = {
            card_id: build_sort_key(card_meta, self.policy_config)
            for card_id, card_meta in card_by_id.items()
        }

        ordered_ids = sorted(
            card_id_to_sort_key.keys(),
            key=lambda card_id: (card_id_to_sort_key[card_id], card_id),
        )
        card_id_to_rank = {
            card_id: index + 1
            for index, card_id in enumerate(ordered_ids)
        }

        explain_by_card_id = {
            card_id: CardRankingExplanation(
                card_id=card_id,
                card_name=card_by_id[card_id].name,
                factual_fields=_factual_fields(card_by_id[card_id]),
                derived_fields=derive_fields(card_by_id[card_id]),
                sort_key=card_id_to_sort_key[card_id],
                ordinal_rank=card_id_to_rank[card_id],
            )
            for card_id in ordered_ids
        }

        return CompiledRanking(
            card_id_to_sort_key=card_id_to_sort_key,
            card_id_to_rank=card_id_to_rank,
            explain_by_card_id=explain_by_card_id,
        )


def _factual_fields(card_meta: CardMeta) -> dict[str, object]:
    return {
        "name": card_meta.name,
        "rarity": card_meta.rarity,
        "colors": list(card_meta.colors),
        "color_identity": list(card_meta.color_identity),
        "card_types": list(card_meta.card_types),
        "supertypes": list(card_meta.supertypes),
        "is_land": card_meta.is_land,
        "is_basic_land": card_meta.is_basic_land,
        "mana_value": card_meta.mana_value,
        "market_price_usd": card_meta.market_price_usd,
    }
