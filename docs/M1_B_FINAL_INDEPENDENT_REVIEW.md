# M1-B / B-NEXT 最终独立验收报告（B5-01）

| 字段 | 值 |
|---|---|
| Reviewer | 最终独立 Reviewer（未参与 M1-B / B-NEXT 任何实现、修复或 Owner 证据生成） |
| 日期 | 2026-11-20 UTC |
| 工作区 / 分支 | `/root/m1b/final-review` / `b-next/m1b-final-review` |
| HEAD / tree | `c3eb7361a4f7b19d8d0fedeb2540eb63c3f7f74e` / `56b7aba98ac8167727659b843cf602b19b569fd9`（与 `work/m1b-integration` 同树） |
| 基线 | `main=3e7afee`；M1-A `4706250`；M1-Offline `290c577` |
| 环境 | Linux 6.17.13-2-pve x86_64；Python 3.11.15；pytest 9.2.0；bubblewrap 0.9.0；ruff 0.17.5；TZ=UTC 主机 |
| 运行纪律 | 每个 pytest 运行独立 `TMPDIR=$(mktemp -d)`；串行、无并发 pytest；先 worktree、后 clean archive 交叉复跑 |
| 证据标签 | `OWNER_REPORTED` / `INDEPENDENTLY_REEXECUTED_THIS_TURN` / `NOT_RUN` / `UNVERIFIED`；不含 hidden expected 明文、凭据或攻击代码 |
| 边界 | **Offline synthetic / MOCK only, not real teaching effect.** 不包含真人学习收益、联网研究、真实 JD/简历、真实 Provider/LLM、LiveGate、生产可用性、M0 G4-H/G5/M0 决策 |

## 0. 最终裁定

**`PASS_WITH_ACTIONS`**。不是无条件 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`，也不是 `BLOCKED`。

- **P0：0**。未发现真实学习收益冒充、hidden expected 明文泄漏、真实 Provider/网络/Key、伪造可信 PASS、保护路径改动或历史数字相加。
- **P1：3**（均为验收/证据/文档闭合项，不是产品行为缺陷）：
  1. **clean archive 复跑不绿**：协议 C-00 要求的无 `.git` clean archive 下，`938` 变为 **`937 passed, 1 failed`**；失败测试要求 `git_sha` 固定 40-hex，而 collector 在无 git 环境按设计返回 `None`。
  2. **证据包未绑定最终冻结树**：final 11 条 audit 记录写 `git_sha=c420d19`，但生成时工作树含未提交的 `b090bb2`/evidence 变更；`c420d19` 本身无法再生当前 evidence（其 `IMPLEMENTATION_COMMIT` 为 `e2b6e85`）。
  3. **最终报告数字/哈希/状态与最终树不一致**：X-01 `235` vs 实测 `268`；实现报告 `100` vs 实测 `209`；B4 demo `6b7bb66e/511/15108` vs 实测 `b3231658/513/15340`；分项计数表求和 `873` vs 总数 `938`；PR4 fix「未合入」、gate「未实现」等状态过时。
- **P2：6**（文档精度/历史残留；见 §10）。
- 技术门（A 536、B 365、集成 938、strict 0 skipped、demo/evidence 确定性、X-01/X-02）在可运行树中成立；但 G1（clean archive）、G6（证据与冻结 SHA 绑定）、G7（文档可复算）未完全满足，故不能给无条件 `PASS_FOR_...`。

### 0.1 关键实测一览

| 项 | 本轮实测 | 标签 |
|---|---|---|
| `pytest tests/m1_teacher -q`（worktree，私有 TMPDIR） | **938 passed**，110.86s，exit 0 | `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| `M1B_REQUIRE_OS_SANDBOX=1 pytest … -q -rs`（worktree） | **938 passed, 0 skipped**，102.92s，exit 0 | 同上 |
| clean archive（`git archive HEAD`，无 `.git`）+ strict | **937 passed, 1 failed**，104.35s，exit 1 | 同上（P1-1） |
| `scripts/m1b/run_safety_ci.sh --allow-root-synthetic` | **938 passed, 0 skipped**，102.63s，exit 0；`SAFETY CI OK` | 同上（本地合成模式） |
| 历史 M1-A `4706250` worktree | **536 passed**，14.29s，exit 0 | 同上 |
| 历史 M1-Offline `290c577` | **365 passed**，16.63s，exit 0；前后 `git status` 均空 | 同上 |
| B4 E2E + durability | **18 passed**（9+9），5.58s | 同上 |
| B5 E2E | **11 passed**，13.15s | 同上 |
| certification | **33 passed**（14 cases / 112 hidden），21.21s | 同上 |
| crash recovery | **35 passed**，14.95s；matrix **34 行**（9/21/2/2） | 同上 |
| scoped idempotency + migration | **46 passed**（31+15），2.80s | 同上 |
| judge supervisor/sandbox/negatives | **64 passed**，6.24s | 同上 |
| judge worker/fixtures/leakage/scorer | **92 passed**，15.46s | 同上 |
| `ruff check m1_teacher tests/m1_teacher` | `All checks passed!`，exit 0 | 同上 |

