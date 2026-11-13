# skill_lookup — implementation and evidence (M0 v0.4)

## Status / trust boundary

- **Implementation built in genuine OS isolation; strict TypeScript compile PASS; 8/8 genuine official-registry tests PASS (2026-11-13 UTC).** Two earlier failures are retained below. Native nonempty-string wire-schema support is still absent (E2-03 scope difference for maintainer review); this is not full E2 conformance, E2 Live PASS, or E1b PASS.
- No model request, real Key access, upstream edit, live profile install, host execution of generated TS/build/tests, or npm lifecycle execution has occurred.
- The official npm CLI was used on the host only for dependency acquisition: first `--package-lock-only --ignore-scripts --no-audit --no-fund`, then `npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org` (exit 0, 26 packages). No project code or lifecycle was executed. Final lock resolves only from `https://registry.npmjs.org` and pins the peer closure with integrity hashes. Downloaded tools/Cordis implementation hashes exactly match the installed upstream hashes below.
- Security initially found no images; Podman 4.9.3 image pull failed (`proxy socket permission denied`, exit 125). Security then OS-tested a local `podman --rootfs` boundary with no network, non-root, read-only root, capabilities dropped, no-new-privileges and actual cgroup limits; the plugin successfully built/tested in that boundary using the public Node runtime. Do not bypass denied permissions or run tests on the host to compensate.
- A human must review/freeze source, lock, fixture hash, actual profile and allowed tools before credentialed use. This document cannot grant approval.

Development record: began task claim at approximately **2026-11-13 20:11:31 UTC**, successful run and delivery review by **20:28:45 UTC** (about **17 minutes wall clock**, including security coordination and two failed build attempts). This is agent development time, not model runtime cost or a human productivity benchmark.

## Sources actually inspected (2026-11-13 UTC)

Read AGENTS and all 695 lines of M0 v0.4, then fetched the official tutorials (HTTP 200):

