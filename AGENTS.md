# Repository Workflow Guidance

## Git workflow

- Before making any change that would be tracked by Git, create or switch to an appropriate non-`main` branch first.
- Do not begin tracked work on `main`.
- Use a separate branch for each feature, bug fix, refactor, documentation update, configuration change, or other tracked change.
- Merge completed branch work back into `main` through the normal review/merge flow.
- Direct commits to `main` are acceptable only for truly tiny fixes made intentionally after deciding they are safe, such as:
  - correcting a typo
  - changing a single obvious value
  - another similarly minimal, low-risk edit
- If there is any doubt about whether a change is "tiny," create a branch instead of working on `main`.
