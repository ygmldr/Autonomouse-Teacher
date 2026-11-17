# M0 G3-C G0 基线冻结报告

> **状态**：G0 只读预检完成；**未开始 G3-C 修复**，不改产品代码/测试/scripts/artifacts/packet/历史 commit。
> **执行**：G3-C G0 基线冻结 Agent（受 Lead 委派）；时间 2026-11-17T11:15Z 起（UTC）。
> **范围**：任务书 §4（G0）＋任务下发要求；0 真实 Key / 0 模型调用 / 0 外部付费 HTTP / 0 Live；未 push。
> **既有裁定不变**：`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE`（限定范围，独立 Reviewer）；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`。本报告不构成 G3-C/G3-D/Live/M0 GO 的任何授权。

## 0. 结论摘要

1. **身份明确、无未解释漂移**：G0 开始时本地 `HEAD` 与远端 `main` 均为 `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`；工作区没有已跟踪文件改动，仅有两份维护者下发的未跟踪任务书。
2. **任务书原字节归档**：两份任务书已提交为 `7199058d267814ac7b180cb82bb03337552d34b1`（父 `bb5bd0b`）；提交前后 sha256 一致（见 §1.3）。
3. **源码事实**：产品 `src/`、`tests/`、`plugins/` 自 G3-B 实现 `9040292` 到 `bb5bd0b` 无任何变化；因此任务书 §1.2 的 SRC-01..SRC-12 全部仍在场。
4. **SRC 现场核对**：**12/12 `STILL_OPEN`**（SRC-12 仅静态存在、不在运行路径）；0 `ALREADY_FIXED`，0 `CHANGED_REQUIRE_REVIEW`（因为 SHA 相同，未触发差异分级流程）。
5. **环境指纹与冻结值一致**：rootfs `25491e45…`、deps `e07729d7…`、stage-b3 `74ff4bed…`、DSH runtime `1cc41d5a…`；Python 3.11.15 / Node v22.23.2；`podman ps -a` 空。无需清理任何 `__pycache__` 或 mount-target。
6. **基线测试（只作基线，不算 C 成果）**：`tests/integration/g3_bridge` **31 passed / 0 failed / 0 skipped / exit 0**；`tests/unit/security/test_gates.py` **14 passed**；`tests/unit/accounting + tests/integration/g2_closure` **280 passed**。
7. **历史 665 passed / 1 skipped 是旧证据**（G3-B OCI 全量），本轮**未重跑**，不得当作 G0 或 G3-C 结果。
8. **LiveGate 未解锁、无 Key 路径**：`run_live.sh` exit 3；`LiveGate.inspect(live_requested=True, …)` 仍返回 `BLOCKED`；bridge/run 路径仅有 AF_UNIX，无 AF_INET/HTTP/Key 引用；宿主无 Key 环境变量、无 `.env`。
9. **OS 信任边界仍 `BLOCKED`**；G0 未执行容器、未做 candidate 攻击，不改变 B0-02。

## 1. 身份核验

### 1.1 远端与本地

现场命令与结果（远端查询窗口 `2026-11-17T11:21:51Z`–`11:21:56Z`）：

```text
$ git remote -v
origin  git@github.com:ygmldr/Autonomouse-Teacher.git (fetch)
origin  git@github.com:ygmldr/Autonomouse-Teacher.git (push)
$ git config --get core.sshCommand
ssh -i /root/.ssh/github -o IdentitiesOnly=yes
$ git rev-parse HEAD            # G0 开始时
bb5bd0bf83e22130ed0d81c54f54a4673654cfe3
$ timeout 45 git ls-remote origin refs/heads/main HEAD
bb5bd0bf83e22130ed0d81c54f54a4673654cfe3  HEAD
bb5bd0bf83e22130ed0d81c54f54a4673654cfe3  refs/heads/main
EXIT=0
```

| 项 | 现场值 | 判定 |
|---|---|---|
| remote `origin` fetch/push | `git@github.com:ygmldr/Autonomouse-Teacher.git` | 与任务书仓库一致 |
| 远端 `main` HEAD | `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3` | 与任务书声称 `bb5bd0b` **一致** |
| 本地 `HEAD`（G0 开始） | `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（branch `main`） | **一致** |
| 工作区（G0 开始） | 仅 `?? docs/Autonomous_Teacher_M0_G3C_G3D_Agent_Iteration_Plan_v1.0.md`、`?? docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv` | 两份任务输入，非源码漂移 |
| 最近提交 | `bb5bd0b chore: add repository secret-scan guard and security policy (no-key)` ← `c605074 docs: archive G3-B independent review and errata (no-key)` ← `b4a2d77 docs: G3-B …` ← `9040292 fix: G3-B B3 resume …` | 与 G3-B 冻结链一致 |

