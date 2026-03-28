# Acceptance Gates

## Purpose

This document defines the first measurable gates for recognition and replay work.

These are provisional Sprint 1 gates, not the final completion gates for the whole sorter.

## Current Focus

The current acceptance focus is:

- parent-side `fuzzy_enigma` integration
- replayable recognition evidence
- stable sim-backed benchmark behavior
- inspectable low-confidence failures

## Required Commands

Run these from the repo root with the shared `.venv`.

### Baseline tests

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

### Sim-truth benchmark baseline

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend sim_truth
```

### Real recognizer benchmark baseline

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma
```

### Mode-aware portable report sample

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --portable-out data\recognition_reports\portable\fuzzy_enigma_small_pool.portable.json
```

### Real recognizer replay sample

```powershell
.\.venv\Scripts\python.exe scripts\replay_recognition.py --backend fuzzy_enigma --pile 0,0
```

### Dataset ingest from a saved recognition summary

```powershell
.\.venv\Scripts\python.exe scripts\ingest_frames.py `
  --summary-json data\recognition_reports\fuzzy_enigma_summary.json `
  --source-mode sim `
  --split benchmark
```

## Sprint 1 Gates

### Gate 1: integration health

- parent tests must pass
- `fuzzy_enigma` must run from the parent repo without import or OCR-backend failure

### Gate 2: replay evidence

- replay and benchmark commands must write JSON summaries under `data/recognition_reports/`
- those summaries must include:
  - expected card
  - predicted card
  - confidence
  - review flag
  - review reason when applicable
  - requested mode
  - effective mode when available
  - fallback flag
  - alternatives
  - debug payload
  - confidence-band counts at the summary level
- `fuzzy_enigma` replay and benchmark runs must also emit inspectable per-case artifacts for development-time review
- portable report outputs must split success and failure cases so the parent can hand the result bundle directly to the submodule developer

### Gate 3: benchmark truthfulness

- benchmark runs must use a parent-owned card-engine config
- benchmark config may differ from live config, especially for recognition deadline budget
- benchmark output must print which card-engine config file was used

### Gate 4: dataset handoff

- a benchmark or replay summary must be ingestible into `data/vision/`
- imported manifests must preserve expected and predicted identity plus confidence metadata

## Provisional Thresholds

These are current working thresholds, not final product sign-off thresholds.

- `sim_truth` benchmark:
  - expected `name_accuracy = 1.000`
- `fuzzy_enigma` benchmark on the current `runtime_small_stack` sim slice:
  - should complete end-to-end
  - should produce non-empty predictions for most cards
  - should clearly outperform the previous timeout-driven `0.167` baseline
- low-confidence matches are acceptable during Sprint 1 if:
  - they are marked for review
  - the evidence needed to inspect them is saved

## Current Known Baseline

Observed during Sprint 1:

- inherited live deadline config produced a weak parent-side `fuzzy_enigma` benchmark around `0.167`
- a parent-owned benchmark config with a larger deadline improved that same slice to about `0.833`

That means the current acceptance focus is not only "accuracy" but also "correct config ownership."

## What Fails The Gate

- the parent benchmark cannot run
- the OCR backend is missing
- the summary JSON omits the evidence needed to inspect bad cases
- replay and benchmark do not use a clear parent-owned config path
- the dataset ingest path requires manual file surgery

## Next Gate Expansion

The next acceptance expansion after Sprint 1 should add:

- stable golden-frame regression commands
- noisy-sim recovery scenarios
- planner behavior under low-confidence reads
- hardware-facing replay and capture ingestion

## Sprint 2 Additions

- startup scan and move verification now retry before escalating
- review-worthy runs should return `REVIEW_REQUIRED` instead of silently passing or collapsing into an ambiguous generic failure
- noisy-sim fixtures now exist to exercise that escalation path

## Sprint 3 Additions

- replay and benchmark outputs now classify review reasons instead of leaving all review cases lumped together
- replay and benchmark outputs now export inspectable OCR and bbox artifacts for `fuzzy_enigma`
- planner coverage now includes partial-knowledge cases where unknown piles should block premature transitions or moves

## Sprint 4 Additions

- replay and benchmark outputs now generate portable success/failure reports with submodule SHA and mode metadata
- parent mode experiments now fail safely when constrained recognition preconditions are missing, instead of crashing the benchmark run
- the parent repo now tracks concrete upstream asks in `docs/submodule_feedback.md`
