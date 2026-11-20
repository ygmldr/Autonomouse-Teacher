# ADR-M1-001: Domain contracts and interface freeze (`m1a.v0`)

- **Status**: Proposed
- **Date**: 2026-11-20 (UTC)
- **Decision owner / decider**: LeadB; implemented by B-PR1a (m1a-contracts)
- **Baseline**: `main@3e7afee`, branch `work/m1a-mvp`
- **Related**: `docs/M1_ARCHITECTURE.md`, `m1_teacher/contracts/**`,
  `m1_teacher/knowledge/graph.py`, `m1_teacher/domains/cf_binary_search.py`

---

## 1. Context and background

M1-A builds an offline, deterministic teacher core on top of the M0 feasibility work. Five
implementation PRs follow: PR2 (learner model + memory), PR3 (diagnostic engine + curriculum
planner), PR4 (session engine + independent assessment/scorer), PR5 (offline end-to-end demo +
reports), then an independent review.

PR2–PR5 are implemented by different agents and partly in parallel. Without a frozen interface,
they would diverge on record shapes, error semantics, graph direction, event idempotency and —
most importantly — on **what the teacher is allowed to see**. Two red lines from the program
brief drive this ADR:

1. **Teacher / scorer isolation**: hidden scoring material (answer keys, expected outputs,
   correct option indices, rubric internals) must never be reachable from teacher-visible
   types, fixtures or modules. The independent scorer (B6) owns it.
2. **M0 isolation**: no `autoteacher_m0` imports, no network/provider/API-key/LiveGate usage,
   no reuse of M0 sessions as learner storage.

PR1 therefore freezes a minimal, discipline-agnostic contract (`m1a.v0`), a validated knowledge
graph, a domain registry and one real domain adapter, with executable tests as evidence.

---

## 2. Decision

We adopt the following decisions (D1–D12). All are implemented and test-enforced in PR1.

### D1 — Discipline-agnostic domain contract

The teacher core talks to learning domains only through `DomainAdapter`:
`domain_id`, `domain_version`, `knowledge_nodes()`, `prerequisite_edges()`, `objectives()`,
`assessment_items(node_id=None)`, `teaching_content(node_id, kind)`, `validate()`.
Domain-specific fields (e.g. CF "function_name" semantics) stay in domain data/adapters, not in
the teacher core. `KnowledgeNode`/`AssessmentItem` carry only generic metadata (difficulty,
assessment mode, item type, opaque `content_ref`/`scoring_spec_ref`).

### D2 — Frozen record types with strict, versioned serialisation

Records are stdlib dataclasses inheriting `Record`, with:

- `schema_version = "m1a.v0"` serialised on every payload;
- `created_at` (UTC ISO-8601, second precision, `Z` suffix) defaulting to `now_utc()`;
  `updated_at` where materialised mutable state needs it;
- lossless `to_dict`/`from_dict`/`to_json`/`from_json` round-trips;
- **fail-closed `from_dict`**: unknown fields, missing/wrong `schema_version`, missing required
  fields, invalid nested structures ⇒ `ValidationError`;
- construction-time validation of enums, numeric ranges, types, timestamps and cross-field
  invariants.

Enumerations are plain uppercase strings (`*_VALUES` tuples, `ENUM_VALUES` map), validated at
construction. They are not `enum.Enum` members so that JSON, SQLite rows and later PRs can
exchange plain strings without conversion.

### D3 — No hidden-answer material in teacher-visible types

No teacher-visible record has an answer/expected/correct/solution field.
`FORBIDDEN_TEACHER_FIELD_TOKENS = ("answer", "expected", "correct", "solution")` is enforced:

- at import time for all frozen record types;
- by serialisation tests;
- via positive leak tests on the real fixtures.

`AssessmentItem.scoring_spec_ref` is an **opaque string reference**, not scoring content.
Hidden specs live only in the fixture `scoring/` directory and are consumed exclusively by the
independent scorer introduced in PR4. `DomainAdapter` and `DomainRegistry` expose no grading or
answer capability. Teacher-side modules must not reference the hidden directory path (AST/text
scan test).

### D4 — `DomainAdapter` + `DomainRegistry` semantics

- `DomainRegistry.register(adapter)` rejects duplicates with `ConflictError`, validates that the
  object structurally implements `DomainAdapter`, and requires non-empty `domain_id` /
  `domain_version`.
