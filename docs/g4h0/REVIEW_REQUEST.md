# G4-H0 — 独立 Review Request（Review Packet v1，无 Key）

- **文档 ID**：`G4H0-REVIEW-REQUEST-v1`
- **提出者**：`a-impl-core`（A 线实施者；非 Lead、非 Reviewer）— 本文件不构成自证或批准
- **请求 Reviewer**：未参与本轮实现的独立 Agent（独立 worktree/分支，自行复现）
- **生成时间（UTC）**：`2026-11-19T18:16Z` → `2026-11-19T18:2xZ`
- **范围**：仅限**本机、无 Key、无真实 Provider/HTTP/付费调用**的 G4-H0 工程准入准备。**不是** E5-PreLive Full、不是 G4-H1/H2/G5/G6/Live 授权。

---

## 0. 冻结身份（Reviewer 必须独立核对）

| 对象 | SHA / 值 | 说明 |
|---|---|---|
| `base_sha` | `3e7afee077845a071cd364e93ab209cac20b2d5f` | G4-H0 起点（G4-F 归档提交） |
| **`impl_sha`（冻结）** | `813e6a680399ba245bd0e76296e1212118a83460` | A0–A3 波次 octopus merge；2026-11-19T18:14:07Z |
| `impl` tree | `1772cb54eb57ebfbdc320959876e0f9ddfbf04e8` | `git rev-parse 813e6a6^{tree}` |
| diff 规模 | **43 files changed, +7703 / -35** | `git diff --shortstat 3e7afee..813e6a6` |
| `src` 变更面 | 仅 `src/autoteacher_m0/security/authorization.py`（+126/-27）与 `src/autoteacher_m0/bridge/controller.py`（+81/-5） | 见 §2 |
| 受保护文件 | `gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py` 相对 `3e7afee` **零 diff** | 已 `git diff --name-only` 核对 |
| 冻结 docs/Packet | 非 `docs/g4h0/` 的既有 docs 相对 `3e7afee` **零 diff**；G4-F v1 Packet 未被改写（见 §3.6） | 已核对 |
| 集成 worktree | `/root/Autonomous Teacher/worktrees/m0-g4h0`（`work/m0-g4h0`，HEAD `813e6a6`）— **只读参考** | 本申请不要求写入 |
| 证据包 | `artifacts/g4h0/packet-v2`（gitignored；175 files / 0 symlink / 173 hashes OK） | 身份限制见 §8-1 |

### 0.1 关键 docs / 证据 SHA-256（集成 worktree 实测）

