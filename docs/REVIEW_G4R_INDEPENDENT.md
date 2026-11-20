# M0 G4-R 独立复核报告（Independent Reviewer）

- **报告 ID**：`M0-G4R-INDEPENDENT-REVIEW-v1`
- **Reviewer**：`a-reviewer`（Independent Reviewer；本报告所有结论来自 Reviewer 自己的命令、原始字节与
  原始日志；**未采信** Owner/Implementer 的 PASS 文字，未参与任何实现/证据生成/文档撰写，未修改
  实现/冻结物/主工作树/其它 worktree，未 push/merge）
- **独立性声明**：Owner 侧证据（`docs/M0_G4R_*`、`artifacts/g4r/**`）只作为被审查对象或
  “Reviewer 独立解析的原始文件”；凡未亲自复跑/复算的项目一律标 `UNVERIFIED`/`NOT_RUN`。
- **最终复核基线（本报告主体）**：`d33e0aabd1714a486325b745c436cb59855d6539`（分支/集成分支
  `work/g4r`，= main `3e7afee` + PR-R1..R4 + R0 基线文档 + **test/tooling-only delta**）
- **base**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（主工作树 `main`，clean）
- **审查工作树**：`/root/Autonomous Teacher/worktrees/g4r-review`，分支 `docs/g4r-independent-review`
  （HEAD = d33e0aa；只写 `docs/REVIEW_G4R_INDEPENDENT.md`、`docs/g4r_review_evidence/`、
  `scripts/g4r_review/`）
- **环境**：Python 3.11.15（`.venv`）、pytest 9.2.0、ruff 0.17.5、Node v22.23.2、Podman 4.9.3、
  Linux 宿主 nproc=12；`PYTHONPATH=src` 已确认 `import autoteacher_m0` 指向本 worktree（见
  `docs/g4r_review_evidence/environment.log`）。
- **审查状态**：源码/证据链/delta 部分已完成；**R-REV5 最终 Packet 尚未到达（UNVERIFIED）**，
  本报告在 Packet 路径到达并完成独立遍历+变异注入后补最终裁定。**本版本不得当作最终裁定引用**。
- **delta 前参考**：`5bf9b8b14212a987fc97ca515a20d99b3a12920c`（中间基线；仅用于 delta 对比与
  “delta 前”运行记录，不作为最终基线）。

---

## 0. 裁定（本版本：`PARTIAL_FOR_G4R_NO_KEY_SCOPE`；最终裁定待 R-REV5）

> 本版本裁定：**`PARTIAL_FOR_G4R_NO_KEY_SCOPE`**。原因：
> 1) R1/R2/R3/R4 的 no-key 修复与 L1-HOST 负例经 Reviewer 自建探针/独立解析复验成立；
> 2) **P1 环境类发现（见 §1.4）**：冻结 rootfs 工件被并发 OCI 运行（`podman --rootfs` 直接指向
>    `artifacts/security/rootfs`）写入挂载点目录，canonical 由 `25491e45…` 变为 `a6737150…`；
>    在清理并恢复 canonical 之前，最终 Stage/Packet/L2 的 rootfs 绑定不可信；
> 3) **R-REV5 最终 Packet 未到**、**R-REV6 未跑**，L2-REAL-DSH 全链 UNVERIFIED。
>
> 若最终 Packet 在**清理后 canonical 环境**中构建并经 Reviewer 独立遍历/变异注入通过，且 delta 仍
> 为 test/tooling-only，则裁定可升为 `PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`（仍仅限 no-key 修复范围）；
> `PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED` 不成立（B03/E5-P04 仍 UNVERIFIED，
> 见 §4）。唯一允许枚举：`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` /
> `PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED` / `PARTIAL_FOR_G4R_NO_KEY_SCOPE` /
> `FAIL_FOR_G4R_NO_KEY_SCOPE` / `BLOCKED_NEEDS_ENVIRONMENT_OR_HUMAN`。
>
> **不表示**：E5-PreLive Full PASS、E5-P04 PASS、B03 关闭、G4-H/G5/G6 授权、Live 批准、M0 GO。
> `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、
> `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 不变。

