# M1-B / B-PR1 — Untrusted Execution Worker、bwrap 隔离与严格 Worker 协议（实现记录）

- 工作树：`/root/m1b/pr1-sandbox`，分支 `b-next/pr1-untrusted-worker`
- 基线：`4706250`（`work/m1a-mvp`），先 merge `b-next/pr1-judge-fixtures`（`0fd3ed4`，认证语料）
- 设计依据：`docs/M1_B_THREAT_MODEL_JUDGE.md`（b-cf，§3 协议 / §4 bwrap 规格 / §6 负例矩阵 / §8 泄漏规格）
- 状态：**IMPLEMENTED + LOCAL/MOCK 证据**。独立评审（`docs/M1_B_PR1_REVIEW.md`）后已修复 P1-1（默认超时 TLE 误分类）/P1-2（宿主非 root principal 报告）/P1-3（安全 CI 不得跳过）；B1-04 仍为 `PARTIAL`（本机 root 运行 bwrap，`LOCAL_ONLY`；目标部署须设 `M1B_REQUIRE_NONROOT_SANDBOX=1`），最终 PASS 仍须独立 Reviewer 在冻结 SHA 上复跑 + 人类批准；本文件不声称安全验收通过，也不开启对真实用户 CODE 的执行。
- 默认策略不变：真实 learner CODE 仍为 `UNTRUSTED_CODE_EXECUTION_BLOCKED`（本 PR 只提供被集成方 b-cf 的 supervisor 调用的 worker 组件；supervisor 集成未在本 PR 内）。

## 1. 范围与文件

本 PR 只新增/修改以下文件（其余文件未动）：

| 文件 | 作用 |
| --- | --- |
| `m1_teacher/assessment/judge/__init__.py` | 包骨架，导出 protocol/sandbox/worker 公共名称 |
| `m1_teacher/assessment/judge/protocol.py` | 冻结协议常量、`WorkerObservation`、严格 request 构建/校验、严格 response 解析、canonical JSON、fail-closed 策略码 |
| `m1_teacher/assessment/judge/sandbox.py` | `BwrapSandbox`：冻结 bwrap 命令、canary 自检、rlimits、有界输出读取、墙钟超时与进程组 SIGKILL |
| `m1_teacher/assessment/judge/worker.py` | `UntrustedExecutionWorker.run_case(...)`：每 case 一个私有目录/进程，只返回观测，不接收 expected |
| `m1_teacher/assessment/judge/worker_runner.py` | 沙箱内单 case runner：stdin 单请求、import solution 一次、协议 fd 分离、单行响应后 `os._exit(0)` |
| `tests/m1_teacher/test_judge_sandbox.py` | bwrap 命令/能效/隔离/资源/超时/canary/fail-closed 测试 |
| `tests/m1_teacher/test_judge_worker.py` | 请求最小化、协议严格解析、伪造响应 fail-closed、真实参考解观测、确定性、清理 |
| `tests/m1_teacher/test_judge_negatives.py` | judgefix 负例与攻击模板矩阵（全部仅在沙箱内执行） |
| `tests/m1_teacher/test_judge_fixture_integrity.py`（更新） | 校验拆分后的 attack schema（`expected_blocked` / `expected_observation`） |
| `fixtures/m1_teacher/judge/sentinels/sentinels.json`（语义修正） | `write_runner_source` 拆分为 RO-bind 与 ephemeral tmpfs 两类 |
| `fixtures/m1_teacher/judge/README.md`（更新） | 记录 attack schema 与两类写文件语义 |
| `docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md` | 本文件 |

未修改：`m1_teacher/assessment/scorer.py`、`session/engine.py`、`contracts/*`、既有域 fixture、M0/security/bridge/scripts/g4、LiveGate。无网络、无真实 Key、全部合成数据。

## 2. 信任边界与数据流

