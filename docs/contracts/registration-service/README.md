# Registration service contract cache

This directory contains a slim, tracked copy of the external Registration Service API contract used by this sorter project.

- `API.md` is copied from `schaffer2013/magic-the-collecting`.
- `API.source.json` records the exact upstream commit and URLs used for the copy.
- Run `scripts/update_registration_api_contract.ps1` from the repository root to refresh the cached copy.

The external contract remains authoritative. The complete service is now pinned at
`third_party/magic-the-collecting`; this cache remains for parent-repository
contract diffs and tooling that expects a stable local path.
