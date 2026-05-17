# SortingMachineArray

Production-oriented test bed refactor for a card sorting machine using a hexagonal architecture.

## What is implemented

- `src/sorter/domain`: pure data/state, command/event models, policy-config ranking service, workflow state.
- `src/sorter/application`: orchestrator + use cases for planning/executing/verifying atomic moves.
- `src/sorter/ports`: motion, camera, vacuum, lights, recognizer, card catalog, run store.
- `src/sorter/adapters/sim`: deterministic `SimWorld` and simulation adapters.
- `src/sorter/adapters/hardware`: explicit hardware adapters (`marlin_motion`, `picamera2_camera`, `gpio_vacuum`, `neopixel_lights`).
- `src/sorter/adapters/persistence`: SQLite run store and local file card catalog.
- `src/sorter/interfaces`: CLI and thin Pygame debug shell.
- `scenarios/fixtures`: deterministic simulation fixtures.
- `data/card_catalog/cards.json`: local runtime card catalog synced from the vendored offline catalog.
- `config/sort_policies/*.json`: ranking preference source-of-truth policies.
- `config/vision/roi_profiles.json`: initial shared ROI ownership scaffold for sim and upcoming hardware captures.
- `tests/unit`, `tests/contract`, `tests/integration`: baseline automated tests.

## Architecture rules

- No domain model performs I/O.
- Application orchestrator depends only on ports.
- Adapters contain I/O and translation logic, not sorting policy.
- Simulation and hardware are swapped by wiring, not `if simulated` branches.
- Runtime has no network fetch dependency in the new flow.

## Run in sim mode

1. Create/activate a Python 3.11+ environment.
2. Install dependencies:
	 - `pip install -e .[dev]`
	 - if you want the real vendored recognizer, also install `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr,moss]`
3. Optional env file:
	 - Copy `.env.example` values into your environment.
4. Run:
	 - `python -m sorter.interfaces.cli --mode sim`
	 - or `python scripts/run_simulation.py`

## Web operator console

- Start the responsive web UI:
	- `python -m sorter.interfaces.web_runner`
- Then open:
	- `http://localhost:8000`
- Included pages:
	- dashboard with live camera panel, run controls, pile state, and latest recognition
	- machine page with axis and I/O controls
	- recognition page with local catalog validation and manual image recognition
	- recent run history
	- capability map that distinguishes ready vs partial hardware-facing features

The current web console is immediately useful in `sim` mode. The camera stream endpoint is already exposed, but the present `PiCamera2Adapter` is still a hardware stub, so true live Pi-camera frames require the hardware capture path to be completed.

## Recognition backend toggle

- Default recognizer backend: `SORTER_RECOGNIZER_BACKEND=moss_machine`
- Native fuzzy-enigma backend: `SORTER_RECOGNIZER_BACKEND=fuzzy_enigma`
- Sim-truth debug backend: `SORTER_RECOGNIZER_BACKEND=sim_truth`
- Parent-owned live card-engine config: `SORTER_CARD_ENGINE_CONFIG=config/card_engine/engine.json`
- Optional card-engine mode: `SORTER_CARD_ENGINE_MODE=greenfield`
- Recognition policy file: `SORTER_RECOGNITION_THRESHOLDS=config/vision/recognition_thresholds.json`
- Optional low-confidence fallback: `SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK=1`
- Startup scan retry budget: `SORTER_STARTUP_SCAN_MAX_RETRIES=1`
- Verification retry budget: `SORTER_VERIFICATION_MAX_RETRIES=2`
- Keep external image fetch opt-in: `SORTER_SIM_IMAGE_AUTO_FETCH=0`
- Keep external ranking enrichment opt-in: `SORTER_ALLOW_EXTERNAL_CARD_ENRICHMENT=0`

When `moss_machine` or `fuzzy_enigma` is enabled, the sim camera now passes the rendered top-card image path through the parent `Frame` so the real recognizer can operate on the same simulated images the sorter sees.
Startup discovery uses the same recognizer backend as the rest of the run, so the default startup path now exercises the vendored submodule too.
The parent repo now also owns a benchmark-specific card-engine config at `config/card_engine/benchmark.engine.json` so replay and benchmark runs can use a more realistic measurement budget without changing the live sorter config.
The sim camera no longer mutates pile observation state on capture by itself; observation now advances when the application processes recognizer results, which makes retries and `REVIEW_REQUIRED` escalation more honest.

## Recognition replay and benchmark

- Replay the configured backend over simulated top-card captures:
	- `python scripts/replay_recognition.py --backend sim_truth`
- Replay the vendored recognizer with the parent benchmark config:
	- `python scripts/replay_recognition.py --backend fuzzy_enigma --pile 1`
	- `python scripts/replay_recognition.py --backend moss_machine --pile 1`
- Generate a benchmark summary JSON:
	- `python scripts/benchmark_recognizer.py --backend sim_truth`
	- `python scripts/benchmark_recognizer.py --backend fuzzy_enigma`
	- `python scripts/benchmark_recognizer.py --backend moss_machine`
	- `python scripts/benchmark_recognizer.py --backend fuzzy_enigma --card-engine-mode small_pool --use-expected-label`
	- `python scripts/benchmark_recognizer.py --backend fuzzy_enigma --card-engine-mode reevaluation --use-expected-label`
	- `python scripts/benchmark_recognizer.py --backend fuzzy_enigma --card-engine-mode confirmation --use-expected-label`
