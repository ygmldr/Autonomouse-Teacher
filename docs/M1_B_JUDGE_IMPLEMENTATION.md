# M1-B / B-PR1 — 可信判题实现：TrustedJudgeSupervisor、默认封禁与隐藏泄漏扫描

- 文档编号：`M1_B_JUDGE_IMPLEMENTATION` / B-PR1 实现记录
- 状态：**IMPLEMENTED + LOCAL_VERIFIED**；独立评审结论 `PASS_WITH_ACTIONS`（`docs/M1_B_PR1_REVIEW.md`），P1-1..P1-4 已修复并待复评。**B1-04/B1-05 在独立评审中为 `PARTIAL`**（宿主非 root principal / 默认超时 TLE 误分类；后者已修复）；**人类批准 + 目标部署验收前，真实用户 CODE 仍为 BLOCKED**。
- 版本：v0.2（2026-11-20，UTC；PR1 实现 + 独立评审 P1-1..P1-4 修复 + P2 处置记录）
- 分支：`b-next/pr1-judge-worker`（基于 `4706250`，已合并 `b-next/pr1-untrusted-worker` HEAD `8d7ede6`）
- 设计依据：`docs/M1_B_THREAT_MODEL_JUDGE.md` v0.2（§3 协议 / §4 沙箱 / §5 默认策略 / §6 负例 / §8 泄漏 / §9 验收映射）
- 证据等级（与 `docs/m1/EVALUATION_PROTOCOL.md` §3 口径一致）：本文件的测试结果是 `LOCAL_VERIFIED`（本机真实运行、离线合成语料、无网络/无 Key）；不是最终 `PASS`，B1 独立验收仍为 `NOT_RUN`。
- 边界：不联网、不调用真实 Provider/Key、不触碰 M0 保护路径；认证语料与攻击模板均为 synthetic/CC0；本文不复制 hidden expected 内容。

---

## 1. 交付范围

| 交付 | 位置 | 说明 |
| --- | --- | --- |
| 可信判题监督器 | `m1_teacher/assessment/judge/supervisor.py` | `TrustedJudgeSupervisor` + `JudgeVerdict`；只持有 expected 与最终 verdict，逐 case 调用不可信 worker |
| CODE 路径改造 | `m1_teacher/assessment/scorer.py` | 默认 BLOCKED；显式 `trusted_fixture_only=True` 才走 supervisor；旧 `_CODE_RUNNER_SOURCE`/`_run_learner_code`/result 文件路径全部删除；MCQ/SHORT_ANSWER 不变 |
| 不可信 Worker/沙箱（合入） | `m1_teacher/assessment/judge/{protocol,sandbox,worker,worker_runner}.py` | 由 m1a-fixtures 工作流实现；本文只引用，不维护第二份实现；详见 `docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md` |
| 监督器单测 | `tests/m1_teacher/test_judge_supervisor.py` | 36 tests：默认 blocked、canonical 类型严格比较、伪造响应 fail-closed、P1-01 数据路径绕过、旧路径删除 |
| 正确性认证 | `tests/m1_teacher/test_judge_correctness.py` | 27 tests：14 参考解 112/112 PASS、负例 WA/RE/TLE/edge_correct、determinism |
| 泄漏扫描 | `tests/m1_teacher/test_hidden_leakage_scan.py` | 16 tests：默认 blocked 不执行、result/history/CLI 导出无 sentinel、攻击模板不 PASS、P2-13、P2-12 认证 expected 指纹扫描 |
| OS CI 门禁 | `tests/m1_teacher/judge_os_gate.py` + `test_judge_ci_gate.py` | P1-3：统一 7 处 sandbox skip；`M1B_REQUIRE_OS_SANDBOX=1` 时缺 bwrap 必须 fail（不得 skip）；helper 行为测试 + 文档 lint |
| 既有测试最小适配 | `tests/m1_teacher/test_assessment_scorer.py` 等 | 仅把真实 CODE 评分测试显式 opt-in `trusted_fixture_only=True` 并更新聚合 failure_reason 断言；未删/未跳过/未弱化断言 |
| 文档 | 本文件 + 威胁模型 v0.2 | 关闭 P1-01/P1-08/P2-05/P2-06，记录 P2-13 |
| Demo/CLI 策略注记 | `m1_teacher/demo.py`、`m1_teacher/cli.py` | 显式注明永不执行 learner CODE、无请求级开关；真实 CODE 的 opt-in 只在可信构造参数 |

---

## 2. 架构与信任边界

```
 learner response / assessment item (untrusted input)
                 │
                 ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ DeterministicScorer (trusted; only hidden-material reader)       │
 │  - MCQ / SHORT_ANSWER: unchanged, no worker                      │
 │  - CODE: policy check -> TrustedJudgeSupervisor                  │
 └──────────────────────────────────────────────────────────────────┘
                 │  code, function_name, per-case args (NO expected)
                 ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ TrustedJudgeSupervisor (trusted memory)                          │
 │  - owns hidden tests/expected + canonical comparison + verdict   │
 │  - every worker output is untrusted data; schema/extra fields    │
 │    violations -> JUDGE_INFRA_ERROR (fail closed)                 │
 └──────────────────────────────────────────────────────────────────┘
                 │  WorkerObservation: status / actual_canonical /
                 │  exception_type / excerpts (NEVER passed/verdict)
                 ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ UntrustedExecutionWorker (m1a-fixtures, one process per case)    │
 │  BwrapSandbox: user/pid/net/ipc/uts ns, uid/gid 65534, ro rootfs │
 │  private tmpfs, rlimits, wall timeout, process-group SIGKILL     │
 └──────────────────────────────────────────────────────────────────┘
```