集成套件收集数独立确认为 **938**（owner venv 与本轮 venv 均为 938）；排除 B5 的 11 + collector 的 14 后为 **913**。M1-A `536` 与 M1-Offline `365` 只作各自历史参考，**未相加，不存在 901**。

## 1. 方法与独立性

- 本轮未修改源码/测试/fixture/既有文档；只新增本文件并 commit（§13）。评审前、测试后 `git status --porcelain` 均为空。
- 主复跑在 `/root/m1b/final-review` worktree；另用 `git archive HEAD | tar -x` 生成无 `.git` clean archive 交叉复跑（§2.2），这是本轮发现 P1-1 的方法。
- 每次 pytest 前 `export TMPDIR=$(mktemp -d)`；不同套件串行执行；未启动其它测试并发。
- 主 venv 为 `/tmp/m1b-venv`（Python 3.11.15 / pytest 9.2.0）；clean archive 的失败项另用 Owner venv（pytest 9.2.0 / pytest-asyncio 1.5.0）复核，结果相同。
- 未设置 `TZ=UTC/PYTHONHASHSEED=0` 的强隔离环境用于全量套件（环境偏差已记录）；对 demo/e2e 另做 `TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0` 双跑，hash 不变。
- 引用 Owner 数字一律标 `OWNER_REPORTED`；本轮命令结果标 `INDEPENDENTLY_REEXECUTED_THIS_TURN`；未执行项标 `NOT_RUN`。

## 2. Git / 范围（X-01）

### 2.1 事实

