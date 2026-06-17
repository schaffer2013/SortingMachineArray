# Hardware Prep Checklist

## Purpose

Use this checklist before a real hardware session. The goal is to make sure the
parent repo, configs, and recognition tooling are ready before spending time on
camera, lighting, calibration, or motion debugging.

## Session Type

Pick one primary goal for the session:

- [ ] capture and lighting validation
- [ ] calibration and pile alignment
- [ ] motion and pick-place bring-up
- [ ] recognition evidence collection
- [ ] supervised end-to-end smoke run

## Environment Checklist

- [ ] activate the shared `.venv`
- [ ] install parent repo dependencies:
  - `pip install -e .[dev]`
- [ ] install vendored recognizer extras if this session uses
      `fuzzy_enigma`:
  - `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`
- [ ] confirm environment defaults are present or intentionally overridden from
      `.env.example`

## Config Checklist

- [ ] verify `config/calibration.json`
  - confirm whether this session is using fixed `place_z_mm` or a probe-aware
    placement experiment
  - confirm BLTouch fields (`probe_enabled`, retract, clearance, max contact)
    match the firmware configuration
- [ ] verify Marlin firmware matches `docs/marlin_firmware_contract.md`
  - confirm X/Y/Z/C are standard absolute coordinates
  - confirm Z homes first toward positive EOT on its normal endstop
  - confirm C homes second toward negative EOT using sensorless homing
  - confirm X/Y home together after Z and C are homed
  - confirm BLTouch deploy/stow/probe behavior before any pile probing
- [ ] verify `config/card_engine/engine.json`
- [ ] verify `config/card_engine/benchmark.engine.json`
- [ ] verify `config/vision/recognition_thresholds.json`
- [ ] verify `config/vision/roi_profiles.json`
- [ ] verify `config/sim_card_lists/default_cards.json` if you plan to compare
      against sim-backed reports
- [ ] verify `data/card_catalog/cards.json` is current enough for the planned
      session

## Refresh Checklist

- [ ] refresh the parent card catalog if card metadata or image coverage has
      changed:
  - `python scripts/sync_parent_card_catalog.py`
- [ ] refresh the derived runtime fixture if the sim card list changed
- [ ] package a fresh submodule feedback bundle if this session is meant to
      collect upstream evidence:
  - `python scripts/package_submodule_feedback.py`

## Software Gate Checklist

These should pass before the session unless you are explicitly debugging one of
them.

- [ ] parent tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests
```

- [ ] acceptance envelope:

```powershell
.\.venv\Scripts\python.exe scripts\check_acceptance.py
```

- [ ] submodule benchmark baseline:

```powershell
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma
```

- [ ] golden-frame sample:

```powershell
.\.venv\Scripts\python.exe scripts\run_golden_frames.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --use-expected-label
```

- [ ] feedback bundle packaging:

```powershell
.\.venv\Scripts\python.exe scripts\package_submodule_feedback.py
```

## Hardware Session Checklist

- [ ] confirm the session's startup path and operator station are ready
- [ ] confirm a capture location exists for any new real-world frames
- [ ] if this session includes pile calibration, run camera-driven
      micro-calibration over all six piles (3x2) before throughput testing
- [ ] during micro-calibration, align each pile so the card-back reference
      appears at the same camera-space position and scale
- [ ] save any resulting per-pile calibration offsets to config-owned data
      instead of ad-hoc operator notes
- [ ] confirm how safe placement height will be chosen for this session:
      fixed placement height or probe-derived pile-top measurement
- [ ] if using BLTouch probing, confirm failed probe states stop motion and are
      visible to the operator
- [ ] confirm you will save enough context to replay failures later
- [ ] confirm the session avoids throughput tuning unless correctness is already
      stable
- [ ] confirm there is a clear stop condition for unsafe motion, bad picks, or
      unusable recognition output

## Outputs To Inspect After The Session

- [ ] `data/recognition_reports/acceptance_envelope.json`
- [ ] `data/recognition_reports/portable/`
- [ ] `data/recognition_reports/artifacts/`
- [ ] `data/recognition_reports/feedback_bundle/submodule_feedback_bundle.zip`
- [ ] any new saved hardware captures intended for replay or dataset ingest

## What A Good First Hardware Session Produces

- [ ] stable framing notes
- [ ] lighting notes tied to saved captures
- [ ] at least one replayable batch of real frames
- [ ] any calibration changes captured in config instead of scratch notes
- [ ] evidence that camera micro-calibration was performed across all six piles
      and produced a consistent card-back alignment reference
- [ ] if probing is used, a record of the measured pile-top heights or the
      resulting safe placement rule
- [ ] a short record of what blocked progress and whether it belongs in
      `docs/submodule_feedback.md`, `docs/acceptance_gates.md`, or code
