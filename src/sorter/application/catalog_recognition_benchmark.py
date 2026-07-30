from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import random
import tempfile
import threading
import time
from typing import Any, Callable, Iterator


BENCHMARK_BACKEND_OPTIONS = ("fuzzy_enigma", "visual_retrieval", "moss_machine")
DEFAULT_BENCHMARK_SAMPLE_SIZE = 25
MAX_BENCHMARK_SAMPLE_SIZE = 500

RecognizeImage = Callable[[Path, dict[str, Any]], dict[str, Any]]
DownloadImage = Callable[[str], bytes]


def eligible_catalog_cards(source_path: Path) -> list[dict[str, Any]]:
    return [
        _benchmark_card(card)
        for card in _iter_catalog_cards(source_path)
        if _is_benchmark_eligible(card)
    ]


def choose_benchmark_cards(
    source_path: Path,
    *,
    sample_size: int,
    seed: int,
) -> tuple[list[dict[str, Any]], int]:
    randomizer = random.Random(seed)
    selected: list[dict[str, Any]] = []
    eligible_count = 0
    for card in _iter_catalog_cards(source_path):
        if not _is_benchmark_eligible(card):
            continue
        eligible_count += 1
        benchmark_card = _benchmark_card(card)
        if len(selected) < sample_size:
            selected.append(benchmark_card)
            continue
        replacement_index = randomizer.randrange(eligible_count)
        if replacement_index < sample_size:
            selected[replacement_index] = benchmark_card

    if sample_size > eligible_count:
        raise ValueError(
            f"Requested {sample_size:,} cards, but only {eligible_count:,} eligible paper cards are available"
        )
    randomizer.shuffle(selected)
    return selected, eligible_count


def _iter_catalog_cards(source_path: Path) -> Iterator[dict[str, Any]]:
    decoder = json.JSONDecoder()
    chunk_size = 1024 * 1024
    with source_path.open(encoding="utf-8") as stream:
        buffer = ""
        position = 0
        finished = False

        while True:
            if not finished and len(buffer) - position < chunk_size:
                buffer = buffer[position:]
                position = 0
                chunk = stream.read(chunk_size)
                if chunk:
                    buffer += chunk
                else:
                    finished = True

            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if position >= len(buffer):
                if finished:
                    raise ValueError(f"Catalog did not contain a card list: {source_path}")
                continue
            if buffer[position] != "[":
                payload = json.loads(buffer[position:] + stream.read())
                cards = payload.get("cards", []) if isinstance(payload, dict) else None
                if not isinstance(cards, list):
                    raise ValueError(f"Catalog did not contain a card list: {source_path}")
                yield from (card for card in cards if isinstance(card, dict))
                return
            position += 1
            break

        while True:
            while position < len(buffer) and (buffer[position].isspace() or buffer[position] == ","):
                position += 1
            if position < len(buffer) and buffer[position] == "]":
                return
            try:
                card, end = decoder.raw_decode(buffer, position)
            except json.JSONDecodeError:
                if finished:
                    raise ValueError(f"Catalog contained invalid JSON: {source_path}") from None
                buffer = buffer[position:]
                position = 0
                chunk = stream.read(chunk_size)
                if chunk:
                    buffer += chunk
                else:
                    finished = True
                continue
            position = end
            if isinstance(card, dict):
                yield card