| 检查 | 实测 |
|---|---|
| `git status --porcelain` | 空（评审前、全部运行后） |
| `git rev-parse HEAD` / `^{tree}` | `c3eb7361…f74e` / `56b7aba9…fd9` |
| `git diff --shortstat main...HEAD` | **268 files changed, 376999 insertions(+), 0 deletions** |
| `git diff --name-status main...HEAD` | **268 A / 0 M / 0 D**（全部为新增路径） |
| `git diff --shortstat 4706250..HEAD` | **209 files changed, 353341 insertions(+), 475 deletions(-)** |
| 保护前缀（`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、`.github/`、`plugins/`） | **0 命中**（两个 diff 均检查） |
| 允许根目录之外 | 0（仅 `docs/`、`fixtures/`、`m1_teacher/`、`tests/`、`scripts/m1b/`） |
| ancestry | `main(3e7afee)` → M1-A `4706250` → B HEAD；M1-A **未**合入 `main`（`main` 树无 `m1_teacher`），M1-A 是 B 的历史祖先 |

### 2.2 结论

- **X-01 = VERIFIED**：无 M0/security/bridge/config-g/scripts-g4/.github/plugins 改动；B 线只在自身教学核、fixture、测试、脚本与文档内演进。
- 相对 M1-A 的 209 文件含 475 行删除（测试/文档更新），不是“100 文件”，也不是“235 文件”。Owner 报告中的 100/235 分别对应历史快照 `e2b6e85` 和 `c420d19`，不是最终 HEAD；属 P1-3 文档修正项。
- `536 + 365 = 901` 不存在；`938` 是本树独立计数。M1-A 的 536 在自身树可复现，但最终树中 5 个 M1-A 测试文件被 D12/去 flake 修正过，“536 原样未改”的措辞不精确（P2-4）。

## 3. 独立复跑

### 3.1 worktree（有序、私有 TMPDIR）

| # | 命令 | 实测 | Exit |
|---|---|---|---|
| E1 | `pytest tests/m1_teacher -q -p no:cacheprovider` | **938 passed in 110.86s** | 0 |
| E2 | `M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs -p no:cacheprovider` | **938 passed in 102.92s；`-rs` 无 skip 行（0 skipped）** | 0 |
| E3 | `PYTHON=/tmp/m1b-venv/bin/python ./scripts/m1b/run_safety_ci.sh --allow-root-synthetic` | **938 passed in 102.63s；`SAFETY CI OK: 0 skipped`** | 0 |
| E4 | 定向 B4 + durability | **18 passed** | 0 |
| E5 | 定向 B5 | **11 passed** | 0 |
| E6 | 定向 certification | **33 passed**（14 cases / 112 hidden 由测试断言与 fixture 计数共同确认） | 0 |
| E7 | 定向 crash recovery（`M1B_MATRIX_OUT=/tmp/rev_matrix.jsonl`） | **35 passed**；matrix **34 行**：9 rolled_back / 21 prepared / 2 goal-prepared / 2 committed，均无 snapshot 半状态 | 0 |
| E8 | scoped idempotency + scope migration | **46 passed**（31+15） | 0 |
| E9 | judge supervisor/sandbox/negatives | **64 passed** | 0 |
| E10 | judge worker/fixtures/leakage/scorer | **92 passed** | 0 |
| E11 | `--collect-only -q` | **938 tests collected**（owner venv 同值） | 0 |
| E12 | ruff | **All checks passed!** | 0 |

时间/环境与 Owner 报告（102.76/102.95/103.43s）有数秒差异，属正常调度波动；计数一致。collector 入口 `B5-01-full-suite` 记录为 103.43s、strict 为 103.10s，与本轮 E1/E2 属不同运行。

### 3.2 clean archive 交叉复跑（P1-1）

```bash
rm -rf /tmp/m1b-rev-final && mkdir -p /tmp/m1b-rev-final
git archive HEAD | tar -x -C /tmp/m1b-rev-final     # no .git
cd /tmp/m1b-rev-final
export TMPDIR=$(mktemp -d)
M1B_REQUIRE_OS_SANDBOX=1 python -m pytest tests/m1_teacher -q -rs -p no:cacheprovider
```

实测：**`1 failed, 937 passed in 104.35s`，exit 1**。唯一失败：

```text
tests/m1_teacher/test_evidence_collector.py:110
test_collects_executed_pass_with_full_index_entry
assert re.fullmatch(r"[0-9a-f]{40}", entry["git_sha"])
TypeError: expected string or bytes-like object, got 'NoneType'
```

根因：无 `.git` 时 `scripts/m1b/collect_evidence.py` 的 `git rev-parse` 返回 `None`；证据包文档（`docs/M1_B_EVIDENCE_PACKET.md`）明确允许 `git_sha` 为 `null`，但该测试要求 40-hex。用 Owner venv 单跑同一测试同样失败（`1 failed in 0.08s`），排除 venv/插件差异。clean archive 下 `python -m m1_teacher.demo` 两次仍逐字节一致且 hash 为 `b08ceee9…`，说明 demo 本身无 `.git` 依赖。

该失败不影响产品路径，但直接违反协议 C-00/G1 的 clean archive 前提；在本轮裁定中记 **P1-1**。

### 3.3 历史基线

| 线 | 命令 | 实测 | 只读性 |
|---|---|---|---|
| M1-A | `git worktree add --detach /tmp/m1a-base 4706250` 后 `pytest tests/m1_teacher -q` | **536 passed in 14.29s**，exit 0 | worktree 用后移除；主树状态空 |
| M1-Offline | `cd /root/at-m1-offline`，`pytest tests/m1_offline -q -p no:cacheprovider` | **365 passed in 16.63s**，exit 0 | 运行前后 `git status --porcelain` 均空；HEAD `290c5770…` |

两线计数分别独立，未相加；`938` 也不是历史数字的拼凑，而是最终树 `pytest` 的独立收集数。

## 4. X-02（无 Key / 无网络 / 无 Provider）

### 4.1 静态

- AST 扫描 `m1_teacher/`、`tests/m1_teacher/`、`scripts/m1b/`：网络 import（`httpx`/`requests`/`aiohttp`/`urllib`/`socket`/`http` 等）**0 命中**。
- `autoteacher_m0` 引用 16 处，全部位于测试的隔离断言/禁止集合，不是 import 或调用。
- `m1_teacher/` 与 `scripts/m1b/` 中未发现 API key/Provider/LiveGate 调用；仅边界注释与 demo 声明。
- 无真实 Key、`OPENAI_*`/`DEEPSEEK_*` 读取点，无 `.env` 依赖。

### 4.2 运行时

- 用 `sitecustomize` 阻断 `socket.socket/create_connection/getaddrinfo` 后：
  - `python -m m1_teacher.demo` → exit 0，sha256 `b08ceee9…`（与正常双跑一致）；
  - `python -m m1_teacher.e2e_b5` → exit 0，sha256 `4d0e0c85…`（一致）。
- 未启动真实 Provider、未发外部请求、未读取凭据。

**X-02 = VERIFIED（LOCAL_ONLY；真实 Provider/LiveGate 仍 BLOCKED）。**

## 5. Demo / E2E / 证据确定性

| Artifact / 命令 | 双跑 | 本轮实测 | 对照 Owner 报告 |
|---|---|---|---|
| `python -m m1_teacher.demo` | 逐字节相同（含 env-pinned、socket-blocked、无 `.git` archive） | `b08ceee915fb0363864e303ded71de4d547eae6d14f7aa693ba1537a810d491b`；53 行 / 5,798 bytes | 一致 |
| `python -m m1_teacher.demo_b4 --json` | 逐字节相同（含 env-pinned） | `b3231658a4ac12a49cd2ac57f4a3e8d9719fbf7476ca36a54e4d8f9eea72d905`；**513 行 / 15,340 bytes** | **不一致**：报告写 `6b7bb66e…` / 511 行 / 15,108 bytes（P1-3） |
| `python -m m1_teacher.e2e_b5` | 逐字节相同 | `4d0e0c851f4ff4d745127932aa62fcfabeca47da2f7d23ae434cae1ab300a2fc`；27 行 / 4,168 bytes | 一致（报告写 27 行） |
| `e2e_b5 --write-evidence` ×2 | 5 文件 byte-identical；且与仓库 `docs/m1b_evidence/` 逐字节相同 | 见下 | 一致 |

最终 B5 evidence hashes（本轮重算 = 仓库 = 报告 §9）：

| 文件 | sha256 |
|---|---|
| `e2e_b5_cf.jsonl` | `526f9dfdc63b2b0781db7e3b11abba6cbb870616f0d5368679d93309f19f0cf1` |
| `e2e_b5_interview.jsonl` | `8f3a16fc51771288c855fa94ab4cec978cf82c0864dd2aedf033c525d2f8452d` |
| `e2e_b5_cross_domain.jsonl` | `c02723ec42e8ec76f3806719ffc6eb81fa38b677623cb982fd519e2eee35925c` |
| `e2e_b5_freshness.jsonl` | `8a25de6e641313327e24f886abb1577105faae973da129f9ad49336b2a890332` |
| `e2e_b5_summary.json` | `b6e67eb71d4d1f9d4c20fe82a62e9b2eb620735be933746c33cee6a694f8fad4` |

`e2e_b5_summary.json` 的 `artifact_manifest.implementation_commit` 为 `c420d19…`，`base_sha=3e7afee…`，`generated_at=2026-11-20T00:00:00Z`；固定 manifest 本身不含 wall clock。

## 6. 证据包核验

- `audit-index.jsonl`：**27 条**。前 16 条历史快照字节保留，前 16 条前缀 sha256 = `11a9f5c3820fffa9250a82837b27c555bb0e649d67c0317d2d68e8fb560dfb25`（与 `c420d19`、`1cad799`、`861d147` 的旧文件一致）。
- final 11 条（第 17–27 条）：**全部 `EXECUTED_PASS`**，均有 `command`、`exit_code=0`、非空 `raw_evidence_path`；无 command-less PASS。
- 27 条 `raw/<run_id>/evidence.json` 的 sha256 均与条目 `sha256` 一致；`audit-index.json` 的 `entry_count=27`、`entries` 与 jsonl 逐项相等；镜像 sha256 = `05b4b9ebbed76cdef862cf638283a6a8fb65a2830cc4c6faccf7042d424d883c`；jsonl sha256 = `4b9a0d0e013a5b78f39f3c604cf5dfe6c0a25346f5ef5562cd4381857e06dbec`。
- 旧 16 条中的 `EXECUTED_FAIL`/`NOT_RUN` 保留，未删除/改写；final 11 条不覆盖旧记录。

**provenance（P1-2）**：final 11 条均记录 `git_sha=c420d193…`，utc 23:03–23:08；但 `c420d19` 的 `e2e_b5.py` 中 `IMPLEMENTATION_COMMIT="e2b6e85…"`，而当前 summary 写 `c420d19` 且其 hash 只能由 `b090bb2` 的未提交工作树产生。即记录 SHA 不能标识实际测量树；按协议 §1.3“必须绑定 command/environment/utc/exit/raw/hash”及 §11“被测冻结 SHA”，该记录不满足可复现绑定。需新增 clean-HEAD 记录或显式记录 tree/dirty 状态并重算索引。

## 7. P1 闭合核验（代码 + 测试 + 本轮探针）

| 项 | 核验 | 本轮证据 | 状态 |
|---|---|---|---|
| PR0 P1-01..P1-08 | 预审 8 项 P1 中 7 项文档修订在 ADR/PORTS（trusted_fixture、事件映射、checksum、零 diff、mastery 导入、trust registry、rubric sidecar）；P1-08 bwrap `--size` 顺序已由 PR1 修复并被 sandbox 测试覆盖 | 静态核对 ADR/PORTS/响应；`test_judge_sandbox` 17 项 + `test_judge_ci_gate` 18 项通过；B0-01 正式签收 `NOT_RUN` | **PARTIAL（文档闭合；合同签收未执行）** |
| PR1 P1-1 默认 TLE | `_is_timeout_kill`：负 exit、或 124/137/152 且 elapsed≥0.9×timeout；`RLIMIT_CPU` 提到 max(10,ceil(wall)+2)；默认 wall 为 2.0s | 独立探针：2.0s 死循环 → `TLE`、`infra_error=False`；1.5s 慢正确解 → `PASS`；`test_judge_correctness` 33 项含 4 个 TLE/慢解断言 | **CLOSED** |
| PR1 P1-2 非 root 启动 fail-closed | `M1B_REQUIRE_NONROOT_SANDBOX` + canary `_enforce_nonroot_requirement`；supervisor verdict 带 `security_profile` | 探针（env=1，root host）：`sandbox_available=False`；verdict `JUDGE_SANDBOX_UNAVAILABLE`、`infra_error=True`、`cases_passed=0`；profile `enforced=True/verified=False`、`host_euid=0`、`uid_map="65534 0 1"` | **CLOSED（实现/local）；目标非 root 部署 `NOT_RUN`** |
| PR1 P1-3 安全 CI 不可 skip | `judge_os_gate.require_os_sandbox` 统一 7 处 skip；`run_safety_ci.sh` 默认 OS+NONROOT=1、断言 0 skipped；`test_judge_ci_gate.py` 18 项 | 脚本 `--allow-root-synthetic`：938 passed / 0 skipped / exit 0；strict 直接运行同样 0 skipped | **PARTIAL**：脚本与门禁已接线到仓库入口，但 `.github/workflows` 无该 job（`NOT_CONFIGURED`），不能称 CI 已接线 |
| PR1 P1-4 环境变量措辞 | 威胁模型明确“仅可信构造/部署参数”，实现不读 env 开关；docs lint 测试 | 全量 938 中 `test_judge_ci_gate.py` 18 项（含 docs lint）通过；92 项 judge 组通过；全 docs 无肯定式“环境变量开启”句子 | **CLOSED（语义）**；changelog 仍有历史删除说明引用旧短语（P2） |
| PR2 P1-1 D12 留痕 / P1-2 goal 写点 | ADR §6/§6b + ARCHITECTURE §12 记录 `ASSESSMENT_PREPARED`；新增 goal crash case | crash 35 passed；matrix 34 行：9/21/2/2；每行无半状态；`verify_rebuild` 由测试断言 | **CLOSED**（进程 kill 语义） |
| PR3 P1-1 结构化 legacy digest | `canonical_response`（新）与 `legacy_canonical_response`（旧）分离；真实 pre-PR3 v1 fixture | `test_real_pre_pr3_structured_legacy_replays_with_old_projection` 在内共 46 项 scoped/migration 测试通过 | **CLOSED** |
| PR3 P1-2 `apply_assessment` scoped | `_find_existing_assessment` 使用 `get_event_for_learner` + `find_scope_owner`；跨 learner/session 抛 scoped conflict | 46 项测试含 legacy 跨 learner/不同 payload/同 scope 幂等 | **CLOSED** |
| PR4 P1-1 阶段计划持久化 | `SESSION_STARTED.payload.vertical.plan` / `jd_snapshot`；`restore_session()`；`_ensure_vertical_plan()` 在 start/resume/current_action/submit/advance 前恢复；缺失/损坏 fail-closed | `test_b4_durability_replay.py` 9 项全过（加速计划重启、完成后不重开、pause/resume、过期 JD、缺失/损坏、replay、篡改、版本拒绝） | **CLOSED** |
| PR4 P1-2 hidden reader allow-list | teacher-visible `learner_scripts/answers.json`；AST/路径守卫；hidden 仍只由 scorer/interview_judge 读取 | 静态扫描 `scan_hidden_reader_allowlist` = `[]`；`scan_hidden_scoring_references` = `[]`；B4/B5 E2E 18+11 通过 | **CLOSED** |
| PR4 P1-3 session replay / 版本拒绝 | `replay_session_state` / `verify_session_replay`；MAP-E12/E13；零写入 | 9 项 durability 测试含 replay 重建、跨域、篡改检测、三类版本拒绝 | **CLOSED（实现面）；event-level `schema_version` 行 PARTIAL** |

PR4 P2-2 持久复核队列仍 `NOT_IMPLEMENTED`（已披露）；B4-05 event-level schema_version 仍 `NOT_IMPLEMENTED`（PARTIAL）。这两项不得写成 PASS。

## 8. 逐项状态（B0–B5 / B1-01..06 / B4-01..03 / B5-01 / B-Q1..Q5 / X-01/02）

| 项 | 状态 | 本轮依据 / 限制 |
|---|---|---|
| B0-01 合同收敛 ADR | **PARTIAL** | ADR/PORTS/CI 文档在树，PR0 预审 P1-01..07 文档层修订 + P1-08 bwrap 顺序修复；B0-01 的独立合同签收/维护者冻结仍 `NOT_RUN` |
| B1-01 不可信 CODE 默认 blocked | **VERIFIED (LOCAL_ONLY)** | 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；本轮 92+64 judge 测试与全量通过；真实用户 CODE 仍 `BLOCKED` |
| B1-02 hidden expected 隔离 | **VERIFIED (LOCAL_ONLY)** | worker 调用最小字段；PR1 评审探针 + 本轮 judge 测试；target-deploy 复核 `NOT_RUN` |
| B1-03 结果伪造 | **VERIFIED (LOCAL_ONLY)** | 12 协议伪造/6 内存伪造/真实 fd 伪造均非 PASS；PR1 评审 + 本轮 negatives 11 项；不能伪造 PASS |
| B1-04 OS confinement | **PARTIAL** | bwrap uid/gid/net/pid/ro-FS/rlimit/canary 本地通过；宿主 root、uid_map `65534→0`；非 root principal 目标部署 `NOT_RUN` |
| B1-05 判题正确性/可用性 | **PARTIAL** | 14/14 参考解、112/112 hidden、TLE 已修复（本轮探针）；目标部署 latency/resource/非 root `NOT_RUN` |
| B1-06 hidden 泄漏扫描 | **VERIFIED (LOCAL_ONLY)** | 92 项 judge 组（含 hidden leakage 16）通过；运行时导出扫描无 hidden 内容；target-deploy 运行时导出复核 `NOT_RUN` |
| B2-01 原子 turn commit | **VERIFIED** | 单 `BEGIN IMMEDIATE`；crash 35 项；34 行 matrix 无半状态 |
| B2-02 crash replay | **VERIFIED** | 9/21/2/2 分组全部收敛；恢复幂等；断电持久性 `UNVERIFIED` |
| B2-03 并发语义 | **VERIFIED** | 真实双进程显式 `IDEMPOTENCY_CONFLICT`；分布式/多主机 `NOT_RUN` |
| B3-01 scoped result id | **VERIFIED** | 46 项 scoped/migration + PR3 评审独立探针；跨 learner/session 不可读 |
| B3-02 同 key 不同 payload | **VERIFIED** | 稳定 `IDEMPOTENCY_CONFLICT`；不返回旧成绩；零写入 |
| B4-01 双 CF 闭环 | **VERIFIED (E2E-MOCK)** | B4 E2E 9 项 + B5 CF 段；同一 SQLite/learner journal；合成学生 |
| B4-02 双 Interview + JD v1→v2 | **VERIFIED（会话内，E2E-MOCK）** | B4 durability 9 项（含重启/暂停恢复）；JD v1→v2 只影响新计划；persistent review queue 仍 `NOT_IMPLEMENTED` |
| B4-03 Freshness 门禁 | **VERIFIED (E2E-MOCK)** | 9 场景 KEEP2/UPDATE2/RECHECK5；5 个 RECHECK + 3 JD 门零写入；无真实抓取 |
| B4-04 跨域/换学科 | **PARTIAL** | CF→Interview→CF 跨域 replay 通过；Interview 方向的重启/跨域覆盖仍有限 |
| B4-05 版本不兼容拒绝 | **PARTIAL** | MAP-E12/E13 的 session/vertical/plan policy 三类已实现并测试；event-level `schema_version` 行 `NOT_IMPLEMENTED` |
| **B5-01 独立产品评审** | **PARTIAL（本轮完成复跑，附 P1 actions）** | A 536 / B 365 / 集成 938（worktree）/ 937+1（clean archive）；旧线未相加；P1-1/2/3 未关闭前不能给无条件 PASS |
| B-Q1 CODE 反例 | **VERIFIED (LOCAL_ONLY)** | 新 supervisor/worker/OS 沙箱 + 攻击模板矩阵；旧 CODE 路径已从 canonical 删除；真实恶意代码未运行 |
| B-Q2 crash 矩阵 | **VERIFIED（进程 kill 语义）** | 34 行 9/21/2/2；`verify_rebuild`；断电持久性 `UNVERIFIED` |
| B-Q3 全局 result_id 负例 | **VERIFIED** | 同 learner/跨 session/跨 item/跨 learner 同 token 均不可读/冲突；details 只含 requester |
| B-Q4 双实现映射 | **PARTIAL** | ADR/PORTS 的字段映射与 checksum/rollback 设计在树；B0-01 独立合同签收 `NOT_RUN`；迁移实现未在真实 learner DB 演练 |
| B-Q5 Judge 错误摘要泄漏 | **PARTIAL** | 新 canonical 路径运行时扫描无 hidden；历史 `m1_offline/cf/judge.py` 仍存在 `expected_repr` 泄漏面且未在本线整改（未集成到 canonical judge） |
| X-01 范围漂移 | **VERIFIED** | 268 文件对 main 全部新增；保护路径 0 命中；209 文件对 M1-A |
| X-02 Key/网络/付费 | **VERIFIED (LOCAL_ONLY)** | AST 0 网络 import；socket 阻断 demo/e2e 通过；无 Key/Provider；LiveGate 未触碰 |

## 9. 必须保留的 NOT_RUN / UNVERIFIED / BLOCKED

1. **真实学习效果/教学收益**：`NOT_VERIFIED`；全部为 synthetic fixtures + 确定性启发式/MOCK。
2. **真实 Provider/LLM/联网/付费**：`BLOCKED`；无 Key、无网络、无 LiveGate。
3. **真实用户 CODE 对外开放**：`BLOCKED`；需人类批准 + 目标部署安全验收。
4. **非 root 目标部署 principal**：`NOT_RUN`；本地 root/uid_map→0；实现仅提供 opt-in 启动门。
5. **断电/掉盘持久性**：`UNVERIFIED`；仅真实 SIGKILL 进程崩溃矩阵。
6. **真实 auth/多租户隔离**：`NOT_RUN`；当前 learner_id 由上层传入，无真实鉴权。
7. **target CI 接线**：`NOT_CONFIGURED/NOT_RUN`；仓库 `.github` 无测试/security job（B 线禁改 `.github`）。
8. **target OS 沙箱/内核差异/cgroup v2/并发延迟**：`NOT_RUN`。
9. **event-level `schema_version` 拒绝**：`NOT_IMPLEMENTED`（PARTIAL）。
10. **持久 review queue/审批 UI**：`NOT_IMPLEMENTED`（已披露）。
11. **B0-01 合同签收 / B4-04 完整双向跨域 / 真实 JD/简历/招聘网站**：`NOT_RUN`。
12. **全仓 M0 套件**：本轮未跑（不在 B 线验收范围；历史 6 failed/1697 passed/19 skipped 不重跑）。
13. **真实恶意代码执行/真实 sentinel**：`NOT_RUN`；仅 synthetic 攻击模板。
14. **clean archive 的 938 passed**：`NOT_RUN`（实测为 937+1；修复后需重跑）。

## 10. 动作（P0/P1/P2）

### P0
无。

### P1-1 clean archive / collector 可移植性
- **动作**：让 `test_collects_executed_pass_with_full_index_entry` 接受无 git 时的 `git_sha=None`（按 `M1_B_EVIDENCE_PACKET.md` 的 `string/null` 契约），并给 collector 增加显式 `--git-sha`/`--tree-sha`（或 clean-archive 记录方式），使证据包在无 `.git` 时仍能绑定冻结 SHA。
- **验收**：`git archive HEAD | tar -x` → 无 `.git` → `M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs` → **938 passed / 0 skipped / exit 0**；audit entry 记录 clean-archive 的 40-hex SHA 与 tree sha。

### P1-2 证据包绑定最终树
- **动作**：在 clean HEAD 上重生成 final 11 条（或记录 `tree_sha` + 工作树 dirty 状态 + `b090bb2/c3eb736` delta），使 `git_sha` 与实际测量树一致；同步修正 `e2e_b5_summary.implementation_commit` 的语义（当前 `c420d19` 的 checkout 不能生成该 summary）；重算 `audit-index.jsonl`/`audit-index.json`/B5 hashes 并更新报告 §13。
- **验收**：按记录 SHA/tree 复跑可得到相同 evidence hashes；或明确记录“dirty tree + tree hash”并保留旧 16 条；`c420d19` 不再是唯一绑定。

### P1-3 最终报告数字/哈希/状态 errata
- **动作**：修正 `M1_B_EVALUATION_REPORT.md`、`M1_B_IMPLEMENTATION_REPORT.md`、`M1_B_REVIEW_REQUEST.md`：
  - X-01 final：`268`（不是 235）；相对 M1-A：`209`（不是 100）。
  - B4 demo：`b3231658…`、`513` 行、`15,340` bytes（不是 `6b7bb66e…`/511/15,108）；与 `M1_B_DOMAINS_IMPLEMENTATION.md` 一致。
  - 938 分项表：当前行求和 873 ≠ 938；改为可复算的 938 = 913（PR4 final）+ 25（B5 11 + collector 14），或按最终文件计数重列。
  - PR4 review-fix 已由 `49cf45b`/`1de6ae6` 合入；`M1B_REQUIRE_OS_SANDBOX` 已在树；review request 的“待合入/NOT_CONFIGURED”表述需更新。
  - PR1 P1-2 区分“实现已 fail-closed（opt-in）”与“非 root 目标部署 NOT_RUN”；PR1 P1-3 标“脚本已接线，`.github` job NOT_CONFIGURED”。
- **验收**：Reviewer 仅用 `git`/`pytest`/`sha256sum`/`wc` 可复算报告每个数字与 hash；grep 不到旧值（235/100/6b7bb66e/511/15108/873 等作为 final 值）。

### P2
- **P2-1**：最终报告的 `demo_b4 --json` 行数/字节数（511/15,108）与实测（513/15,340）不一致；PR4 response 只有 hash `b3231658…`（与实测一致），应统一为 post-PR4-fix 上下文并补行数/字节。
- **P2-2**：PR2 crash matrix 仍引用 32 行/旧 hash；最终树为 34 行，9/21/2/2；旧 hash 标历史或删除。
- **P2-3**：`M1_B_THREAT_MODEL_JUDGE.md` changelog 仍字面引用“环境变量可开启 trusted fixture”的删除说明；改为不含该短语的表述；`M1_B_INTERVIEW_FRESHNESS_MAPPING.md` 的 event `schema_version` 行与实现 PARTIAL 对齐。
- **P2-4**：把“M1-A 536 含于其中、未改”改为“536 为历史基线，最终树有 5 个测试文件因 D12/去 flake 更新”；不要暗示 536 是原样子集。
- **P2-5**：`docs/M1_ARCHITECTURE.md` §14 仍写 `schema_meta.version == 1`（实际 v2），更新或标注历史。
- **P2-6**：`M1_B_REVIEW_REQUEST.md` 的 C-10 B4 hash 期望值、C-06“无脚本/env”等条目按最终树更新；旧 16 条 audit 记录保留但标注“历史窗口”。

## 11. 诚实性审查

**一致/合格的部分**
- 未出现 `536 + 365 = 901`；未把 M1-Offline 365 混入 938；未把 M1-A 536 与 B 线 365 相加。
- 未把 MOCK/合成结果写成真实学习收益；评价/实现/评审文档均明确 `NOT_VERIFIED`/`MOCK`。
- 未把 PARTIAL/BLOCKED 整体写成 PASS；`B1-04`/`B1-05`/`B4-05` 等保留 PARTIAL；评估报告明确 Owner 侧 `PENDING`，未预填最终 PASS。
- 默认结论没有被写成“整体 PASS”；§11 边界明确排除真人收益/联网/Provider/LiveGate。
- hidden expected 明文/凭据未进入本轮报告与证据包（只引用计数、hash、测试名）。

**不一致/需修正的部分**
- 最终树的数字/哈希/状态在多份文档中过时（P1-3），部分为相互矛盾（B4 hash、938 分项和、PR4 合入状态、gate 状态）。
- 证据包 final 11 条与最终 SHA 的绑定不成立（P1-2）；`EXECUTED_PASS` 仅执行事实，不是产品 PASS，报告大体遵守但 `B5-01` 的“final tree 实测”措辞需加 dirty-tree 注记。
- `536` 被描述为“未改”不精确（5 个测试文件被更新）；应保留历史基线标签而非子集断言。
- `M1_B_EVALUATION_REPORT.md` 的 `102.76s/102.95s` 与 collector 的 `103.43s/103.10s` 是不同运行；时间非门禁，但应标注运行来源。
- PR1 P1-2 的“NOT CLOSED”与 550ad37 实现不一致：实现侧启动门已存在且本轮探针通过；非 root 目标部署仍未验证。应分栏表述。

## 12. 复现命令（本轮）

```bash
cd /root/m1b/final-review
git status --porcelain
git rev-parse HEAD && git rev-parse HEAD^{tree}
git diff --name-only main...HEAD | wc -l
git diff --name-only 4706250..HEAD | wc -l
git diff --name-only main...HEAD | grep -E '^(src/autoteacher_m0/|security/|bridge/|config/g|scripts/g4|\.github/|plugins/)' || true

