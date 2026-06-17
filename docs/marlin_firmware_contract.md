# Marlin Firmware Contract

## Purpose

This document is for the firmware team configuring Marlin for the
SortingMachineArray hardware. It describes what the Python controller expects
from Marlin, what each axis means mechanically, and which G-code commands the
web UI and hardware adapter emit.

The sorter controller talks to Marlin as a motion controller. Marlin owns
stepper mapping, endstops, homing direction, soft limits, acceleration,
current, and any board-specific pin assignments.

## Hardware Baseline

This machine is a reworked Ender 3 using a BTT SKR 1.4 Turbo as the Marlin
control board.

Firmware should start from the normal Ender 3 machine envelope unless a later
hardware measurement overrides it. For Z specifically:

- Z max: normal Ender 3 Z max travel.
- Z min: `6.9 mm`.
- Z homes to max, not min.
- C stroke: `85 mm`.
- C min: `0.0 mm`.
- C max/home position: `85.0 mm`.

Keep those limits in firmware soft endstops as well as any host-side
calibration notes. The host UI can request moves, but firmware is responsible
for refusing unsafe travel.

Suction is delegated to a separate Arduino Uno/Nano controller. The SKR should
only issue pick/release requests and wait for response inputs; it must not
directly drive the pump or vent solenoid. See
`docs/suction_subsystem_contract.md` for the shared SKR/Arduino contract.

## Axis Model

The machine is treated as a four-linear-axis system:

| Axis | Meaning | Controller expectation |
| --- | --- | --- |
| X | Gantry/table horizontal axis | Absolute millimeters |
| Y | Gantry/table horizontal axis | Absolute millimeters |
| Z | Main vertical carriage/interface axis | Absolute millimeters in standard Z direction |
| C | End-effector/suction-cup vertical axis | Absolute millimeters in standard Z direction |

The Python runtime stores pose as:

```text
x_mm
y_mm
z_mm
c_mm
```

Z and C are both standard 3D coordinates. C is the end-effector vertical
coordinate, not a host-side offset added to Z.

Example:

```text
Before: Z=10.0, C=2.0
Interface up by 3.0 mm:
After:  Z=13.0, C=-1.0
```

In other words, paired interface movement changes Z and C in opposite
directions in one coordinated Marlin motion block so the end effector stays
fixed in world space during the interface move.

## G-code Contract

The current hardware adapter emits these commands:

| Controller action | G-code sent |
| --- | --- |
| Home axes | `G28 Z`, then `G28 C`, then `G28 X Y` |
| Move X/Y | `G1 X{x_mm:.3f} Y{y_mm:.3f} F6000` |
| Move Z | `G1 Z{z_mm:.3f} F1200` |
| Move C | `G1 C{c_mm:.3f} F1200` |
| Paired Z/C interface move | `G1 Z{z_mm:.3f} C{c_mm:.3f} F1200` |
| Wait idle | `M400` |
| Set NeoPixel status | `M150 R{r} U{g} B{b}` |
| BLTouch deploy/stow/probe | Firmware-standard BLTouch / probe G-code, to be confirmed during bring-up |
| Pick request | Set `P1_22` high, wait for `P1_26` low, then clear `P1_22` |
| Release request | Set `P1_23` high, wait for `P1_25` low, then clear `P1_23` |

The adapter uses absolute positions. Firmware should boot and remain in
absolute coordinate mode for axes. If any startup script or panel macro changes
coordinate mode, restore absolute positioning before accepting controller
commands.

The controller expects one serial command stream shared by motion and lights.
Commands are sent sequentially through the Marlin transport.

## Required Marlin Behavior

Configure Marlin so all of the following are true:

- `G28 Z` homes Z into a known machine coordinate.
- `G28 C` homes C into a known machine coordinate.
- `G28 X Y` homes X and Y together after Z and C are homed.
- Z homes before C.
- Z homes toward its positive end of travel using its normal endstop.
- C homes after Z using sensorless homing toward its negative end of travel.
- X/Y home to their minimum coordinates.
- Z and C home to their maximum coordinates.
- C's physical homing direction is negative, but its configured post-home
  coordinate should still be the C max value.
