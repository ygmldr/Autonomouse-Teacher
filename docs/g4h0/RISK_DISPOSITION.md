# G4-H0 — 风险处置清单（A1，建议态）

- **文档 ID**：`G4H0-RISK-DISPOSITION-v1`
- **执行者**：`a-impl-core`（A 线实施者；非 Lead、非独立 Reviewer）
- **采集时间（UTC）**：`2026-11-19T17:36Z` → `2026-11-19T17:52Z`
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（与 `docs/g4h0/BASELINE.md` 同一基线）
- **输入来源**：`docs/REVIEW_G4F_INDEPENDENT.md`、`docs/M0_G4F_REVIEW_ERRATA.md`、`docs/M0_G4F_HUMAN_HANDOFF.md`、`docs/M0_G4_HUMAN_HANDOFF.md`、`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md`、`docs/M0_G4F_F{1,2,4,5}_REPORT.md`、`docs/E5_PRELIVE_NO_KEY_REPORT.md`、矩阵 CSV、以及本线本地无 Key 复算（`docs/g4h0/evidence/`）。
- **文档性质**：**Agent 只能给出建议，不得代签任何 ACCEPT。** 本文件不修改任何冻结文档/矩阵/Packet，不改变任何门状态；所有 `维护者决策` 栏保持空白，必须由维护者（必要时加独立 Security Reviewer）亲自填写并签名。

## 使用说明与图例

- **建议枚举**：`FIX`（应修复后再进入指定门）/ `ACCEPT`（建议人类接受残余，需明确签收）/ `BLOCK`（在指定门之前必须解决，否则不得推进）。
- **门列含义**：`G4-H0` = 本轮无 Key 准入准备包；`G4-H1` = 真实受信部署准备（**不在本轮授权**）；`G5` = 单次真实模型授权（**不在本轮授权**）；`Live` = 任何真实出站/计费。
- **本线复核边界**：本文的“本线复核状态”只表示本线在本机、无 Key、离线条件下能否复核到该证据；不代表独立 Reviewer 结论。凡 `UNVERIFIED`/`PARTIAL` 均不得被引用为 PASS。

---

## 0. 摘要

- G4-F 独立复核已知口径：**P0=0、P1=0、P2=8**（`REVIEW_G4F_INDEPENDENT.md:311-345`、`M0_G4F_REVIEW_ERRATA.md:59-66`）。本文件覆盖：P2-01..P2-08、DSH merged Registry/E5-P04、P2-RUN-IDENTITY/USERNS/DISK、Crash Hooks/撤销链、F4 candidate-crash + live Controller 组合，共 **16 条 finding**。
- 本线**没有**发现新的 P0/P1；本线新增的事实是：v1 Packet P2-01 漂移**已独立复算复现**（§1.1），并**离线重建出自校验一致的 packet-v2**（§1.1 与 `BASELINE.md` §3.3），但 v2 不修复 P2-02/P2-07 内容问题。
- 处置建议分布（供维护者快速浏览）：`FIX` 6 条、`ACCEPT`（带条件/补偿控制）9 条、`BLOCK` 1 条（DSH merged registry/E5-P04 对 E5-Full/G5 的阻断）；另有若干条在 H0 可为 `ACCEPT`、在 H1/G5 必须 `FIX` 或重新签收（见 §6 汇总矩阵）。
- **没有任何一条被本 Agent 标记为已签收**；`维护者决策` 全部为空。

---

## 1. G4-F P2-01..P2-08 逐条处置

### P2-01 — Packet 构建后出现 2 个 SQLite sidecar；全量 payload tree 与 manifest 不符

