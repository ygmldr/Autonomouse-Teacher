# M1-B B-PR2 — Session + History transactionality and crash recovery

- **Status**: implemented + crash-tested on branch `b-next/pr2-session-txn`,
  based on `work/m1a-mvp` = `4706250` (M1-A B-PR5 reviewed HEAD).
- **Owner**: B-PR2 Implementer-Storage (`m1a-learner` → B-NEXT storage role).
- **Scope**: offline, no network, no API keys/providers, synthetic fixtures only.
- **Evidence class**: `DETERMINISTIC` for the transaction/replay assertions,
  `MOCK` for the synthetic student/scorer fixtures. There is **no** claim of
  real learning effectiveness or of exactly-once execution of a remote scorer.

This document is the audit artifact for B-02 (“Session is not a cross-state
atomic commit”), B-Q2 (session crash matrix), B2-01 (atomic turn commit),
B2-02 (crash replay) and B2-03 (concurrency semantics).

---

## 1. Problem statement (frozen audit finding)

Before B-PR2 `TeachingSessionEngine.submit_response()` wrote, in separate
auto-commit transactions:

1. `RESPONSE_SUBMITTED`
2. `ASSESSED` + `MASTERY_UPDATED` (`LearningHistory.apply_assessment`)
3. learner snapshot upsert
4. session `pending_item_id`/`turn_index` (`save_session`)

A crash at any boundary could persist “scored, mastery applied, session still
pending”. A retry then hit `_find_existing_result()` and returned the old result,
so the stale pending/session state could never be repaired, and a concurrent
writer could silently overwrite newer evidence (`last-write-wins`).

Also, the external scorer call (with potential side effects / latency) happened
before the `RESPONSE_SUBMITTED` event, so a crash during scoring lost the whole
attempt (no durable recovery intent).

---

## 2. Persisted write points after B-PR2

| # | Write point | Transaction | Contents | Failure consequence |
|---|---|---|---|---|
| W1 | transaction **A** (`RESPONSE_SUBMITTED` + `ASSESSMENT_PREPARED`) | one `BEGIN IMMEDIATE` | durable attempt: learner/session/item/turn, `result_id`, response digest, response kind, **canonical response** for deterministic re-scoring, session CAS version | rollback → nothing persisted, retry starts clean; commit → attempt is recoverable |
| W2 | external scorer call | **no DB transaction** | in-memory `AssessmentResult` | crash → attempt stays PREPARED, `recover_session()` re-scores it |
| W3 | transaction **B** (`commit_teaching_turn`) | one `BEGIN IMMEDIATE` | terminal `ASSESSED`/`MASTERY_UPDATED` (or `ERROR` for `EVAL_ERROR`), optional `GOAL_COMPLETED` + goal row, learner snapshot, next session state | rollback → (W1 state) recoverable; commit → turn complete exactly once |
| W4 | crash-recovery audit `ERROR` events | single atomic append | explainable `RECOVERY_*` reason, session/mastery unchanged | retried recovery is a zero-event no-op |

Legacy write points outside `submit_response` (`start_session`,
`_generate_and_persist`, `pause/resume`) are unchanged for the M1-A-facing
behaviour; they do not apply mastery and are not in the B-02 blast radius.

### 2.1 Atomic commit API

`SqliteRepository.commit_teaching_turn(*, learner_id, session_id,
expected_session_version, events, snapshot=None, next_session, goal=None)
-> list[bool]`

Single `BEGIN IMMEDIATE` / `COMMIT`, in this order:

1. re-validate every argument with the fail-closed `_validated_*` helpers;
2. **session CAS**: stored `session_version(current) == expected_session_version`
   else `ConflictError(code="SESSION_VERSION_CONFLICT")`;
3. validate the transition (identity fields unchanged, `turn_index` monotonic,
   `PREPARED` and terminal events cannot share a commit, terminal commits
   advance exactly one turn, `COMPLETE` cannot keep a pending item);
4. insert events (`duplicate event_id` → `ConflictError(code="DUPLICATE_EVENT")`,
   `(learner_id, seq)` collision → `ConflictError(code="EVENT_SEQ_CONFLICT")`);
