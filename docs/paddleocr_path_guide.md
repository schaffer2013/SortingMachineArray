# PaddleOCR Integration Path Guide

## Purpose

This guide maps the current repo structure to a practical OCR integration path.
It is meant to help future OCR work stay aligned with the parent runtime instead
of drifting into a one-off experiment.

## Current Docs To Use

- `README.md`: repo entrypoint, commands, and supported workflows
- `docs/runtime_reference.md`: enduring runtime intent and config ownership
- `docs/acceptance_gates.md`: evidence and verification expectations
- `docs/hardware_prep.md`: software prerequisites before hardware sessions
- `docs/submodule_feedback.md`: current upstream contract gaps worth preserving

## Current Repo Assets Relevant To OCR

These already exist and should be reused rather than recreated:

- `config/vision/roi_profiles.json`
- `config/vision/recognition_thresholds.json`
- `scripts/ingest_frames.py`
- `scripts/replay_recognition.py`
- `scripts/benchmark_recognizer.py`
- `tests/golden_frames/`
- `data/vision/`

## Integration Rules

- keep OCR dependencies inside a recognizer adapter
- keep domain and application layers unaware of OCR implementation details
- make OCR tuning config-driven through `config/vision/...`
- treat low-confidence OCR as an operational state that produces reviewable
  evidence, not a silent success
- benchmark and replay OCR changes before relying on them in live flows

## Recommended Path

### 1. Reuse the current adapter boundary

- implement OCR behind `RecognizerPort`
- keep parent orchestration talking to recognizer results, not OCR internals

### 2. Reuse current dataset and replay tooling

- ingest frames into `data/vision/`
- benchmark from saved summaries and stable manifests
- use golden frames and replay output to validate regressions

### 3. Keep OCR calibration explicit

- tune ROI and threshold settings in config
- do not bury OCR-sensitive assumptions in random adapters
- keep capture and ROI decisions inspectable enough for hardware debugging

### 4. Preserve evidence

- save OCR text, artifacts, candidates, and confidence where available
- make failures diagnosable from saved reports instead of requiring a live rerun

## What Not To Do

- do not add OCR logic to the domain layer
- do not bypass the existing replay and benchmark pipeline
- do not introduce a second competing “main” recognizer path without a clear
  runtime and test story
