# Suction Subsystem Contract

## Purpose

This document is the shared direction for the SKR/Marlin side and the Arduino
suction-controller side.

Core principle:

```text
SKR asks and waits.
Arduino performs and reports.
```

No 24 V or 5 V power-output lines are used as logic handshake lines. Do not use
FAN/HE outputs for SKR-to-Arduino requests unless all real GPIO options are
exhausted.

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

## Ownership Split

SKR 1.4 Turbo / Marlin / OpenPnP owns:

- X/Y/Z/C motion
- homing
- high-level pick/release request
- waiting for Arduino response

Arduino Uno now / Nano later owns:

- pump PWM
- vent solenoid
- vacuum sensor
- pick confirmation
- quiet hold behavior
- release pulse

## SKR Reserved Pins

| Function | SKR connector / pin | Notes |
| --- | --- | --- |
| X home | `X-` / `P1_29` | Used |
| Y home | `Y-` / `P1_28` | Used |
| Z top home | `Z-` / `P1_27` | Used for top-of-machine Z endstop |
| BLTouch servo | `SERVO0` / `P2_00` | Used only for BLTouch deploy/stow |
| BLTouch probe signal | `PROBE` / `P0_10` | Used as probe/device input, not Z homing |

SKR 1.4/Turbo has `X-`, `Y-`, `Z-`, `E0DET`, `E1DET`, and `PWRDET`, not separate
min/max endstop headers. In Marlin's SKR 1.4 pin file these map to:

| Logical input | MCU pin |
| --- | --- |
| `X_STOP` | `P1_29` |
| `Y_STOP` | `P1_28` |
| `Z_STOP` | `P1_27` |
| `E0DET` | `P1_26` |
| `E1DET` | `P1_25` |
| `PWRDET` | `P1_00` |

The same pin file maps `SERVO0` to `P2_00` and the probe input to `P0_10`, so
the BLTouch can remain separate from Z homing.

## SKR To Arduino Request Outputs

Use EXP1 logic pins, not heater/fan outputs:

| Signal | Direction | SKR physical header | MCU pin | Arduino pin |
| --- | --- | --- | --- | --- |
| `PICK_REQUEST` | SKR to Arduino | EXP1 pin 7 | `P1_22` | Arduino `D4` |
| `RELEASE_REQUEST` | SKR to Arduino | EXP1 pin 8 | `P1_23` | Arduino `D5` |
| Logic ground | common | EXP1 pin 9 | `GND` | Arduino `GND` |

Marlin lists EXP1 pins 7 and 8 as `P1_22` and `P1_23`, with EXP1 pin 9 as
ground and pin 10 as 5 V. Use only the signal pins and ground for this
interface.

Electrical rule:

- SKR `P1_22` / `P1_23` are 3.3 V logic outputs.
- Arduino `D4` / `D5` should have 10 kohm pulldowns to GND.
- HIGH means request active.
- LOW means no request.
- A 5 V Arduino normally reads 3.3 V as HIGH, so this is acceptable.
- Do not drive 5 V back into the EXP pins.

## Arduino To SKR Response Inputs

Use the spare detector inputs:

| Signal | Direction | SKR connector | MCU pin | Purpose |
| --- | --- | --- | --- | --- |
| `VAC_GOOD` | Arduino to SKR | `E0DET` | `P1_26` | Pick/vacuum confirmed |
| `RELEASE_DONE` | Arduino to SKR | `E1DET` | `P1_25` | Release cycle complete |
| `VAC_FAULT` | Arduino to SKR | `PWRDET` | `P1_00` | Optional future fault input |

`E0DET` and `E1DET` are Marlin's default filament runout pins, so firmware
should not enable filament runout on those pins. `PWRDET` is Marlin's default
power-loss input / PS_ON-related pin, so reserve it only if power-loss features
are disabled or remapped.

Response electrical rule:

- Arduino must not drive 5 V into SKR inputs.
- Use open-drain / open-collector style.
- Active LOW is preferred.

Recommended circuit per response line:

```text
SKR E0DET/E1DET signal pin ---- collector of NPN or optocoupler transistor
SKR GND ----------------------- emitter of NPN or optocoupler transistor

Arduino output pin -- resistor --> transistor base / optocoupler LED
```

Signal meaning:

| Signal | High / released | Low / pulled down |
| --- | --- | --- |
| `VAC_GOOD` | not ready | vacuum good |
| `RELEASE_DONE` | not done | release done |

## Arduino Pin Allocation

