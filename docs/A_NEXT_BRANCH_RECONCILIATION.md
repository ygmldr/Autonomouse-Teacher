# A-NEXT — 分支仲裁与逐函数行为矩阵（A0-01，A-PR0）

- **文档 ID**：`A-NEXT-BRANCH-RECONCILIATION-v1`
- **生成者**：A-PR0 Implementer-Docs（子 Agent；非 Lead、非 Independent Reviewer）
- **生成时间（UTC）**：`2026-11-20T19:36Z`–`19:50Z`
- **输入**：`/root/handoffs/AT_LeadA_G4R_Next/`（START_HERE、01_LEADA_AGENT_HANDOFF、AUDIT_REQUESTS、
  COMMON_REVIEW_AND_ROADMAP、TEST_EVIDENCE_MATRIX.csv 全部已读）；`work/g4r`、`work/m0-g4h0` 分支（fetch 后实测）；
  `docs/REVIEW_G4R_INDEPENDENT.md`、`docs/M0_G4R_00_BASELINE.md`、`docs/M0_G4R_PACKET_SUMMARY.md`、
  `docs/g4h0/INDEPENDENT_REVIEW.md`（后者只读引用 m0 分支）。
- **性质**：**只读分叉审计 + 行为矩阵 + 建议**。不是 PASS、不是合并授权、不是 Reviewer 结论；
  代码合并/吸收决定权在维护者与独立 Reviewer。0 真实 Key/Provider/HTTP；未在本轮重跑测试（只读 Git 审计）。
- **基线**：`main=3e7afee…`；canonical 候选 `work/g4r=fd1d3a6…`（impl `d33e0aa…`）；
  并行线 `work/m0-g4h0=15c5a08…`。

## 1. 分叉身份与 merge-base（实测）

| 检查 | 结果 |
|---|---|
| `git merge-base main work/g4r` | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| `git merge-base main work/m0-g4h0` | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| `git merge-base work/g4r work/m0-g4h0` | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| 提交数 `main..work/g4r` / `main..work/m0-g4h0` | **28** / **20** |
| 结论 | 两条线是**同源、平行、互不包含**的分支；H0 不是 G4-R 的后续提交，G4-R 也不是 H0 的后续提交 |

`work/g4r` 尖端链（实测）：`main 3e7afee → PR-R1..R4 合并 → impl freeze d33e0aa → docs 合并 bc08bdd/64522d9 →
Review+errata 合并 9768933/fd1d3a6`。`work/m0-g4h0` 尖端链（实测）：`… → docs g4h0 → P2 fixes（87aa52f 等）+
review/addendum/errata 合并 → 15c5a08`。

## 2. 文件级差异（`git diff --name-status` / `--stat` 实测）

### 2.1 `work/g4r`（相对 main）

| 范围 | 统计 | 组成 |
|---|---|---|
| impl freeze `3e7afee..d33e0aa` | **31 files / +6529 / −39**（28 A + 3 M） | M：`src/autoteacher_m0/bridge/controller.py`、`src/autoteacher_m0/security/authorization.py`、`tests/security/test_scan_git_secrets.py`（仅删 1 行）；A：新模块 `src/autoteacher_m0/bridge/{request_lifecycle,recovery_diagnostics}.py`、`scripts/g4r/**`、`tests/g4r_packet/**`、`tests/g4r_registry/**`、`tests/integration/g4r_auth/**`、`tests/integration/g4r_recovery/**`、`docs/M0_G4R_*.md` 与 65 行矩阵 |
| docs/review delta `d33e0aa..fd1d3a6` | **54 files / +4678 / −46** | `docs/REVIEW_G4R_INDEPENDENT.md`、`docs/g4r_review_evidence/**`（43 份）、`scripts/g4r_review/{r_rev2_race_probe,r_rev5_packet_verifier}.py`、`docs/M0_G4R_REVIEW_ERRATA.md`、`docs/M0_G4R_{PACKET_SUMMARY,FINDINGS_AND_DISPOSITION,HUMAN_HANDOFF}.md` 等；**`src/` 与 `tests/` 零 diff**（非 docs 只有 2 个 Reviewer 只读探针脚本） |
| 合计 `main..work/g4r` | 83 files | 28 提交（含 9 个由集成/Review 流程产生的 merge，均属历史、非本轮新增） |

