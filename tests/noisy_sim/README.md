# Noisy Sim

This directory holds sim fixtures that intentionally produce uncertain recognition or recovery behavior.

Current fixtures now cover:

- low-confidence startup scans that retry and then escalate to `REVIEW_REQUIRED`
- false-empty recognition failures where a visible card is incorrectly treated as absent

The adapter-side noisy-sim fault vocabulary also includes ambiguous candidate
clusters and confirmation contradictions so parent recovery logic can be
exercised before hardware brings those cases in for real.
