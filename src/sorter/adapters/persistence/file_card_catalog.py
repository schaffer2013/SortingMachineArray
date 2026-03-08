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
            card = _normalize_card_meta(item)
            cards[card.name] = card
        return cards

    def get_card_meta(self, name: str) -> CardMeta | None:
        return self._cards.get(name)

    def all_cards(self) -> list[CardMeta]:
        return list(self._cards.values())


def _normalize_card_meta(item: dict) -> CardMeta:
    card_types = _normalize_list(item.get("card_types"))
    supertypes = _normalize_list(item.get("supertypes"))
    colors = _normalize_list(item.get("colors"))
    color_identity = _normalize_list(item.get("color_identity"))

    # Legacy migration support for older catalog shape.
    legacy_card_type = item.get("card_type")
    if not card_types and isinstance(legacy_card_type, str) and legacy_card_type.strip():
        normalized = legacy_card_type.strip().lower()
        if normalized in {"basic land", "non-basic land", "land"}:
            card_types = ["land"]
            if normalized == "basic land":
                supertypes = sorted(set(supertypes + ["basic"]))
        else:
            card_types = [normalized]

    legacy_color = item.get("color")
    if not colors and isinstance(legacy_color, str):
        colors = _normalize_legacy_color(legacy_color)

    is_land = bool(item.get("is_land", "land" in card_types))
    is_basic_land = bool(item.get("is_basic_land", is_land and "basic" in supertypes))

    mana_value = _to_number_or_none(item.get("mana_value"))
    market_price_usd = _to_float_or_none(item.get("market_price_usd"))

    return CardMeta(
        name=str(item["name"]),
        oracle_id=_normalize_optional_text(
            item.get("oracle_id")
            or item.get("scryfall_oracle_id")
            or item.get("oracleId")
        ),
        rarity=_normalize_optional_text(item.get("rarity")),
        colors=colors,
        color_identity=color_identity,
        card_types=card_types,
        supertypes=supertypes,
        is_land=is_land,
        is_basic_land=is_basic_land,
        mana_value=mana_value,
        market_price_usd=market_price_usd,
        sort_rank=_to_int_or_none(item.get("sort_rank")),
    )


def _normalize_optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip().lower()
    return stripped or None


def _normalize_list(value: object) -> list[str]:
    if isinstance(value, list):
        return sorted({str(item).strip().lower() for item in value if str(item).strip()})
    if isinstance(value, str) and value.strip():
        return [value.strip().lower()]
    return []


def _normalize_legacy_color(value: str) -> list[str]:
    normalized = value.strip().lower()
    if normalized in {"default", "colorless", ""}:
        return []
    if normalized == "multi":
        return ["w", "u"]

    mapping = {
        "white": "w",
        "blue": "u",
        "black": "b",
        "red": "r",
        "green": "g",
    }
    if normalized in mapping:
        return [mapping[normalized]]
    return [normalized]


def _to_number_or_none(value: object) -> float | int | None:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        try:
            number = float(value)
        except ValueError:
            return None
        return int(number) if number.is_integer() else number
    return None


def _to_float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _to_int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