- `get(domain_id)` raises `NotFoundError` for unknown domains; `list_domains()` is sorted and
  deterministic; registry instances are not global singletons.
- The registry stores adapters only; it exposes no scoring/answer functionality.

### D5 — Knowledge graph semantics

- Edge direction: `source_node_id` **is a prerequisite of** `target_node_id`.
- `HARD` = mandatory prerequisite (remediation required before target teaching);
  `SOFT` = helpful prerequisite (skippable by policy).
- The graph is a DAG: construction rejects duplicate node ids, unknown endpoints, self-loops,
  cycles and duplicate `(source, target, kind)` edges.
- `topological_order()` is deterministic; `prerequisite_closure(seeds, kinds)` returns transitive
  prerequisites and never includes the seeds themselves;
  `direct_prerequisites` / `hard_prerequisites` / `dependents` / `validate_objective` complete
  the read API.
- `validate_objective` rejects objectives targeting nodes absent from the graph (and, defensively,
  unknown `required_node_ids`).

### D6 — Fixture format and loader allow-list

`CFBinarySearchDomainAdapter(fixtures_root)` loads only four explicitly named files:

```
<fixtures_root>/domains/cf_binary_search/knowledge_graph.json
<fixtures_root>/domains/cf_binary_search/objectives.json
<fixtures_root>/domains/cf_binary_search/assessment_items.json
<fixtures_root>/domains/cf_binary_search/teaching_content.json
```

- **No directory enumeration / globbing**; hidden material next to these files is structurally
  unreachable. Tests prove a tree copied without the hidden directory yields an identical
  adapter.
- `domain_version` is a **domain-level** version declared once, at the top level of
  `knowledge_graph.json`. The other three files are linked by `schema_version` + `domain_id`
  only.
- Unknown keys **fail closed** at every level. As a documented forward-compatible tolerance, the
  loader accepts an optional repeated `domain_version` on the other three files only if it
  equals the graph version (B-PR1b fixtures do not use it).
- `assessment_items` items carry `public` as fixture-level data metadata; the frozen v0
  `AssessmentItem` does not expose `public` (forward-compatible, add-only later). The adapter
  loads all items and only filters by `node_id`.
- `options: null` for non-MCQ items is normalised to `[]`; `validate()` requires MCQ items to
  have ≥ 2 options and CODE items to declare `function_name`.
- `teaching_content(node_id, kind)` supports
  `EXPLAIN|HINT_L1|HINT_L2|HINT_L3|REVIEW|PRACTICE`; `PRACTICE` returns the practice item ids as
  a deterministic JSON list string. Unknown kinds fail closed with `ValidationError`; unknown
  nodes raise `NotFoundError`.

### D7 — Error taxonomy

Stable `.code` values: `VALIDATION_ERROR`, `NOT_FOUND`, `CONFLICT`,
`UNSUPPORTED_OPERATION` (base `M1A_ERROR`). Input/contract violations are `ValidationError`;
missing resources are `NotFoundError`. Codes are append-only.

### D8 — Repository protocols (implementation deferred to PR2)

`LearnerRepository` freezes snapshot/goal/event persistence with idempotent
`append_event(event) -> bool` (duplicate `event_id` returns `False`, never duplicates history)
and incremental `list_events(learner_id, since_seq)`. `SessionRepository` freezes
save/load/list for pause/resume/restart. PR2 implements SQLite; the event log is the source of
truth from which snapshots must be rebuildable.

### D9 — Offline / M0 isolation

No `autoteacher_m0` imports, no network modules, no API keys/provider config/LiveGate anywhere in
`m1_teacher/` (AST/text scan tests). The package is deterministic and filesystem-only.

### D10 — Evidence classification vocabulary

Reports use exactly `MOCK | DETERMINISTIC | HUMAN_REVIEWED | NOT_VERIFIED`. PR1 evidence is
deterministic test evidence + synthetic mock fixtures; all effectiveness claims are
`NOT_VERIFIED` in M1-A.

### D11 — Timestamps

UTC ISO-8601 with second precision and `Z` suffix. `+00:00` input is normalised to `Z`.
Sub-second precision and non-UTC offsets are rejected (fail-closed) to keep byte-stable
replay/reporting.

### D12 — Contract evolution rule

`m1a.v0` changes are **additive only**: new enum values, new optional fields with defaults, new
protocols/helpers, new error codes. Existing valid payloads stay valid. Any change must be
recorded in this ADR and in the architecture change log. Removing/renaming fields requires a new
contract version.

