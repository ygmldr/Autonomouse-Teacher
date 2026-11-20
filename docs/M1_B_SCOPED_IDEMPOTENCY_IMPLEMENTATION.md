# M1-B B-PR3 — Scoped idempotency & multi-learner isolation: implementation report

- **Status**: implemented + tested on branch `b-next/pr3-scoped-idempotency`,
  based on PR2 HEAD `998e6d2`; design branch merged as `4a10eb0`
  (`docs/M1_B_SCOPED_IDEMPOTENCY.md`, additive-only).
- **Owner**: B-NEXT implementer (`b-core` / M1-B), directed by the Lead.
- **Scope**: offline teacher core only. No network, no API keys/providers, no M0
  (`src/autoteacher_m0/**`), security, bridge, `config/g*`, `scripts/g4*` or
  LiveGate changes. Synthetic CF fixtures only.
- **Evidence class**: `DETERMINISTIC` for the scope/migration assertions,
  `MOCK` for the synthetic scorer doubles, `CONCURRENCY` (real OS processes)
  for the convergence tests. **No claim** of exactly-once remote scoring, of
  real learning effectiveness, or of multi-tenant authentication/security.
- **B3-01 / B3-02**: the new negative tests below implement the acceptance
  criteria, but `TEST_EVIDENCE_MATRIX.csv` entries remain `NOT_RUN` until an
  independent reviewer re-runs them; this report only records implementer-run
  raw output.

This document is the audit artifact for the Lead-approved PR3 scope
(“scoped idempotency & multi-learner isolation”): what changed, what was
deliberately *not* changed, how the v1→v2 schema migration behaves, the real
test output, and the remaining limitations.

---

## 1. Baseline and problem closure

### 1.1 Frozen defect (design doc §2)

On the pre-fix engine, `submit_response(result_id=...)` resolved an explicit
token through a **global** `event_id` read
(`repository.get_event("evt.assessed.<result_id>")`) whose signature carried
only `result_id`. Consequences proven by the design probe:

1. a second learner reusing learner A's token received A's
   `AssessmentResult` verbatim (`returned_is_A_result=true`), while B's own
   submission was silently skipped (B events `4 → 4`, pending/turn unchanged);
2. a same-session/same-token but different response silently returned the old
   grade (B3-02);
3. the PR2 transactional path had in-flight variants of the same defect:
   `_terminal_result`/`_lookup_result_for_retry` parsed a foreign payload before
   comparing identity, and `_commit_result_turn`'s `DUPLICATE_EVENT` catch
   returned a global terminal result unconditionally.

### 1.2 Fix shape (as designed: plan A)

The lookup key became the full frozen scope
`(learner_id, session_id, item_id, turn_index, result_id)` plus
`request_digest = sha256(canonical_response(response))`. All result reads go
through a scoped repository API that returns an `AssessmentResult` **only** for
an exact v1 scope match; legacy (pre-scope) evidence is only adopted by an
explicit adapter that requires learner+session+item match **and** a provable
response-digest prefix. New writes persist the scope in the event payloads
(add-only) and in a new additive `result_scopes` index table (schema v2).
`history_events` rows are never updated, deleted or rewritten.

`event_id` keeps its historical shape (`evt.assessed.<result_id>` etc.) as the
global uniqueness guard; the “one token, many scopes” v2 event-id plan (design
plan B) is deliberately **not** implemented.

---

## 2. Files changed

