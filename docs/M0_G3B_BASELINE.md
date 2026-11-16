# M0 G3-B B0 — 现场基线冻结（Baseline）

> Gate：**G3-B / B0-01..B0-04**（只读核实 + 设计冻结输入；本文件不实现、不运行项目测试）
> Owner：broker-docs（B0 文档/冻结；B1/B2 为独立实现 Agent）
> 基线观察时间：2026-11-16 ~19:05 UTC
> 任务书：`docs/Autonomous_Teacher_M0_G3B_Trusted_Bridge_Agent_Execution_Plan_v1.0.md`（699 行）
> 证据矩阵：`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`（实际 33 个 case_id）
> 性质：**B0 基线记录**，不是 G3-B 测试 PASS、不是 OS 信任边界证明、不是 Live 授权。
> **v1.1 修订**：2026-11-16 Lead B0 审计后同步目录名/Fake 所有权（`spikes/g3b-trusted-bridge`；Fake 归 B2）；本文件仍只记录基线事实。

## 0. 结论

- **B0 基线：PASS（仅身份/环境/输入核实范围）**。HEAD 可复原；父链、G2-L1.2/G3-A 提交、G3-A Spike 与 Packet、固定 rootfs/deps/target/runtime 均可现场复算；无未解释源码漂移。
- **B0-02（OS 信任边界）只能 BLOCKED**：本 Gate 计划中的候选 DSH、Controller、Broker、Fake 都在同一容器、同一 UID `65534`；文件/socket 权限不能证明候选无法读取/写入可信 DB 或控制面。允许的结论上限是 **`PASS_FOR_IN_PROCESS_INTEGRATION_ONLY`**；`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE` 必须留到不同 OS 主体/namespace/UID 的 G3-D。
- G3-B 所需的 **Route/Model Tuple、UDS 传输、Admission、Attempt Journal、Observation→Broker settle 适配** 已在 `docs/M0_G3B_DESIGN_FREEZE.md` 冻结；实现前需 Lead 对 §7 的 5 个开放决策签核。
- 本文件与设计冻结在 B0 docs commit 入库；任务书/证据矩阵按原字节在同一轮先提交。**未改 src/spikes/tests/scripts/plugins/artifacts**。

## 1. Git / Code Tree 身份（现场）

| 项 | 实测值 |
|---|---|
| observed HEAD（B0 开始） | `a507e25c9f81967d3402fea8fb0f2b323cd27f0f`（`docs: archive G3-A provider bridge spike report`） |
| HEAD parent | `64b057bf4c6ce9ae7f412f0e2ecff354d5640709`（G3-A spike implementation） |
| HEAD tree | `54b76c4715319aeadb41b84396593ec5e73d8d64` |
| `src` subtree | `8b92ac5143a0c963f46b77a56bf487c5da0edf01` |
| tracked files | 218 |
| `git archive --format=tar HEAD` SHA-256 | `6a0e08400eb73b34dbebdb626786bd30e10e0b7643cd82471b1ee562dd5e0f64` |
| `git ls-tree -r HEAD` 文本 SHA-256 | `3fde8860ae84f57398ddbffbe63dc0d42d7498c67d8cbcea59924d13cfe29f71` |
| B0 开始时 worktree | `?? docs/Autonomous_Teacher_M0_G3B_Trusted_Bridge_Agent_Execution_Plan_v1.0.md`、`?? docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`；无 tracked 修改 |
| B0 文档提交后 | 由 B0 docs commit 记录；`git status --porcelain` 应为 clean（见交付消息） |

父链现场（`git rev-list --first-parent -5 HEAD`）：

```text
a507e25 docs: archive G3-A provider bridge spike report
64b057b feat: add G3-A provider bridge spike (no-key)
28e260d docs: archive G2-L1.2 hardening report and fix RED2 counts
53d7ba5 fix: harden G2-L1.1 cancellation semantics, run_id validation, and atomic completion journaling (no-key)
ce899ec docs: archive G2-L1.1 independent review (PASS, P2 findings)
```

