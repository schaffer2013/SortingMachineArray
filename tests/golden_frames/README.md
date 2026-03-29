# Golden Frames

This directory holds stable perception regression slices.

## Terms

A `frame` in this repo is one saved recognition input: the image the
recognizer sees for a single observation, plus the identifying metadata needed
to evaluate the result. In practice that usually means one top-card image path
and its expected card identity.

A `golden frame` is a frame that has been intentionally checked in as a stable
regression case. It is "golden" because we want to rerun it over time and
notice when recognition behavior changes, not because it is guaranteed to be an
easy or perfect example.

A `golden-frame manifest` is the checked-in list of those cases. Each manifest
entry points at one saved frame and the expected label we want the runner to
compare against.

The current slice is sim-backed, but it is now exercised through a fixed manifest
instead of depending on whatever runtime fixture regeneration happened most
recently.

The current golden frames are sim-backed, not hardware captures. The goal is
not to claim these are final hardware-quality benchmarks. The goal is to
establish a repeatable parent-owned regression target that can be expanded
later with more difficult sim cases and future real-world captures.

## Current Command

Run the fixed top-card manifest through the golden-frame runner:

```powershell
.\.venv\Scripts\python.exe scripts\run_golden_frames.py `
  --backend fuzzy_enigma `
  --card-engine-mode small_pool `
  --use-expected-label
```

That command writes:

- a summary JSON under `data/recognition_reports/`
- a portable success or failure bundle under `data/recognition_reports/portable/`
- per-case artifacts under `data/recognition_reports/artifacts/`

Because the command reads `tests/golden_frames/runtime_small_stack_top_cards.json`
directly, it is a better fit for future hardware debugging than replaying a
mutable generated fixture.
