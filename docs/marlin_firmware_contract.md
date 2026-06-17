# Marlin Firmware Contract

## Purpose

This document is for the firmware team configuring Marlin for the
SortingMachineArray hardware. It describes what the Python controller expects
from Marlin, what each axis means mechanically, and which G-code commands the
web UI and hardware adapter emit.

The sorter controller talks to Marlin as a motion controller. Marlin owns
stepper mapping, endstops, homing direction, soft limits, acceleration,
current, and any board-specific pin assignments.

## Axis Model

The machine is treated as a four-linear-axis system:

| Axis | Meaning | Controller expectation |
| --- | --- | --- |
| X | Gantry/table horizontal axis | Absolute millimeters |
| Y | Gantry/table horizontal axis | Absolute millimeters |
| Z | Main vertical carriage/interface axis | Absolute millimeters |
| C | Redundant suction-cup vertical axis | Absolute millimeters |

The Python runtime stores pose as:

```text
x_mm
y_mm
z_mm
c_mm
```

The effective end-effector height is modeled as:

```text
end_effector_z_mm = z_mm + c_mm
```

This sign convention is important. A paired interface move changes `Z` and `C`
in opposite directions so `Z + C` stays constant.

Example:

```text
Before: Z=10.0, C=2.0, end_effector=12.0
Interface up by 3.0 mm:
After:  Z=13.0, C=-1.0, end_effector=12.0
```

If the physical mechanism uses the opposite sign for the suction axis, invert
the C motor direction in firmware rather than changing the Python contract.

## G-code Contract

The current hardware adapter emits these commands:

| Controller action | G-code sent |
| --- | --- |
| Home axes | `G28` |
| Move X/Y | `G1 X{x_mm:.3f} Y{y_mm:.3f} F6000` |
| Move Z | `G1 Z{z_mm:.3f} F1200` |
| Move C | `G1 C{c_mm:.3f} F1200` |
| Wait idle | `M400` |
| Set NeoPixel status | `M150 R{r} U{g} B{b}` |

The adapter uses absolute positions. Firmware should boot and remain in
absolute coordinate mode for axes. If any startup script or panel macro changes
coordinate mode, restore absolute positioning before accepting controller
commands.

The controller expects one serial command stream shared by motion and lights.
Commands are sent sequentially through the Marlin transport.

## Required Marlin Behavior

Configure Marlin so all of the following are true:

- `G28` homes X, Y, Z, and C into known machine coordinates.
- `G1 X... Y...` moves only X and Y.
- `G1 Z...` moves only the main vertical carriage/interface.
- `G1 C...` moves only the suction-cup vertical axis.
- `M400` blocks until all queued motion is complete.
- `M150 R... U... B...` controls the configured status light output.
- Units are millimeters.
- Coordinates are absolute.
- Soft limits prevent travel outside the safe physical envelope.
- Homing leaves both Z and C in positions that make `Z + C` a meaningful
  end-effector height.

## Fourth Axis Setup

Expose the suction-cup axis to G-code as `C`.

In Marlin multi-axis terms, the firmware should provide a named C axis with
steps-per-unit, max feedrate, acceleration, jerk/junction settings, endstop
behavior, and soft limits just like the other linear axes.

The exact Marlin configuration names depend on the Marlin version and board
configuration. The important controller-facing requirement is that these
commands work:

```gcode
G28
G1 C1.000 F1200
M400
```

The firmware team should verify the `C` axis with Marlin's reporting commands
after flashing. In current Marlin documentation, `M92` supports steps-per-unit
for extra axes including `C`, which is useful for checking whether the axis is
compiled and addressable.

## Homing Contract

The web UI and runtime assume homing is a firmware-level operation:

```gcode
G28
```

After `G28`, the Python pose is reset to:

```text
X=0.0
Y=0.0
Z=0.0
C=0.0
```

If the real machine needs nonzero post-home offsets, configure those offsets in
firmware or add an explicit documented startup move. Do not silently rely on an
operator moving axes by hand after homing.

