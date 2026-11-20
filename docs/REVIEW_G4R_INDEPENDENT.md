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
  （审查基线 d33e0aa；只写 `docs/REVIEW_G4R_INDEPENDENT.md`、`docs/g4r_review_evidence/`、
  `scripts/g4r_review/`）
- **环境**：Python 3.11.15（`.venv`）、pytest 9.2.0、ruff 0.17.5、Node v22.23.2、Podman 4.9.3、
  Linux 宿主 nproc=12；`PYTHONPATH=src` 已确认 `import autoteacher_m0` 指向本 worktree（见
  `docs/g4r_review_evidence/environment.log`）。
- **审查状态：FINAL（已包含 R-REV5 与 P1 终态）**。
- **最终冻结实现基线（code）**：`d33e0aabd1714a486325b745c436cb59855d6539`；**docs-only 后续**：
  `bc08bdd3f6cceb73462c33acd98bda276d0b1fbf`（联合回归/矩阵）；集成分支 `work/g4r` HEAD =
  `64522d981fa2ddcee528dab9d38323bac72d4e8a`（docs-only；Reviewer 实测
  `git diff d33e0aa..64522d9 -- src/ tests/ scripts/` = **0 files**）。
- **最终 Packet v2（Reviewer 只读复核对象）**：
  `/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539`
  - frozen UTC `2026-11-20T17:22:37Z`；**43 files / 0 symlinks / payload 40 / hashes 41 行 / all mode 0444**
  - `payload_tree_sha256=4300a7c67a031136cd52f46b44d325db7a5dd14df82f409d25d6a2247737c1f6`
  - `manifest.json=fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9`
  - `hashes.sha256=e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb`
  - identity：`impl_sha=impl_git_commit=d33e0aa…`、`impl_content_sha256=5551078a…`、docs `bc08bdd…`
  - Stage=`stage-20261120T165407Z`（base d33e0aa / manifest `cc7ccb61…` / tree `933f2c07…` /
    trusted `f10053d4…` / candidate `131ab68e…` / loaded 52/52）
  - 环境：rootfs `25491e45…`（清理后）、deps `e07729d7…`、runtime `1cc41d5a…`、adapter `2cb42461…`；
    exclusive window T0/T1 一致（17:05:50–17:08:20Z）；drift/cleanup 已写入 README/manifest.limitations。
- **delta 前参考**：`5bf9b8b14212a987fc97ca515a20d99b3a12920c`（中间基线；仅用于 delta 对比与
  “delta 前”运行记录，不作为最终基线）。

---

## 0. 最终裁定（FINAL）

> # 最终裁定：`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`
>
> 依据：
> 1) R1/R2/R3/R4 的 no-key 修复与 L1-HOST 负例经 Reviewer 自建探针/独立解析复验成立（R-REV2 PASS）；
> 2) delta（5bf9b8b→d33e0aa）为 **test/tooling-only**（4 文件、`src/` 零 diff、collection 1420/exit0、
>    自建/定向回归通过）；
> 3) **R-REV5 最终 Packet 通过 Reviewer 自建独立遍历器**：全树/计数/哈希/tree/identity 独立复算一致，
>    **11 类 mutation 注入全部被检出**，原 Packet 未被读取改变，旧 v1 Packet 未改写（§7）；
> 4) **P1 rootfs 环境项已缓解并记录 limitations**：清理后 rootfs 恢复 `25491e45…`（Reviewer 17:26:37Z
>    独立复算），最终 Stage/Packet 绑定来自独占窗口且 T0/T1 一致；Packet 明确“非全程 NO_DRIFT、
>    不外推生产/L2 需独占窗口”（§1.4）。
>
> **限制**：仅限 no-key 修复/工程范围。**不成立** `PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED`
> ——B03/E5-P04 仍 `UNVERIFIED`（§4）；`API_AVAILABLE` 仅为 L1 机制可行，不构成权威 registry。
> 开放 P2：P2-01（use record body id 交叉校验）、P2-02（consume 端到端接线）；R-REV6（真实 DSH
> two-turn/replay）仍 **NOT_RUN**。
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

