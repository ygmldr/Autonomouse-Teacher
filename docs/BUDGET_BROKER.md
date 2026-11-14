# Budget bookkeeping broker — protocol v1 (offline synthetic only)

## Status and trust boundary

This is a fixed-policy NDJSON/stdio **bookkeeping** bridge for independent offline
fixtures. It is NOT a Key proxy, human-authorization broker, OS sandbox, provider
usage authenticator, LiveGate, or permission to run a model. `dispatch_allowed`
means only **this logical request was recorded for the first time**. It cannot
unlock production Gate/Adapter/primary-route policy. External provider execution
cannot be made exactly-once merely by returning a JSON response.

Only a trusted, frozen launcher selects the startup config, DB and unique scope.
Clients cannot change paths, scope, limits, route/model definitions, prices, fee
rules, Python modules or commands. No message accepts source code. Broker code
has no networking, subprocess, eval, pickle, credential or environment discovery.
Tests may launch it as a child, exclusively inside the existing restricted
container. All route prices are explicit **synthetic fixtures**, never live prices.

## Startup interface (separate from the root project CLI)

```text
/opt/python/bin/python3.11 -B -m autoteacher_m0.accounting.broker --config /work/startup.json
```

The config is a bounded UTF-8 JSON object, no YAML or dynamic expressions. Every
key below is required, unknown keys are rejected. Money/rates are nonnegative
**decimal strings**, not JSON floats or scientific notation. The absolute DB
path is frozen at startup; its parent must already be accessible to the trusted
launcher. Policy (including route price/fee/usage rules) is persisted and compared
on restart; drift fails startup before stdin processing. Existing BudgetLedger
reservations/counters are preserved by an additive table migration.

```json
{
  "v": 1,
  "synthetic": true,
  "db_path": "/work/budget.sqlite3",
  "scope_id": "fixed-offline-scope",
  "max_messages": 4096,
  "limits": {
    "soft_usd": "3", "hard_usd": "10", "per_call_usd": "0.20",
    "max_requests": 50, "max_input_tokens": 2500000,
    "max_output_tokens": 600000, "max_steps": 8, "max_retries": 1
  },
  "routes": [{
    "route_id": "offline-test-only", "model": "fixture-v1",
    "price": {
      "version": "synthetic-broker-v1", "input_per_million": "1",
      "output_per_million": "2", "cached_input_per_million": "0.5",
      "source": "synthetic offline fixture", "captured_at": "2026-11-13T00:00:00Z"
    },
    "known_extra_fee_usd": "0.001",
    "usage_policy": {"cache_write": "input_rate", "reasoning": "included_in_output"}
  }]
}
```

`usage_policy.cache_write='input_rate'` is an explicit fixture billing rule, not
an assumption that real cache writes are free or match ordinary input. Other
cache-write rules are unsupported and refused at startup. Reasoning mode must
be `included_in_output` (do not add reasoning again) or `additional_output`
(add separate reasoning tokens at the configured output rate). Without an exact
known rule the route must not be used. Real providers require separately reviewed
rules and source evidence, not renaming this fixture route. Known per-request fee
for NEW reservations is fixed by startup; client messages cannot lower it. A
legacy pending reservation MUST settle/fail with its persisted `known_fee` and
`price_json`, not a later startup fee/rate. New route policy never reprices an
already-dispatched request. Actual total invoice, if
provided by a trusted test/controller, already includes fees and is not charged
twice. The broker cannot authenticate an invoice or prevent a malicious trusted
caller from lying about usage/starting a new DB; do not give candidate code this
controller/DB/channel capability.

## NDJSON transport and response envelope

- One request / one response per line; maximum request **16384 bytes including LF**.
- Strict UTF-8, one plain object, duplicate keys/NaN/Infinity/floats rejected.
- `v` exactly integer 1, `id` 1..96 ASCII `[A-Za-z0-9][A-Za-z0-9_.:-]*`.
- Token counters are integers 0..1000000000 (not booleans); reservation bounds
  strictly positive. No coercion of strings, negatives or floats to counters.
- No stdout banner/logs; response has `v,id,ok,code,dispatch_allowed,duplicate`.
  Optional `reservation_id`, `reservation`, `settlement`, `snapshot` are pure
  bounded JSON. Money is always a decimal string. All errors use fixed codes and
  no exception payload, invalid input, paths, SQL or client text is echoed.
