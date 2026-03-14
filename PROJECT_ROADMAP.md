# SortingMachineArray Completion Roadmap

## Current Read On The Project

- The repo already has a strong architectural base: domain models, application orchestration, ports, sim adapters, hardware adapter stubs, persistence, CLI, and debug UI.
- The current sim is still more informed than the real machine will be. In particular, the system can still rely on stack truth that would not be visible in the real world.
- Recognition is still placeholder-level. The current recognizer contract is intentionally thin, which is useful, but it means the real perception system still needs to be designed and built.
- Hardware support exists as adapter stubs and a smoke path, not yet as a full runtime path with calibration, safety, recovery, and operator control.
- The remaining work is less about "add one feature" and more about turning the codebase into a trustworthy end-to-end system.

## North Star

- The sorter should make decisions from observations, not hidden simulator truth.
- Simulation and hardware should share the same application flow and the same recognition contract.
- Vision should be modular enough that ROI definitions, OCR logic, and replay tooling work in both sim and real-world runs.
- Ranking should become more complete as cards are discovered, and should only be treated as final once the last pile has been fully discovered and all cards in the run have been recognized.
- Every important decision should be inspectable after the fact through logs, saved frames, and replayable run data.
- Safety, recoverability, and diagnosability matter as much as sort correctness.

## Guiding Principles

- Observation first. A pile is only known to be empty or identifiable if the machine has actually observed it.
- Shared contracts. Sim and hardware should differ in adapters, not in planner behavior or domain assumptions.
- Replay everything important. If a run faults, we should be able to reconstruct what the machine saw and why it acted.
- Safety before throughput. It is better to re-scan or pause than to silently mis-sort or mis-handle a card.
- Config over magic numbers. ROI definitions, thresholds, calibration data, and recovery rules should live in versioned config where practical.
- Progressive ranking. Newly discovered cards should be rankable immediately, but the rank set should remain provisional until all relevant cards have been discovered.
- Measurable progress. Each phase should end with specific artifacts, tests, and exit criteria rather than "mostly done."

## Guardrails

- Do not let application or domain code read hidden sim-only stack truth during normal execution.
- Do not add `if sim` branches to core sorting logic when a port or adapter boundary can solve the problem cleanly.
- Do not treat low-confidence recognition as a successful recognition.
- Do not bury ROI coordinates and confidence thresholds directly inside adapters if they need to be tuned later.
- Do not optimize for speed before the system can reliably detect empty piles, recognize top cards, and recover from failures.
- Do not keep legacy and new flows both "sort of active" indefinitely. Once parity is achieved, archive or retire the old path.

## Completion Criteria

- The same application workflow can run in both sim and hardware modes.
- No production decision depends on hidden simulator truth like full stack contents.
- The system can detect card present vs empty, identify visible cards with measurable confidence, and recover from low-confidence reads.
- Sorting runs are logged well enough to replay failures and diagnose them.
- Calibration, setup, operation, and recovery are documented well enough to hand the machine to someone else.
- The ranking lifecycle is explicit: provisional ranking during discovery, finalized ranking once the last pile has been fully discovered and all cards in the run have been recognized.
- The project has explicit pass-fail acceptance gates rather than informal confidence.

## Cross-Cutting Workstreams

- State and observation model: represent what the machine actually knows, when it learned it, and how confident it is.
- Ranking lifecycle: support incremental rank assignment as cards are seen and a clear transition to finalized ranking once the last pile has been fully discovered and all cards in the run have been recognized.
- Vision and OCR: shared ROI definitions, preprocessing, OCR, image matching, fusion, and replay.
- Data and tooling: frame ingestion, labeling, benchmark splits, missing-asset reporting, and regression evaluation.
- Hardware runtime: bootstrap, calibration, motion safety, pick confirmation, operator controls, and recovery flows.
- Validation and operations: test gates, acceptance scripts, replay, debugging UI, and run documentation.
- Code health and cleanup: coverage baselines, static analysis, import-graph review, and retirement of dead-end compatibility code.

