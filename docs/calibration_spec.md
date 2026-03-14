# Calibration Spec

## Status

Phase 1 calibration baseline defined on 2026-03-13.
Phase 1 calibration definition status: complete.

This document defines how initialization, coarse pile coordinates, fine adjustment, and operator-facing calibration assumptions should work in v1.

## Configuration Ownership

- Initialization should use two JSON files:
  - a main runtime config
  - a calibration-specific config
- The main runtime config should contain:
  - `x,y` locations for all piles
  - motion values such as `safe_z_mm`, `pick_z_mm`, `place_z_mm`, and `max_place_height_mm`
  - camera offset data
  - each pile's initial role
- For v1, the runtime config should describe `6` total piles with initial roles of `1` feeder, `1` collection, and `4` sorting piles.
- The calibration-specific config should contain only values needed for the calibration routine itself.
- Piles should be keyed by stable integer IDs rather than assuming a rectangular grid or `"x,y"` addressing.
- A pile's role should be stored separately from its ID because the role can change over the course of a run.
- Initial pile roles should be persisted as enums.
- The runtime config should include a global maximum place height.
- For now, the baseline default is:
  - `max_place_height_mm = 105.0`

## Pile Coordinate Baseline

- Every pile should have a configured coarse `x,y` machine coordinate.
- Those coordinates should live in the main runtime config.
- Coarse coordinates are the machine's starting belief.
- Fine adjustment is allowed to refine those coordinates and overwrite the stored values once calibration succeeds.

## Fine Adjustment Routine

The fine adjustment routine should assume there is an upside-down Magic card in each bin where cards will live.

The goal is to refine each configured pile coordinate by visually locating the icon on the back of the card.

## Fine Adjustment Flow

For each pile:

1. Move to the pile's configured coarse `x,y` coordinate.
2. Capture an image.
3. Detect the target icon on the back of the Magic card.
4. Compare the detected icon position against the ideal icon position stored in configuration.
5. Move toward the ideal location.
6. Capture again and re-evaluate.
7. Repeat until the detected icon falls within the configured error band.
8. Overwrite the stored pile `x,y` coordinate with the refined value.
9. Use that refined value for runtime operation.

Then repeat the same routine for every pile.

This routine should persist the refined coordinate back into the main runtime config so the next initialization starts from the corrected value rather than the original coarse guess.

## Calibration Vision Requirements

The fine adjustment routine needs calibration-specific vision configuration for:

- the expected target feature on the back of a Magic card
- the ideal icon location in image space
- the acceptable error band
- any ROI used to speed up or stabilize detection

The expected v1 visual target is the icon on the back of a Magic card, not a separate fiducial marker.

These values should live in the calibration-specific config file.

That ownership should be explicit and versioned.

## Runtime Guarantees Expected After Calibration

After successful calibration:

- each pile has a refined stored `x,y` coordinate
- the machine uses the refined values, not the original coarse guesses
- fine-adjustment results persist across runs by updating the main runtime config

## Calibration Trigger Policy

- Fine-adjustment calibration should be operator-invoked, not an automatic startup step.
- Normal startup should use the persisted runtime config values from the last successful calibration.
- The operator should re-run fine adjustment when hardware geometry, camera alignment, lighting setup, or pile fixtures have changed enough to warrant it.
- The operator should be allowed to run calibration for a single selected pile rather than always recalibrating every pile in one session.
- If a single-pile calibration changes whether a pile is enabled, role reassignment should wait until the next run starts rather than mutating active role assignments immediately inside the calibration flow.

## Calibration Failure Handling

- If the routine cannot find the Magic back icon for a pile, it should retry rather than failing immediately.
- If the icon still cannot be found after the configured retry limit, that pile should be marked `disabled`.
- A disabled pile should have no active role and should not participate in the next run unless calibration later re-enables it.
- After calibration finishes, startup should verify that the enabled pile set can still support the minimum required roles.
- The system should ensure there is at least:
  - `1` feeder pile
  - `1` collection pile
  - `2` sorting piles
- If a disabled pile removes one of the required unique roles, startup may reassign roles among the remaining enabled piles.
- This reassignment does not need to be optimized for v1. It only needs to satisfy the minimum viable role set.
- The disabled state should persist in the main runtime config as part of the last successful calibration outcome.
- Reassignment should prefer leaving the collection pile unchanged when that does not conflict with the minimum viable role set.
- If the remaining enabled piles cannot satisfy at least `1` feeder, `1` collection, and `2` sorting piles, startup should fail completely.
- A pile that was disabled by calibration may be re-enabled later only by running calibration again and successfully completing the fine-adjustment routine for that pile.

## Placement Constraint

- The machine may place onto an undiscovered pile only during the feeder-to-other-pile transfer stage.
- That behavior depends on a safe global max placement height.
- For now, use:
  - `max_place_height_mm = 105.0`

## Operator Supervision UI Requirement

Human supervision should include a UI component.

When the machine pauses for card verification, the UI should:

- show the current card image for the active mode, meaning a captured real-world image in hardware mode or the downloaded/rendered image in simulation
- show the card name currently believed by the identifier
- allow the operator to type in the card name
- provide a control to verify the actual card name through `Scrython` fuzzy matching
- provide a control to confirm the chosen card identity
- provide a separate explicit control to resume the run after confirmation
- require the correction to resolve to a valid card before confirmation is allowed
- keep the original recognizer guess visible for debugging even after manual overwrite

The intent is that the operator can resolve uncertain or wrong card recognition without breaking the run context.

That supervision surface should be treated as part of the supported v1 runtime, not as an optional debug convenience.

Operator-confirmed identities should also be captured as recognition feedback so the system can fall back to that confirmed value if the same card later fails recognition again during the current run.

That fallback should follow the physical card instance as it moves from pile to pile during the run rather than attaching only to a single momentary observation.

Normal recognition should still continue for later observations of that card instance. The operator-confirmed value is a fallback, not a permanent replacement for future recognition attempts.

The UI should clearly distinguish manually overwritten card identities from organically discovered recognitions.

The v1 supervision surface should continue using `pygame`.

In sim mode, the downloaded or rendered card image should be treated as the observed frame for UI and debugging purposes, and simulation should optionally allow recognition to be toggled over to known sim info when explicitly needed for debugging or controlled testing.

## Open Details Still To Refine

- exact JSON field names for the runtime and calibration config split
- exact enum values for pile role and disabled state persistence
- exact icon-detection algorithm
- exact retry count before disabling a pile during calibration
- exact role-reassignment procedure when disabled piles remove an initially assigned feeder or collection pile
- exact deterministic tie-break order for reassignment candidates
- exact in-run instance-tracking data model for operator-confirmed fallback identities
- exact operator flow and failure messaging when `Scrython` fuzzy matching does not return a valid card
- exact layout split between run-status and manual-review windows
- exact UI treatment for showing original guess, current guess, and operator-confirmed fallback together
- exact UI wording and state transitions for separate confirm vs resume actions
- exact operator UI layout and interaction order
