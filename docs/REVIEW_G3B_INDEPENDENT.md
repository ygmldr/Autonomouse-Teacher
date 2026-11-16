# M0 G3-B Independent Review (Reviewer)

- Reviewer: independent G3-B reviewer; did not implement B1/B2/B3/B4.
- Frozen inputs: implementation `90402929c710a046e23dd3a3c3dd108b641bc981` (parent
  `6b1e6b6110e9a366de9fbb358bede28bb6adc24e`), base
  `08768165db55351e42364dadf69657d7a2db4a4c`, docs
  `b4a2d774d97242974fcadd21166292dd3b988339`.
- Review Packet: `artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/`
  (706 hash lines + `hashes.sha256` + `packet-integrity-report.txt` = 708 files).
- Reviewer evidence: `artifacts/reviewer-g3b/`; run index:
  `artifacts/reviewer-g3b/RUN_INDEX.md`.
- This report is **not** a Live/GO authorization and does not assert a real
  provider, real usage, invoice, remote exactly-once, or OS trust-boundary PASS.

## 0. Verdict (limited scope)

**`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`** for the no-key G3-B integration
(functional DSH/Controller/Broker/Fake/Attempt/ledger path), **with
`OS_TRUST_BOUNDARY=B0-02=BLOCKED` and no `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`**.

- No P0 (unauthorized Fake send, duplicate send, lost conservative ledger,
  route/tool binding bypass, false success) was found in the exercised path.
- The functional core was independently reproduced: real DSH echo, real DSH
  tool two-turn, real session resume in a new process, two real Controller
  processes racing the same call, crash-after-`ATTEMPT_STARTED` with no resend,
  missing usage/EOF/invalid chunk/cancel conservatism, and SQLite/receipt
  cross-checks.
- The final matrix can remain **PASS 28 / PARTIAL 2 / UNVERIFIED 2 / BLOCKED 1**
  only with the caveats below. The following residuals are **not** upgraded by
  this review: B1-04 cancel (PARTIAL), B2-05 request-digest replay (PARTIAL),
  B3-10/B3-11 (UNVERIFIED), Skill 0.2.2 native harness (BLOCKED), B0-02 (BLOCKED).
- The review found P1/P2 findings (section 7) but none meets the task's P0
  `FAIL` criteria. P1-1/P1-2 are material enough that maintainers should either
  fix them or explicitly accept them before G3-C/G3-D; they do not justify
  `FAIL` under the stated P0 rule.
- **The only allowed trust-boundary statement is: OS boundary is not enforced
  and remains BLOCKED.** The same-uid candidate can read/write the Broker DB,
  write the policy, and obtain a Broker `CLAIMED` result without the Controller
  or a durable attempt (section 4). Direct external TCP is blocked by the
  container network, but that is not sufficient for a trust-boundary PASS.

## 1. R0 identity verification (independent, not Owner self-check text)

### 1.1 Git identity

Commands and results:

```text
$ git -C "/root/Autonomous Teacher" rev-parse HEAD
b4a2d774d97242974fcadd21166292dd3b988339
$ git rev-parse 90402929c710a046e23dd3a3c3dd108b641bc981^{commit}
90402929c710a046e23dd3a3c3dd108b641bc981
$ git rev-parse 90402929c710a046e23dd3a3c3dd108b641bc981^
6b1e6b6110e9a366de9fbb358bede28bb6adc24e
$ git diff --check 0876816 9040292
exit 0
$ git diff --binary 0876816 9040292 | sha256sum
dafe87c635c3739e49c66b965af06275ee9f414970de417f310b7f21d481ed83
$ sha256sum artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/diff.patch
dafe87c635c3739e49c66b965af06275ee9f414970de417f310b7f21d481ed83
```

`diff.patch` is 252,093 bytes and byte-identical to the independently recomputed
`git diff --binary`. The docs commit `b4a2d77` is a child of `9040292`; its
changed paths are only the matrix/report/review-request and `scripts/g3b/*`, not
product source:

```text
git diff --name-status 9040292 b4a2d77
M docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv
A docs/M0_G3B_IMPLEMENTATION_REPORT.md
A docs/M0_G3B_REVIEW_REQUEST.md
A scripts/g3b/build_packet.py
A scripts/g3b/run_regression.sh
```

The 33-row matrix was counted directly: `PASS 28 / PARTIAL 2 / UNVERIFIED 2 /
BLOCKED 1`, 33 rows, IDs B0-01..B4-03 exactly as listed in the review request.

### 1.2 Packet content and hashes

From the packet directory:

```text
$ sha256sum -c hashes.sha256
... 706 files: OK
exit 0
```

Independent blob comparison (`artifacts/reviewer-g3b/r0_blob_compare.py`) compared
every packet `source/**` and `tests/**` file against `git show 9040292:<path>`:
**48/48 source blobs and 5/5 test blobs match byte-for-byte**, no mismatches.
Packet `source-file-list.txt`/`test-file-list.txt` list the same set. Protocol
copies match the docs commit and the current docs files:

| file | sha256 |
|---|---|
| `docs/M0_G3B_IPC_PROTOCOL.md` | `a3434d67801484868242cc834b49e8b831bacc3f1285de44c7bdcd651466b229` |
| `docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md` | `74839ce75c1f53d100c1eb3186b33ca2ba9af61d425c59e2ba5d71c1290970b9` |

`manifest.json` values independently checked: base `0876816`, impl `9040292`,
docs `b4a2d77`, diff sha `dafe87c6…`, source_files 48, test_files 5, external
HTTP 0, real model calls 0, key present false. Packet source/tests are not a
temporary Node replacement: `stage-b3/node_modules/@deepseek-ai/dsh-agent` and
`dsh-llm` are `0.2.2-rc.2`, node is v22.23.2, Python 3.11.15.