## Paired Z/C Movement

The Movement tab includes an "interface only" control. It is intended for the
case where the Z-side interface moves up or down while the suction cup remains
at the same physical height.

The Python controller implements this by sending two moves:

```text
target_z = current_z + delta
target_c = current_c - delta
```

For example, "Interface up 1 mm" from zero sends the logical equivalent of:

```gcode
G1 Z1.000 F1200
G1 C-1.000 F1200
```

The current adapter emits those as sequential moves. If the firmware team wants
true synchronized Z/C paired motion, Marlin may need a coordinated multi-axis
move path that accepts both axes in one block:

```gcode
G1 Z1.000 C-1.000 F1200
```

Before switching the adapter to combined Z/C G-code, verify on hardware that
Marlin coordinates both axes correctly and that the end-effector height remains
fixed through the move.

## Feedrates Used By The Controller

Current controller defaults:

| Move type | Feedrate |
| --- | --- |
| X/Y | `6000 mm/min` |
| Z | `1200 mm/min` |
| C | `1200 mm/min` |

Firmware may clamp feedrates lower for safety. During bring-up, prefer
firmware-side limits that are conservative enough that accidental UI commands
cannot damage the machine.

## Safety Requirements

Firmware should enforce safety even if the host sends a bad command.

Required protections:

- conservative max travel for X, Y, Z, and C
- conservative max feedrate and acceleration for each axis
- endstops or equivalent sensorless limits for every homed axis
- motor direction verified with single-axis jogs before full homing
- Z and C travel ranges that cannot crush the suction cup into the bed or card
  stack
- an accessible emergency stop or power cut path during bring-up

Host-side safety also exists, but it is not a replacement for firmware limits.
For example, the Python app blocks X/Y travel below `min_xy_travel_z_mm`, but
Marlin should still enforce its own travel envelope.

## Bring-up Checklist

Use this sequence before letting the web UI drive the mechanism freely:

1. Flash firmware with X, Y, Z, and C enabled.
2. Connect over serial and verify Marlin responds to basic commands.
3. Verify `M115` reports the expected firmware build.
4. Verify steps-per-unit reporting includes X, Y, Z, and C.
5. Jog each axis a small positive amount and confirm direction.
6. Confirm endstop states before motion.
7. Home one axis at a time if the firmware workflow supports it.
8. Run full `G28`.
9. Run `G1 X10 Y10 F6000`, then return to zero.
10. Run `G1 Z1 F1200`, then return to zero.
11. Run `G1 C1 F1200`, then return to zero.
12. Test paired compensation manually with tiny values:

```gcode
G1 Z1.000 F1200
G1 C-1.000 F1200
M400
```

13. Confirm the interface moved while the suction cup height stayed fixed.
14. Only after those pass, use the web Movement tab.

## Web UI Controls That Depend On Firmware

The Movement tab exposes:

- X/Y jog
- absolute X/Y move
- camera-to-target X/Y move
- Z jog and absolute Z move
- C jog and absolute C move
- paired Z/C interface up/down move
- home and wait-idle controls

If a control fails, inspect the exact G-code contract above first. The web UI is
thin; it is not doing hidden coordinate transforms for the C axis beyond the
paired Z/C compensation rule.

## Open Firmware Decisions

The firmware team should confirm and record:

- board and driver assignment for X, Y, Z, and C
- whether C has a physical endstop, sensorless homing, or a fixed startup
  reference
- whether paired Z/C moves should remain sequential or become one coordinated
  `G1 Z... C...` command
- final travel limits for all four axes
- final safe homing order
- whether C negative travel is expected and safe under the `Z + C` convention
- whether the status LEDs should remain on Marlin `M150`

Once those answers are stable, update this document and the hardware adapter
together so firmware and host software remain aligned.

## References

- Marlin `M92` documentation lists extra-axis parameters including `C`, useful
  for validating C-axis steps-per-unit support:
  <https://marlinfw.org/docs/gcode/M092.html>