5. strictly-advancing snapshot upsert (stale revision →
   `ConflictError(code="SNAPSHOT_REVISION_CONFLICT")`);
6. optional goal upsert;
7. write `next_session`;
8. invariant check: if the new session has **no** pending item, every persisted
   `ASSESSMENT_PREPARED` attempt for that session must have a terminal
   `ASSESSED`/`ERROR` event (`ValidationError(code="INCONSISTENT_PENDING")`);
9. `COMMIT`; any exception rolls the complete transaction back.

`session_version(state) = sha256(canonical_json(state.to_dict()))[:16]` with
sorted compact keys.  The frozen `SessionState` contract is **not** changed (no
new field); the version is a pure content digest, so any persisted change
(`pending_item_id`, `turn_index`, `phase`, `updated_at`) changes it.

Transaction A re-uses the same API: it writes `RESPONSE_SUBMITTED` +
`ASSESSMENT_PREPARED` and a session row whose only change is a strictly
increasing `updated_at`, so the CAS digest always changes even when two writes
happen within the same wall-clock second.

### 2.2 Submitted pipeline

```
submit_response()
  └─ transaction A (CAS): RESPONSE_SUBMITTED + ASSESSMENT_PREPARED   [W1]
  └─ external scorer (outside DB transaction)                        [W2]
  └─ transaction B (CAS): ASSESSED + MASTERY_UPDATED (+GOAL_COMPLETED)
                          + snapshot + next session                  [W3]
```

Transaction A is retried idempotently (deterministic event ids derived from
`attempt_id = attempt:<session>:<turn>:<item>`); transaction B is retried
internally up to 3 times on `EVENT_SEQ_CONFLICT` only.  A CAS failure in B
re-checks the deterministic terminal event ids: if another writer already
committed the same request, the stored result is returned with **zero** new
events; otherwise the conflict is surfaced.

---

## 3. Invariants (enforced in code, asserted by tests)

| ID | Invariant | Enforced by | Tests |
|---|---|---|---|
| INV-1 | A terminal assessment event and the session `pending_item_id`/`turn_index` transition commit together | `commit_teaching_turn` single transaction; transition validation | `test_turn_transaction.py::test_commit_*`, `test_crash_recovery.py::test_crash_during_transaction_b*` |
| INV-2 | Mastery evidence is applied **exactly once per `result_id`** (event ids deterministic, duplicate `event_id` fails closed) | `DUPLICATE_EVENT`, `_terminal_result` retry lookup, snapshot strict-advance | `test_submit_same_result_id_same_response_is_idempotent`, concurrency same-request test |
| INV-3 | `event.seq` is unique and strictly ascending per learner | DB `UNIQUE(learner_id, seq)`, request validation, `EVENT_SEQ_CONFLICT` retry | every crash/concurrency test asserts `seqs == sorted(set(seqs))` |
| INV-4 | No session without a pending item may hold an unresolved `ASSESSMENT_PREPARED` attempt | atomic `INCONSISTENT_PENDING` check | `test_commit_rejects_invalid_transitions_and_orphan_prepared` |
| INV-5 | `turn_index` never decreases; terminal commits advance exactly +1 | transition validation | `test_commit_rejects_invalid_transitions_and_orphan_prepared` |
| INV-6 | The persisted snapshot always equals the snapshot rebuilt from the event log (`verify_rebuild`) after any crash/recovery state | atomic snapshot+event commit; recovery | every crash test asserts `verify_rebuild is True` |
| INV-7 | `EVAL_ERROR` never counts as learner evidence (no mastery change, explicit `ERROR` event) | `_plan_result_transition` | existing M1-A EVAL_ERROR tests + `test_crash_*` |
| INV-8 | No cross-learner/cross-session event or snapshot pollution | scoped lookups, event learner/session validation | `test_concurrent_two_learners_do_not_pollute_each_other` |
| INV-9 | Every crash state is explainable and either recoverable or a no-op | crash matrix (below) | `test_crash_states_collapse_to_three_explainable_logical_states` |

