# M0 G4-F — Human Handoff（待人工决策项）

- **用途**：把只能由维护者/人类完成的事项集中列出，避免把工程证据误读为部署授权。
- **状态**：**全部为 `PENDING_HUMAN_ACTION` / `BLOCKED`；本文件不写 `APPROVED`，
  不构成任何授权。**
- **当前门状态**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
  `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

---

## 1. 必须由人类完成的事项

| # | 事项 | 当前状态 | 需要的动作 | 阻塞对象 |
|---|---|---|---|---|
| H-01 | 真实 Provider Key / 凭据注入 / 账户额度 | 未部署、未读取 | 在受控环境注入并做最小真实探测；不得进入仓库/证据 | E5 Full、Live |
| H-02 | 真实 Provider 价格 / Usage / 限流 / 账单对账 | 未验证（synthetic 费率） | 维护者提供权威价格快照与对账流程 | E5-P01/P05 Full、计费可信 |
| H-03 | 人类 Ed25519 信任根 / 私钥托管 / 轮换与撤销 SOP | 未部署 | 签署并部署信任根；提供撤销链 | G4-H-01/02、Live |
| H-04 | E5-PreLive Full 的人工作业与签收 | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 按 E5 计划逐项执行、签收 | E5 Full、M0 |
| H-05 | `P2-RUN-IDENTITY`：同 UID 场景的 per-run 身份 | 维护者待决 | 签收现状或加 per-run capability/UID | G4-H |
| H-06 | `P2-USERNS` / `P2-DISK` 策略 | 维护者待决 | 签收或给出限额/隔离要求 | G4-H |
| H-07 | 产品内 test-only crash/delay hooks（`G3B_TEST_MODE` 等） | 仍存在，仅可信 env 可触发 | 评估是否在 G4-H 前移除或改测试构建 | G4-H |
| H-08 | 撤销文档签名链 | 无签名，root-owned 输入 | 决定是否要求签名/审计链 | F5-R2 |
| H-09 | F4 candidate-crash + live Controller 子场景 | `UNVERIFIED` | 决定是否在 G4-H/G5 前补测 | F4-R2 |
| H-10 | B03 merged registry / E5-P04 | `UNVERIFIED` | DSH 提供权威导出，或人类明确接受残余 | B03/E5-P04 |
| H-11 | 独立复核 | 未指派（`reviewer=NOT_ASSIGNED`） | 指派未参与实现的 Reviewer，按 `M0_G4F_REVIEW_REQUEST.md` 执行 | G4-F 收口裁定 |
| H-12 | 历史 Packet 的 reviewer 字段 | 旧 Packet `PENDING` | 归档时人工记录复核结论，不改冻结 Packet | 归档 |

---

## 2. 明确不可由 Agent 代替的决定

1. 是否把 `PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE` 作为进入下一阶段的依据；
2. 是否授权 G4-H / G5 / G6；
3. 是否允许任何真实 Key、真实 Provider 请求、真实计费；
4. 是否接受 F4/F5/B03/E5-P04 的残余风险；
5. 是否部署或轮换人类信任根、撤销链与凭据。

---

## 3. 交接检查（Agent 侧已完成）

- 最终 HEAD 联合重跑：F4/F2/F3/F5 全 PASS（详 `M0_G4F_IMPLEMENTATION_REPORT.md` §3）。
- 全量回归、OCI、Node、Ruff、scanner、LiveGate 负例：计数与归因见实现报告 §6/§6.6。
- 矩阵：46 行（38 PASS / 2 UNVERIFIED / 5 NOT_RUN / 1 BLOCKED）。
- Review Packet：`artifacts/review-packet-g4f-e7d92967ec0e/`（自校验 100%）。
- 终态：`podman ps -a` 空；rootfs/deps canonical；0 Key / 0 模型 / 0 外网 / 0 Live。

**STOP。等待人类决策与独立复核。**