---

## 1. R-REV1 证据链（最终基线 d33e0aa）

### 1.1 变更面 + delta（`3e7afee..d33e0aa`，Reviewer 独立）

- `git diff --stat 3e7afee..d33e0aa` = **31 files（28 A / 3 M）**，`+6351/−39` 基础上叠加 delta（见 §1.2）。
- M（3）：`src/autoteacher_m0/bridge/controller.py`、`src/autoteacher_m0/security/authorization.py`、
  `tests/security/test_scan_git_secrets.py`（仅删 1 行未使用变量）。
- A（28）：`scripts/g4r/**`、`src/autoteacher_m0/bridge/{request_lifecycle,recovery_diagnostics}.py`、
  `tests/g4r_packet/**`、`tests/g4r_registry/**`、`tests/integration/g4r_auth/**`、
  `tests/integration/g4r_recovery/**`、`docs/M0_G4R_*.md` + 新矩阵。

### 1.2 delta（`5bf9b8b..d33e0aa`）独立审读 —— 判定：**test/tooling-only 成立**

`git diff --stat 5bf9b8b..d33e0aa` = **4 files，+197/−19**：

| 文件 | 变更 | 判定 |
|---|---|---|
| `scripts/g4r/build_packet_g4r.py` | `--impl-sha` 接受 40-hex git commit 或 64-hex（长度/大小写/非 hex 拒绝）；新增 `--impl-content-sha256`；manifest identity 增 `impl_git_commit`/`impl_content_sha256`；40-hex 时二者一致性校验 | tooling，合理 |
| `scripts/g4r/verify_packet_g4r.py` | 校验 identity 三字段格式/一致性；`--expected-impl-sha` 与 `impl_sha`/`impl_git_commit`/`impl_content_sha256` **精确成员匹配**（否则 `IMPL_SHA_MISMATCH`）| tooling；未放宽（manifest 篡改仍由 hashes/HASH_MISMATCH 检出，新测试覆盖）|
| `tests/g4r_packet/support.py → packet_support.py`（R088）| 重命名 + `import packet_support as support`，修复裸 `import support` 与 `tests/integration/g4_f2/support.py` 名称遮蔽 | test-only，修复 collection |
| `tests/g4r_packet/test_packet_v2.py` | 新增 40-hex 接受/非法 id 拒绝/非法 content sha 拒绝/manifest identity 篡改检出等用例；既有 `test_r4_01` 改用已构建 packet 作为“已存在 root” | test-only，未放宽 |

- **`git diff 5bf9b8b..d33e0aa -- src/` = 空（产品实现零变化）**；`git diff --name-only 3e7afee..d33e0aa
  -- <受保护集>` = 空（`gates.py`/`dsh_adapter.py`/`cli.py`/`run_live.sh`/旧 Reviewer 报告/旧 ERRATA/
  旧 46 行矩阵/handoffs/config/tests/integration/g4_a/）。
- 独立复验两个缺陷已修：`pytest tests --collect-only -q` = **1420 collected，exit 0**（delta 前 5bf9b8b
  上存在 2 个 collection error）；`tests/g4r_packet tests/integration/g4_f2` = **41 passed / 1 skipped**；
  delta 文件 `ruff check` = **All checks passed**。
- 提示（非缺陷）：64-hex `impl_sha` 模式下 `impl_git_commit` 可为 metadata 可选字段；最终 40-hex 包
  不受影响（§1.2 校验强制 40-hex 时一致）。
- 原始记录：`docs/g4r_review_evidence/r_rev1_delta_and_protected_final.log`。

### 1.3 冻结/受保护文件与旧 Packet（最终基线，VERIFIED）

