# M0 G0 — Current Baseline（仓库身份与 G2-L1.1 输入核实）

> Gate：**G0（只读身份核实，不做实现、不跑项目代码/测试）**
> Owner：broker-docs（文档/冻结；与 G2-L1.1 实现者身份分离）
> 日期：2026-11-16 UTC
> 依据：`docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md` §4（本文即 §4.2 输出）与 §0–§5、§14、§16
> 性质：基线记录，不是测试 PASS、不是 G2-L1.1 完成、不是 G3/G4/Live 授权。

## 1. 结论摘要

- **G0 状态：PASS（仅限身份/基线核实范围）**。当前 HEAD 可复原；G2-L1 实现提交 `2786e25` 是 HEAD 的祖先；`src/tests/config/scripts/plugins` 相对 `2786e25` **零差异**；无未解释源码漂移。
- 当前 worktree 唯一变化是未跟踪的 Playbook 本文件；本 G0 commit 会把 Playbook 与本文一起作为 docs-only 提交。
- Playbook §5 的 **T1–T5 五个已知问题在 HEAD 全部仍存在（静态核实 OPEN）**；T6 的新 bound-claim 路径已由 G2-L1-FIX 提供，但旧 v1 unbound claim/兼容残余仍存在，不能写成“全部绑定已强制”。
- G0 未运行 pytest/Node/项目代码，未读取 `/root/.config/autoteacher`，未接触真实 Key/网络；可核指纹与缺失项见 §5。

## 2. 身份与工作树（现场值）

| 字段 | 实测值 |
|---|---|
| 观察时间 | 2026-11-16（UTC，本 G0 执行时） |
| observed HEAD | `6ec8194a190bbdce7e14ffaa2f1dd944d8208bc0`（`docs: annotate G2-L1 review archive and absence evidence`） |
| HEAD parent | `c52b173b78bb523ae8483adfc872af1de33d29e8` |
| HEAD tree | `54b76c4715319aeadb41b84396593ec5e73d8d64` |
| `src` subtree | `8b92ac5143a0c963f46b77a56bf487c5da0edf01` |
| working tree | 仅 `?? docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md`；`git diff --stat` 空；`git diff --check` exit 0 |
| last G2-L1 implementation commit | `2786e25a9e5bd590255026d76fc362abb16d0e7b`（`fix: close G2-L1 egress claim bypass and bind approved request route/model (no-key)`） |
| ancestor 检查 | `git merge-base --is-ancestor 2786e25 HEAD` → exit 0（**是祖先**） |
| 相对 2786e25 的源码差异 | `git diff 2786e25..HEAD -- src tests config scripts plugins` → 空（零路径差异） |
| HEAD 后 docs 提交 | `19f5270`（G2-L1 findings/contract/fix report）、`c52b173`（review 归档）、`6ec8194`（review archive/absence 注记）；均只动 docs |
| tracked 文件 | 196（`src` 41、`tests` 33、`plugins` 34） |

`git log -n 12 --oneline` 关键链：

```text
6ec8194 docs: annotate G2-L1 review archive and absence evidence
c52b173 docs: archive G2-L1 independent review (PASS, non-blocking findings)
19f5270 docs: archive G2-L1 findings, request binding contract, and fix report
2786e25 fix: close G2-L1 egress claim bypass and bind approved request route/model (no-key)
688ed01 docs: add G2-L1-FIX and G3 handoff task book v0.7 (Part A approved)
23f9ed6 docs: add G0-G2 closeout errata (F-FINAL-1..3)
f78ed63 docs: archive G2 audit and G0-G2 closeout
32bea5b feat: G2 egress claim gate and closed-loop integration (no-key)
ada8e28 feat: G2 broker canonical call identity and persistent dispatch claim (no-key)
70cb574 docs: archive G1 audit, errata, and closure
4d71530 fix: G1 close AUTH-08 budget policy gap (B-G1-1)
00df577 fix: G1 observation usage provenance and conservative bounds (no-key)
```

