# M1-B B-PR3 — Scoped idempotency & multi-learner isolation: implementation report

- **Status**: implemented + independently reviewed (`PASS_WITH_ACTIONS`),
  review actions P1-1/P1-2/P2-1..P2-5 closed on branch
  `b-next/pr3-scoped-idempotency`. Based on PR2 HEAD `998e6d2`; design branch
  merged as `4a10eb0` (`docs/M1_B_SCOPED_IDEMPOTENCY.md`); PR2 final merged as
  `25185b1` (PR2 `10fdaa9`); independent review merged as `db636ea`
  (`docs/M1_B_PR3_REVIEW.md`).
- **Owner**: B-NEXT implementer (`b-core` / M1-B), directed by the Lead.
- **Review action resolution**: see §8. The prior implementer-run counts
  `632/595` in this document are **historical** (pre-PR1/P2 merge); the final
  tree evidence in §5 is authoritative.
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
`request_digest = sha256(canonical_response(response))`. All *engine* result
reads go through a scoped repository API that returns an `AssessmentResult`
**only** for an exact v1 scope match; `LearningHistory.apply_assessment`'s
duplicate check is learner/session-scoped as well (review P1-2), and legacy
(pre-scope) evidence is only adopted by an explicit adapter that requires
learner+session+item+turn match **and** a provable response-digest prefix,
computed with the pre-PR3 JSON projection (review P1-1). New writes persist the
scope in the event payloads (add-only) and in a new additive `result_scopes`
index table (schema v2). `history_events` rows are never updated, deleted or
rewritten.

`event_id` keeps its historical shape (`evt.assessed.<result_id>` etc.) as the
global uniqueness guard; the “one token, many scopes” v2 event-id plan (design
plan B) is deliberately **not** implemented.

---

## 2. Files changed

| File | Change |
| --- | --- |
| `m1_teacher/idempotency.py` | **new** pure module: `ResultScope`, `ScopeMetadata`, canonical response/request digest (new compact projection **and** `legacy_canonical_response`/`legacy_request_digest` for pre-PR3 default-separator evidence — review P1-1), deterministic default `result_id`, result-id validation, scope payload helpers, conflict reasons, legacy digest comparison. |
| `m1_teacher/contracts/errors.py` | add-only codes `IDEMPOTENCY_CONFLICT`, `INVALID_RESULT_ID`, `IDEMPOTENCY_UNSUPPORTED` (module constants; existing exception classes/codes unchanged). |
| `m1_teacher/learner/repository.py` | schema v2 (`SCHEMA_VERSION = 2`) + additive `result_scopes` DDL with table-level `CHECK (origin = 'legacy' OR turn_index >= 0)` (review P2-5); v1→v2 migration with legacy backfill; `supports_scoped_idempotency()`; `find_result_in_scope()`, `find_scope_owner()` (metadata only), `get_event_for_learner()`; `commit_teaching_turn(..., scope=...)` writes/advances the scope row **inside the same transaction**. |
| `m1_teacher/learner/history.py` | `assessment_event_drafts(..., scope=None)` embeds the add-only `scope` object; `apply_assessment` duplicate detection is learner/session/item-scoped (`get_event_for_learner` + metadata-only `find_scope_owner`) and raises stable `IDEMPOTENCY_CONFLICT` for foreign scopes / engine-managed PREPARED attempts (review P1-2). |
| `m1_teacher/session/engine.py` | scoped fast-path before pending/turn **and** before PAUSED/COMPLETE gates (review P2-2); explicit token validation; stable `IDEMPOTENCY_CONFLICT` reasons; optional `caller_learner_id` fail-closed assertion; scoped/legacy result adapter with legacy-projection digests and event-log fallback turn check (review P1-1/P2-4); scope carried through transaction A (payload) and B (index row); duplicate/CAS catch re-reads **only** through the exact scoped key. |
| `tests/m1_teacher/test_scoped_idempotency.py` | **new** 31 tests (see §5.2; includes review P1-2/P2-1/P2-2 coverage). |
| `tests/m1_teacher/test_scope_migration.py` | **new** 15 tests (see §5.3; includes review P1-1/P2-4/P2-5 coverage). |
| `fixtures/m1_teacher/migration/pr3_v1_structured_legacy.sqlite` (+ `.manifest.json`, `README.md`) | **new** genuine pre-PR3 v1 database generated by the base `4706250` engine with structured (dict) responses, used to prove legacy-projection compatibility (review P1-1). |
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
8. **Two JSON projections (review P1-1)**: new writes use compact JSON
   (`canonical_response`), while legacy digest/default-id verification uses the
   pre-PR3 default-separator projection (`legacy_canonical_response` /
   `legacy_request_digest`). Mixing them silently misclassified provable legacy
   structured responses as `REQUEST_DIGEST_MISMATCH`; the two functions are kept
   explicit and documented instead of one "compatible" function.