- 旧 v1 Packet 未改写：`manifest.json` = `4aed2a92…1d7f2`、`hashes.sha256` = `421b07ae…9d3d`、
  **177 files / 0 symlink**；旧 `REVIEW_G4F_INDEPENDENT.md` = `b17977d1…`、`M0_G4F_REVIEW_ERRATA.md` =
  `7b8209db…`、旧 46 行矩阵 = `0f4e25ae…`（全部与冻结登记一致）。
- 主工作树 HEAD `3e7afee`、clean（0 行）。
- `d33e0aa` 树身份：`HEAD^{tree}=ac933301…`、`HEAD:src=e10d7c7c…`（= 5bf9b8b 的 src tree，印证 src 未变）。

### 1.4 Canonical 环境 / 加载身份 —— **P1 发现：冻结 rootfs 被并发 OCI 污染**

Reviewer 独立复算（`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner`）：

| 对象 | 实测 | 冻结值 | 判定 |
|---|---|---|---|
| deps tree | `e07729d7…2ecb98` | `e07729d7…` | **NO_DRIFT** |
| DSH runtime binary | `1cc41d5a…be6ea4` | `1cc41d5a…` | **NO_DRIFT** |
| Stage manifest | `82e10c6f…6e501` | `82e10c6f…` | **NO_DRIFT** |
| adapter built JS | `2cb42461…7bf74ba` | `2cb42461…` | **NO_DRIFT** |
| Stage full tree | `7d32ec1d…f222068` | `7d32ec1d…` | **NO_DRIFT** |
| **rootfs tree** | **`a6737150…b39b4fa`（污染态）**；漂移窗口内还观测到 `0340fb78…`；16:43:53 首次复算曾 = `25491e45…` | `25491e45…2fe9c0` | **❌ 非 canonical（P1）** |

**根因（Reviewer 定位，可复现）**：Integration 的 OCI 运行直接以冻结 rootfs 作容器根：
`podman run --rootfs "/root/Autonomous Teacher/artifacts/security/rootfs" … -v …:/evidence --tmpfs /tmp --tmpfs /work`
（argv 见 `worktrees/g4r-phase2/artifacts/g4r/logs/oci-filtered-final.meta`）。podman 在 `--rootfs`
目录内创建挂载点目录且未清理：**新增 6 个空目录**（16:55，mode 1755 sticky）：
`evidence/`、`fixtures/`、`plugin/`、`skill/`、`var/`、`var/tmp/`。同一漂移被 Integration 的 Stage
重建 fail-closed 检出（`stage-build-new-20261120T165224Z.log`：`rootfs is not canonical before build`，
base=d33e0aa）；`stage-build-final`（16:54:07）成功时 rootfs 尚为 `25491e45`，16:55 容器启动后被污染。
**该缺陷属 R5 集成/OCI 流程（rootfs 工件可被 podman 直接写），不是 d33e0aa/src 缺陷**；但它使
“环境 NO_DRIFT”不成立于审查窗口，并会使此后构建的 Stage/Packet 的 `rootfs_sha256` 绑定不可信。
Reviewer **不修改冻结工件**；建议处置见 §9 P1 与给 Lead 的报告。

**加载身份**：6/6 关键模块（`authorization`/`controller`/`request_lifecycle`/`recovery_diagnostics`/
`dispatch_audit`/`gates`）的 `sha256(实际加载文件)` == `git cat-file blob d33e0aa:<path>`（全部一致）。
原始记录：`r_rev1_canonical_env*.log`、`r_rev1_loaded_modules_final.log`、`r_rev1_protected_frozen_final.log`。

---

## 2. R-REV2 单次授权（Reviewer 自建探针，最终基线重跑）

探针：`scripts/g4r_review/r_rev2_race_probe.py`（Reviewer 自建；TEST_ONLY 合成 fixture；无 Key/模型/
网络；输出原始 JSON）。命令（cwd=review worktree，`PYTHONPATH=src`）：见 `r_rev2_race_probe_final.log`。
**exit 0，failure_count=0**（最终基线 d33e0aa 重跑，原始 `r_rev2_race_probe_final.{log,json}`）：