### 1.2 相关提交差异

任务书声称的起点 `bb5bd0b` 与实际远端/本地完全一致，**不需要**按“远端不同”路径生成差异分级。为确认“本轮相关文件”没有悄悄变化，另行核对：

```text
$ git diff --name-status 9040292 bb5bd0b -- src tests plugins
（空，exit 0）
$ git diff --name-status 9040292..bb5bd0b -- \
    src/autoteacher_m0/bridge src/autoteacher_m0/accounting \
    src/autoteacher_m0/security spikes/g3b-trusted-bridge tests/integration/g3_bridge
（空，exit 0）
```

`9040292..bb5bd0b` 的 11 个变更文件全部是 docs、README/SECURITY、secret-scan workflow/script、`scripts/g3b/*`，**没有产品源码、测试或插件变化**。

### 1.3 任务书归档 commit（原字节）

| 项 | 值 |
|---|---|
| commit | `7199058d267814ac7b180cb82bb03337552d34b1` |
| 父 commit | `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3` |
| message | `docs: archive G3-C/G3-D iteration plan and evidence matrix (verbatim)` |
| 变更 | `A docs/Autonomous_Teacher_M0_G3C_G3D_Agent_Iteration_Plan_v1.0.md`（540 行）<br>`A docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`（67 行） |
| 未 stage 其它文件 | 是（仅上述两份） |

逐字节复核（提交前后分别计算，且从 Git blob 再算一次）：

| 文件 | 提交前工作区 sha256 | 提交后 Git blob sha256 |
|---|---|---|
| `docs/Autonomous_Teacher_M0_G3C_G3D_Agent_Iteration_Plan_v1.0.md` | `1ea37869b76e04dfe153239d9063fa5fecf8866cbc146e765a8f5678bc908001` | `1ea37869b76e04dfe153239d9063fa5fecf8866cbc146e765a8f5678bc908001` |
| `docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv` | `ef7bbd9f197c28ed57bab395545e4a2117bc3f2a20bf85393c5f441cc538751b` | `ef7bbd9f197c28ed57bab395545e4a2117bc3f2a20bf85393c5f441cc538751b` |

## 2. 漂移表

| 检查对象 | 冻结/期望值 | 现场实测 | 判定 |
|---|---|---|---|
| 远端 `main` | `bb5bd0b…` | `bb5bd0b…`（11:21:51Z 查询） | **NO_DRIFT** |
| 本地 `HEAD`（G0 开始） | `bb5bd0b…` | `bb5bd0b…` | **NO_DRIFT** |
| 已跟踪工作区 | clean | 无 `M/D/R` 项 | **NO_DRIFT** |
| 未跟踪文件 | 仅两份任务书 | 仅两份任务书，已归档 `7199058` | 预期输入，已冻结 |
| 产品源码/测试/插件 | `9040292` 冻结 | `git diff 9040292..bb5bd0b` 为空 | **NO_DRIFT** |
| `security/gates.py` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` | 同左；`git diff --quiet bb5bd0b -- …` exit 0 | **NO_DRIFT** |
| `runtime/dsh_adapter.py` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` | 同左；diff exit 0 | **NO_DRIFT** |
| `scripts/run_live.sh` | `a8a2753fd6b6b096b66adecfbdde044b42c6c4a26630c24f0fc269b1fe5f957a` | 同左；diff exit 0 | **NO_DRIFT** |
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | 同左（测试前后各一次） | **NO_DRIFT** |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同左（测试前后各一次） | **NO_DRIFT** |
| stage-b3 canonical | `74ff4bedc934e22433492fdf05f228ad1b402cdc673448875cfb03aca9789101` | 同左 | **NO_DRIFT** |
| DSH runtime binary | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（182,717,632 B，`0.2.2-rc.2`） | 同左，`--version`=`0.2.2-rc.2` | **NO_DRIFT** |
| Python | `3.11.15` | `/root/.local/bin/python3.11` = `3.11.15` | **MATCH** |
| Node | `v22.23.2` | `v22.23.2` | **MATCH** |
| 容器 | `podman ps -a` 空 | 空（exit 0） | **MATCH** |

