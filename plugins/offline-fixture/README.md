# Explicit offline fixture provider

This is a deterministic **non-model** public Cordis `LlmAdapter` test fixture. It is never a production/primary-route fallback and does not grant Live permission.

- Plugin exports: `name`, `inject`, `provider`, `model`, `OfflineFixtureAdapter`, `apply`.
- Exact route/model: `offline-test-only` / `fixture-v1`.
- Explicit opt-in: `AUTOTEACHER_OFFLINE_FIXTURE=1` in an otherwise cleared, no-Key environment.
- Only `skill_lookup` may be registered; load its separately reviewed entry/readonly public data. Disable the real provider and all other tools as in the overlay.
- Complete real assembled history is checked at the public `llm/stream` boundary. Non-fixture routes, auxiliary purposes, images/files, unknown scripts and unsafe tools are refused. Startup exercises the genuine waterfall on a nonexistent NON-real route and asserts it is rejected before any adapter executes.
- Script inputs: `FIXTURE_JSON`, `FIXTURE_TOOL`, `FIXTURE_REMEMBER nonce=<8..48 safe chars>`, `FIXTURE_RECALL`, and the bounded `FIXTURE_INTERRUPT nonce=<...>` fault fixture.
- Recall uses only nonce text in genuine prior **user** messages. There is no nonce map, external state/file/environment lookup, random reply or HTTP implementation. Invocation counters are instrumentation only.
- Terminal usage is explicitly **synthetic**, uncached input 7/output 3/cache read 0/cache write 0/reasoning 0/total 10. Interrupted streams may have no usage. These are not provider bills or a budget bridge.

Dependency acquisition may use the official npm CLI with `--ignore-scripts`. Compilation and all generated code MUST run only in a credential-free, no-network, non-root, read-only-input, bounded OS-isolated environment. There are no automatic lifecycle scripts. `npm run build` is an opt-in isolated build only, never a host command authorized by this README.

The SDK/session evidence probe, native-cache preparation and exact commands are separate experimental artifacts documented in [SDK_OFFLINE_SESSIONS](../../docs/SDK_OFFLINE_SESSIONS.md). Never treat project Mock output, genuine DSH Session events produced by this synthetic adapter, and real DeepSeek Live model evidence as interchangeable.