| Case | 配置 | 实测 |
|---|---|---|
| 线程竞态 | 10 轮 × 4 consumer | 10/10 轮恰 1 成功；loser 全 `AUTHORIZATION_REPLAYED`（30/30）；0 双成功；final 完整+0600；0 temp |
| 多进程竞态 | 10 轮 × 3 fork consumer（独立 PID/FD）| 10/10 轮恰 1 成功；loser 全 `REPLAYED`（20/20）；0 双成功 |
| 跨 epoch | 8 轮（两个 run_epoch 竞争）| 8/8 轮恰 1 成功；loser 全 `AUTHORIZATION_EPOCH_MISMATCH`（8/8）|
| 持久腐坏 final | 0B/半 JSON/`{}`/`[]`/错 schema/symlink/`nlink=3`/`0666` | 8 类全部 `AUTHORIZATION_USE_RECORD_INVALID`（**未伪装 REPLAYED**），无第二成功 |
| crash 注入 | 子进程在 `link(2)` 发布点 `os._exit(23)`（temp 已 fsync）| 无 final、1 个 crash temp；重启**恰 1 次成功**、第二次 `REPLAYED`；陈旧 temp 被回收 |
| dir fsync EIO | link 后目录 fsync 注入 EIO | `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` fail-closed（不返回成功）；final 完整保留、0 temp；后续 `REPLAYED` |
| temp 上限 | 256 fresh temp | `AUTHORIZATION_USE_LOG_WRITE_FAILED`（不创建 final）；过期后 consume 成功 1 次且 temp 清零 |
| link 不可用 | 注入 `EOPNOTSUPP` | `WRITE_FAILED`；无 final、无 temp（无直接写 final 回退）|

**判定：R-REV2 = PASS（L1-HOST，最终基线）**；附 P2-01 evidence-integrity nit（§9）。

---

## 3. R-REV3 两层观测分离 / recovery first_cause（代码审读 + 原始文件独立解析）

- **请求层 vs dispatch 层**：`request_lifecycle.py`（`m0.g4r.request-lifecycle.v1`）与既有
  `dispatch-window.jsonl` 分离；dispatch 层兼容 rejection 行写 `dispatch_seq=None` +
  `request_level_only=True`；`dispatch_seq` 仅在 worker 真正进入 `_handle_payload_serial` 后由真实
  audit 序号回填；pre-Controller 事件恒 `null`、`reserved=false`。**未发现伪造 dispatch_seq**。
- **recovery first_cause**：保留条件 = 封闭枚举（`RUN_AUTHORIZATION_REVOKED` 精确 +
  `REVOKED_PRE_SEND:` 前缀）**且** Broker `PENDING`；Broker `OK/FAILED` 仍终态权威；
  每分支追加独立 append-only `recovery-diagnostics.jsonl`，观测失败被隔离（不改变恢复判定）。
- **不变量**：新增代码无 `.free()/release()/resend/begin_attempt`（grep=0）；PENDING/UNCERTAIN held>0、
  不自动 FREE、不盲重发；`tests/integration/g4r_recovery` 19 项在 Reviewer 的定向 run 中通过（§6）。
- **Owner L1 原始文件独立解析（非 L2）**：`worktrees/g4r-recovery/artifacts/g4r/r2/20261120T163245Z-7bd7fa2/`
  - `request-lifecycle.jsonl` 4 行：`received`(null)→`controller_entered`(seq=1)→
    `deadline_before_controller`(seq=1, stage=before_reserve, DEADLINE_EXCEEDED)→
    `failed_before_reserve`(seq=1, CANCELLED)；`reserved=false`。
  - `dispatch-window.jsonl` 1 行：`dispatch_seq=1`、`reserved/dispatched/settled=false`（真实 worker 最终记录）。
  - `recovery-diagnostics.jsonl` 1 行：`primary_cause=REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED`、
    `primary_cause_preserved=true`、观测 `RECEIPT_DOCUMENT_SCHEMA_INVALID`、broker `PENDING`。
  - `probes.json`：Broker PENDING、`fake_received=0`、`fail_calls=[]`、attempt reason 保留 revoke。
