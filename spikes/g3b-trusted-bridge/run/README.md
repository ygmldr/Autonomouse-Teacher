# G3-B B3-prep run scaffolding (NOT B3 PASS)

Container-only. This directory was prepared in parallel with B2 finalization.

## Status (2026-11-16, after B2 `7c6545d`)

- Non-DSH UDS smoke **PASS** in the fixed rootfs at B2 `7c6545d`:
  ack(accepted=true, request_id=transport_id) → 2× whitelisted text-delta →
  finish(stop); Fake counter=1 / synthetic receipt=1; Broker reservation=OK,
  claim=COMPLETED; attempt journal=SETTLED; no Key env; rootfs before/after
  `25491e45…`. This proves integration plumbing only, **not** real DSH, not B3 PASS.
- Log: `artifacts/g3b-trusted-bridge/logs/b3prep-smoke-20261116T194641Z.log`;
  evidence: `artifacts/g3b-trusted-bridge/stage-b3/evidence/`.
- Earlier B2 thread-affinity defect (`AttemptJournal` sqlite cross-thread) was
  fixed by B2 `7c6545d` (`check_same_thread=False`+lock); B3-prep did not edit B2.
- Real DSH B1-01 has NOT been run; `suite.py --mode dsh` is gated by
  `G3B_ENABLE_DSH=1` and `worker.py` is scaffold-only until task-91/B2 final freeze.

## Scenario registry (task-91 / B3)

`python /probe/run/suite.py --mode list` emits `SCENARIOS`; entries are
explicit skeletons/TODO, not PASS:

- `b1-01-real-dsh-echo` — skeleton gated on B2 freeze; must pass ack/chunks/
  usage/finish + Fake counter=1 + Broker reservation/claim + journal SETTLED.
- `b1-02-tool-skill-lookup` — TODO; depends on captured canonical tool schema.
- `b2-crash-reconcile` — TODO; B2 crash hooks, no resend, conservative state.
- `b2-concurrency` — TODO; two clients, serialized ledger/journal, no cross-stream.
- `b2-resource-limits` — TODO; oversized/depth/chunk/deadline fail-closed.
- `b2-guard-separate-evidence` — blocked on Lead O-4 approval; no Guard code here.
- `b3-negative-isolation` — TODO; Key/network/spawn/rootfs negatives.

## Commands

```bash
# host: assemble stage-b3 and run non-DSH UDS smoke (logs/evidence preserved)
bash spikes/g3b-trusted-bridge/scripts/run-suite.sh

# after B2 fix: real DSH B1-01 (run/worker.py) is expected to be invoked here
G3B_ENABLE_DSH=1 ...  # intentionally not wired until B2 freeze/task-91
```

## skill_lookup canonical SHA-256 capture（B3 implementation plan）

Admission `tool_schemas` must equal B2's digest:
`sha256(canonical_json(tool).encode())`, where canonical JSON is
`json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`.
Do NOT hash the provider-side JSON, field order, or the DSH tool object's
serialization.

Capture plan (no B1/B2 edits):
1. Start a throwaway raw AF_UNIX server at the frozen `/work/g3b/bridge.sock`
   (Python `socket`, no BridgeServer) that reads exactly one request line.
2. Launch real DSH with the G3-B bridge patch and `sdk-minimal` profile, then
   call `generate` once; the B1 adapter sends the fully assembled request before
   any response. The throwaway server saves the request `payload.tools`, writes
   a synthetic `ack` then an `error`, and exits.
3. For each captured tool, compute canonical SHA-256 exactly as above; write
   `{"name": ..., "sha256": ...}` entries into the concrete admission JSON.
4. Never derive the digest from the skill-lookup plugin's static schema unless
   a capture proves DSH sends byte-identical canonical tools; DSH may add/rename
   `parameters`/`inputSchema` fields.
5. Record the capture request envelope + tools base64/sha256 in `stage-b3/`.

The capture helper is intentionally not written/running yet (B2 freeze first);
this avoids producing a schema value from a moving DSH/skill plugin.

## Layout

- `worker.py` — launcher-side Controller + real `DeepSeekHarness` skeleton.
- `suite.py` — `smoke` (stub UDS client, non-DSH) and gated `dsh` modes.
- `common.py` — fixed config generation/controller launch/evidence collection.
