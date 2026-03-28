# Sprint 1 Log

## Sprint Goal

Make the real `fuzzy_enigma` recognizer operational, measurable, replayable, and inspectable from the parent project.

## Working Norms

- This log is append-only for the sprint unless a typo or clearly wrong statement needs correction.
- Timestamps use local machine time with offset when available.
- ETAs are best-effort and will be updated as new information appears.
- "Status" is meant to be review-friendly, not perfect.

---

## 2026-03-27T21:10:36-07:00

**Status**

- Sprint 1 started.
- Current branch: `phase-2`
- Remote: `origin https://github.com/schaffer2013/SortingMachineArray.git`
- Pre-existing local delta: uncommitted `docs/two_sprint_plan.md`

**Intent**

- Front-load environment setup and real-backend validation.
- If install/unblock work fails, report that immediately and pivot into the smallest change set needed to make it work.

**Initial ETA**

- Environment and OCR dependency validation: `30-60` minutes
- First meaningful `fuzzy_enigma` benchmark attempt: within the first `90` minutes
- First Sprint 1 checkpoint commit: within the first `2-3` hours

**Notes**

- User approved local installs into `.venv`.
- User approved commit/push/merge workflow.
- No real captures are available, so Sprint 1 will start from sim-backed capture and replay infrastructure.

---

## 2026-03-27T21:14:16-07:00

**Status**

- Parent repo editable install succeeded in `.venv`.
- Submodule OCR install hit a timeout before a clean terminal return.
- However, the important runtime pieces are present:
  - `fuzzy-enigma-card-recognition`
  - `rapidocr-onnxruntime`
  - `onnxruntime`
  - `opencv-python-headless`
- `paddleocr` is not installed yet.

**Explanation**

- This does not currently look like a hard compatibility failure.
- It looks like a heavy optional dependency path exceeded the command timeout.
- The parent adapter only requires an OCR backend to be present, and `rapidocr-onnxruntime` satisfies that requirement.

**Decision**

- Continue immediately with real `fuzzy_enigma` validation using the installed `rapidocr` path.
- Only return to `paddleocr` installation if runtime evidence shows `rapidocr` is insufficient for the current integration work.

**ETA Update**

- First meaningful `fuzzy_enigma` replay/benchmark attempt remains on track within the first `90` minutes.

---

## 2026-03-27T21:20:00-07:00

**Status**

- Real `fuzzy_enigma` benchmark and replay both ran successfully from the parent repo.
- Initial baseline with inherited default engine settings was weak:
  - benchmark `name_accuracy=0.167`
  - `review_count=5/6`
  - replayed `0,0` case returned `predicted=None`

**Explanation**

- The adapter and OCR path are working.
- The problem is not "backend unavailable."
- The first detailed debug read showed a critical clue:
  - OCR and candidate matching were finding the right card for at least some failing cases
  - but the engine exceeded the default live `20.0s` deadline and returned a failure result instead of the partial best match

**Diagnostic Experiment**

- Ran the same parent benchmark using a temporary parent-owned engine config with:
  - `recognition_deadline_seconds=60.0`
  - `catalog_path` pinned to the parent-owned catalog
- Result:
  - `name_accuracy=0.833`
  - `average_confidence=0.754`
  - only `2` cases still marked for review

**Conclusion**

- The biggest immediate blocker is benchmark/runtime config ownership, not adapter wiring.
- Sprint 1 should now prioritize:
  - parent-owned card-engine config
  - benchmark-friendly deadline control
  - richer saved artifacts so the remaining low-confidence cases are easy to inspect

**ETA Update**

- Config and benchmark control changes: next `1-2` hours
- Artifact and dataset layout work: after that, still on track for the current sprint

---

## 2026-03-27T21:32:30-07:00

**Status**

- Parent-owned card-engine config files were added:
  - `config/card_engine/engine.json`
  - `config/card_engine/benchmark.engine.json`
- Parent benchmark and replay scripts now prefer the benchmark config automatically for `fuzzy_enigma`.
- Recognition summaries now preserve:
  - alternatives
  - debug payload
- Dataset scaffolding and import path were added:
  - `data/vision/`
  - `scripts/ingest_frames.py`
- First acceptance and regression scaffolding were added:
  - `docs/acceptance_gates.md`
  - `tests/golden_frames/runtime_small_stack_top_cards.json`
- Summary comparison tooling was added:
  - `scripts/compare_recognition_summaries.py`

**Measured Results**

- `sim_truth` benchmark:
  - `name_accuracy=1.000`
- `fuzzy_enigma` benchmark with parent benchmark config:
  - `name_accuracy=0.833`
  - `average_confidence=0.754`
  - `review_count=2`
- `fuzzy_enigma` replay for `pile 0,0`:
  - `Elspeth, Storm Slayer`
  - confidence `0.516`
  - still marked `review=True`, which is expected under the current `0.6` policy threshold
- summary comparison against `sim_truth` on the current six-card slice:
  - `changed_prediction_count=1`

**Interpretation**

- Sprint 1 moved the project from "backend wired" to "backend benchmarkable and inspectable."
- The current limiting factor is no longer parent integration plumbing.
- The next quality gains are likely to come from:
  - better OCR or ROI tuning
  - benchmark-slice expansion
  - policy refinement for borderline-but-correct low-confidence matches

**Verification Run**

- `.\.venv\Scripts\python.exe -m pytest tests`
- `.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend sim_truth`
- `.\.venv\Scripts\python.exe scripts\benchmark_recognizer.py --backend fuzzy_enigma`
- `.\.venv\Scripts\python.exe scripts\replay_recognition.py --backend fuzzy_enigma --pile 0,0`
- `.\.venv\Scripts\python.exe scripts\ingest_frames.py --summary-json data\recognition_reports\fuzzy_enigma_summary.json --source-mode sim --split benchmark`
- `.\.venv\Scripts\python.exe scripts\compare_recognition_summaries.py --baseline data\recognition_reports\sim_truth_summary.json --candidate data\recognition_reports\fuzzy_enigma_summary.json --json-out data\recognition_reports\sim_vs_fuzzy_compare.json`

**ETA Update**

- This is a strong Sprint 1 checkpoint.
- Next productive slice after commit would be either:
  - benchmark-slice expansion and low-confidence review analysis
  - or the Sprint 2-style planner work around observation-driven recovery

---

## 2026-03-27T21:35:08-07:00

**Status**

- Sprint 1 checkpoint commit created on `sprint-1-recognition-ops`:
  - `e483c70` `Stand up Sprint 1 recognition ops workflow`
- Branch pushed to remote:
  - `origin/sprint-1-recognition-ops`
- Branch merged back into `phase-2`:
  - merge commit `087811a`
- `origin/phase-2` now points at the merge commit as well.

**Why This Checkpoint Matters**

- The branch now contains both:
  - implementation changes
  - a reviewable execution trail through the sprint plan and sprint log

**Recommended Next Slice**

- Expand the stable benchmark set beyond the current six top cards.
- Analyze the two remaining review cases and decide whether the next best improvement is:
  - ROI tuning
  - OCR backend comparison
  - or policy adjustment for borderline-but-correct low-confidence matches.