- 可信侧 (`scorer.py` / `supervisor.py`)：唯一读取 hidden scoring spec 与 hidden expected 的组件；负责 policy、canonical 比较、聚合 verdict、student/infra 分类。
- 不可信侧 (`worker.py` / `sandbox.py` / `worker_runner.py`)：只接收单 case `function_name` + `args`；协议字段/上限/禁止字段由 `protocol.py` 冻结（`expected`/`tests`/`verdict`/`passed` 等禁止字段在双向协议中都非法）。
- 数据流中 **expected 不进入 worker**（argv/env/stdin/mount/内存/response 均无），worker 也不知道 result 文件路径（协议无 result 文件，`stdout`/专用 fd 单行响应 + `os._exit(0)`）。
- 失败隔离：worker 异常/协议违反/sandbox 不可用 → `JUDGE_INFRA_ERROR` 或 policy blocked；学生 WA/RE/TLE → 学生证据；两类严格区分，`EVAL_ERROR` 不改变 mastery（沿用 `m1_teacher/session/engine.py` 既有 EVAL_ERROR 语义）。

---

## 3. 默认封禁与显式 opt-in（P1-01 关闭）

### 3.1 默认策略

`DeterministicScorer(fixtures_root=None, *, timeout_s=2.0, scorer_id=..., clock=None, trusted_fixture_only=False, judge_worker=None)`：

- `trusted_fixture_only=False`（默认）：CODE 提交**不执行** learner code，直接返回
  `AssessmentResult(status="EVAL_ERROR", score=None, failure_reason="UNTRUSTED_CODE_EXECUTION_BLOCKED")`（`scorer.py:501-544` 的 `_score_code` 在进入任何执行路径前检查）。
- `trusted_fixture_only=True`：只允许仓库测试/CI 的合成 fixtures 走 `TrustedJudgeSupervisor` + `BwrapSandbox`；若 worker 缺失/沙箱不可用，同样返回 blocked 风格的 `EVAL_ERROR`，**绝不回退**到 in-process/bare-subprocess 旧路径。
- MCQ / SHORT_ANSWER 不经过 worker，行为与旧实现一致（默认封禁只影响 CODE）。

### 3.2 P1-01：policy 只能来自可信构造/部署配置

`trusted_fixture_only` 是**构造参数**，由可信代码（仓库测试/CI、受控部署配置）显式传入；它 **不是** 请求/数据字段：

| 潜在绕过路径 | 结果 | 证据 |
| --- | --- | --- |
| `AssessmentItem` 字段（含 `scoring_spec_ref`、`item_type` 等） | 不改变 policy；仍 blocked | `test_policy_cannot_be_enabled_from_caller_data_paths` |
| response 字符串 / dict 内 `trusted_fixture_only`、`execution_policy`、`assessment_job.enable_code_execution` | 不改变 policy；worker 从未被调用 | 同上 |
| `result_id` 自报 `trusted_fixture_only=True;request=enable-code` | 不改变 policy | 同上 |
| `scorer.score(..., trusted_fixture_only=True)` 额外关键字 | `TypeError`（无此 API 入口） | 同上 |
| 环境变量 `M1B_TRUSTED_FIXTURE_ONLY` / `M1_TEACHER_TRUSTED_FIXTURE_ONLY` | 不读取、不改变 policy | 同上 |
| `TrustedJudgeSupervisor(...)` 默认构造 | 无论 tests/expected 内容如何都是 blocked | `test_default_policy_blocks_without_touching_worker` |
| AssessmentJob / CLI 请求 | 当前 M1-A 没有该执行入口；demo/CLI 不构造 CODE 执行路径（见 §9） | `demo.py`/`cli.py` 注记 + CLI 泄漏扫描 |

`DeterministicScorer(..., trusted_fixture_only="yes")` 等非法类型 → `ValidationError`（`test_constructor_opt_in_is_explicit_and_validated`）。

### 3.3 旧 CODE 执行路径已删除（B-Q1 根因消除）

- `m1_teacher/assessment/scorer.py` 中已无 `_CODE_RUNNER_SOURCE`、`_run_learner_code`、`_classify_code_outcome`、`result.json` 路径、`sys.executable`、`subprocess` 调用。
- 回归测试：`test_judge_supervisor.py::test_legacy_in_process_runner_path_is_removed` 对 scorer 源码断言上述符号全部不存在。
- 因此威胁模型 §2 的 R1/R2/R3（expected 与 learner code 同进程、worker 返回 passed、result 文件 argv）在 A 线 scorer 路径上不再存在；B 线 `m1_offline` 为历史冻结实现，不在本 PR 改造范围（B1 是 M1-A/M1-B 用户 CODE 开放前的 blocker，B 线后续 PR 复用本边界）。

---

## 4. 判题结果映射（可信聚合）

