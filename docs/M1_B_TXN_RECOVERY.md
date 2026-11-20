# M1-B B-PR2 — Session + History transactionality and crash recovery

- **Status**: implemented + crash-tested on branch `b-next/pr2-session-txn`,
  based on `work/m1a-mvp` = `4706250` (M1-A B-PR5 reviewed HEAD) and integrated
  with B-PR1 under merge `82c121b` (trusted judge / worker boundary assets).
- **Independent review**: `docs/M1_B_PR2_REVIEW.md` =
  **`PASS_WITH_ACTIONS`** (B2-01/02/03 + B-Q2 VERIFIED; 2 P1 are
  contract/document governance, 5 P2 are defence-in-depth/document precision).
  P1-1, P1-2 and the P2 items are closed by the follow-up commit on this branch
  (closure map in §13 below).
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
| W3 | transaction **B** (`commit_teaching_turn`) | one `BEGIN IMMEDIATE` | terminal `ASSESSED`/`MASTERY_UPDATED` (or `ERROR` for `EVAL_ERROR`), learner snapshot, next session state | rollback → (W1 state) recoverable; commit → turn complete exactly once |
| W3b | goal write inside transaction **B** (same `BEGIN IMMEDIATE`) | part of W3 | optional `GOAL_COMPLETED` event + `goals` row update (goal-completion turn only) | rollback → (W1 state) recoverable; commit → goal status/event atomic with the mastery/session update |
| W4 | crash-recovery audit `ERROR` events | single atomic append | explainable `RECOVERY_*` reason, session/mastery unchanged | retried recovery is a zero-event no-op |

The `learners` row is created by `INSERT ... ON CONFLICT DO NOTHING` **inside
the same transaction** as the first event/session write (`_ensure_learner_row`).
It has no dedicated failpoint because it has no independently observable
post-crash state: killing the process before `COMMIT` rolls the row back with the
rest of the transaction, and after `COMMIT` the row is part of the committed
state already covered by W1/W3. Legacy write points outside `submit_response`
(`start_session`, `_generate_and_persist`, `pause/resume`) are unchanged for the
M1-A-facing behaviour; they do not apply mastery and are not in the B-02 blast
radius.

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

For scenarios with **seeded prior evidence** (B-PR5 seed: a snapshot that
predates the event log), log-only rebuild equality is not expected; the goal
crash scenarios assert revision monotonicity and the exact `+1` advance instead
(seed limitation is documented in B-PR5 and asserted as
`verify_rebuild is False` in `test_goal_completion_is_atomic_and_persists_goal_status`).

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

Observed: `35 passed in 14.57s` (merged-tree run after P1-2 added the two goal
write-point cases; see §11 for the suite command).

Every kill point collapses to one of **three** persisted logical states (plus
the seeded-snapshot *prepared* variant used by the two goal write-point cases),
each with one reproducible content hash (wall-clock fields and the CAS session
digest are excluded from the hash):

| Logical state | Persisted shape | event count | hash | Cases observed |
|---|---|---|---|---|
| **rolled_back** (A never committed) | pending `item.bs.mcq.001`, turn 0, no PREPARED, no terminal, no snapshot | 4 | `77c62048e9c34a12` | 9 A-pre-commit points |
| **prepared** (A committed, B not) | same pending/turn, 1 unresolved `ASSESSMENT_PREPARED`, no terminal, no snapshot | 6 | `ec99d57baf55a6e6` | A `after_commit`; scoring-window kill; 11 B-pre-commit points; 8 recovery-pre-commit points |
| **prepared** (goal-completion scenario, seeded snapshot) | pending `item.bs.mcq.004`, turn 0, seeded snapshot revision 1, 1 unresolved `ASSESSMENT_PREPARED`, no terminal/`GOAL_COMPLETED`, goal `ACTIVE` | 6 (seed adds no log rows) | `c054757f2c339965` | B `before_goal`, B `after_goal` |
| **committed** (B committed) | pending `None`, turn 1, terminal `ASSESSED`, snapshot revision 1, mastery `cf.array.basics=0.2` | 8 | `bbd500fbb1ca734b` | B `after_commit`; recovery `after_commit` |

Representative persisted DB summary per state (observed, `M1B_MATRIX_OUT`):

