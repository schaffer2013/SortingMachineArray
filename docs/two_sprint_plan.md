# Two Sprint Plan

## Purpose

This document turns the roadmap into a concrete plan for two focused `8` hour implementation sprints.

The goal of these `16` hours is not to "finish the whole roadmap." The best use of the time is to move the project from:

- "the real recognizer is wired in and benchmarkable"

to:

- "the real recognizer is measurable, replayable, and starting to drive planner behavior through honest observation rather than sim truth"

## Planning Assumptions

- The parent repo now has a toggleable `fuzzy_enigma` backend and replay/benchmark scripts.
- The next highest-leverage work is in roadmap Phases `2`, `3`, `4`, `5`, `7`, and `8`, not in hardware-heavy Phase `6`.
- These sprints should prioritize reusable seams, measurable progress, and debug visibility over one-off features.
- If the `fuzzy-enigma-card-recognition` OCR extras are not installed, Sprint 1 starts by unblocking that environment.

## What These Sprints Should Optimize For

- Real recognizer evidence over assumptions
- Observation-honest application behavior
- Replayable failures
- Confidence-based recovery paths
- Benchmarks and acceptance signals that can guide the next sprint

## Explicit Non-Goals For These Two Sprints

- Full hardware runtime completion
- Final operator UI
- Perfect OCR or perfect recognition accuracy
- Full dataset labeling platform
- Final acceptance-gate thresholds for the entire project

## Sprint 1

**Theme:** Make the real recognizer operational, measurable, and inspectable inside the parent project.

**Primary roadmap alignment**

- Phase `3`: shared vision and OCR platform
- Phase `4`: data, labeling, and recognition tooling
- Phase `7`: early test gates
- Phase `8`: replay/debuggability

### Sprint 1 Outcomes

- `fuzzy_enigma` runs successfully from the parent project in sim mode.
- We have a real benchmark baseline comparing `sim_truth` and `fuzzy_enigma`.
- Recognition runs save enough artifacts to diagnose failures.
- There is a defined dataset layout for saved frames and benchmark inputs.
- There is at least one first-pass golden-frame or stable benchmark set in the parent repo.

### Sprint 1 Work Plan

#### 1. Unblock and baseline the real backend

- Install and validate `third_party/fuzzy-enigma-card-recognition[ocr]`.
- Run parent-side replay and benchmark scripts against `fuzzy_enigma`.
- Record the first benchmark outputs in a human-readable summary.
- Identify the first obvious gap:
  - missing OCR backend
  - empty detection mismatch
  - bad config path
  - low-confidence flood
  - poor split-card handling

**Why first:** everything else is more valuable once there is a real measured baseline.

#### 2. Save richer recognition artifacts

- Persist benchmark-friendly artifacts under a stable parent-owned layout:
  - raw frame path or copy
  - predicted card
  - confidence
  - candidate list
  - `scryfall_id`
  - `oracle_id`
  - debug payload
  - backend used
- Add optional saving of normalized crops and OCR snippets when available from the adapter boundary.
- Make replay output easy to diff between `sim_truth` and `fuzzy_enigma`.

**Why second:** if the backend performs badly, we need inspectable evidence immediately.

#### 3. Create the parent dataset layout and ingestion path

- Add the initial structure for:
  - `data/vision/raw/`
  - `data/vision/normalized/`
  - `data/vision/labels/`
- Implement `scripts/ingest_frames.py` for metadata-preserving import.
- Define a small manifest format for frame metadata:
  - pile id
  - timestamp
  - source mode
  - backend
  - expected card name
  - predicted card name
  - confidence

**Why third:** this keeps replay and future hardware captures from becoming ad hoc.

#### 4. Establish a stable benchmark slice

- Create a small benchmark split that is intentionally stable.
- Seed it from simulated captures first if needed.
- Add a first curated `tests/golden_frames/` subset or equivalent benchmark fixture manifest.
- Add one command or doc section showing how to rerun the same benchmark repeatedly.

**Why fourth:** once a baseline exists, future recognition changes become measurable.

#### 5. Tighten docs and acceptance signals

- Add `docs/acceptance_gates.md` as a first-pass draft focused on perception and replay.
- Document:
  - how to run `sim_truth`
  - how to run `fuzzy_enigma`
  - how to compare them
  - what counts as a concerning result
- Update the roadmap checkboxes for anything genuinely completed.

**Why fifth:** this prevents the sprint from producing code without a way to judge it.

### Sprint 1 Suggested Time Allocation

1. `1.5h`: install/unblock OCR extras and run real baseline
2. `2h`: improve artifact persistence and replay visibility
3. `2h`: dataset layout plus `scripts/ingest_frames.py`
4. `1.5h`: stable benchmark split and golden-frame seed
5. `1h`: acceptance doc, cleanup, and test pass

### Sprint 1 Exit Criteria

