# Legacy Files

This directory holds archived pieces of the pre-refactor root-level flow.

These files are kept for historical reference only. They are not part of the
supported runtime path under `src/sorter/...`.

Current contents:

- `card.py`: legacy card model and card-data fetch flow
- `pile_manager.py`: legacy pile orchestration logic
- `config.json`: legacy monolithic config file

One narrow exception remains: the sim image sync flow may still read
`legacy/pile_manager.py` as plain text to mine old literal card/image names.
That is a read-only compatibility shim, not a supported execution path.
