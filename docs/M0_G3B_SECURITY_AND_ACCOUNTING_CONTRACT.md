# M0 G3-B Security & Accounting Contract (B2)

- Gate: G3-B B2；Owner: verify2；base `0876816`；不进入 G3-C/D/Live。
- Authority: fixed no-Key OCI/WSL-style fake；0 Key/model/external HTTP/network；same-uid OS boundary remains **BLOCKED** (B0-02).

## 1. Identity / Authority

- `CallIdentity` from `accounting/call_identity.py` is single canonical source: UTF-8, sort_keys, compact, ensure_ascii=False, reject NaN/Inf; `call-<48hex>`; reservation_id not included.
- Controller is the only authority for `run_id/logical_step/attempt_index/call_id/request_digest`; DSH request cannot provide call_id/reservation/claim/authorization/digest fields (Admission strict schema rejects them).
- Admission is launcher-provided at fixed `/work/g3b/admission.json`; Controller loads once; second Controller instance reusing admission_id → `ADMISSION_REPLAYED`. Same Controller may handle multiple streams up to `limits.max_calls`.
- `admission.synthetic=true`; route tuple fixed `offline-test-only-g3b/fixture-bridge-v1`; fake scenario fixed by admission, not prompt text.

## 2. Reservation / Claim

- Controller calls real stdio Broker `reserve` with canonical call_id, task id from run_id, route/model tuple, input/output bounds, retry=false.
- Claim uses only `BoundBrokerClaimer.claim_bound` with `expected_route_id`/`expected_model`; legacy unbound `claim_dispatch` is forbidden.
- Controller reuses `EgressBoundary.claim_dispatch_for_request` with explicit G3-B `EgressPolicy` (host `g3b-fake.local:9000`, path `/v1/g3b/`, approved route only) and expected reservation tuple; any mismatch/route/tool/prepared rejection returns error before Fake (Fake received-count 0).
- Claim result/permission is process-local capability; `TrustedEgressTransport.consume_permission` is single-use and not cryptographic/cross-process authorization.

## 3. Attempt Journal / Wire Binding

- Controller-owned SQLite `/work/g3b/attempts.sqlite3`: WAL + synchronous=FULL + busy_timeout; `g3b_attempts` schema as design freeze §5.7; `g3b_admissions` records admission_id/run/controller instance.
- `begin_attempt()` is a transaction commit **before** send; send is allowed only after it returns. States: ATTEMPT_STARTED → RESPONSE_OBSERVED → SETTLED/WORST_CASE_HELD; unknown/no receipt → SETTLEMENT_UNCERTAIN; Broker remains PENDING. No automatic retry/resend.
- `approved_payload_digest = SHA-256(payload_bytes)` where payload bytes are canonical JSON of `fake_payload` (no trailing LF; Fake receives bytes + exactly one LF and strips it). `prepared_digest` is the independent PreparedProviderRequest digest used for call_id/claim; they are expected to differ.
- Evidence equality: Controller approved digest == FakeBackend sent digest == Fake receipt raw_sha256; Test asserts this chain.

## 4. Fake Provider

- `spikes/g3b-trusted-bridge/fake/fake_provider.py`: stdin one line ≤256KiB; strips exactly one LF; atomic receipt (fsync + replace + dir fsync) **before** any chunk; receipt contains raw_sha256/raw_length/transport_encoding/mode/usage/nonce/utc/pid/synthetic/0 model/0 http/0 network; independent `received-count.json` atomic counter.
- Mode comes from admission (`ok_usage|partial_usage|no_usage|error|eof|timeout|cancel|tool_once|tool_final|usage_invalid|receipt_conflict`); no business parsing/ledger/claim/key/network.

## 5. Observation / Ledger / Settlement

- Controller maps raw Fake usage to Broker JSON usage fields (inputTokens/cacheReadTokens/cacheWriteTokens/outputTokens/reasoningTokens); never sends `actual_cost_usd` for synthetic.
- AUTHORITATIVE complete + receipt: `settle`; PARTIAL/MISSING/INVALID with persistent receipt: `fail` + journal `WORST_CASE_HELD`, no zeroing; no receipt/unknown: no settle/fail, journal `SETTLEMENT_UNCERTAIN`, Broker PENDING.
- Observation replay: real Broker journal/claim idempotency; attempt unique per call/reservation; conflicts rejected; no ledger rollback.
- Local claim is not remote exactly-once; fake usage is synthetic and not invoice evidence.

## 6. v1 compatibility / migration

- No changes to Broker/ledger tables or v1 ops; G3-B adds separate `bridge` tables via `CREATE IF NOT EXISTS`; v1 clients remain as prior behavior.
- Existing G2 tests/regression remain authoritative for v1 semantics; G3-B does not modify G2 src.
- Known limitation: same-uid OS trust boundary BLOCKED; DSH real adapter/Node not run in B2; UDS protocol is B1-owned and not exercised here.

## 7. B2 implementation files

`src/autoteacher_m0/bridge/{admission.py,attempts.py,broker_client.py,fake_backend.py,controller.py}`, `spikes/g3b-trusted-bridge/fake/fake_provider.py`, `tests/integration/g3_bridge/{test_attempts.py,test_controller.py}`.
`broker_client.py` is a B2-owned addition approved by Lead because freeze §5.1 did not name the stdio client file; it implements reserve(claim with expected binding)/settle/fail/snapshot only, no legacy unbound claim, no retry/network.
