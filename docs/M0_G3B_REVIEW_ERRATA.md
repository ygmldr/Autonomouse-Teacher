# M0 G3-B Review Errata（append-only）

> 状态：**独立 Review 归档后的追加勘误**。本文件不重写、不替换冻结的 Packet、33 行矩阵、Implementation Report 或 Review Request；它只记录独立 Reviewer 结论、对已有 PASS/证据措辞的受限读法，以及待维护者决定项。
> 写入时间：2026-11-16 UTC。本文是 append-only 记录，不是新的实现/证据提交，**不是 Live/GO 授权**。

## 1. Reviewer 身份与冻结输入

- Reviewer：独立 G3-B Reviewer（未参与 B1/B2/B3/B4 实现）；完整报告见 `docs/REVIEW_G3B_INDEPENDENT.md`。
- Review 文档 sha256：**`3b6635be39f2c1014425480dba2e413d7b0accf72841e44634c99647328e5ec8`**（749 行，原字节归档）。
- Implementation：`90402929c710a046e23dd3a3c3dd108b641bc981`（父 `6b1e6b6110e9a366de9fbb358bede28bb6adc24e`）。
- Base：`08768165db55351e42364dadf69657d7a2db4a4c`。
- Docs：`b4a2d774d97242974fcadd21166292dd3b988339`。
- Packet：`artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/`（Reviewer 记录 708 files = 706 hash lines + `hashes.sha256` + `packet-integrity-report.txt`）。
- Reviewer 独立证据根：`artifacts/reviewer-g3b/`；运行索引：`artifacts/reviewer-g3b/RUN_INDEX.md`（artifacts 已 gitignore，未提交）。

## 2. Reviewer Verdict

**`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`**（功能集成范围），**仅与 `OS_TRUST_BOUNDARY=B0-02=BLOCKED` 同时成立**。

- **P0：none found**。Reviewer 未发现在已执行路径上的未授权 Fake 发送、同一 Claim 重复发送、丢失保守账本、Route/Tool 绑定绕过或 false success finish。
- Reviewer 独立复现了核心功能：真实 DSH echo、真实 DSH tool 两轮、新进程 session resume、两个真实 Controller 竞争同一 call、crash-after-`ATTEMPT_STARTED` 无重发、missing usage/EOF/invalid chunk/cancel 的保守处理、SQLite/receipt 交叉核对。
- 该 verdict **不**升级任何残余：B1-04 cancel 仍 PARTIAL、B2-05 request-digest replay 仍 PARTIAL、B3-10/B3-11 仍 UNVERIFIED、Skill 0.2.2 native harness 仍 BLOCKED、B0-02 仍 BLOCKED。
- Reviewer 同时记录 P1/P2 缺陷（见 §3/§4）；P1-1/P1-2 需要在 G3-C/G3-D 前修复或由维护者明确接受，但不构成其任务定义下的 P0 FAIL。

## 3. P1 Finding 索引

### P1-1 — B3-08 是保守 `WORST_CASE_HELD`，不是持久 receipt 的幂等 settle

- 证据：packet 内 `traces/b3-07-crash-after_response_before_settlement/reconcile-result.json`：before `RESPONSE_OBSERVED`，after `WORST_CASE_HELD`；reservation `FAILED`，cost 为保守上界，counter 1，**无重发**。
- 原因：`mark_response_observed` 只持久 receipt metadata，journal `receipt_json` 不含 usage；`reconcile_on_startup` 因此选择 `fail`/worst-case 而非 `settle`。
- 影响：保守、无低估、无重复发送；但矩阵 B3-08 的 `PASS` 与报告中的“idempotent settle”措辞强于实际观察。
- **受限读法**：B3-08 的 PASS 应读作“持久 receipt + 保守 `WORST_CASE_HELD`、无重发”，不得据此声称已实现/验证幂等 settle。
- 维护者选项：在 receipt journal 中持久 usage 并在 reconcile 时 settlement，或将 B3-08 状态/措辞改为 conservative hold/PARTIAL；历史字节不改，由本 errata 补充读法。

