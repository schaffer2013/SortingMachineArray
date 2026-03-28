# Submodule Feedback

## Purpose

This document captures concrete parent-project feedback for
`third_party/fuzzy-enigma-card-recognition` based on real integration work in
this repo.

The goal is to hand the submodule developer short, evidence-backed requests
instead of vague wishes.

## Current Status

Several early parent asks are now resolved upstream and adopted in this repo:

- first-class `requested_mode` and `effective_mode`
- stable `mode_flags`
- stable `failure_code` and `review_reason`
- offline catalog query API
- engine-side artifact export
- identifier-first `expected_card` support with `scryfall_id` and `oracle_id`

The remaining asks are now more about completeness and ergonomics than missing
foundations.

## Current Parent Needs

### 1. Structured pipeline summary should remain first-class and stable

The engine now exposes structured mode metadata cleanly. The next high-value
piece is making sure the pipeline summary remains stable and clearly documented
for parent repos that need portable evidence.

Requested upstream improvement:

- keep `pipeline_summary` stable and documented, including:
  - `resolution_path`
  - `branches_fired`
  - title ROI summary
  - secondary OCR summary
  - visual-small-pool usage

Why this matters:

- the parent now saves portable success and failure reports directly from the
  upstream result shape
- portable reports are more useful when the resolution path is consistent and
  versionable

### 2. Parent-facing adapter support should stay explicit and stable

The parent repo is now driving:

- `small_pool` with identifier-first expected-card requests
- `reevaluation` with identifier-first expected-card requests
- `confirmation` with identifier-first expected-card requests

Requested upstream improvement:

- keep the adapter support explicit and stable for:
  - expected card by identifiers
  - candidate pool by identifiers
  - explicit tracked-pool usage controls

Why this matters:

- the parent can then use:
  - `reevaluation` for "I think this is X"
  - `confirmation` for verification after a move
  - `small_pool` once the local candidate pool is known

### 3. Parent repos still benefit from a structured offline catalog query API

This is now available upstream. The remaining parent need is adoption and
continued stability as the parent leans harder on local identifier-first flows.

Requested upstream improvement:

- keep the query API stable for:
  - card identity by name or IDs
  - exact printing candidates by name
  - set-code or collector-number refinement when available

Why this matters:

- the parent wants to avoid external card-info lookups
- sorter-side planning and confirmation flows should become more ID-driven over
  time

### 4. First-class artifact export should stay compatible with parent evidence tooling

The parent now consumes engine-side metadata directly and packages its own
portable evidence bundles around that. Keeping the engine export stable will
reduce future duplication.

Requested upstream improvement:

- keep engine-side artifact export stable for:
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
- behavior is now surfaced directly by the engine and preserved by the parent

Recent mode comparison results from the parent repo:

- `greenfield` on the current six-card sim slice:
  - `name_accuracy=0.667`
  - `review_count=2`
- `small_pool` with explicit expected-label requests:
  - `name_accuracy=0.833`
  - `review_count=2`
  - `effective_mode_counts={"small_pool": 6}`
- `reevaluation` with explicit expected-label requests:
  - `name_accuracy=0.500`
  - `review_count=3`
- `confirmation` with explicit expected-label requests:
  - `name_accuracy=0.667`
  - `review_count=3`
- fixed golden-frame manifest with `small_pool` plus expected-label requests:
  - `name_accuracy=0.833`
  - `review_count=0`

The parent repo can also package the current feedback doc plus portable evidence
into one handoff bundle with:

```powershell
.\.venv\Scripts\python.exe scripts\package_submodule_feedback.py
```

## Current Ask Priority

1. stable pipeline summary semantics
2. stable parent-facing expected-card and candidate-pool controls
3. stable offline catalog query API
4. stable artifact export compatibility
