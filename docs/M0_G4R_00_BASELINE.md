# M0 G4-R — R0 基线冻结（无 Key）

- **文档 ID**：`M0-G4R-00-BASELINE-v1`
- **实施者**：`a-impl-core`（Integration 子 Agent；非 Lead、非 Independent Reviewer）
- **工作树 / 分支**：`/root/Autonomous Teacher/worktrees/g4r-integration` / `work/g4r-integration`
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（= 当时 `main` = `origin/main`；Lead 已验证 main clean）
- **采集时间（UTC）**：`2026-11-20T16:16Z` → `2026-11-20T16:22Z`
- **性质**：R0 只读基线冻结 + 矩阵初始化。**不是** G4-R PASS、不是独立复核结论、不改变任何状态常量；不授权 G4-H/G5/G6/Live。
- **硬约束遵守**：仅在本 worktree 的 `docs/` 与 gitignored `artifacts/g4r/` 写入；未改 `src/`、`tests/`、冻结 docs/Packet/Stage/rootfs/deps；未读取/生成/注入真实 Key；未发起任何真实 Provider/外部 HTTP/TCP；未 `fetch`/`pull` 镜像/下载；未触碰主工作树与其它 worktree（只读观察除外）。

## 0. R0 摘要（Gate 判定：**PASS**，但需独立 Reviewer）

| Case | 结果 | 一句证据 |
|---|---|---|
| R0-01 Commit/worktree inventory | **PASS**（owner-measured） | HEAD=`3e7afee`、分支 `work/g4r-integration`、`git status --porcelain -uall` 空、`HEAD^{tree}=feccda00…`、`HEAD:src=66edfac3…` |
| R0-02 Canonical environment | **PASS**（owner-measured，NO_DRIFT） | rootfs/deps/DSH runtime/adapter JS/Stage manifest+tree+trusted+candidate **全部与冻结值一致**（见 §4） |
| R0-03 Zero-key baseline | **PASS**（owner-measured） | `.env` 不存在、Key-like env/argv 0、`podman ps -a` 空、LiveGate 恒 BLOCKED、`run_live.sh` exit 3 |
| R0-04 Legacy freeze | **PASS**（owner-measured） | 旧 Reviewer 报告/ERRATA/46 行矩阵 SHA 与归档值一致；v1 Packet 177 files/0 symlink、173/173 OK；未改写 |
| R0-05 Agent ownership | **PASS**（owner-measured） | `AGENTS.md` + 执行方案 §2 角色分离；R0 无实现改动，Reviewer 独立待指派 |

> 所有 R0 结果为 `L0-STATIC` owner 实测；Reviewer 列保持 `PENDING_INDEPENDENT_REVIEW`，不得把 R0 PASS 外推为产品 PASS。

---

## 1. 身份与工作树清单

| 项 | 值 | 分类 |
|---|---|---|
| worktree HEAD | `3e7afee077845a071cd364e93ab209cac20b2d5f` | **VERIFIED** |
| branch | `work/g4r-integration` | **VERIFIED** |
| `git status --porcelain -uall`（采集时） | 空（clean） | **VERIFIED** |
| `HEAD^{tree}` / `HEAD:src` | `feccda00a78f10a8ee89b49b130838e464d98c46` / `66edfac399c0af8e15f28f6064cb85be8e1dd11d` | **VERIFIED** |
| `git diff e7d9296..HEAD -- src` | 空（G4-F 之后 src 未变） | **VERIFIED** |
| `git log -n 30 --oneline` | 见 `artifacts/g4r/r0/r0-inventory-20261120T161809Z.log` §A（最近提交为 G4-F 归档链，HEAD=`3e7afee docs: archive G4-F independent review (PASS) and final errata (no-key)`） | **VERIFIED** |
| 主工作树 `/root/Autonomous Teacher` | HEAD=`3e7afee`、branch=`main`、status 0 行 | **VERIFIED（只读观察）** |
| Git 远端操作 | 本轮 0 fetch/0 push/0 merge；不使用网络 | **VERIFIED** |

### 1.1 身份分离（AGENTS.md + 执行方案 §2）