**分级结论**：未发现需要标 `ALREADY_FIXED` / `STILL_OPEN` / `CHANGED_REQUIRE_REVIEW` 的“远端≠声称 SHA”差异；所有 SRC 的 `STILL_OPEN` 是源码事实本身（见 §3），不是漂移。

> 观察（非漂移，但需防误用）：宿主 `/usr/bin/dsh` 是 `0.2.1-rc.2`，**不是**锁定 runtime。G3-B/G3-C 必须使用 `artifacts/foundation/deps/deepseek_harness_runtime/...` 的 `0.2.2-rc.2` 二进制（`1cc41d5a…`），不得用系统 `dsh` 替代。

## 3. SRC-01..SRC-12 现场核对（当前源码 `bb5bd0b`）

> 核对方式：通读 `src/autoteacher_m0/bridge/*`、`security/egress.py`、`accounting/broker.py`、`spikes/g3b-trusted-bridge/{fake,run,src}`，并以 `grep -n` 复核行号。**未修改任何代码。**

| ID | 任务书 §1.2 入口 | 当前源码证据（file:line） | 状态 | 现场说明 |
|---|---|---|---|---|
| SRC-01 | `controller.py:98-130,333-351` | `controller.py:98-130` reconcile；`:333-340` `mark_response_observed` 持久 `receipt_json`；`:110-125` 从 `receipt_json` 取 usage、`ALREADY_SETTLED/ALREADY_FAILED` 分支 | **STILL_OPEN** | `receipt_json` 仅含 `receipt_id/raw_sha256/raw_length/mode/sent_payload_digest/observation_digest`，**不含 usage**；重启时 `usage={}` → `complete=False` → `fail`/`WORST_CASE_HELD`；若 Broker 已 `ALREADY_SETTLED` 但 journal 无完整 usage，会被记为 worst-case 而非一致 `SETTLED`。 |
| SRC-02 | `ipc_server.py:293-299` / `controller.py:187-188` | `ipc_server.py:270-300` cancel reader；`:293-298` 以 kwargs 调 `handler(transport_id=…, reason=…)`；`controller.py:187-188` `def cancel(self)`；`:297-298` 吞 `BaseException` | **STILL_OPEN** | 签名不匹配导致 `TypeError` 被吞；`self._cancel` 设置后从未在 `_handle_payload`/发送路径读取；`reason_sink` 只收集不使用。Cancel 仍为 no-op（fail-closed，但非传播）。 |
| SRC-03 | `controller.py:217-235` / `fake/fake_provider.py:81-113` | `fake_provider.py:84,87,106,112` 发 `{"kind":"usage",…}`；`controller.py:217-236` 仅处理 `receipt/chunk/finish/error`，`:233-234` `else: continue` | **STILL_OPEN** | Fake 内部 `usage` 帧被 Controller 丢弃；Broker settle 用的 `receipt.usage` 与 DSH 可见的 StreamChunk usage 不是同一条证据。 |
| SRC-04 | `controller.py:132-138,238-265` / `admission.py:105-118` | `controller.py:132-138` 只做 payload `maxTokens` 1..1024；`:170` 写入 prepared `max_output_tokens`；`:261-264` Reserve `input_tokens=min(1024, admission.max_input_tokens)`、`output_tokens=prepared.max_output_tokens`；`admission.py:56,105-118` 解析 `max_output_tokens/deadline_ms` | **STILL_OPEN** | `admission.max_output_tokens` 未与请求比较（只受 route/边界 1024 限制）；输入预留是固定 `min(1024, …)` 合成上界；`deadline_ms` 在 bridge 运行路径无任何引用（grep 仅命中 admission 定义与测试）。 |
| SRC-05 | `broker_client.py:42-54` | `broker_client.py:14-18` 保存 `timeout_s=15.0`；`:42-54` 阻塞 `self.proc.stdout.readline()`（`:52`），无 select/IO worker/超时 | **STILL_OPEN** | `timeout_s` 属性对阻塞 readline 不生效；Broker 活着但不回包时 Controller 可无限阻塞。 |
| SRC-06 | `ipc_server.py:39-70,105-116,194-208` | `ipc_server.py:39-70` `FrameReader.readline` 对 `socket.timeout` 直接 `continue`（`:58-62`）；`:104-116` accept 后无上限 append 线程；`:149` 仅 `settimeout(1.0)`；`:170` deadline 在首帧解析后才建立；`:194-208` 只在 `next()` 之间检查 deadline | **STILL_OPEN** | 首帧可被慢连接/空连接无限等待；活跃连接/线程无上界、`_threads` 不回收；同步阻塞的 `next(responses)` 不可被 deadline 中断。 |
| SRC-07 | `ipc_server.py:268,302-307` | `ipc_server.py:268` 类属性 `_last_frame_bytes=0`；`:185` `total_bytes = self._last_frame_bytes`；`:246/:307` 写入 | **STILL_OPEN** | 跨连接共享的上一帧长度被当作本连接累计响应字节的初值，相邻请求 Ack/响应会污染 1 MiB 总预算判断。 |
| SRC-08 | `controller.py:238-244` | `controller.py:240-244` `self.calls += 1` 在 `_prepare`（`:244`）之前 | **STILL_OPEN** | 无效 Schema/Route/Tool 请求会先消耗 `max_calls`，候选可用坏帧耗尽额度。 |
| SRC-09 | `protocol.py:26-40` | `protocol.py:26-40` `ERROR_CODES` 无 `CALL_ID_CONFLICT/IDEMPOTENCY_CONFLICT/ALREADY_SETTLED/ALREADY_FAILED/INVALID_USAGE`；`:290-297` `_validate_error`；`:408-411` `validate_error_payload` 对未知码抛 `UNKNOWN_FIELD`；`accounting/broker.py:197,248,263,273,290,300,354` 产生上述码；`controller.py:365-367` 原样放入 error frame；`ipc_server.py:229-235` 编码时校验 | **STILL_OPEN** | Broker 冲突码没有显式 IPC 映射；Controller 返回的未知码在 `encode_envelope` 阶段被降级为 `UNKNOWN_FIELD`，而不是确定性的 `CLAIM_DENIED`/`BUDGET_DENIED`/`INTERNAL`。 |
| SRC-10 | `controller.py:359-363`；`fake_provider.py:109-110` | `controller.py:362` `{"kind":"finish","reason":{"kind":"error"}}`（无 `failure`）；`fake_provider.py:109-110` 同样缺 `failure`；`protocol.py:271-287` 要求 `error/aborted` 必须带 `failure{message,code}` | **STILL_OPEN** | 该 finish 会被 `validate_finish_payload` 拒绝并降级为协议错误（历史上观察为 `UNKNOWN_FIELD`）；DSH 仍无成功 finish，但错误帧 schema 不合契约。 |
| SRC-11 | `fake_backend.py:52-80` | `fake_backend.py:52-80` `subprocess.run(..., stdout=PIPE, stderr=PIPE, timeout=…)`（`:60-62`）；`:74` 进程结束后一次性 `splitlines()` 解析 | **STILL_OPEN** | 不是在线 streaming；输出/帧缓冲没有逐帧上限，只有 256 KiB 输入和 10 s 进程超时；首 Chunk 不可能在 Fake 退出前到达 SDK。 |
| SRC-12 | `attempts.py:133-137` | `attempts.py:132-137` `next_logical_step(run_id)` 的 SQL 为 `SELECT COUNT(*) … WHERE call_id IN (SELECT call_id FROM g3b_attempts)`，未使用 `run_id` | **STILL_OPEN**（**不在运行路径**） | `grep -rn next_logical_step` 仅命中定义及 `artifacts/` 内归档副本，无生产调用；按任务书要求只记录 P2，不重构、不扩大范围。 |