## Planned Artifacts

- [ ] `docs/completion_spec.md`: one-page definition of the machine target and supported operating envelope.
- [x] `docs/calibration_spec.md`: definition of initialization config ownership, pile-coordinate calibration, and supervised calibration flow.
- [ ] `docs/acceptance_gates.md`: measurable test gates that define completion.
- [ ] `config/vision/roi_profiles.json`: shared ROI definitions for sim and hardware captures.
- [ ] `config/vision/recognition_thresholds.json`: thresholds for empty detection, OCR confidence, retries, and manual review.
- [ ] `data/vision/raw/`: immutable raw captures from sim and hardware.
- [ ] `data/vision/normalized/`: normalized and cropped derivatives for repeatable experiments.
- [ ] `data/vision/labels/`: labels for empty detection, visible card identity, and ROI annotations.
- [ ] `scripts/ingest_frames.py`: metadata-preserving frame import.
- [ ] `scripts/replay_recognition.py`: run the recognizer pipeline over saved frames.
- [ ] `scripts/benchmark_recognizer.py`: produce measurable recognition reports.
- [ ] `scripts/audit_code_health.py`: summarize import-graph outliers, low-coverage modules, and likely vestigial code.
- [ ] `tests/golden_frames/`: curated perception regression set.
- [ ] `tests/noisy_sim/`: simulated conditions that intentionally break ideal assumptions.

## Suggested Design Targets

- A richer recognition result should likely include: predicted card, confidence, empty probability, OCR field reads, ROI metadata, and alternative hypotheses.
- A richer pile observation should likely include: visible top card, confidence, empty-confirmed flag, last observed frame id, last observed timestamp, and observation source.
- The ranking model should support a provisional state while discovery is ongoing and a frozen or finalized state once the last pile has been fully discovered and all cards in the run have been recognized.
- Hidden world truth should remain inside sim and hardware adapters only. The application layer should consume observed state plus recognition results.
- Every capture worth acting on should be persistable so a run can be replayed later without needing the original live hardware session.
- ROI configs should use a stable coordinate convention such as normalized image coordinates so the same logical regions can be reused across resolutions.

## Phase 1: Lock The Target

**Goal:** Freeze the intended outcome so later implementation choices stay aligned.

**Status:** Complete on 2026-03-13. The Phase 1 definition is considered locked, with only implementation-detail polish still open.

**Locked decisions from 2026-03-13**

- The machine is primarily for personal use, but the project should remain understandable and followable by others.
- V1 is supervised, not unattended, and should include strong operator tools for seeing and correcting the active card identity.
- Interactive pile-role editing before a run is not required for v1 and can be deferred to v2.
- The fixed hardware baseline is:
  - `BIGTREETECH SKR V1.4 Turbo`
  - `16-pixel NeoPixel ring`
  - `Raspberry Pi camera` with exact version still to be confirmed
  - `Raspberry Pi` for local control and identification
  - a smaller redundant `Z` axis relative to the crossbar
  - a vacuum subsystem with its own microcontroller, digital vacuum request input, and digital setpoint-reached status output
