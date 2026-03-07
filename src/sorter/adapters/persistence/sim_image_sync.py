from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re


def _normalize_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _card_name_from_instance(value: str) -> str:
    base = value.split("#", 1)[0]
    return base.strip().replace("_", " ")


def _extract_cards_from_fixture(fixture_path: Path) -> list[str]:
    if not fixture_path.exists():
        return []
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    cards: list[str] = []
    for pile in data.get("piles", []):
        for raw_card in pile.get("cards", []):
            cards.append(_card_name_from_instance(str(raw_card)))
    return cards


def _extract_cards_from_image_piles(image_piles_path: Path) -> list[str]:
    if not image_piles_path.exists():
        return []
    image_piles = json.loads(image_piles_path.read_text(encoding="utf-8"))
    cards: list[str] = []
    for pile in image_piles:
        for image_name in pile:
            stem = Path(str(image_name)).stem
            cards.append(stem.replace("_", " "))
    return cards


def _extract_literal_cards_from_python(py_path: Path) -> list[str]:
    if not py_path.exists():
        return []
    text = py_path.read_text(encoding="utf-8")
    cards: list[str] = []
    for match in re.findall(r"['\"]([^'\"]+\.(?:jpg|jpeg|png))['\"]", text, flags=re.IGNORECASE):
        cards.append(Path(match).stem.replace("_", " "))
    for match in re.findall(r"['\"]([^'\"]+#[0-9]+)['\"]", text):
        cards.append(_card_name_from_instance(match))
    return cards


def _unique_preserving_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _normalize_name(value)
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _existing_image_index(image_dir: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}
    if not image_dir.exists():
        return index
    for file_path in image_dir.iterdir():
        if file_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        index[_normalize_name(file_path.stem)] = file_path
    return index


def _safe_filename(card_name: str) -> str:
    cleaned = card_name.replace("/", "_").replace(" ", "_")
    cleaned = cleaned.replace("?", "").replace(":", "")
    return cleaned


def _download_missing_cards(card_names: list[str], image_dir: Path) -> tuple[int, int]:
    import requests
    import scrython

    image_dir.mkdir(parents=True, exist_ok=True)
    downloaded = 0
    failed = 0

    for card_name in card_names:
        try:
            card_data = scrython.cards.Named(fuzzy=card_name)
            image_url = _extract_image_url(card_data)
            if image_url is None:
                failed += 1
                continue

            response = requests.get(image_url, timeout=30)
            response.raise_for_status()

            file_path = image_dir / f"{_safe_filename(card_name)}.jpg"
            file_path.write_bytes(response.content)
            downloaded += 1
        except Exception:
            failed += 1

    return downloaded, failed


def _extract_image_url(card_data: object) -> str | None:
    # Scryfall may provide images on the card itself or in card_faces for DFC cards.
    image_uris = None
    try:
        image_uris = card_data.image_uris()  # type: ignore[attr-defined]
    except Exception:
        image_uris = None

    if isinstance(image_uris, dict):
        image_url = image_uris.get("normal") or image_uris.get("large")
        if image_url:
            return str(image_url)

    raw_payload = getattr(card_data, "scryfallJson", None)
    if isinstance(raw_payload, dict):
        root_uris = raw_payload.get("image_uris")
        if isinstance(root_uris, dict):
            image_url = root_uris.get("normal") or root_uris.get("large")
            if image_url:
                return str(image_url)

        faces = raw_payload.get("card_faces")
        if isinstance(faces, list):
            for face in faces:
                if not isinstance(face, dict):
                    continue
                face_uris = face.get("image_uris")
                if not isinstance(face_uris, dict):
                    continue
                image_url = face_uris.get("normal") or face_uris.get("large")
                if image_url:
                    return str(image_url)
    return None


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
    pile_manager_path: Path | None = None,
    image_piles_path: Path | None = None,
    auto_fetch: bool = True,
) -> SyncSummary:
    cards: list[str] = []
    cards.extend(_extract_cards_from_fixture(fixture_path))
    if image_piles_path is not None:
        cards.extend(_extract_cards_from_image_piles(image_piles_path))
    if pile_manager_path is not None:
        cards.extend(_extract_literal_cards_from_python(pile_manager_path))
    cards = _unique_preserving_order(cards)

    index = _existing_image_index(image_dir)
    missing_before = [card for card in cards if _normalize_name(card) not in index]

    downloaded = 0
    failed = 0
    if auto_fetch and missing_before:
        downloaded, failed = _download_missing_cards(missing_before, image_dir)

    refreshed = _existing_image_index(image_dir)
    missing_after = [card for card in cards if _normalize_name(card) not in refreshed]

    _write_log(log_path, cards, missing_after)
    return SyncSummary(
        total_cards=len(cards),
        missing_before=len(missing_before),
        downloaded=downloaded,
        failed=failed,
        missing_after=len(missing_after),
        log_path=log_path,
    )