```
Trusted (supervisor, b-cf)                      Untrusted (worker, 本 PR)
─────────────────────────────                   ─────────────────────────────────────────
hidden expected / tests / scoring spec          stdin: 单 case {schema_version, request_id,
canonical comparator / verdict                    function_name, args, timeout_ms, limits}
受限 judge 日志 / 学生证据判定                     bwrap: user/pid/net/ipc/uts namespaces,
                                                 uid/gid 65534, ro minimal rootfs,
                                                 private tmpfs, rlimits, wall clock
                                                stdout: 单行 {schema_version, request_id,
                                                 status, actual_canonical, exception_type,
                                                 stdout_excerpt, stderr_excerpt}
                                                —— 无 expected / verdict / passed / 路径
```

- 请求中**没有** `expected/tests/hidden/case_index/scoring_path/result_path/db_path/learner_id/session_id/verdict/passed` 等字段（`FORBIDDEN_FIELDS`，构建与解析双向校验）。
- 响应中唯一允许的"结果"是 `actual_canonical`（观测值）与 `status`；`WorkerObservation` dataclass 只有 6 个字段，无任何评分/结论字段。
- 只有可信 supervisor 比较 `actual_canonical == canonical(expected)` 并决定 PASS/WA/RE/TLE；worker 侧永远无法产生 PASS。

## 3. 冻结协议 `m1b.judge.worker.v1`（实现摘要）

- request：`schema_version`, `request_id`（`^[a-f0-9]{16,64}$`）, `function_name`（Python 标识符）, `args`（JSON array）, `timeout_ms`（50..5000）, `stdout_limit`/`stderr_limit`（0..4096）。未知字段/重复键/NaN/Infinity/超限/版本不符 → `WorkerProtocolError` → 调用方映射 `JUDGE_INFRA_ERROR`。
- response：`schema_version`, `request_id`, `status` ∈ {`COMPLETED`,`RAISED`,`SYNTAX_ERROR`,`IMPORT_ERROR`,`MISSING_FUNCTION`,`TIMEOUT`,`INFRA_ERROR`}, `actual_canonical`（仅 COMPLETED 非 null，必须是 canonical JSON 且再规范化后逐字节相等）, `exception_type`（仅限 `^[A-Za-z_][A-Za-z0-9_.]{0,127}$`，不含 message/stack）, `stdout_excerpt`/`stderr_excerpt`（有界 learner 输出）。
- 解析严格性：仅接受恰好一行（多行/空行/截断/超长/非法 UTF-8/重复键/未知字段/request_id 不匹配/非 canonical actual → 全部拒绝，fail-closed）。
- worker 侧自报 `TIMEOUT` 但 supervisor 未观测到超时 → `INFRA_ERROR`（防撒谎）；`COMPLETED` 但退出码非 0 → `INFRA_ERROR`（防篡改）。
- `INFRA_ERROR` 观测由 supervisor 映射为 `JUDGE_INFRA_ERROR`，不改变 mastery/错误计数（集成由 b-cf 实现）。

## 4. OS 隔离规格（实现冻结）

环境实测：`Linux 6.17.13-2-pve x86_64`、`bubblewrap 0.9.0`、宿主 `/usr/bin/python3` = Python 3.12.3；本机以 root 运行 bwrap（目标部署的非 root bwrap 策略不在本 PR 范围）。

### 4.1 冻结命令

```bash
/usr/bin/bwrap \
  --unshare-all --die-with-parent --new-session --clearenv --cap-drop ALL \
  --ro-bind /usr /usr --ro-bind /lib /lib --ro-bind /lib64 /lib64 --ro-bind /bin /bin \
  --ro-bind <PRIVATE_WORK_DIR> /worker \
  --proc /proc --dev /dev --size 16777216 --tmpfs /tmp \
  --uid 65534 --gid 65534 --hostname m1b-worker \
  /usr/bin/python3 /worker/worker_runner.py
```

说明：`--size` 在 bwrap 0.9 中是"作用于下一个 `--tmpfs`"的选项，因此必须置于 `--tmpfs /tmp` **之前**（威胁模型示例中顺序为简写；这是唯一与示例字面顺序不同的地方，语义等价）。`--chdir` 未使用：bwrap 在宿主 cwd 不可见时自动以 `/` 为 cwd（实测）。不含 `--share-net`/`--dev-bind`/`--as-pid-1`。

### 4.2 canary 自检（每次进程内首次 `available()`）

