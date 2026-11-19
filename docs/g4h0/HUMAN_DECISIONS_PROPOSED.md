# G4-H0 — 提议的人类决策清单（PROPOSED，供维护者参考）

- **文档 ID**：`G4H0-HUMAN-DECISIONS-PROPOSED-v1`
- **性质**：**提议稿（PROPOSED）**。本文件由 A 线实施者整理，供维护者审阅；**不是**正式决策记录、不是授权、不是签核。
- **命名原因**：独立 Reviewer 会在自己的分支产出 `docs/g4h0/HUMAN_DECISIONS.md`（正式决策记录）。合并时**以 Reviewer 版本为准**，本文件仅作为提案输入，不得与本文件混淆。
- **基线**：`base=3e7afee077845a071cd364e93ab209cac20b2d5f`；**冻结 impl=`813e6a680399ba245bd0e76296e1212118a83460`**。
- **规则**：所有决策项在维护者亲自填写并签名前保持 `PENDING_HUMAN_ACTION`；Agent 不得代填、代勾、代签任何 ACCEPT / APPROVED / AUTHORIZED。

## 0. 汇总

| # | 决策 | 建议（Agent 建议，非签核） | 当前状态 |
|---|---|---|---|
| D-01 | 是否接受本轮独立 Review 的裁定与范围 | 接受 Reviewer 的 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE` 或 `PARTIAL/BLOCKED`，限定无 Key 范围 | `PENDING_HUMAN_ACTION` |
| D-02 | Packet 版本选择 | 接受 v1 + ERRATA 披露，或采用/复核 v2（v2 仅完整性修复，不含 `813e6a6` 变更） | `PENDING_HUMAN_ACTION` |
| D-03 | P2-03 并发消费修复是否接受 | 先用独立 Reviewer 在冻结 SHA 复测（2 进程 ≥30 轮、恰好一次、loser `REPLAYED`、0 双消费），再接受 | `PENDING_HUMAN_ACTION` |
| D-04 | P2-04/05/06 修复是否接受 | 接受修复（P2-04 lint；P2-05 observation-only；P2-06 reason 保留），以独立复测为准 | `PENDING_HUMAN_ACTION` |
| D-05 | P2-01/P2-02/P2-07 残余 | P2-01 由 v2 或在 ERRATA 中继续披露；P2-02/P2-07 在下一版 Packet/矩阵修正 | `PENDING_HUMAN_ACTION` |
| D-06 | DSH merged registry / E5-P04 | 在 E5-Full/G5 前由人类签收“UNVERIFIED + per-dispatch 白名单补偿控制”，或要求 DSH 权威导出 | `PENDING_HUMAN_ACTION` |
| D-07 | P2-RUN-IDENTITY / P2-USERNS / P2-DISK | 签收残余（附条件）或另立加固工作项；真实部署前不得放宽 DAC/mount/磁盘模型 | `PENDING_HUMAN_ACTION` |
| D-08 | test-only crash/delay hooks、F5-R2 撤销链、F4 candidate-crash+live Controller | G4-H1 前移除/隔离 hooks、补测 F4 子场景；决定撤销链是否需签名；不承诺 exactly-once | `PENDING_HUMAN_ACTION` |
| D-09 | A-05 目标路由 / 官方价格快照 | 维护者在 G4-H1/G5 前确认 provider/model/endpoint/费率与价格快照；A2 研究稿不替代批准 | `PENDING_HUMAN_ACTION` |
| D-10 | A-06 受信部署 Runbook / 信任根 / Key Broker / Egress / Watchdog | 仅在独立审查后由人类执行；本轮不部署、不注入 Key | `BLOCKED` / `PENDING_HUMAN_ACTION` |
| D-11 | 是否进入 G4-H1/H2、G5/G6、任何 Live | **本文件不授权**；需 G4-H-01..06 全部完成 + 人类显式单次授权 | `BLOCKED` |
| D-12 | 状态常量是否维持 | 维持 `G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` | `PENDING_HUMAN_ACTION` |

## 1. 逐项提案与决策栏（留空）

### D-01 独立 Review 裁定与范围
- **背景**：`docs/g4h0/REVIEW_REQUEST.md` 已发出；冻结 impl `813e6a6`、base `3e7afee`；请求最高裁定 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`。
- **建议**：仅在本机、无 Key、无真实 Provider/计费/TLS/Live 范围内接受裁定的**字面范围**；不把任何 PASS 外推为 E5-Full/G5/Live。
- **维护者决策（留空）**：☐ ACCEPT（限定范围）　☐ PARTIAL（要求补测：______）　☐ BLOCKED　签名/日期：__________

