# Vestigial Code Q&A Worksheet

## Purpose

This file is for live review.

For each candidate, we should decide whether it is:

- a real part of the supported path
- a stub we expect to grow soon
- a compatibility layer we still need
- legacy code we should archive
- dead code we should delete

This document is also meant to carry context across future sessions, so each item should preserve:

- what the file currently appears to do
- why it was flagged
- what evidence we already have
- what decision remains open

## How To Use This Worksheet

For each item below:

1. Read the evidence.
2. Answer the review questions.
3. Check one outcome.
4. Write the reason in notes.

When we reach a conclusion later, add:

- the date
- the decision
- the rationale
- any follow-up file moves or deletions

## Current Repo Context

- The active architecture lives under `src/sorter/...`.
- The repo already has a hexagonal split across domain, application, ports, sim adapters, hardware adapters, persistence, CLI, and debug UI.
- The current roadmap says the supported future path is observation-driven, shared between sim and hardware, and increasingly centered on richer perception and recognition.
- The repo still contains root-level legacy files from the older flow, and not all of them have been formally archived yet.
- Static review in this session used in-repo symbol searches and import-graph style checks.
- Runtime coverage in this session was partial because this environment does not currently have `coverage`, `ruff`, `mypy`, or `vulture` installed.
- A partial `pytest` run produced useful signal, but sandbox permission issues around pytest temp/cache paths interfered with a clean full run in this environment.

## Evidence Summary From This Session

- No in-repo callers were found for:
  - `src/sorter/interfaces/api.py:create_app`
  - `src/sorter/application/use_cases/discover_layout.py:discover_top_cards`
  - `src/sorter/application/use_cases/run_cycle.py:run_cycle`
  - `src/sorter/adapters/sim/sim_faults.py:SimFault`
  - `src/sorter/adapters/recognition/manual_label_recognizer.py:ManualLabelRecognizer`
  - `src/sorter/adapters/recognition/template_match_recognizer.py:TemplateMatchRecognizer`
- Several domain symbols also appeared unused in live code paths:
  - `src/sorter/domain/commands.py` command dataclasses
  - `src/sorter/domain/enums.py:RunPhase`
  - `src/sorter/domain/models.py:CardView`
- The old root-level legacy flow still exists, especially:
  - `card.py`
  - `pile_manager.py`
- The README already describes a migration from the old root-level flow into the `src/sorter/...` architecture.
- Low-coverage but likely live modules from this session included:
  - `src/sorter/bootstrap.py`
  - `src/sorter/application/orchestrator.py`
  - `src/sorter/interfaces/pygame_debug.py`
  - `src/sorter/adapters/persistence/sim_image_sync.py`
  - `src/sorter/adapters/persistence/sqlite_run_store.py`

## Important Interpretation Note

"Flagged" does not automatically mean "delete."

In this review, a file may be flagged because it is:

- unreachable
- under-integrated
- a placeholder
- legacy compatibility code
- a valid future seam that is not wired in yet

The goal is to classify correctly, not to maximize deletions.

## Review Questions To Reuse

- [ ] Is this part of the current supported runtime path?
- [ ] Do we expect to actively build on this in the next 1 to 2 roadmap phases?
- [ ] Does it contain unique knowledge that is not already captured somewhere better?
- [ ] Would deleting it break a real workflow, script, or migration path?
- [ ] Is the current location and naming helping future contributors understand the system?

## Outcome Labels

- [ ] `KEEP-LIVE`
- [ ] `KEEP-STUB`
- [ ] `KEEP-COMPAT`
- [ ] `ARCHIVE`
- [ ] `DELETE`

## 1. REST API Placeholder

**Candidate**

- [src/sorter/interfaces/api.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/interfaces/api.py)

**Evidence**

- `create_app()` only raises `NotImplementedError`
- no in-repo callers were found
- current CLI and app flow do not expose an API surface
- this looks like a placeholder for a possible future web or service layer, not a current product feature

**Review Questions**

- [ ] Do we actually want a REST API in this project direction?
- [ ] If yes, is this the file we want to grow into that surface?
- [ ] If no, is this file just broadcasting a fake feature?

**Decision**

- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 2. Discovery Wrapper

**Candidate**

- [src/sorter/application/use_cases/discover_layout.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/application/use_cases/discover_layout.py)