`JudgeVerdict`（`supervisor.py:154-187`）字段：`status / score_ratio / cases_total / cases_passed / failure_codes / infra_error`；不包含 expected/args/actual 原文。`failure_codes` 只含分类与计数（如 `CASES_FAILED:2/7`、`WA`、`RE`、`STUDENT_TLE`、`JUDGE_INFRA_ERROR:...`）。

`DeterministicScorer._map_judge_verdict`（`scorer.py:544+`）映射：

| 可信 verdict | AssessmentResult | 说明 |
| --- | --- | --- |
| `PASS`（cases_passed==total>0） | `CORRECT`，score=max_score | 全部 hidden case actual==expected |
| 部分通过（passed>0 且未全过，含 TLE） | `PARTIAL`，score=max_score × ratio | 失败原因 `JUDGE_CASES_FAILED:<failed>/<total>` 或 `JUDGE_STUDENT_TLE:<passed>/<total>` |
| `WA` / `RE`（0 pass） | `INCORRECT`，score=0 | 失败原因 `JUDGE_CASES_FAILED:0/<total>` / `JUDGE_STUDENT_RE` |
| `TLE`（0 pass） | `INCORRECT`，score=0 | `JUDGE_STUDENT_TLE` |
| `JUDGE_INFRA_ERROR` | `EVAL_ERROR`，score=None | 失败原因 `JUDGE_INFRA_ERROR:<code>`；mastery 不变 |
| `UNTRUSTED_CODE_EXECUTION_BLOCKED` / `JUDGE_SANDBOX_UNAVAILABLE` | `EVAL_ERROR`，score=None | 失败原因 `UNTRUSTED_CODE_EXECUTION_BLOCKED`（blocked 语义统一）；mastery 不变 |

- canonical 比较只由 supervisor 执行：`canonical_json`（`ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":")`）；bool/int/float 严格区分（`test_canonical_comparison_is_type_strict`）；worker `actual_canonical` 必须本身是精确 canonical 形式，否则按协议违反 → `JUDGE_INFRA_ERROR`。
- worker 响应出现 `passed`/`verdict`/`score`/`expected`/未知字段/重复键/非 canonical actual/超限 → `JUDGE_INFRA_ERROR`（`test_forged_passed_field_is_infra_error`、`test_malformed_or_forged_observation_is_infra_error`）。
- 学生错误（RAISED/SYNTAX_ERROR/IMPORT_ERROR/MISSING_FUNCTION）与 TLE 只影响学生证据；infra/blocked 不写 mastery（engine EVAL_ERROR 路径保持）。

---

## 5. Worker/OS 沙箱接入（引用 m1a-fixtures；P1-08 关闭）

- 不可信实现由 m1a-fixtures 提供并已合入本分支（`b-next/pr1-untrusted-worker` HEAD `8d7ede6`）：`protocol.py`（`m1b.judge.worker.v1`）、`sandbox.py`（`BwrapSandbox` + canary）、`worker.py`（`UntrustedExecutionWorker.run_case`）、`worker_runner.py`（单 case、协议 fd、`os._exit(0)`）。其详细证据见 `docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md`；本工作流**不维护第二份实现**。
- supervisor 只依赖 `worker.run_case(code, function_name, args, timeout_s)` 与 `worker.sandbox_available()`（`worker.py:90-150`）；worker 缺失/沙箱不可用 → 直接 blocked。
- 协议上限与实现一致（`protocol.py`）：request 2 MiB / response 128 KiB / args 1 MiB / actual 64 KiB；`request_id` 为 32 位十六进制；stdout/stderr 有界截断；`--size` 必须在 `--tmpfs` 前。

### 5.1 P1-08：bwrap `--size` 顺序（CLOSED）

威胁模型 v0.1 §4.2 早期写作 `--tmpfs /tmp --size 16777216`，bwrap 0.9.0 会拒绝；已修正为 `--size 16777216 --tmpfs /tmp`。本机复测证据：

```text
# 错误顺序：bwrap ... --tmpfs /tmp --size 16777216 ...
bwrap: --size must be followed by --tmpfs
exit=1

# 正确顺序（PR1 实现）：bwrap ... --size 16777216 --tmpfs /tmp ...
pid 2 uid 65534
exit=0
```

PR1 实现 `m1_teacher/assessment/judge/sandbox.py:353-356` 使用正确顺序（源码注释：`bwrap 0.9 requires --size *before* the --tmpfs it configures`）；沙箱定向测试 `tests/m1_teacher/test_judge_sandbox.py` 11 passed，`test_judge_worker.py` 23 passed，真实运行 14 题参考解 112/112 PASS 均通过该命令。威胁模型 v0.2 已标注 **P1-08 CLOSED** 并记录本节证据。

---

### 5.2 P1-1：默认超时 TLE 误分类（已修复）

独立评审复现：默认 `timeout_s=2.0` + 0.5s grace 时 wall 为 2.5s，但旧 `RLIMIT_CPU=2s` 先触发；bwrap 返回正 `exit=137`，worker 只把负 exit 当 timeout → 正 137 落到 `INFRA_ERROR`，故默认死循环被误判为 `EVAL_ERROR:JUDGE_INFRA_ERROR`。

修复（两处都做，符合评审建议）：