canary 在真实沙箱内检查并全部通过才返回 `True`：uid/gid=65534、hostname=`m1b-worker`、pid ≥ 2、`/root` 与 `/etc/passwd` 不可见、宿主 sentinel 文件不可读、`socket.if_nameindex()==['lo']`、`/proc/net/dev` 仅 `lo`、`/usr` 只读、`/worker` 只读、`/tmp` 可写；并记录 `uid_map` 与沙箱内 `python_version`。任一失败 → `available()=False`，`run()` 抛 `SandboxUnavailable`；**绝不回退裸子进程**。

**P1-2 宿主 principal 报告 + 启动校验**：`BwrapSandbox.security_profile()` 返回 `host_euid`、`host_is_root`、`sandbox_uid/gid`、`uid_map`、`mapped_host_uids`、`sandbox_python_version`、`non_root_principal_verified`、`non_root_requirement_enforced`、`non_root_requirement_satisfied`、`profile`（`LOCAL_ONLY` / `NON_ROOT_PRINCIPAL`）与 `limitation`。本机以 root 运行 bwrap，实测 `uid_map=65534 0 1` → `non_root_principal_verified=False`、`profile=LOCAL_ONLY`。

启动期 fail-closed：目标部署设置 `M1B_REQUIRE_NONROOT_SANDBOX=1` 时，canary 在 `_run_probe` 内校验宿主 euid≠0 且 uid_map 不映射到 0；不满足 → `SandboxUnavailable`（`available()=False`），`run()` 拒绝执行 learner code，supervisor/scorer 返回 BLOCKED/EVAL_ERROR，绝不执行 learner code。默认不设该 env 时本地 synthetic 可用但保留 `LOCAL_ONLY` 报告。**namespace 内 uid 65534 不证明宿主非 root principal**；目标部署必须有非 root 服务账号（或单独评审 setuid bwrap），本地不能满足且本机负向验证为 fail-closed。

### 4.3 主机侧 rlimits（`preexec_fn`）

| 资源 | 值 |
| --- | --- |
| `RLIMIT_AS` | 256 MiB |
| `RLIMIT_CPU` | **每 run 动态** `max(10, ceil(wall_s)+2)` 秒（软/硬）；wall timer 为主判据，CPU 限额只作防御性 backstop（P1-1） |
| `RLIMIT_FSIZE` | 1 MiB |
| `RLIMIT_NOFILE` | 64 |
| `RLIMIT_NPROC`（宿主侧） | `max(4096, 当前宿主 uid 进程数+1024)` |
| `RLIMIT_CORE` | 0 |
| wall clock | `timeout_ms/1000 + 0.5s`，超时 `killpg(SIGKILL)`；正 `137/152/124` 仅在 elapsed ≥ 90% timeout 时按学生 TLE 归类（P1-1） |

**NPROC 说明**：实测 `RLIMIT_NPROC=32` 会让 bwrap 自身在宿主 fork 失败（`Creating new namespace failed: Resource temporarily unavailable`，因为该 rlimit 按宿主 uid 进程计数）。因此宿主 preexec 取宽松值；**真正的每沙箱进程上限 32 由 `worker_runner.py` 在 user namespace 内 `setrlimit(RLIMIT_NPROC,32)` 施加**（实测第 31 次 fork 起 `BlockingIOError`）。pidns + 墙钟 + 进程组 kill 是主控制，NPROC 为纵深防御。

### 4.4 输出与生命周期

- worker_runner 先把协议通道 `dup` 到独立 fd，再把 fd 1/2 重定向到 `/dev/null`；learner `print` 只能进入有界 excerpt（≤ limit），无法写入协议通道。
- learner 若直接写协议 fd：supervisor 侧严格解析会因多行/未知字段/request_id 不匹配而 `INFRA_ERROR`（fail-closed，不可能是 PASS）。
- runner 写完唯一响应行后立即 `os._exit(0)`，跳过 learner 可注册的 `atexit`/`finally`/`__del__`。
- 沙箱 stdout 硬上限 128 KiB（超出截断，协议解析失败即 fail-closed），stderr 16 KiB；`SandboxResult` 记录 `timed_out`/`exit_code`/`elapsed_s`/`truncated`，全部视为不可信观测。
- 超时/被 kill 的进程组由 supervisor `killpg(SIGKILL)` + `wait()` 清理；实测 fork/死循环场景宿主 `/proc` 无残留进程、worker 私有临时目录无残留。

