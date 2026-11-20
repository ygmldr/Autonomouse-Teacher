# M1-B 独立测评协议（B-NEXT / B-PR5 前置设计）

| 字段 | 值 |
|---|---|
| 文档状态 | **DESIGN / 协议冻结候选**（本文件只定义测评与取证方法，不含任何新实现或新运行结果） |
| 文档版本 | `m1b.evalprotocol.v0`（2026-11-21 draft；冻结后仅追加修订记录） |
| 适用工作区 | `/root/m1b/evalproto`，分支 `b-next/pr5-eval-protocol`，基线 `work/m1a-mvp@4706250643fd42d48d69ddad7159e011955fa9fd` |
| 适用对象 | LeadB、各 PR Implementer、独立 Reviewer（含 Security/Fault/Policy 分离评审）、维护者 |
| 本文件证据等级 | `SOURCE_INSPECTED`（本轮阅读源码/历史报告）+ `DESIGN`；**不包含** `INDEPENDENTLY_REEXECUTED_THIS_TURN` |
| 本文件不声称 | 任何新测试已运行、任何新集成已 PASS、任何真实教学效果、真实 Provider/网络/LiveGate 授权 |
| 默认最终结论（仅当全部门通过时） | `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`（见 §10） |

> 本协议的上位约束来自 LeadB 交接包（`02_LEADB_AGENT_HANDOFF.md` B5、`AUDIT_REQUESTS.md`、`TEST_EVIDENCE_MATRIX.csv`、`COMMON_REVIEW_AND_ROADMAP.md` §0/§4）与两条历史线的独立报告。协议只规定**如何独立验证**，不替代任何实现。

---

## 0. 文档控制与边界

1. **设计而非结果**：本文件中的命令模板、字段、门禁全部是待执行协议；未执行项一律 `NOT_RUN`，不得被后续文档引用成 PASS。
2. **历史引用隔离**：M1-A 与 M1-Offline 的历史 P2/P1 修复与独立 PASS 仅作为**历史冻结参考**（§2），与新 B 线（B-PR0…B-PR5）验收严格分离。
3. **适用范围**：仅 B 线（`m1_teacher` 候选 canonical core + `m1_offline` 垂直能力整合）。A 线（G4-R/G4-H/G5/LiveGate）与 M0 决策不在本协议授权内（§7、§10）。
4. **修改规则**：本协议冻结后只允许 append-only 修订；任何门禁放宽、STOP 清单删减、证据分类重定义都需要维护者批准并记录修订号。
5. **术语一致性**：本文件的证据类（§1）与证据来源（§1.2）是全 B 线文档（PR 报告、Reviewer 报告、audit-index、STATUS）唯一合法词汇；其它文档使用同义/近义词时以本协议为准。

---

## 1. 证据分级词汇表（冻结）

### 1.1 证据类（Evidence Class，八值冻结）

| 证据类 | 定义 | 允许出现的位置 | 不得用于 |
|---|---|---|---|
| `MOCK` | 合成 fixtures、mock runtime/学生/Provider、脚本化结果或模拟收益 | 设计、演示、E2E 合成路径、fixture 说明 | 真实学习收益、真实模型能力、生产可用性 |
| `DETERMINISTIC` | 在冻结输入/固定 seed/固定时间戳下可重复的本地计算断言（pytest、hash、replay、静态扫描） | 测试报告、artifact 清单、命令证据 | 推断真实行为或学习效果 |
| `HUMAN_REVIEWED` | 指定 human/独立 Reviewer 对**明确范围**的人工审查（须注明 reviewer、范围、证据） | Reviewer 报告、维护者 Gate 记录 | 代替自动复跑、扩大范围外推 |
| `NOT_VERIFIED` | 能力/行为被声称或要求，但当前**没有任何独立证据**（可复现命令/哈希/报告） | 计划、风险、缺口清单 | 写成 PASS、写成已实现 |
| `UNVERIFIED` | 依赖本线之外、当前无法验证的系统（如 M0 Runtime API、真实 Provider、外部 OS 环境）；或来源声称但无法在 B 线范围内核实 | 边界声明、外部依赖声明 | 借外部来源自动转 PASS |
| `BLOCKED` | 需要人类授权、外部依赖或跨线决策才能推进；B 线不可自行解除 | Gate/风险记录、STATUS | 用"未做"替代、降级成 `NOT_RUN` 后放行 |
| `NOT_RUN` | 计划中但本轮**未执行**的命令/测试/探针；未执行原因必须写出 | 矩阵、报告、audit-index | 写成通过、省略不报 |
| `INDEPENDENTLY_REEXECUTED` | **仅限 Reviewer 本轮真正在独立环境复跑**并产出的结果（命令、exit code、哈希、日志齐全） | Reviewer 本轮报告、audit-index | Owner 报告、历史引用、由报告"复述"得来 |

**冻结规则**：`HUMAN_REVIEWED` 与 `INDEPENDENTLY_REEXECUTED` 都必须附 reviewer 身份与独立证据；`MOCK` 不得与"真实收益"在同一结论句中出现；`NOT_VERIFIED` / `UNVERIFIED` / `BLOCKED` / `NOT_RUN` 之间不得互相替换以规避缺口。

### 1.2 证据来源（Evidence Source，四值冻结，不可混用）

| 来源 | 定义 | 允许的写法 |
|---|---|---|
| `SOURCE_INSPECTED` | 本轮直接阅读源码/文档/历史证据得出的"已读"结论 | "inspected: ..." 只能描述阅读结果，不能替代运行 |
| `OWNER_REPORTED` | 实现者（Owner）自己报告的结果；默认视为未独立验证 | 仅作引用；不得写成 `INDEPENDENTLY_REEXECUTED` |
| `REVIEWER_REPORTED` | 独立 Reviewer 在**过去轮次**报告的结果（可引用其报告与 SHA） | 可作历史引用；不得写成"本轮复跑" |
| `INDEPENDENTLY_REEXECUTED_THIS_TURN` | Reviewer **本轮**在冻结 SHA + 独立环境真实执行产生 | 本轮 Reviewer 报告/audit-index；必须附命令、exit code、utc、哈希 |

### 1.3 组合规则（强制）

1. 每条结论 = `[证据类] + [证据来源]`；如 `DETERMINISTIC + INDEPENDENTLY_REEXECUTED_THIS_TURN`。
2. Owner 的 `MOCK/DETERMINISTIC` 结果只能标 `OWNER_REPORTED`；必须被 Reviewer 以本轮独立复跑重新标注后，才能进入 Gate 判定。
3. 历史报告中的 536/365 与哈希只能标 `REVIEWER_REPORTED`（历史）或 `OWNER_REPORTED`；**任何情况下不得**标 `INDEPENDENTLY_REEXECUTED_THIS_TURN`。
4. `INDEPENDENTLY_REEXECUTED` 必须绑定：`command` + `environment` + `utc` + `exit_code` + `raw_evidence_path/sha256`（见 §11）；缺任何一项即降级为 `REVIEWER_REPORTED`。
5. 不允许的混用（发现即 STOP，§12）：`OWNER_REPORTED` 写成 `INDEPENDENTLY_REEXECUTED`；`MOCK` 结果写成真实收益；`NOT_RUN/BLOCKED/UNVERIFIED` 被改写为 `PASS`；历史两套数字相加成"统一 N tests"；无哈希/无命令的"PASS"。

