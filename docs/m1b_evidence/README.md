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


## Provenance / append-only notes (final review P1-2)

- 本证据包按 append-only 维护：既有 16+11 条记录原样保留；P1-2 重新生成时只**追加**新条目
  （`limitation` 中标注 generated-against SHA / supersedes），不覆盖/删除旧行。
- 生成与提交 SHA 的绑定在 `docs/M1_B_EVALUATION_REPORT.md` §13 与本文件下方 provenance 块给出：
  生成时工作树必须 `git status --porcelain` 为空（生成过程只修改 `docs/m1b_evidence/**` 证据文件），
  被测量代码与 `git_sha`/`tree_sha` 由 collector 记录；evidence 文件由后续 commit 提交。
