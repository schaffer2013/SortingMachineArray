# Sprint 3 Log

## Sprint Goal

Harden the next layer of the parent-owned perception workflow by making benchmark and replay outputs more inspectable, expanding recovery-focused metrics, and adding stronger tests around partial or uncertain observations.

## Working Norms

- This log is append-only unless a statement is clearly wrong and needs correction.
- Timestamps use local machine time when available.
- ETAs are best-effort and will be updated as reality changes.

---

## 2026-03-28T03:29:33-07:00

**Status**

- Sprint 3 started from local branch `sprint-3-benchmark-hardening`.
- `phase-2` was clean and already pushed before branching.

**Current Read**

- The parent project can now benchmark and replay the real recognizer, but the saved artifacts are still thinner than the roadmap wants.
- Run metrics capture the basics, but they still do not show enough about confidence distribution, stale-observation pressure, or why a run ended up in review.
- The simulator is more honest than before, but the test suite still needs stronger coverage for behavior under partially known pile state.

**Initial Plan**

- Inspect the benchmark, replay, orchestrator, and run-store paths for the cleanest integration points.
- Save more development-time artifacts from replay or benchmark runs so tuning is easier to inspect.
- Expand metrics and summaries to capture richer recognition and recovery signals.
- Add tests that prove the application behaves sensibly when observations are unknown, stale, or review-prone.

**Initial ETA**

- Read-in and design pass: `30-45` minutes
- Artifact and metrics implementation: `1-2` hours
- Tests, docs, and local commit: after that

---

## 2026-03-28T03:39:20-07:00

**Status**

- Benchmark and replay summaries now capture review reasons and confidence-band counts.
- `fuzzy_enigma` benchmark and replay runs now export inspectable per-case artifacts for debugging.
- Runtime run metrics now use the same review-reason and confidence-band language as the benchmark path.
- Partial-knowledge workflow coverage was expanded to prove the planner waits instead of advancing on unknown state.

**What Changed**

- Added shared recognition-reporting helpers so review classification and confidence bands are not reimplemented differently in different paths.
- Benchmark summaries now distinguish low-confidence reviews from missing-prediction reviews.
- Benchmark and replay commands can now materialize artifact bundles with:
  - copied source frame
  - `case.json`
  - `alternatives.json`
  - `debug.json`
  - `ocr_lines.txt`
  - `bbox.json`
- Runtime metrics now retain:
  - confidence-band counts
  - review-reason counts
- Workflow tests now cover:
  - refusing to move onto an unknown destination
  - refusing to advance feeder discovery when any feeder remains unknown

**Verification**

- `.\.venv\Scripts\python.exe -m pytest tests`
  - `66 passed`
- `.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma --json-out tmp_benchmark_artifacts\fuzzy_summary.json --artifact-root tmp_benchmark_artifacts\artifacts`
  - `name_accuracy=0.833`
  - `average_confidence=0.794`
  - `review_count=1`
  - `review_reason_counts={"confidence_below_threshold": 1}`

**Current Read**

- The benchmark loop is now more inspectable without having to manually dig through the submodule or SQLite rows.
- The next best leverage after this slice is probably one of:
  - stable golden-frame command coverage that does not depend on regenerating the runtime fixture
  - broader noisy-sim fault modeling
  - planner-side ranking behavior under provisional discovery
