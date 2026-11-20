# M1-A Architecture & Contracts (initial draft)

- **Status**: initial draft for B-PR1 (`m1a.v0` interface freeze); later PRs may update this
  document append-only.
- **Owner of this revision**: B-PR1a / m1a-contracts.
- **Baseline**: `main@3e7afee`, worktree branch `work/m1a-mvp`.
- **Contract version**: `m1a.v0` (`m1_teacher.CONTRACT_VERSION`).
- **Scope**: offline, deterministic, no-network teacher core for M1-A. Nothing in this document
  claims real teaching effectiveness or a production launch.

---

## 1. Goals and non-goals (M1-A)

### 1.1 Goals

1. Freeze a **discipline-agnostic** teacher-core contract (`m1a.v0`) before parallel PR2/PR3
   implementation starts, so learner model, diagnostic engine, planner, session engine and
   independent scorer can be developed against stable types.
2. Provide a **validated knowledge graph** (prerequisite DAG, HARD/SOFT edge semantics,
   objective validation) and a **domain registry** with a real adapter for the
   `cf_binary_search` domain.
3. Enforce **teacher / scorer isolation**: no teacher-visible type may carry answer keys,
   expected outputs or correct options. Hidden scoring material stays outside the
   teacher-visible surface and is only consumed by the independent scorer (B6, PR4).
4. Preserve **M0 isolation**: the M1-A core does not import `autoteacher_m0`, does not read
   credentials/provider config and never performs network or LiveGate calls.
5. Keep every result **deterministic and offline**, with executable tests as evidence.

### 1.2 Non-goals

- No real learner adaptation, mastery estimator or planning policy in PR1 (PR2/PR3).
- No session state machine execution, no CLI/demo (PR4/PR5).
- No semantic grading of open-ended answers; the independent scorer may only return
  `NEEDS_REVIEW` when it cannot decide deterministically.
- No network providers, API keys, LiveGate, or real learner data (ever in M1-A).
- No M0 modifications and no reuse of M0 DSH sessions as the student database.

---

## 2. Module layering (B1–B8) and PR mapping

M1-A is decomposed into eight capability blocks (B1–B8) delivered by five PRs plus an
independent review:

| Block | Capability | Delivered by |
|---|---|---|
| **B1** | Learning Domain Contracts — `DomainAdapter`, `KnowledgeNode`, `PrerequisiteEdge`, `LearningObjective`, `AssessmentItem`, `AssessmentResult`, `TeachingAction`, `EvidenceReference`; knowledge graph with dependency/difficulty/assessment-mode metadata; no CF-specific fields hard-coded in the teacher core | **PR1** (this revision) |
| **B2** | Learner Model — mastery/confidence/evidence count/completed practice/error types/recent learning & review times/ability-change history; observed vs inferred evidence; deterministic heuristic or BKT; persistence/restore/idempotency/error-input validation | **PR2** |
| **B3** | Diagnostic Engine — entry diagnosis and stepwise probing; outputs next diagnostic item, selection reason and the knowledge hypothesis to test; never reads hidden answers; insufficient evidence ⇒ `INSUFFICIENT_EVIDENCE` | **PR3** |
| **B4** | Curriculum Planner — selects activities by dependency/mastery/goal/time; supports prerequisite remediation, current-node teaching, practice+feedback, review, reassessment, goal-completion judgement; structured `Reason` explains why this node/step | **PR3** |
| **B5** | Teaching Session Engine — `DIAGNOSE→TEACH→PRACTICE→ASSESS→UPDATE→REVIEW` state machine allowing skip/backtrack/re-entry; every transition has explicit conditions and tests | **PR4** |
| **B6** | Assessment & Evaluation — independent scorer (`CORRECT/INCORRECT/PARTIAL/NEEDS_REVIEW/EVAL_ERROR`); deterministic judging first; open-ended answers must not be faked as semantically correct (→ `NEEDS_REVIEW`); scorer decoupled from planner to prevent hidden-label exploitation | **PR4** |
| **B7** | Memory & Learning History — learner state and learning history as separate concerns; SQLite/equivalent persistence; state rebuildable from events and consistency-checked; M0 DSH sessions are not the student database | **PR2** |
| **B8** | Offline Demonstration — CLI/lightweight local UI: create learner → diagnose → plan → teach/practice → score/explain error → mastery change → interrupt/resume → next recommendation; no web requirement | **PR5** |

**Dependency order**

```
PR1 (contracts) ──> PR2 (B2/B7) ─┐
                └─> PR3 (B3/B4) ─┴─> PR4 (B5/B6) ──> PR5 (B8) ──> independent review
```

