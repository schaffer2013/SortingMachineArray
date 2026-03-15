# PaddleOCR Integration Path Guide

This document maps the current repo documentation to a practical PaddleOCR implementation path for MTG card recognition.

## Why this guide exists

The project docs already define architecture, calibration, and completion direction. What is missing is a single, implementation-focused bridge from those docs to a concrete OCR stack.

This file fills that gap by:

- mapping each existing document to PaddleOCR decisions,
- identifying missing artifacts/configs called out by the roadmap,
- proposing a phased plan that fits the current `RecognizerPort` contract.

---

## How existing docs fit the PaddleOCR path

## `README.md` (architecture and runtime orientation)

What it already gives you:

- the hexagonal architecture boundaries (`ports`, `adapters`, `application`, `domain`),
- where recognition adapters should live,
- the sim runtime/testing entrypoints.

How to apply it for PaddleOCR:

- keep PaddleOCR fully inside a recognition adapter under `src/sorter/adapters/recognition/`,
- keep OCR dependencies and image preprocessing out of domain/application code,
- use existing sim/hardware wiring model to swap recognizer implementations by bootstrap configuration.

## `docs/completion_spec.md` (target behavior)

What it already gives you:

- end-state expectations for reliable operation and operator trust,
- emphasis on observation-based decisions.

How to apply it for PaddleOCR:

- define acceptable recognition quality targets (confidence and failure handling),
- treat low-confidence recognition as an operational state (retry, rescans, manual review), not a silent success.

## `docs/calibration_spec.md` (machine and camera calibration)

What it already gives you:

- ownership and process for calibration data.

How to apply it for PaddleOCR:

- include OCR-related calibration outputs (ROI bands for name line, glare-safe capture settings),
- version these settings in config so OCR tuning does not require code edits.

## `PROJECT_ROADMAP.md` (delivery sequencing)

What it already gives you:

- explicit workstreams for vision/OCR/data/replay,
- planned artifacts for ROI config, thresholds, ingestion, and replay.

How to apply it for PaddleOCR:

- implement PaddleOCR in phases aligned to roadmap artifacts,
- do not jump directly to end-to-end production inference before data and replay tooling exist.

## `VESTIGIAL_CODE_REVIEW.md` (cleanup context)

What it already gives you:

- clear warning that some recognizer files are prototypes/stubs.

How to apply it for PaddleOCR:

- keep experimental recognizers clearly labeled,
- promote only one maintained production recognizer path (Paddle adapter + tests + configs) to avoid drift.

---

## Current gaps (relative to roadmap) for a PaddleOCR path

The roadmap already names most required artifacts; the practical gaps are that they are not yet present/wired:

1. vision config files (ROI profiles + thresholds),
2. frame ingestion and replay scripts,
3. a persisted dataset layout for OCR training/eval,
4. recognizer evaluation harness and acceptance metrics,
5. bootstrap config for selecting recognizer implementation.

---

## Recommended implementation plan

## Phase 1 — Config and contract hardening

Goal: make OCR tuning configurable before model work expands.

- Add `config/vision/roi_profiles.json` for card regions (full card, name bar, optional set/collector fields).
- Add `config/vision/recognition_thresholds.json` for:
  - minimum OCR confidence,
  - retry counts,
  - manual-review threshold.
- Keep output through `RecognitionResult(card_name, confidence)` so application logic stays unchanged.

Deliverable:

- Paddle adapter can read config and run inference deterministically from captured frames.

## Phase 2 — Data and labeling loop

Goal: build repeatable data flow for fine-tuning.

- Add raw frame ingestion script (roadmap-aligned).
- Add deterministic normalization/cropping into `data/vision/normalized/`.
- Create labels for name-line transcription and card identity mapping.
- Include difficult examples: foils, sleeves, low light, angled captures, partial occlusion.

Deliverable:

- versioned train/val/test splits suitable for PaddleOCR fine-tuning.

## Phase 3 — PaddleOCR training and adapter integration

Goal: connect fine-tuned model to runtime adapter.

- Train/fine-tune recognizer on MTG name-line crops.
- Build `PaddleOcrRecognizer` adapter that:
  - crops ROI,
  - preprocesses image,
  - runs OCR,
  - normalizes text,
  - resolves to catalog name (fuzzy + exact matching),
  - returns calibrated confidence.
- Add an offline replay script to benchmark inference before live sorting use.

Deliverable:

- measurable baseline accuracy with reproducible replay results.

## Phase 4 — Operational reliability

Goal: integrate failure behavior with machine workflow.

- Enforce confidence thresholds in verification/discovery workflows.
- Add retry/recapture strategy for low-confidence frames.
- Persist recognition traces (frame id, crop, candidates, confidence) for post-run diagnosis.

Deliverable:

- system behavior that fails safely when OCR is uncertain.

---

## Practical guidance for MTG-specific OCR quality

- Prefer ROI OCR over full-frame OCR.
- Normalize orientation/perspective before OCR.
- Build a post-OCR correction layer constrained by catalog names.
- Track per-condition metrics (foil vs non-foil, sleeve type, lighting profile).
- Start with high precision thresholds; gradually optimize recall once mis-sorts are rare.

---

## Suggested near-term artifacts to add next

1. `config/vision/roi_profiles.json`
2. `config/vision/recognition_thresholds.json`
3. `scripts/ingest_frames.py`
4. `scripts/replay_recognition.py`
5. `docs/recognition_benchmark.md`

These are directly aligned with roadmap language and create a concrete runway for PaddleOCR.