| 文件 | sha256 |
|---|---|
| `docs/g4h0/BASELINE.md` | `8580f5623c44b6b0c49ad83cb65c7e8fafef0789f743ab388afdc7310365cfa1` |
| `docs/g4h0/RISK_DISPOSITION.md` | `edd950a55764e50754af649658dbcf43b9fc2149f5c11e119f0917a63223774f` |
| `docs/g4h0/P2_FIX_REPORT.md` | `70e15167116fe65c2b56c743f1219f7ca123993f202a6a9e43a3673aa7e7e150` |
| `docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md` | `68ad6322dba8a5df56fb8b1848800f47aad2d5ead77ae85c355bef7984f4d649` |
| `docs/g4h0/PROVIDER_CONTRACT_DRAFT.md` | `ed720978235612dcb0515fbd15d19a22301fa4ca6fc35c0a18e3c8b5a6166f2b` |
| `docs/g4h0/PRICE_AND_USAGE_VERIFICATION.md` | `40a7b7dda452e9fda6dfb60b91be43e1d32c4c9894dbd8b6c08b32edb9564fec` |
| `docs/g4h0/BILLABLE_PATH_INVENTORY.md` | `67677aaf06e45ce75e25554a48e02b36b362923e23f58a093930e8f73f4a7f34` |
| `docs/g4h0/A2_SOURCES.md` | `77a5ead5d11704d2e1870c3d8a9eda52778e3b097076994dc5207d657429f018` |
| `docs/g4h0/DEPLOYMENT_RUNBOOK.md` | `b780aa5423104815d885dc48dbc17f69adb1a9c000fac9571c31780705148092` |
| `docs/g4h0/TRUST_BOUNDARY_DIAGRAM.md` | `d0785d1e9d77fdc60c3a5f3494f5ff24b3af640dbf55bbc0e6d2ac336b3c648f` |
| `docs/g4h0/HUMAN_SIGNOFF_TEMPLATE.md` | `9673cb981e59d55e58ce46560a47e01f324f8121ec809b3740fc4b268b7fa6a7` |
| `docs/g4h0/E5_PRELIVE_FULL_CHECKLIST.md` | `90ec78ec2510bf8e878d0b6b8803fe3407960dbf65dede178a461dd27a5a235f` |
| `docs/g4h0/A3_REFS.md` | `f3b3541ba8413e515aa5ea886c595617e326c8b04dfc45fe4e994d9f689d03cd` |
| `docs/g4h0/evidence/a07_no_key_probes.json` | `ac8966feade3ed36de79037b99861e44971f638b5860243ff3523821bafb0a40` |
| `docs/g4h0/evidence/p2_03_a12_loop30_before.log` | `7f5651a9b93c4515a3d645db08008b9dd6635e6394bc72ef0cd36c4a49c9ec54` |
| `docs/g4h0/evidence/p2_03_a12_loop30_after.log` | `daf51fe70704bed58d697e83b5fa72a853254ca59796290d6823e621dd966143` |
| `docs/g4h0/evidence/p2_03_stress_after_fix_natural.json` | `d76e6176af0227f67465b372f4dc7f9258bee1a4b311aa8ad1a7d1fb2f3ad3ba` |
| `docs/g4h0/evidence/p2_03_stress_after_fix_widened.json` | `6367fcf1210b5ca6de25123241ba0e48eeb9f419a22342c64c01f02f527513f5` |
| `docs/g4h0/evidence/p2_04_ruff_test_scan_git_secrets.log` | `cfd8b304c8939cc4cee92e041da4593a1e4af88175fa47eda6d47926bac77b0d` |

> 本 Review Request 自身的 docs SHA 由 Lead 在合并时记录；Reviewer 应从**整合后的 frozen docs commit** 复核，不应信任本表复制的值。

---

## 1. 合并构成（四个分支）

| 分支 | 提交 | 提交者 | UTC | 内容 |
|---|---|---|---|---|
| `work/m0-g4h0-core` | `0a9ee67e7c8f4eecca6ef80c682e0544a2e2f847` | a-impl-core | 2026-11-19T17:55:21Z | A0 BASELINE + A1 RISK_DISPOSITION + 基线/P2-01 证据 |
| `work/m0-g4h0-research` | `011f12804dad535125d2829cebb948e93aafb24f` | a-impl-research | 2026-11-19T17:57:32Z | A2 Provider 契约/价格/计费路径 + A2_SOURCES |
| `work/m0-g4h0-docs` | `f4a154a9834fe24a8b7ac5b81e6ded182ac24bb3` | ygsldr | 2026-11-19T17:49:51Z | A3 Runbook/信任边界/签核模板/E5 清单/A3_REFS |
| `work/m0-g4h0-fix` | `33e2fd6c72978fa07a5e0755858c293fa412ead2` | A-Impl-Fix | 2026-11-19T18:12:53Z | `fix(g4h0)`: P2-03 原子发布 / P2-05 观测 / P2-06 reason 保留（src） |
| 同上 | `9ed7ede7a12a4145ca11b1b50ce81e2da1af05b7` | A-Impl-Fix | 2026-11-19T18:12:59Z | `test(g4h0)`: P2 回归 + P2-03 压测 + A-07 探针（tests/scripts） |
| 同上 | `ff9afd0b592a34e12f27860a3363c8a84b58b18a` | A-Impl-Fix | 2026-11-19T18:13:05Z | `docs(g4h0)`: P2_FIX_REPORT + A-07 证据 + evidence |
| **merge** | **`813e6a680399ba245bd0e76296e1212118a83460`** | ygsldr | 2026-11-19T18:14:07Z | octopus merge，父提交 = 上述四支 HEAD + base |

