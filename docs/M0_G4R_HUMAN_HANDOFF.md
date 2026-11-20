# M0 G4-R — Human Handoff（维护者决策，全部未签核）

- **文档 ID**：`M0-G4R-HUMAN-HANDOFF-v1`
- **冻结 impl**：`d33e0aabd1714a486325b745c436cb59855d6539`；base `3e7afee…`
- **性质**：待人类决策清单。**全部为 `PENDING_HUMAN_ACTION` / `BLOCKED`**；本文件不写 APPROVED，不构成任何授权。
- **当前状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`

## 1. 待维护者决策表

| # | 决策 | 当前状态 | 需要人类做的动作 | 阻塞对象 |
|---|---|---|---|---|
| D-01 | G4-R 裁定与范围 | 待 Independent Reviewer | 接受 Reviewer 的 `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`/`PARTIAL`/`FAIL`/`BLOCKED`（限定无 Key 范围） | G4-R 收口、后续门 |
| D-02 | 最终 Packet v2 是否采用 | F-C 待用本报告 Stage/计数构建 | 复核/接受 v2；v1 保持不可变只读；拒绝静默扩 deselect/未哈希文件 | 证据归档 |
| D-03 | P2-03/04/05/06 修复签收 | Owner 证据 + Reviewer 待复测 | 以 Reviewer 独立复测为准签收；未复测前不得写入“已完全关闭” | G4-H 前加固 |
| D-04 | B03 / E5-P04 Registry 残余 | `UNVERIFIED`（R3 `API_AVAILABLE`，L1 信任边界） | 在 E5-Full/G5 前明确签收“UNVERIFIED + per-dispatch 白名单补偿控制”，或要求 DSH 权威导出/更强可信通道 | E5-Full、G5 |
| D-05 | P2-RUN-IDENTITY / P2-USERNS / P2-DISK | 未签收 | 签收现状（附条件）或另立 per-run 身份/隔离/磁盘配额工作项 | G4-H-05/真实部署 |
| D-06 | F4-R1 / F5-R6 / F1-R4 / F2-R5 / B07 | 维持原残余 | 决定是否补测/接受；禁止把“语义证据”写成字节级/穷举证明 | G4-H、生产 |
| D-07 | R5-01..03（F4-06 candidate crash + live Controller） | **UNVERIFIED**（无可控注入） | 决定是否投入可控 Candidate crash 注入补测；接受则登记“不承诺全部恢复语义” | G4-H |
| D-08 | 环境漂移/清理事件 | 已恢复 `25491e45…` 并记录 | 确认收到漂移窗口（16:52–16:59Z）、清理恢复、Stage fail-closed、`cp -a` rootfs 副本政策；不得对外宣称全程 NO_DRIFT | 证据可信度 |
| D-09 | OCI deselect 差异 | legacy 43 未扩大 + 26 explicit `tests/integration/g4r_auth`（环境类） | 签收新增 deselect 的原因/列表/总数（43→69）与逐项失败分类；禁止静默扩 deselect | OCI 口径 |
| D-10 | 历史证据 junit 误覆盖事件 | 已从冻结 Packet 原字节恢复（sha `7f25ba83…`） | 知悉/接受该事件与恢复记录（gitignored 证据，非 Packet/Reviewer 报告） | 证据卫生 |
| D-11 | G4-H-01..06 人工项 | 全部 `PENDING_HUMAN_ACTION` | 独立二次审阅、人类信任根、Key Broker/Egress、官方价格/Usage、E5-Full Review、单次 G5 授权 | G4-H、G5 |
| D-12 | G5 bounded real request | `BLOCKED` | 新的显式人类单次授权（模型/Key/预算/次数/期限）+ E5-Full | G5、Live |
| D-13 | 其它真正的开放风险 | — | `P2-DISK/USERNS/RUN-IDENTITY`、test-only hooks、撤销链签名、F4 字节级 context 等见 `M0_G4R_FINDINGS_AND_DISPOSITION.md` §4 | 各门 |

## 2. 不得由 Agent 代替的决定

1. 是否把 G4-R 结果作为进入 G4-H/H1 的依据；
2. 是否接受 B03/E5-P04 残余（以及是否要求 Runtime 可信通道/导出）；
3. 是否授权任何真实 Key/Provider/网络/计费（G5 单次）；
4. 是否部署/轮换人类信任根、Key Broker、Egress、Watchdog；
5. 任何 P2 残余的 ACCEPT。

## 3. Agent 侧已完成（供审阅）

- 冻结 impl `d33e0aa` 上完成联合回归：Host 单进程 1420/1412/5/3（失败逐 nodeid 分类，0 REAL_REGRESSION）；最小受影响集 42/26+R1 probe/19/A12-30；OCI filtered（rootfs 副本）1081/1052/1/28/69 leg+new deselect；Node 36/36；Ruff/Scanner/LiveGate/strace 见报告。
- 最终 Stage（base=`d33e0aa`）重建并记录 manifest/tree/loaded source；旧 Stage 仅 HISTORICAL。
- 关键 L2（独占窗口）：F2 `ok=true`（Echo 1、Tool 2）；F5 3/3 true；前后 canonical 一致；冻结 rootfs 未被 OCI 污染（`cp -a` 副本运行）。
- 证据根：`artifacts/g4r/integration/`、`artifacts/g4r/integration-regressions/`、`artifacts/g4r/logs/`。

## 4. 交接签署区（留空，禁止 Agent 填写）

```text
Reviewer / Maintainer:                  ____________________
Independent Security Reviewer:          ____________________
Date (UTC):                             ____________________
Reviewed frozen SHA / Stage:            ____________________
Verdict (PASS / PARTIAL / FAIL / BLOCKED): ____________________
P2 accepted (Y/N/conditions):           ____________________
B03/E5-P04 residual decision:           ____________________
OCO/deslect decision (D-09):            ____________________
G4-H authorization:                     NOT ISSUED
G5 authorization:                       NOT ISSUED
Signature / approval ref:               ____________________
```

> 在真实签署发生前，以上全部 `PENDING_HUMAN_ACTION`。本文件不是授权、不是批准、不是 Live 许可；**STOP，等待维护者决策。**
