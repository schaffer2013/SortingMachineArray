from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import json
import zipfile


@dataclass(frozen=True)
class FeedbackBundleEntry:
    source_path: str
    archive_path: str
    exists: bool


@dataclass(frozen=True)
class FeedbackBundleManifest:
    generated_at_utc: str
    project_root: str
    output_path: str
    entries: tuple[FeedbackBundleEntry, ...]

    def to_dict(self) -> dict:
        return {
            "generated_at_utc": self.generated_at_utc,
            "project_root": self.project_root,
            "output_path": self.output_path,
            "entries": [asdict(entry) for entry in self.entries],
        }


def build_submodule_feedback_bundle(project_root: Path, output_path: Path) -> FeedbackBundleManifest:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    entry_pairs = _entry_pairs(project_root)
    entries = tuple(
        FeedbackBundleEntry(
            source_path=str(source),
            archive_path=archive,
            exists=source.exists(),
        )
        for source, archive in entry_pairs
    )

    manifest = FeedbackBundleManifest(
        generated_at_utc=datetime.now(UTC).isoformat(),
        project_root=str(project_root),
        output_path=str(output_path),
        entries=entries,
    )

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr("manifest.json", json.dumps(manifest.to_dict(), indent=2))
        for entry in entries:
            source = Path(entry.source_path)
            if not source.exists():
                continue
            bundle.write(source, arcname=entry.archive_path)

    return manifest


def _entry_pairs(project_root: Path) -> list[tuple[Path, str]]:
    pairs: list[tuple[Path, str]] = [
        (project_root / "docs" / "submodule_feedback.md", "docs/submodule_feedback.md"),
        (project_root / "docs" / "acceptance_gates.md", "docs/acceptance_gates.md"),
        (
            project_root / "data" / "recognition_reports" / "acceptance_envelope.json",
            "data/recognition_reports/acceptance_envelope.json",
        ),
    ]
    portable_dir = project_root / "data" / "recognition_reports" / "portable"
    if portable_dir.exists():
        for path in sorted(portable_dir.glob("*.portable.json")):
            pairs.append((path, f"data/recognition_reports/portable/{path.name}"))
    return pairs
