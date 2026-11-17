# M0 G3-C 独立复核 v1 归档与 PR1 Errata

> **性质**：append-only 处置记录（不修改 v1 报告文字/字节）。本文件只追加：v1 复核的归档事实、P1 索引、PR1 修复映射、证据的受限读法、未变事项，以及留给二次复核的待验证项。
> **不是** PASS、不是 G3-D/Live/G4/G5/M0 GO 授权；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 与 16 个 D 行 `NOT_RUN` 继续成立。
> **冻结身份（v1 复核）**：Base `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`；G0 `e107e22d32ee0fd25c597a95ae447898f4a52a85`；Implementation `e6fde1cdf0bec9e957e98d569b257c8f17dfa363`；docs HEAD `78be77c3c63fce62527dccd7ec8c1458047d81bf`。
> **PR1 修复身份**：Implementation `b2f6af054555705192c4e1ae3019a68078764736`（父 `78be77c`）；docs 主体 `9ffa0b11c1a32cd023e0192e4763565f4f7de946`（父 `b2f6af0`），其后 `bea0fc3e2d6262161e4557fbf11ff5bc157db54e` 为交叉引用修正；本文件与 v1 报告原字节由最终 docs 归档 commit 一并提交，Packet v2 `manifest.json.docs_sha` 记录该 commit。
> **v1 报告原字节**：`docs/REVIEW_G3C_INDEPENDENT.md`，339 行，sha256 `4744c61f1561c6f92634b29ef9a6a0f7ca82c4627aef31ba3d0163e4886d23b1`；归档前后必须一致，本 errata 不改变其任何字节。

---

## 1. v1 Reviewer 身份、输入与裁定

| 项 | v1 事实 |
|---|---|
| Reviewer | 独立 G3-C Reviewer；未参与 G3-C 实现/证据生成，未复用 Owner 测试模块或结论句 |
| 独立证据根 | `artifacts/reviewer-g3c/`（Git 忽略目录；共 748 个文件，13 MB） |
| 运行索引 | `artifacts/reviewer-g3c/RUN_INDEX.md`；报告 SHA 记录为该文件末尾的 `4744c61f…` |
| 输入 Packet | `artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/`（v1，冻结；`sha256sum -c` 1713/1713 OK，1715 files） |
| 输入 docs | docs commit `78be77c`：Implementation Report / Review Request / Findings / 69 行矩阵 |
| v1 复核范围 | C1 协议/错误语义/Admission；C2 Usage/Receipt/Observation/Recovery；C3 Cancel/Deadline/IPC 资源/增量 Streaming；无 Key 集成与回归；Packet/矩阵/证据索引 |
| 明确不在范围 | G3-D0/D1/D2/D3（16 行 `NOT_RUN`）；真实 Provider/Key/模型/外网/Live；G4/G5/M0 GO |
| **v1 最终裁定** | **`PARTIAL`**（`docs/REVIEW_G3C_INDEPENDENT.md:259-279`） |
| P0 | **无**（`docs/REVIEW_G3C_INDEPENDENT.md:221-223`） |
| P1 | **3 项**：P1-1、P1-2、P1-3（见 §2） |
| P2 | 10 项记录性残余（`docs/REVIEW_G3C_INDEPENDENT.md:244-258`） |

