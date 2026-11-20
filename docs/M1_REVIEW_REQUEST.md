# M1-A Review Request (B-PR5, independent review)

- **Request**: independent review of the M1-A Offline Adaptive Teacher MVP, final PR (B-PR5).
- **Worktree**: `/root/at-m1a-mvp`, branch `work/m1a-mvp`.
- **Base / last reviewed commit**: `933ccdeab2085ff30bbf0dcb65271373eea6ef09` (B-PR4 freeze —
  PR1–PR4 were reviewed/closed for their own scopes). B-PR5 changes (demo/CLI/tests/evidence/docs
  and next-phase stubs) are **uncommitted at request time**; the Lead records the PR5 commit SHA.
  Reviewer: use `git rev-parse HEAD` in the frozen review copy and compare against the Lead's
  recorded SHA; do not assume this document contains the post-commit SHA.
- **Contract version**: `m1a.v0` (frozen) + additive `m1a.extensions.v0` stubs.
- **Evidence classes**: `MOCK` / `DETERMINISTIC` / `HUMAN_REVIEWED` / `NOT_VERIFIED`.
- **Non-claimed scope**: no real teaching effect, no network/provider/LiveGate, no real learner
  data, no M0 modification, no web app. Reviewer should not treat declared limitations as new
  findings unless they are factually wrong.

---

## 1. What to review

1. **Teaching-loop logic**: diagnostic item selection, prerequisite-first planning, remediation
   ordering, teach/practice/assess/update/review transitions, reached-state invariants, goal
   completion — do they match the documented policy and the E2E narrative?
2. **Data isolation / hidden answers**: verify that only `m1_teacher/assessment/scorer.py` can
   read hidden scoring material; teacher-visible records/fixtures/evidence contain no answer keys,
   expected outputs or hidden test content; verify the tamper/delete probes are meaningful.
3. **Idempotency / recovery**: duplicate `result_id`/event does not double-update mastery;
   EVAL_ERROR (raising scorer and missing/broken scoring spec) is never learner evidence and never
   lowers mastery; pause → new engine + same SQLite db → resume is state/snapshot/plan/pending
   consistent and `LearningHistory.verify_rebuild` is true.
4. **Determinism**: demo stdout is byte-identical across two independent processes; JSONL
   evidence is byte-identical across runs; no wall-clock/random source influences decisions or
   persisted evidence.
5. **Evidence honesty**: every number in `docs/M1_IMPLEMENTATION_REPORT.md` and
   `docs/M1_EVALUATION_REPORT.md` is reproducible from the commands below; `MOCK` and
   `DETERMINISTIC` are used correctly; `NOT_RUN`/`NOT_VERIFIED` items are not written as PASS;
   "offline synthetic only, not real teaching effect" boundary is present.
6. **Boundaries**: no `autoteacher_m0` import, no network module, no API key/provider/LiveGate,
   no M0 file changed; `m1a.v0` unchanged (additive stubs only).
7. **CLI/demo**: `--help`, `--demo`, `--student a|b|both`, `--db`, `--json`,
   `--write-evidence` behave as documented and remain fully offline.

## 2. Commands and expected results (frozen tree)

```bash
cd /root/at-m1a-mvp
git rev-parse HEAD                                   # Lead-recorded PR5 SHA

"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
# expected: exit 0, "533 passed" (PR1 268 + PR2 100 + PR3 50 + PR4 75 + PR5 40)

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/a.txt 2>&1
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo > /tmp/b.txt 2>&1
cmp /tmp/a.txt /tmp/b.txt && sha256sum /tmp/a.txt
# expected: identical; sha256 b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/*
# expected:
#   e2e_student_a.jsonl 171cc654f65129af803dbcd97ebffd50a2da97e8c616d3868570a9b7cb9443f1
#   e2e_student_b.jsonl 5e84229ec452b2abad5243fa731f58cde38f76baee5240b01d01a3759eeda46b
#   e2e_summary.json    62f1ebd49b506a5e6f770bed1d1633f1c3993cb3d406636f0eed99d8110333ed

"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --help
"/root/Autonomous Teacher/.venv/bin/python" -m m1_teacher.cli --student both --json >/tmp/both.json

"/root/Autonomous Teacher/.venv/bin/python" -m ruff check \
  m1_teacher/demo.py m1_teacher/cli.py m1_teacher/extensions \
  tests/m1_teacher/test_e2e_student_ab.py \
  tests/m1_teacher/test_e2e_resume_idempotency.py \
  tests/m1_teacher/test_cli_smoke.py
# expected: "All checks passed!"
```

