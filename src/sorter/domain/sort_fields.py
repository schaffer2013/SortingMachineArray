from __future__ import annotations

from sorter.domain.models import CardMeta

_COLOR_TO_BUCKET = {
    "w": "white",
    "u": "blue",
    "b": "black",
    "r": "red",
    "g": "green",
    "white": "white",
    "blue": "blue",
    "black": "black",
    "red": "red",
    "green": "green",
}


def primary_bucket(card_meta: CardMeta) -> str:
    if card_meta.is_basic_land:
        return "basic_land"
    if card_meta.is_land:
        return "nonbasic_land"

    normalized_colors = _normalize_colors(card_meta)
    if len(normalized_colors) == 1:
        return _COLOR_TO_BUCKET.get(normalized_colors[0], "colorless")
    if len(normalized_colors) > 1:
        return "multicolor"
    return "colorless"


def type_bucket(card_meta: CardMeta) -> str:
    if card_meta.is_basic_land:
        return "basic_land"
    if card_meta.is_land:
        return "nonbasic_land"
    if not card_meta.card_types:
        return "other"

    normalized_types = {card_type.strip().lower() for card_type in card_meta.card_types if card_type}
    for label in (
        "creature",
        "artifact",
        "battle",
        "instant",
        "sorcery",
        "planeswalker",
        "enchantment",
    ):
        if label in normalized_types:
            return label
    return "other"


def color_count(card_meta: CardMeta) -> int:
    return len(_normalize_colors(card_meta))


def derive_fields(card_meta: CardMeta) -> dict[str, object]:
    return {
        "primary_bucket": primary_bucket(card_meta),
        "type_bucket": type_bucket(card_meta),
        "color_count": color_count(card_meta),
    }


def _normalize_colors(card_meta: CardMeta) -> list[str]:
    source = card_meta.colors if card_meta.colors else card_meta.color_identity
    normalized = [color.strip().lower() for color in source if color and color.strip()]
    deduped = sorted(set(normalized))
    return deduped