复算命令：

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD && git rev-parse HEAD^{tree} && git rev-parse HEAD:src
git ls-tree -r HEAD | sha256sum
git archive --format=tar HEAD | sha256sum
git rev-list --first-parent -5 HEAD
git status --porcelain -uall
```

**源码/测试相对于 G2-L1.2 `53d7ba5` 的已知变化**：只有 `docs/`（G3-A 报告）与新增 `spikes/g3a-provider-bridge/`（G3-A commit `64b057b`）；`src/tests/config/scripts/plugins` 不由 G3-A 修改。G3-A Packet 的 `delivery_head=28e260d`，当前 HEAD 在 docs 之后为 `a507e25`；Spike 源码字节见 §4。

## 2. 环境/容器指纹（现场复算）

| 项 | 值 | 现场来源/复算 |
|---|---|---|
| fixed rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . \| sha256sum` |
| Python deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同上，目录 `artifacts/foundation/deps` |
| DSH runtime 0.2.2-rc.2 | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（182,717,632 bytes） | `sha256sum artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64`；容器内 `--version` = `0.2.2-rc.2` |
| Node | `/usr/bin/node`（rootfs）SHA-256 `3517c2df0b2f8cd7f422b4b8450ef81c6889f08eb03e281d6de9079b15e6a327`；`v22.23.2` | `sha256sum artifacts/security/rootfs/usr/bin/node`；容器内 `node --version` |
| Python | `/opt/python/bin/python3.11` SHA-256 `cd947cb6d5b3f8589a2a4708198dc104474e47876c6b8215ab8b410592ab7cc1`；`3.11.15` | `sha256sum artifacts/security/rootfs/opt/python/bin/python3.11`；容器内 `--version` |
| target stage | normalized tar `f8f7520364cd07084012783fd6c3c99707aac8d5b0851253375e05d6ca14901b` | `-C artifacts/m0-runtime-integration/stage/target .` 按 §2 命令 |
| target `runtime/node_modules` | `2884de23d75ce7514a40a2ac76ff00cd1e3062ba1cb8a0af0b2ca19fdd063d53`（19 个 `@deepseek-ai` 包） | `-C .../stage/target/runtime/node_modules .` |
| target `runtime/skill` | `636bb021b1751d965a1a368e56560a43cc32bab8e88efd7e49ceb77752302bdc` | `-C .../stage/target/runtime/skill .` |
| DSH `@deepseek-ai/dsh-llm` package.json | `88e094f569429dea011cf9c05dbf63a09f55a07e50b5d6a6187ea150ada2c8bd`；`src/types.ts` `cfe8237e…`、`src/index.ts` `45f7d934…` | `sha256sum .../dsh-llm/package.json src/types.ts src/index.ts` |
| podman | `podman version 4.9.3` | `podman --version` |

容器启动参数（以 G3-A `scripts/run-suite.sh` 为模板，B1/B2 必须复用该安全边界）：

```text
--rootfs artifacts/security/rootfs
--network none --http-proxy=false --unsetenv-all
--env PATH=... --env HOME=/work --env PYTHONPATH=/project/src:/deps --env TMPDIR=/tmp
--read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges
--user 65534:65534 --pids-limit 64 --memory 1g --memory-swap 1g --cpus 1
--tmpfs /tmp:rw,noexec,nosuid,nodev --tmpfs /work:rw,noexec,nosuid,nodev
--workdir /work --timeout ... --systemd=false
```

B0 现场只读探针（固定 rootfs 容器，非项目测试）：

- **AF_UNIX 可用**：`socket(AF_UNIX, SOCK_STREAM)` bind/listen/connect 成功（`AF_UNIX b'ok'`），`SOCK_DGRAM` 也可建；**AF_INET 被拒绝**：`PermissionError:[Errno 13]`。
- **Node AF_UNIX 可用**：`/usr/bin/node` 在同一 rootfs 容器内 `net.createServer` + `net.connect` 成功（`NODE_UDS_OK ok:ping`，exit 0）。
- uid/gid=`65534/65534`；`env` 中 `KEY/TOKEN/SECRET` 变量 **0 个**；`/root/.config/autoteacher` **不存在**。
- Node/Python/DSH runtime 版本探针：`v22.23.2` / `Python 3.11.15` / `0.2.2-rc.2`，exit 0。

复算命令：

```bash
ROOTFS=artifacts/security/rootfs; DEPS=artifacts/foundation/deps
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$ROOTFS" . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "$DEPS" . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/m0-runtime-integration/stage/target . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/m0-runtime-integration/stage/target/runtime/node_modules . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/m0-runtime-integration/stage/target/runtime/skill . | sha256sum
sha256sum "$ROOTFS/usr/bin/node" "$ROOTFS/opt/python/bin/python3.11" \
  "$DEPS/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
```

