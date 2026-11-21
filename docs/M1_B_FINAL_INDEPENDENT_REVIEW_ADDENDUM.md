# M1-B 最终独立评审 Delta 附录（P1 修复复核）

| 字段 | 值 |
|---|---|
| Reviewer | 最终独立 Reviewer（未参与 M1-B / B-NEXT 任何实现、修复或 Owner 证据生成） |
| 日期 | 2026-11-21 UTC |
| 工作区 / 分支 | `/root/m1b/delta-review` / `b-next/m1b-final-review-delta` |
| HEAD / tree（复核时） | `db5ce03cd2e68fefc71dee5c15375cebb178d9c5` / `54fa04e256e50052f8a17c7a7365e3cd3e9b120f` |
| 基线 | `main=3e7afee`；M1-A `4706250`；M1-Offline `290c577`；首轮 final review `5d5ebf8` |
| 环境 | Linux 6.17.13-2-pve x86_64；Python 3.11.15；pytest 9.2.0；bubblewrap 0.9.0；TZ=UTC |
| 运行纪律 | 每个 pytest 独立 `TMPDIR=$(mktemp -d)`；串行、无并发 pytest；先 clean archive、后 worktree |
| 证据标签 | `OWNER_REPORTED` / `INDEPENDENTLY_REEXECUTED_THIS_TURN` / `NOT_RUN` / `UNVERIFIED`；不含 hidden expected 明文、凭据或攻击代码 |
| 边界 | **Offline synthetic / MOCK only, not real teaching effect.** 不扩大真实 Provider/Live/生产/人类 Gate 范围 |

## 0. 结论

**`P1_ACTIONS_PARTIALLY_CLOSED`**。

- **P1-1 clean archive / collector 可移植性：`CLOSED`。** 无 `.git` archive 全量 **939 passed / exit 0**，strict **939 passed / 0 skipped / exit 0**；collector 无 git 时记录 `git_sha=null`、`git_available=false`、`git_sha_source="unavailable"`，显式 `--git-sha/--tree-sha` 标 `explicit`，非法值拒绝。
- **P1-2 证据绑定最终树：`CLOSED`。** 38 条索引哈希、旧 27 条字节前缀、11 条新 provenance、raw sha256、物化视图全部重算一致；在本轮 HEAD 独立再生 B5 5 文件与已提交证据**逐字节相同**。manifest `implementation_commit=12f6290` 的“最后行为代码 SHA / 生成 commit 9c383e5”口径在 README 与 §13 有说明，未发现“绑定最终 SHA”的过度声明。
- **P1-3 最终报告数字/哈希/状态勘误：`PARTIAL`。** 首轮点名的 X-01/939/B4/PR4/PR1/536 已修正并可复算；但最终评测报告仍有 **4 类残留**（§4.2）：collector 测试数 `14` vs 实测 `15`；JD v1 journal 哈希 `554c1153…` vs 当前证据 `c3724217…`；`e2e_b5_summary` manifest 写 `c420d19…` vs 实际 `12f6290…`；多处仍写“独立评审 PENDING/未出/待合入”而首轮评审 `5d5ebf8` 已在 HEAD。另有 1 处最终 PR5 SHA 待回填（P2）。
- **最终裁定建议：维持 `PASS_WITH_ACTIONS`，不升级。** P1-1/P1-2 已关闭，技术门全部通过；但 P1-3 尚未完全满足“每个数字/哈希可复算、三份文档一致”的验收条件，故本轮不能给 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。B5-01 维持 `PARTIAL`。完成 §4.3 的 docs-only errata 后，可用同一组命令复核并升级。

> `EXECUTED_PASS` 只是命令退出 0，不是产品 PASS；本附录不构成真实教学效果、Provider、LiveGate 或生产可用性的任何结论。

## 1. Git / 范围（X-01）