- **finding_id**：`P2-01`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:74`（§2.2）、`:338`（§11 P2 表）；`docs/M0_G4F_REVIEW_ERRATA.md:130`（§4 表）、`:139-144`（§4.1 特别记录）；本线实测 `docs/g4h0/evidence/P2-01_packet_v1_verify_20261119T174453Z.log`、`P2-01_packet_v2_verify_20261119T174135Z.log`、`P2-01_v2.sha256`。
- **本线复核状态（VERIFIED/PARTIAL）**：v1 未改写 = **VERIFIED**（177 files/0 symlink、`sha256sum -c` 173/173 OK，两次一致，mtime 未变）；漂移复现 = **VERIFIED**（全量 tree `111c1361…` ≠ manifest；剔除 `resume-attempts.sqlite3-{shm,wal}` 后 = `e464b9b1…`）；sidecar 行级“无业务数据” = **PARTIAL**（本线只做字节统计：WAL 0 B、SHM 32768 B/非零 40 字节；未在 v1 上打开 SQLite，语义结论沿用 ERRATA §4.1 的历史独立复核）。v2 本地重建 = **VERIFIED**（175 files/0 sidecar/173 hashed/172 payload/tree 匹配/intensity report PASS）。
- **影响**：冻结 Packet 的 payload 自校验漂移，影响证据可复核性与“完整交付物”口径；sidecar 不含 Key/业务行，**未发现内容篡改、密钥泄漏或账本异常**。若被误读为“v1 全量一致”，会造成证据诚信问题。
- **建议**：**FIX（仅以新版本方式）** —— 采用 §BASELINE 3.2 的 sidecar 排除规则生成/接受一份新 Packet（本线已离线生成 `artifacts/g4h0/packet-v2`，见 `BASELINE.md` §3.3），同时在归档文档中保留 v1 不可变副本与 P2-01 披露；**禁止原地修补 v1**。
- **维护者决策（留空）**：☐ 接受 v1 + ERRATA 披露　☐ 采用/复核 v2　☐ 要求再生成 v3　☐ 其它：____________　签核人/日期（UTC）：__________________
- **部署前置条件**：G4-H1 之前必须存在一个**维护者明确接受的 Packet 版本**（v1+errata 或 v2+独立复算）；任何新包必须包含 sidecar 规则与全量文件哈希清单；不得再出现“未哈希 payload 漂移”。

### P2-02 — 矩阵 `F2-07` 证据路径不存在（`f6/.../tool-window.json` vs 实际 `artifacts/g4f/f2/tool-window.json`）

- **finding_id**：`P2-02`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:254`（§9.1）、`:339`；`docs/M0_G4F_REVIEW_ERRATA.md:131`、`:146-150`；冻结矩阵 `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv:13`（F2-07 行）。
- **本线复核状态**：**PARTIAL** —— 本线核对了矩阵行文本与 ERRATA 记录；未重跑 F2 owner evidence（只读证据在 gitignored `artifacts/g4f/`，本线未启动容器）。结论“F2-07 的实质结论仍可由 F6 summary 与独立 Tool run 验证”沿用历史复核，本线未独立重跑。
- **影响**：逐行 evidence path 检查失败 1 处，影响矩阵“可复核性”而非结论实质；F2-07 的 pass 结论有替代证据支持。
- **建议**：**FIX（文档/证据路径层）** —— 在后续矩阵修订或 Packet v2.1 中修正路径，并加“evidence path 存在性 lint”。**不得**静默改写冻结矩阵字节；应通过 append-only errata 或新版本矩阵修正。
- **维护者决策（留空）**：☐ 接受“结论有替代证据”并推迟路径修正　☐ 要求下一版修正　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：无硬前置（不阻断 H0/H1）；若矩阵作为 G4-H0 交付证据，需在 README/索引注明该路径勘误，避免 Reviewer 按错路径复核失败。

### P2-03 — G4-A a12 并发 consume 错误码竞态（loser 可能 `AUTHORIZATION_USE_RECORD_INVALID` 而非 `AUTHORIZATION_REPLAYED`）