### 1.3 Protected files

`git diff 0876816 9040292 -- src/autoteacher_m0/security/gates.py
src/autoteacher_m0/runtime/dsh_adapter.py scripts/run_live.sh` is empty. All three
files are byte-identical at base and impl:

| file | sha256 |
|---|---|
| `src/autoteacher_m0/security/gates.py` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` |
| `scripts/run_live.sh` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` |

### 1.4 Rootfs / deps / stage / no-key

Independent normalized GNU tar recomputation (same normalization as the packet
builder: `--sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner`):

| object | final measured sha256 |
|---|---|
| `artifacts/security/rootfs` | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| `artifacts/foundation/deps` | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| `artifacts/g3b-trusted-bridge/stage-b3` | `74ff4bedc934e22433492fdf05f228ad1b402cdc673448875cfb03aca9789101` |

The host full-pytest run was executed with `PYTHONDONTWRITEBYTECODE=1` and
`python3.11 -B`; deps re-hashed `e07729d7…` afterwards and no new
`deps/**/__pycache__` was found. Container runs were cleaned of the empty
`/etc/resolv.conf` and `/evidence`/`/seed` mountpoint artifacts that podman
creates; every run in `RUN_INDEX.md` ended with rootfs `25491e45…`, and
`podman ps -a` was empty.

Static sensitive/network scan of the Packet for common real-key patterns,
`Bearer` secrets and real provider URLs returned **0 hits**; `manifest` reports
0 external HTTP/model calls, and every Fake receipt inspected contains
`real_model_calls: 0`, `http_calls: 0`, `network_used: false`. Container
`AF_INET` connect returns `PermissionError 13`; `/probe` and `/` writes return
`EROFS`. This is consistent with no real Key/HTTP, but **not** evidence of a real
provider or a trusted OS boundary.

**Reviewer process incident (disclosed, restored):** the first R4 script opened
the packet WAL databases in place with SQLite `mode=ro`; SQLite rewrote four
ephemeral `attempts.sqlite3-shm` index files. This was detected by re-running
`sha256sum -c` and repaired byte-exactly from the pre-existing
`artifacts/review-packet-g3b-90402929-precheck` copy whose hashes equal the frozen
manifest entries. Details (before/source/expected/after hashes):
`artifacts/reviewer-g3b/packet-restore-incident.txt`. Final packet verification:
**706/706 OK**. The R4 script was then changed to read only a private snapshot
under `artifacts/reviewer-g3b/r4-snapshot/`; it no longer opens the packet. This
was a reviewer tooling incident, not an Owner byte change; no packet content
evidence was altered.

**Environment note:** at the very start of the review the shared rootfs was
transiently non-canonical (mount-target modes/churn from concurrent environment
restoration). I did not treat that transient state as a product identity result;
I waited for a stable state, recomputed `25491e45…`, and then ran all containers
against the stable rootfs. All final before/after checks are canonical.

## 2. R1 reverse tracing of every send entrypoint

The only production G3-B send path is:

1. DSH candidate `LlmAdapter` (`spikes/g3b-trusted-bridge/src/index.ts`,
   `BRIDGE_SOCKET = '/work/g3b/bridge.sock'`) only opens the fixed UDS; it does
   not spawn a process, read a key, read a DB, or accept an arbitrary path.
2. `BridgeServer.handle_connection` emits `ack` only after a schema-valid
   `request` (`src/autoteacher_m0/bridge/ipc_server.py:179-183`); `ack` is not a
   grant. It then iterates Controller frames and writes only validated
   chunks/finish/error.
3. `TrustedController._handle_payload`
   (`src/autoteacher_m0/bridge/controller.py:238-364`) performs, in order:
   `_prepare` (route/model/maxTokens/tool admission, image/file rejection),
   `broker.reserve`, `boundary.claim_dispatch_for_request`, durable
   `AttemptJournal.begin_attempt`, then `TrustedEgressTransport.dispatch` with a
   provider closure that calls `FakeBackend.send_exact_bytes`.
4. `EgressBoundary.claim_dispatch_for_request`
   (`src/autoteacher_m0/security/egress.py:543-604`) recomputes the prepared
   digest and call id, compares every bound field, checks the approved tool
   schemas and reservation route/model, and only then calls
   `_BoundClaimer.claim_bound` → `BrokerClient.claim` with
   `expected_route_id`/`expected_model`.
5. `TrustedEgressTransport.dispatch` (`egress.py:751-812`) requires a
   process-local `DispatchPermission` issued by the claim; `consume_permission`
   (`egress.py:685-702`) is single-use and checks object identity plus all
   identity fields. `FakeBackend.send_exact_bytes`
   (`src/autoteacher_m0/bridge/fake_backend.py:48-76`) is the only call to the
   Fake subprocess; it is reached only from the provider closure.
6. `begin_attempt` commits `ATTEMPT_STARTED` before dispatch
   (`src/autoteacher_m0/bridge/attempts.py:71-95`); `mark_response_observed`
   and settle/fail follow only after a matching receipt
   (`controller.py:303-364`). `reconcile_on_startup` never sends; without a
   receipt it marks `SETTLEMENT_UNCERTAIN` and leaves Broker PENDING
   (`controller.py:98-130`; `attempts.py:140-170`).

Legacy/unused entrypoints:

| entrypoint | file:line | G3-B reachability / conclusion |
|---|---|---|
| legacy unbound `EgressBoundary.claim_dispatch` | `security/egress.py:528-536` | Not called by the G3-B Controller; `require_claim` (`:607`) also uses it. The bridge uses only `claim_dispatch_for_request`. Residual library path, not a G3-B functional bypass. |
| `authorize()` / `evaluate_descriptor()` | `security/egress.py:441-443`, `:435` | Diagnostic only; returns `PolicyEvaluation`, never a `DispatchPermission`/send. |
| `require_claim` | `security/egress.py:607-612` | Not called from `src/autoteacher_m0/bridge/*` or the G3-B spike; library residual. |
| `PolicyOnlyFakeTransport.dispatch` | `security/egress.py:853-870` | Explicitly non-sending; `dispatched=False`. |
| `MockEgressTransport` | `security/egress.py:813-851` | Requires a real claim permission; no G3-B Controller use. |
| default OpenCode Go policy | `security/egress.py:25`, `:90`, `:107`, `:872-917` | `policy_from_json` defaults to `opencode.ai` and `opencode-go`; the G3-B Controller does **not** call it. It constructs an explicit `EgressPolicy` for `g3b-fake.local:9000`, path `/v1/g3b/`, route `offline-test-only-g3b`. |
| G3-A direct fake / stdio adapter | `src/autoteacher_m0/runtime/dsh_adapter.py` (unchanged), G3-A spike | Not referenced by the G3-B bridge patch; bridge patch inserts only `g3b-trusted-bridge-provider` and `offline-public-skill`. |
| compaction / judge / retry / files | `spikes/g3b-trusted-bridge/config/bridge.patch.yml` | `compaction-basic`, `image-offload`, `tool-fs`, `subprocess`, real `llm-deepseek` are disabled (`:6`, `:13`, `:17`, `:31`); no compaction/judge/retry provider path in the G3-B profile. Files/images are rejected in `_prepare` (`controller.py:147-156`). |

Additional checks:

- DSH's captured request contains only `skill_lookup`; no second request/header
  was needed for the second tool turn. `B3-01` evidence shows one
  `request/header`, one `tool/result`, and two Controller calls.
- The adapter's `buildRequestPayload` rejects non-frozen provider/model,
  sessionId bounds, maxTokens bounds, and unknown route; it builds only the
  frozen fields and sends over the fixed UDS.
- `BridgeServer._cancel_reader` calls `controller.cancel(transport_id=...,
  reason=...)` (`ipc_server.py:284-289`), but `TrustedController.cancel(self)`
  takes no arguments (`controller.py:187`); the `TypeError` is swallowed and
  `_cancel` is never read by `_handle_payload`. Cancel is therefore a no-op, as
  confirmed by the probe in §3.6. This is a P1 finding (B1-04 remains PARTIAL).

Conclusion for R1: **no functional path from real DSH to Fake that bypasses
Bound Claim + durable `ATTEMPT_STARTED` was found in the G3-B production path.**
The legacy unbound/descriptor APIs remain in the library and are not called by
the Controller; same-uid direct Broker access is an OS-boundary failure
(section 4), not a functional-path bypass.

## 3. R2 independent malicious probes

All probes ran in the fixed rootfs with real DSH 0.2.2-rc.2 and/or the real
Controller/SQLite/Fake; each directory contains `run.log` with UTC and exit.
Probe scripts are under `artifacts/reviewer-g3b/r2/`; no Owner test result was
used as the assertion source.

### 3.1 ① Real DSH tool two turns with only one request/header

Run: `r5/b3-01`, 2026-11-16T20:54:41–20:54:42Z, exit **0**.

- DSH result: `final_response: "ok"`, `finish_reason: "completed"`, error null.
- Events: exactly **1** `request/header` (initial), **1** `tool/result` with the
  real `binary_search` content, and a second step with no second
  `request/header`.
- DB (`r5/b3-01/work/`): 2 distinct `call_id`s, 2 reservations `OK`, 2 claims
  `COMPLETED`, 2 attempts `SETTLED`, 2 receipt files, counter **2**.
- This independently confirms 2× Reserve/Claim/Attempt/Receipt despite one
  header; the second tool result is real tool output, not a second header.

### 3.2 ② Claim-before/after payload tampering and replay

Final run: `r2/payload`, 2026-11-16T21:00:00Z, exit **0**; result
`r2/payload/payload-result.json`.

A valid request first produced ack + 2 chunks + finish and one settled attempt
(counter 1). Raw malicious frames (bypassing client-side encoding) then produced
only ack/error and **no new reservation/claim/attempt/receipt**:

| case | observed |
|---|---|
| `authorized` field injected | error `UNKNOWN_FIELD` |
| `call_id` field injected | error `UNKNOWN_FIELD` |
| `maxTokens=1025` | error `BAD_TYPE` |
| route-b/model-b | ack + error `ROUTE_MISMATCH` |
| unapproved `shell` tool | ack + error `ADMISSION_TOOL_SCHEMA_MISMATCH` |

After the first call was settled, a **new Controller process** with a fresh
admission but the same run/request (the same durable `call_id`) was started:
it returned ack + `UNKNOWN_FIELD`, counter stayed **1**, attempts stayed **1**,
and no second Fake receipt was created. The `UNKNOWN_FIELD` here is the
broker `CALL_ID_CONFLICT` → protocol code mapping issue in P2-1, not a send.

### 3.3 ③ Two real processes racing the same call_id

Independent sequential-start race probe (`r2/concurrency`, 2026-11-16T21:06:46–
21:06:47Z, exit **0**, `concurrency-result.json`):

- two real Controllers, distinct admissions, same run/request/call id;
- barrier-released clients; one got `ack/chunk/chunk/finish`, the other got
  `ack/error`;
- **counter 1**, **1 reservation**, **1 claim**, **1 attempt**, one
  `SETTLED`/`OK`; loser error code `UNKNOWN_FIELD` (not Owner's
  `CLAIM_DENIED`; see P2-1);
