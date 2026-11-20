# M1-A Next Phase Plan (interfaces, fixtures, contracts)

- **Status**: next-phase plan for the primitives after the M1-A MVP; **contracts/stubs only** in
  this phase (`m1_teacher/extensions/`, contract version `m1a.extensions.v0`).
- **Hard boundary for the next phase**: still offline by default; no real network/provider/LiveGate
  or real learner data without a separate human-approved decision. All new verification below is
  static-fixture based (`MOCK` + `DETERMINISTIC` evidence), and no real teaching-effect claim is
  made.
- **Compatibility rule**: the frozen `m1a.v0` contract must not change; next-phase additions are
  additive (new modules/fields/protocols) and recorded in `docs/M1_ADR_001_DOMAIN_CONTRACTS.md`.

---

## 1. Web App (local UI)

- **Contract**: `m1_teacher.extensions.WebAppPort` + `WebSessionView`
  (session id/learner id/phase/turn/pending item/next action kind), `submit(session_id,
  item_id, response)`.
- **Implementation plan**: a local (loopback/offline) read-only UI over the existing
  `TeachingSessionEngine`; it must call the same engine APIs and never read hidden scoring.
- **Static fixture verification** (no browser needed for contract):
  - fixture: one SQLite db seeded by the deterministic demo (Student A path);
  - assert `session_view` fields equal the persisted `SessionState` + `current_action`;
  - assert submit through the UI wrapper produces exactly the same `AssessmentResult`/mastery
    delta as a direct engine submit (same `result_id`);
  - assert page/payload serialisation contains no hidden scoring material.
- **Exit criteria**: deterministic JSON snapshots for 2 students; no new network imports.

## 2. Interview Coach

- **Contract**: `m1_teacher.extensions.InterviewCoachPort`,
  `InterviewTurnRequest(learner_id, question_id, answer_text, untrusted_context)`,
  `start`/`assess_answer`.
- **Implementation plan**: deterministic Socratic follow-up ladder over synthetic question/JD
  fixtures; scoring must be a separate independent rubric (no LLM self-judging); injected
  documents are `DATA_ONLY` and must never alter system instructions.
- **Static fixture verification**:
  - synthetic question set + JD versions with no real personal data;
  - rubric unit checks: correct/partial/vague/infeasible/unsourced answers map to expected
    dimension scores within fixed tolerances; an injection document does not change the rubric
    result hash;
  - system-instruction hash is invariant before/after adversarial documents (contract only).
- **Exit criteria**: deterministic scoring fixtures + injection-invariance test; no provider call.

## 3. Knowledge Freshness

- **Contract**: `m1_teacher.extensions.KnowledgeFreshnessPort`,
  `KnowledgeFreshnessRequest(source_id, uri, observed_at, claim_status)`,
  `classify` → `KEEP`/`UPDATE`/`RECHECK` with structured reason.
- **Implementation plan**: offline versioned knowledge sources with timestamps; `UPDATE` only for
  verified newer authoritative sources; conflicts/expired/community sources stay in `RECHECK`;
  curriculum eligibility is explicit (only `UPDATE`+eligible tier may enter plans).
- **Static fixture verification**:
  - synthetic `old_source`/`new_source` pairs (newer/older/conflict/expired/future-date);
  - expected class + eligibility assertions; a `RECHECK` source must never be planned;
  - reproducibility: same fixtures → same classification JSON.
- **Exit criteria**: deterministic classifier; no network refresh; human review queue preserved.

## 4. Autonomous Research (contract only; no network)

- **Contract**: `m1_teacher.extensions.AutonomousResearchPort`,
  `ResearchTaskSpec(task_id, question, allowed_sources, max_steps=8, requires_network=False,
  evidence_refs)`; `plan_task(objective)`, `collect_evidence(task)`.
- **Design rules**: `requires_network` is fixed `False` in M1-A; `allowed_sources` is an explicit
  allow-list; outputs are evidence references, never auto-written into the learner model without
  independent assessment.
- **Static fixture verification (stub-level now)**:
  - `plan_task` on synthetic objectives returns a deterministic spec with `requires_network=False`
    and a bounded step budget;
  - `collect_evidence` must be rejected (`EXTENSION_NOT_IMPLEMENTED`) until a human-approved
    offline evidence source exists;
  - no URL fetching code is added.
- **Exit criteria**: contract + stub tests only; network research remains blocked pending human
  decision.

## 5. Teacher Improvement experiments (offline recording)

- **Contract**: `m1_teacher.extensions.TeacherImprovementStore` +
  `TeacherExperimentRecord(experiment_id, policy_version, initial_state_digest,
  behaviour_digest, result_digest, notes, evidence_class, real_effect_claim)`.
  `InMemoryTeacherImprovementLog` is a deterministic stub; `real_effect_claim=True` is rejected.
- **Experiment protocol (planned)**:
  1. freeze `policy_version` + initial learner state digest + fixture/scorer version;
  2. run both policy versions on the same synthetic student paths (same seeds/fixed timestamp);
  3. record behaviour digest (action/phase sequence) and result digest (assessment counts,
     mastery deltas, goal completion);
  4. classify all evidence `MOCK` + `DETERMINISTIC`; explicitly no real effect claim.
- **Static fixture verification**: fixture experiment records with known expected policy/state/
  result digests; deterministic re-run produces identical records.
- **Exit criteria**: experiment log round-trips deterministically; no claim of real improvement.

## 6. Gates and non-goals for the next phase

- No network/provider/LiveGate/API key, no real learner data (offline synthetic only) unless a
  separate human-approved scope change exists.
- Hidden scoring material remains scorer-only; teacher components and evidence artifacts must stay
  free of answer keys.
- The `m1a.v0` contract stays frozen; new features use additive contracts and their own versions.
- Human review (`HUMAN_REVIEWED`) is required before any claim stronger than `MOCK`/
  `DETERMINISTIC`; real teaching effectiveness stays `NOT_VERIFIED`.
- Web App, Interview Coach, Knowledge Freshness and Autonomous Research are currently `NOT_RUN`
  beyond the contract stubs in `m1_teacher/extensions/` (which fail closed with
  `EXTENSION_NOT_IMPLEMENTED`).