class CatalogRecognitionBenchmarkManager:
    def __init__(
        self,
        *,
        source_path: Path,
        state_path: Path,
        recognize_image: RecognizeImage,
        download_image: DownloadImage,
    ) -> None:
        self.source_path = source_path
        self.state_path = state_path
        self.recognize_image = recognize_image
        self.download_image = download_image
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread: threading.Thread | None = None
        self._state = self._load_state()
        if self._state.get("running"):
            self._state.update(
                {
                    "running": False,
                    "status": "interrupted",
                    "message": "The previous benchmark was interrupted when the web service stopped.",
                    "finished_at_utc": _utc_now(),
                }
            )
            self._save_state()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return json.loads(json.dumps(self._state))

    def start(
        self,
        *,
        sample_size: int,
        backends: list[str] | tuple[str, ...],
        seed: int | None = None,
    ) -> dict[str, Any]:
        normalized_size = int(sample_size)
        if normalized_size < 1 or normalized_size > MAX_BENCHMARK_SAMPLE_SIZE:
            raise ValueError(f"Sample size must be between 1 and {MAX_BENCHMARK_SAMPLE_SIZE}")
        normalized_backends = tuple(dict.fromkeys(str(value).strip().lower() for value in backends))
        if not normalized_backends:
            raise ValueError("Select at least one recognition backend")
        unsupported = [backend for backend in normalized_backends if backend not in BENCHMARK_BACKEND_OPTIONS]
        if unsupported:
            raise ValueError(f"Unsupported benchmark backend: {', '.join(unsupported)}")
        if not self.source_path.is_file():
            raise ValueError(f"Card catalog is unavailable: {self.source_path}")

        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                raise ValueError("A recognition benchmark is already running")
            selected_seed = random.SystemRandom().randrange(1, 2**31) if seed is None else int(seed)
            self._cancel.clear()
            self._state = {
                "running": True,
                "status": "starting",
                "message": "Loading the card catalog and choosing eligible paper cards.",
                "sample_size": normalized_size,
                "eligible_card_count": None,
                "seed": selected_seed,
                "backends": list(normalized_backends),
                "progress_current": 0,
                "progress_total": normalized_size * len(normalized_backends),
                "progress_percent": 0.0,
                "current_card": None,
                "current_backend": None,
                "started_at_utc": _utc_now(),
                "finished_at_utc": None,
                "cards": [],
                "backend_results": {
                    backend: _empty_backend_result(backend, normalized_size)
                    for backend in normalized_backends
                },
                "cases": [],
                "last_error": None,
            }
            self._save_state()
            self._thread = threading.Thread(
                target=self._run,
                args=(normalized_size, normalized_backends, selected_seed),
                daemon=True,
                name="recognition-benchmark",
            )
            self._thread.start()
            return self.status()

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            if self._thread is None or not self._thread.is_alive():
                raise ValueError("No recognition benchmark is running")
            self._cancel.set()
            self._state["message"] = "Cancellation requested; stopping after the current recognition."
            self._save_state()
            return self.status()

    def _run(self, sample_size: int, backends: tuple[str, ...], seed: int) -> None:
        try:
            cards, eligible_count = choose_benchmark_cards(
                self.source_path,
                sample_size=sample_size,
                seed=seed,
            )
            self._update(
                status="running",
                message=f"Selected {sample_size:,} random eligible paper cards.",
                eligible_card_count=eligible_count,
                cards=[_public_card(card) for card in cards],
            )
            completed = 0
            for card_index, card in enumerate(cards, start=1):
                if self._cancel.is_set():
                    self._finish_cancelled()
                    return
                self._update(
                    persist=False,
                    current_card=_public_card(card),
                    current_backend=None,
                    message=f"Downloading {card_index:,}/{sample_size:,}: {card['name']}",
                )
                try:
                    image_data = self.download_image(card["image_url"])
                except Exception as exc:
                    error = f"Image download failed: {exc}"
                    for backend in backends:
                        completed += 1
                        self._record_case(
                            backend=backend,
                            card=card,
                            result=None,
                            elapsed_seconds=0.0,
                            error=error,
                            completed=completed,
                        )
                    continue

                temp_path: Path | None = None
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as handle:
                        handle.write(image_data)
                        temp_path = Path(handle.name)
                    for backend in backends:
                        if self._cancel.is_set():
                            self._finish_cancelled()
                            return
                        self._update(
                            persist=False,
                            current_backend=backend,
                            message=(
                                f"Testing {backend} on {card_index:,}/{sample_size:,}: "
                                f"{card['name']}"
                            ),
                        )
                        started_at = time.monotonic()
                        result: dict[str, Any] | None = None
                        error: str | None = None
                        try:
                            result = self.recognize_image(
                                temp_path,
                                {
                                    "backend": backend,
                                    "mode": "greenfield",
                                    "track_result": False,
                                    "use_tracked_pool": False,
                                },
                            )
                        except Exception as exc:
                            error = str(exc)
                        completed += 1
                        self._record_case(
                            backend=backend,
                            card=card,
                            result=result,
                            elapsed_seconds=time.monotonic() - started_at,
                            error=error,
                            completed=completed,
                        )
                finally:
                    if temp_path is not None:
                        temp_path.unlink(missing_ok=True)

            self._update(
                running=False,
                status="completed",
                message=f"Benchmark completed across {sample_size:,} cards.",
                current_card=None,
                current_backend=None,
                finished_at_utc=_utc_now(),
            )
        except Exception as exc:
            self._update(
                running=False,
                status="failed",
                message=f"Benchmark failed: {exc}",
                last_error=str(exc),
                current_card=None,
                current_backend=None,
                finished_at_utc=_utc_now(),
            )

    def _record_case(
        self,
        *,
        backend: str,
        card: dict[str, Any],
        result: dict[str, Any] | None,
        elapsed_seconds: float,
        error: str | None,
        completed: int,
    ) -> None:
        predicted_name = str(result.get("card_name") or "").strip() if result else ""
        predicted_scryfall_id = str(result.get("scryfall_id") or "").strip() if result else ""
        expected_name = str(card["name"]).strip()
        matched = bool(predicted_name) and predicted_name.casefold() == expected_name.casefold()
        matched_printing = bool(predicted_scryfall_id) and predicted_scryfall_id == str(card.get("id") or "")
        confidence = float(result.get("confidence") or 0.0) if result else 0.0
        case = {
            "backend": backend,
            "card_id": card.get("id"),
            "expected_name": expected_name,
            "expected_set": card.get("set_code"),
            "expected_collector_number": card.get("collector_number"),
            "predicted_name": predicted_name or None,
            "predicted_scryfall_id": predicted_scryfall_id or None,
            "confidence": confidence,
            "matched": matched,
            "matched_printing": matched_printing,
            "elapsed_seconds": round(max(0.0, elapsed_seconds), 3),
            "error": error,
        }
        with self._lock:
            self._state["cases"].append(case)
            summary = self._state["backend_results"][backend]
            summary["completed"] += 1
            summary["matches"] += int(matched)
            summary["printing_matches"] += int(matched_printing)
            summary["errors"] += int(error is not None)
            summary["total_seconds"] = round(summary["total_seconds"] + max(0.0, elapsed_seconds), 3)
            summary["accuracy"] = round(summary["matches"] / summary["completed"], 4)
            summary["printing_accuracy"] = round(summary["printing_matches"] / summary["completed"], 4)
            summary["average_seconds"] = round(summary["total_seconds"] / summary["completed"], 3)
            self._state["progress_current"] = completed
            self._state["progress_percent"] = round(
                (completed / max(1, int(self._state["progress_total"]))) * 100,
                2,
            )
            self._state["message"] = (
                f"Completed {completed:,}/{self._state['progress_total']:,} backend-card tests."
            )
            if completed % 10 == 0 or completed >= int(self._state["progress_total"]):
                self._save_state()

    def _finish_cancelled(self) -> None:
        self._update(
            running=False,
            status="cancelled",
            message="Benchmark cancelled. Completed results were preserved.",
            current_card=None,
            current_backend=None,
            finished_at_utc=_utc_now(),
        )

    def _update(self, *, persist: bool = True, **values: Any) -> None:
        with self._lock:
            self._state.update(values)
            if persist:
                self._save_state()

    def _load_state(self) -> dict[str, Any]:
        if not self.state_path.is_file():
            return _idle_state()
        try:
            payload = json.loads(self.state_path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else _idle_state()
        except (OSError, json.JSONDecodeError):
            return _idle_state()

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.state_path.with_suffix(".json.tmp")
        temp_path.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        temp_path.replace(self.state_path)


def _is_benchmark_eligible(card: dict[str, Any]) -> bool:
    if bool(card.get("digital")):
        return False
    type_line = str(card.get("type_line") or "")
    type_words = {
        word.casefold()
        for word in type_line.replace("—", " ").replace("-", " ").split()
    }
    if "basic" in type_words and "land" in type_words:
        return False
    return bool(_image_urls(card))


def _benchmark_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(card.get("id") or ""),
        "oracle_id": str(card.get("oracle_id") or ""),
        "name": str(card.get("name") or ""),
        "set_code": str(card.get("set") or "").upper(),
        "collector_number": str(card.get("collector_number") or ""),
        "type_line": str(card.get("type_line") or ""),
        "image_url": _image_urls(card)[0],
    }


