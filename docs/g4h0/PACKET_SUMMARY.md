# G4-H0 — Packet Summary（一页状态，review-request 版本）

- **base SHA**：`3e7afee077845a071cd364e93ab209cac20b2d5f`
- **冻结 impl SHA**：`813e6a680399ba245bd0e76296e1212118a83460`（octopus merge，2026-11-19T18:14:07Z；43 files / +7703 / -35）
- **证据包**：`artifacts/g4h0/packet-v2`（175 files / 173 hashes OK / 0 sidecar；**manifest.impl_sha=e7d9296，属 G4-F 证据完整性重建，不是 `813e6a6` 实现快照**）
- **性质**：无 Key 准入准备状态页。不是授权、不是 PASS、不是 E5 Full。生成时间（UTC）：2026-11-19T18:2xZ。

## Current SHA

| 对象 | 值 |
|---|---|
| base | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| impl | `813e6a680399ba245bd0e76296e1212118a83460`（tree `1772cb54…`） |
| 分支构成 | `work/m0-g4h0-core 0a9ee67` + `work/m0-g4h0-research 011f128` + `work/m0-g4h0-docs f4a154a` + `work/m0-g4h0-fix 33e2fd6/9ed7ede/ff9afd0` |
| 状态常量（未变） | `G4-H=NOT_AUTHORIZED` / `G5=BLOCKED` / `G6=NOT_RUN` / `LiveGate=BLOCKED` / `M0=DECISION_PENDING` / `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` |

## Done（本轮交付）

- **A0**：`BASELINE.md`（HEAD/主工作树 clean、src 50 文件 sha256、docs 冻结哈希、工具版本、状态常量行号证据、A0 分类表）。
- **A1**：`RISK_DISPOSITION.md`（16 条 finding：P2-01..08、DSH registry/E5-P04、RUN-IDENTITY/USERNS/DISK、Crash Hooks/撤销链、F4 组合；建议态、决策栏留空）。
- **A2**：`PROVIDER_CONTRACT_DRAFT.md` / `PRICE_AND_USAGE_VERIFICATION.md` / `BILLABLE_PATH_INVENTORY.md` / `A2_SOURCES.md`（28 来源含 UTC+sha256；0 Key/0 登录/0 真实请求）。
- **A3**：`DEPLOYMENT_RUNBOOK.md` / `TRUST_BOUNDARY_DIAGRAM.md` / `HUMAN_SIGNOFF_TEMPLATE.md` / `E5_PRELIVE_FULL_CHECKLIST.md` / `A3_REFS.md`（`DESIGN_PENDING_HUMAN`，未部署）。
- **P2 修复**：P2-03 原子发布（`authorization.py` +126/-27）、P2-05 observation-only（`controller.py`）、P2-06 reason 保留、P2-04 lint；新增 g4_h0 14 + g4_f5 5 项测试、压测脚本、A-07 22 项负例探针。
- **A4 准备**：`REVIEW_REQUEST.md`、`EVIDENCE_INDEX.md`、`HUMAN_DECISIONS_PROPOSED.md`、本 `PACKET_SUMMARY.md`；冻结 docs/Packet 与受保护 Live 文件零 diff。

## Evidence（关键，可复核）

- v1 Packet 未改写：177 files / 0 symlink / `sha256sum -c` **173/173 OK**（两次）；全量 tree `111c1361…` ≠ manifest `e464b9b1…`，剔除 2 sidecar 后 = manifest（`P2-01_packet_v1_verify_*.log`）。
- v2 Packet：175 files / 0 sidecar / 173 hashes OK / payload 172 / tree `ffae8b3b…`=manifest / integrity report PASS（`P2-01_packet_v2_*.log`、`P2-01_v2.sha256`）。
- P2-03 前后：a12 ×30 before 27/30 → after 30/30；stress natural 1/30 失败 → after 40/40；widened 30/30 INVALID → after 40/40 全绿、loser 全 `REPLAYED`、0 双消费（`p2_03_*` 证据）。
- A-07：22/22 PASS（LiveGate 恒 BLOCKED、CLI/run_live exit 3、Adapter 4 入口拒绝、strace 0 网络、0 Key/env、冻结文件零 diff）——Owner 侧，待独立复跑。
- 成本/模型分类：**0 真实模型调用 / 0 真实 Provider HTTP / 0 真实费用 / 0 真实 Key**；synthetic route `offline-test-only-g3b / fixture-bridge-v1`。

## Blocked（不得写成 PASS）

- **A-08 独立 Review 尚未发生**（本请求等待 Reviewer）；A-03/A-07 与 P2 修复均需在冻结 `813e6a6` 上独立复测。
- `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；真实 Key/Broker/Egress/Watchdog/TLS/账单未部署/未验证。
- DSH merged registry / E5-P04、F4 candidate-crash+live Controller、F4-R1 字节级 context：UNVERIFIED。
- P2-RUN-IDENTITY / USERNS / DISK、test-only hooks、F5-R2 撤销链：维护者未签收。
- 完整回归（g4_a 全目录/unit/f2/f3/c/d/b/全仓 ruff）Owner `NOT_RUN`；不得当 PASS。
- Packet v2 不修 P2-02/P2-07 内容问题，且不是 `813e6a6` 快照（见 `REVIEW_REQUEST.md` §8）。

## Next

1. 独立 Reviewer 从 `813e6a6` 按 `REVIEW_REQUEST.md` §3.1/§6 复跑并给出 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE` 或 `PARTIAL/BLOCKED`。
2. Lead 汇总 `HUMAN_DECISIONS.md`（Reviewer 版）与 `HUMAN_DECISIONS_PROPOSED.md`（本线提案），STOP。
3. 维护者逐项决策（D-01..D-12），未获授权前不得进入 G4-H1/H2/G5/G6/Live。

## Human Decision

- 接受哪份 Packet：v1+ERRATA 或 v2（v2 需独立复核）。
- P2-01..08 逐项 ACCEPT/FIX/BLOCK；P2-03 修复接受前需独立复测。
- DSH registry/E5-P04、RUN-IDENTITY/USERNS/DISK、test hooks/撤销链/F4 组合的残余签收。
- A-05 路由/价格快照由维护者确认；A-06 部署授权另立。
- **Agent 不代签任何 ACCEPT/APPROVED/AUTHORIZED；任何 PASS 不得外推为 E5-Full/G5/Live/M0_GO。**