- **finding_id**：`P2-03`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:292`（R8）、`:340`；`docs/M0_G4F_REVIEW_ERRATA.md:132`、`:152-158`（§4.3 特别记录）；测试：`tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one`（Reviewer 独立循环 2/30 失败、full-host 2/2 失败）。
- **本线复核状态**：**NOT_RUN / UNVERIFIED（本线）** —— 代码修复由 fix agent 负责；截至本文件采集时点（2026-11-19T17:5xZ），fix agent 工作树 `worktrees/m0-g4h0-fix/docs/g4h0/` 下**尚未出现** `P2_FIX_REPORT.md`（只读 `ls` 观察），该修复**未集成到本分支**。本线不声称修复完成，不代签。
- **影响**：安全姿态 **fail-closed**：恰好一个 consume 成功，无发送/计费/双消费；但错误码分类不稳定，会使并发负例测试偶发失败、证据不可重复，掩盖真实的 replay 语义问题。
- **建议**：**FIX（G4-H1 前）** —— 采用原子发布（临时文件 + `link`/`rename`）或有界读取重试，使 loser 稳定返回 `AUTHORIZATION_REPLAYED`；补 2 进程/≥30 轮并发稳定性回归；**不得**放宽 fail-closed 或删除并发测试。修复证据以 `docs/g4h0/P2_FIX_REPORT.md` 为准（由 fix agent 产出），**本 Agent 不代签 ACCEPT**。
- **维护者决策（留空）**：☐ 要求修复后独立复测（推荐）　☐ 接受 fail-closed 残余（需写明理由与 H1 前复核计划）　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：G4-H1 前完成修复 **并**由独立 Reviewer 复测：2 进程/≥30 轮中恰好一次成功、loser 错误码稳定为 replay 类、0 发送/0 计费/0 双消费；修复不得降低授权严格性。

### P2-04 — `tests/security/test_scan_git_secrets.py` 既有 F841（`material` 未使用）

- **finding_id**：`P2-04`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:300`（R8 Ruff）、`:341`；`docs/M0_G4F_REVIEW_ERRATA.md:133`；`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:126`（F6-06）。
- **本线复核状态**：**PARTIAL** —— 本线未重跑 Ruff（host 无直接 `ruff`，仅 `uv` 环境可见）；引用历史复核结论。测试文件存在且属 F1 归档测试。
- **影响**：纯 lint/可维护性问题；不影响 scanner 行为、不影响任何安全门；product + G4-F 测试 scope 的 Ruff 曾 PASS。
- **建议**：**FIX（低风险、可随时做）**；若为本轮冻结避让，可 **ACCEPT** 并在后续提交清理（不得顺带改断言）。
- **维护者决策（留空）**：☐ ACCEPT 并安排后续清理　☐ 要求本轮修复　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：无硬前置；修复时不得改变 scanner 检测行为或测试语义。

### P2-05 — F5 `timeout-pre-send` 无 `dispatch-window.jsonl` 记录（观察缺口）

- **finding_id**：`P2-05`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:212`（R5）、`:342`；`docs/M0_G4F_REVIEW_ERRATA.md:134`、`:163`；`docs/M0_G4F_F5_REPORT.md:299`（F5-R4）。
- **本线复核状态**：**PARTIAL** —— 本线未重跑 F5 L2 容器 case（无容器执行）；引用历史证据：0 reservation/attempt/Fake 的 DB 证据 + DSH error 仍支持“未发送”结论。
- **影响**：窗口观察不完整，会使“pre-send 阶段从未发送”依赖旁证；**不改变**本轮“无发送/无计费”结论，也不改变 fail-closed 行为。
- **建议**：**FIX（观察性，建议 H1 前）** —— 在 dispatch-window 中记录 pre-send 拒绝/超时事件（需要改动产品路径时按小补丁+独立 Review 流程）；若不做，则 **ACCEPT** 为已知观察缺口并在 G4-H1 事故分析中注明“以 DB 0 行/Fake 0 为证据”。
- **维护者决策（留空）**：☐ 接受观察缺口　☐ 要求在指定版本修复　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：若接受残余，G4-H1 的窗口审计不得声称“所有拒绝/超时都有 dispatch-window 记录”；需保留 DB/Fake 旁证作为替代证据。

### P2-06 — F5 recovery 将 revocation attempt reason 重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID`

- **finding_id**：`P2-06`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:211`（R5）、`:343`；`docs/M0_G4F_REVIEW_ERRATA.md:135`、`:164`；`docs/M0_G4F_F5_REPORT.md:300`（F5-R5）。
- **本线复核状态**：**PARTIAL** —— 未重跑 F5 L2；引用历史复核：状态/held 保守、gate journal 与 dispatch-window 保留原始 `RUN_AUTHORIZATION_REVOKED`，无重发/双结算。
- **影响**：恢复路径的 attempt reason 与实际撤销原因不一致，**不会**放宽 fail-closed，但会误导事故分析/审计归因（把“撤销”误读为“receipt schema 无效”）。
- **建议**：**FIX（G4-H1 前，建议）** —— 恢复流程保留或映射原始原因；错误分类与修复过程都必须保持 `SETTLEMENT_UNCERTAIN`/held>0 的保守语义。若不修，**ACCEPT** 时须声明“gate journal/dispatch-window 为原因权威”。
- **维护者决策（留空）**：☐ 要求修复　☐ 接受残余（指定权威证据源）　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：事故 Runbook 必须规定“恢复原因以 gate journal/dispatch-window 为准”；修复不得引入自动重试或放宽 fail-closed。

### P2-07 — Packet `env/zero-key.json` 只列 1/4 LiveGate reasons

- **finding_id**：`P2-07`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:76`（§2.2）、`:344`；`docs/M0_G4F_REVIEW_ERRATA.md:136`、`:165`；本线实测：v1 `env/zero-key.json` 1 项 vs manifest/review 4 项；**v2 仍为 1 项**（`BASELINE.md` §3.3 限制 3）。
- **本线复核状态**：**VERIFIED（问题存在）** —— 在 v1 与 v2 上都实测到 1/4；二者 `live_gate` 均为 `BLOCKED`。
- **影响**：证据一致性瑕疵，可能让读者误以为只有 1 条阻塞原因；不改变 BLOCKED 事实，但削弱“证据包自洽”可信度。
- **建议**：**FIX（下一版 Packet/证据生成器）** —— 统一 `env/zero-key.json` 与 manifest/`review/livegate.json` 的 reasons（4 项）来源；v1 不原地改。若仅为本轮收口，可 **ACCEPT** 并在 errata 中注明“以 manifest/review 为准”。
- **维护者决策（留空）**：☐ 接受并注明权威源　☐ 要求下一版修复　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：无硬前置；任何引用 zero-key 证据的场合必须同时引用 manifest/review 4 项 reasons。