### P1-2 — cancel 路径签名不匹配，cancel 为 no-op；B1-04 维持 PARTIAL

- `ipc_server.py:284-289` 以 kwargs 调用 `controller.cancel(transport_id=..., reason=...)`，而 `controller.py:187` 定义 `cancel(self)` 无参数；`TypeError` 被吞；`self._cancel` 设置后未在 `_handle_payload` 检查。
- Reviewer 探针：ack 后发 cancel，Fake 仍收到一次请求，attempt 结束 `SETTLEMENT_UNCERTAIN`、reservation `PENDING`、无 success finish；属 fail-closed，但不是 cancel 传播。
- **状态维持**：B1-04 PARTIAL；B3-10/B3-11 仍 UNVERIFIED。不得声称 cancel PASS。
- 维护者选项：实现兼容 cancel 契约（发送前停止/发送后标 uncertain、绝不声称免费），或明确接受 B1-04/B3-10 的残余。

## 4. P2 Finding 索引

| ID | 摘要 | 对矩阵/结论影响 |
|---|---|---|
| P2-1 | Broker `CALL_ID_CONFLICT`/`IDEMPOTENCY_CONFLICT` 不在 IPC `ERROR_CODES`，经 `validate_error_payload` 变成 `UNKNOWN_FIELD`；Reviewer 未复现 Owner B3-05 写的 `CLAIM_DENIED`。 | B3-05 的 **at-most-one-send 性质不受影响**（仍只一个 Fake/claim/attempt）；但“精确 `CLAIM_DENIED` 错误码”不可作为已验证结论，B3-05 读作“一个成功、另一路确定拒绝（实际码可能 `UNKNOWN_FIELD`）”。 |
| P2-2 | `finish` error payload 缺 `failure{message,code}`，被校验器拒绝并成 `UNKNOWN_FIELD`（no_usage/partial_usage/eof）。 | DSH 仍 error/no success，账本保守；错误帧 schema 是缺陷，不升级成功路径。 |
| P2-3 | `max_calls` 在 `_prepare` 前递增，无效请求可消耗 admission 调用额度。 | 无 Fake 发送；DoS/加固问题，不是预算低估。 |
| P2-4 | `budget_provider_observations` 表在 packet/Reviewer 运行中为空；Observation 证据主要是 attempt `receipt_json` digest。 | O-3 映射/settle 保守，未观察到低估；缺独立 observation 行，需文档化接受或补持久化。 |
| P2-5 | B3-07 trace `reconcile-result.json` 是第二次 reconcile（SETTLED→SETTLED），首次 `ATTEMPT_STARTED→SETTLED` 在 logs；trace 单独看会误导。 | 证据可追溯性缺陷；不改变状态，建议保留两次结果/命名。 |
| P2-6 | `run/concurrency.py` 直接运行有 socket startup 超时抖动；debug wrapper/独立 sequential-start probe 通过。 | 不产生额外 Fake 发送；B3-05 精确命令可复现性下降，建议修启动/barrier。 |
| P2-7 | 重启时 `register_admission` 先于 reconcile；复用旧 admission id 会先 `ADMISSION_REPLAYED`，需 fresh admission 才能 reconcile。 | 恢复需新 admission 是 launcher/recovery contract；应在文档中显式化，不改变当前 PASS 证据。 |
| P2-8 | Reviewer 首次 R4 脚本曾触碰 packet 的 ephemeral SQLite `-shm` 文件；已恢复，最终 706/706 hashes 通过；不是 Owner 实现问题。 | 透明披露；不改变 Packet 冻结或 Owner 结论。 |

## 5. 33 行矩阵的受限读法（不修改冻结字节）

`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv` 保持原字节；以下仅是**审阅读法**，不是对历史矩阵的改写：

