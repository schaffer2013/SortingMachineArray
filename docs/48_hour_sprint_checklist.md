# 48 Hour Sprint Checklist

## Purpose

This is the short-term execution checklist for the next `48` hours of software work before deeper hardware integration starts.

The goal is not to "finish the whole roadmap." The goal is to remove as much software uncertainty as possible so hardware bring-up this week is blocked by real hardware issues, not missing tooling, missing evidence, or avoidable recognition ambiguity.

## Outcome Target

By the end of this sprint, the parent project should have:

- mode-aware real recognizer integration, not just a single default path
- portable success and failure bundles that can be handed to the submodule developer
- less reliance on static card-name assumptions in parent logic
- stronger golden-frame and noisy-sim regression coverage
- clearer parent-side requests for missing submodule functionality

## Rules For This Sprint

- Prefer reusable tooling over one-off debug code.
- Prefer parent-owned evidence and manifests over screenshots or hand notes.
- Prefer `scryfall_id` and `oracle_id` over hardcoded card-name assumptions.
- Prefer submodule queries and structured outputs over external card lookups.
- Prefer changes that help both sim and upcoming hardware work.

## Git Strategy

- Start the sprint from a clean integration branch.
  Current expected base: `pre_hardware_48h_sprint`
- Use short-lived feature branches for major slices when the write scope is large enough to deserve isolation.
  Expected examples:
  - `portable_recognition_reports`
  - `mode_aware_parent_integration`
  - `golden_frame_hardening`
  - `noisy_sim_expansion`
- Commit locally at meaningful checkpoints even if the slice is not fully done yet.
- Push branches when a slice is stable enough to preserve remotely or open for review.
- Merge back into the active sprint branch at stable points, not only at the very end.
- Merge into `main` only when a checkpoint is:
  - tested
  - documented
  - coherent as a standalone improvement
- Prefer several stable merges to `main` across the `48` hours instead of one giant end-of-sprint merge.
- Keep unfinished exploratory work off `main` unless it is hidden behind a safe flag or clearly non-disruptive.
- If a branch reveals a bad direction, close it locally or keep it unmerged rather than forcing partial work into the mainline.

## Stable Merge Points

- Stable Point 1:
  - portable recognition evidence format
  - initial `docs/submodule_feedback.md`
  - tests for evidence export
- Stable Point 2:
  - mode-aware parent integration
  - saved mode metadata in reports
  - replay or benchmark comparison coverage by mode
- Stable Point 3:
  - static-card cleanup
  - submodule-query-based replacements where practical
  - tests proving parent flow no longer depends on example card names
- Stable Point 4:
  - golden-frame command hardening
  - broader noisy-sim fault coverage
  - updated acceptance docs

## Merge Discipline

- Before each stable merge:
  - run the targeted tests for that slice
  - run broader validation if the slice touches shared orchestration or benchmark code
  - update the checklist or acceptance docs if the slice changes the supported workflow
- After each stable merge:
  - verify the branch is clean
  - note what was merged and what remains
  - continue from a fresh clean branch if the next slice is large enough

## Block 1: Portable Recognition Evidence

- [x] Add a parent-owned portable report format for recognition outcomes.
- [x] Include both success and failure cases.
- [x] Record:
  - backend
  - requested mode
  - effective mode or mode-related flags when available
  - confidence
  - review flag
  - review reason
  - `scryfall_id`
  - `oracle_id`
  - expected identity when known
  - predicted identity
  - candidate list
  - artifact paths
  - timing data when available
- [x] Ensure the format is easy to hand to the submodule developer without needing local SQLite access.

## Block 2: Mode-Aware Parent Integration

- [ ] Add parent-side policy for using more than one recognition mode.
- [x] Start with practical use of:
  - `greenfield`
  - `small_pool`
  - `reevaluation`
  - `confirmation`
- [x] Make mode choice explicit in saved reports and logs.
- [x] Add benchmark or replay coverage that compares modes, not just backends.
- [x] If the parent cannot yet use a mode safely, document the missing requirement in the submodule feedback doc.

## Block 3: Remove Static Card Assumptions

- [ ] Find parent-side code paths that still depend on fixed card-name examples or hardcoded card-specific assumptions.
- [ ] Replace those assumptions with:
  - observed recognizer outputs
  - tracked-pool entries
  - expected-card identifiers
  - offline catalog queries through the submodule when appropriate
- [x] Avoid new network-based card lookups in the parent repo.
- [ ] Add tests proving the parent flow does not rely on example cards like `Lightning Bolt` or other baked-in names.

## Block 4: Golden-Frame Hardening

- [x] Add a stable golden-frame command that does not depend on regenerating the runtime fixture during the run.
- [ ] Expand the golden-frame manifest beyond the current small slice if practical.
- [x] Make golden-frame output portable and diffable across:
  - backend
  - mode
  - config
- [x] Add at least one command or doc section that a future hardware debugging session could reuse unchanged.

## Block 5: Broader Noisy-Sim Fault Modeling

- [x] Expand noisy-sim recognition faults beyond the current low-confidence or missing-prediction cases.
- [ ] Add deterministic cases for high-value failure classes such as:
  - false empty
  - ambiguous candidate set
  - stale observation pressure
  - contradiction during confirmation
  - mode-mismatch cases where a constrained mode should fail safely
- [x] Add tests that prove the parent behavior remains safe and inspectable.

## Block 6: Planner And Ranking Pressure

- [ ] Push further on provisional discovery behavior where practical.
- [ ] Add tests around planner behavior when:
  - some piles are known and some are still unknown
  - newly observed cards should influence ranking without finalizing it
  - the system should wait for more information instead of pretending the state is complete
- [ ] If full provisional-ranking implementation is too large for this sprint, leave a clean seam and document the remaining work.

## Block 7: Submodule Feedback Package

- [x] Create `docs/submodule_feedback.md`.
- [x] Keep it short, concrete, and evidence-backed.
- [x] Include:
  - missing structured metadata we need from the recognizer
  - failure and review reasons that should be first-class
  - mode and effective-path metadata we need in results
  - artifact-export capabilities we want upstream
  - any parent workarounds we had to implement because the submodule does not expose enough directly
- [x] Link each request to a real parent-side use case or saved report example.

## Block 8: Docs And Acceptance Tightening

- [x] Update acceptance docs to include portable evidence bundles and mode-aware runs.
- [ ] Update the roadmap for anything truly completed.
- [ ] Keep one current sprint log only if active execution starts again.
- [x] Make sure the docs folder reflects the current plan instead of old sprint-by-sprint narration.

## Suggested Execution Order

1. Portable recognition evidence
2. Mode-aware parent integration
3. Static-card cleanup
4. Submodule feedback doc
5. Golden-frame hardening
6. Broader noisy-sim coverage
7. Planner and ranking pressure
8. Docs and acceptance cleanup

## Minimum Win For The 48 Hours

- one portable evidence format
- one submodule feedback document
- one real mode-aware parent integration path beyond default `greenfield`
- one meaningful removal of hardcoded card assumptions
- one stronger golden-frame command
- one broader noisy-sim expansion

## Stretch Win For The 48 Hours

- the parent project can compare recognizer backends and recognizer modes with portable evidence bundles
- the parent project no longer relies on example-card shortcuts in the supported path
- the submodule developer can receive a compact evidence package plus a clear request list without extra explanation
- the next hardware session can start with a much smaller software unknown surface