1. **wall timer 成为主判据**：`BwrapSandbox._cpu_limit_for_timeout(wall_s)` 按每次 run 动态设置 `RLIMIT_CPU = max(10, ceil(wall_s)+2)`（`sandbox.py`），确保 wall timeout 先触发；CPU limit 仅作防御性 backstop。
2. **worker 分类健壮化**：`UntrustedExecutionWorker._is_timeout_kill(result, timeout_s)` 将正 `124` / `137(128+SIGKILL)` / `152(128+SIGXCPU)` 在 `elapsed_s ≥ 0.9 × timeout_s` 时归类为 `TIMEOUT`（学生 TLE）；过早的资源 kill 仍为 `INFRA_ERROR`。负 exit（supervisor 进程组 kill）仍直接视为 timeout。
3. **回归测试**（`test_judge_correctness.py`，真实 worker/sandbox）：
   - `test_default_timeout_infinite_loop_is_student_tle`：默认 2.0s 死循环 → `TLE`（`infra_error=False`）；
   - `test_default_timeout_slow_correct_solution_passes`：`time.sleep(1.5)` 后返回正确值 → `PASS`；
   - `test_short_timeout_infinite_loop_is_still_student_tle`：0.5s 死循环 → `TLE`；
   - `test_scorer_default_timeout_infinite_loop_is_tle_not_infra`：`DeterministicScorer(..., trusted_fixture_only=True)` 默认 timeout → `INCORRECT / JUDGE_STUDENT_TLE`（不是 EVAL_ERROR）；
   - `test_scorer_default_timeout_slow_correct_solution_passes`：慢正确解 → `CORRECT`；
   - `test_judge_worker.py` 单测直接覆盖正 `137/152/124` 的 elapsed 阈值分类与 `_interpret` 映射。
   文档同步：`docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md` §4.3/§9.6 已改为动态 RLIMIT_CPU + 正 kill 分类说明。

### 5.3 P1-2：宿主非 root principal（LOCAL_ONLY，未满足）

本机 bwrap 以 root 启动，`/proc/self/uid_map = 65534 0 1`（inside 65534 → host 0）。namespace 内 uid 65534 **不**证明独立非 root OS principal。新增：

- `BwrapSandbox.security_profile()`：返回 host euid、`host_is_root`、uid_map、mapped host uids、sandbox uid/gid/python version、`non_root_principal_verified`、`profile`（`LOCAL_ONLY` / `NON_ROOT_PRINCIPAL`）与 limitation。
- `_non_root_principal_verified(host_euid, uid_map)`：host euid≠0 且所有 uid_map 映射目标≠0 才为 True。
- canary 自检新增记录 `uid_map` 与沙箱内 `python_version`；测试 `test_judge_sandbox.py::test_security_profile_records_host_euid_uid_map_and_non_root_flag` 断言当前 root 环境 `non_root_principal_verified=False`、`profile=LOCAL_ONLY`，并确认 host `/root`/`/etc`/sentinel 不可见（canary 既有断言）。
- 文档明确目标部署必须使用专用非 root 服务账号（或单独评审 setuid bwrap），本机结果 `LOCAL_ONLY`；**B1-04 仍为 `PARTIAL`，不声称满足**。

### 5.4 P1-3：安全 CI 不得跳过 OS 证据

- 新增 `tests/m1_teacher/judge_os_gate.py`，统一替换 7 处 sandbox 相关 `pytest.skip`/`skipif`：
  - 默认（普通单测 CI）缺 bwrap → `pytest.skip`；
  - 设置 `M1B_REQUIRE_OS_SANDBOX=1` → `pytest.fail`（拒绝 skip），保证安全 job 不可能在没有 OS 证据时全绿。
- `tests/m1_teacher/test_judge_ci_gate.py` 覆盖 helper 行为（available/unavailable、env truthy/falsey、required 时 fail、文档 lint）。
- 安全 CI 命令（期望 0 skipped）：`M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs`。
- P1-4：威胁模型 §5.1 删除“环境变量可作为开启开关”的旧表述，统一为仅可信构造/部署参数；实现与 P1-01 一致（不读任何 env 开关）。

## 6. 本地验证证据（真实运行）

### 6.1 全量 suite（本分支，2026-11-20，评审修复后）

```text
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
703 passed in 60.86s

$ M1B_REQUIRE_OS_SANDBOX=1 "/root/Autonomous Teacher/.venv/bin/python" \
    -m pytest tests/m1_teacher -q -rs
703 passed in 60.18s
# 0 skipped：安全 CI 门禁下没有跳过任何 OS/隔离动态证据
```

- 独立评审基线 **674 passed**；评审修复新增/加强了 29 个测试（P1-1 correctness 回归 5、P2-12 leakage 1、P1-3 ci gate 17、P1-2 sandbox 3、P1-1 worker 单测 3）→ **703 passed**；旧 M1-A 测试语义保留（无删除/跳过/弱化；仅 CODE 测试显式 opt-in + failure_reason 契约更新）。
- 全量 suite 运行环境：本机 Linux 6.17 + bwrap 0.9.0；离线，无 Provider/Key。

### 6.2 定向测试