- assertions: `fake_counter_one=true`, at-most-one completed claim/attempt=true,
  one success/one deterministic error=true.

The Owner's own `run/concurrency.py` direct invocation timed out twice waiting
for the `b` socket (15s harness wait), while a wrapper/debug run and the
independent sequential-start probe passed. This is harness-startup flakiness
(P2-6), not an extra Fake send. The Owner Packet's B3-05 result shows
`CLAIM_DENIED`; that exact code was **not reproducible** with final code and
same call id (P2-1).

### 3.4 ④ Crash after `ATTEMPT_STARTED`, before Fake send

Run: `r2/crash` (2026-11-16T21:00:16–21:00:18Z, exit 1 because the crashed DSH
saw EOF) with `G3B_TEST_MODE=1`,
`G3B_CRASH_HOOK=after_attempt_start_before_fake_send`; reconcile run
`r2/crash-reconcile` (21:00:32–33Z, exit 0).

- Crash evidence: one attempt `ATTEMPT_STARTED`, reservation `PENDING`, no
  receipt, Fake counter 0.
- Reconcile (`r2/crash-reconcile/reconcile-result.json`): before
  `ATTEMPT_STARTED`; after `SETTLEMENT_UNCERTAIN` with
  `reason=NO_RECEIPT_AFTER_CRASH`; counter 0, receipts 0; reservation remains
  `PENDING` at full reserved bounds.
- No new Fake send and no automatic retry. This is the expected conservative
  behavior.

### 3.5 ⑤ Guard missing / BOOT_INVALID with no Controller authorization

- `r2/guard-no-controller` (21:00:48–50Z, exit 1 expected): real DSH produced a
  `request/header`, then `turn/end` error `RBG_GUARD_BOOT_INVALID`; stderr
  contains `RBG_BOOT_INVALID ... fail_closed:true`; there is **no** Broker DB,
  no attempt DB, and no receipt (Fake counter 0). Three-layer zero proof:
  DSH attempt evidence + no Broker/attempt rows + Fake 0.
- `r2/bad-admission` (21:01:06–07Z, exit 1 expected): controller log shows
  `ADMISSION_MISSING`; DSH produced a `request/header` and then error
  `G3B_BRIDGE_CONNECT_FAILED`; no Broker/attempt DB and no Fake receipt.

### 3.6 ⑥ Missing/invalid usage, invalid chunk/EOF, cancel

Real-DSH usage scenarios (each exit 1 expected; logs under `r2/usage-*`):

| scenario | attempt state | reservation | counter | result |
|---|---|---|---:|---|
| `no_usage` | `WORST_CASE_HELD` (`USAGE_NOT_AUTHORITATIVE`) | `FAILED`, input_used 1024, output_used 256, cost 0.002536 | 1 | DSH finish error, no success |
| `partial_usage` | `WORST_CASE_HELD` (`USAGE_NOT_AUTHORITATIVE`) | `FAILED`, full bounds | 1 | DSH finish error |
| `eof` | `WORST_CASE_HELD` (`USAGE_NOT_AUTHORITATIVE`) | `FAILED`, full bounds | 1 | DSH finish error |
| `usage_invalid` | `ATTEMPT_STARTED` | `PENDING`, full bounds | 1 | DSH error, no settlement/zero |

No scenario produced a zero-cost settlement or a success finish. The
`usage_invalid` run leaves a receipt on disk but the journal has
`receipt_id=null`/`ATTEMPT_STARTED`/`PENDING`; a restart reconcile can classify
it conservatively; no undercount occurs.

Invalid chunk / EOF at the adapter boundary (`r2/invalid-chunk`,
21:02:34–37Z, exit 0): a stub UDS server sent a valid ack and then an invalid
chunk (`type:"evil"`), or closed after ack. Real DSH returned
`finish_reason:"error"` with empty final response in both cases; no success
finish. `invalid-chunk-result.json` assertions true.

Cancel (`r2/cancel`, 21:07:43–54Z, exit 0): after a valid ack, a real cancel
frame was sent while the Fake was in timeout mode. The Controller still sent one
Fake request (counter 1), waited for the Fake timeout, then ended with
`SETTLEMENT_UNCERTAIN`; attempt `SETTLEMENT_UNCERTAIN`, reservation `PENDING`,
no success finish, no zero-cost settlement. This is fail-closed but **cancel is
not propagated**: `TrustedController.cancel` has no parameters and `_cancel` is
not checked (P1-2). It matches B1-04/PARTIAL; do not call cancel PASS.

## 4. R3 OS boundary — measured, not diagram-based

Run: `r3/boundary_probe.py`, 2026-11-16T20:57:38Z, exit **0**; evidence
`r3/boundary-result.json`. The probe ran as uid 65534 inside the fixed rootfs,
started its own Broker, and attempted the actions the task specifies:

| action | actual OS result | conclusion |
|---|---|---|
| write policy file under `/work/boundary` | `policy_write=true` | same-uid candidate can write policy path |
| read Broker SQLite | `broker_db_read.ok=true`, 1 reservation | same-uid candidate can read Broker DB |
| write Broker SQLite | `broker_db_write=true` | same-uid candidate can write Broker DB |
| reserve + claim without Controller/durable attempt | `RESERVED` then `CLAIMED` (`dispatch_allowed=true`) | no OS boundary; local claim is not protected from same-uid code |
| direct external TCP to 1.1.1.1:443 | `PermissionError:13` | network namespace blocks external TCP, but this does not prove file/control-plane isolation |
| write `/probe` | `EROFS` | read-only mount only |
| write `/` | `EROFS` | read-only rootfs only |

