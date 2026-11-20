# A-NEXT A-PR3 / R-REV6 — L2 报告 Append-only Addendum（P2-A4-1 / P3 修正）

- **类型**：append-only addendum。**不修改** `docs/A_NEXT_RREV6_L2_REPORT.md`
  已冻结字节（该报告最后提交 `95a020b27ccf05ae3cd504d8c138bc279706fee2`），
  也不修改 `artifacts/a_next/rrev6/l2/run-20261120T202039Z/` 下任何既有证据文件。
- **起因**：Reviewer batch-3 host 级审核结果 **PASS（host-scope）**，同时记录
  **P2-A4-1**（`evidence-index.json` 的 `receipts` 键与实际 `receipt/` 目录路径不一致）
  与 **P3**（索引覆盖范围声明、case 计数措辞）。
- **本次动作**：仅新增两个文件：
  1) `artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index-v2.json`
     （gitignored；在原 `evidence-index.json` 旁新增，**不覆盖**原文件）；
  2) 本 addendum（被提交）。
- **未运行 OCI**：本次修正不启动任何容器、不执行 podman run/exec、不触碰 Reviewer
  20:45–21:10Z 独立窗口；未 push。
- **Owner 证据身份不变**：本次窗口 L2 证据仍是 **Implementer/Owner 证据，不是 Reviewer
  独立复跑**；本 addendum 不把它升级为 Reviewer 证据。

---

## 1. Reviewer host 级结论（原样记录，不外推）

- Reviewer batch-3 对本轮 L2 证据的 **host 级审核结论 = PASS（host-scope）**：
  Reviewer 按实际目录映射逐一校验 **114 个 case 级证据文件**全部通过。
- Reviewer 同时指出两个非阻断问题：
  - **P2-A4-1**：`evidence-index.json` 使用 `receipts` 键嵌套 receipt 哈希，实际磁盘路径为
    `receipt/<rcpt-*.json>`；按索引字面路径解析会 miss，需人工映射。
  - **P3**：原索引只覆盖 9 类核心证据（未含 `cleanup/`、`env/`、`peercred/`、`logs/` 等），
    覆盖范围未在文件中显式声明；case 计数措辞需统一。
- 该 host 级 PASS **不等同**于 R-REV6 的独立 L2 PASS：Reviewer 的独立 OCI 复跑为
  **NOT_RUN**（见 §3）。

## 2. P2-A4-1 修正：`evidence-index-v2.json`（权威路径映射）

- 新文件：`artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index-v2.json`
  - SHA-256：`bac7b550b653079fc382fb702be2374526af10d6c99c976935732b80747f2832`
  - schema：`m0.a_next.rrev6.evidence-index.v2`，`authoritative: true`
  - 相对原 v1 的修正：`files["receipts"] = {<name>: {...}}` →
    `files["receipt/<name>"] = {...}`（`receipt/` 前缀为真实相对路径）
  - 逐文件复核：**case 级 114 文件 + run 级 5 文件 = 119 文件**，每个文件重新读取并校验
    `sha256` 与 `bytes`；`mismatches = []`、`missing = []`、`all_verified = true`
  - 其中 case 级 114 = 13 个 case 目录内的 105 个路径条目 + 9 个 receipt 文件
    （R6-01:1、R6-02:2、R6-03:2、R6-04:1、R6-04B:1、R6-07:1、R6-11:1 共 9 个 receipt）；
    run 级 5 = `t0.json`、`t1.json`、`matrix.json`、`audit.json`、`summary.json`
  - `run` 绑定：`run_head=d083c54…`、`report_commit=95a020b…`、Stage manifest
    `34b3db73…`、Stage tree `2b9edab8…`、frozen rootfs `25491e45…`、deps `e07729d7…`
- **原 `evidence-index.json` 保留作历史，字节不变**
  （SHA-256 `4c5f9f000e1ca00fedf98879a1d0dbbd0b3e2f748074f6e1df0cc8310c524db7`，
  即原报告 §5.1 所记值）；v2 的 `supersedes.sha256` 记录该值以证明未被改写。
- **权威性**：自本 addendum 起，`evidence-index-v2.json` 为本次 L2 证据索引的权威映射；
  v1 仅作历史/差异对照。

## 3. P3 修正：覆盖范围显式收窄 + case 计数措辞统一

### 3.1 覆盖范围（v2 `coverage_scope` 明确声明）

