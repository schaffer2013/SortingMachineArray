# Acceptance Gates

## Purpose

This document defines the current software acceptance checks for the parent
repo. It is not a sprint log and it is not a full product-completion spec.

## Required Commands

Run these from the repo root with the shared `.venv`.

### Test suite

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

### Acceptance envelope

```powershell
.\.venv\Scripts\python.exe scripts\check_acceptance.py
```

### Sim benchmark baseline

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend sim_truth
```

### Submodule benchmark baseline

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma
```

### Mode-aware portable report sample

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --use-expected-label `
  --portable-out data\recognition_reports\portable\fuzzy_enigma_small_pool.portable.json
```

### Replay sample

```powershell
.\.venv\Scripts\python.exe scripts\replay_recognition.py --backend fuzzy_enigma --pile 0,0
```

### Golden-frame sample

```powershell
.\.venv\Scripts\python.exe scripts\run_golden_frames.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --use-expected-label
```

## Gate Conditions

### Gate 1: baseline health

- parent tests pass
- the acceptance envelope command completes
- the selected recognizer backend runs from the parent repo without import or
  configuration guesswork

### Gate 2: evidence quality

- replay and benchmark commands write summaries under
  `data/recognition_reports/`
- those summaries preserve enough information to inspect bad outcomes:
  - expected and predicted identity
  - confidence
  - review flag
  - review reason or failure code when available
  - requested and effective mode when available
  - alternatives and artifact paths when available
- `fuzzy_enigma` runs emit portable reports and inspectable per-case artifacts

### Gate 3: config ownership

- replay and benchmark flows use explicit parent-owned config paths
- the active card-engine config can be identified from the run output or saved
  report
- local catalog and submodule query paths remain the default over ambient
  network lookups

### Gate 4: replayability

- at least one fixed golden-frame command is rerunnable without depending on
  mutable runtime regeneration
- saved summaries remain ingestible by `scripts/ingest_frames.py`

## Failure Conditions

The current gate fails when:

- the parent benchmark cannot run
- required evidence is missing from saved summaries
- replay or benchmark behavior depends on unclear local state
- local catalog or submodule-backed flows are bypassed by implicit external
  lookups in the supported path

## Related Docs

- `docs/runtime_reference.md`
- `docs/hardware_prep.md`
- `docs/submodule_feedback.md`