---

## 3. Alternatives considered

| Alternative | Why rejected |
|---|---|
| Pydantic models for records | Adds runtime model dependency and implicit coercion; the project only needs strict explicit validation. Stdlib dataclasses keep PR1 dependency-free and transparent for audit. |
| `enum.Enum` members stored on records | Serialisation/SQLite/later-PR interop becomes conversion-prone; the brief requires uppercase **strings** validated at construction. `*_VALUES` tuples keep JSON-native. |
| Frozen dataclasses / immutability | Safer, but PR2–PR4 legitimately build derived state and may mutate in-memory working copies; mutability keeps them unblocked. Validation-at-construction documented as the contract. |
| One big `domain.json` fixture file | Blurs the hidden-scoring separation and makes allow-listing harder. Four separate allow-listed files proved simpler to validate and to prove isolation. |
| Hidden `scoring/` content loaded by the adapter, filtered later | Unacceptable: would put answer material one attribute away from teacher code. Structural unreachability (never load, never list) is the only defensible boundary. |
| Generic untyped `dict` records | Would push shape errors into PR2–PR5; strict records catch integration bugs early. |
| Global singleton domain registry | Hidden global state harms test determinism and multi-domain isolation. Explicit instance registry. |
| Lazy fixture loading inside `validate()`/methods | Eager loading keeps failure early/fail-closed and guarantees the adapter never reads extra files at call time. |
| `UnsupportedOperationError` for unknown teaching-content kinds | LeadB ruling: unknown content kinds are caller input errors ⇒ `ValidationError` (fail closed, no silent empty string). |

---

## 4. Consequences

### Positive

- PR2–PR5 can develop in parallel against a stable, test-enforced contract.
- Teacher/scorer isolation is structural (allow-list loader + answer-free types + scans), not a
  convention.
- Deterministic timestamps, sorted registry listing and deterministic topo order give
  reproducible evidence for the independent review.
- Strict `from_dict` prevents silent schema drift across PRs.
- One real domain (CF binary search) validates the adapter/graph design before the planner and
  session engine arrive.

### Negative / costs

- Strict unknown-key rejection means fixture/record changes require deliberate contract updates
  (accepted: the point of the freeze).
- Dataclass field ordering required one documented normalisation: in `AssessmentResult`,
  `scorer_id` is declared before the optional `score`/`max_score` so the dataclass is
  constructible; **wire field names are unchanged** (field order is not part of the contract).
- Mutable records mean invalid states are reachable by in-place mutation; PR2–PR4 must build new
  records for persisted changes (documented limitation).
- Eager fixture loading keeps the whole domain in memory (small, bounded fixtures).
- `domain_version` tolerance adds a small amount of loader complexity for forward compatibility.

---

## 5. Compatibility with PR2–PR5

| PR | Consumes | Must not do |
|---|---|---|
| PR2 | `LearnerSnapshot`, `HistoryEvent`, `LearnerGoal`, `SessionState`, repository protocols | mutate frozen types' shapes; add non-additive fields; store answers |
| PR3 | `KnowledgeGraph`, `DomainAdapter`, `Reason`, `DiagnosisResult`, `CurriculumPlan`, `PlanStep` | read hidden scoring specs; infer answers from item metadata |
| PR4 | `SESSION_PHASE`, `TeachingAction`, `AssessmentResult`, `EvidenceReference`; adds independent scorer types | put hidden material into teacher-visible records; treat `EVAL_ERROR` as a learner error |
| PR5 | everything, CLI/demo, reports | claim real learning effects; skip evidence classes |

Additive extensions expected later (all allowed under D12): optional fields on records with
defaults (e.g. an optional `public` flag if ever needed), additional registry/helper methods,
scorer-local types (separate module, not teacher-visible), new `Reason.code` policy constants,
new error codes.

---

## 6. Contract deltas / documented implementation choices (all additive or non-breaking)

Recorded for the reviewer:

1. **`AssessmentResult` field declaration**: `scorer_id` is required by the frozen contract but
   listed after the optional `score`/`max_score`; it is declared **keyword-only** in that frozen
   position (a required field after defaults is otherwise invalid Python). Wire field names and
   serialised order are exactly as frozen. For the same reason, `created_at`/`updated_at` are
   keyword-only constructor arguments, except `updated_at` on state records which keeps its
   documented position.