9. **`LearningHistory.apply_assessment` scoped duplicate detection (review
   P1-2)**: the old global `get_event(assessed_event_id(...))` was replaced by a
   learner-filtered lookup plus metadata-only `find_scope_owner` checks. This is
   not an engine-path change but is required for public-API completeness; a
   foreign learner/session/item or engine-managed PREPARED attempt now raises
   stable `IDEMPOTENCY_CONFLICT` instead of silently dropping the assessment.
10. **Phase-gate ordering (review P2-2)**: the same-scope TERMINAL fast lookup
    now runs **before** `PAUSED`/`COMPLETE` checks, so a lost-response retry of a
    submission that completed or paused the session returns the stored result
    (zero writes); non-scope calls are still rejected by the phase gates.
11. **Convergent-retry semantics (review P2-1)**: same-scope/same-payload
    concurrent submissions are documented and tested as *convergent retry*
    (both callers observe the identical result; exactly one terminal/mastery),
    not as an explicit conflict. Different payloads/cross-scope reuse remain
    explicit conflicts.
12. **Legacy event-log fallback turn check (review P2-4)**: the fallback used
    when the additive index row is missing now enforces the same
    `-1`/current/just-consumed turn rule as the indexed legacy row adapter.
13. **Schema defense (review P2-5)**: `result_scopes` now has table-level
    `CHECK (origin = 'legacy' OR turn_index >= 0)` plus the same application-level
    validation on read (covers older v2 tables created before the CHECK).

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

**Legacy projection (review P1-1):** the pre-PR3 engine used
`json.dumps(..., ensure_ascii=False, sort_keys=True, allow_nan=False)` without
`separators` (default `", "` / `": "` spacing). The module therefore exposes:

```text
legacy_canonical_response(response)   # pre-PR3 projection (dict/list only differ)
legacy_request_digest(response)       # sha256(legacy_canonical_response(...))
```

New writes are never verified with the legacy projection and old evidence is
never verified with the compact one. For a structured fixture response
`{"answer": "A", "why": "because"}` the old prefix is `622f5b364e154174` while
the new compact prefix differs — the genuine v1 fixture test covers this exact
case.

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
    updated_at TEXT NOT NULL,
    CHECK (origin = 'legacy' OR turn_index >= 0)
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

**Genuine old-engine fixture (review P1-1):**
`fixtures/m1_teacher/migration/pr3_v1_structured_legacy.sqlite` was written by
the base `4706250` engine (before any PR3 code existed) with structured
`dict` responses and schema version 1; the test copies it to a temp directory,
opens it (triggering the real v1→v2 migration) and replays the same token. This
avoids the previous self-referential fixture that was generated by the *new*
engine and downgraded in-test (which could not detect the projection bug).

---

## 4. Engine behaviour

`TeachingSessionEngine.submit_response(session_id, item_id, response, *,
result_id=None, caller_learner_id=None)`:

1. optional `caller_learner_id` (trusted outer-layer assertion; M1 has no real
   auth) must equal the session owner, otherwise fail closed **before** any
   result read or write (`CONFLICT`/`CALLER_LEARNER_MISMATCH`).
