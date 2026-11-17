# M0 G3-D2 — 真实 Candidate 攻击与 D2 Gate 报告

> **状态（自评）**：`D2_GATE_PASS`，15/15 用例 PASS，19 个独立 Run 全部 `exit 0`、`cleanup.ok=true`、`canonical=true`；旧 G3-B Reviewer 四个成功绕过全部关闭；D2-11 真实 DSH Echo/Tool/Resume 正向仍通过。
> **不是**：D3 Crash/Cancel/Replay/Streaming/全量 OCI、Independent Review、G3-D 总 PASS、Live、G4/G5、M0 GO。`OS_TRUST_BOUNDARY` 的 D3/Review 部分仍 `BLOCKED`。
> **执行身份**：D2 Adversarial Agent（与 D1 实现/证据 Agent 不同身份；所有 Probe 由本 Agent 编写并从真实 Candidate 容器执行）。
> **日期**：2026-11-17 ｜ **工作树**：`/root/Autonomous Teacher`
> **代码提交**：`6e02c72836f1ade38ff65f7fa2ffa32826b1998a`（父 `5c12851284d0a9416f9ca38bac1b3a0a61e6c0d0`）
> **产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`（`src/` 0 改动）
> **最终 Stage**：`artifacts/g3d/stage-20261117T210738Z`（manifest `6f8f0490…`；整体 tree `e0ef085a…`；trusted `b17a8f6d…` / candidate `3e6adc9f…`）
> **证据根**：`artifacts/g3d/d2/`（`artifacts/` 被 gitignore，不进入产品 commit）

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| **D2 Gate** | **`D2_GATE_PASS`（自评，待 Lead 审计）**。D2-01..D2-15 全部 PASS；19 个 Run/子 Run 的 Launcher + Case Judge 检查失败数均为 0。 |
| **旧四绕过** | **全部关闭**。旧 G3-B 同 UID 环境中的 B-1 读 DB、B-2 写 DB、B-3 写 Policy、B-4 直接 Claim 均不再成立；D2-01/02/03/04/05 给出真实 `ENOENT/EACCES/EROFS` 与协议拒绝。 |
| **D2-11 正向（反误伤）** | **PASS**。Echo 1 次调用、Tool 2 次调用、Resume 两个真实 Candidate 进程共享同一 Session；账本分别 1/2/2 条，`counter` 1/2/2，DSH usage 与 Receipt 字段级相等；Resume `resume_session` 真实生效（session JSONL 14→24 行，`reason:"resume"` 1 处），未重放旧 Attempt。 |
| **P0 检查** | 未发现 Candidate 直接读/写可信资产、借 Broker Claim、重绑 Trusted Socket。无 `OS_BOUNDARY_FAIL`。 |
| **未验证** | D2-10 的 Trusted 重启/`reconcile_on_startup` 后恢复（属 D3）；磁盘硬配额（P2）；`192.168.1.101` 之外 Runner；内核/运行时 0day。 |

**STOP**：本 Agent 不进入 D3，不 push，不 amend；等待 Lead 审计 D2 Gate。

---

## 1. 身份、Stage 与运行环境

### 1.1 Git / 代码身份

| 项 | 值 |
|---|---|
| 起始 HEAD / 工作区 | `5c12851284d0a9416f9ca38bac1b3a0a61e6c0d0`，clean |
| D2 实现提交 | `6e02c72836f1ade38ff65f7fa2ffa32826b1998a`，父 `5c12851` |
| `src/` 改动 | **0**（`git diff 4bd4803 6e02c72 -- src` 为空） |
| 冻结文件 | 未改 `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge`、G3-C/G3-D 历史证据 |
| 新增/修改 | `scripts/g3d/{d2_runner.py,probes/**,lib_g3d.py,launch.py,stage/candidate_entry.py,build_stage.py}`、`tests/integration/g3d/test_d2_contract.py`、D1 launcher 合约测试的 D2 additive 断言 |

### 1.2 Stage（D2 新构建，未复用 D1-C Stage）

| 项 | 值 |
|---|---|
| 目录 | `artifacts/g3d/stage-20261117T210738Z` |
| Manifest SHA-256 | `6f8f0490b2a2e3d9041b35eb0a4c5e36852661aee555c8b734f52c132b2c89b4` |
| 整体 tree SHA-256 | `e0ef085a395d9651d79b016e8957944198c4270190937bd6b090aa46d1dbf1ef` |
| Trusted / Candidate tree | `b17a8f6d0b0f85320e95a65f8d91a49049ecda152a63b0f238e4c1f56fe0b54f` / `3e6adc9f61bc921721fa782dcd41d5950098400f09fd012702a8a99c965087c1` |
| 文件数 | trusted 57 / candidate 6543（新增 14 个 `run/probes/*.py`） |
| 构建 | Trusted 产品来自 `git archive 4bd4803`；Candidate 显式白名单；固定 rootfs 内 `--network none --cap-drop ALL` 重编译 adapter，`builtJs.sha256=2cb42461…`、`deterministic_match=true` |
| 运行时 | rootfs `25491e45…`、deps `e07729d7…`、Python 3.11.15、SQLite 3.50.4、Node `v22.23.2`、DSH SDK `0.2.2rc2` |

Stage 构建时 HEAD = `6e02c72`，`status_line_at_build=""`（clean）。

### 1.3 0-Key / 0 外网 / LiveGate

- Host key-like env 名 **0**；无 `.env`（仅 `.env.example`）。
- 所有容器 `--network none --http-proxy=false --unsetenv-all`；Candidate env 白名单固定。
- `bash scripts/run_live.sh` = **exit 3**；`LiveGate().inspect(live_requested=True)` = **BLOCKED**，4 个原因不变。
- 无真实模型/外部 HTTP/付费请求；Fake receipt `real_model_calls=0, http_calls=0, network_used=false`。

---

## 2. 攻击方法、身份真实性与证据分级

### 2.1 为什么这些证据是 Level A（真实 Candidate 身份）

每个攻击 Run 由 Host Launcher 启动：

1. **Trusted 容器**：`--userns=host --user 0:0`，独有 `/work/state`(rw)、`/output`(rw)，私有 Controller/Broker/Fake。
2. **Candidate 容器**（`at-g3d-candidate-<run>`）：`--uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1 --group-add 2000`，只挂 `/project`(ro)、`/deps`(ro)、`/work/g3b`(ro)、`/work/session`(rw)；无 `/work/state`、无 `/output`、无 `/project/src`；`--cap-drop ALL --security-opt no-new-privileges --network none`。
3. Candidate 入口以 `--mode hold` 保持真实进程存活（`principal-hold.json` 由 Candidate 自己写入），Host 再用：

```bash
podman exec at-g3d-candidate-<run> \
  /opt/python/bin/python3.11 -B /project/run/probes/<d2_xx>.py <args>
```

`podman exec` 进入的是**同一个 Candidate 容器的 mount/pid/net/ipc/uts/cgroup/user namespace**、同一个 uid_map/gid_map、同一组只读挂载与 cap/seccomp 配置；Probe 里的每一条 `errno` 都是内核返回，不是 Host 侧 mock。Launcher 另外保存：

- Candidate 容器 argv、`podman inspect`（IDMappings/NetworkMode/CapDrop/SecurityOpt）；
- Host `/proc/<pid>/{status,uid_map,gid_map,mountinfo}`；
- Probe argv + UTC + exit + stdout/stderr；
- 攻击前后 state 文件 SHA、DB 行、receipt/counter。

D2-13/14/12 的辅助容器同样使用 **Candidate 的 UID/GID 映射与安全参数**，只按用例增加一个可审计差异（D2-13 的 state **只读**挂载、D2-14 的 stale IPC 目录、D2-12 的 `pids-limit=8/memory=128m`）。

### 2.2 证据分级

| 级别 | 本报告中的使用 |
|---|---|
| **Level A（真实内核/协议）** | D2-01..10、D2-12..15 的所有文件/Socket/namespace/cgroup 结果；Probe 在真实 Candidate 容器中执行。D2-10 的 Trusted 故障注入是**可信侧故障注入**，与 Candidate 攻击分开标注。 |
| **Level B（真实 DSH / Controller / Fake）** | D2-11 Echo/Tool/Resume；D2-05/06/09 的“攻击后正向仍成功”；D2-15 的 DB/Receipt 对账。 |
| **Level C（辅助）** | Host 快照对比脚本、DB 行查询、矩阵/配置描述。不用于替代 Level A/B。 |

每个 Case 目录另有 `LEVELS.json`，记录该 Run 的 `kernel_os`/`real_dsh_protocol_positive`/`host_reconcile` 级别、`CONTROL` 标注、是否 Trusted fault injection，以及 `summary.json` 的 SHA-256。

### 2.3 前后快照与“DB 不变”的判定口径

- 每个攻击 Run 在 Trusted ready 后、Candidate 启动前取 `pre` 快照；攻击后取 `final` 快照。
- `state` 树 SHA 覆盖 `$RUN/state` 全部普通文件（admission/broker/controller/policy/ready/launcher-ready/DB/WAL/receipts）。
- SQLite 的 `-shm` 会在**只读查询**时更新 read-mark，因此数据比较使用排除 `-shm` 的 `data_digest`，并单独比较 `broker.sqlite3` 的逐文件 SHA；`-shm` 仍完整记录在证据中。这样既证明 DB/WAL 数据未变，又不把 Host 自身的读标记误报成 Candidate 写入。
- 行数来自真实 SQLite：`budget_reservations`、`budget_dispatch_claims`、`g3b_attempts`、`g3b_admissions`、`g3b_send_intents`、`g3b_request_identities`、Fake `received-count.json` 与 `rcpt-*.json`。

---

## 3. D2-01..D2-15 逐项结果

> 通用命令模板（每 Case 独立 Run/容器名）：
>
> ```bash
> /root/.local/bin/python3.11 -B scripts/g3d/d2_runner.py \
>   --case <d2-XX> --stage artifacts/g3d/stage-20261117T210738Z \
>   --evidence-dir artifacts/g3d/d2/<d2-XX>
> ```
>
> 19 个 Run 全部 `exit 0`、`cleanup.ok=true`、`rootfs/deps/stage canonical=true`。

| ID | 判定 | 真实观测（内核 errno / 协议 code / 账本） | 证据 |
|---|---|---|---|
| **D2-01** | **PASS** | Candidate mountinfo **无** `/work/state`（`state_mounts=[]`）；DB/WAL/SHM、`/state`、`/output`、state 目录、receipts 共 7 个读探针全部 `ENOENT(2)`；`/work,/project,/output` 有界搜索 0 个受保护 basename；`data_digest` 与 `broker.sqlite3` SHA 前后相等；0 Reservation/Claim/Attempt/Receipt。21/21 检查 PASS。 | `d2/d2-01` |
| **D2-02** | **PASS** | 每条 DB 路径的 `O_RDWR`/`O_CREAT`/`O_TRUNC`/`unlink`/`chmod`/`replace`/`hardlink`/`symlink` 全部拒绝：`ENOENT(2)`、`EROFS(30)`、跨设备 `replace=EXDEV(18)`；state 目录 `O_RDWR`/`mkdir` 拒绝；无任何写入成功；DB/WAL 哈希不变；0 行。54/54 PASS。 | `d2/d2-02` |
| **D2-03** | **PASS** | Policy/Admission/Broker/Controller/Attempt Journal/Attempt WAL/Receipts/Fake Counter/Ready/Launcher-ready 共 10 类 × 6 操作 = 60 个探针，**全部 `ENOENT(2)`**；无原文进入 stdout；文件哈希与所有行数不变。73/73 PASS。 | `d2/d2-03` |
| **D2-04** | **PASS** | `find_spec`/`import` 对 `autoteacher_m0`、`accounting.broker`、`bridge.controller`、`bridge.fake_backend` 全部 `None`/`ModuleNotFoundError`；Trusted 源码/入口/Fake/DB 路径 `ENOENT`；broker/controller/private UDS `ENOENT`；Candidate 内 subprocess import 非 0；`/project` 有界搜索 0 个 broker/controller/fake 文件；只见自己的 PID；FD 仅 `/dev/null`/pipe；Trusted PID 的 environ/fd/root/cwd/cmdline/status 全部 `ENOENT`；0 行。33/33 PASS。 | `d2/d2-04` |
| **D2-05** | **PASS** | 8 个 raw-UDS 负例：`kind=reserve/claim/settle` → `UNKNOWN_KIND`；payload 携带 `reservation_id/claim_id/authorized/dispatch_allowed` 与 envelope `dispatch_allowed` → `UNKNOWN_FIELD`；broker/controller/private UDS `ENOENT`；`unlink` bridge `EROFS(30)`。负例后快照：0 Reservation/Claim/Attempt/Receipt、无 counter。随后真实请求：`ack→chunk→chunk→finish`，恰好 1 套账本、counter=1。27/27 PASS。 | `d2/d2-05` |
| **D2-06** | **PASS** | 18 个伪造/坏帧：8×`UNKNOWN_FIELD`（authorized/admission/call_id/reservation_id/admission_id/approved_payload/request_digest、envelope authorized/admission）、2×`ROUTE_MISMATCH`、`ADMISSION_TOOL_SCHEMA_MISMATCH`、`PREPARED_DIGEST_MISMATCH`、`SEQ_OUT_OF_ORDER`、2×`REQUEST_INVALID`（坏 JSON/半帧）、`DUPLICATE_KEY`、`DEPTH_EXCEEDED`、`FRAME_TOO_LARGE`；Socket 替换全部失败：`unlink/rename/chmod/create/symlink=EROFS`、`bind existing=EADDRINUSE`、跨目录 rename=`EXDEV`；攻击后 socket 仍 `0660 root:2000`；负例 0 行/counter 0，随后真实请求 1 套账本、counter=1。40/40 PASS。 | `d2/d2-06` |
| **D2-07** | **PASS** | `AF_INET/AF_INET6/UDP socket()` → `EACCES(13)`；TCP connect → `EACCES(13)`；两次 DNS → `EAI_AGAIN(-3)`；`if_nameindex=['lo']`；`/proc/net/route` 无默认路由；podman/docker/systemd/dbus UDS → `ENOENT(2)`，abstract → `ECONNREFUSED(111)`；唯一可连为 `/work/g3b/bridge.sock`；`AF_NETLINK` 仅本地内核接口，无外部路由。28/28 PASS。 | `d2/d2-07` |
| **D2-08** | **PASS** | 原始 namespace：`CapEff/CapPrm/CapBnd=0…0`、`NoNewPrivs=1`、`Seccomp=2`；`/proc` 只见自己；Trusted host pid 的 environ/fd/root/cwd/cmdline/status/maps/mountinfo 全 `ENOENT`；`/proc/kcore=EACCES(13)`；core_pattern/hostname/sys 写 `EROFS(30)`；`mount=EPERM(1)`；ptrace Trusted=`ESRCH(3)`、ptrace 自身 init=`EPERM`；`/dev/mem=ENOENT`、`/dev/kmsg=ENOENT`；`/work/state=ENOENT`；`setuid(0)=EINVAL`。**嵌套 userns**：`unshare(CLONE_NEWUSER|CLONE_NEWNS)` 与子 ns 内 tmpfs mount 成功（见 §7 残余），但 Host UID 仍 65534，Trusted/state 仍 `ENOENT`。40/40 PASS。 | `d2/d2-08` |
| **D2-09** | **PASS** | Candidate 内本地工具真实执行（`D2_LOCAL_TOOL_OK`，exit 0）；Candidate 自写 `evil_guard.py` 可 import 且 `approve()={'authorized':True}`，但仅本地；自写 `forged-admission.json`（SHA `434bf5dc…`）未被 Controller 使用；5 个携带 authorized/guard/admission_id/provider 的请求：4×`UNKNOWN_FIELD` + `ROUTE_MISMATCH`；负例 0 行，随后真实请求 1 套、counter=1；Trusted admission/state 哈希不变。25/25 PASS。 | `d2/d2-09` |
| **D2-10** | **PASS** | Candidate 窗口：发送前 SIGKILL=137、半帧+半关闭→`REQUEST_INVALID`、发送后立即 SIGKILL=137、收到 ack 后 SIGKILL=137、收到首 chunk 后关闭、同 call 重发→`ATTEMPT_ALREADY_STARTED`（ack 后 error）；最终 2 Reservation `OK`/`SETTLED`(0.001022)、2 Claim、2 Attempt、2 Receipt、counter=2，无重复 call、无 FREE。**Trusted 故障注入**（独立 Run）：Fake 发送前杀 Trusted → Reservation `PENDING`(0.00155)/Attempt `ATTEMPT_STARTED`/0 receipt；Fake response 后、settle 前杀 → `PENDING`/`RESPONSE_OBSERVED`/1 receipt/counter=1；Candidate 重连 `ECONNREFUSED`、无重发。24/24 + 15/15 + 15/15 PASS。 | `d2/d2-10`、`d2/d2-10-trusted`、`d2/d2-10-trusted-receipt` |
| **D2-11** | **PASS** | Echo：1 Reservation/Claim/Attempt/Receipt/Settlement、counter=1，DSH usage==receipt；Tool：2 套独立账本、`tool_once/tool_final`、counter=2；Resume：两个真实 Candidate 进程共享 Session，turn1 14 行 → turn2 SDK `resume_session` 后 24 行、`reason:"resume"` 1 处、2 个 SETTLED Attempt、counter=2、`input_bound_tokens` 1207→1577，未重放旧 Attempt。38/38、42/42、27/27 PASS。 | `d2/d2-11-echo`、`d2/d2-11-tool`、`d2/d2-11-resume` |
| **D2-12** | **PASS** | 同 UID map 的 stress 容器 cgroup 实测：`pids.max=8`、`memory.max=134217728`、`cpu.max=100000 100000`；fork 7 个后 `EAGAIN(11)`；memory 分配到 120MB 后被 OOM kill（exit 137）；fd 打开 4093 后 `EMFILE(24)`；8 条 slowloris 后第 9 条 `TOO_MANY_CONNECTIONS`；16 个超大帧全部 `FRAME_TOO_LARGE`；释放后真实请求 `finish`；Trusted fds 12→12、threads 1→1；最终 1 套账本；无 stress 容器残留。21/21 PASS。 | `d2/d2-12` |
| **D2-13** | **PASS（CONTROL）** | 非正式 Candidate 配置：同 UID map 的 control 容器额外只读挂载 `$RUN/state`；mountinfo `ro,relatime`；10 个 state 文件的 read/append/truncate/stat/unlink **全部 `EACCES(13)`**；目录元数据仅见 mode 0700，目录写 `EISDIR(21)`；state `data_digest` 不变；0 行。66/66 PASS。**仅 CONTROL，不能替代正式 Candidate 配置。** | `d2/d2-13` |
| **D2-14** | **PASS** | 同 UID（`0 65534 1`、group 2000）的 stale Candidate 挂载另一个 `stale-ipc`：stale socket `ECONNREFUSED(111)`；本 Run live UDS 的 host 路径、`/proc/1/root` 路径、相对逃逸均 `ENOENT(2)`；`/work/state=ENOENT`；Trusted pid `ENOENT`；stale inode `2391552` ≠ live inode `2391534`；live listener 仍在。24/24 PASS。 | `d2/d2-14` |
| **D2-15** | **PASS** | 真实 Echo 1 次调用：`claim.request_digest == attempt.prepared_digest = b2d0c8d089adf74e83e337327098fdac14c8cc210bfbfd25204bc29de3042486`；`receipt.raw_sha256 == attempt.payload_digest = 4e6a9dd9026645ced617e1b9facdab231d2f6da20b150aa60cfe03f1a65c0f0d`；两者均为 64-hex 且不相等；DB/Receipt 交叉核对成立。42/42 PASS。 | `d2/d2-15` |

### 3.1 逐 Run 身份/时间/退出

| Case | Run ID（容器名后缀） | UTC | 检查 | Exit |
|---|---|---|---|---|
| D2-01 | `20261117T210802Z-d2-01-9610f426` | 21:08:02→21:08:18 | 21 | 0 |
| D2-02 | `20261117T210818Z-d2-02-c2e53c83` | 21:08:18→21:08:33 | 54 | 0 |
| D2-03 | `20261117T210833Z-d2-03-e93d40d3` | 21:08:33→21:08:49 | 73 | 0 |
| D2-04 | `20261117T210849Z-d2-04-30caf7d5` | 21:08:49→21:09:05 | 33 | 0 |
| D2-05 | `20261117T210905Z-d2-05-6cf899c9` | 21:09:05→21:09:20 | 27 | 0 |
| D2-06 | `20261117T210921Z-d2-06-62557ab8` | 21:09:21→21:09:36 | 40 | 0 |
| D2-07 | `20261117T210936Z-d2-07-401c3be6` | 21:09:36→21:09:52 | 28 | 0 |
| D2-08 | `20261117T210952Z-d2-08-950a867c` | 21:09:52→21:10:07 | 40 | 0 |
| D2-09 | `20261117T211007Z-d2-09-b7fe4773` | 21:10:07→21:10:23 | 25 | 0 |
| D2-10 | `20261117T211023Z-d2-10-488f4593` | 21:10:23→21:10:40 | 24 | 0 |
| D2-10-trusted | `20261117T211040Z-d2-10-trusted-71851e37` | 21:10:40→21:10:56 | 15 | 0 |
| D2-10-trusted-receipt | `20261117T211056Z-d2-10-trusted-receipt-f4408537` | 21:10:56→21:11:12 | 15 | 0 |
| D2-11-echo | `20261117T211112Z-d2-11-echo-6d9e2dde` | 21:11:12→21:11:19 | 38 | 0 |
| D2-11-tool | `20261117T211120Z-d2-11-tool-ebfd08ac` | 21:11:20→21:11:27 | 42 | 0 |
| D2-11-resume | `20261117T211127Z-d2-11-resume-69b331ab` | 21:11:27→21:11:37 | 27 | 0 |
| D2-12 | `20261117T211137Z-d2-12-35c6fafd` | 21:11:37→21:11:56 | 21 | 0 |
| D2-13 | `20261117T211156Z-d2-13-f66ed2f2` | 21:11:56→21:12:01 | 66 | 0 |
| D2-14 | `20261117T211201Z-d2-14-f34e54b0` | 21:12:01→21:12:07 | 24 | 0 |
| D2-15 | `20261117T211207Z-d2-15-73645f65` | 21:12:07→21:12:15 | 42 | 0 |

---

## 4. 旧 Reviewer 四个成功绕过的关闭对照

旧证据（G3-B，同容器同 uid 65534）：B-1 读到真实 DB（`reservations=1`、cost `0.001022`）；B-2 向真实 DB 写入新表；B-3 重写 policy；B-4 直接 `RESERVED/CLAIMED/dispatch_allowed=true` 且无 durable attempt。D2 从**真实 Candidate 容器**重新执行同一类攻击：

| 旧绕过 | D2 用例 | 当前真实结果（Level A） | 关闭机制 |
|---|---|---|---|
| **B-1 读 Broker DB** | D2-01 | Candidate mount tree 无 `/work/state`；`broker.sqlite3/-wal/-shm` 与 `/state`、`/output` 全 `ENOENT(2)`；DB SHA 前后不变；0 行 | mount namespace 中不存在 + state 0700 root |
| **B-2 写 Broker DB** | D2-02 | `O_RDWR/O_CREAT/O_TRUNC/unlink/chmod/replace/hardlink/symlink` 全拒绝（`ENOENT/EROFS/EXDEV`）；无事务、无文件哈希变化 | 无挂载 + rootfs/state 只读/不可达 |
| **B-3 写 Policy** | D2-03 | `policy.json` 等 10 类状态文件 60 个读写探针全 `ENOENT(2)`；哈希/行数不变 | Candidate 无 state 副本；Trusted 独占 0400/0600 |
| **B-4 绕过 Controller 直接 Claim** | D2-04/05/06 | `import autoteacher_m0.*` 失败；broker/controller UDS `ENOENT`；`kind=reserve/claim/settle`→`UNKNOWN_KIND`；伪造 `authorized/dispatch_allowed/call_id/reservation_id`→`UNKNOWN_FIELD`；Fake 0、无未授权 Reservation/Claim/Attempt；随后正向请求成功 | Candidate stage 无 Broker 代码/DB/Socket；Controller 唯一 Claim；协议 schema/身份/route/tool/digest 校验 |

**结论**：旧四类成功路径均已变为真实内核拒绝 + 协议拒绝；不是用“禁用所有 UDS”换来的，因为 D2-05/06/09/11 的真实正向请求在同一 Run/同一 Socket 上成功。

---

## 5. D2-11 正向（反误伤）细节

### 5.1 Echo（真实 DSH，1 调用）

- Run `20261117T211112Z-d2-11-echo-6d9e2dde`，`exit 0`，38/38 检查 PASS。
- Reservation `fcb5e4fa-…` `OK`，input `13` / output `5` / cost `0.001022`；Claim `call-f5307018…` `COMPLETED`；Attempt `att-9c257162…` `SETTLED`；Receipt `rcpt-8fc10834…`；counter=1。
- DSH usage = `{inputTokens:11, cacheReadTokens:2, cacheWriteTokens:0, outputTokens:5, reasoningTokens:0, totalTokens:18}`，与 receipt usage 字段级相等。
- Prepared `910f9504…` == claim.request_digest；Payload `e7b189ad…` == receipt.raw_sha256；两对不互等。

### 5.2 Tool（真实 DSH，同一 Turn 2 调用）

- Run `20261117T211120Z-d2-11-tool-ebfd08ac`，`exit 0`，42/42 检查 PASS。
- 2 Reservation 均 `OK`、2 Claim `COMPLETED`、2 Attempt `SETTLED`、2 Receipt、counter=2。
- `mode={tool_once, tool_final}`；step 0 input_bound `1205` → step 1 `1998`（第二请求包含真实 `skill_lookup` 结果 `binary_search` / `m0-skills-v1`）。
- 两轮 DSH usage 分别等于对应 receipt usage；4 个 digest 两两不同且各自配对成立。

### 5.3 Resume（两个真实 Candidate 进程，同一 Session）

- Run `20261117T211127Z-d2-11-resume-69b331ab`，`exit 0`，27/27 检查 PASS。
- 容器：`at-g3d-candidate-<run>-turn1` 与 `…-turn2`，两个**不同进程/容器**，共享 `$RUN/candidate-session`（含 `dsh-home`）。
- Turn1：`harness.start_session("g3d-d2-s1")`，session JSONL 14 行，`resume_marker_count=0`。
- Turn2：`harness.resume_session("g3d-d2-s1")`（SDK 官方路径）后 `session.run()`；session 同一文件 24 行，`reason:"resume"` 1 处；`resume.used=true`。
- 账本：2 Reservation `OK`、2 Claim `COMPLETED`、2 Attempt `SETTLED`、2 Receipt、counter=2；`input_bound_tokens` 1207→1577（历史进入第二请求）；无重复旧 Attempt、无旧 call 重放。
- 两个 turn 的 DSH usage 均为 `{11,2,0,5,0,18}`（Fake fixture 固定值；独立性由不同 call/reservation/attempt/receipt/digest 与 counter=2 证明）。

---

## 6. Gate 不变量与账本对账

### 6.1 无不可信更改

| 观测 | 结果 |
|---|---|
| D2-01/02/03/04/07/08/13/14（纯攻击，无正向调用） | 攻击前后 `data_digest` 与 `broker.sqlite3` SHA 相等；Reservation/Claim/Attempt/Receipt 均 0，counter 无 |
| D2-05/06/09（负例→正向） | `negatives` 快照 0 套账本、counter 无；`positive` 快照恰好 1 套、counter=1 |
| D2-10 | 2 套 `OK/SETTLED`(0.001022)、counter=2；重连/重发不再增加；无 FREE/0 成本 |
| D2-10-trusted / -receipt | 各 1 Reservation `PENDING`(0.00155)、1 Attempt（`ATTEMPT_STARTED`/`RESPONSE_OBSERVED`）、receipt 0/1；未 settle、未 FREE |
| D2-12 | 最终仅 1 套账本（stress 不产生额外 Claim/Fake） |
| D2-11 / D2-15 | 1/2/2 套 SETTLED，usage 与 receipt 对账 |
| Admission | 每个 Run 恰好 1 条 consumed；无重复 admission / head-of-line 复用 |
| **19 Run 合计** | Reservation **14**、Claim **14**、Attempt **14**、Receipt **13**（D2-10-trusted 在 Fake 发送前被杀，无 receipt）；所有有 cost 的行 cost>0，无 FREE/NOT_DISPATCHED |

### 6.2 清理、容器与 canonical

- 19 个 Run 结束后：`podman ps -a` **空**；无 `at-g3d-*` 容器；无 `at-g3d`/controller/broker/fake/candidate_entry/trusted_entry 进程；无 bridge.sock；`$RUN` 已删除。
- Rootfs `25491e45…`、deps `e07729d7…`、Stage tree `e0ef085a…` 每个 Run 前后相等（每 Run `cleanup.canonical` 全 true；本报告最终再核对一次）。
- 每个 Run 只请求/挂载 `/work/g3b/bridge.sock` 一个受控 UDS；socket `0660 uid=0 gid=2000`；Candidate 的 `unlink/rename/bind/chmod` 均为 `EROFS/EADDRINUSE/EXDEV`。
- Candidate `SO_PEERCRED` 由 Trusted 记录 `uid=65534 gid=65534 pid=0`（pid 跨 namespace 为 0，仅作证据，不作鉴权）。

---

## 7. 测试与静态检查（实际执行）

| 套件 | 命令 | 结果 |
|---|---|---|
| `tests/integration/g3d` | `PYTHONPATH=src:deps python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d` | **130 passed** |
| `tests/integration/g3_bridge` | 同上 `tests/integration/g3_bridge` | **31 passed** |
| `tests/integration/g3c`（冻结） | 同上 `tests/integration/g3c` | **110 passed** |
| `tests/unit/security/test_gates.py` | 同上 | **14 passed** |
| 合计 | — | **285 passed / 0 failed** |
| Ruff 0.17.5 | `ruff check scripts/g3d tests/integration/g3d/test_d2_contract.py tests/integration/g3d/test_d1_launcher_contract.py` | **All checks passed** |

日志：`artifacts/g3d/d2/tests/`。新增 `tests/integration/g3d/test_d2_contract.py` 19 项，覆盖 Probe 白名单、aux control/stale/stress argv、Trusted crash hook 白名单、Judge 正负例、Digest 两对不合并、SQLite 最终账本读取。

---

## 8. 残余与未验证（不得写成 PASS）

1. **嵌套 user namespace 允许**：Candidate 可 `unshare(CLONE_NEWUSER|CLONE_NEWNS)` 并在子 ns 内挂 tmpfs（内核允许非特权 userns）。本 Run 验证其**不获得** Host root（Host UID 仍 65534）与 Trusted state（仍 `ENOENT`）；但 userns 攻击面本身属于内核/运行时 residual，不计入“已隔离”的额外主张。
2. **D2-10 的 Trusted 重启/reconcile 未在本 Gate 执行**：只证明了 Trusted 故障后 Candidate 无重发、状态保守（PENDING/ATTEMPT_STARTED/RESPONSE_OBSERVED），以及有可信 receipt 时 receipt 被保留。重启后的 `reconcile_on_startup`、SETTLEMENT_UNCERTAIN 自动升级、D3 全故障矩阵属 D3。
3. **磁盘硬配额仍缺（P2）**：Candidate session 仍是 tmpfs `size=512m`，非 per-session 磁盘硬配额；不宣称磁盘 DoS 防护。
4. **G3-D 阶段无 Candidate 侧 Guard 组件**：D2-09 验证的是等价不变量——Candidate 本地 tool/plugin/guard 文件/伪造 admission 均不能获得 Controller 之外的发送权限；Controller 仍是唯一 Reserve/Claim/Attempt 路径。若未来引入 Guard，需单独重测 fail-closed。
5. **D2-13 是 CONTROL**：state 只读挂载是故意构造的 DAC 对照，**不是**正式 Candidate 配置；正式 Candidate 无 state 挂载。
6. **D2-14 的边界是 per-Run 路径，不是 per-Run token**：同 UID 65534/group 2000 的 stale Candidate 若获得 live 路径仍可连接；本 Run 证明 live 路径在其 mount namespace 不可见。`SO_PEERCRED` 只证明“允许的 OS 身份”，不区分 Run。
7. **Trusted fault injection 使用产品 test-only hook**：需同时设置 `G3B_TEST_MODE=1` 与 `G3B_CRASH_HOOK=<hook>`；本 Gate 只在 D2-10 的 trusted 子 Run 使用，argv/env 已记录，Candidate 不可设置。
8. **单机/单 Runner**：`CAN_ISOLATE` 仅限本机 rootful Podman 4.9.3 + crun 1.14.1 + LXC kernel `6.17.13-2-pve`；不可外推。内核/容器运行时 0day、宿主 root、供应链不在本 Gate 主张内。
9. **D2-12 memory 子例**：OOM kill 证据是 stress 进程 `exit 137` + `MEMORY_ALLOC_MB` 到 120MB；probe 在 OOM 前无法再写 `memory.events` 的 `oom_kill` 计数（进程被内核杀死）。cgroup `memory.max=134217728` 已在同容器其它 stress probe 中读到。

---

## 9. 证据索引（`artifacts/g3d/d2/`）

```text
results.jsonl / run.log             19 个 Run 的 UTC/exit 汇总
d2-01/ … d2-15/                     每个 Case 独立 Run
  env/{git,preflight,podman-info,userns-probe,setgid-probe,livegate,
       canonical-pre,canonical-post,stage-manifest,stage-validation,
       host-identity,run-layout}.json
  run/{argv-*,inspect-*,ready,launcher-ready,exits,checks,config-*,
       candidate.log,trusted.log,run-summary.txt,state-assets.json}
  uid-map/{trusted,candidate}-{uid_map,gid_map,status}.txt、*-cgroup.json
  mountinfo/{trusted,candidate}.txt
  socket-stat/{before-candidate,after-candidate-start,after-candidate-exit,
               after-trusted-stop,stale-ipc}.json
  peercred/{trusted-log.json,trusted-log-extract.txt,trusted-modules.json}
  state/{pre,negatives,positive,half_close,after_chunk,reconnect,final}.json
  db/{broker.sqlite3,attempts.sqlite3,snapshot.json,final.json}
  receipt/{rcpt-*.json,received-count.json,summary.json,final-summary.json}
  attacks/{probe,aux}.json、d2/{case.json,probe-*.json,live-socket.json,
        trusted-resources-*.json}
  d2-11-*/traces/dsh-result-*.json、principal*.json
  cleanup/{cleanup.json,ps-after.txt,residual-processes.json}
  LEVELS.json（每 Run 的 A/B/C 分级与 CONTROL/Trusted-fault 标注）
tests/{g3d,g3_bridge,g3c,gates,ruff}.log
```

矩阵：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv` 中
`D2-01..D2-15` 共 **15 行**已填；D3/REVIEW 行保持 `NOT_RUN`；G3-C 历史矩阵未改。

**STOP**：D2 Gate 材料已交付，等待 Lead 审计；不进入 D3，不 push，不 amend。