### 2.2 `work/m0-g4h0`（相对 main）

| 统计 | 组成 |
|---|---|
| **90 files / +12226 / −35**（86 A + 4 M） | M：`src/autoteacher_m0/bridge/controller.py`、`src/autoteacher_m0/security/authorization.py`、`tests/integration/g4_f5/g4f5_support.py`、`tests/security/test_scan_git_secrets.py`；A：`docs/g4h0/**`（Runbook/信任边界/Provider 研究/Review/证据等）、`tests/integration/g4_h0/**`、`tests/integration/g4_f5/**`、`scripts/g4h0/**`、`scripts/g4h0-review/**`；**无新增 src 模块** |

### 2.3 两分支交集与分歧

| 项 | 结果 |
|---|---|
| 同被两分支修改的文件 | **仅 3 个**：`src/autoteacher_m0/bridge/controller.py`、`src/autoteacher_m0/security/authorization.py`、`tests/security/test_scan_git_secrets.py`（第三个两边是同一处 1 行删除，实测 `git diff work/m0-g4h0..work/g4r -- tests/security/` 为空） |
| 真正的语义分歧面 | **2 个安全核心文件**：`git diff work/m0-g4h0..work/g4r -- controller.py authorization.py` = **483 insertions / 177 deletions** |
| 仅 G4-R 的文件 / 仅 H0 的文件 | 80 / 87（各自新增的 tests/scripts/docs/新模块；`work/g4r..work/m0-g4h0` 全量显示 164 files 是两侧新增文件各自缺失的并集，不是 164 个冲突） |
| 生效先决 | 两分支都改同一 `autoteacher_m0` 包、同一 `security.authorization`/`bridge.controller` 导入面；H0 的 P2 修复与其 `request-lifecycle` 观测补丁只能在 H0 的旧结构上生效；G4-R 的新模块（`request_lifecycle`/`recovery_diagnostics`/`dispatch_audit` 接线）只能在 G4-R 结构上生效。**任何跨分支 cherry-pick 都必须重写调用点，且没有 Reviewer 覆盖整合后的组合** |

## 3. 逐函数行为矩阵（canonical = `work/g4r` impl `d33e0aa` 为基准候选）

> 判定词：`相同` = 逐字节/逐行为无差异；`G4-R 更强` = G4-R 覆盖了 H0 的已知缺口/更严格 fail-closed；
> `同等缺口` = 两边都缺（不得据此宣称解决）。所有“回归验证”均指**必须由独立 Reviewer 在目标分支重跑**的测试。

