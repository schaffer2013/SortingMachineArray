from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import cv2
import numpy as np

try:  # pragma: no cover - import path is environment-dependent
    from card_engine.retrieval.embeddings import create_embedder
    from card_engine.retrieval.index import VisualIndex
except ModuleNotFoundError:  # pragma: no cover - fallback for the vendored submodule layout
    import sys

    _REPO_ROOT = Path(__file__).resolve().parents[3]
    _VENDORED_SRC = _REPO_ROOT / "third_party" / "fuzzy-enigma-card-recognition" / "src"
    if _VENDORED_SRC.exists():
        src_str = str(_VENDORED_SRC)
        if src_str not in sys.path:
            sys.path.insert(0, src_str)
    from card_engine.retrieval.embeddings import create_embedder  # type: ignore
    from card_engine.retrieval.index import VisualIndex  # type: ignore


ProgressCallback = Callable[[int, int, str | None], None]

DEFAULT_VISUAL_INDEX_REFRESH_DAYS = 7
VISUAL_INDEX_REFRESH_DAY_OPTIONS = (1, 3, 7, 14, 30, 60, 90)
DEFAULT_VISUAL_INDEX_SOURCE_PATH = Path("data/catalog/default-cards.json")
DEFAULT_VISUAL_INDEX_PATH = Path("data/index/card_embeddings.npz")
DEFAULT_VISUAL_METADATA_PATH = Path("data/index/card_embeddings.jsonl")
DEFAULT_VISUAL_INDEX_STATE_PATH = Path("data/index/visual_index_state.json")
DEFAULT_VISUAL_INDEX_REFERENCE_DIR = Path("data/index/reference_images")
REQUEST_HEADERS = {
    "User-Agent": "card-sorter-testbed/0.8.10 (+visual index refresh)",
    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
}


@dataclass(frozen=True)
class VisualIndexBuildResult:
    index_path: Path
    metadata_path: Path
    reference_dir: Path
    source_catalog_path: Path
    card_count: int
    downloaded_count: int
    reused_count: int
    updated_at_utc: str
    refresh_days: int


