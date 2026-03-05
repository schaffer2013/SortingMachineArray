from __future__ import annotations

from typing import Protocol

from sorter.domain.models import CardMeta


class CardCatalogPort(Protocol):
    def get_card_meta(self, name: str) -> CardMeta | None: ...
    def all_cards(self) -> list[CardMeta]: ...