2. explicit `result_id` is validated (`INVALID_RESULT_ID`) and the exact scoped
   lookup runs before pending/turn validation **and before the PAUSED/COMPLETE
   phase gates** (review P2-2), so a lost-response retry after the session
   completed/paused still returns the stored result. Same scope+digest terminal →
   first result returned, zero events, scorer not called. Different
   digest/item/session/learner → `IDEMPOTENCY_CONFLICT` with a stable reason;
   state unchanged. A new token on an already-consumed turn →
   `TURN_ALREADY_ASSESSED` (no content-based implicit de-duplication).
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
   turn (both the indexed-row adapter and the event-log fallback enforce this —
   review P2-4), and the stored 16-hex response-digest prefix must match the
   current request **under the pre-PR3 JSON projection** (review P1-1);
   otherwise `LEGACY_SCOPE_MISMATCH` / `REQUEST_DIGEST_MISMATCH` /
   `DIGEST_UNPROVEN`/`TURN_MISMATCH`. If the repository lacks the scoped API,
   explicit token replay fails closed with `IDEMPOTENCY_UNSUPPORTED` (no global
   fallback).
7. `LearningHistory.apply_assessment` (public non-engine API) performs a
   learner/session/item-scoped duplicate check and raises
   `IDEMPOTENCY_CONFLICT` for foreign scopes or engine-managed PREPARED attempts
   (review P1-2); same-scope replay remains idempotent.

`recover_session()`/`recover_pending_turns()` keep PR2 semantics; they now
carry the decoded scope through re-scoring and the terminal commit so recovery
also writes/advances the index row.

---

## 5. Test evidence (implementer run, raw output)

### 5.1 Commands and results (final tree, review actions applied)

```bash
cd /root/m1b/pr3
# Final tree = PR1 + PR2 final + PR3 + independent review doc + review actions.
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
# 783 passed in 71.07s   (clean host: no concurrent unrelated suites)

"/root/Autonomous Teacher/.venv/bin/python" -m pytest   tests/m1_teacher/test_scoped_idempotency.py -q
# 31 passed in 2.06s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest   tests/m1_teacher/test_scope_migration.py -q
# 15 passed in 0.86s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest   tests/m1_teacher/test_crash_recovery.py -q
# 35 passed in 14.50s

"/root/Autonomous Teacher/.venv/bin/python" -m pytest   tests/m1_teacher/test_concurrency.py -q
# 9 passed in 2.67s

"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
# All checks passed!

# Require the real OS sandbox for judge tests; on this host nothing is skipped.
M1B_REQUIRE_OS_SANDBOX=1 "/root/Autonomous Teacher/.venv/bin/python" \
  -m pytest tests/m1_teacher -q
# 783 passed in 70.14s   (0 skipped)
```

**Count history (not to be confused with the final tree):**

| Milestone | Full `tests/m1_teacher` count |
| --- | --- |
| Pre-PR1/PR2 merge (PR3 implementation branch `3103a06`) | 632 passed (of which PR2 base `998e6d2` = 595, PR3 = +37) |
| PR2 final merged (`25185b1`, PR1 judge + PR2 fixes) | 774 passed |
| Independent review merged (`db636ea`) + review actions (this tree) | **783 passed** |

No crash/concurrency regression: 35 crash + 9 concurrency PR2/PR1 tests pass; the
review-action changes (P2-2) only strengthened the post-completion retry
assertions (same result + zero writes instead of a phase conflict).

> **Host-concurrency note (environmental, PR1 scope).** PR1 judge-negative /
> hidden-leakage tests scan shared `/tmp` paths, so unrelated `pytest
> tests/m1_teacher` suites running in parallel on the same host can make them
> fail spuriously (the independent review documented the same in its §9.6).
> During this turn two such environmental failures were observed while other
> agents ran suites concurrently; the final §5.1 run above was captured on an
> idle host, and every affected test passes in isolation
> (`test_judge_correctness.py` 27 passed; `test_crash_recovery.py` 35 passed).
> No PR3 test was skipped/xfailed or changed to hide the issue. `ruff check .`
still reports 39 pre-existing findings, all in untouched `scripts/g3b`,
`scripts/g3c`, `scripts/g4` and `spikes/g3b-trusted-bridge`; the touched tree
(`m1_teacher`, `tests/m1_teacher`) is clean.

