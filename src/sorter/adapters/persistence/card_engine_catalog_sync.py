from __future__ import annotations

from dataclasses import dataclass
import importlib
from pathlib import Path
import sys
from types import ModuleType


_KNOWN_CARD_TYPES = {
    "artifact",
    "battle",
    "conspiracy",
    "creature",
    "dungeon",
    "enchantment",
    "instant",
    "kindred",
    "land",
    "phenomenon",
    "plane",
    "planeswalker",
    "scheme",
    "sorcery",
    "tribal",
    "vanguard",
}

_KNOWN_SUPERTYPES = {
    "basic",
    "elite",
    "hero",
    "host",
    "kindred",
    "legendary",
    "ongoing",
    "snow",
    "world",
}


@dataclass(frozen=True)
class CardEngineCatalogSyncRequest:
    name: str | None = None
    set_code: str | None = None
    collector_number: str | None = None
    scryfall_id: str | None = None
    oracle_id: str | None = None


@dataclass(frozen=True)
class CardEngineCatalogModules:
    config: ModuleType
    query: ModuleType


def load_card_engine_catalog_modules(project_root: Path) -> CardEngineCatalogModules:
    try:
        return CardEngineCatalogModules(
            config=importlib.import_module("card_engine.config"),
            query=importlib.import_module("card_engine.catalog.query"),
        )
    except ModuleNotFoundError as exc:
        if exc.name and not exc.name.startswith("card_engine"):
            raise RuntimeError(
                "Card-engine catalog query support is unavailable. Install the vendored submodule with "
                "`pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`."
            ) from exc

    submodule_src = project_root / "third_party" / "fuzzy-enigma-card-recognition" / "src"
    if not submodule_src.exists():
        raise RuntimeError(f"Vendored card_engine source not found at {submodule_src}")
    src_str = str(submodule_src)
    if src_str not in sys.path:
        sys.path.insert(0, src_str)
    importlib.invalidate_caches()
    return CardEngineCatalogModules(
        config=importlib.import_module("card_engine.config"),
        query=importlib.import_module("card_engine.catalog.query"),
    )


def load_offline_catalog_query(project_root: Path, *, config_path: Path | None = None):
    modules = load_card_engine_catalog_modules(project_root)
    config = modules.config.load_engine_config(str(config_path)) if config_path is not None else modules.config.load_engine_config()
    return modules.query.OfflineCatalogQuery.from_sqlite(config.catalog_path)


def resolve_catalog_card(query, request: CardEngineCatalogSyncRequest) -> dict[str, object]:
    if not any((request.name, request.set_code, request.collector_number, request.scryfall_id, request.oracle_id)):
        raise ValueError("Catalog sync request must include at least one identifying field.")

    identity = query.resolve_card_identity(
        name_query=request.name,
        oracle_id=request.oracle_id,
        scryfall_id=request.scryfall_id,
        set_code=request.set_code,
        collector_number=request.collector_number,
    )
    if identity is None:
        raise LookupError(f"Unable to resolve card identity for request: {request}")

    printing = _resolve_printing(query, identity, request)
    if printing is None:
        raise LookupError(f"Unable to resolve a printed card for request: {request}")

    oracle = identity.get("oracle")
    if oracle is None:
        oracle = query.get_oracle_card(printing.oracle_id)
    if oracle is None:
        raise LookupError(f"Unable to resolve oracle data for request: {request}")

    card_types, supertypes = _parse_type_line(printing.type_line or oracle.type_line)
    colors = _normalize_symbols(printing.colors or oracle.colors)
    color_identity = _normalize_symbols(printing.color_identity or oracle.color_identity)

    return {
        "name": printing.name,
        "scryfall_id": printing.scryfall_id.lower(),
        "oracle_id": printing.oracle_id.lower(),
        "set_code": printing.set_code.lower() if printing.set_code else None,
        "collector_number": printing.collector_number,
        "rarity": printing.rarity.lower() if isinstance(printing.rarity, str) and printing.rarity else None,
        "colors": colors,
        "color_identity": color_identity,
        "card_types": card_types,
        "supertypes": supertypes,
        "is_land": "land" in card_types,
        "is_basic_land": "land" in card_types and "basic" in supertypes,
        "mana_value": None,
        "market_price_usd": None,
    }


def _resolve_printing(query, identity: dict[str, object], request: CardEngineCatalogSyncRequest):
    if request.scryfall_id:
        return query.get_printed_card(request.scryfall_id)

    printings = identity.get("printings")
    if not isinstance(printings, list):
        printing = identity.get("printing")
        return printing

    filtered = list(printings)
    if request.set_code:
        filtered = [
            printing
            for printing in filtered
            if isinstance(printing.set_code, str) and printing.set_code.lower() == request.set_code.lower()
        ]
    if request.collector_number:
        filtered = [
            printing
            for printing in filtered
            if str(printing.collector_number or "").lower() == str(request.collector_number).lower()
        ]
    if not filtered:
        return None
    filtered.sort(key=lambda printing: (_collector_sort_key(printing.collector_number), printing.scryfall_id))
    return filtered[0]


def _collector_sort_key(value: str | None) -> tuple[int, str]:
    if value is None:
        return (10**9, "")
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    if digits:
        return (int(digits), str(value))
    return (10**9, str(value))


def _normalize_symbols(values: tuple[str, ...] | list[str] | None) -> list[str]:
    if not values:
        return []
    return sorted({str(value).strip().lower() for value in values if str(value).strip()})


def _parse_type_line(type_line: str | None) -> tuple[list[str], list[str]]:
    if not isinstance(type_line, str) or not type_line.strip():
        return [], []
    card_types: set[str] = set()
    supertypes: set[str] = set()
    for face in type_line.split("//"):
        left = face.split("—", 1)[0].strip()
        for token in left.split():
            normalized = token.strip().lower()
            if not normalized:
                continue
            if normalized in _KNOWN_CARD_TYPES:
                card_types.add(normalized)
            elif normalized in _KNOWN_SUPERTYPES:
                supertypes.add(normalized)
    return sorted(card_types), sorted(supertypes)