复核前提：`git merge-base 813e6a6 3e7afee` = `3e7afee`；merge 后工作树 clean、无未提交文件（Lead 已声明，Reviewer 独立复核）。

---

## 2. 变更面（Reviewer 应逐项验证）

| 类别 | 文件 | 变更 | 说明 |
|---|---|---|---|
| `src`（安全） | `src/autoteacher_m0/security/authorization.py` | +126/-27 | P2-03：use-record 同目录临时文件写全 + fsync + `os.link` 原子发布；loser 有界读重试（仅影响错误码分类，不授权）；`O_NOFOLLOW`/0600/目录约束不变 |
| `src`（bridge） | `src/autoteacher_m0/bridge/controller.py` | +81/-5 | P2-05：envelope-deadline **observation-only** dispatch-window 记录（不参与 allow/deny、不占 dispatch 序号）；P2-06：recovery 保留原 reason 并追加 `|RECOVERY_EVIDENCE:`（状态/held 语义不变） |
| tests | `tests/integration/g4_h0/{conftest.py,test_p2_03_concurrent_consume.py}` | +510 | P2-03 定向 14 项（TEST_ONLY 合成签名） |
| tests | `tests/integration/g4_f5/test_f5_pre_send_timeout_observation.py` | +123 | P2-05 2 项 |
| tests | `tests/integration/g4_f5/test_f5_recovery_reason.py` | +137 | P2-06 3 项 |
| tests | `tests/integration/g4_f5/g4f5_support.py` | +3/-2 | 可选 dispatch_journal 参数 |
| tests | `tests/security/test_scan_git_secrets.py` | -1 | P2-04 删除未使用变量（F841） |
| scripts | `scripts/g4h0/p2_03_stress.py` | +264 | 2 进程 ≥30 轮压测（非产品代码） |
| scripts | `scripts/g4h0/no_key_probes.py` | +468 | A-07 22 项本地负例（非产品代码） |
| docs | `docs/g4h0/**`（13 份文档 + evidence） | 新增 | 见 §0.1 与 EVIDENCE_INDEX.md |

**零 diff 复核点**：`src/autoteacher_m0/security/gates.py`、`scripts/run_live.sh`、`src/autoteacher_m0/runtime/dsh_adapter.py`、`src/autoteacher_m0/cli.py`、以及非 `docs/g4h0/` 的既有 `docs/**`、G4-F 冻结 Packet/矩阵/历史证据。

---

## 3. 已执行命令、Case ID、时间戳与原始日志（Owner 侧，待独立复核）

> 所有命令均在**本机、无 Key、无真实 Provider/HTTP** 条件下执行；Python 为 `/root/Autonomous Teacher/.venv/bin/python`（3.11.15）或 `/root/.local/bin/python3.11`。下表数字为 Owner 报告值，**Reviewer 必须自行重跑/复算**，不得直接引用。