The candidate was able to obtain a Broker `CLAIMED` result with a fabricated
call id and arbitrary request digest, with **no** Controller and **no** durable
attempt row. A second probe (`r3/actual-db`, 21:14:49–50Z, exit 0,
`actual-db-result.json`) mounted the **actual reviewer-run B1-01 Broker DB and
`broker.json`**; as uid 65534 it read the real settled reservation
(`9ae93f05…`, `OK`, cost `0.001022`), wrote a new SQLite table into the DB
(`write=true`), and rewrote the policy file (`policy_write=true`). This is direct
evidence that same-uid code is not separated from the trusted Broker/policy.
That is exactly why B0-02 cannot be PASS in same-uid G3-B.
**Verdict for OS boundary: `BLOCKED`.** Do not issue
`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`; recovery requires a different OS
principal/namespace and actual permission denials (G3-D).

## 5. R4 data / financial cross-check

### 5.1 Packet SQLite (independent read-only snapshot)

`artifacts/reviewer-g3b/r4_crosscheck.py` reads a private copy
(`r4-snapshot/`), never the packet in place. Result:
`artifacts/reviewer-g3b/r4-crosscheck.json`.

- 24 trace `work/` directories with DBs were checked (the table below includes
  the main positive/crash traces; full per-trace rows are in the JSON).
- Aggregate checks all true:
  `all_link_counts`, `all_one_claim_per_call`, `all_one_attempt_per_call`,
  `all_claim_digest_matches`, `all_attempt_state_matches_reservation`,
  `all_receipt_digest_matches`, `all_counter_matches`,
  `all_observations_empty`.
- `counter_attempt_receipt_mismatch_traces = [b1-04-timeout,
  b2-09-usage_invalid]`: Fake wrote a receipt/counter but the Controller did not
  record a receipt in the attempt journal (timeout / invalid usage). This is
  conservative, not a false `NOT_DISPATCHED`; the reservation is `PENDING` and
  the attempt `SETTLEMENT_UNCERTAIN`/`ATTEMPT_STARTED`, and the receipt remains on
  disk for a restart reconcile.
- Main positive chains:

| trace | calls | reservations | claims | attempts | receipts | counter |
|---|---:|---:|---:|---:|---:|---:|
| `b1-01-real-dsh-echo` | 1 | 1 OK | 1 COMPLETED | 1 SETTLED | 1 | 1 |
| `b3-01-real-tool-two-turns` | 2 | 2 OK | 2 COMPLETED | 2 SETTLED | 2 | 2 |
| `b3-02-resume-second-fixed` | 2 | 2 OK | 2 COMPLETED | 2 SETTLED | 2 | 2 |
| `b3-05-two-controller-race` | 1 | 1 OK | 1 COMPLETED | 1 SETTLED | 1 | 1 |
| `b3-07-crash-after_claim_before_attempt_start` | 1 | 1 PENDING | 1 CLAIMED | 0 | 0 | 0 |
| `b3-06-crash-after-attempt-before-fake` | 1 | 1 PENDING | 1 CLAIMED | 1 SETTLEMENT_UNCERTAIN | 0 | 0 |
| `b3-07-after-fake-receive-before-response` | 1 | 1 OK | 1 COMPLETED | 1 SETTLED | 1 | 1 |
| `b3-07-crash-after_response_before_settlement` | 1 | 1 FAILED | 1 COMPLETED | 1 WORST_CASE_HELD | 1 | 1 |

For every settled call, `call_id` maps uniquely to one
reservation/call-link/claim/attempt/receipt; Tool turns are independent rows
with distinct call ids. Pending/uncertain paths are held at full reserved
bounds; no row showed `NOT_DISPATCHED` while a Fake receipt existed.

### 5.2 What each hash covers

- `prepared_digest` / `budget_dispatch_claims.request_digest`: SHA-256 of
  canonical `PreparedProviderRequest` over schema/scope/run/step/attempt,
  route/provider/model/host/port/method/path, stream, max output tokens,
  system, messages, tools, response/retry shapes and file/image/store flags.
  It excludes `call_id`, `request_digest` and `reservation_id`.
- `payload_digest` (`g3b_attempts.payload_digest`): SHA-256 of the exact
  canonical Fake payload bytes, which include schema, `call_id`,
  `prepared_digest`, route/model, messages, tools, system, max output tokens,
  stream, mode and nonce. It is the approved/sent payload digest.
- Fake receipt `raw_sha256` = SHA-256 of the raw line bytes without the exactly
  one LF; `raw_length` = those bytes' length. For every checked settled
  attempt, `payload_digest == sent_payload_digest == receipt.raw_sha256`, while
  `prepared_digest != payload_digest` as expected. The Envelope `hash` is only
  frame-payload integrity and is never used as a call/payload digest.
- `observation_digest` = SHA-256 of canonical normalized observation; it is
  stored in the attempt `receipt_json` together with the receipt id and raw
  digest. It is not a substitute for the payload digest.
- `budget_provider_observations` is empty in every packet trace and every
  independent run; the Controller maps raw Fake usage directly to Broker
  `settle`/`fail` (O-3), and the attempt journal holds the receipt/observation
  digest. This is a P2 observation-table note, not an undercount.

### 5.3 Independent reviewer runs

`artifacts/reviewer-g3b/r5_crosscheck.py` / `r5-crosscheck.json`:
B1-01 1 call; B3-01 2 calls; B3-02 first 1 and second 2 (old call id present
unchanged, new call id added); B3-05 1; crash 1 `ATTEMPT_STARTED` → reconcile
`SETTLEMENT_UNCERTAIN`; no/partial/eof `WORST_CASE_HELD`/`FAILED` full bounds;
usage_invalid `ATTEMPT_STARTED`/`PENDING`; all `prepared != payload`, all
receipt raw hashes match payload, all reservation/call links one-to-one.