2. **Optional repeated `domain_version`** on objectives/items/teaching-content files is tolerated
   (must match the graph version) as a forward-compatibility measure; final fixtures declare it
   once in `knowledge_graph.json`. Unknown *other* keys still fail closed.
3. **`domain_version` placement**: per LeadB final ruling, declared once in
   `knowledge_graph.json`; other files link via `schema_version` + `domain_id`.
4. **`options: null` normalisation** to `[]` in the adapter (fixtures use `null` for non-MCQ
   items); MCQ still requires ≥ 2 options.
5. **`teaching_content(kind="PRACTICE")`** returns a compact deterministic JSON list string
   (e.g. `["item.bs.mcq.001"]`); unknown kinds raise `ValidationError`.
6. **Convenience additions** beyond the minimal frozen API: `default_fixtures_root()`,
   `KnowledgeGraph.node_ids()/edges()/__len__`, `DomainRegistry.__len__/__contains__`,
   `M1AError.to_dict()`. No behaviour of frozen members changed.
7. **Timestamp normalisation**: `+00:00` accepted and normalised to `Z`; sub-second precision is
   rejected.
8. **Empty-identifier rejection**: identifiers/codes/titles/prompts must not be blank (stricter
   than the brief, which only marked them required). Considered safe for v0.

---

## 6b. D12 additive change log

Append-only log of additive contract changes allowed by **D12**; existing valid
payloads remain valid and no frozen member is renamed/removed.

| Date (UTC) | PR | Change | Compatibility |
|---|---|---|---|
| 2026-11-20 | B-PR2 | `HISTORY_EVENT_TYPE` += `ASSESSMENT_PREPARED` | Additive enum value; older payloads unaffected |
| 2026-11-20 | B-PR4 | `TEACHING_ACTION_KIND` += `SOCRATIC_QUESTION`, `ASK_CLARIFICATION` | Additive enum values used only by the vertical interview policy; CF/A paths never emit them |

B-PR4 note: the two new action kinds are teacher-visible but answer-free
(no `answer`/`expected`/`correct`/`solution` fields) and remain subject to the
same freeze checks (`FORBIDDEN_TEACHER_FIELD_TOKENS`, strict `from_dict`).

---

## 7. Open questions / unresolved

1. **`AssessmentItem.public`**: fixture metadata today. If PR4/PR5 needs item visibility tiers,
   add an optional field additively (default `True`) in a future revision; not part of v0.
2. **SOFT prerequisite policy**: when may a planner skip a soft gap? PR3 decision; graph exposes
   the data, PR1 does not encode policy.
3. **Mastery estimator choice** (deterministic heuristic vs BKT-like) and its evidence thresholds
   are PR2 decisions; `m1a.v0` only fixes the `MasteryEstimate` shape.
4. **Semantic scoring limits for `SHORT_ANSWER`**: PR4 must define conservative rules and the
   `NEEDS_REVIEW` fallback; PR1 fixes only the status vocabulary.
5. **`domain_version` bump policy**: when fixtures change semantically, whether to bump
   `domain_version` (and how the scorer references spec versions) is not yet defined.
6. **Additional domains**: whether M1-A needs a second real adapter; the registry contract is
   ready but untested beyond CF binary search.
7. **Machine-readable evidence classes**: reporting uses the fixed vocabulary, but records do not
   carry an evidence-class field. Add only if later PRs need it for automated auditing.
8. **Persistence schema/versioning**: PR2 owns SQLite schema/version migration; the repository
   protocols leave storage details free.

---

## 8. References

- `m1_teacher/contracts/types.py` — frozen records, enums, strict serialisation
- `m1_teacher/contracts/domain.py` — `DomainAdapter`, `DomainRegistry`
- `m1_teacher/contracts/repository.py` — persistence protocols
- `m1_teacher/contracts/errors.py` — error taxonomy
- `m1_teacher/knowledge/graph.py` — validated prerequisite DAG
- `m1_teacher/domains/cf_binary_search.py` — allow-listed CF fixture adapter + registry builder
- `tests/m1_teacher/test_contracts.py`, `test_knowledge_graph.py`, `test_domain_adapter.py`
- `fixtures/m1_teacher/` — synthetic fixtures (B-PR1b, CC0-1.0)
- `docs/M1_ARCHITECTURE.md` — architecture and data flow