```json
{"state": "rolled_back", "case": "A-prepare:after_begin", "pending_item_id": "item.bs.mcq.001", "turn_index": 0, "phase": "DIAGNOSE", "prepared_total": 0, "prepared_unresolved": 0, "terminal_results": 0, "event_count": 4, "event_types": {"ACTION_TAKEN":1,"DIAGNOSIS_COMPLETED":1,"PLAN_CREATED":1,"SESSION_STARTED":1}, "snapshot_revision": null, "masteries": {}, "content_hash": "77c62048e9c34a12"}
{"state": "prepared", "case": "A-prepare:after_commit", "pending_item_id": "item.bs.mcq.001", "turn_index": 0, "phase": "DIAGNOSE", "prepared_total": 1, "prepared_unresolved": 1, "terminal_results": 0, "event_count": 6, "event_types": {"ACTION_TAKEN":1,"ASSESSMENT_PREPARED":1,"DIAGNOSIS_COMPLETED":1,"PLAN_CREATED":1,"RESPONSE_SUBMITTED":1,"SESSION_STARTED":1}, "snapshot_revision": null, "masteries": {}, "content_hash": "ec99d57baf55a6e6"}
{"state": "committed", "case": "C-commit:after_commit", "pending_item_id": null, "turn_index": 1, "phase": "REVIEW", "prepared_total": 1, "prepared_unresolved": 0, "terminal_results": 1, "event_count": 8, "event_types": {"ACTION_TAKEN":1,"ASSESSED":1,"ASSESSMENT_PREPARED":1,"DIAGNOSIS_COMPLETED":1,"MASTERY_UPDATED":1,"PLAN_CREATED":1,"RESPONSE_SUBMITTED":1,"SESSION_STARTED":1}, "snapshot_revision": 1, "masteries": {"cf.array.basics": 0.2}, "content_hash": "bbd500fbb1ca734b"}
{"state": "prepared (goal, seeded)", "case": "G-commit:before_goal", "pending_item_id": "item.bs.mcq.004", "turn_index": 0, "phase": "DIAGNOSE", "prepared_total": 1, "prepared_unresolved": 1, "terminal_results": 0, "event_count": 6, "snapshot_revision": 1, "goal_status": "ACTIVE", "goal_completed_events": 0, "content_hash": "c054757f2c339965"}
```

Per-case crash/recovery matrix (35 tests; each row is a real child-process
`SIGKILL`):

| Case group | Failpoints tested | Post-crash state | Recovery |
|---|---|---|---|
| transaction A, pre-commit | `after_begin`, `after_session_check`, `before/after_event_insert_1`, `before/after_event_insert_2`, `before/after_session`, `before_commit` | rolled_back | `recover_session` → `ALREADY_CONSISTENT` (0 events), then a normal retry commits |
| transaction A, `after_commit` | `after_commit` | prepared | `RECOVERED` (+2 events) |
| scoring window B | child scorer `SIGKILL` | prepared | `RECOVERED` |
| transaction B, pre-commit | `after_begin`, `after_session_check`, `before/after_event_insert_1`, `before/after_event_insert_2`, `before/after_snapshot`, `before/after_session`, `before_commit` | prepared | `RECOVERED` |
| transaction B, `after_commit` | `after_commit` | committed | `ALREADY_CONSISTENT` (0 events) |
| transaction B goal write (P1-2) | `before_goal`, `after_goal` (near-complete snapshot ⇒ next correct answer completes the goal) | prepared (seeded snapshot rev 1, goal `ACTIVE`, no `GOAL_COMPLETED`) | `RECOVERED`; final goal `COMPLETED`, exactly one `GOAL_COMPLETED` event, snapshot revision `setup+1`; duplicate submit is rejected because the session is `COMPLETE` (0 events) |
| recovery crashed, pre-commit | 8 `commit:*` points during recovery | prepared | second `recover_session` → `RECOVERED`; third → `ALREADY_CONSISTENT` |
| recovery crashed, `after_commit` | `commit:after_commit` | committed | `ALREADY_CONSISTENT` |

Every case additionally asserts: exactly one terminal event in the committed
state, `turn_index == setup+1`, `pending_item_id is None`, no duplicate mastery
application, unique/ascending `seq`, only the expected learner/session rows, and
an idempotent retry/zero-event recovery.  For non-seeded scenarios the committed
snapshot revision is 1 and `verify_rebuild == True`; the two goal cases use a
seeded snapshot (revision advances `setup+1`, seeded evidence predates the log)
and assert goal status/event atomicity instead.  Crash-then-recover converges to
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