| # | 行为 | H0（`work/m0-g4h0@15c5a08`） | G4-R（`work/g4r@fd1d3a6`，impl `d33e0aa`） | Canonical 判定 | 回归验证（必须运行） |
|---|---|---|---|---|---|
| 1 | 授权验证（strict JSON/Ed25519/5 根绑定/route/tools/budget/deadline/撤销/时间窗） | 与 G4-R 相同（`git diff` 在 `load_execution_authorization`/`ExpectedBindings`/`binding_drift`/`parse_budget_policy` 段**无 hunk**） | 同左（继承 G4-A 冻结实现；`_trusted_directory`/`_external_regular_file` 亦无 diff） | **相同 → G4-R 继承** | `pytest tests/integration/g4_a -q`（A01..A15）；Reviewer R-REV1 `r_rev1_protected_frozen_final.log` |
| 2 | **consume / 单次消费原子发布** | `_publish_use_record`：同目录 temp（0600，`O_WRONLY\|O_CREAT\|O_EXCL\|O_NOFOLLOW\|O_CLOEXEC`）→ 写全 body → `fsync(fd)` → `os.link`；**无目录 fsync**；读 retry=20；无 temp 上限/TTL 回收；读检查 regular/size（**无 nlink>2 / group-other-writable 拒绝**）；无 `DURABILITY_UNKNOWN` | 拆分为 `_use_record_temp_path/_open_use_record_temp/_write_use_record_body/_link_use_record_no_replace/_fsync_directory/_safe_unlink_temp/_count_use_log_entries/_reap_stale_use_record_temps`；link 成功后 **`_fsync_directory`**；目录 fsync 失败 → `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` **fail-closed**（use 已花、不得返回成功/不得发送）；`MAX_USE_RECORD_TEMPS=256` + TTL 300s + 容量统计排除 temp；读增加 **nlink>2 / group-other-writable 拒绝**；读 retry=5；link 不可用/跨设备 `WRITE_FAILED` 且无写 final 回退 | **G4-R 更强（覆盖 H0 F-02）**；残余：P2-01 body `authorization_id` 未与路径交叉校验（两分支同等缺口，G4-R Reviewer 已记为 P2-01 OPEN） | `pytest tests/integration/g4r_auth -q`（R1-01..06：线程/进程/epoch/腐败/crash 各窗口/dir-fsync EIO/link EOPNOTSUPP/hardlink/symlink/temp cap）；Reviewer `scripts/g4r_review/r_rev2_race_probe.py` |
| 3 | 目录权限（trusted approval/keys/revocation/use-log 目录） | `_trusted_directory`/`_require_private_node`/`_external_regular_file`：仓库外、非 symlink、owner/mode、尺寸上限、`O_NOFOLLOW`+`fstat` | 与 H0 相同（无 diff） | **相同 → G4-R 继承** | `tests/integration/g4_a/test_a07_trusted_file_boundary.py`、`test_a14_key_registration_rotation.py`；R-REV1 受保护件复核 |
| 4 | run epoch（replay vs 跨 run/epoch） | consume 内 `_IDENTIFIER` 校验 `run_epoch`；同 epoch → `AUTHORIZATION_REPLAYED`，异 epoch → `AUTHORIZATION_EPOCH_MISMATCH`；无跨 epoch 复用 | 同左（该段逻辑相同）；新增 R1-03/R1-05 跨 epoch/crash 测试与 Reviewer 探针 | **相同语义；G4-R 测试更强** | `pytest tests/integration/g4r_auth -q`（R1-03/R1-05）；`tests/integration/g4_a/test_a08*`、`test_a12_replay_epoch.py`；Reviewer R-REV2 跨 epoch 8/8 |
| 5 | 取消 / 截止时间 | `cancel()` 有界 per-transport registry（pre-start cancel 记住、terminal 重复 no-op）+ `_checkpoint`；**P2-05 补丁** `_observe_envelope_deadline` 仅 observation-only（`dispatch_seq=None`、`observation_only=True`、`reserved/dispatched` 快照），不参与 allow/deny | `cancel()`/`_checkpoint` 逐字节相同；新增 `request_lifecycle.py`（`m0.g4r.request-lifecycle.v1`）在 transport 层记录 `received/controller_entered/deadline_before_controller/protocol_rejected` 等；dispatch-window 仍只记真实 dispatch；rejection 行 `dispatch_seq=None` + `request_level_only=True`；无伪造 dispatch_seq | **G4-R 更强（观测同步、可验证；allow/deny 语义不变）** | `pytest tests/integration/g4r_recovery -q`（R2-01..04）；Reviewer R-REV3（L1 PASS；L2 `NOT_RUN`） |
| 6 | 恢复 cause / recovery 观测 | `_preserved_uncertain_reason()`：保留原 reason 并追加 `\|RECOVERY_EVIDENCE:<fallback>`，**≤256 字符截断**（H0 Reviewer 记为 F-05 nit）；状态/held 语义不变 | 新模块 `recovery_diagnostics.py`（append-only JSONL）：`primary_cause` 封闭枚举（`RUN_AUTHORIZATION_REVOKED` 精确 + `REVOKED_PRE_SEND:` 前缀）且 Broker `PENDING` 才保留；Broker `OK/FAILED` 终态权威；观测失败隔离、不改变恢复判定/held/不重发 | **G4-R 更强（结构化、无截断拼接）** | `pytest tests/integration/g4r_recovery/test_r2_recovery_semantics.py -q`（R2-05..09）；R-REV3 原始 JSONL 独立解析 |
| 7 | 审计写入（dispatch-window / lifecycle / observability） | `dispatch_audit` best-effort（不影响 allow/deny）；单通道 dispatch-window + observation-only deadline 行 | 三通道：`request-lifecycle.jsonl` + `dispatch-window.jsonl` + `recovery-diagnostics.jsonl`；`observability_status()` 返回各通道 gap 指示且 `safety_admission_changed=False`（恒定：日志失败只丢证据、不改安全准入） | **G4-R 更强** | `pytest tests/integration/g4r_recovery/test_r2_04_observability_gap.py -q`；R-REV3 |
| 8 | **rootfs 防写（禁止对冻结 rootfs 直接 `--rootfs`）** | **无代码级强制**；H0 分支未涉及该风险 | **无代码级强制**（`git grep rootfs -- src scripts` 只命中历史 G3 脚本；无 `--rootfs` 拦截/副本强制逻辑）；仅 Reviewer P1 结论 + Packet README/limitations 的流程要求（`cp -a` 副本、独占窗口、T0/T1 对比） | **同等缺口（两者都 NOT_IMPLEMENTED）**——不构成选择 G4-R 的理由，必须由 A0-03/A5 新增物理防写与 T0/T1 断言 | 目前无既有测试；A0-03 需新增（见 §7 第 8 行与 `docs/A_NEXT_BASELINE.md` §7） |