v1 裁定 `PARTIAL` 的理由不是产品语义失败：Reviewer 在自己的 11 类恶意探针、14 次固定 rootfs 真实 DSH 复跑、15 例 SQLite/Receipt 对账中没有发现 P0；但真实 DSH 覆盖标注、双 Controller 冷启动和矩阵证据索引三项 P1 必须先修正或缩小主张，因此不能签 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`。

**v1 未验证/未主张**（原文 `docs/REVIEW_G3C_INDEPENDENT.md:280-293`）：G3-D 全部 16 行；OS 边界；真实 Key/模型/远端 exactly-once/账单；v1 Reviewer 未复跑 real-DSH replay；未做双进程真实 DSH 同 Claim；host-level 22 行仍是宿主 pytest；G2 280 只核对未独立重跑；SIGTERM 终态不确定、需 reconcile；DSH runtime/插件/内核未完整审计。

---

## 2. P1 索引与证据位置

行号指 v1 报告 `docs/REVIEW_G3C_INDEPENDENT.md` 自身；涉及的 `docs/M0_G3C_IMPLEMENTATION_REPORT.md:83`、`docs/M0_G3C_FINDINGS_AND_DISPOSITION.md:61`、矩阵第 3 行是 **v1 时刻（docs `78be77c`）** 的引用，不是当前 docs 的行号。当前 docs 已被 PR1 修正，读旧行号时必须配合本 errata 与 Packet v1。

### P1-1 真实 DSH 覆盖被高估 / C1-01A 无 DSH 证据

- **v1 位置**：`docs/REVIEW_G3C_INDEPENDENT.md:225-231`。
- **v1 所指声明**：旧 Implementation Report（`78be77c`）第 83 行把 C1-01A 描述为“真实 DSH replay”；旧 Findings 第 61 行把 8 行列入“真实 DSH”。
- **v1 实际证据**：
  - 唯一含 `ATTEMPT_ALREADY_STARTED` 的 Owner 证据是 `artifacts/g3c/traces/probe-replay/probe-result.json`，由 `spikes/g3b-trusted-bridge/run_c3/probes_c3.py --probe replay` 产生；该目录**没有** `dsh-result.json`，即不是 DSH。
  - C1-01A 矩阵行（v1 docs 矩阵第 3 行）的 `command_argv`/`log_path` 为空，`db_or_receipt_path=artifacts/g3c/traces/C1-01A` 不存在；observed 与 C1-04（raw-UDS）相同。
  - 旧 Findings 的“真实 DSH”列表 28 行中有 8 行实际是 summary/no-run（C1-01A）、raw-UDS（C1-04、C3-01B/C、C3-02A/B）、container reconcile（C2-02D/E）。
- **Reviewer 独立证据**：`artifacts/reviewer-g3c/r1-static/matrix-label-audit.txt`；R3 的 14 次 Reviewer 自建真实 DSH 运行见 `artifacts/reviewer-g3c/r3-dsh/commands.jsonl` 与 `artifacts/reviewer-g3c/r3-dsh/traces/reviewer-*/`。
- **性质**：证据标注/覆盖主张缺陷，不是产品语义 P0；raw-UDS replay 语义本身经 Reviewer 探针验证。

### P1-2 两个 Controller 同时冷启动共享 AttemptJournal 会未处理崩溃

- **v1 位置**：`docs/REVIEW_G3C_INDEPENDENT.md:232-237`。
- **v1 所指代码**：`src/autoteacher_m0/bridge/attempts.py:55-61`（v1 impl `e6fde1c`）先 `PRAGMA journal_mode=WAL` 后设 `busy_timeout`；`controller.main` 直接构造 journal，未捕获 `sqlite3.OperationalError`。
- **v1 复现**：6 次同时冷启动中 3 次一个进程在 `AttemptJournal.__init__` 抛 `database is locked` 并 exit 1；存活进程发送 1 个 Fake，counter=1，无第二次发送。安全属性（至多一次 Claim/Fake）保持，但不满足 R2 要求的“第二个进程确定性拒绝”。
- **Reviewer 独立证据**：`artifacts/reviewer-g3c/r2/p2c-startup-lock.log`、`artifacts/reviewer-g3c/r2/summary.json`、`artifacts/reviewer-g3c/r2/p2c-session-identity.log`。
- **性质**：并发启动确定性/受控错误缺陷；不是重复发送，也不是计费错误。

### P1-3 矩阵证据索引 25/53 行不可解析

- **v1 位置**：`docs/REVIEW_G3C_INDEPENDENT.md:238-243`。
- **v1 所指**：53 个 PASS 行中 25 行的 `db_or_receipt_path` 不存在。示例：C1-01A/B/C/D 指向从未存在的 `artifacts/g3c/traces/<case_id>`；C2-04 指向 `artifacts/g3c/evidence/junit-g3c-only.xml`（实际为 `junit-g3c.xml`）；C3-03A..G、C3-04D、C3-01A/E、C3-02D/E、C2-03A..E 也指向 `traces/<case_id>` 占位路径。C1-01A 与 C-END-01 的 `command_argv`/`log_path` 为空。
- **Reviewer 独立证据**：`artifacts/reviewer-g3c/r1-static/matrix-path-audit.txt`（before 25 missing）；审计方法为逐行解析矩阵路径并在冻结 Packet/工作树中检查存在性。
- **性质**：证据索引可追溯性缺陷；实际 log/junit/trace 存在且可复现，但“从矩阵逐行可追溯”不成立。

---

## 3. PR1 修复映射

| v1 P1 | PR1 处置 | 提交/证据 | 本 errata 的限定 |
|---|---|---|---|
| P1-1 真实 DSH 标注 | **docs 修正，不新增 real-DSH replay**：Report §0/§4/§9/§13、Findings §4 证据类型表、矩阵 observed/argv/log/path 逐行更正；8 行改为 raw-UDS/reconcile/summary；C1-01A 明确为 raw-UDS；C-END-01 改为 summary 并链接 echo/tool/resume 子 trace；C2-04 指向真实 `junit-g3c.xml` | `9ffa0b1`（报告/Findings/矩阵）；`bea0fc3`（交叉引用）；证据类型表见 `docs/M0_G3C_FINDINGS_AND_DISPOSITION.md` §4 | **没有**新增“real-DSH replay”运行；P1-1 是“缩小/更正主张”，不是“补齐 real DSH replay”。二次复核应验证标注与路径，不要求 C1-01A 变成 DSH |
| P1-2 双 Controller 冷启动 | **代码修复**：先 `busy_timeout` 后 WAL；可重试锁错误有界重试（默认 10 s / 0.05 s）；per-socket `flock` singleton；受控退出码 `CONTROLLER_SINGLETON_LOCKED=5`、`ATTEMPT_JOURNAL_UNAVAILABLE=4`、`ADMISSION_REPLAYED_AFTER_RECOVERY=3`；新增 20 轮双进程冷启动测试 | `b2f6af0`（3 files, +662/−45）；`tests/integration/g3c/test_c3_05_twocontroller_coldstart.py`；Owner 证据 `artifacts/g3c/evidence/concurrency-coldstart-20261117T153229Z.json`（20/20 singleton、0 traceback、Fake counter=1、Attempt `SETTLED`）与 `artifacts/g3c/logs/coldstart-20261117T153229Z/` | PR1 的 20 轮是 Owner 运行；二次 Reviewer 必须用自己的命令重跑至少 20 轮，核验 exit 5/4/3、无 traceback、Fake=1，不能只引用 Owner JSON |
| P1-3 矩阵 25 条坏路径 | **矩阵修正**：25 个 `db_or_receipt_path` 改为实际 junit/log/trace；补 C1-01A/C-END-01 的 argv/log；C2-04 junit 修正；D 行 16 条原字节未动 | `9ffa0b1` 矩阵；审计 `artifacts/g3c/evidence/matrix-path-audit-pr1.txt`：docs/工作矩阵均 before 25 missing → after 0 missing；D 行 before/after SHA 一致 | 二次 Reviewer 必须独立重跑路径存在性审计，并核对 D 行字节未改；不能只信 Owner 的 `after 0` 结论 |

**P1-1 的 8 行更正**：C1-01A、C1-04、C2-02D、C2-02E、C3-01B、C3-01C、C3-02A、C3-02B 不再列为 real DSH；C1-01A 归为 raw-UDS，C2-02D/E 归为 container reconcile，C1-04/C3-01B/C/C3-02A/B 归为 raw-UDS。矩阵/Findings 的逐 case 证据类型表以 19 real DSH + 1 real DSH summary + 6 raw-UDS + 2 container reconcile + 23 host pytest + 2 G0/regression = 53 PASS 行归档。

**P1-2 的边界**：受控 exit 5 只覆盖“同一 socket 路径的第二个 Controller 冷启动”；不覆盖两个真实 DSH 客户端同 Claim（worker 每进程自带 Controller/admission）。该残余未因 PR1 消失，见 §5。

**P1-3 的边界**：路径存在性修正不等于每个 case 的断言都被二次 Reviewer 复验；二次复核仍需按 R1/R4 对关键 case 做语义核对。

### 3.1 本归档的独立回归实测（供二次复核参照，不是二次裁定）

本归档在 **`b2f6af0` 源码**上重跑了回归（源码 HEAD 为 `b2f6af0`；运行期间 docs 工作区已含最终归档内容，docs HEAD 仍为 `bea0fc3`，随后由最终 docs commit 固化），原始日志写在新文件 `artifacts/g3c/regression/pr1-*.log`（不覆盖旧日志）：

| 项 | 实测 | 说明 |
|---|---|---|
| host full | **773 passed / 2 failed / 1 skipped**（776 collected，exit 1） | 2 失败仍是 §6 的既有宿主环境限制（可写 config、硬编码 `/project`） |
| fixed OCI full | **773 passed / 2 failed / 1 skipped**（exit 1） | 2 失败仍是 `pgrep`/noexec 环境限制 |
| `tests/integration/g3c` | **110 passed** | 含 P1-2 新增 5 个冷启动测试 |
| `tests/integration/g3_bridge` | **31 passed** | — |
| `tests/unit/security/test_gates.py` | **14 passed** | — |
| G2 accounting/closure | **280 passed** | 本轮由归档 Agent 重跑，不是 v1 Reviewer 的独立证据 |
| Ruff | **All checks passed!** | — |
| Node adapter / Guard | **9/9 / 19/19**（0 fail） | 固定 rootfs |
| P1-2 20 轮冷启动 | **20/20 controlled singleton，0 traceback，Fake counter=1，Attempt `SETTLED`** | 新证据 `artifacts/g3c/evidence/concurrency-coldstart-20261117T161008Z.json`，日志 `artifacts/g3c/logs/coldstart-20261117T161008Z/` |
| real-DSH 冒烟 | Echo：1 Attempt `SETTLED`；Tool：2 Attempts `SETTLED`；均 `finish=completed`、controller exit 0、`key_env=[]` | 新 trace `artifacts/g3c/traces/pr1v2-{echo,tool}/`；仍为 Fake Provider |
| canonical | rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…` | 运行期 podman 在 rootfs 创建的空 `evidence/` 挂载点已用 `rmdir` 清理，最终 hash 恢复 canonical；见 `pr1-canonical-after.log` 的 POST-RUN CORRECTION |
| absence / 0-Key | `podman ps -a` 空、无残留 broker/fake/controller；`run_live.sh` exit 3、`LiveGate` `BLOCKED`、`KEY_ENV_COUNT=0` | `pr1-livegate.log`、`pr1-canonical-after.log` |