**根因（Reviewer 定位，可复现；Lead 已复核并升级清理清单）**：Integration 的 OCI 运行直接以冻结
rootfs 作容器根：`podman run --rootfs "/root/Autonomous Teacher/artifacts/security/rootfs" …`（argv 见
`worktrees/g4r-phase2/artifacts/g4r/logs/oci-filtered-final.meta`）。podman 在该目录内创建挂载点目录
且未清理。Lead 复核确认时间线：16:53:34 曾清理恢复 `25491e45…`；**16:54:07 Stage 构建成功时
rootfs 为 canonical**（`stage-20261120T165407Z`，候选有效）；16:55–16:59 又发生**二次污染**（范围扩大：
除 `evidence/fixtures/plugin/skill/var/var/tmp` 外，`probe/` 下新增 `lib/node_modules/test/package.json`），
当前 canonical 观测到 `e1a8fcf9…`。**两次污染窗口：16:52–16:53 与 16:55–16:59；三个漂移哈希：
`0340fb78…`、`a6737150…`、`e1a8fcf9…`（冻结值 `25491e45…`）**。同一漂移被 Integration 的 Stage 重建
fail-closed 检出（`stage-build-new-20261120T165224Z.log`：`rootfs is not canonical before build`，base=d33e0aa）。
**该缺陷属 R5 集成/OCI 流程（rootfs 工件可被 podman `--rootfs` 直接写），不是 d33e0aa/src 缺陷**；
但它使“环境 NO_DRIFT”不成立于审查窗口，并会使此后构建的 Stage/Packet 的 `rootfs_sha256` 绑定不可信。
Reviewer **不修改冻结工件**；处置要求（Lead 已发 Integration）：停止容器 → 精确删除两轮污染目录 →
复算期望恢复 `25491e45…`（不等则 STOP）→ 此后 OCI 改用 rootfs **可写副本**，禁止直接 `--rootfs`
冻结工件；最终 Packet 必须含 drift/cleanup/独占窗口记录，不得写“全程 NO_DRIFT”。

**加载身份**：6/6 关键模块（`authorization`/`controller`/`request_lifecycle`/`recovery_diagnostics`/
`dispatch_audit`/`gates`）的 `sha256(实际加载文件)` == `git cat-file blob d33e0aa:<path>`（全部一致）；
最终 Stage trusted `src/*.py` = **52/52 == git d33e0aa blobs**（Reviewer 独立逐文件复算）。

**P1 终态（Reviewer 17:25–17:27Z 独立复算）**：rootfs 已恢复冻结 canonical
`25491e45…2fe9c0`（清理后），deps `e07729d7…`、runtime `1cc41d5a…`、adapter `2cb42461…` 均与冻结值一致；
最终 Stage `stage-20261120T165407Z` 的 manifest `cc7ccb61…`、tree `933f2c07…`、trusted `f10053d4…`、
candidate `131ab68e…`、base/head=`d33e0aa` 全部经 Reviewer 复算一致；Packet 环境身份来自
**exclusive window 17:05:50–17:08:20Z**（`identity/environment.json`：T0/T1 rootfs 均 `25491e45…`、
`T0_T1_equal=true`、OCI 使用 rootfs **可写副本**且 `frozen_rootfs_unchanged=true`）。
⇒ **P1 = RESOLVED_WITH_LIMITATIONS（记录保留，不写“全程 NO_DRIFT”）**：清理链
`25491e45→0340fb78→25491e45→a6737150/e1a8fcf9→(clean 17:01:49)25491e45` 已写入
README/manifest.limitations；L2/OCI 必须在独占窗口串行，不得外推生产/持续 NO_DRIFT。
原始记录：`r_rev1_canonical_env*.log`、`r_rev1_canonical_env_clean_final.log`、
`r_rev1_stage_identity_final.log`、`r_rev1_loaded_modules_stage_52.log`、`r_rev1_protected_frozen_final.log`。

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

## 7. R-REV5 最终 Packet v2（Reviewer 自建独立遍历器）—— **PASS**

**对象**：`/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539`
（只读；Reviewer 未使用 Owner `verify_packet_g4r.py`，使用自建 `scripts/g4r_review/r_rev5_packet_verifier.py`）。

**独立复算结果**（原始日志 `docs/g4r_review_evidence/r_rev5_*`）：

| 项 | Reviewer 实测 | 与 Owner 声明一致 |
|---|---|---|
| files / symlinks / payload / hashes 行 | **43 / 0 / 40 / 41** | ✓ |
| 文件 mode | 全部 `0o444`；固定 metadata 例外 3 个 | ✓ |
| `payload_tree_sha256` | `4300a7c67a031136cd52f46b44d325db7a5dd14df82f409d25d6a2247737c1f6` | ✓ |
| `manifest.json` sha256 | `fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9` | ✓ |
| `hashes.sha256` sha256 | `e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb` | ✓ |
| hashes 覆盖/逐文件复算 | 覆盖 = payload+manifest，0 mismatch | ✓ |
| identity | `impl_sha=impl_git_commit=d33e0aa…`；`impl_content_sha256=5551078a…`；docs commit `bc08bdd…` | ✓ |
| Stage/环境绑定 | stage `stage-20261120T165407Z` manifest `cc7ccb61…`/tree `933f2c07…`/trusted `f10053d4…`/candidate `131ab68e…`/base d33e0aa；rootfs `25491e45…`（清理后） | ✓ |
| live gate snapshot | `identity/livegate.json` status BLOCKED、reasons count/digest 与 manifest 一致 | ✓ |
| safety counters | external_network_calls=0 / real_model_calls=0 / provider_keys_seen=0 | ✓ |
| SQLite snapshots | 只读 `mode=ro&immutable=1` 打开、`PRAGMA quick_check` OK、读取后 Packet 文件集/大小/mtime 不变（无 -wal/-shm 生成） | ✓ |
| 隐藏/未知/非普通文件 | 0 命中（无 hidden、无未知、无 symlink/hardlink/特殊文件） | ✓ |
| 矩阵 | `matrix/G4R_Test_Evidence_Matrix.csv` sha256 = `741d7d55…`（= integration docs 矩阵；65 行 + header） | ✓ |
| 旧 v1 Packet | 177 files / 0 symlink / 173-173 `sha256sum -c` OK / manifest `4aed2a92…` / hashes `421b07ae…`（未改写） | ✓ |
| 原 Packet 读取稳定性 | 复核前后 manifest/hashes 字节不变（`fe45d760…`/`e7a67c77…`） | ✓ |