| 检查 | 本轮实测 | 标签 |
|---|---|---|
| `git status --porcelain`（复核前/全部运行后） | 空 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| `git rev-parse HEAD` / `HEAD^{tree}` | `db5ce03…` / `54fa04e…` | 同上 |
| `git diff --name-status main...HEAD` | **302 A / 0 M / 0 D**（302 行）；保护前缀 **0** | 同上 |
| `git diff --name-only 4706250..HEAD` | **243** 文件；0 个保护前缀命中 | 同上 |
| 变更顶层目录 | 仅 `docs/`(151)、`fixtures/`(36)、`m1_teacher/`(23)、`scripts/m1b/`(2)、`tests/m1_teacher/`(31) | 同上 |
| 必需的最终评审/修复 commit | `5d5ebf8`、`12f6290`、`c9469c3`、`9c383e5`、`580be70`、`42c90a8`、`8f8d00e`、`305416d`、`d9201e9`、`e3b7c35` 均为 HEAD 祖先 | 同上 |
| 保护路径（`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、`LiveGate`、`plugins/`、`.github/`） | 0 改动 | 同上 |

**X-01 = VERIFIED（对本 delta 范围）**：无 M0/security/bridge/config-g/scripts-g4/LiveGate/plugins/.github 变更。

## 2. P1-1 clean archive / collector 可移植性（CLOSED）

### 2.1 无 `.git` clean archive 复跑

```bash
git archive HEAD | tar -x -C /tmp/m1b-delta-archive-*   # 无 .git
cd /tmp/m1b-delta-archive-*
export TMPDIR=$(mktemp -d)
python -m pytest tests/m1_teacher -q -p no:cacheprovider
M1B_REQUIRE_OS_SANDBOX=1 python -m pytest tests/m1_teacher -q -rs -p no:cacheprovider
```

| 运行 | 实测 | Exit | 标签 |
|---|---|---:|---|
| clean archive full | **939 passed in 105.07s**（1 个 pytest 配置 warning，非失败） | 0 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| clean archive strict | **939 passed in 102.78s；0 skipped**（`-rs` 无 skip 行） | 0 | 同上 |
| worktree full（对照） | **939 passed in 102.89s** | 0 | 同上 |
| worktree strict（对照） | **939 passed in 103.15s；0 skipped** | 0 | 同上 |

首轮 `937 passed, 1 failed` 的失败项（`test_collects_executed_pass_with_full_index_entry` 要求 40-hex）已不存在；collector 测试文件收集数为 **15**（新增 1 条 no-git 回归）。

### 2.2 collector 无 git / 显式绑定探针

在无 `.git` archive 中独立运行 collector（输出到 `/tmp`，未改仓库）：

| 场景 | 实测字段 | Exit |
|---|---|---:|
| 无 git、未给 SHA | `git_sha=None`、`git_available=False`、`git_sha_source="unavailable"`、`tree_sha=None`、`branch="UNKNOWN"`、`status=EXECUTED_PASS` | 0 |
| 显式 `--git-sha 0123…4567 --tree-sha 89ab…cdef` | `git_sha=0123…4567`、`tree_sha=89ab…cdef`、`git_available=False`、`git_sha_source="explicit"` | 0 |
| 非法 `--git-sha deadbeef` | 拒绝：`--git-sha must be a 40-hex git commit id` | 2 |

实现与测试一致：`git_available` 与 `git_sha_source` 分离记录，显式值不会被标成 `git`，无 git 时不会编造 40-hex。未发现伪造路径。

**P1-1 = CLOSED。** 未发现测试弱化：该文件仅把“无 git 也必须是 40-hex”的断言改为按 `git_available` 分支，并新增 no-git/显式绑定回归。

## 3. P1-2 证据绑定最终树（CLOSED）

### 3.1 索引/哈希重算

| 项 | 重算值 | 与 Owner 声明 |
|---|---|---|
| `docs/m1b_evidence/audit-index.jsonl` | **`a11ce42948d5dd43563a1bf6befa8bb7c8600ba3b73f9df32e345b07bc66ea80`**，38 行 | 一致 |
| `docs/m1b_evidence/audit-index.json` | **`8db875301cc10f5af3af4f038b42d50a43a9291ac50c96719f7fd9ce37fc34e5`**，`entry_count=38` | 一致 |
| `e2e_b5_summary.json` | **`a07cfe7ec06208bc3271e01eaaf62a6145c753bf175b23c844658c756d444053`** | 一致 |
| 旧 27 条前缀 | 与 `9c383e5:docs/m1b_evidence/audit-index.jsonl` **逐字节相同**；sha256 **`4b9a0d0e013a5b78f39f3c604cf5dfe6c0a25346f5ef5562cd4381857e06dbec`** | 一致 |
| 旧 16 条前缀 | sha256 **`11a9f5c3820fffa9250a82837b27c555bb0e649d67c0317d2d68e8fb560dfb25`** | 一致 |
| 38 条 `raw/<run_id>/evidence.json` | 每条的 sha256 均与索引 `sha256` 相符 | 一致 |
| `audit-index.json` ↔ jsonl | `entries` 与 38 行逐项相等 | 一致 |
| 新 11 条（第 28–38 条） | 全部 `EXECUTED_PASS`、`exit_code=0`、有 `command`；`git_sha=9c383e5…`、`tree_sha=333828d…`、`git_available=True`、`git_sha_source="git"`；`limitation` 均含 `supersedes earlier final entries … c420d19` | 一致 |

### 3.2 独立再生性（本轮 HEAD）

```bash
python -m m1_teacher.e2e_b5                  # ×2
python -m m1_teacher.e2e_b5 --write-evidence /tmp/b5_a
python -m m1_teacher.e2e_b5 --write-evidence /tmp/b5_b
```

| 检查 | 实测 | 标签 |
|---|---|---|
| B5 stdout 双跑 | 逐字节相同；sha256 **`4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`**；27 行 / 4,168 bytes | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| 两次 `--write-evidence` | 5 文件 byte-identical | 同上 |
| 临时输出 vs 仓库证据 | `cf`/`interview`/`cross_domain`/`freshness`/`summary` **5/5 逐字节相同**；summary 仍为 `a07cfe7e…` | 同上 |

结论：证据包可由最终树确定性再生，且与提交内容一致；旧 27 条未被改写，11 条新记录把 `git_sha/tree_sha` 与实际测量树绑定。

### 3.3 manifest 口径

- `e2e_b5_summary.json` 的 `artifact_manifest.implementation_commit=12f6290…`；README 与 Evaluation Report §13 说明它是“最后行为代码 SHA”，生成 commit `9c383e5` 只改该常量 + 文档；collector 索引独立记录生成 SHA `9c383e5`/tree `333828d`。
- 该说明与 collector 记录不矛盾；未发现把 `12f6290` 写成“生成 commit”或“最终 PR5 SHA”的过度声明。
- **但** Evaluation Report §8 仍写 `implementation_commit=c420d19…`，与本文件 §9/§13、实现报告和实际 summary 矛盾；归入 P1-3 残留 R3。

**P1-2 = CLOSED（证据与再生性）；其遗留的 §8 文档哈希归 P1-3。**

## 4. P1-3 最终报告数字/哈希/状态（PARTIAL）

### 4.1 已修正且本轮可复算

| 检查 | 本轮命令/实测 | 标签 |
|---|---|---|
| 测试收集数 | `pytest --collect-only -q` → **939 tests collected** | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| 计数构成 | 939 = 913 + 26（B5 11 + collector 15）；实现报告 536+173+63+46+95+26 = 939 | 同上 |
| X-01 vs main | **302 A / 0 M / 0 D**；保护前缀 0 | 同上 |
| X-01 vs M1-A | **243 files** | 同上 |
| A demo 双跑 | **`b08ceee9…`；53 行 / 5,798 bytes**，逐字节相同 | 同上 |
| B4 demo `--json` 双跑 | **`b3231658…`；513 行 / 15,340 bytes**，逐字节相同 | 同上 |
| B5 demo 双跑 | **`4d0e0c85…`；27 行 / 4,168 bytes**，逐字节相同 | 同上 |
| 证据 5 文件哈希 | cf `526f9dfd…`、interview `8f3a16fc…`、cross `c02723ec…`、freshness `8a25de6e…`、summary `a07cfe7e…` | 同上 |
| PR4 P1 修复合入 | `49cf45b`、`1de6ae6` 均为 HEAD 祖先 | 同上 |
| PR1 P1-2/P1-3 表述 | 三份文档均为“实现 fail-closed / 非 root 目标部署 `NOT_RUN`”与“脚本已接线、`.github` job `NOT_CONFIGURED`”分栏 | 静态核对 |
| 历史基线 | M1-A `4706250` worktree/archive → **536 passed**；M1-Offline `290c577` → **365 passed**；两边 `git status` 空；未相加 | 同上 |
| 旧过时值 | `873`/`235`/`100`/`6b7bb66e` 未作为 final 值出现；`938`/`268`/`511`/`15,108` 仅以“reviewer 树/旧树/历史”标注出现 | 同上 |
| 三份文档主要数字/证据哈希 | 939、302/243、B4/B5/A demo、证据 5 文件在评测报告/实现报告/审阅请求间一致 | 静态核对 |

### 4.2 残留（P1-3 未全闭；均为最终评测报告）

| # | 位置 | 现状 | 可复算的正确值/应为 |
|---|---|---|---|
| R1 | `M1_B_EVALUATION_REPORT.md:89` | `test_evidence_collector.py` 写 **14 passed** | 实测 **15 passed**；§3.2/§13/实现报告均为 15 |
| R2 | `M1_B_EVALUATION_REPORT.md:115` | JD v1 journal sha256 写 **`554c1153…`** | 当前 summary 为 **`c372421798cce3169d2231ff902f07e254f1e606d43f4c1bbe5f687da6bf153a`**；`554c1153…` 是旧树（`1cad799`）值，未标历史 |
| R3 | `M1_B_EVALUATION_REPORT.md:165` | `e2e_b5_summary.json` manifest 写 **`implementation_commit=c420d19…`** | 实际为 **`12f6290c43523d5c3930915fe18810adca8609a4`**；§9/§13 已正确，仅 §8 未同步 |
| R4 | `M1_B_EVALUATION_REPORT.md:28,31,39,132` | 仍写“B5-01 独立评审 `PENDING`/“独立评审未出”/“`INDEPENDENTLY_REEXECUTED` PENDING”/“报告待 Reviewer commit 合入” | 首轮评审 `5d5ebf8` 已在 HEAD（merge `ff6daa6`），应改为 `PASS_WITH_ACTIONS`；仅 **delta 复核** 仍 `PENDING`；B5-01 在 delta 前维持 `PARTIAL` |
| R5 | `M1_B_EVALUATION_REPORT.md:229` | 最终 PR5 commit 仍是占位“由 Lead/交付记录回填” | 本 delta 分支起点为 merge **`db5ce03…`**；建议回填该 SHA 并注明 code/test 树 `d9201e9`。此条为 P2 级待回填，不是错误 hash |

这些残留说明 P1-3 的验收条件“Reviewer 仅用 `git`/`pytest`/`sha256sum`/`wc` 可复算报告每个数字与 hash”未完全满足：R1 与 `pytest` 输出冲突，R2/R3 与当前证据/manifest 冲突，R4 与本树评审状态冲突。

### 4.3 关闭建议（docs-only）

只改 `docs/M1_B_EVALUATION_REPORT.md` 的上述行：14→15；554c1153→c3724217（或删除具体值并标注旧树）；c420d19→12f6290；PENDING/待合入→`PASS_WITH_ACTIONS` + delta `PENDING` + B5-01 `PARTIAL`；回填 `db5ce03`。不改代码/测试/证据，无需重跑全量；仅需重新执行 `sha256sum`、`--collect-only`、summary/hash grep 与文档互查，即可由原 Reviewer 复核关闭 P1-3。

## 5. docs lint 修复（8f8d00e）复核

- `8f8d00e` 只改 `tests/m1_teacher/test_judge_ci_gate.py`：新增 `_without_quoted_env_toggle_mentions`，在断言前剥离引号内含“环境变量开启”的片段；未改产品代码/其它测试。
- 只读探针（复制同一辅助函数，未改仓库）：

| 输入 | 剥离后 | 断言 |
|---|---|---|
| `全 docs 无肯定式“环境变量开启”句子` | 无该短语 | **通过**（历史引用放行） |
| `历史删除说明提到 "环境变量开启" 的旧短语` | 无该短语 | **通过** |
| `旧短语 \`环境变量开启\` 仅作历史引用` | 无该短语 | **通过** |
| `可以通过环境变量开启 trusted fixture 路径` | 保留 | **失败**（未加引号肯定式仍拦截） |
| `代码内显式参数/环境变量开启` | 保留 | **失败** |
| `可以通过“环境变量开启”trusted fixture 路径` | 剥离后通过 | **通过**（见下） |

