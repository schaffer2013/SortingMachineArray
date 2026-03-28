# Next Extended Sprint Plan

## Purpose

This plan is the follow-on execution guide after the successful pre-hardware recognition sprint.

The goal is to use the stronger upstream `fuzzy-enigma-card-recognition` API surface to remove more parent-side glue, reduce card-specific shortcuts, and arrive at hardware integration with a cleaner, more inspectable runtime.

## What Changed Since The Last Sprint

- The submodule now exposes first-class:
  - `requested_mode`
  - `effective_mode`
  - `mode_flags`
  - `failure_code`
  - `review_reason`
- The submodule now supports:
  - parent-facing offline catalog queries
  - artifact export
  - documented failure/review codes
  - parent-facing mode and candidate-pool controls
- The submodule now also supports:
  - identifier-first `expected_card` inputs with `scryfall_id` and `oracle_id`
  - a structured pipeline summary suitable for parent-side reporting
- This means the parent repo should stop scraping debug blobs where stable top-level fields now exist.

## Outcome Target

By the end of this sprint, the parent project should be in a stronger pre-hardware state:

- parent integration uses the submodule's structured metadata directly
- portable reports are cleaner and more upstream-aligned
- static card-name assumptions are reduced or eliminated in supported paths
- mode-aware recognition is exercised through stable commands and tests
- planner and recovery logic are better aligned with partial, uncertain observations
- the next hardware pass is blocked mainly by camera, lighting, calibration, and motion work rather than software ambiguity

## Recommended Sprint Shape

Treat this as a `72` hour style execution plan with stable checkpoints.

- First `8-12` hours:
  - metadata alignment
  - report cleanup
  - parent/submodule contract tightening
- Next `12-24` hours:
  - static-card cleanup
  - submodule-query-driven identity flows
  - mode-policy hardening
- Final `24-36+` hours:
  - planner pressure
  - acceptance hardening
  - hardware-facing setup and calibration seams

If time is shorter, stop after the latest stable merge point rather than leaving a large mixed branch half-finished.

## Git Plan

- Base branch:
  - start from clean `main`
- Short-lived feature branches:
  - `structured_metadata_alignment`
  - `identifier_first_parent_cleanup`
  - `mode_policy_and_recovery`
  - `hardware_readiness_prep`
- Merge to `main` only at stable points with tests and docs updated.
- Prefer several small merges over one large end-of-sprint merge.

## Stable Merge Point 1: Structured Metadata Alignment

### Goal

Remove parent-side guessing now that the submodule exposes stable fields directly.

### Tasks

- [ ] Update the parent `fuzzy_enigma` adapter to rely on top-level submodule fields before falling back to debug.
- [ ] Update portable recognition reports to preserve:
  - `requested_mode`
  - `effective_mode`
  - `mode_flags`
  - `failure_code`
  - `review_reason`
- [ ] Preserve submodule pipeline summary data directly in parent-side evidence when available.
- [ ] Update replay and benchmark summaries to use submodule failure/review codes directly when present.
- [ ] Update the parent feedback bundle generator to prefer upstream artifact export when available.
- [ ] Refresh `docs/submodule_feedback.md` so resolved asks are marked as resolved and only current gaps remain.

### Verification

- [ ] Parent adapter tests
- [ ] portable-report tests
- [ ] replay/benchmark tests
- [ ] targeted end-to-end benchmark run with `fuzzy_enigma`

## Stable Merge Point 2: Identifier-First Cleanup

### Goal

Reduce parent dependence on hardcoded example card names and adopt the submodule's identifier-first identity controls cleanly.

### Tasks

- [ ] Audit parent code, fixtures, and docs for baked-in example names such as `Lightning Bolt`, `Island`, or similar static references.
- [ ] Replace supported-path name assumptions with:
  - observed recognizer output
  - `scryfall_id`
  - `oracle_id`
  - submodule offline catalog queries
- [ ] Prefer identifier-first `ExpectedCard` construction in parent flows that already know printing or oracle identity.
- [ ] Add a small parent utility layer for submodule-backed catalog lookup where needed.
- [ ] Update tests so expected identity flows can be driven by IDs or submodule-resolved records instead of literal example names.
- [ ] Update saved report formats and acceptance docs to emphasize IDs over names when both are available.