- Run the fixed golden-frame manifest without regenerating runtime state:
	- `python scripts/run_golden_frames.py --backend fuzzy_enigma --card-engine-mode small_pool --use-expected-label`
- Compare two saved summaries directly:
	- `python scripts/compare_recognition_summaries.py --baseline data/recognition_reports/sim_truth_summary.json --candidate data/recognition_reports/fuzzy_enigma_summary.json`
- Package the current feedback doc plus portable evidence for the submodule developer:
	- `python scripts/package_submodule_feedback.py`
- The summary JSON is written under `data/recognition_reports/`.
- Portable success/failure reports are written under `data/recognition_reports/portable/`.
- For `fuzzy_enigma` and `moss_machine`, replay and benchmark commands automatically prefer the parent-owned benchmark config unless you override `--card-engine-config`.
- The summary JSON now includes alternatives, review reasons, confidence-band counts, and debug payloads, not just the final score line.
- Replay and benchmark commands now accept `--card-engine-mode` so mode requests are explicit and reportable.
- Replay and benchmark commands now accept `--use-expected-label`, `--use-tracked-pool`, `--track-result`, and `--prefer-visual-small-pool` so parent-side mode experiments are explicit and portable.
- `fuzzy_enigma` replay and benchmark runs also export inspectable per-case artifacts under `data/recognition_reports/artifacts/` by default, including copied source frames, `ocr_lines.txt`, `debug.json`, and `bbox.json` when available.
- Portable reports include requested mode, effective mode, request options, submodule SHA, and separate success/failure case lists so they can be handed to the submodule developer directly.
- Sim runs can now return `REVIEW_REQUIRED` when startup scan or post-move verification exhausts the configured retry budget.
- Golden-frame runs reuse the same summary, artifact, and portable-report pipeline, so saved sim slices and future hardware captures can converge on one evidence format.

## Vision dataset ingest

- Parent-owned dataset root: `data/vision/`
- Import replay or benchmark outputs into the dataset layout:
	- `python scripts/ingest_frames.py --summary-json data/recognition_reports/fuzzy_enigma_summary.json --source-mode sim --split benchmark`
- Imported frames land under `data/vision/raw/...`
- Imported manifests land under `data/vision/labels/...`
- The initial stable sim-backed regression slice is documented in `tests/golden_frames/runtime_small_stack_top_cards.json`

If you want to run the real vendored recognizer, make sure the submodule OCR and Moss extras are installed first:

- `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr,moss]`

## Hardware mode notes

- Hardware smoke entrypoint:
	- `python scripts/hardware_smoke_test.py`
- Hardware prep reference:
	- `docs/hardware_prep.md`
- NeoPixels on BTT SKR 1.4 Turbo:
	- `src/sorter/adapters/hardware/neopixel_lights.py` maps machine status to Marlin `M150` RGB commands.
	- Integrate this with your serial transport to the SKR board firmware.

## Tests

- Run all tests:
	- `pytest -q`
- Noisy-sim review escalation coverage:
	- `pytest tests/integration/test_noisy_sim_review_required.py -q`
- Run the current pre-hardware acceptance envelope:
	- `python scripts/check_acceptance.py`

## Sim image sync

- Log extracted card names and rebuild missing simulation images only when needed:
	- `python scripts/sync_simulated_images.py`
- Dry-run without downloading:
	- `python scripts/sync_simulated_images.py --no-fetch`
- The script writes a card log to `data/logs/simulated_cards.log`.
- Sim runs call this sync automatically before bootstrapping (`SORTER_AUTO_IMAGE_SYNC=1`).
- Automatic remote image fetch is opt-in (`SORTER_SIM_IMAGE_AUTO_FETCH=0` by default).

## Configurable sim card list

- Card list source-of-truth: `config/sim_card_lists/default_cards.json`
- Runtime derived fixture: `data/generated/runtime_fixture.json`
- The checked-in parent card catalog is now synced from the vendored offline catalog instead of carrying a stale handwritten demo set.
- Refresh the parent catalog from the current default sim list with:
	- `python scripts/sync_parent_card_catalog.py`
- Defaults are controlled by:
	- `SORTER_SIM_CARD_LIST`
	- `SORTER_RUNTIME_FIXTURE`
- To disable this flow and use `SORTER_SCENARIO` directly, set:
	- `SORTER_SIM_CARD_LIST=none`

## OCR implementation guide

- PaddleOCR integration planning guide:
	- `docs/paddleocr_path_guide.md`

## Current Docs

- Forward plan from the current repo state:
	- `PROJECT_ROADMAP.md`
- Runtime intent and config ownership:
	- `docs/runtime_reference.md`
- Acceptance and verification rules:
	- `docs/acceptance_gates.md`
- Hardware bring-up preparation:
	- `docs/hardware_prep.md`
- Current upstream feedback for the vendored recognizer:
	- `docs/submodule_feedback.md`

