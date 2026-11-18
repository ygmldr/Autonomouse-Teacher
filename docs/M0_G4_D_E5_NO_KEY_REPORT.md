# M0 G4-D — 外部 Watchdog、撤销与 E5 无 Key 子集报告（No-Key）

- **任务**：G4-D（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §7、§8、§10、§12、§13、§14；矩阵 G4-D-01..15）
- **执行者**：G4-D Watchdog / Revocation / E5-NoKey Agent（独立实现 Agent；不是 Reviewer）
- **实现 HEAD**：`d3d429cf9d0cb1e9dbc68317928631db413be309`（父链 `d8a8dc8` → `718b44e` → `4622389` → `0975412` → `2019c49` → `d8e71a8` → `d3d429c`）
- **G4-D Stage**：`artifacts/g4/c/stages/stage-20261118T193401Z`，`base_sha = d3d429c…`，manifest `85353018…17de48`，tree `9c9ce313…358762b`
- **环境**：宿主 root（CT101），host CPython **3.12.13** + pytest **9.1.1**（离线 uv 缓存缺 `iniconfig`，未能建 3.11 venv；未联网）；Podman 4.9.3；crun；`run_live.sh` 以 `/bin/sh` 调用（文件本身 0600，未改动）
- **性质**：**no-key / no-model / no-network / no-`podman pull` / no-Live**。真实双主体容器只使用冻结 canonical rootfs 与 Fake Provider；`real_model_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`LiveGate=BLOCKED`、`run_live.sh exit=3`。
- **本报告不是**授权、不是 G4 PASS、不是 E5-PreLive Full、不是 Live 批准；`E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT` 固定不变。

---

## 0. 裁定摘要

| 项 | 结果 |
|---|---|
| G4-D-01..15 | **12 PASS / 2 PARTIAL（D05、D09）/ 1 UNVERIFIED（D13，registry 本身）**；无 FAIL |
| 外部 Watchdog | 真实独立进程（host PID 级），SIGTERM→有界 SIGKILL→`/proc` 复查→`podman ps -a` 复查→UDS/run-dir/rootfs-target `lstat` 复查；`rm -f` 返回 0 从不当作 absence |
| 真实双主体 L2 run | 6 次（D01 kill、D02 hang、D03 完整 echo、D08a/D08b 故障注入、D15 同 UID 攻击），每次均记录 argv/UTC/exit/uid_map/mountinfo/socket-peercred/cleanup/absence |
| 容器终态 | `podman ps -a` **空**；rootfs `25491e45…`、deps `e07729d7…` 与 canonical 完全一致 |
| 哨兵 | 真实运行面 + 证据 + docs + tests + 既有 packet 共 **8815 文件 0 命中**（运行期 8804 + 最终复核含 JUnit/packet）；扫描器正控必须命中；Candidate env/argv/mount/`/proc` 0 明文 |
| 撤销 / epoch | 撤销后未来 dispatch 全拒绝、单次使用记录不增；pending attempt 保持 `ATTEMPT_STARTED`、第二次 `begin_attempt` 拒绝；跨 epoch ticket 拒绝 |
| Live 入口 | `run_live.sh=3`、CLI `--live=3`、Adapter `SECURITY_BLOCKED`、`LiveGate=BLOCKED`，即使 env 注入假 Key/代理/审批 flag 也不变 |
| 回归 | g4_a/b/c **339 passed**；g3c/g3d/g3_bridge/unit-security **404 passed, 1 failed**（已知 frozen-src 断言，见 §10）；g4_d **26 passed** |
| ruff（ pinned 0.17.5） | 全部新增/修改文件 `All checks passed!` |
| STOP 条件 | 未触发；**STOP，不进入 G4-E** |

---

## 1. 基线与改动边界

### 1.1 起点

| 项 | 值 |
|---|---|
| 起点 HEAD | `4521561`（G4-C 完成），工作区 clean |
| 起点 stage | `stage-20261118T174947Z`（G4-C，base `3fd0d85`）——G4-D 未复用该 stage 作为本次证据，而是按 G4-C builder 在 G4-D HEAD 重建 |
| G4-A/B/C 合同 | 只读引用；未修改 `gates.py`、`run_live.sh`、`dsh_adapter.py`、DSH 核心、G4-A/B/C 合同或历史证据/Packet |

### 1.2 本包改动（全部为最小增量）

| 文件 | 内容 |
|---|---|
| `src/autoteacher_m0/security/watchdog.py` | **仅新增** `ProcessAbsenceReport`/`PathAbsenceReport`、`confirm_process_absence`、`confirm_path_absence`、`scan_marked_processes`，并把 engine 查询超时/不可用稳定映射为 `WatchdogViolation`；`ExternalWatchdog` 既有状态机未改 |
| `scripts/g4/watchdog_runner.py` | 新增：Candidate/Trusted 之外的真实外部监管进程（kill/absence/freeze/cleanup/证据） |
| `scripts/g4/launch_d.py` | 新增：复用未修改的 `G4CLauncher` 的 hold-open 驱动；**故意不做 in-process cleanup/evaluate**，teardown 归外部 watchdog |
| `scripts/g4/secret_sentinel_probe.py` | 新增：显式根/pid 的字节级哨兵扫描 + 正控；只输出路径/偏移/计数，不输出命中上下文 |
| `scripts/g4/e5_probe.py` | 新增：P01..P05、D05/D06/D07/D15 的 host 级探针（调用真实产品代码与真实冻结 stage 字节） |
| `scripts/g4/run_g4_d.py` | 新增：D01..D15 用例编排、容器冻结/故障注入、人工清理、证据汇总 |
| `scripts/g4/probes/g4d_candidate_iso_probe.py` | 新增：在真实 Candidate 容器内经 `podman exec` 执行 known-path 探测 |
| `tests/integration/g4_d/**` | 新增 26 个 host 契约测试 |

### 1.3 实现期发现并修复的自身缺陷（RED→GREEN，均有真实复现）

| ID | 缺陷 | 复现 | 修复后证据 |
|---|---|---|---|
| F1 | 用 `podman pause` 注入 hang 后，若进程已被杀，容器会卡在 `paused/container state improper`，`rm -f` 无法删除 | D02 首轮：容器残留、后续 watchdog 全部 preflight 失败、rootfs 出现空 `g4c` 目录 | 改为 host 侧 `SIGSTOP` 容器 init（`state=T` 复核），`rm -f` 必可回收；D02 终态容器空 |
| F2 | `podman inspect` 输出被 8 KiB 截断导致 JSON 解析失败，`uid_map/mountinfo/cgroup` 证据为空 | D01 首轮 `containers-up.json` 无 inspect/proc | `cmd(max_stdout=1 MiB)`；D01/D15 现记录 pid/uid_map/mountinfo/cgroup limits |
| F3 | `min(value, RLIM_INFINITY=-1)` 使 rlimit soft 变成 infinity，CPU/AS/NOFILE 限制实际未生效 | D09 首轮 CPU 20 s 未杀、AS/NOFILE “通过”是假通过 | 显式处理 `RLIM_INFINITY`；CPU `-24`、AS `1`、NOFILE `2` 真实发生 |
| F4 | 从 `podman exec` 的 PID namespace 内 `os.kill(1,SIGSTOP)` 未真正停止 init（实测状态仍 `S`） | D02 第二轮仍完成一次 send | watchdog 改为对 host `/proc/<container-init>` 发 `SIGSTOP` 并读 `/proc/<pid>/stat` 复核 `T` |
| F5 | `/proc/<pid>/environ` 以 NUL 分隔，按行解析只得到首个变量名 | D03 首轮 `env_names=['PYTHONPATH']` | 按 NUL 切分；D03 Candidate 现列出 11 个真实变量名 |

> F1–F5 属于本包新增工具的缺陷，不是产品安全缺陷；修复提交为 `718b44e`、`4622389`、`0975412`、`2019c49`、`d8e71a8`、`d3d429c`。`d8a8dc8` 是任务要求的 `feat:` 提交；后续为真实运行暴露的修正与证据卫生修正，未 amend。

---

## 2. 外部 Watchdog：真实进程与不变量

**部署形态**：`watchdog_runner.py` 是宿主独立进程，`start_new_session=True` 启动被监管对象（`launch_d.py`/`launch_c.py`），自身不属于 Candidate/Trusted 容器，也不是 Candidate 内守护线程。它拥有：

1. **deadline/up 触发**：总 deadline、容器 up 后 kill-after；每次 poll 重新读 `podman ps -a`（0.25 s 节流），不依赖目标自报。
2. **终止**：`kill_process_tree` 对 ppid 树 + pgid 发 SIGTERM → 有界 grace → SIGKILL；随后按 run_id/run_dir/容器名/entry 文件名扫描 argv/environ/cwd，杀掉 setsid/双 fork 逃逸进程；最后逐个 `/proc` 复查（zombie 视为已退出）。
3. **容器 absence**：对每个本 run 容器 `podman kill -s KILL` + `rm -f`，然后 `podman ps -a` **全表**复查为空、再 `podman inspect <name>` 必须失败；`rm -f` rc=0 单独 **不** 构成 absence。
4. **路径 absence**：socket 仅在“root-owned 且确为 socket”时 unlink，然后 `lstat` 复查 ENOENT；run-dir 用 `safe_delete_tree`（先复制 state/DB 到证据）后复查 ENOENT；rootfs 空 mount-target 目录（`g4c`）只有“root-owned、空目录”才 rmdir 并复查。
5. **失败闭合**：任一 observation 失败 → `FAIL_CLOSED`、exit 4、保留 `manual_cleanup` 命令；watchdog 自身异常 → exit 6 且仍先终止/清理；podman 查询失败 → 不声称 absence，exit 4/7。
6. **账本保守**：每次 kill/hang 都写 `pending.json`：`PENDING_CONSERVATIVE`、`retry_allowed=false`、`worst_case_reserved=true`；从不自动重发。

**证据形态**（每次 run，`artifacts/g4/e5/runs/<case>/watchdog/`）：
`watchdog.json`、`watchdog.txt`、`commands.jsonl`、`preflight.json`、`target.json`、`logs/target.{stdout,stderr}.txt`、`snapshots/containers-{up,pre-kill}.json`、`snapshots/socket-*.json`、`proc/<phase>/*-{uid_map,mountinfo,status,cgroup,cmdline}`、`live/surfaces.json`、`probes/exec-*.json`、`cleanup/{kill,escaped-processes,container-absence,injection,run-dir-delete}.json`、`absence/processes.json`、`run-copy/state/**`、`run-copy/ledger-summary.json`、`pending.json`。

### 2.1 D01 — 真实 Candidate+Trusted 进程树 kill、OS absence、无重试

- run_id `g4d-d01-20261118T193417Z`；`19:34:17Z → 19:34:24Z`；watchdog exit **0**，`status=PASS`，`reason=WATCHDOG_DEADLINE_AFTER_UP`，target exit `-15`。
- 容器：`at-g3d-trusted-…` + `at-g3d-candidate-…` 均被记录、`kill -s KILL`、`rm -f`；`ps -a` after = **[]**；两容器 `inspect` 均 exit 125（不存在）。
- 进程：kill 信号 1 次（root pgid），`survivors=[]`；absence 复查 pids `[1094491, 1094689, 1094801]`（launcher + trusted init + candidate init）全部 absent，`proc_entries=[]`；逃逸扫描 0。
- Socket：pre-kill `present=true`、`mode=0660`、`uid=0`、`gid=2000`、client-observed `SO_PEERCRED pid=1094689 uid=0`（root 客户端；server 侧 candidate uid 由同 run trusted peercred 证据给出）；kill 后 `lstat` ENOENT。
- run-dir：14 files / 9 dirs 删除，复查 ENOENT；rootfs target `g4c`（`0o1755 root`，空）删除并复查 ENOENT。
- 账本：`g3b_attempts=0`、`g3b_send_intents=0`、`budget_reservations=0`、send journal 不存在；`pending=PENDING_CONSERVATIVE, retry_allowed=false`；**无自动重发路径**。
- check：**24/24 PASS**。

### 2.2 D02 — Trusted hang + 真实 deadline/清理

- run_id `g4d-d02-20261118T193424Z`；`19:34:25Z → 19:34:36Z`；watchdog exit **0**，`reason=WATCHDOG_DEADLINE_AFTER_UP`，target exit `-15`。
- 注入：`host-sigstop-container-init`，target = trusted init pid，`/proc/<pid>/stat` 复核 `state=T`，`verified=true`；**未使用** `podman pause`（F1）。
- 真实 Candidate `valid` probe 在 trusted UDS 上被挂起；watchdog 在 up+8 s 触发 kill；因 trusted 从未处理该请求，本次 run 的 `g3b_attempts=0`、`g3b_send_intents=0`、`budget_reservations=0`、无 receipt（**没有把“零账本”伪装成已发送**）。
- 清理：两容器 `rm -f` 成功、`ps -a` after=[]、inspect 125；absence 复查 `[1095234, 1095536]` 全部 absent；run-dir/socket/rootfs-target 复查 ENOENT；23/23 checks PASS。
- “既有 in-flight Attempt 保守、不重发”的账本层证据由 D05 的真实 `AttemptJournal` 用例补齐（§5）。

### 2.3 D08 — 注入 cleanup 失败 / podman 查询失败（fail-closed，人工介入）

| 子用例 | 注入 | 结果 | 关键证据 |
|---|---|---|---|
| D08a | `podman` 包装器：`rm` 恒返回 0 但**不删除**，`ps` 说真话 | watchdog **exit 4 / FAIL_CLOSED**；失败 check：`containers_absent_after_rm` + 两容器 `inspect_absent_*`；pending 保守 | `runs/d08a/watchdog/cleanup/container-absence.json`；`manual-cleanup.json` 由操作者显式 `podman rm -f`，`remaining_after=[]` |
| D08b | 包装器：枚举型 `ps --format {{.ID}}` 返回 125（daemon 查询失败），preflight `{{.Names}}` 正常 | watchdog **exit 4 / FAIL_CLOSED**；失败 check：`poll-ps_query_ok`、`cleanup-ps-*-query_ok`、`containers_absent_after_rm`；**不声称 absence** | `runs/d08b/watchdog/commands.jsonl`；`manual-cleanup.json` 发现并删除两容器，`remaining_after=[]` |

两次注入后均由 `run_g4_d.py` 记录 **operator_action=true** 的人工清理与二次复查；最终 `podman ps -a` 空。这说明“清理失败必须暴露 BLOCKED + 保留 trace + 人工介入”，而不是自动重试或伪造成功。

### 2.4 D09 — CPU/pids/memory/nofile 限制

真实 OS 观测（watchdog 对 target 施加 rlimit，非模拟）：

| 项 | 设置 | 观测 | 状态 |
|---|---|---|---|
| CPU | `RLIMIT_CPU=1s`（hard=∞） | target exit **-24**（SIGXCPU） | PASS |
| 地址空间 | `RLIMIT_AS=512 MiB`，target 申请 1.5 GiB | target exit **1**（捕获 `MemoryError`） | PASS |
| 文件描述符 | `RLIMIT_NOFILE=64`，target 打开 200 个 | target exit **2**（`EMFILE`） | PASS |
| 进程数 | `RLIMIT_NPROC=16`（host root） | target exit 0；**root 不受 NPROC 限制** | **UNVERIFIED** |
| 容器 cgroup | 真实 D01 双主体 | candidate/trusted `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000`、`PidsLimit=256` | PASS |

D09 因此标 **PARTIAL**：CPU/AS/NOFILE 与容器 cgroup 限制实测生效；NPROC 明确 `UNVERIFIED`，未用容器 `--pids-limit` 冒充 host `RLIMIT_NPROC`。

---

## 3. D03/D04 — 哨兵边界与扫描

### 3.1 方法

- 唯一哨兵值为任务书 §7.2 指定的明显非真实值；**本报告不复写该值**，其唯一定义在 `scripts/g4/secret_sentinel_probe.py`，运行时只写入 repo-external 的 `artifacts/g4/e5/fixtures/trusted/sentinel.txt`（root 0600）。绝不从 `os.environ`、`~/.config`、宿主 Key 管理器读取。
- 扫描器按**原始字节**比较 JSON/JSONL/SQLite 页/JUnit/日志；命中只输出 path/offset/count，不输出上下文；`--self-test` 正控必须命中，否则结果不算 clean。
- 排除项（写死在 `run_g4_d.py`）：哨兵 fixture 本身、`scripts/`（扫描器源码必须含该常量）、以及归档任务书中**定义**哨兵名的那一段；这些都是“定义处”，不是传播面。

### 3.2 D03 真实双主体传播面（D03 run = 完整 c01 echo，launcher PASS 21/21 checks）

| 面 | 证据 | 结果 |
|---|---|---|
| Candidate env | live `/proc/<candidate-init>/environ`（NUL 解析） | 11 个变量名：`DSH_RESOURCE_CACHE, DSH_RUNTIME_MODE, HOME, HOSTNAME, NARB_NATIVE_CACHE_DIR, NO_COLOR, PATH, PKG_NATIVE_CACHE_PATH, PYTHONDONTWRITEBYTECODE, PYTHONPATH, TMPDIR`；哨兵 0；无 Key/代理名 |
| Candidate argv | `runs/d03/launcher/run/argv-candidate.json` | 无哨兵；`--network none`；mount 仅 stage/deps/passwd/group/candidate-session/ipc |
| Candidate mount | live mountinfo + argv mounts | 无 trusted fixture/state/Key 路径；哨兵 0 |
| Candidate `/proc` | environ/cmdline/mountinfo | 0/0/0 |
| Session / tool output / logs | launcher session、candidate stdout/stderr、trusted log | 0 |
| Broker log / Receipt | `run/g4c-egress.json`、`receipt/rcpt-*.json`、DB | 0 |
| JUnit / docs / 既有 packet | 见 §3.3 | 0 |
| **正控** | 临时文件写入哨兵 + 伪造 broker log | 扫描器命中 ≥2 且 `clean=false`（证明不是“永远干净”） |

D03 结果：**PASS（L2 真实双主体）**。未主张：真实人类 Key 保护、真实出站 TLS/账单（E5-P05 FULL 仍 BLOCKED）。

### 3.3 D04 全量扫描结果

- roots：`artifacts/g4/e5/runs/**`、`artifacts/g4/c/runs/**`（G4-C 复用证据）、`docs/**`、`tests/integration/g4_d/**`、既有 `artifacts/review-packet-*`（若存在）。
- 运行期扫描（`run_g4_d`）：**8804 个常规文件，命中 0，`clean=true`，正控 `control=true`**；
  最终复核（含 JUnit 与既有 11 个 review-packet 根、已写入的 docs/matrix）：**8815 个常规文件，命中 0**；
  无 missing root；JSON 见 `runs/scan/sentinel-scan.json` 与 `final-sentinel-scan.json`。
- Session/Receipt/日志/JUnit/Packet：G4-D 不构建正式 Packet（G4-E 职责），故 Packet 列记 `NOT_BUILT`；既有 packet 若存在则已被同一字节扫描覆盖。JUnit 在回归阶段生成后再次纳入最终扫描（§10.3）。

---

## 4. D05/D06 — 撤销与 epoch

### 4.1 D05 撤销 + pending in-flight（`runs/d05-revocation/host/d05-revocation.json`）

用真实产品代码 `load_execution_authorization` / `consume_execution_authorization` / `AttemptJournal`，TEST_ONLY 签名，repo-external 文件：

| 断言 | 结果 |
|---|---|
| 首次 consume 写入单次使用记录（0600） | 通过 |
| 写入 `revocations=[auth_id]` 后 `load` | 拒绝，理由含 `AUTHORIZATION_REVOKED` |
| 撤销后再次 consume（新 epoch） | `AuthorizationRejected`，`AUTHORIZATION_REVOKED` |
| use-log 记录数 | 保持 1（撤销不产生第二次消费） |
| 既有 attempt | `state=ATTEMPT_STARTED`、`pending_attempts=1`、行内容不变 |
| 同 call_id 第二次 `begin_attempt` | `ValueError: ATTEMPT_ALREADY_STARTED` |
| DB | `g3b_attempts=1`、`receipt_id IS NULL` 的行数 1、无新 send |

**状态：PARTIAL**。原因不是逻辑失败，而是 G4-C 合成 controller 不消费“人类 authorization 文件”，因此不存在可在容器内撤销的真实人类票据；撤销语义在真实产品 authorization/attempt 层已证明，端到端“人类撤销文件 → 运行中容器”属于 G4-H 部署项。

### 4.2 D06 run epoch / stale approval（`runs/d06-epoch/host/d06-epoch.json`）

| 断言 | 结果 |
|---|---|
| 同一 `TrustedSendGate` 改变 `auth_epoch` 后消费旧 ticket | `AUTH_EPOCH_MISMATCH` |
| 新 run 的 gate 消费旧 run ticket | `AUTHORIZATION_UNKNOWN`（无法花旧预算） |
| 授权契约：epoch A consume 后 epoch B 复用同一 authorization | `AUTHORIZATION_EPOCH_MISMATCH` |
| gate journal | epoch 拒绝被记账（`decision=AUTH_EPOCH_MISMATCH`） |

**状态：PASS（L1-HOST；L2 不适用）**。理由：`TrustedSendAuthorization` 只存在于进程内存（`_issued` 按对象身份注册），跨进程/跨 run 根本不共享票据；因此“新 run 用旧票据花钱”在结构上不可达，测试直接验证了产品代码的 epoch 检查与 journal。

---

## 5. D07 — 假 Secret 不打开 LiveGate

`runs/d07-live/host/d07-live.json`（child env 注入 `DEEPSEEK_API_KEY`/`OPENCODE_API_KEY`=TEST_ONLY 哨兵、`HTTP(S)_PROXY`、`AT_M0_LIVE_APPROVED=1`、`AUTOTEACHER_LIVE=1`）：

| 入口 | 结果 |
|---|---|
| `gates.LiveGate.inspect(live_requested=True, …全部可诊断证据满足)` | `BLOCKED`，恒含 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` |
| `scripts/run_live.sh`（`/bin/sh`） | exit **3**，stderr `BLOCKED` |
| `python -m autoteacher_m0.cli smoke --live` | exit **3**，JSON `status=BLOCKED` |
| `HarnessAdapter._require_live_authorization()` | `RuntimeFailure(SECURITY_BLOCKED)` |
| Markdown `APPROVED` 文件 / 自签 JSON | 不改变 gate |
| `gates.py` 静态 | 无 `os.environ` / `getenv` / `open(` |
| 计数 | `real_provider_calls=0, real_external_http_calls=0, provider_keys_seen=0, billable_send_allowed=0` |

**状态：PASS**。

---

## 6. D15 — 旧 Run 同 UID 已知路径攻击

### 6.1 真实 Candidate 容器内（`runs/d15/watchdog/probes/exec-candidate.json`）

`podman exec` 以容器 root（host uid 65534）执行 known-path 探测：

| 目标 | 结果 |
|---|---|
| `run_dir/state/controller.json`（新 run 可信状态） | `ENOENT` |
| `run_dir/state/injected.json` 写入 | `ENOENT` |
| `run_dir/state/` 列目录 | `ENOENT` |
| trusted 哨兵 fixture 绝对路径 | `ENOENT` |
| 旧 run（d01）已知绝对路径 | `ENOENT` |
| `/work/session/...` 自有 session 写入 | `ALLOWED`（候选自有面） |
| `/work/g3b/bridge.sock` stat/connect | `ALLOWED`（唯一协议通道） |

原因：Candidate 只挂载 stage/deps/session/ipc；host 绝对路径与 `/work/state` 均不在其 mount namespace。**不是靠随机目录名**。

### 6.2 Host 同 UID（`runs/d15-oldrun/host/d15-oldrun.json`）

以 uid/gid 65534 子进程访问 `state`（root 0700）、`ipc`（root:2000 2750）、socket（0660 root:2000，connect）：

`read_new_state / write_new_state / list_new_state / read_old_state / connect_socket` 全部 **EACCES**；candidate 自有 `candidate-session`（65534:65534）可写。

**状态：PASS**，残余：P2-RUN-IDENTITY 仍为维护者待决；本包只证明“同 UID + 已知路径”被 OS mode/ownership 与 namespace 拒绝，不把目录名随机性当认证。若某 run 目录被误设为 group/other 可读写或 candidate 可写，该拒绝会失效——这是部署不变量，需 G4-H/P2 决策。

---

## 7. E5-P01..P05 两列状态

| Gate | 本轮能证明（NO_KEY_SUBSET） | 证据 | 本轮不能证明（FULL_STATUS） |
|---|---|---|---|
| **E5-P01** | TEST_ONLY Ed25519 签名与 **真实冻结字节** 的 5 个聚合根逐项一致（`signed_bindings_equal_frozen_bytes=true`）；任一 root 变化 → `BINDING_DRIFT:PRE_DISPATCH:*` + `*_MISMATCH` 拒绝 | `runs/p01-binding/host/p01-binding.json`；`runs/d05-revocation/…` | `BLOCKED_PENDING_HUMAN_DEPLOYMENT`（外部真实人类签名/信任根未部署） |
| **E5-P02** | compiled stage/runtime、deps lock、source、profile+policy、plugin+tool-registry 五个 root 任一漂移都在 pre-dispatch 拒绝；route contract 改变、tool schema 改变同样拒绝；拒绝时无 attempt 启动 | `runs/p02-admission/host/p02-admission.json` | `BLOCKED_PENDING_HUMAN_DEPLOYMENT`（真实部署后动态文件不可写未证） |
| **E5-P03** | Markdown/env flag/CLI/自签 JSON 均不能开 gate；`run_live/CLI exit 3`、Adapter BLOCKED、LiveGate 恒 BLOCKED | `runs/p03-bypass/host/p03-bypass.json`、`runs/d07-live/…` | `BLOCKED_PENDING_HUMAN_DEPLOYMENT`（正式人类审批与独立 trust root 未上线） |
| **E5-P04** | 真实 stage 的 `capture-tools.json` 与 Controller 允许的 tool schema digest 完全一致，且只有 `skill_lookup`；L0 profile 无候选 shell 工具 | `runs/p04-registry/host/p04-registry.json` | **NO_KEY_SUBSET = UNVERIFIED**：DSH 0.2.2-rc.2 无权威 merged registry/schema 导出 API；`registry_export_api=UNVERIFIED`。FULL=`BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| **E5-P05** | 哨兵跨 mount/env/log/IPC 不进入 Candidate；env allowlist 丢弃 secret；扫描器正控命中；Watchdog 真实清理（D01/D02/D03） | `runs/p05-secret/host/p05-secret.json`、§2、§3 | `BLOCKED_PENDING_HUMAN_DEPLOYMENT`（真实 Key 保护、真实出站 TLS/账单/供应商硬额未证） |

> 统一 `E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT`；不允许用 NO_KEY_SUBSET 的 PASS 冒充 Full PASS。

---

## 8. 矩阵映射（G4-D-01..15）

| 行 | 状态 | 一句话 |
|---|---|---|
| D-01 | **PASS** | 真实双主体 kill、OS/proc/容器/socket/run-dir absence、0 attempt、retry=false |
| D-02 | **PASS** | trusted init 真实 `T` 冻结；真实 deadline kill/cleanup；本 run 无 attempt/receipt，未伪造 |
| D-03 | **PASS** | Candidate env/argv/mount/`/proc`/session/log/receipt 0 哨兵；正控有效 |
| D-04 | **PASS** | 运行期 8804 / 最终 8815 文件 0 命中；Packet=NOT_BUILT（G4-E） |
| D-05 | **PARTIAL** | 撤销/单次使用/pending attempt 不重发均在真实产品层证明；容器内人类撤销入口不存在（G4-H） |
| D-06 | **PASS** | 同 gate 改 epoch `AUTH_EPOCH_MISMATCH`；跨 run `AUTHORIZATION_UNKNOWN`；契约层 `AUTHORIZATION_EPOCH_MISMATCH` |
| D-07 | **PASS** | 四类 Live 入口 + 假 secret/proxy 全 BLOCKED，计数全 0 |
| D-08 | **PASS** | 两种注入均 FAIL_CLOSED/exit 4 + 人工清理 + 二次复查空 |
| D-09 | **PARTIAL** | CPU/AS/NOFILE + cgroup 实测；NPROC UNVERIFIED |
| D-10 | **PASS** | P01 子集 PASS / FULL BLOCKED |
| D-11 | **PASS** | P02 子集 PASS / FULL BLOCKED |
| D-12 | **PASS** | P03 子集 PASS / FULL BLOCKED |
| D-13 | **UNVERIFIED** | P04 可观测白名单 PASS，registry 本身 UNVERIFIED |
| D-14 | **PASS** | P05 子集 PASS / FULL BLOCKED |
| D-15 | **PASS** | 容器内 + host 同 UID known-path 全 EACCES/ENOENT；残余 P2-RUN-IDENTITY |

`G4-H-01..06` 保持 **BLOCKED**；`G4-E-01..10` 保持 **NOT_RUN**（不属于本包）。

---

## 9. 回归、ruff 与环境说明

| 套件 | 命令（节选） | 实际结果 |
|---|---|---|
| g4_a + g4_b + g4_c | `python -B -m pytest tests/integration/g4_{a,b,c} -q`（`PYTHONPATH=src`） | **339 passed, exit 0**（125 s） |
| g3c + g3d + g3_bridge + unit/security | `python -B -m pytest tests/integration/g3c tests/integration/g3d tests/integration/g3_bridge tests/unit/security -q`（`PYTHONPATH=src`） | **404 passed, 1 failed, exit 1** |
| 已知失败 | `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` | **预期失败**：G4-A 对 `src/` 的授权改动使该 frozen-src 断言为 false；按任务书不修历史测试，如实归类为“已知冻结断言失败”，非本包回归 |
| g4_d | `python -B -m pytest tests/integration/g4_d -q --junitxml=artifacts/g4/e5/junit-g4d.xml` | **26 passed, exit 0** |
| sandbox live controller（补充） | 同上 host 环境 | 4 passed, 1 failed；失败项 `test_all_live_entrypoints_remain_blocked` 以硬编码容器路径 `PYTHONPATH=/project/src:/deps` 启动子进程，host 上 `ModuleNotFoundError` → **host-only 环境失败（OPS-P2-b 类）**，与本包改动无关 |
| ruff 0.17.5 | `ruff check` 新增/修改文件 + `tests/integration/g4_d` | **All checks passed!** |

**环境偏差（必须记录）**：本机 `uv run` 离线缓存缺少 `iniconfig` wheel，无法创建 3.11 venv；回归使用 conda CPython 3.12.13 + pytest 9.1.1，并显式 `PYTHONPATH=src` 以便 broker/fake 子进程导入产品包。无网络、无 `uv sync`。因此测试计数与 G4-A 报告（3.11 环境）不可逐字比较，但通过/失败归因明确。

**轮次内清洗**：首轮 D02 的 `podman pause` 残留容器使后续 preflight 失败；该容器最终按 crun 状态修复后删除，`podman ps -a` 为空、rootfs 恢复 `25491e45…`。最终证据轮（`d3d429c`）从空容器、canonical rootfs 开始，结束时再次验证空容器与 canonical。

---

## 10. 残余、未主张与 STOP

1. **E5 FULL 不通过**：无真实人类信任根、无私钥托管、无真实 Key、无真实出站；`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
2. **P04 registry**：DSH 无可观测的 merged registry/schema 导出；只能证明“已捕获 tool schema 与白名单一致”，不能证明未知动态 tools 已被删除；若长期运行需 G4-H 决策。
3. **P2-RUN-IDENTITY**：同 UID 旧 run 的拒绝依赖“run state 0700 root / ipc 2750 root:2000 / socket 0660 root:2000 + 独立 mount/UID namespace”；不是目录名熵。任何把这些目录放宽到 candidate 可写的部署都会破坏该结论。
4. **D05 撤销入口**：G4-C synthetic controller 没有“人类 revocation 文件”输入；撤销在 authorization/attempt 层验证，容器内端到端撤销属 G4-H。
5. **D09 NPROC**：host root 不受 `RLIMIT_NPROC` 限制；只证明容器 cgroup `pids.max` 生效，未证明 host watchdog 的 NPROC 上限。
6. **G4-C 复用**：D03/D04 使用 `run_g4_d.py` 编排的真实 c01 echo；G4-C 原始证据 `artifacts/g4/c/runs/c01-…` 未修改，仅作为 D04 扫描根之一与 peercred 交叉引用。
7. **本报告不含独立 Reviewer 结论**；所有矩阵行 `reviewer_verdict=PENDING_INDEPENDENT_REVIEW`。
8. **STOP**：未进入 G4-E，未构建 Review Packet，未推进 G4-H/G5/G6。`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`。

---

*证据根：`artifacts/g4/e5/`（gitignored）。索引：`summary.json`、`summary.txt`、`evidence-digest.json`、`commands.jsonl`、`runs/**`。本文件不含哨兵实际字节，以免与自身泄漏扫描混淆。*
