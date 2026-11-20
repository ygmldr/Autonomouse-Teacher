# M1-B / B-PR1 安全评审 P1 修复复核附录（独立 Reviewer，no-key）

- 复核对象：`/root/m1b/review-pr1b`，分支 `b-next/pr1-review-addendum`，HEAD `817523344c6c421d6ce7ed15082eb064e1d2b834`（parent `62c32c5`）。
- 范围：仅复核 `62c32c5..8175233` 修复 delta，不重做整体安全评审；不覆盖 B-PR2..B-PR5、M0/security/bridge/LiveGate。
- 方式：静态审计 + 本机真实复跑 + 自写 `/tmp` 只读探针；探针只使用 synthetic 数据，不联网、不使用 Provider/Key、不执行真实恶意代码。
- 证据标签：`OWNER_REPORTED`（Owner 文档/报告，未被本评审独立证明）；`INDEPENDENTLY_REEXECUTED_THIS_TURN`（本轮独立命令/探针）；`NOT_RUN`（未执行或本机无法证明）。
- 本文件只新增本附录；不改源码/测试/既有文档/commit，不 amend；不含 hidden expected 明文、sentinel 原值或凭据。

## 0. 结论

**`P1_ACTIONS_PARTIALLY_CLOSED`**

- **P1-1 CLOSED**：默认 2.0s 死循环现为 `JUDGE_STUDENT_TLE`，慢正确解 PASS，短超时仍 TLE；过早资源 kill 仍为 INFRA。
- **P1-4 CLOSED（语义）**：无“环境变量可启用 trusted fixture”的肯定表述；实现不读该开关，运行时 env 黑盒验证仍 blocked。字面残留：威胁模型 changelog 的删除说明仍引用旧短语（P2 文本清理）。
- **P1-3 机制已关闭，强制接线未完成**：7 处原 skip 已统一；`M1B_REQUIRE_OS_SANDBOX=1` + 缺 bwrap 时 fail 而非 skip（独立模拟 0 skipped）。但仓库内没有任何 CI workflow/Makefile 设置该变量，安全 job 的实际接线为 `NOT_CONFIGURED`/`NOT_RUN`。
- **P1-2 未关闭**：报告/文档/测试已落地，本机 `non_root_principal_verified=False`、`LOCAL_ONLY`，文档不声称 B1-04 满足；但“启动时校验”未实现（无生产调用点、canary 不 fail-closed），目标部署非 root 验收 `NOT_RUN`，P1-2 原验收条件未满足。
- 未发现 P0；未发现修复引入的新 P1。修复 delta 只含 1 个 commit、15 个文件（`docs/`、`m1_teacher/`、`tests/m1_teacher/`），无 M0/保护路径。
- **本附录不构成整体集成 PASS**；真实用户 CODE 仍 **BLOCKED**，需人类批准 + 目标部署安全验收。

## 1. Git 范围与保护路径

| 检查 | 实测 | 标签 |
| --- | --- | --- |
| `git log --oneline 62c32c5..HEAD` | 仅 `8175233 fix(m1b): close B-PR1 review P1-1..P1-4 and P2 actions (no-key)` | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `git diff 62c32c5..HEAD --stat` | 15 files, +706/−80；`git diff --check` exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `git status --porcelain` | 复核开始/测试后为空（提交前仅本附录待加） | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| 保护路径 | 无 `src/`、`fixtures/`、`config/`、`scripts/`、`plugins/`、`security/`、`bridge/`、M0 路径 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| commit 范围 | `8175233^ == 62c32c5`；仅 1 个修复 commit，无 amend 痕迹 | INDEPENDENTLY_REEXECUTED_THIS_TURN |

变更文件全部为：3 个 `docs/M1_B_*.md`、`sandbox.py`/`worker.py`/`scorer.py`、9 个 `tests/m1_teacher/*`（含新增 `judge_os_gate.py`、`test_judge_ci_gate.py`）。`docs/M1_B_PR1_REVIEW.md` 在修复 commit 中未变。

## 2. 测试与静态检查实测

环境：Linux 6.17 宿主、bubblewrap 0.9.0、宿主 venv Python 3.11.15、沙箱内 `/usr/bin/python3` 3.12.3、uid=0(root)。时间：2026-11-20 UTC。

