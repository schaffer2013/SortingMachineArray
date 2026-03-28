from __future__ import annotations

from pathlib import Path
import argparse
import json
import random
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from sorter.adapters.persistence.sim_card_list_loader import load_catalog_image_candidates


VERBOSE = True


def _vlog(message: str) -> None:
    if VERBOSE:
        print(f"[verbose] {message}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add locally available random cards to config/sim_card_lists/default_cards.json "
            "until the total card count reaches the target."
        )
    )
    parser.add_argument("target", type=int, help="Target total number of cards (sum of entry counts)")
    parser.add_argument(
        "sets",
        nargs="*",
        default=None,
        help="Optional list of set codes to restrict random selection (example: FDN EOC IMA).",
    )
    return parser.parse_args()


def _normalize_set(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _entry_set_id(entry: dict) -> str | None:
    set_id = entry.get("set")
    if set_id is None:
        set_id = entry.get("setId")
    if set_id is None:
        return None
    return _normalize_set(str(set_id))


def _load_default_cards(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _total_cards(entries: list[dict]) -> int:
    return sum(int(entry.get("count", 0)) for entry in entries)


def _find_matching_entry(entries: list[dict], card_name: str, set_id: str | None) -> dict | None:
    for entry in entries:
        if str(entry.get("name", "")).strip() != card_name:
            continue
        if _entry_set_id(entry) == set_id:
            return entry
    return None


def _choose_local_candidates(allowed_sets: set[str] | None) -> list[tuple[str, str | None]]:
    candidates = []
    for record in load_catalog_image_candidates(PROJECT_ROOT / "data" / "card_catalog" / "cards.json"):
        if allowed_sets is not None and record.set_id not in allowed_sets:
            continue
        candidates.append((record.name, record.set_id))
    return candidates


def _add_random_cards(payload: dict, target: int, allowed_sets: set[str] | None) -> int:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("default_cards.json must contain an 'entries' list")

    current_total = _total_cards(entries)
    if current_total >= target:
        return 0

    needed = target - current_total
    candidates = _choose_local_candidates(allowed_sets)
    if not candidates:
        raise RuntimeError("No locally available catalog-backed image candidates matched the requested set filter.")

    random_seed = int(payload.get("random_seed", 42))
    rng = random.Random(random_seed)
    rng.shuffle(candidates)
    _vlog(
        f"Starting local fill: current_total={current_total}, target={target}, "
        f"needed={needed}, candidate_pool={len(candidates)}"
    )

    added = 0
    cursor = 0
    while added < needed:
        if cursor >= len(candidates):
            cursor = 0
            rng.shuffle(candidates)
        card_name, set_id = candidates[cursor]
        cursor += 1

        existing = _find_matching_entry(entries, card_name=card_name, set_id=set_id)
        if existing is not None:
            existing["count"] = int(existing.get("count", 0)) + 1
            _vlog(f"Incremented existing entry: '{card_name}' [{set_id or 'no-set'}] -> count={existing['count']}")
        else:
            entry = {"name": card_name, "count": 1}
            if set_id:
                entry["set"] = set_id.upper()
            entries.append(entry)
            _vlog(f"Added new local entry: '{card_name}' [{set_id or 'no-set'}]")
        added += 1

    return added


def main() -> int:
    args = _parse_args()
    if args.target <= 0:
        raise ValueError("target must be > 0")

    cards_path = PROJECT_ROOT / "config" / "sim_card_lists" / "default_cards.json"

    allowed_sets: set[str] | None = None
    if args.sets:
        normalized_values = {normalized for value in args.sets if (normalized := _normalize_set(value)) is not None}
        allowed_sets = normalized_values or None

    payload = _load_default_cards(cards_path)
    added = _add_random_cards(payload=payload, target=args.target, allowed_sets=allowed_sets)
    if added > 0:
        cards_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    final_total = _total_cards(payload.get("entries", []))
    used_sets = "None" if allowed_sets is None else ",".join(sorted(value.upper() for value in allowed_sets))
    print({"path": str(cards_path), "added": added, "final_total": final_total, "sets": used_sets, "source": "local_catalog"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