### P2-08 — Host full 失败集合与 Owner 归因不同（run2 1352/4/1 但 a12 替换 target-profile）

- **finding_id**：`P2-08`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:291`（R8.1）、`:345`；`docs/M0_G4F_REVIEW_ERRATA.md:137`、`:166`。
- **本线复核状态**：**PARTIAL** —— 本线未重跑 full host suite（本阶段无 src 变更）；引用历史复核：run1 1351/5/1、run2 1352/4/1，计数复现、失败集合不同。
- **影响**：失败归因不可复用；其中 a12 归 P2-03，target-profile 是独立 worktree `config` mode（0644）环境差异，非产品缺陷。
- **建议**：**ACCEPT（作为环境类归因记录）** + 流程改进：归档脚本固定 `config` 权限（`chmod 0444`）与 clean worktree 前置，避免同类环境差异混入失败集合；不要把不同失败集合写成同一归因。
- **维护者决策（留空）**：☐ 接受环境类归因　☐ 要求补齐固定环境的可复现脚本　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：无硬前置；后续回归报告必须同时给出“计数 + 失败集合 + 环境模式”，不得只报计数。

---

## 2. DSH merged Registry / E5-P04

### R-REG-01 — DSH 无权威 merged tool registry/schema 导出；E5-P04 与矩阵 F2-08 维持 UNVERIFIED

- **finding_id**：`DSH-REGISTRY/E5-P04`（对应 `F2-08`、`B03`）
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:238`（E5 两列）、`:353`（§12.3）；冻结矩阵 `…Matrix_v1.0.csv:14`（F2-08 行，UNVERIFIED）；`docs/M0_G4F_F2_REPORT.md:14`、`:27`、`:314-327`；`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:18`、`:45`、`:52`、`:126`、`:153`；`docs/M0_G4F_HUMAN_HANDOFF.md:24`（H-10）；`docs/E5_PRELIVE_NO_KEY_REPORT.md:41`（E5-P04）。
- **本线复核状态**：**UNVERIFIED（引用）** —— 本线未也不应声称拥有 DSH 权威 registry；本阶段未启动 DSH 会话。
- **影响**：无法证明 DSH 实际 merged/有效工具面**只含** `skill_lookup`，也无法排除未来配置/动态注册引入危险工具（Shell/代码执行/上传）。补偿控制是 Controller 的 **per-dispatch 严格白名单**（route/model、tool name+schema、重复 tool、message tool-call/addition/removal、purpose、origin 均在 Reserve/Claim 之前校验；`REVIEW_G4F_INDEPENDENT.md:100`、`:145-147`）。
- **建议**：**ACCEPT-with-compensating-control（仅 G4-H0）** —— H0 阶段可带此残余，但必须由维护者/安全 Reviewer 明确签收“无权威 registry 导出 + per-dispatch 白名单兜底”；**BLOCK** 在 E5-PreLive Full / G5 / Live：除非 DSH 提供权威导出，或人类明确接受残余并写入事故/变更流程。**不得**把 subset PASS 冒充 E5-P04 PASS。
- **维护者决策（留空）**：☐ 接受残余 + 白名单补偿控制　☐ 要求 DSH 权威 registry 导出后再评估　☐ 其它：____________　签核人/日期（Security Reviewer 联签）：__________________
- **部署前置条件**：① Controller 白名单保持 `{skill_lookup}` 且与实际 per-dispatch surface 严格一致；② 任何 profile/config/插件/运行时变更都使该结论失效并需重新验证；③ E5-P04 在 E5-Full 矩阵中保持 UNVERIFIED；④ 禁止任何“registry 已证明只有 skill_lookup”的表述。

