# M0 G3-D0 — Lead 签核草案（D0 → D1 准备）

> **状态**：`D0_PRE_SIGNOFF_ACCEPTED_PENDING_MAINTAINER_AUTHORIZATION`（Lead 预签，**不是** G3-D PASS，**不是** D1 实施授权）。
> **日期**：2026-11-17 ｜ **角色**：G3-D 预研/签核 Agent（受 Lead 委托起草）｜ **工作树**：`/root/Autonomous Teacher`
> **基线**：HEAD `fff3623`（`docs: archive G3-C independent review v2 (PASS) and final errata (no-key)`）；G3-C 代码冻结点 `b2f6af0`；D0 设计 `docs/M0_G3D_OS_BOUNDARY_DESIGN.md`（1326 行，sha256 `2cf03c99…`，commit `981e4ed`）。
> **范围**：本文件只记录 Lead 对 D0 六项（O-D1..O-D6）的逐项签核建议、D1 前必须由维护者批准的事项、以及范围/非主张。**不实现、不启动容器、不修改产品代码/测试/脚本/证据/Packet、不 commit/push**；所有 D1/D2/D3 结论仍待实施与独立复核。
> **规则**：`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；D 矩阵 16 行仍为 `NOT_RUN`。本文件不能用于解除 LiveGate、接入 Key、启动 G4/G5/Live。

---

## 0. 六条预签结论（摘要）

| 项 | 预签结论 | 条件/边界 |
|---|---|---|
| **O-D1 IPC 方案** | **接受 D0 的方案 A（additive）作为 D1 实现基线** | 前提是维护者批准；`BridgeServer` 新增 `socket_mode`/`socket_gid`/`on_ready` 与可选 peercred；默认 0600、默认不校验 peer，保持 G3-C 旧测试；隔离模式 `chmod 0770` + `peer_uid=65534`，不改协议字段/语义。备选 B 仅作为 A 无法实施时的 fallback。 |
| **O-D2 Principal 映射** | **接受** candidate 父 UID 65534 / trusted 父 UID 0 的双 Principal 设计 | 独立 user/mount/pid/net/ipc/uts/cgroup namespace；candidate 只读代码/依赖；trusted 独占 Broker/Attempt/Admission/Receipt/Policy；`admission.launcher.uid` **必须保持 65534**，不得写成 trusted 0。 |
| **O-D3 挂载/存储** | **接受** D0 §2.4/§4 的 ro/rw 目录清单与 synthetic `passwd`/`group` | 唯一共享路径是 IPC 目录（2750 root:2000）；socket 0770 root:2000；candidate `--group-add 2000`；candidate 不挂 state/evidence/logs/repo/Key/launcher 控制面；tmpfs `/tmp`、`/work` = 1777。 |
| **O-D4 生命周期/清理** | **接受** 独立 host launcher + 两容器一次性运行层 | trusted 先就绪、candidate 后启动；进程组/容器信号；socket/挂载/子进程清理；`podman ps -a` 空、无孤儿、socket 不存在；每次前后重算 rootfs/deps canonical；避免共享 rootfs 哈希漂移。 |
| **O-D5 D2 攻击矩阵** | **接受** D2-01..D2-12 的“真实 candidate 身份执行”映射 | 每条必须有 candidate 内命令、真实 errno/协议拒绝、uid_map/gid_map/mountinfo、DB/Receipt 前后 hash；旧 Reviewer 四个绕过必须逐条改为内核/协议拒绝；禁止 host/trusted 伪造 candidate 结果。 |
| **O-D6 D3 组合回归** | **接受** 正向 Echo/Tool/Resume + 跨主体 crash/cancel/cleanup + 同 SHA 复现 | 不解除 LiveGate、不接 Key、不做真实模型/外网；D3 仍需独立 D Reviewer；D2 高风险项真实拒绝是 D3 通过前提。 |

> **总体预签**：D0 设计足以进入 D1 准备与实施计划阶段；但 D0 不是 `PASS_FOR_G3D_*`，D1 实施与任何 `OS_TRUST_BOUNDARY` 状态变更都必须由维护者另行授权，并由独立 D Reviewer 复核真实证据。

---

## 1. 本次现场核实（只读）

### 1.1 Git / 证据身份

| 检查 | 现场结果 |
|---|---|
| `git rev-parse HEAD` | `fff36232687afb779befb49fb6e2a10cedbcb7fd` |
| `git status --porcelain` | 空（clean） |
| 远端 `origin/main` | `fff3623`（与本地 HEAD 一致） |
| G3-C 二次独立复核 | `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`（`docs/REVIEW_G3C_INDEPENDENT_v2.md`，Reviewer #2；P0=0/P1=0，P2 记录性 5 项） |
| G3-C 代码冻结点 | `b2f6af054555705192c4e1ae3019a68078764736`（PR1 fix；父 `78be77c`） |
| `git diff --stat b2f6af0..HEAD -- src tests` | 空（**代码/测试与 `b2f6af0` 一致**；HEAD 的差异只在 docs 与 `scripts/g3c` 归档/复现脚本） |
| D0 设计文件 | `docs/M0_G3D_OS_BOUNDARY_DESIGN.md`，1326 行，sha256 `2cf03c9907140daf484026940b2bd8f0c7eec9478f985833ec6378d2f620ee7d`，commit `981e4ed` |
| D 矩阵 | `docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv` 共 16 条 D 行，全部 `NOT_RUN`，`reviewer_verdict` 空 |
| `OS_TRUST_BOUNDARY` | `B0-02=BLOCKED`（G3-C 复核 v2 §0/§10 明确未改变） |

**D0 行号与当前现场的差异（必须说明）**：D0 §0.4 自己已提示“行号只用于定位设计缺口，D1 以 C 冻结为准”。当前 `ipc_server.py` 已是 521 行的 G3-C 版本，`serve_forever()` 在 `170-225`，`bind` 后固定 `chmod(..., 0o600)` 在 **179 行**；D0 正文中“约 179 行/约 101 行”的旧估计不再作为实施行号。本签核与 D1 计划全部使用 **`fff3623` 现场行号**。

### 1.2 环境事实（复核 D0，未启动容器）

| 项 | 现场结果 |
|---|---|
| 宿主身份 | `uid=0(root)`；当前 LXC userns `0 100000 65536` |
| Podman / runtime | `podman 4.9.3`，rootful（`rootless=false`），crun `1.14.1`，cgroup v2 |
| cgroup controllers | `cpuset cpu io memory hugetlb pids rdma misc dmem`；Podman 报告 `memory,pids` |
| `/etc/subuid`、`/etc/subgid` | 均为空（rootless/keep-id/auto 不可用；D0 已实测） |
| kernel | `6.17.13-2-pve`（Ubuntu 24.04.4 LTS，LXC） |
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（本次重算一致） |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（本次重算一致） |
| gid 2000 | `getent group 2000` 无输出（未被宿主其它组占用；D1 preflight 仍需断言） |
| 容器 | `podman ps -a` 为空；无 `at-g3d-*` 残留 |
| `SO_PEERCRED` | 宿主 Python 可用：`SOL_SOCKET=1`、`SO_PEERCRED=17`、`struct.calcsize("3i")=12`；socketpair 返回 `(pid, uid, gid)`。跨 pidns 时 `pid=0`，不可用于鉴权（D0 P-05）。 |

> 本次没有启动任何容器、没有 `podman pull`、没有读取 Key、没有外网/模型调用；只做了 `git`/`stat`/`sha256sum`/宿主 Python 只读检查。

### 1.3 未重跑/UNVERIFIED（D1 必须实测）

| 项 | 状态 | 说明 |
|---|---|---|
| 容器级 `--uidmap 0:65534:1`/`--gidmap`/`SO_PEERCRED`/`--network none`/cgroup | **UNVERIFIED（沿用 D0 P-04/P-05/P-08 的实测）** | 本次未启动容器；D1 preflight 必须在目标 Runner 上重跑并记录原始 argv/errno |
| socket 0770 root:2000 + setgid 继承 + cap-drop 下 `chmod` | **UNVERIFIED（D0 P-05 有 770/2000 结果，但 D1 配置组合需重验）** | D1 `on_ready` 必须 `stat` 断言；失败不得继续 |
| trusted `--cap-drop ALL` 下 `chown` 不可用 | **推导**（基于 Linux `CAP_CHOWN` 语义） | D1 不依赖 `chown`；以 setgid 目录为准；若要 `socket_gid`，必须在 preflight 证明 cap 可用 |
| D2-01..D2-12 的 errno/协议拒绝 | **计划/未执行** | 本文件只签核映射，不作为 PASS 证据 |
| D3 正向/故障矩阵 | **计划/未执行** | 必须由 D1/D2/D3 真实运行产生 |
| `--systemd=false`/`--timeout 300`/`--ulimit` 等 argv | **D0/G3-C 基线，未在本次重跑** | D1 首次启动逐项记录，不临时改参数 |

---

## 2. 逐项签核

### 2.1 O-D1 — IPC 方案选择：建议方案 A（additive）

#### 2.1.1 当前硬缺口（现场核对）

| 位置 | 现场 |
|---|---|
| `src/autoteacher_m0/bridge/ipc_server.py:178-181` | `server.bind(...)` 后无条件 `os.chmod(self.socket_path, 0o600)`，再 `listen`/`settimeout` |
| `BridgeServer.__init__` `:127-157` | 只接受 controller/socket_path/四个时限/连接参数；无 socket mode/gid/ready hook/peer 校验 |
| `BridgeServer._connection_thread` `:255-268` | `accept` 后直接 `handle_connection`，无 `SO_PEERCRED` |
| `src/autoteacher_m0/bridge/controller.py:1608` | `BridgeServer(controller, config["socket_path"])`，没有传任何隔离参数 |
| `controller.py:1555-1560` | 配置只允许 `required` 集合加上 `fake_python`；新增 socket 字段会被 `CONFIG_INVALID` 拒绝 |
| `grep` 检索 `SO_PEERCRED`/`peercred`/`socket_mode`/`on_ready`（`src`、`tests`） | 0 匹配（现场确认不存在） |

因此，D1 若不改这一点：candidate（父 65534、group 2000）连接 0600 root socket 会 `EACCES(13)`，正向 DSH 必失败；若改成 0666 则违反最小权限。**必须二选一**。

#### 2.1.2 推荐：方案 A（direct，additive）

**理由**：
1. 只保留一个 UDS，不增加 trusted-side 代理进程和额外生命周期/攻击面；
2. controller 直接看到 candidate 的 `SO_PEERCRED`，可在 transport 层做附加鉴权；
3. 改动是 additive 的：默认 `0600`、默认无 gid、默认无 peer 校验，G3-C 旧测试与旧调用方行为不变；
4. 不需要改协议字段、状态机、错误码集合或 ack 语义。

**最小 diff 形状（不实现，仅轮廓）**：

| 文件/位置 | 当前 | D1 最小改动 |
|---|---|---|
| `ipc_server.py:127-131` | 4 个 keyword-only 参数 | 追加 5 个 keyword-only 参数，默认值不改变旧行为；精确签名见下方代码块 |
| `ipc_server.py:132-149` | 现有校验/赋值 | 增加 mode 白名单 `{0o600, 0o660, 0o770}`（拒绝 0666）；gid/uid 非负整数；`peer_gids` 非空 int 元组且仅当 `peer_uid` 配置时允许；`on_ready` 若提供必须 callable；`peer_uid is not None` 且 `not hasattr(socket, "SO_PEERCRED")` 时启动即失败（fail-closed）；保存字段 |
| `ipc_server.py:178-181` | `bind` → `chmod 0600` → `listen` → `settimeout` | `bind` → `os.chmod(self.socket_path, self.socket_mode)` → 仅当 `socket_gid is not None` 时 `os.chown(self.socket_path, -1, self.socket_gid)` → `listen` → `settimeout` → 仅当 `on_ready is not None` 时调用一次 `on_ready()`（在开始 `accept` 之前） |
| `ipc_server.py:255-268` | 直接 `handle_connection` | 在 `try` 内、`handle_connection` 前调用 `_authorize_peer(context.sock)`；不通过则记录 `PEER_REJECTED`、关闭并返回（finally 仍清 active/thread）；**不发送协议 error 帧**（错误码集合没有 peer-auth 码，关闭即 fail-closed） |
| `ipc_server.py:280-283` 附近 | `_record_connection_failure` | 新增 `_authorize_peer(sock) -> bool`：`struct.unpack("3i", sock.getsockopt(SOL_SOCKET, SO_PEERCRED, 12))`；只校验 `uid`（以及可选的 `gid` 白名单）；**忽略 pid**（跨 pidns 为 0）；`getsockopt` 失败也拒绝 |
| `controller.py:1550` | `def main(argv=None) -> int` | 追加 keyword-only `on_ready`（默认 `None`）；`python -m` 调用不受影响 |
| `controller.py:1555-1560` | 只允许 `fake_python` 可选 | 把 `socket_mode`/`socket_gid`/`peer_uid`/`peer_gids` 加入可选集合，并做类型/范围校验；未知字段仍 `CONFIG_INVALID` |
| `controller.py:1608` | `BridgeServer(controller, socket_path)` | 传 `socket_mode=config.get("socket_mode", 0o600)`、`socket_gid=config.get("socket_gid")`、`peer_uid=config.get("peer_uid")`、`peer_gids=tuple(...) if ... else None`、`on_ready=on_ready` |
| `$STAGE/trusted/run/trusted_entry.py`（D1 新增） | — | `umask 007`；校验 `/work/state`、`/work/g3b` owner/mode；调用 `controller.main(["--config", ...], on_ready=write_ready)`；`write_ready` 在 `on_ready` 内断言 socket `S_ISSOCK`、mode `0770`、gid `2000`，再写 `/work/state/ready`（fsync 文件 + 目录） |

新增参数的精确签名（仅轮廓，不实现）：

```python
def __init__(
    self, controller, socket_path: str = DEFAULT_SOCKET_PATH, *,
    first_frame_deadline_s: float = REQUEST_DEADLINE_SECONDS,
    request_deadline_s: float = REQUEST_DEADLINE_SECONDS,
    max_connections: int = DEFAULT_MAX_CONNECTIONS,
    accept_timeout_s: float = _ACCEPT_TIMEOUT,
    socket_mode: int = 0o600,
    socket_gid: int | None = None,
    on_ready: Callable[[], None] | None = None,
    peer_uid: int | None = None,
    peer_gids: tuple[int, ...] | None = None,
) -> None:
    ...