- `G1 X... Y...` moves only X and Y.
- `G1 Z...` moves only the main vertical carriage/interface.
- `G1 C...` moves only the suction-cup vertical axis.
- `G1 Z... C...` coordinates Z and C in one planner block.
- `M400` blocks until all queued motion is complete.
- `M150 R... U... B...` controls the configured status light output.
- Pick/release requests are high-level SKR-to-Arduino requests. Pump PWM,
  venting, vacuum sensing, and hold-mode control live on the Arduino.
- `VAC_GOOD` is expected on `E0DET` / `P1_26`; `RELEASE_DONE` is expected on
  `E1DET` / `P1_25`, active-low.
- Units are millimeters.
- Coordinates are absolute.
- Soft limits prevent travel outside the safe physical envelope.
- Z soft limits use normal Ender 3 Z max and `6.9 mm` Z min.
- C soft limits use `0.0 mm` minimum and `85.0 mm` maximum.
- X/Y minimum is `0.0`; Z/C minimum is also `0.0`, even though Z/C home to max.
- Homing leaves Z and C in known standard coordinates.
- The BLTouch on the end effector is available for pile-height probing.

## Fourth Axis Setup

Expose the end-effector/suction-cup vertical axis to G-code as `C`.

In Marlin multi-axis terms, the firmware should provide a named C axis with
steps-per-unit, max feedrate, acceleration, jerk/junction settings, endstop
behavior, and soft limits just like the other linear axes.

The exact Marlin configuration names depend on the Marlin version and board
configuration. The important controller-facing requirement is that these
commands work:

```gcode
G28 Z
G28 C
G28 X Y
G1 C1.000 F1200
M400
```

The firmware team should verify the `C` axis with Marlin's reporting commands
after flashing. In current Marlin documentation, `M92` supports steps-per-unit
for extra axes including `C`, which is useful for checking whether the axis is
compiled and addressable.

## Homing Contract

The web UI and runtime assume homing is a staged firmware-level operation:

```gcode
G28 Z
G28 C
G28 X Y
```

After that full sequence, the Python pose is:

```text
X=0.0
Y=0.0
Z=<configured Z max/home position>
C=<configured C max/home position>
```

`0.0` is the minimum coordinate for every axis. Because Z and C home to their
maximum end-of-travel positions, they must not be reset to zero after homing.
The host tracks those homed values through `z_home_mm` and `c_home_mm` in
`config/calibration.json`.

For the current mechanism, `c_home_mm` should be `85.0` because C only has an
85 mm stroke.

Firmware should execute the vertical homing sequence in this order:

1. Home Z first toward the positive end of travel using the normal Z endstop.
2. Home C second toward its negative end of travel using sensorless homing.
3. Home X and Y together.

If the real machine needs nonzero post-home offsets, configure those offsets in
firmware or add an explicit documented startup move. Do not silently rely on an
operator moving axes by hand after homing.

## BLTouch / Probe Contract

The machine has a BLTouch mounted on the end effector. Firmware should configure
the probe as the authoritative pile-height/contact sensor.

The Python calibration model already includes:

```text
probe_enabled
probe_retract_z_mm
probe_place_clearance_mm
probe_max_contact_z_mm
```

Expected firmware behavior:

- BLTouch deploy, stow, reset, and probe commands work over the same Marlin
  serial connection.
- Probe offsets from the suction cup and camera are documented in firmware and
  calibration notes.
- Probing is performed in standard machine coordinates.
- Failed probe states are surfaced as Marlin errors rather than silently
  continuing motion.
- Probe contact limits are conservative enough to protect the end effector,
  suction cup, and card stacks.

The exact probe G-code sequence is still a firmware bring-up decision. Once the
team chooses it, update this document and the Python hardware adapter together.

## Paired Z/C Movement

The Movement tab includes an "interface only" control. It is intended for the
case where the Z-side interface moves up or down while the suction cup remains
fixed in world space.

The Python controller implements this by sending two moves:

```text
target_z = current_z + delta
target_c = current_c - delta
```

For example, "Interface up 1 mm" from zero sends:

```gcode
G1 Z1.000 C-1.000 F1200
```

This is a required firmware capability. Marlin must accept both axes in one
block and coordinate them through the planner.

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
- Z travel constrained to normal Ender 3 Z max and `6.9 mm` minimum
- C travel constrained to `0.0 mm` minimum and `85.0 mm` maximum
- conservative max feedrate and acceleration for each axis
- endstops or equivalent sensorless limits for every homed axis
- motor direction verified with single-axis jogs before full homing
- Z and C travel ranges that cannot crush the suction cup into the bed or card
  stack
- BLTouch trigger/failure handling that prevents blind downward motion after a
  failed probe
- optocoupled or level-shifted request/response wiring for the suction
  subsystem
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
8. Run staged homing:

```gcode
G28 Z
G28 C
G28 X Y
```

9. Run `G1 X10 Y10 F6000`, then return to zero.
10. Run `G1 Z1 F1200`, then return to zero.
11. Run `G1 C1 F1200`, then return to zero.
12. Verify BLTouch deploy/stow/probe behavior with the end effector in a safe
    test location.
13. Test paired interface movement manually with tiny values:

```gcode
G1 Z1.000 C-1.000 F1200
M400
```

14. Confirm the interface moved while the C/end-effector coordinate stayed
    fixed.
15. Only after those pass, use the web Movement tab.

## Web UI Controls That Depend On Firmware

The Movement tab exposes:

- X/Y jog
- absolute X/Y move
- camera-to-target X/Y move
- Z jog and absolute Z move
- C jog and absolute C move
- paired Z/C interface up/down move
- BLTouch/probe calibration fields on the Machine tab
- home and wait-idle controls

If a control fails, inspect the exact G-code contract above first. The web UI is
thin; it is not doing hidden coordinate transforms for the C axis beyond the
paired Z/C compensation rule.

## Open Firmware Decisions

The firmware team should confirm and record:

- board and driver assignment for X, Y, Z, and C
- confirmation of the exact Ender 3 Z max value used in firmware
- whether C has a physical endstop, sensorless homing, or a fixed startup
  reference
- final sensorless homing settings for C toward negative end of travel
- final Z homing settings toward positive end of travel
- final BLTouch deploy/stow/probe G-code sequence
- BLTouch offsets relative to the suction cup and camera reference
- final travel limits for all four axes
- final safe homing order
- whether the status LEDs should remain on Marlin `M150`
- final SKR request pins and response pin identifiers for the suction
  subsystem

Once those answers are stable, update this document and the hardware adapter
together so firmware and host software remain aligned.

## References

- Marlin `M92` documentation lists extra-axis parameters including `C`, useful
  for validating C-axis steps-per-unit support:
  <https://marlinfw.org/docs/gcode/M092.html>

## Connection Inventory

This list is the shared connection map for firmware and wiring review. When a
row says "signal pin only," the design uses that named input signal and does
not imply the whole physical connector is dedicated to that function.