---

## 3. P2-RUN-IDENTITY / P2-USERNS / P2-DISK

### R-ID-01 — P2-RUN-IDENTITY：`SO_PEERCRED` 只鉴别 UID，不是 per-run token

- **finding_id**：`P2-RUN-IDENTITY`
- **证据来源**：`docs/M0_G4_HUMAN_HANDOFF.md:109-115`（§5.1 三项 P2 签收表，本项行 `:115`）；`docs/M0_G4F_HUMAN_HANDOFF.md:19`（H-05）；`docs/M0_G4F_REVIEW_ERRATA.md:268`（§9 #2）；`docs/M0_G4_FINDINGS_AND_DISPOSITION.md:39`（A-R6）、`:103`（D-R1）、`:159`（P2-RUN-IDENTITY）；`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:138`（P2-4）；`docs/M0_G4_IMPLEMENTATION_REPORT.md:110`、`:207`；DAC 缓解实测见 `docs/REVIEW_G4F_INDEPENDENT.md:138-139`（run 目录 root 0700、文件 0400/0600，宿主同 UID 访问 EACCES）。
- **本线复核状态**：**PARTIAL（引用 + 实测记录存在）** —— 本线未重跑 OS/raw-UDS 双 Principal 攻击（需容器），引用独立复核的 DAC/ENOENT/EACCES 结果。
- **影响**：同 UID 旧 Run/恶意进程**可能**在 mount/DAC 被放宽时连接 Bridge；当前依赖 run 目录权限与 Candidate mount namespace 隔离。若未来把状态目录/文件权限放宽，该残余会升级为真实越权路径。
- **建议**：**ACCEPT-with-conditions（H0）**：明确签收“per-run 身份未实现，依赖 DAC/mount 隔离”；**FIX（H1 前）**：加 per-run capability/独立 UID（或等价一次性 token 绑定），并重新取证；**BLOCK** 多 Run/多租户或权限放宽场景。
- **维护者决策（留空）**：☐ 接受现状残余（附条件）　☐ 另立 per-run 身份工作项　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：run state 目录保持 root `0700`、文件 `0400/0600`，不允许 Candidate/同 UID 写入；不得以“目录名随机”替代身份；若权限模型变化必须重新做 OS 负例。

### R-NS-01 — P2-USERNS：内核允许嵌套 user namespace

- **finding_id**：`P2-USERNS`
- **证据来源**：`docs/M0_G4_HUMAN_HANDOFF.md:109-115`（本项行 `:114`）；`docs/M0_G4F_HUMAN_HANDOFF.md:20`（H-06）；`docs/M0_G4F_REVIEW_ERRATA.md:268`；`docs/M0_G4_FINDINGS_AND_DISPOSITION.md:158`；`docs/M0_G4_00_BASELINE.md:321`；`docs/M0_G4_IMPLEMENTATION_REPORT.md:110`。
- **本线复核状态**：**PARTIAL（引用）** —— 本线未重跑内核/容器负例；当前容器配置有 `--cap-drop ALL`、`no-new-privileges`、seccomp、`--uidmap 0:65534:1` 等缓解（`REVIEW_G4F_INDEPENDENT.md:125`、`:136-139`），但未做嵌套 userns 逃逸验证。
- **影响**：增加内核攻击面；在宿主内核/容器运行时存在漏洞时，隔离强度低于“禁止 userns”的基线。本轮无 Key/无真实数据，影响有限；真实部署后风险不可忽略。
- **建议**：**ACCEPT-with-conditions（H0）**：签收内核攻击面 + 依赖固定内核/运行时与补丁策略；**FIX（H1 前）**：选择 seccomp/禁嵌套 userns 策略或明确威胁模型接受；**BLOCK** 生产多租户。
- **维护者决策（留空）**：☐ 接受并固定内核/运行时策略　☐ 要求禁 userns/加 seccomp 后重新取证　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：固定 rootfs/deps/stage/内核版本；部署文档必须写明“未实现 userns 逃逸防护”；变更内核/运行时即失效重审。

### R-DISK-01 — P2-DISK：Candidate `/work/session` 是 host bind mount，无磁盘硬配额