| 测试文件 | 结果 | 覆盖 |
| --- | --- | --- |
| `test_judge_supervisor.py` | **36 passed in 0.05s** | 默认 blocked / P1-01 数据路径绕过 / canonical 类型严格 / 伪造响应 INFRA / 旧路径删除 / 确定性 |
| `test_judge_correctness.py` | **32 passed in 22.68s** | 14 参考解 112/112 PASS；7 负例 WA/RE/TLE/edge_correct；determinism；P1-1 默认 2.0s TLE/慢正确解；real worker+supervisor |
| `test_hidden_leakage_scan.py` | **16 passed in 4.48s** | 默认 blocked 不执行 learner code + mastery 不变；result/history/CLI 导出 sentinel 扫描；11 攻击模板不 PASS；P2-13；P2-12 112 expected 指纹扫描 |
| `test_judge_ci_gate.py` | **17 passed in 0.02s** | P1-3 helper 行为：缺 sandbox 默认 skip、`M1B_REQUIRE_OS_SANDBOX=1` 时 fail；文档 lint |
| `test_judge_worker.py`（m1a-fixtures） | **26 passed in 5.04s** | 单 case 协议、stdout/协议分离、伪造响应、超时、无 expected 进入 worker；P1-1 CPU kill 分类单测 |
| `test_judge_sandbox.py`（m1a-fixtures） | **14 passed in 0.78s** | bwrap 隔离（uid/fs/net/pid/rlimit/timeout）、canary、P1-08 命令、P1-2 security_profile |
| `test_judge_negatives.py`（m1a-fixtures） | **11 passed in 5.54s** | 负例分类与安全语义 |
| `test_judge_fixture_integrity.py`（m1a-fixtures） | **15 passed in 1.28s** | 认证语料完整性/无 sentinel 泄漏 |
| `test_assessment_scorer.py`（适配后） | **34 passed in 5.23s** | 既有 scorer 语义（显式 trusted-fixture opt-in） |

### 6.3 B1-05 正确性细节

- 14/14 reference solutions 经 `TrustedJudgeSupervisor` → `UntrustedExecutionWorker` → `BwrapSandbox` 全部 PASS；hidden cases **112/112**；单独探针一次跑完 14 题约 **4.0s**（测试文件 12.35s 包含重复跑与 TLE 负例）。
- 负例矩阵：`constant_return`/`off_by_one` → WA；`syntax_error`/`runtime_exception`/`missing_function` → RE；`infinite_loop` → TLE（短 timeout 0.5s）；`edge_correct` → PASS。逐条见 `test_judge_correctness.py::test_negative_classification`。
- 确定性：同输入两次 supervisor verdict 逐字段相同（`test_identical_inputs_produce_identical_verdicts`）。
- 判题错误不改 mastery：默认 blocked 的 engine 集成测试断言 snapshot=None、无 `ASSESSED`、ERROR payload `mastery_unchanged=True`、history rebuild 一致（`test_default_blocked_code_is_not_executed_and_never_evidence`）；既有 EVAL_ERROR 测试保持 34 passed。

---

## 7. B1-06 隐藏泄漏规格与运行时扫描（含 P2-13）

### 7.1 运行时扫描实现（不只 AST）

`test_hidden_leakage_scan.py` 构造 synthetic hidden spec（expected/args 使用认证语料的 sentinel 值），走完整链路后收集并扫描：

1. `AssessmentResult.to_dict()`（scorer 输出）；
2. `LearningHistory` / repository `HistoryEvent` payloads（engine 事件）；
3. `JudgeVerdict.to_dict()` 与 failure_reason/failure_codes；
4. 攻击模板（11 个模板 / 10 类 family：stack_frame_probe/argv_result_forgery/host_sentinel_read/socket_connect/fork_subprocess/infinite_loop/forged_protocol_output/write_runner_source_*/exit_code_tamper/exception_override）经真实 worker+supervisor 的 verdict；
5. CLI `--demo --json` 与 `python -m m1_teacher.demo` 输出（端到端 teacher-visible 导出）；
6. worker 请求边界（fake worker 记录：只收到 code/function_name/args，无 expected）。

断言：`sentinel_expected` / `sentinel_secret_token` / host sentinel content 在所有 teacher-visible 表面 **0 次出现**；hidden 评分路径（`judge/certification`、`judge/sentinels`、`fixtures/m1_teacher/judge`）不出现；`failure_reason` 不含 expected/args 原文；攻击模板永不 PASS。

### 7.2 P2-13：`AssessmentItem.scoring_spec_ref` 的记录与决定

- 现状：`AssessmentItem`（`m1a.v0` 合同）是 teacher-visible item，包含 `scoring_spec_ref` 字段（例如 `scoring/item.bs.code.001.json`，指向 hidden spec 的**相对定位符**）。engine/history 事件会序列化 item 字段，因此该 ref 会出现在 teacher-visible JSON 导出中。
- 定位：**是元数据 locator，不是 hidden 内容**。该字段只暴露文件相对名（不含 expected/args/测试正文，也不含 absolute path/traversal）；真正读取 spec 的组件仍只有 trusted scorer（静态约束由既有 `test_only_scorer_module_references_hidden_scoring_path` 等保证）。
- 决定（PR1）：**保留** `scoring_spec_ref`（不改 `m1a.v0` item schema，避免破坏冻结合同与历史事件 replay）；在运行时扫描中新增断言：
  - 断言该字段是安全相对路径（非 absolute、无 `..`）；
  - 断言 hidden spec **内容**（sentinel expected/args）不随该字段进入任何 teacher-visible 导出。