### 3.1 状态统计

| 状态 | 数量 | ID |
|---|---:|---|
| `STILL_OPEN` | **12** | SRC-01..SRC-12（SRC-12 不在运行路径） |
| `ALREADY_FIXED` | 0 | — |
| `CHANGED_REQUIRE_REVIEW` | 0 | — |

**注意**：SRC 的 `STILL_OPEN` 与 G3-B 已通过的有限范围不矛盾；G3-B 的 PASS 是“无 Key 集成范围”，其 Errata 已明确 P1-1/P1-2/P2 等残余。基线测试全绿也不能说明这些 SRC 已修复（见 §6）。

## 4. 安全基线：LiveGate / 真实 Provider / Key / 外网

### 4.1 LiveGate 与入口

- `src/autoteacher_m0/security/gates.py:63-86`：`LiveGate.inspect()` **永远**把 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` 放进 reasons 并返回 `GateDecision("BLOCKED", …)`；`require_live()` 直接抛 `SecurityBlocked`。该类没有 `authorize()/approve()`，也没有凭据注入路径。
- `scripts/run_live.sh` 全文 5 行，固定打印阻断并 `exit 3`：

```text
$ sh scripts/run_live.sh
BLOCKED SECURITY_BLOCKED: no independent authorization/controller boundary.
Review docs/M0_RUNBOOK.md; a Markdown approval is not an execution capability.
RUN_LIVE_EXIT=3
```

- 即使显式请求 Live 且伪造“完整”诊断基线，仍为 BLOCKED：

```text
$ PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
    /root/.local/bin/python3.11 -B -c \
    "from autoteacher_m0.security.gates import LiveGate, Baseline; \
     b=Baseline('a'*64,'b'*64); \
     print(LiveGate().inspect(live_requested=True, actual=b, reviewed=b, \
       actual_tools=('skill_lookup',), session_log_disabled=True))"