---

## 2. 历史冻结参考（只引用，不相加）

两条历史交付线**不同基线、不同合同、不同分支**，不是连续的 PR 链；其独立 PASS 只覆盖各自范围，不能组合成"已集成完成"。

| 历史线 | 冻结实现/修复 SHA | 报告/审查 SHA | 历史结论（引用） | 历史数值（`REVIEWER_REPORTED`，仅参考） |
|---|---|---|---|---|
| M1-A Offline Adaptive Teacher MVP | C5 `d4f10f3…`；C6 证据确定性修复 `3010426d9557fa1042f9c06cfef491758e1dce72` | branch tip `4706250`（含独立 Review 文档）；Review `docs/M1_INDEPENDENT_REVIEW.md` | `PASS_FOR_M1A_OFFLINE_MVP`（0 P0 / 1 P1→C6 关闭 / 0 P2） | 536 tests（PR1 268 + PR2 100 + PR3 50 + PR4 75 + PR5 43）；demo `b08ceee9…`（53 行）；evidence `e2e_student_a.jsonl 171cc654…`、`e2e_student_b.jsonl 5e84229e…`、`e2e_summary.json 23b871a3…` |
| M1-Offline Teacher（B 线设计与评测） | C2 `052d980d9a45558da8789c90725ae6c48f3f7a7d` | branch tip `290c5770…`；Review `docs/m1/REVIEW_M1_OFFLINE.md` | `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE`（P1-1/P2-1..6 关闭；P2-7 disclosed/deferred） | 365 tests；demo hash 依公开面文件集合而不同：clean C2 `1d57ca62…`（38 行）、artifact 上下文 `2282caff…`；artifact `eval_baseline_v1.json 25ed416a…`、`.md 154ef1d8…`、`contamination_v1.json 8b80a6f3…`、`cf_loop_canonical.jsonl 6e3d96ae…`、loop traces `ed850c77…`/`4019c946…` |

**强制禁令**：

1. **禁止相加**：`536 + 365 = 901` 之类的"统一测试数"没有任何意义，属 STOP 行为（§12）。B 线新集成套件必须在**新分支/新冻结 SHA**上单独执行、单独计数、单独写 `docs/M1_B_EVALUATION_REPORT.md`。
2. **禁止跨线借用**：M1-A 的 PASS 不能证明 M1-Offline 的评测协议；反之亦然；也不能证明二者集成可用。
3. **禁止把分支名当 PR**：历史交付是分支（`b-pr5`、`work/m1a-mvp`、`work/m1-offline-design`）而非合并 PR；集成必须走新的独立评审与合并流程。
4. **哈希上下文**：M1-Offline 的 demo/artifact hash 对公开面文件集合敏感（clean C2 与含 review 文档的 worktree 值不同）。任何 artifact 哈希引用都必须记录其**生成上下文**（冻结 SHA、文件集合/`git status`、命令、utc）；不同上下文的差异不等于回归（但必须解释）。
5. **历史 P2 教训**：M1-Offline P2-7（report JSON 含 `environment.utc_timestamp`）与 M1-A P1-1（summary 含 wall-clock/git）说明"artifact 可复现"必须把**确定性字段与非确定性字段**分开声明（§3.5、§11）。

---

## 3. 独立复跑协议（Reviewer 可执行）

### 3.1 角色与独立性

1. **Implementer/Owner** 只能产出 `OWNER_REPORTED` 证据；不得修改 Reviewer 证据，不得为 Reviewer 预生成"可验收"的结论文档。
2. **Reviewer** 必须与实现者分离（B 线实现 Reviewer 与 A 线安全 Reviewer 职责分离）；不得修改被审实现/测试/fixture；只能写自己的 review 文档与 `/tmp` 探针/证据。
3. Reviewer 的验收结论只能来自**本轮**自己的命令（`INDEPENDENTLY_REEXECUTED_THIS_TURN`）；引用 owner 报告时必须显式降级为 `OWNER_REPORTED` 并附引用来源。
4. 每条 Reviewer 命令产物必须落盘（`raw_evidence_path`）+ 计算 `sha256`，并在 audit-index（§11）登记；未登记的运行不得进入 Gate。
5. Reviewer 必须在**冻结 SHA 的 clean archive 副本**上执行，不得在实现者 worktree 上直接验收；真实 worktree 只读检查 `git status --porcelain` 以发现未提交漂移。

### 3.2 环境基准（每轮记录到 audit-index.environment）

```bash
# 方案 A：最小显式环境（推荐；不引入 provider/Key 变量）
cd /tmp/m1b-rev/<line>-<sha>
env -i \
  PATH=/usr/local/bin:/usr/bin:/bin \
  HOME=/tmp/m1b-home \
  TMPDIR=/tmp/m1b-tmp \
  TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 \
  PYTHONHASHSEED=0 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest <suite> -q

# 方案 B：保留宿主环境但显式隔离（必须记录并清空敏感变量）
env -u PYTHONPATH -u M1_TEACHER_FIXTURES -u OPENAI_API_KEY -u DEEPSEEK_API_KEY \
  TZ=UTC LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest <suite> -q
```

强制项：

1. `TZ=UTC`、`LANG=C.UTF-8`、`LC_ALL=C.UTF-8`、`PYTHONHASHSEED=0`。
2. 全新解包目录，清理 `__pycache__` / `.pytest_cache` / `.ruff_cache`（clean archive 本应没有；若出现必须记录来源）。
3. 禁止：真实 API Key、Provider 配置文件、真实个人数据、外部网络；M1 相关 `M1_TEACHER_FIXTURES` 若被使用必须显式记录并校验 fixture 树哈希。
4. Python：`/root/Autonomous Teacher/.venv/bin/python`（3.11.x）；pytest/ruff 版本写入环境记录。
5. 每套测试结束后记录 `python -m pytest ... -q` 的**完整末行**（passed/failed/skipped 数）与 exit code；`skipped` 不为 0 时必须逐条列出理由，否则该子集降级为 `NOT_RUN`。

### 3.3 冻结副本获取（clean archive）

