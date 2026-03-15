# Phase 2 Gameplan

## Status

Drafted on 2026-03-14.
Slice 1 status: complete on 2026-03-14.

This document turns the Phase 2 roadmap into an execution plan for making the simulator obey the same observation limits the real machine will have.

## Phase 2 Goal

Phase 2 should make the sorter behave like a machine that only knows what it has actually observed.

By the end of this phase:

- the planner should no longer depend on hidden full-stack sim truth
- pile knowledge should be represented as observations, not as binary discovered or not-discovered flags
- discovery should happen through scan, pick, verify, and empty confirmation steps
- ranking should update progressively as cards are observed and only become final after the last pile is fully discovered
- the simulator should be able to produce realistic ambiguity and perception-related failures

## Why This Phase Exists

The current architecture is already split into domain, application, ports, adapters, and interfaces. That is a strong base. The main remaining problem is behavioral honesty: sim can still know more than hardware ever will.

If we skip this phase, later planner and vision work will be optimized around unrealistic knowledge and will likely need rework.

## Phase Boundary

Phase 2 is about state honesty and sim behavior, not full real recognition.

In scope:

- separating hidden sim truth from observed runtime state
- richer pile observation state
- discovery-driven planning and ranking updates
- realistic sim faults and ambiguity
- tests and fixtures that prove planner behavior under partial knowledge

Out of scope:

- full OCR pipeline
- shared ROI config work beyond what Phase 2 absolutely needs
- hardware runtime implementation
- polished operator UI implementation

## Locked Inputs From Phase 1

- ranking is provisional during discovery and final only after the last pile has been fully discovered and all cards have been recognized
- the machine should only trust what it has observed
- sim should still be useful for debugging and can explicitly toggle to known sim info when desired
- operator correction behavior exists in the product definition, but full UI implementation belongs later

## Current Code Areas Most Likely To Change

- `src/sorter/domain/models.py`
- `src/sorter/domain/machine_state.py`
- `src/sorter/domain/events.py`
- `src/sorter/domain/ranking_service.py`
- `src/sorter/application/orchestrator.py`
- `src/sorter/application/use_cases/plan_next_move.py`
- `src/sorter/application/use_cases/execute_move.py`
- `src/sorter/application/use_cases/verify_move.py`
- `src/sorter/adapters/sim/sim_world.py`
- `src/sorter/adapters/sim/sim_camera.py`
- `src/sorter/adapters/sim/sim_recognizer.py`
- `src/sorter/adapters/sim/sim_faults.py`
- `src/sorter/bootstrap.py`
- `tests/unit/test_models.py`
- `tests/unit/test_workflow_state.py`
- `tests/integration/test_sim_scenario.py`
- new noisy or partial-knowledge scenario fixtures under `scenarios/fixtures/`

## Workstreams

### 1. Observation Model

Replace coarse discovered-state assumptions with explicit observation state.

Target outcomes:

- piles can be `unknown`, `top_card_seen`, `empty_suspected`, or `empty_confirmed`
- pile observation stores card identity, confidence, observation source, timestamp or sequence, and frame reference
- stale knowledge is represented explicitly instead of being silently trusted

Likely implementation:

- extend domain models rather than hiding observation details inside sim adapters
- make unknown a valid first-class state
- make empty confirmation different from "recognizer returned nothing once"

### 2. Hidden Truth Boundary

Keep full card stacks in sim for setup and determinism, but stop exposing that truth to the planner path.

Target outcomes:

- sim world can still render and mutate real hidden piles
- application flow only sees observations and verified move results
- normal orchestration cannot inspect full stack contents

Likely implementation:

- separate hidden world state from machine-visible state in `sim_world.py`
- ensure planner paths consume snapshots or observation DTOs instead of live hidden objects

### 3. Discovery And Move Lifecycle

Make discovery happen through realistic steps rather than direct access to top-card truth.

Target outcomes:

- top card becomes known only after a scan or verification step
- pile emptiness becomes known only after an observation confirms it
- moves update knowledge through observed consequences, not direct stack mutation shortcuts

Likely implementation:

