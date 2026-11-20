# M1-A Evaluation Report (B-PR5 offline closed loop)

- **Status**: final offline evaluation report for the M1-A MVP.
- **Command**: `cd /root/at-m1a-mvp && "/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence`
- **Raw evidence**: `docs/m1a_evidence/e2e_student_a.jsonl`,
  `docs/m1a_evidence/e2e_student_b.jsonl`, `docs/m1a_evidence/e2e_summary.json`
  (SHA-256 in `docs/M1_IMPLEMENTATION_REPORT.md` §4).
- **Fixed inputs**: synthetic students `student_a` / `student_b` (CC0-1.0), one objective
  `obj.cf.binary_search.mastery`, fixed timestamp `2026-11-20T00:00:00Z`, turn budget 10,
  pause/restart at turn 5, deterministic planner policy
  (`PlannerPolicy(prerequisite_mastery_threshold=0.25)` — an explicit E2E simulator constant so
  two seeded observations represent a known prerequisite).
- **Evidence classes**: `MOCK` (synthetic student fixtures/scripted outcomes/seeded prior),
  `DETERMINISTIC` (state machine, mastery arithmetic, ids, replay), `NOT_VERIFIED` (real teaching
  effect). `HUMAN_REVIEWED` = `NOT_RUN` until the independent review.
- **Boundary**: offline synthetic only; **not real teaching effect**. No real learner, no real
  model, no network/provider, no API key.

---

## 1. Closed-loop result summary

| Item | Student A | Student B |
|---|---|---|
| Seeded prior (MOCK, evidence-driven history) | 9 seeded observations: array/sortedness/linear/binary ≥ 0.30 evidence 2; boundary 0.00 evidence 1 | 6 seeded observations: array/linear 0.30 evidence 2; sortedness/binary 0.00 evidence 1 |
| Initial diagnosis (status / target / item / reason) | `READY` / `cf.complexity.log` / `item.bs.mcq.007` / `TARGET_EVIDENCE_GAP` | `READY` / `cf.sort.sortedness` / `item.bs.mcq.002` / `HARD_PREREQUISITE_GAP` |
| First action | `DIAGNOSE` item.bs.mcq.007 (cf.complexity.log) | `DIAGNOSE` item.bs.mcq.002 (cf.sort.sortedness) |
| Plan steps | 8 | 8 |
| Plan prefix (phase/action/node/reason) | `TEACH/EXPLAIN/binary/TEACH_TARGET_NODE` → `PRACTICE/PRACTICE/binary/PRACTICE_TARGET_NODE` → `ASSESS/DIAGNOSE/binary/ASSESS_PROGRESS` → boundary … | `TEACH/RETEACH/sortedness/REMEDIATE_HARD_PREREQUISITE` → `PRACTICE/PRACTICE/sortedness/PRACTICE_HARD_PREREQUISITE` → `TEACH/RETEACH/binary/REMEDIATE_HARD_PREREQUISITE` → boundary … |
| Phase sequence | DIAGNOSE×3 → ASSESS/UPDATE/REVIEW → DIAGNOSE×2 → … → TEACH → PRACTICE → … → PAUSED → REVIEW → … (REVIEW at turn 10) | DIAGNOSE×3 → ASSESS/UPDATE/REVIEW → … → TEACH → PAUSED → REVIEW → PRACTICE/ASSESS/UPDATE/REVIEW … (REVIEW at turn 10) |
| Assessments (status counts) | 8: CORRECT 7, INCORRECT 1 | 7: INCORRECT 3, NEEDS_REVIEW 4 |
| Mastery before → after (evidence-driven) | binary 0.30→**0.543571** (evidence 2→8, confidence 0.75→0.996); complexity 0→0.20 (1); boundary 0.00→0.00 (2) | binary 0.00→**0.00** (3, all INCORRECT); sortedness 0.00→**0.00** (2, all INCORRECT); others unchanged |
| Next recommendation | PRACTICE binary (PRACTICE_TARGET_NODE) → ASSESS binary → REASSESS boundary | REASSESS sortedness (REASSESS_STUCK_NODE) → REASSESS binary → EXPLAIN boundary |
| Interrupt/restart (pause at turn 5) | snapshot_equal=True, plan_equal=True, paused_plan_equal=True, pending_equal=True, verify_rebuild(before/after)=True | same |
| `verify_rebuild` (full history replay vs materialised snapshot) | True | True |