@dataclass
class VisualIndexRefreshManager:
    project_root: Path
    config_path: Path | None = None
    source_catalog_path: Path | None = None
    index_path: Path | None = None
    metadata_path: Path | None = None
    state_path: Path | None = None
    reference_dir: Path | None = None
    model: str = "opencv_v1"
    model_path: str | None = None
    overwrite_downloads: bool = False

    def __post_init__(self) -> None:
        self.project_root = Path(self.project_root)
        self.config_path = Path(self.config_path) if self.config_path is not None else self.project_root / "config/card_engine/engine.json"
        self.source_catalog_path = Path(self.source_catalog_path) if self.source_catalog_path is not None else self.project_root / DEFAULT_VISUAL_INDEX_SOURCE_PATH
        self.index_path = Path(self.index_path) if self.index_path is not None else self.project_root / DEFAULT_VISUAL_INDEX_PATH
        self.metadata_path = Path(self.metadata_path) if self.metadata_path is not None else self.project_root / DEFAULT_VISUAL_METADATA_PATH
        self.state_path = Path(self.state_path) if self.state_path is not None else self.project_root / DEFAULT_VISUAL_INDEX_STATE_PATH
        self.reference_dir = Path(self.reference_dir) if self.reference_dir is not None else self.project_root / DEFAULT_VISUAL_INDEX_REFERENCE_DIR
        self._lock = threading.RLock()
        self._refresh_thread: threading.Thread | None = None
        self._refresh_error: str | None = None

    def refresh_days(self) -> int:
        return load_visual_index_policy(self.config_path)

    def status(self, *, running: bool = False, auto_start: bool = False) -> dict[str, Any]:
        with self._lock:
            refresh_thread_alive = self._refresh_thread.is_alive() if self._refresh_thread is not None else False
            state = self._read_state()
            refresh_days = self.refresh_days()
            needs_refresh, age_days, reason = self._needs_refresh(refresh_days, state)
            refreshing = bool(state.get("refreshing")) or refresh_thread_alive
            ready = self.index_path.is_file() and self.metadata_path.is_file() and not needs_refresh

            if auto_start and needs_refresh and not running and not refreshing:
                self._start_background_refresh(force=False, reason=reason)
                refreshing = True

            return {
                "configured_refresh_days": refresh_days,
                "refresh_options": list(VISUAL_INDEX_REFRESH_DAY_OPTIONS),
                "project_root": str(self.project_root),
                "config_path": str(self.config_path),
                "source_catalog_path": str(self.source_catalog_path),
                "index_path": str(self.index_path),
                "metadata_path": str(self.metadata_path),
                "state_path": str(self.state_path),
                "reference_dir": str(self.reference_dir),
                "updated_at_utc": state.get("updated_at_utc"),
                "last_started_at_utc": state.get("last_started_at_utc"),
                "last_finished_at_utc": state.get("last_finished_at_utc"),
                "age_days": age_days,
                "source_card_count": state.get("source_card_count"),
                "indexed_card_count": state.get("indexed_card_count"),
                "progress_current": state.get("progress_current"),
                "progress_total": state.get("progress_total"),
                "progress_percent": state.get("progress_percent"),
                "progress_message": state.get("progress_message"),
                "needs_refresh": needs_refresh,
                "running": running,
                "refreshing": refreshing,
                "ready": ready,
                "progress": self._progress_payload(state, refreshing=refreshing),
                "action": state.get("last_action") or ("refreshing" if refreshing else ("stale" if needs_refresh else "reuse")),
                "message": self._status_message(
                    running=running,
                    refreshing=refreshing,
                    ready=ready,
                    needs_refresh=needs_refresh,
                    age_days=age_days,
                    reason=reason,
                    state=state,
                ),
                "last_error": self._refresh_error or state.get("last_error"),
                "source_catalog_mtime_ns": state.get("source_catalog_mtime_ns"),
                "source_catalog_size": state.get("source_catalog_size"),
            }

    def refresh(self, *, force: bool = True) -> dict[str, Any]:
        with self._lock:
            if self._refresh_thread is not None and self._refresh_thread.is_alive():
                return {
                    **self.status(running=False, auto_start=False),
                    "ok": True,
                    "message": "Visual index refresh is already running.",
                }
            self._start_background_refresh(force=force, reason="manual")
            return {
                **self.status(running=False, auto_start=False),
                "ok": True,
                "message": "Visual index refresh started.",
            }

    def maybe_refresh(self, *, running: bool, auto_start: bool = True) -> dict[str, Any]:
        return self.status(running=running, auto_start=auto_start)

    def save_policy(self, refresh_days: int) -> dict[str, Any]:
        save_visual_index_policy(self.config_path, refresh_days)
        return self.status(running=False, auto_start=False)

    def _start_background_refresh(self, *, force: bool, reason: str) -> None:
        if self._refresh_thread is not None and self._refresh_thread.is_alive():
            return
        self._refresh_error = None
        self._write_state(
            {
                **self._read_state(),
                "refreshing": True,
                "last_started_at_utc": _utc_now_iso(),
                "last_action": "refreshing" if force else reason,
                "last_error": None,
                "progress_current": 0,
                "progress_total": None,
                "progress_percent": 0.0,
                "progress_message": "Starting refresh...",
            }
        )
        self._refresh_thread = threading.Thread(
            target=self._refresh_worker,
            kwargs={"force": force, "reason": reason},
            daemon=True,
        )
        self._refresh_thread.start()

    def _refresh_worker(self, *, force: bool, reason: str) -> None:
        try:
            progress_lock = threading.Lock()
            last_reported_percent = {"value": -1.0}

            def report_progress(current: int, total: int, message: str | None = None) -> None:
                if total > 0:
                    percent = max(0.0, min(100.0, (current / total) * 100.0))
                else:
                    percent = 0.0
                if message is None:
                    message = f"Indexed {current:,}/{total:,} cards" if total > 0 else "Refreshing visual index..."
                with progress_lock:
                    if percent < 100.0 and percent - last_reported_percent["value"] < 1.0:
                        return
                    last_reported_percent["value"] = percent
                self._write_state(
                    {
                        **self._read_state(),
                        "refreshing": True,
                        "last_started_at_utc": self._read_state().get("last_started_at_utc"),
                        "last_action": reason if reason != "manual" else "manual",
                        "last_error": None,
                        "progress_current": current,
                        "progress_total": total,
                        "progress_percent": round(percent, 2),
                        "progress_message": message,
                    }
                )

            result = build_visual_index_from_catalog(
                project_root=self.project_root,
                source_catalog_path=self.source_catalog_path,
                index_path=self.index_path,
                metadata_path=self.metadata_path,
                reference_dir=self.reference_dir,
                refresh_days=self.refresh_days(),
                model=self.model,
                model_path=self.model_path,
                overwrite_downloads=self.overwrite_downloads or force,
                progress_callback=report_progress,
            )
            self._write_state(
                {
                    "updated_at_utc": result.updated_at_utc,
                    "last_started_at_utc": self._read_state().get("last_started_at_utc"),
                    "last_finished_at_utc": _utc_now_iso(),
                    "last_action": reason if reason != "manual" else "manual",
                    "refreshing": False,
                    "last_error": None,
                    "refresh_days": result.refresh_days,
                    "source_catalog_path": str(result.source_catalog_path),
                    "source_catalog_mtime_ns": result.source_catalog_path.stat().st_mtime_ns,
                    "source_catalog_size": result.source_catalog_path.stat().st_size,
                    "indexed_card_count": result.card_count,
                    "source_card_count": result.card_count,
                    "progress_current": result.card_count,
                    "progress_total": result.card_count,
                    "progress_percent": 100.0,
                    "progress_message": f"Indexed {result.card_count:,}/{result.card_count:,} cards",
                    "index_path": str(result.index_path),
                    "metadata_path": str(result.metadata_path),
                    "reference_dir": str(result.reference_dir),
                    "downloaded_count": result.downloaded_count,
                    "reused_count": result.reused_count,
                }
            )
        except Exception as exc:  # pragma: no cover - surfaced through status and API
            self._refresh_error = str(exc)
            self._write_state(
                {
                    **self._read_state(),
                    "refreshing": False,
                    "last_finished_at_utc": _utc_now_iso(),
                    "last_error": self._refresh_error,
                    "last_action": "error",
                }
            )
        finally:
            with self._lock:
                self._refresh_thread = None

    def _status_message(
        self,
        *,
        running: bool,
        refreshing: bool,
        ready: bool,
        needs_refresh: bool,
        age_days: float | None,
        reason: str,
        state: dict[str, Any],
    ) -> str:
        if refreshing:
            return "Visual index refresh is running in the background."
        if self._refresh_error or state.get("last_error"):
            return f"Visual index refresh failed: {self._refresh_error or state.get('last_error')}"
        if ready and not needs_refresh:
            if age_days is None:
                return "Visual index is ready."
            return f"Visual index is ready ({age_days:.1f} days old)."
        if running and needs_refresh:
            return "Visual index refresh is deferred while the sorter is running."
        progress = self._progress_payload(state, refreshing=refreshing)
        if refreshing and progress["percent"] is not None:
            return f"Visual index refresh is running ({progress['percent']:.1f}%)."
        if reason == "missing":
            return "Visual index is missing and will refresh when the sorter is idle."
        if reason == "stale":
            return f"Visual index is stale ({age_days:.1f} days old) and will refresh when the sorter is idle."
        if reason == "source_changed":
            return "Visual index source catalog changed and will refresh when the sorter is idle."
        return "Visual index refresh is pending."

    def _progress_payload(self, state: dict[str, Any], *, refreshing: bool) -> dict[str, Any]:
        current = state.get("progress_current")
        total = state.get("progress_total")
        percent = state.get("progress_percent")
        if percent is None and isinstance(current, int) and isinstance(total, int) and total > 0:
            percent = round((current / total) * 100.0, 2)
        if percent is None:
            percent = 0.0 if refreshing else None
        return {
            "current": current,
            "total": total,
            "percent": percent,
            "message": state.get("progress_message"),
        }

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, payload: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def _needs_refresh(self, refresh_days: int, state: dict[str, Any]) -> tuple[bool, float | None, str]:
        if not self.index_path.is_file() or not self.metadata_path.is_file():
            return True, _state_age_days(state), "missing"
        if not self.source_catalog_path.is_file():
            return True, _state_age_days(state), "source_missing"
        source_mtime_ns = self.source_catalog_path.stat().st_mtime_ns
        source_size = self.source_catalog_path.stat().st_size
        if state.get("source_catalog_mtime_ns") != source_mtime_ns or state.get("source_catalog_size") != source_size:
            return True, _state_age_days(state), "source_changed"
        age_days = _state_age_days(state)
        if age_days is None:
            return True, None, "missing"
        return age_days >= refresh_days, age_days, "stale" if age_days >= refresh_days else "fresh"


