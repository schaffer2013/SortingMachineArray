# Suction Subsystem Contract

## Purpose

This document is the shared direction for both sides of the suction subsystem:
the Marlin/SKR firmware side and the Arduino suction-controller side.

Core principle:

```text
SKR handles motion and waits.
Arduino handles suction, pump control, venting, and vacuum feedback.
```

The SKR must not directly control the pump or vent solenoid. It should only send
pick/release requests and wait for done/ready responses.

## Architecture

```text
OpenPnP / Marlin
        |
BTT SKR 1.4 Turbo  = motion controller + high-level request/wait logic
        |
Arduino Uno/Nano   = suction controller
        |
pump / vent solenoid / vacuum sensor
```

## SKR Developer Guidance

Already used:

| SKR resource | Use |
| --- | --- |
| `X_MIN` | X homing |
| `Y_MIN` | Y homing |
| `Z_MAX` | Z homing |
| `SERVO0` | BLTouch, unavailable |

Recommended SKR pins/signals:

| Function | Direction | SKR side |
| --- | --- | --- |
| `VAC_GOOD` | Arduino to SKR | `X_MAX` endstop input |
| `RELEASE_DONE` | Arduino to SKR | `Y_MAX` endstop input |
| `PICK_REQUEST` | SKR to Arduino | unused FAN/HE output through optocoupler |
| `RELEASE_REQUEST` | SKR to Arduino | unused FAN/HE output through optocoupler |

Use active-low response signals if possible.

## SKR G-code Concept

Pick:

```gcode
M42 P<PICK_REQUEST_PIN> S255
M226 P<X_MAX_PIN> S0
M42 P<PICK_REQUEST_PIN> S0
```

Release:

```gcode
M42 P<RELEASE_REQUEST_PIN> S255
M226 P<Y_MAX_PIN> S0
M42 P<RELEASE_REQUEST_PIN> S0
```

`M226` should wait until the Arduino pulls the corresponding response input
active.

The exact `P...` pin numbers must come from the final SKR 1.4 Turbo Marlin pin
mapping. Record those final pin names/numbers in this document once assigned.

## Arduino Developer Guidance

Recommended Arduino pinout:

| Arduino pin | Function |
| --- | --- |
| `D4` | `PICK_REQUEST` input from SKR optocoupler |
| `D5` | `RELEASE_REQUEST` input from SKR optocoupler |
| `D6` | `VAC_GOOD` output to SKR `X_MAX` |
| `D7` | `RELEASE_DONE` output to SKR `Y_MAX` |
| `D9` | Pump PWM output |
| `D3` | Vent solenoid output |
| `A0` | Vacuum sensor input, optional/reserved |

## Arduino Behavior

On `PICK_REQUEST`:

1. Turn vent off.
2. Run pump at 100% until the vacuum-good threshold is reached or timeout.
3. Assert `VAC_GOOD`.
4. Enter hold mode.

In hold mode:

1. Run pump continuously at low PWM or PI trim.
2. Maintain suction quietly.
3. Keep `VAC_GOOD` asserted while vacuum remains acceptable.

On `RELEASE_REQUEST`:

1. Turn pump off.
2. Turn vent solenoid on briefly.
3. Deassert `VAC_GOOD`.
4. Assert `RELEASE_DONE`.

Timeouts and fault states should be explicit. If vacuum cannot be reached, the
Arduino should avoid asserting `VAC_GOOD`, and the SKR-side wait should time out
or require operator recovery according to the final firmware policy.

## Electrical Interface

SKR to Arduino request lines:

```text
SKR FAN/HE output -> optocoupler input -> Arduino D4/D5
```

Add optocouplers between the SKR switched outputs and Arduino inputs. Do not
wire SKR heater/fan outputs directly to Arduino pins.

Arduino to SKR response lines:

```text
Arduino D6/D7 -> open-drain/open-collector style pull-down -> SKR X_MAX/Y_MAX
```

Do not send 5 V from the Arduino directly into SKR endstop inputs. Use
transistor pull-downs, optocouplers, or level shifting.

## Power

```text
Ender 3 V2 24 V PSU
        |
        +-- 24 V -> 5 V buck -> Arduino + sensor
        +-- 24 V -> 5 V buck -> pump
        +-- 24 V -> 5 V or 12 V buck -> vent solenoid, depending on final valve
```

All grounds common unless optocouplers are intentionally used for isolation. For
this build, common ground is acceptable.

## Firmware Bring-up Checklist

- Confirm SKR pin mapping for `PICK_REQUEST` and `RELEASE_REQUEST`.
- Confirm SKR endstop input mapping for `VAC_GOOD` and `RELEASE_DONE`.
- Confirm `M42` can drive both request outputs.
- Confirm `M226` can wait on the selected response inputs.
- Confirm active-low response behavior.
- Confirm Arduino request inputs change state only through the optocouplers.
- Confirm Arduino response outputs do not drive 5 V into SKR inputs.
- Confirm pump full-power, hold-power, and off states.
- Confirm vent pulse duration releases a card reliably without excessive air.
- Confirm vacuum sensor threshold and timeout behavior if `A0` is used.
- Confirm failure behavior when `VAC_GOOD` never arrives.
- Confirm release behavior deasserts `VAC_GOOD` and asserts `RELEASE_DONE`.

## Open Decisions

- Final SKR `PICK_REQUEST_PIN` and `RELEASE_REQUEST_PIN` values.
- Final SKR `X_MAX_PIN` and `Y_MAX_PIN` identifiers for `M226`.
- Active-low polarity details in Marlin and Arduino firmware.
- Vacuum-good threshold if the sensor is installed.
- Pick timeout and release timeout durations.
- Hold-mode PWM baseline and optional PI trim constants.
- Vent solenoid voltage and buck converter selection.
