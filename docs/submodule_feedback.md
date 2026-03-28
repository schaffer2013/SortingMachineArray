# Submodule Feedback

## Purpose

This document captures concrete parent-project feedback for
`third_party/fuzzy-enigma-card-recognition` based on real integration work in
this repo.

The goal is to hand the submodule developer short, evidence-backed requests
instead of vague wishes.

## Current Parent Needs

### 1. Structured mode metadata should be first-class

The engine already places requested and effective mode information inside debug
payloads, but parent repos benefit when this is exposed as a stable structured
result field instead of requiring debug parsing.

Requested upstream improvement:

- return `requested_mode`
- return `effective_mode`
- return mode-related flags such as:
  - expected-card present
  - candidate-pool present
  - tracked-pool used
  - visual-small-pool path used

Why this matters:

- the parent now saves portable success and failure reports
- mode-aware comparisons are harder when the parent must scrape raw debug blobs

### 2. Constrained-mode precondition failures should return structured results, not exceptions

Observed parent-side case:

- requesting `small_pool` without a tracked pool currently raises
  `ValueError("No tracked pool is available for constrained recognition.")`

Parent-side workaround:

- the parent now catches that failure and converts it into a reviewable result
  with `review_reason=missing_tracked_pool`

Requested upstream improvement:

- return a structured failure result with a stable error code such as
  `missing_tracked_pool`
- avoid forcing parent repos to catch mode-precondition exceptions around
  otherwise normal recognition calls

Why this matters:

- parent benchmarks should be able to compare modes safely
- hardware-time failures should become evidence, not crashes

### 3. Parent-facing adapter should eventually accept expected-card and candidate-pool inputs directly

The parent repo wants to use more than just open-ended `greenfield`
recognition.

Requested upstream improvement:

- expose adapter-level support for:
  - expected card by identifiers
  - candidate pool by identifiers
  - explicit tracked-pool usage controls

Why this matters:

- the parent can then use:
  - `reevaluation` for "I think this is X"
  - `confirmation` for verification after a move
  - `small_pool` once the local candidate pool is known

### 4. Stable failure and review reason codes would reduce parent guesswork

Requested upstream improvement:

- return stable machine-readable reason codes for failures such as:
  - `missing_tracked_pool`
  - `deadline_exceeded`
  - `detection_failed`
  - `ocr_weak`
  - `candidate_tie_unresolved`
  - `expected_card_contradicted`

Why this matters:

- the parent currently infers review reasons from a mix of policy and debug
  payloads
- structured reasons would make logs, portable reports, and operator recovery
  simpler

### 5. First-class artifact export would be valuable

The parent now exports its own portable evidence bundles, but it still has to
reconstruct them from adapter output.

Requested upstream improvement:

- optional engine-side artifact export for:
  - normalized image
  - ROI crops
  - OCR text
  - bbox
  - candidate list
  - timings
  - mode metadata

Why this matters:

- upstream and parent repos would then inspect the same evidence model
- it would reduce duplicated packaging work in embedding repos

## Current Parent Evidence

The parent repo can now generate portable success or failure reports with:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --portable-out tmp_portable_check\portable.json `
  --artifact-root tmp_portable_check\artifacts
```

Recent concrete result:

- `greenfield` benchmark remains operational from the parent repo
- `small_pool` without tracked-pool setup is now captured as a safe reviewable
  result instead of a crash
- requested mode: `small_pool`
- review reason cluster: `missing_tracked_pool`
- behavior is now safely reportable from the parent side, but it would be
  better if the engine surfaced that condition directly

## Current Ask Priority

1. structured failure codes
2. first-class requested and effective mode fields
3. adapter support for expected-card and candidate-pool inputs
4. optional artifact export