## 4. H0 开放 `F-02` 在 G4-R 是否已被覆盖（A-Q5 直接回答）

- **H0 `F-02`**（来自 `docs/g4h0/INDEPENDENT_REVIEW_ADDENDUM.md` 之前的主审 `F-02`）：use record 在
  `os.link` 发布后**未 fsync 父目录** ⇒ 掉电/崩溃后目录项可能未持久化，已返回成功的 consume 在重启后可能
  允许同一授权再次消费（历史语义相同，非回归；LOW）。
- **G4-R 答复：已被覆盖（代码 + 测试 + 独立 Reviewer 复验）**：
  1. 代码：`_fsync_directory(directory)` 在 link 成功后调用；失败 → `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`
     **fail-closed**，use 视为已花、不返回成功、不发送。实测行号：`src/autoteacher_m0/security/authorization.py:918`
     （`_fsync_directory`）、`:1074`（`_link_use_record_no_replace` 调用）、`:1088`（目录 fsync 调用）、
     `:1095`（`DURABILITY_UNKNOWN` 拒绝）。
  2. 测试：`tests/integration/g4r_auth/test_r1_atomic_use_record.py:326`
     （`test_r1_05_crash_after_link_before_dir_fsync_never_double_authorizes`）与 `:345`
     （`test_r1_05_dir_fsync_failure_is_fail_closed_not_success`）；另有 hardlink/symlink/temp 上限等。
  3. 独立复核：Reviewer `R-REV2` 的 dir fsync EIO 用例返回 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`
     fail-closed、final 保留、0 temp、后续 `REPLAYED`（`docs/REVIEW_G4R_INDEPENDENT.md:163` 行）。
     对照：H0 `F-02` 定义见只读引用 `work/m0-g4h0:docs/g4h0/INDEPENDENT_REVIEW.md:325`。
- **残余（不得写成“已彻底解决”）**：真实掉电/跨文件系统/其他 FS 的持久性未穷举（Reviewer 只做 EIO 注入）；
  `nlink==2` 被容忍（crash 后 final+temp 共存）；P2-01 body-id 交叉校验仍 OPEN。
  ⇒ **结论：H0 的 F-02 不构成保留 H0 use-record 实现的理由；G4-R 是该行为的 canonical 实现。**

## 5. 为什么不能盲 merge / cherry-pick

1. **没有线性关系**：两分支同源平行（merge-base = main），不是上下游；`work/g4r` 的 9 个历史 merge 是
   集成/Review 流程产物，不代表可把 H0 直接并入。
2. **核心安全文件双写且实现不兼容**：两分支都改 `authorization.py`/`controller.py`，但 G4-R 把
   use-record 拆成 8 个函数 + 目录 fsync + `DURABILITY_UNKNOWN`，把 P2-05/P2-06 重做为
   `request_lifecycle`/`recovery_diagnostics`；H0 仍是单函数 `_publish_use_record`（无目录 fsync）、
   `_observe_envelope_deadline` observation-only 补丁、`_preserved_uncertain_reason` 字符串拼接。
   Cherry-pick H0 的 P2 修复到 G4-R 会**语义冲突或覆盖 G4-R 的更强实现**（例如回退目录 fsync、
   回退 `DURABILITY_UNKNOWN` fail-closed、把结构化 recovery 诊断改回 256 字符截断）。
3. **Reviewer 证书只覆盖各自冻结对象**：G4-R 的 `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` 覆盖 impl
   `d33e0aa`（+docs 到 `fd1d3a6`）；H0 的 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`（含 addendum F-01 CLOSED）
   覆盖 H0 自身 tip/基线。**没有任何 Reviewer 证书覆盖“G4-R + H0 补丁”的混合体**，合并后的组合必须新审。
