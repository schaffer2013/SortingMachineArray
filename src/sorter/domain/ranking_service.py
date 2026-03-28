from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from sorter.domain.models import CardMeta
from sorter.domain.policy_evaluator import build_sort_key
from sorter.domain.sort_fields import derive_fields
from sorter.domain.sort_policy_config import SortPolicyConfig


logger = logging.getLogger(__name__)


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
    def __init__(self, policy_config: SortPolicyConfig, *, allow_external_enrichment: bool = False):
        self.policy_config = policy_config
        self.allow_external_enrichment = allow_external_enrichment

    def compile(self, card_by_id: dict[str, CardMeta]) -> CompiledRanking:
        effective_card_by_id = _maybe_enrich_missing_metadata(
            card_by_id,
            allow_external_enrichment=self.allow_external_enrichment,
        )
        card_id_to_sort_key = {
            card_id: build_sort_key(card_meta, self.policy_config)
            for card_id, card_meta in effective_card_by_id.items()
        }

        ordered_ids = sorted(
            card_id_to_sort_key.keys(),
            key=lambda card_id: (card_id_to_sort_key[card_id], card_id),
        )
        card_id_to_rank: dict[str, int] = {}
        current_rank = 0
        last_sort_key: tuple | None = None
        for card_id in ordered_ids:
            sort_key = card_id_to_sort_key[card_id]
            if sort_key != last_sort_key:
                current_rank += 1
                last_sort_key = sort_key
            card_id_to_rank[card_id] = current_rank

            card_meta = effective_card_by_id[card_id]
            derived = derive_fields(card_meta)
            colors = list(card_meta.colors) or list(card_meta.color_identity)
            logger.debug(
                "rank generated: card_id=%s card=%s rank=%s sort_key=%s primary_bucket=%s colors=%s card_types=%s",
                card_id,
                card_meta.name,
                current_rank,
                sort_key,
                derived.get("primary_bucket"),
                colors,
                list(card_meta.card_types),
            )

        explain_by_card_id = {
            card_id: CardRankingExplanation(
                card_id=card_id,
                card_name=effective_card_by_id[card_id].name,
                factual_fields=_factual_fields(effective_card_by_id[card_id]),
                derived_fields=derive_fields(effective_card_by_id[card_id]),
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
        "scryfall_id": card_meta.scryfall_id,
        "oracle_id": card_meta.oracle_id,
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


def _maybe_enrich_missing_metadata(
    card_by_id: dict[str, CardMeta],
    *,
    allow_external_enrichment: bool,
) -> dict[str, CardMeta]:
    if not allow_external_enrichment:
        return card_by_id
    return _enrich_missing_metadata_with_scrython(card_by_id)


def _enrich_missing_metadata_with_scrython(card_by_id: dict[str, CardMeta]) -> dict[str, CardMeta]:
    # Only query Scryfall for cards with insufficient metadata for color/type ranking.
    names_to_fetch: set[str] = set()
    for card_meta in card_by_id.values():
        if _needs_enrichment(card_meta):
            names_to_fetch.add(card_meta.name)

    if not names_to_fetch:
        return card_by_id

    try:
        import scrython
    except Exception:
        logger.warning("Scrython unavailable; using existing catalog metadata for ranking")
        return card_by_id

    fetched_by_name: dict[str, CardMeta] = {}
    for card_name in sorted(names_to_fetch):
        try:
            card_data = scrython.cards.Named(fuzzy=card_name)
            payload = _extract_scryfall_payload(card_data)
            if payload is None:
                continue
            fetched_by_name[card_name] = _meta_from_scryfall_payload(card_name, payload)
        except Exception as exc:
            logger.debug("scrython enrichment failed: card=%s err=%s", card_name, exc)

    enriched: dict[str, CardMeta] = {}
    for card_id, card_meta in card_by_id.items():
        fetched = fetched_by_name.get(card_meta.name)
        if fetched is None:
            enriched[card_id] = card_meta
            continue
        enriched[card_id] = _merge_meta(card_meta, fetched)
    return enriched


def _needs_enrichment(card_meta: CardMeta) -> bool:
    return not card_meta.colors and not card_meta.color_identity and not card_meta.card_types


def _extract_scryfall_payload(card_data: object) -> dict[str, Any] | None:
    payload = getattr(card_data, "_scryfall_data", None)
    if isinstance(payload, dict):
        return payload
    for attr in ("scryfallJson", "scryfall_json", "_json"):
        value = getattr(card_data, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if isinstance(value, dict):
            return value
    return None


def _meta_from_scryfall_payload(name: str, payload: dict[str, Any]) -> CardMeta:
    colors = _normalize_text_list(payload.get("colors"))
    color_identity = _normalize_text_list(payload.get("color_identity"))
    rarity_raw = payload.get("rarity")
    rarity = str(rarity_raw).strip().lower() if isinstance(rarity_raw, str) and rarity_raw.strip() else None
    scryfall_id_raw = payload.get("id")
    scryfall_id = (
        str(scryfall_id_raw).strip().lower()
        if isinstance(scryfall_id_raw, str) and scryfall_id_raw.strip()
        else None
    )
    oracle_id_raw = payload.get("oracle_id")
    oracle_id = (
        str(oracle_id_raw).strip().lower()
        if isinstance(oracle_id_raw, str) and oracle_id_raw.strip()
        else None
    )

    supertypes, card_types = _parse_type_line(payload.get("type_line"))
    is_land = "land" in card_types
    is_basic_land = is_land and "basic" in supertypes

    return CardMeta(
        name=name,
        scryfall_id=scryfall_id,
        oracle_id=oracle_id,
        rarity=rarity,
        colors=colors,
        color_identity=color_identity,
        card_types=card_types,
        supertypes=supertypes,
        is_land=is_land,
        is_basic_land=is_basic_land,
    )


def _merge_meta(existing: CardMeta, fetched: CardMeta) -> CardMeta:
    return CardMeta(
        name=existing.name,
        scryfall_id=existing.scryfall_id or fetched.scryfall_id,
        oracle_id=existing.oracle_id or fetched.oracle_id,
        rarity=existing.rarity or fetched.rarity,
        colors=existing.colors or fetched.colors,
        color_identity=existing.color_identity or fetched.color_identity,
        card_types=existing.card_types or fetched.card_types,
        supertypes=existing.supertypes or fetched.supertypes,
        is_land=existing.is_land or fetched.is_land,
        is_basic_land=existing.is_basic_land or fetched.is_basic_land,
        mana_value=existing.mana_value,
        market_price_usd=existing.market_price_usd,
        sort_rank=existing.sort_rank,
    )


def _normalize_text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted({str(item).strip().lower() for item in value if str(item).strip()})


def _parse_type_line(type_line: object) -> tuple[list[str], list[str]]:
    if not isinstance(type_line, str) or not type_line.strip():
        return [], []

    left = type_line.split("—", 1)[0]
    tokens = [token.strip().lower() for token in left.split() if token.strip()]
    known_supertypes = {"basic", "legendary", "snow", "world", "ongoing"}

    supertypes: list[str] = []
    card_types: list[str] = []
    for token in tokens:
        if token in known_supertypes:
            supertypes.append(token)
        else:
            card_types.append(token)

    return sorted(set(supertypes)), sorted(set(card_types))