**Evidence**

- no in-repo callers were found
- current behavior looks out of step with the roadmap's observation-driven discovery model
- specifically, it mutates `pile.discovered` directly based on whether `result.card_name is None`, which does not match the newer idea of richer observation states
- discovery work is expected to be redesigned around observations, confidence, and explicit ranking lifecycle transitions

**Review Questions**

- [ ] Is this meant to become the real discovery entrypoint later?
- [ ] If yes, should we rewrite it soon so it matches the future model?
- [ ] If no, is it just leftover design debris?

**Decision**

- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 3. `run_cycle` Wrapper

**Candidate**

- [src/sorter/application/use_cases/run_cycle.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/application/use_cases/run_cycle.py)

**Evidence**

- no in-repo callers were found
- it currently just forwards to `plan_next_move`
- there is no visible extra orchestration, state transition, or recovery logic here yet
- if this file stays, it should probably have a clear future responsibility

**Review Questions**

- [ ] Is this a real seam we expect to grow?
- [ ] If yes, what should live here that does not belong elsewhere?
- [ ] If no, is this just one layer too many?

**Decision**

- [ ] `KEEP-STUB`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 4. Sim Fault Placeholder

**Candidate**

- [src/sorter/adapters/sim/sim_faults.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/adapters/sim/sim_faults.py)

**Evidence**

- defines `SimFault`
- no current callers were found
- the roadmap explicitly calls for simulated fault injection later, so this may be pre-laid scaffolding
- today it is not integrated into `SimWorld`, orchestrator flow, or test scenarios

**Review Questions**

- [ ] Do we expect sim fault injection work soon?
- [ ] If yes, is this file useful scaffolding or would we redesign it anyway?
- [ ] If no, is keeping this file helping anything today?

**Decision**

- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 5. Recognition Adapter Experiments

**Candidates**

- [src/sorter/adapters/recognition/manual_label_recognizer.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/adapters/recognition/manual_label_recognizer.py)
- [src/sorter/adapters/recognition/template_match_recognizer.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/adapters/recognition/template_match_recognizer.py)

**Evidence**

- no live callers were found
- both look like prototype recognizers rather than integrated runtime options
- `TemplateMatchRecognizer` currently just reads `frame.metadata['card_name']` and returns a fixed confidence when present
- `ManualLabelRecognizer` currently returns a configured fallback name rather than using image evidence
- both could still be useful as debugging or bring-up adapters if intentionally wired into bootstrap later

**Review Questions**

- [ ] Do we want these as real fallback recognizers or debug tools?
- [ ] Should one of them become an explicit baseline recognizer in the vision plan?
- [ ] If kept, should they be wired into a selectable bootstrap path?
- [ ] If not, are they just abandoned experiments?

**Decision**

- [ ] `KEEP-LIVE`
- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 6. Legacy Root-Level Flow

**Candidates**

- [card.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/card.py)
- [pile_manager.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/pile_manager.py)

**Evidence**

- they appear to belong to the pre-refactor flow
- the old path mostly references itself
- the README already maps these concerns into `src/sorter/...`
- `card.py` still contains older network/data-fetch-era behavior and legacy card modeling
- `pile_manager.py` still represents the older pile orchestration model
- these may still contain historical logic worth preserving, even if they are no longer the supported path

**Review Questions**

- [ ] Is any real workflow still using these files?
- [ ] Is there knowledge here that has not yet been migrated into the new architecture?
- [ ] Would moving them into `legacy/` reduce confusion immediately?
- [ ] Are they still helping, or just making the repo feel split-brain?

**Decision**

- [ ] `KEEP-COMPAT`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 7. Legacy Sort Policy Wrapper

**Candidate**

- [src/sorter/domain/sort_policy.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/domain/sort_policy.py)

**Evidence**

- explicitly described as a legacy compatibility wrapper
- it exists to bridge older tests or scripts toward the newer `RankingService` flow
- this is more likely a compatibility decision than accidental dead code

**Review Questions**

- [ ] Is anything current still expected to import `SortPolicy` directly?
- [ ] If yes, what is the migration path off it?
- [ ] If no, why is it still in the active path?

**Decision**

- [ ] `KEEP-COMPAT`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 8. Unused Domain Abstractions