4. **测试不可平移**：H0 的 `tests/integration/g4_h0/**` 与 `g4_f5/**` 针对 H0 的旧内部结构
   （单函数发布/observation-only 行）；直接放到 G4-R 上会因实现不同而失去断言意义或制造假绿。
5. **工程风险**：同一 Python 包同一模块的两次独立演化，盲 merge 会产生未测试的 hybrid；且 H0 的
   P2-05/P2-06 目标已被 G4-R R2 以更结构化方式满足，重复吸收只会增加漂移。
6. **规则约束**：交接明确“不可盲 merge 或 cherry-pick H0 实现”；A-PR0 只做仲裁与文档，不做代码合并
   （本任务 0 merge/cherry-pick/push，见 `git rev-list --merges fd1d3a6..HEAD` = 0）。

## 6. Canonical 建议（供维护者/Reviewer 决定，不代签）

**建议：以 `work/g4r`（tip `fd1d3a6`，安全实现冻结 `d33e0aa`，Reviewer 报告
`M0-G4R-INDEPENDENT-REVIEW-v1`）作为 canonical 安全基线**；理由：

- 唯一同时具备：原子单次消费（tmp+fsync+link+**dir fsync**+`DURABILITY_UNKNOWN`）、request-lifecycle 与
  dispatch-window 分离、结构化 recovery first-cause、Packet v2 独立全树复核（R-REV5 PASS）、
  no-key 负例（R-REV7 PASS）。
- H0 的 P2 修复（P2-03 use-record）已被 G4-R R1 以更强机制覆盖；H0 的 P2-05/P2-06 已被 G4-R R2 覆盖；
  H0 的 F-02 在 G4-R 已覆盖（§4）。
- G4-R 的残余已由 Reviewer 明确登记：P2-01/P2-02 OPEN、B03/E5-P04 `UNVERIFIED`、R-REV6 `NOT_RUN`、
  P1 rootfs 环境限制。**canonical 不等于完整通过**。

**H0 仅选择性吸收“已审阅、无 Key 的文档类内容”**（建议清单；全部只读、不改 G4-R 代码）：