- 实际 `docs/` 全量扫描：仅 `M1_B_FINAL_INDEPENDENT_REVIEW.md` 有 1 处引号内历史引用，剥离后 0 残留；全部 docs 通过；`test_judge_ci_gate.py` 18 passed。
- **P2 观察（不阻断）**：剥离逻辑不区分“历史/否定”与“肯定”；把肯定句写成 `可以“环境变量开启”…` 也会通过。当前 docs 全量人工可读且产品不读 env，故不构成 P1；若该 guard 要承担语义防线，建议后续只放行带“历史/删除/不再/否定”上下文的引号片段。

## 6. 全量回归与测试弱化审计

| 运行 | 实测 | Exit | 标签 |
|---|---|---:|---|
| worktree full（私有 TMPDIR） | **939 passed in 102.89s** | 0 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| worktree strict `M1B_REQUIRE_OS_SANDBOX=1 -q -rs` | **939 passed in 103.15s；0 skipped** | 0 | 同上 |
| clean archive full | **939 passed in 105.07s** | 0 | 同上 |
| clean archive strict | **939 passed in 102.78s；0 skipped** | 0 | 同上 |
| 定向 B5 | **11 passed** | 0 | 同上 |
| 定向 B4 E2E + durability | **18 passed**（9+9） | 0 | 同上 |
| 定向 certification | **33 passed**（测试内含 112/112 hidden 断言） | 0 | 同上 |
| 定向 crash recovery | **35 passed**；`M1B_MATRIX_OUT` **34 行**（9/21/2/2 为 Owner 分类，本轮确认行数/无半状态断言通过） | 0 | 同上 |
| 定向 scoped + migration | **46 passed**（31+15） | 0 | 同上 |
| 定向 collector | **15 passed** | 0 | 同上 |
| 定向 judge_ci_gate | **18 passed** | 0 | 同上 |
| `ruff check m1_teacher tests/m1_teacher` | **All checks passed!** | 0 | 同上 |