- V1 supports all `Magic: The Gathering` cards, unsleeved, in reasonable condition.
- V1 uses one top-down camera surrounded by NeoPixels.
- Calibration should include a pile-coordinate fine adjustment routine that visually aligns using the icon on the back of Magic cards.
- Initialization should use two config files: a main runtime config and a calibration-specific config.
- The main runtime config should hold global machine values, initial pile roles, and `x,y` coordinates for all piles.
- Piles should use stable integer IDs rather than assuming a rectangular array or coordinate-shaped identity.
- Pile role should be separate from pile ID because that role can change during a run, while the config only defines the initial role.
- Initial pile roles should be persisted as enums in the runtime config.
- V1 should assume `6` total piles with initial roles of `1` feeder, `1` collection, and `4` sorting piles.
- The configuration should include a global max placement height, with `105 mm` as the current baseline default.
- The calibration config should hold only calibration-routine values such as maximum fine-adjustment movement, acceptable error band, ideal image-space target location, and calibration-specific vision targets.
- Fine calibration should assume an upside-down Magic card is present in each bin, visually detect the back-of-card icon, iteratively move toward a configured ideal image-space location, and overwrite the stored pile `x,y` coordinate in the main runtime config once within the configured error band.
- Fine-adjustment calibration should run on operator demand rather than automatically at startup.
- Fine-adjustment calibration should support a single selected pile, not only full-machine recalibration.
- If single-pile calibration changes whether a pile is enabled, role reassignment should happen at the next run start rather than immediately during calibration.
- If calibration cannot find the Magic back icon for a pile after retries, that pile should be marked `disabled`.
- Disabled piles should have no active role and should not be used in a run.
- Startup may reassign roles across the remaining enabled piles if needed, but v1 does not need an optimized reassignment strategy.
- Disabled state should persist in the main runtime config as part of the last known calibration result.
- Startup reassignment should prefer to keep the collection pile unchanged when that still allows a valid minimum-role layout.
- If startup cannot satisfy at least `1` feeder, `1` collection, and `2` sorting piles after disabled-pile handling, the run should fail completely.
- A disabled pile may be brought back only by running calibration again and successfully recalibrating that pile.
- A pile is fully discovered only when it is empty and all cards that were in it during the run have been recognized.
- The machine may move onto an undiscovered pile only during the feeder-to-other-pile transfer stage, which implies a defined maximum safe placement height is required.
- Ranking is progressive during discovery and final only once the last pile has been fully discovered and all cards in the run have been recognized.
- Low-confidence or wrong identification should escalate to operator confirmation or operator-defined correction in v1.
- Supervised operation should include a UI that pauses the run, shows the current card image and predicted identity, lets the operator type the correct card name, provides a way to verify that actual identity, and then confirm the card before resuming.
- The supervised operator surface for v1 should be a local desktop-style UI.
- Separate windows are acceptable if that produces a cleaner split between live run status and manual review.
- The v1 supervision surface should stay on `pygame` rather than introducing a new GUI stack.
- Manual correction should verify against a valid card using `Scrython` fuzzy matching and should not allow invalid card identities to be confirmed.
- Operator-confirmed card identities should be captured as fallback recognition values for the same physical card instance if it later fails recognition again during the current run.
- The UI should keep the recognizer's original guess visible for debugging even after a manual overwrite.
- Manual overwrite should not stop future recognition attempts for that card instance. It should provide a fallback value only when later recognition fails.
- The supervision UI should visibly distinguish manually overwritten identities from organically discovered recognitions.
- Operator confirmation and run resume should be separate UI actions.
- In sim mode, the downloaded or rendered card image should be treated as the observed frame, and recognition should be able to toggle over to known sim info when explicitly enabled for debugging or controlled tests.
- The top success priorities are:
  - sort correctness
  - card recognition accuracy
  - ease of debugging
- Throughput is explicitly out of scope as a primary v1 goal.

**Primary outputs**

- [x] Write a one-page completion spec with target hardware, supported card conditions, lighting assumptions, pile height limits, and expected operator involvement.
- [x] Decide the MVP boundary: CLI-only vs UI-assisted, supervised vs unattended, single camera vs future multi-camera.
- [x] Freeze the initialization config ownership, pile coordinate source, safe placement baseline, and fine-adjustment direction so later perception and planning work have a stable target.
- [x] Define success metrics now: sort accuracy, recognition accuracy, empty-pile detection accuracy, retry rate, acceptable run time, and operator interventions per run.
- [x] Write down explicit non-goals for v1 so the project does not sprawl.
- [x] Define the required supervised operator verification surface for low-confidence card identification.
- [x] Freeze the config split, pile ID model, and separation of pile identity from pile role.
- [x] Define the minimum viable enabled-pile set and fallback behavior after calibration disables piles.