GateDecision(status='BLOCKED', reasons=('EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED',), external_boundary_deployed=False)
GATE_EXIT=0
```

- `tests/unit/security/test_gates.py`：**14 passed / exit 0**（见 §6），覆盖“任何文件/环境变量/对象都不能解锁”的既有断言。

### 4.2 无 Key / 无外网路径的静态证据

执行的命令与结果：

| 检查 | 命令（摘要） | 结果 |
|---|---|---|
| bridge/spike 中 Key/Bearer/URL 模式 | `grep -rniE "api[_-]?key\|bearer \|authorization:\|sk-[a-z0-9]{10,}\|https?://" src/autoteacher_m0/bridge spikes/g3b-trusted-bridge/{src,fake,config}` | **exit 1（0 命中）** |
| 运行路径网络 API/真实 Provider | `grep -rniE "requests\.\|httpx\|urllib\|socket\.socket\(\|AF_INET\|create_connection\|https?://\|DEEPSEEK_API_KEY\|OPENAI_API_KEY\|Authorization" src/autoteacher_m0/bridge spikes/g3b-trusted-bridge/{src,fake,run,config}` | 仅命中 **AF_UNIX**（`ipc_server.py:97`、spike 的 `common.py/capture_tools.py/concurrency.py/raw_negatives.py/guard_separate.py`）及注释；**0 个 AF_INET/HTTP/Key 调用** |
| 宿主 Key 环境变量 | `env \| grep -iE '^[A-Z_]*(KEY\|TOKEN\|SECRET\|PASSWORD)[A-Z_]*=' \| cut -d= -f1` | **空输出**（只列名，不读取值） |
| `.env` | `ls -l .env` | **不存在**；`.env.example` 明示 `# DEEPSEEK_API_KEY is intentionally absent.` |
| Live 开关 / 真实 Provider | `grep -rn "LIVE\|live" src/autoteacher_m0/bridge spikes/g3b-trusted-bridge/{run,config}` | bridge 运行路径无 Live 开关；仅注释出现 |
| Adapter 目标 | `spikes/g3b-trusted-bridge/src/index.ts:29,315,454-455` | 固定 `BRIDGE_SOCKET=/work/g3b/bridge.sock`、AF_UNIX、`realModelCalls:0/httpCalls:0`；不 spawn、不读 Key |
| Bridge profile | `spikes/g3b-trusted-bridge/config/bridge.patch.yml` | 禁用 `llm-deepseek`、`session-log-deepseek`、compaction/image/tool-fs/subprocess/pty 等；只保留 bridge adapter + offline skill |
| 容器 | `podman ps -a` | 空（G0 未运行任何容器） |

**边界说明**：以上是静态 + 既有定向门禁测试 + 未启动 Live 的证据，能证明本轮 G0 没有打开 Live/Key/外网路径；它**不能**证明真实 Provider 行为、远端 exactly-once、账单准确性或 OS 信任边界。后三者不在 G0 范围且仍为 UNVERIFIED/BLOCKED。

