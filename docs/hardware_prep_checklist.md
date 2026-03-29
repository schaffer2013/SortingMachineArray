# Hardware Prep Checklist

## Purpose

This is the pre-hardware software checklist for the next camera and motion integration pass.

The goal is to make the first real hardware session diagnose camera, lighting, calibration, and motion issues instead of rediscovering missing software setup.

## Before Touching Hardware

- Create and activate the shared `.venv`.
- Install parent repo deps:
  - `pip install -e .[dev]`
- Install vendored recognizer deps:
  - `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`
- Confirm the parent repo can import and run the vendored recognizer from the repo root.

## Commands That Should Pass First

```powershell
.\.venv\Scripts\python.exe -m pytest tests
.\.venv\Scripts\python.exe scripts\check_acceptance.py
.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma
.\.venv\Scripts\python.exe scripts\run_golden_frames.py --backend fuzzy_enigma --card-engine-mode small_pool --use-expected-label
.\.venv\Scripts\python.exe scripts\package_submodule_feedback.py
```

## Configs To Verify

- Parent runtime env defaults:
  - `.env.example`
- Parent calibration config:
  - `config/calibration.json`
- Parent card-engine live config:
  - `config/card_engine/engine.json`
- Parent card-engine benchmark config:
  - `config/card_engine/benchmark.engine.json`
- Parent recognition thresholds:
  - `config/vision/recognition_thresholds.json`
- Initial shared ROI ownership stub:
  - `config/vision/roi_profiles.json`
- Parent sim-card-list source of truth:
  - `config/sim_card_lists/default_cards.json`
- Parent card catalog snapshot:
  - `data/card_catalog/cards.json`

## Recommended Preflight Refresh

- Refresh the parent card catalog from the current sim list:
  - `python scripts/sync_parent_card_catalog.py`
- Rebuild the generated runtime fixture if the sim list changed:
  - run the normal sim bootstrap once or regenerate through the parent flow
- Repackage the current upstream feedback bundle:
  - `python scripts/package_submodule_feedback.py`

## Expected Outputs To Inspect

- Acceptance envelope:
  - `data/recognition_reports/acceptance_envelope.json`
- Portable success/failure reports:
  - `data/recognition_reports/portable/`
- Per-case benchmark artifacts:
  - `data/recognition_reports/artifacts/`
- Feedback bundle for the submodule developer:
  - `data/recognition_reports/feedback_bundle/submodule_feedback_bundle.zip`

## First Hardware Session Focus

- Verify camera framing is stable and centered enough for future ROI tuning.
- Verify exposure and lighting can be held steady enough for repeatable captures.
- Verify motion can reach pile coordinates safely before any live pick/place loop.
- Save every useful capture so the same parent replay and benchmark tools can be reused.
- Do not optimize throughput yet.

## Out Of Scope For The First Pass

- unattended sorting
- aggressive speed tuning
- broad ROI tuning inside adapter code
- adding hidden hardware-only branches to core planning logic