## 5. 与威胁模型 §3.2 的偏离（Lead 已批准，最小放宽）

| 项目 | 威胁模型原值 | 本实现值 | 理由 | 仍存在的边界 |
| --- | --- | --- | --- | --- |
| request `args` canonical | ≤ 4096 B | ≤ 1 MiB | 认证语料 112 条 hidden 中 11 条 `large` 用例超过 4096B（最大 644,455B，如 100000 元素数组）；args 由**可信 supervisor** 按 hidden fixture 生成，learner 不可影响其大小 | 仍硬性 reject >1MiB；深度 ≤4；节点数 ≤1,048,576；worker 内存受 RLIMIT_AS=256MiB |
| request 总大小 | ≤ 16 KiB | ≤ 2 MiB | 同上（args 之外还有字段开销） | >2MiB request 直接 `WorkerProtocolError`/sandbox 侧拒绝，且**不执行 learner code**（见测试） |
| `actual_canonical` | ≤ 8192 B | ≤ 64 KiB | hidden expected 中 list 输出最大 38,464B（5000 元素 running_sum）；不放宽则 2 条 large 用例无法 PASS | 仍硬性 reject >64KiB（`UnserializableActual`）；response 上限同步 |
| response 总大小 | ≤ 16 KiB | ≤ 128 KiB | 承载上述 actual + 有界 excerpts | 多行/超长仍 fail-closed |
| sandbox stdout cap | — | 128 KiB | 同上（协议行为唯一 stdout 输出） | 超出截断 → 解析失败 → INFRA |

**批准与测试化**：Lead 已批准该第三类偏离（可信侧大输入/大输出），`protocol.py` 常量处注明 "B-PR1 deviation from threat-model 4096B, approved by Lead for trusted-fixture certification cases"。对应 fail-closed 测试断言：

- `test_oversized_request_is_fail_closed_and_never_executed`：>2 MiB request 被 `parse_request` / sandbox runner 双重拒绝；>1 MiB args 被 `build_request` 拒绝，worker 返回 `INFRA_ERROR` 且 sandbox 未被调用（不执行 learner code）。
- `test_oversized_request_is_rejected_inside_the_sandbox_before_learner_code`：向真实沙箱 runner 注入 >2 MiB stdin，返回结构化 `INFRA_ERROR`，且含 `time.sleep(5)` 的 solution 未被导入（耗时 < 1.5s），证明"超限不执行"。
- `test_forged_worker_responses_map_to_infra_error`：未知字段/重复键/超长/多行/request_id 不匹配/非 canonical actual 等全部 → `INFRA_ERROR`。
- `test_worker_reference_observations_match_hidden_expected`：112/112 hidden（含 15 条 large、11 条 >4096B）在放宽值内全部 COMPLETED 且 actual == expected。

**未改变**任何字段名、禁止字段集合、status 枚举、canonical 规则与"无 verdict/passed"语义；威胁模型中"不可信输入放大"的防护目标不因该偏离而削弱（args/hidden expected 只来自可信侧，learner 输出仍走独立通道且有界）。

## 6. 认证 fixtures 语义修正（`write_runner_source`）

原 `attack.write_runner_source` 模板写 `../runner.py`，在 bwrap 下实际落在**沙箱内私有 root tmpfs**（可写、随沙箱销毁、无法触达宿主），因此"声明 blocked 但实际 COMPLETED"是错误声明。已拆分为两类（`fixtures/m1_teacher/judge/sentinels/sentinels.json`）：

| attack | 行为 | `expected_blocked` | `expected_classification` | `expected_observation` |
| --- | --- | --- | --- | --- |
| `write_runner_source_ro_bind` | 写 `/worker/solution.py` 或 `/worker/worker_runner.py` | `true` | `RE` | `write_denied_readonly_worker_bind`（只读 bind，实测 RAISED/OSError） |
| `write_runner_source_ephemeral_tmpfs` | 写沙箱内 `../runner.py` | `false` | `WA` | `ephemeral_write_no_host_effect`（写入仅限沙箱 tmpfs，宿主无效果） |