- `fuzzy_enigma` can be run from the parent repo without manual guesswork.
- Benchmark output exists for both backends.
- Recognition artifacts are inspectable after a run.
- Dataset layout and ingest path exist in-repo.
- A repeatable benchmark slice is documented.

## Sprint 2

**Theme:** Use real observations and confidence signals to start changing planner behavior.

**Primary roadmap alignment**

- Phase `2`: honest observation limits
- Phase `5`: planner and state robustness
- Phase `7`: noisy sim and regression tests
- Phase `8`: replay and debugging surfaces

### Sprint 2 Outcomes

- Planner decisions depend more directly on observed state and less on convenient sim assumptions.
- Low-confidence reads trigger explicit recovery behavior.
- We have at least one noisy-sim path that exercises perception failure handling.
- Run logs and replay are rich enough to explain a bad move or stalled run.

### Sprint 2 Work Plan

#### 1. Refactor discovery and verification around explicit observations

- Push more state changes through observation events instead of direct pile mutation shortcuts.
- Make feeder discovery more realistic:
  - only learn next visible card after a scan or reveal
  - only confirm empty after a legitimate scan or pick/verify path
- Add observation staleness tracking where useful.

**Why first:** this is the core honesty boundary between simulator convenience and real machine behavior.

#### 2. Add recovery policy for uncertain recognition

- Define first-pass behavior for:
  - re-scan
  - retry count
  - mark-for-review
  - optional quarantine path
- Make verification answer:
  - what was expected
  - what was observed
  - whether confidence was sufficient
  - what retry or escalation should happen next

**Why second:** a real recognizer is only useful if uncertainty causes safe behavior.

#### 3. Add noisy sim scenarios

- Create `tests/noisy_sim/` fixtures or equivalent scenario coverage.
- Simulate a few high-value fault classes:
  - missing image
  - low confidence
  - false empty
  - ambiguous candidate list
  - stale observation after movement
- Use those scenarios in integration tests.

**Why third:** the planner should start failing in realistic ways before hardware does it for real.

#### 4. Expand run metrics and replay summaries

- Add run metrics for:
  - scans
  - retries
  - reviews
  - fallbacks
  - confidence distribution
  - stale-observation hits
- Improve replay output so a single failed move is explainable from saved data.
- If feasible, add a lightweight SQLite-to-report script.

**Why fourth:** this makes planner changes auditable instead of subjective.

#### 5. Add stronger tests and update planning docs

- Add unit and integration tests for:
  - observation-state transitions
  - low-confidence routing
  - stale observation behavior
  - noisy sim recovery paths
- Update roadmap status and acceptance draft from actual sprint results.

**Why fifth:** this locks in the progress and makes the next sprint start from firmer ground.

### Sprint 2 Suggested Time Allocation

1. `2.5h`: discovery and observation-state refactor
2. `2h`: recovery policy and verification changes
3. `1.5h`: noisy sim fixtures and tests
4. `1h`: run metrics and replay summary improvements
5. `1h`: docs, cleanup, and full test pass

### Sprint 2 Exit Criteria

- Planner behavior is more observation-driven than before.
- Low-confidence recognition leads to a defined next action.
- At least one noisy-sim failure path is replayable and tested.
- Run logs and reports can explain a bad recognition-driven decision.

## Recommended Order Across The Full 16 Hours

1. Make `fuzzy_enigma` actually runnable and measurable in the parent repo.
2. Save artifacts so failures are explainable.
3. Create the dataset and benchmark backbone.
4. Refactor planner behavior to honor observations and uncertainty.
5. Add noisy-sim tests so recovery logic gets exercised.
6. Capture the resulting acceptance signals in docs.

## Highest-Risk Dependencies

- The OCR backend may still need environment work before `fuzzy_enigma` produces meaningful results.
- The submodule may expose useful debug info inconsistently across modes.
- Planner refactors can easily reintroduce hidden sim truth if boundaries are not watched carefully.
- Replay and benchmark data can become noisy or non-repeatable if manifests are not versioned early.

## Decision Rules During The Sprint

- Prefer work that improves both sim and future hardware paths.
- Prefer config-driven changes over hard-coded heuristics.
- Prefer replayable evidence over subjective inspection.
- Prefer explicit recovery behavior over silent fallback.
- If a task does not improve recognizer measurability, observation honesty, or recovery behavior, it is probably not the best use of these `16` hours.

## Deliverables Expected By The End Of Both Sprints

- A working parent-side `fuzzy_enigma` benchmark flow
- Parent-owned saved recognition artifacts
- A durable frame dataset layout and ingest script
- A first stable benchmark or golden-frame slice
- More honest observation-driven planner behavior
- Low-confidence recovery logic with tests
- At least one noisy-sim regression path
- A first draft of acceptance gates tied to real commands and outputs
