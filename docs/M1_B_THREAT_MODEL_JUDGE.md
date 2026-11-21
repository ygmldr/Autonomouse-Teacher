# M1-B / B-PR1 — Judge 信任边界威胁模型与 Worker 隔离协议

- 文档编号：`M1_B_THREAT_MODEL_JUDGE` / B-PR1 设计前置
- 状态：**DESIGN + IMPLEMENTED_LOCAL_VERIFIED**（设计规格；PR1 已实现并在本机通过本地测试；独立验收前真实用户 CODE 仍 BLOCKED）
- 版本：v0.4（2026-11-20，UTC；PR1 实现 + 评审/复核附录 P1/P2 回填；P1-2 启动校验与 P1-3 CI 接线见 §4.4/§10.2）
- 作者：B-NEXT / B-PR1 Judge 安全边界设计负责人（Implementer 前置设计）
- 工作树：`/root/m1b/tm`，分支 `b-next/pr1-threat-model`，基线 `4706250643fd42d48d69ddad7159e011955fa9fd`
  （`work/m1a-mvp`，即 M1-A PR1–PR5 冻结 HEAD）
- 对照实现线：
  - A 线：`/root/at-m1a-mvp` @ `4706250`（`m1_teacher`，M1-A MVP）
  - B 线：`/root/at-m1-offline` @ `290c577`（branch `work/m1-offline-design`，M1 Offline Teacher）
- 交接依据：`/root/leadb_zip/START_HERE.md`、`02_LEADB_AGENT_HANDOFF.md`（B1）、`AUDIT_REQUESTS.md`（B-Q1/B-Q5）、`COMMON_REVIEW_AND_ROADMAP.md`（B-01）、`TEST_EVIDENCE_MATRIX.csv`（B1-01..B1-06）。
- 结论性质：**offline synthetic, design-only**。本文不声称任何 B1 验收项 PASS；`LOCAL_PROBE` 只用于证明现有实现的根因与拟议 OS 边界在本机的可行性，不等于 PR1 实现验收，也不等于真实用户 CODE 可开放。
- 强制边界：不联网、不调用真实 Provider/Key、不写真实 Provider/M0 代码、不复制真实 hidden fixture 内容；`LOCAL_PROBE` 全部使用自编 synthetic sentinel 与临时 `/tmp` 脚本（脚本不入库）。本文不修改任何实现/测试/fixture。

### 证据等级（与 `docs/m1/EVALUATION_PROTOCOL.md` §3 口径一致）

| 等级 | 本文用法 |
| --- | --- |
| `DESIGN_ONLY` | 仅设计/规格/冻结协议的历史标记（本文 v0.1） |
| `IMPLEMENTED_LOCAL_VERIFIED` | PR1 已实现并通过本机本地测试；独立安全 Reviewer 复跑/人类批准前不得当作最终 PASS |
| `LOCAL_PROBE` | 本机真实运行的一次性探针（脚本在 `/tmp/m1b_probe`，不提交；仅合成数据；命令与输出摘要见附录 A） |
| `SOURCE_INSPECTED` | 对指定 SHA 的源码逐行静态核对（`file:line` 引用） |
| `NOT_RUN` | 尚未执行，不得视为通过 |
| `UNVERIFIED` | 依赖外部/独立评审或不在本 PR 范围 |

> **B1 门禁声明**：B1 是"任何真实用户/外部提交的 CODE 进入判题与教学闭环"之前的 **BLOCKER**。
> 在 OS 沙箱 + 可信判题协议实现、并通过**独立安全 Reviewer**验收与人类批准之前：
> 默认策略必须为 `UNTRUSTED_CODE_EXECUTION_BLOCKED`（不执行 learner code），
> 且不得以"现有 536 / 365 测试通过"为依据开放该能力；两套历史 suite 数字也不得相加。

---

## 0. 结论摘要（给 Reviewer 的 60 秒视图）

1. **根因已复现**：A 线 `m1_teacher/assessment/scorer.py` 与 B 线 `m1_offline/cf/judge.py` 都把 hidden `expected/tests` 送进**导入了学习者代码的同一个 Python 进程**（不同文件/不同 JSON 形态，本质相同），并把 `result` 文件路径放进子进程 `argv`，父进程**信任**该文件中的 `cases[].passed`。`LOCAL_PROBE` 已真实证明：
   - 学习者代码可沿调用栈读取 expected 并返回之 → 旧 A/B 判题均得到 `CORRECT`/`passed=True`；
   - 学习者代码可在 `atexit` 中覆写 result 文件 → 旧 A/B 父进程均接受伪造 `passed` → `CORRECT`/`passed=True`；
   - 学习者代码以 **uid=0 + host 全文件系统 + host 网络接口**运行（A/B 均实测到 `eth0`/`cni-podman0`、`/root` 可见可列、A 线 hidden scoring spec 可读、host 私有 sentinel 可读）；
   - B 线 `JudgeResult.failures` 字符串包含 `args_repr` / `expected_repr`，实测 3/3 synthetic sentinel expected 出现在 failures（B-Q5 的 API 泄漏面）。
