# Visual retrieval index artifact

This directory contains a Git LFS snapshot of the generated visual retrieval
index. Both files are required:

- `card_embeddings.npz`: 115,684 embeddings with shape `(115684, 704)` and
  `float32` values.
- `card_embeddings.jsonl`: 115,684 metadata records aligned by row with the
  embeddings.

The source catalog contained 115,709 cards. Twenty-five cards were skipped
because their configured image URLs returned HTTP 404 responses when this
snapshot was built.

## Integrity

| File | SHA-256 |
| --- | --- |
| `card_embeddings.npz` | `12a0452ddc3a7212c486212f40575e6f569eb7eb526c8b0c85d27640bd07889c` |
| `card_embeddings.jsonl` | `3d4316902820868e7a5ff7cdad0ade4292b0896463a65aeac9bc72aaf743deba` |

## Restore into a runtime checkout

Fetch the LFS objects, then copy both files into the ignored runtime index
directory:

```bash
git lfs pull
mkdir -p data/index
cp artifacts/visual-index/card_embeddings.npz data/index/
cp artifacts/visual-index/card_embeddings.jsonl data/index/
```

Keeping the snapshot separate from `data/index/` prevents later syncs from
modifying tracked files and making deployed checkouts dirty.