**Candidates**

- [src/sorter/domain/commands.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/domain/commands.py)
- [src/sorter/domain/enums.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/domain/enums.py) `RunPhase`
- [src/sorter/domain/models.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/domain/models.py) `CardView`

**Evidence**

- several command dataclasses appear to have no live callers
- `RunPhase` appears unused
- `CardView` appears unused
- these look like architecture-facing abstractions that may have been added ahead of their integration
- partial pruning may be better than removing the entire files if other symbols in those modules are actively useful

**Review Questions**

- [ ] Are these the start of a command-oriented architecture we still want?
- [ ] If yes, which of these symbols are truly worth keeping now?
- [ ] If no, should we do a partial prune instead of keeping a speculative abstraction layer?

**Decision**

- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`
- [ ] `PARTIAL-PRUNE`

**Notes**

- 
- Current status:
- Future-session context:

## 9. Script Review

**Candidates**

- [scripts/hardware_smoke_test.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/scripts/hardware_smoke_test.py)
- [scripts/import_recorded_frames.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/scripts/import_recorded_frames.py)
- [scripts/build_card_catalog.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/scripts/build_card_catalog.py)
- [scripts/build_scenario_fixture.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/scripts/build_scenario_fixture.py)

**Evidence**

- some are clearly useful
- some are thin utilities that may be either future tools or temporary migration helpers
- `hardware_smoke_test.py` is currently the only named hardware bootstrap path mentioned by the CLI error message
- `import_recorded_frames.py` is intentionally very thin today and the roadmap already calls for expanding it into a real ingestion tool
- `build_card_catalog.py` and `build_scenario_fixture.py` may still be useful but should be classified as supported tooling or migration helpers

**Review Questions**

- [ ] Which of these are part of the supported workflow today?
- [ ] Which should become proper CLI subcommands?
- [ ] Which are one-off utilities we can archive after use?

**Decision**

- [ ] `KEEP-LIVE`
- [ ] `KEEP-STUB`
- [ ] `ARCHIVE`
- [ ] `DELETE`

**Notes**

- 
- Current status:
- Future-session context:

## 10. Low-Coverage But Probably Live Modules

**Candidates**

- [src/sorter/bootstrap.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/bootstrap.py)
- [src/sorter/application/orchestrator.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/application/orchestrator.py)
- [src/sorter/interfaces/pygame_debug.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/interfaces/pygame_debug.py)
- [src/sorter/adapters/persistence/sim_image_sync.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/adapters/persistence/sim_image_sync.py)
- [src/sorter/adapters/persistence/sqlite_run_store.py](C:/Users/Pullo/OneDrive/Desktop/Python/SortingMachineArray/src/sorter/adapters/persistence/sqlite_run_store.py)

**Evidence**

- these do not look vestigial
- they do look under-tested relative to their importance
- these modules are likely more valuable as testing priorities than pruning targets
- removing "obvious dead code" before securing these core paths would risk spending energy in the wrong place

**Review Questions**

- [ ] Are these definitely part of the supported path?
- [ ] Which one is the highest-risk test gap?
- [ ] Should we improve tests here before we do much pruning elsewhere?

**Decision**

- [ ] `KEEP-LIVE`
- [ ] `REFINE-AND-TEST`

**Notes**

- 
- Current status:
- Future-session context:

## Quick Starting Points For Discussion

- [ ] Start with the likely easiest deletes: `api.py`, `run_cycle.py`, `discover_layout.py`
- [ ] Then decide whether recognition prototypes are future tools or abandoned experiments
- [ ] Then decide whether root-level legacy files should move to `legacy/` now or stay put a bit longer
- [ ] Then review the unused domain abstractions for partial pruning

## Session Log

### 2026-03-13

- This worksheet was created to preserve vestigial-code findings in a future-session-friendly format.
- The original version was too much like an audit memo and not enough like a reusable Q&A worksheet, so it was rewritten into this structure.
- Current confidence level:
  - high confidence on obvious placeholders like `src/sorter/interfaces/api.py`
  - medium confidence on wrappers like `run_cycle.py` and `discover_layout.py`
  - medium confidence that recognition prototypes and sim fault types are intentional scaffolding rather than garbage
  - high confidence that root-level legacy files should eventually move out of the active supported path
