# Completion Spec

## Status

Phase 1 baseline defined on 2026-03-13 from direct product-owner decisions.

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
- Recognition results should be explainable enough for an operator to confirm or correct them.
- Hardware integration should expose vacuum-ready status as a first-class signal.
- Calibration should explicitly include safe placement height for moves involving undiscovered piles.
- Calibration should also include fine XY pile alignment using the icon on the back of Magic cards to refine pile coordinates beyond coarse machine coordinates.
- The perception and orchestration layers should preserve enough state to show:
  - the current card image
  - the predicted identity
  - confidence or uncertainty
  - the current run phase
  - what the operator can do next

## Open Details Still To Freeze

These do not block the Phase 1 definition, but they remain concrete follow-ups:

- exact Pi camera model
- exact safe placement height and how it is calibrated
- exact pile fine-adjustment workflow using the Magic card back icon
- exact UI surface for operator confirmation
- exact acceptable recognition and sort-accuracy thresholds for acceptance gates