| 命令 | 实测 | 标签 |
| --- | --- | --- |
| `pytest tests/m1_teacher -q` | **703 passed in 61.57s**，exit 0，0 skipped | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `M1B_REQUIRE_OS_SANDBOX=1 pytest tests/m1_teacher -q -rs` | **703 passed in 60.99s**，exit 0；`-rs` 无 skip 行（0 skipped） | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| 定向 correctness/worker/sandbox/ci_gate | **89 passed in 27.72s**，exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| `ruff check m1_teacher tests/m1_teacher` | `All checks passed!`，exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| Owner `703 passed` 声明 | 与本轮 703 一致；Owner 的 60.86s/60.18s/64.92s 为时限波动，仅 `OWNER_REPORTED` | OWNER_REPORTED |
| 缺 bwrap 模拟（gate 未设，见 §3.3） | 32 passed, **67 skipped**, exit 0 | INDEPENDENTLY_REEXECUTED_THIS_TURN |
| 缺 bwrap 模拟（`M1B_REQUIRE_OS_SANDBOX=1`） | **8 failed, 59 errors, 0 skipped**，exit 1；67 条 “refuses to skip” | INDEPENDENTLY_REEXECUTED_THIS_TURN |

- 703 真实性可复算：修复前 674 + 新增 29（correctness +5、sandbox +3、worker +3、leakage +1、ci_gate +17）。diff 未删除测试；无 `xfail`；judge 测试中已无 `pytest.raises(Exception)` 过宽断言。
- 59 errors 是 fixture setup 中 `pytest.fail` 的 pytest 计数口径，仍使 job 非零退出，满足“不得 skip 后全绿”的目标；不是错误通过。

## 3. P1 逐项复核

### 3.1 P1-1 默认超时 TLE：CLOSED

实现要点（静态核对）：`BwrapSandbox._cpu_limit_for_timeout(wall_s)` 设置 `RLIMIT_CPU = max(10, ceil(wall)+2)`，wall timer 为主判据；`worker._is_timeout_kill` 仅把负 exit，或正 `124/137/152` 且 `elapsed >= 0.9×timeout` 判为 TIMEOUT，过早 kill 仍 INFRA。`_interpret` 已使用该分类。

独立探针 `INDEPENDENTLY_REEXECUTED_THIS_TURN`（synthetic fixtures，真实 bwrap + worker）：

| 场景 | 实测 |
| --- | --- |
| `DeterministicScorer(..., trusted_fixture_only=True)` 默认 2.0s 死循环 | `INCORRECT` / `JUDGE_STUDENT_TLE`（非 EVAL_ERROR/INFRA） |
| 默认 2.0s，`sleep(1.5)` 后返回正确值 | `CORRECT` / score 1.0 |
| 0.5s 超时死循环 | `INCORRECT` / `JUDGE_STUDENT_TLE` |
| supervisor timeout 2.0/3.0/5.0 死循环 | 全部 `TLE`、`infra_error=False`、`cases_passed=0` |
| 真实 learner 立即 self-SIGKILL（正 137，elapsed≈0.1s） | `INFRA_ERROR`（未误报 TLE） |
| 137 @0.3s / 137 @1.79s / 152 @0.2s / 124 @0.1s（timeout 2.0/0.5） | 全部 `INFRA_ERROR` |
| 137 @1.8s（timeout 2.0） | `TIMEOUT`（边界符合 0.9×） |
| 沙箱内 `resource.getrlimit(RLIMIT_CPU)`（wall 2.5s） | `[10, 10]`，CPU 限额确实高于 wall |

残留（P2，非 P1）：正信号码在 elapsed≥90% 时可能把 learner 自 kill 记为 TLE，但 TLE 仍是学生失败，不能伪造 PASS；1.5s 慢正确解对 2.0s 的余量约 0.5s，在极端负载 CI 上有 flake 风险。

### 3.2 P1-2 宿主非 root principal：未关闭（报告/文档部分完成）

独立探针 `INDEPENDENTLY_REEXECUTED_THIS_TURN`：`BwrapSandbox.security_profile()` 返回 `host_euid=0`、`host_is_root=True`、`uid_map="65534 0 1"`、`mapped_host_uids=[0]`、`sandbox_uid/gid=65534`、`sandbox_python_version=3.12.3`、`non_root_principal_verified=False`、`profile=LOCAL_ONLY`，limitation 明示本地不满足。逻辑边界探针：root host / map-to-0 / 多行含 0 / 空 map 均为 False；`1000, "65534 1000 1"` 为 True。