**Exit criteria**

- [x] A future contributor can tell what "complete" means without reading code.
- [x] The supported machine setup and constraints are documented clearly enough that later ROI and calibration work has a stable reference.
- [x] There is a single source of truth for project success metrics.

## Phase 2: Make The Simulator Honest About Observation Limits

**Goal:** Ensure the planner behaves like a real machine that only knows what it has observed.

**Primary outputs**

- [ ] Where card names are tracked in the form "Snapcaster Mage#snapcastermage", it should be "Snapcaster Mage#{card.scryfall_id}" 
- [ ] Split hidden world truth from observed machine state so the planner cannot read the full `card_stack` in normal execution.
- [ ] Replace the binary `discovered` concept with richer pile observations such as `unknown`, `top_card_seen`, `empty_confirmed`, `confidence`, `last_seen_at`, and `frame_id`.
- [ ] Make feeder discovery realistic: the picker only learns the next visible card after a scan and only learns a pile is empty when a scan or pick/verify sequence confirms it.
- [ ] Ensure every move updates state through observations and verification, not direct knowledge shortcuts.
- [ ] Define discovery-driven ranking behavior so newly identified cards can enter a provisional rank set before the final rank set is locked.
- [ ] Model observation staleness so the system can distinguish "recently seen" from "assumed unchanged."
- [ ] Add simulated perception faults such as blur, glare, skew, occlusion, bad crop, false empty, missed pick, double feed, and dropped card.
- [ ] Add tests that prove the planner still behaves correctly when pile contents are partially known or temporarily unknown.

**Implementation notes**

- Keep true stack contents in the sim world for rendering and deterministic test setup, but do not expose them to the planner path.
- Prefer explicit observation events over silent mutation. Good examples are `frame_captured`, `top_card_recognized`, `empty_confirmed`, `pick_verified`, and `move_rejected`.
- Make "unknown" a first-class state rather than treating it as empty or failed recognition.
- Keep ranking state explicit. Observed cards can receive ranks as they are discovered, but the system should know whether that ranking is provisional or finalized.
- Build at least one noisy sim scenario that frequently produces ambiguous perception so recovery logic gets exercised early.

**Exit criteria**

- The planner can run without direct knowledge of full pile contents.
- Tests cover realistic discovery behavior, not just idealized stack truth.
- Sim runs can now fail for perception reasons in controlled, replayable ways.

## Phase 3: Build A Shared Vision And OCR Platform

**Goal:** Create a perception system that can operate over both sim frames and real captures.

**Primary outputs**

- [ ] Expand the `Frame` contract so frames can carry image path or bytes, timestamp, camera id, pile id, pose, exposure context, and calibration metadata.
- [ ] Define shared ROI configuration files for common regions such as title bar, art box, set code, collector number, border edges, and empty-pile region.
- [ ] Define calibration-specific vision targets and ROIs for pile-coordinate fine adjustment, including the back-of-card Magic icon.
- [ ] Use calibration config to store the ideal image-space target location, acceptable error band, and maximum fine-adjustment movement for Magic back icon alignment.
- [ ] Build preprocessing steps that work in both sim and hardware captures: crop, perspective correction, brightness normalization, denoise, sharpen, threshold, and glare handling.
- [ ] Implement empty-vs-card-present detection before card identity recognition.
- [ ] Implement OCR on stable ROIs and combine it with image matching or embedding-based matching for final card identity scoring.
- [ ] Add confidence fusion and fallback behavior: re-scan, reposition, alternate recognizer, or manual review.
- [ ] Save intermediate outputs that matter during development, such as normalized crops and OCR text snippets, so tuning is inspectable.
- [ ] Build a replay harness that runs the same recognizer pipeline against saved sim frames and real-world captures.