测试弱化审计：`git diff c3eb736..HEAD -- tests/` 仅 2 个文件（collector、judge_ci_gate）；无新增 `skip`/`xfail`，删除行仅为旧断言/格式；collector 断言按 `git_available` 分支，judge_ci_gate 仅新增引号剥离辅助函数。未发现为通过而删除测试或放宽产品断言。

## 7. 必须保留的 NOT_RUN / UNVERIFIED / BLOCKED

1. **真实学习效果/教学收益**：`NOT_VERIFIED`；全部为 synthetic fixtures + 确定性启发式/MOCK。
2. **真实 Provider/LLM/联网/付费**：`BLOCKED`；无 Key、无网络、无 LiveGate。
3. **真实用户 CODE 对外开放**：`BLOCKED`；需人类批准 + 目标部署安全验收。
4. **非 root 目标部署 principal**：`NOT_RUN`；本地 root/uid_map→0；实现仅提供 opt-in 启动门。
5. **断电/掉盘持久性**：`UNVERIFIED`；仅真实 SIGKILL 进程崩溃矩阵。
6. **真实 auth/多租户隔离**：`NOT_RUN`。
7. **target CI 接线**：`NOT_CONFIGURED/NOT_RUN`；`.github/workflows` 无该安全 job。
8. **target OS 沙箱/内核差异/cgroup v2/并发延迟**：`NOT_RUN`。
9. **event-level `schema_version` 拒绝 / 持久 review queue**：`NOT_IMPLEMENTED`（PARTIAL 已披露）。
10. **B0-01 合同签收 / B4-04 完整双向跨域 / 真实 JD/简历/招聘网站**：`NOT_RUN`。
11. **全仓 M0 套件**：`NOT_RUN`（不在 B 线验收范围）。
12. **真实恶意代码执行/真实 sentinel**：`NOT_RUN`。
13. **人类 Gate H-01..H-08**：真实 CODE、Provider/LiveGate、非 root 部署、B0 签收、GitHub PR/合并、schema 迁移、最终签收均保持各自 `PENDING/BLOCKED/NOT_RUN`，不因本附录解除。

