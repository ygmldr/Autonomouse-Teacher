# G4-H0 — 文档勘误（append-only：Reviewer P2 与已知不一致登记）

- **文档 ID**：`G4H0-ERRATA-v1`
- **生成时间（UTC）**：`2026-11-19T18:39Z`（`date -u` 采样）
- **生成者**：`a-impl-docs`（A 线文档实施者 Agent；**非** Reviewer、**非**维护者）
- **文档性质**：**append-only 勘误登记**。本文件只**新增**自身；**不修改**任何既有 `docs/g4h0/*` 文档
  （以保持 Reviewer 报告引用的 SHA 稳定），不改 `src/`，不部署、不授权、不代签。所有“维护者决策”栏留空。
- **状态常量（未因本文件改变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

## 0. 适用对象与引用约定

| 对象 | 值 / 位置 |
|---|---|
| base | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 冻结 impl（主审对象） | `813e6a680399ba245bd0e76296e1212118a83460` |
| test-only delta（含 F-01 修复） | `b57494a`（其后包含 `87aa52f`；`work/m0-g4h0` / `work/m0-g4h0-fix`） |
| 主审报告 | `docs/g4h0/INDEPENDENT_REVIEW.md` @ `work/m0-g4h0-review` `77b3159`（`G4H0-INDEPENDENT-REVIEW-v1`，424 行；裁定 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`，`P0=0`、`P1=0`，P2 = 5 个 finding ID：`F-01`；`F-02`；`F-03`；`F-04`/`F-05`） |
| 维护者决策表 | `docs/g4h0/HUMAN_DECISIONS.md` @ `77b3159`（`G4H0-HUMAN-DECISIONS-v1`，`HD-01..HD-13`） |
| P2 修复报告（权威状态源之一） | `docs/g4h0/P2_FIX_REPORT.md` @ `b57494a`（268 行；`P2-03/04/05/06` 均 `FIXED`） |
| 集成状态权威源 | `docs/g4h0/REVIEW_REQUEST.md`（224 行）、`docs/g4h0/EVIDENCE_INDEX.md`（77 行）@ `b57494a` |
| Packet v2 | 集成 worktree gitignored `artifacts/g4h0/packet-v2`（`manifest.json` 只读读取） |
| v1 Packet（不可变） | 主工作树 gitignored `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99`（未改写） |

> **引用约定**：本 errata 位于 `work/m0-g4h0-docs` @ `f4a154a`；上述对象位于 review/integration/fix 分支，
> **尚未合并进本分支**（本分支仅含 A3 五文件）。因此本文引用其分支内路径与行号；存在性自查见 §8。
> 本 errata **不修改** `DEPLOYMENT_RUNBOOK.md` / `RISK_DISPOSITION.md` / `A3_REFS.md` /
> `E5_PRELIVE_FULL_CHECKLIST.md` 等既有文件；需更正处一律以本文覆盖，待下一版文档再落笔。

## 1. 勘误总表

| ID | 原 finding | 对象 | 处置建议 | 状态 |
|---|---|---|---|---|
| E-01 | `F-03`（`HD-12`） | `DEPLOYMENT_RUNBOOK.md` §4.5/§4.6（同批 `A3_REFS.md` C-01、`E5_PRELIVE_FULL_CHECKLIST.md` V-12、Runbook U-09 同属旧状态） | 以 `P2_FIX_REPORT.md` + `REVIEW_REQUEST.md` 为准；下一版 Runbook 更正 | **口径已更正（本文）**；原文件不改（SHA 稳定） |
| E-02 | `F-02`（`HD-11`） | `authorization.py` use-record 发布（非本文文件） | H0 无 Key 范围可接受；**G4-H1 前** fsync 目录或明示接受 | **OPEN / LOW**（未修，不得称已修复） |
| E-03 | `F-04`/`F-05`（`HD-13`） | `_read_use_record` FIFO 阻塞、recovery reason 256 截断 | 下个加固窗口处理；H0 可接受为 nit | **OPEN / LOW（nit）** |
| E-04 | 已知不一致 | `RISK_DISPOSITION.md`（0a9ee67 时点快照） | 不改正文；P2-03..06 最新状态以 `REVIEW_REQUEST.md`/`EVIDENCE_INDEX.md`/`P2_FIX_REPORT.md` 为准 | **快照说明** |
| E-05 | 已知不一致 | `artifacts/g4h0/packet-v2` 身份限制 + P2-02/P2-07 内容缺陷 | 不宣称 v2 为 813e6a6 实现快照；v1 不可变 | **已披露** |
| E-06 | `F-01`（`HD-10`） | `tests/integration/g4_h0/test_p2_03_concurrent_consume.py` | test-only delta `87aa52f` 已交付并合并 `b57494a`；待 Reviewer addendum | **test-only FIXED**；独立 addendum **UNVERIFIED/NOT_RUN**（待合并） |

---

## 2. E-01（原 `F-03`）— Runbook 与 P2-03 修复口径冲突

- **finding_id**：`F-03`（Reviewer 报告 §7；维护者决策 `HD-12`）
- **来源**：`docs/g4h0/INDEPENDENT_REVIEW.md`（@`77b3159`）§5/§7；`docs/g4h0/HUMAN_DECISIONS.md` `HD-12`；
  冲突对象 `docs/g4h0/DEPLOYMENT_RUNBOOK.md`（@本分支 `f4a154a`）§4.5（`:134-149`，仍写 P2-03“未修复前
  不得把并发撤销/消费演练写成 PASS”）与 §4.6（`:151-158`，仍描述旧 `O_CREAT|O_EXCL` 落记录机制）。
- **事实（权威口径）**：`P2_FIX_REPORT.md` 声明 `P2-03/04/05/06` 均 `FIXED`，主审已独立复验成立
  （`INDEPENDENT_REVIEW.md` §2/§3；P2-03 安全契约：恰好一次、0 双消费、loser 稳定
  `AUTHORIZATION_REPLAYED`）。新机制为：**同目录**随机名临时文件
  （`.use-record-tmp-*`，`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, `0o600`）→ 循环写全 body →
  `fsync(fd)` → `os.link(temp, record_path)` **原子发布**（`link` 不覆盖既有名字，至多一个 publisher 成功）；
  `FileExistsError` → loser 读记录并映射 `REPLAYED`/`EPOCH_MISMATCH`；非 EEXIST 的 `OSError` → 清理 temp 并抛
  `AUTHORIZATION_USE_LOG_WRITE_FAILED`（授权未被消费、fail-closed）；`_read_use_record` 改单描述符 +
  `fstat` + 定长读取 + size 校验；`_read_use_record_settled` 仅在 `INVALID` 时有界重试（20×10ms，只影响错误码
  分类）；`MAX_AUTHORIZATION_USES` 排除 temp 残留。既有签名/绑定/路由/工具/预算/时限/撤销/epoch 校验不变。
