from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.adapters.persistence.card_engine_catalog_sync import (
    CardEngineCatalogSyncRequest,
    load_offline_catalog_query,
    resolve_catalog_card,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync the parent card catalog from the vendored card-engine offline catalog.")
    parser.add_argument(
        "--sim-card-list",
        default="config/sim_card_lists/default_cards.json",
        help="Parent sim-card-list JSON to resolve through the vendored offline catalog.",
    )
    parser.add_argument(
        "--card-engine-config",
        default="config/card_engine/benchmark.engine.json",
        help="Parent-owned card-engine config used to locate the vendored offline catalog.",
    )
    parser.add_argument(
        "--output",
        default="data/card_catalog/cards.json",
        help="Output JSON path for the parent card catalog snapshot.",
    )
    args = parser.parse_args()

    sim_card_list_path = PROJECT_ROOT / args.sim_card_list
    card_engine_config_path = PROJECT_ROOT / args.card_engine_config
    output_path = PROJECT_ROOT / args.output

    raw = json.loads(sim_card_list_path.read_text(encoding="utf-8"))
    entries = raw.get("entries", [])
    query = load_offline_catalog_query(PROJECT_ROOT, config_path=card_engine_config_path)

    resolved_cards: list[dict[str, object]] = []
    seen_keys: set[tuple[str | None, str | None, str | None, str | None, str | None]] = set()
    for item in entries:
        if not isinstance(item, dict):
            continue
        request = CardEngineCatalogSyncRequest(
            name=_clean_optional(item.get("name")),
            set_code=_clean_optional(item.get("set") or item.get("set_code") or item.get("setId")),
            collector_number=_clean_optional(item.get("collector_number")),
            scryfall_id=_clean_optional(item.get("scryfall_id")),
            oracle_id=_clean_optional(item.get("oracle_id")),
        )
        dedupe_key = (
            request.name,
            request.set_code.lower() if request.set_code else None,
            request.collector_number,
            request.scryfall_id.lower() if request.scryfall_id else None,
            request.oracle_id.lower() if request.oracle_id else None,
        )
        if dedupe_key in seen_keys:
            continue
        seen_keys.add(dedupe_key)
        resolved_cards.append(resolve_catalog_card(query, request))

    payload = {
        "version": 2,
        "source": "vendored_card_engine_offline_catalog",
        "source_sim_card_list": str(sim_card_list_path.relative_to(PROJECT_ROOT)).replace("\\", "/"),
        "cards": resolved_cards,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"wrote={output_path}")
    print(f"cards={len(resolved_cards)}")
    return 0


def _clean_optional(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped or None


if __name__ == "__main__":
    raise SystemExit(main())