def _public_card(card: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in card.items() if key != "image_url"}


def _image_urls(card: dict[str, Any]) -> list[str]:
    order = ("normal", "large", "small", "png")
    urls: list[str] = []
    image_uris = card.get("image_uris")
    if isinstance(image_uris, dict):
        urls.extend(str(image_uris[key]) for key in order if image_uris.get(key))
    for face in card.get("card_faces") or []:
        if not isinstance(face, dict):
            continue
        face_uris = face.get("image_uris")
        if isinstance(face_uris, dict):
            urls.extend(str(face_uris[key]) for key in order if face_uris.get(key))
    return list(dict.fromkeys(urls))


def _empty_backend_result(backend: str, sample_size: int) -> dict[str, Any]:
    return {
        "backend": backend,
        "total": sample_size,
        "completed": 0,
        "matches": 0,
        "printing_matches": 0,
        "errors": 0,
        "accuracy": 0.0,
        "printing_accuracy": 0.0,
        "total_seconds": 0.0,
        "average_seconds": 0.0,
    }


def _idle_state() -> dict[str, Any]:
    return {
        "running": False,
        "status": "idle",
        "message": "Choose a sample size and one or more backends to begin.",
        "sample_size": DEFAULT_BENCHMARK_SAMPLE_SIZE,
        "eligible_card_count": None,
        "seed": None,
        "backends": list(BENCHMARK_BACKEND_OPTIONS),
        "progress_current": 0,
        "progress_total": 0,
        "progress_percent": 0.0,
        "current_card": None,
        "current_backend": None,
        "started_at_utc": None,
        "finished_at_utc": None,
        "cards": [],
        "backend_results": {},
        "cases": [],
        "last_error": None,
    }


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