- 残余风险：spec 文件名本身对 Teacher 可见（信息面极小，不含内容）；若未来要求隐藏文件名，需要 `m1a.v0` 合同变更并另行评审，不在 PR1 范围。
- 测试：`test_hidden_leakage_scan.py::_assert_scoring_spec_refs_are_safe_metadata`（在 blocked engine/history 导出扫描中调用）。

---

## 8. B1-01..B1-06 映射与状态

> 状态口径：`IMPLEMENTED_LOCAL_VERIFIED` = 实现在本分支 + 本地测试真实通过；`NOT_RUN` = 独立安全 Reviewer 复跑/人类批准尚未进行。没有任何一项被本文件单方面宣称为最终 `PASS`。

| 验收项 | 实现/证据 | 状态 |
| --- | --- | --- |
| **B1-01** 默认 blocked | `DeterministicScorer` 默认不执行 CODE → `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`；engine 集成断言无执行/mastery 不变；P1-01 绕过测试；demo/CLI 无开启入口 | `IMPLEMENTED_LOCAL_VERIFIED`（评审 `VERIFIED LOCAL_ONLY`） |
| **B1-02** expected 隔离 | supervisor 只发 code/function_name/args；worker 协议禁止 expected；协议/worker 测试 + fake-worker 边界测试 + 真实 worker 112/112 通过；worker 内存/挂载/argv 无 expected 由 m1a-fixtures 测试覆盖 | `IMPLEMENTED_LOCAL_VERIFIED` |
| **B1-03** verdict 伪造 | 无 result 文件/argv；worker 响应无 passed/verdict；supervisor 严格 schema + canonical 比较；伪造 passed/未知字段/重复键/非 canonical/worker 异常 → `JUDGE_INFRA_ERROR`；atexit/exit 篡改由 worker 协议测试覆盖 | `IMPLEMENTED_LOCAL_VERIFIED` |
| **B1-04** OS 围栏 | merged `BwrapSandbox`（uid 65534、最小 ro rootfs、私有 tmpfs、netns none、pid/uts/ipc、dynamic rlimits、timeout、进程组 kill、canary fail-closed）；sandbox/worker 定向通过；**P1-2 宿主非 root principal 本机未满足（`LOCAL_ONLY`）** | **`PARTIAL`**（评审结论；待目标部署非 root 复跑） |
| **B1-05** 正确性/可用性 | 14/14 参考解、112/112 hidden cases PASS；WA/RE/TLE/edge_correct 分类正确；determinism；错误不改 mastery；**P1-1 默认 2.0s 死循环 TLE 已修复并回归** | 评审后修复，`LOCAL_RETESTED`；最终需复评为 `VERIFIED`（评审时 `PARTIAL`） |
| **B1-06** 泄漏扫描 | 运行时导出扫描（result/history/verdict/CLI/攻击模板），sentinel 0 泄漏；failure_reason 聚合无原文；P2-13 记录 `scoring_spec_ref` 决策 | `IMPLEMENTED_LOCAL_VERIFIED` |

**门禁**：B1 是真实用户 CODE 开放前的 **BLOCKER**。即使本分支 674 tests 全绿，仍需：独立安全 Reviewer 在冻结 SHA 上复跑/静态审计 + 人类批准；在此之前默认策略保持 `UNTRUSTED_CODE_EXECUTION_BLOCKED`，不得把 `IMPLEMENTED_LOCAL_VERIFIED` 当作可开放生产 CODE 的 `PASS`。

---

## 9. Demo / CLI 策略说明

- `m1_teacher/demo.py`：使用 `MockStudentScorer`（脚本化 synthetic 学生，`MOCK` 证据），**从不执行 learner CODE**；代码注释明确：任何未来 demo 若走独立 scorer 评分 CODE，必须显式 `DeterministicScorer(..., trusted_fixture_only=True)` 并标注 synthetic/trusted fixtures。
- `m1_teacher/cli.py`：`--demo`/`--student`/`--json` 均基于 demo 的 MOCK 路径；**不暴露** CLI 参数或请求字段启用 CODE 执行；policy 是可信构造/部署决策（P1-01）。
- CLI 端到端 JSON 导出已纳入 B1-06 扫描（`test_cli_demo_json_export_contains_no_hidden_material`）。

---

## 10. 限制、非目标与开放事项

- OS 沙箱/协议实现来自并行工作流；本文件不重复维护，若其后续变更（协议上限/命令）需同步引用 `docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md` 并重新跑本文件 §6 命令。
- 本机 `LOCAL_VERIFIED` 不等于目标 CI/部署可用：bwrap/userns 在部署环境需要验收；沙箱不可用时全部 CODE blocked（这是设计的安全降级），MCQ/SHORT 不受影响。
- **P1-2**：本机 bwrap 以 root 运行（`uid_map=65534 0 1`），`security_profile()["non_root_principal_verified"]=False`、`profile=LOCAL_ONLY`；B1-04 的独立非 root principal 仍需目标部署（专用非 root 服务账号或单独评审 setuid bwrap）复跑，本地不满足。
- **P1-3**：安全 CI 必须使用 `M1B_REQUIRE_OS_SANDBOX=1`，否则无 bwrap 的 job 会合法 skip 掉全部 OS 动态证据；普通单测 CI 的 skip 不构成 B1-04/05 证据。
- OS 沙箱 ≠ 学习效度或真实用户安全性证明；B1 只降低判题信任边界风险，不评价教学效果。
- B 线 `m1_offline` 仍是历史冻结实现（`judge.py` 的 in-process/result 文件路径不在本 PR 改造范围）；真实用户 CODE 的开放需要 B 线同类适配 + 本边界复用，另行评审。
- P2 开放：`AssessmentItem.scoring_spec_ref` 文件名可见（§7.2 已记录决定/残余风险）；若产品要求完全隐藏 spec 文件名，需要合同变更。
- 真实用户 CODE 仍 **BLOCKED**：需要独立 Reviewer 复跑 + 人类批准（本文件不构成批准）。