- **影响**：维护者按冻结 Runbook 签核/部署时会读到**过时缺陷状态**（把已修 P2-03 当成未修），影响人类判断；
  不改变任何安全语义，也不影响主审裁定范围。
- **处置建议**：**FIX（文档）**——下一版 Runbook 更新 §4.5/§4.6 与 U-09，并在同批 `A3_REFS.md` C-01、
  `E5_PRELIVE_FULL_CHECKLIST.md` V-12 同步状态；原文件本轮**不改**，以本文覆盖（append-only、SHA 稳定）。
  主审建议亦为“append-only errata / 下一版 Runbook 更新（禁止原地改写冻结证据）”。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**口径已由本 errata 更正**；原文档保持 `f4a154a` 字节不变；下一版文档待维护者决定。
- **关联**：`HD-04`（接受 P2-03 修复）、`HD-12`（本项）。

---

## 3. E-02（原 `F-02`）— use record 发布后未 fsync 目录项（掉电持久性残余）

- **finding_id**：`F-02`（Reviewer 报告 §7；`HD-11`）
- **来源**：`docs/g4h0/INDEPENDENT_REVIEW.md` §7 `F-02`；`P2_FIX_REPORT.md` §7 已自认“与旧语义一致、
  不在本修复范围”。目标代码 `src/autoteacher_m0/security/authorization.py`（**非本任务文件**）。
