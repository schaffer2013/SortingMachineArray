from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
import random
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from PIL import Image


CORNERS = ("nw", "ne", "se", "sw")
SPLITS = ("staged", "train", "eval")


@dataclass(frozen=True)
class CaptureBox:
    min_x_mm: float
    max_x_mm: float
    min_y_mm: float
    max_y_mm: float
    min_z_mm: float
    max_z_mm: float

    @staticmethod
    def from_payload(payload: dict[str, Any]) -> "CaptureBox":
        return CaptureBox(
            min_x_mm=float(payload["min_x_mm"]),
            max_x_mm=float(payload["max_x_mm"]),
            min_y_mm=float(payload["min_y_mm"]),
            max_y_mm=float(payload["max_y_mm"]),
            min_z_mm=float(payload["min_z_mm"]),
            max_z_mm=float(payload["max_z_mm"]),
        ).normalized()

    def normalized(self) -> "CaptureBox":
        min_x, max_x = sorted((self.min_x_mm, self.max_x_mm))
        min_y, max_y = sorted((self.min_y_mm, self.max_y_mm))
        min_z, max_z = sorted((self.min_z_mm, self.max_z_mm))
        if min_x == max_x or min_y == max_y or min_z == max_z:
            raise ValueError("Capture box must have non-zero X, Y, and Z ranges")
        return CaptureBox(min_x, max_x, min_y, max_y, min_z, max_z)

    def clamp_point(self, point: dict[str, Any]) -> dict[str, float]:
        return {
            "x_mm": _clamp(float(point["x_mm"]), self.min_x_mm, self.max_x_mm),
            "y_mm": _clamp(float(point["y_mm"]), self.min_y_mm, self.max_y_mm),
            "z_mm": _clamp(float(point["z_mm"]), self.min_z_mm, self.max_z_mm),
        }


def generate_spring_capture_points(
    capture_box: CaptureBox,
    count: int,
    *,
    seed: int | None = None,
    iterations: int = 420,
) -> list[dict[str, float]]:
    point_count = max(1, min(200, int(count)))
    rng = random.Random(seed)
    points = [
        {
            "x_mm": rng.uniform(capture_box.min_x_mm, capture_box.max_x_mm),
            "y_mm": rng.uniform(capture_box.min_y_mm, capture_box.max_y_mm),
            "z_mm": rng.uniform(capture_box.min_z_mm, capture_box.max_z_mm),
        }
        for _ in range(point_count)
    ]
    spans = {
        "x_mm": capture_box.max_x_mm - capture_box.min_x_mm,
        "y_mm": capture_box.max_y_mm - capture_box.min_y_mm,
        "z_mm": capture_box.max_z_mm - capture_box.min_z_mm,
    }
    mins = {"x_mm": capture_box.min_x_mm, "y_mm": capture_box.min_y_mm, "z_mm": capture_box.min_z_mm}
    maxes = {"x_mm": capture_box.max_x_mm, "y_mm": capture_box.max_y_mm, "z_mm": capture_box.max_z_mm}
    axes = ("x_mm", "y_mm", "z_mm")

    for step in range(max(1, int(iterations))):
        forces = [{axis: 0.0 for axis in axes} for _ in points]
        for index, point in enumerate(points):
            for other_index in range(index + 1, len(points)):
                other = points[other_index]
                delta = {axis: (point[axis] - other[axis]) / spans[axis] for axis in axes}
                distance_sq = sum(value * value for value in delta.values()) + 0.0007
                strength = 0.010 / distance_sq
                distance = math.sqrt(distance_sq)
                for axis in axes:
                    force = (delta[axis] / distance) * strength * spans[axis]
                    forces[index][axis] += force
                    forces[other_index][axis] -= force
            for axis in axes:
                low_distance = max(0.001, (point[axis] - mins[axis]) / spans[axis])
                high_distance = max(0.001, (maxes[axis] - point[axis]) / spans[axis])
                forces[index][axis] += (0.0028 / (low_distance * low_distance)) * spans[axis]
                forces[index][axis] -= (0.0028 / (high_distance * high_distance)) * spans[axis]
        damping = max(0.018, 0.16 * (1 - (step / max(1, iterations))))
        for index, point in enumerate(points):
            for axis in axes:
                point[axis] = _clamp(point[axis] + forces[index][axis] * damping, mins[axis], maxes[axis])

    return [{axis: round(point[axis], 3) for axis in axes} for point in points]