PR2 and PR3 may run in parallel after PR1; PR4 depends on both (it updates state built by PR2
and actions produced by PR3); PR5 depends on all previous PRs. The independent reviewer works
on the frozen final SHA and must not modify implementation files.

---

## 3. Repository layout (B-PR1 additions)

```
m1_teacher/
  __init__.py                      # CONTRACT_VERSION="m1a.v0", public re-exports
  contracts/
    __init__.py                    # re-exports the frozen surface
    errors.py                      # M1AError + Validation/NotFound/Conflict/UnsupportedOperation
    types.py                       # Record base, enums, all frozen records
    domain.py                      # DomainAdapter Protocol, DomainRegistry
    repository.py                  # LearnerRepository / SessionRepository Protocols
  knowledge/
    __init__.py
    graph.py                       # KnowledgeGraph (validated prerequisite DAG)
  domains/
    __init__.py
    cf_binary_search.py            # CFBinarySearchDomainAdapter, build_default_registry
tests/m1_teacher/
  conftest.py                      # repo_root / fixtures_dir / cf_domain_dir fixtures
  test_contracts.py                # strict schema/enum/range/roundtrip tests
  test_knowledge_graph.py          # graph validation/topology/closure/objective tests
  test_domain_adapter.py           # adapter/registry/hidden-isolation/static-scan tests
  test_fixtures_cf.py              # B-PR1b fixture validation (owned by m1a-fixtures)
fixtures/m1_teacher/               # B-PR1b synthetic fixtures (owned by m1a-fixtures)
  domains/cf_binary_search/{knowledge_graph,objectives,assessment_items,teaching_content}.json
  domains/cf_binary_search/scoring/<item_id>.json   # HIDDEN scoring specs
docs/M1_ARCHITECTURE.md            # this document
docs/M1_ADR_001_DOMAIN_CONTRACTS.md
```

---

## 4. Frozen public contract `m1a.v0`

### 4.1 Record base (`m1_teacher.contracts.types.Record`)

- `schema_version = "m1a.v0"` on every record; serialised first in `to_dict()`.
- UTC ISO-8601 timestamp with second precision and `Z` suffix; `created_at` defaults to
  `now_utc()` and may be supplied explicitly. `+00:00` input is normalised to `Z`.
  Records representing mutable materialised state (`MasteryEstimate`, `LearnerSnapshot`,
  `SessionState`) additionally carry `updated_at`.
- `to_dict() / from_dict() / to_json() / from_json()` round-trip losslessly.
- `from_dict()` is **strict**: unknown fields, missing or mismatched `schema_version`, missing
  required fields and malformed nested records raise `ValidationError`. Omitted optional fields
  fall back to their documented defaults.
- Enumerations are plain uppercase strings validated at construction; values are frozen as
  `*_VALUES` tuples and in `ENUM_VALUES`.
- Numeric fields enforce the documented ranges (difficulty 1–5, mastery/confidence 0–1,
  edge weight 0–1, non-negative counters, `0 < max_score` and `0 ≤ score ≤ max_score`).
- Cross-field invariants are validated: objective success criteria keys/ranges/subset,
  assessment score range, snapshot mastery key/`node_id` consistency.
- Records are mutable dataclasses (value objects validated at construction). Producers should
  build new records rather than mutate; mutation bypasses validation.

### 4.2 Enumerations

| Enum | Values |
|---|---|
| `ASSESSMENT_STATUS` | `CORRECT`, `INCORRECT`, `PARTIAL`, `NEEDS_REVIEW`, `EVAL_ERROR` |
| `EVIDENCE_SOURCE` | `OBSERVED`, `INFERRED` |
| `EDGE_KIND` | `HARD`, `SOFT` |
| `ASSESSMENT_MODE` | `DETERMINISTIC_JUDGE`, `RULE_RUBRIC`, `HUMAN_REVIEW_REQUIRED` |
| `ITEM_TYPE` | `MCQ`, `CODE`, `SHORT_ANSWER` |
| `TEACHING_ACTION_KIND` | `DIAGNOSE`, `EXPLAIN`, `HINT`, `PRACTICE`, `REVIEW`, `RETEACH`, `REASSESS`, `GOAL_COMPLETE`, `SESSION_PAUSE`, `SESSION_RESUME` |
| `SESSION_PHASE` | `DIAGNOSE`, `TEACH`, `PRACTICE`, `ASSESS`, `UPDATE`, `REVIEW`, `COMPLETE`, `PAUSED` |
| `HISTORY_EVENT_TYPE` | `SESSION_STARTED`, `PLAN_CREATED`, `DIAGNOSIS_COMPLETED`, `ITEM_PRESENTED`, `RESPONSE_SUBMITTED`, `ASSESSED`, `MASTERY_UPDATED`, `ACTION_TAKEN`, `SESSION_PAUSED`, `SESSION_RESUMED`, `GOAL_COMPLETED`, `ERROR` |
| `DIAGNOSIS_STATUS` | `READY`, `INSUFFICIENT_EVIDENCE` |
| `GOAL_STATUS` | `ACTIVE`, `COMPLETED`, `PAUSED` |