If a hash/count differs on the same frozen tree, treat it as a regression and report it; do not
fall back to this document's PASS values.

## 3. Evidence index

| Item | Location | SHA-256 |
|---|---|---|
| Student A E2E trace (61 JSONL lines) | `docs/m1a_evidence/e2e_student_a.jsonl` | `171cc654f65129af803dbcd97ebffd50a2da97e8c616d3868570a9b7cb9443f1` |
| Student B E2E trace (54 JSONL lines) | `docs/m1a_evidence/e2e_student_b.jsonl` | `5e84229ec452b2abad5243fa731f58cde38f76baee5240b01d01a3759eeda46b` |
| Scenario summary (A/B path diffs, checks, hashes, NOT_RUN) | `docs/m1a_evidence/e2e_summary.json` | `62f1ebd49b506a5e6f770bed1d1633f1c3993cb3d406636f0eed99d8110333ed` |
| Architecture (final) | `docs/M1_ARCHITECTURE.md` | (tracked doc) |
| Implementation report | `docs/M1_IMPLEMENTATION_REPORT.md` | (tracked doc) |
| Evaluation report | `docs/M1_EVALUATION_REPORT.md` | (tracked doc) |
| Next-phase plan + interface stubs | `docs/M1_NEXT_PHASE_PLAN.md`, `m1_teacher/extensions/` | (tracked doc/code) |
| Demo stdout determinism hash | command in §2 | `b08ceee9…` |

The JSONL projection deliberately contains no wall-clock timestamps and no hidden scoring
material; the only timestamp value it may contain is the fixed `2026-11-20T00:00:00Z`.

## 4. Review checklist (per item: PASS / PARTIAL / FAIL / NOT_RUN + evidence)

- [ ] R1 Teaching logic: prerequisite-first remediation before target teaching; diagnosis reasons;
      review/reassess/goal-complete rules; A/B paths differ for explainable reasons.
- [ ] R2 Hidden-label isolation: only `assessment/scorer.py` references hidden scoring; static scan
      + delete/tamper probes; no answer material in teacher types/fixtures/evidence.
- [ ] R3 Idempotency: duplicate result/event → one mastery update; no duplicate history.
- [ ] R4 Recovery: pause → new engine + same SQLite db → resume; snapshot/plan/pending equal;
      `verify_rebuild=True`.
- [ ] R5 EVAL_ERROR isolation: raising scorer and missing/broken spec; mastery unchanged; no
      INCORRECT; retry/exhaustion/REVIEW path correct.
- [ ] R6 Determinism: demo stdout byte-identical across processes; JSONL byte-identical; no
      wall-clock/random behaviour.
- [ ] R7 Evidence honesty: docs numbers reproducible; `MOCK`/`DETERMINISTIC`/`NOT_VERIFIED` used
      correctly; boundary statement present; no real-learning claim.
- [ ] R8 Boundaries: no M0 import/modification; no network/API key/LiveGate; `m1a.v0` unchanged.
- [ ] R9 CLI/demo behavior matches documentation and stays offline.
- [ ] R10 Next-phase stubs are contract-only and fail closed with `EXTENSION_NOT_IMPLEMENTED`
      (`teacher_improvement` in-memory log refuses `real_effect_claim=True`).

## 5. Declared limitations (not findings unless incorrect)

Single synthetic domain (`cf_binary_search`); heuristic (uncalibrated) mastery model; MOCK student
outcomes; CODE judging is a local subprocess boundary, not an OS sandbox; open-ended answers are
conservative (`NEEDS_REVIEW`, at most `PARTIAL`); next-phase features are stubs only; no real
learner study; no network/provider. Full list: `docs/M1_ARCHITECTURE.md` §10 and
`docs/M1_EVALUATION_REPORT.md` §limitations/§NOT_RUN.

## 6. Requested disposition

`PASS_FOR_M1A_OFFLINE_MVP_SCOPE` / `PARTIAL` / `FAIL` with per-item evidence, plus any
P0/P1/P2 findings and a clear statement that the result is limited to offline synthetic
evaluation. Do not approve any real-teaching-effect, LiveGate or production claim.
