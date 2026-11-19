# G4-H0 — 证据索引与 A-01..A-08 实际状态

- **文档 ID**：`G4H0-EVIDENCE-INDEX-v1`
- **基线**：`base=3e7afee077845a071cd364e93ab209cac20b2d5f`；**冻结 impl=`813e6a680399ba245bd0e76296e1212118a83460`**
- **性质**：证据地图 + 状态登记。**禁止预填 PASS**；本文件不是评审结论、不是授权、不是 E5 Full。
- **状态口径**（与 `docs/E5_PRELIVE_FULL_CHECKLIST.md` §0 一致）：`PASS`（本轮已独立证实/可复算）｜`PARTIAL`（部分完成/有明示缺口）｜`UNVERIFIED`（无权威证据）｜`NOT_RUN`（未执行）｜`BLOCKED`（被人类/部署条件阻断）｜`HUMAN_REQUIRED`（只能人类完成）。
- **重要**：Owner 侧数字（fix agent/研究/文档 agent）不等于独立复核；凡未由独立 Reviewer 重跑的本轮结果一律不标 `PASS`。

## 1. A-01..A-08 验收矩阵（本轮实际状态）

| ID | 验收对象 | 本轮实际状态 | 证据文件 / 命令 | 说明与残余 |
|---|---|---|---|---|
| **A-01** | SHA / 代码 / Stage / 依赖冻结身份 | **PARTIAL** | `docs/g4h0/BASELINE.md`；`docs/g4h0/evidence/BASELINE_COMMANDS_20261119T174015Z.log`、`BASELINE_HASHES_20261119T174453Z.txt`；`git rev-parse`/`ls-tree`/`sha256sum` | Git HEAD/base、src 50 文件 sha256、受保护文件、docs 冻结哈希、Stage manifest `82e10c6f…` 已核对（VERIFIED）；**rootfs/deps/stage 全量 tree 未复算**（PARTIAL）。integrated impl `813e6a6` 的完整 diff/证据身份见 `REVIEW_REQUEST.md` §0/§2 |
| **A-02** | P2 与历史残余逐项 disposition | **PARTIAL** | `docs/g4h0/RISK_DISPOSITION.md`（16 条 finding，含建议/留空决策栏/前置条件）；`P2_FIX_REPORT.md` | 文档已交付（建议态）；P2-03/04/05/06 在集成后已有实现（见 A-03/`P2_FIX_REPORT.md`）；**维护者未签收任何 ACCEPT**（HUMAN_REQUIRED）。注意 `RISK_DISPOSITION.md` 是 `0a9ee67` 时点快照，P2-03..06 状态以 `REVIEW_REQUEST.md`/本表为准 |
| **A-03** | 并发 consume 的恰一次 / 失败码稳定 | **PARTIAL** | `src/autoteacher_m0/security/authorization.py`（+126/-27）；`tests/integration/g4_h0/test_p2_03_concurrent_consume.py`（14 项）；`scripts/g4h0/p2_03_stress.py`；`docs/g4h0/evidence/p2_03_*`；`docs/g4h0/P2_FIX_REPORT.md` §1 | Owner：before a12 27/30（1 失败形态 INVALID）、widened 30/30 INVALID；after a12 30/30、stress 40+40 轮全绿、loser 全 `REPLAYED`、0 双消费。**独立复测未做 → 不标 PASS**；修复证据需在冻结 `813e6a6` 上重跑（见 `REVIEW_REQUEST.md` §3.1） |
| **A-04** | 旧 Packet 不改写；新包完整性可复核 | **PARTIAL** | v1：`docs/g4h0/evidence/P2-01_packet_v1_verify_20261119T174453Z.log`（177 files/0 symlink、173/173 OK、payload tree 漂移复算）；v2：`P2-01_packet_v2_{build,verify}_*.log`、`P2-01_v2.sha256`、`BASELINE.md` §3 | v1 未改写 = VERIFIED；v2 本地自校验 = VERIFIED（175/0 sidecar/173 OK/172 payload/tree 匹配）；但 **v2 未经第二方独立复算**，且 v2 不是 `813e6a6` 的快照（`manifest.impl_sha=e7d9296`）→ 整体 PARTIAL |
| **A-05** | 正式 Provider 契约不借 Synthetic 充数 | **PARTIAL** | `docs/g4h0/PROVIDER_CONTRACT_DRAFT.md`、`PRICE_AND_USAGE_VERIFICATION.md`、`BILLABLE_PATH_INVENTORY.md`、`A2_SOURCES.md` | 官方文档层契约/价格已核实（28 来源、采集时间+sha256、`VERIFIED/INFERRED/UNVERIFIED` 分层；`0 Key/0 真实请求/0 真实费用`）；**目标路由未批准**（HUMAN DECISION）、真实 wire/usage/账单 UNVERIFIED。研究文档完成 ≠ 契约验证 PASS |
| **A-06** | 签名 / Key / Egress / 预算 / Watchdog / Runbook | **PARTIAL**（设计完成、实现/部署 BLOCKED） | `docs/g4h0/DEPLOYMENT_RUNBOOK.md`、`TRUST_BOUNDARY_DIAGRAM.md`、`HUMAN_SIGNOFF_TEMPLATE.md`、`E5_PRELIVE_FULL_CHECKLIST.md`、`A3_REFS.md` | 可审计 Runbook/权限图/签核模板/E5 清单已交付（`DESIGN_PENDING_HUMAN`）；真实信任根/Key Broker/Egress/Watchdog **未部署**、未演练 → 部署层面 BLOCKED/HUMAN_REQUIRED。任何“已部署/已批准”表述禁止 |
| **A-07** | LiveGate 仍 BLOCKED，0 真 Key / 真 HTTP | **PARTIAL**（Owner 22/22 已跑；待独立复跑） | `docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md`；`docs/g4h0/evidence/a07_no_key_probes.{log,json}`；`scripts/g4h0/no_key_probes.py`；`docs/g4h0/BASELINE.md` §6（本线：`run_live.sh` exit 3、0 key-like env、`podman ps -a` 空） | 22/22 PASS（LiveGate 恒 BLOCKED、require_live 恒抛、run_live/CLI exit 3、Adapter 4 入口拒绝、strace 0 网络、0 Key/env、冻结文件零 diff）；证据生成于 fix 工作树提交前（2026-11-19T18:09:38Z），**需在冻结 SHA 上重跑 → 不预填 PASS**；完整 CLI/Adapter/strace 矩阵已由 A-07 覆盖，真实 Provider 仍 BLOCKED |
| **A-08** | 独立 H0 Review，随后 STOP | **NOT_RUN（本请求已发出，等待独立 Reviewer）** | 本 `docs/g4h0/REVIEW_REQUEST.md` | 尚未发生独立复核；本 impl 线不自证。Reviewer 应从 `813e6a6` 独立复现并按 `REVIEW_REQUEST.md` §6 负例清单执行 |