### 4.3 Records (field names are the contract)

`KnowledgeNode`, `PrerequisiteEdge`, `LearningObjective`, `AssessmentItem`, `AssessmentResult`,
`Reason`, `TeachingAction`, `EvidenceReference`, `MasteryEstimate`, `LearnerSnapshot`,
`LearnerGoal`, `HistoryEvent`, `SessionState`, `PlanStep`, `CurriculumPlan`,
`DiagnosisResult` — see `m1_teacher/contracts/types.py` for the authoritative field definitions
and docstrings, and the ADR for freeze/versioning rules.

Key semantic notes:

- `Reason{code, node_ids, detail, policy_version}` is the structured explanation unit used by
  PR3/PR4 for every decision; reason codes are stable uppercase policy codes.
- `HistoryEvent.event_id` is the append-only idempotency key; `seq` orders a learner's events.
- `SessionState.phase` defaults to `PAUSED` so persistence never implies "running".
- `AssessmentItem` carries **no answer material** — `scoring_spec_ref` is an opaque string
  reference only (see §6).

### 4.4 Protocols

- `DomainAdapter` — `domain_id`, `domain_version`, `knowledge_nodes()`,
  `prerequisite_edges()`, `objectives()`, `assessment_items(node_id=None)`,
  `teaching_content(node_id, kind)`, `validate()`. No scoring/answer capability exists on the
  interface.
- `DomainRegistry` — `register(adapter)` (duplicate `domain_id` ⇒ `ConflictError`),
  `get(domain_id)` (missing ⇒ `NotFoundError`), `list_domains()` (sorted, deterministic).
- `LearnerRepository` — `get_snapshot`, `upsert_snapshot`, `append_event` (returns `False`
  for a duplicate `event_id`), `get_event`, `list_events(learner_id, since_seq=None)`,
  `get_goal`, `upsert_goal`.
- `SessionRepository` — `save_session`, `load_session`, `list_sessions`.

### 4.5 Error taxonomy (`m1_teacher.contracts.errors`)

`M1AError` base with stable `.code`; subclasses `ValidationError` (`VALIDATION_ERROR`,
fail-closed input/contract failures), `NotFoundError` (`NOT_FOUND`), `ConflictError`
(`CONFLICT`), `UnsupportedOperationError` (`UNSUPPORTED_OPERATION`). Codes are append-only.

---

## 5. Domain knowledge semantics

### 5.1 Knowledge graph

- Nodes are `KnowledgeNode` records with unique `node_id`, difficulty 1–5 and an
  `assessment_mode` that tells B6 how the node is judged.
- Edges are directed `PrerequisiteEdge` records: **`source_node_id` is a prerequisite of
  `target_node_id`**.
  - `HARD`: mandatory prerequisite; remediation is required before teaching the target
    (PR3 planner policy).
  - `SOFT`: helpful prerequisite; may be skipped when mastery/evidence or time budget says so.
- Construction validates: unique node ids, existing edge endpoints, no self-loops, no cycles
  (DAG) and no duplicate `(source, target, kind)` edges. Cyclic/invalid domains fail closed
  at load time.
- `topological_order()` is deterministic (node insertion order breaks ties) and guarantees
  every prerequisite precedes its dependants.
- `prerequisite_closure(node_ids, kinds=("HARD","SOFT"))` returns all transitive prerequisites
  of the seeds; seed nodes are never included (even if one seed is a prerequisite of another).
- `direct_prerequisites`, `hard_prerequisites` (direct HARD sources), `dependents` and
  `validate_objective` complete the frozen read API.

### 5.2 Domain adapter and fixtures

`CFBinarySearchDomainAdapter` loads exactly four allow-listed JSON files from
`<fixtures_root>/domains/cf_binary_search/`:

| File | Top-level keys | Notes |
|---|---|---|
| `knowledge_graph.json` | `schema_version`, `domain_id`, `domain_version`, `nodes`, `edges` | **`domain_version` is declared only here, once per domain** |
| `objectives.json` | `schema_version`, `domain_id`, `objectives` | linked via `schema_version` + `domain_id` |
| `assessment_items.json` | `schema_version`, `domain_id`, `items` | teacher-visible item metadata only, no answers |
| `teaching_content.json` | `schema_version`, `domain_id`, `nodes` | per-node `EXPLAIN/HINT_L1/HINT_L2/HINT_L3/PRACTICE_ITEM_IDS/REVIEW` |

Fixture contract rules (final):

- `schema_version` is always `"m1a.v0"`; `domain_id` is always `"cf_binary_search"`;
  `domain_version` is a **domain-level** version and appears once, at the top level of
  `knowledge_graph.json` (currently `"0.1.0"`). The other three files are associated through
  `schema_version` + `domain_id`.
- Unknown keys **fail closed** everywhere (file level, node/edge/objective/item level,
  teaching-content level). As a documented forward-compatible tolerance the loader also accepts
  an optional repeated `domain_version` on the other three files, but only if it equals the
  graph's `domain_version`; the B-PR1b fixtures do not use it.
- The loader uses an explicit path allow-list and never enumerates the domain directory, so
  hidden material in `scoring/` is structurally unreachable. A test copies the fixture tree
  without `scoring/` and proves the adapter behaves identically.
- `options: null` (non-MCQ items) is normalised to `[]`; `MCQ` items must have ≥ 2 options
  (checked by `adapter.validate()`).
- `item.public` is **fixture-level metadata only**: the frozen `m1a.v0` `AssessmentItem` does not
  expose a `public` field (forward-compatible; a later PR may add it only additively). The
  adapter loads all items and filters by `node_id` only.
- `assessment_items` may set `deterministic: false` for rubric-based items (B-PR1b fixtures:
  13 deterministic + 3 `SHORT_ANSWER` rubric items that can yield `NEEDS_REVIEW`).
- `teaching_content(node_id, kind)` supports `EXPLAIN|HINT_L1|HINT_L2|HINT_L3|REVIEW|PRACTICE`;
  `PRACTICE` returns the practice item ids as a deterministic JSON list string
  (e.g. `["item.bs.mcq.001"]`). Unknown kinds fail closed with `ValidationError`; unknown nodes
  raise `NotFoundError` (this includes unknown `assessment_items(node_id=...)` filters).
- Domain registration defaults to `<repo>/fixtures/m1_teacher` and can be overridden by an
  explicit argument or `M1_TEACHER_FIXTURES`.

---

## 6. Teacher / scorer isolation (hidden-answer boundary)

- All records in `m1_teacher.contracts.types` are **teacher-visible**; none may contain
  `answer`, `expected`, `correct`, `solution` fields. `FORBIDDEN_TEACHER_FIELD_TOKENS` records
  the rule and the module raises at import time if a violating field is added; tests enforce it.
- Hidden scoring specs live in `fixtures/m1_teacher/domains/cf_binary_search/scoring/` and are
  readable only by the **independent assessment scorer** (B6, PR4). Teacher-side modules never
  mention that path (enforced by an AST/text scan over
  `m1_teacher/contracts`, `m1_teacher/knowledge`, `m1_teacher/domains`).
- The scorer ingests learner responses and returns `AssessmentResult` (`CORRECT/INCORRECT/
  PARTIAL/NEEDS_REVIEW/EVAL_ERROR`) plus `EvidenceReference`; the teacher core only consumes
  those teacher-visible outputs. `EVAL_ERROR` must never be counted as a learner error (PR4).
- An MCQ correct option index, expected function outputs and rubric concept groups never
  appear in teacher-visible serialisations (covered by positive leak tests against the real
  fixtures).

---

## 7. Data flow (target closed loop, B3–B7)

```
Goal (LearnerGoal: learner_id × objective_id)
  → Diagnose (B3: DiagnosisResult + next item + structured Reason; insufficient evidence allowed)
  → Plan (B4: CurriculumPlan of ordered PlanSteps, each with Reason; prerequisite-first)
  → Session teaching (B5: TeachingAction per turn, content from DomainAdapter.teaching_content)
  → Response + independent assessment (B6: AssessmentResult from hidden specs; EVAL_ERROR isolated)
  → Update (B2/B7: mastery/confidence/evidence count via observed evidence only; append HistoryEvent;
             rebuildable LearnerSnapshot, idempotent by event_id)
  → Review / next recommendation (B4: REASSESS / REVIEW / GOAL_COMPLETE, deterministic)
```

All state transitions are persisted through `LearnerRepository` + `SessionRepository`
(PR2 SQLite implementation), so pause/resume/restart recovery is possible without holding state
in memory only.