export TMPDIR=$(mktemp -d)
PY=/tmp/m1b-venv/bin/python
"$PY" -m pytest tests/m1_teacher -q -p no:cacheprovider
M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs -p no:cacheprovider
"$PY" -m pytest tests/m1_teacher/test_b4_e2e.py tests/m1_teacher/test_b4_durability_replay.py -q
"$PY" -m pytest tests/m1_teacher/test_b5_e2e.py -q
"$PY" -m pytest tests/m1_teacher/test_judge_correctness.py -q
"$PY" -m pytest tests/m1_teacher/test_crash_recovery.py -q
"$PY" -m pytest tests/m1_teacher/test_scoped_idempotency.py tests/m1_teacher/test_scope_migration.py -q
PYTHON="$PY" ./scripts/m1b/run_safety_ci.sh --allow-root-synthetic
"/root/Autonomous Teacher/.venv/bin/ruff" check m1_teacher tests/m1_teacher

# historical baselines
git worktree add --detach /tmp/m1a-base 4706250
(cd /tmp/m1a-base && "$PY" -m pytest tests/m1_teacher -q)
git worktree remove /tmp/m1a-base --force
(cd /root/at-m1-offline && git status --porcelain && "$PY" -m pytest tests/m1_offline -q -p no:cacheprovider)