---

## 11. 复现命令

```bash
# 工作树
cd /root/m1b/pr1-judge   # branch b-next/pr1-judge-worker

# 全量（真实输出：703 passed in 60.86s）
# 安全 CI 门禁（真实输出：703 passed, 0 skipped in 64.92s）
M1B_REQUIRE_OS_SANDBOX=1 "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q -rs
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q

# 定向
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_judge_supervisor.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_judge_ci_gate.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_judge_correctness.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_hidden_leakage_scan.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_judge_worker.py tests/m1_teacher/test_judge_sandbox.py -q

# P1-08 顺序证据（正确顺序 exit 0；错误顺序 exit 1）
/usr/bin/bwrap --unshare-all --die-with-parent --clearenv \
  --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin \
  --proc /proc --dev /dev --size 16777216 --tmpfs /tmp \
  --uid 65534 --gid 65534 --hostname m1b-worker \
  /usr/bin/python3 -c "import os; print('pid', os.getpid(), 'uid', os.getuid())"
```

---

## 12. 变更文件清单（本 PR1 可信侧）

| 文件 | 变更 |
| --- | --- |
| `m1_teacher/assessment/judge/supervisor.py` | 新增：`JudgeVerdict` + `TrustedJudgeSupervisor`（可信比较、默认 blocked、fail-closed） |
| `m1_teacher/assessment/judge/__init__.py` | add-only 导出 supervisor 名称（文件仍归 m1a-fixtures；无删除/改动既有导出） |
| `m1_teacher/assessment/scorer.py` | CODE 路径改为 supervisor；默认 blocked；删除旧 runner/result-file 路径；新增 `trusted_fixture_only`/`judge_worker` 构造参数 |
| `m1_teacher/demo.py`、`m1_teacher/cli.py` | 增加 B-PR1 policy 注记（不执行 CODE、无请求级开关） |
| `m1_teacher/assessment/judge/sandbox.py` | P1-1 动态 `RLIMIT_CPU`（wall 优先）+ P1-2 `security_profile()`/uid_map/python_version canary 记录 |
| `m1_teacher/assessment/judge/worker.py` | P1-1 正 `124/137/152` + elapsed 阈值分类；P2-3 固定 `PYTHONHASHSEED`/`PYTHONDONTWRITEBYTECODE` |
| `m1_teacher/assessment/scorer.py` | P2-4 移除 `spec-sha256` evidence ref；P2-10 timeout 上限 5.0 与 supervisor/worker 对齐 |
| `tests/m1_teacher/judge_os_gate.py` + `test_judge_ci_gate.py` | 新增：P1-3 统一 OS sandbox 门禁 helper（17 tests） |
| `tests/m1_teacher/test_judge_supervisor.py` | 新增 36 tests |
| `tests/m1_teacher/test_judge_correctness.py` | 新增 32 tests（含 P1-1 默认 2.0s TLE / 慢正确解回归） |
| `tests/m1_teacher/test_hidden_leakage_scan.py` | 新增 16 tests（含 P2-13、P2-12 认证 expected 指纹扫描） |
| `tests/m1_teacher/test_judge_sandbox.py` / `test_judge_worker.py` | 新增 P1-2 security profile/非 root 校验逻辑、P1-1 CPU kill 分类单测 |
| `tests/m1_teacher/test_diagnostic_engine.py` | 稳定化既有 `created_at` 跨加载时序 flake（仅比较行为字段；非 PR1 语义变更） |
| `docs/M1_B_PR1_REVIEW.md` | 合入独立评审报告（原文） |
| `tests/m1_teacher/test_assessment_scorer.py` | 最小适配：CODE 测试显式 `trusted_fixture_only=True`；failure_reason 聚合契约更新；断言未弱化 |
| `tests/m1_teacher/test_fixtures_cf.py` | 合并自 worker 分支：teacher-visible fixture 扫描范围 narrowing（judge corpus 由 `test_judge_fixture_integrity.py` 校验） |
| `docs/M1_B_THREAT_MODEL_JUDGE.md` | v0.2：P1-01/P1-08 CLOSED、P2-05/P2-06 表述与实现对齐、协议上限同步 |
| `docs/M1_B_JUDGE_IMPLEMENTATION.md` | 本文件 |

---

## 13. 独立评审 P1/P2 处置（评审 `PASS_WITH_ACTIONS`）

### 13.1 P1（必须修）关闭证据

