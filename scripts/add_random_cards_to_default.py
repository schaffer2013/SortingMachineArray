from __future__ import annotations

from pathlib import Path
import argparse
import json

import requests
import scrython


# Toggle detailed runtime logs without changing CLI arguments.
VERBOSE = True


def _vlog(message: str) -> None:
    if VERBOSE:
        print(f"[verbose] {message}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Add random cards to config/sim_card_lists/default_cards.json until total card count "
            "reaches the target."
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


def _load_default_cards(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _total_cards(entries: list[dict]) -> int:
    return sum(int(entry.get("count", 0)) for entry in entries)


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


def _safe_filename(card_name: str) -> str:
    cleaned = card_name.replace("/", "_").replace(" ", "_")
    cleaned = cleaned.replace("?", "").replace(":", "")
    return cleaned


def _build_scryfall_query(allowed_sets: set[str] | None) -> str:
    base = "game:paper"
    if not allowed_sets:
        return base
    set_terms = [f"set:{set_id}" for set_id in sorted(allowed_sets)]
    return f"{base} ({' or '.join(set_terms)})"


def _extract_image_url(payload: dict) -> str | None:
    image_uris = payload.get("image_uris")
    if isinstance(image_uris, dict):
        image_url = image_uris.get("normal") or image_uris.get("large")
        if isinstance(image_url, str) and image_url.strip():
            return image_url

    faces = payload.get("card_faces")
    if isinstance(faces, list):
        for face in faces:
            if not isinstance(face, dict):
                continue
            face_uris = face.get("image_uris")
            if not isinstance(face_uris, dict):
                continue
            image_url = face_uris.get("normal") or face_uris.get("large")
            if isinstance(image_url, str) and image_url.strip():
                return image_url
    return None


def _scryfall_payload(card_data: object) -> dict | None:
    direct_payload = getattr(card_data, "_scryfall_data", None)
    if isinstance(direct_payload, dict):
        return direct_payload

    # Some scrython versions expose normalized values as attributes instead of raw JSON.
    attr_payload: dict[str, object] = {}
    for key in ("name", "set", "image_uris", "card_faces"):
        value = getattr(card_data, key, None)
        if value is not None:
            attr_payload[key] = value
    if attr_payload:
        return attr_payload

    candidates = ["scryfallJson", "scryfall_json", "_json", "json"]
    for attr_name in candidates:
        payload = getattr(card_data, attr_name, None)
        if callable(payload):
            try:
                payload = payload()
            except Exception:
                continue

        if isinstance(payload, dict):
            return payload

        if isinstance(payload, str):
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    if hasattr(card_data, "__dict__") and isinstance(card_data.__dict__, dict):
        payload = card_data.__dict__.get("scryfallJson")
        if isinstance(payload, dict):
            return payload
    return None


def _fetch_random_card(query: str) -> tuple[str, str, str] | None:
    card_data = scrython.cards.Random(q=query)
    payload = _scryfall_payload(card_data)
    if payload is None:
        _vlog("Scrython returned no payload.")
        return None

    card_name = payload.get("name")
    set_id = _normalize_set(payload.get("set"))
    image_url = _extract_image_url(payload)

    if not isinstance(card_name, str) or not card_name.strip():
        _vlog("Random card payload missing valid name.")
        return None
    if set_id is None:
        _vlog("Random card payload missing valid set.")
        return None
    if image_url is None:
        _vlog(f"Random card '{card_name}' has no image URL.")
        return None

    return card_name.strip(), set_id, image_url


def _download_card_image(image_root: Path, card_name: str, set_id: str, image_url: str) -> Path:
    target_dir = image_root / set_id
    target_dir.mkdir(parents=True, exist_ok=True)
    file_path = target_dir / f"{_safe_filename(card_name)}.jpg"
    if file_path.exists():
        _vlog(f"Image already exists: {file_path}")
        return file_path

    response = requests.get(image_url, timeout=30)
    response.raise_for_status()
    file_path.write_bytes(response.content)
    _vlog(f"Downloaded image for '{card_name}' [{set_id}] -> {file_path}")
    return file_path


def _find_matching_entry(entries: list[dict], card_name: str, set_id: str | None) -> dict | None:
    for entry in entries:
        if str(entry.get("name", "")).strip() != card_name:
            continue
        if _entry_set_id(entry) == set_id:
            return entry
    return None


def _add_random_cards(payload: dict, image_root: Path, target: int, allowed_sets: set[str] | None) -> int:
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("default_cards.json must contain an 'entries' list")

    current_total = _total_cards(entries)
    if current_total >= target:
        return 0

    needed = target - current_total
    query = _build_scryfall_query(allowed_sets)
    _vlog(f"Starting random fill: current_total={current_total}, target={target}, needed={needed}, query='{query}'")
    added = 0
    attempts = 0
    max_attempts = max(needed * 10, 25)

    while added < needed and attempts < max_attempts:
        attempts += 1
        try:
            _vlog(f"Attempt {attempts}/{max_attempts}")
            random_card = _fetch_random_card(query)
            if random_card is None:
                continue
            card_name, set_id, image_url = random_card
            _download_card_image(image_root=image_root, card_name=card_name, set_id=set_id, image_url=image_url)
        except Exception as exc:
            _vlog(f"Attempt {attempts} failed with {type(exc).__name__}: {exc}")
            continue

        existing = _find_matching_entry(entries, card_name=card_name, set_id=set_id)
        if existing is not None:
            existing["count"] = int(existing.get("count", 0)) + 1
            _vlog(f"Incremented existing entry: '{card_name}' [{set_id}] -> count={existing['count']}")
        else:
            entries.append({"name": card_name, "set": set_id.upper(), "count": 1})
            _vlog(f"Added new entry: '{card_name}' [{set_id}]")
        added += 1

    if added < needed:
        raise RuntimeError(
            f"Unable to add enough random cards. Requested {needed}, added {added}, attempts {attempts}."
        )
    return added


def main() -> int:
    args = _parse_args()
    if args.target <= 0:
        raise ValueError("target must be > 0")

    root = Path(__file__).resolve().parents[1]
    cards_path = root / "config" / "sim_card_lists" / "default_cards.json"
    image_root = root / "SimulatedCardImages"

    allowed_sets: set[str] | None = None
    if args.sets:
        normalized_values: set[str] = set()
        for value in args.sets:
            normalized = _normalize_set(value)
            if normalized is not None:
                normalized_values.add(normalized)
        allowed_sets = normalized_values
        if not allowed_sets:
            allowed_sets = None

    payload = _load_default_cards(cards_path)
    added = _add_random_cards(payload=payload, image_root=image_root, target=args.target, allowed_sets=allowed_sets)
    if added > 0:
        cards_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    final_total = _total_cards(payload.get("entries", []))
    used_sets = "None" if allowed_sets is None else ",".join(sorted(value.upper() for value in allowed_sets))
    print({"path": str(cards_path), "added": added, "final_total": final_total, "sets": used_sets})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())