**Implementation notes**

- Empty detection should be treated as its own classifier or decision stage, not just "recognition returned nothing."
- ROI definitions should be data-driven so the same logical crop can be tuned without changing code.
- Recognition should return structured evidence, not just a final label. Future debugging will depend on seeing why a label was chosen.
- The first viable recognizer does not need to be perfect, but it must expose enough internal detail to improve safely.

**Exit criteria**

- A saved frame from sim or hardware can be pushed through the same recognition pipeline.
- ROI and threshold changes can be made by editing config rather than rewriting core logic.
- Low-confidence results produce an actionable next step rather than a dead end.

## Phase 4: Data, Labeling, And Recognition Tooling

**Goal:** Build the data backbone that makes perception iteration repeatable instead of ad hoc.

**Primary outputs**

- [ ] Define a durable dataset layout for raw captures, normalized crops, labels, ROI annotations, and train-validation-test splits.
- [ ] Upgrade `scripts/import_recorded_frames.py` into a real ingestion tool that preserves metadata like pile id, capture time, camera settings, lighting conditions, and source mode.
- [ ] Add a labeling workflow for visible card name, empty/not-empty, ROI boxes, and recognition confidence review.
- [ ] Add a way to mark unusable frames such as blur, glare, occlusion, or framing errors so they are still learnable from.
- [ ] Expand the card catalog pipeline so sorter metadata and recognition assets come from a consistent source of truth.
- [ ] Add reports for missing assets, weak coverage, mislabeled frames, low-confidence clusters, and cards with no usable image examples.
- [ ] Define a benchmark split that will remain stable across recognizer experiments.

**Implementation notes**

- Preserve raw captures. Derived crops and normalized images can be regenerated later, but source material should remain immutable.
- Keep label formats simple and versioned so tooling can evolve without corrupting old data.
- Favor benchmark repeatability over clever one-off scripts. A slower but reproducible benchmark is more valuable than a fast opaque one.

**Exit criteria**

- New frames can be ingested and labeled without manual repo surgery.
- Recognition changes can be measured against a stable benchmark set.
- Missing-data problems are visible through reports instead of being discovered only during failures.

## Phase 5: Planner And State Robustness

**Goal:** Make the sorter robust to uncertain observations and recovery paths.

**Primary outputs**

- [ ] Refactor discovery and planning so recognition updates state through explicit events rather than direct pile mutation shortcuts.
- [ ] Update planning logic so it operates on observed top cards and confirmed empty states instead of full internal knowledge.
- [ ] Support incremental ranking updates during discovery and an explicit "ranking finalized" transition once all active cards are discovered.
- [ ] Add low-confidence branches for re-scan, second-look capture, different camera pose, or quarantine pile handling.
- [ ] Strengthen move verification so source and destination observations are both checked after each move.
- [ ] Track richer run metrics such as scan count, retries, distance traveled, confidence distribution, stale observations, and fault causes.
- [ ] Revisit the sorting strategy after the observation model is honest so the planner can optimize for fewer scans and safer moves, not just rank order.
- [ ] Define what counts as a recoverable fault versus a stop-the-run fault.

**Implementation notes**

- A good planner in this project is not just "correct if card identities are known." It must also decide when to seek more information.
- Ranking-aware planning should be able to use what is already known without pretending the unknown portion is final.
- Build recovery around explicit policies. For example: retry count, alternative scan pose, quarantine destination, or operator confirmation.
- Verification should answer more than "did the command run." It should answer "did the intended card move and did the observed state now make sense."

**Exit criteria**

- The planner behaves sensibly under partial knowledge and low-confidence observations.
- Misrecognitions and ambiguous reads follow a documented recovery path.
- Metrics are rich enough to compare planner strategies, not just final success state.

