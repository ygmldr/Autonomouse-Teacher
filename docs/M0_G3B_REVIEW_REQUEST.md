# M0 G3-B Review Request

> 状态：**B4 完成；请求 Lead 指派独立 Reviewer**。本文件不预设 Reviewer 结论，不是 Live/GO 授权。
> Base `0876816`；Implementation `90402929c710a046e23dd3a3c3dd108b641bc981`（父 `6b1e6b6`）；Docs 为 B4 docs commit（SHA 见 Lead 报告）。
> Packet：`artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/`（manifest 的 docs_sha 为本 docs commit）。
> 33 行证据：`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`。

## 0. Reviewer 身份与范围

- 实现者/Owner 与 Reviewer 必须分离；Reviewer 必须从冻结的 Base/Impl/Docs Git Blob + Packet 原始字节复核，不得只读本请求/报告叙述。
- 范围：G3-B no-key trusted bridge 集成；**不**包括真实 Provider HTTP/Key/Live、G3-C/D/G4/G5/G6。
- 最高可请求 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`；**禁止** `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`（B0-02 同 uid 已 `BLOCKED`）。
- 不得把 Fake synthetic usage 当真实账单；不得把本地 Claim 当远端 exactly-once；不得把 native Guard/Skill 0.2.1 结果替代组合/0.2.2 结论。

## 1. R0–R5 问题清单

### R0 — 身份复核

1. 独立执行 `git rev-parse`/`git cat-file`/`git diff --check`/`git diff --binary 0876816..9040292`，与 Packet `manifest.json`、`diff.patch`、`hashes.sha256` 是否逐字节一致？
2. Packet `source/`、`tests/` 是否与 Impl Git Blob 一一对应（路径/SHA-256/blob）？`protocols/` 是否与 docs commit 一致？
3. 真实 DSH 0.2.2-rc.2 二进制、Node/Python、rootfs `25491e45…`、deps `e07729d7…`、stage `74ff4bed…` 是否与 manifest 一致？是否被临时 Node 模块替换？
4. LiveGate/`security/gates.py`/`runtime/dsh_adapter.py`/`scripts/run_live.sh` 是否与批准冻结值一致、无解锁？B4 记录 `git diff 0876816..9040292` 为空，sha256 见报告 §1。

### R1 — 追踪所有可发送入口（反向）

1. 以 Fake Provider 实际 stdin/收据为起点反向追踪：每条到达路径是否必须经 Bound Claim + durable `ATTEMPT_STARTED`？
2. 旧 `claim_dispatch()`/`require_claim()`/`authorize()`/descriptor-only、G3-A 直 spawn Fake、默认 Real Provider、Compaction/Judge、Retry/Cache/Files 是否存在旁路？
3. Adapter 是否只连接固定 `/work/g3b/bridge.sock`，不 spawn、不读 DB/Key、不指定任意路径？
4. B3-02 修复只改 BrokerClient message id，是否仍保持原幂等/冲突检查与 B1 协议？旧 SETTLED attempt 是否不重发？

### R2 — 独立恶意探针（至少六类；不得复用 Owner 结论）

1. Tool 两次调用但仅一个 `request/header`：独立确认 2 个 call/reservation/claim/attempt/receipt，且第二请求带真实 tool result。
2. Claim 后篡改 Prepared（消息/tool/route/maxTokens）：0 未批准发送；已有 Attempt 不得二次发送。
3. 两个真实进程同一 `call_id` 竞争：最多一个 Fake 收据/Claim；第二个确定拒绝。
4. Crash after `ATTEMPT_STARTED`（Send 前）：新进程 reconcile 不自动重发；无 receipt → PENDING/`SETTLEMENT_UNCERTAIN`。
5. Guard 缺失/故障且无 Controller 授权：真实 DSH 仍有尝试证据，Fake 收据 0。
6. Missing/partial/invalid usage、非法 chunk、EOF/cancel：不出现零成本假结算/成功 finish；已发送未知必须保守。
7. 建议增补：Unicode/长 run_id、相同 call_id 不同 payload、重复 Observation/冲突、未批准 Tool Registry、伪造 admission、B3-10/B3-11 进程树/背压。

### R3 — OS 安全边界（独立执行，不以结构图投票）

- 候选进程尝试打开 Broker SQLite/Policy/Admission、篡改 Controller FD/可执行路径、发未经核验 Claim、开 direct socket；只有 OS 实际拒绝才可得 trust boundary 结论。
- 当前同容器同 uid：Reviewer 应确认 **B0-02 BLOCKED**，不得写成 `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`；可与 functional integration PASS 并存。
- `env/b4-isolation-probes.txt` 明确说明 B4 未执行不同 OS 主体/candidate 攻击；这是如实限制，不是失败隐藏。

### R4 — 数据/财务交叉核对

- SQLite 实际行：`call_id` 能否唯一映射 Reservation/Claim/Attempt/Receipt/Observation/费用？Tool 两轮是否独立？Pending 是否保守计入？已 Settlement replay 是否不新发请求？
- Fake receipt 原始字节 `raw_sha256/raw_length` 是否等于 Controller approved payload digest/trusted sent digest（B2-06）？每个 hash 覆盖哪些字节（frame/prepared/payload）？
- 是否出现 Fake 已收到而控制面报告 `NOT_DISPATCHED`（P0 FAIL）？Crash 是否诚实标 Unknown/Pending？

### R5 — 复跑与裁定

1. 在独立冻结 stage 运行重点真实 DSH SDK case、G2 核心、Python 全量、Node Guard/Skill/Bridge、至少一组真实 Crash/并发。
2. 使用 Packet `logs/commands.jsonl` 的完整 argv/UTC/exit；记录自己的 argv 与容器 absence；不得用 host Node 替代 fixed OCI。
3. 给出限定范围 verdict（见 §4）；分 P0/P1/P2；不使用含糊“全面 PASS”。
4. 特别复核：B1-04 cancel（PARTIAL）、B2-05 replay（PARTIAL）、B2-10 冲突观测残余、B3-10/B3-11（UNVERIFIED）、Skill 0.2.2 harness（BLOCKED）。

## 2. 最小重跑命令（B4 已执行；Reviewer 必须独立重跑）

```bash
cd "/root/Autonomous Teacher"