| File | Change |
| --- | --- |
| `m1_teacher/idempotency.py` | **new** pure module: `ResultScope`, `ScopeMetadata`, canonical response/request digest, deterministic default `result_id`, result-id validation, scope payload helpers, conflict reasons, legacy digest comparison. |
| `m1_teacher/contracts/errors.py` | add-only codes `IDEMPOTENCY_CONFLICT`, `INVALID_RESULT_ID`, `IDEMPOTENCY_UNSUPPORTED` (module constants; existing exception classes/codes unchanged). |
| `m1_teacher/learner/repository.py` | schema v2 (`SCHEMA_VERSION = 2`) + additive `result_scopes` DDL; v1→v2 migration with legacy backfill; `supports_scoped_idempotency()`; `find_result_in_scope()`, `find_scope_owner()` (metadata only), `get_event_for_learner()`; `commit_teaching_turn(..., scope=...)` writes/advances the scope row **inside the same transaction**. |
| `m1_teacher/learner/history.py` | `assessment_event_drafts(..., scope=None)` embeds the add-only `scope` object in `ASSESSED`/`MASTERY_UPDATED` payloads (legacy call sites unchanged). |
| `m1_teacher/session/engine.py` | scoped fast-path before pending/turn checks; explicit token validation; stable `IDEMPOTENCY_CONFLICT` reasons; optional `caller_learner_id` fail-closed assertion; scoped/legacy result adapter; scope carried through transaction A (payload) and B (index row); duplicate/CAS catch re-reads **only** through the exact scoped key; migration-compatible legacy event id/digest path. |
| `tests/m1_teacher/test_scoped_idempotency.py` | **new** 26 tests (see §5). |
| `tests/m1_teacher/test_scope_migration.py` | **new** 11 tests (see §5). |
| `docs/M1_B_SCOPED_IDEMPOTENCY_IMPLEMENTATION.md` | this report. |

No existing test needed behavioural changes: PR2’s
`test_e2e_resume_idempotency.py::test_duplicate_result_id_updates_mastery_once`
already expected the stronger different-response conflict and keeps passing;
`test_session_engine.py::test_duplicate_submit_with_same_result_id_is_idempotent`
(same response) keeps passing unchanged. No test was weakened or removed.

### 2.1 Implementation deviations from the design draft (all Lead-approved scope)

1. **Pure module location**: `m1_teacher/idempotency.py` instead of
   `m1_teacher/session/idempotency.py`. Importing the latter would execute
   `m1_teacher/session/__init__.py` → `engine.py` → `learner.repository` while
   `learner.repository` itself imports the helpers, creating an import cycle.
   The module is pure (stdlib `hashlib`/`json`/`re`/`dataclasses` only, no I/O).
2. **Attempt id shape retained**: `attempt:<session>:<turn>:<item>`
   (PR2 on-disk recovery compatibility). Learner/session binding is enforced by
   decoding and validating the `ASSESSMENT_PREPARED` payload (and the embedded
   scope) instead of renaming attempt ids.
3. **`caller_learner_id` mismatch** raises the existing `ConflictError` code
   `CONFLICT` with `details={"reason": "CALLER_LEARNER_MISMATCH"}` instead of a
   new `SCOPE_OWNERSHIP_MISMATCH` code, keeping the Lead-approved error-code
   set at exactly three additions.
4. **Index column names**: `turn_index` / `result_event_id` / `origin` (design
   draft used `turn_id` / `terminal_event_id`; same semantics, no external
   dependency on the names).
5. **Reason precedence**: for a token reused after the turn advanced, a
   different response reports `REQUEST_DIGEST_MISMATCH` (more meaningful and
   deterministic); a same-response replay in a later turn reports
   `TURN_MISMATCH`. A retry of the **just-committed** same submission
   (`owner.turn_index == scope.turn_index - 1`, identical digest/item) is a
   legitimate idempotent replay (matrix M1) and is tolerated in both the v1 and
   legacy adapters.
6. **Legacy unknown digest**: default reject (`LEGACY_DIGEST_UNPROVEN`) is
   implemented; the optional explicit migration-tool opt-in
   (`allow_legacy_unknown_digest=True`) is **not** added in this PR (fail-closed
   default only).
7. **Upgrade compatibility**: for default (non-explicit) submissions the engine
   recognises the pre-PR3 default id
   (`result:<session>:<turn>:<item>:<digest16>`) through the legacy adapter, so
   a same-request retry against an upgraded database can still adopt the old
   result; new writes always use `result.v1.<32-hex>`.

---

## 3. Scoped-idempotency API and persistence