## Phase 6: Real Hardware Execution

**Goal:** Turn the architecture into a safe, supervised hardware runtime.

**Primary outputs**

- [ ] Build a true hardware bootstrap path in the CLI instead of relying on a smoke-test-only entrypoint.
- [ ] Finish motion, camera, vacuum, and lights integration with safe homing, bounds checking, and startup validation.
- [ ] Add calibration flows for pile coordinates, camera offset, focus or exposure locking, and ROI alignment.
- [ ] Add a pile-coordinate fine adjustment routine that refines pile XY placement by visually locating the back-of-card Magic icon.
- [ ] Persist refined pile coordinates back into the main runtime config so future runs start from the calibrated pile map.
- [ ] Disable piles that repeatedly fail icon-based fine adjustment and apply simple minimum-role reassignment before allowing a run to start.
- [ ] Decide and implement pick confirmation for hardware: vacuum sensing, camera verification, current draw, or a hybrid method.
- [ ] Add supervised run controls for pause, retry, re-scan, skip, and safe abort.
- [ ] Add a `pygame`-based human-verification UI that shows the current mode-appropriate card image, predicted identity, operator-entered correction, and explicit verify/confirm actions.
- [ ] Keep confirm and resume as separate actions in the supervision UI.
- [ ] Build the supervision surface as a local desktop-style UI rather than a web app.
- [ ] Make the UI clearly label manually overwritten identities versus organically discovered recognitions.
- [ ] Validate operator-entered corrections through `Scrython` fuzzy matching and block confirmation unless the correction resolves to a valid card.
- [ ] Feed operator-confirmed card identities back into runtime recognition as fallback values for later failures on the same physical card instance.
- [ ] Keep original recognizer guesses visible in the UI after manual overwrite for debugging and auditability.
- [ ] Add recovery procedures for jam, mispick, mismatch, dropped card, and unrecoverable low-confidence recognition.
- [ ] Add operator-visible machine state transitions so the human can tell whether the machine is discovering, moving, verifying, paused, or faulted.

**Implementation notes**

- Hardware mode should fail safe on startup if calibration, connectivity, or required peripherals are missing.
- Keep hardware side effects behind adapter boundaries so the rest of the system remains testable.
- Calibrations should be explicit versioned data, not hand-edited magic in code.
- Fine calibration should combine coarse machine coordinates with camera-based visual refinement rather than relying on raw machine coordinates alone.
- The first real-world goal should be supervised repeatability, not autonomy.

**Exit criteria**

- The machine can start, calibrate, run, pause, and abort through a supported hardware path.
- Common operational faults have defined recovery behavior.
- Hardware runs produce the same style of logs and replay artifacts as sim runs.

## Phase 7: Test Gates And Acceptance

**Goal:** Define and enforce proof that the system works well enough to be called complete.

**Primary outputs**

- [ ] Add unit tests for ROI configs, observation-state transitions, confidence thresholds, and recovery decisions.
- [ ] Add contract tests for camera and recognizer adapters using saved frames rather than perfect sim metadata.
- [ ] Add golden-frame regression tests so recognition changes can be measured before and after refactors.
- [ ] Add noisy sim scenarios that mimic real hardware conditions instead of always returning perfect identity data.
- [ ] Establish a repeatable coverage baseline for `src/sorter` and track which modules remain effectively untested.
- [ ] Add static analysis or scripted import-graph checks to flag modules, wrappers, and symbols with no live callers.
- [ ] Perform a vestigial-code audit to classify low-signal files as entrypoint, compatibility shim, future placeholder, or removal candidate.
- [ ] Add hardware acceptance scripts for homing, frame quality, repeated pick-place cycles, and supervised end-to-end sorts.
- [ ] Define pass-fail thresholds that must be met before the project is called complete.
- [ ] Add one command or documented workflow that runs the benchmark suite and summarizes whether the project is currently inside or outside the acceptance envelope.