| Case ID | 命令（精确 argv） | UTC | 结果（Owner） | 原始证据路径 |
|---|---|---|---|---|
| `P2-03-A12-BEFORE` | `for i in $(seq 1 30); do python -m pytest tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one -q; done`（`git archive 3e7afee` 干净副本中） | 2026-11-19T17:53:32Z | **27 passed / 3 failed**；失败 shape 均为 loser 得 `AUTHORIZATION_USE_RECORD_INVALID` | `docs/g4h0/evidence/p2_03_a12_loop30_before.log` |
| `P2-03-A12-AFTER` | 同上（修复后 worktree） | 2026-11-19T17:53:32Z（日志头）| **30/30 PASS** | `docs/g4h0/evidence/p2_03_a12_loop30_after.log` |
| `P2-03-STRESS-BEFORE-N` | `PYTHONPATH=src python scripts/g4h0/p2_03_stress.py --rounds 30 --label before-fix-natural`（`git archive 3e7afee` 副本） | 见 log/json（`docs/g4h0/evidence/p2_03_stress_before_fix_natural.json`） | 30 轮：失败 1（loser `AUTHORIZATION_USE_RECORD_INVALID`），双消费 0 | `docs/g4h0/evidence/p2_03_stress_before_fix_natural.{log,json}` |
| `P2-03-STRESS-BEFORE-W` | 同上 + `--widen-write-ms 100`（TEST_ONLY 竞态放大器） | 见 log/json | 30 轮：**30/30** loser `AUTHORIZATION_USE_RECORD_INVALID`，双消费 0 | `…before_fix_widened.{log,json}` |
| `P2-03-STRESS-AFTER-N` | `PYTHONPATH=src python scripts/g4h0/p2_03_stress.py --rounds 40 --label after-fix-natural ...` | 见 log/json | **40/40 全绿**，loser 全 `AUTHORIZATION_REPLAYED`，双消费 0、残留 0、mode 0o600 | `…after_fix_natural.{log,json}` |
| `P2-03-STRESS-AFTER-W` | 同上 + `--widen-write-ms 100` | 见 log/json | **40/40 全绿**，同上 | `…after_fix_widened.{log,json}` |
| `P2-04-RUFF` | `/root/Autonomous Teacher/.venv/bin/ruff check tests/security/test_scan_git_secrets.py tests/security/` | 2026-11-19T18:09:38Z | `All checks passed!` exit 0 | `docs/g4h0/evidence/p2_04_ruff_test_scan_git_secrets.log` |
| `A-07-PROBES` | `PYTHONPATH=src /root/Autonomous Teacher/.venv/bin/python scripts/g4h0/no_key_probes.py --output docs/g4h0/evidence/a07_no_key_probes.json` | 2026-11-19T18:09:38Z | **22/22 PASS**（LiveGate 恒 BLOCKED、CLI/run_live exit 3、strace 0 网络、0 Key/env、冻结文件零 diff） | `docs/g4h0/evidence/a07_no_key_probes.{log,json}`；`docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md` |
| `P2-FIX-UNIT` | `pytest tests/integration/g4_h0 -q` / `tests/integration/g4_f5 -q` / `tests/integration/g4_a/test_a12_replay_epoch.py -q` / `tests/security -q` | 见 P2_FIX_REPORT §6 | 14 / 17 / 19 / 7 passed（Owner） | `docs/g4h0/P2_FIX_REPORT.md` §6 |
| `P2-FIX-SUBSET` | `pytest tests/integration/g4_h0 tests/integration/g4_f5 tests/integration/g4_a/test_a12_replay_epoch.py tests/integration/g4_a/test_a07_trusted_file_boundary.py tests/security tests/unit/security -q` | Owner 报告 85.02s | **189 passed**（Owner） | `docs/g4h0/P2_FIX_REPORT.md` §6 |
| `PKT-V1-CHECK` | `cd <v1-packet> && sha256sum -c hashes.sha256` | 2026-11-19T17:41Z / 17:42Z（两次） | **173/173 OK**；177 files/0 symlink；全量 payload tree `111c1361…` ≠ manifest `e464b9b1…`；剔除 2 sidecar 后 = manifest | `docs/g4h0/evidence/P2-01_packet_v1_verify_20261119T174453Z.log` |
| `PKT-V2-BUILD` | `PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B scripts/g4/build_packet_g4f.py --docs-sha 3e7afee… --out "$PWD/artifacts/g4h0/packet-v2" --force` | 2026-11-19T17:40:16Z | 175 files/0 symlink/0 sidecar/173 hashes OK/payload 172/tree `ffae8b3b…`=manifest | `docs/g4h0/evidence/P2-01_packet_v2_{build,verify}_*.log`、`docs/g4h0/evidence/P2-01_v2.sha256` |
| `INFRA-GUARD` | `git diff --name-only 3e7afee..813e6a6 -- <受保护文件/既有 docs>` | 2026-11-19T18:16Z | 输出为空（零 diff） | 本文件 §2；可 `git diff` 独立复算 |