### 3.1 Frozen scope and digests (`m1_teacher/idempotency.py`)

```text
scope            = (learner_id, session_id, item_id, turn_index, result_id)
request_digest   = sha256(canonical_response(response))           # 64 lowercase hex
default_result_id= "result.v1." + sha256(canonical_json({learner_id,
                    session_id, item_id, turn_index, request_digest}))[:32]
result_id charset= ^[A-Za-z0-9][A-Za-z0-9._:@-]{0,127}$
scope payload    = {"scope_version": "m1b.scope.v1", learner_id, session_id,
                    item_id, turn_index, result_id, request_digest}
```

`ResultScope` is a frozen, fully validated dataclass; `ScopeMetadata` is the
metadata-only projection of a `result_scopes` row (never contains the grading
result). `request_digest` is computed from the canonical response only; the
turn/session/learner are bound through the scope, not mixed into the digest.

### 3.2 Repository extension (additive)

```python
supports_scoped_idempotency() -> bool
find_result_in_scope(scope: ResultScope) -> AssessmentResult | None   # exact v1 scope only
find_scope_owner(result_id: str) -> ScopeMetadata | None              # metadata only, no result
get_event_for_learner(learner_id, event_id) -> HistoryEvent | None    # learner-filtered read
commit_teaching_turn(..., scope: ResultScope | None = None)           # atomic scope row write
```

Semantics:

- `find_result_in_scope` returns a result only for a **TERMINAL v1 row whose
  learner/session/item/turn/digest all match**; a mismatching v1 row raises
  `ConflictError(code="IDEMPOTENCY_CONFLICT")` with
  `details = {reason, requested_scope, policy_version}` (requester data only);
  `PREPARED`/absent/legacy-origin rows return `None`.
- `find_scope_owner` never loads `payload["result"]`, so cross-scope conflict
  decisions cannot parse foreign grading material.
- `get_event_for_learner` returns `None` for another learner’s event id.
- `commit_teaching_turn(scope=...)` validates that the scope owner equals the
  commit learner/session, then inserts a `PREPARED` row (transaction A) or
  advances it to `TERMINAL` with `result_event_id` (transaction B) inside the
  same `BEGIN IMMEDIATE` transaction as the events/snapshot/session. A
  scope/`result_id` mismatch rolls the entire turn back with
  `IDEMPOTENCY_CONFLICT`.

### 3.3 Schema v2 (additive only)

```sql
CREATE TABLE IF NOT EXISTS result_scopes (
    result_id TEXT PRIMARY KEY,
    scope_version TEXT NOT NULL,
    learner_id TEXT NOT NULL REFERENCES learners(learner_id),
    session_id TEXT NOT NULL,
    item_id TEXT NOT NULL,
    turn_index INTEGER NOT NULL CHECK (turn_index >= -1),
    request_digest TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('PREPARED','TERMINAL')),
    attempt_id TEXT NOT NULL,
    result_event_id TEXT,
    origin TEXT NOT NULL DEFAULT 'v1' CHECK (origin IN ('v1','legacy')),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX idx_result_scopes_scope ON result_scopes(learner_id, session_id, item_id, turn_index);
CREATE INDEX idx_result_scopes_session ON result_scopes(learner_id, session_id, status);
```

`turn_index = -1` is allowed only for `origin='legacy'` rows whose turn cannot be
proven; new v1 rows always carry `>= 0`.

### 3.4 Migration (v1 → v2)

`initialize_schema()` now:

1. creates the unchanged v1 tables;
2. if `schema_meta.version` is absent → creates v1+v2 and inserts `2`;
3. if `2` → re-creates the additive table/indexes with `IF NOT EXISTS`
   (self-heals a v2 database whose additive table is missing; no downgrade);
4. if `1` → creates the additive table, runs `_backfill_legacy_scopes(conn)`
   **inside the same transaction**, then updates `schema_meta.version = 2`;
5. any other version (newer/unknown/negative) → `ValidationError`
   (“unsupported on-disk schema version”) and the migration transaction rolls
   back, leaving the file at v1 with no partial table.