文档核对：威胁模型 §4.4/§4.5/§10.2、worker 文档 §4.2/§9、实现文档 §5.3/§10 均明确目标部署必须用专用非 root 账号（或单独评审 setuid bwrap），明确写 B1-04 仍 `PARTIAL`、本地 `LOCAL_ONLY`、不得声称满足。未发现“B1-04 本地已 VERIFIED”的表述。

但原 P1-2 验收要求“目标环境 `id -u != 0`、uid_map 不映射到 0、B1-04 全套复跑”，本轮均为 `NOT_RUN`。另有实现缺口：

- `security_profile()` 仅被测试调用，无 supervisor/worker/sandbox 生产调用点；`available()`/canary 不因非 root 未验证而 fail-closed。
- canary 只在 `_probe_payload` 记录 `uid_map`/`python_version`，`_verify_probe_payload` 不校验宿主 euid 或 uid_map。
- 威胁模型 §4.5 写“由 `security_profile()`/canary **校验**宿主 euid≠0、uid_map 不映射到 0”，与实际“只报告、不校验/不阻断”不一致。
- 实现文档 §13.1 把 P1-2 标为 **CLOSED** 属过度声明；更准确应为“报告与文档落地，部署验收未完成”。

结论：P1-2 **NOT CLOSED**；B1-04 仍 `PARTIAL`，非 root principal 仍 `NOT_RUN`。

### 3.3 P1-3 CI 可跳过 OS 证据：机制关闭，接线未完成

- 旧 skip 独立计数：`62c32c5` 中 6 处 `pytest.skip` + 1 处 `@pytest.mark.skipif` = **7 处**；修复后 judge 测试中已无独立 `pytest.skip`，7 处均改走 `judge_os_gate.require_os_sandbox`（sandbox 另新增 1 处 security_profile gate）。
- 独立模拟（`/tmp` pytest plugin 将 `BwrapSandbox._run_probe` 替换为 `SandboxUnavailable`）：
  - gate 未设：32 passed / 67 skipped / 0 failed（普通单测 CI 的合法 skip 保留）。
  - `M1B_REQUIRE_OS_SANDBOX=1`：**8 failed / 59 errors / 0 skipped**，exit 1；67 条 skip 条件全部转为 “refuses to skip”。满足“必须 fail 而不是 skip”。
- **未完成**：仓库 `.github/workflows/` 只有 `secret-scan.yml`，无测试/security job，也无 Makefile/脚本设置 `M1B_REQUIRE_OS_SANDBOX=1`；文档仅给命令。若外部安全 job 不设该变量，普通 `pytest` 仍会 skip 全部 OS 证据。该环境变量门禁是 opt-in 机制，不是仓库内强制接线；安全 job 实际执行 `NOT_CONFIGURED`/`NOT_RUN`。

### 3.4 P1-4 文档“环境变量可启用 trusted fixture”：CLOSED

独立 `INDEPENDENTLY_REEXECUTED_THIS_TURN`：

- 全 `docs/*.md` 扫描“环境变量”相关行 11 条；仅否定/历史评审/无关 M0/SDK 条目，无肯定“env 可启用 trusted fixture”表述。首轮“代码内显式参数 + 环境变量”并列的旧句已不存在；新短语 `由可信构造/部署参数开启` 存在；`实现不读取任何环境变量开关` 存在。
- **字面残留（P2）**：威胁模型 changelog v0.3（line 717）仍有删除说明引用“环境变量 + 开启 trusted fixture”旧句。它是历史删除记录、不是能力声明，但按“全 docs 无该短语”的字面验收会命中；建议改写为“删除环境变量开关表述”。新增 docs lint 只匹配另外两个精确串，未覆盖此句。
- 运行时：设置 `M1B_TRUSTED_FIXTURE_ONLY=1`、`M1_TEACHER_TRUSTED_FIXTURE_ONLY=1`、`M1B_ENABLE_CODE_EXECUTION=1` 后，默认 scorer 仍 `EVAL_ERROR:UNTRUSTED_CODE_EXECUTION_BLOCKED`，worker 调用 0 次；默认 supervisor 仍 `UNTRUSTED_CODE_EXECUTION_BLOCKED`，worker 调用 0 次。
- 静态：`m1_teacher/` 中无 `M1B_TRUSTED*`/`TRUSTED_FIXTURE_ONLY` env 读取点；仅有测试/评审文档引用。
- 残留（P2）：新增 docs lint 只按两个精确短语扫描 `docs/*.md` 顶层，不覆盖 README/子目录/同义改写；属弱守卫，不是安全控制。