- **L2-REAL-DSH**：审查时 Integration `artifacts/g4r/` 仅有 `r0/`（L2 证据未产生）⇒ **UNVERIFIED/NOT_RUN**。

**判定：R-REV3 = PARTIAL（L1 代码/原始证据 PASS；L2 与端到端接线 UNVERIFIED，见 P2-02）。**

---

## 4. R-REV4 Registry 可行性 / 信任边界（Reviewer 独立执行 + 判定）

- 冻结配置未改：`git diff 3e7afee..d33e0aa -- config/` = 0；`config/g4/runtime-policy.json`
  `registry_status` = `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT`（未变）；`approved_tools` 仍 `skill_lookup`
  （digest `c984bef0…`）。
- Reviewer 独立执行 Owner instrumentation（只读冻结 Stage `candidate/`，Runtime 冻结 binary，测试 copy
  仅写 `/tmp`；`--mode observe` exit 0）：`runtime_sha256=1cc41d5a…`、`stage_bridge_sha256=2cb42461…`、
  `stage_skill_sha256=521bc0f1…`、`frozen_patch_sha256=0cf5d340…`、`network="unshare -n"`、
  `real_key_present=false`、`real_provider_calls=0`；epoch 0→1→2；dispatch face == registry ==
  `[skill_lookup]`，digest `c984bef0…`（== approved），`approved_face=true`。
- 独立攻击模式 `--mode attack-late-extra-bash`（exit 0）：epoch 2 late register `bash`；dispatch face
  `[bash, skill_lookup]`、`approved_face=false`、`registry_approved=false`、`face_equals_registry=true`；
  enforce 在 adapter 前拒绝（runtime stdout 中 `G3B_BRIDGE_*` 标记 = **0**，adapter 未被到达）。
- 判定：**`API_AVAILABLE` 机制面经 Reviewer 独立执行确认（L1）**；但 Owner 文档自认且 Reviewer 同意：
  无外部导出 API、snapshot 为进程内插件自报（可伪造、SHA 非身份）、trusted channel 未实现 ⇒
  **权威 registry/B03/E5-P04 维持 UNVERIFIED**，`REGISTRY_RUNTIME_SNAPSHOT_VERIFIED` 不成立；
  RG-05/07/08/12 仍 UNVERIFIED/NOT_RUN。证据等级封顶 L1-INSTRUMENTED-OBSERVATION（instrumentation
  为 Owner 代码，Reviewer 独立执行与解析）。
- 原始记录：`r_rev4_registry_observe2.{summary,events}.json*`、`r_rev4_registry_attack.*`。

**判定：R-REV4 = PARTIAL（机制独立复现 PASS；权威性/信任通道 UNVERIFIED；config 未改 PASS）。**

---

## 5. R-REV7 无 Key / 恒 BLOCKED（Reviewer 独立负例）

| 检查 | 实测 | 证据 |
|---|---|---|
| `LiveGate().inspect()` | `status=BLOCKED`、`external_boundary_deployed=False`；reasons 5 项 | `r_rev7_livegate.log` |
| `LiveGate().require_live()` | 抛 `SecurityBlocked`、`code=SECURITY_BLOCKED`；无 approve/unlock/authorize 入口 | 同上 |
| `scripts/run_live.sh` | exit **3**，stderr `BLOCKED SECURITY_BLOCKED` | `r_rev7_run_live.log` |
| CLI `smoke --live` | exit **3**，stdout JSON `{"status":"BLOCKED","error_code":"SECURITY_BLOCKED",…}` | `r_rev7_cli_live.log` |
| Key-like env / `.env` / 新增 src 行 | env key-like=0；无 `.env`；新增行网络/Key/env 解锁=0 命中 | `r_rev7_env_scan.log`、`r_rev7_added_lines_scan.log` |