- **finding_id**：`P2-DISK`
- **证据来源**：`docs/M0_G4_HUMAN_HANDOFF.md:109-115`（本项行 `:113`）；`docs/M0_G4F_HUMAN_HANDOFF.md:20`（H-06）；`docs/M0_G4F_REVIEW_ERRATA.md:268`；`docs/M0_G4_FINDINGS_AND_DISPOSITION.md:157`；`docs/M0_G4_00_BASELINE.md:320`。
- **本线复核状态**：**PARTIAL（引用）** —— 本线未做磁盘配额/DoS 实测。
- **影响**：候选会话可写满 host 磁盘（DoS/证据破坏），影响可信运行环境；不直接影响授权/发送路径，但会破坏审计与恢复。
- **建议**：**FIX（真实/长期运行前）** —— 配额/独立文件系统/写入上限；**ACCEPT-with-monitor（H0 合成）**：本轮 synthetic 会话、无真实用户数据，接受并监控 session 目录大小；**BLOCK** 真实凭据长期运行。
- **维护者决策（留空）**：☐ 接受并加监控　☐ 要求配额/隔离后重新取证　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：G4-H1 前给出 session 目录配额与超额 fail-closed 行为；事故 Runbook 包含磁盘耗尽处置；不得在未加配额时进行长时间真实运行。

---

## 4. Crash Hooks / 撤销链

### R-HOOK-01 — 产品内 test-only crash/delay hooks 仍存在（`G3B_TEST_MODE` 等）

- **finding_id**：`P2-3 / F4/F5 TEST-HOOKS`
- **证据来源**：`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:98`（F5-R1）、`:103`（F5-R6）、`:137`（P2-3）；`docs/M0_G4F_F4_REPORT.md:162-168`（`G3B_TEST_MODE=1`）、`:316-318`；`docs/M0_G4F_F5_REPORT.md:296`（F5-R1）、`:301`（F5-R6）；`docs/M0_G4F_HUMAN_HANDOFF.md:21`（H-07）。
- **本线复核状态**：**PARTIAL（引用）** —— 本线未审计全部 hook 触发路径（需源码级 review + 定向测试），仅确认文档披露：hook 只由 launcher 可信 env 触发、未新增生产后门。
- **影响**：可信产品代码保留测试钩子；若 env 控制被误用/泄漏，可制造 crash/delay，影响恢复语义与可用性；不直接导致未授权发送。
- **建议**：**FIX（G4-H1 前，建议）**：移除或编译期剔除 test-only hooks（或改为独立测试构建）；若保留，必须 **ACCEPT** 并证明“Candidate 无法触发、仅 launcher 可信 env 可触发”，列入 H1 审计清单。**BLOCK** 任何真实部署中保留未审计 hook。
- **维护者决策（留空）**：☐ 要求 H1 前移除/隔离　☐ 接受并附触发条件证明　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：hook 清单 + 触发路径负例 + env 白名单证据；移除/隔离后需回归 F4/F5 相关恢复语义。

### R-REV-01 — F5-R2：撤销文档 root-owned，但无独立签名/审计链

- **finding_id**：`F5-R2`
- **证据来源**：`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:99`；`docs/M0_G4F_F5_REPORT.md:297`；`docs/M0_G4F_HUMAN_HANDOFF.md:22`（H-08）；相关恢复语义 `:300`（F5-R5）。
- **本线复核状态**：**PARTIAL（引用）** —— 未重跑 F5；文档层面确认“与 policy/admission 同信任边界、非新权威、无独立签名”。
- **影响**：撤销输入与 policy/admission 同属 root-owned 信任域；无法独立证明“撤销来自被授权的人类控制面”，也无法检测 root 域内的静默改写（有 root 即可改一切，故属信任边界内残余）。
- **建议**：**ACCEPT-with-conditions（H0）**：在信任根/Key Broker 未部署前，撤销文档与 policy 同边界是已知残余；**FIX（H1 前/真实控制面）**：要求签名/审计链或纳入人类信任根部署；**BLOCK** 声称“独立可验证撤销”。
- **维护者决策（留空）**：☐ 接受同边界残余　☐ 要求签名/审计链　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：G4-H1 Runbook 必须写明“撤销文档非独立签名权威”；任何真实撤销演练需记录 root 域变更审计；不得把本项写成已独立验证。

### R-REV-02 — F5-R6：crash 使用 `os._exit(97)` test-only hook，外部 SIGKILL 窗口未枚举