### 3.1 需 Reviewer 优先复跑的负例清单（建议顺序）

1. **P2-03 前后对比**：从 `3e7afee` 干净副本跑 a12 standalone ×30（期望复现 ≥1 次 `AUTHORIZATION_USE_RECORD_INVALID`）；从 `813e6a6` 跑同循环 ×30（期望 30/30）；再跑 `p2_03_stress.py --rounds 40` 自然/放大各一次（期望 0 双消费、loser 全 `REPLAYED`）。
2. **P2-04**：`ruff check tests/security/`（期望 `All checks passed!`），并核对 diff 仅删 1 行、无断言变化。
3. **P2-05**：`pytest tests/integration/g4_f5/test_f5_pre_send_timeout_observation.py -q`（2 项）；确认 observation-only 记录不影响 allow/deny、`dispatch_seq` 不被消耗。
4. **P2-06**：`pytest tests/integration/g4_f5/test_f5_recovery_reason.py -q`（3 项）；确认状态仍 `SETTLEMENT_UNCERTAIN`、held>0、不重发/不双结算。
5. **A-07**：`scripts/g4h0/no_key_probes.py` 在 `813e6a6` 上重跑（22/22）；独立验证 `run_live.sh`/CLI exit 3、`strace -f -e trace=network` 0 网络、0 key-like env、4 个冻结文件零 diff。
6. **P2-01 v1/v2**：v1 `sha256sum -c` 173/173 且 177 files/0 symlink（确认未被本轮改写）；payload tree 复算（全量 vs 剔 sidecar）；v2 175 files/0 sidecar/173 hashes OK/`P2-01_v2.sha256` 175/175。
7. **A-02/A-05/A-06 文档**：核对 `RISK_DISPOSITION.md` 的 finding/建议/留空栏、`PROVIDER_CONTRACT_DRAFT.md` 的 `VERIFIED/INFERRED/UNVERIFIED` 分层与“未批准路由”、`DEPLOYMENT_RUNBOOK.md` 的 `DESIGN_PENDING_HUMAN` 与失败关闭约束；检查文档之间 P2 编号/SHA/状态词一致性（见 §8）。
8. **身份与范围**：`git rev-parse`/`git diff --name-only 3e7afee..813e6a6` 复算 43 files/+7703/-35；受保护文件与冻结 docs 零 diff；`813e6a6` 工作树 clean。
9. **集成回归（Lead/Reviewer 决定是否抽跑）**：`tests/integration/g4_a/`、`tests/unit/`、`g4_f2/f3/c/d/b`、全仓 ruff 均为 Owner `NOT_RUN`（见 P2_FIX_REPORT §6），不得当作 PASS。

---

## 4. 状态分类（已证实 / 未验证 / 阻断）

### 4.1 本轮已证实（Engineering scope，可复核）
- A0 基线：HEAD/base、主工作树 clean、src 50 文件 sha256、docs 冻结哈希、状态常量证据（`BASELINE.md`）。
- A2 研究：28 个官方/辅助来源的采集时间+响应字节+sha256；官方契约层字段/价格/错误码/限流（`A2_SOURCES.md`、`PROVIDER_CONTRACT_DRAFT.md`、`PRICE_AND_USAGE_VERIFICATION.md`、`BILLABLE_PATH_INVENTORY.md`）。
- A3 设计：受信部署 Runbook、信任边界、人工签核模板、E5 全量清单（**均为 DESIGN_PENDING_HUMAN，不是部署证据**）。
- A-04：G4-F v1 Packet 未被改写（173/173、177 files、sidecar mtime 未变）；v2 本地重建完整性自洽（175/173/payload tree 匹配/0 sidecar）。
- P2-03/04/05/06：修复实现 + 定向测试 + 压测/证据（Owner 侧）；A-07：22/22 无 Key 负例（Owner 侧）。
- 受保护 Live 文件与冻结 docs/Packet 零 diff；集成 worktree clean。