```

**D1 controller 配置形状（JSON，数值为十进制）**：

```json
{
  "admission_path": "/work/state/admission.json",
  "broker_config_path": "/work/state/broker.json",
  "fake_script": "/project/fake/fake_provider.py",
  "receipt_dir": "/work/state/receipts",
  "attempt_db": "/work/state/attempts.sqlite3",
  "socket_path": "/work/g3b/bridge.sock",
  "python": "/opt/python/bin/python3.11",
  "fake_python": "/opt/python/bin/python3.11",
  "expected_uid": 65534,
  "socket_mode": 504,
  "socket_gid": null,
  "peer_uid": 65534,
  "peer_gids": [65534]
}
```

> `504` = `0o770`。`socket_gid: null` 是刻意的：trusted 容器以 `--cap-drop ALL` 运行，**没有 `CAP_CHOWN`**，`os.chown(..., gid=2000)` 会 `EPERM`；D1 依赖 host launcher 预创建的 **setgid 目录 2750 root:2000** 让 `bind` 创建的 socket 自动继承 gid 2000，再由 `chmod 0770` 固定 mode，并在 `on_ready` 里用 `stat` 断言 gid=2000（失败即不写 ready、服务退出）。`socket_gid` 参数仍保留给有 `CAP_CHOWN` 的环境；D1 不通过加 cap 来使用它。

**Peercred 细节（必须按本机实测配置）**：

- D0 P-05 实测：candidate 连接时 trusted 侧看到 `PEERCRED pid=0 uid=65534 gid=65534`。
- **gid 是 65534，不是 2000**：2000 只是 candidate 的 supplementary group（用于目录/socket 权限），不是 primary gid；`SO_PEERCRED` 返回 effective/primary gid。D1 的 `peer_gids` 应为 `[65534]`；若写成 `[2000]` 会把合法 candidate 拒绝（D1 负向会误伤）。
- **pid 不可用**：candidate 与 trusted 在不同 PID namespace，peer pid 为 0；禁止用 pid 或 `/proc/<pid>` 做鉴权。
- uid 校验只能证明“连接来自 candidate 主体”，不能区分同一 run 的多个 candidate 容器（它们都是 65534）；D1/D3 默认每 run 一个正向 candidate；D2-12 多 candidate 只用于资源/并发，不主张 candidate 间隔离。
- 若目标 Runner 没有 `SO_PEERCRED`：D1 配置了 `peer_uid` 时启动必须失败并标 `BLOCKED_NEEDS_ENVIRONMENT`；**不得**退化为“只靠文件 mode”或 0666。

**默认回归（必须保持）**：
- 不传新参数时：socket mode 0600、无 chown、无 peer 校验、无 ready hook；`tests/integration/g3_bridge` 与 `tests/integration/g3c` 旧用例不得因本改动改变行为。
- 新增测试至少覆盖：默认 0600；隔离模式 0770 + gid 2000；`on_ready` 恰调用一次；peer uid 65534 接受、peer uid 0 拒绝且不写协议帧；`socket_mode=0o666` 被构造器拒绝；`peer_uid` 配置但 `SO_PEERCRED` 缺失时 fail-closed。

#### 2.1.3 备选方案 B（fallback，不推荐默认）

**做法**：controller 继续监听 trusted-only 的私有 socket（0700 目录、0600）；新增 trusted-side proxy 监听 `/work/g3b/bridge.sock`（0770 root:2000），proxy 做 peercred 后双向转发字节。

**B 的理由**：完全不改 B1 `ipc_server.py`；candidate 只看到 proxy socket。
**B 的代价**：
1. 多一个 trusted 进程和一组连接/字节/超时上限，生命周期与清理更复杂；
2. controller 看到的是 proxy 的 root peer，**无法直接对 candidate 做 peercred**；鉴权责任转移到 proxy；
3. proxy 必须严格不解析、不转发任意文件/任意 socket，仍是一个新的攻击面；
4. 需要额外的 proxy 测试、崩溃/重启语义和证据，D1 时间与风险更高。

**结论**：除非维护者明确拒绝修改 `ipc_server.py`，否则 D1 采用 **A**；B 只在 A 无法实施时启用，且需重新签核。

---

### 2.2 O-D2 — Principal 映射

#### 2.2.1 设计表（签核基线）

| 维度 | Candidate（不可信） | Trusted Controller/Launcher（可信） |
|---|---|---|
| 容器 | `at-g3d-candidate-<run>` | `at-g3d-trusted-<run>` + host launcher |
| 宿主内核 UID | **65534**（container uid 0 经 `--uidmap 0:65534:1`） | **0**（`--userns=host --user 0:0`） |
| User namespace | 独立（嵌套 userns；`--uidmap 0:65534:1`，`--gidmap 0:65534:1 --gidmap 2000:2000:1`） | host userns（rootful） |
| Mount namespace | 独立；rootfs/stage/deps ro，session/tmp rw，IPC ro | 独立；rootfs/stage/deps ro，state/evidence/IPC rw |
| PID namespace | 独立；只见自己的进程（`pid=1` 或 exec 子进程） | 独立；Broker/Fake/Controller 子进程 |
| Network namespace | 独立；`--network none`，仅 `lo` | 独立；`--network none` |
| IPC/UTS/cgroup ns | 独立 | 独立 |
| Capabilities | `--cap-drop ALL`、`no-new-privileges`、`CapEff=0` | `--cap-drop ALL`、`no-new-privileges`（root 但无 cap） |
| rootfs | 共享 canonical rootfs，ro | 同左，ro |
| 代码/依赖 | candidate stage + deps，ro；不含 controller/broker/fake/policy | trusted stage + deps，ro；含 controller/broker/fake |
| 状态 | 仅 `/work/session` + tmpfs；**无 state** | `/work/state`（Broker SQLite/WAL/SHM、attempts、receipts、admission、policy） |
| UDS | 只连接 `/work/g3b/bridge.sock`（ro 挂载） | 绑定同一 socket（rw 挂载）；不向 candidate 暴露私有控制 socket |
| 生命周期 | host launcher 启动/超时/强杀 | host launcher 启动/ready/停止；崩溃由 reconcile 处理 |

#### 2.2.2 签核要点

1. **candidate 不是宿主 root**：candidate 的 container uid 0 只在其嵌套 userns 内是 root；宿主 LXC 看到的是 **65534**。D1 证据必须同时给出：
   - candidate 内 `/proc/self/uid_map` = `0 65534 1`；`gid_map` 至少 `0 65534 1` 与 `2000 2000 1`；
   - host 对 `podman inspect -f '{{.State.Pid}}' "$CAND"` 得到的进程，`/proc/<pid>/status` 的 `Uid:` 为 `65534`（trusted 为 `0`）；
   - trusted 侧连接日志的 `SO_PEERCRED uid=65534 gid=65534 pid=0`。
2. **candidate 只读代码/依赖**：`/`、`/project`、`/deps`、synthetic `/etc/passwd`/`/etc/group` 全部 ro；candidate stage 不包含 `autoteacher_m0/accounting`、`bridge/{controller,admission,attempts,broker_client,fake_backend}.py`、`fake/`、`config/{admission,broker,controller}.json`。
3. **trusted 独占控制面**：state 目录只挂 trusted；candidate 不挂 state/evidence/logs/repo/Key/launcher 控制面。trusted 不读 candidate session（避免被 candidate 写入文件影响），证据采集由 host launcher 以不跟随 symlink/FIFO 的方式做。
4. **`admission.launcher.uid` 必须保持 65534**：
   - `src/autoteacher_m0/bridge/admission.py:98-100` 用 `launcher["uid"] != expected_uid` 做 `ADMISSION_LAUNCHER_MISMATCH` 检查；
   - 该字段语义是 **Controller 期望的容器 peer uid**（G3-B 中 launcher/candidate 同为 65534），不是 trusted host launcher 的 uid 0；
   - 写成 0 会在 bind socket 之前 `ADMISSION_LAUNCHER_MISMATCH`，且与 peercred 65534 不符。D1 controller 配置的 `expected_uid` 也保持 65534；`peer_uid` 是**另一个**显式字段（同为 65534，但语义是 transport 鉴权，不要复用同一个名字）。
5. **trusted 以 root 运行但 cap-drop ALL**：不要授权 `CAP_SYS_ADMIN`/`CAP_CHOWN`；socket gid 依赖 setgid 目录（见 O-D1），不通过加 cap 解决。
6. **candidate 不能成为 trusted 的 supervisor**：不持有 Podman socket、不持有 trusted PID/FD、不能通过 `/proc` 发信号；D1 用 host launcher 独立监管。

---

### 2.3 O-D3 — 挂载/存储清单

#### 2.3.1 Host 目录与权限（`$RUN` = 一次运行根，建议 `artifacts/g3d/runs/<run_id>/`）

```text
$RUN/
  state/                   0700 root:root      # trusted only
    broker.sqlite3         0600 root
    broker.sqlite3-wal     0600 root
    broker.sqlite3-shm     0600 root
    attempts.sqlite3       0600 root
    admission.json         0400 root
    broker.json            0400 root
    policy.json            0400 root          # 如与 broker.json 分立
    receipts/              0700 root
    received-count.json    0600 root
    controller.json        0400 root
    ready                  0600 root          # trusted on_ready 写；launcher 等待
  ipc/                     2750 root:2000     # setgid；唯一共享目录
    bridge.sock            0770 root:2000     # 由 trusted bind 创建
    bridge.sock.lock       0600 root          # controller singleton lock（candidate ro 可见但不可写）
  candidate-session/       0700 65534:65534  # DSH home/session/resume
  evidence/                0700 root:root     # host/trusted 证据；candidate 不挂
  logs/                    0700 root:root     # podman/launcher 日志；candidate 不挂