No-Key/禁网基线复现（容器只读探针，不运行项目代码）：

```bash
podman run --rm --rootfs --network none --http-proxy=false --unsetenv-all \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work --env TMPDIR=/tmp \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 16 --memory 256m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev --tmpfs /work:rw,noexec,nosuid,nodev \
  --workdir /work artifacts/security/rootfs /opt/python/bin/python3.11 -c \
  'import os,socket; print(os.getuid(), [k for k in os.environ if "KEY" in k or "TOKEN" in k]);
   socket.socket(socket.AF_INET, socket.SOCK_STREAM)'   # 预期 PermissionError
```

## 3. G3-A Spike 与 Packet 一致性（现场）

| 项 | 值 |
|---|---|
| G3-A implementation commit | `64b057bf4c6ce9ae7f412f0e2ecff354d5640709`（14 个文件，均 `spikes/g3a-provider-bridge/**`） |
| G3-A docs commit | `a507e25c9f81967d3402fea8fb0f2b323cd27f0f` |
| G3-A Packet | `artifacts/review-packet-g3a-28e260ded339498945cfd0bf5eb530003aead1da/`（79 文件） |
| Packet `manifest.json` | `6cd4aa984783e5c6dc037c0a93c2a86a9fabbbb0b51ba8720989a8728b0e95e5`；`hashes.sha256` `d36e8a7b…`；`env/identity.json` `403c9c39…` |
| Packet checksum | `(cd packet && sha256sum -c hashes.sha256)` → **78/78 OK，exit 0** |
| Spike 源码 14/14 | Packet `source/g3a-provider-bridge/**` 14 文件与 `git show 64b057b:spikes/g3a-provider-bridge/**` 逐文件 SHA-256 **14/14 MATCH** |
| 文件数说明 | 任务描述曾写“15 files”；实际 Git commit 与 Packet 均为 **14 个文件**（README、package、tsconfig、src/index.ts、fake、config、run/{worker,suite}、scripts 5 个、test 1 个）；B0 以实际为准，本文件不编造第 15 个文件 |

可复用模块（G3-A 已验证，但需 B1 重写为 UDS/无 spawn adapter）：

- `spikes/g3a-provider-bridge/src/index.ts`：`LlmAdapter.stream` 真实边界；`GenerateOptions` 校验、`StreamChunk` 归一、`AbortSignal` 处理、`ctx.llm.registerAdapter`（见 §4 API）。
- `fake/fake_provider.py`：stdin 单行原始字节 receipt、`G3A_*` 合成模式、PDEATHSIG 父死清理；G3-B 需替换为固定 G3-B 收据契约（见设计冻结）。
- `run/worker.py`/`run/suite.py`：真实 SDK harness、Session resume、`skill_lookup` tool turn、EOF/error/cancel 场景；G3-B 可复用 worker/suite 骨架，但必须移除“插件自己 spawn fake”路径。
- `config/bridge.patch.yml`：真实 provider 禁用、只加载 bridge/skill；G3-B 需新增 Guard 组合与 G3-B bridge 入口。

限制（不得继承为安全证明）：G3-A 的 Fake 子进程由 DSH 插件 `spawn()`，同容器同 uid；不是可信 Controller；无 Guard/Broker；`g3a-bridge-test/bridge-v1` 不满足 G2 Broker `_ROUTE/_MODEL`；request/header 次数不能用于计费。

## 4. 现场源码入口（B0 已读，B1/B2 继续以实际行为准）