这些计数是归档 Agent 的实测，不是二次 Reviewer 的独立复跑，也不构成 PASS。二次复核必须用自己的命令重跑并记录自己的 argv/UTC/exit。

---

## 4. v1 报告与矩阵的受限读法

1. **v1 报告是快照，不是当前 HEAD 的描述**：它针对 `e6fde1c` + docs `78be77c` + Packet v1；当前 docs 已由 `9ffa0b1`/`bea0fc3` 修正，行号/文字已变。引用 v1 报告行号时，必须同时说明是 v1 docs blob 的行号。
2. **v1 `PARTIAL` 仍是最后一次独立裁定**：PR1 是 Owner 修复；本归档没有执行二次独立复核，也没有把 PR1 结果改写成 PASS。任何“已修复/PASS”说法都必须由二次 Reviewer 重新裁定。
3. **Packet v1 冻结**：`artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/` 是 v1 的原始字节包（1713/1713 OK，1715 files）；本 PR 不修改、不重建、不复用其 manifest 作为 v2 身份。
4. **矩阵 `impl_sha` 与 trace 生成批次不同**：PR1 后矩阵 53 行 `impl_sha` 统一写 `b2f6af0`（当前实现），但多数旧 trace 实际由 `e6fde1c` 产生；trace 内 `argv.json`/`commands.jsonl` 可追溯生成批次。不得把旧 trace 说成 `b2f6af0` 新运行；PR1 只复跑 Echo/Tool 冒烟（`artifacts/g3c/pr1/traces/{echo,tool}`）。
5. **计数按身份区分**：v1 Reviewer 实测 host/OCI 各 768 passed / 2 env failed / 1 skipped，对应 `e6fde1c`；PR1 报告实测 773/2/1，对应 `b2f6af0`。两组数字不能混用。
6. **v1 Reviewer 的 14 次真实 DSH 是 Reviewer 自己的 `reviewer-*` trace**，位于 `artifacts/reviewer-g3c/r3-dsh/`，不是 Owner 的 `*-fixed` trace；两者不能互相冒充。
7. **P2 仍然是 P2**：SRC-12、P2-4、断连 cancel、OCI/host 环境失败、SIGTERM 终态不确定等没有被 PR1 消除；v1 报告 §8 P2 与 §10 仍适用。

