# Runtime Reference

## Purpose

This document captures the current long-lived intent for the repo: what the
supported runtime is, how configuration is owned, and what behavior the code
should optimize for.

## Current Product Shape

- The project is a supervised Magic card sorting machine.
- The current supported software path is the parent repo under `src/sorter/...`.
- The sorter should prefer inspectability and safe recovery over silent guesses.
- Simulation, replay, benchmark, and golden-frame workflows are first-class
  because they are how we validate changes before hardware use.

## Supported Runtime Modes

- `sim` is the current supported end-to-end runtime.
- `hardware` remains a bring-up path driven by explicit smoke and prep scripts,
  not a general-purpose CLI flow yet.
- The recognizer boundary is owned by `RecognizerPort`.
- The parent repo currently supports:
  - `fuzzy_enigma` as the default sim/runtime backend
  - `sim_truth`
    for controlled debugging and comparison runs

## Recognition And Review Policy

- Runtime behavior should be driven by local catalog data and submodule APIs by
  default.
- External live card lookups are opt-in and should only be used when local data
  is insufficient for the requested behavior.
- Low-confidence or contradictory recognition should produce reviewable evidence
  rather than quietly collapsing into a guessed success.
- Reports, replays, and artifacts should stay understandable enough that a
  parent developer or submodule developer can diagnose a failure from saved
  outputs.

## Configuration Ownership

- Environment defaults live in `.env.example`.
- Runtime configuration is loaded through `src/sorter/config/settings.py`.
- Calibration data lives in `config/calibration.json`.
- Recognition thresholds live in `config/vision/recognition_thresholds.json`.
- ROI ownership lives in `config/vision/roi_profiles.json`.
- Parent-owned card-engine configs live under `config/card_engine/`.
- The checked-in parent card catalog snapshot lives at
  `data/card_catalog/cards.json`.

## Calibration Expectations

- Calibration values should remain configuration-owned, not hard-coded into
  adapters or orchestration logic.
- Coarse pile coordinates and machine calibration belong in the parent config.
- Fine tuning and ROI adjustments should be explicit operator actions, not
  hidden side effects of normal startup.
- Fixed `place_z_mm` remains the current fallback placement height, but the
  hardware path should be able to derive a safer pile-specific placement height
  from a probe measurement when a BLTouch-style or equivalent probing method is
  available.
- Hardware-facing assumptions should stay visible in docs and config rather than
  being buried in adapter-specific code.

## Camera-Driven Micro-Calibration Contract

- The hardware target uses six piles arranged as three columns by two rows.
- Coarse pile coordinates still come from `config/calibration.json`, but they
  are treated as a starting guess for hardware runs, not a guaranteed final
  pick location.
- Before normal sorting, the machine should support a micro-calibration pass
  that uses the end-effector camera to align each pile to a shared visual
  reference: the back of a Magic card framed at a consistent pixel location.
- During this pass, the end effector may move in XY and Z to center and scale
  the card-back reference so each pile produces the same camera-space target.
- Per-pile XY (and, when needed, effective Z contact/approach) offsets from the
  camera alignment should be persisted as calibration-owned data so picks and
  places are repeatable across runs.
- The goal is to prevent accumulated pick/place drift: suction contact should
  happen at the same relative location on cards in every pile, including after
  many repeated transfers.
- BLTouch-style probing remains complementary to this flow: probing handles
  pile-height safety and placement clearance, while camera micro-calibration
  handles lateral centering and card-face alignment.

## Documentation Set

The current docs with active purpose are:

- `README.md`: repo entrypoint and supported commands
- `PROJECT_ROADMAP.md`: forward-looking milestone order from the current repo state
- `docs/runtime_reference.md`: enduring runtime intent and config ownership
- `docs/acceptance_gates.md`: current acceptance commands and evidence rules
- `docs/hardware_prep.md`: software-side preparation before hardware work
- `docs/submodule_feedback.md`: current upstream asks backed by parent evidence
- `docs/paddleocr_path_guide.md`: OCR integration guidance

Historical planning notes and completed sprint worksheets should not stay in the
active docs set once they stop guiding current work.