### 5.2 New tests — `tests/m1_teacher/test_scoped_idempotency.py` (31)

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
| `test_concurrent_same_scope_same_response_converges_to_one_result` | M16/T-9 convergent retry (P2-1, real processes) |
| `test_eval_error_retry_is_scoped_and_zero_extra_events` | T-5 |
| `test_no_unscoped_result_lookup_in_engine_source` | T-14 (AST) |
| `test_idempotency_module_is_pure_and_offline` | purity |
| `test_concurrent_cross_learner_same_token_single_winner` | M17/T-10 (real processes) |
| `test_apply_assessment_cross_learner_token_is_explicit_conflict` | P1-2 |
| `test_apply_assessment_same_scope_replay_stays_idempotent` | P1-2 |
| `test_apply_assessment_same_token_other_session_conflicts` | P1-2 |
| `test_same_token_retry_after_complete_returns_stored_result` | P2-2 |
| `test_same_token_retry_after_paused_returns_stored_result` | P2-2 |

### 5.3 New tests — `tests/m1_teacher/test_scope_migration.py` (15)

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
| `test_real_pre_pr3_structured_legacy_replays_with_old_projection` | P1-1 (genuine 4706250 v1 DB + dict replay/conflict/foreign) |
| `test_pre_pr3_structured_default_id_uses_old_projection` | P1-1 old default id |
| `test_legacy_event_fallback_enforces_turn_rule` | P2-4 |
| `test_schema_rejects_v1_rows_with_unknown_turn` | P2-5 |

The design draft’s test-file split (`test_multilearner_isolation.py`,
`test_result_scope_migration.py`, `test_concurrent_idempotency.py`,
`test_no_unscoped_result_lookup.py`) was consolidated into the Lead-specified
two new files; the test cases themselves are all present (mapping in §5.4).

### 5.4 B3-01 / B3-02 acceptance mapping

| Evidence-matrix item | Implemented coverage | Status |
| --- | --- | --- |
| **B3-01** Scoped result ID (NEGATIVE) | `test_cross_learner_token_replay_is_rejected_without_foreign_result_leak`, `test_cross_session_same_learner_token_replay_conflicts`, `test_same_token_for_different_item_in_same_session_conflicts`, `test_concurrent_cross_learner_same_token_single_winner` + repository `find_result_in_scope` identity re-check + AST scan. No API returns a foreign `AssessmentResult`; target learner events/snapshot unchanged; error details contain requester scope only. | implementer-run PASS; **matrix NOT_RUN** pending independent reviewer rerun |
| **B3-02** Same key different payload (NEGATIVE) | `test_same_token_different_response_conflicts_and_never_returns_old_grade`, `test_new_token_on_consumed_turn_is_stable_conflict`, `test_same_token_for_different_item_in_same_session_conflicts`, `test_eval_error_retry_is_scoped_and_zero_extra_events`; stable `IDEMPOTENCY_CONFLICT` code+reason, zero state writes, old grade never returned. | implementer-run PASS; **matrix NOT_RUN** pending independent reviewer rerun |
| B2-01/B2-02 cross (COLD-CRASH) | PR2/PR1 `test_crash_recovery.py` green (35 passed); scope row written atomically in A/B; prepared-window retry test. | no regression |
| B2-03 cross (CONCURRENCY) | PR2 `test_concurrency.py` green (9 passed); two new real-process convergence tests (same scope M16 convergent retry; cross learner M17). | no regression |

---

## 5.5 Independent review action closure (`db636ea`, P1=2 / P2=5)

