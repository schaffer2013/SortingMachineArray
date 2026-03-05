from __future__ import annotations

from pathlib import Path
import shutil


def import_frames(source_dir: Path, target_dir: Path) -> int:
    target_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for file_path in source_dir.glob("*.jpg"):
        shutil.copy2(file_path, target_dir / file_path.name)
        count += 1
    return count


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    copied = import_frames(root / "recorded_frames", root / "data/recorded_frames")
    print({"copied": copied})