### D-02 Packet 版本
- **背景**：G4-F v1 Packet 有 P2-01 sidecar 漂移/P2-02 路径/P2-07 reasons（详见 `RISK_DISPOSITION.md`）；v2 已本地重建（175 files/173 hashes OK，**manifest.impl_sha=e7d9296，非 `813e6a6` 快照**）。
- **建议**：明确接受“v1 + ERRATA 披露”与/或复核采用 v2；无论选择哪份，都不得声称 v1 全量自校验一致，也不得把 v2 当作本轮实现的 Packet。
- **维护者决策（留空）**：☐ 接受 v1+ERRATA　☐ 采用 v2（Reviewer 已复核）　☐ 要求 v2.1/v3（修正 P2-02/P2-07）　☐ 其它：______　签名/日期：__________

### D-03 P2-03 并发消费修复
- **背景**：Owner 证据：before a12 27/30、widened 30/30 失败；after a12 30/30、stress 40+40 全绿、loser 全 `REPLAYED`、0 双消费（`P2_FIX_REPORT.md` §1）；独立复测未做。
- **建议**：**必须先由独立 Reviewer 在冻结 `813e6a6` 重跑**并确认“恰好一次 + 不放宽 fail-closed”后接受；否则维持 `RISK_DISPOSITION.md` 的“H1 前 FIX”建议。
- **维护者决策（留空）**：☐ 接受（附独立复测证据：______）　☐ 要求进一步修复　☐ BLOCKED　签名/日期：__________

### D-04 P2-04/05/06 修复
- **背景**：P2-04 删除未使用变量；P2-05 envelope-deadline observation-only 记录；P2-06 recovery 保留原始 reason + `|RECOVERY_EVIDENCE:`；状态/held 语义不变（`P2_FIX_REPORT.md` §2–§4）。
- **建议**：接受修复，但以独立复测（定向 2/3 项测试 + 语义不变检查）为准。
- **维护者决策（留空）**：☐ 接受　☐ 接受但要求补测：______　☐ 其它：______　签名/日期：__________

### D-05 P2-01 / P2-02 / P2-07 残余
- **背景**：P2-01（sidecar/tree）、P2-02（矩阵 F2-07 路径）、P2-07（`env/zero-key.json` 1/4 reasons）均未在 v2 中消除内容问题（v2 只保证完整性自洽）。
- **建议**：P2-01 由“接受 v1+ERRATA”或“采用 v2”二选一；P2-02/P2-07 记入下一版 Packet/矩阵修订；不得静默改写冻结字节。
- **维护者决策（留空）**：☐ 接受披露　☐ 要求下一版修正（范围：______）　☐ 其它：______　签名/日期：__________

### D-06 DSH merged registry / E5-P04
- **背景**：DSH `0.2.2-rc.2` 无权威 merged tool registry/schema 导出；只能证明实际 per-dispatch 工具面可观测且受白名单约束（`RISK_DISPOSITION.md` §2）。
- **建议**：G4-H0 可带残余但需人类/ Security Reviewer 签收“UNVERIFIED + per-dispatch 白名单兜底”；**E5-Full/G5 前必须**取得权威导出或明确风险签收。禁止写成 E5-P04 PASS。
- **维护者决策（留空）**：☐ 签收残余＋补偿控制　☐ 要求权威导出　☐ BLOCKED（E5-Full/G5）　签名（含 Security Reviewer）：__________