| 角色 | 本轮承担 | 禁止 |
|---|---|---|
| Lead | 排程、依赖、只读复核、邀请 Independent Reviewer、冲突协调 | 直接实现/改文件/代签 Reviewer/自批 Live |
| F-A / F-B / F-C / RG 子 Agent | R1 授权原子性 / R2 recovery 观测 / R4 Packet+lints / R3 Registry Spike | 改冻结件、把 observed request 当权威 registry |
| **Integration（本 Agent）** | R0 基线+矩阵初始化；后续 R5 联合回归、Stage 重建、矩阵终稿、Packet v2 整合 | 篡改测试结果、删除失败 case、自签 Reviewer |
| Independent Reviewer | 独立攻击/静态审阅/原始文件审计/出 Verdict | 与实现 Agent 混用身份、用 Owner 汇总当验证 |

**声明**：R0 阶段本 Agent **未实现** R1/R2/R3 的任何代码或测试；未充当 Independent Reviewer；未授权任何 Live/Key 行为。

---

## 2. 根因 / 目标 / P2 → R 阶段映射

| finding | 问题摘要（来源） | 本轮工作项 | 负责 | R0 初始状态 |
|---|---|---|---|---|
| P2-01 | Packet 构建后出现 2 个未哈希 SQLite sidecar；全量 payload tree 与 manifest 不符（`REVIEW_G4F_INDEPENDENT.md:74/338`、`M0_G4F_REVIEW_ERRATA.md:139-144`） | R4：新 Builder/Verifier 必须拒绝新增未列举 sidecar/隐藏文件；旧 Packet 一字节不改 | F-C + R4 | `NOT_RUN` |
| P2-02 | 矩阵 F2-07 证据路径不存在（`f6/.../tool-window.json`；实际 `artifacts/g4f/f2/tool-window.json`）（`REVIEW_G4F_INDEPENDENT.md:254/339`） | R4：新矩阵只引用新采集 `artifacts/g4r/` 证据；`M0_G4R_SOURCE_ERRATA_APPEND.md` 纠正旧路径 | F-C + R4 | `NOT_RUN` |
| P2-03 | a12 并发 consume loser 偶发 `AUTHORIZATION_USE_RECORD_INVALID`（`REVIEW_G4F_INDEPENDENT.md:340`、`M0_G4F_REVIEW_ERRATA.md:152-158`） | R1：`tmp→fsync→os.link(no-replace)→fsync(dir)` 原子发布；200 线程/50 进程/epoch/crash/FS 负例 | F-A | `NOT_RUN` |
| P2-04 | `tests/security/test_scan_git_secrets.py` F841（`REVIEW_G4F_INDEPENDENT.md:341`） | R4：删除未使用变量；ruff 全变更范围 0 finding | F-C + R4 | `NOT_RUN` |
| P2-05 | F5 `timeout-pre-send` 无 dispatch-window 记录（`REVIEW_G4F_INDEPENDENT.md:342`） | R2：区分 request-lifecycle 与 dispatch-window；未进入 Controller 的 case 不伪造 dispatch | F-B | `NOT_RUN` |
| P2-06 | recovery 将 revocation reason 重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID`（`REVIEW_G4F_INDEPENDENT.md:343`） | R2：保留 first cause + 独立 recovery observation；Broker 仍是唯一费用权威 | F-B | `NOT_RUN` |
| P2-07 | Packet `env/zero-key.json` 只列 1/4 LiveGate reasons（`REVIEW_G4F_INDEPENDENT.md:344`） | R4：同一 `LiveGate.inspect` 输入下 manifest/env/review reasons 逐元素相等 | F-C + R4 | `NOT_RUN` |
| P2-08 | Host full 失败集合与归因不同（`REVIEW_G4F_INDEPENDENT.md:345`） | R4：逐 nodeid 记录 + 固定 config mode/PYTHONPATH/HOME/Stage；分类 ENVIRONMENT_ONLY/REAL_REGRESSION/FLAKY_REPRODUCED | F-C + R4 | `NOT_RUN` |
| B03 / E5-P04 | DSH 无权威 merged tool registry 导出，`--dump-config` 是 Cordis entries 非 `ctx.tools`（`M0_G4_B_RUNTIME_INVENTORY.md` §4、`REVIEW_G4F_INDEPENDENT.md:238/353`） | R3：Registry Authority Spike；给出 `REGISTRY_RUNTIME_SNAPSHOT_VERIFIED_FOR_FROZEN_SCOPE` 或 `REGISTRY_UNVERIFIED_WITH_CONTROLS_DOCUMENTED`；**不允许伪造 PASS** | RG | `NOT_RUN` |
| F4-06 / F4-R2 | Candidate crash + live Controller 组合未验证（`REVIEW_G4F_INDEPENDENT.md:188/354`） | R5（可选）：真实双 Principal 下 Candidate crash 子场景；不可控则保持 `UNVERIFIED` | Integration + R5 | `NOT_RUN` |
| P2-DISK / P2-USERNS / P2-RUN-IDENTITY | 磁盘配额/userns/per-run 身份 | **不在本轮"顺手关闭"范围**（执行方案 §11）；由维护者另行签收/加固 | 人类 | 维持原有残余 |
| F4-R1 / F5-R6 / F1-R4 / F2-R5 / B07 | 字节级 context / 外部 SIGKILL 窗口 / scanner 启发式 / audit 写失败 / title fallback | 维持原残余，不因本轮观测改动而弱化 | — | 维持 |

---

## 3. 只读冻结物清单与 SHA（实测，未修改）

| 对象 | sha256 / 实测值 | 对照 | 分类 |
|---|---|---|---|
| `docs/REVIEW_G4F_INDEPENDENT.md` | `b17977d1ff8506de440996f7bd411149ae968cef6564391b74b28980468ddc4b` | = `M0_G4F_REVIEW_ERRATA.md` §1.3 登记值 | **VERIFIED** |
| `docs/M0_G4F_REVIEW_ERRATA.md` | `7b8209db9c15897e6b4d271361703e4425a9a3a361cb3818d53e5fd92eb9b42b` | append-only 归档；本轮未改 | **VERIFIED** |
| 旧 46 行矩阵 `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv` | `0f4e25ae76632ff60e0c644d34a19bf6c602cf49e347112a1fb3be87a091dba3` | = ERRATA §6.1 归档后值（43 PASS/2 UNVERIFIED/1 BLOCKED） | **VERIFIED** |
| `docs/M0_G4_B_RUNTIME_INVENTORY.md` | `fc3d82149d21ea2e7bfb2023ddb1d08b098f935ceb1da4ebc3afed1594229b15` | 本轮只读引用（§4 B03） | **VERIFIED** |
| `docs/M0_G4F_HUMAN_HANDOFF.md` | `cd26d1e158258ebf457636ba9fd19f6e500271d3232a551fd4197155a49624b0` | 本轮只读引用 | **VERIFIED** |
| `docs/AGENTS.md` | `1d97a7e369a3831267516a968070ee5bca0950350c350e2ebbd9eed91cf30133` | 角色分离依据 | **VERIFIED** |
| v1 Review Packet `/root/Autonomous Teacher/artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99` | 177 files / 0 symlink；`manifest.json` `4aed2a923ea3fae52ed3eac9d0c5838077242ed32045804d687dcef703a1d7f2`；`hashes.sha256` `421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d`；integrity report `3a4546c8bfbd0647cc1c65644912b52802a3ec5e87a2835ba641c5107c30b430`；`sha256sum -c` **173/173 OK，exit 0** | 未被本轮改写；P2-01 sidecar/tree 漂移事实沿用 ERRATA §4.1（本轮不重打包、不打开 Packet 内 SQLite） | **VERIFIED（字节/哈希）**；完整 payload tree = **PARTIAL（P2-01 已知漂移）** |
| G4-F Stage `stage-20261119T142828Z` manifest | `82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501` | = `M0_G4F_REVIEW_ERRATA.md` §1.2 冻结值 | **VERIFIED** |
| 旧 Stage（G3-D `stage-20261117T221955Z`）等 | 只读列出；**不得**用于本轮加载/冒充新 Stage | R4 将重建新 Stage；旧 Stage 仅 fail-closed 负例对象 | 观察 |

> 本轮**没有**修改任何冻结 docs/Packet/Stage/rootfs/deps；`git status` 仅显示本任务新增 `docs/` 文件（commit 前）。

---

## 4. 环境清单与 canonical 复算（关键）

复算配方与历史完全一致（`docs/M0_G3B_BASELINE.md:209-211`、`docs/LOCAL_OCI_VALIDATION.md:48-49`）：
`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C <tree> . | sha256sum`（pipefail）。

| 对象 / 路径 | 实测值（本轮） | 冻结值（来源） | 漂移 | 分类 |
|---|---|---|---|---|
| rootfs `artifacts/security/rootfs` | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | `25491e45…`（`config/g4/runtime-policy.json` `environment_binding`；`REVIEW_G4F_INDEPENDENT.md:18`） | **NO_DRIFT** | **VERIFIED** |
| deps `artifacts/foundation/deps` | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | `e07729d7…`（同上） | **NO_DRIFT** | **VERIFIED** |
| DSH runtime `artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64` | sha256 `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；size `182717632` B；`env -i` 自报 `0.2.2-rc.2` | `1cc41d5a…` / `0.2.2-rc.2`（同上；`REVIEW_G4F_INDEPENDENT.md:18`） | **NO_DRIFT** | **VERIFIED** |
| adapter built JS `…/stage-20261119T142828Z/candidate/runtime/bridge/lib/index.js` | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba`（字节实测；`build-meta.json` sha256 `58088b16…`） | `2cb42461…`（stage `trusted/REFERENCE.json`；`M0_G4F_IMPLEMENTATION_REPORT.md:97`；`runtime-policy.json` `stage_binding.adapter_built_js_sha256`） | **NO_DRIFT** | **VERIFIED** |
| Stage manifest `…/stage-20261119T142828Z/manifest.json` | `82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501` | `82e10c6f…`（ERRATA §1.2） | **NO_DRIFT** | **VERIFIED** |
| Stage tree（整 stage） | `7d32ec1d8b02726ba52ef8303e8677b46384e9954559e838b31bb8c58f222068` | `7d32ec1d…`（ERRATA §1.2 / stage-summary） | **NO_DRIFT** | **VERIFIED** |
| Stage trusted tree | `6d887bbf4c83ee87145bd5e71d97475a2c61cdbe97b101302650eb84cc1b5aec` | `6d887bbf…`（stage-summary） | **NO_DRIFT** | **VERIFIED** |
| Stage candidate tree | `2459db9df83b9dedfa68c6c0210f5904f0c11601e57744a3d357c4884a06907c` | `2459db9d…`（stage-summary） | **NO_DRIFT** | **VERIFIED** |
| 实际加载源码（18 modules） | 18/18 `stage trusted == git 3e7afee blob == loaded_sha256`；`all_from_project_src=true`、`all_match_head=true`、`all_match_stage=true`；controller `0152fcde…` | `REVIEW_G4F_INDEPENDENT.md:83/214`（18/18） | **NO_DRIFT** | **VERIFIED** |
| Stage 构建基线 | stage `base_sha = head_at_build = e7d9296`（不是 `3e7afee`） | 说明：`3e7afee` 相对 `e7d9296` 只改 docs/`build_packet_g4f.py`，`git diff e7d9296..3e7afee -- src` **为空**；因此当前环境/源码身份与冻结 stage 一致 | 无产品源码漂移 | **VERIFIED（附说明）** |
| Python / Node / Podman / sha256sum | venv Python `3.11.15`；Node `v22.23.2`；Podman `4.9.3`；GNU tar＋sha256sum 可用 | `runtime-policy.json` 记录版本 | **NO_DRIFT** | **VERIFIED** |
| 磁盘 | `6.6G` 可用（`/` 92%） | 本轮不复制大 tree（只读哈希）；临时 `/tmp` 副本已清理 | — | 观察 |

**结论**：本轮环境与冻结口径 **5/5（rootfs、deps、DSH runtime、adapter JS、Stage manifest+tree）plus loaded source 全部一致，0 drift**；**未触发** `BLOCKED_NEEDS_ENVIRONMENT`。注意：R4 冻结 impl 后必须**重建新 Stage**（不得复用旧 Stage 字节冒充新代码），本表只证明 R0 起点环境 canonical 与旧冻结一致。

> 环境漂移风险（历史）：跑 OCI 可能在 rootfs 生成空挂载点（如 `/evidence`）；本轮**未启动任何容器**，故未产生新挂载点；实测 canonical 亦确认无漂移。

---

## 5. 无 Key / 无 Live 证据（R0，本机只读）

| 检查 | 实测结果 | 证据 |
|---|---|---|
| `.env` 文件 | worktree `ABSENT`；主工作树 `ABSENT`；`git ls-files` 中无 `.env` | `artifacts/g4r/r0/r0-nokey-20261120T161849Z.log` |
| Key-like **env 名称**（值从不打印） | `NONE`；`DEEPSEEK_API_KEY`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`/`OPENCODE_API_KEY`/`AT_M0_LIVE_APPROVED`/`AT_M0_ALLOW_LIVE`/`G4B_TEST_MODE` 全部 `<UNSET>` | 同上 |
| Key-like **argv** | `/proc/<pid>/cmdline` 扫描 46 个进程，`key_like_argv_hits=0`（探针进程自身已排除；值不打印） | `artifacts/g4r/r0/r0-adapter-and-argv-20261120T161918Z.log` |
| 容器 | `podman ps -a` 仅表头（无容器）；本机 images=4（冻结本地镜像，未 pull） | `r0-nokey-*.log` |
| Fake-only / 无真实路由 | `runtime-policy.json`：`synthetic_only=true`、`billable_send_authorized=false`、`live_gate_effect=NONE_BLOCKED`、route=`offline-test-only-g3b/fixture-bridge-v1` | `r0-nokey-*.log` |
| 网络隔离（静态） | 冻结 launcher argv 含 `"--network", "none", "--http-proxy=false", "--unsetenv-all"`（`scripts/g3d/launch.py:619`）；本轮**未启动容器** | `r0-nokey-*.log` |
| LiveGate（代码级负例） | `LiveGate.inspect(live_requested=True, …, actual_tools=("skill_lookup",), session_log_disabled=True)` → `status=BLOCKED`，首个 reason `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`；`require_live()` → `SECURITY_BLOCKED` | 同上（L1-HOST 探针，无网络） |
| `run_live.sh` 负例 | exit **3**；stdout 空；stderr 含 `BLOCKED SECURITY_BLOCKED`（预期负例） | 同上 |
| 真实 Provider / 模型 / 计费 / HTTP | **本轮 0**：未启动 DSH/容器、未 import Provider SDK、未发起任何 socket；所有命令为本地 git/tar/sha256sum/python 只读探针 | 全部 R0 日志 |