def load_visual_index_policy(config_path: str | Path | None = None) -> int:
    path = Path(config_path) if config_path is not None else None
    if path is None or not path.exists():
        return DEFAULT_VISUAL_INDEX_REFRESH_DAYS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DEFAULT_VISUAL_INDEX_REFRESH_DAYS
    if not isinstance(payload, dict):
        return DEFAULT_VISUAL_INDEX_REFRESH_DAYS
    value = payload.get("visual_index_refresh_days", DEFAULT_VISUAL_INDEX_REFRESH_DAYS)
    return _normalize_refresh_days(value)


def save_visual_index_policy(config_path: str | Path, refresh_days: int) -> None:
    path = Path(config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {}
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                payload = loaded
        except (OSError, json.JSONDecodeError):
            payload = {}
    payload["visual_index_refresh_days"] = _normalize_refresh_days(refresh_days)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def build_visual_index_from_catalog(
    *,
    project_root: str | Path,
    source_catalog_path: str | Path,
    index_path: str | Path,
    metadata_path: str | Path,
    reference_dir: str | Path,
    refresh_days: int = DEFAULT_VISUAL_INDEX_REFRESH_DAYS,
    model: str = "opencv_v1",
    model_path: str | None = None,
    overwrite_downloads: bool = False,
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> VisualIndexBuildResult:
    project_root_path = Path(project_root)
    source_path = Path(source_catalog_path)
    index_file = Path(index_path)
    metadata_file = Path(metadata_path)
    reference_root = Path(reference_dir)
    index_file.parent.mkdir(parents=True, exist_ok=True)
    metadata_file.parent.mkdir(parents=True, exist_ok=True)
    reference_root.mkdir(parents=True, exist_ok=True)

    payload = json.loads(source_path.read_text(encoding="utf-8"))
    cards = payload if isinstance(payload, list) else payload.get("cards", [])
    if not isinstance(cards, list):
        raise ValueError(f"Catalog did not contain a card list: {source_path}")

    selected_cards = [card for card in cards if isinstance(card, dict) and _extract_image_url(card)]
    selected_cards.sort(
        key=lambda card: (
            str(card.get("set") or card.get("set_code") or "").lower(),
            str(card.get("collector_number") or "").lower(),
            str(card.get("name") or "").lower(),
            str(card.get("id") or card.get("scryfall_id") or "").lower(),
        )
    )
    if limit is not None:
        selected_cards = selected_cards[: max(0, int(limit))]
    if not selected_cards:
        raise ValueError(f"No cards with image URLs were found in {source_path}")

    embedder = create_embedder(model, model_path)
    vectors: np.ndarray | None = None
    metadata: list[dict[str, Any]] = []
    downloaded = 0
    reused = 0

    for index, card in enumerate(selected_cards, start=0):
        image_url = _extract_image_url(card)
        if not image_url:
            continue
        reference_path = reference_root / _reference_file_name(card, image_url)
        if overwrite_downloads or not reference_path.exists():
            _download(image_url, reference_path)
            downloaded += 1
        else:
            reused += 1
        image = _load_image(reference_path)
        vector = embedder.embed(image)
        if vectors is None:
            vectors = np.empty((len(selected_cards), vector.shape[0]), dtype=np.float32)
        vectors[index] = vector
        metadata.append(
            {
                "name": card.get("name"),
                "scryfall_id": card.get("id") or card.get("scryfall_id"),
                "oracle_id": card.get("oracle_id"),
                "set_code": card.get("set") or card.get("set_code"),
                "collector_number": card.get("collector_number"),
                "image_url": image_url,
                "image_path": reference_path.relative_to(project_root_path).as_posix(),
                "crop_type": "full_card",
            }
        )
        if progress_callback is not None:
            progress_callback(index + 1, len(selected_cards), f"Indexed {index + 1:,}/{len(selected_cards):,} cards")

    if vectors is None:
        raise ValueError("Visual index builder did not produce any embeddings.")

    index = VisualIndex(vectors, metadata)
    index.save(index_file, metadata_file)
    updated_at = _utc_now_iso()
    return VisualIndexBuildResult(
        index_path=index_file,
        metadata_path=metadata_file,
        reference_dir=reference_root,
        source_catalog_path=source_path,
        card_count=len(metadata),
        downloaded_count=downloaded,
        reused_count=reused,
        updated_at_utc=updated_at,
        refresh_days=_normalize_refresh_days(refresh_days),
    )


def visual_index_refresh_needed(
    *,
    project_root: str | Path,
    config_path: str | Path | None = None,
) -> tuple[bool, float | None, str]:
    manager = VisualIndexRefreshManager(project_root=Path(project_root), config_path=Path(config_path) if config_path is not None else None)
    status = manager.status(running=False, auto_start=False)
    return bool(status["needs_refresh"]), status.get("age_days"), str(status.get("action") or "reuse")


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _state_age_days(state: dict[str, Any]) -> float | None:
    updated_at = state.get("updated_at_utc")
    if not isinstance(updated_at, str) or not updated_at.strip():
        return None
    try:
        timestamp = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    age = datetime.now(UTC) - timestamp
    return age / timedelta(days=1)


def _normalize_refresh_days(value: Any) -> int:
    try:
        refresh_days = int(value)
    except (TypeError, ValueError):
        return DEFAULT_VISUAL_INDEX_REFRESH_DAYS
    if refresh_days in VISUAL_INDEX_REFRESH_DAY_OPTIONS:
        return refresh_days
    return DEFAULT_VISUAL_INDEX_REFRESH_DAYS


def _extract_image_url(card: dict[str, Any]) -> str | None:
    image_uris = card.get("image_uris")
    if isinstance(image_uris, dict):
        for key in ("png", "large", "normal"):
            value = image_uris.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    card_faces = card.get("card_faces")
    if isinstance(card_faces, list):
        for face in card_faces:
            if not isinstance(face, dict):
                continue
            face_uris = face.get("image_uris")
            if not isinstance(face_uris, dict):
                continue
            for key in ("png", "large", "normal"):
                value = face_uris.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
    return None


def _reference_file_name(card: dict[str, Any], image_url: str) -> str:
    parsed = urlparse(image_url)
    suffix = Path(parsed.path).suffix or ".png"
    set_code = _slug(str(card.get("set") or card.get("set_code") or "set"))
    collector = _slug(str(card.get("collector_number") or "card"))
    name = _slug(str(card.get("name") or "card"))
    card_id = _slug(str(card.get("id") or card.get("scryfall_id") or hashlib.sha1(image_url.encode("utf-8")).hexdigest()))[:16]
    return f"{set_code}-{collector}-{name}-{card_id}{suffix}"


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-") or "card"


def _download(image_url: str, output_path: Path) -> None:
    request = Request(image_url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=30) as response:
        output_path.write_bytes(response.read())


def _load_image(path: Path) -> np.ndarray:
    image = cv2.imread(str(path))
    if image is None:
        raise ValueError(f"Unable to read downloaded reference image: {path}")
    return image
