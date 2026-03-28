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
- `data/card_catalog/cards.json`: local runtime card catalog.
- `config/sort_policies/*.json`: ranking preference source-of-truth policies.
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
	 - if you want the real vendored recognizer, also install `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`
3. Optional env file:
	 - Copy `.env.example` values into your environment.
4. Run:
	 - `python -m sorter.interfaces.cli --mode sim`
	 - or `python scripts/run_simulation.py`

## Recognition backend toggle

- Default sim backend: `SORTER_RECOGNIZER_BACKEND=sim_truth`
- Vendored submodule backend: `SORTER_RECOGNIZER_BACKEND=fuzzy_enigma`
- Parent-owned live card-engine config: `SORTER_CARD_ENGINE_CONFIG=config/card_engine/engine.json`
- Optional card-engine mode: `SORTER_CARD_ENGINE_MODE=greenfield`
- Recognition policy file: `SORTER_RECOGNITION_THRESHOLDS=config/vision/recognition_thresholds.json`
- Optional low-confidence fallback: `SORTER_FUZZY_ENIGMA_SIM_TRUTH_FALLBACK=1`

When `fuzzy_enigma` is enabled, the sim camera now passes the rendered top-card image path through the parent `Frame` so the real recognizer can operate on the same simulated images the sorter sees.
The parent repo now also owns a benchmark-specific card-engine config at `config/card_engine/benchmark.engine.json` so replay and benchmark runs can use a more realistic measurement budget without changing the live sorter config.

## Recognition replay and benchmark

- Replay the configured backend over simulated top-card captures:
	- `python scripts/replay_recognition.py --backend sim_truth`
- Replay the vendored recognizer with the parent benchmark config:
	- `python scripts/replay_recognition.py --backend fuzzy_enigma --pile 0,0`
- Generate a benchmark summary JSON:
	- `python scripts/benchmark_recognizer.py --backend sim_truth`
	- `python scripts/benchmark_recognizer.py --backend fuzzy_enigma`
- Compare two saved summaries directly:
	- `python scripts/compare_recognition_summaries.py --baseline data/recognition_reports/sim_truth_summary.json --candidate data/recognition_reports/fuzzy_enigma_summary.json`
- The summary JSON is written under `data/recognition_reports/`.
- For `fuzzy_enigma`, replay and benchmark commands automatically prefer the parent-owned benchmark config unless you override `--card-engine-config`.
- The summary JSON now includes alternatives and debug payloads, not just the final score line.

## Vision dataset ingest

- Parent-owned dataset root: `data/vision/`
- Import replay or benchmark outputs into the dataset layout:
	- `python scripts/ingest_frames.py --summary-json data/recognition_reports/fuzzy_enigma_summary.json --source-mode sim --split benchmark`
- Imported frames land under `data/vision/raw/...`
- Imported manifests land under `data/vision/labels/...`
- The initial stable sim-backed regression slice is documented in `tests/golden_frames/runtime_small_stack_top_cards.json`

If you want to run the real vendored recognizer, make sure the submodule OCR extras are installed first:

- `pip install -e ./third_party/fuzzy-enigma-card-recognition[ocr]`

## Hardware mode notes

- Hardware smoke entrypoint:
	- `python scripts/hardware_smoke_test.py`
- NeoPixels on BTT SKR 1.4 Turbo:
	- `src/sorter/adapters/hardware/neopixel_lights.py` maps machine status to Marlin `M150` RGB commands.
	- Integrate this with your serial transport to the SKR board firmware.

## Tests

- Run all tests:
	- `pytest -q`

## Sim image sync

- Log extracted card names and rebuild missing simulation images only when needed:
	- `python scripts/sync_simulated_images.py`
- Dry-run without downloading:
	- `python scripts/sync_simulated_images.py --no-fetch`
- The script writes a card log to `data/logs/simulated_cards.log`.
- Sim runs call this sync automatically before bootstrapping (`SORTER_AUTO_IMAGE_SYNC=1`).

## Configurable sim card list

- Card list source-of-truth: `config/sim_card_lists/default_cards.json`
- Runtime derived fixture: `data/generated/runtime_fixture.json`
- Defaults are controlled by:
	- `SORTER_SIM_CARD_LIST`
	- `SORTER_RUNTIME_FIXTURE`
- To disable this flow and use `SORTER_SCENARIO` directly, set:
	- `SORTER_SIM_CARD_LIST=none`

## Legacy to new module mapping

- `card.py` -> `src/sorter/domain/models.py` (+ `scripts/build_card_catalog.py`)
- `pile.py` -> `src/sorter/domain/models.py`
- `card_sorter.py` -> `src/sorter/domain/ranking_service.py` + `src/sorter/domain/policy_evaluator.py`
- `pile_manager.py` -> `src/sorter/domain/machine_state.py` + application use cases
- `gantry_system.py` -> `src/sorter/ports/motion.py` + `adapters/sim/sim_motion.py` + `adapters/hardware/marlin_motion.py`
- `camera_system.py` -> `src/sorter/ports/camera.py` + `adapters/sim/sim_camera.py` + `adapters/hardware/picamera2_camera.py`
- `ui_system.py` -> `src/sorter/interfaces/pygame_debug.py`
- `main_controller.py` -> `src/sorter/application/orchestrator.py`
- `config_manager.py` + `config.json` -> `src/sorter/config/settings.py` + `src/sorter/config/calibration.py` + `config/calibration.json`
- `generateSimulatedPiles.py` -> `src/sorter/adapters/persistence/scenario_loader.py`
- `downloadSimulatedImages.py` -> `scripts/build_card_catalog.py`