- Oversized/unterminated frames or broken output terminate fail-closed; no grant
  is emitted. EOF closes cleanly; pending records are not refunded. Protocol
  errors on an otherwise bounded line can return an error and continue.
- Startup/protocol stdout failures have nonzero exit; normal EOF exit 0.

### Reserve

```json
{"v":1,"id":"stream-001-reserve","op":"reserve","task_id":"session-001","route_id":"offline-test-only","model":"fixture-v1","purpose":"conversation","input_tokens":1200,"output_tokens":2048,"retry":false}
```

All keys required, no optional policy override. Purpose is `conversation`,
`compaction`, or `judge`; every logical stream including retry/compaction/Judge
needs a new ID/reservation in the **same fixed scope**. `task_id` must be the
stable parent task/session attribution; callers must not generate a new task ID
to evade task step/retry caps. The client supplies complete assembled context
and billed-output upper bounds; broker cannot prove tokenizer/input completeness.
A bounded explicit caller may not claim transport attempts hidden within a
stream are separately guarded.

First committed reservation reply: `ok=true, code='RESERVED',
dispatch_allowed=true, duplicate=false`, plus `reservation_id` and reservation.
Commit is synchronous and happens **before** stdout. Same ID and exact canonical
request replay: same reservation, `dispatch_allowed=false,
code='DUPLICATE_NO_DISPATCH', duplicate=true`, even after restart or a lost ack.
The client **must not dispatch** on replay or if ack is absent. This conservative
at-most-once grant may strand a paid reservation; it deliberately does not try to
recover external exactly-once dispatch. Same ID / different body is
`IDEMPOTENCY_CONFLICT`, never a new reservation. Budget denial is persisted in the
journal and latches this broker scope blocked; compaction/error handlers cannot
catch it then obtain a main-stream grant. No reset/refund policy endpoint exists.

### Settle / fail

```json
{"v":1,"id":"stream-001-settle","op":"settle","reservation_id":"<returned-id>","usage":{"inputTokens":100,"cacheReadTokens":20,"cacheWriteTokens":10,"outputTokens":40,"reasoningTokens":5,"totalTokens":170,"actual_cost_usd":null}}
```

`op='fail'` has the same shape. `usage` may be null (failed/missing response), or
an object containing only the fields shown; individual counters may be absent or
null (explicitly incomplete, never free). A complete authoritative fixture above
has total input **100+20+10=130**, cache-read 20, ordinary-rate input 110;
`included_in_output` bills output 40 (not 45). `totalTokens`, when supplied with
complete counters, must match billed input+output under the fixed mode. Other
unknown usage fields/rules are rejected with reservation still pending.

Missing/incomplete dimensions use at least the full corresponding reservation
bound, no cache discount from incomplete input, and an estimated no-invoice
settlement costs **at least the whole reservation**, including known fees and
worst cache path. This floor applies to missing/estimated **usage dimensions**
(`Usage.estimated=true`), not merely to `cost_kind='estimated'`: complete trusted
token counts without a dollar invoice may settle below the reservation using the
known snapshot. Small monetary replies use plain decimal (for example
`"0.0000005"`), never scientific notation. Fail with no usage does not zero/refund a possibly billed call.
Actual `actual_cost_usd`, when a decimal string, is an authoritative inclusive
fixture invoice under a **trusted caller assumption**, even if tokens are
missing. Overruns are recorded honestly, never clipped, and persistently block
future reservations across processes/routes. Reasoning `additional_output`
requires its count or falls back to the full output bound; it is not assumed 0.

Settlement replay using the same ID/body is idempotent. A new ID targeting an
already settled reservation returns `ALREADY_SETTLED`; no double charge/refund.
`settle` and `fail` never return `dispatch_allowed=true`.

### Snapshot

```json
{"v":1,"id":"inspect-001","op":"snapshot"}
```

Returns persisted request/token totals, pending/committed/spent/reserved Decimal
costs, blocked/soft-budget state and route IDs. Snapshot itself creates no
reservation and never authorizes dispatch. Replayed ID returns its original
snapshot (with `duplicate=true`), not a new read. Journal entries have a fixed
startup `max_messages` bound; hitting it refuses fresh messages, without deleting
old identity records or refunding pending work.