# R0 identity (host, read-only)
git rev-parse 9040292
git diff --check 0876816 9040292
git diff --binary 0876816 9040292 | sha256sum
# compare to packet manifest.diff_sha256 / diff.patch

# Host Python (never write bytecode; CPython3.11 matches deps)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest tests/integration/g3_bridge -q
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest tests -q -p no:cacheprovider
./artifacts/foundation/deps/bin/ruff check src tests

# Canonical fixed OCI full suite (B4 used this final authoritative run):
# stage = git archive 9040292; mount /project, deps at /deps and /project/artifacts/foundation/deps;
# --network none --read-only --user 65534 --cap-drop ALL --security-opt no-new-privileges;
# run: /opt/python/bin/python3.11 -B -m pytest /project/tests -q
# B4 result: 665 passed, 1 skipped, 0 failed (logs/b4-oci-full-pytest2.log)

# Guard native + precheck (fixed rootfs):
# /usr/bin/node --test guard-pr1.test.mjs precheck.test.mjs
# B4 result: 19/19 pass (logs/b4-guard-native-20261116T201930Z.log)

# B1 adapter:
# /usr/bin/node --test /src/test/adapter-signal.test.mjs
# /probe = built stage/runtime/bridge; mount G3-A runtime node_modules at /probe/node_modules and /src/node_modules
# B4 result: 6/6 pass.