- **事实**：`_publish_use_record` 对记录 body `fsync(fd)` 后 `os.link` 发布，但**未 fsync 父目录**；
  掉电/崩溃后目录项可能未持久化，已返回成功的 consume 在重启后**可能**允许同一授权再次消费。
  旧实现同样未做，故非本轮回归；正常运行时无影响。
- **影响**：H0 无 Key 范围无实际影响；**G4-H1/G5 前**需处置，否则在最坏掉电场景下“单次消费”持久性不能
  完全成立（不得宣称已修复/已证明）。
- **处置建议**：**FIX（H1 前）**：`os.link` 成功后对父目录 `os.open(dir, O_RDONLY|O_DIRECTORY)` +
  `os.fsync`（失败按 fail-closed 或记告警）+ 定向测试；H0 可 `DEFER`/明示接受。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**OPEN / LOW**——未修复；**不得写成“已修复”**。

---

## 4. E-03（原 `F-04`/`F-05`）— 加固 nit

- **finding_id**：`F-04`、`F-05`（Reviewer 报告 §7；`HD-13`）
- **来源**：`docs/g4h0/INDEPENDENT_REVIEW.md` §7 `F-04`/`F-05`；`HUMAN_DECISIONS.md` `HD-13`。
- **事实**：
  - `F-04`：`_read_use_record` 未加 `O_NONBLOCK`；若**可信 use-log 目录内**记录名被替换为 FIFO，读端可能阻塞
    （DoS 类；需 trusted 目录写权限；旧 `stat+read_bytes` 同样会阻塞，非回归）。
  - `F-05`：`_preserved_uncertain_reason` 在多次恢复时重复追加 `|RECOVERY_EVIDENCE:` 并受 **256 字符**上限
    截断，可能截断最新证据文本；仅证据可读性，无状态/安全/held 语义影响。
- **影响**：低；无 H0 阻断。`F-04` 在“可信目录被恶意替换”假设下才成立；`F-05` 只影响事故归因文本完整性。
- **处置建议**：**FIX（下个加固窗口）**：`F-04` 打开时加 `O_NONBLOCK` 并在 `fstat` 后按普通文件读取；
  `F-05` 将完整证据记录到独立字段而非拼接 reason。H0 可 `ACCEPT` 为 nit。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**OPEN / LOW（nit）**。

---

## 5. E-04 — `RISK_DISPOSITION.md` 为 `0a9ee67` 时点快照

- **finding_id**：已知不一致（非 Reviewer finding 编号；主审报告 §7“另记录”亦提及措辞精度）
- **来源**：`docs/g4h0/REVIEW_REQUEST.md:196`、`docs/g4h0/EVIDENCE_INDEX.md:14`（@`b57494a`）明确说明
  `RISK_DISPOSITION.md` 是 `0a9ee67` 时点快照；其中 `P2-03/04/05/06` 标为“未修复/UNVERIFIED”，
  与集成后的 `P2_FIX_REPORT.md`（`FIXED`）不一致。
- **影响**：若直接引用 `RISK_DISPOSITION.md` 的 P2 状态，会低估当前修复进度、或与 `REVIEW_REQUEST.md` 矛盾；
  不改变其“A1 建议态、决策栏留空、不代签”的性质。
- **处置建议**：**ACCEPT（快照语义）**——不修改其正文；引用 P2-03..06 最新状态时统一以
  `REVIEW_REQUEST.md`/`EVIDENCE_INDEX.md`/`P2_FIX_REPORT.md` 为准，并注明 `RISK_DISPOSITION.md` 是
  `0a9ee67` 快照。若维护者要求，可另发 append-only errata（本文件即该 errata 的一部分）。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**快照说明（不改写）**。

---

## 6. E-05 — packet-v2 身份限制与 P2-02/P2-07 内容缺陷

- **finding_id**：已知不一致（主审报告 §5；`HD-02`/`HD-03`/`HD-08`）
- **来源**：`docs/g4h0/PACKET_SUMMARY.md`、`docs/g4h0/REVIEW_REQUEST.md` §8、`INDEPENDENT_REVIEW.md` §5；
  只读读取集成 worktree `artifacts/g4h0/packet-v2/manifest.json`。