## 4. P2 抽查（按首轮编号）

| 编号 | 复核结果 | 说明 |
| --- | --- | --- |
| P2-1 协议上限/多行 | **PARTIAL** | §4.3 已改 128 KiB + 拒绝多行，协议实测两行→`WorkerProtocolError`、超限→拒绝；但威胁模型 §3.1（line 209）仍写“只取第一行；后续字节丢弃”，与实现/§4.3 矛盾。 |
| P2-2 文档状态 | **PARTIAL** | 状态已改 `DESIGN + IMPLEMENTED_LOCAL_VERIFIED`；但威胁模型头部“版本：v0.2”未随 changelog v0.3 更新，实现文档“设计依据 v0.2”亦旧。 |
| P2-3 clearenv env/pin | **PARTIAL（Owner 已承认）** | worker 固定 `PYTHONHASHSEED=0`/`PYTHONDONTWRITEBYTECODE=1`，测试断言精确；沙箱内实测两变量生效（`LC_CTYPE`/`PWD` 仍可见）；解释器版本 pin 仍未实现。 |
| P2-4 spec-sha256 | **ADDRESSED** | 成功 CODE 的 `evidence_refs` 实测仅 `item:<id>`，无 `spec-sha256`；`_spec_digest` 仅内部变量，未进入结果。 |
| P2-7 NPROC/CPU 证据 | **PARTIAL（Owner 已承认）** | 新增 CPU/wall 分类单测；`RLIMIT_NPROC=32` 套件级 fork 压力测试仍无。 |
| P2-9 过宽异常断言 | **ADDRESSED** | judge 测试中 `pytest.raises(Exception)` 为 0；已收窄为 `ValidationError`/`WorkerProtocolError`。 |
| P2-10 timeout 上限一致性 | **ADDRESSED** | scorer 5.0 接受、5.0001 拒绝；supervisor 5.0 接受、5.0001 拒绝；worker 同；协议 `MAX_TIMEOUT_MS=5000`。 |
| P2-11 demo/cli 表述 | **ADDRESSED** | demo/cli 注释明确无 CODE 执行、无请求/CLI 开关；实现文档 §9 与修正后表述一致。 |
| P2-12 认证 expected 指纹 | **PARTIAL** | 新增 112 expected canonical SHA-256 对 CLI `--demo --json` 扫描；result/history 直扫仍以 synthetic sentinel 为主。 |
| P1-4 字面残留 | **P2** | 威胁模型 changelog 的删除说明仍字面引用旧短语；语义无关，但按字面验收会命中，建议改写并加 lint 覆盖。 |
| P2-5/P2-6/P2-8 | **RECORDED** | 威胁模型/实现文档已列残余风险；不阻断本地评审。 |

## 5. 新风险与测试质量

- **worker tmp 前缀**：改为 `m1b_judge_worker_<pid>_` 后，并发进程不再碰撞；相关测试同步使用 `WORK_DIR_PREFIX`。副作用是“临时目录残留”断言只观察本进程前缀，跨进程残留检测变弱；且挂载源路径多暴露一个宿主 PID（低风险，属 P2-8 路径面），不构成安全回退。
- **sandbox.command 注释陈旧**：`sandbox.py:411-413` 仍称 `extra_env` 只用于 canary、正常 worker 不传 env；实际 P2-3 已在正常 worker 传两个固定变量。属注释不一致（P2）。
- **diagnostic 测试改动**：`test_behaviour_unchanged_without_hidden_scoring_directory` 从 objective 全 dict 相等改为排除 `created_at` 后比较。`created_at` 是加载时 wall-clock 元数据，属合理 flake 稳定化；但确实减少了断言面，记录为 P2 测试质量项，不影响 PR1 安全结论。
- **CPU rlimit 提高到 min 10s**：wall timer 仍为主判据；短 timeout 下 CPU 限额不再提供 2s 级 CPU 上限，但 wall kill + NPROC=32 + pidns 仍约束。残留 CPU 消耗风险为 P2 纵深，不是新 P1。
- **文档 lint 弱点**：P1-4 测试仅匹配精确短语且只看 `docs/*.md`；P1-2 的“校验”措辞未被测试覆盖。建议后续改为语义/关键句断言。
- **无弱化通过**：无新增测试用例级 skip/xfail 标记；无删除既有安全断言；703 计数真实；定向 89 passed；ruff 0。