## 6. R5 reruns and counts

### 6.1 Canonical fixed-rootfs full pytest

Command (full argv/UTC in `r5/oci-full/run.log` and `r5/oci-full-ro/run.log`):

```text
/opt/python/bin/python3.11 -B -m pytest /project/tests -q -p no:cacheprovider
cwd=/project, PYTHONPATH=/project/src:/deps, deps also mounted at
/project/artifacts/foundation/deps
```

| run | project stage | result | exit |
|---|---|---|---:|
| 20:50:47–20:51:51Z | `git archive 9040292` (files mode 664) | 1 failed, 664 passed, 1 skipped | 1 |
| 20:52:26–20:53:28Z | same stage, files chmod 0444 | **665 passed, 1 skipped, 0 failed** | **0** |

The only failure in the first run was
`tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`:
`/project/config/dsh/target-runtime.patch.yml` had `st_mode=33204` (group/other
write) because the staging extraction retained writable modes. After
`chmod 444` on the staged files, the target test alone passed **4/4** and the
full suite passed 665/1. **Independent judgment: this failure is a staging file
mode artifact, not a product defect.** The canonical OCI count is 665 passed /
1 skipped / 0 failed.

### 6.2 Host full pytest

`r5/host-full`, 21:03:42–21:05:10Z, exit 1,
`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps
/root/.local/bin/python3.11 -B -m pytest tests -q -p no:cacheprovider`:
**663 passed / 2 failed / 1 skipped**. The two failures are host-environment
artifacts, matching the Lead's observation:

1. target-profile file is `0644` (owner-writable) on the host; test requires
   read-only files; same staging/mode issue, not product.
2. `test_all_live_entrypoints_remain_blocked` hardcodes
   `PYTHONPATH=/project/src:/deps`; host has no `/project`, so the child exits 1
   with `ModuleNotFoundError` instead of the expected blocked exit 3. In the
   container `/project` exists and the test passes.

Deps stayed canonical `e07729d7…` after the host run; no bytecode was written.
The host failures must not be hidden or converted to a product PASS.

### 6.3 Real DSH / concurrency / crash reruns

| case | UTC | exit | result |
|---|---|---:|---|
| B1-01 echo | 20:54:27–29Z | 0 | `okok`/`completed`; 1 reservation/claim/attempt SETTLED; counter 1 |
| B3-01 tool two turns | 20:54:41–42Z | 0 | `ok`/`completed`; one `request/header`, one real tool result; 2 calls/attempts/receipts; counter 2 |
| B3-02 first | 20:54:58–59Z | 0 | `okok`; call `call-0b9dc357…` SETTLED; counter 1 |
| B3-02 second | 20:55:28–30Z | 0 | `okok`; resume `request/header`; old call still SETTLED, new call `call-837629a1…` added; counter 2; old attempt not resent |
| B3-05 independent race | 21:06:46–47Z | 0 | 1 finish + 1 error; counter 1; 1 reservation/claim/attempt |
| crash after attempt-start | 21:00:16–18Z | 1 (expected EOF) | attempt `ATTEMPT_STARTED`; Fake 0; reconcile `SETTLEMENT_UNCERTAIN`, PENDING, no resend |
| crash reconcile | 21:00:32–33Z | 0 | `ATTEMPT_STARTED` -> `SETTLEMENT_UNCERTAIN`; counter 0/receipts 0 |

B3-02 second-process first attempt used the wrong seed root in my harness
(`/output/seed` instead of `/output/seed/work`), producing
`session not found` with no Controller request; retry with the correct seed
path passed. This was a reviewer harness mistake, not a product failure, and is
recorded in `r5/b3-02-second/run.log`.

Direct `run/concurrency.py` timed out twice (20:55:44–59Z, 21:05:59–21:06:15Z)
waiting for the second socket; a debug wrapper and the independent
sequential-start race passed. The product property (at most one Fake receipt)
held in every successful race; the startup flakiness is P2-6.

### 6.4 Environment after R5

All runs ended with rootfs `25491e45…`, deps `e07729d7…`, stage-b3 `74ff4bed…`;
`podman ps -a` was empty and no broker/probe processes remained. The only
reviewer-caused rootfs hygiene steps were removal of podman-created zero-byte
`/etc/resolv.conf` and empty `/evidence`/`/seed` mountpoints, with canonical
hash re-verified after each. No real Key, model, or external HTTP was used.

## 7. Findings (P0/P1/P2)

### P0 — none found

No exercised path produced an unauthorized Fake send, duplicate send for the
same claim, lost conservative accounting, route/tool binding bypass, or a false
success finish. The same-uid Broker/DB access in §4 is the expected OS-boundary
BLOCKED condition, not a P0 functional-path finding; it must not be reported as
a trust-boundary PASS.

### P1-1 — B3-08 evidence shows conservative `WORST_CASE_HELD`, not an idempotent settle of the persisted receipt

- Evidence:
  `artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/traces/b3-07-crash-after_response_before_settlement/reconcile-result.json`:
  before `RESPONSE_OBSERVED`, after `WORST_CASE_HELD`; reservation `FAILED`,
  cost `0.002536`, input_used 1024/output_used 256; counter 1; no resend.
- Cause: `mark_response_observed` persists only receipt metadata
  (`controller.py:333-338`); the real receipt file has usage, but the journal
  `receipt_json` does not, so `reconcile_on_startup` (`controller.py:108-126`)
  chooses `fail`/worst-case rather than `settle`.
