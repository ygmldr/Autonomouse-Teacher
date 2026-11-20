# M1-B evidence packet (offline, synthetic only)

This directory is an append-only evidence packet produced by
`scripts/m1b/collect_evidence.py`.

- `audit-index.jsonl` - authoritative append-only audit index (one JSON object per run).
- `audit-index.json` - materialised view of the same entries (rewritten atomically; entries
  are never dropped or altered).
- `raw/<run_id>/evidence.json` - the hashed raw evidence for one run (command, environment,
  exit code, stdout/stderr summaries, artifacts).
- `raw/<run_id>/stdout.log` / `stderr.log` - captured streams (capped at 2 MiB each).

Boundary: **offline synthetic only, not real teaching effect**. `EXECUTED_PASS` is an
execution outcome and is NOT a product/evidence PASS. Evidence classes (`MOCK`,
`DETERMINISTIC`, `INDEPENDENTLY_REEXECUTED`, ...) must be assigned by the Reviewer; the
collector never upgrades an execution result into a product PASS claim. No real API key,
network access, real learner data or real provider is used. `utc` timestamps in the index
are wall-clock audit metadata and must not be treated as deterministic artifact content.
A packet without a command, without a hash, or without Reviewer re-execution cannot be
used as PASS evidence.