**Mutation 注入（自建 suite，全部在 `/tmp` 副本上，原 Packet 不动）——11/11 全部 FAIL 检出**：
新增 `-wal`、新增 `-shm`、隐藏文件、未知文件、删除 payload、改字节、改 mode(0644)、
payload→symlink、hardlink 异常（nlink>1）、manifest identity 篡改（impl sha/git/40-hex）、
livegate snapshot reasons 篡改。`mutation_undetected=[]`，原 Packet 复测 `status=PASS`。
（原始：`r_rev5_packet_verify.log/json`、`r_rev5_verifier_selftest.log`）

**判定：R-REV5 = PASS。** Packet 在清理后 canonical 环境构建、含 drift/cleanup 与“非全程 NO_DRIFT”
限制声明，Reviewer 独立遍历 + mutation 注入通过。

## 8. R-REV6 真实双 Principal/DSH Tool 两轮+Replay（Fake-only）

- Owner R3 自报 RG-05 two-turn **NOT_RUN**；Reviewer 仅独立执行了 `observe`/`attack-late-extra-bash`
  两个 probe 模式（§4），**未跑** two-turn/replay + usage/hash 逐字段对账。
- Packet 内含 Integration **独占窗口 (17:05:50–17:08:20Z)** 的 L2 相关计数（f2: tool_dispatch=2/ok；
  f5: timeout-pre-send/revocation-post-reserve/timeout-post-send ok；OCI 在 rootfs 可写副本上
  1053 passed/26 环境类失败/28 skipped，`frozen_rootfs_unchanged=true`）——这是 **Integration 产出**，
  Reviewer 未独立重跑，仅作为 Packet 内容独立读取核对，不据此判 PASS。
- **NOT_RUN / UNVERIFIED（BLOCKED_NEEDS_ENVIRONMENT）**，不计入 PASS。

---

## 9. Findings

**P0 = 0。P1 = 1（环境/证据完整性，非源码）—— 已 RESOLVED_WITH_LIMITATIONS（记录保留）。P2 = 2 开放 + 1 已由 delta 修复（R-REV5 验证）。**