Backfill reads the append-only log only: for each `ASSESSED`/`ERROR` event that
carries a self-contained `result` object it inserts an `origin='legacy'` row
with `learner_id = event.learner_id`, `session_id = event.session_id`,
`item_id/result_id` from the payload, `result_event_id = event_id`, and
turn/digest recovered from the matching `ASSESSMENT_PREPARED` /
`RESPONSE_SUBMITTED` event when possible (`legacy:<16-hex>` marker). Otherwise
the row is `turn_index=-1`, `request_digest='legacy:unproven'`. Recovery/audit
`ERROR` events without a `result` payload are skipped (they are not terminal
assessment results). Malformed JSON fails the whole migration closed. Rows are
inserted with `INSERT OR IGNORE` so a rerun/reopen is idempotent.

---

## 4. Engine behaviour

`TeachingSessionEngine.submit_response(session_id, item_id, response, *,
result_id=None, caller_learner_id=None)`:

1. optional `caller_learner_id` (trusted outer-layer assertion; M1 has no real
   auth) must equal the session owner, otherwise fail closed **before** any
   result read or write (`CONFLICT`/`CALLER_LEARNER_MISMATCH`).
2. explicit `result_id` is validated (`INVALID_RESULT_ID`) and the exact scoped
   lookup runs before pending/turn validation (so a retry after the turn
   advanced still works). Same scope+digest terminal → first result returned,
   zero events, scorer not called. Different digest/item/session/learner →
   `IDEMPOTENCY_CONFLICT` with a stable reason; state unchanged. A new token on
   an already-consumed turn → `TURN_ALREADY_ASSESSED` (no content-based implicit
   de-duplication).
3. a durable attempt is one per `(learner, session, item, turn)`: transaction A
   writes `RESPONSE_SUBMITTED` + `ASSESSMENT_PREPARED` (payload now also carries
   `request_digest` and the add-only `scope` object) and the `PREPARED` index row.
   A retry resumes the same attempt; a different explicit token for that
   prepared attempt conflicts instead of becoming a second scoring attempt.
4. the external scorer runs outside any transaction (at-least-once invocation
   possible; exactly-once state application via deterministic terminal event ids
   + the scope row).
5. transaction B writes terminal events (+ optional mastery snapshot/goal/session)
   and advances the scope row `PREPARED → TERMINAL` atomically. Duplicate/CAS
   conflicts are resolved only by re-reading the **exact scope**, never a global
   terminal result.
6. legacy evidence is only adopted by the explicit adapter: learner/session/item
   must match, `turn_index` must be `-1`, equal, or the just-consumed previous
   turn, and the stored 16-hex response-digest prefix must match the current
   request; otherwise `LEGACY_SCOPE_MISMATCH` / `REQUEST_DIGEST_MISMATCH` /
   `LEGACY_DIGEST_UNPROVEN`. If the repository lacks the scoped API, explicit
   token replay fails closed with `IDEMPOTENCY_UNSUPPORTED` (no global fallback).

`recover_session()`/`recover_pending_turns()` keep PR2 semantics; they now
carry the decoded scope through re-scoring and the terminal commit so recovery
also writes/advances the index row.

---

## 5. Test evidence (implementer run, raw output)

### 5.1 Commands and results

```bash
cd /root/m1b/pr3
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
# 632 passed in 33.73s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_scoped_idempotency.py \
  tests/m1_teacher/test_scope_migration.py -q
# 37 passed in 2.51s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_crash_recovery.py \
  tests/m1_teacher/test_concurrency.py -q
# 42 passed in 14.88s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_turn_transaction.py \
  tests/m1_teacher/test_e2e_resume_idempotency.py \
  tests/m1_teacher/test_session_engine.py -q
# 52 passed in 2.94s

"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
# All checks passed!
```

