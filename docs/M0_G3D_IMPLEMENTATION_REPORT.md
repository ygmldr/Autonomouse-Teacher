# M0 G3-D — 双 Principal 隔离实施报告（D-G0 / D-P0 / D1 / D2 / D3 / D4 交付）

> **状态（Owner 自评，非终审）**：`D-G0=PASS_AT_4BD4803`、`D-P0=PASS`、`D1_GATE_PASS`、`D2_GATE_PASS`、`D3_GATE_PASS`；D4 完成 Implementation Report、Review Request、Matrix 与 Review Packet。
> **不是**：Independent Review、`G3-D PASS`、`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`、Live、G4/G5、M0 GO。最终状态等待**未参与 D1/D2/D3 实现**的 Independent D Reviewer；`D-REVIEW-01` 在独立复核前保持 `NOT_RUN`。
> **日期**：2026-11-17 ｜ **工作树**：`/root/Autonomous Teacher` ｜ **全程**：0 Key / 0 真实模型 / 0 外部 HTTP / 0 Live；未 `podman pull`。
> **证据根**：`artifacts/g3d/{d1,d2,d3,d4}/`（`artifacts/` 被 gitignore，不进入产品 commit）
> **Review Packet**：`artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26/`

---

## 0. 结论先行

| 项 | Owner 自评 | 核心事实 |
|---|---|---|
| **D-G0** | `PASS_AT_4BD4803` | 工作树 clean；base `4bd4803`；rootfs/deps canonical；0-Key；LiveGate BLOCKED；旧 G3-C `e6fde1c` Stage 未复用。 |
| **D-P0** | `PASS` | 两对 Digest 勘误为 `DOCS_ONLY`；OCI `pgrep`/`/tmp noexec` 两项可移植性修复且未放宽沙箱；固定 OCI `775 passed / 0 failed / 1 skipped`。 |
| **D1** | `D1_GATE_PASS` | 真实 DSH Echo **29/29**、Tool 两轮 **33/33**；两个真实 OS Principal；1/1/1/1 与 2/2/2/2 账本；Fake counter 1/2；UID/Peercred/Socket/Mount/Network/Cgroup 现场证据齐全。 |
| **D2** | `D2_GATE_PASS` | **15/15** 用例、19 个 Run 全 `exit 0`；旧 G3-B 四个同 UID 绕过（读 DB/写 DB/写 Policy/直接 Claim）全部变为真实内核/协议拒绝；D2-11 正向仍成功。 |
| **D3** | `D3_GATE_PASS` | **17/17** 矩阵行；跨容器 Crash/Cancel/Replay/Deadline/Streaming/10+ 重启/双 Candidate 并发全部执行；固定 OCI **916 tests / 0 failed / 7 skipped / 4 explicit deselects**。 |
| **D4** | 材料已交付 | 本报告 + Review Request + Findings/Disposition + 矩阵 `D0-01` 填 PASS + Review Packet。不自行签 G3-D PASS。 |
| **矩阵** | **52 PASS / 1 NOT_RUN** | 53 行；仅 `D-REVIEW-01` 为 `NOT_RUN`（等 Independent Reviewer）。历史 G3-C 矩阵未改。 |
| **G3-D 总状态** | **PENDING_INDEPENDENT_REVIEW** | Owner 自评仅为各 Gate PASS；最终 `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`/`PARTIAL`/`FAIL`/`BLOCKED` 只能由 Independent Reviewer 出具。 |
| **OS 边界** | 仍 `B0-02=BLOCKED`（历史） | 本 Gate 只主张“本机、已冻结 SHA、rootful Podman 受信基础”下的双 Principal 隔离证据；不得外推。 |
| **Live / G4 / G5 / M0 GO** | **未授权、未执行** | `run_live.sh` exit 3；`LiveGate` BLOCKED（4 reasons）；`OS_TRUST_BOUNDARY` 不因 D3/D4 自动解锁。 |

---

## 1. 身份、Stage、Runtime 与范围

### 1.1 Git 身份链

