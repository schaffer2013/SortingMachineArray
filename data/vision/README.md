# Vision Dataset Layout

This directory is parent-owned recognition data for replay, benchmark, and future hardware capture work.

## Layout

- `raw/`: immutable imported frame files grouped by source mode, scenario, and split
- `normalized/`: derived crops or normalized artifacts that can be regenerated
- `labels/`: JSONL manifests and future ROI or review labels

## Current Sprint 1 Usage

- `scripts/replay_recognition.py` and `scripts/benchmark_recognizer.py` produce recognition summaries.
- `scripts/ingest_frames.py` imports frame files referenced by those summaries into this dataset layout.
- Imported label manifests preserve expected and predicted identity, confidence, fallback state, candidate alternatives, and debug payload when available.
- Development-time replay and benchmark artifacts such as OCR snippets, bbox metadata, and per-case debug JSON now live under `data/recognition_reports/artifacts/` rather than being mixed into the immutable dataset layout.
