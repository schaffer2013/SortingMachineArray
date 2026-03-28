from __future__ import annotations

import json

from sorter.application.vision_dataset import ingest_recognition_summary


def test_ingest_recognition_summary_copies_frames_and_writes_manifest(tmp_path):
    source_image = tmp_path / "source" / "card.jpg"
    source_image.parent.mkdir(parents=True, exist_ok=True)
    source_image.write_bytes(b"image-bytes")
    summary_path = tmp_path / "summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "backend": "fuzzy_enigma",
                "scenario_name": "demo",
                "cases": [
                    {
                        "pile_key": "0,0",
                        "frame_id": "frame-1",
                        "frame_path": str(source_image),
                        "expected_name": "Opt",
                        "predicted_name": "Opt",
                        "confidence": 0.91,
                        "needs_review": False,
                        "fallback_used": False,
                        "alternatives": [{"name": "Opt", "score": 0.91}],
                        "debug": {"active_roi": "standard"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    records = ingest_recognition_summary(summary_path, dataset_root=tmp_path / "data/vision", source_mode="sim", split="benchmark")

    assert len(records) == 1
    record = records[0]
    assert record.expected_name == "Opt"
    assert record.imported_frame_path.endswith("frame-1.jpg")
    assert (tmp_path / "data/vision/raw/sim/demo/benchmark/frame-1.jpg").exists()
    manifest_path = tmp_path / "data/vision/labels/sim/demo/benchmark.jsonl"
    assert manifest_path.exists()
    manifest_lines = manifest_path.read_text(encoding="utf-8").splitlines()
    assert len(manifest_lines) == 1