```bash
# M1-A（C6 修复后历史冻结参考；本轮 Reviewer 复跑用）
rm -rf /tmp/m1b-rev/m1a-c6 && mkdir -p /tmp/m1b-rev/m1a-c6
git -C /root/m1b/evalproto archive 3010426d9557fa1042f9c06cfef491758e1dce72 \
  | tar -x -C /tmp/m1b-rev/m1a-c6

# M1-Offline（C2 修复后历史冻结参考）
rm -rf /tmp/m1b-rev/m1off-c2 && mkdir -p /tmp/m1b-rev/m1off-c2
git -C /root/m1b/evalproto archive 052d980d9a45558da8789c90725ae6c48f3f7a7d \
  | tar -x -C /tmp/m1b-rev/m1off-c2

# B 线新 PR / 集成（每个 PR 冻结 SHA 由 LeadB 发布；示例占位）
# git archive <B_PR_SHA> | tar -x -C /tmp/m1b-rev/<pr-id>
```

要求：`archive` 后核对解包目录内无 `.git`、无未提交文件；记录解包命令与文件数/树哈希。若仓库尚未包含目标 SHA（例如新分支未 fetch），Reviewer 必须报告 `BLOCKED` 而不是在旧树上验收。

### 3.4 命令矩阵（历史两套 + 新套件）

下表中的 `<VENV_PY>` = `/root/Autonomous Teacher/.venv/bin/python`；所有命令默认在 clean archive 根目录执行（`cd /tmp/m1b-rev/<copy>`）。

| # | 对象 | 命令（模板） | 历史/预期不变式（仅 `REVIEWER_REPORTED` 参考） | 必须记录 |
|---|---|---|---|---|
| C-01 | M1-A 全套 | `<VENV_PY> -m pytest tests/m1_teacher -q` | 历史 536 passed，0 failed/skip | exit code、末行、utc、SHA |
| C-02 | M1-A 分 PR 计数 | `<VENV_PY> -m pytest tests/m1_teacher --collect-only -q` 后按文件统计 | 历史 268/100/50/75/43 | 计数命令与原始输出 |
| C-03 | M1-A demo 双跑 | `<VENV_PY> -m m1_teacher.demo > /tmp/d1.txt; ... > /tmp/d2.txt; diff ...; sha256sum` | 历史 `b08ceee9…`，53 行 | 两文件 sha256、diff exit |
| C-04 | M1-A evidence 复跑 | `<VENV_PY> -m m1_teacher.demo --write-evidence; sha256sum docs/m1a_evidence/*` | 历史 `171cc654…`/`5e84229e…`/`23b871a3…` | 3 个 sha256 + 文件行数 |
| C-05 | M1-A CLI | `<VENV_PY> -m m1_teacher.cli --help; --student both --json; --demo` | 历史 536 tests 对应 CLI 行为 | exit code、JSON schema 键 |
| C-06 | M1-A no-.git 复跑 | 复制 `m1_teacher/`+`fixtures/m1_teacher/` 到无 `.git` 目录，重跑 C-03/C-04 | 历史 P1-1 修复后 summary/A/B 字节一致 | 两目录 sha256 对比 |
| C-07 | M1-Offline 全套 | `<VENV_PY> -m pytest tests/m1_offline -q` | open 历史 365 passed，0 failed/skip | exit code、末行 |
| C-08 | M1-Offline 评测子集 | `pytest tests/m1_offline/test_{closed_loop,evaluation_protocol,negatives,contamination,compare_v0_v1}.py -q` | 历史 76 passed | 同上 |
| C-09 | M1-Offline CF / Interview 子集 | `pytest tests/m1_offline/test_{cf_judge,cf_teacher,cf_negatives}.py -q`；`...test_{interview_coach,interview_rubric,freshness}.py -q` | 历史 75 / 49 passed | 同上 |
| C-10 | M1-Offline demo 双跑 | `<VENV_PY> -m m1_offline.demo > d1; ... > d2; diff; sha256sum` | 历史 clean C2 `1d57ca62…`（38 行）；artifact 上下文 `2282caff…`；须记录文件集合上下文 | 两文件 sha256 + 上下文 |
| C-11 | M1-Offline artifacts | `<VENV_PY> -m m1_offline.demo --write-artifacts; sha256sum docs/m1/traces/*.jsonl docs/m1/reports/*` | 历史 `ed850c77…`/`4019c946…`/`25ed416a…`/`154ef1d8…`/`8b80a6f3…`（report JSON 含 `utc_timestamp` 非确定性字段，见 P2-7） | trace 与 report 分别标注 deterministic/volatile |
| C-12 | M1-Offline canonical 回放 | 用 `m1_offline.evaluation.harness.replay_trace` 对 `cf_loop_canonical.jsonl` 重建；断言 events=19、assessments=3、evidence=6、final_state==最后一个 memory 快照、且逐字节等于 live run 的 `to_jsonl()` | 历史 `6e3d96ae…` | 重建断言 + 两 run 字节对比 |
| C-13 | M1-Offline contamination | `<VENV_PY> -c "from m1_offline.evaluation.contamination import ...; ..."`（`run_contamination_suite`，注入文档 + 真实 Coach system_instructions） | 历史 C1–C4 全 PASS、NOT_RUN=0 | 每 check 的 status/counts |
| C-14 | B 线新集成套件（计划） | `<VENV_PY> -m pytest tests/m1b_integration -q -m "not live and not network and not requires_isolation_worker"` | **NOT_RUN**（套件尚未落地；路径/标记由 B-PR0 ADR 冻结） | exit code、末行、逐 case 明细 |
| C-15 | B 线隔离 Worker 安全负例（计划） | 仅在隔离 Worker 容器内：`<VENV_PY> -m pytest tests/m1b_integration -q -m "requires_isolation_worker"` | **NOT_RUN**；主机直跑即 STOP | worker 镜像/配置、exit、分类日志摘要 |
| C-16 | B 线 demo/UI（计划） | `python -m m1b.demo`（名称由 B-PR5 冻结） | **NOT_RUN** | 双跑 sha256 |

**命令矩阵规则**：

1. C-14/C-15/C-16 在任何 PR 未落地前只能写 `NOT_RUN`，不得用历史 536/365 冒充新集成结果。
2. 测试必须使用冻结 fixture；`M1_TEACHER_FIXTURES` 指向外部 fixture 时，必须记录 fixture 树哈希并把结果标注 `OWNER_REPORTED`，Reviewer 默认拒绝直接采信。
3. 任何 `-k/-m/--deselect` 过滤都要逐条记录理由并写入 audit-index.limitation；静默过滤视为弱化行为（§4、§12）。
4. 测试失败时不得删除/跳过断言来"修复"；失败样例与输出必须保留（§11.4）。

### 3.5 artifact / demo 确定性复跑规范