### 4.2 未验证（UNVERIFIED，不得写成 PASS）
- **P2-03/05/06 修复的独立复测**：Owner 的结果尚需 Reviewer 从 `813e6a6` 重跑（尤其并发压测、窗口观测、recovery reason）。
- **A-07 证据对冻结 SHA 的绑定**：探针于 2026-11-19T18:09:38Z 在 fix 工作树（修复提交前）生成；Worktree 内容与 `813e6a6` 的一致性需 Reviewer 在冻结 SHA 上重跑确认。
- **P2-03 压测 evidence 对冻结 SHA 的绑定**：after-fix 运行发生在 fix 工作树提交前，需在 `813e6a6` 重跑。
- **G4-F P2-01 v2 的独立复算**：v2 由本 impl 侧生成，尚无第二方独立复算。
- **E5-P04 / DSH merged registry**：仍 UNVERIFIED（无权威导出，仅 per-dispatch 白名单兜底）。
- **F4 candidate-crash + live Controller**、F4-R1 字节级 context：仍 UNVERIFIED。
- **真实 Provider/Key/TLS/账单/额度**：0 真实调用、0 真实费用，全部 UNVERIFIED。
- 完整回归（g4_a 全目录/unit 全量/f2/f3/c/d/b、全仓 ruff、OCI/Node/DSH）：Owner `NOT_RUN`，未验证。

### 4.3 阻断（BLOCKED / HUMAN_REQUIRED）
- `E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT`（人类信任根/Key Broker/真实 Egress/部署后只读、真实账单）。
- `G4-H = NOT_AUTHORIZED`、`G5 = BLOCKED`、`G6 = NOT_RUN`、`LiveGate = BLOCKED`、`M0 = DECISION_PENDING`（本轮不变）。
- P2-RUN-IDENTITY / P2-USERNS / P2-DISK、test-only hooks、F5-R2 撤销链、F4 子场景：维护者签收/补测前保持残余（见 `RISK_DISPOSITION.md`）。
- 任何真实 Key 注入、真实 Provider 调用、G5 授权：**不在本轮授权范围**。

---

## 5. 被测模型 / 费用来源分类（强制声明）

```text
真实模型调用（real model calls）        = 0
真实外部 HTTP/TCP（真实 Provider）      = 0
真实费用（real spend / invoice）        = 0
真实 Provider Key（读取/生成/使用）     = 0
被测 Provider Route                    = synthetic_only / offline-test-only-g3b / fixture-bridge-v1
费用来源                               = Synthetic fixture 价格（非供应商账单；不得作为真实费用证据）
真实路由（primary_route）              = 未批准、未选定；维护者须在 G4-H1/G5 前确认（A2 稿）
```

- 所有“费用/usage”读数均为 synthetic fixture / 本地 bookkeeping，**不是**真实计费证据。
- A2 的官方价格页快照（2026-11-19T17:47:09Z）只用于**文档层核实**，未触发任何请求计费。
- 本轮**没有**任何真实出站；A-07 `strace` 只观察 hard-stop 入口，0 `AF_INET/connect`。

---

## 6. 请求 Reviewer 的复核范围（建议清单）

