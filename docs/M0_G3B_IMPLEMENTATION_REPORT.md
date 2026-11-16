# M0 G3-B Implementation Report

> 状态：**B4 完成，提交独立 Reviewer 前**。本报告请求限定范围裁定 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`，OS Trust Boundary 仍 **BLOCKED**；**不是 Live/GO 授权**。
> Base：`08768165db55351e42364dadf69657d7a2db4a4c`；Implementation：`90402929c710a046e23dd3a3c3dd108b641bc981`（父 `6b1e6b6110e9a366de9fbb358bede28bb6adc24e`）。
> Docs commit 为本报告/Review Request/matrix/`scripts/g3b` 的 B4 docs commit；其 SHA 与最终 packet 的 `docs_sha` 由 B4 向 Lead 汇报。最终 Packet：`artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/`。
> 33 行逐 ID 结果：`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`。

## 0. TL;DR 与明确 Gate 裁定

- 完成真实 DSH 0.2.2-rc.2 + 真实 SQLite Broker + durable Attempt + Fake Provider 的无 Key 端到端闭环；B1/B2/B3/B4 全部在最终 impl `9040292` 下重新核验。
- 33 行矩阵统计：**PASS 28 / PARTIAL 2 / UNVERIFIED 2 / BLOCKED 1**；B3 工作矩阵 22 行聚合统计为 **18 PASS / 2 PARTIAL / 1 UNVERIFIED / 1 BLOCKED**（拆分到 33 行后 B3-10 与 B3-11 各计 UNVERIFIED）。
- 请求 Reviewer 给出 **`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`**：P0 集成/账本/失败关闭证据满足；**B0-02 OS 信任边界如实 BLOCKED**，不签 `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`。
- 仍是 `PARTIAL`：B1-04 cancel 模式、B2-05 request-digest replay；`UNVERIFIED`：B3-10/B3-11；另 B2-10 冲突观测注入有残余说明。
- 0 真实 Key / 0 真实模型 / 0 外部 HTTP；Fake usage 不是供应商账单；本地 Claim 不是远端 exactly-once。

## 1. Actual Git / Runtime / Container Identity

| 项 | 现场值 |
|---|---|
| Base | `08768165db55351e42364dadf69657d7a2db4a4c`（B0 v1.1） |
| Implementation | `90402929c710a046e23dd3a3c3dd108b641bc981`（B3 final，父 `6b1e6b6`） |
| B1 | `812092c`；B2 final `7c6545d`；B3 phase1/2：`cc0eb12`/`b38b702`/`d01c803`/`4bab1d2`/`6b1e6b6`/`9040292` |
| Docs | 本 B4 docs commit（B1/B2 的 IPC/Contract 已随 B1/B2 入库；本 commit 更新 report/review/matrix/scripts） |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（B4 所有容器运行前后复核一致；canonical 包含空 `/probe`,`/project`,`/output` mount-target 目录，已证明不含其他空探针目录） |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| stage-b3 | `74ff4bedc934e22433492fdf05f228ad1b402cdc673448875cfb03aca9789101`（B4 实测） |
| runtime/sdk | DSH `0.2.2-rc.2`；SDK wheel `0.2.2rc2` |
| node/python | Node `v22.23.2`；Python `3.11.15` |
| identity 证据 | `artifacts/g3b-trusted-bridge/env/b4-identity.json`；`logs/b4-identity.log` |
| B4-01 保护文件 | `gates.py` `3ed08634…`；`dsh_adapter.py` `88891149…`；`run_live.sh` `a8a2753f…`；`git diff 0876816..9040292` 为空 |

B3 早期 evidence identity 曾记录 deps `9a03676c…`（源头为宿主 Python `__pycache__` 漂移）。B4 未沿用该旧值：所有 B4 命令使用 `PYTHONDONTWRITEBYTECODE=1 ... python3 -B`，最终实测 canonical `e07729d7…`；历史记录未覆盖，仅在此报告差异。

## 2. Security Trust Boundary / 可信组件所有权

- trusted Launcher：创建固定无 Key/禁网容器、`/work/g3b/admission.json`、capability 边界；候选侧只获得固定 UDS。
- B1 Adapter：只连固定 `/work/g3b/bridge.sock`；不 spawn、不读 Broker DB/Key、不能指定任意路径。
- B2 Controller：唯一 Reserve/Claim/Attempt 发起者；Fake 由 trusted Controller 启动；Fake receipt/counter 是独立证据。
- Broker：真实 SQLite；预算权威；v1 既有 ops 不变。
- **B0-02 BLOCKED**：候选/Controller/Broker/Fake 同容器同 uid（65534）；本任务无法提供不同 OS 主体或实际权限拒绝证明。`env/b4-isolation-probes.txt` 明确记录未执行 candidate 攻击、无 OS 边界正证据；恢复条件为 G3-D。`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE` 禁止。
- 非主张：本地 at-most-one-send 不等于远端 exactly-once；Fake usage 不是真实 token/账单；LiveGate/run_live 未解锁。

## 3. Architecture Diff（G3-A 复用 / G3-B 新增）

- G3-A 复用：真实 DSH `LlmAdapter`/Cordis stream、runtime SIGTERM/AbortSignal、Skill 插件；B1/B2 的 ABI 路径在 G3-B 重新验证。
- B1（`812092c`）：`src/autoteacher_m0/bridge/{protocol,ipc_server}.py`、`spikes/g3b-trusted-bridge/{src/index.ts,scripts/build.*,test/adapter-signal.test.mjs}`；冻结 Envelope、固定 UDS、严格解析、ack/finish/error/cancel、资源上限。
- B2：`src/autoteacher_m0/bridge/{admission,attempts,broker_client,controller,fake_backend}.py`、B2-owned `fake/fake_provider.py`；admission 启动一次消费、durable journal、bound reserve/claim、receipt digest、保守 reconcile/settle/fail。
- B3：`spikes/g3b-trusted-bridge/run/{worker,suite,reconcile,raw_negatives,concurrency,capture_tools,common}.py`、`scripts/run-suite.sh`；guard precheck additive；真实 DSH 场景、负例、crash、并发、session resume。
- B4：`scripts/g3b/build_packet.py` + `run_regression.sh`；本报告/Review Request/matrix；不改产品代码。
- 未改：`src/autoteacher_m0/security/gates.py`、`runtime/dsh_adapter.py`、`scripts/run_live.sh`、DSH 核心、G3-A packet。

### 3.1 受控偏差（相对冻结设计，均有测试/理由）

1. **Protocol 字符串转义放宽**（B1/B3）：冻结设计曾要求字符串内 C0 控制字符一律拒绝；实际允许 JSON 字符串中的 `\t/\n/\r`（仍拒绝 NUL/其他 C0/DEL），因为 DSH system-reminder 含换行且 JSON 转义不会破坏一行帧。测试：`tests/integration/g3_bridge/test_protocol.py::test_escaped_newlines_in_messages_are_allowed`；真实 DSH B1-01/B3-01 重跑通过。未放宽 UTF-8/NaN/重复 key/未知字段/大小限制。
2. **Controller tools/approve/reconcile 补充**：为真实 DSH tool 回合增加 tool schema hash 绑定、`tool_once/tool_final` 场景和 reconcile 路径；不改变 bound claim/attempt 顺序。测试：B2 host + B3-01/B3-03/B3-07/B3-08。
3. **Admission `tool` 场景**：`ALLOWED_SCENARIOS` 增加 `tool_once/tool_final/tool`，仅用于按 `tool_schemas` 精确绑定的测试场景；admission 仍是 Launcher 固定文件，候选不能自授权；B3-01/B3-03 验证。
4. **Fake 内部帧**：Fake→Controller 使用独立一行 JSON `{kind:chunk|usage|finish}`，由 Controller 转 B1 Envelope；未把 Fake 内部格式暴露给候选，也未改变 B1 Envelope/错误码；B2 host + B1-01/B3-01 验证。
5. **Guard precheck additive**（O-4 批准）：`plugins/runtime-budget-guard/src/index.ts` 增加 `reserveMode:"reserve"|"precheck"`；默认 `reserve` 保持原生字节/行为，`precheck` 只做 policy/trace，不 reserve/settle；Guard 原生+precheck **19/19**；真实 DSH + Bridge 组合 B3-03 PASS，且只有一个 Controller-owned broker child。
6. **B3-02 resume 修复**（`9040292`）：BrokerClient 原 `b2-<op>-<seq>` 进程内 id 在 resume 新进程复用持久 broker journal，触发 `IDEMPOTENCY_CONFLICT` 并被 B1 映射成 `UNKNOWN_FIELD`；修复为 `b2-<op>-<instance16>-<seq>`。未改 broker 幂等/冲突检查、未改 B1 协议/错误码；B3-02 重跑：第二进程 `okok/completed`、新 call_id `call-0224a35b…`/reservation/claim/attempt SETTLED，旧 attempt 未重发，counter 1→2。
7. **B0-03 Egress 说明**（O-2）：`security/egress.py` 未修改；G3-B Fake 发送走 Controller→Fake 直接通道，不经过 legacy egress 默认 `opencode-go` 路由；runtime bridge patch 禁用真实 `llm-deepseek`/paid 路径。B0-03 的同一 tuple 由 DSH 运行时 marker、admission、Broker 三者核对；不声称 Egress 层被实际使用。

## 4. Frozen IPC Protocol & State Machine

- 权威：`docs/M0_G3B_IPC_PROTOCOL.md`（sha256 `a3434d67…`）、`SECURITY_AND_ACCOUNTING_CONTRACT`（`74839ce7…`）、`DESIGN_FREEZE` v1.1（`708772af…`）。
- 传输：AF_UNIX 固定 `/work/g3b/bridge.sock`；Envelope `at-m0/g3b-bridge/v1`；request 无 attemptOrdinal；sessionId 1..512；ack `{accepted:true}` 先于任何拒绝；所有拒绝用 `error`；framing/JSON/未知字段/seq 失败不回 ack 且关闭。
- 状态：attempt journal WAL/FULL；`RESERVED→CLAIMED→ATTEMPT_STARTED→RESPONSE_OBSERVED→SETTLED/WORST_CASE_HELD/SETTLEMENT_UNCERTAIN`；commit-before-send；settle/fail 仅在持久 receipt 可映射时调用；无 receipt/发送未知 → PENDING + UNCERTAIN，绝不自动重发。
- 真实 UDS 负例（B1-02/B1-03/B0-04/B3-12）与真实 success（B1-01/B3-01）均在最终 impl 下复核。

## 5. Real DSH SDK → Broker → Fake → Ledger Positive Trace

| 场景 | 证据 | 结果 |
|---|---|---|
| B1-01 echo（B4 重跑 `b4-dsh-b1-01`，20:19:05–07Z） | `logs/b4-dsh-b1-01-20261116T201905Z.log`；`traces/b1-01-real-dsh-echo`；`ledger/b1-01.json` | okok/completed；counter=1；1 reservation/claim/attempt SETTLED；2 chunks |
| B3-01 tool 两轮（B4 重跑 `b4-dsh-b3-01`，20:19:12–14Z） | `logs/b4-dsh-b3-01-tool-20261116T201912Z.log`；`traces/b3-01-real-tool-two-turns`；`ledger/b3-01.json` | 2 个独立 stream/call_id/reservation/claim/attempt/receipt SETTLED；counter=2；tool-call+tool-result |
| B3-02 resume（B3 fixed 证据，20:12:36–39Z） | `traces/b3-02-resume-first`、`b3-02-resume-second-fixed`；`logs/b3-02-resume-second-fixed-20261116T201236Z.log` | 第二进程 okok/completed；旧 attempt 不重发；counter 1→2；broker id 实例 uuid 修复 |
| B3-03 Guard+Bridge 组合 | `traces/b3-03-guard-precheck-combination`；`ledger/b3-03.json` | guard precheck 2×，无 guard reserve/settle，无第二 broker child；Controller 2 组 Reserve/Claim/Attempt |

## 6. Guard / Tool / Session Combined Trace

- Guard native + precheck（B4）：`logs/b4-guard-native-20261116T201930Z.log`，**19 tests / 19 pass / 0 fail**（15 native + 4 precheck）；B3-03 真实 DSH 组合 PASS。
- Skill：0.2.1-rc.2 声明 harness **8/8 pass**（`logs/b4-skill-021-*.log`，G3-A stage + plugin node_modules）；0.2.2-rc.2 `ToolRuntime` 的 `mode:'native'` 配置与测试 harness 不兼容，**BLOCKED（harness 版本限制，不是插件 artifact 失败）**；0.2.2 下插件产物由真实 Bridge tool case 执行（B3-01）。
- Session resume：B3-02 fixed；Tool 第二轮无二次 request/header 但 Controller 独立预算/Claim（B3-09/B3-01）。
- **不得**把 native Guard 19/19 或 0.2.1 Skill 当 Guard+Bridge/0.2.2 组合通过。

## 7. Negative / Crash / Concurrency Matrix（逐 ID）

完整 33 行字段见 `docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`。状态摘要：

| 组 | PASS | PARTIAL | UNVERIFIED | BLOCKED |
|---|---|---|---|---|
| B0 | B0-01/03/04 | — | — | B0-02 |
| B1 | B1-01/02/03 | B1-04（cancel 未实现） | — | — |
| B2 | B2-01/02/03/04/06/07/08/09/10 | B2-05（replay 未跑） | — | — |
| B3 | B3-01..09、B3-12 | — | B3-10/B3-11 | — |
| B4 | B4-01/02/03 | — | — | — |
| **合计** | **28** | **2** | **2** | **1** |

关键负例：B1-02/B1-03 真实 UDS 解析失败无 ack；B0-04 admission/env 自授权 Fake0；B2-03 ROUTE_MISMATCH；B2-04 host 层 admission/self-auth 拒绝 + 静态确认 Controller 无 legacy claimer 调用 + 真实无 admission；B2-07 无 durable attempt 不发送；B2-09 missing/partial/invalid usage 保守；B3-04 bad admission/guard invalid Fake0；B3-05 真实双 Controller 一胜一 `CLAIM_DENIED`；B3-06/07/08 crash 无重发/幂等/保守；B3-12 unapproved tool/file/image/store Fake0。B2-10 为 host 层 idempotent reconcile replay，冲突观测未单独注入（残余说明）；B1-04 cancel 模式未实现；B3-10/B3-11 未跑进程树/背压资源边界。

## 8. Actual Test Commands & Results（真实计数，不可预填）

| 测试 | argv/日志 | 结果 |
|---|---|---|
| host full（任务指定 python3，实际 3.12） | `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps python3 -B -m pytest tests -q`；`logs/b4-host-full-pytest.log` | **EXIT 2，collection 2 errors**：deps 的 `pydantic_core` 为 cp311，宿主 3.12 不兼容。记录为环境不匹配，不作通过证据。 |
| host full（CPython3.11.15，匹配 deps） | `PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest tests -q -p no:cacheprovider`；`logs/b4-host-full-pytest-py311.log` | **663 passed / 2 failed / 1 skipped / 82.13s**；两失败均为宿主环境：config 文件可写 mode、live 子进程硬编码 `/project` 路径不存在；未改宿主代码。 |
| canonical fixed OCI full | `/opt/python/bin/python3.11 -B -m pytest /project/tests -q`，rootfs/deps/stage 固定、`--network none`、uid 65534；`logs/b4-oci-full-pytest2.log` | **665 passed / 1 skipped / 0 failed / 61.10s**（`/project` 挂载 + deps 同时位于 `/project/artifacts/foundation/deps` 与 `/deps`，满足 crash child 相对 PYTHONPATH）。 |
| ruff | `artifacts/foundation/deps/bin/ruff check src tests`；`logs/b4-ruff.log` | **All checks passed! exit 0** |
| G2 定向 | `pytest tests/integration/budget_bridge tests/integration/g2_closure tests/unit/accounting tests/integration/sandbox/test_egress_boundary.py -q`；`logs/b4-g2-targeted.log` | **332 passed / 28.93s** |
| G3-B host | `pytest tests/integration/g3_bridge -q`；`logs/b4-host-g3bridge.log` | **31 passed / 7.61s** |
| LiveGate unit | `pytest tests/unit/security/test_gates.py -q`；`logs/b4-gates-unit.log` | **14 passed** |
| Guard native+precheck | rootfs Node `--test guard-pr1.test.mjs precheck.test.mjs`；`logs/b4-guard-native-20261116T201930Z.log` | **19/19 pass** |
| B1 adapter | rootfs Node `--test /src/test/adapter-signal.test.mjs`（`/probe`=built stage，G3-A runtime node_modules）；`logs/b4-adapter-node-*.log` | **6/6 pass** |
| Skill 0.2.1 harness | G3-A native stage + plugin 0.2.1 node_modules；`logs/b4-skill-021-*.log` | **8/8 pass** |
| Skill 0.2.2 harness | G3-A 0.2.2 stage + runtime node_modules；`logs/b4-skill-022-*.log` | **BLOCKED**：`invalid config: $.mode expected nullable but got native`（ToolRuntime 0.2.2 harness 限制，G3-A 已独立记录） |
| 真实 DSH B1-01 | `run/suite.py --mode dsh`；`logs/b4-dsh-b1-01-20261116T201905Z.log` | exit 0；okok/completed；counter=1 |
| 真实 DSH B3-01 | `run/worker.py --scenario tool`；`logs/b4-dsh-b3-01-tool-20261116T201912Z.log` | exit 0；2 组 SETTLED/counter=2 |
| 真实 DSH B3-02 | B3 fixed 证据；`logs/b3-02-resume-second-fixed-20261116T201236Z.log` | exit 0；resume okok/completed；旧 attempt 不重发 |

环境核验：B4 所有容器退出后 `podman ps -a` 空、无 broker/probe 进程；rootfs/deps 复算 canonical（`logs/b4-container-absence.log`）。

## 9. Cost / Usage / Observation Conservative Semantics

- 契约：`docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md` §5、设计冻结 §5.9。
- 已实现/验证：完整可信 synthetic usage → settle；partial/no/invalid usage 时不填 0、不重试；B2-09 证据显示 partial/no → WORST_CASE_HELD/FAILED，invalid → ATTEMPT_STARTED/PENDING；发送未知/无 receipt → SETTLEMENT_UNCERTAIN；reconcile 仅凭持久 receipt 幂等结算。
- `to_usage()` 仅交叉校验；Controller 原始 observation 字段映射到既有 settle/fail，无新 broker op（O-3）。
- Fake usage/费用是 synthetic；真实 Provider HTTP/usage/invoice/billing 仍 UNVERIFIED，不作为账单/额度证明。

## 10. Source Diff & Compatibility / v1 Residual

- Packet `diff.patch` 必须与 `git diff --binary 0876816..9040292` 字节一致；source/tests 必须与 Git Blob 一致；由 `scripts/g3b/build_packet.py` 生成并自检。
- 产品范围：`src/autoteacher_m0/bridge/*`、`spikes/g3b-trusted-bridge/*`、`tests/integration/g3_bridge/*`、`plugins/runtime-budget-guard/*`（O-4 additive precheck）；未改 DSH 核心/LiveGate/gates/adapter/run_live。
- Broker v1：既有 snapshot/reserve/claim/settle/fail 不变；新增独立 `g3b_attempts`/`g3b_admissions`；禁旧 unbound `claim_dispatch()` 生产路径。
- B3-02 只改 BrokerClient message id，不改 broker 幂等/冲突语义、不改 B1 协议/错误码；旧 SETTLED attempt 不重发。
- 残余：同 uid OS 边界 BLOCKED；旧 egress 默认 route 在 G3-B 未使用；真实 Provider/远端 exactly-once 未验证。

## 11. Blocked / Unverified & G3-C/G3-D/G4 Dependency

| 项 | 状态 |
|---|---|
| B0-02 candidate 攻击/不同 OS 主体 | **BLOCKED**；G3-D 恢复条件：不同 principal/namespace、实际权限拒绝 |
| B1-04 cancel 模式 | PARTIAL（eof/error/timeout 有证据；cancel 未实现） |
| B2-05 request-digest replay | PARTIAL（Unicode/长 run_id 通过；replay 未跑） |
| B2-10 冲突观察 | PASS（idempotent replay host 证据）；冲突注入未单独覆盖，Reviewer 可要求补测 |
| B3-10/B3-11 进程树/背压/资源边界 | UNVERIFIED |
| Skill 0.2.2 native harness | BLOCKED（harness config 不兼容，不是插件 artifact 失败） |
| 真实 Provider HTTP/usage/invoice、远端 exactly-once | UNVERIFIED，不属 G3-B |
| 动态 Live 专用行为 | B4-01 静态未改 + gates 单测；动态 Live 调用 UNVERIFIED |
| 生产 BoundBrokerClaimer/TrustedTransport 接线 | 不在 G3-B；G3-C/D 依赖 |
| 真 OS 安全边界 | G3-D；本报告禁止 TRUST_BOUNDARY PASS |

## 12. STOP + Requested Reviewer Verdict

- **STOP**：B4 完成；不进入 G3-C/G3-D/G4/G5/Live；不启动独立 Reviewer（由 Lead 指派）。
- 请求 Reviewer 按 `docs/M0_G3B_REVIEW_REQUEST.md` 独立复核，并给出**限定范围**结论：
  - `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`（若 P0 集成/账本/失败关闭满足；OS 边界仍 BLOCKED）
  - `BLOCKED`（关键证据不可复现）
  - `FAIL`（未授权发送/重复发送/错误记账等 P0）
- **禁止** `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`；任何最终裁定不能作为 Live/GO。

## 附：待 Reviewer/维护者关注

1. B3-10/B3-11、B1-04 cancel、B2-05 replay 的残余范围。
2. B2-10 冲突 observation 注入建议。
3. Skill 0.2.2 harness BLOCKED 的接受边界。
4. B0-03 Egress 不在 G3-B 路径的说明是否满足 O-2 范围。
5. 独立复算 Packet hashes/source blob，抽检 SQLite/receipt。
