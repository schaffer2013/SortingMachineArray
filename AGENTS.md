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

## Raspberry Pi deployment verification

- Before deploying to the board, make sure the development machine is clean and on the intended commit:
  - `git status --short --branch`
  - `git rev-parse --short HEAD`
- Make sure GitHub has the same commit before asking the Pi to update:
  - `git push origin main`
  - `git fetch origin main`
  - `git rev-parse --short main`
  - `git rev-parse --short origin/main`
- Check the board's current and remote view from the web API:
  - `Invoke-WebRequest -UseBasicParsing -Uri 'http://sortingmachine.local:8000/api/system?refresh=true'`
  - Confirm `current_sha`, `remote_sha`, `commits_behind`, `dirty`, and `can_update`.
- Pull the GitHub `main` commit onto the board through the web API:
  - `Invoke-WebRequest -UseBasicParsing -Method POST -Uri 'http://sortingmachine.local:8000/api/system/update'`
  - Confirm the response reports the expected `version` and `current_sha`.
- If the update response says `restart_required: true`, restart the Pi web service before testing new routes or UI:
  - `ssh raspberry@sortingmachine 'sudo systemctl restart sortingmachine-web'`
  - If SSH is unavailable, have the operator run `sudo systemctl restart sortingmachine-web` on the Pi.
- After restart, verify the running web process, not just the working copy:
  - reload the relevant page, such as `http://sortingmachine.local:8000/camera`
  - call `http://sortingmachine.local:8000/api/system`
  - confirm the System tab/API reports the expected `x.y.z-SHA`.
- Treat deployment as incomplete until all three locations agree: development `main`, `origin/main`, and the Pi System API.

## Collection integration

- Before implementing or changing anything that interfaces with the collection or registration service, review the current collection API contract in:
  - `https://github.com/schaffer2013/magic-the-collecting/blob/main/API.md`
- Treat that external `API.md` as the authoritative contract for collection-facing endpoints, fields, status codes, and export shape.
- If local docs or assumptions disagree with the external API contract, update the local repo to match the external contract rather than inventing a divergent sorter-side interface.