- **B3-08 `PASS`**：读作“持久 receipt + 保守 `WORST_CASE_HELD`、无重发”；不应读作“已实现 receipt 幂等 settle”（P1-1）。
- **B3-05 `PASS`**：at-most-one-send 成立；但 error code 精确值未证实，可能为 `UNKNOWN_FIELD` 而非 `CLAIM_DENIED`（P2-1）。因此报告/复核不得把 `CLAIM_DENIED` 当作已复现。
- **B1-04 `PARTIAL`**：cancel 实际 no-op（P1-2），不升级。
- **B2-05 `PARTIAL`**：request-digest replay 未完整执行；Reviewer 只做了 same-call sequential replay，且得到 `UNKNOWN_FIELD`，不升级。
- **B3-10 / B3-11 `UNVERIFIED`**：进程树/背压/资源边界未独立测试，维持。
- **B0-02 `BLOCKED`**：同 uid 的候选可读写 Broker DB/policy、可在无 Controller/durable attempt 时获 Broker claim；只有外部网络被容器阻断，不构成 OS 边界 PASS。
- 其余 PASS 项按 Reviewer R0–R5 的独立复跑和 Packet 冻结字节读取；P1/P2 不改变 P0 结论，但不能被忽略。

## 6. OS Trust Boundary / Non-goals

- **OS Trust Boundary = B0-02 = BLOCKED**；禁止 `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`。
- 无 Live、无 GO、无真实 Key/Provider HTTP；Fake usage 不是真实账单；本地 Claim 不是远端 exactly-once。
- 恢复真实 OS 边界需要不同 OS principal/namespace、实际权限拒绝；属 G3-D/G4，不是本轮。

## 7. Packet 冻结确认

- Packet 未被本任务修改：`artifacts/review-packet-g3b-90402929c710a046e23dd3a3c3dd108b641bc981/`。
- `manifest.docs_sha` 仍为 **`b4a2d774d97242974fcadd21166292dd3b988339`**；Reviewer 已记录 706/706 hashes、packet 708 files；本 errata 不重建/不重签 Packet。
- Review 文档 `docs/REVIEW_G3B_INDEPENDENT.md` 原字节归档，sha256 见 §1；Reviewer 证据根见 §1；本 errata 属于冻结后的 append-only 补充，不改变任何历史字节。

## 8. 待维护者决定（G3-C/G3-D 前）

1. 是否在下一 Gate 前修复 P1-1（B3-08 语义/receipt usage 持久化）与 P1-2（cancel 契约）；若接受残余，需书面记录。
2. 是否修复 P2-1（Broker conflict 错误码映射）与 P2-2（finish-error payload schema）；这两项影响确定性错误码/证据质量，不影响已观察到的 P0 性质。
3. 是否为 P2-3（max_calls 配额）、P2-4（observation 表）、P2-5（trace 命名）、P2-6（并发启动抖动）、P2-7（recovery admission contract）安排后续修复或明示接受。
4. 是否接受 `PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE` 与上述 P1/P2/UNVERIFIED/BLOCKED 并存的最终措辞；不得转成 `PASS_FOR_G3B_TRUST_BOUNDARY_SCOPE`、Live 或 GO。
5. 是否将 Reviewer 证据根 `artifacts/reviewer-g3b/` 作为只读归档保留（当前 gitignored，不提交）；Packet 保持冻结。

## 9. 引用

- `docs/REVIEW_G3B_INDEPENDENT.md`（sha256 `3b6635be…`；§0 Verdict、§7 Findings、§8 Residual、§9 Recommendation）。
- `artifacts/reviewer-g3b/RUN_INDEX.md`（Reviewer run UTC/exit/evidence 索引）。
- `artifacts/reviewer-g3b/packet-restore-incident.txt`（P2-8 透明披露）。
- `docs/M0_G3B_IMPLEMENTATION_REPORT.md`、`docs/M0_G3B_REVIEW_REQUEST.md`、`docs/Autonomous_Teacher_M0_G3B_Review_Evidence_Matrix_v1.0.csv`（冻结历史字节；本 errata 不重写）。