## 6. B1 状态更新建议

| 项 | 建议状态 | 理由 |
| --- | --- | --- |
| B1-01/02/03/06 | `VERIFIED (LOCAL_ONLY)`（维持） | 修复未触碰这些路径；本轮全量/定向复跑通过。 |
| B1-04 | `PARTIAL`（维持，补充 LOCAL_ONLY 注记） | 宿主 root、uid_map `65534 0 1`；非 root principal 无 enforcement；目标部署 `NOT_RUN`。 |
| B1-05 | 建议 **`VERIFIED (LOCAL_ONLY)`** | P1-1 默认 TLE/慢正确解/短超时已独立复现；112/112 由 correctness 套件通过；目标部署延迟/并发仍 `NOT_RUN`，不得视为生产 PASS。 |

## 7. 残留动作与 NOT_RUN

**P1 残留：**

1. P1-2：实现启动期 fail-closed 或明确“只报告不校验”的文档修正；在目标非 root 部署复跑 `id -u != 0`、uid_map 不含 0、B1-04 全套。当前不可标 CLOSED。
2. P1-3：把 `M1B_REQUIRE_OS_SANDBOX=1` 接入仓库内 security job/Makefile，并留存 0 skipped 证据；否则该风险仅由外部约定兜底。

**P2 残留：**

3. 修正威胁模型 §3.1 “只取第一行”旧表述（P2-1）。
4. 同步威胁模型头部版本 v0.2→v0.3、实现文档设计依据版本（P2-2）。
5. 将 112 expected 指纹扫描扩展到 result/history 直出（P2-12）；补解释器版本 pin（P2-3）、NPROC 压力测试（P2-7）。
6. `test_diagnostic_engine` 的 `created_at` 排除属可接受 flake 修复，但建议加注释/独立断言确认仅时间字段变化。
7. 改写威胁模型 changelog 中引用旧句的删除说明，避免字面 grep 命中（P1-4 字面残留）。

**NOT_RUN：** 目标部署非 root 服务账号 / setuid bwrap 策略；真实 security CI job；内核/userns 差异、cgroup v2、并发/吞吐/延迟；真实用户 CODE 人类批准与目标部署验收。

## 8. 声明

- 本轮仅新增 `docs/M1_B_PR1_REVIEW_ADDENDUM.md` 并提交；未修改源码/测试/既有文档，未 amend。
- 本附录是 **P1 修复 delta 复核**，不构成 B-PR1 整体安全 PASS，也不构成 B-PR2..B-PR5、M0/security/bridge/LiveGate 或整体集成 PASS。
- 真实用户 CODE 仍 **BLOCKED**；`LOCAL_ONLY` 证据不能替代目标部署验收与人类批准。
- 本文件不含 hidden expected 明文、sentinel 原值、真实凭据或攻击代码。

## 9. 复现命令（本轮）

```bash
cd /root/m1b/review-pr1b
git log --oneline 62c32c5..HEAD
git diff 62c32c5..HEAD --stat && git diff --check 62c32c5..HEAD
git status --porcelain
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q
M1B_REQUIRE_OS_SANDBOX=1 "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher -q -rs
"/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/m1_teacher/test_judge_correctness.py \
  tests/m1_teacher/test_judge_worker.py tests/m1_teacher/test_judge_sandbox.py \
  tests/m1_teacher/test_judge_ci_gate.py -q
"/root/Autonomous Teacher/.venv/bin/python" -m ruff check m1_teacher tests/m1_teacher
# /tmp 探针（不提交）：pr1b_probe_p1_1.py / p1_2.py / p1_4.py / p2.py；
# 缺 bwrap 模拟：PYTHONPATH=/tmp/pr1b_plugins ... -p pr1b_missing_bwrap；
#   M1B_REQUIRE_OS_SANDBOX=1 ... -rs
```

## 10. 提交

- 本附录：`docs/M1_B_PR1_REVIEW_ADDENDUM.md`。
- 提交命令：`git add docs/M1_B_PR1_REVIEW_ADDENDUM.md && git commit -m "docs(m1b): B-PR1 review P1-closure addendum (no-key)"`；提交 sha 见交接消息。
