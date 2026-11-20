# G4-R Packet Summary（一页，Integration → Review/Packet 输入）

- **base**：`3e7afee077845a071cd364e93ab209cac20b2d5f`
- **冻结 impl**：`d33e0aabd1714a486325b745c436cb59855d6539`（集成分支 `work/g4r`；本轮 Integration 提交在其上仅加 docs/矩阵）
- **最终 Stage**：`stage-20261120T165407Z` — manifest `cc7ccb61…`、stage tree `933f2c07…`、trusted `f10053d4…`、candidate `131ab68e…`、base=`d33e0aa`、trusted 60 / candidate 6549、loaded src 52/52 == git blobs；旧 Stage `82e10c6f…` 仅 HISTORICAL
- **环境**：rootfs `25491e45…`（清理后复验；漂移链路已记录，不称全程 NO_DRIFT）、deps `e07729d7…`、DSH runtime `1cc41d5a…`（0.2.2-rc.2）、adapter JS `2cb42461…`、Node v22.23.2
- **状态常量**：`G4-H=NOT_AUTHORIZED` / `G5=BLOCKED` / `G6=NOT_RUN` / `LiveGate=BLOCKED` / `M0=DECISION_PENDING` / `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`

## Done（本轮交付）
A0–A4 / R1–R5 联合收口：P2-03 原子消费、P2-05 lifecycle/dispatch 分离、P2-06 first-cause 保留、P2-04 lint、R4 builder/verifier + 矩阵/errata、R3 registry feasibility（`API_AVAILABLE`，B03/E5-P04 仍 UNVERIFIED）、R0 基线、最终 Stage 重建、联合回归 + 关键 L2 + 终稿矩阵 + 本文档集。

## Evidence（关键计数，全部实际运行）
- **Host full 单进程**：1420 collected / **1412 passed / 5 failed / 3 skipped** / 510.8s；5 个失败逐 nodeid 分类 = 1 stale-baseline ENV + 1 flaky-order + 3 drift-window/config-mode ENV（清理/修复后复核通过）→ **0 REAL_REGRESSION**。Delta 前 `5bf9b8b` collection error（support.py 名称遮蔽）= REAL_REGRESSION(test-only)，已在 `d33e0aa` 修复。
- **受影响最小集**：g4r_packet+g4_f2 **42 passed**；R1 **26 passed** + 独立探针 **PASS 50/50**；R2 **19 passed**；A12 **30/30**。
- **OCI filtered（rootfs 副本）**：**1081 tests / 1052 passed / 1 failed / 28 skipped / 69 deselected / 80.4s**；legacy 43 deselect 不变 + 显式 `--deselect=tests/integration/g4r_auth`（26 tests，ENVIRONMENT_ONLY uid-owner harness）；1 failed = target-profile ENVIRONMENT_ONLY；冻结 rootfs 前后 `25491e45…`。
- **Node TAP**：adapter 9/9 + guard 19/19 + skill 8/8 = **36/36**。
- **Ruff**：变更范围 All checks passed；repo-wide 5 个既有错误（旧 scripts，非本 PR）。
- **Scanner**：self-test PASS；全历史 503 files/1070 blobs/208 commits **findings=0**；no-history 0；positive-control 检出伪造 `sk-`（exit 1，masked）。
- **LiveGate/四入口**：inspect BLOCKED、require_live SECURITY_BLOCKED、run_live exit3、CLI --live exit3、Adapter 4/4 SECURITY_BLOCKED、strace 0 网络。
- **独占窗口 L2（17:05:50–17:08:20Z，逐条串行 + canonical 快照）**：F2 **ok=true**（Echo dispatch=1、Tool two rounds dispatch=2、consistency 全 true、0 real model/HTTP/key）；F5 **3/3 true**；T0/T1 rootfs=`25491e45`、deps/stage 身份不变、podman 前后空。
- **矩阵终稿**：`docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv` → 65 cases：**PASS 29 / PARTIAL 14 / NOT_RUN 12 / UNVERIFIED 4 / BLOCKED 6**（sha256 见报告消息）。
- **结构化证据**：`artifacts/g4r/integration/{integration-env.json,integration-stage.json}`、`artifacts/g4r/integration-regressions/{host,oci,node,ruff,scanner,livegate}.json`、`artifacts/g4r/integration/l2/{f2,f5}`、`artifacts/g4r/logs/`。

## Blocked / UNVERIFIED（不得写成 PASS）
- `R5-01..03`（F4-06 candidate crash + live Controller）**UNVERIFIED**（无可控注入；不虚构）。
- `B03/E5-P04` **UNVERIFIED**（R3 证据上限 L1；REV/RG-12 未做）；RG-05/09/10/12 NOT_RUN。
- `REV-01..08` NOT_RUN（Reviewer 未开始）。
- 真实 Key/Provider/TLS/账单/额度、人类信任根、Key Broker/Egress/Watchdog：全部 BLOCKED/HUMAN_REQUIRED。
- 环境非全程 NO_DRIFT：16:52–16:53Z、16:55–16:59Z 漂移窗口与清理恢复记录见 `integration-env.json`；最终 Packet 必须引用独占窗口/清理后的身份。

## Next
1. F-C 用本报告 A–E 输入构建**最终 Packet v2**（Stage=`stage-20261120T165407Z`、计数、deselect 差异、环境漂移链）。
2. Independent Reviewer 从 `d33e0aa` 独立复跑（host/OCI/Node/stress/L2/Packet mutation/registry 等级），给 `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` 或 `PARTIAL/FAIL/BLOCKED`。
3. 维护者按 `M0_G4R_HUMAN_HANDOFF.md` 决策；STOP，不进入 G4-H/G5/G6/Live。

## Human Decision
- 接受 G4-R 裁定与最终 Packet v2；签收 P2-03/04/05/06 修复（需独立复测）。
- B03/E5-P04 残余：签收“UNVERIFIED + per-dispatch 白名单补偿控制”或要求权威导出。
- 签收环境漂移事件记录、OCI deselect 差异（43→69）、历史 junit 恢复事件。
- G4-H-01..06 / G5：**NOT AUTHORIZED / NOT ISSUED**；任何真实 Key/Provider/Live 需新的显式人类授权。

> **Agent 不代签/不写 PASS**；本页不是授权，不改变任何状态常量；Reviewer 裁定后 STOP 等维护者。
