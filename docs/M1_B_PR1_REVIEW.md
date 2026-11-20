# M1-B / B-PR1 独立安全评审：可信判题边界（no-key）

- 评审对象：`b-next/pr1-review`，HEAD `6e20fd13a9c4ebf79188f0aac326edb074f2317b`，基线 `4706250643fd42d48d69ddad7159e011955fa9fd`（`git merge-base` 一致）。
- 评审范围：`TrustedJudgeSupervisor`、`UntrustedExecutionWorker`、`BwrapSandbox`、`m1b.judge.worker.v1` 协议、`DeterministicScorer` CODE 路径、默认封禁、认证语料/负例/泄漏扫描与文档声明。
- 评审方式：静态审计 + 本机真实复跑 + 自写 `/tmp` 只读探针（不提交）。所有探针只使用 synthetic 数据；未联网、未使用 Provider/Key、未执行真实恶意代码；未写入任何 hidden expected 明文。
- 证据标签：`OWNER_REPORTED`（Owner 文档/报告，未由本评审独立证明）、`INDEPENDENTLY_REEXECUTED_THIS_TURN`（本轮独立命令/探针）、`NOT_RUN`（未执行或无法在本机证明）。
- 本评审只新增本文件；未修改源码/测试/既有文档/提交，未 amend。评审提交见下方 §9。

## 0. 结论

**`PASS_WITH_ACTIONS`**

- P0：无。未发现隐藏 expected 泄漏、可信 verdict 被伪造为 PASS、宿主敏感文件读取、网络外联、沙箱不可用时的裸子进程回退。
- P1：4 项（默认超时下 TLE 误分类为 INFRA；宿主非 root principal 未满足；CI 可在无 bwrap 时跳过全部 OS 动态证据；威胁模型仍称环境变量可开启 trusted-fixture，与 P1-01/实现矛盾）。
- B1 状态：B1-01/02/03/06 `VERIFIED (LOCAL_ONLY)`；B1-04 `PARTIAL`；B1-05 `PARTIAL`。详见 §3。
- **LOCAL_VERIFIED ≠ 目标部署可用**。真实用户 CODE 仍为 **BLOCKED**，需要人类批准与目标部署验收；本评审不代表 B-PR2..B-PR5、M0/security/bridge/LiveGate 或整体集成通过。

## 1. 独立复跑命令与实测

环境：Linux 6.17 宿主、bubblewrap 0.9.0、`/usr/bin/python3` 3.12.3（沙箱内）、宿主 venv Python 3.11.15；uid=0（root）。时间：2026-11-20 UTC。

| 命令 | 实测 | 标签 |
| --- | --- | --- |
| `git rev-parse HEAD` / `git merge-base 4706250 HEAD` | `6e20fd1…` / `4706250…` | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `git status --porcelain` | 空（评审开始与提交前） | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `git diff --name-only 4706250..HEAD` | 30 个路径；全部位于 `docs/`、`m1_teacher/`、`tests/m1_teacher/`、`fixtures/m1_teacher/judge/`；无 `src/`、`security`、`bridge`、`config/g*`、`scripts/g4*`、LiveGate、plugins、M0 路径 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `cd /root/m1b/review-pr1 && "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q` | **674 passed in 51.48s**，exit 0（real 51.838s） | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| 定向 8 个文件（`test_judge_*`、`test_hidden_leakage_scan.py`、`test_assessment_scorer.py`）联合跑 | **172 passed in 34.50s**，exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_supervisor.py` | 36 passed in 0.06s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_correctness.py` | 27 passed in 12.19s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_worker.py` | 23 passed in 4.76s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_sandbox.py` | 11 passed in 0.72s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_negatives.py` | 11 passed in 5.41s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_judge_fixture_integrity.py` | 15 passed in 1.14s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_hidden_leakage_scan.py` | 15 passed in 3.54s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `test_assessment_scorer.py` | 34 passed in 4.77s | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher` | `All checks passed!`，exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |

Owner 文档称 `674 passed in 50.11s`、定向计数与上表一致；计数/时限与本轮实测相符（`OWNER_REPORTED`，本轮独立复跑）。Owner 的 `596` worker-branch 基线未在本分支单独复跑：`NOT_RUN`。

## 2. 独立安全探针

探针位于 `/tmp/pr1_probe_{os,default,isolation,forgery,correctness,leakage}.py`，只读运行，不提交；结果摘要如下。

### 2.1 默认策略不可由数据路径启用（B1-01）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`DEFAULT_POLICY_PROBE_OK`：

- 构造 `DeterministicScorer(fixtures_root, judge_worker=NeverWorker())`（默认 `trusted_fixture_only=False`）；提交 `item.bs.code.001` 的 4 种 response（纯代码、含 `trusted_fixture_only=True` 的 dict、含 `assessment_job.enable_code_execution` 的 dict、list）→ 全部 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，`score=None`；worker 调用次数 0；副作用 sentinel 文件未创建。
- 额外关键字 `scorer.score(..., trusted_fixture_only=True)` → `TypeError`；`M1B_TRUSTED_FIXTURE_ONLY` / `M1_TEACHER_TRUSTED_FIXTURE_ONLY` 环境变量 → 仍 blocked；篡改 item（`item_id`/`max_score`/`scoring_spec_ref` 保持不变）→ 仍 blocked。
- `TrustedJudgeSupervisor(NeverWorker())` 默认 evaluate → `UNTRUSTED_CODE_EXECUTION_BLOCKED`，worker 未调用。
- engine 集成：CODE-only adapter + 默认 scorer + CODE 提交 → `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，`score=None`，sentinel 未创建；`snapshot=None`，无 `ASSESSED` event，`ERROR` payload `mastery_unchanged=True`，`history.verify_rebuild()==True`。
- 已有 snapshot 场景：先以 MCQ 结果建立 `revision=1`/mastery 快照，再提交 blocked CODE；前后 snapshot `to_dict()` 逐字节相同，`revision` 不变。
- 显式 `trusted_fixture_only=True` + 不可用 sandbox → 仍 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，无裸子进程回退，sentinel 未创建。

### 2.2 expected 隔离（B1-02）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`EXPECTED_ISOLATION_PROBE_OK`：

- 包装真实 `UntrustedExecutionWorker` 捕获 supervisor→worker 调用：字段仅 `code`/`function_name`/`args`/`timeout_s`；synthetic expected sentinel 不出现在调用中；`inspect.signature` 同样只有这些参数。
- 沙箱内 learner 代码检查：`argv=["/worker/worker_runner.py"]`、`cwd="/"`、`env={}`（除解释器自身产生的 `LC_CTYPE`/`PWD` 外无宿主敏感变量）、`/worker` 仅 `solution.py`/`worker_runner.py`、宿主 certification 路径不存在、宿主 sentinel 读取 `FileNotFoundError`、`inspect` 调用栈中 `expected`/`tests`/`scoring_spec_ref`/`hidden`/`test_cases` 命中为空；`sys.path` 无 fixtures 路径。
- 真实 supervisor 对 5 类攻击代码（stack-frame 查找 expected、argv result 伪造、宿主 sentinel 读取、stdout 伪造 passed、`os._exit`）→ 分别 `WA`/`WA`/`RE`/`WA`/`JUDGE_INFRA_ERROR`，均非 PASS，`cases_passed==0`，verdict/failure_codes 不含 expected/args/sentinel。
- 捕获的 request JSON 字段集合等于 `REQUEST_FIELDS`，不含 `expected`/`tests`/`hidden`/`verdict`/`passed`/路径；worker 目录不含 hidden expected 内容。

### 2.3 verdict 伪造（B1-03）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`VERDICT_FORGERY_PROBE_OK`：

- 协议层 12 种伪造/畸形响应（额外 `passed`/`verdict`/`score`/`expected`、未知字段、`status=PASS`、非 canonical actual、重复键、多行、超长、空、request_id 不匹配）→ 全部 `WorkerProtocolError` / 上层 `JUDGE_INFRA_ERROR`。
- supervisor 对 6 种内存伪造 observation（dict 带 `passed`/`verdict`/未知字段、`SimpleNamespace` 带 `passed`、`status=PASS`、非 canonical actual）→ 全部 `JUDGE_INFRA_ERROR`，`cases_passed=0`，`passed=False`。
- 真实沙箱 learner 代码读取 `sys._getframe(1).f_locals["payload"]["request_id"]` 与 `sys.modules["__main__"]._PROTOCOL_FD`，直接写伪造 `COMPLETED + passed:true` 并 `os._exit(0)` → worker 观测 `INFRA_ERROR`，supervisor `JUDGE_INFRA_ERROR`；不能 PASS。
- 同一路径写合法单行 `COMPLETED actual="0"` 时，只有 trusted expected 也等于 0 才 PASS（等价于答对），expected=7 时为 WA；不存在“无需 expected 即 PASS”的路径。
- **残余风险（P2）**：learner 可伪造 `INFRA_ERROR`/`RAISED` 观测。INFRA 会被可信端判 `JUDGE_INFRA_ERROR`（EVAL_ERROR、mastery 不变），因此恶意学习者可主动抑制负面学生证据；`RAISED` 只得到 RE。不能伪造 PASS。worker 文档 §9.7 已承认“可抢先输出一行/掩盖 runner 响应”，但威胁模型未把它列为显式风险项。

### 2.4 OS 围栏（B1-04）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`OS_FENCE_PROBE_OK`：

- 真实 bwrap 内：`uid=65534`、`euid=65534`、`gid/egid=65534`、`pid=2`、`ppid=1`、hostname=`m1b-worker`；`/root`、`/etc/passwd` 不可见；宿主 sentinel/certification 路径不可读；`/usr` 与 `/worker` 写入 `OSError`；`/tmp` 可写；`socket.if_nameindex()==["lo"]`，`/proc/net/dev` 仅 `lo`，外联 `OSError`；`CapEff/CapPrm=0`、`NoNewPrivs=1`、`Seccomp=2`。
- 超时/子进程清理：fork + `while True` + timeout 0.4s → `TIMEOUT`，0.94s 内返回，宿主 `/proc` 无 marker 残留，worker 临时目录集合不变；fork 后 `setsid` 的 sleep 子进程亦无残留。
- 资源：400 MiB 分配 → `MemoryError`；5 MiB 文件 → `OSError`；200 fd → `OSError`；fork 循环 30 次后 `BlockingIOError`（`RLIMIT_NPROC=32` 在 userns 内生效）。
- 不可用路径：`BwrapSandbox(bwrap_path="/nonexistent/...")` → `available()=False`，worker 返回 `INFRA_ERROR`，副作用 marker 未创建；`run()` 抛 `SandboxUnavailable`；无裸子进程回退。
- **重要限制（P1-2）**：本机 bwrap 以 root 启动；沙箱内 `/proc/self/uid_map` 为 `65534 0 1`（inside 65534 → host 0）。因此“沙箱内 uid 65534”成立，但“独立非 root OS principal”在宿主层面未成立。所有宿主敏感路径均未挂载，当前未发现直接读取；但目标部署必须用专用非 root 服务/setuid bwrap，并验证宿主 uid_map，不能把 namespace 内 65534 当作宿主非 root 证明。
- **P1-1 证据（默认超时 TLE）**：`RLIMIT_CPU_SECONDS=2`，而 scorer/supervisor 默认 `timeout_s=2.0` + worker 0.5s grace（wall 2.5s）；CPU 限制在 2.0s 先触发。直接 sandbox 结果为 `exit=137`、`timed_out=False`；`worker._interpret` 仅把 `exit_code < 0` 当 timeout，正 137 落到 `INFRA_ERROR`。实测 supervisor `timeout_s=0.5/1.0/1.5` → `TLE`，`2.0/3.0` → `JUDGE_INFRA_ERROR`；`DeterministicScorer(FIX, trusted_fixture_only=True)` 默认对死循环返回 `EVAL_ERROR:JUDGE_INFRA_ERROR:WORKER_INFRA_ERROR`。这与 B1-05“死循环 TLE”及 worker 文档 §9.6“SIGKILL/SIGXCPU → TIMEOUT”不符。

### 2.5 正确性与可用性（B1-05）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`B1_05_PROBE_OK`（除默认 TLE 分类外）：

- 14/14 参考解、**112/112** hidden cases 经真实 worker+supervisor PASS，3.26s；逐题 7–10/7–10 全 PASS。
- 负例 7/7 与声明一致：edge_correct PASS；constant_return/off_by_one WA；syntax/runtime/missing RE；infinite_loop TLE（0.5s 短超时）。
- 手写 wrong/syntax/runtime/missing → WA/RE/RE/RE；0.4s 超时 → TLE；同输入重复 verdict 逐字段相同。
- 默认 2.0s 无限循环 → INFRA（P1-1），因此 B1-05 不能给 VERIFIED。

### 2.6 运行时泄漏（B1-06）

`INDEPENDENTLY_REEXECUTED_THIS_TURN`，`RUNTIME_LEAKAGE_PROBE_OK`：

- 用 synthetic hidden spec（expected/args 为 review 专用 sentinel）走完整 `DeterministicScorer` + `LearningHistory`：`AssessmentResult.to_dict()`、`ASSESSED`/`MASTERY_UPDATED` 等 event payloads 中 sentinel 0 次、hidden path 0 次；`scoring_spec_ref` 仅 `scoring/leak.json` 相对路径，非绝对、无 `..`。
- 默认 blocked engine 的 events/result 扫描同样无 sentinel/hidden path；`history.verify_rebuild()` 成功。
- 认证语料每个 expected 值的 canonical SHA-256 指纹在 result/history/CLI/demo 中均未出现；`judge/certification`、`judge/sentinels`、fixtures 绝对路径未出现。
- CLI `--demo --json`（47,999 bytes）与 `python -m m1_teacher.demo`（5,782 bytes）exit 0，扫描 0 sentinel/0 fingerprint/0 hidden path。
- **P2 残余**：`AssessmentResult.evidence_refs` 含 `spec-sha256:<16 hex>`（`scorer.py:313`），是 hidden scoring spec 的截断 SHA-256；文档明确接受“哈希非内容”，但在单 case/低熵 expected 场景可作为离线字典校验面。本评审未把它计为 P0/P1，建议 HMAC 化或移除。
- **P2 残余**：`ASSESSED` event 的 item 投影确实携带 `scoring_spec_ref`（实测为 `scoring/item.bs.code.001.json` 形式）；仅相对文件名，无内容/绝对路径/遍历，符合 P2-13 记录，但依旧暴露 hidden spec 文件名。

### 2.7 bwrap 命令与 P1-08

`INDEPENDENTLY_REEXECUTED_THIS_TURN`：

- 错误顺序 `--tmpfs /tmp --size 16777216` → exit 1，stderr `bwrap: --size must be followed by --tmpfs`。
- 正确顺序 `--size 16777216 --tmpfs /tmp` → exit 0，`pid 2 uid 65534`。
- 实现命令与文档 §4.1 一致：`--unshare-all --die-with-parent --new-session --clearenv --cap-drop ALL`，ro-bind 仅 `/usr /lib /lib64 /bin` 与私有 work dir，`--proc /proc --dev /dev`，私有 tmpfs，uid/gid 65534，hostname；无 `--share-net`/`--dev-bind`/`--as-pid-1`。P1-08 关闭证据成立。

## 3. B1-01..B1-06 独立状态

| 项 | 独立证据 | 状态 | 说明 |
| --- | --- | --- | --- |
| B1-01 Untrusted code blocked | 默认 scorer/supervisor/engine 全 blocked；无副作用；无 worker 调用；快照不变 | **VERIFIED (LOCAL_ONLY)** | 真实用户 CODE 仍 BLOCKED |
| B1-02 Hidden expected isolation | worker 调用字段最小化；沙箱帧/argv/env/FS/宿主路径探针无 expected | **VERIFIED (LOCAL_ONLY)** | 无 hidden expected 明文进入 worker |
| B1-03 Result forgery | 12 协议伪造 + 6 内存伪造 + 真实协议 fd 伪造均非 PASS | **VERIFIED (LOCAL_ONLY)** | P2：可伪造 INFRA/RAISED 抑制学生证据 |
| B1-04 Judge confinement | uid/gid 65534、pid/net/uts/ipc、ro FS、tmpfs、rlimit、超时、无残留、fail-closed | **PARTIAL** | 宿主 uid_map 65534→0；非 root principal 与目标部署 `NOT_RUN`（P1-2） |
| B1-05 Correctness | 112/112、WA/RE/TLE(0.5s)、determinism | **PARTIAL** | 默认 2.0s 死循环误判 INFRA（P1-1） |
| B1-06 Hidden leakage scan | result/history/CLI/demo 运行时扫描；sentinel/路径/指纹 0 命中 | **VERIFIED (LOCAL_ONLY)** | P2：spec-sha256 与 scoring_spec_ref 元数据残余 |

## 4. 发现分级与必须动作

### P0（阻断级）

无。

### P1（真实用户 CODE 开放/目标部署前必须处理）

| ID | 发现 | 证据 | 动作/验收 |
| --- | --- | --- | --- |
| **P1-1** | 默认 `timeout_s=2.0` 下死循环/慢解被 RLIMIT_CPU 2s 杀死，worker 把正 `exit=137` 映射为 `INFRA_ERROR`，而非 `TLE`；默认 `DeterministicScorer(...trusted_fixture_only=True)` 返回 `EVAL_ERROR`。 | `sandbox.py:65`；`worker.py:226-231`；实测 2.0/3.0→INFRA，0.5/1.0/1.5→TLE；直接 sandbox `exit=137,timed_out=False`；`docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md:235` 与实现相反。 | 让 wall clock 成为主判据：将 `RLIMIT_CPU` 提到 > `MAX_CASE_TIMEOUT_S + grace`（如 10s），或可靠识别 128+SIGKILL/SIGXCPU 且只在该 case 的 wall 预算耗尽时判 TIMEOUT；新增默认 2.0s 死循环回归测试与慢正确解测试，要求 `TLE`/`JUDGE_STUDENT_TLE`，不是 EVAL_ERROR；同步修正文档。**验收**：默认 scorer 死循环 → `INCORRECT/JUDGE_STUDENT_TLE`；慢正确解 → PASS；无 infra 误报。 |
| **P1-2** | “独立非 root OS principal”在宿主层未满足：bwrap 以 root 运行，`/proc/self/uid_map = 65534 0 1`；沙箱内 65534 映射到宿主 0。 | 独立探针；`docs/M1_B_THREAT_MODEL_JUDGE.md:352` 已承认 root 运行风险，但 §1/§4.4 仍称“非 root”；`docs/M1_B_JUDGE_WORKER_IMPLEMENTATION.md:60` 承认 root。 | 目标部署用专用非 root 服务账号 + 非 setuid bwrap/userns 策略（或 setuid 方案单独评审）；启动时记录并校验宿主 euid≠0 与 uid_map，canary 增加该项；文档明确“local root ≠ deployed non-root”。**验收**：目标环境 `id -u != 0`、uid_map 不映射到 0、B1-04 全套复跑。 |
| **P1-3** | 无 bwrap 的 CI 会 skip 所有动态 OS/B1-05 测试，`674 passed` 仍可不含任何隔离证据。 | 7 处 `pytest.skip`（correctness/negatives/sandbox×3/worker/leakage skipif）；本机 0 skipped；Owner 未提供“0 skip”门禁。 | 独立 security CI job 强制 bwrap，`-rs` 统计 skip=0；或在 judge 测试加 session gate（bwrap 不可用则 fail，而非 skip）；普通单测 CI 可保留 skip。**验收**：安全 job 输出 0 skipped 且包含 sandbox/correctness 全量。 |
| **P1-4** | 威胁模型 §5.1 仍写 `TRUSTED_FIXTURE_TEST_ONLY` 可由“代码内显式参数/环境变量”开启，与 P1-01（绝不可由环境变量）和实现（不读环境变量）矛盾。 | `docs/M1_B_THREAT_MODEL_JUDGE.md:369` vs `:368`；`test_judge_supervisor.py::test_policy_cannot_enable...`；实现无 env 读取。 | 删除“环境变量”，统一为“仅可信构造/部署参数”；加文档 lint/断言或回归测试；**验收**：全仓文档无“env 可开启 trusted fixture”表述。 |

### P2（不阻断本地评审，但应记录/排期）

| ID | 发现 | 动作 |
| --- | --- | --- |
| P2-1 | 威胁模型 §4.3 仍写 supervisor 读取“最大 16 KiB、只看第一行、后续丢弃”；实现为 response 128 KiB、**多行直接拒绝**（`protocol.py:496-497`）。 | 按 P2-05/06 实现值更新 §4.3，并明确“拒绝多行”而非“取第一行”。 |
| P2-2 | 威胁模型头仍为 `DESIGN_ONLY/未实现`（`docs/M1_B_THREAT_MODEL_JUDGE.md:4,43,521`），但 v0.2 已回填 PR1 实现；状态语义混乱。 | 改为“DESIGN + IMPLEMENTED_LOCAL_VERIFIED（独立验收前）”，保留历史版本说明。 |
| P2-3 | `docs/M1_B_PORTS.md:204` 要求 `--clearenv` 下固定 `PYTHONHASHSEED=0`/`PYTHONDONTWRITEBYTECODE=1` 并 pin worker 解释器；实现未设置这两个 env，只硬编码 `/usr/bin/python3`（本机 3.12.3），沙箱内实际可见 `LC_CTYPE`/`PWD`。 | 要么在 runner 启动时显式设置并 pin 版本校验，要么修订设计；避免跨解释器/哈希种子差异。 |
| P2-4 | `AssessmentResult.evidence_refs` 含 `spec-sha256:<16>` 隐藏 spec 截断哈希（`scorer.py:313`）；设计文档接受“哈希非内容”，但低熵单 case 可作离线字典校验。 | 改为服务端密钥 HMAC，或删除该 ref；保留时在威胁模型标注熵/字典风险。 |
| P2-5 | `scoring_spec_ref` 文件名进入 `ASSESSED` item 投影（实测 `scoring/item.bs.code.001.json`）；仅相对、无内容，属已记录 P2-13。 | 保持现状或按 PORTS P2-13 改为不透明 `spec_ref_id`；新增断言已覆盖相对性。 |
| P2-6 | learner 可借 `sys.modules["__main__"]._PROTOCOL_FD` + 栈帧 request_id 伪造合法 observation（含 INFRA），不能 PASS；worker 文档 §9.7 承认但威胁模型未列为显式风险。 | 长期把 learner 执行放入子进程、协议 fd 不继承（parent runner 写响应），或使用 learner 不可读 nonce；至少新增伪造 INFRA/RAISED 的负例并更新威胁矩阵。 |
| P2-7 | 测试套件未直接覆盖 NPROC=32 与 RLIMIT_CPU 分类；owner 文档称“实测第 31 次 fork”，但 `test_judge_sandbox.py` 无该断言。 | 增加 NPROC/CPU 沙箱测试（独立探针已测：30 次 fork 后 BlockingIOError；CPU 2s→exit 137）。 |
| P2-8 | `/proc/1/cmdline` 在沙箱内暴露宿主 worker work dir 路径（`/tmp/m1b_judge_worker_*`），虽不可访问、无 expected。 | 低风险；可在设计上接受并记录，或用 `--argv0`/隐藏 mount source 降低路径面。 |
| P2-9 | 部分测试用 `pytest.raises(Exception)`（`test_judge_supervisor.py:444`、`test_judge_worker.py:604`）过宽，可能因错误原因通过。 | 收紧为 `ValidationError`/`WorkerProtocolError`；不影响现有安全结论。 |
| P2-10 | `DeterministicScorer(timeout_s=60)` 合法，但 `_get_supervisor()` 传给 supervisor 的 timeout 最大 5.0，实际 CODE 会 `EVAL_ERROR:SUPERVISOR_EXCEPTION`。 | 统一上限或显式拒绝 >5；加构造/评分一致性测试。 |
| P2-11 | 任务摘要称 demo/cli“显式 trusted_fixture_only=True”；实际 diff 仅注释，demo 使用 `MockStudentScorer`，CLI 无 CODE 入口。 | 不是安全缺陷（无 CODE 执行更安全）；请修正交接/文档表述，避免“已显式 opt-in”的误解。 |
| P2-12 | 泄漏测试以 synthetic sentinel 为主；认证语料 112 个 expected 值没有逐个指纹扫描（本评审独立指纹扫描为 0 命中）。 | 增加认证语料 expected 的哈希/存在性扫描，避免未来回归只覆盖 sentinel 而漏掉真实语料。 |

## 5. 文档声明 vs 实现核对

| 声明 | 独立核对 | 结论 |
| --- | --- | --- |
| Owner：674 passed；14/14 参考解 112/112 hidden PASS；默认 CODE 封禁 | 674 passed 51.48s；112/112 3.26s；默认 blocked + no execution + snapshot 不变 | 数字与主结论相符（`INDEPENDENTLY_REEXECUTED_THIS_TURN`） |
| P1-01：opt-in 只来自构造/部署，不可由 item/response/result_id/env/kwarg | 4 类 response、item 篡改、env、额外 kwarg 全部不能开启；worker 从未调用 | 实现层面成立；文档 §5.1 仍写 env（P1-4） |
| P1-08：`--size` 必须在 `--tmpfs` 前 | 错误顺序 exit 1/正确顺序 exit 0；实现命令正确 | CLOSED 成立 |
| 协议上限：request 2 MiB / response 128 KiB / args 1 MiB / actual 64 KiB | 实现常量一致；大语料 112/112 通过；超限 fail-closed | 与 P2-05/06 注记一致；§4.3 旧数（P2-1） |
| 默认策略：FAIL-CLOSED、无裸子进程回退 | 不可用 sandbox → INFRA/blocked，marker 未创建；无 `subprocess` fallback | 成立 |
| bwrap 命令/隔离 | 独立 canary 与实测一致 | 成立；宿主 root 映射见 P1-2 |
| `scoring_spec_ref` 仅为相对元数据 | 实测相对、无绝对/遍历；内容不随导出 | 成立，残余 P2-5 |
| `spec-sha256` 哈希非泄漏 | 实测出现在 evidence_refs；设计接受，但存在低熵字典面 | 文档过于绝对（P2-4） |
| Worker 文档：SIGKILL/SIGXCPU → TIMEOUT | 实现正 137 → INFRA；默认 TLE 失效 | **文档与实现相反**（P1-1） |
| NPROC=32 实测 | 实现存在且独立探针生效；测试套件无断言 | 实现成立、证据不足（P2-7） |
| B1-04 非 root principal | 宿主 uid_map 65534→0；root 运行 bwrap | 本地不成立（P1-2） |

## 6. 测试质量审计

- **真实断言**：默认策略、canonical 类型严格比较、伪造协议、真实 bwrap 隔离、112/112、负例分类均以行为/数值断言，不是单纯 grep；`test_legacy_in_process_runner_path_is_removed` 是源码断言，但仅作为辅助，另有运行时测试。
- **攻击代码执行位置**：11 个 attack templates 仅在真实 bwrap worker 中执行；`test_judge_fixture_integrity.py` 在主机 `exec` 的是 trusted reference/负例（无 attack、TLE 明确跳过），未发现把攻击代码在主机直跑。该测试的 `exec` 仍应视为 trusted-fixture-only，代码注释已标注。
- **TLE 超时**：负例/攻击 TLE 使用 0.3–0.5s（短超时），不会 hung suite；但也因此掩盖了默认 2.0s 的 CPU-vs-wall 分类缺陷（P1-1）。
- **跳过**：本机 0 skipped；所有动态测试在 bwrap 不可用时 skip（7 处），无 bwrap 的 CI 可全绿但没有 OS 证据（P1-3）。fail-closed 单测不依赖 bwrap。
- **旧测试适配**：`test_assessment_scorer.py` 仅把 CODE fixture 显式 opt-in、更新 failure_reason 前缀（`CASES_FAILED`→`JUDGE_CASES_FAILED`、`SYNTAX_ERROR`→`JUDGE_STUDENT_RE`、`TIMEOUT`→`JUDGE_STUDENT_TLE`）；断言未删除/跳过；仍验证 CORRECT/WA/PARTIAL/TLE 语义。`test_fixtures_cf.py` 将 `judge/**` 从 broad teacher-visible 扫描排除，但保留 `domains/**`+README 断言，并有专门 integrity suite；属授权范围收窄，不是删除教师可见断言。
- **轻微弱点**：`pytest.raises(Exception)` 过宽（P2-9）；NPROC/CPU 与默认 TLE 缺少直接测试（P2-7、P1-1）；泄漏测试未扫描全部认证语料 expected（P2-12）。

## 7. 明确限制与声明

- 本评审是 **LOCAL_VERIFIED**：单机、root、bwrap 0.9.0、合成 fixture；**不等于目标 CI/部署可用**。目标部署的 bwrap/userns/非 root 策略、内核差异、并发/吞吐、cgroup 限额均 `NOT_RUN`。
- **真实用户 CODE 仍 BLOCKED**：默认策略未变；开启需要人类批准 + 目标部署安全验收 + P1 动作完成。
- 本评审不覆盖 B-PR2（事务/恢复）、B-PR3（result_id 隔离）、B-PR4（domain ports）、B-PR5（E2E）；也不覆盖 M0/security/bridge/LiveGate/费用账本。
- OS sandbox 不是内核 0day/侧信道防护；bwrap 隔离不证明教学效度或评分绝对正确。
- 本文件不含 hidden expected 明文、sentinel 原值或真实凭据；所有结论用计数、状态、相对路径与指纹表示。
- `596` 历史基线、目标部署非 root bwrap、真实用户 CODE 人类批准：`NOT_RUN`。

## 8. 复现命令（本评审）

```bash
cd /root/m1b/review-pr1
git rev-parse HEAD
git status --porcelain
git diff --name-only 4706250..HEAD
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
"/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_teacher/test_judge_supervisor.py \
  tests/m1_teacher/test_judge_correctness.py \
  tests/m1_teacher/test_judge_worker.py \
  tests/m1_teacher/test_judge_sandbox.py \
  tests/m1_teacher/test_judge_negatives.py \
  tests/m1_teacher/test_judge_fixture_integrity.py \
  tests/m1_teacher/test_hidden_leakage_scan.py \
  tests/m1_teacher/test_assessment_scorer.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
# 独立探针（不提交）
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_os.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_default.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_isolation.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_forgery.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_correctness.py
"/root/Autonomous Teacher/.venv/bin/python" /tmp/pr1_probe_leakage.py
```

本评审只有本文件新增；评审提交见提交消息中的 sha。未修改任何源码/测试/既有文档，未 amend。

## 9. 评审提交

- 评审文件：`docs/M1_B_PR1_REVIEW.md`（本文件）。
- 评审提交：`git add docs/M1_B_PR1_REVIEW.md && git commit -m "docs(m1b): B-PR1 independent judge security review (no-key)"`；提交 sha 见交接消息。
- 被审冻结 HEAD：`6e20fd13a9c4ebf79188f0aac326edb074f2317b`。