| ID | 级别 | 描述 | 影响/建议 |
|---|---|---|---|
| P1-01 | **P1 → RESOLVED_WITH_LIMITATIONS** | 冻结 rootfs 工件被并发 OCI 运行污染（`podman --rootfs artifacts/security/rootfs` 直指冻结工件）：**两次污染窗口 16:52–16:53 与 16:55–16:59**；三个漂移哈希 `0340fb78…`/`a6737150…`/`e1a8fcf9…`（冻结值 `25491e45…`）；16:54:07 Stage 构建时仍 canonical；Integration Stage 重建 16:52 fail-closed 检出 | 已缓解：17:01:49 清理恢复 `25491e45…`（Reviewer 17:26:37Z 独立复算一致）；最终 Stage/Packet 绑定来自独占窗口 17:05:50–17:08:20Z（T0/T1 一致、OCI 用 rootfs 可写副本、frozen_rootfs_unchanged=true）；Packet README/limitations 记录 drift/cleanup 并声明“非全程 NO_DRIFT、不外推生产/L2 需独占窗口”。**流程要求保留**：禁止再对冻结 rootfs 直接 `--rootfs` |
| P2-01 | P2（evidence integrity，低）| `_read_use_record` 校验 schema/epoch 但不校验 body `authorization_id` == 路径 `sha256(id)`；Reviewer 探针实测“schema 合法但属其它授权 id 的记录”判 `AUTHORIZATION_REPLAYED`（保守拒绝，无第二成功）| 无授权放宽；审计上错配记录与真实 replay 不可区分。建议读取时交叉校验 body id，不符→INVALID |
| P2-02 | P2（scope gap）| production `src/` 内 `consume_execution_authorization()` **无 Controller/launcher 调用方**（仅测试/`scripts/g4` 探针），R1 修复为模块级；dispatch 前链路端到端单次授权强制未接线 | 不得把模块级 PASS 外推 Live 链 PASS；G4-H1 前需接线并 L2 复验 |
| P2-03 | P2（**CLOSED**）| delta 前 `tests/g4r_packet/support.py` 裸 import 与 `g4_f2/support.py` 名称遮蔽（2 collection error）；builder 拒绝 40-hex git commit | delta `d33e0aa` 已修且 Reviewer 独立复验：collection 1420 exit0、builder/verifier identity 三字段、delta ruff 通过；最终 Packet 构建/校验使用 40-hex impl id 成功 → **CLOSED** |
| 观察-1 | 文档 nit | `deadline_before_controller` 在 `controller_entered=true` 时携带真实 `dispatch_seq=1`（文档已解释，命名略易误读）| 无安全语义问题；可选改名/加注 |
| 观察-2 | 设计边界 | `nlink>2` 拒绝、`nlink==2` 容忍（final+crash temp）；`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 新 fail-closed 码当前无 Controller 消费方 | 接线时须映射为“不确定/不发送” |

---

## 10. R-REV 矩阵（最终基线 d33e0aa；R-REV5 待 Packet）

| Case | 对象 | 状态 | 说明 |
|---|---|---|---|
| R-REV1 | 证据链/SHA/delta/冻结保护/加载身份 | **PASS（with env limitation）** | delta test/tooling-only 成立；受保护零 diff；v1 Packet 未改；加载 6/6 + Stage trusted 52/52 == git d33e0aa；canonical 清理后 rootfs/deps/runtime/stage 全部一致（P1 已 RESOLVED_WITH_LIMITATIONS，不写“全程 NO_DRIFT”）|
| R-REV2 | 单次授权并发/crash/腐败/fail-closed | **PASS（L1-HOST）** | Reviewer 自建探针 exit 0；P2-01 nit |
| R-REV3 | 两层观测/recovery first_cause | **PARTIAL** | L1 代码+原始 JSONL 独立解析 PASS；L2/端到端接线 UNVERIFIED；P2-02 |
| R-REV4 | Registry API/信任边界/config | **PARTIAL** | API_AVAILABLE 机制独立复现（observe/attack）；权威性/B03/E5-P04 UNVERIFIED；config 未改 |
| R-REV5 | 最终 Packet v2 独立遍历+变异注入 | **PASS** | 自建遍历器：43/0/40/41、tree `4300a7c6…`、manifest `fe45d760…`、hashes `e7a67c77…` 全部独立复算一致；11/11 mutation FAIL 检出；原 Packet 不变；v1 未改写 |
| R-REV6 | 真实双 Principal/DSH 两轮+Replay | **NOT_RUN** | 环境/时间不允许；Owner RG-05 亦 NOT_RUN；Packet 内 L2 计数为 Integration 产出（Reviewer 未独立重跑）|
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
- `docs/g4r_review_evidence/r_rev5_verifier_selftest.log` — 自建 Packet 遍历器在合成包上的自测
  （clean issues=[]；8 类 mutation 全部检出）。
- 探针脚本：`scripts/g4r_review/r_rev2_race_probe.py`（自建）、
  `scripts/g4r_review/r_rev5_packet_verifier.py`（自建独立 Packet 遍历器 + mutation 注入）。

---

## 13. 最终裁定与 STOP

- **最终复核基线**：impl `d33e0aa`；docs-only `bc08bdd`；集成 `work/g4r` HEAD `64522d9`
  （`git diff d33e0aa..64522d9 -- src/ tests/ scripts/` = 0 files）。
- **最终 Packet**：`review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539`
  （43 files / 0 symlink / payload 40 / tree `4300a7c6…` / manifest `fe45d760…` / hashes `e7a67c77…`）。
- **裁定**：**`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE`**（no-key 修复/工程范围；见 §0）。
- **明确不宣称**：E5-PreLive Full PASS、E5-P04 PASS、B03 关闭、G4-H1/H2 已部署、G5 已获批、
  G6 GO、M0 GO、Live/生产安全。`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
  `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 不变。
- **仍需维护者/Lead 决策**：P2-01/P2-02 处置；B03/E5-P04 残余接受或要求权威 registry；
  正式受信部署（G4-H1）与单次 G5 授权；rootfs/OCI 流程修复（禁止 `--rootfs` 冻结工件、L2 独占窗口）。
- **STOP**：本报告完成后 Independent Reviewer 停止，等待维护者决策；不得据此进入部署/真实调用。