## Error codes

`INVALID_MESSAGE`, `FRAME_TOO_LARGE`, `INCOMPLETE_FRAME`, `ROUTE_BLOCKED`,
`BUDGET_EXCEEDED`, `IDEMPOTENCY_CONFLICT`, `UNKNOWN_RESERVATION`,
`ALREADY_SETTLED`, `INVALID_USAGE`, `MESSAGE_LIMIT`, `INTERNAL_ERROR`,
`STARTUP_BLOCKED`. None are permission grants. Non-protocol I/O/DB errors never
return arbitrary exception messages or fail open. A successful pipe write is not
proof a client received the response or a provider billed a request.

## Implementation and evidence

Protocol contract was published before implementation to plugin/Lead. The fixed
startup module is [broker.py](</root/Autonomous Teacher/src/autoteacher_m0/accounting/broker.py>),
usage conversion is [broker_usage.py](</root/Autonomous Teacher/src/autoteacher_m0/accounting/broker_usage.py>),
and [ledger.py](</root/Autonomous Teacher/src/autoteacher_m0/accounting/ledger.py>)
adds durable policy/message tables plus thread-local nested SAVEPOINT composition
under the existing `BEGIN IMMEDIATE` transaction with `synchronous=FULL`. Journal
and reservation/settlement commit together, before emitting an acknowledgement.
The legacy public reserve/settle/fail/snapshot ABI remains available. Internal
`journal_once` callbacks are trusted Python implementation code, **not** accepted
from any protocol message. No second floating-point ledger exists.

### Initial snapshot results (before independent migration audit)

The following 132-case historical snapshot did NOT catch the legacy-fee defect
reported below. Its original manifest/raw evidence are preserved, not rewritten.
The corrected delivery and superseding manifest are described in the audit
correction section at the end of this document.

- Initial one invocation: **132 passed in 4.40s, ruff All checks passed, exit 0**.
  This includes the retained **63** accounting/evaluation/Mock-pair compatibility
  tests and **69** new broker/stdio cases; do NOT add historical pass counts.
  Earlier evolving snapshots (125 and 127 passed) are preserved as earlier runs,
  not additional independent cases.
- [Final pytest/lint log](</root/Autonomous Teacher/artifacts/budget-broker/final2.log>),
  [exact argv](</root/Autonomous Teacher/artifacts/budget-broker/final2.argv>),
  [exit](</root/Autonomous Teacher/artifacts/budget-broker/final2.exit>) and
  [exact-name empty container query](</root/Autonomous Teacher/artifacts/budget-broker/final2.containers>).
- [Unit cases](</root/Autonomous Teacher/tests/unit/accounting/test_broker.py>)
  cover strict schemas, duplicate keys, 16KiB framing, float/NaN/type rejection,
  fixed startup policy drift, unknown usage, disjoint cache conversion,
  included/additional reasoning, incomplete usage floors, known fees, actual
  inclusive invoices, plain tiny Decimal replies, legacy scientific-policy
  compatibility, atomic journal rollback, lost acknowledgement, one grant across
  concurrent brokers, two-route shared caps, persistent denial/overrun,
  request/step/retry bounds, duplicate settlement and fixed sanitized exceptions.
- [Real child-process tests](</root/Autonomous Teacher/tests/integration/budget_bridge/test_stdio.py>)
  start the actual module over stdin/stdout, restart against one DB, compete from
  four independent OS processes, kill a known test child after ack, and crash a
  child inside an uncommitted transaction. They assert no duplicate dispatch grant,
  no duplicate charge/refund, pending survival, pre-ack rollback, fixed startup
  errors, clean EOF/nonzero protocol exits and child cleanup.
- [Independent raw stdio transcript](</root/Autonomous Teacher/artifacts/budget-broker/transcript.log>)
  preserves each real child's argv, request/reply, stderr and exit. A restart
  replays reserve with `dispatch_allowed=false`; complete 7+0+0 input / 3 output
  settles to synthetic `0.001013`; missing-usage fail charges full `0.0012`; a
  distinct settlement ID cannot settle again. Final state is two recorded
  bookkeeping requests, no pending, synthetic cost `0.002213`, **zero model calls**.
  Purpose `compaction` in this transcript is only a bookkeeping label, not an
  actual DSH compaction invocation.