Path differences (all `true`, from `e2e_summary.path_differences`): `first_action_differs`,
`initial_plan_differs`, `phase_sequence_differs`, `final_mastery_differs`,
`next_recommendation_differs`.

Policy checks (`e2e_summary.policy_checks`): `prerequisite_remediation_before_target=True`,
`student_a_has_no_prerequisite_remediation=True`, `interrupt_resume_state_equal=True`,
`history_verify_rebuild=True`.

## 2. Why the two paths differ (explainable, not tuned per student)

1. **Seeded prior evidence differs** (per fixture `expected_traits`, replayed through the real
   learner model): A has complete prerequisites + weak boundary handling; B is missing the
   `cf.sort.sortedness` HARD prerequisite (and has weak binary search).
2. **Diagnosis** uses observed mastery + the prerequisite DAG: A's evidence gap is on a target
   node (`TARGET_EVIDENCE_GAP`), B's is a blocking prerequisite (`HARD_PREREQUISITE_GAP`).
3. **Planner** enforces "HARD prerequisites block teaching": B gets `RETEACH`+`PRACTICE` for
   sortedness (and then the dependent binary node) **before** teaching boundary/lower-bound
   targets; A starts directly with target teaching (`TEACH/EXPLAIN` binary).
4. **Session outcomes** come from the synthetic `response_script` (MOCK): A's script yields mostly
   CORRECT except a boundary off-by-one item, so binary mastery rises via observed evidence; B's
   script yields INCORRECT on sortedness/binary items and NEEDS_REVIEW on open-ended items, so
   mastery does **not** rise and the review recommendation remains reassessment.
5. Every plan/session decision carries a structured `Reason` (`code`, `node_ids`, `detail`,
   `policy_version`), so the difference is auditable from the JSONL evidence, not inferred from
   prose.

## 3. Evidence-driven mastery checks (real assertions, not impressions)

- **Wrong answers never raise mastery**: `test_wrong_answers_never_raise_mastery` runs a session
  whose test scorer returns INCORRECT for every item; every mastery value stays exactly `0.0`,
  error counters are recorded, and `snapshot.revision == len(ASSESSED events)`.
- **Consecutive correct raises mastery by the frozen formula**: with `correct_step=0.2` and
  `decay=1/(1+e)`, a node with `n` observed CORRECT outcomes must equal
  `min(1, Σ 0.2/(1+i))`; the test asserts the exact value, confidence `1-0.5^n` and
  `evidence_count == n` for every touched node.
- **Open-ended answers are not faked as correct**: the real scorer returns at most `PARTIAL` for
  keyword evidence and `NEEDS_REVIEW` when semantic evidence is unverifiable. Student B's session
  produced 4 `NEEDS_REVIEW` outcomes that never changed mastery.
- **EVAL_ERROR is not learner evidence**: with a raising scorer and with the real deterministic
  scorer against a deleted scoring spec, the engine records `EVAL_ERROR`/`ERROR`, retries up to
  the policy limit, returns the session to `REVIEW`, and keeps the learner snapshot **byte-identical**
  (mastery, confidence, evidence count, error counters, revision all unchanged). EVAL_ERROR is
  never counted as INCORRECT.
- **Idempotency**: repeating `submit_response` with the same `result_id` returns the first result
  and writes no new events/no second mastery update; re-applying an already-appended history event
  returns `False` and changes nothing.