## 8. B5-01 状态与最终裁定建议

- **B5-01：维持 `PARTIAL`**（技术复跑已通过，但 P1-3 残留未闭；不能写成完整 PASS）。
- **最终裁定：维持 `PASS_WITH_ACTIONS`（P0=0；P1 残余 1 项：P1-3 文档残留 R1–R4）**。不升级为 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。
- 若完成 §4.3 的 docs-only errata，且复核者确认 R1→15、R2→`c3724217…`、R3→`12f6290…`、R4→`PASS_WITH_ACTIONS`/delta `PENDING`，则本 Reviewer 建议将结论更新为 **`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`**，且**仅限**：离线、合成 fixtures、确定性/mock E2E、可复现证据的本集成范围。
- 该升级仍**不包含**：真人学习收益、真实 Provider/LLM/联网/真实 JD/简历、Live/LiveGate、生产可用、真实 OS 判题安全承诺、M0 G4-H/G5/M0 决策；相关人类 Gate 仍须独立批准。

## 9. 声明 / 提交

- 本文件是本次 delta 复核唯一新增文件；只 commit 本文件；未修改源码/测试/fixture/既有文档/证据数据/既有 commit，未 amend。
- 本文命令均在 `/root/m1b/delta-review` 的 HEAD `db5ce03…` 上串行执行，私有 TMPDIR；复核前后 `git status --porcelain` 为空。
- 本文数字均来自 `INDEPENDENTLY_REEXECUTED_THIS_TURN`；引用 Owner 的历史 9/21/2/2、103/104s 等标 `OWNER_REPORTED`；未重跑的 M0/目标部署/真实 Provider 等标 `NOT_RUN/BLOCKED`。
- 本附录不授权真实用户 CODE、真实 Provider/LLM、联网研究、真实 JD/简历、LiveGate、生产部署或 M0 G4-H/G5/M0 决策。
- 提交：`docs(m1b): final independent review delta addendum — P1 closures (no-key)`；commit sha 见交付消息。