| 组件 | 现场入口 |
|---|---|
| DSH `LlmAdapter` | target stage `@deepseek-ai/dsh-llm/src/index.ts:223`（abstract class），`registerAdapter` `:416`；`GenerateOptions` `src/types.ts:564`；`StreamChunk` `src/types.ts:496` |
| G3-A Adapter | `spikes/g3a-provider-bridge/src/index.ts:247-497`（`BridgeAdapter.stream`、`ctx.llm.registerAdapter`、`spawn` fake at `:323`） |
| G3-A Fake | `spikes/g3a-provider-bridge/fake/fake_provider.py:125-161`（receipt）、`:164-265`（stdin/modes） |
| G3-A harness | `run/worker.py:122-180`（harness/run/resume）、`run/suite.py:200-338`（echo/tool/session/eof/error/cancel+merged config） |
| Egress | `src/autoteacher_m0/security/egress.py:123`（Prepared）、`:169-219`（strict schema，含 schema_version）、`:249`（DispatchPermission）、`:543-605`（claim_for_request）、`:704-810`（TrustedEgressTransport）、`:685-701`（consume_permission）、`:528-535`（legacy unbound claim） |
| Broker | `src/autoteacher_m0/accounting/broker.py:23-24`（`_ROUTE/_MODEL`）、`:140-199`（5 op 校验）、`:303-357`（handle）、`:201-251`（reserve/snapshot）、`:253-301`（settle/fail + completion precheck） |
| Ledger | `ledger.py:135`（bind_call）、`:199`（claim_dispatch）、`:282`（claim_for_call）、`:307-327`（journal precheck）、`:339`（reserve）、`:384`（settle）、`:424`（snapshot） |
| Observation | `observation.py:106`（ProviderObservation）、`:235-279`（to_usage）、`:339-…`（deliver_observation）、`:290-321`（provenance capability） |
| Usage mapping | `broker_usage.py:56-61`（validate_usage）、`:69-97`（official_usage） |
| Guard | `plugins/runtime-budget-guard/src/index.ts:739`（apply/BOOT）、`:775`（`llm/stream` prepend）、`:478/507`（reserve/settle）、`:199/201`（provider/model regex） |
| Skill | `plugins/skill-lookup/src/index.ts:87-92`（`ctx.tools.register(defineTool('skill_lookup'))`） |
| SDK spawn | `artifacts/foundation/deps/deepseek_harness/client.py:89-99`（`subprocess.Popen` 固定 stdin/stdout/stderr，**无 `pass_fds`**） |

## 5. G0 差距表（G3-B 需要什么）

| 能力 | 现状 | G3-B 决策 |
|---|---|---|
| 真实 DSH 0.2.2-rc.2 / SDK / Session / Tool | G3-A 已证明可运行；Spike 直接 spawn Fake | **复用** runtime/SDK；B1 新增 UDS adapter，不修改 DSH 核心 |
| CallIdentity / Prepared / Bound Claim / Egress | G2 已提供；`claim_dispatch_for_request` 强制 expected binding；旧 unbound 仍在 | **复用**；生产路径禁用 `claim_dispatch()`/`require_claim()` legacy；B2 只调用 bound 路径 |
| Broker/ledger 持久预算与 reservation | G2 已提供 5 op，真实 SQLite/stdio；completion precheck 已同事务 | **复用**，不新增协议 op（见设计冻结 §6 兼容性） |
| Attempt 持久化 | 不存在；G2 仅内存诊断 | **新增** Controller-owned SQLite attempt journal（WAL+FULL），begin 先 commit 再发送 |
| 可信 Controller / IPC / Admission | 不存在（G3-A 插件自己 spawn Fake） | **新增** `src/autoteacher_m0/bridge/*` + `spikes/g3b-trusted-bridge/*`；Launcher 固定 admission |
| Fake Provider | G3-A Python fake 由插件 spawn，收据只证明 stdio | **新增** B2-owned `spikes/g3b-trusted-bridge/fake/fake_provider.py` + Controller-owned FakeBackend（固定路径、stdin 精确字节、独立 receipt/counter） |
| Guard + Bridge 组合 | G3-A Profile 未加载 Guard；Guard 已独立 15/15 | B3 组合测试；Broker 唯一预算权威，Guard 仅预检/不二次 Reserve（Lead 决策） |
| Observation → Ledger settle | `to_usage()` 返回 `Usage` dataclass，与 Broker `settle` JSON usage **形状不兼容**；但 Controller 从原始字段映射后语义一致（B0 容器 probe 验证 AUTH/PARTIAL/MISSING 的 `Usage` 完全相等） | B2 Controller 原始字段映射；不新增 broker op（见设计冻结 §1.3） |
| OS 信任边界（B0-02） | 同容器同 uid；UDS/DB/Policy 可被同 uid 进程访问 | **BLOCKED**；G3-B 仅结构闭环，G3-D 做不同主体/namespace/UID |
| 真实 provider HTTP/usage/invoice/Live | 全部不存在 | **BLOCKED/UNVERIFIED**；G5 前不做 |

### 5.1 继承的 G2-L1.2 修复（B0 现场确认，不再重做）