| 吸收对象 | 用途 | 生效条件 |
|---|---|---|
| `docs/g4h0/DEPLOYMENT_RUNBOOK.md`、`TRUST_BOUNDARY_DIAGRAM.md`、`HUMAN_SIGNOFF_TEMPLATE.md`、`E5_PRELIVE_FULL_CHECKLIST.md`、`A3_REFS.md`、`ERRATA.md` | A6/G4-H1 决策准备：受信部署/信任边界/签核/E5 清单/引用差异 | 标注“基于 H0 时点”；其中 P2-03/F-02/F-01 状态以 G4-R 当前实现为准，逐条重述 |
| `docs/g4h0/PROVIDER_CONTRACT_DRAFT.md`、`PRICE_AND_USAGE_VERIFICATION.md`、`BILLABLE_PATH_INVENTORY.md`、`A2_SOURCES.md` | 官方 API/价格/Usage 研究快照 | 标注“2026-11-19 研究快照、未获批/无真实调用”；G5 前重新核实 |
| `docs/g4h0/INDEPENDENT_REVIEW.md`、`INDEPENDENT_REVIEW_ADDENDUM.md`、`HUMAN_DECISIONS.md`、`RISK_DISPOSITION.md`、`P2_FIX_REPORT.md`、`BASELINE.md`、`PACKET_SUMMARY.md`、`EVIDENCE_INDEX.md`、`NO_KEY_AND_LIVEGATE_EVIDENCE.md` | H0 的独立复核/风险/修复记录 | 只作 H0 证据；**不得**作为 G4-R 合并审阅结论；P2 状态以 G4-R Reviewer 为准 |
| `docs/g4h0/evidence/**`、`docs/g4h0/review-evidence/**` | H0 原始证据引用 | 只读；不复制为 G4-R 证据；引用时注明 H0 基线 |

**明确不吸收（除非新 Review）**：H0 的 `src/` 改动、`tests/integration/g4_h0/**`、`g4_f5/**`、`scripts/g4h0/**`
（其 P2 实现已被 G4-R 覆盖/取代；测试针对旧内部结构）。任何跨分支代码采纳必须是**新提交 + 独立 Reviewer 重审**。

## 7. 每个行为的回归验证测试清单（在 canonical 分支上执行）

| 行为 | 命令（cwd = canonical worktree，`PYTHONPATH=src`） | 预期 | 状态（本轮） |
|---|---|---|---|
| 授权验证 | `pytest tests/integration/g4_a -q` | 与 G4-A 冻结套件一致（A01..A15） | `NOT_RUN`（本轮未跑；需 Reviewer/CI） |
| consume 原子性 | `pytest tests/integration/g4r_auth -q` | 全绿；R1-01..06 含 crash/dir-fsync/link 负例 | `NOT_RUN`（Owner 报告 26 passed；Reviewer R-REV2 PASS） |
| 目录权限 | `pytest tests/integration/g4_a/test_a07_trusted_file_boundary.py tests/integration/g4_a/test_a14_key_registration_rotation.py -q` | 全绿 | `NOT_RUN` |
| run epoch | `pytest tests/integration/g4r_auth/test_r1_atomic_use_record.py -q`（R1-03/05） + `tests/integration/g4_a/test_a08* test_a12_replay_epoch.py -q` | replay/epoch mismatch 分类稳定 | `NOT_RUN`（Reviewer R-REV2 覆盖子集） |
| 取消/截止 | `pytest tests/integration/g4r_recovery -q` | R2-01..04 全绿；0 伪造 dispatch_seq | `NOT_RUN`（Owner 19 passed；Reviewer R-REV3 部分） |
| 恢复 cause | `pytest tests/integration/g4r_recovery/test_r2_recovery_semantics.py -q` | first_cause 保留、Broker 终态权威 | `NOT_RUN` |
| 审计写入 | `pytest tests/integration/g4r_recovery/test_r2_04_observability_gap.py -q` | gap 非 bypass、`safety_admission_changed=false` | `NOT_RUN` |
| **rootfs 防写** | **尚无测试**；A0-03/A5 需新增：启动/结束 `rootfs` SHA 对比、`--rootfs` 指向冻结目录必须拒绝、`cp -a` 副本强制、失败即 STOP | T0/T1 一致、漂移即 FAIL | **`NOT_RUN`（未实现）** |
| 回归面（host/OCI/Node） | `pytest tests --collect-only -q`；定向套件；Node TAP；Ruff；Scanner | 与 Reviewer R-REV8 一致 | `NOT_RUN`（Reviewer 只做定向；Host full/OCI/Node 未独立执行） |
| Packet/证据完整性 | Reviewer 自建 `scripts/g4r_review/r_rev5_packet_verifier.py` + mutation | 43/0/40/41、11/11 mutation 检出 | `REVIEWER_REPORTED`（R-REV5 PASS） |

