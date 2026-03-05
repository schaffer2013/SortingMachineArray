# SortingMachineArray

Production-oriented test bed refactor for a card sorting machine using a hexagonal architecture.

## What is implemented

- `src/sorter/domain`: pure data/state, command/event models, sort policy, workflow state.
- `src/sorter/application`: orchestrator + use cases for planning/executing/verifying atomic moves.
- `src/sorter/ports`: motion, camera, vacuum, lights, recognizer, card catalog, run store.
- `src/sorter/adapters/sim`: deterministic `SimWorld` and simulation adapters.
- `src/sorter/adapters/hardware`: explicit hardware adapters (`marlin_motion`, `picamera2_camera`, `gpio_vacuum`, `neopixel_lights`).
- `src/sorter/adapters/persistence`: SQLite run store and local file card catalog.
- `src/sorter/interfaces`: CLI and thin Pygame debug shell.
- `scenarios/fixtures`: deterministic simulation fixtures.
- `data/card_catalog/cards.json`: local runtime card catalog.
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
3. Optional env file:
	 - Copy `.env.example` values into your environment.
4. Run:
	 - `python -m sorter.interfaces.cli --mode sim`
	 - or `python scripts/run_simulation.py`

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

## Legacy to new module mapping

- `card.py` -> `src/sorter/domain/models.py` (+ `scripts/build_card_catalog.py`)
- `pile.py` -> `src/sorter/domain/models.py`
- `card_sorter.py` -> `src/sorter/domain/sort_policy.py`
- `pile_manager.py` -> `src/sorter/domain/machine_state.py` + application use cases
- `gantry_system.py` -> `src/sorter/ports/motion.py` + `adapters/sim/sim_motion.py` + `adapters/hardware/marlin_motion.py`
- `camera_system.py` -> `src/sorter/ports/camera.py` + `adapters/sim/sim_camera.py` + `adapters/hardware/picamera2_camera.py`
- `ui_system.py` -> `src/sorter/interfaces/pygame_debug.py`
- `main_controller.py` -> `src/sorter/application/orchestrator.py`
- `config_manager.py` + `config.json` -> `src/sorter/config/settings.py` + `src/sorter/config/calibration.py` + `config/calibration.json`
- `generateSimulatedPiles.py` -> `src/sorter/adapters/persistence/scenario_loader.py`
- `downloadSimulatedImages.py` -> `scripts/build_card_catalog.py`