- **finding_id**：`F5-R6`
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:356`（§12.6）；`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:103`；`docs/M0_G4F_F5_REPORT.md:301`。
- **本线复核状态**：**PARTIAL（引用）** —— 未重跑 F5 crash 窗口；确认历史结论：使用产品既有 hook，非外部 SIGKILL，纳秒窗口未枚举。
- **影响**：真实外部 SIGKILL/断电等时序窗口未覆盖；当前恢复语义保持 `PENDING`/`SETTLEMENT_UNCERTAIN` 保守，未发现双发送/双结算，但**不能承诺 exactly-once**。
- **建议**：**ACCEPT（H0）** + 明确不承诺 exactly-once；**FIX（可选，H1 前）**：补外部 SIGKILL/窗口枚举测试；任何“恰好一次”表述必须删除。
- **维护者决策（留空）**：☐ 接受不承诺 exactly-once　☐ 要求补测　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：H1/事故 Runbook 必须定义 `SETTLEMENT_UNCERTAIN` 的人工对账流程；不得自动重试未知计费状态；不得对外承诺 exactly-once。

---

## 5. F4 candidate-crash + live Controller 组合

### R-F4-01 — `F4-R2`：candidate crash + live Controller 组合未验证；`F4-R1` 字节级 context 未验证

- **finding_id**：`F4-R2`（关联 `F4-R1`、矩阵 `F4-06`）
- **证据来源**：`docs/REVIEW_G4F_INDEPENDENT.md:188`（§6.3）、`:354`（§12.4）；冻结矩阵 `…Matrix_v1.0.csv:28`（F4-06 行，UNVERIFIED）；`docs/M0_G4F_HUMAN_HANDOFF.md:23`（H-09）；`docs/M0_G4F_F4_REPORT.md:28`、`:316-318`；`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md:83`。
- **本线复核状态**：**UNVERIFIED（引用）** —— 本线未重跑 F4 L2（需真实双 Principal 容器）；确认文档口径：crash-resume 负例只证明“无存活 Controller 时 resume 不重发”，**未**覆盖“Candidate 在 provider 请求中途崩溃且 Controller 继续服务/自动重试”的子场景；也不做字节级 context 包含证明（只做 semantic digest/length）。
- **影响**：不能把 crash-resume 的成功概括为全部恢复语义；`DSH 是否会对未完成 Candidate turn 自动重试/重发` 未知，直接影响“重复计费/重复发送”风险判断。当前证据只能说明：无存活 Controller 时不重发，且恢复保持保守状态。
- **建议**：**FIX/ADD TEST（G4-H1 前，建议，成本可控）**或在 H0 明确登记残余：补“Candidate crash + live Controller”子场景（含是否自动重试、是否双 Fake、账本 held/known 语义）；**BLOCK** 任何“恰好一次/自动重试安全”主张与依赖该假设的预算承诺。矩阵 `F4-06` 在补测前保持 `UNVERIFIED`。
- **维护者决策（留空）**：☐ 要求 H1 前补测　☐ 接受残余（不承诺恢复语义，需人工对账）　☐ 其它：____________　签核人/日期：__________________
- **部署前置条件**：G4-H1 Runbook 必须写“candidate crash + live Controller 未验证；未知计费状态保守处理、人工对账”；不得把本项转写成 PASS；若补测，需独立复现。

---

## 6. 汇总处置矩阵（Agent 建议，非签核）

| finding | 建议 | G4-H0 | G4-H1 前 | G5 / Live 前 | 人类签核 |
|---|---|---|---|---|---|
| P2-01 Packet sidecar 漂移 | FIX（新版本） | 需披露/接受某版本 | 必须有被接受的 Packet | 同左 | **必须** |
| P2-02 F2-07 路径 | FIX（文档） | 可接受（有替代证据） | 建议修正 | 无硬阻断 | 必须 |
| P2-03 A12 并发错误码 | FIX | 可带残余（fail-closed） | **建议必须修复+独立复测** | 必须 | **必须** |
| P2-04 F841 lint | FIX/ACCEPT | 可接受 | 可接受 | 无硬阻断 | 必须（知会） |
| P2-05 timeout-pre-send 观察缺口 | FIX/ACCEPT | 可接受（有旁证） | 建议修复 | 事故分析需注明 | 必须 |
| P2-06 recovery reason 重写 | FIX | 可带残余（conservative） | 建议修复 | 事故分析必须用 gate journal | 必须 |
| P2-07 zero-key 1/4 reasons | FIX（下一版） | 可接受（BLOCKED 不变） | 建议修复 | 无硬阻断 | 必须（知会） |
| P2-08 host 失败集合归因 | ACCEPT | 可接受 | 可接受（需固定环境） | 无硬阻断 | 必须（知会） |
| DSH merged registry / E5-P04 | ACCEPT+补偿控制 / BLOCK | 可带残余 | 需签收残余 | **BLOCK**（E5-Full/G5） | **必须 + Security Reviewer** |
| P2-RUN-IDENTITY | ACCEPT+条件 / FIX | 附条件接受 | 建议 FIX | **BLOCK**（多 Run/生产） | **必须** |
| P2-USERNS | ACCEPT+条件 / FIX | 附条件接受 | 建议 FIX | **BLOCK**（生产多租户） | **必须** |
| P2-DISK | FIX/ACCEPT+监控 | 可接受（synthetic） | 需配额 | **BLOCK**（真实长期） | **必须** |
| Test-only crash/delay hooks | FIX / ACCEPT+证明 | 可接受（仅 trusted env） | 建议 FIX/隔离 | **BLOCK**（未审计 hook） | **必须** |
| F5-R2 撤销链无签名 | ACCEPT+条件 / FIX | 附条件接受 | 建议 FIX | **BLOCK**（声称独立撤销） | **必须** |
| F5-R6 外部 SIGKILL 窗口 | ACCEPT | 可接受（不承诺 exactly-once） | 可选补测 | 不得承诺 exactly-once | 必须 |
| F4 candidate-crash + live Controller | FIX/补测 / 登记残余 | 可登记 UNVERIFIED | 建议补测 | 不得承诺恢复语义 | **必须** |

> 上表“G4-H0 可接受”仅表示**可由维护者选择接受并写入披露**，不表示本 Agent 已接受或已通过；任何 ACCEPT 必须由维护者亲自签署并记录范围/失效条件。

---

## 7. 维护者决策页（留空，禁止 Agent 填写）

```text
审阅人 / Maintainer:                     ____________________
独立 Security Reviewer（如需）:          ____________________
日期（UTC）:                             ____________________
审阅的冻结 SHA / Packet 版本:            ____________________