- 两者均 `SYNTHETIC_TEST_ONLY`，无真实凭据/个人信息/真实载荷。
- 负例测试断言：ephemeral 模板即使写成功也**不是 PASS**（`actual_canonical` 不等于隐藏 expected），且**宿主无效果**（宿主 sentinel 内容不变、宿主目录文件集合不变、无残留进程/临时目录）；RO-bind 模板写 `/worker` 被拒绝并观测为 RE。
- `test_judge_fixture_integrity.py` 已同步校验新字段：`expected_observation` 允许受控枚举、`expected_blocked=false` 时 classification 不得为 PASS 且必须声明 observation；仍保持严格 schema（未知字段 fail）。

## 7. 可复现证据（本机，2026-11-20 UTC）

### 7.1 定向测试

```
$ cd /root/m1b/pr1-sandbox
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
    tests/m1_teacher/test_judge_sandbox.py \
    tests/m1_teacher/test_judge_worker.py \
    tests/m1_teacher/test_judge_negatives.py \
    tests/m1_teacher/test_judge_fixture_integrity.py -q
............................................................  [100%]
60 passed in 13.76s
```

`ruff check`（judge 包 + 4 个测试文件）→ `All checks passed!`。

### 7.2 B1-05 worker 侧认证基线（全部在真实 bwrap 沙箱内）

```
REFERENCE: 112/112 PASS in 3.90s (34.8 ms/case)
per-case passed: cf_array_max_subarray 9/9, cf_array_running_sum 7/7,
  cf_array_sum_even 7/7, cf_bs_first_index 8/8, cf_bs_search_insert 8/8,
  cf_dp_climb_stairs 7/7, cf_dp_coin_change 10/10, cf_dp_lcs 7/7,
  cf_graph_bfs_dist 8/8, cf_graph_count_components 8/8, cf_sort_insertion 7/7,
  cf_tp_dedupe_sorted 7/7, cf_tp_is_palindrome 10/10, cf_tp_pair_sum_sorted 9/9
mismatches: []   # 15 条 large（含 11 条 >4096B）全部包含在 112 内
```

（PASS 判定为 worker 观测 `COMPLETED` 且 `actual_canonical == canonical(expected)`；最终 verdict 仍由 supervisor 决定。）

### 7.3 负例矩阵（全部仅在沙箱内执行）

| negative | failure_mode | 声明 | 实测观测 |
| --- | --- | --- | --- |
| `neg.pass.edge_correct` | edge_correct | PASS | ZCOMPLETED，9/9 隐藏用例 actual == expected |
| `neg.wa.constant_return` | constant_return | WA | COMPLETED，actual ≠ expected |
| `neg.wa.off_by_one` | off_by_one | WA | COMPLETED，actual ≠ expected |
| `neg.re.syntax_error` | syntax_error | RE | SYNTAX_ERROR |
| `neg.re.runtime_exception` | runtime_exception | RE | RAISED |
| `neg.re.missing_function` | missing_function | RE | MISSING_FUNCTION |
| `neg.tle.infinite_loop` | infinite_loop | TLE | TIMEOUT（墙钟 kill，0.9s 内） |

### 7.4 攻击模板矩阵（`expected_blocked` 与真实观测）

| attack | blocked | 声明分类 | 实测状态 | 命中 sentinel |
| --- | --- | --- | --- | --- |
| `attack.stack_frame_probe` | true | WA | COMPLETED（actual=-1） | false |
| `attack.argv_result_forgery` | true | WA | COMPLETED（actual=0） | false |
| `attack.forged_protocol_output` | true | WA | COMPLETED（actual=0） | false |
| `attack.socket_connect` | true | WA | COMPLETED（actual=-1，无外联失败被捕获） | false |
| `attack.exception_override` | true | WA | COMPLETED（actual=0） | false |
| `attack.host_sentinel_read` | true | RE | RAISED（FileNotFoundError/OSError） | false |
| `attack.write_runner_source_ro_bind` | true | RE | RAISED（OSError，只读 bind） | false |
| `attack.exit_code_tamper` | true | RE | INFRA_ERROR（os._exit(0) 无响应，fail-closed） | false |
| `attack.fork_subprocess` | true | TLE | TIMEOUT（~0.9s，killpg，无宿主残留） | false |
| `attack.infinite_loop` | true | TLE | TIMEOUT（~0.9s） | false |
| `attack.write_runner_source_ephemeral_tmpfs` | false | WA | COMPLETED（actual=0，仅沙箱 tmpfs，宿主无效果） | false |