- **事实**：
  - v2 为 **175 files / 173 hashes OK / 0 sidecar / payload 172 / tree `ffae8b3b…` = manifest / integrity report PASS**；
    但 `manifest.impl_sha = e7d92967…`（G4-F 证据完整性重建的 impl SHA）、`docs_sha = 3e7afee…`、
    `code_sha = dbacb76f…`、`base_sha = bb2e9142…`、`head_at_packet = 3e7afee…`；
    **不是冻结 impl `813e6a6` 的实现快照**，不得当作本轮 H0 实现身份包。
  - **P2-02 内容缺陷仍在**：矩阵 `F2-07` 的 evidence path 指向
    `artifacts/g4f/f6/integration/f2/tool-window.json`（不存在），实际为 `artifacts/g4f/f2/tool-window.json`；
    v2 未修正。
  - **P2-07 内容缺陷仍在**：v1/v2 的 `env/zero-key.json.live_gate_reasons` 均为 **1 项**，而 manifest/
    review livegate 为 4 项（主审实测 `review/livegate.json.gate_all_evidence.reasons` 也是 1 项——因此
    `RISK_DISPOSITION.md`“v1/v2 的 zero-key 与 manifest/review 4 项不一致”的措辞不精确，但“1/4 项”事实成立）。
  - **v1 不可变**：177 files / 0 symlink / `sha256sum -c` 173/173 OK；2 个 post-build SQLite sidecar 已按
    P2-01 披露，未重打包、未改写。
- **影响**：选 v2 作为 G4-H1 证据基础时，必须接受“v2 身份 ≠ 813e6a6 实现快照 + P2-02/P2-07 未修”的限制；
  不得把 v2 自校验 PASS 写成 P2-02/P2-07 已修复或本轮实现已验证。
- **处置建议**：**ACCEPT（披露）或 FIX（新版本包）**：下一版 Packet 修正身份字段与 P2-02/P2-07，同时保留
  v1/v2 原字节；H0 引用时同时引用 manifest 4 项与 errata。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**已披露**；v1/v2 均未改写（本任务零写入）。

---

## 7. E-06（原 `F-01`）— test-only delta `87aa52f`（待 Reviewer addendum）

- **finding_id**：`F-01`（high；`HD-10`）
- **来源**：`docs/g4h0/INDEPENDENT_REVIEW.md` §7 `F-01`（g4_h0 新测试时序缺陷：固定 `sleep(0.3)` 与
  实测 consume 基线 `332–337 ms` 冲突，单跑 10/10 失败、目录整跑 14 passed，非确定性；仅影响证据绿色状态，
  不改变安全语义）；`docs/g4h0/HUMAN_DECISIONS.md` `HD-10`。
- **事实（delta）**：`87aa52f` = `test(g4h0): make P2-03 bounded-retry tests deterministic`
  （`tests/integration/g4_h0/test_p2_03_concurrent_consume.py` +106/−20，另加
  `docs/g4h0/evidence/p2_03_g4h0_standalone_3x.log`；**只改测试**，无 `src/` 变更）；已合并到集成分支
  `b57494a` = `merge(g4h0): deterministic P2-03 retry-bound test after review finding (test-only, no src change)`。
- **影响**：F-01 的修复属 **test-only**，不改变实现/安全语义；在 Reviewer 发布 addendum 并独立复跑确认前，
  “g4_h0 稳定绿色”仍为 `UNVERIFIED`，不得写成 PASS/H0 绿色证据已成立。
- **处置建议**：**FIX 已交付，待独立确认（ACCEPT 待人类）**：见
  `docs/g4h0/INDEPENDENT_REVIEW_ADDENDUM.md`（Reviewer 产出后以其为准；**待合并**——截至本 errata 生成
  （2026-11-19T18:39Z），`work/m0-g4h0-review` @ `77b3159` 树内尚无该文件）。确认标准：≥10 次稳定复跑
  `tests/integration/g4_h0` 全绿 + 独立压力证据（`HD-10` 建议）。
- **维护者决策**：`[ ] ACCEPT  [ ] FIX  [ ] BLOCK  [ ] DEFER`　签核人：`__________`　UTC：`__________`　条件：`__________`
- **状态**：**test-only FIXED（合并 b57494a）**；独立 addendum **UNVERIFIED/NOT_RUN（待合并）**。

---