- v2 **不声称全树覆盖**。明确覆盖：
  - **case 级 114 文件**：`cases/<case-id>-20261120T202039Z/` 下用于 A4
    digest/ledger 审计的选定证据（`a_next/case-runner.json`、`run/dispatch-window.jsonl`、
    `run/state/request-lifecycle.jsonl`、`run/state/recovery-diagnostics.jsonl`（存在时）、
    `run/state/{broker,attempts}.sqlite3`（存在时）、`db/snapshot.json`、
    `run/g4c-egress.json`、`run/g4c-send-journal.jsonl`、`checks/checks.json`（存在时）、
    `traces/dsh-result.json`（存在时）、`receipt/*.json`）；
  - **run 级 5 文件**：t0/t1/matrix/audit/summary。
- **显式未索引（存在但不覆盖）**：`cleanup/`、`env/`、`peercred/`、`uid-map/`、
  `mountinfo/`、`network-probe/`、`socket-stat/`、`traces/` 除 `dsh-result.json` 外、
  `logs/`、`run/*.stdout.txt`、`run/*.stderr.txt`、`run/*.log`。
  这些文件仍在证据树中，可由 Reviewer 自行读取；v2 不把它们计入 114/119。
- 与 Reviewer host 级 PASS 的关系：Reviewer 已按实际映射人工校验 114 个 case 级文件；
  v2 只是把**同一批 114 文件**写成可机读、路径正确的权威索引，并显式声明范围。

### 3.2 case 计数措辞统一

- **13 个真实容器 case 目录**：`R6-01..R6-12`（12 个）+ `R6-04B`（同 business request
  字节级重放子 case，1 个）= **13 个 `cases/<id>-20261120T202039Z/` 目录**；
- **1 个 audit-only 状态行**：`R6-13`（usage/hash 跨 case 审计，无独立容器目录）；
- 因此 Owner 审计状态行 = **13 + 1 = 14 行**（`audit.json` 的 `counts.total=14`、
  `PASS 14 / PARTIAL 0 / NOT_RUN 0`），与 `cases/` 目录数 13 不矛盾。
- 原报告 §5.1/§5.2 中的措辞“13 case + R6-04B 子 case = 14 evidence 行”以本节为精确表述。

## 4. L2 状态与 A4 矩阵状态（Reviewer 独立复跑为 NOT_RUN）

- Reviewer 的**独立 OCI 复跑 = NOT_RUN**（Reviewer 自有窗口尚未产出独立 L2 结果；
  本轮 Reviewer 结论仅 host 级）。
- 因此**维持**：**A4 / R-REV6 总状态 = PARTIAL**（Owner L2 证据已提供并被 host 级审核，
  但缺 Reviewer 独立 OCI 复跑）；**不得**写成 R-REV6 PASS。
- **A4-01 / A4-02 / A4-03 矩阵状态保持 NOT_RUN**（本批 Owner 证据 + 本次 addendum
  均不改变矩阵状态；矩阵 CSV 由 Lead/Integration 维护，本 Agent 未改任何 CSV 字节）。
- **“Owner 证据非 Reviewer 复跑”不变**：本窗口所有容器/DSH/DB/JSONL 证据均为
  Implementer/Owner 产出；addendum 只修正索引与措辞，不改变证据等级，也不构成独立验证。

## 5. 本次修正的文件与校验

| 文件 | 状态 | SHA-256 / 说明 |
|---|---|---|
| `artifacts/.../run-20261120T202039Z/evidence-index-v2.json` | **新增**（gitignored） | `bac7b550b653079fc382fb702be2374526af10d6c99c976935732b80747f2832`；119/119 文件 sha 校验通过 |
| `docs/A_NEXT_RREV6_L2_REPORT_ADDENDUM.md` | **新增**（本文件，被提交） | 提交 SHA 由交付消息给出 |
| `artifacts/.../run-20261120T202039Z/evidence-index.json` | **未改** | `4c5f9f00…`（与冻结报告一致） |
| `docs/A_NEXT_RREV6_L2_REPORT.md` | **未改字节** | 保持 `95a020b` 冻结版本 |
| 原始 case 证据（114 case 文件 + run 级 5 文件） | **未改字节** | v2 逐文件重算 sha/bytes 全部一致 |
| `artifacts/{security/rootfs,foundation/deps,g3c/stage,g3a-provider-bridge/stage}` 副本 | **未动** | 保留供 Reviewer/Packet 引用 |

- 本次无 OCI：未执行 podman run/exec、未占用 Reviewer 20:45–21:10Z 窗口；未 push。
- 复核命令（只读）：

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-rrev6"
sha256sum docs/A_NEXT_RREV6_L2_REPORT.md \
  artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index.json \
  artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index-v2.json
# 报告 sha 应等于 95a020b 版本的冻结字节；v1=4c5f9f00…；v2=bac7b550…
```