- [Your first plugin](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/): named `apply`, `inject`, context-owned automatic cleanup.
- [Build a tool](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/tool): `defineTool`, typed parameters, canonical output schema/render.
- [Package and install](https://deepseek-harness.github.io/deepseek-harness/en/develop/basic/publish): `dsh.bundle.patch`, package-name patch rows, exact `engines.dsh`, host-shared peer/dev dependencies. No `prepare`, install or other automatic lifecycle scripts were added.

Read-only local upstream inspection under `/usr/lib/node_modules/@deepseek-ai/dsh/`:

- `package.json`: DSH **0.2.1-rc.2**. npm official registry metadata independently returned the same version and tarball integrity; no `gitHead` was published, so a Git commit is **UNKNOWN**, not invented.
- `node_modules/@deepseek-ai/cordis/package.json`, `lib/types/{context,fiber,registry}.d.ts`: Cordis **4.0.5**, `ctx.plugin()`, `fiber.await()/restart()/dispose()`, no `ctx.start()` invented.
- `node_modules/@deepseek-ai/dsh-tools/package.json`, `lib/types/{index,schema,json-schema,testing}.d.ts`, implementation `lib/index.js`: tools **0.2.1-rc.2**, `ToolRuntime` requires `systemPrompt`, register uses scoped Cordis effects, `schemas()`, `get()`, `execute({callId,name,arguments,signal})`; failures normalize as `INVALID_ARGS` / `UNKNOWN_TOOL`.
- `node_modules/@deepseek-ai/dsh-system-prompt/lib/types/index.d.ts`: genuine prompt registry `assemble().tools` (no model needed).
- `node_modules/@deepseek-ai/dsh-tool-todo/lib/index.js`: installed real tool's object output schema and render convention.

Upstream installed implementation SHA-256:

| Module | SHA-256 |
|---|---|
| dsh-tools/lib/index.js | `1e53932e7c4213ea24a7d87f06960b7a7702cb21f8a5741c97242b4a470a442a` |
| cordis/lib/index.js | `6a9394c0877ff45218818c6e815edd038f8057e1a1deb390a8d43ec81c57691e` |

## Minimal ABI delivered to foundation

Source [index.ts](../plugins/skill-lookup/src/index.ts); build output is `plugins/skill-lookup/lib/index.js`. Genuine container-built artifact bytes/base64 and SHA-256 are retained in [offline-complete-deps.log](../plugins/skill-lookup/evidence/offline-complete-deps.log); the ephemeral container output was not loaded/executed on the host. Rebuild in the same approved isolation or recover only the four explicitly named artifact payloads with a data decoder; never treat logs as executable code.

```ts
export const name = 'autoteacher-skill-lookup'
export const inject = ['tools']
export function apply(ctx: Context): void
```

`apply` loads the fixed fixture snapshot and registers **the official** `defineTool` via `ctx.tools.register`. The official Cordis fiber owns cleanup. There is no ABI stub, alternative tools registry, mock `Context`, model adapter, shell tool, network client, or generic read-file tool.

- Tool: `skill_lookup({skill_id: string})`.
- Success canonical value: `{id,title,prerequisites,objectives,source_version}`. `binary_search.prerequisites` is exactly `['ordered_search_space','monotonicity','loop_invariants']`.
- Unknown nonempty ID: `{error:'SKILL_NOT_FOUND',skill_id,source_version:'m0-skills-v1'}`; a normal explicit not-found canonical outcome, not an unexpected exception.
- Output is an enforced closed-object `oneOf` contract and JSON text rendering for the model. This differs intentionally from the taskbook sketch's unstructured JSON-in-string canonical value.
- **Schema limitation:** the installed official schema subset has no `minLength`, `pattern`, `not`, or other string-length constraints. Required/string rejects missing/wrong-type input; a project semantic validator raises the official `ToolArgsError` (`INVALID_ARGS`) on empty/whitespace IDs **before lookup**. The test explicitly asserts blank strings PASS the native wire schema before the project layer rejects them. Do NOT describe E2-03b as native schema rejection; exact E2-03 acceptance remains a maintainer review issue. Nonempty unknown strings are not restricted to a fixture enum (which would defeat not-found).
- Official parameter-root schema is open. Extra keys do not select any paths or other behavior; only `skill_id` is read. No unsupported `additionalProperties` root DSL extension is fabricated.

## Fixture / packaging

Canonical input [skills.json](../fixtures/skills.json) is public sample data only, separate from evaluation cases. SHA-256: `6988fc43029688fbe60fa401e7fe460a59441717afc88c7664958299b1835300`; source version `m0-skills-v1`.

The build [copy-fixture.mjs](../plugins/skill-lookup/scripts/copy-fixture.mjs) copies exactly that file into `lib/skills.json`, sets mode 0444, and writes `lib/fixture.sha256`. This makes the npm bundle self-contained instead of relying on fragile paths outside an installed package. Editing canonical fixtures requires rebuilding and reapproving the bundle; changes are not live hot-reloaded.

Runtime opens only `new URL('./skills.json', import.meta.url)` with `O_RDONLY | O_NOFOLLOW`, rejects non-regular / >64KiB fixtures, validates version/shape/duplicate IDs, and fails closed before tool registration if invalid. No runtime fixture path is configurable. Activation retains private frozen metadata; each call returns a new canonical object. This is a read-only implementation policy, **not** a substitute for OS-level read-only mounts or an E5 sandbox PASS.

Bundle [package.json](../plugins/skill-lookup/package.json) exports built ESM and declares `dsh.bundle.patch`; [cordis.patch.yml](../plugins/skill-lookup/cordis.patch.yml) inserts the same package name/id. Host-shared `cordis` and `dsh-tools` are peer + dev dependencies, per the official packaging guide. [package-lock.json](../plugins/skill-lookup/package-lock.json) locks official packages; TypeScript **5.9.3**, `@types/node` **22.19.0**, Node **22.23.2**, npm **10.9.8** were selected. No package install/build lifecycle is enabled.

## Build debugging history (raw failures retained)

1. [offline-first.log](../plugins/skill-lookup/evidence/offline-first.log): genuine container compilation under 512MiB memory; V8 default heap ~256MiB exhausted, orchestrator exited 1. No tests reached.
2. [offline-bounded-retry.log](../plugins/skill-lookup/evidence/offline-bounded-retry.log): security/lead agreed bounded 1GiB development compiler environment + Node 768MiB heap, same access restrictions. Strict `tsc` exited 2: published `dsh-llm` declarations import `@deepseek-ai/dsh-attachment`, but the upstream manifest lists it only as a devDependency. The ordinary tools peer closure omits it. Fixed only this plugin's devDependencies by explicitly pinning official attachment **0.2.1-rc.2**; official `npm install --ignore-scripts` added 1 package (exit 0). No upstream edit, ABI substitute, `skipLibCheck` or relaxed type settings.
3. [offline-complete-deps.log](../plugins/skill-lookup/evidence/offline-complete-deps.log): complete-dependency isolated rerun **exit 0**; strict `tsc` exit 0, fixture copy exit 0, tests **8 passed / 0 failed**. Actual uid **65534**, inherited environment only `HOME/HOSTNAME/PATH`, actual cgroup `memory.max=1073741824`, `pids.max=32`, `cpu.max=100000 100000`. Compiler memory configuration is separate from the security candidate runner's <=512MiB policy; it does not alter that policy or claim E5 acceptance.

Final source SHA-256 `a618fb029faf7606b64549d6f0ea82259af1a2c5fb2dce27119b7d1b22115346`; final dependency lock `8ed939c93d14fecf838a35e0122717b931f5bdb7d55af7023a5cb1ef3d3e1c73`; successful raw log `4781b912958559125f44fc0280656e885d6d91d8c77052d8838181dd8dc76b9d`. Generated JS `521bc0f1126d895de84ebe61fd58c978a5bcae9b4c334f1fd417faee88483b0b`; generated declaration `4831b65d75146d3bf6e598f5261f2b8eb66d7f335159c62feb9e370914e4150e`. The public fixture hash above matches the built snapshot.

## Reproduction — isolated execution only, NOT host instructions

Security supplied and probed the execution boundary used below. Dependency acquisition may use network only in a no-credential dependencies stage with scripts disabled. Freeze that stage before copying untrusted source. Then deny network, real credentials, private data, Docker socket and host-sensitive mounts; enforce resource limits and allow writes only to disposable build workspace/tmp:

```sh
# Dependencies-only stage; official package manager, no project execution:
npm ci --ignore-scripts --no-audit --no-fund --registry=https://registry.npmjs.org
# In the verified no-network/no-credential build/test sandbox ONLY:
npm run build
npm test
```

Repository-relative structure must include both `plugins/skill-lookup/` and `fixtures/skills.json`; dev/test dependencies must not be omitted. The build is plain `tsc` plus explicit fixture copy, not a bundled ABI replacement. Do not use `npx` auto-fetch or set `skipLibCheck` to hide upstream type incompatibility.

The actual successful sandbox command was the following (run from the plugin directory). `.sandbox-stage` contained only the explicit public plugin source/dependency allowlist plus the public fixture. [orchestrate.mjs](../plugins/skill-lookup/sandbox/orchestrate.mjs) copies those to disposable `/work`, runs the three Node commands without a shell, and emits four artifact payloads. Rootfs is security-owned; no host private home, Key, Docker socket, evaluation labels, or real DSH home is mounted.

```sh
timeout 90s podman run --rm --name at-m0-plugin-test --rootfs \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges --user 65534:65534 \
  --pids-limit 32 --memory 1g --memory-swap 1g --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 75 --systemd=false \
  --mount 'type=bind,src=/root/Autonomous Teacher/plugins/skill-lookup/.sandbox-stage,dst=/project,ro=true' \
  '/root/Autonomous Teacher/artifacts/security/rootfs' \
  /usr/bin/node /project/orchestrate.mjs
```

After human approval only, a disposable profile can link the **built** bundle using the official `dsh plugin --profile <disposable> add <absolute-package-path> --ignore-scripts`, inspect composed config, then start the approved restricted runtime. Profile installation / tool allowlisting / real model events are **not tested** here; sdk-minimal includes dangerous tools and must not receive Keys based on this plugin being read-only.

## Executed offline test matrix (genuine isolated official services)

[Test implementation](../plugins/skill-lookup/test/plugin.test.mjs) uses real official Cordis `Context`, `SystemPrompt`, and `ToolRuntime`, not a homemade registry or ABI shim. No provider, agent loop, credentials, runtime profile, or model is started.

| Test | Assertion | Status |
|---|---|---|
| E2-01 | injection, one registered tool, projected schema + prompt assembly, exact SkillInfo and rendering | PASS (offline registry) |
| E2-02 | arbitrary unknown IDs / traversal-looking strings return fixed explicit not-found | PASS (offline registry) |
| E2-03a | official schema missing/wrong type rejection; execution `INVALID_ARGS` | PASS (offline registry) |
| E2-03b | native blank acceptance documented, separate project semantic rejection `INVALID_ARGS` | PASS (offline registry); native nonempty schema unsupported |
| E2-04a | official fiber restart x3 gives identical results / no duplicates | PASS (offline registry) |
| E2-04b | two fresh OS processes boot real registries and match the fixture | PASS (offline registry) |
| E2-05 | dispose removes schema/prompt/get visibility, dispatch `UNKNOWN_TOOL`, remount single registration | PASS (offline registry) |
| fixture | build/source digest match, read-only bits, unchanged bytes, frozen result and isolated snapshot | PASS (offline registry) |
| E1b / E2 Live | actual model-originated tool events x3 on approved primary route | BLOCKED: human security approval and live execution not granted |

Registry/fiber/process restart assertions are not a claim that CLI profile removal or full credentialed DSH Runtime restart already passed. PASS entries above refer only to the preserved genuine offline run and its exact assertions. Profile-level install/remove/full runtime restart and model-originated calls remain NOT TESTED / BLOCKED pending their own approved integration evidence.