Baseline: PR2 (`998e6d2`) full suite was **595 passed**; PR3 adds 37 tests →
**632 passed**. No crash/concurrency regression (42/42 PR2 crash+concurrency
tests still pass). `ruff check .` still reports 39 pre-existing findings, all in
untouched `scripts/g3b`, `scripts/g3c`, `scripts/g4` and
`spikes/g3b-trusted-bridge` files; the touched tree (`m1_teacher`,
`tests/m1_teacher`) is clean.

### 5.2 New tests — `tests/m1_teacher/test_scoped_idempotency.py` (26)

| Test | Covers |
| --- | --- |
| `test_same_token_same_response_returns_first_result_and_writes_nothing` | I1, M1 |
| `test_scope_and_request_digest_are_persisted_in_events_and_index` | scope payload/index, M1 |
| `test_same_token_different_response_conflicts_and_never_returns_old_grade` | I2, M3, T-3/B3-02 |
| `test_new_token_on_consumed_turn_is_stable_conflict` | M10, T-3 family |
| `test_same_token_for_different_item_in_same_session_conflicts` | M4/M5, T-4 |
| `test_cross_learner_token_replay_is_rejected_without_foreign_result_leak` | I3, M7, T-1/B3-01 |
| `test_cross_session_same_learner_token_replay_conflicts` | M8, T-2 |
| `test_two_learners_with_distinct_tokens_stay_isolated` | isolation/B3-01 |
| `test_invalid_result_id_is_rejected_before_any_state_change` (7 tokens) | M15, T-8 |
| `test_valid_token_charset_is_accepted` | M15 positive |
| `test_caller_learner_mismatch_fails_closed_before_scoped_read` | Q3 |
| `test_missing_scoped_extension_fails_closed_for_explicit_tokens` | M18 |
| `test_prepared_attempt_retry_same_token_resumes_without_duplicate_mastery` | M2/M10, T-6 cross |
| `test_scope_conflict_rolls_back_events_and_session` | I4/I5, atomicity |
| `test_concurrent_same_token_same_response_converges` | M16/T-9 (real processes) |
| `test_eval_error_retry_is_scoped_and_zero_extra_events` | T-5 |
| `test_no_unscoped_result_lookup_in_engine_source` | T-14 (AST) |
| `test_idempotency_module_is_pure_and_offline` | purity |
| `test_concurrent_cross_learner_same_token_single_winner` | M17/T-10 (real processes) |

### 5.3 New tests — `tests/m1_teacher/test_scope_migration.py` (11)

| Test | Covers |
| --- | --- |
| `test_fresh_database_is_schema_v2_with_empty_scope_index` | schema v2 |
| `test_v1_database_migrates_additively_and_preserves_history` | T-12/M12: byte-identical history/session/snapshot/goal rows, backfill row fields |
| `test_v1_migration_is_idempotent_on_reopen` | T-12 |
| `test_v1_migration_skips_audit_error_events_without_result_payload` | backfill safety |
| `test_migrated_legacy_result_is_adoptable_with_digest_proof` | M12/T-11 |
| `test_unproven_legacy_result_is_rejected_by_default` | M14, T-11 |
| `test_unsupported_schema_version_fails_closed` (3 versions) | fail closed |
| `test_corrupt_legacy_event_rolls_back_the_whole_migration` | fail closed/rollback |
| `test_v2_database_self_heals_a_missing_additive_table` | self-heal |

The design draft’s test-file split (`test_multilearner_isolation.py`,
`test_result_scope_migration.py`, `test_concurrent_idempotency.py`,
`test_no_unscoped_result_lookup.py`) was consolidated into the Lead-specified
two new files; the test cases themselves are all present (mapping in §5.4).

### 5.4 B3-01 / B3-02 acceptance mapping