# demos / evidence
"$PY" -m m1_teacher.demo > /tmp/d1; "$PY" -m m1_teacher.demo > /tmp/d2; cmp /tmp/d1 /tmp/d2; sha256sum /tmp/d1
"$PY" -m m1_teacher.demo_b4 --json > /tmp/b41; "$PY" -m m1_teacher.demo_b4 --json > /tmp/b42; cmp /tmp/b41 /tmp/b42; sha256sum /tmp/b41; wc -lc /tmp/b41
"$PY" -m m1_teacher.e2e_b5 > /tmp/e1; "$PY" -m m1_teacher.e2e_b5 > /tmp/e2; cmp /tmp/e1 /tmp/e2; sha256sum /tmp/e1; wc -l /tmp/e1
rm -rf /tmp/b5a /tmp/b5b
"$PY" -m m1_teacher.e2e_b5 --write-evidence /tmp/b5a
"$PY" -m m1_teacher.e2e_b5 --write-evidence /tmp/b5b
diff -r /tmp/b5a /tmp/b5b
sha256sum /tmp/b5a/*

# clean archive (P1-1)
rm -rf /tmp/m1b-rev-final && mkdir /tmp/m1b-rev-final
git archive HEAD | tar -x -C /tmp/m1b-rev-final
(cd /tmp/m1b-rev-final && export TMPDIR=$(mktemp -d) && M1B_REQUIRE_OS_SANDBOX=1 "$PY" -m pytest tests/m1_teacher -q -rs -p no:cacheprovider)

# audit index
sha256sum docs/m1b_evidence/audit-index.jsonl docs/m1b_evidence/audit-index.json
head -16 docs/m1b_evidence/audit-index.jsonl | sha256sum
```

## 13. 声明 / 提交

- 本文件是唯一新增文件；只 commit 本文件；未修改源码/测试/fixture/既有文档/既有 commit，未 amend。
- 本评审不授权真实用户 CODE、真实 Provider/LLM、联网研究、真实 JD/简历、LiveGate、生产部署或 M0 G4-H/G5/M0 决策；相关项保持 `BLOCKED`/`NOT_RUN`。
- 本文数字均来自本轮 `INDEPENDENTLY_REEXECUTED_THIS_TURN` 命令与 §6 证据重算；与 Owner 声明不一致处已逐项标注（P1-3）。
- 提交：`docs(m1b): final independent integration review (no-key)`；commit sha 见交付消息。