| Connection | From | To | Purpose | Notes |
| --- | --- | --- | --- | --- |
| 24 V input | Ender 3 V2 PSU | BTT SKR 1.4 Turbo power input | Main controller power | Reworked Ender 3 baseline. |
| X motor | SKR X driver output | X stepper motor | X gantry motion | Standard Ender-style motor wiring unless reworked hardware changes it. |
| Y motor | SKR Y driver output | Y stepper motor | Y gantry motion | Standard Ender-style motor wiring unless reworked hardware changes it. |
| Z motor | SKR Z driver output | Z/interface stepper motor | Main vertical interface motion | Homes positive to Z max using the normal Z endstop. |
| C motor | SKR extra driver output | C/end-effector stepper motor | 85 mm suction-cup vertical stroke | Exposed to Marlin as the `C` axis. Homes physically negative with sensorless homing, then reports C max/home as `85.0 mm`. |
| X homing | X endstop switch | SKR `X_MIN` | X homing input | Uses the normal `X_MIN` endstop input. |
| Y homing | Y endstop switch | SKR `Y_MIN` | Y homing input | Uses the normal `Y_MIN` endstop input. |
| Z homing | Z max endstop switch | SKR `Z_MAX` | Z positive-EOT homing input | Uses the `Z_MAX` endstop input for Z homing. |
| C homing | C driver sensorless signal | SKR / driver sensorless homing path | C negative-EOT homing | No physical C endstop is expected. Configure sensorless homing for C. |
| BLTouch servo | BLTouch control lead | SKR `SERVO0` | BLTouch deploy/stow | `SERVO0` is unavailable for other uses. |
| BLTouch probe | BLTouch probe output | SKR configured probe/Z-probe input | Probe trigger | Firmware team must confirm final probe input and offsets. |
| NeoPixel status light | SKR NeoPixel/status output | NeoPixel ring | Machine status lighting | Controlled with Marlin `M150`. |
| Host serial | Host Raspberry Pi / operator computer | SKR USB or serial port | Python controller to Marlin | Motion, lights, and request/wait commands share one serialized command channel. |
| `PICK_REQUEST` | SKR EXP1 pin 7 / `P1_22` 3.3 V logic output | Arduino `D4` with 10 kohm pulldown to GND | High-level pick request | Use EXP1 signal pin and ground only. HIGH means request active. Do not use FAN/HE outputs unless real GPIO is exhausted. Do not drive 5 V back into EXP1. |
| `RELEASE_REQUEST` | SKR EXP1 pin 8 / `P1_23` 3.3 V logic output | Arduino `D5` with 10 kohm pulldown to GND | High-level release request | Use EXP1 signal pin and ground only. HIGH means request active. Do not use FAN/HE outputs unless real GPIO is exhausted. Do not drive 5 V back into EXP1. |
| EXP1 logic ground | SKR EXP1 pin 9 / GND | Arduino GND | Request-line reference | Use ground with EXP1 pins 7 and 8. EXP1 pin 10 is 5 V and is not needed for this handshake. |
| `VAC_GOOD` | Arduino `D6` open-drain/open-collector style output | SKR `E0DET` / `P1_26` signal input | Vacuum-ready response for wait | Uses the `E0DET` detector signal pin only, not a normal filament runout function and not the whole connector. Active-low. Disable filament runout on this pin. Do not drive 5 V into the SKR input. |
| `RELEASE_DONE` | Arduino `D7` open-drain/open-collector style output | SKR `E1DET` / `P1_25` signal input | Release-complete response for wait | Uses the `E1DET` detector signal pin only, not a normal filament runout function and not the whole connector. Active-low. Disable filament runout on this pin. Do not drive 5 V into the SKR input. |
| `VAC_FAULT` optional | Arduino `D8` open-drain/open-collector style output | SKR `PWRDET` / `P1_00` signal input | Optional future suction fault input | Reserve only if power-loss features are disabled or remapped. Do not drive 5 V into the SKR input. |
| Arduino logic power | 24 V to 5 V buck | Arduino 5 V / GND | Suction controller power | Common ground is acceptable for this build unless isolation is intentionally changed. |
| Vacuum sensor power | 24 V to 5 V buck | Vacuum sensor | Sensor power | Sensor signal is reserved to Arduino `A0`. |
| Vacuum sensor signal | Vacuum sensor | Arduino `A0` | Optional/reserved vacuum feedback | Used for vacuum-good threshold if installed. |
| Pump power/control | 24 V to 5 V buck and Arduino pump driver | Pump via Arduino `D9` PWM control | Pump full-power and hold-mode control | Arduino owns pump PWM; SKR must not directly drive pump. |
| Vent solenoid power/control | 24 V to 5 V or 12 V buck and Arduino solenoid driver | Vent solenoid via Arduino `D3` | Release vent pulse | Final valve voltage determines buck output. Arduino owns vent timing; SKR must not directly drive solenoid. |
| Ground reference | PSU / bucks / SKR / Arduino | Common ground | Shared logic reference | Common ground is acceptable unless optocouplers are intentionally used for full isolation. |