## 8. 引用文件存在性/验证自查（只读，不合并、不 checkout 其它分支）

已执行（只读检查；不修改其它 worktree）：

| 检查 | 结果 |
|---|---|
| `git -C worktrees/m0-g4h0-review rev-parse HEAD` | `77b3159aadb5298c6b30f69a8624d4e61fd025cc`（= 主审报告 @77b3159） |
| `docs/g4h0/INDEPENDENT_REVIEW.md`（review 分支） | 存在，424 行，`G4H0-INDEPENDENT-REVIEW-v1` |
| `docs/g4h0/HUMAN_DECISIONS.md`（review 分支） | 存在，83 行，`G4H0-HUMAN-DECISIONS-v1`（含 `HD-01..HD-13`） |
| `docs/g4h0/P2_FIX_REPORT.md`（review/integration 分支） | 存在，268 行；`P2-03/04/05/06=FIXED` |
| `docs/g4h0/REVIEW_REQUEST.md` / `EVIDENCE_INDEX.md`（integration @`b57494a`） | 存在，224 / 77 行 |
| `artifacts/g4h0/packet-v2/manifest.json`（integration，gitignored） | 存在；身份字段见 E-05 |
| `docs/g4h0/INDEPENDENT_REVIEW_ADDENDUM.md` | **尚未存在（待 Reviewer 产出/合并）** |
| 本文件提交后范围校验 | `git diff f4a154a..HEAD --name-only` → **仅 `docs/g4h0/ERRATA.md`**（见提交报告） |

> 本任务硬约束复核：未修改 `DEPLOYMENT_RUNBOOK.md` / `RISK_DISPOSITION.md` / 其它既有 `docs/g4h0/*`；
> 未改 `src/`、未建 `--live`、未删除/改变 `LiveGate` `BLOCKED` 语义、未使用真实 Key/凭据、未发真实请求、
> 未改冻结 Packet、未触碰其它 worktree 的写域（只读引用）。

---

## 9. 维护者决策汇总（**空白，Agent 不代签**）

| 勘误 | 对应决策 ID（`HUMAN_DECISIONS.md`） | 建议 | 维护者决定（ACCEPT/FIX/BLOCK/DEFER） | 签核人/UTC/条件 |
|---|---|---|---|---|
| E-01 | HD-12 | FIX（下一版文档） | `__________` | `__________` |
| E-02 | HD-11 | FIX（G4-H1 前）/ H0 DEFER | `__________` | `__________` |
| E-03 | HD-13 | FIX（下个加固窗口）/ H0 ACCEPT | `__________` | `__________` |
| E-04 | HD-01（及 HD-04..07） | ACCEPT 快照语义 | `__________` | `__________` |
| E-05 | HD-02 / HD-03 / HD-08 | ACCEPT 披露或 FIX（新版本包） | `__________` | `__________` |
| E-06 | HD-10 | ACCEPT（待 addendum 独立确认） | `__________` | `__________` |

> 在维护者填写并签署前，上述各项保持**未签核**；`HD-` 表全部初始 `未签核`，不得以本 errata 替代。

---

## 10. 不主张 / STOP

- 本文件**不主张**：主审裁定升级、`E5_PRELIVE_FULL/E5-P04 PASS`、G4-H1/H2/G5/G6/M0 GO、真实部署或 Live；
  不主张 P2-03 之后残余（F-02/F-04/F-05）已修复；不主张 packet-v2 已修正 P2-02/P2-07 或等同于 `813e6a6`。
- 本文件不修改任何冻结文档/Packet/矩阵/历史证据字节；后续如需更正，按 append-only 追加 v2。
- **STOP**：等待维护者按 `HUMAN_DECISIONS.md` 与本文 §9 决策；Agent 不代签、不推进下一门。

## 11. append-only 版本记录

| 版本 | UTC | 内容 |
|---|---|---|
| v1 | 2026-11-19T18:39Z | 初始勘误：E-01（F-03 口径）、E-02（F-02）、E-03（F-04/F-05）、E-04（RISK_DISPOSITION 快照）、E-05（packet-v2 身份/P2-02/P2-07）、E-06（F-01 test-only delta 87aa52f/待 addendum） |

---