> 说明：R0 的 `LiveGate` 探针是 L1-HOST 静态/逻辑负例；完整 A-07/R4-11 四入口 + strace 矩阵属 R4 采集范围，R0 不冒充。

---

## 6. `config/g4/runtime-policy.json` 与 Registry 记录

- 文件 sha256：`d0851a41b0af15e422b85d5ce6b6c4ba5bb27a76be0a1d1d5502a428d6df8066`
- `registry_status` = **`UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT`**
- `registry_reason`：DSH `0.2.2-rc.2` 无权威 merged tool registry/schema 导出；`--dump-config` 返回 Cordis entry list（非 `ctx.tools` 最终集合）
- `approved_tools` = **仅 `skill_lookup`**，schema sha256 = `c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704`
- `tool_schema_source` = `candidate/fixtures/capture-tools.json`；该文件（stage candidate，**只读**）sha256 = `d3f8909129f11c27bb8d83c48ee0eacd4359c25f68b6fcc72320d778a258bafc`；用与 Controller 相同的 `canonical_json` + sha256 复算其 `skill_lookup` schema = **`c984bef0…`**（与 policy 逐字节一致，**VERIFIED**）
- `tool_admission_rule` = `DENY_ANY_TOOL_WHOSE_CANONICAL_JSON_SHA256_IS_NOT_LISTED_ABOVE_BEFORE_RESERVE_OR_CLAIM`；`forbidden_tool_prefixes` = bash/pwsh/terminal/fs_/file_/web_/subagent/workflow/agent/mcp_/image_
- 证据：`artifacts/g4r/r0/r0-adapter-schema-final-20261120T162109Z.log`、`r0-inventory-*.log` §F
- **结论**：`B03/E5-P04` 维持 **UNVERIFIED**（R3 负责可行性与有界 Spike；不得把 `--dump-config` 或 per-dispatch request.tools 当权威 registry；不得在本轮关闭）。