| # | Action | Code change | Test evidence | Status |
| --- | --- | --- | --- | --- |
| P1-1 | legacy digest projection incompatible for structured responses | `legacy_canonical_response`/`legacy_request_digest` (pre-PR3 default separators); legacy row/event/default-id comparisons use them; genuine base `4706250` v1 fixture | `test_real_pre_pr3_structured_legacy_replays_with_old_projection` (same dict → old result, zero events, scorer 0 calls; different dict → `REQUEST_DIGEST_MISMATCH`; foreign learner → `LEGACY_SCOPE_MISMATCH`), `test_pre_pr3_structured_default_id_uses_old_projection` | CLOSED |
| P1-2 | `LearningHistory.apply_assessment` global duplicate lookup | learner-filtered `get_event_for_learner` + metadata-only `find_scope_owner`; foreign learner/session/item or PREPARED attempt → stable `IDEMPOTENCY_CONFLICT` | `test_apply_assessment_cross_learner_token_is_explicit_conflict` (B conflict, not silent drop; A/B states untouched), `test_apply_assessment_same_scope_replay_stays_idempotent`, `test_apply_assessment_same_token_other_session_conflicts` | CLOSED |
| P2-1 | concurrent same-scope semantics wording | report/design clarify convergent retry = acceptance semantics; test renamed/strengthened to assert both callers get identical result | `test_concurrent_same_scope_same_response_converges_to_one_result` | CLOSED |
| P2-2 | PAUSED/COMPLETE gate before scoped fast path | fast TERMINAL lookup moved before phase gates in both engine paths | `test_same_token_retry_after_complete_returns_stored_result`, `test_same_token_retry_after_paused_returns_stored_result`; PR2 goal-completion crash helper updated to assert idempotent replay | CLOSED |
| P2-3 | stale report counts | this §5.1 updated to final 783 with 632/595/774 marked historical | this document | CLOSED |
| P2-4 | `_legacy_event_lookup` turn not checked | attempt turn recovered from `ASSESSMENT_PREPARED`/`RESPONSE_SUBMITTED`; same `-1`/current/previous rule as indexed adapter | `test_legacy_event_fallback_enforces_turn_rule` | CLOSED |
| P2-5 | v1 row may have `turn_index=-1` | table-level `CHECK (origin = 'legacy' OR turn_index >= 0)` + read-time validation | `test_schema_rejects_v1_rows_with_unknown_turn` | CLOSED |

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
   prefixes are accepted (now with the pre-PR3 JSON projection for structured
   responses, review P1-1); unproven historical results stay rejected (no opt-in
   migration tool in this PR). Backfilled `origin='legacy'` rows are metadata,
   not re-validated grading data.
5. **Post-commit default-token replay.** A retry without an explicit
   `result_id` after the terminal commit still produces the existing
   no-pending/phase `ConflictError` (same as PR2); explicit tokens are the
   idempotent retry mechanism and now also replay after PAUSED/COMPLETE
   (review P2-2). A **new** token on a consumed turn remains a stable
   `TURN_ALREADY_ASSESSED` conflict.
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
10. **Protocol-only repositories (no scoped API)** still fall back to the
    historical global event-existence check in `LearningHistory.apply_assessment`;
    a foreign-owner collision still conflicts, but there is no turn/digest
    binding for that degraded path. The production SQLite repository always has
    the scoped API.
11. **Older v2 files** created between the first PR3 commit and review P2-5 may
    have the previous, weaker `turn_index >= -1` CHECK; SQLite cannot alter a
    CHECK in place, so read-time validation (`_scope_metadata`) additionally
    rejects v1 `turn_index=-1` rows. Newly created/migrated databases have the
    tightened table-level CHECK.
12. **Concurrent same-scope semantics are convergent-retry**, not an explicit
    conflict: both callers may observe success with the identical stored result.
    Different payloads or cross-scope reuse are the explicit-conflict cases
    (review P2-1, documented in design §6/M16).

---

## 7. Reviewer checklist (post-review actions)

1. Confirm this branch contains the independent review document
   (`docs/M1_B_PR3_REVIEW.md`, commit `db636ea`) plus the action commits; no
   existing commit was amended and no test was weakened.
2. `git diff --name-only 4706250..HEAD` must contain only B-line paths; the
   protected-path scan (M0/security/bridge/config/g*/scripts/LiveGate) must be
   empty.
3. Run §5.1 commands; expect **783 passed** (`M1B_REQUIRE_OS_SANDBOX=1` also
   783 passed / 0 skipped on this host), touched-tree ruff clean.
4. Confirm no historical event rewrite: `history_events` rows are byte-identical
   across the v1→v2 migration
   (`test_v1_database_migrates_additively_and_preserves_history`), and the
   genuine `4706250` v1 fixture replays correctly
   (`test_real_pre_pr3_structured_legacy_replays_with_old_projection`).
5. Re-run the P1-1/P1-2 and B3-01/B3-02 negative tests and inspect raw assertion
   output; then update `TEST_EVIDENCE_MATRIX.csv` from `NOT_RUN` to the reviewed
   result (the implementer deliberately leaves it unchanged).