- **Hidden-label isolation**: teacher components produce identical knowledge nodes/edges/objectives/
  items, diagnosis and plans when the hidden scoring directory is deleted or every spec is
  overwritten with junk on a temporary fixture copy. A static scan confirms only
  `m1_teacher/assessment/scorer.py` references hidden scoring paths.

## 4. FAILURE CASES / robustness matrix

| Case | Expected | Observed (test) |
|---|---|---|
| Scorer infrastructure failure (raising) | EVAL_ERROR, mastery unchanged, no INCORRECT | pass (`test_raising_scorer_is_eval_error_and_never_lowers_mastery`) |
| Missing scoring spec (real scorer) | EVAL_ERROR ×3, retry_exhausted, phase REVIEW, mastery still None/unchanged | pass (`test_missing_scoring_spec_is_eval_error_only`) |
| All-wrong session | mastery stays 0.0, errors recorded | pass (`test_wrong_answers_never_raise_mastery`) |
| Duplicate result_id (network-style retry) | exactly one mastery update | pass (`test_duplicate_result_id_updates_mastery_once`) |
| Duplicate history event | no double update | pass (`test_duplicate_history_event_is_idempotent`) |
| Pause → restart (new engine + new SQLite connection, same db) | state/snapshot/plan/pending identical, history rebuild true | pass (`test_pause_restart_new_engine_same_db_is_consistent`) |
| Resume without pause | `ConflictError` (fail closed) | pass (`test_resume_requires_paused_state`) |
| Hidden scoring dir deleted | teacher behaviour identical | pass (`test_teacher_components_do_not_need_hidden_scoring_material`) |
| Hidden scoring specs tampered | teacher behaviour identical | pass (`test_tampered_scoring_specs_do_not_change_teacher_behaviour`) |

## 5. Reproducibility / determinism evidence

- Full suite: `pytest tests/m1_teacher -q` → **536 passed** (exit 0) on the C6-fixed tree.
- Demo (real subprocess runs, two independent processes):
  stdout byte-identical; `sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`,
  `md5=f92be523b3a562f0826cae7ec8c74010`, 53 lines.
- Evidence artifacts: byte-identical across consecutive runs and independent of `.git`/date (asserted in tests); hashes:
  - `e2e_student_a.jsonl` `171cc654f65129af803dbcd97ebffd50a2da97e8c616d3868570a9b7cb9443f1`
  - `e2e_student_b.jsonl` `5e84229ec452b2abad5243fa731f58cde38f76baee5240b01d01a3759eeda46b`
  - `e2e_summary.json` `23b871a3743f6100d23130dc72f3796129cbb8bb0b97baa4492d54e3a96af8ce` (fixed `artifact_manifest`: no wall-clock/git reads; content-tree deterministic)
- Determinism mechanism: fixed E2E scorer timestamp, content-addressed ids
  (`plan:`/`step:`/`action:`/`diagnosis:` fingerprints), deterministic planner/diagnostic
  ordering, and an evidence projection that omits wall-clock timestamps (the demo output contains
  no wall clock; only the fixed timestamp appears).

## 6. Boundary statement (non-claims)

> **Offline synthetic only, not real teaching effect.** The numbers above describe a deterministic
> local state machine over synthetic CC0-1.0 fixtures and scripted mock student outcomes. They do
> not measure learning gains, teaching quality, model capability or real learner behaviour, and
> must not be extrapolated. M1-A makes no production/LiveGate/network claim.

## 7. NOT_RUN items

- Real learner study / real teaching effectiveness measurement: `NOT_RUN`.
- Real LLM/provider/network integration: `NOT_RUN` (out of scope and forbidden).
- Human expert review of teaching quality: `NOT_RUN` (independent review follows this PR;
  `HUMAN_REVIEWED` evidence class not claimed).
- Multi-domain E2E (Interview Coach, Knowledge Freshness, Autonomous Research): `NOT_RUN`
  (contract-only stubs in `m1_teacher/extensions/`; see `docs/M1_NEXT_PHASE_PLAN.md`).
- Web App / browser UI: `NOT_RUN` (CLI/demo only in M1-A).