Command: `pytest tests/m1_teacher/test_concurrency.py -q` → `9 passed in 2.64s`
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
* **Corrupt/old/unsupported state** (review P2-3 precision): unsupported
  `schema_meta.version` and corrupted snapshot/prepared-event JSON fail closed
  with `ValidationError`; a **tampered pending** state is detected by
  `recover_session()` as `RecoveryReport(status="FAILED",
  error_codes=["RECOVERY_STATE_INCONSISTENT"])` plus exactly one deterministic
  `ERROR` audit event (`stage="RECOVERY"`), with the session left unchanged —
  never “best effort”, never a false completion.

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
  `ASSESSMENT_PREPARED`.  This is an additive enum value under ADR-M1-001 D12;
  per D12 the change is recorded in **`docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6
  item 9** and in the **`docs/M1_ARCHITECTURE.md` §12 change log** (review
  P1-1).  No value was renamed/removed and no payload shape changed.  The PR1
  freeze test (`tests/m1_teacher/test_contracts.py::_expected_enums`) was
  minimally updated to include the new value — recorded in the commit message.
* `tests/m1_teacher/test_e2e_resume_idempotency.py::test_duplicate_result_id_updates_mastery_once`
  previously asserted that the same `result_id` with a *different response text*
  silently returns the first grade.  That is exactly the B-Q3/B3 silent
  idempotency defect, so the test now asserts the stronger contract: identical
  retry → same result and zero events; same key/different response →
  `IDEMPOTENCY_CONFLICT` with unchanged state (review P2-5 wording).  The
  4 removed test lines are **replaced by equivalent-or-stronger assertions** in
  the two adapted tests: the diagnostic wall-clock equality assert is replaced by
  a per-semantic-field comparison (only the non-behavioural `created_at` metadata
  is excluded) and the e2e call is moved inside `pytest.raises`, while the
  “same response returns the same result / zero new events” assertion is kept and
  strengthened.  No assertion was weakened, no test skipped/xfailed and no mock
  replaced an assertion.
* `tests/m1_teacher/test_diagnostic_engine.py::test_behaviour_unchanged_without_hidden_scoring_directory`
  compared two separately loaded adapter objectives **including** the
  load-time wall-clock `created_at` field; the module-scoped adapter fixture can
  have loaded in the previous second, which made the assertion fail ~5% of runs
  (observed 1/20 isolated module runs and once in a full-suite run).  The test
  now compares every semantic objective field and excludes only that
  non-behavioural timestamp metadata (the frozen contract validates the
  timestamp format, not a fixed value).  This is a determinism fix for a
  pre-existing flake, not a weakening; all other M1-A tests are unmodified.
* **Forward-only storage compatibility** (review P2-4): a database written by
  this PR can contain `ASSESSMENT_PREPARED` rows.  The frozen `HistoryEvent`
  enum validation means an **older build** (base `4706250`) opening such a DB
  raises `ValidationError` when decoding that event type — there is no silent
  downgrade and no compatibility adapter in this PR.  Rolling back to an older
  build requires exporting/rebuilding the learner DB first; this is declared in
  §10.

## 10. Known limitations / UNVERIFIED

1. **Power-loss durability is not proven**: `PRAGMA synchronous=NORMAL` + WAL is
   used; the crash tests kill the process (`SIGKILL`), not the host/disk.  OS
   page-cache/hardware power-loss behaviour remains `UNVERIFIED`.
2. Crash failpoints cover the assessment-turn **event, snapshot, session and
   goal-row** write points of the teaching-turn transaction (goal write points
   `before_goal`/`after_goal` are now exercised by real-`SIGKILL` tests with a
   near-complete snapshot; review P1-2).  They do **not** cover the `learners`
   row insert as an independent point (it is created inside the same transaction
   and is not independently observable after a crash — see §2), and they are not
   an exhaustive fuzzer; other concurrency interleavings are covered only by the
   serialisation/conflict tests.
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
10. **Forward-only storage**: a DB written by this PR is not readable by older
   builds because of the additive `ASSESSMENT_PREPARED` event value (review
   P2-4; also §9).  Downgrade requires an export/rebuild step; no compatibility
   adapter is implemented in this PR (B0 migration/rollback is a separate
   workstream).

---

## 11. Evidence commands and observed results

Environment: `/root/Autonomous Teacher/.venv/bin/python` (Python 3.11.15),
worktree `/root/m1b/pr2`, no network, no keys, synthetic fixtures.

| Command | Observed (merged tree: B-PR1 + B-PR2) |
|---|---|
| `"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q` | `737 passed in 64.62s` (674 B-PR1 legacy/sandbox/worker tests + 63 B-PR2 tests: 19 turn-transaction, 35 crash, 9 concurrency; M1-A B-PR5 baseline `536 passed` and pre-merge B-PR2-only tree `595 passed` are historical) |
| `... pytest tests/m1_teacher/test_turn_transaction.py -q` | `19 passed in 0.81s` |
| `... pytest tests/m1_teacher/test_crash_recovery.py -q` | `35 passed in 13.11s` |
| `... pytest tests/m1_teacher/test_concurrency.py -q` | `9 passed in 2.64s` |
| `"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher` | `All checks passed!` |
| `M1B_MATRIX_OUT=/tmp/m1b_matrix_final.jsonl ... pytest tests/m1_teacher/test_crash_recovery.py -q` | 34 matrix rows; 9 rolled_back / 21 prepared / 2 prepared-with-seeded-snapshot / 2 committed (see §5) |