---

## 5. Packet v1 冻结说明

- 路径：`artifacts/review-packet-g3c-e6fde1cdf0bec9e957e98d569b257c8f17dfa363/`。
- 身份：base `bb5bd0b`、g0 `e107e22`、impl `e6fde1c`、docs `78be77c`（`docs_parent_sha=dd4bf40`）。
- 完整性：`sha256sum -c hashes.sha256` 1713/1713 OK；manifest `file_count=1715`；`diff_sha256=6b33cd74bfee871f2e805ad1fc0db4077121d325085f4c9713007247db3fcd80`。
- 冻结策略：v1 packet 不修改、不追加、不重新打包；PR1/v2 使用新目录 `artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/`，并在其 `manifest.previous_review` 中索引 v1 的 PARTIAL/P1。v2 的 `docs-diff.patch` 记录 `bb5bd0b..<最终 docs commit>`（含 docs 变更），`diff.patch` 记录 `bb5bd0b..b2f6af0`（实现）。
- sqlite 只做字节 hash，不用 `sqlite3` CLI 打开；如需查询先复制到 `/tmp` 只读副本。

---

## 6. 未变事项（PR1 不改变）

- **G3-D 16 行仍 `NOT_RUN`**：D0-01、D1-01、D2-01..12、D3-01、D-REVIEW-01；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`。
- **无 Live/GO**：`run_live.sh` 仍 exit 3；`LiveGate().inspect(live_requested=True)` 仍 `BLOCKED`；不签 G3-D/Live/G4/G5/M0 GO。
- **0 真实 Key / 0 真实模型 / 0 外部付费 HTTP**：真实 DSH 只用固定 rootfs + Fake Provider；`key_env=[]`、`http_calls=0`；Fake usage/cost 是 `synthetic_fixture_only`。
- **未做 real-DSH replay**：P1-1 的处置是标注修正，不是补跑；raw-UDS replay 仍不能写成 DSH。
- **未做双真实 DSH 同 Claim**：P1-2 修复覆盖 Controller/socket/Broker/Fake/SQLite 级冷启动，不覆盖两个真实 DSH 客户端同 Claim。
- **G2 280 未由 v1 Reviewer 独立重跑**：v1 只核对 Owner junit/log；PR1 报告的重跑也是 Owner 运行；二次复核若要主张需自行复跑。
- **host-level 22 行仍是宿主 pytest**（真实 socket/子进程，但不是 DSH）；不得合并为 real-DSH。
- **SIGTERM 终态不确定**：v1 Reviewer 得到 `RESPONSE_OBSERVED`/PENDING，Owner `sigterm-fixed` 为 `WORST_CASE_HELD`；两者保守但时序不确定，仍需 reconcile。
- **环境失败未修复**：host 2 个（可写 config、硬编码 `/project`）与 OCI 2 个（无 `pgrep`、`/tmp` noexec）是环境限制，v1/PR1 都记录为既有失败，不是产品断言通过。
- **历史与范围**：G3-B 裁定、G3-B packet、33 行矩阵、`docs/REVIEW_G3B_INDEPENDENT.md`、G3-B errata、G3-D0 设计均未被本 PR 修改；未 push、未 amend、未重写历史。

---

## 7. 本 errata 的边界与待二次复核事项

- 本文件 **不改变** v1 报告的任何文字、行号内容或字节；v1 报告以原字节提交，sha256 必须保持 `4744c61f…`。若后续发现新的处置事实，只能追加新的 errata，不能改写本文件或 v1 报告。
- 本文件 **不裁定** PR1 已 PASS；它只记录“P1 的处置位置与证据”，最终裁定留给 Lead 指派的二次独立 Reviewer。
- 二次 Reviewer 的最小待验证项：
  1. **P1-1**：逐行核对 53 个 PASS 行的证据类型（real DSH 必须有 `dsh-result.json`；raw-UDS 不得写成 DSH；reconcile 不得写成 DSH；host pytest 不得写成 DSH）；重点复核原 8 行与 C1-01A/C-END-01 的 argv/log/path。
  2. **P1-2**：用 Reviewer 自己的命令重跑 ≥20 轮双 Controller 同时冷启动；核验 1 成功 + 1 受控拒绝（exit 5 或 3/4，按场景）、0 traceback、Fake counter=1、Attempt `SETTLED`；并核对 `busy_timeout` 在 WAL 之前的代码顺序与 per-socket singleton。
  3. **P1-3**：独立重跑矩阵路径审计（docs 矩阵 + 工作矩阵），确认 `missing_paths=0`；核对 D 行 16 条与 v1 冻结字节一致；抽查 C1-01A/C-END-01/C2-04 的 argv/log/junit。
  4. **真实 DSH 标注口径**：确认 `impl_sha=b2f6af0` 与旧 trace 生成批次 `e6fde1c` 的区分；确认 PR1 只复跑 Echo/Tool；不得把 Owner 的 `*-fixed` trace 当成 Reviewer 新运行。
  5. **回归/环境**：在 `b2f6af0` + 最终 docs commit 上复跑 host full、g3c、g3_bridge、gates、G2、Ruff、Node/Guard、OCI；记录实际计数与环境失败；核对 canonical/absence/0-Key/LiveGate。
  6. **裁定枚举**：只能 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE` / `FAIL` / `PARTIAL` / `BLOCKED`；禁止 G3-D/Live/G4/G5/M0 GO。

---

*本 errata 由 G3-C Packet v2/PR1 归档 Agent 追加；不 push、不 amend、不修改 v1 packet、G3-B 历史、Reviewer 原始证据或其他 artifacts。*