- Impact: conservative (full reserved bounds), **no undercount** and no resend;
  but the B3-08 wording "idempotent settle" and the matrix `PASS` are stronger
  than the observed status. Recommendation: either persist usage in the receipt
  journal/read the receipt on reconcile and settle if authoritative, or change
  B3-08 to `PARTIAL`/wording to "conservative hold" before acceptance. This is
  not a P0.

### P1-2 — cancel is non-functional (B1-04 remains PARTIAL)

- `ipc_server.py:284-289` calls `controller.cancel(transport_id=..., reason=...)`;
  `controller.py:187` defines `cancel(self)` with no parameters; the `TypeError`
  is swallowed. `self._cancel` is set but never checked in `_handle_payload`.
- Probe `r2/cancel` sent a cancel after ack; Fake still received one request,
  attempt ended `SETTLEMENT_UNCERTAIN`, reservation `PENDING`, no success finish.
  This is fail-closed but not cancellation propagation.
- Recommendation: either implement a compatible cancel contract (stop before
  send / mark uncertain; never claim free) or explicitly keep B1-04/B3-10
  PARTIAL/UNVERIFIED and do not claim cancel PASS.

### P2-1 — Broker conflict error codes are not in the IPC error set and surface as `UNKNOWN_FIELD`; the Owner B3-05 `CLAIM_DENIED` was not reproduced

- `broker.py:248` raises `ProtocolError("CALL_ID_CONFLICT")`; the Controller
  raises `BridgeError(reserved.get("code"))` (`controller.py:265-266`), then
  `validate_error_payload` rejects non-frozen codes and maps them to
  `UNKNOWN_FIELD` (`protocol.py:408-410`).
- Independent races/replay (two-process sequential-start, debug wrapper, and
  second-Controller same-call replay) all produced `UNKNOWN_FIELD` for the
  losing/duplicate call, not `CLAIM_DENIED`; the Owner Packet B3-05 trace says
  `CLAIM_DENIED`. Core at-most-one-send remains true.
- Recommendation: map `CALL_ID_CONFLICT`/`IDEMPOTENCY_CONFLICT` to
  `CLAIM_DENIED`/`BUDGET_DENIED` (or add approved codes through the design-freeze
  process), and correct the B3-05 evidence wording. No P0.

### P2-2 — malformed finish-error payload for non-authoritative usage

- `controller.py:359-360` returns `{"kind":"finish","reason":{"kind":"error"}}`
  without the required `failure{message,code}`; `validate_finish_payload`
  rejects it, so the server sends `UNKNOWN_FIELD`. Observed for `no_usage`,
  `partial_usage`, `eof` (`G3B_BRIDGE_UNKNOWN_FIELD`). The DSH outcome is still
  error/no success; accounting is conservative. Recommendation: return a valid
  `finish(error, failure=...)` or a proper `error` envelope. No P0.

### P2-3 — `max_calls` is consumed by invalid requests

- `controller.py:242-244` increments `self.calls` before `_prepare`; a candidate
  can consume the 8-call admission with invalid frames and deny later valid
  calls. No fake send; DoS/hardening only. Recommendation: increment after
  successful reserve/prepare or use a separate validation counter.

### P2-4 — observation table unused

- `budget_provider_observations` is empty in all 24 packet traces and all
  reviewer runs; the only observation evidence is the attempt `receipt_json`
  digest. The O-3 mapping/settle path is conservative, but there is no
  independent observation row for cross-checking. Recommendation: document this
  as an accepted G3-B residual or persist the normalized observation/digest in
  the dedicated table; no undercount observed.

### P2-5 — B3-07 trace snapshot overwritten by reconcile #2

- `traces/b3-07-after-fake-receive-before-response/reconcile-result.json` is the
  second reconcile (before=after=SETTLED). The first reconcile log
  `logs/b3-07-after-fake-receive-before-response-reconcile1-…log` correctly
  shows `ATTEMPT_STARTED` -> `SETTLED`. The evidence remains available in logs,
  but the trace file alone is misleading. Recommendation: preserve both
  reconcile results or name them `reconcile1/2`. No P0.

### P2-6 — concurrency harness startup flakiness

- Direct `run/concurrency.py` waited 15s for `/work/g3b/bridge-b.sock` twice and
  failed; a debug wrapper and the independent sequential-start probe passed
  immediately. This is a test-harness startup timing issue, not an extra send;
  it reduces reproducibility of the Owner's exact B3-05 command. Recommendation:
  make controller startup/socket wait robust and record the retry, or use the
  sequential-start/barrier probe as the canonical test; no P0.

### P2-7 — recovery requires a fresh admission id; document the launcher contract

- `TrustedController.__init__` calls `register_admission` before reconcile; a
  restarted process reusing the same admission id fails `ADMISSION_REPLAYED`
  before it can reconcile. The Owner's reconcile uses a fresh admission, which
  works; this should be an explicit launcher/recovery contract, not only an
  implementation detail. No P0.

### P2-8 — reviewer tooling incident (not an Owner finding)

The packet `-shm` incident described in §1.4 changed/restored four ephemeral
SQLite files via this reviewer's first R4 script. Final 706/706 hashes pass; the
script now reads a private snapshot. This is recorded for transparency and is
not attributed to the implementation/Owner.

## 8. Unverified / BLOCKED and residual limits

- **B0-02 OS trust boundary: BLOCKED.** Same-uid candidate can read/write Broker
  DB/policy and obtain a Broker claim; only external network is blocked. No
  `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`.
- **B1-04 cancel: PARTIAL** (cancel no-op; probe fail-closed but not propagated).
- **B2-05 request-digest replay: PARTIAL** (Owner did not run full replay; this
  review tested same-call sequential replay and got a deterministic
  `UNKNOWN_FIELD`, not all digest variants).