- make scan and verify behavior explicit in orchestrator or use cases
- add post-move verification rules for both source and destination
- distinguish observed success from commanded success

### 4. Ranking Lifecycle

Align ranking logic with incremental discovery.

Target outcomes:

- newly observed cards join the provisional ranking set immediately
- unknown cards do not block all planning, but they do block finalization
- ranking finalization happens only after the last pile is fully discovered

Likely implementation:

- update ranking service to represent provisional vs finalized state
- define what happens when the same card instance is observed multiple times

### 5. Sim Faults And Ambiguity

Make sim capable of perception-related failure instead of only idealized success.

Target outcomes:

- sim can produce blur, glare, skew, occlusion, false empty, missed pick, double feed, and dropped-card style outcomes
- test scenarios can intentionally exercise recovery logic
- deterministic fixtures can still reproduce faults

Likely implementation:

- expand `sim_faults.py`
- teach `sim_camera.py` and `sim_recognizer.py` to emit degraded or ambiguous outcomes
- keep fault injection deterministic through scenario config

### 6. Test And Fixture Coverage

Make Phase 2 verifiable instead of hand-waved.

Target outcomes:

- unit tests for observation-state transitions
- integration tests for partial-knowledge sort flow
- at least one noisy or ambiguous scenario fixture
- at least one scenario that proves rank finalization waits until final discovery

## Recommended Implementation Sequence

### Slice 1. Rename and identity hygiene

- [x] update card naming from `Name#slug` to `Name#{card.scryfall_id}` where applicable
- [x] confirm the sim identity-generation path prefers `scryfall_id`, falls back to `oracle_id`, and then falls back to a stable name slug when metadata is missing
- [x] add focused tests for `scryfall_id` normalization and sim instance-id expansion

### Slice 2. Domain observation model

- introduce richer pile observation data in `models.py`
- update `machine_state.py` to reason from observation states instead of hidden certainty
- adjust `events.py` if explicit observation events are needed

### Slice 3. Sim world truth split

- keep hidden stack truth in sim internals
- expose only observed state to orchestrator-facing paths
- prevent accidental planner reads of full stack contents

### Slice 4. Discovery-driven orchestrator flow

- update orchestrator and use cases so scan, pick, move, and verify change state through observations
- make empty confirmation explicit
- make source and destination verification part of the move lifecycle

### Slice 5. Progressive ranking

- update ranking service to support provisional accumulation and explicit finalization
- ensure finalization only occurs after the last pile is fully discovered

### Slice 6. Fault injection

- add deterministic fault definitions to sim
- teach camera or recognizer adapters to surface ambiguity and false-empty style failures

### Slice 7. Test and fixture hardening

- add targeted unit tests
- add at least one new partial-knowledge fixture
- add at least one noisy fixture
- update integration tests to assert honest observation behavior

## Concrete Deliverables

- richer observation state in domain models
- hidden truth split in sim adapters
- discovery-aware planner behavior
- provisional and finalized ranking lifecycle
- deterministic sim fault injection
- new scenario fixtures for partial knowledge and ambiguity
- tests covering unknown, stale, empty-confirmed, and ambiguous states

## Acceptance Checks

Phase 2 is complete when all of the following are true:

- planner logic can run without reading full hidden pile contents
- a pile can be unknown without being treated as empty
- a pile is only marked empty when observation confirms it
- ranking updates as cards are discovered but does not finalize early
- sim can reproduce at least one perception-driven failure mode
- tests demonstrate planner behavior under partial knowledge, not just ideal truth

## Risks To Watch

- leaking hidden stack references through convenience helpers
- treating missing recognition as confirmed empty
- freezing ranking too early
- adding sim-only special cases in application logic instead of behind adapter boundaries
- making fault injection so random that tests stop being deterministic

## Suggested First PR Shape

If we want to implement Phase 2 incrementally with low risk, the safest first PR is:

1. identity cleanup to `scryfall_id`
2. richer pile observation state in domain models
3. planner updates so unknown is no longer treated as known-empty or known-card
4. focused tests for those state transitions

That gives the project an honest state model before the deeper sim adapter refactors land.