| 旧问题（G2-L1.1 报告） | 当前 HEAD 证据 | 状态 |
|---|---|---|
| T1 Provider 进入后异常归因 `NOT_DISPATCHED` | `egress.py:751-777`：进入 provider 前 `mark_dispatch_attempt_started`/计数递增；异常走 `_started_failure` 返回 `ATTEMPT_STARTED`/`BILLABLE_UNKNOWN`（不再报 `NOT_DISPATCHED`） | **FIXED（G2-L1.2）** |
| T2 `call_id` 跨模块 Unicode 不一致 | `accounting/call_identity.py:44-47` 唯一 `canonical_json`（`ensure_ascii=False`）；`egress.py:20-22` 从 accounting 导入，`:222-232` 使用该实现 | **FIXED（G2-L1.2）** |
| T3 Prepared schema_version 未强制 | `egress.py:169-219` `prepared_schema_error` 校验固定版本；`:557-559` claim 前调用 | **FIXED（G2-L1.2）** |
| T4 无效 completion journal 增长 | `broker.py:280-301` completion precheck；`ledger.py:307-327` precheck 与 journal 同事务，拒绝不写行 | **FIXED（G2-L1.2）** |
| T5 `evaluate_descriptor` 消耗 attempt | `egress.py:401-421` 只增 `policy_checks/policy_allowed`，不增 attempts；`_mark_claim` `:461-465` 以 claims 兼容旧 attempts | **FIXED（G2-L1.2）** |

因此 G3-B B1/B2 **不得重复修复** T1–T5；如实现中发现回归，按新 Finding 处理并先报 Lead。

### 5.2 E1–E5 映射（v0.4 强制基准）

- E1–E3（真实模型/工具/成本）：**BLOCKED**（无 Key/无网络；G3-B 仅 synthetic Fake）。
- E4（教学效果）：**NOT RUN**（G6）。
- E5（安全/隔离）：G3-B 只做容器内 no-Key/禁网/非 root/只读/资源限制的结构性证据；**E5-PreLive 不得由 G3-B 声称**；真实 OS/Key 边界留 G4/G3-D。
- GO/CONDITIONAL GO/NO-GO：**DECISION PENDING**；G3-B 完成后仍不是最终 GO。

## 6. 未验证/阻断（B0 如实列出）

1. **B0-02 OS 信任边界 BLOCKED**：候选 DSH 与 Controller/Broker/Fake 同容器同 uid；不能证明候选不能读/写 Broker DB/Policy/Admission 或连接控制面。只允许 `PASS_FOR_IN_PROCESS_INTEGRATION_ONLY`。
2. 真实 DSH + Controller UDS 的**候选 namespace/网络隔离**未验证；AF_UNIX 在固定 rootfs 可用（B0 探针），但同 uid 意味着连接本身不是授权。
3. DSH SDK 单 turn cancel 无公开 API；G3-A 仅 runtime SIGTERM/Adapter AbortSignal；G3-B 继续 worker/runtime 级取消，`UNVERIFIED`。
4. 真实 Provider HTTP/TLS/usage/invoice/billing、远端 exactly-once：**UNVERIFIED**。
5. 生产 BoundBrokerClaimer/TrustedTransport 调用点不存在（G2-L1 报告 F-9）；B2 只能测试级接线。
6. Skill native harness 0.2.2 兼容限制（0.2.1 test harness）仍为 BLOCKED；不得用 0.2.1 PASS 覆盖 0.2.2。
7. G3-A Spike 文件数为 14（非任务描述曾说的 15）；本 B0 以实际 Git/Packet 为准。

## 7. B0 环境基线复现摘要

```bash
# 1) 代码身份
git rev-parse HEAD HEAD^{tree} HEAD:src
git ls-tree -r HEAD | sha256sum
git archive --format=tar HEAD | sha256sum

# 2) 根文件系统/依赖/运行时
sha256sum artifacts/security/rootfs/usr/bin/node \
  artifacts/security/rootfs/opt/python/bin/python3.11 \
  artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/m0-runtime-integration/stage/target . | sha256sum

# 3) 容器 no-Key/禁网/AF_UNIX 探针（固定 rootfs，宿主不执行项目代码）
# 见 §2 的 podman 命令；预期 uid=65534、KEY/TOKEN env=[]、AF_INET PermissionError、AF_UNIX OK、
# /root/.config/autoteacher 不存在。
```

**B0 不做**：不运行 pytest/Node 项目代码/真实 SDK suite；不改源代码；不创建证据 Packet（由 B4）；不进入 G3-B 实现。
