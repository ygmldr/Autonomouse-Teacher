# Task 15 — bounded native startup diagnosis and exact read-only cache

## Outcome (2026-11-13 UTC)

**A new, independent, keyless SDK startup subset now PASSes with the same locked wheel and an exact preseeded read-only native cache.** Actual initialize readiness, an empty registered-tool schema list, graceful runtime exit **0**, invalid-initialize validation/cleanup, and missing-executable cleanup were observed. No diagnostic preload is needed in the final successful control.

This is **not** full H1/E1, Live/model/tool-call validation, Session persistence/resume, or permission to enable the production Adapter/Gate. No `run`, `Session.run`, Session creation, prompt, Fake provider or model request occurred. Previous [task11 failure](<SDK_OFFLINE_PROBE.md>) and [phase2 independent audit](<REVIEW_PHASE2.md#L58-L72>) remain accurate historical observations for the unseeded configuration; neither report nor its raw evidence was rewritten.

Base HEAD was `e0181942161937e93ecd79635d29bca532dae61c`, implementation baseline `c155789557e525925435e7f8a8bf573856d80311`. Read AGENTS, all 695 lines of v0.4, task15 constraints and both prior reports before work. Changes are only this document and [new native evidence](<../artifacts/sdk-native/manifest.json>). Root Git commits remain foundation-owned. Time window: about 21:49:56–22:00:45 UTC for diagnosis/execution; final evidence documentation followed.

## Boundaries kept unchanged

- Reused **SDK/runtime wheel 0.2.2rc2**, native CLI **0.2.2-rc.2**, SHA-256 `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`. Embedded package metadata still reports `0.0.0-dev`; no build commit is invented and no system DSH 0.2.1 substituted.
- Every generated Python/CJS/MJS probe ran **only inside** Podman, no network/proxy inheritance, explicit allowlisted environment, uid65534, cap-drop ALL, no-new-privileges, read-only root and public input binds, no socket/private home/credentials, pids32, memory512MiB, CPU1, bounded wall time. `/tmp` (32MiB) and `/work` (128MiB) stayed **noexec/nosuid/nodev**. There is **no writable-executable mount**.
- SDK env merges with its parent, so the container and [final probe](<../artifacts/sdk-native/stage/probe-final.py>) explicitly reset the environment. Final environment contains only PATH, HOME, PYTHONPATH, PYTHONDONTWRITEBYTECODE, TMPDIR, DSH_RUNTIME_MODE=exe, DSH_RESOURCE_CACHE, NO_COLOR, and the documented `NARB_NATIVE_CACHE_DIR`. It contains **no NODE_OPTIONS**. No Key was read/injected.
- Only already-existing `/probe` and `/deps` bind targets were used. Shared rootfs and foundation deps were neither changed nor replaced. Normalized GNU tar hashes before/after match exactly: rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`, deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`. See [before](<../artifacts/sdk-native/rootfs-before-final.sha256>), [after](<../artifacts/sdk-native/rootfs-after-final.sha256>) and [dependency after](<../artifacts/sdk-native/deps-after-final.sha256>). No new shared mountpoint metadata drift occurred.
- Host activity was trusted tool/file operations and official dependency acquisition (`npm pack --ignore-scripts --registry=https://registry.npmjs.org`). No host probe/package lifecycle execution, native build, upstream edit, module-resolution override, `process.dlopen` patch, native-integrity bypass, or Gate modification occurred.

## Two evidence-driven paths; third stopped as unnecessary

### 1. Public formatting-only preload made the actual failure visible

The [formatting-only preload](<../artifacts/sdk-native/stage/inspect.cjs>) only changes `node:util.inspect.defaultOptions` depth/array/string formatting and writes Node/ABI versions to **stderr**. It does not touch stdout/JSON-RPC or any loader, validation, filesystem or security behavior. It is loaded through public `NODE_OPTIONS=--require=/probe/inspect.cjs`; relevant public references are [Node CLI require](https://nodejs.org/api/cli.html#-require-module), [NODE_OPTIONS](https://nodejs.org/api/cli.html#node_optionsoptions) and [inspect defaults](https://nodejs.org/api/util.html#utilinspectdefaultoptions). Generic documentation availability is not assumed to prove this executable's support: its actual stderr marker confirms the preload ran.

[Path1 log](<../artifacts/sdk-native/path1-inspect.log>) now expands prior `[Object]` attempts and observes:

- Embedded Node **v24.22.2**, modules ABI **137**, N-API **10**.
- The optional prebuild **exists** at `/snapshot/node/node_modules/node-addon-require-builtin-linux-x64-gnu/prebuilt/linux-x64-gnu-napi-v9.node` and is materialized under `/tmp/node-addon-native-custom-loader-65534/native-cache/.../0.1.9/linux-x64-gnu/`.
- That concrete cached native load fails with **`failed to map segment from shared object`**. Two local-build fallback paths separately fail `MODULE_NOT_FOUND`; they are not evidence that the optional prebuild itself was absent.
- SDK initialization remains BLOCKED on this unseeded path; failure cleanup remains PASS. The outer diagnostic exit0 is not initialize success.

This is a concrete mapping failure at a noexec temporary cache path, rather than the former unspecified `[Object]`. The next controlled intervention demonstrates a compatible mapping location without relaxing noexec; no broad claim about all possible ABI/permission failures is made.

### 2. Exact embedded bytes were verified before using the official read-only cache

The public [Node SEA asset API](https://nodejs.org/api/single-executable-applications.html#assets) exposes immutable assets in the **same locked executable**. [Asset discovery](<../artifacts/sdk-native/path2-assets.log>) found `__pkg_manifest__` and `__pkg_archive__`; [manifest inspection](<../artifacts/sdk-native/path2-manifest.log>) located exact archive offsets and recorded compression=2. No snapshot filesystem hooks or module resolution were patched.

Fetched official, exact `node-addon-native-custom-loader@0.1.9` and `node-addon-require-builtin-linux-x64-gnu@0.1.9` tarballs with scripts disabled; [npm provenance/integrity](<../artifacts/sdk-native/native-pack.json>) is retained. A [read-only matcher](<../artifacts/sdk-native/stage/match-embedded.cjs>) reads SEA assets, Brotli-decompresses the four named members, checks original manifest sizes, compares **every byte** with the fetched official files, and logs both digests. [All four exact matches passed](<../artifacts/sdk-native/path2-exact-match-readable.log>), not merely version equality:

| Embedded member / exact candidate | Bytes | SHA-256 |
|---|---:|---|
| native loader implementation | 25080 | `6d83f4e5426895d40820acf507146226a893c5aefba00a08bf0884446160049e` |
| loader package metadata | 840 | `a8ae0ae29211fc65fb482502081f70bae242404f042ddf1091b439471cffae3e` |
| native package metadata | 733 | `3c00dc0affa1e17a5ce682a818c56bb60aa792f5a6ae6fb731a7338102832225` |
| NAPI-v9 native payload | 295392 | `40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f` |

SEA manifest SHA `7ac45c7a47d27cc84d2ccc609039c43db9ffdecc0b2ac399c31c2174c881dcc6`; archive SHA `d9ce86f8342cc61b3c411f3cef2eb91ea213473d074e0a96e99d85a93e050978`. These prove the selected loader/native members match the locked binary, not that the entire binary has a known Git source commit.

One staging error is honestly preserved: [first exact-match preflight](<../artifacts/sdk-native/path2-exact-match.log>) exited1 because a newly generated matcher was mode0600 and unreadable to uid65534. Correcting **only that public stage file's read bit** allowed the match. No sandbox flag/private-file permission was changed, no native load was attempted on that failed preflight, and this was not repeated native startup by luck.

The exact matched [official loader:31–42](<../artifacts/sdk-native/stage/candidates/loader/lib/index.js#L31-L42>) supports `NARB_NATIVE_CACHE_DIR`. Its [existing-file path:74–92](<../artifacts/sdk-native/stage/candidates/loader/lib/index.js#L74-L92>) reuses a deterministic package/version/platform/name path **only when SHA-256 matches the original embedded source**; otherwise it falls back to the source. The original [prebuilt validation:430–445](<../artifacts/sdk-native/stage/candidates/loader/lib/index.js#L430-L445>) is unchanged.

Preseeded only this exact official payload, mode0444, under the task-owned read-only stage:

```text
/probe/native-cache/node-addon-require-builtin-linux-x64-gnu/0.1.9/linux-x64-gnu/linux-x64-gnu-napi-v9.node
NARB_NATIVE_CACHE_DIR=/probe/native-cache
```

The [first cache run](<../artifacts/sdk-native/path2-cache.log>) succeeded with diagnostic formatting still enabled. The [final minimal control](<../artifacts/sdk-native/path2-final-no-preload.log>) **removed NODE_OPTIONS/preload entirely**, additionally asserted the actual empty-registry marker and graceful exit0, verified cache hash/read-only bits and actual mount flags, and also succeeded. Thus success does not rely on formatting code or changed module behavior. The executable and its native validation remain original; the only native-loading configuration change is the official cache directory pointing at an immutable, exact matching file rather than a materialized writable noexec temp cache.

### 3. Side-loaded npm/Node distribution

**NOT ATTEMPTED.** Path2 met the task's actual startup/close/registry stop condition with the original wheel. There was no need to side-load or silently substitute another Runtime. The exact 0.2.2 tools package fetched here was **static API reference only**, not an alternate executed runtime.

## Actual final assertions and limited meaning

| Assertion | Actual result |
|---|---|
| Locked native executable/version/SDK | Original binary SHA unchanged; CLI0.2.2-rc.2 / wheels0.2.2rc2 |
| Actual mounted `/`, `/probe`, `/deps` | ro; checked from container mountinfo |
| Actual `/tmp`, `/work` | rw, nosuid, nodev, **noexec** |
| Session-log upload / dangerous tool/execution/compaction rows | Same restricted patch; merged upload=false and twelve disabled rows asserted |
| Public SDK `start()`/initialize | **PASS**, initialized true, subprocess alive/ready; no input sent |
| Actual registered tool schemas | **[]**, emitted by the real Cordis-injected observer and explicitly asserted |
| Normal close | **PASS**, original runtime exits0; proc cleared, reader threads stopped, waitpid reports no child |
| Invalid maxTokens=0 initialize | **PASS negative**, actual JSON-RPC `JsonRpcError: initialize maxTokens must be a positive safe integer`, cleanup PASS |
| Explicit missing runtime | **PASS negative**, FileNotFoundError, cleanup PASS |
| No model/Session input | No calls authored; observer refuses any accidental llm/stream or agent/request; no such marker occurred |
| Production Adapter/Gate, Live tool registration/calls, Session recovery | **NOT EXECUTED / NOT APPROVED** |

The observer uses genuine `ctx.tools.schemas()` for **registered-definition inspection**, confirmed by the exact-version [official API:299–317](<../artifacts/sdk-native/tools-source/src/index.ts#L299-L317>). With no Session there is no per-agent/per-step resolved ToolSet to inspect; this is not a claim about a future different profile or scoped agent's live tool admission. The underlying sdk-minimal sandbox policy still names danger-full-access; effective OS isolation and disabled tools here do not promote that profile to a credentialed trusted baseline.

Final raw log SHA **`21231d7af8cdc0c02959c5fc02b2bf3991d195cf9b745e30b525947a71fd496d`**; final probe SHA **`189e0bc949bc3a5ec37286cd341b068fef36ccca17bfdc3bfce43c02045c0bca`**. [Machine manifest](<../artifacts/sdk-native/manifest.json>) records provenance, paths, failures, exact identities and safety limits. All own jobs were collected; named task containers were queried absent. No old evidence was overwritten.

## Minimal reproduction — only inside the verified boundary

After separately verifying the manifest/member match and fixed read-only payload, run **trusted container tooling**, not the Python probe on the host. The following is the exact final command from the repository root; the probe itself supplies only the explicit cache env to its official subprocess:

```sh
set -o pipefail
timeout 90s podman run --rm --name at-m0-sdk-native-final --rootfs \
  --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work/user-home --env PYTHONPATH=/deps \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp --env DSH_RUNTIME_MODE=exe \
  --env DSH_RESOURCE_CACHE=/work/resource-cache --env NO_COLOR=1 \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 32 --memory 512m --memory-swap 512m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --workdir /work --timeout 75 --systemd=false \
  --mount 'type=bind,src=/root/Autonomous Teacher/artifacts/sdk-native/stage,dst=/probe,ro=true' \
  --mount 'type=bind,src=/root/Autonomous Teacher/artifacts/foundation/deps,dst=/deps,ro=true' \
  '/root/Autonomous Teacher/artifacts/security/rootfs' \
  /opt/python/bin/python3.11 /probe/probe-final.py
```

Independent verification should replay **this new pinned configuration** and preserve a new log, not rewrite prior BLOCKED evidence. Any later credentialed use, provider/Session tests, budget bridge, changed native payload/version/profile or Gate changes require separate scope, review and human authorization. Current mandatory Live acceptance and overall M0 decision remain BLOCKED / DECISION PENDING.
