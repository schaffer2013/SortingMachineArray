# Completion Spec

## Status

Phase 1 baseline defined on 2026-03-13 from direct product-owner decisions.
Phase 1 definition status: complete.

This document is the current source of truth for what "complete enough for v1" means.

## Product Intent

- This machine is primarily for personal use.
- The repo and architecture should still be followable enough that another motivated builder could understand and reproduce the approach.
- The goal is a supervised Magic card sorting machine, not a high-throughput commercial product.

## V1 Operation Model

- V1 is supervised, not unattended.
- The operator should have strong inspection and intervention tools.
- The operator should be able to:
  - see the active card under review
  - see what the identifier believes the card is
  - confirm or reject that identification
  - define the correct card when recognition is uncertain or wrong
- The machine should favor safe escalation to the operator over autonomous guessing.
- Changing pile roles interactively before a run is not required for v1 and can be treated as a v2 feature.

## Target Hardware Baseline

The Phase 1 hardware target is:

- Mechanical platform: a repurposed `Ender 3` frame stripped down and adapted for this card-sorting machine
- Motion control: `BIGTREETECH SKR V1.4 Turbo`
- Lighting: `16-pixel NeoPixel ring`
- Camera: `Raspberry Pi camera`, exact model still to be confirmed, but the software should assume a single Pi camera class device for v1
- Compute: `Raspberry Pi`
- Vertical motion: a smaller redundant `Z` axis relative to the crossbar
- Vacuum subsystem:
  - a small self-contained microcontroller
  - one digital control signal to request vacuum
  - one digital status signal indicating vacuum setpoint reached
  - the microcontroller itself handles pull-to-setpoint behavior locally

## Camera And Vision Assumptions

- V1 uses one top-down camera only.
- The camera is surrounded by NeoPixel lighting.
- Local identification runs on the Raspberry Pi.
- The software should assume a single controlled imaging station rather than multiple camera angles.
- Calibration should include a pile-coordinate fine adjustment routine that uses the back-of-card Magic icon as a visual alignment target.

## Configuration And Initialization

- At initialization, the machine should load two JSON configuration files:
  - a main runtime config
  - a calibration-specific config
- The main runtime config should define global machine settings and per-pile coordinates rather than scattering those values through code.
- The main runtime config should include:
  - a global maximum placement height
  - `x,y` coordinates for every pile
  - motion values such as safe and working `Z` heights
  - camera offsets and other runtime machine values
  - each pile's initial role
- For v1, the initial pile layout should assume:
  - `6` total piles
  - `1` feeder pile
  - `1` collection pile
  - `4` sorting piles
- For now, the default global placement constraint is:
  - `max_place_height_mm = 105.0`
- Piles should use stable integer IDs rather than assuming a rectangular array layout.
- A pile's role should be stored separately from its ID because that role can change during operation.
- Initial pile roles in the runtime config should be represented as enums rather than freeform strings.
- Fine adjustment is allowed to overwrite stored pile `x,y` values after calibration succeeds, so the main runtime config remains the persisted source of truth for later runs.

## Supported Cards

- All `Magic: The Gathering` cards
- No sleeves
- Any reasonable card condition

Interpretation for v1:

- The system should handle ordinary wear and print variation.
- The system does not need to optimize for sleeved cards in v1.
- The system does not need to guarantee support for severely damaged, folded, or unusually altered cards unless later explicitly added.

## Discovery Definition

A pile is considered fully discovered only when:

- it no longer has cards in it
- the machine has recognized all cards that were in that pile during the run

Additional operating assumption:

- nothing moves cards between piles except the machine itself

This matters because the software is allowed to trust the continuity of pile state between machine actions, but not hidden card identities it has not yet observed.

## Sorting And Discovery Strategy

V1 should follow the current intended physical workflow:

1. Move cards from a feeder pile to another pile even though the feeder pile is not yet fully discovered.
2. This is the only time the machine should place onto an undiscovered pile.
3. That move requires a defined maximum safe placement height.
4. Then move cards back to the feeder pile in order to discover them.
5. Ranking can be built progressively as cards are recognized.
6. Ranking becomes final only once the last pile has been fully discovered and all cards in the run have been recognized.

## Recovery Policy For V1

When confidence is low or recognition is wrong:

- the machine should pause for operator involvement
- the operator should be able to confirm the detected card or define the correct card
- the supervised flow should use a UI rather than only terminal prompts

During operator review, the UI should:

- show the current card image
- show the card name currently believed by the identifier
- allow the operator to type the actual card name
- provide a control to verify the actual selected card identity through `Scrython` fuzzy matching
- provide a control to confirm the chosen card
- provide a separate explicit control to resume the run after confirmation
- record the operator-confirmed identity so it can be used as a fallback value for that same physical card instance if it later fails recognition again during the current run
- require that the correction resolve to a valid card before confirmation is allowed
- keep the original recognizer guess visible for debugging even after a manual overwrite
- continue attempting normal recognition for that card instance on later observations, using the operator-confirmed value only as a fallback when recognition fails

V1 should prefer:

- human confirmation
- debugging visibility
- correction tools

over:

- automatic retries without explanation
- silent fallback guesses
- autonomy-first behavior

## Top Success Metrics

The top three priorities for v1 are:

1. Sort correctness
2. Card recognition accuracy
3. Ease of debugging

Secondary priorities:

- hardware safety
- operator trust
- reproducibility of failures

## Explicit Non-Goals For V1

- Throughput is not a primary goal for v1.
- The project does not need to optimize for maximum speed before correctness and observability are strong.
- V1 does not need multi-camera operation.
- V1 does not need unattended autonomy.
- V1 does not need sleeve support unless explicitly re-scoped later.

## Implications For Implementation

- The UI and debug tooling are not optional extras for v1; they are part of the product.
- The supervised runtime UI should be a local desktop-style window rather than a web UI.
- Separate desktop windows are acceptable if that keeps the supervision surface cleaner than forcing everything into one window.
- The v1 supervision surface should continue using `pygame` rather than introducing a separate GUI stack.
- Recognition results should be explainable enough for an operator to confirm or correct them.
- Hardware integration should expose vacuum-ready status as a first-class signal.
- Calibration should explicitly include safe placement height for moves involving undiscovered piles.
- Calibration should also include fine XY pile alignment using the icon on the back of Magic cards to refine pile coordinates beyond coarse machine coordinates.
- Fine calibration should assume an upside-down Magic card is present in each bin, detect the configured icon target, compare it to an ideal configured image-space location, iterate until within error band, and then persist the refined pile coordinate back into the main runtime config.
- The calibration config should only hold values used by the calibration routine itself, such as maximum fine-adjustment movement, acceptable error band, ideal image-space target location, and calibration-specific vision targets.
- Fine-adjustment calibration should run only when explicitly requested by the operator, not automatically at every startup.
- Fine-adjustment calibration should be allowed to run for one selected pile rather than requiring a full all-pile session every time.
- If a single-pile calibration changes pile availability, startup-style role reassignment should be deferred until the next run begins rather than changing roles immediately during calibration.
- If fine adjustment cannot find the Magic back icon for a pile after retries, that pile should be marked `disabled`.
- A disabled pile should have no active role and should not be used in the run.
- After calibration disables piles, the startup role assignment should ensure there is still at least `1` feeder, `1` collection, and `2` sorting piles.
- If those minimum roles cannot be satisfied after reassignment, the machine should treat startup as a complete failure rather than trying to limp into a run.
- A disabled pile may return to service only after the operator runs calibration again and that pile successfully calibrates.
- Disabled state should persist in the main runtime config so startup behavior is based on the last known calibration outcome.
- During simple startup reassignment, the collection pile should stay unchanged if it is still enabled and the minimum-role requirements can still be satisfied.
- The perception and orchestration layers should preserve enough state to show:
  - the current card image from the active mode, meaning the captured real-world image in hardware mode or the downloaded/rendered image in simulation
  - the predicted identity
  - the original recognizer guess when the current identity has been manually overwritten
  - confidence or uncertainty
  - the current run phase
  - what the operator can do next
  - whether a card identity was manually overwritten rather than organically discovered by recognition
- In sim mode, the downloaded or rendered card image should be treated as the observed frame for UI and debugging purposes.
- Sim mode should also support a recognizer toggle that can fall back to known sim info when explicitly enabled for debugging or controlled experiments.

## Open Details Still To Freeze

These do not block the Phase 1 definition, but they remain concrete follow-ups:

- exact Pi camera model
- exact JSON field names for the split runtime and calibration config files
- exact enum values for persisted pile roles and disabled state
- exact icon-detection algorithm for the Magic card back target
- exact retry count and operator messaging for failed icon detection during calibration
- exact deterministic reassignment order after disabled-pile handling
- exact in-run instance-tracking data model for operator-confirmed fallback identities
- exact operator flow and failure messaging when `Scrython` fuzzy matching does not return a valid card
- exact layout split between run-status and manual-review windows
- exact UI treatment for showing original guess, current guess, and operator-confirmed fallback together
- exact UI wording and state transitions for separate confirm vs resume actions
- exact UI layout and interaction polish for operator confirmation
- exact acceptable recognition and sort-accuracy thresholds for acceptance gates
