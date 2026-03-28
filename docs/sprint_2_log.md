# Sprint 2 Log

## Sprint Goal

Make the sorter more observation-driven and recovery-aware by reducing hidden sim truth leakage, adding explicit retry or review behavior for uncertain recognition, and introducing noisy-sim coverage plus richer run metrics.

## Working Norms

- This log is append-only unless a statement is clearly wrong and needs correction.
- Timestamps use local machine time when available.
- ETAs are best-effort and will be updated as reality changes.

---

## 2026-03-27T22:10:47-07:00

**Status**

- Sprint 2 started from `phase-2` after the Sprint 1 checkpoint was merged and pushed.
- Working tree was clean enough to branch from.

**Current Read**

- The biggest remaining architectural gap is that the sim camera still mutates observed pile state on capture, which means the application learns too much before recognition has even succeeded.
- The orchestrator also still handles low-confidence results as a hard stop instead of a structured retry or review path.
- Noisy-sim coverage is still mostly aspirational.

**Initial Plan**

- Move observation mutation out of the camera path and into the recognition-orchestration path.
- Add retry-aware startup scan and move verification flows.
- Distinguish review-required runs from hard faults.
- Add simple noisy-sim recognition faults that can be exercised in tests.
- Track richer run metrics and update docs accordingly.

**Initial ETA**

- Observation and recovery refactor: `2-3` hours
- Noisy-sim support and tests: `1-2` hours
- Metrics, docs, verification, and merge: after that

---

## 2026-03-27T22:23:47-07:00

**Status**

- Observation mutation was moved out of the sim camera path.
- Startup scan and move verification now retry before escalating.
- Unresolved perception now returns `REVIEW_REQUIRED` instead of collapsing into an undifferentiated fault path.
- Initial noisy-sim recognition fault injection is in place.
- Run metrics now include:
  - scans
  - retries
  - review-required count
  - fallback count
  - low-confidence count

**What Changed**

- `SimCameraAdapter.capture_top_card(...)` now captures frame data without mutating observed pile state.
- `SimWorld.pick_from(...)` now leaves the newly exposed source top card unknown until the next scan instead of auto-revealing it.
- `Orchestrator` now owns the observation cycle:
  - capture
  - recognize
  - apply observation
  - retry if needed
  - escalate to `REVIEW_REQUIRED` when retries are exhausted
- `SQLiteRunStore` now persists final run metrics.
- A noisy-sim fixture now proves the startup review-required path in tests.

**Verification**

- `.\.venv\Scripts\python.exe -m pytest tests`
  - `64 passed`
- `.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma`
  - `name_accuracy=0.833`
  - `average_confidence=0.794`
  - `review_count=1`
- `.\.venv\Scripts\python.exe scripts\replay_recognition.py --backend fuzzy_enigma --pile 0,0`
  - `Elspeth, Storm Slayer`
  - confidence `0.753`
  - `review=False`

**Important Note**

- Sim-backed benchmark and replay commands should be run sequentially, not in parallel, because they both touch the generated runtime fixture path.

**Sprint 2 Assessment**

- The planner is not fully free of hidden truth yet because ranking still depends on observed card IDs in ways that deserve a deeper follow-up.
- But Sprint 2 did complete its intended practical goals:
  - more honest observation updates
  - explicit retry and review behavior
  - noisy-sim regression coverage
  - richer run metrics and clearer operational status

---

## 2026-03-27T22:29:22-07:00

**Status**

- Sprint 2 branch `sprint-2-observation-recovery` was merged into `phase-2`.
- `phase-2` was pushed to `origin`.
- Merge commit: `ca4e9c8`

**Final Outcome**

- The parent project now treats recognition as an observation workflow instead of a hidden-truth side effect.
- Low-confidence or missing recognitions now have retry budgets and a clean `REVIEW_REQUIRED` escalation path.
- The sim harness can inject basic recognition faults for regression coverage.
- Run completion records now persist richer metrics for later analysis.

**Final Verification Snapshot**

- `.\.venv\Scripts\python.exe -m pytest tests`
  - `64 passed`
- `.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma`
  - `name_accuracy=0.833`
  - `average_confidence=0.794`
  - `review_count=1`
- `.\.venv\Scripts\python.exe scripts\compare_recognition_summaries.py --baseline data\recognition_reports\sim_truth_summary.json --candidate data\recognition_reports\fuzzy_enigma_summary.json --json-out data\recognition_reports\sim_vs_fuzzy_compare.json`
  - `changed_prediction_count=1`
  - `candidate_review_reduction=0`

**Follow-On Read**

- The next strongest lever is still improving candidate-quality and confidence calibration for the remaining review-heavy cases rather than expanding more simulation complexity first.