**Implementation notes**

- Acceptance should include both correctness and operational behavior. A sorter that only works in ideal lighting or only with hand-reset intervention is not complete.
- Golden-frame tests should include both easy and adversarial examples.
- Keep benchmark reports lightweight enough that they can be run often, not only before major releases.
- Coverage and static analysis should be used to drive cleanup, not just to chase percentages. The goal is to expose code that no longer participates in the supported path.

**Exit criteria**

- There is a documented acceptance gate and the project can be measured against it repeatedly.
- Recognition regressions become visible quickly.
- Real hardware validation is part of the completion story, not an informal last step.

## Phase 8: Debuggability, UX, And Documentation

**Goal:** Make the system understandable and maintainable by future-you or someone new to the project.

**Primary outputs**

- [ ] Improve the debug UI so it can show the live frame, ROIs, OCR text, predicted card, confidence, and last action.
- [ ] Add run replay from saved frames and SQLite logs so failed runs can be reconstructed without guesswork.
- [ ] Write setup docs for environment, simulation, hardware wiring, calibration, and troubleshooting.
- [ ] Document the supported operating envelope: lighting, sleeves or no sleeves, card condition, pile height, and expected operator checks.
- [ ] Write a short operator checklist for startup, supervised run, pause or resume, and fault recovery.
- [ ] Write a maintainer checklist for adding new recognition logic, updating ROI configs, and validating thresholds.
- [ ] Document which legacy or compatibility files remain intentionally and why, so unexplained leftovers stop accumulating.
- [ ] Retire or archive the remaining legacy root-level flow once the new architecture has full feature parity.

**Implementation notes**

- Replay tooling is one of the highest leverage debugging tools in a perception-heavy system.
- Good docs should reduce future uncertainty around calibration, expected behavior, and what a fault actually means.
- Archive legacy code deliberately rather than deleting context impulsively. Preserve useful historical ideas while making the supported path unambiguous.

**Exit criteria**

- A new contributor can run sim mode, understand a saved run, and locate the main debugging surfaces.
- Operator and maintainer workflows are documented separately and clearly.
- The supported path through the repo is obvious.

## Dependency Map

- Phase 1 unlocks clean decisions for every later phase.
- Phase 2 should happen before large planner work, otherwise planner behavior will be optimized around unrealistic knowledge.
- Phase 3 and Phase 4 should advance together. Recognition quality depends on both shared pipeline design and usable data.
- Phase 5 should begin once the observation model exists, not before.
- Phase 6 can continue in parallel at the adapter level, but full end-to-end hardware mode should wait until observation and recovery behavior are better defined.
- Phase 7 starts early as tests and benchmarks, but acceptance gates should harden as the other phases mature.
- Phase 8 should not be saved for the very end; replay and debugging tools will speed every earlier phase.

## Suggested Implementation Order

1. Split world truth from observed state.
2. Define the richer frame, recognition, and ROI schema.
3. Build metadata-preserving frame ingestion and a stable dataset layout.
4. Implement empty detection plus OCR and image matching in a replayable pipeline.
5. Refactor planner and verification around observed state and recovery policies.
6. Finish hardware bootstrap, calibration, and supervised controls.
7. Harden acceptance gates, regression benchmarks, replay tooling, and operator docs.

## Final Done Checklist

- [ ] Simulation and hardware share the same application flow and recognition contract.
- [ ] The sorter never relies on hidden simulator knowledge during normal operation.
- [ ] Empty-pile detection and visible-card recognition are benchmarked and meet agreed thresholds.
- [ ] Low-confidence cases trigger a safe recovery path instead of silent mis-sorts.
- [ ] Hardware can complete repeated supervised runs safely and predictably.
- [ ] Logs, replay tools, and docs are strong enough to support the next debugging session without reverse-engineering the codebase.
- [ ] The legacy flow is no longer a competing implementation path.