| 编号 | 结论 | 证据 |
| --- | --- | --- |
| P1-1 默认超时 TLE 误分类 | **CLOSED（本地修复/回归通过，待复评）** | wall timer 优先：`BwrapSandbox._cpu_limit_for_timeout` 动态 `RLIMIT_CPU=max(10,ceil(wall)+2)`；worker 正 `124/137/152` + `elapsed≥0.9×timeout` → TIMEOUT。测试：`test_default_timeout_infinite_loop_is_student_tle`、`test_default_timeout_slow_correct_solution_passes`、`test_short_timeout_infinite_loop_is_still_student_tle`、`test_scorer_default_timeout_infinite_loop_is_tle_not_infra`、`test_scorer_default_timeout_slow_correct_solution_passes`、`test_timeout_kill_classification_positive_signal_codes` |
| P1-2 宿主非 root principal | **CLOSED（报告/文档/测试落地；B1-04 仍 `PARTIAL`，LOCAL_ONLY）** | `security_profile()` + `_non_root_principal_verified()`；本机实测 `uid_map=65534 0 1`、`non_root_principal_verified=False`、`profile=LOCAL_ONLY`；测试 `test_security_profile_records_host_euid_uid_map_and_non_root_flag`、`test_non_root_principal_verification_logic`；文档 §5.3/§10 明确目标部署要求，不声称 B1-04 满足 |
| P1-3 CI 可跳过 OS 证据 | **CLOSED** | `judge_os_gate.require_os_sandbox` 统一 7 处 skip；`M1B_REQUIRE_OS_SANDBOX=1` 时 fail 而非 skip；测试 `test_gate_fails_when_security_ci_requires_os_sandbox` 等 17 tests；安全 CI 命令与 0 skipped 证据见 §6/§11 |
| P1-4 文档矛盾 | **CLOSED** | 威胁模型 §5.1 删除“环境变量可作为开启开关”的旧表述，统一仅可信构造/部署参数；实现不读 env；`test_docs_do_not_claim_env_can_enable_trusted_fixture` 全 docs lint |

### 13.2 P2 处置

| 编号 | 处置 | 说明 |
| --- | --- | --- |
| P2-1 §4.3 上限/首行规则 | ADDRESSED | 威胁模型更新 128 KiB、拒绝多行（与 `protocol.py` 一致） |
| P2-2 威胁模型 DESIGN_ONLY 状态 | ADDRESSED | 改为 `DESIGN + IMPLEMENTED_LOCAL_VERIFIED`，保留历史 v0.1 语义 |
| P2-3 clearenv 固定 env / 解释器 pin | PARTIAL | worker 已固定 `PYTHONHASHSEED=0`/`PYTHONDONTWRITEBYTECODE=1`，解释器路径固定 `/usr/bin/python3`；**版本 pin 校验未实现**，记录为部署验收项 |
| P2-4 `spec-sha256` evidence ref | ADDRESSED | 从 CODE 路径 `evidence_refs` 移除；仅保留 `item:<id>` |
| P2-5 `scoring_spec_ref` 文件名可见 | RECORDED | §7.2 保留原因/残余风险；不改为不透明 id（避免 `m1a.v0` 合同变更） |
| P2-6 learner 伪造合法 observation | RECORDED | 威胁模型 §10.2 新增风险说明：不能 PASS，最多 WA/RE/INFRA（fail-closed）；长期需子进程/不继承 fd |
| P2-7 NPROC/CPU 套件证据 | PARTIAL | P1-1 新增 wall/CPU 分类单测；`RLIMIT_NPROC=32` 套件级 fork 压力测试未加（需受控安全测试环境，避免宿主压力），保留独立探针/部署验收 |
| P2-8 `/proc/1/cmdline` 路径暴露 | RECORDED | 威胁模型 §10.2 记录为低风险（目录未挂载、不含 expected） |
| P2-9 `pytest.raises(Exception)` 过宽 | ADDRESSED | 收窄为 `ValidationError` / `WorkerProtocolError` |
| P2-10 scorer timeout 上限与 supervisor 不一致 | ADDRESSED | `_MAX_TIMEOUT_S=5.0` 与 supervisor/worker 对齐，构造期 fail-closed 明确报错 |
| P2-11 demo/cli opt-in 表述 | ADDRESSED | 实现文档明确 demo/CLI 无 CODE 入口、仅注释；不移交“已显式 opt-in”误解 |
| P2-12 认证语料 expected 指纹扫描 | ADDRESSED | 新增 112 个 expected canonical SHA-256 对 CLI 导出扫描（0 命中） |

## 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-11-20 | PR1 可信侧实现完成 + 本地验证：默认 blocked、supervisor 协议/比较、旧路径删除、P1-01/P1-08 关闭、P2-13 记录、B1-01..06 本地证据映射 |
| v0.2 | 2026-11-20 | 独立评审 `PASS_WITH_ACTIONS` 后修复：P1-1（默认 TLE 误分类，wall/CPU 分类 + 回归）、P1-2（security_profile/宿主非 root principal，LOCAL_ONLY）、P1-3（M1B_REQUIRE_OS_SANDBOX 安全门禁）、P1-4（文档仅构造参数）；P2-1/2/4/9/10/11/12 已处置，P2-3/7 部分缓解，P2-5/6/8 记录；新增测试计数与 CI 命令见 §6/§11/§13 |