### Verification

- [ ] static-reference grep pass with remaining intentional examples documented
- [ ] unit tests for catalog query helper or identity resolution seam
- [ ] regression test proving supported flow does not depend on a fixed demo card

## Stable Merge Point 3: Mode Policy And Recovery Hardening

### Goal

Move from "mode support exists" to "the parent has a sensible policy for when and why to use each mode."

### Tasks

- [ ] Add or refine parent-side policy for:
  - `greenfield`
  - `small_pool`
  - `reevaluation`
  - `confirmation`
- [ ] Make requested mode selection explicit in workflow, replay, and benchmark paths.
- [ ] Use submodule `failure_code` and `review_reason` directly for recovery policy decisions where safe.
- [ ] Add deterministic tests for:
  - missing tracked pool
  - missing expected card
  - confirmation contradiction
  - candidate tie unresolved
  - deadline exceeded
- [ ] Expand portable evidence so success/failure bundles clearly show:
  - requested mode
  - effective mode
  - why review happened
  - what the next recovery action should be

### Verification

- [ ] mode-policy unit tests
- [ ] noisy-sim and contract tests
- [ ] benchmark comparison across at least `greenfield` and one constrained mode
- [ ] evidence output check proving pipeline summary is visible in the parent-facing report path

## Stable Merge Point 4: Planner Pressure Under Partial Knowledge

### Goal

Push the planner further toward hardware-realistic uncertainty handling.

### Tasks

- [ ] Add more tests around provisional ranking while discovery is still incomplete.
- [ ] Add tests for stale observations affecting planner confidence or re-scan decisions.
- [ ] Tighten state transitions for:
  - newly observed top card
  - low-confidence observation
  - review-required observation
  - post-move verification mismatch
- [ ] Keep explicit seams for full ranking-finalization work if the complete implementation is too large for one sprint.
- [ ] Expand acceptance reporting to call out whether failures came from perception, policy, or planner-state disagreement.

### Verification

- [ ] workflow state tests
- [ ] planner tests
- [ ] full `pytest tests`

## Stable Merge Point 5: Hardware Readiness Prep

### Goal

Spend the last stretch reducing software friction before touching real hardware.

### Tasks

- [ ] Define or stub `config/vision/roi_profiles.json` ownership if not fully implemented yet.
- [ ] Tighten the frame contract for hardware-facing fields that are clearly needed now:
  - timestamp
  - camera id
  - pile id
  - image path
  - capture context
- [ ] Add or refine docs for parent-owned card-engine config usage in live vs benchmark vs replay contexts.
- [ ] Add a hardware-prep checklist section to `README.md` or a focused doc covering:
  - what configs must exist
  - what benchmark commands should pass first
  - what evidence commands to run before hardware bring-up
- [ ] Leave clean seams for upcoming calibration work rather than burying hardware assumptions inside adapters.

### Verification

- [ ] config loading tests where applicable
- [ ] smoke path or CLI bootstrap tests where applicable
- [ ] docs updated to match supported commands

## Suggested Execution Order

1. Structured metadata alignment
2. Identifier-first cleanup
3. Mode policy and recovery hardening
4. Planner pressure under partial knowledge
5. Hardware readiness prep

## Minimum Win

- parent reports and recovery logic use upstream structured metadata cleanly
- at least one real static-card dependency is removed from the supported path
- mode-aware policy gets stronger tests and clearer evidence output
- planner coverage improves under partial knowledge
- hardware-prep docs and seams are cleaner than they are today

## Strong Win

- the parent repo no longer depends on brittle debug scraping in the normal `fuzzy_enigma` path
- success and failure bundles are directly useful to both this repo and the submodule developer
- the parent uses submodule catalog queries instead of ad hoc name assumptions
- the next hardware session starts from a repo with cleaner contracts, clearer commands, and fewer hidden software unknowns

## Stretch Goal

If the sprint is going especially well, the stretch goal is to arrive at a pre-hardware launch point where:

- one command verifies the software acceptance envelope
- one command produces a portable feedback bundle
- one command exercises golden frames with explicit mode selection
- the main remaining unknowns are camera framing, lighting, calibration, and physical pick/place behavior