## 5. 环境指纹与复算

### 5.1 指纹

| 对象 | 现场值 | 说明 |
|---|---|---|
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | G0 前段与测试后 `11:22:18Z` 各复算一次，一致 |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | pytest 前后各复算一次，一致；无新 `__pycache__` |
| stage-b3 canonical | `74ff4bedc934e22433492fdf05f228ad1b402cdc673448875cfb03aca9789101` | 135 MB；与 G3-B 报告一致 |
| DSH runtime bin | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`，182,717,632 bytes，`--version`=`0.2.2-rc.2` | `artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64` |
| DSH SDK wheel | `0.2.2rc2` | `deepseek_harness_sdk-0.2.2rc2.dist-info` / `deepseek_harness_runtime_bin-0.2.2rc2.dist-info` |
| Python | `3.11.15`（`/root/.local/bin/python3.11`） | 与 deps 的 cp311 匹配 |
| Node | `v22.23.2`（`/usr/bin/node`） | 与 G3-B 冻结一致 |
| podman | `4.9.3`；`podman ps -a` 空 | G0 未用容器 |
| OS | Ubuntu 24.04.4 LTS；Linux `6.17.13-2-pve` x86_64 | 宿主环境 |
| 系统 `dsh`（观察） | `0.2.1-rc.2`（`/usr/bin/dsh`） | **非锁定 runtime，禁止替代使用** |

### 5.2 canonical 复算命令

```bash
cd "/root/Autonomous Teacher"
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -cf - -C artifacts/foundation/deps . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner \
  -cf - -C artifacts/g3b-trusted-bridge/stage-b3 . | sha256sum
sha256sum artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64
```

### 5.3 清理与卫生

- rootfs/deps/stage 均与冻结值一致，**未执行任何删除/清理**。
- 未新建 `__pycache__`（所有 pytest 均使用 `PYTHONDONTWRITEBYTECODE=1` 与 `python3.11 -B`；`find src spikes tests -name __pycache__ -newermt "2026-11-17 11:14:00"` 为空）。
- 未启动容器，`podman ps -a` 空；无挂载残留、无 broker/fake 进程。

## 6. 基线测试（只作基线，不是 G3-C 成果）

全部使用宿主 CPython 3.11.15 + 锁定 deps，且强制 `-B` / `PYTHONDONTWRITEBYTECODE=1` 防止 deps 漂移：

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest <target> -q -p no:cacheprovider
```

| 目标 | 实际结果 | exit | 耗时 |
|---|---|---:|---:|
| `tests/integration/g3_bridge` | **31 passed / 0 failed / 0 skipped** | 0 | 7.35 s |
| `tests/unit/security/test_gates.py` | **14 passed / 0 failed / 0 skipped** | 0 | 0.06 s |
| `tests/unit/accounting tests/integration/g2_closure` | **280 passed / 0 failed / 0 skipped** | 0 | 21.77 s |

补充事实：

- `tests/integration/g3_bridge` 的 31 项与 G3-B B4 记录的 `b4-host-g3bridge` 31 passed 一致；`tests/unit/security/test_gates.py` 与 `b4-gates-unit` 的 14 passed 一致；但**相同计数不代表旧证据被本轮重新取得**，本轮只核验基线未回归。
- **历史 665 passed / 1 skipped 是旧证据**：出自 G3-B 的固定 OCI 全量运行（`docs/REVIEW_G3B_INDEPENDENT.md` §6.1、`docs/M0_G3B_IMPLEMENTATION_REPORT.md` §8；`b4-oci-full-pytest2`）。本轮 G0 **未重跑容器/真实 DSH**，因此该数字不得写入 G3-C 结果，也不得作为 C 的 PASS 依据。
- 历史宿主全量 `663 passed / 2 failed / 1 skipped` 同样是旧证据，两失败是宿主 staging mode 与 `/project` 硬编码的环境问题（见 Reviewer §6.2），本轮未复跑、未掩盖、未改宿主代码。
- 这些测试是 **G3-B 基线**，不覆盖 §3 的 SRC-01..SRC-12；C Agent 必须为每个修复提供新的 RED/GREEN 与原始 trace。

## 7. 本轮起点声明