class CardBackTrainingStore:
    def __init__(self, root: Path):
        self.root = root
        self.models_root = self.root / "models"
        self.models_root.mkdir(parents=True, exist_ok=True)

    def summary(self) -> dict[str, Any]:
        models = self.list_models()
        active = next((model for model in models if model.get("active")), models[0] if models else None)
        return {
            "root": str(self.root),
            "active_model_id": active["model_id"] if active else None,
            "models": models,
        }

    def list_models(self) -> list[dict[str, Any]]:
        manifests = []
        for manifest_path in sorted(self.models_root.glob("*/manifest.json")):
            manifest = self._load_manifest(manifest_path.parent.name)
            manifests.append(self._model_summary(manifest))
        return manifests

    def create_model(self, name: str, *, base_model_id: str | None = None, notes: str | None = None) -> dict[str, Any]:
        clean_name = str(name or "").strip()
        if not clean_name:
            raise ValueError("Model name is required")
        model_id = _unique_model_id(self.models_root, clean_name)
        now = _now()
        base_payload = None
        if base_model_id:
            base_payload = self._load_manifest(base_model_id)
        manifest = {
            "model_id": model_id,
            "name": clean_name,
            "notes": notes or "",
            "created_at_utc": now,
            "updated_at_utc": now,
            "base_model_id": base_model_id or None,
            "active": not any(self.models_root.glob("*/manifest.json")),
            "samples": [],
            "training_runs": [],
        }
        model_dir = self._model_dir(model_id)
        model_dir.mkdir(parents=True, exist_ok=False)
        (model_dir / "images").mkdir()
        (model_dir / "labels").mkdir()
        if base_payload:
            manifest["base_sample_count"] = len(base_payload.get("samples", []))
        self._save_manifest(manifest)
        return self._model_summary(manifest)

    def set_active_model(self, model_id: str) -> dict[str, Any]:
        selected = None
        for manifest_path in sorted(self.models_root.glob("*/manifest.json")):
            manifest = self._load_manifest(manifest_path.parent.name)
            manifest["active"] = manifest["model_id"] == model_id
            if manifest["active"]:
                selected = manifest
            self._save_manifest(manifest)
        if selected is None:
            raise ValueError(f"Unknown training model: {model_id}")
        return self._model_summary(selected)

    def delete_model(self, model_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        was_active = bool(manifest.get("active"))
        shutil.rmtree(self._model_dir(model_id))
        remaining = []
        for manifest_path in sorted(self.models_root.glob("*/manifest.json")):
            remaining_manifest = self._load_manifest(manifest_path.parent.name)
            remaining.append(remaining_manifest)
        if was_active and remaining:
            remaining[0]["active"] = True
        for index, remaining_manifest in enumerate(remaining):
            if was_active and index > 0:
                remaining_manifest["active"] = False
            self._save_manifest(remaining_manifest)
        return {"deleted_model_id": model_id, "summary": self.summary()}

    def capture_sample(
        self,
        model_id: str,
        image: Image.Image,
        *,
        point: dict[str, Any] | None,
        lighting: dict[str, Any] | None,
        detection: dict[str, Any] | None,
        expected_crop: dict[str, Any] | None,
        truth_corners: dict[str, Any] | None,
        split: str = "staged",
    ) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        sample_id = f"sample-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:8]}"
        normalized_split = _normalize_split(split)
        image_rel = f"images/{sample_id}.jpg"
        label_rel = f"labels/{sample_id}.json"
        model_dir = self._model_dir(model_id)
        image_path = model_dir / image_rel
        image.convert("RGB").save(image_path, format="JPEG", quality=92)
        label = {
            "sample_id": sample_id,
            "model_id": model_id,
            "captured_at_utc": _now(),
            "split": normalized_split,
            "point": _optional_float_point(point),
            "lighting": lighting or {},
            "detection": _strip_large_data_urls(detection or {}),
            "expected_crop": expected_crop or {},
            "truth_corners_px": _normalize_corners(truth_corners),
            "image_path": image_rel,
            "image_size": [image.width, image.height],
        }
        (model_dir / label_rel).write_text(json.dumps(label, indent=2), encoding="utf-8")
        sample = {
            "sample_id": sample_id,
            "split": normalized_split,
            "captured_at_utc": label["captured_at_utc"],
            "point": label["point"],
            "lighting": label["lighting"],
            "image_path": image_rel,
            "label_path": label_rel,
            "image_size": label["image_size"],
            "has_truth": bool(label["truth_corners_px"]),
        }
        manifest.setdefault("samples", []).append(sample)
        manifest["updated_at_utc"] = _now()
        self._save_manifest(manifest)
        return {**sample, "model": self._model_summary(manifest), "label": label}

    def update_sample_label(self, model_id: str, sample_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        sample = _find_sample(manifest, sample_id)
        label_path = self._model_dir(model_id) / sample["label_path"]
        label = json.loads(label_path.read_text(encoding="utf-8"))
        if "truth_corners_px" in payload:
            label["truth_corners_px"] = _normalize_corners(payload.get("truth_corners_px"))
            sample["has_truth"] = bool(label["truth_corners_px"])
        if "expected_crop" in payload:
            label["expected_crop"] = payload.get("expected_crop") or {}
        if "split" in payload:
            normalized_split = _normalize_split(str(payload.get("split")))
            label["split"] = normalized_split
            sample["split"] = normalized_split
        label["updated_at_utc"] = _now()
        label_path.write_text(json.dumps(label, indent=2), encoding="utf-8")
        manifest["updated_at_utc"] = _now()
        self._save_manifest(manifest)
        return {**sample, "model": self._model_summary(manifest), "label": label}

    def delete_sample(self, model_id: str, sample_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        sample = _find_sample(manifest, sample_id)
        model_dir = self._model_dir(model_id)
        for relative_path in (sample.get("image_path"), sample.get("label_path")):
            if relative_path:
                path = model_dir / relative_path
                if path.exists():
                    path.unlink()
        manifest["samples"] = [item for item in manifest.get("samples", []) if item.get("sample_id") != sample_id]
        manifest["updated_at_utc"] = _now()
        self._save_manifest(manifest)
        return {"deleted_sample_id": sample_id, "model": self._model_summary(manifest)}

    def sample_image_path(self, model_id: str, sample_id: str) -> Path:
        manifest = self._load_manifest(model_id)
        sample = _find_sample(manifest, sample_id)
        image_path = self._model_dir(model_id) / sample["image_path"]
        if not image_path.exists():
            raise ValueError(f"Training sample image is missing: {sample_id}")
        return image_path

    def sample_payload(self, model_id: str, sample_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        sample = _find_sample(manifest, sample_id)
        label_path = self._model_dir(model_id) / sample["label_path"]
        label = json.loads(label_path.read_text(encoding="utf-8"))
        return {**sample, "model": self._model_summary(manifest), "label": label}

    def latest_corner_template(self, model_id: str) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        for sample in reversed(manifest.get("samples", [])):
            label_path = self._model_dir(model_id) / sample["label_path"]
            label = json.loads(label_path.read_text(encoding="utf-8"))
            image_size = label.get("image_size")
            if not (isinstance(image_size, list) and len(image_size) == 2 and image_size[0] and image_size[1]):
                continue
            corners = label.get("truth_corners_px") or label.get("detection", {}).get("corners_px")
            normalized = _normalize_corners(corners)
            if not normalized:
                continue
            return {
                "sample_id": sample["sample_id"],
                "image_size": [float(image_size[0]), float(image_size[1])],
                "corners_px": normalized,
            }
        raise ValueError(f"Training model has no tuned corner template: {model_id}")

    def register_training_run(self, model_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        manifest = self._load_manifest(model_id)
        run = {
            "run_id": f"run-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}-{uuid4().hex[:6]}",
            "created_at_utc": _now(),
            "status": str(payload.get("status") or "planned"),
            "notes": str(payload.get("notes") or ""),
            "metrics": payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {},
            "artifact_path": str(payload.get("artifact_path") or ""),
        }
        manifest.setdefault("training_runs", []).append(run)
        manifest["updated_at_utc"] = _now()
        self._save_manifest(manifest)
        return {"run": run, "model": self._model_summary(manifest)}

    def _model_dir(self, model_id: str) -> Path:
        return self.models_root / _slug(str(model_id))

    def _load_manifest(self, model_id: str) -> dict[str, Any]:
        path = self._model_dir(model_id) / "manifest.json"
        if not path.exists():
            raise ValueError(f"Unknown training model: {model_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _save_manifest(self, manifest: dict[str, Any]) -> None:
        model_dir = self._model_dir(str(manifest["model_id"]))
        model_dir.mkdir(parents=True, exist_ok=True)
        temp_path = model_dir / "manifest.json.tmp"
        temp_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        shutil.move(str(temp_path), model_dir / "manifest.json")

    def _model_summary(self, manifest: dict[str, Any]) -> dict[str, Any]:
        samples = list(manifest.get("samples", []))
        split_counts = {split: sum(1 for sample in samples if sample.get("split", "staged") == split) for split in SPLITS}
        return {
            "model_id": manifest["model_id"],
            "name": manifest.get("name", manifest["model_id"]),
            "notes": manifest.get("notes", ""),
            "created_at_utc": manifest.get("created_at_utc"),
            "updated_at_utc": manifest.get("updated_at_utc"),
            "base_model_id": manifest.get("base_model_id"),
            "active": bool(manifest.get("active")),
            "sample_count": len(samples),
            "staged_count": split_counts["staged"],
            "train_count": split_counts["train"],
            "eval_count": split_counts["eval"],
            "truth_count": sum(1 for sample in samples if sample.get("has_truth")),
            "training_run_count": len(manifest.get("training_runs", [])),
            "latest_training_run": (manifest.get("training_runs") or [None])[-1],
            "recent_samples": samples[-12:][::-1],
        }


def _find_sample(manifest: dict[str, Any], sample_id: str) -> dict[str, Any]:
    for sample in manifest.get("samples", []):
        if sample.get("sample_id") == sample_id:
            return sample
    raise ValueError(f"Unknown sample: {sample_id}")


def _normalize_split(value: str) -> str:
    normalized = str(value or "staged").strip().lower()
    if normalized not in SPLITS:
        raise ValueError("Sample split must be staged, train, or eval")
    return normalized


def _normalize_corners(value: Any) -> dict[str, list[float]]:
    if not isinstance(value, dict):
        return {}
    corners: dict[str, list[float]] = {}
    for corner in CORNERS:
        point = value.get(corner)
        if isinstance(point, dict):
            x_value = point.get("x")
            y_value = point.get("y")
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            x_value, y_value = point[0], point[1]
        else:
            continue
        corners[corner] = [round(float(x_value), 3), round(float(y_value), 3)]
    return corners


def _optional_float_point(value: Any) -> dict[str, float] | None:
    if not isinstance(value, dict):
        return None
    required = ("x_mm", "y_mm", "z_mm")
    if not all(key in value for key in required):
        return None
    return {key: round(float(value[key]), 3) for key in required}


def _strip_large_data_urls(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("<omitted>" if isinstance(item, str) and item.startswith("data:image/") else _strip_large_data_urls(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_strip_large_data_urls(item) for item in value]
    return value


def _unique_model_id(root: Path, name: str) -> str:
    base = _slug(name)
    candidate = base
    index = 2
    while (root / candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "model"


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _now() -> str:
    return datetime.now(UTC).isoformat()