---

## 4. Crash failpoints (real `SIGKILL`, test-only)

`M1B_CRASH_FAILPOINT` is read by the repository commit path. It is **off by
default** (a dictionary lookup returning immediately) and never changes normal
semantics. Point names may be prefixed with `prepare:` (transaction A) or
`commit:` (transaction B); an unprefixed name matches both.

`after_begin`, `after_session_check`, `before_event_insert_<n>`,
`after_event_insert_<n>`, `before_snapshot`, `after_snapshot`, `before_goal`,
`after_goal`, `before_session`, `after_session`, `before_commit`,
`after_commit`.

Crash evidence is produced by `tests/m1_teacher/txn_child.py` (a separate OS
process) with `os.kill(os.getpid(), SIGKILL)`; the parent pytest process then
opens the same SQLite file as a **new** process.  Crash in the scoring window
uses a child scorer that `SIGKILL`s itself (`--kill-in-scorer`), never a mocked
Python exception.

---

## 5. Crash matrix (B-Q2) — actual results

Command (matrix JSONL is advisory evidence; assertions are in the tests):

```
cd /root/m1b/pr2 && M1B_MATRIX_OUT=/tmp/m1b_matrix.jsonl \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_crash_recovery.py -q
```

Observed: `33 passed in 14.10s` (last full run; see §9 for the suite command).

Every kill point collapses to one of **three** persisted logical states, each
with one reproducible content hash (wall-clock fields and the CAS session digest
are excluded from the hash):

| Logical state | Persisted shape | event count | hash | Cases observed |
|---|---|---|---|---|
| **rolled_back** (A never committed) | pending `item.bs.mcq.001`, turn 0, no PREPARED, no terminal, no snapshot | 4 | `77c62048e9c34a12` | 9 A-pre-commit points |
| **prepared** (A committed, B not) | same pending/turn, 1 unresolved `ASSESSMENT_PREPARED`, no terminal, no snapshot | 6 | `ec99d57baf55a6e6` | A `after_commit`; scoring-window kill; 11 B-pre-commit points; 8 recovery-pre-commit points |
| **committed** (B committed) | pending `None`, turn 1, terminal `ASSESSED`, snapshot revision 1, mastery `cf.array.basics=0.2` | 8 | `bbd500fbb1ca734b` | B `after_commit`; recovery `after_commit` |

Representative persisted DB summary per state (observed, `M1B_MATRIX_OUT`):

```json
{"state": "rolled_back", "case": "A-prepare:after_begin", "pending_item_id": "item.bs.mcq.001", "turn_index": 0, "phase": "DIAGNOSE", "prepared_total": 0, "prepared_unresolved": 0, "terminal_results": 0, "event_count": 4, "event_types": {"ACTION_TAKEN":1,"DIAGNOSIS_COMPLETED":1,"PLAN_CREATED":1,"SESSION_STARTED":1}, "snapshot_revision": null, "masteries": {}, "content_hash": "77c62048e9c34a12"}
{"state": "prepared", "case": "A-prepare:after_commit", "pending_item_id": "item.bs.mcq.001", "turn_index": 0, "phase": "DIAGNOSE", "prepared_total": 1, "prepared_unresolved": 1, "terminal_results": 0, "event_count": 6, "event_types": {"ACTION_TAKEN":1,"ASSESSMENT_PREPARED":1,"DIAGNOSIS_COMPLETED":1,"PLAN_CREATED":1,"RESPONSE_SUBMITTED":1,"SESSION_STARTED":1}, "snapshot_revision": null, "masteries": {}, "content_hash": "ec99d57baf55a6e6"}
{"state": "committed", "case": "C-commit:after_commit", "pending_item_id": null, "turn_index": 1, "phase": "REVIEW", "prepared_total": 1, "prepared_unresolved": 0, "terminal_results": 1, "event_count": 8, "event_types": {"ACTION_TAKEN":1,"ASSESSED":1,"ASSESSMENT_PREPARED":1,"DIAGNOSIS_COMPLETED":1,"MASTERY_UPDATED":1,"PLAN_CREATED":1,"RESPONSE_SUBMITTED":1,"SESSION_STARTED":1}, "snapshot_revision": 1, "masteries": {"cf.array.basics": 0.2}, "content_hash": "bbd500fbb1ca734b"}
```

