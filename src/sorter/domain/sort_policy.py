from __future__ import annotations

from sorter.domain.models import CardInstance
from sorter.domain.ranking_service import RankingService
from sorter.domain.sort_policy_config import SortPolicyConfig, SortCriterion


class SortPolicy:
    """Legacy compatibility wrapper for older tests/scripts.

    New code should use `RankingService` with explicit JSON policy configuration.
    """

    def __init__(self):
        self._fallback_policy = SortPolicyConfig(
            version=1,
            policy_name="legacy_name_only",
            criteria=[SortCriterion(kind="alpha", field="name")],
        )

    def compare(self, card1: CardInstance, card2: CardInstance) -> bool:
        mapping = self.rank_mapping([card1, card2])
        return mapping[card1.card_id] < mapping[card2.card_id]

    def rank_mapping(self, cards: list[CardInstance]) -> dict[str, int]:
        service = RankingService(self._fallback_policy)
        compiled = service.compile({card.card_id: card.meta for card in cards})
        return compiled.card_id_to_rank