| Arduino pin | Function | Notes |
| --- | --- | --- |
| `D4` | `PICK_REQUEST` input | From SKR EXP1 pin 7 / `P1_22` |
| `D5` | `RELEASE_REQUEST` input | From SKR EXP1 pin 8 / `P1_23` |
| `D6` | `VAC_GOOD` output | Open-drain driver to SKR `E0DET` / `P1_26` |
| `D7` | `RELEASE_DONE` output | Open-drain driver to SKR `E1DET` / `P1_25` |
| `D8` | `VAC_FAULT` output | Optional future output to `PWRDET` / `P1_00` |
| `D9` | Pump PWM | Drives pump transistor/MOSFET |
| `D3` | Vent solenoid output | Drives solenoid transistor |
| `A0` | Vacuum sensor input | Reserved for pressure/vacuum sensor |

## Power And Load Wiring

Assume suction subsystem loads are 5 V:

```text
Ender 3 V2 24 V PSU
        |
        +-- LM2596 buck set to 5 V
              |
              +-- Arduino
              +-- sensor
              +-- pump power
              +-- vent solenoid power
```

Do not power the pump or solenoid from Arduino pins. Arduino pins only drive
the transistor bases/gates.

Load drivers:

| Load | Arduino pin | Driver |
| --- | --- | --- |
| Pump | `D9` PWM | Prefer logic-level MOSFET; TIP120 acceptable for prototype but wastes voltage |
| Vent solenoid | `D3` | TIP120 is acceptable |
| Flyback diode | both loads | Required; diode stripe/cathode to +5 V |

## Firmware Behavior Contract

Pick sequence:

1. OpenPnP/Marlin moves nozzle to pick location.
2. SKR sets `PICK_REQUEST` high on `P1_22`.
3. Arduino sees `D4` high.
4. Arduino closes vent.
5. Arduino runs pump at 100%.
6. Arduino waits for vacuum threshold, or fixed timeout in V1 if no sensor is
   installed.
7. Arduino asserts `VAC_GOOD` low on `E0DET` / `P1_26`.
8. SKR waits until `E0DET` reads active low, then continues.
9. Arduino enters HOLD mode.

Hold behavior:

- Vent closed.
- Pump runs continuously at low PWM for quiet rumble.
- Later: PI trim around target vacuum.
- `VAC_GOOD` remains active while vacuum/card hold is valid.

Release sequence:

1. OpenPnP/Marlin moves nozzle to place location.
2. SKR sets `RELEASE_REQUEST` high on `P1_23`.
3. Arduino sees `D5` high.
4. Arduino turns pump off.
5. Arduino opens vent solenoid for release pulse.
6. Arduino deasserts `VAC_GOOD`.
7. Arduino asserts `RELEASE_DONE` low on `E1DET` / `P1_25`.
8. SKR waits until `E1DET` reads active low, then continues.
9. SKR clears `RELEASE_REQUEST`.
10. Arduino closes vent and clears `RELEASE_DONE`.

## SKR Firmware Requirements

Firmware team should:

- Disable LCD/TFT features using EXP1 pins `P1_22` / `P1_23`, or confirm no
  conflict.
- Configure `P1_22` as `PICK_REQUEST` output.
- Configure `P1_23` as `RELEASE_REQUEST` output.
- Configure `P1_26` / `E0DET` as `VAC_GOOD` input with pullup, active low.
- Configure `P1_25` / `E1DET` as `RELEASE_DONE` input with pullup, active low.
- Disable filament runout usage on `E0DET` / `E1DET`.
- Leave `P1_00` / `PWRDET` unused unless power-loss features are disabled or
  remapped.
- Expose the sequence through `M42` / `M226` or custom G-code macros.

Conceptual G-code:

```gcode
; PICK
set P1_22 HIGH
wait for P1_26 LOW
set P1_22 LOW

; RELEASE
set P1_23 HIGH
wait for P1_25 LOW
set P1_23 LOW
```

## Arduino Firmware Requirements

Arduino team should:

- Treat `D4` high as `PICK_REQUEST`.
- Treat `D5` high as `RELEASE_REQUEST`.
- Drive `D6` through open-drain/open-collector hardware for `VAC_GOOD`.
- Drive `D7` through open-drain/open-collector hardware for `RELEASE_DONE`.
- Never drive SKR input lines directly with 5 V.
- Run pump with PWM on `D9`.
- Drive vent solenoid on `D3`.
- Implement PICK, HOLD, RELEASE, and FAULT states.

## Open Decisions

- Final Marlin syntax or macro names for setting `P1_22` / `P1_23`.
- Final Marlin syntax or macro names for waiting on `P1_26` / `P1_25`.
- Whether `VAC_FAULT` on `PWRDET` / `P1_00` is used in V1.
- Vacuum-good threshold if the sensor is installed.
- Pick timeout and release timeout durations.
- Hold-mode PWM baseline and optional PI trim constants.
