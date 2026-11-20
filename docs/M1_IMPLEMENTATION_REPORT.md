# M1-A Implementation Report (B-PR1 … B-PR5)

- **Status**: final implementation report for the M1-A Offline Adaptive Teacher MVP.
- **Worktree / branch**: `/root/at-m1a-mvp` / `work/m1a-mvp`.
- **Base / reviewed commits**: worktree baseline `3e7afee077845a071cd364e93ab209cac20b2d5f`;
  B-PR5 reviewed commit **C5** `d4f10f3b32ee115759e2f9409c033b7ec8d76f6c`. The C6 minimal fix
  (deterministic ``e2e_summary.json`` provenance, P1-1) is uncommitted at report time — Lead
  records the C6 SHA.
- **Evidence provenance**: all three ``docs/m1a_evidence/`` artifacts are content-tree
  deterministic. ``e2e_summary.json`` contains a **fixed** ``artifact_manifest``
  (``manifest_version`` / fixed ``generated_at`` / fixed ``base_sha`` / fixed
  ``implementation_commit``) and **no wall-clock timestamp and no dynamically read git SHA**, so
  it is byte-identical with or without ``.git`` and on any date.
- **Contract version**: `m1a.v0` (frozen) + additive next-phase `m1a.extensions.v0` (stubs).
- **Date of measurements**: `2026-11-20` (UTC).
- **Boundary**: offline synthetic only. Nothing in this report measures or claims real teaching
  effectiveness; evidence classes are used explicitly (`MOCK` / `DETERMINISTIC` /
  `HUMAN_REVIEWED` / `NOT_VERIFIED`).

---

## 1. What was delivered per PR

| PR | Blocks | Content | Tests | Evidence class |
|---|---|---|---|---|
| B-PR1 | B1 | Frozen `m1a.v0` contracts, validated knowledge graph, domain registry, CF binary-search adapter (allow-listed public fixtures only), synthetic CC0-1.0 fixtures | **268** | DETERMINISTIC + MOCK fixtures |
| B-PR2 | B2/B7 | Evidence-driven learner model (heuristic mastery), append-only learning history, SQLite persistence/rebuild/idempotency | **100** | DETERMINISTIC |
| B-PR3 | B3/B4 | Diagnostic engine (next item + hypothesis + `Reason`) and curriculum planner (prerequisite remediation, teach/practice/assess, review, reassess, goal completion) | **50** | DETERMINISTIC |
| B-PR4 | B5/B6 | Teaching-session state machine (`DIAGNOSE→TEACH→PRACTICE→ASSESS→UPDATE→REVIEW`, pause/resume, EVAL_ERROR isolation) and independent assessment scorer (only hidden-scoring reader) | **75** | DETERMINISTIC |
| B-PR5 (this PR) | B8 | Student A/B E2E paths, deterministic demo + CLI, reproducible evidence JSONL, next-phase interface stubs, this report + architecture/evaluation/review/next-phase docs | **43** | MOCK (synthetic students) + DETERMINISTIC (state machine/ids/replay) |

Test widths per file (collected, real):

```
tests/m1_teacher/test_contracts.py                  169
tests/m1_teacher/test_knowledge_graph.py             41
tests/m1_teacher/test_domain_adapter.py              38
tests/m1_teacher/test_fixtures_cf.py                 20   # PR1 total 268
tests/m1_teacher/test_learner_model.py               48
tests/m1_teacher/test_history.py                     27
tests/m1_teacher/test_repository_sqlite.py           25   # PR2 total 100
tests/m1_teacher/test_diagnostic_engine.py           16
tests/m1_teacher/test_curriculum_planner.py          19
tests/m1_teacher/test_planner_policy.py              15   # PR3 total 50
tests/m1_teacher/test_assessment_scorer.py           34
tests/m1_teacher/test_session_engine.py              22
tests/m1_teacher/test_session_transitions.py         19   # PR4 total 75
tests/m1_teacher/test_e2e_student_ab.py              18
tests/m1_teacher/test_e2e_resume_idempotency.py      13
tests/m1_teacher/test_cli_smoke.py                   12   # PR5 total 43
```

## 2. B-PR5 new files (real line counts)

| File | Lines | Purpose |
|---|---|---|
| `m1_teacher/demo.py` | 1376 | deterministic Student A/B E2E runner, MOCK student scorer, evidence writer, text/JSON output |
| `m1_teacher/cli.py` | 177 | offline argparse CLI (`--demo`, `--student a|b|both`, `--db`, `--json`, `--write-evidence`) |
| `m1_teacher/extensions/interfaces.py` | 251 | next-phase contract-only Protocols/value objects (fail closed) |
| `m1_teacher/extensions/__init__.py` | 47 | extension exports |
| `tests/m1_teacher/test_e2e_student_ab.py` | 560 | A/B path differences, policy rules, reproducibility, evidence checks |
| `tests/m1_teacher/test_e2e_resume_idempotency.py` | 574 | pause/restart, idempotency, EVAL_ERROR isolation, hidden-label isolation |
| `tests/m1_teacher/test_cli_smoke.py` | 245 | CLI surface + cross-process determinism + evidence reproducibility |

No PR1–PR4 implementation/fixture file was modified by B-PR5.

## 3. Exact commands and real outputs (final verification)

```bash
cd /root/at-m1a-mvp
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
# exit 0 -> "536 passed in 13.61s"  (real run: real 0m13.805s)

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo    # run twice
# exit 0 both; stdout byte-identical; sha256=b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b
# md5=f92be523b3a562f0826cae7ec8c74010; 53 lines

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
# exit 0 -> writes docs/m1a_evidence/*.jsonl + e2e_summary.json (see §4)

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --help
# exit 0, usage printed (offline; no network/API key)

"/root/Autonomous Teacher/.venv/bin/python" -m ruff check \
  m1_teacher/demo.py m1_teacher/cli.py m1_teacher/extensions \
  tests/m1_teacher/test_e2e_student_ab.py \
  tests/m1_teacher/test_e2e_resume_idempotency.py \
  tests/m1_teacher/test_cli_smoke.py
# "All checks passed!"
```

