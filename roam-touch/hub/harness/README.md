# Harness tools (copies)

`~/.local/bin/` is not a git repository, so these are **copies** of the owner's live
harness tools as extended for the ledger/session sources. The live files are the ones
that run; these exist so the change is reviewable and recoverable.

* `memindex` — added the `ledger` and `sessions` record sources (chunked by
  `../ledger_index.py`), FTS5 (`chunks_fts_v2`) population and backfill, and a
  `record_files` mtime/size guard so unchanged transcripts are never reparsed.
* `memsearch` — added `--exact` (FTS5 literal match) and the two new sources.

Originals before the change: `~/.local/bin/backups/*.2026-08-11.bak`.

If you edit the live tools, re-copy them here.
