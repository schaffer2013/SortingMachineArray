from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
from pathlib import Path


@dataclass(frozen=True)
class VisionIngestRecord:
    source_summary_path: str
    scenario_name: str
    backend: str
    source_mode: str
    split: str
    pile_key: str
    frame_id: str
    frame_path: str
    imported_frame_path: str
    expected_name: str | None
    predicted_name: str | None
    confidence: float
    needs_review: bool
    fallback_used: bool
    expected_scryfall_id: str | None = None
    expected_oracle_id: str | None = None
    predicted_scryfall_id: str | None = None
    predicted_oracle_id: str | None = None
    alternatives: tuple[dict, ...] = ()
    debug: dict | None = None


def ingest_recognition_summary(
    summary_path: Path,
    *,
    dataset_root: Path,
    source_mode: str,
    split: str = "benchmark",
) -> list[VisionIngestRecord]:
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Recognition summary payload must be a JSON object.")

    scenario_name = str(payload.get("scenario_name", summary_path.stem))
    backend = str(payload.get("backend", "unknown"))
    raw_dir = dataset_root / "raw" / source_mode / scenario_name / split
    label_dir = dataset_root / "labels" / source_mode / scenario_name
    raw_dir.mkdir(parents=True, exist_ok=True)
    label_dir.mkdir(parents=True, exist_ok=True)

    cases = payload.get("cases", [])
    if not isinstance(cases, list):
        raise ValueError("Recognition summary 'cases' must be a list.")

    records: list[VisionIngestRecord] = []
    for case in cases:
        if not isinstance(case, dict):
            continue
        frame_path_raw = case.get("frame_path")
        if not isinstance(frame_path_raw, str) or not frame_path_raw:
            continue
        source_frame_path = Path(frame_path_raw)
        if not source_frame_path.exists():
            continue

        frame_id = str(case.get("frame_id") or source_frame_path.stem)
        target_path = raw_dir / f"{frame_id}{source_frame_path.suffix.lower() or '.jpg'}"
        shutil.copy2(source_frame_path, target_path)

        records.append(
            VisionIngestRecord(
                source_summary_path=str(summary_path),
                scenario_name=scenario_name,
                backend=backend,
                source_mode=source_mode,
                split=split,
                pile_key=str(case.get("pile_key", "")),
                frame_id=frame_id,
                frame_path=str(source_frame_path),
                imported_frame_path=str(target_path),
                expected_name=case.get("expected_name"),
                predicted_name=case.get("predicted_name"),
                confidence=float(case.get("confidence", 0.0)),
                needs_review=bool(case.get("needs_review", False)),
                fallback_used=bool(case.get("fallback_used", False)),
                expected_scryfall_id=case.get("expected_scryfall_id"),
                expected_oracle_id=case.get("expected_oracle_id"),
                predicted_scryfall_id=case.get("predicted_scryfall_id"),
                predicted_oracle_id=case.get("predicted_oracle_id"),
                alternatives=tuple(case.get("alternatives", []) or []),
                debug=case.get("debug"),
            )
        )

    manifest_path = label_dir / f"{split}.jsonl"
    with manifest_path.open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(record.__dict__, ensure_ascii=False) + "\n")

    return records