### 1.1 其他必须登记的状态（不属于 A-01..A-08 行，但影响结论）

| 项 | 状态 | 证据/说明 |
|---|---|---|
| 完整 host 回归（`tests/integration/g4_a/` 全目录、`tests/unit/` 全量、`g4_f2/f3/c/d/b`、全仓 ruff） | **NOT_RUN** | `P2_FIX_REPORT.md` §6 明确未重跑；不得当作 PASS |
| 定向回归（g4_h0 14 / g4_f5 17 / a12 19 / security 7 / 子集 189） | **PARTIAL**（Owner 报告；待 Reviewer 在冻结 SHA 复跑） | `P2_FIX_REPORT.md` §6 |
| 真实 Key / Provider / TLS / 账单 / 额度 | **BLOCKED / HUMAN_REQUIRED** | 0 真实调用、0 真实费用；`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| DSH merged registry / E5-P04 | **UNVERIFIED** | 无权威导出；per-dispatch 白名单兜底（见 `RISK_DISPOSITION.md` §2） |
| F4 candidate-crash + live Controller / F4-R1 字节级 context | **UNVERIFIED** | `RISK_DISPOSITION.md` §5；矩阵 `F4-06` 仍 UNVERIFIED |
| P2-RUN-IDENTITY / P2-USERNS / P2-DISK / test-only hooks / F5-R2 撤销链 / F5-R6 SIGKILL 窗口 | **PARTIAL / HUMAN_REQUIRED**（未签收） | `RISK_DISPOSITION.md` §3/§4；`M0_G4_HUMAN_HANDOFF.md` §5.1 |
| Packet v2 独立复算 | **PARTIAL** | 本线生成，无第二方复算；且 v2 不含 `813e6a6` 变更（见 `REVIEW_REQUEST.md` §8-1） |
| host `dsh` CLI 0.2.1-rc.2 vs 冻结 runtime 0.2.2-rc.2 | **PARTIAL（已披露）** | `BASELINE.md` §4；G4-F 身份以 stage 工件为准 |
| 状态常量（G4-H/G5/G6/LiveGate/M0/E5） | **VERIFIED（未变）** | `REVIEW_G4F_INDEPENDENT.md:35-40`；`M0_G4F_REVIEW_ERRATA.md:92-97`；`gates.py:70/82`；`run_live.sh:5`；本轮零改动 |

## 2. 证据文件索引（本轮，按用途）

| 证据组 | 文件 | 说明 |
|---|---|---|
| 基线/身份 | `docs/g4h0/evidence/BASELINE_COMMANDS_20261119T174015Z.log`、`BASELINE_HASHES_20261119T174453Z.txt` | Git 身份、src/docs 哈希、工具版本、外部 worktree 观察、v1 Packet 检查 |
| 环境/无 Key 基线 | `docs/g4h0/evidence/ENV_TOOLS_LIVEGATE_20261119T174800Z.log` | 脱敏 env 扫描（值不打印）、工具版本、`podman ps -a`、`run_live.sh` exit 3、主工作树状态 |
| P2-01 v1/v2 | `P2-01_packet_v1_verify_20261119T174453Z.log`、`P2-01_packet_v2_build_20261119T174016Z.log`、`P2-01_packet_v2_verify_20261119T174135Z.log`、`P2-01_v2.sha256` | v1 未改写 + sidecar 漂移复算；v2 重建与完整性；175 行可复核哈希清单 |
| P2-03 前后对比 | `p2_03_a12_loop30_before.log`、`p2_03_a12_loop30_after.log`、`p2_03_stress_before_fix_{natural,widened}.{log,json}`、`p2_03_stress_after_fix_{natural,widened}.{log,json}` | a12 standalone ×30；2 进程压测 30/40 轮（自然/放大窗口） |
| P2-04 | `p2_04_ruff_test_scan_git_secrets.log` | F841 修复前后 ruff 结果 |
| A-07 | `a07_no_key_probes.{log,json}` | 22 项负例逐项结果 + 汇总（`status=PASS`，Owner 侧） |
| 文档 | `docs/g4h0/*.md`（BASELINE/RISK_DISPOSITION/P2_FIX_REPORT/NO_KEY_AND_LIVEGATE_EVIDENCE/A2×4/A3×5） | 见 `REVIEW_REQUEST.md` §0.1 的 sha256 表 |

## 3. 复核命令索引（Reviewer 用；均为本地、无 Key）

```text
# 身份/范围
git -C "/root/Autonomous Teacher/worktrees/m0-g4h0" rev-parse HEAD  # = 813e6a680399…
git -C "/root/Autonomous Teacher/worktrees/m0-g4h0" diff --shortstat 3e7afee..813e6a6
git -C "/root/Autonomous Teacher/worktrees/m0-g4h0" diff --name-only 3e7afee..813e6a6 -- \
  src/autoteacher_m0/security/gates.py scripts/run_live.sh src/autoteacher_m0/runtime/dsh_adapter.py src/autoteacher_m0/cli.py
# P2-03（从冻结 SHA 复跑）
cd <clean-worktree-813e6a6> && for i in $(seq 1 30); do python -m pytest \
  tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one -q; done
PYTHONPATH=src python scripts/g4h0/p2_03_stress.py --rounds 40 --label after-fix-natural --output /tmp/after-n.json
PYTHONPATH=src python scripts/g4h0/p2_03_stress.py --rounds 40 --widen-write-ms 100 --label after-fix-widened --output /tmp/after-w.json
# P2-04/05/06
"/root/Autonomous Teacher/.venv/bin/ruff" check tests/security/
python -m pytest tests/integration/g4_f5/test_f5_pre_send_timeout_observation.py tests/integration/g4_f5/test_f5_recovery_reason.py -q
# A-07
PYTHONPATH=src python scripts/g4h0/no_key_probes.py --output /tmp/a07.json
# P2-01 v1/v2
cd "/root/Autonomous Teacher/artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99" && sha256sum -c hashes.sha256   # 173/173
cd "/root/Autonomous Teacher/worktrees/m0-g4h0/artifacts/g4h0/packet-v2" && sha256sum -c hashes.sha256  # 173/173
cd "/root/Autonomous Teacher/worktrees/m0-g4h0/artifacts/g4h0/packet-v2" && sha256sum -c \
  "/root/Autonomous Teacher/worktrees/m0-g4h0-core/docs/g4h0/evidence/P2-01_v2.sha256"  # 175/175
```

## 4. 不得外推（强制）

1. 本索引中任何 `PARTIAL`/Owner 侧数字都**不是** `PASS`，更不是 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`；唯一权威裁定由独立 Reviewer 给出。
2. 不得把 A-05 研究文档、A-06 设计文档出现即当作契约已验证或部署已就绪；不得把 v2 Packet 完整性自洽当作 `813e6a6` 的实现快照。
3. 不得把本轮结果写成 E5-PreLive Full、G4/H/G5/G6/Live 通过或 `M0_GO`；状态常量保持 `G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