2. **冻结边界**：可信端 `TrustedJudgeSupervisor` 独占 hidden expected、scoring spec/config、比较器与最终 verdict；不可信端 `UntrustedExecutionWorker` 只接收**单个 case 的输入 + 目标函数名**（**绝不含 expected**），只返回**观测 actual/异常/状态**，**不含任何 verdict/passed 字段**；OS 层用 `bwrap` 独立 user/pid/net/ipc/uts namespaces + 非 root uid + read-only 最小 rootfs + 私有 tmpfs + rlimits + supervisor wall-clock。
3. **本机 OS 边界已实测可用**：`bwrap 0.9.0`，`--unshare-all --die-with-parent --clearenv` + `ro-bind /usr /lib /lib64 /bin` + `--proc --dev --tmpfs /tmp` 可运行 python3；实测 uid/gid=65534、pid=2、host `/root`/`/etc`/`/home`/`/var/lib` 不可见、host sentinel `FileNotFoundError`、`/usr` 只读、`/tmp` 私有可写、`/proc/net/dev` **只有 lo**、`socket.if_nameindex()==['lo']`；rlimits（AS/CPU/FSIZE/NOFILE）与进程组清理实测生效。**不发起任何外网连接**。
4. **默认策略**：对外/开放路径默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED`（不执行 learner code，返回结构化 blocked，mastery 不变）；仅显式 `trusted_fixture_test_only` 的合成内部测试入口允许执行自编 fixtures；MCQ/静态短答案不受影响。
5. **验收状态**：PR1 已实现（见 `docs/M1_B_JUDGE_IMPLEMENTATION.md`）；B1-01/02/03/06 为 `IMPLEMENTED_LOCAL_VERIFIED`，B1-04/B1-05 在独立评审后为 `PARTIAL`（P1-2 宿主非 root principal 未满足；P1-1 默认超时误分类已修复、待复评）。独立 Reviewer 复跑 + 人类批准前不得开放真实用户 CODE。

**最高风险 Top 5（给 Reviewer）**
1. 若 PR1 只"加沙箱"但不把 expected 从 worker 内存/协议中移除，调用栈泄漏与协议伪造仍然成立（必须先冻结 §3 协议）。
2. 若保留"worker 返回 passed"或保留 result 文件/argv 路径，任何 worker 侧伪造都能造成 PASS（必须由可信端比较 actual）。
3. 若默认策略没有 fail-closed（沙箱不可用回退裸子进程），B1-01 等于没有控制（必须 `UNTRUSTED_CODE_EXECUTION_BLOCKED`）。
4. 若 `JudgeResult.failures`/日志/Teacher trace 继续携带 `args_repr`/`expected_repr`，hidden expected 会经 diagnostic/trace 泄漏（B1-06）。
5. OS 沙箱可用性依赖内核/容器策略（userns、bwrap、cgroup 缺失），部署环境差异可能导致 blocked 或隔离不足；必须有启动自检与独立验收，不能默认"本机可用=生产可用"。

---

## 1. 资产、信任域与边界

### 1.1 资产清单

| # | 资产 | 当前位置（示例） | 安全属性 | 泄露/破坏影响 |
| --- | --- | --- | --- | --- |
| A1 | hidden expected / hidden tests | A：`fixtures/m1_teacher/domains/cf_binary_search/scoring/*.json`；B：`fixtures/m1/cf/hidden/*.json` | 机密性（绝不进入不可信域） | 学习者可硬编码/逐题作弊；判题失去意义 |
| A2 | scoring spec / scorer config / 比较器 | A/B 的 scoring 规格与判题代码 | 机密性 + 完整性 | 可被篡改以产生 PASS；可被伪造 |
| A3 | 最终 verdict（`AssessmentResult.passed/status/score`、B 线 `JudgeResult.passed`） | 当前由 worker 子进程产出 | 完整性（只能由可信端决定） | 伪造 PASS → mastery 上涨/错误教学 |
| A4 | learner/session DB、事件日志（A：SQLite；B2 将加事务） | 宿主 repository | 机密性 + 完整性隔离 | 跨学习者泄漏、重复 mastery、错误恢复 |
| A5 | 可信结果目录 / attempt journal（PR1 新增） | 仅 supervisor 可写 | 完整性 | 伪造已完成 attempt；幂等/恢复被破坏 |
| A6 | Teacher 可见输出：`DiagnosticResult`、`TeachingAction`、trace/JSONL 导出、CLI/API 响应 | Teacher Core / b-eval harness | 机密性（不得含 A1/A2） | B1-06 泄漏；被学习者反向利用 |
| A7 | Learner mastery / 错误计数 | A：`LearnerSnapshot`；B：`LearnerState` | 只允许来自 observed evidence | 判题错误被当成学生错误 → 错误下调 mastery |
| A8 | runtime/Provider 凭证、M0 security/bridge/LiveGate | 不在本 PR 范围（M0 保护路径） | — | 本文件不触碰、不设计、不复用；仍 0 Key/0 外部网络 |

### 1.2 两个信任域

```
        (untrusted input: learner code / response)                    (trusted memory only)
 ┌──────────────────────────────┐        request(no expected)      ┌────────────────────────────────┐
 │ UntrustedExecutionWorker     │ <──────────────────────────────  │ TrustedJudgeSupervisor         │
 │  - bwrap user/pid/net/ipc/   │                                  │  - hidden expected/tests       │
 │    uts namespaces            │  response(actual/exception only) │  - scoring spec/config         │
 │  - uid 65534, ro minimal root│ ───────────────────────────────> │  - canonical comparator        │
 │  - private tmpfs, no network │                                  │  - final PASS/WA/RE/TLE verdict│
 │  - rlimits + wall timeout    │                                  │  - learner/session DB writes   │
 │  - outputs ALL untrusted     │                                  │  - trusted result dir/journal  │
 └──────────────────────────────┘                                  └────────────────────────────────┘
```

| 边界维度 | TrustedJudgeSupervisor | UntrustedExecutionWorker | 强制手段（目标实现） |
| --- | --- | --- | --- |
| 进程 | 宿主可信进程 | 独立 bwrap 子进程（独立 pid namespace） | `--unshare-pid` / `Popen` 独立进程组 |
| 身份 | 宿主判题服务身份 | 非 root（uid/gid 65534），无宿主 sudo/caps | `--unshare-user --uid 65534 --gid 65534` |
| 文件系统 | 可见 fixture/DB/可信目录 | read-only 最小 rootfs（仅 /usr /lib /lib64 /bin + ro worker 目录 + 私有 tmpfs），**不可见** fixture/scoring/expected/DB/host 私有目录 | `--ro-bind` 白名单 + `--tmpfs`；禁止 `/root`、`/home`、`/etc`、`/var`、`/tmp` 宿主目录 |
| 网络 | 不用于判题 | 无网络接口（netns none，只有 lo） | `--unshare-net` |
| IPC/UTS | 宿主 | 独立 IPC/UTS（随机 hostname） | `--unshare-ipc --unshare-uts` |
| 通道 | 写入 request stdin、读取 response stdout（或专用 fd） | 只读 request stdin、写 response 单行 | 管道；**无 result 文件、无 argv 路径** |
| 资源 | 由 supervisor 设置/观测 | CPU/AS/NPROC/FSIZE/NOFILE + wall timeout + 输出上限 | `resource.setrlimit`（preexec）+ `communicate(timeout)` + 进程组 SIGKILL |
| 身份/产物可信性 | 全部可信（expected/verdict/DB） | **actual、异常类型、退出码、stdout/stderr、耗时、资源消耗、协议字段全部不可信** | supervisor 严格 schema 校验 + 自己比较 expected |

### 1.3 安全不变量（PR1 必须测试的不变量）

- **I1（expected 不出可信域）**：expected/hidden 全量 tests/scoring spec 内容绝不出现在 worker 的 argv、env、stdin request、mount、worker 进程可见内存、response、日志、panic、coredump 路径中。
- **I2（verdict 不可伪造）**：worker 无论返回什么（actual、exception、exit code、stdout、伪造 JSON、协议字段），都不得让可信端产生 PASS；PASS 仅当"可信端 schema 校验通过的 COMPLETED actual 规范化后与可信 expected 完全相等"。
- **I3（隔离不退化）**：worker 不能读取宿主私有文件/DB/fixture、不能访问网络、不能逃逸到宿主进程/文件系统、不能造成宿主资源耗尽；任何隔离不可用 → fail-closed BLOCKED。
- **I4（错误不惩罚学生）**：`JUDGE_INFRA_ERROR` / `UNTRUSTED_CODE_EXECUTION_BLOCKED` 不得写 mastery、不得计错误、不得作为 INCORRECT；学生 TLE/RE/WA 才进入学生证据。
- **I5（不泄漏）**：Teacher 可见的 messages/traces/JSON/导出/诊断失败只含聚合错误码、计数与公开可解释提示；不含 expected/hidden args/scoring 内容。
- **I6（确定性）**：同一 `(problem, case, solution)` 在固定协议/版本下产生逐字段相同结果；request_id/时间戳不得进入比较语义。

### 1.4 威胁模型范围

- **在范围内**：学习者提交的 CODE（半对抗，最坏情况视为恶意 Python 代码）；scorer/worker 自身崩溃与被篡改；隐藏 expected 经调用栈/协议/日志泄漏；伪造 verdict；跨学习者 DB 读取（作为 asset A4 的隔离目标，详细事务/幂等在 B-PR2/B-PR3）；原型污染类攻击（输出伪造、异常覆盖、退出码篡改、fork 子进程）。
- **不在范围内**：宿主内核/bwrap 自身 0day、物理侧信道、真实恶意软件、真实 Provider/网络、真实个人数据、M0 安全桥/LiveGate/费用账本（不得改动）、把 OS 沙箱等同于"教学有效"。
- **信任假设**：宿主 supervisor 进程、bwrap 二进制、Python 解释器与内核可信；部署者不把 root 交给学习者；hidden fixture 在可信数据面不可被学习者/外部输入改写。

---

## 2. 现有实现根因证据（SOURCE_INSPECTED + LOCAL_PROBE）

> 以下逐条引用 **A 线 @4706250** 与 **B 线 @290c577** 的源码行号。行号以两仓库冻结 SHA 为准。
> `LOCAL_PROBE` 复现脚本只使用 synthetic sentinel，不引用 hidden fixture 内容（见附录 A）。

### 2.1 A 线 `m1_teacher/assessment/scorer.py`（M1-A）

**2.1.1 expected 与学习者代码同进程**

- `m1_teacher/assessment/scorer.py:30-40`：docstring 自称 "isolated child process … This is a local correctness/determinism boundary, **not** an OS security sandbox"；即 A 线已承认非沙箱，但实现仍把其用于 CODE 判分。
- `m1_teacher/assessment/scorer.py:534-597` `_run_learner_code`：创建 tempdir、写 `solution.py` 与 runner、`tempfile` 内运行 `subprocess.Popen([...])`。
- `m1_teacher/assessment/scorer.py:548`：`result_path = os.path.join(work_dir, "result.json")`。
- `m1_teacher/assessment/scorer.py:556-561`：`payload = json.dumps({"function_name": ..., "tests": normalized_tests})` 作为 **stdin** 传给子进程；`tests` 内含 `args` 与 **`expected`**。
- `m1_teacher/assessment/scorer.py:115-181`（`_CODE_RUNNER_SOURCE`）：
  - `76-81`（B 线对应）在 A 线为 `134-140`：`payload = json.loads(sys.stdin.read())` → `tests = payload.get("tests")`，expected 进入 runner 进程内存的普通 local 变量；
  - `144-152`（A 线）：`importlib.util.spec_from_file_location(...); spec.loader.exec_module(module)` **在同一个 Python 进程内**导入学习者 solution；
  - `162-180`（A 线）：逐 case 取 `expected = case.get("expected")`，`entry["passed"] = (actual_json == expected_json)` —— **passed 由不可信子进程计算**。
- `m1_teacher/assessment/scorer.py:564`：`[sys.executable, "-I", "-B", runner_path, result_path]` —— result 文件路径进入子进程 `argv[1]`。
- `m1_teacher/assessment/scorer.py:586-595`：父进程从 `result_path` 读 JSON；`609-647` `_classify_code_outcome` 中 `621`：`passed = sum(1 for case in cases if case.get("passed") is True)`，`638`：`if passed == total and total > 0: return "CORRECT"` —— **父进程完全信任不可信子进程提供的 `passed` 字段**。

**2.1.2 无 OS 隔离（uid/FS/网络/进程）**

- 子进程仅 `-I -B` + 最小 env（`_minimal_env`）+ tempdir + `start_new_session=True`（`_run_learner_code`），没有 mount/user/net/pid namespace、没有非 root、没有 rlimit；继承宿主 uid/FS/网络。
- `LOCAL_PROBE` 实测（A 线 current checkout）：synthetic 学习者代码在 scorer 子进程内得到 `uid=0`、`interfaces=["cni-podman0","eth0","lo"]`、`/root` 可见且可列、host 私有 sentinel 可读、**A 线真实 hidden scoring spec 可读**（只记录可读布尔值，未复制内容）、可写 `/tmp` 文件作为"逃逸"证据。见附录 A.4。
- `m1_teacher/assessment/scorer.py:599-607`：仅 kill 进程组；无资源上限（CPU/AS/NPROC/FSIZE/NOFILE）。

**2.1.3 现有测试的隔离假设（gap 证据）**

- `tests/m1_teacher/test_assessment_scorer.py:1-15`：测试目标承认 fail-closed/EVAL_ERROR 边界，但**没有任何 OS 隔离/沙箱断言**；同进程风险未被测试覆盖。
- `tests/m1_teacher/test_assessment_scorer.py:280-293`：`test_code_timeout_is_student_failure_not_infrastructure` 只验证超时分类，不验证隔离。
- `tests/m1_teacher/test_assessment_scorer.py:484-500`：静态测试只扫描"source 字符串里是否出现 hidden path"（AST/字符串层），**不能证明运行时不可达**；AUDIT B-Q5 明确要求运行时导出扫描，而不是只看 git AST。
- `m1_teacher/assessment/scorer.py:469-491`（`_score_mcq`）与 `649+`（`_score_short_answer`）不需要 worker；这是默认 blocked 策略下应保持可用的正确行为（见 §5）。

**2.1.4 与 B1-05 相关的正面控制（现有设计中对的部分）**

- `m1_teacher/session/engine.py:812-831` `_score_safely`：scorer 抛异常 → 构造 `EVAL_ERROR`（不把异常当学生错误）。
- `m1_teacher/session/engine.py:855-895` `_handle_eval_error`：只写 `ERROR` 事件，不调用 `apply_assessment`，不写 snapshot、不改 error_counts。
- `m1_teacher/session/engine.py:938-961` `_handle_observed_result`：只有 `CORRECT/INCORRECT/PARTIAL` 才 `apply_assessment`（`945`），即"判题错误不改 Learner mastery"在 A 线已有代码级接线（`LOCAL_PROBE` 重跑相关 3 个测试 3 passed，见附录 A.5）。
- 但该控制的前提是 **scorer 自身可信**；当 scorer 把隐藏 expected 交给不可信 code 并被伪造 PASS 时，错误方向是"把作弊当 CORRECT"，属于 A3/A7 破坏，不是 EVAL_ERROR 路径能覆盖的。

### 2.2 B 线 `m1_offline/cf/judge.py`（M1 Offline Teacher）

**2.2.1 expected 与学习者代码同进程（"stdin 不进 temp 目录"并不等于隔离）**

- `m1_offline/cf/judge.py:51` 注释/设计宣称："test payload from stdin (so hidden expectations never sit in the temp dir)"；`docs/m1/CF_TEACHER_SPEC.md:96-140` 也记录该设计。
- 但 `judge.py:55-145`（`_RUNNER_SOURCE`）：
  - `76-81`：`payload = json.loads(sys.stdin.read())`；`tests = payload.get("tests") or []` —— hidden 全量 `tests` 在 **runner 进程内存**；
  - `88-100`：`importlib.util.spec_from_file_location("m1_cf_learner_solution", "solution.py"); spec.loader.exec_module(module)` —— 学习者代码在**同一个 Python 进程**导入；
  - `117-137`：逐 case `expected = case.get("expected")`，`entry["passed"] = actual == expected`；hidden expected 与学习者代码共享地址空间。
- `judge.py:302-352` `_run_subprocess`：`311` argv 含 `result_path`；`333-340` 父进程读 result 文件并解析；无 mount/user/net/pid namespace、无不 root、无 rlimit。
- `judge.py:356-420` `_interpret`：`400` `if case.get("passed") is True: passed_count += 1`；`414` `passed=passed_count == total` —— **父进程信任子进程写的 `passed`**。
- `LOCAL_PROBE` 实测（B 线 current checkout）：synthetic 学习者代码沿调用栈读取 runner `payload["tests"]` → 返回 expected → `JudgeResult.passed=True`；`atexit` 覆写 result 文件 → 父进程 `passed=True`；worker 以 uid=0/宿主网络/host FS 运行（`eth0` 等）。见附录 A.4。

**2.2.2 `JudgeResult.failures` 的 expected 泄漏面（B-Q5）**

- `judge.py:121-122`：失败 case 记录 `args_repr: repr(args)[:200]`、`expected_repr: repr(expected)[:200]`；
- `judge.py:407-412`：mismatch 失败字符串拼成 `case-XX kind=... mismatch: args=<args_repr> expected=<expected_repr> actual=<actual_repr>`，截断后进入 `failures.append(...)`；
- `judge.py:149-164` `JudgeResult` dataclass：`failures: list[str]` 是**调用方可见 API**。
- 实测：synthetic sentinel expected 在 `JudgeResult.failures` 中 3/3 出现（附录 A.4 `B_expected_in_judgeresult_failures`）。
- **Teacher 路径核对（SOURCE_INSPECTED）**：
  - `m1_offline/cf/teacher.py:283`：仅 fatal 错误（syntax/import/missing_function）时把 `result.failures[0]` 放进 `DiagnosticResult.explanation`；fatal 消息来自 runner 的异常类型/消息，**不含 expected**；
  - `teacher.py:328` / `369`：mismatch 路径仅内部 `_parse_failures`/`_has_off_by_one` 读取 failures，用于分类；
  - `teacher.py:406-413`：最终 `explanation` 只拼 `failed_kinds`、`cases_passed/total` 与聚合原因，**不逐条输出 failures**；
  - `m1_offline/evaluation/harness.py:1038`：`failure_count = len(verdict.failures)`；`1061`：trace payload 写入 `judge_failure_count`（整数），**当前 b-eval trace 不含 expected**。
  - `LOCAL_PROBE`：用 inline hidden 调用 `CFTeacher.diagnose`，synthetic sentinel 在 `DiagnosticResult` 可见字段中出现：`False`（见附录 A.4）；但 `JudgeResult.failures` 本身已构成泄漏面——任何调用方把它写日志/trace/LLM prompt 都会泄漏，属于 API 设计缺陷而非"目前未触发"。
- 结论：B1-06 必须把 expected/args 从**任何 Teacher 可见/导出路径**移除（`failures` 改为 case 序号 + 分类；或只在受限 judge 内部日志保留哈希），并增加**运行时导出扫描**，不能只依赖当前 harness "恰好只取 count"。

**2.2.3 B 线已有文档与合同的现状**

- `docs/m1/CF_TEACHER_SPEC.md:25`、`96-140`、`128-140`、`289-291`：已如实披露"本地子进程不是安全沙箱"；威胁模型进一步把该限制升级为**默认能力门禁**（B1-01），而不是继续作为可接受的已知限制。
- `m1_offline/types.py:601-628` `AssessmentResult`（`passed/score/dimensions/...`）：passed 是 Teacher 可见的最终判定语义；因此 A3 的完整性要求必须由可信端产生。
- `m1_offline/types.py` 不含 expected 字段是正确的（隐藏面应在 scoring 侧）；问题在于实现把 scoring 内容送进 worker。

### 2.3 共同根因（B-01）

| 根因 | A 线证据 | B 线证据 | 后果 |
| --- | --- | --- | --- |
| R1 hidden expected 与学习者代码同进程/同地址空间 | `scorer.py:556-561`, `115-181`（runner 内 tests/expected + `exec_module`） | `judge.py:76-81`, `117-137`, `88-100` | 调用栈/`gc`/`inspect` 可读取 expected；LOCAL_PROBE 实测可作弊 PASS |
| R2 worker 侧计算并返回 `passed`，父进程信任 | `scorer.py:621`, `638` | `judge.py:400`, `414` | worker 篡改 result 即伪造 PASS；LOCAL_PROBE 实测 atexit 覆写成功 |
| R3 result 文件路径经 argv 暴露且 worker 可写 | `scorer.py:548`, `564`, `586-595` | `judge.py:311`, `333-340` | 伪造/覆盖 result；协议不可信 |
| R4 无 OS 隔离（uid/FS/net/pid/rlimit） | `scorer.py:534-597`（仅 -I/-B/tempdir/timeout） | `judge.py:302-352` 同构 | uid=0、host FS/网络可见；LOCAL_PROBE 实测 |
| R5 失败摘要携带 expected_repr/args_repr | A 无（failure_reason 仅计数；`scorer.py:609-647`） | `judge.py:121-122`, `407-412` | B-Q5 泄漏面；任何 caller 记录即泄漏 |
| R6 默认无能力门禁 | A/B 默认 CODE 即可执行 | 同 | 真实用户 CODE 在无沙箱下即可进入判题 |

> 说明：A 线 `_CODE_RUNNER_SOURCE` 在 runner 内存中同样有 `payload`/`tests`；B 线通过 stdin 只是避免 expected 落到 temp 文件，**不改变同进程事实**。两线都不满足 B1-02/03/04。

---

## 3. 冻结 Worker 协议 `m1b.judge.worker.v1`（DESIGN + IMPLEMENTED）

> 设计原则：**worker 只知道"要执行什么"，不知道"正确答案是什么"；只报告"观测到什么"，不报告"是否通过"。**
> 一个 worker 进程只处理一个 case（一次请求），进程退出即销毁；不跨 case 持久化，避免 expected/状态累积。

### 3.1 版本与传输

- 协议版本常量：`m1b.judge.worker.v1`（request/response 都必须携带；不匹配 → `JUDGE_INFRA_ERROR`）。
- 传输：supervisor 通过 stdin 发送**单个** UTF-8 JSON 对象（无 BOM、无换行要求），通过**专用协议 fd** 读取**恰好一行** UTF-8 JSON（上限 128 KiB；多行/空行/后续多余字节一律拒绝并判 `JUDGE_INFRA_ERROR`，不做“取第一行”的宽松解析；与 `protocol.parse_worker_response` 实现一致）。该 fd 由 worker_runner 在导入 learner 代码前 `os.dup(1)` 得到（通常为 fd 3），随后 fd 1/2 被重定向到 `/dev/null`； learner 的 `print`/`sys.stdout.write` 不能进入协议通道，worker_runner 写完唯一一行响应后立即 `os._exit(0)`（详见 §4.3；与 m1a-fixtures 的 `worker_runner.py` 实现一致）。
- **不使用** argv 传入任何路径/expected；**不使用** result 文件；**不使用**共享可写目录。
- supervisor 侧禁止把 request/response 写入 Teacher 可见日志（仅受限 judge 日志，且只含 request_id/case_index/分类/耗时/资源摘要；不允许 expected/args 原文）。

### 3.2 Trusted → Worker 请求（唯一允许字段）

```json
{
  "schema_version": "m1b.judge.worker.v1",
  "request_id": "7c1f0b9a2d4e6f80112233445566aabb",
  "function_name": "binary_search_exact",
  "args": [[1, 3, 5, 7, 9], 4],
  "timeout_ms": 1500,
  "stdout_limit": 512,
  "stderr_limit": 512
}
```

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | 必须 `"m1b.judge.worker.v1"` | 协议版本 |
| `request_id` | string | `^[a-f0-9]{16,64}$`（实现生成 32 hex） | supervisor 生成，仅用于日志关联；不参与比较 |
| `function_name` | string | `^[A-Za-z_][A-Za-z0-9_]{0,127}$` | 目标函数名 |
| `args` | array (JSON) | canonical JSON ≤ 1 MiB；允许 JSON 基本类型/数组/对象；深度 ≤ 4；总节点数 ≤ 1,048,576 | **单个 case 的输入**（不是全量 tests） |
| `timeout_ms` | integer | 50 ≤ x ≤ 5000 | 该 case 的墙钟预算（supervisor 还会外加 500ms kill 宽限） |
| `stdout_limit` | integer | 0..4096 | learner stdout 截断上限 |
| `stderr_limit` | integer | 0..4096 | learner stderr 截断上限 |

**禁止字段（worker 必须拒绝、不得提供任何默认行为）**：`expected`、`tests`、`hidden`、`case_index`、`scoring_spec_ref`、`scoring_path`、`workspace`、`result_path`、`db_path`、`learner_id`、`session_id`、`verdict`、`passed`、任何宿主路径。未知字段 → worker 返回 `INFRA_ERROR(REQUEST_UNKNOWN_FIELD)`；supervisor 本身也不得构造这些字段（测试断言 request JSON 不含 expected 子串）。
**P2-05/06 对齐说明（PR1 已关闭）**：PR1 实现的 `m1_teacher/assessment/judge/protocol.py` 在保持字段名/语义/禁止字段不变的前提下，把字节上限按 14 题认证语料的最大 hidden actual 上调为 request 2 MiB / response 128 KiB / args 1 MiB / actual 64 KiB；`request_id` 由 `secrets.token_hex(16)` 生成 32 位十六进制，示例与正则一致。协议通道的精确表述见 §3.1 与 `worker_runner.py`（`os.dup(1)` 专用 fd、fd1/2 重定向、`os._exit(0)`）。

### 3.3 Worker → Trusted 响应（唯一允许字段）

```json
{
  "schema_version": "m1b.judge.worker.v1",
  "request_id": "7c1f0b9a2d4e6f80112233445566aabb",
  "status": "COMPLETED",
  "actual_canonical": "-1",
  "exception_type": null,
  "stdout_excerpt": "",
  "stderr_excerpt": ""
}
```

| 字段 | 类型 | 约束 | 说明 |
| --- | --- | --- | --- |
| `schema_version` | string | `"m1b.judge.worker.v1"` | 版本 |
| `request_id` | string | 必须与请求一致 | 关联/防串 |
| `status` | string enum | `COMPLETED` / `RAISED` / `SYNTAX_ERROR` / `IMPORT_ERROR` / `MISSING_FUNCTION` / `TIMEOUT` / `INFRA_ERROR` | 只描述 worker 观测；**不是 verdict** |
| `actual_canonical` | string\|null | `COMPLETED` 时非 null，canonical JSON ≤ 64 KiB；其他状态为 null | 观测返回值（字符串形式）；不是 passed |
| `exception_type` | string\|null | ≤128；`^[A-Za-z_][A-Za-z0-9_.]{0,127}$` | 异常类名，**不含 message/堆栈/expected** |
| `stdout_excerpt` | string | ≤ `stdout_limit` 字节（UTF-8 截断按字符边界） | learner stdout（不可信、仅调试/聚合） |
| `stderr_excerpt` | string | ≤ `stderr_limit` 字节 | learner stderr（不可信） |

**禁止字段**：`passed`、`verdict`、`score`、`correct`、`expected`、`tests`、`case_count`、`hidden_*`、`assessment`、任何评分/结果结论。响应中出现未知字段 → `JUDGE_INFRA_ERROR`（fail-closed，绝不当 PASS）。
响应中 `status=INFRA_ERROR/TIMEOUT` 由 supervisor 映射为 `JUDGE_INFRA_ERROR`（TIMEOUT 由 supervisor 自己的墙钟复核：若 supervisor kill 了 worker → `STUDENT_TLE`；若 worker 自报 TIMEOUT 且 supervisor 记录到超时 → `STUDENT_TLE`；若 worker 自报 TIMEOUT 但 supervisor 未观测到超时 → `JUDGE_INFRA_ERROR`，防止 worker 谎报）。

### 3.4 规范化与比较规则（仅 Trusted 侧）

- canonical JSON：`json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, separators=(",", ":"))`（UTF-8 字节比较）；超长/不可序列化 → `RAISED(UnserializableActual)`/`RE`，不是 PASS。
- 比较器只在 supervisor 内运行：`actual_canonical == canonical(expected)` 才 PASS；任何异常/缺失/截断/多行/重复键/未知字段/JSON 解析失败 → 对应 STUDENT_ERROR 或 `JUDGE_INFRA_ERROR`，**永远不是 PASS**。
- `request_id` 只用于审计关联，不参与评分；worker 无法从 request 推出 expected。
- 一个 case 一次进程；禁止把多个 case 的 expected 顺序带入 worker（即使设计批量版也必须逐 case 独立请求，且 worker 不保存历史）。

### 3.5 可信侧的 fail-closed 决策表

| Worker 响应/观测 | 可信分类 | 教学语义 | 是否可改变 mastery |
| --- | --- | --- | --- |
| `COMPLETED` + actual == expected | `PASS` → `CORRECT` | 观测证据 | 可（CORRECT 规则） |
| `COMPLETED` + actual != expected | `WA` → `INCORRECT` | 学生错误 | 可（INCORRECT 规则） |
| `RAISED` | `RE` → `INCORRECT`/runtime | 学生运行错误 | 可（学生证据） |
| `SYNTAX_ERROR` / `IMPORT_ERROR` / `MISSING_FUNCTION` | `RE` | 学生提交问题 | 可（学生证据） |
| `TIMEOUT`（supervisor 复核成立） | `STUDENT_TLE` | 学生超时 | 可（学生证据；拿不到部分 case 证据时按 0） |
| `TIMEOUT`（复核不成立）/ `INFRA_ERROR` | `JUDGE_INFRA_ERROR` | **非学生证据** | **禁止改变 mastery/错误计数** |
| schema 未知字段/超长/截断/多行/重复键/request_id 不匹配 | `JUDGE_INFRA_ERROR` | 基础设施失败 | 禁止 |
| 沙箱不可用/启动自检失败（未执行） | `UNTRUSTED_CODE_EXECUTION_BLOCKED` | 能力被阻断 | 禁止 |
| 未知/缺失响应/worker 崩溃/被 kill | `JUDGE_INFRA_ERROR` | 基础设施失败 | 禁止 |

> 分类必须写入受限 judge 日志；Teacher 只看到聚合 code（如 `JUDGE_INFRA_ERROR` / `STUDENT_TLE` / `WRONG_ANSWER`），不看到 actual/args/expected 原文（§8）。

---

## 4. OS 隔离规格（bwrap；本机 LOCAL_PROBE 已验证属性）

### 4.1 环境事实（LOCAL_PROBE，2026-11-20T19:46Z，附录 A.1–A.2）

- `bwrap --version` = **bubblewrap 0.9.0**；内核 `Linux 6.17.13-2-pve x86_64`；宿主以 root 运行；`/usr/bin/python3` = Python 3.12.3；userns 可用（`--unshare-all` + `--uid/--gid` 成功）。
- 实测启动开销：`bwrap … python3 -c pass` ≈ **0.01 s/次**（附录 A.6）；单 case 进程化对 14 题×~8 cases 的离线判题可接受（计划值，PR1 再测）。

### 4.2 冻结启动命令（模板；路径占位为 supervisor 机密）

```bash
/usr/bin/bwrap \
  --unshare-all --die-with-parent --clearenv \
  --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin \
  --ro-bind <WORKER_DIR> /worker \
  --proc /proc --dev /dev --size 16777216 --tmpfs /tmp \
  --uid 65534 --gid 65534 --hostname m1b-worker \
  /usr/bin/python3 /worker/worker_runner.py
```

- `<WORKER_DIR>`： supervisor 为本次调用生成的只读目录，**只含** `worker_runner.py` 与 `solution.py`（synthetic/受控写入）；不 bind 任何 fixture/scoring/expected/DB/host 目录。
- 不使用 `--share-net`；不使用 `--dev-bind`；不使用 `--as-pid-1`（保留 bwrap reaper）；标准输入=protocol request，标准输出=protocol response（见 §4.3 的 fd 分离建议）。
- **P1-08（已关闭，PR1 实现同步）**：bwrap 0.9.0 要求 `--size` **紧跟**它所配置的 `--tmpfs`。本文早期版本写作 `--tmpfs /tmp --size 16777216` 会被 bwrap 拒绝；本机复测：错误顺序 `exit=1`，stderr 为 `bwrap: --size must be followed by --tmpfs`；正确顺序（上）`exit=0`，观测 `uid=65534, pid=2`。PR1 的 `m1_teacher/assessment/judge/sandbox.py` 已按 `--size` → `--tmpfs` 顺序构造命令（实现含注释 "bwrap 0.9 requires --size *before* the --tmpfs it configures"；见 `sandbox.py:353-356` 一带），worker/sandbox 测试全绿，故不存在旧命令形式。
- 宿主侧 `preexec_fn` 在 exec bwrap 前设置 rlimits（bwrap 0.9 本身无 `--rlimit-*` 选项，实测 `--help` 无 rlimit 段；使用 Python `resource.setrlimit`，bwrap 与 python3 继承）：

| 资源 | 限制 | 实测（LOCAL_PROBE） |
| --- | --- | --- |
| `RLIMIT_AS` | 256 MiB（可按 target 调整，不可 > 1 GiB） | `bytearray(400 MiB)` → `MemoryError`，exit=1，0.023s |
| `RLIMIT_CPU` | 2 s（软/硬相同；与 wall timeout 交叉校验） | 死循环 → 2.010s 被 SIGKILL（exit=137） |
| `RLIMIT_FSIZE` | 1 MiB | 写 5 MiB → `OSError: [Errno 27] File too large`，exit=1，0.028s |
| `RLIMIT_NOFILE` | 64 | 计划断言（未单独构造高 fd 探针） |
| `RLIMIT_NPROC` | 计划 32（**限制说明见 §4.4 风险**） | 本机未做 fork-bomb 探针（避免对宿主造成压力）；PR1 在专用测试容器执行并只测进程数上限 |
| wall-clock | `timeout_ms` + 500ms 宽限；`Popen` 独立 session | 1.0s 超时 → 进程组 `SIGKILL`，elapsed 1.004s，`leftover_pids=[]` |
| stdout/stderr | 各 ≤ 4096 bytes（截断） | worker side capture/截断；PR1 用 fd 重定向 + 有界 drain，避免内存放大 |

### 4.3 stdout/stderr 与协议通道分离（防伪造/防内存放大）

设计要求（PR1 实现）：

1. worker_runner 启动时先把协议通道 `dup` 到专用 fd（如 fd 3）并设置 `close-on-exec`；随后把 fd 1/2 重定向到 `/dev/null` 或"有界 drain"（最多保留 `stdout_limit/stderr_limit` 字节后丢弃），在调用 learner 代码前后保持重定向。
2. learner 的 `print`/`sys.stdout.write` 不能写进协议通道；即使 learner 直接 `os.write(3, forged_json)`，其内容也只能是额外字节/行；按冻结实现，worker 端要求**恰好一行**协议 JSON，**多行直接拒绝**（`WorkerProtocolError` → `JUDGE_INFRA_ERROR`），不做“取第一行”的宽松解析；伪造若满足 schema 也拿不到 expected（worker 内无 expected），只能得到 WA/RE，不能 PASS。
3. worker_runner 写完唯一一行 response 后立即 `os._exit(0)`，跳过 learner 可注册的 `atexit`/`finally`/`__del__`（LOCAL_PROBE 已证明旧实现因 atexit 覆写 result 文件而 PASS）。
4. supervisor 读取有界：response 上限 **128 KiB**（`protocol.py MAX_RESPONSE_BYTES`），**拒绝多行**（`parse_worker_response` 要求恰好一行非空 JSON），超限/多行/非法 UTF-8/未知字段 → `JUDGE_INFRA_ERROR`（实现已按 P2-1 同步）。
5. PR1 测试必须覆盖：learner 打印 `{"passed":true}`、`os.write(fd3, …)`、`atexit` 伪造、`sys.exit/os._exit` 篡改退出码 —— 均不得 PASS。

### 4.4 身份、文件系统、网络、生命周期的强制清单

| 维度 | 冻结要求 | LOCAL_PROBE 证据（附录 A.2） |
| --- | --- | --- |
| 用户/身份 | userns + `--uid 65534 --gid 65534`；无 setuid/caps；不 bind `/etc/sudoers`、不 bind host root。**P1-2（启动校验已实现）**：目标部署必须设置 `M1B_REQUIRE_NONROOT_SANDBOX=1`；此时 canary 校验宿主 euid≠0 且 uid_map 不映射到 0，不满足 → `SandboxUnavailable` → BLOCKED，绝不执行 learner code。默认不设该 env 时本地 synthetic 可用但记录 `LOCAL_ONLY` | 本机 bwrap 以 root 运行：`/proc/self/uid_map=65534 0 1`；默认 profile `non_root_principal_verified=False`、`profile=LOCAL_ONLY`；设置 `M1B_REQUIRE_NONROOT_SANDBOX=1` 时 `available()=False`（fail-closed）。**B1-04 本地仍 `PARTIAL`/`LOCAL_ONLY`，不得声称已满足** |
| 文件系统 | ro `/usr /lib /lib64 /bin`；ro worker dir；私有 tmpfs `/tmp`（size 限制）；**不 bind** `/root /home /etc /var /tmp` 宿主路径 | `/root`、`/etc`、`/home`、`/var/lib`、host sentinel 全部不可见/`FileNotFoundError`；`/usr` 写入 `OSError`；`/tmp` 可写 |
| 网络 | `--unshare-net`（无接口，仅 lo）；不提供 `/etc/resolv.conf`、无 DNS | `/proc/net/dev` 只有 lo；`socket.if_nameindex()==['lo']` |
| PID/IPC/UTS | `--unshare-pid --unshare-ipc --unshare-uts`；bwrap reaper + `--die-with-parent` | `pid=2`、hostname=`m1b-worker` |
| 生命周期 | 每 case 一进程；超时/异常均 kill 进程组；reap；fail-closed。**P1-1**：RLIMIT_CPU 按 `max(10, ceil(wall)+2)` 动态设置，wall timer 为主判据 | 1.0s 超时 → SIGKILL 进程组，leftover=[]；2.0s 死循环 → STUDENT_TLE；宿主 root/uid_map 见 P1-2 |
| 沙箱可用性 | supervisor 启动/每次调用前 canary 自检（uid、/root 不可见、/proc/net/dev 只有 lo、/usr 只读、python3 可跑、host sentinel 不可见、uid_map/python_version 记录）；任一失败 → **BLOCKED**。安全 CI 用 `M1B_REQUIRE_OS_SANDBOX=1` 强制不得 skip（P1-3） | 本机 canary 探针通过；不可用路径为设计断言（PR1 测试用 fake bwrap 失败路径）；安全 CI 期望 0 skipped |

**禁止的降级**：bwrap 不可用、userns 被禁、rlimit 设置失败、canary 失败、`/worker` 只读挂载失败、python3 不可执行 → 一律 `UNTRUSTED_CODE_EXECUTION_BLOCKED`；**绝不回退**到裸 `subprocess.run(sys.executable ...)`（即现有 A/B 行为），**绝不**跳过 isolation 继续判分。

### 4.5 已知限制（OS 层）

- bwrap 隔离不是内核 0day/侧信道防护；仅作为"判题信任边界"。
- `RLIMIT_NPROC` 对 uid 65534 在不同内核/映射下计数语义可能不同，需在目标部署环境验证；未完成前把 NPROC 作为**纵深防御**（pidns + wall timeout + 进程组 kill 是主控制），并在 PR1 记录实测。
- **P1-2（启动校验已实现）**：本机以 root 运行 bwrap（uid_map `65534 0 1`），默认 `LOCAL_ONLY`。目标部署必须使用非 root 服务账号（或单独评审的 setuid bwrap）并设置 `M1B_REQUIRE_NONROOT_SANDBOX=1`；canary 在启动时校验宿主 euid≠0、uid_map 不映射到 0，不满足则 fail-closed（`SandboxUnavailable` → BLOCKED，不执行 learner code）。本机设该 env 的负向验证通过；目标部署非 root 验收仍 `NOT_RUN`，B1-04 仍 `PARTIAL`。
- cgroup v2 内存/pid 限额可作为增强项，本设计不强依赖（bwrap 0.9 + rlimit 已覆盖基线）。

---

## 5. 默认策略与集成点（DESIGN + IMPLEMENTED）

### 5.1 能力策略（冻结建议）

| 策略 | 语义 | 默认 | 允许的调用方 |
| --- | --- | --- | --- |
| `UNTRUSTED_CODE_EXECUTION_BLOCKED` | 不执行 learner code；返回结构化 blocked；mastery 不变 | **是（所有对外/开放路径）** | 任意外部/产品 API、默认 CLI、默认 demo |
| `TRUSTED_FIXTURE_TEST_ONLY` | 仅限仓库内部自编 synthetic fixtures 的可信测试入口；显式 opt-in；仍建议在沙箱内运行 | 否 | 仓库测试/CI（显式参数或测试专用入口）、PR1 的 B1-05 证据 |
| `SANDBOXED_WORKER` | 经 B1-01..B1-04 独立验收 + 人类批准后才允许的 CODE 判题 | 否（PR1 之后也不默认对外） | 未来受控服务；仍需人工批准 |

- **MCQ / 静态 SHORT_ANSWER**：不执行 code、不需要 worker，保持现有行为（A `scorer.py:469-491`, `649+`；B 无 CODE 路径的复用逻辑同样不涉及 worker）。默认 blocked 只影响 CODE。
- **P1-01（已关闭）**：`trusted_fixture_only` **只能**来自可信构造/部署配置——即 `DeterministicScorer(...)` / `TrustedJudgeSupervisor(...)` 的构造参数（由仓库测试/CI 或受控部署代码显式传入），**绝不可**来自 AssessmentJob、请求体、响应体、`AssessmentItem` 字段、`result_id`、环境变量或任何调用方自报数据。数据路径无法改变策略；PR1 回归测试 `tests/m1_teacher/test_judge_supervisor.py::test_policy_cannot_be_enabled_from_caller_data_paths` 覆盖 item/response/result_id/env 绕过尝试，并断言 worker 从未被调用。
- **TRUSTED_FIXTURE_TEST_ONLY 的边界（P1-4 已修正）**：**只能**由可信构造/部署参数开启（`DeterministicScorer(..., trusted_fixture_only=True)` / `TrustedJudgeSupervisor(..., trusted_fixture_only=True)`），且必须由仓库测试/CI 使用自编 synthetic fixtures；**不可**由代码内环境变量、learner 输入、请求体、LLM 文本、AssessmentJob 或任何调用方自报数据开启。实现不读取任何环境变量开关。该模式不是安全策略，仅用于离线合成测试与 PR1 证据。

### 5.2 返回结构（blocked 与 infra error 的区分）

- A 线 `AssessmentScorer.score` 返回 `AssessmentResult`（契约枚举固定，见 `m1_teacher/contracts/types.py:47-53`, `683-715`）：
  - `status="EVAL_ERROR"`（不是学生错误）；
  - `score=None`；`scorer_id="m1b.blocked.scorer.v0"`（或统一 worker 版 id）；
  - `failure_reason="UNTRUSTED_CODE_EXECUTION_BLOCKED"`（或 `JUDGE_INFRA_ERROR`）；
  - `evidence_refs` 只含 `item:<id>` 等非敏感引用；不含 expected/hidden。
- B 线 `JudgeResult`：建议新增 `error="untrusted_blocked"`（或在 teacher 映射层转 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`）；`passed=False, cases_passed=0, cases_total=len(tests)`；**不执行 learner code**。
- Teacher/engine 接线（A）：`m1_teacher/session/engine.py:812-831`/`855-895` 的 EVAL_ERROR 分支直接生效：`ERROR` 事件、无 `apply_assessment`、无 mastery/error_counts 变化；测试必须断言 `AssessmentResult.passed=False` 且 snapshot revision/mastery/error_counts 不变。
- b-eval（B）：`harness.py:845-864` 将 `verdict.error` 标为 `tool_error`，`1080-1090` 的 payload 只记录 count；blocked 走同样的 tool_error 语义，不得计入学生失败。
- 事件/日志：blocked 只记录聚合 code（`UNTRUSTED_CODE_EXECUTION_BLOCKED`）与 item_id；不记录 request/args。

### 5.3 兼容性影响（M1-A / M1-offline 现有测试）

- A 线现有 PR4 的 CODE 测试（`tests/m1_teacher/test_assessment_scorer.py` 34 tests、`test_session_engine.py` 22、`test_session_transitions.py` 19 中包含 CODE 项/参考解路径）在默认 `BLOCKED` 下会得到 EVAL_ERROR/blocked；PR1 必须让这些"合成 fixtures 正确性"测试显式 opt-in `TRUSTED_FIXTURE_TEST_ONLY`（或注入 trusted worker fixture），并新增测试断言**无 opt-in 时 blocked**。这是"显式 opt-in"，不是弱化断言：参考解仍必须 CORRECT，错误解仍必须 WA，等等。
- B 线现有 `tests/m1_offline/test_cf_judge.py`（31 tests，LOCAL_PROBE 重跑 31 passed，附录 A.5）默认运行在 trusted fixtures 上；PR1 后同样需要显式 trusted-fixture 入口，并新增 blocked 默认测试。历史 365 / 536 数字保持各自冻结结论，**不合并、不相加**。
- CLI/demo/API（PR5）：默认调用 scored CODE → blocked；MCQ/SHORT 演示不受影响；demo 若需展示 CODE 教学，必须显式开启 trusted-fixture 模式并在输出中标注 `TRUSTED_FIXTURE_TEST_ONLY`。

---

## 6. 负例矩阵（B-Q1 / B1-02/03/04；全部 synthetic sentinel、沙箱允许后才执行）

> 约定：synthetic hidden expected 形如 `SENTINEL_DO_NOT_LEAK_<id>`（测试时随机生成，绝不使用真实 fixture expected）；
> **pre-fix 列**是本轮 LOCAL_PROBE 对现状的实测（LOCAL_PROBE，非 PR1 验收）；
> **post-fix 期望**是 PR1 实现后必须由独立 Reviewer 在安全测试容器中验证的目标。
> 所有攻击代码只为探针合成；PR1 在专用隔离环境重跑，绝不在宿主直跑真实恶意代码。

| ID | 攻击（synthetic learner code 行为） | pre-fix（现状 LOCAL_PROBE） | post-fix 期望分类 | 必须的证据（不泄漏 expected） |
| --- | --- | --- | --- | --- |
| N-01 | `inspect.stack()` 找 runner frame 的 `tests/payload`，读取 expected 并返回 | **A: CORRECT；B: passed=True**（实测） | **WA**（actual 不匹配）或 RE；worker 内无 expected 可读 | worker request/response JSON 不含 sentinel；worker 内存/挂载无 expected（PR1 test）；响应仅 actual/status |
| N-02 | 通过 `sys.argv[1]`/已知路径写 result 文件伪造 `cases[].passed` | **A: CORRECT；B: passed=True**（实测） | **WA/JUDGE_INFRA_ERROR**；协议中无 result 路径 | worker 无 argv 路径；协议响应无 passed；supervisor 忽略/拒绝伪造文件 |
| N-03 | 在协议 stdout 打印伪造 `{"passed":true}` / 伪造完整响应 | 父进程可能误读（旧 B/A 都信任 result） | **WA**（stdout 只作为 learner output excerpt，不进协议）或 INFRA | stdout/stderr 与协议 fd 分离；worker 响应单行 schema 校验 |
| N-04 | 读宿主私有目录 / hidden scoring spec / host sentinel | **A: hidden spec readable=true、/root 可列、host sentinel 可读；B: /root、sentinel 可读** | **FileNotFoundError/PermissionError → RE**；host 内容不可见 | sandbox canary + 文件系统断言；只记录布尔/异常类，不复制内容 |
| N-05 | 访问网卡/DNS/外网 socket | 现状可看到 `eth0`、`cni-podman0` | netns 无接口（仅 lo）；无 `/etc/resolv.conf`；连接失败 → RE | `/proc/net/dev` 只有 lo；`if_nameindex()` 仅 lo；不发起真实外网连接 |
| N-06 | fork/子进程逃逸、后台进程 | 现状无 pidns/进程组边界 | 1 次调用内子进程随 sandbox 销毁；不残留宿主进程 | `leftover_pids=[]`、pidns 断言、进程组 kill 日志 |
| N-07 | 死循环/超时 | 现状 A/B 有 wall timeout（可能正确分类） | **STUDENT_TLE**（supervisor 自己的墙钟复核；不是 PASS） | supervisor 计时 + 进程组 kill + 分类日志（不含代码内容） |
| N-08 | 输出巨量 stdout/stderr 制造内存/日志放大 | 旧 runner 捕获可能放大（A 使用 DEVNULL 但无 rlimit；B 截断 400） | 有界 drain/截断；内存/FSIZE 限额；不得影响宿主 | stdout_excerpt ≤ 上限；`RLIMIT_AS/FSIZE` 实测 |
| N-09 | 写 runner 源码 / `solution.py` / 只读挂载 | 旧可写 tempdir（solution 可被改） | **EROFS/失败 → RE/INFRA**；worker dir ro | ro-bind 断言；写入异常类 |
| N-10 | `atexit`/`sys.exit`/`os._exit` 篡改退出码或事后伪造 result | **A/B 实测 atexit 覆写 result → PASS** | response 单行 + `os._exit(0)` 跳过 atexit；退出码不作为 verdict；非法/缺失响应 → **JUDGE_INFRA_ERROR** | 退出码/响应字节记录；分类不是 PASS |
| N-11 | 资源耗尽（CPU/内存/fd/fsize/进程数） | 现状无 rlimit（仅 wall timeout） | CPU/AS/FSIZE/NOFILE/NPROC + wall timeout → **STUDENT_TLE 或 JUDGE_INFRA_ERROR**（按是否基础设施） | rlimit 配置与 exit/信号记录；不泄露代码 |
| N-12 | 请求注入 `expected`/`tests`/未知字段 | 设计层不存在（当前 A/B 反而主动发送 expected） | worker **拒绝** 请求未知字段 → INFRA；supervisor 不构造该字段 | request JSON schema 测试 + grep 无 `expected` |
| N-13 | 伪造 worker 响应（额外 `passed`/未知字段/超长/重复键/request_id 不匹配） | 旧父进程信任 result | **JUDGE_INFRA_ERROR**（fail-closed，绝不 PASS） | schema 校验日志/分类；无 mastery 变化 |
| N-14 | 返回不可序列化/NaN/Infinity/超大对象 | 旧 runner `canonical` 失败时 adversarially 可能伪造 passed（父级信任） | **RE**（RAISED/UNSERIALIZABLE），不是 PASS | worker 状态/异常类；canonical 校验日志 |
| N-15 | 隐藏内容经 failures/diagnostic/trace 泄漏 | **B: 3/3 sentinel 出现在 `JudgeResult.failures`；Teacher diagnostic 当前为 False（但 API 面存在）** | 端到端导出扫描 0 hit（sentinel 指纹 + hidden 文件 SHA-256） | B1-06 扫描报告（只含 hit count，不打印命中值） |
| N-16 | 跨 case 状态污染（worker 保存前 case 的 expected/结果） | 旧 runner 单进程跑全部 cases（expected 全部在内存） | 每 case 一进程；worker 不保存历史；request 独立 | 进程生命周期/请求隔离测试 |

**B1-02 专项（expected 隔离证明方法）**：supervisor 侧在每次调用前后检查：
`request_json`（无 sentinel/expected 字段）→ `worker cmdline`（无路径/expected）→ `env`（无 sentinel）→ mount view（仅 /worker、/usr、/tmp、/proc、/dev）→ `/proc/self/maps` 或 grep worker 内存（PR1 在测试环境）→ `stdout/stderr`、`response`、panic 日志、coredump 配置（关闭）→ 结果：0 命中。
**B1-03 专项（verdict 伪造证明方法）**：用"compromised worker"模拟器（非真实恶意代码）发送伪造 JSON（多形态：额外 passed、schema 错、超长、重复键、伪造 request_id）→ supervisor 必须全部 `JUDGE_INFRA_ERROR`；用正确 actual ≠ expected → WA；只有 actual == expected 才 PASS。
**B1-04 专项（confinement 证明）**：sandbox canary（uid/root 不可见/网络/ro/tmp）+ 资源耗尽 + fork/timeout + 进程组清理；全部输出 exit/分类摘要，不打印代码内容。

---

## 7. 正确性与可用性矩阵（B1-05；PR1 已实现，独立评审后 PARTIAL）

> 这些"正确性"必须在 **B1-02/03/04 协议 + OS 沙箱**下重新验证；当前只把两线既有 trusted-fixture 测试作为基线证据（LOCAL_PROBE 重跑 B 线 judge 测试：31 passed，附录 A.5），**不构成安全验收**。

### 7.1 14 份 CF 参考解与失败分类（目标矩阵）

B 线 fixture 14 题（公开 metadata；`fixtures/m1/cf/problems/*.json`）：
`cf_array_sum_even`, `cf_array_running_sum`, `cf_array_max_subarray`, `cf_tp_pair_sum_sorted`, `cf_tp_dedupe_sorted`, `cf_tp_is_palindrome`, `cf_bs_first_index`, `cf_sort_insertion`, `cf_bs_search_insert`, `cf_graph_count_components`, `cf_graph_bfs_dist`, `cf_dp_climb_stairs`, `cf_dp_coin_change`, `cf_dp_lcs`。

| 用例类型 | 期望结果 | 判定方 | 目标证据（PR1） |
| --- | --- | --- | --- |
| 14 份 reference solution | 全部 `PASS`（hidden cases 全过） | supervisor 对 worker actual 比较 | 14/14 逐题结果 JSON（只含 problem_id/pass/case counts/耗时） |
| 错误解（wrong answer） | `WA` → INCORRECT（非 PASS） | supervisor | 每类错误解 1 例 + failure_kind |
| 语法错误 | `SYNTAX_ERROR` → RE | worker 观测/可信映射 | result 分类 |
| 运行异常 | `RAISED` → RE | worker 观测 | result 分类 |
| 死循环 | `STUDENT_TLE`（supervisor 墙钟） | supervisor | 超时/kill 记录 |
| 边界题（空数组/单元素/重复元素等） | 参考解 PASS；错误边界解 WA | supervisor | 边界 case 结果（case_index + pass） |
| 同题同输入 deterministic | 两次运行逐字段相同 | supervisor | 两次 result JSON 对比（SHA-256 相同） |
| 判题错误（infra/blocked）不改 mastery | snapshot/mastery/errors 不变 | A engine EVAL_ERROR 分支；B tool_error | A: `_handle_eval_error`；B: harness tool_error；测试断言 |

### 7.2 可用性/成本（PLAN；PR1 实测补数）

- worker 启动：LOCAL_PROBE `bwrap … python3 -c pass` ≈ 0.01s/次；加 Python 启动估计每 case ~30–60ms；14 题 × 112 hidden cases ≈ 3–7s（单次全量判题，计划值）。
- supervisor 侧比较与 schema 校验 < 1ms/case；无网络/无外部依赖安装（仅宿主已有 python3/bwrap）。
- 限制：沙箱不可用环境（无 userns/setuid bwrap）→ 全部 CODE blocked，不影响 MCQ/SHORT 教学与既有合成 demo；这是**有意的可用性降级**（安全优先）。

### 7.3 与历史数字的关系

- M1-A 历史 536 tests、M1-offline 历史 365 tests 是**各自分支冻结结论**，不得相加称"统一 901 tests"。
- 本 PR1 是 B-NEXT 的新实现（Judge Worker + 默认 blocked + 协议 + 泄漏清理），其正确性证据必须在新分支重新生成，独立 Reviewer 复跑；历史数字仅作基线参考。
- 当前证据类别：本文 §7 为 `DESIGN_ONLY`/`PLAN`；`trusted-fixture` 基线是 `LOCAL_PROBE` 复跑（31 passed），不是 B1-05 PASS。

---

## 8. 隐藏内容不泄漏规格（B1-06）

### 8.1 允许 vs 禁止的 Teacher 可见内容

| 通道 | 允许 | 禁止 |
| --- | --- | --- |
| `DiagnosticResult`（A/B） | 聚合 error_code、confidence、status、失败分类计数、公开 hint rationale | expected/hidden args/expected_repr/args_repr/scoring spec 内容/路径/hidden 用例正文 |
| `TeacherAction` / session events | 公开 teaching content、node ids、hint 级别、行动理由 | 同上 |
| trace JSONL / JSON 导出 / API 响应 | event ids、step、聚合 counts、耗时、分类、blocked 标记 | 同上 |
| 教师可见日志/异常消息 | 分类、case_index、聚合计数 | expected 原文、hidden 输入原文、scoring 文件内容 |
| 受限 judge 日志（不可 teacher 可见） | case_index、分类、耗时、资源摘要、hidden 文件哈希 | 也不得写 expected 原文；只能写 firewalled 的 hash/count |
| worker request/response | §3 字段 | 任何 expected/verdict 字段 |

### 8.2 现有泄漏面清单（SOURCE_INSPECTED + LOCAL_PROBE）

| 面 | 现状 | 证据 | PR1 处理 |
| --- | --- | --- | --- |
| B `JudgeResult.failures` | 含 `args=... expected=... actual=...` | `judge.py:121-122`, `407-412`；LOCAL_PROBE 3/3 sentinel | 移除原文，改为 `case_index + failure_kind`（或纯 hash）；Teacher 侧完全不可见 |
| B `CFTeacher` fatal detail | `failures[0]` 仅 fatal 消息（无 expected） | `teacher.py:283`；LOCAL_PROBE sentinel 在 diagnosis 中 False | 仍建议脱敏/只保留分类 |
| B b-eval trace | 只记录 `judge_failure_count` | `harness.py:1038`, `1061` | 保持；新增扫描断言 |
| A `AssessmentResult.failure_reason` | CODE 仅 `CASES_FAILED:x/y`/`TIMEOUT` 等，无 expected | `scorer.py:609-647` | 保持；新增扫描 |
| A `evidence_refs` | `item:<id>`、`spec-sha256:<hash>`（哈希非内容） | `scorer.py` `_result` 区域 | 保持（哈希可作为审计，非泄漏） |
| A/B worker 日志/cwd | 旧实现 cwd 泄漏（`/tmp/m1a_scorer_*`/`/tmp/m1_cf_judge_*`） | LOCAL_PROBE facts | PR1 不向 Teacher 暴露 cwd；受限日志仅内部 |
| A/B worker stdout | 旧实现 stdout 丢弃/截断，不进入 Teacher | local probe | 保持为不可信 excerpt，不默认教师可见 |

### 8.3 运行时导出扫描规格（不只 git AST）

PR1 必须新增端到端扫描测试（建议 `tests/.../test_judge_leakage_scan.py`）：

1. 构造 synthetic sentinel：每次测试运行生成随机 `SENTINEL_DO_NOT_LEAK_<16 hex>` 作为 hidden expected（fixture 仅存在于测试沙箱/临时目录）；
2. 走完整闭环：judge/worker → assessment → session/teacher → trace/JSON 导出 → CLI/API 响应（A/B 各自路径）；
3. 收集所有"teacher 可见"导出（包括 `DiagnosticResult.to_dict()`、`TeachingAction`、trace events、`AssessmentResult.to_dict()`、b-eval trace payload、异常/日志 buffer），序列化后：
   - 子串搜索 sentinel（含 base64/JSON-escaped 变体）；
   - 搜索 hidden 文件原始字节的 SHA-256（hex/字符串形式）；
   - 搜索 `scoring/` 路径与 hidden 文件基名；
4. 断言 hit = 0；命中时报告仅输出 surface 名称与计数，不打印命中值（避免二次泄漏）。
5. 对 `JUDGE_INFRA_ERROR`/`UNTRUSTED_CODE_EXECUTION_BLOCKED`/`STUDENT_TLE` 各状态重复扫描；对 worker request/response 单独扫描（期望 0）。
6. 扫描范围必须覆盖**运行时**（而非 git AST）；现有 A `tests/m1_teacher/test_assessment_scorer.py:484+` 的静态 source scan 仅作为补充，不满足 B-Q5。

---

## 9. 验收映射（TEST_EVIDENCE_MATRIX B1-01..B1-06）

> 本表只做"设计 → 实现后测试/证据"的映射；当前状态全部 `NOT_RUN`（本文 `DESIGN_ONLY`/`LOCAL_PROBE`）。
> PR1 = Implementer-Judge + Implementer-OS，评审 = Reviewer-Security（与 A 线安全 Reviewer 职责分离）。

| 验收项 | 目标（来自矩阵） | 本文设计落点 | PR1 交付（计划） | 当前状态 |
| --- | --- | --- | --- | --- |
| B1-01 Untrusted code blocked | 在 worker 隔离前，CODE 对外默认硬失败且不执行 learner code | §5（默认策略）、§3.5、§4.4 fail-closed | 默认 blocked 单测（A/B）：不 spawn worker、返回 blocked、mastery 不变；CLI/API 默认路径集成测试 | `NOT_RUN`（DESIGN_ONLY） |
| B1-02 Hidden expected isolation | expected 绝不进入 worker 内存/stdin/挂载/env/args/logs | §3.2/3.3、§4.2、§6 N-01/N-04/N-12/N-16、§8 | worker 协议隔离测试 + sentinel 扫描 + 挂载/请求检查 + canary | `NOT_RUN`（LOCAL_PROBE 证明旧实现泄漏） |
| B1-03 Result forgery | 不可信 worker 不能通过写 result/output JSON 伪造 PASS | §3.3/3.4/3.5、§6 N-02/N-03/N-09/N-10/N-13 | 伪造矩阵测试（额外 passed、伪协议、atexit、未知字段、超长、重复键）→ 全部非 PASS/INFRA | `NOT_RUN`（LOCAL_PROBE 证明旧实现可伪造） |
| B1-04 Judge confinement | 无网络/host secret 读取/子进程逃逸/资源耗尽 | §4（OS 规格）、§6 N-04/N-05/N-06/N-08/N-11 | sandbox canary + FS/net/pid/rlimit/timeout 测试；进程组清理；无外网连接 | `NOT_RUN`（LOCAL_PROBE 验证 bwrap 属性） |
| B1-05 Judge correctness | 14 参考解通过；错误/超时/异常独立分类；确定性；延迟成本；错误不改 mastery | §7、§3.5 | 14/14 reference + wrong/RE/TLE/boundary/determinism/perf 证据；A 线 mastery 不变性 | `NOT_RUN`（trusted-fixture 基线 LOCAL_PROBE 31 passed，仅参考） |
| B1-06 Hidden leakage scan | Teacher messages/traces/exports/diagnostic 失败无 expected/hidden 内容 | §8 | 端到端导出扫描（sentinel + hidden SHA-256 + `scoring/` 路径）；失败字符串脱敏测试 | `NOT_RUN`（LOCAL_PROBE 证明 B failures 泄漏面） |

**门禁语义**：B1-01 是"真实用户 CODE 前 BLOCKER"；B1-02/03/04/06 为安全必要条件；B1-05 为可用性/正确性必要条件。只有六项在**同一冻结 SHA** 上由独立 Reviewer 复跑通过 + 人类批准，才允许把 CODE 从 `BLOCKED` 迁到 `SANDBOXED_WORKER`；迁移本身不属于本设计 PR。

---

## 10. 非目标、保留与未决问题

### 10.1 非目标（本 PR 明确不做）

- 本文件不是实现记录（PR1 实现见 `docs/M1_B_JUDGE_IMPLEMENTATION.md`）；不重复维护 worker/sandbox 代码，也不替代独立安全验收。
- 不做真实网络/真实 Provider/真实 Key、不访问真实招聘网站/简历；不运行真实恶意代码；负例只在安全测试容器中使用 synthetic sentinel。
- 不修改 M0 保护路径（`src/autoteacher_m0/`、security/bridge、`config/g*`、`scripts/g4*`、LiveGate/费用账本）；不复用 A 线真实 Provider 信任/密钥路径。
- 不把 OS 沙箱当作"学习效度"或"评分不可被恶意输入破坏"的证明；不声称真实用户 CODE 可开放。
- 不做 cgroup/内核级 0day 防护；不做多租户 auth（M1-A 还没有真实鉴权，不能自称多租户安全）。
- 不合并/不重新计算两线历史 suite 数字（536/365 保持各自冻结结论；不声称"901 tests"）。

### 10.2 保留风险（即使 PR1 实现完成仍需记录）

- bwrap/内核 0day、侧信道（时间/进程名/文件缓存）、宿主 root 权限本身的风险；需要部署级隔离与补丁策略。
- 同机多租户/共享宿主的 DoS 成本（每个 case 一进程的启动与调度开销）；PR1 需在目标部署测延迟与并发上限。
- `RLIMIT_NPROC` 与 userns uid 映射的跨内核差异；cgroup 缺失时的资源隔离"尽力而为"性质。
- Worker 语言固定为 Python 时的解释器/库漏洞面；未来多语言 worker 需单独评估。
- 受限 judge 日志仍可能被运维人员查看；建议加密/最小保留/hash-only。
- 真实用户 CODE 开放 = 新工作项：需要人类批准、部署环境验收、另一次独立验收（不在本 PR）。
- `LOCAL_PROBE` 只在本机（Linux 6.17 + bwrap 0.9）执行；目标 CI/生产环境是否允许 userns/bwrap 尚未验证（`NOT_RUN`）。
- **P2-6（已记录，残余风险）**：learner 代码可通过 `sys.modules["__main__"]._PROTOCOL_FD` 与栈帧读取 request_id 后伪造一行合法 observation（含 INFRA/RAISED）；因 worker 内无 expected，伪造最多造成 `WA/RE/INFRA_ERROR`，**不能造成 PASS**，且属于 fail-closed 可接受面。长期可把 learner 执行放入独立子进程/协议 fd 不继承/learner 不可读 nonce 进一步降低。
- **P2-8（已记录，低风险）**：沙箱内 `/proc/1/cmdline` 可能暴露宿主 worker 临时目录路径（`/tmp/m1b_judge_worker_*`）；该目录未挂载、不可访问且不含 expected，接受为低风险。
- **P2-7（部分缓解）**：P1-1 修复新增 wall/CPU 超时分类的单测；`RLIMIT_NPROC=32` 的套件级 fork 压力测试仍未加入（需要受控安全测试环境，避免对宿主造成压力），以独立探针/部署验收为主。
- **P2-3（部分缓解）**：worker 运行现固定传入 `PYTHONHASHSEED=0`/`PYTHONDONTWRITEBYTECODE=1`；解释器路径固定为 `/usr/bin/python3`，但尚无版本 pin 校验（跨部署版本一致性未验证）。

### 10.3 待独立 Reviewer 静态预审的问题（请逐条给意见）

1. 是否同意"每 case 一 worker 进程"的冻结协议（vs 批量 worker）？批量的性能收益 vs expected 累积/超时隔离/取证复杂度，本文建议 v1 单 case。
2. 是否同意 blocked 返回 `EVAL_ERROR`+`failure_reason="UNTRUSTED_CODE_EXECUTION_BLOCKED"`（A 契约无法新增 status）？是否需要在 `AssessmentResult.dimensions` 加 `blocked=True`（假设可加 dimensions 键）或另设 `AssessorOutcome` envelope？
3. `stdout_excerpt` 是否需要教师可见？本文建议**默认不进入 Teacher messages/traces**（仅受限 judge 日志，≤512B，且标记 untrusted）。
4. B 线 `JudgeResult` 是否直接加 `error="untrusted_blocked"`，还是通过 teacher 映射层统一为 `EVAL_ERROR`？需与 A 线合同收敛（B0）对齐。
5. rlimit 中 `RLIMIT_AS=256MiB` 是否足够运行 14 题参考解/学习者代码（例如 DP 题大输入）；PR1 需按 fixture 最大内存实测后定值（当前是计划值）。
6. 是否接受"bwrap 不可用 → 全部 CODE blocked"的可用性降级？是否有需要保留 trusted-fixture-only 给 CI 的豁免边界（本文建议仅仓库内部显式 opt-in，不可由外部开启）。
7. B1-06 的扫描是否必须包含 A 线 trace/JSON 导出与 B 线 b-eval trace 两条路径？本文要求两条都扫，且扫描必须运行时而非仅 AST。

---

## 附录 A — LOCAL_PROBE 记录（synthetic；脚本不提交；2026-11-20 UTC）

> 探针目录：`/tmp/m1b_probe/`（仅临时；`logs/*.json` 为原始输出；下列为摘要）。
> 全部内容为自编 synthetic sentinel 与合成探针代码；**未发起任何外部网络连接**；未复制 hidden fixture 内容（仅记录布尔可读性）。
> 探针脚本/日志 SHA-256（2026-11-20T19:5xZ）：
> - `run_sandbox_suite.py` `002576ce3ec5bcd8e23ae70aed8e148d816849a7a2c5fd6d5c8aeac6cee1309b`
> - `old_impl_probes.py` `a7dd5ad2896e40778acbf318fc0d8119cd241dad4a5d0fc2cbd4a8bc9e19f82b`
> - `sandbox/basic_probe.py` `11eb4e4b91b331f39ca85a9637b6cd23704ed08871fdcd58bd710dc76bc04c47`
> - `sandbox_worker/worker_runner.py` `3fffee33a0d7d3281bd897765807af48a015f45a95781030eb56ccf81dead8ef`
> - `logs/sandbox_suite.json` `ffa9783d7e7c0fc7e1e9537599d8bb92a388a81f2d32e49c0b2f2eb280e4e0bd`
> - `logs/old_impl_probes.json` `2f9d0d36fb25f1cc12d6565e8383673a3479790422bfeca6755bdba107e107b9`
> - `logs/sandbox_basic.json` `e628bbd85782c9904acd0fd0dc037e41381ecb2e1728311d469412b7ae9501a0`
> - `logs/bwrap_latency.log` `1106e717213c59a53b03ebe0b068170089d4e09e048caa538491002c5efeb1f7`

### A.1 环境

```
2026-11-20T19:46:23Z
Linux 6.17.13-2-pve x86_64
bubblewrap 0.9.0
/usr/bin/python3 = Python 3.12.3
host runs as uid=0(root)
```

### A.2 Sandbox 属性（命令见 §4.2 模板；worker 只读目录=`/tmp/m1b_probe/sandbox`，输出入 `logs/sandbox_basic.json`）

```json
{"uid":65534,"gid":65534,"pid":2,"hostname":"m1b-worker",
 "root_entries":["bin","dev","lib","lib64","probe","proc","tmp","usr"],
 "env_keys":["LC_CTYPE","PWD"],
 "interfaces":["lo"],
 "probe_paths":{"/root":false,"/etc":false,"/home":false,"/var/lib":false,
   "/tmp/m1b_probe":false,
   "/tmp/m1b_probe/host_private/SENTINEL_EXPECTED.txt":false},
 "sandbox_private_sentinel":{"error":"FileNotFoundError"},
 "usr_write":"OSError","tmp_write":"OK"}
```

结论：非 root、独立 pid/uts、最小 rootfs、host 私有路径不可见、host sentinel 不可读、/usr 只读、/tmp 私有可写、网络仅 lo。
（`/proc/net/dev` 输出只有 `lo:` 行；`socket.if_nameindex()` 仅 `lo`。）

### A.3 资源与超时

| 探针 | 命令要点 | 实测 |
| --- | --- | --- |
| RLIMIT_AS 256MiB | `resource.setrlimit` preexec + bwrap python | `MemoryError`，exit=1，0.023s |
| RLIMIT_FSIZE 1MiB | 写 5MiB | `OSError: [Errno 27] File too large`，exit=1，0.028s |
| RLIMIT_CPU 2s | 死循环 | 2.010s 被 SIGKILL，exit=137 |
| wall timeout 1s + 进程组 kill | `Popen(start_new_session)` + `killpg` | elapsed 1.004s，returncode=-9，`leftover_pids=[]` |
| bwrap 启动开销 | `bwrap … python3 -c pass` ×3 | 0.01s/次 |

### A.4 旧实现脆弱性（A @4706250 / B @290c577；synthetic sentinel）

| 探针 | 结果（摘要） |
| --- | --- |
| A_expected_stack_leak | `status=CORRECT, score=1.0`（学习者从调用栈读 expected 并返回） |
| A_result_file_forgery | `status=CORRECT, score=1.0`（atexit 覆写 result 文件） |
| A_host_escape | facts: `uid=0, interfaces=["cni-podman0","eth0","lo"], root_visible=true, root_listable=true, hidden_scoring_spec_readable=true, host_sentinel_readable=true, cwd=/tmp/m1a_scorer_*` |
| B_expected_stack_leak | `passed=true, cases_passed=3/3` |
| B_result_file_forgery | `passed=true, cases_passed=3/3` |
| B_expected_in_judgeresult_failures | `sentinel_present_in_failures=["SENTINEL_DO_NOT_LEAK_B1","B2","B3"]`（3/3） |
| B_host_escape | facts: `uid=0, interfaces=["cni-podman0","eth0","lo"], root_visible=true, root_listable=true, host_sentinel_readable=true, cwd=/tmp/m1_cf_judge_*` |
| B_teacher_diagnosis_sentinel_reachable | `sentinel_in_teacher_visible_diagnosis=false`（当前 teacher 只聚合 explanation；但 `JudgeResult.failures` API 仍泄漏） |

### A.5 既有测试基线复跑（LOCAL_PROBE，非验收）

- B 线 `pytest tests/m1_offline/test_cf_judge.py -q` → **31 passed in 1.61s**（trusted-fixture 基线，不代表 B1-05 安全验收）。
- A 线 `pytest tests/m1_teacher/test_assessment_scorer.py::test_eval_error_never_mutates_mastery tests/m1_teacher/test_session_engine.py::test_raising_scorer_is_eval_error_and_never_evidence tests/m1_teacher/test_session_engine.py::test_eval_error_preserves_existing_snapshot_exactly -q` → **3 passed in 0.38s**（"judge/infra 错误不改 mastery" 现有控制）。
- 本文件不声称 536/365 合并，也不把上述复跑当 PR1 验收。

### A.6 拟议协议 prototype 探针（`m1b.judge.worker.v1` 形态；synthetic）

worker 只读目录 `/tmp/m1b_probe/sandbox_worker`，`worker_runner.py` 实现 §3 协议（stdout 分离、严格字段、无 expected）。

| 探针 | 结果 |
| --- | --- |
| 正确 solution + expected=2（expected 只在 supervisor 内存） | `PASS` |
| 错误 solution | `WA` |
| learner print 伪 `{"passed": true, "verdict": "PASS"}` | stdout 进入 excerpt；判分 `WA`（非 PASS） |
| learner 读 host `/root`/host 私有目录/网卡 | actual facts: `uid=65534, interfaces=["lo"], root_visible=false, host_private_visible=false, etc_visible=false`；判分 `WA` |
| 伪造 worker 响应含额外 `passed:true` | supervisor → `JUDGE_INFRA_ERROR`（拒绝未知字段） |
| 请求中注入 `expected` 字段 | worker `INFRA_ERROR(REQUEST_UNKNOWN_FIELD)` → supervisor `JUDGE_INFRA_ERROR` |

> 该 prototype 是**设计可行性探针**（脚本在 `/tmp`，不入库），不是 PR1 实现；其 `stdout_excerpt` 采用内存 StringIO（设计已要求改为有界 drain/重定向，见 §4.3）。

---

## 附录 B — 协议示例（synthetic，无 hidden 内容）

**请求（只含单 case 输入）**

```json
{"schema_version":"m1b.judge.worker.v1","request_id":"00112233445566aabbccddeeff00112233",
 "function_name":"probe_fn","args":[[1,2,3],2],"timeout_ms":1500,
 "stdout_limit":512,"stderr_limit":512}
```

**响应（COMPLETED，无 verdict）**

```json
{"schema_version":"m1b.judge.worker.v1","request_id":"00112233445566aabbccddeeff00112233",
 "status":"COMPLETED","actual_canonical":"2","exception_type":null,
 "stdout_excerpt":"","stderr_excerpt":""}
```

**响应（学生语法错误）**

```json
{"schema_version":"m1b.judge.worker.v1","request_id":"00112233445566aabbccddeeff00112233",
 "status":"SYNTAX_ERROR","actual_canonical":null,"exception_type":null,
 "stdout_excerpt":"","stderr_excerpt":""}
```

**被 supervisor 拒绝的伪造响应（示例）**

```json
{"schema_version":"m1b.judge.worker.v1","request_id":"00112233445566aabbccddeeff00112233",
 "status":"COMPLETED","actual_canonical":"2","passed":true}
```

→ `JUDGE_INFRA_ERROR(unknown-fields)`；`passed` 字段在协议中不存在，绝不采信。

---

## 附录 C — 威胁 → 控制 → 验收追踪矩阵

| 威胁 | 控制（§） | 验收（B1/测试） |
| --- | --- | --- |
| T1 学习者读 expected（调用栈/进程内存） | 协议不含 expected；worker 只收 args；expected 仅 supervisor 内存（§3） | B1-02 / N-01/N-12 |
| T2 学习者伪造 result/response 产生 PASS | 无 result 文件/无 argv 路径；worker 响应无 verdict；supervisor 比较 actual==expected（§3.3/3.4） | B1-03 / N-02/N-03/N-13 |
| T3 学习者读取宿主敏感文件/DB/fixture | 最小 ro rootfs + 私有 tmpfs + 非 root + 不 bind 敏感目录（§4） | B1-02/04 / N-04 |
| T4 学习者访问网络/DNS | netns none（仅 lo）、无 /etc（§4） | B1-04 / N-05 |
| T5 学习者 fork/逃逸/残留进程 | pidns + die-with-parent + 进程组 kill + wall timeout（§4.3/4.4） | B1-04 / N-06 |
| T6 资源耗尽（CPU/内存/fd/fsize/输出） | rlimits + wall timeout + 有界输出（§4.2/4.3） | B1-04 / N-08/N-11 |
| T7 判题基础设施错误被当学生错误 | 可信分类表（§3.5）+ BLOCKED/INFRA 不写 mastery（§5.2） | B1-05 / A 线 3 个既有测试 + PR1 |
| T8 hidden expected 经 failures/日志/trace 泄漏 | 泄漏面清理 + 运行时导出扫描（§8） | B1-06 / N-15 |
| T9 无沙箱时静默降级执行 | 默认 BLOCKED + canary fail-closed + 禁止裸 subprocess 回退（§4.4/§5） | B1-01 / PR1 blocked 测试 |
| T10 worker 被攻陷后谎报 status | 不可信响应全部 schema 校验；TIMEOUT 由 supervisor 时钟复核；只有 expected 匹配才 PASS（§3.4/3.5） | B1-03/N-13；B1-05 分类测试 |

---

## 附录 D — 独立 Reviewer 静态预审清单（PR1 动工前）

- [ ] 是否同意 §1.3 六条安全不变量作为 PR1 验收不变量？
- [ ] 是否同意 §3 协议中 expected **永不**进入 worker 的字段集、且响应**没有** verdict/passed？
- [ ] 是否同意 §3.4 仅 supervisor 比较、worker actual 不可信、TIMEOUT/INFRA 分类规则？
- [ ] 是否同意 §4 的 bwrap 拓扑、uid/网络/只读/私有 tmpfs/rlimit/进程组清理与 fail-closed 规则？
- [ ] 是否同意 §5 默认 `UNTRUSTED_CODE_EXECUTION_BLOCKED` 及 trusted-fixture opt-in 只限仓库内部？
- [ ] §6 负例矩阵是否覆盖 B-Q1 全部要求（读 expected/伪造 passed/读 host/网络/fork/超时/输出伪造/写 runner/异常覆盖）？是否还需要补充项？
- [ ] §7 正确性矩阵是否接受"在 OS 沙箱+可信协议下重新验证 14 题"，且历史 suite 数字不合并？
- [ ] §8 泄漏规格是否接受"运行时导出扫描 + failures 原文移除"为 B1-06 的唯一通过方式？
- [ ] 是否确认本文只含 synthetic sentinel/公开 metadata，没有真实 hidden fixture 内容或真实个人数据？
- [ ] 是否确认 PR1 不得修改 M0 保护路径/不得联网/不得使用真实 Key，且 B1 是真实用户 CODE 的 BLOCKER？

---

## 变更记录

| 版本 | 日期 | 变更 |
| --- | --- | --- |
| v0.1 | 2026-11-20 | 初版 DESIGN_ONLY：资产/信任域、A/B 根因证据、冻结 worker 协议 v1、bwrap OS 规格与 LOCAL_PROBE、默认 BLOCKED 策略、负例矩阵、正确性/泄漏规格、B1-01..06 验收映射、非目标与 Reviewer 清单 |
| v0.2 | 2026-11-20 | PR1 实现回填：P1-08 CLOSED（`--size` 必须在 `--tmpfs` 前，给出实测 exit 1/exit 0 与 sandbox.py 同步证据）；P1-01 CLOSED（opt-in 仅构造/部署配置，不可由数据路径/请求/env 绕过）；P2-05 修正 request_id 正则示例；P2-06 统一协议通道为专用 fd（dup(1)）+ fd1/2 重定向 + `os._exit(0)` 表述 |
| v0.3 | 2026-11-20 | 独立评审 PASS_WITH_ACTIONS 回填：P1-4 CLOSED（trusted fixture 仅可信构造/部署参数可开启；历史开启方式说明已移除，实现不读取任何环境变量开关）；P2-1（§4.3 上限 128 KiB、拒绝多行）；P2-2（状态改为 DESIGN + IMPLEMENTED_LOCAL_VERIFIED）；P1-1/P1-2 说明同步（CPU/wall TLE 与 host 非 root principal LOCAL_ONLY） |
| v0.4 | 2026-11-20 | 复核附录回填：P1-2 启动校验实现（`M1B_REQUIRE_NONROOT_SANDBOX=1` canary fail-closed，默认 LOCAL_ONLY）；P1-3 CI 接线脚本 `scripts/m1b/run_safety_ci.sh`（.github 仍 NOT_CONFIGURED/NOT_RUN）；§3.1 首行规则与实现一致；版本号/changelog 对齐 |
| v0.5 | 2026-11-21 | 文档精度（final review P2-3）：清理历史 changelog 中不准确的开启方式引用；语义不变——trusted fixture 仅可信构造/部署参数可开启，实现不读取环境变量开关；P1-4 关闭状态不变 |