| Evidence-matrix item | Implemented coverage | Status |
| --- | --- | --- |
| **B3-01** Scoped result ID (NEGATIVE) | `test_cross_learner_token_replay_is_rejected_without_foreign_result_leak`, `test_cross_session_same_learner_token_replay_conflicts`, `test_same_token_for_different_item_in_same_session_conflicts`, `test_concurrent_cross_learner_same_token_single_winner` + repository `find_result_in_scope` identity re-check + AST scan. No API returns a foreign `AssessmentResult`; target learner events/snapshot unchanged; error details contain requester scope only. | implementer-run PASS; **matrix NOT_RUN** pending independent reviewer rerun |
| **B3-02** Same key different payload (NEGATIVE) | `test_same_token_different_response_conflicts_and_never_returns_old_grade`, `test_new_token_on_consumed_turn_is_stable_conflict`, `test_same_token_for_different_item_in_same_session_conflicts`, `test_eval_error_retry_is_scoped_and_zero_extra_events`; stable `IDEMPOTENCY_CONFLICT` code+reason, zero state writes, old grade never returned. | implementer-run PASS; **matrix NOT_RUN** pending independent reviewer rerun |
| B2-01/B2-02 cross (COLD-CRASH) | PR2 `test_crash_recovery.py` unchanged and green (42/42 with concurrency); scope row written atomically in A/B; prepared-window retry test. | no regression |
| B2-03 cross (CONCURRENCY) | PR2 `test_concurrency.py` green; two new real-process convergence tests (same scope M16; cross learner M17). | no regression |

---

## 6. Known limitations / explicit non-claims

1. **No authentication / multi-tenant security.** M1-A/M1-B have no auth layer;
   `caller_learner_id` is only a trusted-upper-layer assertion. A caller that
   already knows another learner's/session's ids can load that session (existing
   boundary). This PR guarantees data-access-layer scoping, **not** tenant
   isolation.
2. **At-least-once external scorer.** A crash between transaction A and B may
   invoke the scorer twice; persisted state is applied exactly once, but remote
   scoring side effects are not exactly-once.
3. **Strict cross-scope token policy (plan A).** The same `result_id` cannot be
   reused across learners/sessions/turns/items; a future product requirement for
   per-scope token reuse needs the deliberately deferred v2 event-id plan B.
4. **Legacy adoption is best-effort evidence.** Only provable 16-hex digest
   prefixes are accepted; unproven historical results stay rejected (no opt-in
   migration tool in this PR). Backfilled `origin='legacy'` rows are metadata,
   not re-validated grading data.
5. **Post-commit default-token replay.** A retry without an explicit
   `result_id` after the terminal commit still produces the existing
   no-pending `ConflictError` (same as PR2); explicit tokens are the idempotent
   retry mechanism.
6. **No real auth, no network/provider/Key, no M0/LiveGate changes**; M0
   capability status remains `UNVERIFIED`. All fixtures are synthetic/CC0.
7. **New event payload fields change new-run export/demo baselines**
   (`scope`, `request_digest`) — expected add-only change; frozen historical M1-A
   baselines and PR2’s recorded content hashes are **not** recomputed or
   rewritten (the PR2 crash-matrix doc’s hashes were produced on the PR2 branch
   before the additive payload fields existed).
8. **Single-writer product constraint** (PR2) is unchanged; concurrency tests
   prove serialisation/conflict semantics, not multi-writer throughput. The v2
   database is self-healed only for a missing additive table; arbitrary manual
   tampering beyond that is out of scope.
9. `TEST_EVIDENCE_MATRIX.csv` B3-01/B3-02 entries are **not** edited by the
   implementer; independent reviewer must re-run the commands in §5.1 and update
   the matrix.

---

## 7. Reviewer checklist

1. `git diff 998e6d2 -- m1_teacher tests/m1_teacher` shows only the files in §2
   (no M0/security/bridge/config/g*/scripts/LiveGate changes; `git status` clean
   except the reported files).
2. Run §5.1 commands; expect `632 passed` and touched-tree ruff clean.
3. Confirm no historical event rewrite: `history_events` rows are byte-identical
   across the v1→v2 migration (`test_v1_database_migrates_additively_and_preserves_history`).
4. Re-run the B3-01/B3-02 negative tests and inspect raw assertion output; then
   update `TEST_EVIDENCE_MATRIX.csv` from `NOT_RUN` to the reviewed result (the
   implementer deliberately leaves it unchanged).