Per-case crash/recovery matrix (33 tests; each row is a real child-process
`SIGKILL` unless marked otherwise):

| Case group | Failpoints tested | Post-crash state | Recovery |
|---|---|---|---|
| transaction A, pre-commit | `after_begin`, `after_session_check`, `before/after_event_insert_1`, `before/after_event_insert_2`, `before/after_session`, `before_commit` | rolled_back | `recover_session` → `ALREADY_CONSISTENT` (0 events), then a normal retry commits |
| transaction A, `after_commit` | `after_commit` | prepared | `RECOVERED` (+2 events) |
| scoring window B | child scorer `SIGKILL` | prepared | `RECOVERED` |
| transaction B, pre-commit | `after_begin`, `after_session_check`, `before/after_event_insert_1`, `before/after_event_insert_2`, `before/after_snapshot`, `before/after_session`, `before_commit` | prepared | `RECOVERED` |
| transaction B, `after_commit` | `after_commit` | committed | `ALREADY_CONSISTENT` (0 events) |
| recovery crashed, pre-commit | 8 `commit:*` points during recovery | prepared | second `recover_session` → `RECOVERED`; third → `ALREADY_CONSISTENT` |
| recovery crashed, `after_commit` | `commit:after_commit` | committed | `ALREADY_CONSISTENT` |

Every case additionally asserts: exactly one terminal event in the committed
state, `turn_index == setup+1`, `pending_item_id is None`, snapshot revision 1,
`verify_rebuild == True`, no duplicate mastery application, unique/ascending
`seq`, only the expected learner/session rows, and an idempotent retry with the
persisted `result_id` appending zero events.  Crash-then-recover converges to
the **identical content hash** as an uninterrupted commit
(`test_crash_states_collapse_to_three_explainable_logical_states`).

---

## 6. Recovery algorithm

`TeachingSessionEngine.recover_session(session_id)` /
`recover_pending_turns(learner_id)`:

1. load the session and collect `ASSESSMENT_PREPARED` events without a terminal
   `ASSESSED`/`ERROR` event (deterministic `result_id` matching);
2. verify the persisted `pending_item_id`/`turn_index` still match the prepared
   attempt; otherwise append one deterministic `ERROR` event with
   `stage="RECOVERY"`, `status="RECOVERY_STATE_INCONSISTENT"`, keep the session
   unchanged and report `FAILED` (never fabricate completion);
3. re-score the persisted canonical response with the injected scorer
   **outside any transaction**, requiring the same deterministic
   `result_id`/item/learner identity; scorer exception → `RECOVERY_SCORER_ERROR`,
   identity mismatch → `RECOVERY_SCORER_MISMATCH` (audit `ERROR` event, session
   stays pending);
4. commit the terminal events/snapshot/next session through the same atomic
   `commit_teaching_turn` (with seq-conflict retry);
5. repeated calls are idempotent: terminal attempts are found first, so a second
   call returns `status="ALREADY_CONSISTENT"` with 0 appended events.

`RecoveryReport` returns `session_id, learner_id, status
(ALREADY_CONSISTENT|RECOVERED|PARTIAL|FAILED), prepared_attempts,
recovered_attempts, pending_attempt_ids, error_codes, events_appended`.
A repository without the transactional extension makes the recovery API fail
closed with `UnsupportedOperationError(code="RECOVERY_UNSUPPORTED")`.

---

## 7. Exactly-once vs at-least-once (explicit boundary)

* **State application is exactly-once** per `result_id`: the `ASSESSED` /
  `ERROR` terminal event ids are deterministic; a duplicate commit fails closed
  (`DUPLICATE_EVENT`) and retries return the stored result with zero events.
  Mastery/snapshot/`turn_index` advance at most once per attempt.