## 8. 复现命令（本矩阵的来源）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-baseline"
git fetch --all --prune
git merge-base main work/g4r; git merge-base main work/m0-g4h0; git merge-base work/g4r work/m0-g4h0
git diff --name-status 3e7afee..d33e0aa; git diff --stat 3e7afee..d33e0aa
git diff --name-status d33e0aa..fd1d3a6; git diff --stat d33e0aa..fd1d3a6
git diff --name-status 3e7afee..15c5a08; git diff --stat 3e7afee..15c5a08
git diff --name-only main..work/g4r | sort > /tmp/g4r.txt
git diff --name-only main..work/m0-g4h0 | sort > /tmp/m0.txt
comm -12 /tmp/g4r.txt /tmp/m0.txt                       # 预期 3 个文件
git diff --stat work/m0-g4h0..work/g4r -- src/autoteacher_m0/{bridge/controller.py,security/authorization.py}
git grep -n '_fsync_directory\|DURABILITY_UNKNOWN\|MAX_USE_RECORD_TEMPS' work/g4r -- src/autoteacher_m0/security/authorization.py
git grep -n '_publish_use_record\|_observe_envelope_deadline\|_preserved_uncertain_reason' work/m0-g4h0 -- src/autoteacher_m0
git grep -ln 'rootfs' work/g4r -- src scripts   # 无 --rootfs 防写实现；仅历史 G3 脚本
```

## 9. 残余风险 / 未验证（不写 PASS）

1. **P2-01（use record body `authorization_id` 交叉校验）OPEN**、**P2-02（consume 无生产 Controller/launcher
   端到端调用方）OPEN**（`docs/REVIEW_G4R_INDEPENDENT.md` §9）；A-PR1 才接线，本轮不声称解决。
2. **B03/E5-P04 Registry 权威性 `UNVERIFIED`**、`REGISTRY_RUNTIME_SNAPSHOT_VERIFIED` 不成立；
   `RG-05/07/08/12` 仍 `UNVERIFIED/NOT_RUN`。
3. **R-REV6 真实 DSH two-turn/replay `NOT_RUN`**；Packet 内 L2 计数为 Integration 产出，Reviewer 未重跑。
4. **P1 rootfs 环境限制**：已恢复但不得外推“全程 NO_DRIFT/生产安全”；物理防写未实现（A0-03 `NOT_RUN`）。
5. **Owner 证据路径不可复核**：`artifacts/g4r/**` 为 gitignored，本树无 `artifacts/`；只能引用 CSV/文档记录，
   独立复核需维护者提供精简证据包（交接包 AUDIT_REQUESTS 的 `audit-index.json` 建议）。
6. **无 CI 闸门**：A0-05 要求“CI 能检测 main/canonical 来源、Branch Delta、受保护文件变动、H0 cherry-pick
   回归”；本仓库当前无该 CI → `NOT_RUN`，需维护者决定实现位置。
7. 两分支 tip 可变；本文件结论绑定上述实测 SHA。

## 10. STOP / 不主张

- 不主张合并/吸收已批准；不主张 H0 被否定、G4-R 完整通过；不代维护者做 canonical 决策（本文仅建议）。
- 不主张 A-PR1+ 可开工；不主张任何真实 Key/Provider/HTTP/Live。
- 状态常量保持：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
- **STOP**：等待维护者/Independent Reviewer 对 canonical 建议与 A0 文档复核。