```

#### 2.3.2 挂载表

| Host 路径 | 类型 | trusted 挂载 | candidate 挂载 | 说明 |
|---|---|---|---|---|
| `artifacts/security/rootfs` | dir | `/` ro | `/` ro | 共享 canonical rootfs；只读 |
| `$STAGE/trusted` | dir | `/project` ro | **不挂** | controller/broker/fake/trusted entry |
| `$STAGE/candidate` | dir | **不挂** | `/project` ro | DSH SDK/adapter/candidate entry；不含 trusted 代码 |
| `artifacts/foundation/deps` | dir | `/deps` ro | `/deps` ro | 公共 Python deps；candidate 的 `PYTHONPATH` 只有 `/deps` |
| `$STAGE/trusted/etc/passwd` | file | `/etc/passwd` ro | **不挂** | trusted synthetic |
| `$STAGE/trusted/etc/group` | file | `/etc/group` ro | **不挂** | trusted synthetic |
| `$STAGE/candidate/etc/passwd` | file | **不挂** | `/etc/passwd` ro | candidate synthetic；root home=`/work/session` |
| `$STAGE/candidate/etc/group` | file | **不挂** | `/etc/group` ro | candidate synthetic；含 `socket:x:2000:` |
| `$RUN/state` | dir | `/work/state` rw | **不挂** | DB/WAL/SHM/attempt/receipt/policy/ready |
| `$RUN/ipc` | dir | `/work/g3b` rw | `/work/g3b` **ro** | 唯一 UDS；candidate 不能 unlink/rename/bind |
| `$RUN/candidate-session` | dir | **不挂** | `/work/session` rw | DSH home/session/resume |
| `$RUN/evidence` | dir | `/output` rw | **不挂** | trace/DB 副本/日志 |
| `$RUN/logs` | dir | 不挂（host 采集） | 不挂 | podman logs / host 日志 |
| `/tmp` | tmpfs | `/tmp` rw | `/tmp` rw | `rw,noexec,nosuid,nodev,size=…,mode=1777` |
| `/work` | tmpfs | `/work` rw | `/work` rw | 仅 tmpfs；其下 bind 子目录；`mode=1777` |

**candidate 禁止挂载**：`$RUN/state` 任意子路径、`$RUN/evidence`、`$RUN/logs`、repo 根、`src/`、`spikes/`、`fake/`（除 candidate stage 内副本）、`fixtures/`（除 stage 内副本）、`~/.ssh`、`~/.config`、`.env`、`/run/podman`、`/var/run/docker.sock`、宿主 `/etc`、宿主 home、任何 Key 路径。

#### 2.3.3 Synthetic `passwd` / `group`

- candidate `etc/passwd`：`root:x:0:0:root:/work/session:/nonexistent`、`nobody:x:65534:65534:nobody:/work/session:/nonexistent`；`group`：`root:x:0:`、`nobody:x:65534:`、`socket:x:2000:`。
- trusted `etc/passwd`：home 用 `/work`；`group` 同上（含 `socket:x:2000:`）。
- mode `0444`，只读挂载；**不修改 rootfs 原文件**。
- 原因（D0 P-10）：uid 0 在 rootfs 原 passwd 中无条目时，Node `os.userInfo()` 会 `ENOENT`；synthetic 文件是 DSH 可运行的必要条件。

#### 2.3.4 UDS 权限与组

- 固定路径：`/work/g3b/bridge.sock`（adapter 编译期常量，不接受 env/argv 覆盖）。
- `$RUN/ipc`：`2750 root:2000`（setgid）；candidate group 2000 获得 `r-x`，可穿越目录、可 connect，不可创建/删除/重命名。
- socket：`0770 root:2000`；candidate `--group-add 2000` 只用于连接，不授予 state/DB 权限。
- candidate 侧 IPC 挂载为 **ro**：即使目录误放宽，`unlink` → `EROFS(30)`，同路径 `bind` → `EADDRINUSE(98)`（D0 P-05 实测）。
- 禁止 0666、禁止 candidate 可写 IPC 目录、禁止 abstract socket/TCP。
- **cap-drop 注意**：trusted 没有 `CAP_CHOWN`，不要依赖 `chown`；依赖 setgid 目录继承 + `chmod` + `on_ready` 内 `stat` 断言。D1 preflight 要确认 gid 2000 未被宿主其它组占用。

---

### 2.4 O-D4 — 生命周期/清理

**签核顺序（host launcher，root；不进入 candidate namespace）**：

1. **Preflight**：校验 Git SHA/分支、`src/tests` 未被意外修改、rootfs/deps canonical、`podman ps -a` 空、无 stale `at-g3d-*`/socket、gid 2000 可用、无 `*KEY*/*TOKEN*/*SECRET*` env、`.env` 不存在。
2. **创建 `$RUN`**：`state` 0700 root、`ipc` 2750 root:2000、`candidate-session` 0700 65534:65534、`evidence`/`logs` 0700 root；删除 stale `$RUN/state/ready` 与 `$RUN/ipc/bridge.sock`（仅 launcher/root，且 `O_NOFOLLOW`/只删 socket）。
3. **生成配置**：admission/broker/controller/passwd/group；admission `launcher.uid=65534`；controller 配置含 O-D1 字段；文件 0400/0600；校验无 Key。
4. **启动 trusted**：`podman run -d`，固定 name；等待 `$RUN/state/ready`（首选）或 host `ss -xl` 看到 LISTEN（fallback）；断言 socket `S_ISSOCK`、mode 0770、gid 2000；不要以 host root 去 connect（peer 校验会拒绝，且这不是 candidate 证据）。
5. **启动 candidate**：`podman run -d`（或前台 + 外层 timeout），固定 name；设置外层 watchdog；等待退出/超时；采集 stdout/stderr/exit。
6. **采集**：candidate/trusted `uid_map`/`gid_map`/`mountinfo`/`/proc` 视图；DB/WAL/SHM/receipt/counter 前后 hash；`podman logs`；UTC；完整 argv。
7. **停止/清理**：candidate 先 SIGTERM（`podman stop -t 3`）再 SIGKILL；trusted 后 `podman stop -t 5`；`podman rm -f`；trusted 停止后 `lstat` 确认 `S_ISSOCK` 再 unlink `bridge.sock`；**同时删除 controller singleton 的 `bridge.sock.lock`**（`lstat` 确认为普通文件、owner root，`O_NOFOLLOW` 语义下只 unlink 该文件名）；`rmdir` 仅空 IPC 目录；验证容器不存在。
8. **无残余断言**：`podman ps -a --filter name=at-g3d-` 为空；全局 `podman ps -a` 为空（本轮要求）；`pgrep -af 'at-g3d|autoteacher_m0.bridge.controller|fake_provider'` 为空；`ss -xl` 无 `bridge.sock`；socket 文件不存在；`$RUN/ipc` 为空；candidate 无残留 FD（进程已死）。
9. **Hash/证据**：重算 rootfs/deps canonical；只清理可证明为空的 mount target（Podman 会在 rootfs 自动创建目标）；写 `cleanup.json` 与 `commands.jsonl`。

**关键规则**：
- **一次性运行层**：每次 run 独立 `$RUN`、独立容器名、独立 state；不复用上一次的 socket/DB/attempt；避免多 Agent 共享 rootfs 造成哈希漂移。
- **mount target 放在 tmpfs `/work` 下**（`/work/state`、`/work/g3b`、`/work/session`），或只用 rootfs 已存在的目标；不要在 rootfs 顶层新建 bind target。
- **进程组信号**：容器内 controller/DSH 用 `start_new_session=True`/独立进程组；host 只通过 `podman stop/kill` 和容器退出码监管，不直接 `kill` 容器内 PID。
- **candidate session 是不可信文件树**：launcher/trusted 不得以 root 递归 `open`/跟随 symlink、hardlink、FIFO；证据采集用 `tar` 默认不解引用（不加 `-h`/`--dereference`）、`O_NOFOLLOW|O_NONBLOCK`、文件数/大小上限。否则 candidate 可放指向宿主文件的 symlink 造成 confused deputy，或用 FIFO 阻塞清理。
- **失败处理**：任何 `podman` 查询/清理失败都记为 `SECURITY_BLOCKED`/非 PASS；不能把 `podman rm` 退出码当作“已清理”；清理不完整时 D1 不进入 D2。

---

### 2.5 O-D5 — D2 攻击矩阵映射（D2-01..D2-12）

> **执行约定**：所有攻击必须从**真实 candidate 容器/身份**执行：`podman exec "$CAND" /opt/python/bin/python3.11 -B -c '<script>'`（或 candidate entry 的 `--scenario`）。禁止从 trusted uid 0、host root 或 mock client 伪造 candidate 结果。每个用例独立 run/独立容器名/独立 state 快照；记录 UTC、完整 argv、exit、stdout/stderr、candidate `uid_map`/`gid_map`/`mountinfo`/`/proc` 视图、trusted `uid_map`、攻击前后 DB/WAL/SHM/receipt/counter hash、`podman ps -a`。D2 runner 可把只读 probe 目录挂到 `/probe-attacks`（不进入 candidate stage、不含 trusted 代码）；D1 正向不挂该目录。

| ID | 从 candidate 执行的命令（摘要） | 期望内核/协议拒绝 | 关键证据 |
|---|---|---|---|
| **D2-01** | `podman exec "$CAND" /opt/python/bin/python3.11 -B /probe-attacks/candidate_probe.py --case D2-01`（逐路径 `open` 并打印 errno） | 全部 `ENOENT(2)`；故意 ro 控制组误挂时 `EACCES(13)` | candidate stdout 的 errno；`mountinfo` 无 `$RUN/state`；DB/WAL/SHM 前后 hash 不变；Broker 行数不变 |
| **D2-02** | 以 `O_RDWR`/`O_CREAT` 打开并写 `/work/state/broker.sqlite3` | `ENOENT(2)`；误挂 ro 时 `EROFS(30)`/`EACCES(13)` | 前后 DB hash、`PRAGMA integrity_check`、reservation 行数、Fake counter |
| **D2-03** | 逐路径读/写 `/work/state/{admission.json,broker.json,policy.json,attempts.sqlite3,receipts,received-count.json}` | `ENOENT(2)`；误挂时读 `EACCES(13)`、写 `EROFS(30)` | 文件 hash、attempt 行数、receipt 数；candidate stdout 不得出现 admission_id/limits/policy 内容 |
| **D2-04** | `attack 'import autoteacher_m0.accounting.broker as b; print(b.__file__)'`；再 `open("/project/src/autoteacher_m0/accounting/broker.py")` | `ModuleNotFoundError`（exit 1）；路径 `ENOENT(2)`；`sys.path` 无 `/project/src` | stderr traceback、candidate `sys.path`、`os.walk('/project')` 无 `broker*.py`/`controller*.py` |
| **D2-05** | connect `/work/g3b/{controller,broker}.sock`、`/work/private/controller.sock`；再向 `bridge.sock` 发伪造 `reservation_id`/`call_id` 帧 | 私有 socket `ENOENT(2)`；bridge 伪造帧被 controller 拒绝（`UNKNOWN_FIELD`/`REQUEST_INVALID` 等 G3-C 冻结码）；Fake 0、新 reservation 0 | Fake counter、Broker reservation 行数、controller 日志、socket 连接数 |
| **D2-06** | 逐条发送：额外 `call_id`/`reservation_id`/`admission_id`/`authorized`/`approved_payload`/`request_digest`；`maxTokens=1025`；未授权 tool；错 `seq`；坏 `hash`；超大帧；深嵌套；半帧/EOF/伪造 finish | controller 在 Fake 前拒绝；错误码在 G3-C 集合内；Fake 0、无新 reservation/settle | 每个完整 frame、error frame、Fake counter、Broker/attempt 行 |
| **D2-07** | `socket(AF_INET/AF_INET6)`；DNS `example.invalid`；connect `192.0.2.1:9`（TEST-NET-1，不发 HTTP）；connect `/run/podman/podman.sock`、`/var/run/docker.sock`；只允许 `bridge.sock` | AF_INET/AF_INET6 `EPERM(13)`（若换机可创建，`connect` 必须 `ENETUNREACH/EACCES`）；DNS `EAI_AGAIN`；Podman/Docker socket `ENOENT(2)` | stdout、`if_nameindex()` 仅 `lo`、`/proc/net/route`、host `ss` 无 candidate 外部连接 |
| **D2-08** | 列 `/proc` pid；读 `/proc/<trusted-host-pid>/{environ,fd,cwd,root}`；读 `/proc/kcore`、`/proc/keys`、`/proc/sysrq-trigger`；写 `/proc/sys/kernel/core_pattern` | trusted pid `ENOENT(2)`；masked 路径 `ENOENT/EPERM/EACCES`；`core_pattern` 写 `EACCES(13)`/`EROFS(30)`；只看到自己的 pid | candidate `/proc` 列表、trusted host pid、`uid_map`、env 变量名、写 errno |
| **D2-09** | DSH 内置 tool 本地执行（允许）；不加载 Guard/坏 Guard/自写 patch；tool 尝试直连 Broker/HTTP | 本地 tool 可在 candidate 沙箱执行；任何 Provider 调用仍被 controller 拒绝；Fake 0；无未授权外呼 | DSH events、tool result、controller 日志、Fake counter、Broker 行、patch hash |
| **D2-10** | candidate 在发 request 前/ack 前/chunk 后 `os._exit(137)` 或 SIGKILL；Ctrl-C/cancel；trusted 在 `ATTEMPT_STARTED` 后、Fake send 前/后 `podman kill`；重启 reconcile | 无自动重发；attempt 保守（STARTED/UNCERTAIN/HELD）；Broker 不免费/不 0；Fake 最多 1 receipt；socket 最终不存在；无孤儿 | attempt/broker 前后行、receipt/counter、controller/launcher 日志、`podman ps -a`、`ss -xl`、进程表 |
| **D2-11** | 正向 DSH Echo 1 call、Tool 2 轮、Resume 第二进程 | 1/2 个 reservation/claim/attempt/receipt；SETTLED；DSH text/usage/finish 合法；隔离不误伤 | SDK events、Fake receipts、Broker/attempt 行、digest 链、session 文件、进程/挂载 |
| **D2-12** | 两个 candidate/客户端并发；慢请求/半帧；fork 循环；大内存；重复连接（资源子用例可用 `at-g3d-attack-<run>`，安全参数相同，`--pids-limit 8 --memory 128m`） | `pids.max` → `EAGAIN(11)`；`memory.max` → OOM kill；连接/帧/总量上限拒绝；无跨 stream、无额外 reservation/Fake | cgroup 文件、`podman stats`、controller 日志、DB 行、连接数、进程数 |

**旧 Reviewer 四个成功绕过（D0 §7）逐条关闭**：

| 旧绕过 | 旧结果（G3-B 同容器同 uid 65534） | D2/D1 新设计下的期望 |
|---|---|---|
| **B-1 读 Broker DB** | `broker_db_read.ok=true`；读到真实 reservation | candidate 不挂 `$RUN/state`；`open` → `ENOENT(2)`；误挂 ro → `EACCES(13)`；DB hash 不变（D2-01） |
| **B-2 写 Broker DB** | `broker_db_write=true`；向真实 DB 写新表 | `open(O_RDWR/O_CREAT)` → `ENOENT(2)`；误挂 → `EACCES/EROFS`；hash 不变（D2-02） |
| **B-3 写 Policy** | `policy_write=true`；重写 policy | policy 只在 trusted `/work/state`（0400 root）；`ENOENT(2)`；误挂 → `EACCES(13)`；hash 不变（D2-03） |
| **B-4 绕过 Controller 直接 claim** | `RESERVED`/`CLAIMED`/`dispatch_allowed=true`；无 durable attempt | candidate stage 无 broker/accounting/DB/socket；`import` → `ModuleNotFoundError`；`connect broker.sock` → `ENOENT(2)`；bridge 伪造 request → controller error；Fake 0、reservation 0（D2-04/05/06） |

> **关键点**：B-1..B-3 的“内核拒绝”不是一句 `chmod 600`，而是 mount namespace 中路径不存在（`ENOENT`）+ DAC 0700 root 的 `EACCES` 后备；B-4 的拒绝是未挂载路径/不存在 socket 的 `ENOENT`/`ModuleNotFoundError` + controller 协议拒绝。D2 必须同时记录 `mountinfo` 与 errno；只写权限表不算证据。

**D2 中的 defense-in-depth 控制组（可选，不得冒充真实 candidate）**：可额外启动一个一次性控制容器（同 candidate uid/userns/mount 配置，但故意把 `$RUN/state` ro 挂到 `/work/trusted`），执行 B-1..B-3；期望 `EACCES(13)`、hash 不变。该容器不参与正向链路，结果不能替代 D2-01..03 的“真实 candidate 未挂载”证据。

---

### 2.6 O-D6 — D3 组合回归

#### 2.6.1 正向组合（真实 DSH，双 Principal）

| 场景 | 期望 |
|---|---|
| Echo 1 call | 1 reservation/claim/attempt/receipt/SETTLED；DSH text+usage+finish；Fake 1；无 Key/HTTP |
| Tool 两轮 | 2 个独立 call/reservation/claim/attempt/receipt；tool result 进入第二轮；无跨 call 复用 |
| Session Resume | 第二个 candidate 进程恢复同一 session；旧 call 行不变；新 call 新增；无重复旧 attempt |
| Guard precheck | Guard 只做本地 precheck；Controller 仍是唯一 Reserve/Claim/Attempt 发起者 |
| Guard 缺失/无效 | Controller 拒绝/fail-closed；Fake 0；不得因 candidate 内 Guard 放行而外呼 |

#### 2.6.2 跨主体故障矩阵（W1..W10）

| 窗口 | 动作 | 期望 |
|---|---|---|
| W1 | candidate 发 request 前 SIGKILL | 无 reservation/attempt；Fake 0 |
| W2 | request 后 ack 前 SIGKILL | 无发送；attempt 不产生或保守；Fake 0 |
| W3 | `ATTEMPT_STARTED` 后、Fake send 前 kill trusted | reservation PENDING/CLAIMED；attempt STARTED；Fake 0；重启 reconcile → UNCERTAIN/held；不重发 |
| W4 | Fake receipt 后、response 前 kill trusted | receipt 1；attempt 无 settle；重启 reconcile 保守；Broker PENDING/FAILED；不重发 |
| W5 | response 后、settle 前 kill trusted | receipt 1；attempt WORST_CASE_HELD/UNCERTAIN；Broker 不 0；不重发 |
| W6 | candidate finish 前断连 | controller 保守；不自动 retry；无第二 receipt |
| W7 | cancel mid-stream | 进入 transport 控制；若已发送，保守；不免费 |
| W8 | trusted 正常停止 | socket unlink；无 orphan；candidate EOF fail-closed |
| W9 | 重启 controller | 新 admission_id；旧 attempt reconcile；不 `ADMISSION_REPLAYED`；不重发旧 call |
| W10 | 重启 candidate | 同 session 新进程；新 transport_id；旧 call 不复用；Resume 正向 |

#### 2.6.3 无残余检查（每个 D3 run）

1. `podman ps -a --filter name=at-g3d-` 为空；全局 `podman ps -a` 为空（本轮要求）。
2. `$RUN/ipc/bridge.sock` 不存在；`ss -xl` 无残留；IPC 目录为空。
3. `pgrep -af 'autoteacher_m0.bridge.controller|fake_provider|at-g3d'` 为空。
4. candidate `mountinfo` 无 `$RUN/state`、无 `$RUN/evidence`、无 `/project/src`、无 Podman socket、无 Key。
5. candidate/trusted env 无 `*KEY*/*TOKEN*/*SECRET*`；日志无 Key/Authorization。
6. Broker DB/WAL/SHM、attempt、receipt 快照一致；`PRAGMA integrity_check=ok`；无孤立 reservation/claim/attempt。
7. `prepared_digest != payload_digest == receipt.raw_sha256` 对每个 settled call 成立；Fake counter == receipt 数。
8. rootfs `25491e45…`、deps `e07729d7…` 前后一致；无新增 mount target；只删可证明空目录。
9. 无外部 HTTP/模型/Key：Fake/Controller 计数、host `ss`、日志。
10. `$RUN/evidence` 0700 root；candidate 不可读。
11. evidence 采集未跟随 candidate session 的 symlink/FIFO（`tar` 不解引用或 `O_NOFOLLOW`）；无宿主文件被 root launcher 读入 evidence。

#### 2.6.4 D3 通过条件

- D2 高风险项（至少 D2-01/02/03/04/07/08）真实内核拒绝；
- 正向 Echo/Tool/Resume 仍可用（不是“全部禁用”）；
- 跨主体 crash/cancel/cleanup 保守一致、无重发；
- 同一冻结 SHA/rootfs/deps 可复现；
- 0 Key/0 HTTP/no-live 不变量不变；
- 独立 D Reviewer 用新攻击脚本复验高风险项。

否则 `FAIL`/`BLOCKED`，不得进入 G4/Live。

---

## 3. 范围与非主张

1. **D 的范围**：无 Key、Fake Provider、固定 rootfs/deps 的 OS 信任边界；D1 正向 + D2 攻击 + D3 组合。**不包含**真实 Provider/Key/模型/外网、G4/G5/Live、远端 exactly-once、账单准确。
2. **不改**：`src/autoteacher_m0/security/gates.py`、`dsh_adapter.py`、`scripts/run_live.sh`、DSH 核心、G3-C 协议/冻结语义；D1 只做 O-D1 的 additive socket 变更与 D1 启动器/入口/测试。若实现中发现必须改这些文件，先 STOP，回 Lead/维护者重新签核。
3. **不主张**：内核逃逸、容器运行时逃逸、宿主 root/物理/硬件、供应链、可信侧内部人、跨内核侧信道、candidate 磁盘 DoS 之外的生产安全。rootful Podman + LXC 的残余风险（D0 §8 风险 3）不在本 Gate 的 PASS 范围。
4. **不外推**：本机 `CAN_ISOLATE` 只适用于 2026-11-17 的 LXC CT101；换 Runner 必须重跑 D0 §3 探针；不满足则 `BLOCKED_NEEDS_ENVIRONMENT`，**不得用 mock、同 UID、chmod 表、日志文字冒充内核拒绝**。
5. **本文件不是 D1 实施**：没有改任何产品代码/测试/脚本/证据/Packet；没有 commit/push；没有启动容器；没有 Key/模型/外网/Live。

---

## 4. 待维护者批准项（D1 前的硬门）

| # | 待批准 | 具体内容 | 不批准的后果 |
|---|---|---|---|
| 1 | **批准 IPC 方案** | 方案 A（additive：`socket_mode`/`socket_gid`/`on_ready` + peercred；默认 0600；隔离模式 0770/2000/peer uid 65534） | 不能进入 D1；若选 B，需重新签核 proxy 设计与测试 |
| 2 | **授权 D1 实施** | 从 `fff3623` 建 D 分支；代码基线 `b2f6af0`（`git diff b2f6af0..HEAD -- src tests` 为空）；Lead 统一归档 commit | D1 不得开始；本文件保持预签 |
| 3 | **确认目标 Runner 环境** | rootful Podman≥4.9 + crun + cgroup v2 pids/memory + user namespace/`--uidmap` + 共享目录 owner/mode/组；D1 preflight 实测 | 环境不满足时 D1 只能 `BLOCKED_NEEDS_ENVIRONMENT`，不得 mock |
| 4 | **批准权限参数** | `$RUN/ipc` 2750 root:2000；socket 0770 root:2000；candidate `--group-add 2000`；candidate 不挂 state；`admission.launcher.uid=65534`；peercred uid 65534 / gid 65534 | 不能把 socket 改 0666/同 UID；否则 D1 不得继续 |
| 5 | **批准 no-live 边界** | 0 Key/0 模型/0 外部付费 HTTP/0 LiveGate 解除；D1/D2/D3 只用 Fake/固定 rootfs/合成数据 | 任何真实 Key/外网/付费 HTTP 触发 STOP |
| 6 | **批准停止点** | D1→D2→D3→D Report/Review Request/Matrix→独立 D Reviewer→STOP；不自动进 G4/G5/Live | 不得跳过独立 D 复核或自动解锁 LiveGate |

> 建议维护者在这 6 项上逐项勾选；未勾选项视为未授权。D1 实施 Agent 不得以“D0 已预签”为由跳过本表。

---

## 5. 签核记录

| 字段 | 值 |
|---|---|
| Lead 预签结论 | `D0_PRE_SIGNOFF_ACCEPTED_PENDING_MAINTAINER_AUTHORIZATION` |
| 预签日期 | 2026-11-17（UTC） |
| 依据 | HEAD `fff3623`；G3-C 复核 v2 `PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`；D0 `981e4ed`/sha256 `2cf03c99…`；现场只读核对 |
| D1 授权 | **未授权**（待维护者） |
| `OS_TRUST_BOUNDARY` | **BLOCKED**（B0-02） |
| 文件变更 | 仅本文件与 `docs/M0_G3D_D1_IMPLEMENTATION_PLAN.md`；未 commit/push |
| 维护者批准（待填） | ☐ 方案 A ☐ 方案 B ｜ ☐ 授权 D1 ｜ ☐ 环境确认 ｜ ☐ 权限参数 ｜ ☐ no-live ｜ ☐ 停止点 |

---

> **结束原则**：D0 预签只表示“设计与环境预研足以制定 D1 计划”，不表示 OS 边界已经通过。G3-D 的 PASS 必须来自 D1/D2/D3 的真实内核拒绝、真实 candidate 身份、正向 DSH 与独立复核；在此之前 `OS_TRUST_BOUNDARY=B0-02=BLOCKED` 不变。