1. **身份与范围**：§0/§1/§2 的 SHA、merge 构成、43 files/+7703/-35、受保护文件与冻结 docs 零 diff、工作树 clean；`docs/g4h0/` 新增文件是否超出允许范围；是否误改 src 之外的冻结区域。
2. **P2-03**：原子发布实现是否真正保证“恰好一次 + loser 稳定 replay + fail-closed 不放宽”；`os.link` 失败路径、有界重试边界、临时文件清理、MAX 计数排除；独立从 `3e7afee` 复现 before 失败、从 `813e6a6` 复跑 after 全绿；2 进程 ≥30 轮（建议 40 轮 + 放大窗口）。
3. **P2-04**：仅删未使用变量、无断言/扫描器行为变化；`ruff check tests/security/` 通过。
4. **P2-05**：observation-only 记录不参与 allow/deny、不占 `dispatch_seq`、不掩盖 abort；deadline 分支行为与 0 reservation/0 attempt/0 Fake 结论。
5. **P2-06**：recovery reason 保留原始标签 + 追加证据；状态/held/不重发/不双结算不变；gate journal/dispatch-window 仍为原因权威。
6. **A-07**：22 项负例在冻结 SHA 上重跑；LiveGate 恒 BLOCKED、CLI/run_live exit 3、Adapter 四入口拒绝、SDK 未 import、0 网络、0 Key/env、冻结文件零 diff。
7. **A-04/P2-01**：v1 Packet 未被改写（173/173、177/0、mtime）；v1 payload tree 漂移复算；v2 完整性（175/173/172/0 sidecar/`P2-01_v2.sha256` 175/175）及 v2 的身份限制（§8-1）。
8. **A-02/A-05/A-06 文档**：风险处置是否“只建议、不代签”；Provider 研究是否区分官方/辅助/第三方来源且未把 Synthetic 当真实；Runbook/信任边界/签核模板/E5 清单是否明确 `DESIGN_PENDING_HUMAN`/`BLOCKED` 且无“已部署/已批准”表述。
9. **一致性**：§8 已知不一致项是否被正确处理；状态词是否乱标 PASS；P2 编号是否跨文档一致。
10. **负例/对抗**：自行构造负例（replay 竞态、symlink use-record、坏/半写记录、deadline 竞争、伪 env/Markdown 解锁、假 Key 泄漏、v1/v2 packet 篡改）验证 fail-closed。

---

## 7. 请求的最高裁定

```text
PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE
```

或（如发现缺口）`PARTIAL_FOR_G4H0_READINESS_NO_KEY_SCOPE` / `BLOCKED`。**不得**给出 `E5_PRELIVE_FULL PASS`、`G4 PASS`、`G5 PASS`、`LIVE_APPROVED`、`M0_GO` 或等价表述；Reviewer 的结论只覆盖本机、无 Key、无真实 Provider/计费/TLS/Live 的 G4-H0 工程准入准备范围。

---

## 8. 已知不一致 / 限制（本申请主动披露；Reviewer 应据此复核）