1. **双跑规则**：同一冻结副本上连续两次运行（间隔 ≥1s），`diff` 为空才允许声称"两次一致"；stdout/artifact 的 sha256 两次都必须记录。
2. **上下文规则**：artifact hash 必须与生成上下文绑定（冻结 SHA、`git status --porcelain` 输出、命令、utc、文件集合/树哈希）。不同公开面文件集合导致 hash 不同时，必须解释原因（参考 M1-Offline `1d57ca62…` vs `2282caff…`），不得静默改文档期望值。
3. **确定性分类**：每个 artifact 声明 `deterministic: true/false` 与 `volatile_fields`（如 `environment.utc_timestamp`）。`deterministic:true` 的 artifact 必须通过"两次运行 + no-.git 副本 + 不同日期/TZ/hashseed"复跑字节一致（M1-A C6 的 summary 即此类）；含 wall-clock/git 动态字段的 artifact 只能标 `deterministic:false` 或把字段移出（参考 M1-A P1-1、M1-Offline P2-7）。
4. **网络阻断复跑**：demo/class 相关运行必须在 socket 阻断（`sitecustomize` 拦截 `socket.socket/create_connection/getaddrinfo`）下复跑一次并记录；失败即 STOP。
5. **无 `.git` 副本**：至少对声明 deterministic 的 artifact 在复制树（无 `.git`、无 `.pytest_cache`）重生成并比较字节。
6. **依赖指纹**：对可复现指纹类证据（如 M1-Offline `dependency_fingerprint`）必须用文档给出的**一行命令**重算并与声明值比较；算法未文档化/不可复算的指纹视为 `NOT_VERIFIED`。

### 3.6 Reviewer 结果记录

1. 每条 Reviewer 执行写入 audit-index（§11），状态只用 §1 词汇；失败也保留（不得只提交 PASS 样例）。
2. Reviewer 报告必须包含：冻结 SHA、clean archive 生成命令、环境、命令矩阵逐项 exit/末行、artifact hashes、与 Owner 声明值的差异（若有）、limitations、STOP 触发检查结果。
3. Owner 结果与 Reviewer 结果分开呈现；差异未解释前不得进入 Gate。

---

## 4. B-PR0…B-PR5 独立验收门

### 4.1 通用门（每个 PR 都适用）

- G1 冻结：PR 有冻结 SHA；Reviewer 在 clean archive 上复跑。
- G2 证据：每项结论带 `[evidence class]+[source]`；Gate 判定项必须 `INDEPENDENTLY_REEXECUTED_THIS_TURN`。
- G3 回归：必须重跑**旧两套相关子集 + 本 PR 新增测试**；不得只跑新增测试。
- G4 安全：无真实 Key/网络/Provider；CODE 相关路径遵守 §5；不触碰 §7 保护路径。
- G5 诚实：`NOT_RUN/BLOCKED/UNVERIFIED/NOT_VERIFIED` 保留；不得预填 PASS；失败样例保留。
- G6 可复现：所有 artifact 有 sha256 + 生成上下文；deterministic 声明需通过 §3.5 复跑。
- G7 文档：PR 报告的命令/数字可由 Reviewer 复算；Mock 与真实效果措辞分离。
- G8 计数：新套件计数独立统计；历史 536/365 只作引用，不相加（§2）。

### 4.2 各 PR 门禁表

| PR | 交付物（冻结前） | Reviewer 必须重跑 | 必须拒绝的弱化行为 | 关联 case |
|---|---|---|---|---|
| **B-PR0** contract-convergence-adr | `docs/M1_B_CONVERGENCE_ADR.md`：`m1a.v0` vs `m1.offline.v0` 全字段对照、唯一 canonical Learner/Session/Event 协议、唯一 mastery 写入者、迁移/rollback、Domain/Assessment/Knowledge/Policy port 设计、roundtrip/reject 策略、两线 CI/demo 命令固定 | 静态审查 ADR+源码；两线 CI 命令 smoke；roundtrip/lossless 单测；`git diff` 确认无实现语义偷改 | 双写 LearnerState；无迁移/rollback；改旧合同语义不升 ADR；把两线测试数相加；只设计不验证 roundtrip；隐藏跨线未声明依赖 | B0-01 |
| **B-PR1** trusted-judge-worker | `TrustedJudgeSupervisor` + `UntrustedExecutionWorker` 边界；不可信 CODE 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；可信端持有 expected/verdict；OS 隔离配置；hidden 不进入 Worker；`JUDGE_INFRA_ERROR` vs `STUDENT_TLE` 分类 | 负例矩阵 B1-01..06（**仅在隔离 Worker 容器**）；参考解/错解/语法错/死循环/边界正确性；determinism；隐藏泄漏扫描（运行时导出 JSON，不只 AST）；mastery 不受 judge error 影响 | 在主机直跑恶意 PoC；把 Worker 自报 `passed` 当 verdict；expected 进入 Worker stdin/argv/文件/日志；仅 `python -I -B` 就当 OS 隔离；用 mock 异常代替隔离测试；删负例断言；`BLOCKED`→`PASS` | B1-01…B1-06 |
| **B-PR2** session-transaction-and-recovery | 单事务 `commit_teaching_turn` 或可证明的持久 Recovery Intent；写点/不变量矩阵；真实 SIGKILL 注入恢复；`ASSESSMENT_PREPARED`/attempt 边界；at-least-once scorer vs exactly-once state 声明 | crash 矩阵 B2-01..03；真实 `SIGKILL`（非 mock exception）；pending/turn/mastery/event count/hash；跨 learner/session 污染；busy/lock/旧 schema/非法迁移 fail-closed | mock 异常当 crash；未证单事务却标 atomic；恢复后 stale pending/重复 mastery；并发 last-write-wins 静默；只测正常 pause/restart；跳过故障注入 | B2-01…B2-03 |
| **B-PR3** scoped-idempotency | 复合键 `(learner_id, session_id, item_id, turn_id, result_id)` + 请求 digest；`IDEMPOTENCY_CONFLICT`；跨 learner/session 不可读旧结果 | B3-01/B3-02 负例：同键同 payload 幂等、同键不同 payload conflict、跨 learner/session 同 key 不可读；异常重试重放；旧 global-ID 适配审计 | 全局 `result_id` 先查后验；静默返回首结果；跨用户读取；把"同 learner 重试"当所有场景；缺 conflict 码；修改旧测试期望以放行 | B3-01/B3-02 |
| **B-PR4** cf-interview-domain-ports | CF/Interview/Freshness 作为 Domain Plugin/KnowledgeSource；不直接写 Snapshot；interview 5 阶段追问 + 4 维 rubric 独立 + unknown facts → ASK_CLARIFICATION；JD v1→v2 影响计划但不静默导入冲突/过期；Hint Ladder 门控 | B4-01..03：双 CF learner 同 canonical journal/replay；双 interview learner + JD v1→v2 计划差异；freshness 过期/冲突/未授权不进入教学；跨域 session 不中断；版本不兼容拒绝 | domain 直接写 mastery/snapshot；读取 hidden labels；过期/冲突来源静默进入教学；interview 编造项目事实；rubric 被 teacher 自评替代；用 mock 检索冒充 freshness | B4-01…B4-03 |
| **B-PR5** unified-e2e-and-blind-evaluation | 新集成套件 + `docs/M1_B_EVALUATION_REPORT.md`；旧两套独立复跑；blind deterministic eval 协议落地；audit-index/证据包；最终边界声明 | C-01..C-16 全部适用项；新集成套件独立计数；blind scorer 无策略标识/预注册检查；audit-index 完整性；历史数字不相加 | 相加 536+365；真实收益/显著性声明；mock 结果当效果；改旧期望值；只跑新套件不跑旧套件；audit-index 缺哈希；`BLOCKED/NOT_RUN` 写成 PASS；把 review 结论预填 | B5-01、X-01、X-02 |