### D-07 P2-RUN-IDENTITY / P2-USERNS / P2-DISK
- **背景**：`SO_PEERCRED` 仅 UID 非 per-run token；内核允许嵌套 userns；candidate session 无磁盘硬配额（`RISK_DISPOSITION.md` §3）。
- **建议**：H0 附条件接受（依赖 run 目录 0700/文件 0400/0600、synthetic 数据与监控）；真实部署/多租户前 FIX（per-run 身份、seccomp/禁 userns、磁盘配额）。
- **维护者决策（留空）**：☐ 附条件接受　☐ 另立加固工作项（负责人：______）　☐ 其它：______　签名/日期：__________

### D-08 test hooks / 撤销链 / F4 子场景
- **背景**：产品内 test-only crash/delay hooks；F5-R2 撤销文档无独立签名/审计链；F4 candidate-crash + live Controller 组合未验证（`RISK_DISPOSITION.md` §4/§5）。
- **建议**：G4-H1 前移除/隔离 hooks 并补测 F4 子场景；撤销链是否要求签名由人类决定；**任何材料不得承诺 exactly-once**。
- **维护者决策（留空）**：☐ 要求 H1 前完成（范围：______）　☐ 接受残余（不承诺 exactly-once）　☐ 其它：______　签名/日期：__________

### D-09 A-05 目标路由与价格
- **背景**：A2 官方文档研究稿：`deepseek-flash` 等官方字段/价格有页面快照（2026-11-19T17:47:09Z），但**目标路由未批准**、真实 wire/usage/账单未验证；仓库存在两条“目标路由”声明（见 `PROVIDER_CONTRACT_DRAFT.md` §1/§15 D-01）。
- **建议**：G4-H1/G5 前由维护者选定并逐字段确认 provider/model/endpoint/method/path/streaming/rate/价格；研究稿不替代批准。
- **维护者决策（留空）**：☐ 选定路由：______（provider/model/endpoint/价格快照 URL+UTC）　☐ 推迟　签名/日期：__________

### D-10 A-06 受信部署
- **背景**：Runbook/信任边界/签核模板/E5 清单均为 `DESIGN_PENDING_HUMAN`；真实信任根/Key Broker/Egress/Watchdog 未部署。
- **建议**：仅由维护者在独立权限域执行；Agent 不得注入 Key、不得部署、不得打开 LiveGate。
- **维护者决策（留空）**：☐ 批准进入 G4-H1 准备（需另立授权：______）　☐ 保持 BLOCKED　签名/日期：__________

### D-11 G4-H1/H2、G5/G6 与任何 Live
- **当前**：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`。
- **建议**：本轮不授权；需 G4-H-01..06 全部完成 + 人类显式单次 G5 授权（模型/Key/预算/次数/期限），不得用本文件或任何 Agent Markdown 代替。
- **维护者决策（留空）**：☐ 维持 BLOCKED　☐ 另立 G4-H1 授权（编号：______）　签名/日期：__________

### D-12 状态常量
- **建议**：保持冻结值不变，直到人类对上述事项作出决定并在正式文件（Reviewer 的 `HUMAN_DECISIONS.md` / 维护者签核文件）中记录。
- **维护者决策（留空）**：☐ 维持不变　☐ 其它：______　签名/日期：__________

## 2. 签名区（留空，禁止 Agent 填写）

```text
Maintainer:                       ____________________
Independent Security Reviewer:    ____________________
Date (UTC):                       ____________________
Reviewed base / impl SHA:         ____________________
Accepted scope:                   ____________________
Conditions / expiry:              ____________________
Signature / approval ref:         ____________________
G5 authorization:                 NOT ISSUED
```

> 在维护者真实签署前，以上全部保持 `PENDING_HUMAN_ACTION`。本文件不是授权，不改变任何门状态，不替代 Reviewer 的 `HUMAN_DECISIONS.md`。