1. **Packet v2 不是 `813e6a6` 的快照**：`artifacts/g4h0/packet-v2/manifest.json` 的 `impl_sha = e7d92967…`（G4-F 证据 HEAD）、`docs_sha = build_sha = 3e7afee`。v2 是**G4-F 归档证据的完整性修复重建**（P2-01），**不包含**本轮 `813e6a6` 的 src 变更，不能作为“813e6a6 的 Packet”。本轮实现的证据 = `git 813e6a6` + `P2_FIX_REPORT.md` + 新增 tests/scripts + evidence 目录。
2. **`RISK_DISPOSITION.md` 是 0a9ee67 时点快照**：其中 P2-03/04/05/06 标为“未修复/UNVERIFIED”，而集成后 fix 分支已交付修复（`33e2fd6`/`9ed7ede`/`ff9afd0` 见 §1）。本请求与 `EVIDENCE_INDEX.md` 采用**更新后状态**（“实现已交付、独立复测未完成”）；`RISK_DISPOSITION.md` 本身未改写（属我线已提交文档，Lead 合并策略决定是否加 errata）。
3. **A-07 与 P2-03 压测证据的时间绑定**：均在 fix 工作树提交前（2026-11-19T18:09Z 左右）生成，未显式记录“工作树内容 == `813e6a6`”；Reviewer 应在冻结 SHA 上重跑（§3.1）。
4. **Packet v2 仍含已知内容缺陷**：`P2-02`（矩阵 `F2-07` 错误路径）未修；`P2-07`（`env/zero-key.json` 1/4 reasons）未修；v2 的矩阵副本为归档后 46 行 43/2/0/1。这些限制已写入 `RISK_DISPOSITION.md`，不得被 v2 的“完整性自洽”掩盖。
5. **A2/A-05 状态词**：`PROVIDER_CONTRACT_DRAFT.md` §0 使用 `PARTIAL / PASS_FOR_RESEARCH_SCOPE`；本请求只把它计入 A-05 的“研究文档完成”，真实 Provider 契约/路由/价格签 **仍 UNVERIFIED/ HUMAN_REQUIRED**，不构成 PASS。
6. **host `dsh` CLI 版本**：本机 `dsh` = `0.2.1-rc.2`，与 G4-F 冻结 runtime `0.2.2-rc.2`（stage artifact `1cc41d5a…`）不是同一二进制（`BASELINE.md` §4 已披露）；任何“DSH 版本一致”表述必须以 stage 工件为准。
7. **A3_REFS C-12 的跨分支交付物**：`A3_REFS.md:70` 提示 A 线并行交付物可能不在本分支；集成后 `813e6a6` 已包含 A0/A1/A2/A3 全部文档，该歧义在集成层面已解决，但 Review Request 仍按“集成后”引用。
8. **P2 编号映射**：G4-F 复核用 `P2-01..P2-08`；`A3_REFS.md` 用 `C-01/P2-03`、`C-02/P2-05+P2-06`；`P2_FIX_REPORT.md` 用 `P2-03/04/05/06`。三者指向同一组发现，无冲突；Reviewer 可按 `RISK_DISPOSITION.md` §6 汇总表核对。

---

## 9. Reviewer 约束（与执行方案/AGENTS.md 一致）

- Reviewer 必须**未参与**本轮实现/证据生成；从**冻结 SHA `813e6a6`** 的独立 clean worktree 复现，不得用 Owner 的 `summary/checks` 文字代替自己的命令结论。
- 不得修改 `src/`、冻结 docs/Packet、`artifacts/` 证据；不得 `push`/`merge`/`amend`；只写自己的 review 产物（独立分支/目录）。
- 不得读取/生成/使用真实 Key，不得发起任何真实 Provider/付费请求；负例中的假 Key 只能出现在被测子进程 env，不得打印。
- 若发现 P0/P1、scope 漂移、真实 Key/网络、或证据路径错位 → **立即 STOP 并保全证据**，按 `RISK_DISPOSITION.md` 的 finding 语义登记。
- 结论只覆盖本机、无 Key、无真实 Provider/计费/TLS/Live 范围；不得签发任何人类授权。

---

## 10. 附件与引用

- 状态/证据总览：`docs/g4h0/EVIDENCE_INDEX.md`（A-01..A-08 实际状态，禁止预填 PASS）。
- 残余与建议：`docs/g4h0/RISK_DISPOSITION.md`（A1，建议态；注意 §8-2 的时点限制）。
- P2 修复：`docs/g4h0/P2_FIX_REPORT.md`、`docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md`、`docs/g4h0/evidence/**`。
- A0：`docs/g4h0/BASELINE.md`；A2：`docs/g4h0/{A2_SOURCES,PROVIDER_CONTRACT_DRAFT,PRICE_AND_USAGE_VERIFICATION,BILLABLE_PATH_INVENTORY}.md`；A3：`docs/g4h0/{A3_REFS,DEPLOYMENT_RUNBOOK,TRUST_BOUNDARY_DIAGRAM,HUMAN_SIGNOFF_TEMPLATE,E5_PRELIVE_FULL_CHECKLIST}.md`。
- 一页状态：`docs/g4h0/PACKET_SUMMARY.md`；人类决策建议：`docs/g4h0/HUMAN_DECISIONS_PROPOSED.md`。

> **本文件不是自证、不是授权、不是 PASS**。请求 Reviewer 独立给出 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE` 或 `PARTIAL/BLOCKED`；最终 STOP 于维护者决策。