- **产品代码起点**：`bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（G3-B 冻结链末端的 `chore` 提交；`src/tests/plugins` 与该链 `9040292` 完全一致）。
- **Docs 起点**：G0 任务书归档 `7199058d267814ac7b180cb82bb03337552d34b1`（父 `bb5bd0b`）；本报告单独提交为下一个 docs commit。
- **G3-C 实施必须从本 G0 冻结的 docs HEAD 出发**，但不得把 docs 提交误当作产品修复；`impl` 仍应是新的独立 commit。
- **未做**：G3-C1/C2/C3 的任何修复、任何测试新增、任何代码/测试/scripts 修改、任何 push、任何容器运行、任何真实 Key/模型/外部 HTTP/Live。
- **裁定不变**：`PASS_FOR_G3B_NO_KEY_INTEGRATION_SCOPE` 仍是限定范围的历史结论；`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；本基线**不是** G3-C PASS，也不是 G3-D 隔离能力证明。
- **G0 验收**：源码身份明确；无未解释漂移；禁网/无 Key 的宿主测试环境存在且可复算；旧 B0-02 BLOCKED 未被改成 PASS。满足任务书 §4 的 G0 出口。

## 8. 风险与后续交接

1. **SRC 全部仍未修复**：基线测试 31/14/280 全绿不改变 §3；C Agent 不应以“测试通过”声称 SRC 已关闭。
2. **P1/P2 仍有效**：P1-1（B3-08 保守 hold，非幂等 settle）、P1-2（cancel no-op）、P2-1/P2-2（Broker 错误码/finish schema）、P2-3（max_calls）、P2-4（observation 表空）、P2-5（trace 覆盖）、P2-6（并发启动抖动）、P2-7（recovery admission 契约）均未在 `bb5bd0b` 修复。
3. **测试环境限制**：宿主全量测试有 2 个已知环境失败（staging mode、`/project` 硬编码）；G3-C 全量回归应使用固定 rootfs/OCI，或明确记录宿主限制。宿主 Python 必须继续 `-B`，否则 deps 会因 `__pycache__` 漂移。
4. **运行时混淆风险**：系统 `dsh` 是 `0.2.1-rc.2`；只能用 deps 内 `1cc41d5a…` 的 `0.2.2-rc.2`。
5. **OS 边界未测**：G0 未运行容器、未做 candidate 攻击；G3-D 仍需不同 principal/namespace 与实际内核拒绝证据，不能因本轮 rootfs 哈希稳定而推断隔离成立。
6. **远端未被本轮改变**：未 push；远端仍为 `bb5bd0b`，本地新增两个 docs commit，由 Lead 统一决定推送。

## 9. 关键命令复算清单

```bash
cd "/root/Autonomous Teacher"

# 1) 身份
git remote -v
git config --get core.sshCommand
git rev-parse HEAD
git status --porcelain -uall
git ls-remote origin refs/heads/main HEAD

# 2) 保护文件与产品差异
sha256sum src/autoteacher_m0/security/gates.py \
          src/autoteacher_m0/runtime/dsh_adapter.py scripts/run_live.sh
git diff --quiet bb5bd0b -- src/autoteacher_m0/security/gates.py \
          src/autoteacher_m0/runtime/dsh_adapter.py scripts/run_live.sh; echo $?
git diff --name-status 9040292 bb5bd0b -- src tests plugins

# 3) 归档与基线 docs
sha256sum docs/Autonomous_Teacher_M0_G3C_G3D_Agent_Iteration_Plan_v1.0.md \
          docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv
git cat-file blob 7199058:docs/Autonomous_Teacher_M0_G3C_G3D_Agent_Iteration_Plan_v1.0.md | sha256sum
git cat-file blob 7199058:docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv | sha256sum

# 4) 环境
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/security/rootfs . | sha256sum
tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C artifacts/foundation/deps . | sha256sum
sha256sum artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64
/root/.local/bin/python3.11 --version; node --version; podman ps -a

# 5) 基线测试（-B 必须）
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/integration/g3_bridge -q -p no:cacheprovider
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  /root/.local/bin/python3.11 -B -m pytest tests/unit/security/test_gates.py -q -p no:cacheprovider
```

---

**STOP**：G0 完成。等待 Lead 审计后按任务书进入 G3-C；本 Agent 不开始任何 C 修复。