逐项决策（ACCEPT / FIX / BLOCK / 其它 + 理由）：
P2-01: ____________________   P2-02: ____________________   P2-03: ____________________
P2-04: ____________________   P2-05: ____________________   P2-06: ____________________
P2-07: ____________________   P2-08: ____________________
DSH-Registry/E5-P04: ____________________
P2-RUN-IDENTITY: ____________________   P2-USERNS: ____________________   P2-DISK: ____________________
Test-hooks: ____________________   F5-R2: ____________________   F5-R6: ____________________
F4 candidate-crash + live Controller: ____________________

接受范围与失效条件:                      ____________________
是否进入 G4-H1 / G5:                     NOT AUTHORIZED BY THIS DOCUMENT
签名 / 审批编号:                         ____________________
```

---

## 8. 参考与证据

- 冻结复核与 errata：`docs/REVIEW_G4F_INDEPENDENT.md`、`docs/M0_G4F_REVIEW_ERRATA.md`（行号见各条）。
- 人类交接：`docs/M0_G4F_HUMAN_HANDOFF.md`（H-01..H-12）、`docs/M0_G4_HUMAN_HANDOFF.md`（G4-H-01..06、P2 签收、E5 Full）。
- findings 明细：`docs/M0_G4F_FINDINGS_AND_DISPOSITION.md`；F2/F4/F5 报告：`docs/M0_G4F_F2_REPORT.md`、`docs/M0_G4F_F4_REPORT.md`、`docs/M0_G4F_F5_REPORT.md`；E5：`docs/E5_PRELIVE_NO_KEY_REPORT.md`。
- 冻结矩阵：`docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`（46 行：43 PASS / 2 UNVERIFIED / 1 BLOCKED；`F2-08`:14、`F2-07`:13、`F4-06`:28、`E5-FULL`:47）。
- 本线基线证据：`docs/g4h0/BASELINE.md`、`docs/g4h0/evidence/`（v1 校验、v2 重建与哈希清单、env/工具/负例日志）。
- P2-03..P2-06 的代码修复证据**不在本文件**：以 fix agent 的 `docs/g4h0/P2_FIX_REPORT.md` 为准（本文件采集时点尚未集成到本分支；本 Agent 不代签、不声称修复完成）。

> 结束状态：以上全部为 **PENDING MAINTAINER / INDEPENDENT REVIEWER DECISION**；本文件不授权 G4-H、G5、G6、Live 或 `M0_GO`。