- **B3-10/B3-11: UNVERIFIED** (process-tree/backpressure/resource bounds not
  independently tested).
- **B3-03 normal Guard+Bridge combination: not independently rerun**; this
  review ran guard-invalid/no-controller and bad-admission zero-proof only.
  Native Guard/precheck counts are not a substitute for the combination.
- **B2-10 conflicting observation: not independently injected**; only the
  idempotent/replay paths were observed.
- **Skill 0.2.2 native harness: BLOCKED** (Owner's harness-version limitation; not
  contradicted by this review).
- **Real provider HTTP/usage/invoice, remote exactly-once, LiveGate dynamic
  Live call: UNVERIFIED / out of scope.** Fake usage is synthetic and is not a
  supplier bill.
- **Exact B3-05 `CLAIM_DENIED` code: not reproduced**; see P2-1.
- **Packet exact B3-08 settle: not observed**; conservative hold observed (P1-1).

## 9. Recommendation to maintainers

- **Accept** `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE` **only together with**
  `OS_TRUST_BOUNDARY=B0-02=BLOCKED` and the explicit residuals above; do not
  convert this to `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`, Live, or GO.
- **Do not** accept a blanket "all PASS": B1-04, B2-05, B3-10, B3-11 and the
  Skill 0.2.2 harness retain their Owner statuses.
- Before G3-C/G3-D, fix or explicitly accept P1-1 (B3-08 semantics) and P1-2
  (cancel contract); fix P2-1/P2-2 error mapping so deterministic Broker
  rejections are not reported as `UNKNOWN_FIELD`, and add a robust concurrency
  startup/barrier test. These are not P0 blockers under the task's stated rule,
  but they are real evidence-quality/robustness defects.
- Keep the B3-05 matrix exact-code claim and B3-08 "idempotent settle" wording
  consistent with observed evidence; do not edit historical bytes without an
  append-only errata.
- Continue to treat same-uid OS isolation as **BLOCKED** until G3-D provides
  different principals/namespaces and actual permission denials. No Live/Key/
  provider authorization is granted by this review.

## Appendix A — key reproducible commands

Container template (all mounts are existing rootfs mount targets; no new
mountpoint is required except the explicitly cleaned `/evidence`/`/seed` in the
reconcile/concurrency probes):

```bash
podman run --rm --name <unique> \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/probe/src:/deps --env PYTHONDONTWRITEBYTECODE=1 \
  --env TMPDIR=/tmp --read-only --read-only-tmpfs=false \
  --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --pids-limit 256 --memory 2g --cpus 2 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,mode=1777 \
  --mount type=bind,src=<stage-b3>,dst=/probe,ro=true \
  --mount type=bind,src=<stage-project>,dst=/project,ro=true \
  --mount type=bind,src=<deps>,dst=/deps,ro=true \
  --mount type=bind,src=<deps>,dst=/project/artifacts/foundation/deps,ro=true \
  --mount type=bind,src=<evidence>,dst=/output,rw=true \
  --workdir /project \
  --rootfs "<repo>/artifacts/security/rootfs" \
  /opt/python/bin/python3.11 -B <command>
```

Key independent commands:

```bash
# R0 (host, read-only)
git diff --check 0876816 9040292
git diff --binary 0876816 9040292 | sha256sum
cd artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981 && sha256sum -c hashes.sha256
PYTHONDONTWRITEBYTECODE=1 python3 -B artifacts/reviewer-g3b/r0_blob_compare.py

# R5 full OCI
/opt/python/bin/python3.11 -B -m pytest /project/tests -q -p no:cacheprovider

# Real DSH
/opt/python/bin/python3.11 -B /probe/run/capture_tools.py
/opt/python/bin/python3.11 -B /probe/run/worker.py --mode dsh --evidence /output --session <id> [--scenario tool|--resume --seed ...]
/probe/run/concurrency.py
/opt/python/bin/python3.11 -B /probe/run/reconcile.py

# Reviewer probes
/opt/python/bin/python3.11 -B /output/payload_probe.py
/opt/python/bin/python3.11 -B /output/concurrency_probe.py
/opt/python/bin/python3.11 -B /output/boundary_probe.py
/opt/python/bin/python3.11 -B /output/cancel_probe.py
/opt/python/bin/python3.11 -B /output/invalid_chunk_probe.py

# R4 (private snapshot, never packet in place)
PYTHONDONTWRITEBYTECODE=1 python3 -B artifacts/reviewer-g3b/r4_crosscheck.py
PYTHONDONTWRITEBYTECODE=1 python3 -B artifacts/reviewer-g3b/r5_crosscheck.py
```

Evidence index:

- `artifacts/reviewer-g3b/RUN_INDEX.md` — all run UTC/exit/evidence.
- `artifacts/reviewer-g3b/r0-identity.json` — Git/packet/rootfs identity.
- `artifacts/reviewer-g3b/r4-crosscheck.json` — packet 24-trace SQLite/receipt check.
- `artifacts/reviewer-g3b/r5-crosscheck.json` — reviewer-run DB/receipt check.
- `artifacts/reviewer-g3b/r5/oci-full-ro/run.log` — 665 passed / 1 skipped / 0 failed.
- `artifacts/reviewer-g3b/r5/b1-01/`, `r5/b3-01/`, `r5/b3-02-*/` — real-DSH evidence.
- `artifacts/reviewer-g3b/r2/` — malicious probes and crash/guard/usage/error evidence.
- `artifacts/reviewer-g3b/r3/boundary-result.json` — OS-boundary measurement.
- `artifacts/reviewer-g3b/packet-restore-incident.txt` — reviewer tooling incident.