---

## 8. Session state machine (overview; exact transition conditions in PR4)

`SESSION_PHASE` values: `DIAGNOSE`, `TEACH`, `PRACTICE`, `ASSESS`, `UPDATE`, `REVIEW`,
`COMPLETE`, `PAUSED`.

Nominal loop: `DIAGNOSE → TEACH → PRACTICE → ASSESS → UPDATE → REVIEW → next activity` with
`REVIEW` able to route back to `DIAGNOSE`/`TEACH`/`PRACTICE` and `COMPLETE` closing the goal.
Skip/backtrack/re-entry (e.g. `ASSESS → TEACH`, `REVIEW → PRACTICE`) is allowed only when
explicit conditions hold; `PAUSED` may be entered from active phases and resumed to the prior
activity. PR4 owns the authoritative transition table and tests.

---

## 9. Isolation, determinism and evidence classification

**Hard boundaries**

- No import of `autoteacher_m0` anywhere under `m1_teacher/` (test-enforced).
- No network modules, no HTTP/provider SDK imports (AST scan test-enforced).
- No API keys, provider configuration, LiveGate or real learner data; fixtures are synthetic,
  self-authored and offline.
- No hidden scoring labels in teacher-visible types, fixtures' public files, or test snapshots.
- M0 artifacts (`plugins/`, `config/`, `scripts/`, `src/autoteacher_m0/`, existing docs/tests)
  are not modified by any M1-A PR.

**Evidence classification** (fixed vocabulary for M1-A reports):

| Class | Meaning |
|---|---|
| `MOCK` | Simulated/mock components or synthetic inputs; not real model behaviour |
| `DETERMINISTIC` | Reproducible offline computation/assertion (e.g. pytest evidence, fixture checks) |
| `HUMAN_REVIEWED` | Manually inspected outcome by an independent human/agent reviewer |
| `NOT_VERIFIED` | Claimed/planned but not yet demonstrated; must not be reported as PASS |

PR1 evidence is `DETERMINISTIC` (268 passing tests at this revision) plus `MOCK` fixtures; there
is no `HUMAN_REVIEWED` outcome yet, and all learning/teaching-effectiveness claims remain
`NOT_VERIFIED` for M1-A.

---

## 10. Known limitations / open questions

1. Only one domain adapter (`cf_binary_search`) exists; multi-domain registration is supported by
   the registry but untested against a second real domain.
2. Mastery estimation, diagnostic selection, planning and session transitions are **not
   implemented** in PR1 — only their frozen data contracts/protocols exist.
3. `SOFT` prerequisite remediation policy (when a soft gap may be skipped) is a PR3 decision.
4. Semantic scoring of `SHORT_ANSWER` is intentionally conservative; the scorer must return
   `NEEDS_REVIEW` rather than guessing.
5. `AssessmentItem.public` is fixture metadata only in v0; if later PRs need it, they must add it
   additively and bump/review the contract (documented in the ADR).
6. Records are mutable dataclasses; PR2–PR4 must treat them as value objects and rebuild rather
   than mutate persisted state in place.
7. No contract for evidence classification fields on records yet (it is a report-level
   vocabulary); adding machine-readable evidence classes would be an additive change.
8. Fixture provenance is synthetic/CC0-1.0 per B-PR1b README; no real course material is used.

---

## 11. PR dependency and ownership summary

| PR | Blocks | Contract usage | May change `m1a.v0`? |
|---|---|---|---|
| PR1 | B1 | defines `m1a.v0` | freezes it |
| PR2 | B2, B7 | `LearnerSnapshot`, `HistoryEvent`, repository protocols | no; additive only with ADR note |
| PR3 | B3, B4 | `KnowledgeGraph`, `DomainAdapter`, `Reason`, `DiagnosisResult`, `CurriculumPlan` | no; additive only |
| PR4 | B5, B6 | `SESSION_PHASE`, `AssessmentResult`, `TeachingAction`; new scorer types | may add scorer-only types; teacher-visible types add-only |
| PR5 | B8 | all of the above | no; docs/evidence only |

Any future change to `m1a.v0` must be **additive only** (new enum values, new optional fields
with defaults, new protocols/helpers), must be recorded in
`docs/M1_ADR_001_DOMAIN_CONTRACTS.md`, and must keep all previously valid JSON payloads valid.

---

## 12. Change log

| Date (UTC) | Revision | Change |
|---|---|---|
| 2026-11-20 | B-PR1 initial | Contract freeze `m1a.v0`, knowledge graph, registry, CF adapter, tests, initial architecture and ADR |