## 3. 相关路径与内容身份（HEAD）

所有 `blob` 为 Git blob SHA-1，`sha256` 为当前工作树文件内容 SHA-256（与 HEAD 一致；除 Playbook 未跟踪）。

| 路径 | Git blob | SHA-256 |
|---|---|---|
| `src/autoteacher_m0/security/egress.py` | `a9f991d6476c8c79ac6c6ad39a4f5d103f5f136b` | `c8c6f942b2b5d53a7365e3580751ab21de207470310d05b141c39c4507aff091` |
| `src/autoteacher_m0/accounting/call_identity.py` | `24789042ea13d5875ce4b2e7eb6a57cccc2b1d65` | `4d92badf789f77b78e5cbbded7d7e6ea4d6587c01064beebe8082701b89cdd29` |
| `src/autoteacher_m0/accounting/ledger.py` | `7c811df6808168f13ccf7e7a1a7ea1f6536dffd6` | `771b75c55bf2003408f54dd0f95d2c8bd47002f998abd74fd8933e619b2c4fd7` |
| `src/autoteacher_m0/accounting/broker.py` | `279497cd1b5b1125e93401a90600ba8b899ce66c` | `5439fb49a7b8a1f4114bc895e2c04d03c9c8a45db54fa7a820d6530363df768a` |
| `src/autoteacher_m0/accounting/observation.py` | `1e7056939ddf9de227fe8fdfb5d19b63d3da3a2a` | `90a355618d1e85f03b0dd7bc7ff23c84cc66dd93995157c824eee6cc400b7187` |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `86ae5d6e6f8bf50f68972e28744530af4f109dcf` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` |
| `src/autoteacher_m0/security/gates.py` | `edf7f45fdbd058f89177a8e8f8d918274516b9d4` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` |
| `scripts/run_live.sh` | `dd0814e165eea620164e7c6b372abbdc014e972a` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` |
| `docs/M0_REQUEST_BINDING_CONTRACT.md` | `a030a072b5e7df2e2a9c1438cbf5534fed739389` | `785b851ce4eda846f9fbf41964f647aa61a1873a1ec6916a48e37c6c5c4b2951` |
| `docs/ADR-002-unified-call-identity.md` | `b4e5501ecbf8e215bf7cf3b2207abd87d37b17b2` | `22d277d109db4422927e5c84909b021b769d5bb78d7e9a1d615d1a8bf4440654` |
| `tests/integration/g2_closure/test_g2l1_fix.py` | `face4fbbd119bf14af759346b9c490c565a57710` | `6d77bf16522348d9242ab7d203d470c6fbd18ae50d76e18078578ba2850022b5` |
| `tests/integration/g2_closure/test_g2l1_red.py` | `e9b1ef45f7c7aaf244f3caa6769a432d73c32afa` | `cce02418280529e9a6ee3f7682419142a24991195d384b3e3a593f87fbd8f343` |
| `tests/integration/g2_closure/test_g2_closure.py` | `cfc32cf466aa7b57b2f173fcd7c012aa63a69b46` | `285ff6f88338b276fce903b2ca25cdf95b169c8275873c6a7bf620bb4b5909af` |
| `tests/integration/sandbox/test_egress_boundary.py` | `695e3ba5edb177cb0ab6f17c0cbbd15eb7d0813c` | `f5afb1e6e9496feee0fac60813bab66330b4074a3c39a816915c12d0e842d051` |

Playbook（本 G0 同时入库）：`docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md`，当前未跟踪内容 sha256 `41c909662b5066dff41b685e1491ddf51378a6dd0a3b9d2633d3012c41c1389a`，808 行；本 commit 后其 blob 由 Git 记录。

## 4. T1–T6 逐项现场核对（静态；未运行项目代码）

### T1 — Provider 进入后异常仍归因 `NOT_DISPATCHED`：**OPEN（P1，确认）**

- `TrustedEgressTransport.dispatch()`：`selected(request)` 的 `except BaseException` 直接走 `_denied(...)`（`src/autoteacher_m0/security/egress.py:670-675`）；`_denied()` 固定返回 `state = AttemptState.NOT_DISPATCHED`（同文件 `:655-660`）。
- `provider_calls` 只在返回 `Mapping` 之后 `+= 1`（`:674-676`）；provider 已进入但抛异常时计数为 0。
- 独立 Reviewer 的机制 probe（F-2，`docs/REVIEW_G2L1.md` §6）记录 provider 实际调用 1 次后抛 `RuntimeError`，返回 `dispatched=False, state=NOT_DISPATCHED, provider_calls=0`；本次静态行号与 HEAD 一致。
- 结论：T1 仍在 HEAD；G2-L1.1 **必须补** attempt-start/BILLABLE_UNKNOWN/保守预算语义。

### T2 — `call_id` 跨模块 Unicode canonicalization 不一致：**OPEN（P1，确认）**

- Accounting 侧：`CallIdentity.call_id` 用 `json.dumps(...)` **未传 `ensure_ascii`**（默认 `True`），`src/autoteacher_m0/accounting/call_identity.py:78-81`。
- Egress 侧：`canonical_json()` 显式 `ensure_ascii=False`（`src/autoteacher_m0/security/egress.py:172-174`）；`prepared_call_id()` 正是用该函数计算（`:193-198`）。
- 对同一非 ASCII `run_id`，两侧可能产生不同 `call-<48hex>`；`grep` 未发现其他统一入口。结论：T2 仍 OPEN；须以 `call_identity.py` 为唯一实现并显式 `ensure_ascii=False`，跨进程/跨模块测试。

### T3 — `PreparedProviderRequest.schema_version` 未强制：**OPEN（P1，确认）**

- 仅有常量 `PREPARED_SCHEMA_VERSION = "m0.prepared.v1"`（`egress.py:115`）、dataclass 默认值（`:126`）和 digest 字段列表（`:177-182`）。
- 全仓检索 `schema_version`（排除 pycache）只有上述三处定义/使用 + 测试 fixture；`claim_dispatch_for_request()`（`:486-545`）未做 `prepared.schema_version == PREPARED_SCHEMA_VERSION` 校验。
- Reviewer F-1 的 probe 已显示 `m0.prepared.v0` 仍可获 `allowed=True`；静态代码与之一致。结论：T3 仍 OPEN。

### T4 — Broker 无效 completion 的 journal 增长：**OPEN（P2，静态确认；需 G2-L1.1 RED）**

- `_complete()` 对未知 reservation 只返回 `UNKNOWN_RESERVATION`（`src/autoteacher_m0/accounting/broker.py:253-259`；未知 usage 在 `:267-273` 也返回 envelope）。
- `handle()` 对 `settle/fail` 仅在“已存在 message id”且 reservation 非 PENDING 时短路为 `ALREADY_SETTLED`（`:310-325`）；其他情况一律落到 `journal_once` 写入新 journal 行（`:326-328`）。
- Journal 容量只在 **reserve** 时检查 `count + pending + 2 <= max_messages`（`:204-228`）；completion/journal insert 本身没有上限（`ledger.journal_once` `:307-325`）。唯一 unknown/invalid completion 可不断增 journal 行，直到外部磁盘/进程停止，而不是由 `max_messages` 硬性阻止。
- 结论：T4 仍 OPEN；需先写 fail-first（大量唯一 unknown-reservation/invalid-usage completions）再定最小修法；G0 不执行测试。

### T5 — `evaluate_descriptor()` 仍消耗 attempt 配额：**OPEN（P2，确认）**

- `_evaluate()` 用 `stream.attempts + 1 > policy.max_attempts` 判断上限（`egress.py:353-357`）。
- `evaluate_descriptor()` 调 `_record_policy()`（`:396-400`），后者在 `evaluation.allowed` 时 `stream.attempts += 1`（`:363-370`）。
- 即纯诊断多次通过会消耗之后正式发送的 Attempt 配额；`attempts_detail` 已逐条记录，但顶层 `attempts` 未分离 policy/claim/dispatch 语义。结论：T5 仍 OPEN。

### T6 — 兼容/源码级回归：**部分已有、残余 OPEN**

- G2-L1-FIX 已提供 `PreparedProviderRequest`/`BoundBrokerClaimer`/`claim_dispatch_for_request()`（`egress.py:486-545`）和旧 v1 兼容路径；BIND-01 由 ledger `expected_route_id/expected_model` 提供权威 `ROUTE_MISMATCH`（`broker.py` claim 接 `:297-309`）。
- 旧 `claim_dispatch()` 仍是无 expected 字段的 legacy 路径（`egress.py:471-478`；`_claim_with` 在 `:432-451` 也允许无绑定 claimer）；Reviewer 残余 #1/F-9 明确该旧路径可产生可消费 permission，且生产 `BoundBrokerClaimer`/`TrustedEgressTransport` 尚未接线。此残余 **OPEN**，属 G3 迁移项，不能写“所有 claim 均绑定”。
- `gates.py`/`dsh_adapter.py`/`scripts/run_live.sh` 与 `2786e25` 字节相同（本文件 §3 blobs）；LiveGate/E1–E5 仍硬阻断，本次未运行/未解锁。

## 5. Toolchain / Container / 环境指纹

| 项 | 实测/来源 | 状态 |
|---|---|---|
| Host Python | `Python 3.12.3`（`python3 --version`） | 实测 |
| Host Node / npm | `v22.23.2` / `10.9.8`（`node --version` / `npm --version`） | 实测；G0 未运行 Node 项目代码 |
| OCI image ref | `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b` | `podman image inspect` 成功；image ID `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715` |
| OCI rootfs | normalized tar sha256 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（`artifacts/security/rootfs`） | 本次重算一致 |
| Python deps | normalized tar sha256 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（`artifacts/foundation/deps`） | 本次重算一致 |
| OCI 运行时 Python | CPython 3.11.15（`artifacts/security/verification-summary.md` 记录 `Local uv CPython3.11.15`、`Final 45 passed`；rootfs 为 `/opt/python/bin/python3.11`） | 历史证据 + 路径核实；**G0 未执行容器** |
| DSH / Cordis plugin lock | `plugins/offline-fixture/package.json`：engines `dsh 0.2.2-rc.2`、node `>=22`；peerDependencies `@deepseek-ai/cordis 4.1.0`、`@deepseek-ai/dsh-llm/dsh-tools 0.2.2-rc.2`；lockfile 同版本 | 仓库文本核实；实际 DSH Runtime/SDK 安装版本未执行 → **UNVERIFIED** |
| 隔离网络/权限 | 历史冻结证据为 `--network none`、read-only、uid 65534、cap drop ALL、no-new-privileges；G0 只读审查未启动容器 | 继承证据，本 G0 未重证 |
| 真实 Key/模型/HTTP | G0 未接触；未读 `/root/.config/autoteacher`；无 socket/真实调用 | 约束遵守 |

## 6. 约束与 G0 验收

- **只读**：G0 未修改源码/测试、未运行 pytest/Node/项目代码、未 stage 其他文件。
- **无 Key/无网络**：未读取/导入/打印任何真实 Key/Token；未发起真实 Provider/HTTP/socket 调用；未读用户 Home 凭据目录。
- **可复原性**：HEAD/parent/tree、关键路径 blob/SHA-256、祖先关系与源码零差异均已记录；T1–T5 的真实文件与行号现场定位；T6 残余明确。
- **G0 结论**：`PASS_FOR_G0_SCOPE`（身份/基线可复原、无未解释源码漂移、问题清单可复核）。不代表 G2-L1.1 已修复或任何测试 PASS。
- 后续：由 Lead 另派 G2-L1.1 实现者按 §5 T1–T6 写 RED/GREEN；本 G0 文档只提供输入，不实现、不替写实现结论。