**判定：R-REV7 = PASS（本机无 Key 范围）**；真实人类授权边界/Key Broker/Egress/Watchdog 仍 NOT DEPLOYED。

---

## 6. R-REV8 Host/OCI/Node/Ruff/Scanner 独立复跑

| 检查 | 实测（最终基线 d33e0aa）| 判定 |
|---|---|---|
| 全仓 collection | `pytest tests --collect-only -q` = **1420 collected，exit 0**（delta 修复前 2 collection error）| PASS |
| G4-R 定向套件 | `pytest tests/integration/g4r_auth tests/integration/g4r_recovery tests/g4r_packet tests/g4r_registry tests/security -q` = **69 passed / 1 skipped / 0 failed**（230.55s；宿主上 Integration 全量 suite 并发，失败事实未改写）| PASS |
| packet/f2 | `pytest tests/g4r_packet tests/integration/g4_f2 -q` = **41 passed / 1 skipped** | PASS |
| 单元 | `pytest tests/unit -q` = **396 passed**（5bf9b8b 运行；src tree 与最终基线相同 `e10d7c7c`）| PASS |
| Ruff | 变更范围 **All checks passed**；全仓 5 errors 全在未改动旧脚本（base 为 6，净 −1）| PASS |
| Scanner | `tests/security` 7 passed（含 git secrets scanner）| PASS |
| Node | `node --version` v22.23.2（未独立跑 Node TAP/集成）| 观察 |
| OCI/Podman | **NOT_RUN（Reviewer）**；且发现 Integration OCI 污染冻结 rootfs 的 P1（§1.4）| NOT_RUN |
| Host full | **NOT_RUN（Reviewer）**；Integration 并发运行中（`g4r-phase2`）| NOT_RUN |

**判定：R-REV8 = PARTIAL（定向/unit/ruff/scanner PASS；OCI/Node/Host full 未由 Reviewer 独立执行）。**
注：1 个 skip = `tests/g4r_packet/test_packet_v2.py::test_v1_packet_is_untouched_by_v2_build`（本 worktree
无 v1 Packet 副本时跳过）；Reviewer 已在 §1.3 单独验证主工作树 v1 Packet 未改写。

---

## 7. R-REV5 最终 Packet（UNVERIFIED，待 Lead 路径）

最终 Packet 将由 F-C 从 `d33e0aa` 构建（含新 Stage/Runtime SHA），文件名 `review-packet-g4r-v2-d33e0aa…`。
本版本未收到路径 ⇒：

- 全树独立遍历（文件/目录/symlink/隐藏/未知/manifest-hashes-payload 一致性）、
  `-wal/-shm`/隐藏/未知文件/ symlink/篡改注入必须 FAIL、旧 v1 Packet 未改写、SQLite 快照只读可读
  → **UNVERIFIED（待补）**；
- **构建前置条件**：必须先按 §1.4/§9-P1 清理并恢复 rootfs canonical（`25491e45…`），最终 Packet 的
  环境绑定应在清理后快照产生；否则 Packet 的 rootfs 绑定不可信；
- Reviewer 将使用**自建独立遍历器**（不复用 Owner verifier）。R-REV5 未通过前不得给出
  `PASS_FOR_G4R_*` 裁定。

---

## 8. R-REV6 真实双 Principal/DSH Tool 两轮+Replay（Fake-only）

- Owner R3 自报 RG-05 two-turn **NOT_RUN**；Reviewer 仅独立执行了 `observe`/`attack-late-extra-bash`
  两个 probe 模式（§4），**未跑** two-turn/replay + usage/hash 逐字段对账。
- **NOT_RUN / UNVERIFIED（BLOCKED_NEEDS_ENVIRONMENT）**，不计入 PASS。

---

## 9. Findings

**P0 = 0。P1 = 1（环境/证据完整性，非源码）。P2 = 2 开放 + 1 已由 delta 修复。**