* **External scorer invocation is at-least-once**: a crash between A and B (or
  in recovery) re-invokes the injected scorer.  The scorer contract is
  deterministic for synthetic offline assessment
  (`pure function of item, learner, response, result_id`); a non-deterministic
  scorer that returns a different `result_id`/identity makes recovery fail
  closed (`RECOVERY_SCORER_MISMATCH`) instead of applying a second state change.
* **No remote/network exactly-once promise** is made.  If a future scorer has
  remote side effects (paid API, external submission), that component must be
  independently idempotent/deduplicated; this PR does not claim it.

---

## 8. Concurrency semantics and the single-writer constraint

Command: `pytest tests/m1_teacher/test_concurrency.py -q` → `9 passed in 2.91s`
(real processes, file barrier).

* **Same session, two different responses**: exactly one turn is applied; the
  loser receives an explicit `IDEMPOTENCY_CONFLICT` / `SESSION_VERSION_CONFLICT`
  / pending conflict; never a silent last-write-wins.
* **Same session, same request id**: both processes may return the same stored
  result; state is applied exactly once (single `ASSESSED`, single mastery
  update), demonstrating at-least-once scorer / exactly-once state.
* **Same learner, two sessions**: commits serialise via `BEGIN IMMEDIATE` and
  seq-conflict retry, or the loser fails closed with
  `SNAPSHOT_REVISION_CONFLICT` (strict snapshot advance prevents one session
  overwriting the other session’s newer evidence).  The failed session keeps its
  prepared attempt and is completed by `recover_session`; the final snapshot is
  revision 2 with both updates and `verify_rebuild == True`.
* **Cross learner**: concurrent learners in one file stay isolated (events,
  snapshots and result ids).
* **Cold start**: a new process opens the existing SQLite file, continues the
  session and idempotently replays a stored result id.
* **Busy/locked DB**: the configured `busy_timeout_ms` bounds the wait; on
  timeout the write fails closed with `ConflictError(code="DB_BUSY")` and the
  same submission succeeds after the lock is released.
* **Corrupt/old/unsupported state**: unsupported `schema_meta.version`,
  corrupted snapshot/prepared-event JSON and tampered pending state all fail
  closed (`ValidationError`), never “best effort”.

**Product constraint**: one active *writer* per learner/session is assumed.
SQLite serialises writers and conflicts are explicit, but the system does not
provide distributed locking, multi-host coordination or automatic retry on
`SNAPSHOT_REVISION_CONFLICT` (an operator/recovery pass is required).  This is a
documented limitation, not a hidden behaviour.

---

## 9. Compatibility, fallback and minimal M1-A test adaptations

* Repository extension is **additive**: all M1-A methods keep their old
  behaviour.  The engine uses
  `getattr(repository, "commit_teaching_turn")` + `session_version` feature
  detection; protocol-only repositories fall back to the legacy multi-write
  path, exposed as `engine.supports_transactional_turns is False` and
  documented as **non-atomic** (no recovery guarantee, `RECOVERY_UNSUPPORTED`).
* `HISTORY_EVENT_TYPE_VALUES` gains one **appended** value,
  `ASSESSMENT_PREPARED` (the frozen contract allows append-only enum values; no
  value was renamed/removed).  The PR1 freeze test
  (`tests/m1_teacher/test_contracts.py::_expected_enums`) was minimally updated
  to include the new value — recorded in the commit message.
* `tests/m1_teacher/test_e2e_resume_idempotency.py::test_duplicate_result_id_updates_mastery_once`
  previously asserted that the same `result_id` with a *different response text*
  silently returns the first grade.  That is exactly the B-Q3/B3 silent
  idempotency defect, so the test now asserts the stronger contract: identical
  retry → same result and zero events; same key/different response →
  `IDEMPOTENCY_CONFLICT` with unchanged state.  No assertion was deleted or
  weakened; the new assertions are strictly stronger.
* All other M1-A tests are unmodified (`536 passed` baseline before this PR).

## 10. Known limitations / UNVERIFIED

1. **Power-loss durability is not proven**: `PRAGMA synchronous=NORMAL` + WAL is
   used; the crash tests kill the process (`SIGKILL`), not the host/disk.  OS
   page-cache/hardware power-loss behaviour remains `UNVERIFIED`.