## 12. E-07 — Reviewer addendum 合并与 F-01 状态更新（append-only）

- **追加时间（UTC）**：`2026-11-19T18:44Z`。本节**只在文件末尾追加**；上文 §0–§11（含 v1 版本记录表）字节未改。
- **更新对象**：E-06（原 `F-01`）在写入时点（`2026-11-19T18:39Z`）记录的“addendum 待合并 / F-01
  `UNVERIFIED/NOT_RUN`”属**时点快照**；现由本条在事实层面更新，E-06 正文不改。
- **addendum 身份**：`docs/g4h0/INDEPENDENT_REVIEW_ADDENDUM.md`，ID
  `G4H0-INDEPENDENT-REVIEW-ADDENDUM-v1`；review 分支提交
  `4bd42d5755d47fb73a851caa41e7678d6daeaeb0`（Lead 已合并；Reviewer `a-reviewer`，未参与实现/证据生成/
  文档撰写）。同提交含 `docs/g4h0/review-evidence/delta_*.log`。
- **delta 复审对象**：`87aa52f34eab0185d3512a6e62e5b075748b5bbb`（test-only，2 文件）→ 集成 HEAD
  `b57494a5eecb2406d5a20605b04e2a54cda0dae8`；`git diff 813e6a6..b57494a` = 6 files（+560/−20），其中
  `src/` 与受保护实现文件**零 diff**（实现对象与冻结 `813e6a6` 等价）。
- **独立复验数字**（Reviewer 自跑；引自 addendum §2/§3 与 `review-evidence/delta_*.log`）：

  | 项 | 结果 | 证据日志 |
  |---|---|---|
  | `F-01` 单测 `test_retry_bound_stays_fail_closed_for_a_late_publisher` 单独 ×10 | **10/10 passed**（对照：冻结 `813e6a6` 上 0 passed / 10 failed） | `delta_f01_single_10x.log` |
  | `pytest tests/integration/g4_h0 -q` 连续 ×10（每次全新进程） | **10/10 次均 `14 passed`** | `delta_g4h0_dir_10x.log` |
  | `pytest tests/integration/g4_f5 -q` | **17 passed** | `delta_g4_f5.log` |
  | `ruff check tests/integration/g4_h0/` | **All checks passed!**（exit 0） | `delta_ruff.log` |
  | delta 的 `src/` 与受保护文件 | **零 diff**（仅 test-only + docs/evidence） | `delta_scope.log` |

- **状态更新**：`F-01` = **`CLOSED`（独立确认）**；Reviewer 维持主审裁定
  `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`。**范围限制不变**：仅覆盖“G4-H0 无 Key 准入准备/证据就绪”，
  **不表示且禁止宣称** `E5_PRELIVE_FULL/E5-P04 PASS`、G4-H1/H2、G5、G6、M0 GO、部署或 Live 授权。
- **与 E-06 的关系**：E-06 的事实（`87aa52f` test-only、已合并 `b57494a`、纯测试无 `src/` 变更）与处置建议
  保持不变且已被独立确认；仅“待合并/UNVERIFIED”状态更新为上述 `CLOSED`。§7 E-06 原文字节不改。
- **仍 OPEN（不因本条关闭）**：
  - `E-02`（原 `F-02`）：目录项未 fsync 的掉电持久性残余 → **G4-H1 前** `FIX`（fsync 目录 + 测试）或明示接受；
  - `E-03`（原 `F-04`/`F-05`）：`O_NONBLOCK` / 256 截断 nit → 下个加固窗口；
  - `E-01`/`E-04`/`E-05`：文档口径、时点快照、packet-v2 披露 → 按 `HUMAN_DECISIONS.md`
    （`HD-01..HD-08`、`HD-11..HD-13`）由维护者处置。以上均**未修/未签收**，不得写成 PASS。
- **维护者决策（本项，留空不代签）**：`[ ] ACCEPT（记录 F-01 CLOSED）  [ ] DEFER`
  签核人：`__________`　UTC：`__________`　条件：`__________`。
  为保持 append-only，本节不修改 §9 既有决策汇总表。
- **状态常量（未变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
- **append-only 记录**：v1.1 — 2026-11-19T18:44Z 追加本节（E-07）；上文 v1 字节未改。