| ID | 级别 | 描述 | 影响/建议 |
|---|---|---|---|
| P1-01 | **P1** | 冻结 rootfs 工件被并发 OCI 运行污染：`podman run --rootfs artifacts/security/rootfs` 在制品内创建 6 个空挂载点目录（`evidence fixtures plugin skill var var/tmp`）；canonical 由 `25491e45…` 变为 `a6737150…`（窗口内另见 `0340fb78…`）；Integration Stage 重建 16:52 fail-closed 检出 | 环境/证据完整性：清理前构建的 Stage/Packet/L2 的 rootfs 绑定不可信。**建议**：停止并发 OCI；删除空挂载点目录或恢复 canonical rootfs 并复算回 `25491e45…`；最终 Stage/Packet 前后各做 canonical 快照；OCI 改用 COW/复制 staging，禁止 `--rootfs` 直指冻结工件；Packet 报告中登记该事件窗口与恢复证据（不得写“全程 NO_DRIFT”）|
| P2-01 | P2（evidence integrity，低）| `_read_use_record` 校验 schema/epoch 但不校验 body `authorization_id` == 路径 `sha256(id)`；Reviewer 探针实测“schema 合法但属其它授权 id 的记录”判 `AUTHORIZATION_REPLAYED`（保守拒绝，无第二成功）| 无授权放宽；审计上错配记录与真实 replay 不可区分。建议读取时交叉校验 body id，不符→INVALID |
| P2-02 | P2（scope gap）| production `src/` 内 `consume_execution_authorization()` **无 Controller/launcher 调用方**（仅测试/`scripts/g4` 探针），R1 修复为模块级；dispatch 前链路端到端单次授权强制未接线 | 不得把模块级 PASS 外推 Live 链 PASS；G4-H1 前需接线并 L2 复验 |
| P2-03 | P2（已修复，待最终确认）| delta 前 `tests/g4r_packet/support.py` 裸 import 与 `g4_f2/support.py` 名称遮蔽（2 collection error）；builder 拒绝 40-hex git commit | delta `d33e0aa` 已修：collection 1420 exit0、builder/verifier identity 三字段、delta ruff 通过；**Reviewer 独立复验通过**（§1.2）→ 可 CLOSED |
| 观察-1 | 文档 nit | `deadline_before_controller` 在 `controller_entered=true` 时携带真实 `dispatch_seq=1`（文档已解释，命名略易误读）| 无安全语义问题；可选改名/加注 |
| 观察-2 | 设计边界 | `nlink>2` 拒绝、`nlink==2` 容忍（final+crash temp）；`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 新 fail-closed 码当前无 Controller 消费方 | 接线时须映射为“不确定/不发送” |

---

## 10. R-REV 矩阵（最终基线 d33e0aa；R-REV5 待 Packet）

| Case | 对象 | 状态 | 说明 |
|---|---|---|---|
| R-REV1 | 证据链/SHA/delta/冻结保护/加载身份 | **PARTIAL** | delta test/tooling-only 成立、受保护零 diff、v1 Packet 未改、加载 6/6 VERIFIED；**rootfs canonical 被并发 OCI 污染 = P1**（其它 canonical 项 NO_DRIFT）|
| R-REV2 | 单次授权并发/crash/腐败/fail-closed | **PASS（L1-HOST）** | Reviewer 自建探针 exit 0；P2-01 nit |
| R-REV3 | 两层观测/recovery first_cause | **PARTIAL** | L1 代码+原始 JSONL 独立解析 PASS；L2/端到端接线 UNVERIFIED；P2-02 |
| R-REV4 | Registry API/信任边界/config | **PARTIAL** | API_AVAILABLE 机制独立复现（observe/attack）；权威性/B03/E5-P04 UNVERIFIED；config 未改 |
| R-REV5 | 最终 Packet v2 独立遍历+变异注入 | **UNVERIFIED** | 待 Lead 最终 Packet 路径（且需 clean rootfs）|
| R-REV6 | 真实双 Principal/DSH 两轮+Replay | **NOT_RUN** | 环境/时间不允许；Owner RG-05 亦 NOT_RUN |
| R-REV7 | 无 Key/恒 BLOCKED | **PASS（本机无 Key 范围）** | §5 |
| R-REV8 | Host/OCI/Node/Ruff/Scanner | **PARTIAL** | 定向 69 passed+1 skip / packet+f2 41+1 / unit 396 / ruff/scanner PASS；OCI/Node/Host full NOT_RUN |

---

## 11. 残余风险 / 未验证项

1. **P1 rootfs 污染**：清理/恢复 canonical 前，最终 Stage/Packet/L2 的 rootfs 绑定不可信（§1.4）。
2. **L2-REAL-DSH 全链**：R2 的 L2、timeout/revocation/in-flight 容器内对账未由 Reviewer 复跑。
3. **单次授权端到端未接线**（P2-02）：模块级 PASS ≠ dispatch 前链路强制。
4. **Registry 权威性**：自报 snapshot 可伪造、无 trusted channel；B03/E5-P04 仍 UNVERIFIED。
5. **崩溃/掉电/跨 FS**：R1 crash 为 seam 注入 + `os._exit`；未做随机 SIGKILL/断电/其它文件系统。
6. **R-REV5/R-REV6 未完成**；最终 Packet、真实 DSH two-turn/replay、usage/hash 对账缺失。
7. 本报告仅覆盖本机、无 Key、无真实 Provider/HTTP/TCP 的 G4-R 修复范围；不构成 E5-Full/G4-H/G5/
   G6/Live 的任何批准。

---

## 12. 证据索引

- `docs/g4r_review_evidence/r_rev1_delta_and_protected_final.log` — delta 4 文件、src 零 diff、受保护零 diff、trees。
- `docs/g4r_review_evidence/r_rev1_canonical_env_final_drift_window.log` — 16:53:15 rootfs 漂移态 `0340fb78…`。
- `docs/g4r_review_evidence/r_rev1_canonical_env_final_stable.log` — 16:57:20 rootfs 污染态 `a6737150…`（deps/runtime/stage 仍 canonical）。
- `docs/g4r_review_evidence/r_rev1_loaded_modules_final.log` — 6/6 加载模块 == HEAD blob（d33e0aa）。
- `docs/g4r_review_evidence/r_rev1_protected_frozen_final.log` — v1 Packet/旧报告/旧矩阵字节。
- `docs/g4r_review_evidence/r_rev2_race_probe_final.{log,json}` — Reviewer 自建单次授权探针（最终基线重跑）。
- `docs/g4r_review_evidence/r_rev4_registry_{observe2,attack}.{log,summary.json,events.jsonl}` — Reviewer 独立执行的 registry probe。
- `docs/g4r_review_evidence/r_rev7_*.log` — LiveGate/run_live/CLI/env/added-lines 负例。
- `docs/g4r_review_evidence/r_rev8_{collect_only_final,g4r_targeted_final,packet_f2_final,unit,ruff_*,scanner}.log` — 回归/计数。
- 探针脚本：`scripts/g4r_review/r_rev2_race_probe.py`（自建）；最终 Packet 独立遍历器将追加到
  `scripts/g4r_review/`。

---

## 13. 待补（收到最终 Packet 路径后）

1. R-REV5：用**自建独立遍历器**全树校验最终 v2 Packet（manifest/hashes/payload/tree、隐藏/未知/
   symlink、`-wal/-shm` 注入、篡改注入必须 FAIL、v1 未改写、SQLite 只读可读），要求 Packet 的
   rootfs 绑定来自 §1.4 清理后的 canonical 快照。
2. 复核 delta 后的最终 SHA 未再变化；若 Packet 构建随附新 SHA，在最终报告中以该 SHA 为最终基线。
3. 给出**最终裁定**（唯一枚举）并 `send_message` Lead；完成后 `task-15` complete 并 **STOP**。

> **STOP（本版本）**：R-REV5 与 rootfs canonical 恢复完成前，不得给出 `PASS_FOR_G4R_*`；不得宣称
> 任何部署/G5/E5-Full/M0 GO。