- [Transcript argv](</root/Autonomous Teacher/artifacts/budget-broker/transcript.argv>),
  [exit](</root/Autonomous Teacher/artifacts/budget-broker/transcript.exit>) and
  [empty container query](</root/Autonomous Teacher/artifacts/budget-broker/transcript.containers>).
  [Probe source](</root/Autonomous Teacher/artifacts/budget-broker/stage/broker_probe.py>)
  ran inside the container only, never on the host.
- [Exact source hashes](</root/Autonomous Teacher/artifacts/budget-broker/source.sha256>)
  and [evidence manifest](</root/Autonomous Teacher/artifacts/budget-broker/manifest.json>)
  bind this delivery; later Git SHA must be externally associated with this
  snapshot, not retroactively inserted into earlier evidence.

### Actual isolation and remaining limitations

All new project code, Python/pytest/ruff and child processes ran only inside the
preverified immutable local OCI image
`localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`
with `--pull=never`. CPython 3.11.15 / UID 65534, `network none`, proxy disabled,
unset inherited environment, read-only root, cap-drop ALL, no-new-privileges,
no engine socket, no credentials/private labels/host root bind. Public stage and
frozen foundation dependencies were mounted read-only. Actual final run cgroups:
memory 536870912, pids 32, cpu quota 100000/100000. `/tmp` 32m and `/work` 128m
noexec/nosuid/nodev tmpfs; outer timeout 90s and engine timeout 75s. Every named
container was independently queried through the official engine after removal,
query exit 0 with an empty result. Shared rootfs/dependencies were not modified.
The corrected 148-case run re-used this same immutable image digest and the same
isolation flag set; only its container name, its read-only stage path and the
added in-container migration probe differ (see the corrected argv below).

SQLite durability here is proven across **process** restart/crash within a bounded
container tmpfs. Tmpfs intentionally disappears on container removal; this is not
a power-loss or host-reboot durability test. A future trusted controller must use
one externally protected durable DB/scope, prevent candidate access and separate
its own resource/lifetime policy. Broker stdin is a trusted-controller channel,
not OS identity authentication. Bounded incomplete-line clients are ultimately
limited by the external process timeout, not a Python network watchdog.

This task does **not** claim public Cordis `llm/stream` integration, actual DSH
reserve-before-provider ordering, hidden per-HTTP attempt interception, genuine
billing correctness or human approval. Task22 must separately join this broker
to the audited public hook and test rejection before fixture-provider entry,
retry/compaction/Judge coverage, cancellation and finalization. Production
Gate/Adapter/primary route remain unchanged and all Live remains BLOCKED.

### Independent migration-audit correction: legacy-pending fee repricing

An independent read-only auditor reproduced one real accounting defect in the
frozen pre-fix delivery (identifier `BROKER-LEGACY-FEE-REPRICING`, recorded in
the [reviewer findings](</root/Autonomous Teacher/artifacts/reviewer-broker-pre/findings.json>)).
The historical 132-case snapshot did include a migrated-pending settlement
case, but under a startup policy whose fee and rates matched the persisted
snapshot (only the synthetic price version label differed). It never exercised
a settlement after a real startup fee/rate change, so its pass could not expose
this defect.

**Defect (pre-fix).** When a reservation had been created directly through the
legacy `BudgetLedger` before the first broker startup binding (a pending
"legacy" row), the broker settle/fail path passed the *current* startup
`RoutePolicy.known_fee` into `official_usage` instead of the `known_fee`
persisted on that reservation row. The original **price** was already honored:
`Ledger.settle` loads `PriceSnapshot` from the persisted `price_json`, so
`price_version` stayed `legacy-price`. A newer fee was thereby mixed into an
older price snapshot. In the reproduction, a synthetic-fee `0.001` reservation
(reserved cost `0.00112`) settled with complete trusted usage of 7 uncached +
0 cache-read + 0 cache-write input and 3 inclusive output under a later startup
fee `0.01` returned `cost_usd="0.010013"` with `reservation_exceeded=true`; the
false overrun latched `blocked=true` on the scope and denied subsequent
legitimate reservations. This was an accounting-correctness / false-scope-block
defect, **not** an authorization, Key-handling or provider-usage-authentication
bypass, and it changed no trust boundary.

