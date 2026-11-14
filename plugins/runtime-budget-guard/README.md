# Runtime budget guard (logical-stream pre-dispatch middleware)

A real public Cordis plugin for the locked DSH `0.2.2-rc.2` runtime. It registers
the **outermost** global `llm/stream` waterfall listener and commits a unique
reservation to the fixed-scope stdio bookkeeping broker **before** `next()` is
called or iterated. A denied or unavailable reservation never enters any provider
adapter. A `finally` block settles or fails each unique reservation exactly once.

This is bookkeeping middleware, **not** an authorization layer, Key proxy, OS
sandbox, provider-usage authenticator or LiveGate. It controls one candidate
logical model stream; it does not bound a provider library's internal HTTP/Files
retries. See [docs/RUNTIME_BUDGET_GUARD.md](../../docs/RUNTIME_BUDGET_GUARD.md)
for the full boundary, test evidence and integration requirements.

## Shape

- `name` / `inject`: `autoteacher-runtime-budget-guard` / `['llm']`
- `apply(ctx, config)`: validates the frozen config, creates one broker child
  client, registers `ctx.on('llm/stream', ..., { prepend: true })`, and registers
  broker shutdown as a Cordis fiber effect.
- On any configuration error the plugin registers a **deny-all** middleware
  (`BOOT_INVALID`, fail-closed) instead of letting the loader continue without a
  guard. The upstream loader itself logs and continues when a plugin throws, so
  integration must also assert the `RBG_BOOT` marker before traffic.
- v0.5 PR1: provider-internal automatic retry is disabled for admitted profiles
  (`maxRetries` must be 0); every logical stream counts as one request + one step;
  `requestDigest` is post-hoc audit (`REQUEST_INTEGRITY_UNCERTAIN`) and NOT a
  pre-send interception; settlement uncertainty is machine-readable
  (`RBG_RESULT`), fails the call and latches later dispatches; task IDs are
  `rbg-` + sha256(NFC sessionId); public logs are allowlisted/hashed, raw broker
  stderr only goes to an explicitly configured restricted file.
- Built output: strict TypeScript 5.9.3 (`tsc -p tsconfig.json`, `strict`,
  `noUncheckedIndexedAccess`, `exactOptionalPropertyTypes`).

## Config (profile-provided, never client text)

```yaml
policy:
  provider: offline-test-only            # explicit synthetic fixture route only
  model: fixture-v1
  brokerScopeId: fixed-offline-scope
  maxOutputTokens: 1024                  # request maxTokens bound, 1..1024
  maxInputTokens: 2500000                # conservative input upper bound
  maxProviderRetries: 0                  # v0.5 PR1/M0: provider auto retry disabled; nonzero rejected
  purposes: [conversation, compaction, judge]
broker:
  python: /opt/python/bin/python3.11     # fixed absolute interpreter
  pythonPath: /project/src:/deps         # fixed absolute module path
  configPath: /probe/config.json         # fixed read-only broker startup policy
  configSha256: "<64 lowercase hex>"     # policy bytes are hash-checked at load
  cwd: /work
  requestTimeoutMs: 5000
  startupTimeoutMs: 8000
```

The broker startup policy bytes must be the reviewed synthetic fixture policy
(`v:1`, `synthetic:true`, one `offline-test-only`/`fixture-v1` route, nonzero
synthetic prices, explicit fee and usage rules). The guard checks the exact file
hash and cross-checks scope id, route/model, price rules and usage rules before
spawning anything.

## Broker protocol

One fixed child argv (`python -B -m autoteacher_m0.accounting.broker --config
<fixed path>`), explicit environment whitelist (`PATH`, `HOME`, `PYTHONPATH`,
`PYTHONDONTWRITEBYTECODE`, `TMPDIR`), no shell, no client parameters, bounded
16384-byte NDJSON frames, serialized requests and bounded response timeouts. If
the child fails, exits, times out or returns a malformed/mismatched reply, the
guard fails closed permanently (no respawn). Settlements are never retried: an
uncertain settlement leaves the reservation pending and blocks later streams.

## Test

- `npm run build` compiles `src/` to `lib/` with the pinned TypeScript.
- `npm test` runs the committed PR1 targeted tests (`tests/guard-pr1.test.mjs`):
  real Cordis `LlmRuntime` public waterfall + the committed fake NDJSON broker
  fixture + scripted providers. Execute only inside the reviewed credential-free,
  no-network, non-root, read-only OCI boundary; never run this package or its
  generated code on the host. Historical phase5 evidence remains under the
  parent repository's gitignored `artifacts/` and was not rewritten.