---

## 7. 已知外部事实（只观察，不触碰、不共享）

| 对象 | 值（只读观察） | 说明 |
|---|---|---|
| B 线 worktree `/root/at-m1-offline` | HEAD=`290c5770461bb5af2a38c6e6d24ee76350bcb410`，branch=`work/m1-offline-design` | B 线（M1 离线设计）独立工作树；本线未读取其内容、未共享 artifact/凭据、未以其为 base |
| 上一轮未合并分支 `worktrees/m0-g4h0` | HEAD=`15c5a08b6f518dadf43f652d5a25f91d5d80811b`，branch=`work/m0-g4h0` | 仅作 **prior art** 观察；**不是**本线 base（本线 base = `main@3e7afee`） |
| 主工作树 `/root/Autonomous Teacher` | HEAD=`3e7afee`、clean | 只读观察，未写入 |
| 网络 | 0 fetch/push/pull/下载 | 本轮全程离线 |

---

## 8. Matrix 初始化（唯一 writer 职责）

- 新矩阵：`docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（由交接包 CSV 为初稿）。
- 初始状态：**65 个 case**：`R1-01..08`(8)、`R2-01..09`(9)、`RG-00..12`(13)、`R4-01..13`(13)、`R5-01..03`(3)、`REV-01..08`(8) 全部 `NOT_RUN`；`G4-H-01..06`(6) `BLOCKED`；`R0-01..05`(5) 已按 §0 实测填入 `PASS`（owner-measured，reviewer=`PENDING_INDEPENDENT_REVIEW`）。
- 填入字段：`status/utc/exit_code/git_sha/runtime_sha/stage_sha/source_evidence/reviewer/residual`（R0 行完整；其余行保持空）。
- 后续职责：本 Agent 作为**唯一 writer**，汇总各实现 Agent（F-A/F-B/F-C/RG）上报的 case 结果并更新矩阵；**不覆盖旧 46 行 G4-F 矩阵**；未执行保持 `NOT_RUN`，无法验证填 `UNVERIFIED`，绝不预填 PASS。

---

## 9. artifacts/g4r/r0/ 证据索引（gitignored）

| 文件 | 内容 |
|---|---|
| `r0-inventory-20261120T161809Z.log` | Git 身份/worktree/log、冻结物 SHA、环境 canonical 复算、18/18 loaded source、runtime-policy、capture-tools、磁盘 |
| `r0-nokey-20261120T161849Z.log` | .env/env 名称/argv/容器/静态网络隔离/LiveGate 探针/run_live 负例（值全部 masked） |
| `r0-adapter-and-argv-20261120T161918Z.log` | adapter JS 定位、`/proc` argv 扫描、capture-tools canonical schema 复算 |
| `r0-adapter-schema-final-20261120T162109Z.log` | adapter built JS 字节实测（`candidate/runtime/bridge/lib/index.js` = `2cb42461…`）、schema SHA 对照 |
| `SHA256SUMS` | 上述日志的 sha256 清单（生成于提交前） |

复现命令（无网络、无 Key）：

```text
cd "/root/Autonomous Teacher/worktrees/g4r-integration"
git rev-parse HEAD && git status --porcelain -uall
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "/root/Autonomous Teacher/artifacts/security/rootfs" . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C "/root/Autonomous Teacher/artifacts/foundation/deps" . | sha256sum
sha256sum "/root/Autonomous Teacher/artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64"
sha256sum "/root/Autonomous Teacher/artifacts/g4/c/stages/stage-20261119T142828Z/manifest.json"
podman ps -a
sh scripts/run_live.sh; echo "expected exit=3"
```

---

## 10. R0 Gate 判定与下一步

- **R0 Gate：满足**（冻结 SHA、无 Key 证据、环境清单、P2 映射、独立分支/矩阵/Reviewer 规划齐全；环境 0 drift）。
- **未触发**：`BLOCKED_NEEDS_ENVIRONMENT`、`FAIL_FOR_G4R_NO_KEY_SCOPE`、任何 STOP 条件。
- **下一步**：等待 Lead 分配 R1/R2/R3/R4 实施（独立 worktree/PR），本 Agent 负责后续 **R5 联合回归 + Stage 重建 + 矩阵终稿 + Packet v2 整合**；**阶段二等 Lead 的“G4-R impl SHA 已冻结”消息**，不提前开始。
- 本轮不产生任何 G4-R PASS；最高裁定只能由 Independent Reviewer 给出：`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` / `PASS_FOR_G4R_NO_KEY_SCOPE_WITH_B03_RUNTIME_SNAPSHOT_VERIFIED` / `PARTIAL_FOR_G4R_NO_KEY_SCOPE` / `FAIL_FOR_G4R_NO_KEY_SCOPE` / `BLOCKED_NEEDS_ENVIRONMENT_OR_HUMAN`。

## 11. 边界（不得外推）

1. 本文件是 R0 基线冻结，不是 G4-R 通过；R0 PASS 只覆盖 L0-STATIC owner 实测。
2. 环境 canonical 与旧冻结一致，**不能**替代新 impl Stage 重建与 R4/R5 独立复核。
3. `B03/E5-P04=UNVERIFIED` 不变；`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 全部不变。
4. 任何真实 Key/Provider/TLS/账单/额度、人类信任根、Key Broker、Egress、G4-H/G5 均 **未授权、未验证**；禁止把本文件或 R0 结果当作授权凭据。