Ruff format: new files are formatted (`ruff format --check` clean for the same list).

## 4. Reproducible evidence artifacts (`docs/m1a_evidence/`)

Generated by the fixed command above; JSONL is byte-identical across consecutive runs (verified
by tests and by re-running). The projection excludes wall-clock timestamps and any hidden scoring
material; the E2E mock scorer is pinned to `2026-11-20T00:00:00Z`.

| Artifact | Lines | SHA-256 | Contents |
|---|---|---|---|
| `e2e_student_a.jsonl` | 61 | `171cc654f65129af803dbcd97ebffd50a2da97e8c616d3868570a9b7cb9443f1` | seeded prior evidence, diagnosis, plan, actions, assessments, mastery updates, pause/resume, mastery_after |
| `e2e_student_b.jsonl` | 54 | `5e84229ec452b2abad5243fa731f58cde38f76baee5240b01d01a3759eeda46b` | same schema for Student B (prerequisite-remediation path) |
| `e2e_summary.json` | — | `23b871a3743f6100d23130dc72f3796129cbb8bb0b97baa4492d54e3a96af8ce` | command, fixed `artifact_manifest` (manifest_version + fixed generated_at/base_sha/implementation_commit; **no wall-clock/git reads**), fixed seed/timestamp, A/B summaries, path differences, policy checks, evidence hashes, classification, `NOT_RUN` items, disclaimer |

Evidence classes inside the JSONL: `["MOCK", "DETERMINISTIC"]` (synthetic student outcomes;
deterministic state machine/model/ids). No `HUMAN_REVIEWED` outcome exists yet.

## 5. Requirements coverage (from the B-PR5 brief)

| Requirement | Where verified |
|---|---|
| 1. Student A/B different diagnosis/plan/review/reason | `test_e2e_student_ab.py` (first action, plan, phase sequence, diagnosis reason, recommendations) + §evaluation report |
| 2. Same inputs/state → reproducible plan; demo double-run stdout identical | `test_same_state_reproduces_identical_plan`, `test_cli_smoke.py::test_demo_is_deterministic_across_processes`, evidence tests |
| 3. Wrong answers never raise mastery; consecutive correct raises (exact values) | `test_wrong_answers_never_raise_mastery`, `test_consecutive_correct_raise_mastery_exactly` (asserts value/confidence/evidence count against the frozen formula) |
| 4. HARD prerequisite remediation before target teaching (Student B sortedness) | `test_planner_prioritises_hard_prerequisite_remediation`, scenario plan assertion, `e2e_summary.policy_checks.prerequisite_remediation_before_target=True` |
| 5. Pause → new engine + same SQLite db → resume; snapshot/plan/pending equal; `verify_rebuild=True` | `test_pause_restart_new_engine_same_db_is_consistent`, `test_resume_requires_paused_state` |
| 6. Scorer anomaly (EVAL_ERROR) is not student error / does not lower mastery | `test_raising_scorer_is_eval_error_and_never_lowers_mastery`, `test_missing_scoring_spec_is_eval_error_only` (real `DeterministicScorer` + broken spec) |
| 7. Teacher/planner/diagnostic cannot access hidden labels; only scorer reads hidden path | `test_teacher_components_do_not_need_hidden_scoring_material`, `test_tampered_scoring_specs_do_not_change_teacher_behaviour`, `test_teacher_code_references_hidden_scoring_only_in_scorer` (AST scan) |
| 8. Duplicate result_id/event does not double-update mastery | `test_duplicate_result_id_updates_mastery_once`, `test_duplicate_history_event_is_idempotent` |
| 9. Independent teacher-policy tests (prerequisite/review/reassess/goal-complete + structured `Reason`) | `test_e2e_student_ab.py` §“Independent teacher-policy tests” (4 rule tests + structured reasons + diagnostic reason code) |
| CLI/demo offline deterministic; evidence classified; no network/Key/M0 | `test_cli_smoke.py` (11 tests), AST scan test, evidence files, disclaimer |

## 6. Boundaries / limitations / NOT_RUN

- All student outcomes are `MOCK` (synthetic fixture `response_script`); mastery values are the
  deterministic heuristic arithmetic, **not** real learning gains.
- `HUMAN_REVIEWED` is `NOT_RUN`; the independent review follows this PR.
- Real teaching effectiveness, real learner outcomes, real model behaviour: `NOT_VERIFIED`
  (no measurement attempt in M1-A).
- Network/LLM provider/LiveGate integration: `NOT_RUN` and forbidden in M1-A; no M0 file, no
  provider SDK, no LiveGate, no API key is touched.
- Only the `cf_binary_search` synthetic domain is exercised; multi-domain and interview/knowledge
  freshness/autonomous research remain next-phase contracts (`m1_teacher/extensions/`, stubs
  fail closed with `EXTENSION_NOT_IMPLEMENTED`).
- `CODE` assessment runs learner code in a local child process; it is not an OS security sandbox.

## 7. Reproduction checklist

```bash
cd /root/at-m1a-mvp
git rev-parse HEAD                     # reviewed commit C5=d4f10f3… (C6 evidence fix uncommitted)
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q      # 536 passed
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > a.txt; ... > b.txt; cmp a.txt b.txt
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/*
```

Any re-run that disagrees with the hashes above on the same frozen tree must be treated as a
regression and recorded honestly; old PASS values must not be retained.