# Real DSH suite: B4 reran B1-01 echo and B3-01 tool with capture_tools + stage-b3;
# see logs/b4-dsh-b1-01-*.log, logs/b4-dsh-b3-01-tool-*.log; B3-02 fixed evidence is logs/b3-02-resume-second-fixed-*.log.
```

- Reviewer 必须用自己记录的真实命令/UTC/exit 生成新的 `reviewer-*` 证据；不得只阅读 Owner 日志。
- 任何 host Python 命令必须加 `PYTHONDONTWRITEBYTECODE=1 ... -B`；host 不运行项目 Node/TS；Node/DSH 在固定 rootfs 容器内。
- B4 宿主 `python3` 为 3.12、deps `pydantic_core` 为 cp311，因此任务字符串中的 `python3` 全量会 collection error；B4 已如实用 CPython3.11 跑并在固定 OCI 运行 canonical full suite。Reviewer 应使用匹配版本并记录。
- 复跑后检查容器/进程 absence（`podman ps -a`、残留 broker/probe 进程）并记录；rootfs/deps 复算 canonical。

## 3. 证据索引

| 证据 | 路径 |
|---|---|
| Packet manifest / hashes / integrity | `artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/{manifest.json,hashes.sha256,packet-integrity-report.txt}` |
| Base→Impl diff | 同上 `diff.patch` |
| 协议/契约 | `docs/M0_G3B_IPC_PROTOCOL.md`、`docs/M0_G3B_SECURITY_AND_ACCOUNTING_CONTRACT.md` |
| Design freeze/Baseline | `docs/M0_G3B_DESIGN_FREEZE.md` v1.1、`docs/M0_G3B_BASELINE.md` |
| 33 行矩阵 | `docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv` |
| B3 traces/ledger/logs | `artifacts/g3b-trusted-bridge/{traces,ledger,logs}/`（packet 快照） |
| B4 identity | `artifacts/g3b-trusted-bridge/env/b4-identity.json` |
| B4 regression logs | `artifacts/g3b-trusted-bridge/logs/b4-*.log` |
| Owner 报告 | `docs/M0_G3B_IMPLEMENTATION_REPORT.md`（原始证据优先，不得替代） |

## 4. 范围裁定请求（不预设结论）

请 Reviewer 在独立复验后给出**限定范围**结论：

- `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`：R0–R4 的 P0 集成/账本/失败关闭项在真实 DSH + 真实 SQLite + 进程/持久证据下满足；B0-02/OS Boundary 仍 BLOCKED、真实 provider/usage/invoice 未验证。
- `BLOCKED`：固定环境/证据不可复现或关键 P0 无法验证（写清障碍、恢复条件、不可替代项）。
- `FAIL`：出现 P0 未授权发送、重复发送、漏记/低估、Guard 缺失仍发送、错误 success、Packet 身份漂移等；局部 pass 不能签总体 PASS。
- **禁止**：`PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`（同 uid 不可证明 OS 边界）。

## 5. Reviewer 不得做的事

- 不得把 Owner 的 `SELF_CHECK_PASS`/报告文字当作最终结论；必须独立执行 R0/R4/R5。
- 不得修改历史证据/Packet；发现缺陷发 Lead + Owner，不代改。
- 不得读取真实 Key/配置、不得访问真实供应商 HTTP；所有执行保持固定 no-key 隔离。
- 不得把 B4 的宿主环境失败隐藏为通过；必须同时报告 host 与固定 OCI 结果。
- 不得把 B1-04/B2-05 PARTIAL、B3-10/B3-11 UNVERIFIED、Skill 0.2.2 harness BLOCKED 写成 PASS。

## 6. 需要维护者/Lead 决定的事项

1. 是否接受 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE` 与 OS `BLOCKED` 并存的措辞。
2. B2-10 是否需补冲突 observation 注入；B3-10/B3-11 是否必须在本轮补齐。
3. Skill 0.2.2 native harness BLOCKED 的接受边界（0.2.1 8/8；0.2.2 插件产物由真实 bridge tool case 执行）。
4. B0-03 的 Egress 层说明（O-2 下不经过 egress）是否满足原矩阵语义。
5. Packet final verify 后由维护者决定是否送 Reviewer；不自动进入 G3-C/D/G4/Live。
