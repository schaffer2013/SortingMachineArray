from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from sorter.adapters.persistence.card_engine_catalog_sync import (
    CardEngineCatalogSyncRequest,
    load_offline_catalog_query,
    resolve_catalog_card,
)
from sorter.adapters.persistence.sim_card_list_loader import load_sim_card_list


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _card_name_from_instance(value: str) -> str:
    base = value.split("#", 1)[0]
    return base.strip().replace("_", " ")


@dataclass(frozen=True)
class CardImageRef:
    name: str
    set_id: str | None


def _extract_cards_from_fixture(fixture_path: Path) -> list[CardImageRef]:
    if not fixture_path.exists():
        return []
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    set_map_raw = data.get("card_set_by_instance_id", {})
    set_map = {
        str(card_id): str(set_id).strip().lower()
        for card_id, set_id in set_map_raw.items()
        if isinstance(card_id, str) and isinstance(set_id, str) and set_id.strip()
    }
    cards: list[CardImageRef] = []
    for pile in data.get("piles", []):
        for raw_card in pile.get("cards", []):
            card_id = str(raw_card)
            cards.append(CardImageRef(name=_card_name_from_instance(card_id), set_id=set_map.get(card_id)))
    return cards


def _extract_cards_from_sim_card_list(sim_card_list_path: Path | None) -> list[CardImageRef]:
    if sim_card_list_path is None or not sim_card_list_path.exists():
        return []
    config = load_sim_card_list(sim_card_list_path)
    refs: list[CardImageRef] = []
    for entry in config.entries:
        refs.append(CardImageRef(name=entry.name, set_id=entry.set_id))
    return refs


def _unique_refs_preserving_order(values: list[CardImageRef]) -> list[CardImageRef]:
    out: list[CardImageRef] = []
    seen: set[tuple[str, str]] = set()
    for value in values:
        key = (_normalize_name(value.name), (value.set_id or "").lower())
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _existing_image_index(image_dir: Path) -> dict[tuple[str, str], Path]:
    index: dict[tuple[str, str], Path] = {}
    if not image_dir.exists():
        return index
    for file_path in image_dir.rglob("*"):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        try:
            relative_parent = file_path.relative_to(image_dir).parent
            if relative_parent == Path("."):
                set_id = "default"
            else:
                set_id = relative_parent.parts[0].lower()
        except ValueError:
            set_id = "default"
        index[(set_id, _normalize_name(file_path.stem))] = file_path
    return index


def _has_image_for_ref(index: dict[tuple[str, str], Path], card_ref: CardImageRef) -> bool:
    normalized_name = _normalize_name(card_ref.name)
    if card_ref.set_id:
        return (card_ref.set_id.lower(), normalized_name) in index
    return any(name == normalized_name for _, name in index.keys())


def _safe_filename(card_name: str) -> str:
    cleaned = card_name.replace("/", "_").replace(" ", "_")
    cleaned = cleaned.replace("?", "").replace(":", "")
    return cleaned


def _download_missing_cards(
    card_refs: list[CardImageRef],
    image_dir: Path,
    *,
    project_root: Path,
) -> tuple[int, int]:
    query = load_offline_catalog_query(project_root)
    image_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failed = 0

    for card_ref in card_refs:
        card_name = card_ref.name
        try:
            card_data = _resolve_catalog_card_for_image(query, card_name=card_name, set_id=card_ref.set_id)
            image_url = card_data.get("image_url")
            if image_url is None:
                failed += 1
                continue

            with urlopen(image_url, timeout=30) as response:
                content = response.read()

            set_id = str(card_data.get("set_code", "")).strip().lower() or (card_ref.set_id or "default").lower()
            target_dir = image_dir / set_id
            target_dir.mkdir(parents=True, exist_ok=True)
            file_path = target_dir / f"{_safe_filename(card_name)}.jpg"
            file_path.write_bytes(content)
            downloaded += 1
        except (HTTPError, URLError, TimeoutError, OSError):
            failed += 1
        except Exception:
            failed += 1

    return downloaded, failed


def _resolve_catalog_card_for_image(query, *, card_name: str, set_id: str | None) -> dict[str, object]:
    request = CardEngineCatalogSyncRequest(
        name=card_name,
        set_code=set_id,
    )
    try:
        return resolve_catalog_card(query, request)
    except LookupError:
        if not set_id:
            raise
    return resolve_catalog_card(query, CardEngineCatalogSyncRequest(name=card_name))


def _write_log(log_path: Path, cards: list[str], missing: list[str]) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Simulated card list",
        f"total_cards={len(cards)}",
        f"missing_images={len(missing)}",
        "",
        "[cards]",
        *cards,
        "",
        "[missing_images]",
        *missing,
        "",
    ]
    log_path.write_text("\n".join(lines), encoding="utf-8")


@dataclass(frozen=True)
class SyncSummary:
    total_cards: int
    missing_before: int
    downloaded: int
    failed: int
    missing_after: int
    log_path: Path


def sync_simulated_images(
    project_root: Path,
    fixture_path: Path,
    image_dir: Path,
    log_path: Path,
    sim_card_list_path: Path | None = None,
    auto_fetch: bool = True,
) -> SyncSummary:
    cards: list[CardImageRef] = []
    cards.extend(_extract_cards_from_fixture(fixture_path))
    cards.extend(_extract_cards_from_sim_card_list(sim_card_list_path))
    cards = _unique_refs_preserving_order(cards)

    index = _existing_image_index(image_dir)
    missing_before = [card for card in cards if not _has_image_for_ref(index, card)]

    downloaded = 0
    failed = 0
    if auto_fetch and missing_before:
        downloaded, failed = _download_missing_cards(
            missing_before,
            image_dir,
            project_root=project_root,
        )

    refreshed = _existing_image_index(image_dir)
    missing_after = [card for card in cards if not _has_image_for_ref(refreshed, card)]

    card_names = [card.name if card.set_id is None else f"{card.name} [{card.set_id}]" for card in cards]
    missing_names = [card.name if card.set_id is None else f"{card.name} [{card.set_id}]" for card in missing_after]

    _write_log(log_path, card_names, missing_names)
    return SyncSummary(
        total_cards=len(cards),
        missing_before=len(missing_before),
        downloaded=downloaded,
        failed=failed,
        missing_after=len(missing_after),
        log_path=log_path,
    )