Additional independent-review commands re-run in this worktree:
`pytest tests/m1_teacher/test_contracts.py -q` (enum freeze + additive delta,
169 passed) and the review's full-suite re-execution (733 tests before the two
P1-2 goal cases; 737 after).

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
- `m1_teacher/learner/repository.py` follow-up (review P2-1/P2-2):
  `_terminal_result_ids` only accepts deterministic `ASSESSED` /
  `evt.evalerror.*` events (RECOVERY audit `ERROR` never terminates an attempt),
  and plain/batch appends carry the explicit `EVENT_SEQ_CONFLICT` code so the
  recovery audit retry branch is reachable.
- Tests follow-up: 2 real-`SIGKILL` goal write-point cases (P1-2), P2-1
  orphan-PREPARED regression, P2-2 audit seq-conflict retry regression, plus
  `txn_support` goal-completion scenario helpers.
- Docs follow-up: ADR-M1-001 §6 item 9 + `M1_ARCHITECTURE.md` §12 change-log row
  (P1-1), this document's §2/§5/§8/§9/§10/§11 precision fixes (P1-2, P2-3,
  P2-4, P2-5) and §13 review-action closure map.
- No changes to `m1_teacher/contracts/repository.py`, `contracts/errors.py`,
  domain/knowledge/assessment modules, fixtures, or M0/protected paths.

---

## 13. Independent-review action closure (P1/P2)

Review: `docs/M1_B_PR2_REVIEW.md` (conclusion `PASS_WITH_ACTIONS`).  All actions
are closed in the follow-up commit on this branch; no product behaviour changed
by the P1 items (they are contract/document governance).

| Finding | Severity | Action taken | Evidence |
|---|---|---|---|
| **P1-1** D12 additive-enum change not recorded in ADR/architecture | P1 | `docs/M1_ADR_001_DOMAIN_CONTRACTS.md` §6 **item 9** records the `ASSESSMENT_PREPARED` additive delta (D12 + reason + forward-only storage); `docs/M1_ARCHITECTURE.md` §12 change log gained one append row | `grep -n ASSESSMENT_PREPARED docs/M1_ADR_001_DOMAIN_CONTRACTS.md docs/M1_ARCHITECTURE.md`; `pytest tests/m1_teacher/test_contracts.py -q` green |
| **P1-2** “crash failpoints cover every repository write point” over-claim; goal/`learners` gaps | P1 | Added 2 real-`SIGKILL` cases for `commit:before_goal` / `commit:after_goal` with a near-complete snapshot (goal-completion turn); reused recovery to assert `GOAL_COMPLETED` + goal row atomic; §2 and §10 item 2 now state the precise scope and the `learners`-row rationale (same transaction, no independent failpoint) | `pytest tests/m1_teacher/test_crash_recovery.py -q` → 35 passed; matrix 34 rows incl. 2 goal rows; `test_crash_during_goal_completion_write_point*` |
| **P2-1** RECOVERY audit `ERROR` wrongly counted as terminal (INV-4 bypass via repo API) | P2 | `_terminal_result_ids` accepts only deterministic terminal events (`ASSESSED` / `evt.evalerror.*`) and ignores `stage="RECOVERY"` audit rows; regression test asserts clearing pending after failed recovery → `ValidationError(code="INCONSISTENT_PENDING")` | `test_recovery_audit_error_does_not_satisfy_terminal_invariant` |
| **P2-2** audit seq-conflict retry branch dead | P2 | All plain/batch event appends now raise `ConflictError(code="EVENT_SEQ_CONFLICT")` for seq collisions; regression test forces a native collision on the first audit append and asserts the retry appends once and returns a `RecoveryReport` | `test_recovery_audit_event_seq_conflict_retry_branch` |
| **P2-3** §8 tampered-pending error-code description inaccurate | P2 | §8 now states: schema/corrupt JSON → `ValidationError`; tampered pending → `RecoveryReport(FAILED, RECOVERY_STATE_INCONSISTENT)` + exactly one `RECOVERY` audit `ERROR`, session unchanged | `grep` + review probe 4.6 output |
| **P2-4** old build cannot read new DB (undocumented downgrade) | P2 | Declared forward-only storage in §9 and §10 item 10 (export/rebuild required before rolling back; no compatibility adapter in this PR) | document text; review probe downgrade case |
| **P2-5** “no assertion was deleted” wording inaccurate | P2 | §9 now states the 4 replaced lines are equivalent-or-stronger assertion replacements (only non-behavioural `created_at` excluded; idempotency assertion kept/strengthened), no weakening/skip/mock pass | `git diff` of the adapted tests; full suite green |

**Still NOT_VERIFIED / out of scope** (unchanged): host power-loss durability,
multi-host SQLite, remote/network exactly-once, real learner DB migration,
and B-PR1/3/4/5 or overall integration conclusions.  The crash evidence remains
process-`SIGKILL` level (`DETERMINISTIC` + `MOCK` synthetic fixtures only).
