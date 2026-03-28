# Golden Frames

This directory holds stable perception regression slices.

The current slice is sim-backed, but it is now exercised through a fixed manifest
instead of depending on whatever runtime fixture regeneration happened most
recently.

The goal is not to claim these are final hardware-quality benchmarks. The goal is to establish a repeatable parent-owned regression target that can be expanded later.

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
