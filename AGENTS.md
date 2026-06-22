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
- Updating submodule pointers after pulling submodules is also allowed directly on `main`:
  - switch to `main`
  - pull submodules recursively to bring them up to date
  - commit and push the resulting submodule pointer change directly from `main`
- If there is any doubt about whether a change is "tiny," create a branch instead of working on `main`.
- Commit completed changes before changing context when practical, using explicit path staging and a concise message.
- When the work context changes, ask whether to switch branches, merge the current branch, or leave the current branch active if that choice is not already clear.

## Software version tracking

- Track the software version for each commit as `x.y.z-SHA`, where `x.y.z` comes from the project version in `pyproject.toml` and `SHA` is the short Git commit SHA.
- When making a release-oriented or operator-visible change, confirm that the web System tab reports the expected `x.y.z-SHA` after the commit is created.
- Increment `x.y.z` intentionally when the user requests a version bump or when the change should be treated as a new packaged software version; otherwise the commit SHA uniquely identifies the build.

## Collection integration

- Before implementing or changing anything that interfaces with the collection or registration service, review the current collection API contract in:
  - `https://github.com/schaffer2013/magic-the-collecting/blob/main/API.md`
- Treat that external `API.md` as the authoritative contract for collection-facing endpoints, fields, status codes, and export shape.
- If local docs or assumptions disagree with the external API contract, update the local repo to match the external contract rather than inventing a divergent sorter-side interface.