**Correction.** One production path changed: `settle`/`fail` in
[broker.py](</root/Autonomous Teacher/src/autoteacher_m0/accounting/broker.py>)
now build `official_usage` with `Decimal(row["known_fee"])`, the fee persisted
on the pending reservation. Startup route fees apply only to new reservations.
Prices were already read from `row["price_json"]` by `Ledger.settle`; that
`Ledger` logic is unchanged, as are `ledger.py`, `budget.py` and
`broker_usage.py`. No protocol op, message field, error code, response shape or
trust-boundary statement changed; protocol v1 above is unchanged. A **16-case**
parametrized regression was added to
[test_broker.py](</root/Autonomous Teacher/tests/unit/accounting/test_broker.py>):
both fee directions (`0.001`→`0.01`, `0.01`→`0.001`) × four usage shapes
(complete token-only, partial, missing, inclusive actual invoice) × `settle` and
`fail`. Each case asserts the persisted fee and `legacy-price` version are used,
no false `reservation_exceeded`/scope block, correct `estimated` and `cost_kind`,
settlement replay/`ALREADY_SETTLED` idempotence, and that the next new
reservation receives the new startup fee and is dispatchable.

### Corrected delivery evidence

- One single invocation of the real child/stdin suite: **148 passed in 4.47s,
  ruff All checks passed, exit 0**. The 148 is one count: historical **132**
  (63 retained compatibility + 69 broker/stdio, see initial snapshot above) plus
  **16** new migration regressions from this fix; earlier 125/127/132 runs are
  NOT additive. The pre-fix 132 pass is preserved as history, not presented as
  validation of the fix.
- The runtime read-only project stage mounted at `/project` matches the current
  working tree byte-for-byte for every one of its 56 repository-backed files
  (all six delivered code/test files plus frozen dependencies and the other
  suite files); its only extra file is the container-only migration probe. This
  is how the 148-pass log is bound to the current sources; `docs/BUDGET_BROKER.md`
  is not executed and is not in that stage, so it is bound separately by the new
  hash manifests.
- [Corrected argv](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/final.argv>),
  [log](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/final.log>),
  [exit](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/final.exit>),
  [empty container query result](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/final.containers>).
  The in-container prefix recorded CPython 3.11.15, UID 65534, memory 536870912,
  pids 32, cpu quota 100000/100000; isolation/image identity is the same frozen
  digest and `--pull=never` profile described above (corrected container name
  `at-m0-budget-broker-migration-fix`). No host Python/pytest was used.
- The same containerized invocation re-ran the reviewer's read-only
  [migration probe](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/stage/migration_fee_probe.py>)
  against the corrected code: a `0.001` legacy pending reservation settled under
  a later `0.01` startup fee with complete 7/0/0 input + 3 output yields
  `cost_usd="0.001013"`, `price_version="legacy-price"`,
  `reservation_exceeded=false`, snapshot `spent_usd="0.001013"`,
  `blocked=false`, and `wrong_fee_repricing_observed=false`; the log ends with
  `EXACT_REVIEWER_REPRO_FIXED`. There was **zero model calls**, no Key/provider
  access, no network and no LiveGate change.
- Host UTC: the corrected `final.argv` mtime is 2026-11-13T23:35:51Z and the
  `final.log`/`final.exit` mtimes are 2026-11-13T23:35:56Z (host timezone
  `Etc/UTC`); these are filesystem timestamps, not an in-run wall-clock log.
  `final.exit` contains `0`. `final.containers` is empty (0 bytes); a read-only
  post-run documentation audit additionally found no container with that exact
  name (query exit 0) — see the
  [documentation audit log](</root/Autonomous Teacher/artifacts/budget-broker/doc-audit.log>),
  which also records the other read-only cross-checks.
- Superseding binding:
  [manifest-fixed.json](</root/Autonomous Teacher/artifacts/budget-broker/manifest-fixed.json>)
  records this correction, its `supersedes` anchor for the historical manifest
  and the full **7-file delivery hash list**;
  [source-fixed.sha256](</root/Autonomous Teacher/artifacts/budget-broker/source-fixed.sha256>),
  [evidence-fixed.sha256](</root/Autonomous Teacher/artifacts/budget-broker/evidence-fixed.sha256>)
  and [manifest-fixed.sha256](</root/Autonomous Teacher/artifacts/budget-broker/manifest-fixed.sha256>)
  bind the hashes. A document cannot contain its own hash, so this file's hash
  is recorded in the new hash manifests instead; the documentation audit log is
  itself bound by `evidence-fixed.sha256`.
