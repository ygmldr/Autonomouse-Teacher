# M0 G0 — Lead 裁定记录（Gate / P0-P1 / G1-G2 范围）

- 任务：`task-59`（G0 文档归档）；日期：2026-11-15 UTC
- 前置：G0 baseline/source inventory 已通过 Lead 审计；基线与阻塞项见
  [`M0_G0_BASELINE.md`](M0_G0_BASELINE.md)（`0923d002…`）与 [`OPEN_BLOCKERS.md`](OPEN_BLOCKERS.md)（`0002beb1…`）。
- 当前 HEAD：`abbc6bcd2a2128456627d9370465323b505aafd9`（v0.6 手册 docs commit）；
  **实现 SHA 仍为** `87f44e1227f38e454c4dc418b0e289df85721fb5`，两者必须分开引用，不得把 docs SHA 当测试基线。
- 本文件记录 Lead/维护者裁定，不含凭据；不构成 Live/真实 Key 授权。

## 1. G0 接受与门禁状态

1. G0 baseline/source inventory **接受**：实现 SHA `87f44e1`、历史 PR0–PR4 冻结链与 G0 映射作为后续 G1/G2 的基线；不重算/不改写历史证据。
2. 允许启动 **G1/G2** 的离线实现与独立审阅；**G3+ 未授权**，不得在 G1/G2 内提前实施/以文档代替。
3. **Live、真实 Key、真实模型、真实外部网络仍 BLOCKED**；LiveGate/P03 不因本裁定改变，总体仍 **DECISION PENDING**，不签发 GO。
4. G1 完成必须经独立审阅后才算关闭；G2 完成后再停止，进入下一轮人工裁定。

## 2. P0/P1 调整

- **P0（首批 10 项）** = 原 9 项 + 将 **AUTH-06（A3）升为 P0**：
  - 原 9 项（见 OPEN_BLOCKERS P0 行）：AUTH-02(A1)、AUTH-05(A2)、OBS-03(A6)、OBS-05/06+INT-15(A7)、WD-03/04(A8)、UNIFIED-ID(A9)、CLAIM(A10)、RESERVATION-VALIDATION、PERSISTENT-ATTEMPTS；以及 G1/G2 交叉项按 OPEN_BLOCKERS 标注执行。
  - **AUTH-06（A3）升 P0**：trusted authorization 路径异常时 `approver` 未初始化，可能触发 `UnboundLocalError`；必须显式 fail-closed（返回 `approved=False`/安全拒绝），不得崩溃/未定义变量进入对象；补 AUTH-06 定向负测。
- **P1（3 项）= A4、A5、A13**（按 OPEN_BLOCKERS/G0 baseline 的 A 编号定义）；在 P0 修复后处理，仍须定向测试与独立复核。
- 任何新增/降级 P0/P1 必须由 Lead/维护者显式裁定并记录，不由实现者自行调整。

## 3. A6（OBS-03）test-first

A6 按 **test-first** 处理，不得先写 PASS：

1. 先写能**证伪**“PARTIAL/MISSING 不得低于保守上界（worst-case bound）”的定向测试，覆盖残余路径（如 complete input + missing output + actual/provider_invoice 等）；
2. 测试失败后，再依据 route billing policy 语义决定是否需要 policy/代码修正；
3. 只有定向测试+独立复跑通过，才能把 OBS-03 标为关闭；不得用“静态未复现”直接写 PASS，不得把未知/缺失 usage 当 0。

## 4. G1 / G2 范围

| Gate | 范围 | 不包含 |
|---|---|---|
| **G1** | A1/A2/A3/A4/A5/A6/A7/A8（security/authorization/observation/watchdog；含 P0 修复、P1 A4/A5/A13 中属 G1 的项、A6 test-first） | A9–A11（G2）；G3+；Live/真实 Key/网络 |
| **G2** | A9/A10/A11 + **broker 原子 claim** + 真实 SQLite/stdio Broker/FakeProvider 闭环 + ADR-002（统一 CallIdentity/全链 ID） | G1 范围重做；G3+/G4；真实 provider/Live |
| **G3+** | **未授权** | 不得在 G1/G2 内以插件/文档替代外部 egress/Key/人类边界 |

## 5. 禁止事项与边界

1. 不重做 PR0–PR4；不改写任何历史证据/冻结 manifest/旧 commit 字节；不 amend 历史。
2. 不读取/使用 OpenCode Go 凭据（`OPENCODE_API_KEY` 等），不触发任何真实 Key/模型/HTTP；OpenCode Go 仍仅 INTERNAL-TEST-ONLY，US$10 硬上限/≤50 次/维护者最终批准，smoke 未获授权。
3. 不启动 Live、真实网络、真实 provider；G1/G2 只在固定 digest 无 Key 禁网隔离 OCI 内执行项目代码/测试。
4. 不修改生产 Gate/Adapter/primary route 以解锁 Live；G1/G2 的代码修改须最小、定向测试、可复验。
5. G1 完成必须独立审阅；G2 完成后再停止；G3+ 需 Lead/维护者另行授权。

## 6. 参考

- G0 基线：[`M0_G0_BASELINE.md`](M0_G0_BASELINE.md)（`0923d0023ce056f74cea1bfc7b831c6ebb283fe554600a477f74009e5fb72390`）
- 阻塞项：[`OPEN_BLOCKERS.md`](OPEN_BLOCKERS.md)（`0002beb1258025756d36a2aee7cc6f6450faab1ca8af8a7701b6652875a4fad3`）
- G0 证据：`artifacts/g0-baseline/manifest.json`（gitignored，evidence 2/2 OK；不提交）
- 历史裁定：[`M0_CLOSEOUT_DECISIONS.md`](M0_CLOSEOUT_DECISIONS.md)；收口报告：[`M0_CLOSEOUT_REPORT.md`](M0_CLOSEOUT_REPORT.md)