| 对象 | SHA | 说明 |
|---|---|---|
| 产品/测试基线 | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b` | D-P0 提交；`src` 已含 D1-A；D-G0 审批输入 |
| D1-A IPC | `51abc6619ef87ad7b93aa3162fed52ab14df6e56` | `ipc_server.py` + `controller.py` + 803 行测试；`+1054/−16` |
| D1-B Stage/Launcher | `aacb1d01d979a0d7140bce0311e39b4a03009637` | Stage builder、launcher、lib、candidate/trusted entry、config、合约测试；11 文件 `+5146` |
| D1-C Tool 正向 | `46e2407ab14a1867fddc7c3df17b72bdd0fb0bc7` | Tool 两轮 + Gate 证据；`+474/−95`；父 `aacb1d0` |
| D2 攻击套件 | `6e02c72836f1ade38ff65f7fa2ffa32826b1998a` | 14 个 probe + `d2_runner.py` + 合约测试；父 `5c12851` |
| D3 故障/并发 | `ef84f57db93f4d8f9bd00dcb8e31ae2075995ace` | `d3_runner.py`、`d3_probes/**`、suite；父 `bb34931` |
| D3 OCI/可移植性修正 | `dc8214e0963018a3fa2ab26676d6a0f911841f3c` | 跳过/清理/测试修正 |
| D3 最终实现 | `cf40c6bfb84ceae98e795db19efa955aa3035991` | 显式 4 deselect、保持 D1-A 冻结测试字节 |
| D3 Gate docs/matrix | `4cc1679` → `941ac93` → `bb34931` → `97230a0` | D3 报告与矩阵；D4 开始前 HEAD |
| **D4 docs（本提交）** | **`docs_sha`（见 Packet manifest）** | 本报告、Review Request、Findings、矩阵 `D0-01`、Packet builder |

**关键不变量**：`git diff 4bd4803 97230a0 -- src` 为空；D1-A 的 `src` 改动在 `51abc66`，已是 `4bd4803` 的祖先。`spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge`、G3-C 历史 docs/Packet 均无改动。

### 1.2 Stage 身份（三个独立 Stage，未复用旧 G3-C）

| Phase | Stage 目录 | Manifest SHA-256 | Tree SHA-256 | Trusted / Candidate tree | 文件数 |
|---|---|---|---|---|---|
| D1 | `artifacts/g3d/stage-20261117T195831Z` | `83b241c77b28813b1d1b55ed96b7f940027a0bd8f2b4eefbbb14b0c4cf09110e` | `9b6fc7b4d22cb2cbf5c21c1c6dc0714646a651280056cc5426f248b6fdb2548b` | `c1c27eb5…` / `1474002f…` | 57 / 6529 |
| D2 | `artifacts/g3d/stage-20261117T210738Z` | `6f8f0490b2a2e3d9041b35eb0a4c5e36852661aee555c8b734f52c132b2c89b4` | `e0ef085a395d9651d79b016e8957944198c4270190937bd6b090aa46d1dbf1ef` | `b17a8f6d…` / `3e6adc9f…` | 57 / 6543 |
| **D3（最终）** | `artifacts/g3d/stage-20261117T221955Z` | `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03` | `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5` | `3a004bee…` / `6c850e4b…` | 57 / 6549 |

- Trusted 产品文件来自 `git archive 4bd4803`；Candidate 为显式**白名单**构建，不是“先复制整个 repo 再删除”。
- Stage manifest 记录每个文件的 path/sha256/bytes/mode/source；运行期 `inspect.getfile` 的 10 个 Trusted 模块字节 SHA 与 `git show 4bd4803:<path>` 逐项相等。
- 旧 G3-C Stage `fcdb0de4…`（49/49 `.py` = `e6fde1c`）**未被 D1/D2/D3 复用**；D-P0 overlay 复现只为证明“加载正确源码”的方法。

### 1.3 Runtime / Adapter

| 项 | 值 |
|---|---|
| Rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（5,748 files） |
| Deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（1,061 files） |
| Podman / crun | `4.9.3` rootful / `1.14.1`；cgroup v2 + systemd；kernel `6.17.13-2-pve` |
| Python / SQLite / Node | `3.11.15` / `3.50.4` / `v22.23.2` |
| DSH SDK | `0.2.2-rc.2`（SDK `0.2.2rc2`）；runtime `1cc41d5a…` |
| Adapter | `lib/index.js` `2cb42461…`，`deterministic_match=true`；build-meta 固定 Node/TS |
| 资源上限 | Trusted/Candidate `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000`；stress 子容器实测 `pids.max=8`、`memory.max=134217728` |

### 1.4 本轮范围与**不批准**事项

**范围内**：D-G0/D-P0/D1/D2/D3 的双 Principal 隔离实现、真实 DSH（Fake Provider）正向、恶意 Candidate 攻击、跨主体故障/恢复、固定 OCI/Node 回归、D4 报告/矩阵/Packet。

**明确不批准**：真实 Provider Key/模型/HTTP/Live；`podman pull`；G4/G5/M0 GO；把 rootful Podman/宿主 root 之外的内核/运行时 0day 纳入主张；把本机 `CAN_ISOLATE` 外推到其它 Runner；用同一 Agent 自评替代 Independent Review。

---

## 2. D-G0 — 环境、源码与威胁假设冻结

| Case | 结论 | 证据摘要 |
|---|---|---|
| `D-G0-01` Git clean baseline | `PASS_AT_4BD4803` | `git status --porcelain -uall` 0 行；HEAD `4bd4803`；产品 drift 仅 D1-A 2 src + 1 test 与 D-P0 2 test/0 src；原 18:44 的 `BLOCKED_WORKSPACE_CONFLICT` 作为历史快照保留。 |
| `D-G0-02` Podman/userns | `PASS` | Podman 4.9.3 rootful、crun 1.14.1、cgroup v2；真实 userns `uid_map=0 65534 1`、`gid_map=0 65534 1 + 2000 2000 1`；`CapEff=0`、`NoNewPrivs=1`；setgid `root:2000 2750`；`podman ps -a` 空。 |
| `D-G0-03` canonical/Stage | `PASS` | rootfs/deps/stage 前后一致；10 个 Trusted 模块的 `inspect.getfile` 字节 SHA 等于 `git show 4bd4803` blob；旧 G3-C stage 不可复用。 |
| `D-G0-04` 0-Key/无外网/LiveGate | `PASS` | key-like env 名 0；无 `.env`；`run_live.sh` exit 3；`LiveGate` BLOCKED（4 reasons 不变）。 |
| `D-G0-05` DSH/Node/Adapter | `PASS` | DSH `0.2.2-rc.2`、runtime `1cc41d5a…`、Node `v22.23.2`、adapter `2cb42461…`；版本/产物 SHA 固定。 |

**D-G0 STOP 语义**：任一 UID/Namespace/Rootfs/Deps/Stage 不兼容、出现凭据/外网、Stage 身份不可证明，均 `BLOCKED`。本轮未触发。

---

## 3. D-P0 — Digest 勘误与 OCI 可移植性收口

### 3.1 两对 Digest（唯一正确关系）

```text
PreparedProviderRequest.request_digest == BrokerClaim.request_digest
FakeOutboundPayload_SHA256           == FakeReceipt.raw_sha256
```

- 两对保护不同字节：Prepared 对保护语义请求；Payload 对保护实际获准发送的 Fake 出站字节（含 nonce）。
- **不得**把两者合并，也**不得**要求 `prepared == payload`。关联字段 `call_id / reservation_id / attempt_id / nonce / receipt_id` 必须保留。
- v2 Reviewer §7 第 258 行是**文字错误**；R4 脚本实际字段比较正确（`claim.request_digest == prepared_digest` 与 `payload_digest == receipt.raw_sha256` 分开），因此判定 `DOCS_ONLY`，未改 `src/`、未改 v2 原文。
- 独立只读探针：6 datasets / 7 attempts 全部 `prepared==claim.request_digest`、`payload==receipt.raw_sha256`、两值不互等，0 例外。

### 3.2 OCI 两项可移植性（未放宽沙箱）

| 项 | RED | GREEN |
|---|---|---|
| 进程清理依赖 `pgrep` | 固定 OCI `FileNotFoundError: pgrep` | `/proc` + `os.kill(pid,0)` 正/负对照；找不到 broker 时显式失败，不产生假 PASS |
| `/tmp noexec` 下 exec wrapper | `PermissionError` | 可信 Python 读取 shadow Broker 模块，不 `execve`；保留没有任何可执行文件/包安装 |

- 固定 OCI full：**775 passed / 0 failed / 1 skipped**，exit 0；host full **773 passed / 2 failed / 1 skipped**（2 个 host-only 环境限制）。
- `--read-only --read-only-tmpfs=false`、`/tmp noexec`、`--cap-drop ALL`、`no-new-privileges`、`--network none`、`--user 65534` 全部保留。
- overlay 复现：1/1 pass，输家 `CONTROLLER_SINGLETON_LOCKED` exit 5，0 traceback，Fake=1，Attempt `SETTLED`；容器内实际加载 `b2f6af0` 源码，不是旧 `e6fde1c` Stage。

---

## 4. D1 — 双 Principal 正向集成

### 4.1 D1-A：最小 additive IPC 边界

| 变更 | 内容 |
|---|---|
| `BridgeServer.__init__` | 新增 `socket_mode`（默认 `0600`，只允许 `0600/0660`）、`socket_gid`（默认 `None`）、`expected_peer_uid`（默认 `None`）、`on_ready`；旧调用字节/行为不变。 |
| Socket 边界 | `bind → chmod →（仅合法时 chown）→ listen → verify stat`；Mode/GID/Owner 不符即失败，不静默放宽；`0666/0777` 拒绝；bool 拒绝。 |
| `SO_PEERCRED` | 接受连接后、任何读取/ack 前校验；`uid != expected_peer_uid` 记录 `PEER_UID_DENIED`、无 ack、无 Broker/Fake；`SO_PEERCRED` 不可用/长度错误 → fail-closed `PEERCRED_UNAVAILABLE`。`pid=0` 跨 PID namespace 正常，**不作为鉴权**。 |
| `on_ready` | 仅在 `listen()` 与权限校验完成后触发一次；Ready 由 Trusted 写 `state/ready`（0600，`O_NOFOLLOW|O_EXCL`），Launcher 独立复核 socket stat + `/proc/<pid>/net/unix` LISTEN + inode + 容器 running 后才启动 Candidate。 |
| Stale socket | 仅可信 Launcher/Controller 在受控路径操作；`lstat` + Owner/类型检查，防 symlink 与跨 Run 误删。 |

### 4.2 D1-01 真实 DSH Echo（正式 Gate Run）

| 项 | 值 |
|---|---|
| Run ID | `20261117T195848Z-d1-echo-87ab9355` |
| 命令 | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-echo --scenario echo --session g3d-d1-s1 --stage artifacts/g3d/stage-20261117T195831Z --evidence-dir artifacts/g3d/d1/echo` |
| UTC / 退出 | `19:58:48Z → 19:58:55Z`；Launcher/Trusted/Candidate 均 0 |
| 断言 | **29/29 PASS** |
| 账本 | 1 Reservation `OK`（`0.001022`）/ 1 Claim `COMPLETED` / 1 Attempt `SETTLED` / 1 Receipt / Fake counter=1 |
| DSH | `final_response="ok"`、`finish_reason="completed"`、13 events、session `g3d-d1-s1` |
| Usage | `{inputTokens:11, cacheReadTokens:2, cacheWriteTokens:0, outputTokens:5, reasoningTokens:0, totalTokens:18}`，与 receipt **字段级相等** |
| Prepared 对 | `claim.request_digest == attempt.prepared_digest == 9543ffbd5b16950a4a529a7016dbd249a9e4cea50f67a9a61c6a3ac257bf4f94` |
| Payload 对 | `attempt.payload_digest == receipt.raw_sha256 == 64f8f5552a3f10e8952b0c0f0b8b4eeb90c545650e82c8f1b10c0687bf42ed8c` |

### 4.3 D1-02 真实 DSH Tool 两轮（强制 Gate Run）

| 项 | 值 |
|---|---|
| Run ID | `20261117T195859Z-d1-tool-38773582` |
| 断言 | **33/33 PASS**；同一真实 Turn，2 次 Provider 请求 |
| 账本 | 2 Reservation `OK` / 2 Claim `COMPLETED` / 2 Attempt `SETTLED`（`tool_once`/`tool_final`）/ 2 Receipt / Fake counter=2 |
| Tool | `skill_lookup({"skill_id":"binary_search"})`；真实结果含 `binary_search` / `Binary Search` / `m0-skills-v1`，进入第二轮请求（`1205 → 1998` tokens） |
| Digest | 两轮各自的 `prepared == claim.request_digest`、`payload == receipt.raw_sha256`，4 个 Digest 两两不同 |
| Usage | 两轮 DSH step 1/2 usage 分别与对应 receipt **字段级相等** |

### 4.4 双 Principal / Socket / Peercred / Mount / Network / Cgroup

| 观测 | Trusted | Candidate |
|---|---|---|
| 容器 | `--userns=host --user 0:0`；`--network none --read-only --cap-drop ALL --security-opt no-new-privileges` | `--uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1 --group-add 2000 --user 0:0`；同上安全参数 |
| Host `/proc/<pid>/status` | `Uid/Gid 0/0`、`CapEff=0`、`NoNewPrivs=1`、`Seccomp=2` | `Uid/Gid 65534/65534`、`CapEff=0`、`NoNewPrivs=1`、`Seccomp=2` |
| uid_map / gid_map | `0 100000 65536`（Runner 嵌套 LXC 视角） | `0 65534 1` / `0 65534 1` + `2000 2000 1` |
| 挂载 | `/work/state`(rw)、`/output`(rw) 独有 | `/project`(ro)、`/deps`(ro)、`/work/g3b`(ro)、`/work/session`(rw)；**无** `/work/state`、`/output`、`/project/src` |
| Socket | `S_ISSOCK 0660 uid=0 gid=2000`；`ipc/ 2750 root:2000` setgid | 可连接；`unlink/rename/create` = `EROFS(30)` |
| Peercred | `bridge socket ready mode=0660 gid=2000 uid=0 peer_uid=65534`；`bridge peer accepted uid=65534 gid=65534 pid=0` | — |
| 网络 | `NetworkMode=none` | `AF_INET/AF_INET6 socket()` → `EACCES(13)`；DNS → `EAI_AGAIN(-3)`；仅 `lo`；无默认路由 |
| Cgroup | `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000` | 同左；`memory.current≈10–12MB`、`pids.current=1` |

**Candidate 边界自检**：`traces/principal.json` 的 `problems=[]`；`find_spec` 对 `autoteacher_m0/controller/broker/fake_backend` 均为 `None`；`PYTHONPATH=/deps`；无 Key-like env；无 Trusted 组件进程。

---

## 5. D2 — 真实 Candidate 攻击

### 5.1 方法与证据级别

- 每个攻击由 Host Launcher 启动真实 Candidate 容器（同一 mount/pid/net/ipc/uts/cgroup/user namespace、同一 uid_map/gid_map、同一组只读挂载），再用 `podman exec` 在**同一容器**内执行 Probe；每一条 errno 都来自内核，不是 Host mock。
- `D2-01..10、D2-12..15` 为 **Level A**（真实内核/协议）；`D2-11` 与攻击后正向为 **Level B**（真实 DSH/Controller/Fake）；Host 快照为 **Level C**（仅对账）。
- 每个 Case 独立 Run/容器名/State 快照；`pre` 在 Candidate 启动前、`final` 在攻击后；SQLite `-shm` 的 Host read-mark 不计入 `data_digest`，其余 DB/WAL/文件逐字节比较。

### 5.2 逐项结果（15/15 PASS）

| ID | 攻击 | 真实观测 |
|---|---|---|
| **D2-01** | 读 Broker DB/WAL/SHM | Candidate mountinfo 无 `/work/state`（`state_mounts=[]`）；7 个受保护路径读探针全 `ENOENT(2)`；有界搜索 0 命中；DB SHA/行数不变；0/0/0/0。21/21 |
| **D2-02** | 写/截断/替换 DB | `O_RDWR/O_CREAT/O_TRUNC/unlink/chmod/replace/hardlink/symlink` 全拒绝：`ENOENT(2)`、`EROFS(30)`、replace `EXDEV(18)`；state 目录写拒绝；哈希/行数不变。54/54 |
| **D2-03** | Policy/Admission/Attempt/Receipt | 10 类 × 6 操作 = 60 探针全 `ENOENT(2)`；无原文进入 Candidate stdout；哈希/行数不变。73/73 |
| **D2-04** | Broker 进程/import/FD | `find_spec`/import 全 `None`/`ModuleNotFoundError`；Trusted 源码/入口/Fake/DB `ENOENT`；broker/controller 私有 UDS `ENOENT`；仅见自身 PID/FD；0 行。33/33 |
| **D2-05** | 绕过 Controller 直接 Claim/Fake | 8 个 raw-UDS 负例：`kind=reserve/claim/settle` → `UNKNOWN_KIND`；`reservation_id/claim_id/authorized/dispatch_allowed` → `UNKNOWN_FIELD`；bridge `unlink` `EROFS(30)`；负例后 0 套账本；随后真实请求恰好 1 套、counter=1。27/27 |
| **D2-06** | 伪造 admission/call/route/tools/坏帧/Socket 替换 | 18 个负例：`UNKNOWN_FIELD`×8、`ROUTE_MISMATCH`×2、`ADMISSION_TOOL_SCHEMA_MISMATCH`、`PREPARED_DIGEST_MISMATCH`、`SEQ_OUT_OF_ORDER`、`REQUEST_INVALID`×2、`DUPLICATE_KEY`、`DEPTH_EXCEEDED`、`FRAME_TOO_LARGE`；Socket 替换全失败（`EROFS/EADDRINUSE/EXDEV`）；攻击后 socket 仍 `0660 root:2000`；正向 1 套、counter=1。40/40 |
| **D2-07** | 外网/DNS/其它 UDS | `AF_INET/AF_INET6/UDP socket()` → `EACCES(13)`；TCP connect → `EACCES`；DNS → `EAI_AGAIN(-3)`；`if_nameindex=['lo']`；无默认路由；podman/docker/systemd/dbus UDS `ENOENT`；唯一可连 `/work/g3b/bridge.sock`。28/28 |
| **D2-08** | `/proc`、FD、environ、`/sys`、`/dev`、mount、ptrace、cap、userns、runtime socket | `CapEff/CapPrm/CapBnd=0`、`NoNewPrivs=1`、`Seccomp=2`；Trusted `/proc` 条目全 `ENOENT`；`/proc/kcore EACCES(13)`；core_pattern/hostname/sys 写 `EROFS(30)`；`mount EPERM(1)`；ptrace Trusted `ESRCH(3)`、ptrace init `EPERM`；`setuid(0) EINVAL`；嵌套 userns 可建，但 Host UID 仍 65534、state 仍 `ENOENT`。40/40 |
| **D2-09** | 不可信 Tool/插件/Guard 伪造 | Candidate 本地工具真实执行 `D2_LOCAL_TOOL_OK`；自写 `evil_guard.py` 的 `approve()` 仅本地；自写 `forged-admission.json`（SHA `434bf5dc…`）未被 Controller 使用；5 个携带 authorized/guard/admission_id 的请求 4×`UNKNOWN_FIELD`+`ROUTE_MISMATCH`；负例 0 行；正向 1 套、counter=1。25/25 |
| **D2-10** | Candidate SIGKILL/半帧/断连/重连/重发 | 发送前 SIGKILL=137、半帧+半关闭 → `REQUEST_INVALID`、发送后/ack 后 SIGKILL=137、首 chunk 后关闭、同 call 重发 → `ATTEMPT_ALREADY_STARTED`；最终 2 套 `OK/SETTLED`、counter=2，无重复 call；Trusted 故障子 Run 保持 `PENDING/ATTEMPT_STARTED/RESPONSE_OBSERVED`，receipt 0/1，未 FREE。24/24 + 15/15 + 15/15 |
| **D2-11** | 正向反误伤 Echo/Tool/Resume | Echo 1 套、Tool 2 套独立账本、Resume 两个真实 Candidate 进程共享同一 Session（14→24 行、`reason:"resume"` 1），2 SETTLED、counter=2、无旧 Attempt 重放；DSH usage 与 receipt 字段级相等。38/38、42/42、27/27 |
| **D2-12** | Slowloris/超大帧/子进程/FD/Memory/CPU | 同 UID stress 容器：`pids.max=8`、`memory.max=134217728`、`cpu.max=100000 100000`；fork 7 后 `EAGAIN(11)`；120MB 后 OOM exit 137；fd 4093 后 `EMFILE(24)`；第 9 条 slowloris `TOO_MANY_CONNECTIONS`；16 超大帧 `FRAME_TOO_LARGE`；释放后正向完成；Trusted fds 12→12、threads 1→1。21/21 |
| **D2-13** | DAC 对照（**CONTROL**） | 同 UID map 的 control 容器额外只读挂载 `$RUN/state`；10 个 state 文件读/写/truncate/unlink 全 `EACCES(13)`；目录写 `EISDIR(21)`；state digest 不变。66/66。**仅 CONTROL，不是正式 Candidate 配置** |
| **D2-14** | 同 UID stale Run 访问本 Run UDS | stale Candidate 挂载另一 `stale-ipc`：stale socket `ECONNREFUSED(111)`；本 Run live 路径/`/proc/1/root`/相对逃逸全 `ENOENT(2)`；`/work/state ENOENT`；Trusted pid `ENOENT`；inode 不同；live listener 仍在。24/24 |
| **D2-15** | 两对 Digest 身份 | 真实 Echo：`claim.request_digest == attempt.prepared_digest = b2d0c8d0…`；`receipt.raw_sha256 == attempt.payload_digest = 4e6a9dd9…`；两值 64-hex 且不相等。42/42 |

### 5.3 旧四个同 UID 绕过全部关闭

| 旧 G3-B 绕过 | 当前结果 | 关闭机制 |
|---|---|---|
| B-1 读 Broker DB | D2-01：路径 `ENOENT(2)`、DB SHA 不变、0 行 | Candidate mount namespace 无 `/work/state`；state `0700 root:root` |
| B-2 写 Broker DB | D2-02：`ENOENT/EROFS/EXDEV`；无事务/哈希变化 | 无挂载 + rootfs/state 只读/不可达 |
| B-3 写 Policy | D2-03：60 探针全 `ENOENT(2)`；哈希/行数不变 | Candidate 无 state 副本；Trusted 独占 |
| B-4 绕过 Controller 直接 Claim | D2-04/05/06：import 失败、私有 UDS `ENOENT`、`UNKNOWN_KIND/FIELD`、Fake=0 | Candidate Stage 无 Broker 代码/DB/Socket；Controller 唯一 Claim |

**19 个 Run 合计**：Reservation 14、Claim 14、Attempt 14、Receipt 13（`D2-10-trusted` 在 Fake 发送前被杀，无 receipt）；所有有 cost 的行 cost>0，无 FREE/NOT_DISPATCHED；`podman ps -a` 空；rootfs/deps/stage 每 Run canonical。

---

## 6. D3 — 跨 Principal Crash / Cancel / Replay / Recovery / Streaming

### 6.1 总览（17/17 矩阵行 PASS）

- 13 个 case/suite，所有单 run `exit 0`；每个 crash 注入都是真实进程/内核动作，恢复均为**新的真实 Trusted 进程**读取同一 state 后由产品 `reconcile_on_startup` 处理。
- 未发现 P0（未授权发送、自动重发、假结算、误 FREE、Candidate 读 Trusted state）。

### 6.2 崩溃窗口

| Case | 注入/快照 | 恢复后 |
|---|---|---|
| **C02** Candidate 预 Reserve SIGKILL | `137`；kill 快照 0 Reservation/Claim/Attempt/Receipt/counter | 同一 Trusted 仍 running；随后真实 Echo 1 套 `SETTLED` |
| **C03** Claim 后、`ATTEMPT_STARTED` 前 crash | claim=1、Attempt=0、Receipt=0；Reservation `PENDING 0.00155`；intent `CLAIMED` | 新 Trusted exit 3（`ADMISSION_REPLAYED_AFTER_RECOVERY`）；intent `HELD_UNCERTAIN/CRASH_BEFORE_SEND_NO_EVIDENCE`；无 Fake/重发 |
| **C04** `ATTEMPT_STARTED` 后、Fake 前 crash | Attempt `ATTEMPT_STARTED`、intent `CONSUMED`、Receipt=0、Reservation `PENDING` | 新 Trusted：`SETTLEMENT_UNCERTAIN/NO_RECEIPT_AFTER_CRASH`；receipt/counter 不增；无自动发送 |
| **C05** Receipt 后、结算前 crash | Attempt `RESPONSE_OBSERVED`、Receipt=1、Broker `PENDING`、messages=1 | 新 Trusted 验证 receipt+usage，**恰好 settle 1 次**（messages 1→2、Broker `OK 0.001022`、Attempt `SETTLED`）；第二次重启 0 次、receipt/counter 仍 1 |
| **C06** Broker 已结算、Journal 未标 crash | Broker `OK 0.001022`（messages=2）、Attempt `RESPONSE_OBSERVED` | 新 Trusted 以 Broker `OK` 为权威，直接 `SETTLED`；messages 仍 2（无二次 settle）；无 `WORST_CASE_HELD` |

### 6.3 Cancel / Disconnect / Deadline

| 场景 | 结果 |
|---|---|
| **C07 before_send** | Broker `SIGSTOP` 后请求进入 Reserve；cancel → client `CANCELLED`；Attempt=0、Fake=0、Claim=0；Reservation `PENDING 0.00155`；intent `HELD_UNCERTAIN/PRE_SEND_ABORT:_Cancelled`。8/8 |
| **C07 after_send** | receipt 已落盘后 cancel；client `CANCELLED`；Attempt `SETTLED`、Reservation `OK 0.001022`、Receipt=1；**无 Fee=0**。5/5 |
| **C07 two_streams** | 两个 UDS 连接：A `CANCELLED`、B `finish`；2 Claim/2 Receipt，均 `SETTLED 0.001022`。6/6。**Controller payload 单飞**，这是“两个连接、一个 active + 一个 queued”，不是两个并发 Provider 调用 |
| **C08 half_close** | `shutdown(SHUT_WR)` 后请求仍完成；1 Receipt、`SETTLED 0.001022`；无 FREE。5/5 |
| **C08 disconnect_mid_stream** | 客户端中途关闭；1 Receipt、`SETTLED 0.001022`；无伪造成功/Fee=0。5/5 |
| **C08 Trusted SIGTERM** | 流进行中 SIGTERM；Trusted 退出、socket 消失；0 orphan；最终 Attempt `ATTEMPT_STARTED`、Reservation `PENDING 0.00155`、Receipt=1（保守，不伪造 Cancel/Fee=0）。4/4 |
| **C09 Broker SIGSTOP** | 真实 broker 被 `SIGSTOP`；**2.5219s** 返回 `DEADLINE_EXCEEDED`；Trusted 仍 running；0 Reservation/Attempt/Receipt；仅 durable request-identity 行。8/8 |
| **C09 Fake no-frame** | receipt 已写、35s 无帧；**3.5147s** 返回 `DEADLINE_EXCEEDED`；Attempt `SETTLEMENT_UNCERTAIN`、Reservation `PENDING`、Receipt=1；未 settle。7/7 |
| **C09 首帧 stall** | `slow_usage` 1.2s 首帧、admission deadline 800ms；**0.8085s** 返回 `DEADLINE_EXCEEDED`；同样保守。7/7 |

### 6.4 Streaming 与并发

| 项 | 观测 |
|---|---|
| **C10 首 Chunk 先于 Fake 退出** | DSH `stream_time0[0]=1794954332813 ms` → host monotonic 估算 `1856889.8140`；Fake `first_chunk_flushed.monotonic=1856889.8140`；Fake `exit_after_finish.monotonic=1856891.8185`；**T1 < T2，提前 2.0045s**；`stream_slow`、1 SETTLED、usage==receipt；不是 buffered replay。17/17 |
| **C11 real-DSH 并发** | 两个真实 Candidate 容器**同时 running**；同 prompt、不同 session；2 个 identity（logical_step 0/1），`identity_digest`/`call_id` 两两不同；2 Claim/2 Attempt/2 Receipt、counter=2；均 `SETTLED 0.001022`。**这是两个合法独立请求，不是同请求重放**。16/16 |
| **C11 same-claim 负例** | 受控双真实 Controller（两个 UDS）+ 共享 AttemptJournal/Broker/Fake；两个客户端同 sessionId/messages/tools、均 logical_step 0、同一 business digest；**恰好 1 finish、1 `ATTEMPT_ALREADY_STARTED`**；1 Reservation/Claim/Attempt/Receipt、counter=1；2 admission 行。**只能作为受控 same-claim 负例，不能拼成 real-DSH same-claim PASS**。14/14 |
| **C12 10+ 重启/压力** | 1 次真实 Echo 后 **10 次**真实 Trusted 重启（新进程/新容器、同一 state）；每次 reconcile 后 `ADMISSION_REPLAYED_AFTER_RECOVERY` exit 3；快照 1/1/1/1 不变、0 新 Receipt/Claim；每轮 `podman ps -a` 空、canonical；stress `pids.max=8`、fork 7 后 `EAGAIN(11)`；最终 1/1/1/1。62/62 |

### 6.5 D3 回归

| Case | 结果 |
|---|---|
| **REG-01 固定 OCI full** | `exit 0`；**916 tests / 0 failed / 0 errors / 7 skipped / 4 explicit known deselects**；JUnit `3937cd12…`；argv/UTC/stdout/stderr 全保存。 |
| **REG-02 Node** | Node `v22.23.2`；`runtime-budget-guard` **19/19** exit 0；`skill-lookup` build exit 0、**8/8** exit 0。Host 运行，不是 DSH Candidate。 |
| **REG-03 清理/canonical** | `podman ps -a` 空；0 `at-g3d-*`；0 controller/broker/fake/candidate 残留；rootfs `25491e45…`、deps `e07729d7…`、stage `e1ff1449…` 前后一致；仅移除 root-owned 空 `rootfs/evidence` mount target。 |
| **REG-04 账务** | 24 个 case 证据目录、25 个 attempt 对、0 problems；两对 Digest 分开成立、Broker OK、cost>0。 |

**D3 测试计数**：`tests/integration/g3d` 144、`g3_bridge` 31、`g3c` 110、`gates` 14 → **299 passed / 0 failed**；Ruff 0.17.5 `All checks passed`。

---

## 7. 账本与 Digest 两对关系（跨阶段结论）

| 关系 | 证据 |
|---|---|
| `PreparedProviderRequest.request_digest == BrokerClaim.request_digest` | D1 Echo/Tool、D2-11/15、D3 C01/C05/C10/C11 的 Claim/Attempt 逐对照；REG-04 25 对全成立 |
| `FakeOutboundPayload_SHA256 == FakeReceipt.raw_sha256` | 同上；每份 receipt 的 `raw_sha256` 与 Attempt `payload_digest` 相等 |
| 两对**不要求互等** | 所有 SETTLED 对中 `prepared != payload`；D2-15、D3 REG-04 显式断言 |
| 关联字段 | `call_id/reservation_id/attempt_id/nonce/receipt_id` 跨 Prepared/Claim/Attempt/Receipt/Broker 一致；不以列表位置配对 |
| Usage → Receipt → Broker | DSH usage 与 receipt usage 字段级相等；Broker `OK` + cost>0 与 Attempt `SETTLED` 成对；崩溃窗口保持 `PENDING/SETTLEMENT_UNCERTAIN` 且 cost 不为 0 |

---

## 8. 测试计数（实际执行）

| 套件 | D1 | D2 | D3 | D4（本轮最终） |
|---|---|---|---|---|
| `tests/integration/g3d` | 111 | 130 | 144 | 含于 host full |
| `tests/integration/g3_bridge` | 31 | 31 | 31 | 含于 host full |
| `tests/integration/g3c`（冻结） | 110 | 110 | 110 | 含于 host full |
| `tests/unit/security/test_gates.py` | 14 | 14 | 14 | 含于 host full |
| Host 小计 | 266 | 285 | 299 | **917 passed / 2 known env failed / 1 skipped（920 tests）** |
| 固定 OCI full | — | — | **916 tests / 0 failed / 7 skipped / 4 deselects** | **916 tests / 0 failed / 7 skipped / 4 deselects，exit 0** |
| Node Guard / Skill | — | — | 19/19、8/8 | **19/19、build 0、8/8** |
| Ruff | 0.16.2 pass | 0.17.5 pass | 0.17.5 pass | **0.17.5 `All checks passed`** |

**D4 host 的 2 个失败**（既有 host-only 环境限制，不是本轮引入，也不被隐藏）：

1. `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`：普通 checkout 的 `config/dsh/*` 是 `0644`；只读部署/固定 OCI 中由 `0444` 满足。
2. `tests/integration/sandbox/test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked`：测试硬编码 `PYTHONPATH=/project/src:/deps`，宿主无 `/project`。

**D4 固定 OCI 的 4 个显式 deselect**（rootfs 无 `tar`/`git`、uid 65534）：

1. `test_manifest_tree_accepts_matching_stage`
2. `test_manifest_tree_detects_unknown_extra_and_tamper`
3. `test_manifest_tree_detects_symlink`
4. `test_admission_launcher_uid_is_not_the_socket_peer_uid`

另有 **7 skipped**：5 个 root-only UDS/布局测试、1 个 `git` diff 测试、1 个既有 external public probe mount skip。**0 个产品失败/错误**。Host pytest 覆盖被 deselect 的 tar 树哈希与 root 契约；未修改 D1-A 冻结测试。

> D4 备注：第一次 OCI 尝试用 `git archive` 的 `0644` 文件模式，命中上述 `target_profile_static` 的**既有** host-only 语义（当时 908 passed / 1 failed）；随后按 D3 REG-01 的只读冻结树形态（文件 `0444`、目录 `0555`）重新物化并重跑，得到 909 passed / 7 skipped / 916 tests / 0 failed。两次原始日志都在 Packet 的 `regressions/` 中，未删除失败尝试。

---

## 9. 0-Key / 0 外网 / LiveGate / 清理

| 项 | 结果 |
|---|---|
| Host key-like env 名 | **0**；无 `.env`（仅 `.env.example`） |
| `run_live.sh` | **exit 3**（`SECURITY_BLOCKED`） |
| `LiveGate().inspect(live_requested=True)` | **BLOCKED**，4 reasons 不变：`EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`、`BASELINE_EVIDENCE_MISSING`、`ACTUAL_TOOL_REGISTRY_NOT_APPROVED`、`SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED` |
| 真实模型/外部 HTTP | **0**：39 份 D1/D2/D3 Fake receipt 全 `synthetic=true`、`real_model_calls=0`、`http_calls=0`、`network_used=false`；0 anomalies |
| 容器网络 | 273 个 D1/D2/D3 `inspect-*.json` 全 `NetworkMode=none`；无 `AF_INET` 成功连接 |
| 容器/进程/socket | `podman ps -a` 0；`at-g3d-*` 0；controller/broker/fake/candidate 残留 0；无 bridge.sock |
| Rootfs/deps/stage | D4 前后 `25491e45…` / `e07729d7…` / `e1ff1449…`；仅移除 OCI 运行产生的 root-owned 空 `rootfs/evidence` mount target |
| `podman pull` | 未执行；无新 image |

---

## 10. 矩阵

- 文件：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`
- **53 行；52 PASS / 1 NOT_RUN**。
- 本轮只改 `D0-01`：`NOT_RUN → PASS`，引用 D0 设计 `981e4ed` + `M0_G3D_G0_REBASELINE.md` 的 `PASS_AT_4BD4803` 与现场 hash；其他 51 行字节不变。
- `D-REVIEW-01` 保持 **`NOT_RUN`**，`reviewer_status` 留空；Independent Reviewer 出具裁定后才可更新。
- 历史 G3-C 矩阵 `Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv` **未修改**（C 53 PASS / D 16 NOT_RUN 为历史状态）。

---

## 11. 残余风险与明确未主张

### 11.1 残余（详见 `docs/M0_G3D_FINDINGS_AND_DISPOSITION.md`）

- D2：嵌套 user namespace 可用（内核残余）；Candidate session 无磁盘硬配额（P2）；无 Candidate 侧 Guard 组件；D2-13 是 CONTROL；per-Run path 不是 per-Run token；Trusted crash hook 是 test-only；单机 rootful Podman/Trusted root 属 TCB。
- D3：C11 real-DSH 并发是两个独立请求 + 受控 same-claim 负例（不合并）；C07 “双流”是单飞 Controller 下两个连接；C09 Broker 只 SIGSTOP 不重启；C08 SIGTERM 故意留保守状态；C10 用 host realtime/monotonic 换算；C12 重启只 reconcile 不接新 admission；OCI 4 deselect/7 skip；Node 为 host 运行。
- G3-C P2（SRC-12、P2-4、P2-6）承接说明见 Findings 文档；本轮不重复开旧架构项。

### 11.2 明确未主张

1. **独立复核前不签 `G3-D PASS`**。本报告的所有 `*_GATE_PASS` 都是 Owner 自评，最终裁定只能由未参与 D1/D2/D3 的 Reviewer 出具。
2. 不主张 `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE` 已成立；该裁定需 D1 正向 + D2 实测拒绝 + D3 无 Key 恢复一致性 + 独立复核四者同时满足。
3. 不主张 Live / G4 / G5 / M0 GO；`run_live.sh` 仍 exit 3、LiveGate 仍 BLOCKED。
4. 不主张内核/容器运行时 0day 防护、宿主 root 攻陷防护、供应链完整性、真实 Provider invoice/账单、远端 exactly-once。
5. 不主张 `CAN_ISOLATE` 可迁移到其它 Runner；本机 rootful Podman 4.9.3 + crun 1.14.1 + LXC 嵌套是已记录的受信基础。
6. 不主张 Candidate session 的磁盘 DoS 防护（无硬配额，P2 残余）。
7. 不主张 D2-13 的 DAC CONTROL 可替代正式 Candidate 无 state 配置。
8. 不把 real-DSH 两个独立请求说成“real-DSH same-claim PASS”；same-claim 结论只来自受控双 Controller/UDS 负例。

---

## 12. D4 交付物与复现入口

| 交付物 | 路径 |
|---|---|
| 本报告 | `docs/M0_G3D_IMPLEMENTATION_REPORT.md` |
| Independent Reviewer 指令 | `docs/M0_G3D_REVIEW_REQUEST.md` |
| 残余风险登记/处置 | `docs/M0_G3D_FINDINGS_AND_DISPOSITION.md` |
| 矩阵 | `docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv` |
| Review Packet | `artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26/` |
| Packet builder | `scripts/g3d/build_packet.py` |
| D4 回归原始日志 | `artifacts/g3d/d4/regression/`（OCI/host/Node/Ruff/canonical/LiveGate/zero-key） |
| D1/D2/D3 证据 | `artifacts/g3d/d1/`、`artifacts/g3d/d2/`、`artifacts/g3d/d3/` |

**复现**：见 `docs/M0_G3D_REVIEW_REQUEST.md` §2 与 Packet 的 `review/reviewer-reproduction.md`。所有命令为 host-side 或固定 rootfs 容器，**不得**使用真实 Key/模型/HTTP/Live，**不得** `podman pull`。

---

## 13. 提交边界与 STOP

- 本 Agent 只写 `docs/`、矩阵、`scripts/g3d/build_packet.py` 与 Packet 构建物；未改 `src/`、D1-D3 证据、旧 G3-C Packet、历史 docs、Stage/Rootfs/Deps。
- 不 amend、不 push。
- **STOP**：等待 Lead 指派未参与实现的 Independent D Reviewer；复核前 `D-REVIEW-01` 保持 `NOT_RUN`，不得把 G3-D 标为终审 PASS。