- Corrected delivery file hashes (exact values; the same six values appear in
  the 7-file list of `source-fixed.sha256`, which also binds this document):
  `budget.py`
  `50e2ae7106ecf9584e9f4081a1fafa594b4b220bad9ef195c61142cac1c90e7e`;
  `ledger.py`
  `64e0844b957e6204c0310068a502ac62ff7a9cd93fdc38d8c4e02a486c194d3c`;
  `broker.py`
  `9dce2f9397fa5e91d387af7422f94d81ba7116f94923cced55269e9a0b2fc3d3`;
  `broker_usage.py`
  `8be713b421052c43121dc178a11df4dea8e4be6ecf518d4a6d9232d84c70a6f8`;
  `test_broker.py`
  `c51d5a1fd44f0f67e6daa6acbec7d698d1caac139e70ac9d4f29bd455b8eb9df`;
  `test_stdio.py`
  `380ef29aa38c707900710c3a37f4a4e92163bc4356f80477137985d27a7510a3`.
- Corrected raw-evidence hashes: `final.argv`
  `4a9d2896ff2741963788334293ed38ab35c46925990087b79b51ca0bb42c86c6`;
  `final.log`
  `5a9f4069564f4648312bebd35f1e9e350b9e0183a634aca4d7952dff34612cd1`;
  `final.exit`
  `9a271f2a916b0b6ee6cecb2426f0b3206ef074578be55d9bc94f6f3fe3ab86aa`;
  `final.containers`
  `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`;
  `migration_fee_probe.py`
  `9f9586f843180099b4f41c9c601bdd224857e2c2f72404af89fedc508b15c61c`.
  The full lists are authoritative in `evidence-fixed.sha256` and
  `manifest-fixed.json`.

### History preservation and unchanged trust boundary

The pre-fix 132-case delivery and its independent audit are retained verbatim.
The old
[manifest.json](</root/Autonomous Teacher/artifacts/budget-broker/manifest.json>)
hash `08572a8331fc7fec497af7cf4352cf0f1db4a0797a31a9bea271f53ee77707c0`,
[evidence.sha256](</root/Autonomous Teacher/artifacts/budget-broker/evidence.sha256>)
hash `741fb2dfbf389ff034df271363cf9669f6a49fed2bbf7f733dd506f0179ed669`
and
[manifest.sha256](</root/Autonomous Teacher/artifacts/budget-broker/manifest.sha256>)
still verify unchanged (re-checked without rewriting; see the documentation
audit log); old raw runs were not edited. The old
[source.sha256](</root/Autonomous Teacher/artifacts/budget-broker/source.sha256>)
now differs only for the three intentionally changed files — `broker.py`,
`test_broker.py` (fix) and this document (post-run documentation update) — and
its original bytes are preserved under
[pre-fix/](</root/Autonomous Teacher/artifacts/budget-broker/migration-fix/pre-fix/>):
`broker.py`
`646dcec530cc1c26d2833f758a7b5c75b229bb38b326951b8928e21264e53037`,
`test_broker.py`
`14f5c6c99084986329960ec8764bbbac2344e0881b656061fdad5a37bbc849ec`,
this document
`1ff2ceb8ab1297050f491b31203526b44180dd13dd3f2e879b66f505d8890987`.
No pre-fix hash was rewritten inside a historical file and no earlier run was
relabelled. `manifest-fixed.json` supersedes the old manifest only for the
corrected delivery; the old manifest remains the correct anchor for the
historical 132-case snapshot. Git association stays `UNRECORDED` as before.

None of this makes the broker an authorization service, Key proxy, OS sandbox,
human-approval mechanism, provider-usage authenticator or LiveGate.
`dispatch_allowed` still means only that this logical request was recorded for
the first time; no reset/refund endpoint exists; external provider execution
cannot be made exactly-once by a JSON response. The corrected run executes only
synthetic fixtures, with zero model calls, and all Live remains BLOCKED.
Production Gate/Adapter/primary route are unchanged, and the separate Task22
hook integration/ordering/cancellation work is still required.