2. Crash failpoints cover every repository write point in the teaching turn, but
   are not an exhaustive fuzzer; other concurrency interleavings are covered only
   by the serialisation/conflict tests.
3. Single SQLite file / single host.  Multi-host or shared-filesystem behaviour
   is out of scope (and unsafe for SQLite WAL).
4. Recovery re-scores the canonical response as a string for non-`str`/`dict`
   response types (`response_kind` metadata is persisted; only text/structured
   are reconstructed losslessly).  Synthetic CF responses are text/structured.
5. The external scorer is at-least-once (§7).  A deterministic scorer that
   ignores the supplied `result_id` makes recovery fail closed rather than
   double-apply, but it cannot be auto-corrected.
6. A recovery failure is recorded once per attempt (deterministic `ERROR` event
   id); repeated calls are no-ops until the underlying condition is fixed
   (sticky audit trail by design, fail-closed).
7. `start_session`/action-generation/pause writes are not part of the atomic
   teaching-turn transaction; they are not mastery evidence and were outside the
   B-02 finding.  They remain individually transactional (no torn rows).
8. The M1-A demo evidence JSONL projection does not project the new internal
   `ASSESSMENT_PREPARED` event type (unknown type is dropped by the frozen
   projection); the two-phase write evidence is in this document’s crash matrix
   instead.
9. Multi-writer coordination / automatic retry policy is a product decision;
   current behaviour is explicit `ConflictError` + recovery API.

---

## 11. Evidence commands and observed results

Environment: `/root/Autonomous Teacher/.venv/bin/python` (Python 3.11.15),
worktree `/root/m1b/pr2`, no network, no keys, synthetic fixtures.

| Command | Observed |
|---|---|
| `"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q` | `595 passed in 35.29s` (M1-A baseline was `536 passed in 16.77s`; +17 turn-transaction, +33 crash, +9 concurrency tests) |
| `... pytest tests/m1_teacher/test_turn_transaction.py -q` | `17 passed in 0.94s` |
| `... pytest tests/m1_teacher/test_crash_recovery.py -q` | `33 passed in 14.10s` |
| `... pytest tests/m1_teacher/test_concurrency.py -q` | `9 passed in 2.91s` |
| `"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher` | `All checks passed!` |
| `M1B_MATRIX_OUT=/tmp/m1b_matrix.jsonl ... pytest tests/m1_teacher/test_crash_recovery.py -q` | 32 matrix rows; 3 distinct logical states (see §5) |

(All numbers are from actual runs in this worktree; wall-clock durations vary by
a few percent between runs.)

## 12. Change list

- `m1_teacher/learner/repository.py`: `session_version`, strict-advance snapshot
  option, `commit_teaching_turn`, `FAILPOINT_ENV` crash points,
  `DB_BUSY`/`SESSION_VERSION_CONFLICT`/`DUPLICATE_EVENT`/`EVENT_SEQ_CONFLICT`/
  `SNAPSHOT_REVISION_CONFLICT`/`INCONSISTENT_PENDING` fail-closed codes,
  configurable `busy_timeout_ms`.
- `m1_teacher/learner/history.py`: `EventDraft`,
  `assessment_event_drafts` (single source of the assessment event payload
  schema, reused by the atomic commit).
- `m1_teacher/session/engine.py`: two-phase
  `submit_response` (A → scorer → B) with legacy fallback, transition planner,
  transaction retry, `recover_session`/`recover_pending_turns`,
  `RecoveryReport`, monotonic session timestamps.
- `m1_teacher/contracts/types.py`: append `ASSESSMENT_PREPARED` event type
  (additive).
- `tests/m1_teacher/`: `test_turn_transaction.py`, `test_crash_recovery.py`,
  `test_concurrency.py`, `txn_child.py`, `txn_support.py`; minimal PR1 test
  adaptations listed in §9.
- No changes to `m1_teacher/contracts/repository.py`, `contracts/errors.py`,
  domain/knowledge/assessment modules, fixtures, or M0/protected paths.
