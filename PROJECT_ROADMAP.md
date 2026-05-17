# SortingMachineArray Roadmap

## Purpose

This roadmap describes the supported path forward from the current repo state.
It is not a sprint diary and it is not a record of already-finished cleanup.

Use this document to answer:

- what the project already supports
- what should happen next
- what "v1 supervised hardware-ready" means from here

## Current Baseline

- The parent repo under `src/sorter/...` is the active implementation.
- `sim` is the supported end-to-end runtime.
- `hardware` is still a bring-up path, not a fully supported operator flow.
- Recognition is already split behind `RecognizerPort`.
- The parent supports `sim_truth` and the vendored
  `fuzzy-enigma-card-recognition` backend.
- Local catalog data and submodule APIs are the default metadata source.
- External live lookups should stay opt-in and should only be used when the
  requested data is not available from the local cache or offline catalog.
- Replay, benchmark, and golden-frame tooling are active and should remain the
  main way we validate recognition changes before hardware sessions.

## North Star

The project is done when a supervised operator can run the sorter on real
hardware using the same core application flow we already exercise in sim, with
enough evidence, review tooling, and recovery behavior that failures are
inspectable instead of mysterious.

## Working Rules

- Keep the parent repo responsible for orchestration, machine state, config,
  evidence packaging, and operator workflow.
- Keep the submodule responsible for card-recognition internals and offline
  catalog querying.
- Prefer local identifier-first and catalog-backed flows over name-only or
  network-backed flows.
- Treat low-confidence recognition as a reviewable state, not a successful
  guess.
- Do not keep dead compatibility layers once the supported path is clear.
- Only add docs that help someone run, verify, or maintain the current system.

## Roadmap

### 1. Stabilize The Parent And Submodule Contract

This is the immediate milestone. The repo now depends on the submodule for more
than recognition alone, so the integration seam should be explicit and boring.

Current focus:

- keep parent-side recognition requests mode-aware and evidence-rich
- keep offline catalog lookup as the default path for card metadata and image
  resolution
- remove remaining parent assumptions that still look like raw Scryfall-shaped
  payload handling instead of normalized catalog records
- keep live external enrichment opt-in and limited to cases where local data is
  insufficient

Done when:

- the parent runtime, replay, and benchmark flows all use the same normalized
  recognition result shape
- catalog-backed metadata resolution is the default supported path
- submodule feedback is captured in `docs/submodule_feedback.md` with concrete
  evidence instead of ad hoc notes

### 2. Finish Observation-Honest Planning

The sorter should behave like a machine that only knows what it actually saw.
This matters more than adding more planner cleverness right now.

Current focus:

- make pile knowledge, confidence, and staleness explicit in state transitions
- keep ranking provisional while discovery is still incomplete
- strengthen review-required and retry flows so the planner seeks more evidence
  instead of pretending uncertainty is success
- record the run metrics needed to compare recovery behavior, not just final
  sort outcomes

Done when:

- planner decisions are driven by observed state only
- retries, re-scan, and review-required paths are visible in logs and tests
- ranking finalization is an explicit state transition, not an assumption

### 3. Build The First Real Hardware Observation Loop

The next hardware milestone is not "full autonomy." It is a repeatable,
inspectable capture and verification loop.

Current focus:

- finish the bootstrap path that loads config, hardware adapters, and machine
  status without custom local surgery
- wire camera, motion, vacuum, and lighting into one supervised startup path
- make calibration data explicit, versioned, and recoverable through config
- support a probe-aware placement path so hardware can discover a safe drop
  height from the measured pile top when probing hardware is available, while
  keeping fixed placement height as the fallback
- save real captures in a form that replay and benchmark tools can consume

Done when:

- a hardware session can capture frames, save evidence, and feed those frames
  back through replay tooling
- pile-coordinate and ROI tuning are config-owned rather than hidden in adapter
  code
- hardware startup fails clearly when prerequisites are missing

### 4. Ship The Supervised Operator Flow

The hardware runtime needs a human-facing review loop that matches the repo's
current recognition and evidence model.

Current focus:

- show the active card frame, predicted identity, confidence, and review reason
- support operator correction and explicit confirmation as separate actions
- validate operator-entered identities with local catalog or submodule-backed
  lookup first, with live external lookup only as an opt-in fallback when the
  local data is not enough
- keep original guesses and final overrides visible for debugging

Done when:

- low-confidence runs pause in a clear operator state instead of collapsing into
  silent fallback
- corrected identities feed back into the active run as controlled overrides
- the review workflow is documented and testable

### 5. Reach Supervised End-To-End Hardware Runs

Once capture, verification, and operator review are stable, the next milestone
is complete supervised sorting on real hardware.

Current focus:

- safe startup, homing, and bounds checks
- repeatable pick, place, and post-move verification
- recoverable handling for empty misreads, bad picks, dropped cards, and review
  escalation
- run logging that makes hardware failures replayable

Done when:

- the machine can complete repeated supervised runs without requiring code edits
  between sessions
- common faults have a documented stop, retry, or review path
- real runs produce the same style of evidence package as sim runs

### 6. Harden Acceptance And Maintenance

The project should become easier to keep healthy as the hardware path grows.

Current focus:

- keep `tests`, replay, benchmark, and golden-frame commands part of normal
  development instead of end-of-cycle checks
- add targeted hardware acceptance checks once the runtime path is stable
- continue deleting vestigial code and docs that no longer support the active
  path
- keep the active docs set small and current

Done when:

- acceptance status can be checked from documented commands
- regressions show up in saved evidence, not just during manual debugging
- a new contributor can find the supported runtime path without reverse
  engineering the repo

### 7. Generalize Machine Sequences

The first registration sequence is being used as a testbed for reusable,
versioned machine sequences composed from typed steps plus declarative configs.

TODO:

- migrate existing hard-coded sorter workflows onto the reusable sequence
  framework once the registration sequence proves the model
- replace one-off command-list builders with shared sequence primitives where it
  improves clarity without weakening safety

## Suggested Order

1. Finish the parent/submodule contract and catalog-first metadata flow.
2. Tighten observation-honest planning and ranking finalization behavior.
3. Make hardware capture, calibration, and evidence persistence repeatable.
4. Build the supervised review UI around the existing recognition evidence
   model.
5. Run repeated supervised hardware sorts and turn the results into acceptance
   gates.

## Not The Current Priority

- throughput tuning
- unattended operation
- adding new parallel UI or service stacks
- keeping old legacy flows alive as a second supported runtime

## Active Supporting Docs

- `README.md`
- `docs/runtime_reference.md`
- `docs/acceptance_gates.md`
- `docs/hardware_prep.md`
- `docs/submodule_feedback.md`
- `docs/paddleocr_path_guide.md`