---

## 5. 安全负例取证规范

### 5.1 执行边界

1. 安全负例（提交代码读 expected、改结果文件、读宿主秘密、网络访问、fork/超时、输出伪造等）**只能在隔离 Worker/容器内执行**；禁止在宿主直接运行恶意/sentinel PoC。
2. 合成 sentinel：fixtures 标记 `TEST_ONLY`/`synthetic`，不含真实个人数据、真实 Key、真实私有路径；sentinel 内容不得进入公开文档的正文（只引用 case id 与哈希）。
3. Worker 最低隔离基线（由 B-PR1 实现并验收）：非 root principal、只读最小 rootfs、`--network none`/netns、私有 tmpfs、禁设备/宿主敏感目录、CPU/内存/pids/file-size/输出长度/执行时限、子进程清理；不得拉取外部依赖镜像。
4. 违反"主机直跑 PoC"即 **STOP**（§12），并保留现场。

### 5.2 负例矩阵（与 TEST_EVIDENCE_MATRIX B1-01..06 对齐）

| case_id | 负例 | 期望行为（fail closed） | 证据字段（不得含 hidden） |
|---|---|---|---|
| B1-01 | 提交不可信 CODE | 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`，不执行 learner code | exit code、classification、policy/feature flag 版本 |
| B1-02 | 试图读取 expected/hidden | Worker 无 expected（stdin/mount/env/argv/log 均无）；结果 `JUDGE_INFRA_ERROR` 或拒绝 | 分类、日志摘要长度上限、no-hit 记录 |
| B1-03 | 伪造 result JSON/输出 `passed:true` | 可信端忽略 Worker 自报，按可信 expected 比较后判 WA/RE | classification 与 verdict 来源（trusted）|
| B1-04 | 读宿主 secret/网络/子进程逃逸/资源耗尽 | OS 隔离拒绝；网络不可达；超限分类 `STUDENT_TLE` 或 `JUDGE_INFRA_ERROR` | Syscall/exit 摘要、resource 记录 |
| B1-05 | 正确/错误/超时/异常/边界参考解 | CORRECT/WA/TLE/RE/边界判定稳定且 deterministic | 每 case verdict + 重跑一致性 |
| B1-06 | 隐藏内容经 messages/trace/diagnostics/exports 泄漏 | 扫描运行时导出 JSON/日志：无 expected/args 内容 | 扫描命令、hit 计数（0） |

**eval 失败语义**：`JUDGE_INFRA_ERROR` 不是学生错误，不改变 mastery；`STUDENT_TLE`/`WRONG_ANSWER` 才是学生证据。证据中只允许聚合错误码与非泄露提示，不允许 `args_repr/expected_repr` 原文（参考 M1-Offline judge 已知风险）。

### 5.3 证据格式

- 只记录：`case_id`、隔离配置摘要、`exit_code`、`classification`、`verdict`（trusted 端）、日志摘要（长度上限，不含 hidden/expected/args）、`sha256`、`limitation`。
- 保留通过样例与失败样例（失败不得删除）。
- 任何出现 hidden expected/args 原文、真实 Key、宿主敏感路径的证据包即 STOP。

---

## 6. 崩溃 / 恢复证据规范

### 6.1 注入方式（真实崩溃，不是 mock 异常）

1. 真实 `SIGKILL`/进程退出/电源式冷启动：在以下写点**前后**注入（每个窗口至少一例）：
   - `RESPONSE_SUBMITTED` insert 前/后；
   - `ASSESSED` / `MASTERY_UPDATED` insert 前/后；
   - Snapshot upsert 前/后；
   - `save_session`（pending/turn 更新）前/后；
   - 单事务 commit 前/后；
   - 恢复/重放 前/后。
2. 注入器必须用真实子进程并在目标写点 `os.kill(pid, SIGKILL)`（或等价故障注入），然后**新进程**打开同一 SQLite 恢复；禁止用 `raise`/mock exception 代替 crash 证据（mock 异常只能作辅助单测，标 `MOCK` 且不能计入 B2 证据）。
3. 记录：注入方式、目标写点、进程 pid/时间、SQLite 文件拷贝（或只读快照）+ sha256、恢复命令。

### 6.2 每 case 必录字段

| 字段 | 说明 |
|---|---|
| `case_id` | B2-01/02/03 或细化编号 |
| `write_point` | 注入点（见 6.1） |
| `pending_item_id` | 恢复前后值（含 null） |
| `turn_index` | 恢复前后值；必须单调 |
| `mastery` | 相关节点 mastery/confidence/evidence_count 前后值 |
| `event_count` | 恢复前后事件总数；seq 唯一、单调 |
| `hashes` | snapshot hash / event log hash / session state hash（前后/恢复后） |
| `replay_equal` | rebuild 后快照 == 持久化快照（bool） |
| `cross_scope` | 其他 learner/session 的 mastery/events 是否变化（必须为否） |
| `classification` | `PASS_RECOVERED` / `RECOVERED_WITH_EXPLICIT_LIMITATION` / `FAILED`；不得把未知窗口写成 PASS |

### 6.3 不变量与判定

1. 无重复 mastery（同一 result 只应用一次）、pending 与 assessed 一致、turn index 单调、事件 seq 唯一。
2. 崩溃窗口无法判定时：宁可 `PARTIAL/NOT_VERIFIED`，不得声称"事务已完成"。
3. 明确声明语义：`at-least-once scorer invocation` / `exactly-once state application`（如可证明），不得承诺无法证明的远程 exactly-once。
4. 跨 learner/session 污染检查必须显式执行（查询另一 learner 的快照/事件哈希，断言不变）。
5. 旧 schema/损坏 DB/非法迁移：必须 fail closed（明确错误码 + 不写部分状态），并作为负例保留。

---

## 7. 跨线检查 X-01 / X-02

### 7.1 X-01 无运行时范围漂移

每个 B/M1 提交（含 B-PR0..B-PR5）由 Reviewer 做静态检查：

```bash
git diff --name-only <base>..<candidate_sha> > /tmp/m1b_changed_files.txt
# 保护路径（任一命中即 STOP）
grep -E '^(src/autoteacher_m0/|security/|bridge/|config/g|scripts/g4|plugins/.*(live|g4)|docs/.*LiveGate)' /tmp/m1b_changed_files.txt
# A 线提交不得修改 M1 代码（反向检查）
# 例如 A 线 candidate 的 diff 不得含 ^m1_teacher/ 或 ^m1_offline/ 或 ^tests/(m1_teacher|m1_offline)/
```

| 检查 | 允许 | 拒绝（STOP） |
|---|---|---|
| M1 提交修改范围 | B 线自己的 `m1_teacher/`、`m1_offline/`、`tests/`、`docs/`、新 `m1b_*/` 路径 | 修改 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate/账本/授权路径 |
| A 线提交修改范围 | A 线自身路径 | 修改任何 M1 代码/tests/fixtures |
| 基线 | 从 `main@3e7afee` 分叉、各自独立分支 | 用 merge/cherry-pick 把两条线串成"已集成"而不做独立验收 |

证据：`git diff --name-only <base>..<sha>` 原始输出 + 过滤命令 + exit code + 文件清单 sha256；命中即 STOP 并保全证据。

### 7.2 X-02 无真实 Key / 外部网络 / 付费请求

| 检查 | 命令模板 | 通过标准 |
|---|---|---|
| 静态网络/Key 扫描 | AST/文本扫描 `m1_teacher/**`、`m1_offline/**`、新 B 路径、tests：禁 `socket/http/urllib/requests/httpx/aiohttp` import、provider SDK、`sk-`/Bearer/Key 形态 | 0 命中（或已批准并记录白名单） |
| 运行时网络阻断 | socket-blocking `sitecustomize`（模板见附录 A.3）；或 `--network none` 隔离运行 | demo/示例在阻断下仍 exit 0 且输出哈希一致 |
| 环境 | 环境记录中无 Key/Provider 配置；敏感 env 清空 | environment 字段可审计；0 个付费请求 |
| LiveGate | 状态不变：**BLOCKED**；B 线不调用/不解锁 | 文档/代码/命令均无 Live 放行 |
| 真实数据 | fixtures 全部 synthetic/CC0-1.0；无真实个人数据/简历/JD | 声明 + 扫描：0 命中 |

Reviewer 必须把 X-01/X-02 结果写入 audit-index（`case_id` X-01/X-02），并在最终 Review 报告中给出命令与原始输出摘要。

---

## 8. B4 / B5 验收映射

| case_id | 验收目标 | 必要条件（可执行证据） | 允许的最终状态 | Mock provenance 要求 |
|---|---|---|---|---|
| B4-01 | 双 CF learner 使用同一 canonical mastery/session journal | 统一事件表 + replay engine；两个合成 learner 走 CF 闭环；journal hash/replay 一致；跨 learner 隔离 | `PASS` 仅当 Reviewer 复跑；否则 `NOT_RUN` | 明确 MOCK 学生/合成 fixtures |
| B4-02 | 双 interview learner + JD v1→v2 产生不同证据化计划 | 5 阶段追问、4 维 rubric 独立；JD 版本影响计划；unknown project facts → ASK_CLARIFICATION；不编造 | 同上 | MOCK 问答 + 合成 JD |
| B4-03 | Freshness 过期/冲突/未授权来源不得静默进入教学 | KEEP/UPDATE/RECHECK 门；`RECHECK/expired/conflict` 进入计划 = FAIL；课程内容只来自 eligible 来源 | 同上 | 合成知识源（published/observed/valid_until） |
| B5-01 | Reviewer 独立重跑旧两套 + 新集成套件并标注 mock provenance | 本协议 §3 命令矩阵；新套件独立计数；audit-index；确认旧 536/365 仅历史引用、未相加；最终报告写 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE` 或 PARTIAL/FAIL/BLOCKED | `PASS` 仅当 Reviewer 本轮全跑；owner PASS 不计 | 所有 E2E/mock 结果标 `MOCK`；不得写学习收益 |

> 映射来源：`TEST_EVIDENCE_MATRIX.csv`（B4-01…B5-01、X-01/X-02）。B4/B5 未实现之前一律 `NOT_RUN`；不得用 M1-A/M1-Offline 历史结果填表。

---

## 9. 盲评定义与二次验证规则

### 9.1 定义（避免夸大）

1. 对**确定性 mock learner** 无法做统计意义上的真实盲评（没有真实受试者、没有随机化人群、没有学习收益可估计）。因此 B 线只允许：
   **deterministic fixed-case / fixed-seed / blind-rubric comparison（策略标签盲）** —— 评分者/评分函数看不到策略版本（如 v0/v1、teacher 标识），但**不声称**统计盲评或学习收益。
2. 适用对象：`m1_offline/evaluation/compare.py` 式固定 case 对照，及新 B 线集成对照；两者都必须固定 case 集、seed、维度、变量定义并预注册。
3. 禁止措辞："盲测证明 A 更好""显著提升""真实学习收益"；允许措辞："策略标签盲的确定性合成对照，模拟器内部行为差异，不构成学习效果证据"。

### 9.2 二次验证规则（blind rubric）

1. **预注册**：运行前把 case 清单、seed、维度、评分函数文件 hash、scorer 标识写入 audit-index；运行后不得改维度/阈值/case 集（改了即新实验，旧结论作废）。
2. **盲输入**：评分函数签名与盲视图不得含 policy/strategy/teacher 标识；静态检查签名与数据类字段（参考 `m1_offline/evaluation/compare.py` 的 blind 视图设计）。
3. **双跑**：同一冻结 SHA 上由 Reviewer 独立跑两次；run digest、case count、failure list、variance 记录必须一致；不一致即 `FAIL`/`NOT_VERIFIED`。
4. **二次验证**：由**第二 Reviewer**（或同一 Reviewer 的第二独立 clean archive）重复盲评分，比较 `blind rubric` 输出 hash；不一致时采用更保守结论并记录分歧；第二次复算不能引用第一次的中间结果。
5. **边界**：输出必须包含 `not real teaching effect` / `no significance claimed`；学习收益=NOT_VERIFIED；真实效果=NOT_RUN。任何"v1 优于 v0"只能描述为模拟器内部差异。

---

## 10. 默认 / 最终结论边界

1. **默认结论**（当且仅当 §3/§4 全部门通过）：
   `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`。
2. 该结论仅覆盖：离线、合成 fixtures、确定性/mock E2E、独立复跑证据齐全的 M1-B 集成范围。
3. **明确不包含**（任何文档不得暗示）：真人学习收益/教学效果；联网研究/招聘网站/真实 JD/简历；真实 Provider/LLM 能力；真实 OS 判题安全承诺；Live/LiveGate/授权/生产可用；M0 G4-H/G5/LiveGate/M0 决策变更。
4. 结论类型只能是：`PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE` / `PARTIAL_FOR_..._SCOPE` / `FAIL` / `BLOCKED`；附每项证据、未关闭项、限制。
5. **人类 Gate 不在本协议范围**：H-01/H-02/H-03、G5、LiveGate、M0 决策保持各自状态（BLOCKED/DECISION_PENDING），B 线不得自行推进。

---

## 11. 证据包格式（audit-index.json + append-only 矩阵）

### 11.1 目录约定（建议）

```
docs/m1b_evidence/
├── audit-index.json                  # 本轮 Reviewer 证据索引（append-only entries）
├── matrices/
│   ├── TEST_EVIDENCE_MATRIX.base.csv # 初始冻结矩阵（不改旧字节）
│   └── TEST_EVIDENCE_MATRIX.appendonly.csv  # 只追加新行/校正行（带 previous_sha256）
├── <pr-id>/<case_id>/                # raw evidence：日志/JSONL/摘要（不含 Key/PII/hidden）
└── manifests/                        # artifact sha256 清单、文件集合上下文
```

### 11.2 `audit-index.json` 字段（冻结）

| 字段 | 类型 | 必填 | 语义 |
|---|---|---|---|
| `schema_version` | string | 是 | 固定 `"m1b.audit-index.v0"` |
| `entries` | array | 是 | append-only；顺序即追加顺序 |
| `entries[].case_id` | string | 是 | 如 `B1-02`、`B4-01`、`X-01` |
| `entries[].branch` | string | 是 | 被测分支 |
| `entries[].git_sha` | string | 是 | 被测冻结 SHA（40 hex；不得写 branch 代指） |
| `entries[].stage_sha` / `runtime_sha` | string/null | 否 | 分阶段产物/运行时镜像 SHA（如适用） |
| `entries[].command` | string/array | 是 | Reviewer 实际执行命令（原样） |
| `entries[].environment` | object | 是 | 记录 TZ/LANG/LC_ALL/PYTHONHASHSEED/python/pytest/OS/venv；不含 Key |
| `entries[].utc` | string | 是 | ISO-8601 UTC（如 `2026-11-21T00:00:00Z`） |
| `entries[].exit_code` | integer | 是 | 进程 exit code |
| `entries[].status` | string | 是 | §1 证据类/状态词（`INDEPENDENTLY_REEXECUTED` 等） |
| `entries[].raw_evidence_path` | string | 是 | raw 文件路径（相对 repo，或 /tmp 导出后 sha256 记录） |
| `entries[].sha256` | string | 是 | raw evidence 的 sha256（64 hex） |
| `entries[].limitation` | string/null | 否 | 非 PASS 必填；缺失即校验失败 |
| `entries[].deterministic` | boolean | 否 | artifact/case 是否内容确定 |
| `entries[].volatile_fields` | array | 否 | 非确定字段（如 `environment.utc_timestamp`） |
| `entries[].file_set_digest` | string/null | 否 | 公开面/文件集合上下文哈希（解释 hash 上下文差异） |
| `entries[].previous_sha256` | string/null | 否 | append-only 链的前序记录哈希（可选但推荐） |

**示例（模板，不是运行结果）**：

```json
{
  "schema_version": "m1b.audit-index.v0",
  "entries": [
    {
      "case_id": "B2-02",
      "branch": "b-next/pr2-session-transaction",
      "git_sha": "<FROZEN_40_HEX_SHA>",
      "stage_sha": null,
      "runtime_sha": null,
      "command": "python -m pytest tests/m1b_integration/test_crash_recovery.py -q",
      "environment": {"TZ": "UTC", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8", "PYTHONHASHSEED": "0", "python": "3.11.15", "pytest": "9.2.0", "os": "Linux"},
      "utc": "YYYY-MM-DDTHH:MM:SSZ",
      "exit_code": 0,
      "status": "NOT_RUN",
      "raw_evidence_path": "docs/m1b_evidence/pr2/B2-02/pytest.log",
      "sha256": "<64_HEX_SHA256_OF_RAW_EVIDENCE>",
      "limitation": "template example only; suite not yet implemented; replace after real run",
      "deterministic": true,
      "volatile_fields": [],
      "file_set_digest": null,
      "previous_sha256": null
    }
  ]
}
```

### 11.3 append-only 矩阵规则

1. 初始矩阵（来自交接包的 `TEST_EVIDENCE_MATRIX.csv`）视为冻结快照，**不改旧字节**。
2. 新结果写入 `TEST_EVIDENCE_MATRIX.appendonly.csv`：每行含 `case_id, frozen_status, review_status, evidence_class, evidence_source, command, git_sha, utc, exit_code, raw_evidence_sha256, limitation, appended_utc`。
3. 若需校正旧行：只追加校正行（保留原行 + `supersedes` 指针），禁止原地编辑/"全 PASS 重写"。
4. 矩阵与 audit-index 的 `sha256` 必须互相可追溯；失败样例同样保留。

### 11.4 失败/负面证据保留

- 至少保留：一个通过样例 + 一个失败样例（含输出摘要与 exit code）；不得只提交 PASS 汇总。
- raw evidence 可放 gitignored packet，但 audit-index 必须记录 `sha256` 与导出说明；不含 Key/PII/hidden expected。

---

## 12. 失败即停规则与 STOP 清单

### 12.1 立即 STOP 条件（任一命中）

1. 发现真实 API Key/凭证，或真实 Provider/SDK 调用、任何付费请求。
2. 任何外部网络访问（运行期或测试），或依赖在线服务/联网研究。
3. 未批准修改保护路径：`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate/账本/授权路径。
4. 证据分类错误：`MOCK` 当真实收益、`OWNER_REPORTED` 当 `INDEPENDENTLY_REEXECUTED`、`NOT_RUN/BLOCKED/UNVERIFIED` 改 PASS、历史 536+365 相加。
5. 无哈希/无法复现的证据被当作 PASS；artifact hash 与声明不符且未解释。
6. 跨 learner/session 数据泄漏或可能泄漏（如全局 `result_id` 读到他人结果）。
7. 可伪造 PASS 的 CODE Judge 被默认暴露给不可信输入；hidden expected 进入 Worker/Teacher 可见输出。
8. 在主机直接执行恶意/sentinel PoC（非隔离 Worker）。
9. 删除/跳过/弱化断言、修改冻结测试期望或 fixtures 以"通过"。
10. 试图解锁 LiveGate / 触发真实模型授权 / 改变 M0 G4-H/G5/M0 决策。

### 12.2 STOP 处理流程

1. 停止后续命令与运行；不得继续"补齐"证据。
2. 保全现场：复制受影响证据到只读位置并记录 sha256；记录时间、命令、环境、影响范围。
3. 在 audit-index 中写 `status: "BLOCKED"` 或 `STOP`（§1 词汇），附 limitation 与触发条目。
4. 通知 Lead/维护者与独立 Reviewer；不得自行修复后继续宣称 PASS。
5. 由独立 Reviewer 重新评估；只有维护者决定是否允许恢复执行。恢复后新增 evidence 记录，不覆盖 STOP 记录。

### 12.3 每轮 Gate 前的 pre-flight / post-flight 检查清单

- [ ] clean archive 冻结 SHA 正确、无 `.git`、无未提交文件。
- [ ] 环境变量已记录且无 Key；网络阻断已启用/验证。
- [ ] 旧两套回归子集 + 新套件均已跑（未跑=NOT_RUN，不得省略）。
- [ ] 每条结论有 evidence class + source + command + hash。
- [ ] artifact 确定性声明与 §3.5 复跑结果一致。
- [ ] 历史数字未被相加，Mock/真实未混写。
- [ ] STOP 清单逐项检查通过。
- [ ] audit-index/matrix append-only 校验通过（sha256 链连续）。

---

## 附录 A：命令模板

### A.1 完整 Reviewer 复跑模板（示例，历史两套）

```bash
set -u
VENV_PY="/root/Autonomous Teacher/.venv/bin/python"
WORK=/tmp/m1b-rev/$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$WORK"/{m1a-c6,m1off-c2} "$WORK"/logs
log="$WORK/logs"

# 1) clean archives (SHA 由 LeadB 发布)
git archive 3010426d9557fa1042f9c06cfef491758e1dce72 | tar -x -C "$WORK/m1a-c6"
git archive 052d980d9a45558da8789c90725ae6c48f3f7a7d | tar -x -C "$WORK/m1off-c2"

# 2) M1-A suite + demo + evidence
cd "$WORK/m1a-c6" && rm -rf .pytest_cache
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME="$WORK" TMPDIR=/tmp TZ=UTC \
  LANG=C.UTF-8 LC_ALL=C.UTF-8 PYTHONHASHSEED=0 \
  "$VENV_PY" -m pytest tests/m1_teacher -q 2>&1 | tee "$log/m1a_pytest.log"
"$VENV_PY" -m m1_teacher.demo > "$log/m1a_demo1.txt" 2>&1
"$VENV_PY" -m m1_teacher.demo > "$log/m1a_demo2.txt" 2>&1
diff "$log/m1a_demo1.txt" "$log/m1a_demo2.txt" && sha256sum "$log/m1a_demo1.txt"
"$VENV_PY" -m m1_teacher.demo --write-evidence
sha256sum docs/m1a_evidence/* | tee "$log/m1a_evidence_sha256.txt"

# 3) M1-Offline suite + demo + artifacts + canonical replay
cd "$WORK/m1off-c2" && rm -rf .pytest_cache
"$VENV_PY" -m pytest tests/m1_offline -q 2>&1 | tee "$log/m1off_pytest.log"
"$VENV_PY" -m m1_offline.demo > "$log/m1off_demo1.txt" 2>&1
"$VENV_PY" -m m1_offline.demo > "$log/m1off_demo2.txt" 2>&1
diff "$log/m1off_demo1.txt" "$log/m1off_demo2.txt" && sha256sum "$log/m1off_demo1.txt"
"$VENV_PY" -m m1_offline.demo --write-artifacts
sha256sum docs/m1/traces/loop_v*.jsonl docs/m1/reports/*.json docs/m1/reports/*.md \
  | tee "$log/m1off_artifact_sha256.txt"

# 4) 汇总（人工写入 audit-index；此处仅列出需收集的信息）
printf 'sha=%s\n' "$(git rev-parse HEAD)"
```

> 说明：`$WORK` 与 `logs` 为 Reviewer 临时目录；最终结论只能引用抄录进 audit-index 的条目；此时 `TZ=UTC` 保证时间可读，但不得把 wall-clock 字段写入 deterministic artifact 的 expected hash。

### A.2 新 B 线集成套件（计划命令；套件未落地前一律 NOT_RUN）

```bash
# 默认离线套件（B-PR0 ADR 冻结实际路径与 marker）
"$VENV_PY" -m pytest tests/m1b_integration -q \
  -m "not live and not network and not requires_isolation_worker" 2>&1 | tee /tmp/m1b_integration.log
# 隔离 Worker 安全负例（只在隔离容器内执行；主机直跑=STOP）
# podman run --rm --network none --read-only ... "$VENV_PY" -m pytest tests/m1b_integration -q -m requires_isolation_worker
```

### A.3 socket 阻断 `sitecustomize.py` 模板

```python
# /tmp/m1b_nonet/sitecustomize.py  (仅测试网络阻断；通过 PYTHONPATH=/tmp/m1b_nonet 生效)
import socket

class _NoNetwork(OSError):
    pass

def _deny(*args, **kwargs):
    raise _NoNetwork("M1B_NO_NETWORK: runtime network access is blocked in independent verification")

socket.socket = _deny
socket.create_connection = _deny
socket.getaddrinfo = _deny
```

### A.4 audit-index 校验（建议 Reviewer 自带脚本）

- 必填字段/类型；`status` ∈ §1 冻结词汇；`sha256` 为 64 hex；非 PASS 必填 `limitation`；
- `raw_evidence_path` 存在且 `sha256` 匹配；environment 不含 Key/PII；
- append-only：旧 entry 的 `sha256` 不变，新 entry 只追加；`previous_sha256`（如有）链连续。

---

## 附录 B：证据类 × 证据来源允许矩阵

| | SOURCE_INSPECTED | OWNER_REPORTED | REVIEWER_REPORTED | INDEPENDENTLY_REEXECUTED_THIS_TURN |
|---|---|---|---|---|
| MOCK | 允许（仅描述 fixtures） | 允许 | 允许（历史 mock 结论） | 允许（Reviewer 自己跑的 mock E2E） |
| DETERMINISTIC | 允许（阅读测试） | 允许 | 允许（历史报告） | **Gate 唯一认可** |
| HUMAN_REVIEWED | — | — | 允许（reviewer 身份+范围） | 允许 |
| NOT_VERIFIED | 允许 | 允许 | 允许 | 允许 |
| UNVERIFIED | 允许 | 允许 | 允许 | 允许（仍 UNVERIFIED） |
| BLOCKED | 允许 | 允许 | 允许 | 允许 |
| NOT_RUN | 允许 | 允许 | 允许 | 允许（但 Gate 不通过） |
| INDEPENDENTLY_REEXECUTED | 禁止 | 禁止 | 禁止（那是过去轮次） | 允许 |

---

## 附录 C：术语与变更控制

| 术语 | 定义 |
|---|---|
| clean archive | 用 `git archive <SHA> \| tar -x` 得到、无 `.git`/无未提交文件的冻结副本 |
| canonical core | B-PR0 ADR 选定的唯一业务状态/事件协议实现（候选 `m1_teacher`，最终以 ADR 为准） |
| mock provenance | 标明 E2E/结果来自合成 fixtures、mock learner/runtime、脚本化 outcome，不是真实行为 |
| deterministic vs volatile | artifact 字段是否可由内容树唯一决定；volatile 字段须显式列名并不得进入 expected hash 承诺 |
| independent | Reviewer 未参与实现、未修改被审对象、本轮真实执行 |
| STOP | §12.1 任一触发后立即停止并保全证据，等待独立重新评估 |

**变更控制**：本协议修订只允许 append-only；修改需记录 `revision, date, change, approver`；冻结版本的旧字节与哈希保留。任何降低 Gate/删除 STOP/替换证据词汇的修改一律拒绝并升级维护者。