另测试：注入伪造协议行（learner 直写协议 fd）→ `INFRA_ERROR`；`atexit` 伪造不改变响应（COMPLETED actual=0，无 "passed" 文本）；超大 request（>2MiB）在 protocol 与 sandbox runner 双重拒绝且**不执行 learner code**；超大 args（>1MiB）→ INFRA 且 sandbox 未被调用。

### 7.5 全量回归（真实输出）

```
$ cd /root/m1b/pr1-sandbox
$ "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
........................................................................ [ 96%]
....................                                                     [100%]
596 passed in 32.11s
```

`596 = M1-A 536 + 本 PR 新增 60`（M1-A 基线测试未删改；旧 scorer/session 路径未改动）。另：`tests/m1_teacher/test_fixtures_cf.py` 的 broad 扫描已按 Lead 授权、最小限定为 teacher-visible fixtures（`domains/**` + 根 README，显式排除 `judge/**`）；教师可见断言未删除/未弱化，judge corpus 由 `test_judge_fixture_integrity.py` 单独校验。

## 8. 负例矩阵落点（威胁模型 §6 → 本实现证据）

| ID | 攻击 | 本实现落点 | 状态（LOCAL） |
| --- | --- | --- | --- |
| N-01 | 调用栈找 expected | 协议 request 无 expected；`stack_frame_probe` 攻击实测无 sentinel | 已测，FAIL_CLOSED |
| N-02 | argv/result 文件伪造 | 无 result 文件、无 argv 路径；`argv_result_forgery` 实测 COMPLETED(WA) | 已测，非 PASS |
| N-03 | stdout 伪造 `{"passed":true}` | fd 分离 + 单行严格 schema；`forged_protocol_output` 实测 COMPLETED(WA) | 已测，非 PASS |
| N-04 | 读宿主私有/sentinel | bwrap ro rootfs + canary；`host_sentinel_read` 实测 RAISED | 已测，宿主不可见 |
| N-05 | 网络 | netns 仅 lo；socket 攻击被捕获 | 已测，无外联 |
| N-06 | fork/子进程逃逸 | pidns + killpg；无宿主残留 | 已测 |
| N-07 | 死循环/超时 | 墙钟 kill；TIMEOUT | 已测，STUDENT_TLE 语义 |
| N-08 | 输出放大 | 有界 excerpt + sandbox stdout cap + FSIZE | 已测 |
| N-09 | 写 runner/solution | `/worker` 只读 bind；RO-bind 攻击 RAISED | 已测 |
| N-10 | atexit / os._exit 篡改 | `os._exit(0)` 跳 atexit；无响应/非 0 退出 → INFRA | 已测 |
| N-11 | 资源耗尽 | AS/CPU/FSIZE/NOFILE/NPROC(+inner)/wall | 已测（内存/文件/fd/CPU/fork） |
| N-12 | 请求注入 expected/未知字段 | request 严格 schema；sandbox runner 拒绝 | 已测 |
| N-13 | 伪造 worker 响应 | 严格解析：额外字段/重复键/超长/多行/request_id 不匹配 → INFRA | 已测 |
| N-14 | 不可序列化/NaN/超长 actual | runner 输出 RAISED(`UnserializableActual`)，永不为 PASS | 已测 |
| N-15 | 经 diagnostic/trace 泄漏 | worker observation 无 expected；supervisor/Teacher 导出扫描由 b-cf supervisor 集成负责（本 PR 提供无泄漏的 observation 面） | 部分（本 PR 面） |
| N-16 | 跨 case 状态污染 | 每 case 一进程一私有目录；不保存历史 | 已测 |

## 9. 已知限制与残余风险

1. **证据等级**：本文件为 IMPLEMENTED + LOCAL/MOCK；bwrap 隔离依赖宿主内核/userns 配置，目标 CI/生产环境是否允许 bwrap 仍 `NOT_RUN`；不能据此开启真实用户 CODE。
2. **P1-2（启动校验已实现；目标部署 PARTIAL/NOT_RUN）** bwrap/内核 0day、侧信道、宿主本身以 root 运行 bwrap 的风险不在防护范围；本机 `uid_map=65534 0 1`（inside→host 0），默认 `security_profile()["non_root_principal_verified"]=False`/`LOCAL_ONLY`；设置 `M1B_REQUIRE_NONROOT_SANDBOX=1` 时 canary fail-closed（`available()=False`）。生产部署必须使用非 root 服务账号（或单独评审的 setuid 方案）并复跑 B1-04；本地不满足。
3. `RLIMIT_NPROC` 在不同内核/userns 映射下语义不同：宿主侧必须宽松，真正上限在沙箱内施加；cgroup v2 限额未使用（增强项）。
4. 每 case 一进程的启动成本实测 ~30–50 ms（112 case ≈ 3.9 s），并发/吞吐上限、目标部署延迟与本机差异未测。
5. `exit_code_tamper` 类（`os._exit`）在 worker 侧表现为"无有效响应 → INFRA"，与 fixture 声明的 RE 同属 fail-closed；supervisor 映射时需把无响应/非 0 退出统一归入 `JUDGE_INFRA_ERROR`（b-cf 集成）。
6. **P1-1（已修复）** `TIMEOUT` 由墙钟 kill 产生；正 `exit=137(128+SIGKILL)`/`152(128+SIGXCPU)`/`124` 仅在 `elapsed_s ≥ 0.9 × timeout_s` 时归为 TIMEOUT（学生 TLE 语义），过早的资源 kill 仍为 `INFRA_ERROR`；同时 `RLIMIT_CPU` 动态设为 `max(10, ceil(wall)+2)`，确保 wall timer 先触发。回归测试：默认 2.0s 死循环 → `STUDENT_TLE`，~1.5s 慢正确解 → PASS，短 timeout 0.5s 仍 TLE。
7. learner 若直接写协议 fd，可抢先输出一行；严格解析只会得到 INFRA/WA/RE，不可能 PASS，但可能掩盖 runner 的真实响应（fail-closed 可接受，记录为已知面）。
8. 协议限值偏离（§5）已由 Lead 批准并注释在代码；若后续 Reviewer 要求回到 4096B，则 large hidden cases 需另行协议（如 supervisor 侧标记 unsupported 或分片），否则 B1-05 的 112/112 不成立。
9. 认证语料含 hidden expected，属 JUDGE 内部资产；Teacher 可见性隔离由 `test_judge_fixture_integrity.py` 与 supervisor 集成共同保证。

### 9.1 安全 CI 接线（review addendum P1-3）

仓库内提供了安全 CI 入口脚本 `scripts/m1b/run_safety_ci.sh`：

```bash
PYTHON=/path/to/venv/bin/python ./scripts/m1b/run_safety_ci.sh
# 本地 root 合成验证（非部署安全证据）：
./scripts/m1b/run_safety_ci.sh --allow-root-synthetic
```

脚本默认 `export M1B_REQUIRE_OS_SANDBOX=1 M1B_REQUIRE_NONROOT_SANDBOX=1`，运行 `pytest tests/m1_teacher -q -rs` 并断言 exit 0、输出无 `skipped`、无 `s` progress 行；`--allow-root-synthetic` 仅用于本地 root 合成评估（把 `M1B_REQUIRE_NONROOT_SANDBOX` 设为 0），**不可作为部署安全证据**。当前仓库 `.github/workflows/` 未配置该 job（= `NOT_CONFIGURED`/`NOT_RUN`），需维护者/CI owner 接线；本 PR 不修改 `.github`。

## 10. 运行方式

```bash
cd /root/m1b/pr1-sandbox
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_judge_sandbox.py \
  tests/m1_teacher/test_judge_worker.py \
  tests/m1_teacher/test_judge_negatives.py \
  tests/m1_teacher/test_judge_fixture_integrity.py -q
```

无网络、无真实 Key；bwrap 不可用的宿主上动态沙箱测试会以明确原因 skip，fail-closed 单元测试仍执行。
