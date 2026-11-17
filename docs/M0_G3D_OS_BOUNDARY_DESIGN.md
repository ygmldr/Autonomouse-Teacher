# M0 G3-D0 — OS 安全边界设计冻结与环境可行性预研

> **版本**：v1.0 ｜ **日期**：2026-11-17 ｜ **角色**：G3-D0 Design Agent ｜ **基线**：`bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（本地 `main`）
>
> **范围**：只做设计冻结、只读/临时探针与攻击计划；**不实现 D1/D2/D3、不修改 `src/`/`spikes/`/`tests/`/`scripts/`/已有 docs/artifacts、不 commit、不 push**。
>
> **无 Key / 无模型 / 无外部付费 HTTP / 无 Live**：本轮未读取任何真实 Key，未启动真实 Provider、模型或外部网络请求；所有容器均为本地 `--rootfs`、`--network none`、合成数据。
>
> **裁定边界**：本文件不是 `PASS_FOR_G3D_*`。`OS_TRUST_BOUNDARY` 在 D2/D3 真实内核拒绝证据产生前**仍是 BLOCKED**。本文件只回答“这台机器能否建立双 Principal 隔离”和“D1/D2/D3 应如何做”。

---

## 0. 结论摘要

### 0.1 环境可行性判定

**`CAN_ISOLATE`（仅限本机，2026-11-17，LXC CT101）**，但附四个必须在 D1 关闭的条件：

1. 本机是 **rootful Podman 4.9.3 + crun 1.14.1**，运行在 Proxmox LXC（Ubuntu 24.04，kernel `6.17.13-2-pve`）。`/etc/subuid`、`/etc/subgid` 为空，**rootless Podman / `--userns=keep-id` / `--userns=auto` 不可用**；但 rootful 下的 **`--uidmap 0:65534:1` 嵌套 user namespace 可用**。
2. 已用一个可信侧容器（host uid 0）与一个候选侧容器（container uid 0 → 宿主 LXC uid **65534**，独立 user/mount/pid/net/ipc/uts/cgroup namespace）实际跑通：共享 host 目录中的 UDS、`SO_PEERCRED`、只读挂载、`--network none`、cgroup v2 限制。
3. 已实测内核拒绝形态：候选读取/写入可信 0700 root 目录 → `EACCES(13)`；写只读 rootfs/共享目录 → `EROFS(30)`；`AF_INET/AF_INET6` socket → `EPERM(13)`；`pids.max=8` 时 fork 7 个后 `EAGAIN(11)`；`memory.max`/`cpu.max` 生效。
4. **关键实现缺口**：当前 B1 `ipc_server.py` 在 bind 后无条件 `chmod 0600`，且没有 `SO_PEERCRED` 校验。若 D1 不改这一点，候选即使属于 group 2000 也**无法连接**；若简单放宽为 0666，则失去最小权限。D1 必须在“**最小 additive socket 权限参数 + peercred**”与“**可信侧代理**”之间二选一（见 §2.5、§4.8、§8）。

> **不能把本机 `CAN_ISOLATE` 外推到其他 Runner。** 换机必须重跑 §3 的探针；若目标机不能建立双 UID/user namespace，G3-D 必须报 `BLOCKED_NEEDS_ENVIRONMENT`，**不得用 mock、同 UID 或“权限表”冒充**。

### 0.2 本机探针的关键数字

| 项 | 结果 |
|---|---|
| OS / 虚拟化 | Ubuntu 24.04.4 LTS，LXC（`container=lxc`），kernel `6.17.13-2-pve`，x86_64 |
| 当前 LXC userns | `0 100000 65536`（宿主 uid 0 → 外层 100000） |
| Podman / runtime | 4.9.3，crun 1.14.1，rootful（`rootless=false`），cgroup v2/systemd |
| cgroup controllers | `cpuset cpu io memory hugetlb pids rdma misc dmem`；Podman 报告 `memory,pids` |
| rootfs canonical | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps canonical | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| rootfs 运行时 | Python `3.11.15`、SQLite `3.50.4`、Node `v22.23.2` |
| 双主体 | trusted parent uid `0`；candidate parent uid `65534`（container uid 0） |
| UDS peercred | trusted 侧看到 candidate `uid=65534 gid=65534 pid=0`（不同 pidns，pid 不可用） |
| 探针后容器 | `podman ps -a` 为空 |

### 0.3 本轮明确没做

- 没有启动最终 D1 双容器方案；只做了最小可行性探针。
- 没有执行 D2-01..D2-12 的真实攻击；本文件的 D2 是**计划**，不是 PASS 证据。
- 没有修改 `ipc_server.py`、`controller.py`、DSH 核心或任何产品代码。
- 没有生成/读取真实 Key，没有 DNS/HTTP/模型调用，没有 `podman pull`。

### 0.4 并行 G3-C 工作树提示（重要）

- 本文件基于 `bb5bd0b` 的 G3-B 冻结事实写作；写作时 `git status` 显示 **G3-C 正在同一 worktree 修改** `src/autoteacher_m0/bridge/*`、`accounting/*`、`spikes/g3b-trusted-bridge/*`，并新增 `tests/integration/g3c/*`（文件数随时间增加；HEAD 仍为 `bb5bd0b`，改动未提交）。
- 因此：本文件引用的 G3-B 行号（如 `ipc_server.py` 的 `serve_forever`）只用于**定位设计缺口**；D1 必须在 **G3-C 冻结提交**上重新确认 socket mode/peercred、admission/error 语义、cancel/deadline/limits。当前工作树中 `serve_forever` 仍执行 `os.chmod(..., 0o600)`（并行 C 改动后约 179 行），但 C 可能继续改；D1 以 C freeze 为准，不沿用本文件行号。
- 这些改动属于并行 G3-C Agent；**本 Agent 未修改**它们，也不得把本文件与它们混为一个提交。

---

## 1. 威胁模型

### 1.1 候选 DSH 是什么、能做什么

G3-D 的 Candidate 是运行真实 DSH SDK、公开 `LlmAdapter`、不可信插件/会话/工具指令的进程集合。它被视为**任意代码执行**：插件、工具参数、会话文件、模型输出都可能诱导它执行攻击者选择的系统调用。候选可以：

- 读写自己挂载内的文件；创建/删除/重命名/软链接/硬链接；
- 打开 AF_UNIX/AF_INET/AF_INET6/AF_NETLINK socket，连接它“猜得到”的任意路径；
- fork/exec 任意本地程序，创建线程、子进程、临时文件；
- 读取自己的 `/proc`、`/sys`、`/dev`、cgroup 视图；
- 尝试读取 `/proc/<其它 pid>/environ|fd|cwd|root`，尝试复用/猜测 FD；
- 重启自身、SIGKILL 自身、Ctrl-C、关闭 UDS、制造慢请求/并发；
- 通过 DSH 内置工具执行任意本地命令；
- 向固定 UDS 发送任意字节/JSON、重复帧、超大帧、伪造 `transport_id`/`call_id`/`admission_id`；
- 尝试写 `/proc/sys/...`、`/sys/...`、`/dev/...` 等内核接口；
- 尝试连接宿主 Podman socket、Docker socket、项目 `.git`、artifacts、Broker/Fake/Controller 的私有路径。

### 1.2 受测攻击面与设计控制

| 攻击面 | 候选可能的动作 | 本设计的控制 | 对应测试 |
|---|---|---|---|
| 文件 | 读/写 Broker SQLite/WAL/SHM、Policy、Admission、Attempt Journal、Receipt、Fake counter、Key、launcher 配置 | 可信状态只在 trusted 容器 `/work/state`；candidate **不挂载**；host 目录 0700 root；文件 0400/0600 root；rootfs/代码 ro | D2-01/02/03/04 |
| Socket | 连接 Broker/Controller 私有 socket、Podman socket、任意 Unix socket、外部 TCP | candidate 只看到 `/work/g3b/bridge.sock`；目录 2750 root:2000、socket 0770 root:2000、candidate 侧 ro；`--network none`；AF_INET 实测 EPERM | D2-05/06/07 |
| FD | 猜测/复用 trusted 的 DB、Broker stdio、Fake pipe、launcher FD | 不同 pidns/uid；candidate 只有 0/1/2/3；trusted FD 不在其 `/proc`；无 FD 传递 | D2-08 |
| `/proc` | 读 trusted `environ`/`fd`/`cwd`/`root`，枚举宿主进程 | private pid namespace；candidate 只看到自己的 pid；`/proc/sysrq-trigger`、`/proc/kcore` 等由 runtime masked | D2-08 |
| 环境 | 注入 `*_KEY`/`*_TOKEN`/代理/`PYTHONPATH`/`LD_*`，伪造 launcher 身份 | `--unsetenv-all`，只显式给 `PATH/HOME/TMPDIR/PYTHONPATH/PYTHONDONTWRITEBYTECODE`；admission 的 launcher uid 固定；无 Key | D2-06/08/09 |
| 符号链接 | 在 `/work` 创建指向 `/work/state/...`、`/proc/...`、`/etc/...` 的链接 | 路径解析在 candidate 的 mount namespace 内；目标不存在或只读；不跟随到 trusted | D2-01/03/08 |
| 重启/崩溃 | 重启自身、SIGKILL、断连、制造 crash window | controller 的 Attempt/Journal/Broker 保守状态；不自动重发；launcher 清理 socket/容器 | D2-10、D3 |
| 内置工具 | 任意 tool 执行、Guard 不加载、插件注入、工具 schema 不匹配 | 工具执行只在 candidate 沙箱内；Provider 调用必须经 controller admission/claim/attempt；Guard 不是信任源 | D2-09、D2-11 |
| 资源 | fork 炸弹、内存耗尽、慢连接、并发连接、超大帧 | cgroup v2 `pids.max`/`memory.max`/`cpu.max`；B1/C3 的连接/帧/总量上限 | D2-12 |
| 内核接口 | `mount`、`unshare`、`ptrace`、`keyctl`、`bpf`、写 `core_pattern` | cap-drop ALL + no-new-privileges + 嵌套 userns + 默认 seccomp；无 CAP_SYS_ADMIN | D2-08 |

### 1.3 明确不抵御

本设计**不声称**抵御以下情形，也不把以下情形计入 G3-D PASS：

- **内核逃逸**：candidate 利用 Linux kernel/CVE 逃出 namespace、提权到宿主 root；
- **容器运行时逃逸**：Podman/crun/conmon/LXC 漏洞或配置错误导致 candidate 取得 trusted/宿主权限；
- **宿主 root / 物理/硬件**：宿主 root、Proxmox 宿主、CPU/内存侧信道、DMA、恶意硬件；
- **供应链**：rootfs、deps、Podman、DSH SDK、Node/Python 运行时本身被篡改；
- **可信侧内部人**：trusted Controller/Launcher 自身被攻陷，或维护者主动把状态目录挂给 candidate；
- **资源之外的持久 DoS**：candidate 把 host session 目录写满、耗尽宿主磁盘/IO（见 §8 风险 5）；
- **跨内核边界的侧信道**：cache/timing/spectre 类。

这些是 residual risk，不是本 Gate 的失败；但**不能用“已禁网”替代文件/控制面隔离**，也不能用 mock 结果替代真实内核拒绝。

### 1.4 信任假设与 TCB

- **TCB**：宿主内核、Podman/crun/LXC、rootfs/deps 的 canonical 字节、host root launcher、trusted Controller/Broker/Fake 代码。
- **可信输入**：rootfs `25491e45…`、deps `e07729d7…`、冻结 Git SHA、admission/policy/broker 配置由 launcher 生成。
- **候选输入**：DSH SDK/插件/会话/工具参数全部不可信；adapter 只按公开协议发请求，不自带 `call_id`/claim/digest/admission。
- **无 Key**：本轮及 D1/D2/D3 均无真实 Key；未来 Key 只作为 trusted-only 路径设计（§2.4），不进入 candidate 的 mount/env/argv。

### 1.5 受保护资产

1. Broker SQLite、WAL、SHM 及其历史 reservation/claim/settle 行；
2. Policy、Admission（`admission_id`、limits、route、tool_schemas、launcher uid）；
3. Attempt Journal（`g3b_attempts`/`g3b_admissions`）；
4. Fake receipt、`received-count.json`、payload digest；
5. 可信可执行路径（`python -m autoteacher_m0.accounting.broker`、Fake 脚本、Controller）；
6. launcher 控制路径（host Podman socket、run 目录、日志、清理脚本）；
7. 未来 Provider Key（本轮不存在）。

---

## 2. 双 Principal 设计

### 2.1 总览

| 维度 | Candidate（不可信） | Trusted Controller/Launcher（可信） |
|---|---|---|
| 容器 | 独立 container（`at-g3d-candidate-<run>`） | 独立 container（`at-g3d-trusted-<run>`）+ host launcher |
| 内核 UID | parent **65534**；container uid 0（独立 userns） | parent **0**；container uid 0（host userns） |
| User namespace | **独立**：`--uidmap 0:65534:1`，`--gidmap 0:65534:1` + `2000:2000:1` | host userns（`--userns=host`），rootful |
| Mount namespace | 独立；只挂 candidate stage/deps/ro rootfs/tmpfs/session/ipc ro | 独立；挂 trusted stage/deps/ro rootfs/tmpfs/state rw/ipc rw/evidence |
| PID namespace | 独立；只看到自己的进程 | 独立；Broker/Fake/Controller 子进程 |
| Network namespace | 独立；`--network none`，仅 `lo` | 独立；`--network none` |
| IPC/UTS/cgroup ns | 独立 | 独立 |
| Capabilities | `--cap-drop ALL`；`CapEff=0`；`no-new-privileges` | `--cap-drop ALL`；`no-new-privileges` |
| rootfs | 共享 `artifacts/security/rootfs`，**ro** | 同左，**ro** |
| 代码/依赖 | candidate stage + deps，**ro**；不含 broker/controller/fake/policy | trusted stage + deps，**ro**；含 controller/broker/fake |
| 状态 | 仅 `/work/session` 与 tmpfs；**无 state** | `/work/state`（DB/WAL/SHM/attempt/receipt/admission/policy） |
| UDS | 只连接 `/work/g3b/bridge.sock`（ro 挂载） | 绑定 `/work/g3b/bridge.sock`（rw 挂载）；private socket 不暴露 |
| 网络 | 无 AF_INET/AF_INET6（实测 EPERM）；无 DNS | 无网络；stdio 子进程 |
| 生命周期 | launcher 启动/超时/强杀 | launcher 启动/健康检查/停止；崩溃由 reconcile 处理 |

> 为什么 candidate 是 container uid 0：Podman 的 `--uidmap` 要求 container ID 0 必须映射；把 container 0 映射到 parent **65534** 后，candidate 在宿主 LXC 上就是非 root 的 65534，且拥有自己的 user namespace。它不是“宿主 root”，也不是“与 trusted 同 UID”。
>
> **与 G3-B 的关键差别**：G3-B 的 candidate/Controller/Broker/Fake 全部是 uid 65534、同一容器；D1 的 trusted 是 parent uid 0、candidate 是 parent uid 65534，且 user/mount/pid/net/ipc/cgroup namespace 分离。candidate 数值仍是 65534，但不再与 trusted 同 UID/同 mount/同容器；这正是 B0-02 的修复点。

### 2.2 Candidate Principal

**身份与命名空间**

- `--userns=private`（由 `--uidmap` 触发），映射固定为：
  - uid：`0 → 65534`（长度 1）；
  - gid：`0 → 65534`（长度 1），`2000 → 2000`（长度 1，用于 UDS 组）。
- 这属于“rootless-equivalent”：candidate 在 userns 内是 root，但宿主 kuid 是 65534、CapEff=0；**Podman engine 本身是 rootful**（本机无 subuid），该 residual 见 §8 风险 3。
- 进程：`--user 0:0 --group-add 2000`；`os.getuid()=0`（userns 内），宿主 kuid `65534`；`os.getgroups()` 必须包含 2000（本机精确配置实测为 `[2000, 0]`，primary gid 0 仍存在）。
- 补充组 2000 只用于连接 UDS；**不是** trusted 的组，也不授予 DB/Policy 权限。
- 需要 synthetic `/etc/passwd`、`/etc/group`（`root`、`nobody`、`socket:x:2000`），否则 uid 0 在 rootfs 的原 passwd 中无条目，Node `os.userInfo()` 会 `ENOENT`（已实测）。两个文件从 stage 只读挂载，**不修改 rootfs**。

**文件系统**

- `/`：共享 rootfs，`--read-only --read-only-tmpfs=false`；不能写 `/`、`/etc`、`/usr`、`/opt`。
- `/project`：candidate stage，ro；只含 DSH SDK/配置/插件/adapter 运行所需文件、candidate runner、fixtures；**不含** `autoteacher_m0.accounting`、`bridge.controller/admission/attempts/broker_client/fake_backend`、`fake/`、admission/policy/broker 配置。
- `/deps`：公共 Python deps，ro；candidate 的 `PYTHONPATH` **只能** `/deps`，不能含 `/project/src`。
- `/work`、`/tmp`：tmpfs，rw，`noexec,nosuid,nodev`；大小有界。
- `/work/session`：host run 目录，rw，owner `65534:65534`，mode `0700`；仅 candidate 可见；用于 DSH home/session/resume。
- `/work/g3b`：host IPC 目录，**ro**；只暴露 `bridge.sock`；candidate 不能 unlink/rename/bind。
- `/etc/passwd`、`/etc/group`：synthetic ro。
- 无 `/work/state`、无 `/output`、无 repo、无 `.git`、无 `artifacts`、无宿主 home、无 Podman socket、无 Key 路径。

**能力与系统调用**

- `--cap-drop ALL`、`--security-opt no-new-privileges`、默认 seccomp；`CapEff=0`（实测）。
- 无 CAP_SYS_ADMIN：不能 mount/pivot_root、不能 unshare 出可写 mount 影响 trusted；即使 candidate 在自身 userns 内再 `unshare(CLONE_NEWUSER)`，其宿主 kuid 仍是 65534，无法读 trusted 的 0700 文件。
- `--network none`；AF_INET/AF_INET6 实测 `EPERM(13)`；只有 `lo`；DNS `EAI_AGAIN`。
- cgroup v2：`pids.max`、`memory.max`、`cpu.max`；candidate 只看到自己的 cgroup 子树；`--ulimit nofile=4096:4096` 限制 FD 数（本机已用 64:64 验证限额可生效）。

**生命周期**

- 由 host launcher 启动；candidate 不控制 supervisor，不持有 Podman socket，不能启动/停止 trusted。
- 退出/崩溃只影响自己的 namespace；UDS 关闭由 controller 观察，FD 随进程退出关闭；不留下可被下一个 candidate 接管的 socket（socket 属于 trusted，candidate 侧 ro）。
- 同一 run 的 candidate 重启必须使用**新的进程/新的 transport_id**；旧 attempt 不允许自动重发（A-01/A-05）。

### 2.3 Trusted Controller / Launcher Principal

**身份**

- trusted 容器：`--userns=host --user 0:0`，parent uid 0；独立 mount/pid/net/ipc/uts/cgroup namespace；`--cap-drop ALL`；rootfs ro。
- host launcher：宿主 root 的外部脚本/进程，负责建目录、生成配置、启动/停止容器、快照/清理；**不进入** candidate 的 namespace，不被 candidate 访问。
- trusted 容器内运行：Controller（`python -B -m ...` 或 entrypoint）、Broker 子进程（stdio）、Fake 子进程（stdio）、可选的 trusted-side UDS proxy（仅 fallback 方案）。

**持有物**

- `/work/state/`：Broker SQLite + `-wal` + `-shm`、`attempts.sqlite3`、`receipts/`、`received-count.json`、`admission.json`、`broker.json`/policy、controller config。
- `/work/g3b/`：唯一对外 UDS（或 proxy 的 socket）。
- `/project`：trusted stage（controller/broker/fake/runner）；`/deps`。
- `/output`：证据输出（trace/DB 副本/日志），仅 trusted/launcher 可写。
- 未来 Key：`/work/secrets/provider.key` 仅 trusted ro，0400 root；candidate 无此挂载/路径/环境变量。

**权限**

- state 目录 `0700 root:root`；DB/WAL/SHM/attempt/receipt `0600` 或 `0640` root；admission/policy `0400` root。
- candidate 的 0700 root 目录读取实测 `EACCES(13)`；即使 candidate 猜到路径也无法穿越。
- trusted 不挂 candidate session，不读 candidate 的 `/work`；避免 trusted 被 candidate 写入的文件影响。

**网络**

- 无外部网络；Broker/Fake 通过 stdio pipe 通信；trusted 不需要 TCP。
- 如未来需要 Provider HTTP，必须另开 G4 评审；本 Gate 不打开。

### 2.4 存储路径与挂载表

设一次 run 的根目录为 `$RUN`（建议 `artifacts/g3d-runs/<run_id>/`，已 gitignore；D1 实现时固定并记录）；`$STAGE` 为 D1 的只读 stage 根（布局见 §4.1）：

```text
$RUN/
  state/                   0700 root:root   # trusted only
    broker.sqlite3         0600 root
    broker.sqlite3-wal     0600 root
    broker.sqlite3-shm     0600 root
    attempts.sqlite3       0600 root
    admission.json         0400 root
    broker.json            0400 root
    policy.json            0400 root       # 如与 broker.json 分立
    receipts/              0700 root
    received-count.json    0600 root
    controller.json        0400 root
  ipc/                     2750 root:2000  # setgid；唯一共享目录
    bridge.sock            0770 root:2000  # direct 方案；proxy 方案由 proxy 创建
  candidate-session/       0700 65534:65534
  evidence/                0700 root:root
  logs/                    0700 root:root
```

| host 路径 | 类型 | trusted 挂载 | candidate 挂载 | 说明 |
|---|---|---|---|---|
| `artifacts/security/rootfs` | dir | `/` ro | `/` ro | 共享 canonical rootfs；只读 |
| `$STAGE/trusted` | dir | `/project` ro | **不挂** | controller/broker/fake/runner |
| `$STAGE/candidate` | dir | **不挂** | `/project` ro | 只含 DSH/adapter/candidate runner |
| `artifacts/foundation/deps` | dir | `/deps` ro | `/deps` ro | 公共 Python deps；不含项目包 |
| `$STAGE/trusted/etc/passwd` | file | `/etc/passwd` ro | **不挂** | trusted 侧 synthetic，root/nobody |
| `$STAGE/trusted/etc/group` | file | `/etc/group` ro | **不挂** | trusted 侧 synthetic，root/nobody/socket 2000 |
| `$STAGE/candidate/etc/passwd` | file | **不挂** | `/etc/passwd` ro | candidate 侧 synthetic，root/nobody |
| `$STAGE/candidate/etc/group` | file | **不挂** | `/etc/group` ro | candidate 侧 synthetic，root/nobody/socket 2000 |
| `$RUN/state` | dir | `/work/state` rw | **不挂** | DB/WAL/SHM/attempt/receipt/policy |
| `$RUN/ipc` | dir | `/work/g3b` rw | `/work/g3b` **ro** | 唯一 UDS；candidate 不能改 |
| `$RUN/candidate-session` | dir | **不挂** | `/work/session` rw | DSH home/session/resume |
| `$RUN/evidence` | dir | `/output` rw | **不挂** | trace/证据 |
| `$RUN/logs` | dir | 不挂（launcher 采集） | 不挂 | podman logs/宿主日志 |
| `/tmp` | tmpfs | `/tmp` rw | `/tmp` rw | `noexec,nosuid,nodev`，有界 |
| `/work` | tmpfs | `/work` rw | `/work` rw | 仅 tmpfs；其下再 bind 子目录 |
| `/run`、`/dev`、`/sys`、`/proc` | runtime | 默认 | 默认 | 不由项目挂载；runtime masked |

**禁止的挂载（candidate）**：`$RUN/state` 任意子路径、`$RUN/evidence`、`$RUN/logs`、repo 根、`src/`、`spikes/`、`fake/`、`fixtures/`（除 candidate stage 内副本）、`~/.ssh`、`~/.config`、`.env`、`/run/podman`、`/var/run/docker.sock`、宿主 `/etc`、宿主 home。

> **挂载目标漂移**：Podman 会为 bind target 在 rootfs 中自动创建缺失目录/文件（本机首次探针曾生成空 `/ipc`、0 字节 `/server.py`、`/etc/resolv.conf`）。D1 必须把新目标全部放在 tmpfs `/work` 之下（如 `/work/g3b`、`/work/state`、`/work/session`），或只使用 rootfs 已存在的目标；每次运行前后重算 rootfs canonical，只删除可证明为空的目录/0 字节文件并记录。

### 2.5 UDS 权限、SO_PEERCRED 与代理方案

**固定路径**：adapter 编译期常量 `/work/g3b/bridge.sock`（不接受 env/argv 覆盖），见 `spikes/g3b-trusted-bridge/src/index.ts` 的 `BRIDGE_SOCKET`/`createConnection`。candidate 与 trusted 都把 `$RUN/ipc` 挂到 `/work/g3b`，因此路径一致。

**目录与 socket 权限**

- `$RUN/ipc`：`2750 root:2000`（setgid）。candidate 以 group 2000 获得 `r-x`：可穿越目录、可连接 socket，**不可创建/删除/重命名**。
- socket：`0770 root:2000`。trusted 入口 `umask 007`，setgid 目录使新 socket 继承 group 2000；D1 的 trusted 实现还必须显式 `chmod 0660/0770` + `chown root:2000` 作为双保险（当前 B1 代码固定 0600，见下文缺口）。
- candidate 侧挂载为 **ro**：即使目录权限被误放宽，`unlink`/`bind` 仍返回 `EROFS(30)`（已实测）；`bind` 同路径在 socket 存在时返回 `EADDRINUSE(98)`。
- 不允许 0666，不允许 candidate 可写 IPC 目录，不允许 abstract socket/TCP。
- 本机 `getent group 2000` 无输出（gid 2000 未被占用）；D1 仍应在 preflight 断言 gid 2000 只用于该 IPC，避免宿主其它组混入。

**实测的 peercred**

在 trusted 侧对 candidate 连接调用 `getsockopt(SOL_SOCKET, SO_PEERCRED)`：

```text
PEERCRED pid=0 uid=65534 gid=65534
```

- `uid=65534`：candidate container uid 0 在 trusted userns 中的 kuid；
- `gid=65534`：candidate 的 primary gid 0 映射；
- `pid=0`：candidate 与 trusted 在不同 PID namespace，内核无法把 peer pid 映射到 trusted pidns，因此 **pid 不能用于鉴权**。
- 结论：controller 只能用 **peer uid**（可选 gid）做附加校验；不能依赖 pid、不能依赖 `/proc/<pid>`。peer uid 只能证明“连接来自 candidate 主体”，**不能区分同一 run 的多个 candidate 容器**（它们都是 65534/group 2000）。因此 D1/D3 默认每 run 一个正向 candidate；D2-12 的多 candidate 只用于资源/并发测试，不主张 candidate 之间的隔离。
- `SO_PEERCRED` 在本机可用；若某个 Runner 上不可用，D1 必须标 `BLOCKED` 或改用 proxy 的 `SO_PEERCRED`，不得只靠文件 mode。

**当前 B1 代码的硬缺口**

- `src/autoteacher_m0/bridge/ipc_server.py` 的 `serve_forever()`（G3-B 冻结版约 101 行；并行 G3-C 工作树中约 179 行）在 `server.bind(...)` 后执行 `os.chmod(self.socket_path, 0o600)`，**无条件 0600 root**。
- `ipc_server.py` 与 `controller.py` 中**没有** `SO_PEERCRED` 校验（`grep` 无匹配）。
- 后果：按现有代码，candidate（parent 65534，group 2000）连接会被 `EACCES(13)` 拒绝，正向链路必然失败；但若为了连通把 0600 改成 0666，则任何本机进程都能连，违背最小权限。
- D1 必须二选一（建议 A）：

| 方案 | 做法 | 优点 | 代价/风险 |
|---|---|---|---|
| **A. direct（推荐）** | 给 `BridgeServer` 增加 additive 参数：`socket_mode=0o600`、`socket_gid=None`、`on_ready=None`；bind 后按参数 `chmod/chown`；`handle_connection` 先取 `SO_PEERCRED`，`uid != expected_uid` 立即关闭；controller 传 `0o660/0o770`、gid 2000、expected_uid 65534；默认值 0600 保持旧测试不变 | 只一个 socket；controller 直接看到 peercred；无额外进程 | 需要 B1-owned `ipc_server.py` 的最小改动，须与 G3-C 的 IPC 改动协调、由 Lead 批准；旧测试需断言默认 0600 不回归 |
| **B. proxy（fallback）** | controller 仍 0600，监听 `/work/private/controller.sock`（trusted-only，0700）；trusted-side proxy 监听 `/work/g3b/bridge.sock`（0770 root:2000），校验 peercred 后双向转发字节；proxy 有连接数/字节/超时上限 | 不改 B1 代码；candidate 只看到 proxy socket | 多一个 trusted 进程；controller 看到的是 proxy 的 root peer，不能做 candidate peercred 校验；proxy 必须严格不解析、不转发任意文件 |

> 不允许的“解法”：把 socket 改成 0666；把 candidate 加进 root 组；把整个 `$RUN` 挂给 candidate；用 `chmod 600` 当作 OS 边界；用 mock 代理冒充内核证据。

### 2.6 进程监管与生命周期

**启动（launcher，host root）**

1. 校验冻结输入：repo SHA、rootfs `25491e45…`、deps `e07729d7…`、stage 文件清单/hash；确认 `podman ps -a` 为空、无残留 socket。
2. 创建 `$RUN/{state,ipc,candidate-session,evidence,logs}`，设置 §2.4 的 owner/mode；`chown 65534:65534 candidate-session`；`chmod 2750 ipc; chgrp 2000 ipc`。
3. 生成 synthetic `passwd/group`、admission、broker/policy、controller config、candidate/trusted stage 清单；确认 env 中无 `*KEY*/*TOKEN*/*SECRET*`。
4. 启动 trusted 容器（detached，固定 name），采集 `podman logs`；等待 readiness（见 §4.5）。
5. 启动 candidate 容器（固定 name，前台或 detached + 等待退出），设置外层 `timeout`。
6. 采集 candidate/trusted 的 stdout/stderr、退出码、`uid_map`、`mountinfo`、DB/receipt 快照。
7. 停止 candidate（SIGTERM→SIGKILL），再停止 trusted；`podman rm -f`；删除 socket；`podman ps -a` 必须为空；检查孤儿进程。
8. 重算 rootfs/deps canonical；只清理可证明为空的 mount target；写 evidence index。

**关键顺序**

- trusted 必须先于 candidate 可用；candidate 的 adapter 没有连接重试（`createConnection` 单次），所以 readiness 必须确定。
- 建议 D1 在 trusted 侧增加 `on_ready` 回调/文件：`server.listen(2)` 成功后写 `$RUN/state/ready`（fsync）；launcher 等该文件。fallback：host `ss -xl` 轮询 `bridge.sock` 处于 LISTEN，再启动 candidate（`ss` 在本机存在）。
- candidate 退出后，trusted 的 controller 可能仍持有 attempt/socket；launcher 先让 controller 完成 EOF/reconcile，再停止，避免把“正常退出”误记为 crash。

**崩溃/监管**

- candidate 崩溃/被 SIGKILL：trusted 看到 UDS EOF；controller 按 A-02/A-03 保守处理；不得自动重发；不得把未确认发送当免费。
- trusted controller 崩溃：candidate 收到 EOF/ECONNRESET，adapter fail-closed；launcher 杀 candidate；重启 controller 时 `reconcile_on_startup` 处理旧 attempt/receipt；新 admission 使用新 `admission_id`（避免 `ADMISSION_REPLAYED`）。
- Broker/Fake 子进程崩溃：controller 观察到 `BROKER_EXITED`/`FAKE_*`，返回错误；不发新请求；journal 保守。
- 任何情况下 candidate 不能成为 trusted 的 supervisor，不能持有其 PID/FD，不能通过 `/proc` 发信号。
- **candidate session 是不可信文件树**：launcher/trusted 不得以 root 递归 open/跟随 symlink、hardlink 或 FIFO；证据采集使用 `tar` 默认不解引用（不 `-h`/`--dereference`）、`O_NOFOLLOW|O_NONBLOCK`、文件数/大小上限。否则 candidate 可在 session 放一个指向宿主 `/etc/shadow` 的 symlink，让 root launcher 自己读取并写入 evidence（confused deputy）；也可用 FIFO 阻塞清理。
- 清理必须验证“容器不存在”而不是只看 `podman rm` 退出码：`podman ps -a --filter name=at-g3d-` 为空；`pgrep -af 'at-g3d|autoteacher_m0.accounting.broker|fake_provider'` 为空；socket 文件不存在。

### 2.7 与既有不变量的映射

| 不变量 | 本设计如何满足 |
|---|---|
| T-01 CallIdentity 只来自 trusted | candidate 请求 schema 无 `call_id`/reservation/digest/admission；controller 生成；peercred 仅辅助 |
| T-02 每 Provider 请求独立 Reserve/Claim/Attempt | candidate 只能经 controller；controller 仍是唯一发起者 |
| T-03 Fake 只收 approved bytes | Fake 只在 trusted 容器；candidate 无法 spawn/stdio 接触 |
| T-04 claim 不可跨进程伪造 | candidate 无 Broker 模块/DB/socket；BoundClaimer 仍在 trusted |
| T-05 文件权限/容器描述不是证据 | D2 用真实 errno/mountinfo/peercred/hash；不以“只读描述”代替 |
| A-01 无 ATTEMPT_STARTED 不发送 | controller 仍在 trusted；candidate 不能写 journal |
| A-02/A-03 异常不免费 | candidate crash/EOF 由 trusted journal 保守记录 |
| A-04 Broker 状态权威 | DB 只在 trusted；candidate 不可写 |
| A-05 不自动重试 | adapter `maxRetries=0`；controller 不重发；candidate 重启不重放旧 call |
| A-06 synthetic | Fake 仍 synthetic；D2/D3 不产生真实账单 |
| R-01..R-04 | 由 G3-C 冻结实现；D2/D3 复跑，不因隔离放宽 |

---

## 3. 本机可行性实测（只读/临时探针）

> 时间窗：2026-11-17 11:16–11:40 UTC。所有容器 `--rootfs`、本地、`--network none`、无 pull；探针后 `podman ps -a` 为空。
> 探针不是 D1 最终方案，也不构成 D2 攻击证据。

### 3.1 环境基线

| 项 | 命令/来源 | 结果 |
|---|---|---|
| OS | `/etc/os-release`, `uname -a` | Ubuntu 24.04.4 LTS；kernel `6.17.13-2-pve`；LXC（`/proc/1/environ` 有 `container=lxc`） |
| 当前身份 | `id`, `/proc/self/uid_map` | `uid=0(root)`；userns `0 100000 65536`；`CapEff=000001ffffffffff` |
| Podman | `podman --version`, `podman info` | `4.9.3`；rootful（`rootless=false`）；crun `1.14.1`；cgroup v2/systemd；seccomp enabled；AppArmor/SELinux disabled |
| cgroup | `stat -fc %T /sys/fs/cgroup`, `cgroup.controllers` | `cgroup2fs`；`cpuset cpu io memory hugetlb pids rdma misc dmem`；Podman 报告 `memory,pids` |
| userns sysctl | `sysctl kernel.unprivileged_userns_clone user.max_user_namespaces` | `1`；`2147483647` |
| subuid/subgid | `cat /etc/subuid /etc/subgid` | 均为 0 字节（空） |
| 工具 | `command -v` | `podman/unshare/newuidmap/newgidmap/setfacl/sudo/bwrap/nsenter/ss/lsof/fuser` 均存在；`setfacl 2.3.2`、`bubblewrap 0.9.0`、`sudo 1.9.15p5` |
| rootfs | canonical tar | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps | canonical tar | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| 本地 image | `podman images` | `localhost/autoteacher-local-oci:rootfs c83e44ab…`（107 MB）；本轮未用 image，直接用 rootfs |
| 容器 | `podman ps -a` | 探针前/后均为空 |

### 3.2 探针结果

以下命令均以 `set +e` 记录真实 exit；容器名带 `$$` 唯一后缀，跑完清理。

**P-01 `unshare` 命名空间**

```bash
unshare --user --map-root-user --mount --pid --net --fork --mount-proc \
  sh -c 'id; cat /proc/self/uid_map; echo pid=$$; ls /proc | grep -c "^[0-9]"'
# exit=0
# uid=0(root) gid=0(root) groups=0(root)
# uid_map: 0 0 1
# pid=1
# 3
```

**P-02 Podman rootfs 基本运行（uid 65534）**

```bash
podman run --rm --rootfs --network none --read-only --read-only-tmpfs=false \
  --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 \
  --pids-limit 32 --memory 256m --tmpfs /work:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --workdir /work "$ROOTFS" /opt/python/bin/python3.11 -B -c '...'
# uid 65534 gid 65534
# root_write_errno 30 Read-only file system
# visible_pids 1
# exit=0
```

**P-03 rootless / keep-id / auto（不可用）**

```bash
podman run --userns=keep-id --user 65534:65534 ...
# exit=125
# Error: ... potentially insufficient UIDs or GIDs available in user namespace
# (requested 100000:100000 ...): Check /etc/subuid ...: invalid argument

podman run --userns=auto ...
# exit=125
# Error: ... no subuid ranges found for user "root" in /etc/subuid

podman unshare id
# exit=125
# Error: please use unshare with rootless
```

**P-04 嵌套 userns 映射（关键可用项）**

```bash
podman run --rm --rootfs \
  --uidmap 0:65534:1 --uidmap 1:1:65533 \
  --gidmap 0:65534:1 --gidmap 1:1:65533 ...
# uid 0 gid 0
# uid_map: 0 65534 1 / 1 1 65533
# gid_map: 0 65534 1 / 1 1 65533
# exit=0
```

> 后续采用更紧的映射：只映射 `0→65534`，另加 gid `2000→2000`；Podman 要求 container ID 0 被映射，但不要求映射整个区间。

**P-05 双容器 + 共享 UDS + peercred**

- trusted 容器（uid 0）在 `$BASE/ipc`（`2750 root:2000`）bind `bridge.sock`，`umask 007`，`listen(1)`；socket 实测 `SOCK_MODE=770 UID=0 GID=2000`。
- candidate 容器（`--uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1 --group-add 2000`）以 ro 挂载同一目录，连接并发送 `hello`。
- 结果：

```text
candidate: uid 0 gid 0 groups [2000]
candidate: UDS_REPLY b'OK'
trusted:   PEERCRED pid=0 uid=65534 gid=65534
host stat: bridge.sock mode=770 uid=0 gid=2000
```

- candidate 对 socket `unlink` → `EROFS(30)`；对同路径 `bind` → `EADDRINUSE(98)`；`connect` 成功。

**P-06 DAC 与只读拒绝（trusted 目录误挂场景）**

将 `$BASE/state`（`0700 root:root`，内含 `0600 secret`）以 ro 挂到 candidate `/work/trusted`：

```text
READ_TRUSTED_SECRET      ERRNO=13:Permission denied
LIST_TRUSTED_DIR         ERRNO=13:Permission denied
WRITE_TRUSTED            ERRNO=13:Permission denied
WRITE_IPC                ERRNO=30:Read-only file system
ROOTFS_WRITE             ERRNO=30:Read-only file system
SYMLINK_READ (/state/...) ERRNO=2:No such file or directory
```

**P-07 网络与 socket family**

```text
AF_INET   ERRNO=13:Permission denied
AF_INET6  ERRNO=13:Permission denied
AF_UNIX   CREATE_OK
AF_NETLINK CREATE_OK
DNS       gaierror [Errno -3] Temporary failure in name resolution
IFACES    [(1, 'lo')]
```

- 即使加 `--security-opt seccomp=unconfined`，容器内 `Seccomp: 2`、`Seccomp_filters: 2`，AF_INET 仍 `EPERM(13)`；本机未能把该拒绝归因到单一层（LXC 外层的 seccomp + crun 内层 filter），因此 D2 只记录**实际 errno**，不声称“仅靠 netns”或“仅靠 seccomp”。host 自身与 `unshare --net` 下 AF_INET 可创建，说明不是内核全局禁止。
- 结论：本机 candidate 无法创建 AF_INET/AF_INET6；D2-07 期望 `EPERM(13)`；若换机后创建成功，必须继续测 `connect`，以 `ENETUNREACH/EACCES` 作为拒绝，不能因“socket 创建成功”记 PASS。

**P-08 cgroup v2 限制**

```text
pids.max     8
memory.max   134217728
cpu.max      50000 100000
cgroup.controllers  cpuset cpu io memory hugetlb pids
CGROUP_SELF  0::/
FORKED 7 ERR (11, 'Resource temporarily unavailable')
```

- `--pids-limit 8` 下 fork 7 个后 `EAGAIN(11)`；`--memory 128m`、`--cpus 0.5` 在 `podman inspect` 与 cgroup 文件均生效；candidate 只看到自己的 cgroup 子树。

**P-09 环境、FD、/proc**

```text
ENV ['HOME', 'HOSTNAME', 'PATH', 'TMPDIR']
FD  ['0', '1', '2', '3']
HOST_PODMAN_SOCK False False     # /run/podman/podman.sock, /var/run/docker.sock
PROC_PIDS [1]
```

- `--unsetenv-all` 后只显式注入最小变量；无 `*KEY*/*TOKEN*/*SECRET*`；candidate 只看到 pid 1；无宿主 Podman/Docker socket。

**P-10 runtime 版本与 synthetic passwd**

```text
python 3.11.15
sqlite 3.50.4
node   v22.23.2
uname  6.17.13-2-pve
```

- 不挂 synthetic passwd 时，Node `os.userInfo()` 对 uid 0 返回 `ERR_SYSTEM_ERROR ... ENOENT`；挂载 `root:x:0:0...` 后返回 `{"uid":0,"gid":0,"username":"root","homedir":"/work"}`。这是 D1 必须挂 passwd/group 的直接原因。

**P-11 `podman exec` 到运行中的 candidate**

- 以 `--uidmap 0:65534:1` 启动 candidate 后，`podman exec` 进入同一容器：

```text
uid 0 gid 0 groups [2000]
uid_map 0 65534 1
UDS_REPLY b'OK'
STATE_LIST_ERR 2 No such file or directory
```

- 说明 D2 可以从**真实 candidate namespace/uid** 执行攻击，而不是从 trusted 或宿主 root 伪造。

**P-12 参数敏感性（必须固定）**

- 一次缺少 `--read-only-tmpfs=false` 的探针报：

```text
Error: crun: open `run/.containerenv`: Permission denied: OCI permission denied
exit=126
```

- 加上该参数（以及 `--tmpfs /tmp`、`--tmpfs /work`、`--no-hosts`）后同一 rootfs 正常。D1 固定使用已验证的参数组合；把 `--read-only-tmpfs=false` 写入启动脚本，不在 D1 临时改。

**P-13 本地 G3-B 证据中的旧绕过（用于 §7 对照）**

- `artifacts/reviewer-g3b/r3/boundary-result.json`：uid 65534，同一容器内读 Broker DB `ok=true`、写 DB `true`、写 policy `true`、直接 reserve/claim 得到 `RESERVED`/`CLAIMED` 且 `dispatch_allowed=true`；网络 `PermissionError:13`；rootfs/probe 写 `EROFS`。
- `artifacts/reviewer-g3b/r3/actual-db-result.json`：挂载实际 B1 Broker DB 后，uid 65534 读到真实 settled reservation `9ae93f05…`（cost `0.001022`）、向 DB 写入新表 `true`、重写 policy `true`。

### 3.3 可用性矩阵

| 能力 | 本机 | 本设计是否依赖 | 备注 |
|---|---|---|---|
| rootful Podman | ✅ | ✅ | 4.9.3，crun 1.14.1 |
| rootless Podman | ❌ | ❌ | `/etc/subuid` 空；不阻塞，candidate 用嵌套 userns 等价非 root |
| `--userns=keep-id` | ❌ | ❌ | rootful 下报 insufficient UIDs；不用 |
| `--userns=auto` | ❌ | ❌ | 无 subuid；不用 |
| `--uidmap` 嵌套 userns | ✅ | ✅ | `0→65534` 成功；candidate 核心 |
| `unshare --user --mount --pid --net` | ✅ | 备选 | 若 Podman 不可用可作为 fallback |
| cgroup v2 + pids/memory/cpu | ✅ | ✅ | 实测限制生效 |
| `setfacl` | ✅ | ❌ | 存在但不用；组权限已足够，ACL 作为诊断 fallback |
| `sudo` / host caps | ✅ | ❌ | 当前已是 root；launcher 用 root |
| `SO_PEERCRED` | ✅ | ✅ | uid/gid 可用，pid=0 不可用 |
| 共享 rootfs 双容器 | ✅ | ✅ | 并发 ro；canonical 不变 |
| AF_INET/AF_INET6 | ❌（EPERM） | ✅（拒绝） | 期望拒绝；换机需重测 |
| synthetic passwd/group | ✅ | ✅ | uid 0 需 passwd 条目 |
| `--read-only-tmpfs=false` | ✅ 必须 | ✅ | 不加会 crun EACCES |
| 本地 image | ✅ | ❌ | 用 `--rootfs` 直接复用 canonical rootfs |

### 3.4 判定与最小环境需求

**本机判定：`CAN_ISOLATE`**，因为同时满足：

1. 两个不同内核 UID 的容器/命名空间（0 vs 65534）；
2. candidate 独立 user/mount/pid/net/ipc/uts/cgroup namespace；
3. 共享 UDS 的组权限、peercred、candidate 侧 ro；
4. 真实 DAC/EROFS/EPERM/EAGAIN 拒绝形态；
5. cgroup v2 资源上限；
6. 同一 canonical rootfs 可并发只读复用。

**若目标 Runner 不具备以下任一项，必须写 `BLOCKED_NEEDS_ENVIRONMENT`，不得 mock：**

- Linux user namespace（`kernel.unprivileged_userns_clone=1` 或等价）与 `--uidmap`/`newuidmap`；
- 能以 root 或带 `CAP_SETUID/CAP_SETGID` 的 launcher 启动 Podman/crun；
- mount namespace + bind mount + read-only rootfs；
- cgroup v2 的 pids/memory（cpu 可选但建议）；
- 能在两个容器间共享一个 host 目录并设置 owner/mode/组；
- 至少一个非 root 的 candidate UID，且与 trusted UID 不同。

最小需求示例：`root + podman>=4.9 + crun + cgroup v2 + userns + newuidmap`；若只有 Docker 无 userns/uidmap，需重新设计（可能用两个 host UID + mount namespace），不能在本文直接外推。

### 3.5 环境漂移、清理与 no-live 证据

**rootfs 漂移（已恢复）**

- 首次双容器探针把新 bind target 放在 rootfs 顶层，Podman 自动创建：
  - `artifacts/security/rootfs/ipc/`（空目录）；
  - `artifacts/security/rootfs/server.py`（0 字节）；
  - `artifacts/security/rootfs/etc/resolv.conf`（0 字节）。
- 只删除这三个**可证明为空/0 字节**的目标；重算 canonical 恢复 `25491e45…`。未删除/改写任何 rootfs 运行时文件。

**deps 漂移（已恢复，来源未归因）**

- 2026-11-17T11:35:15Z 观察到 `artifacts/foundation/deps` 下 8 个 `__pycache__` 目录（CPython 3.11 字节码）。D0 的宿主 Python 只执行 stdlib（socket/json），未导入项目或 deps；该漂移可能来自共享工作区的并行进程。
- 只删除 `__pycache__` 目录（可再生缓存），重算 canonical 恢复 `e07729d7…`；未改任何 deps 源文件。若并行 Agent 还在使用 deps，需在 D1 前协调串行，避免 hash 竞争。

**no-live 证据**

- 未读取真实 Key；candidate/trusted env 无 `*KEY*/*TOKEN*/*SECRET*`；无 `.env` 挂载。
- 未执行 `podman pull`；本地 image 未使用；无外部 HTTP/DNS/模型请求。
- 容器 `--network none`；AF_INET/AF_INET6 实测拒绝；Fake/Controller 只在 stdio。
- 宿主未执行项目 pytest/Node/SDK；容器内也只跑 Python/Node 版本与 socket/DAC 探针，不跑项目业务代码。
- 探针后 `podman ps -a` 为空；无后台 job。

---

## 4. D1 启动配置草案（不实现）

> 以下是 D1 应实现的**草案**，不是本轮已执行命令。D1 必须把实际 argv、UTC、exit、容器 digest/rootfs hash、stage hash 写入 packet。

### 4.1 Stage 布局

```text
$STAGE/
  candidate/
    run/candidate_entry.py        # 只启动 DSH SDK/worker，不 import controller/broker
    config/bridge.patch.yml
    runtime/                      # DSH SDK/runtime（公开、无 Key）
    runtime/bridge/lib/...        # 已构建 adapter
    runtime/bridge/node_modules/...
    native/, native-cache/, pkg-cache/   # 如 DSH 需要，ro
    fixtures/                     # 仅公开/synthetic fixture；禁止私有评估标签
    etc/passwd, etc/group         # synthetic
  trusted/
    run/trusted_entry.py          # umask 007；写 ready；调 controller main
    run/proxy.py                  # 仅 fallback 方案
    src/autoteacher_m0/...        # controller/broker/admission/attempts/fake_backend
    fake/fake_provider.py
    config/controller.template.json
    etc/passwd, etc/group
```

**candidate stage 明确排除**：`autoteacher_m0/accounting/`、`autoteacher_m0/bridge/{controller,admission,attempts,broker_client,fake_backend}.py`、`fake/`、`config/{admission,broker,controller}.json`、`receipts/`、任何 DB/WAL/SHM/Key/launcher 脚本；也**不包含** G3-B `run/common.py` 中的 `start_controller()`/controller 启动路径。若 candidate runner 需要协议常量，复制**最小只读常量**到 candidate stage，不 import trusted 模块。

### 4.2 Trusted 容器 argv（草案）

```bash
ROOTFS="/root/Autonomous Teacher/artifacts/security/rootfs"
TRUSTED="at-g3d-trusted-<run>"
podman run -d --name "$TRUSTED" --rootfs --timeout 300 \
  --userns=host --user 0:0 \
  --network none --http-proxy=false --unsetenv-all --no-hosts \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --memory-swap 1g --cpus 1 \
  --ulimit nofile=4096:4096 \
  --env PATH=/opt/python/bin:/usr/bin \
  --env HOME=/work \
  --env PYTHONPATH=/project/src:/deps \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env TMPDIR=/tmp \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --mount "type=bind,src=$STAGE/trusted,dst=/project,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$STAGE/trusted/etc/passwd,dst=/etc/passwd,ro=true" \
  --mount "type=bind,src=$STAGE/trusted/etc/group,dst=/etc/group,ro=true" \
  --mount "type=bind,src=$RUN/state,dst=/work/state,rw=true" \
  --mount "type=bind,src=$RUN/ipc,dst=/work/g3b,rw=true" \
  --mount "type=bind,src=$RUN/evidence,dst=/output,rw=true" \
  --workdir /project \
  "$ROOTFS" /opt/python/bin/python3.11 -B /project/run/trusted_entry.py \
    --config /work/state/controller.json
```

**trusted entrypoint 必须做的事**：

1. `os.umask(0o007)`；
2. 校验 `/work/state`、`/work/g3b` 的 owner/mode（不是 0777、不是 candidate 可写）；
3. 调 `controller.main(["--config", ...])`；
4. 通过 §4.6 的 `on_ready` additive hook（或 fallback `ss -xl` 轮询）在 `BridgeServer` bind/listen 成功后写 `/work/state/ready`（`fsync`），供 launcher 等待；
5. 退出时删除自己的 socket（controller 已有 finally unlink；entrypoint 再验证）。

**trusted 容器不挂**：candidate session、candidate stage、repo、宿主 home、Podman socket、Key。`/output` 只用于证据，不挂给 candidate。

### 4.3 Candidate 容器 argv（草案）

```bash
CAND="at-g3d-candidate-<run>"
podman run -d --name "$CAND" --rootfs --timeout 300 \
  --uidmap 0:65534:1 \
  --gidmap 0:65534:1 --gidmap 2000:2000:1 \
  --user 0:0 --group-add 2000 \
  --network none --http-proxy=false --unsetenv-all --no-hosts \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --memory-swap 1g --cpus 1 \
  --ulimit nofile=4096:4096 \
  --env PATH=/opt/python/bin:/usr/bin \
  --env HOME=/work/session \
  --env PYTHONPATH=/deps \
  --env PYTHONDONTWRITEBYTECODE=1 \
  --env TMPDIR=/tmp \
  --env DSH_RUNTIME_MODE=exe \
  --env DSH_RESOURCE_CACHE=/work/resources \
  --env NARB_NATIVE_CACHE_DIR=/project/native-cache \
  --env PKG_NATIVE_CACHE_PATH=/project/pkg-cache \
  --env NO_COLOR=1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --mount "type=bind,src=$STAGE/candidate,dst=/project,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$STAGE/candidate/etc/passwd,dst=/etc/passwd,ro=true" \
  --mount "type=bind,src=$STAGE/candidate/etc/group,dst=/etc/group,ro=true" \
  --mount "type=bind,src=$RUN/candidate-session,dst=/work/session,rw=true" \
  --mount "type=bind,src=$RUN/ipc,dst=/work/g3b,ro=true" \
  --workdir /work/session \
  "$ROOTFS" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
    --run-id "<run>" --session "<session>"
```

**candidate entrypoint 必须做的事**：

1. 断言 `os.getuid()==0`（userns 内）、`os.getgroups()` 含 2000、`/work/state` 不存在；
2. 断言 `PYTHONPATH` 不含 `/project/src`，且 `import autoteacher_m0.accounting` 失败；
3. 断言 `/work/g3b/bridge.sock` 是 `S_IFSOCK`，且不是自己创建的；
4. 只启动 DSH SDK/worker；不 import controller/broker/fake；不 spawn 任何 trusted 进程；
5. 退出码/事件写 `/work/session` 或 stdout，由 launcher 采集。

### 4.4 生成文件（trusted 侧，launcher 写）

- `$RUN/state/admission.json`：沿用 G3-B schema `m0.g3b.admission.v1`，`launcher.uid=65534`、`launcher.container=true`、`synthetic=true`、route `offline-test-only-g3b/fixture-bridge-v1`、`limits.max_attempts=1`、`max_calls` 按测试、`deadline_ms` 按 C 冻结；mode `0400 root`。
  - 语义注意：G3-B 的 `admission.launcher.uid` 实际是 Controller 期望的**容器 peer uid**（G3-B 中 launcher/candidate 同为 65534）；D1 仍填 65534。trusted host launcher 的 root uid 0 **不写入**该字段，否则会 `ADMISSION_LAUNCHER_MISMATCH`，且 peercred 校验（candidate 65534）也会不符。
- `$RUN/state/broker.json`：synthetic policy；配置中的 DB/日志路径必须是**容器内路径**（`/work/state/broker.sqlite3` 等，host 对应 `$RUN/state/…`）；mode `0400 root`。
- `$RUN/state/controller.json`：字段沿用 `controller.main` 的 `required` 集（G3-B 冻结版约 375-385 行；以 G3-C 冻结代码为准）：`admission_path=/work/state/admission.json`、`broker_config_path=/work/state/broker.json`、`fake_script=/project/fake/fake_provider.py`、`receipt_dir=/work/state/receipts`、`attempt_db=/work/state/attempts.sqlite3`、`socket_path=/work/g3b/bridge.sock`、`python=/opt/python/bin/python3.11`、`fake_python=/opt/python/bin/python3.11`、`expected_uid=65534`；mode `0400 root`。
- `$STAGE/{candidate,trusted}/etc/passwd`：`root:x:0:0:root:<home>:/nonexistent`、`nobody:x:65534:65534:nobody:<home>:/nonexistent`；candidate 的 `<home>` 用 `/work/session`（与 `HOME` 一致，避免 SDK 用 `os.userInfo().homedir` 时落到 tmpfs `/work`），trusted 用 `/work`。`group`：`root:x:0:`、`nobody:x:65534:`、`socket:x:2000:`；mode `0444`。
- 无 Key、无 token、无 `.env`。

### 4.5 启动/清理顺序

```text
1. launcher 预检：git SHA、rootfs/deps hash、podman ps -a 空、无残留 socket、env 无 key
2. mkdir/chmod/chown $RUN/{state,ipc,candidate-session,evidence,logs}；删除 stale `$RUN/state/ready` 与 `$RUN/ipc/bridge.sock`（仅 launcher/root）
3. 写 admission/broker/controller/passwd/group，校验 mode
4. podman run -d trusted
5. 等 $RUN/state/ready（首选）或 ss -xl 看到 LISTEN（fallback）
6. podman run -d candidate；启动外层 timeout/watchdog
7. 等 candidate 退出；采集 stdout/stderr/exit/uid_map/mountinfo
8. 采 DB/receipt/counter 快照；记录 broker/attempt/receipt hash
9. podman stop -t 3 candidate；podman rm -f candidate
10. podman stop -t 5 trusted；podman rm -f trusted
11. rm -f $RUN/ipc/bridge.sock；rmdir $RUN/ipc（若空）
12. 验证 podman ps -a 空、pgrep 无 orphan、socket 不存在
13. 重算 rootfs/deps canonical；清理可证明空的 mount target；写 evidence index
```

**失败/超时**：launcher 的 `trap` 必须执行 9–13；不能只 `podman rm`；`podman ps -a` 查询是清理的最终证据。candidate 超时先 SIGTERM，再 SIGKILL；trusted 超时同理。任何 `podman` 查询失败都记为 `SECURITY_BLOCKED`，不能当作“已清理”。

### 4.6 D1 必须做的最小代码/脚本变更（本轮不做）

1. `src/autoteacher_m0/bridge/ipc_server.py`：additive `socket_mode`/`socket_gid`/`on_ready`，以及 `SO_PEERCRED` 校验（默认 0600、无 gid、无 peer 校验，保持旧测试）；controller config 传 `0660/0770`、gid 2000、expected_uid 65534。**或** fallback proxy，不改 B1。
2. `$STAGE/trusted/run/trusted_entry.py`：umask、ready、config 校验；`$STAGE/candidate/run/candidate_entry.py`：只跑 DSH。
3. launcher 脚本：目录/权限/启动/等待/超时/清理/快照；不把候选 stage 与 trusted stage 混用。
4. 测试：D1 正向 Echo 1 call；socket mode/peercred 定向测试；0600 默认回归。

> 这些变更属于 D1 实施，须在 G3-C 冻结后由 Lead 批准；G3-D0 不改代码。

---

## 5. D2 攻击计划（D2-01..D2-12）

> **执行约定**：所有攻击从**真实 candidate 容器/身份**执行：`podman exec "$CAND" /opt/python/bin/python3.11 -B -c '<script>'`。禁止从 trusted uid 0、host root 或 mock client 伪造 candidate 结果。每个用例记录：UTC、完整 argv、exit、stdout/stderr、candidate `uid_map`/`mountinfo`/`/proc` 视图、trusted `uid_map`、攻击前后 DB/WAL/SHM/receipt hash、Broker 行、Fake counter、`podman ps -a`。

**统一 helper（写入 D2 runner，不是产品代码）**：

```bash
CAND="at-g3d-candidate-<run>"
TRUSTED="at-g3d-trusted-<run>"
ROOTFS="/root/Autonomous Teacher/artifacts/security/rootfs"
attack() { podman exec "$CAND" /opt/python/bin/python3.11 -B -c "$1"; }
```

### 5.0 用例总表

| ID | 攻击 | 期望内核拒绝/结果 | 若无法判定 |
|---|---|---|---|
| D2-01 | 读 Broker DB/WAL/SHM | `ENOENT(2)`；mountinfo 无 state；hash 不变 | 若路径可见/可读 → FAIL |
| D2-02 | 写 Broker DB | `ENOENT(2)`；误挂时 `EACCES/EROFS`；hash 不变 | 若写入成功 → FAIL |
| D2-03 | 读/写 Policy/Admission/Attempt/Receipt | `ENOENT(2)`；误挂时 `EACCES(13)`；hash 不变 | 若读到内容 → FAIL |
| D2-04 | 直接启动 Broker 操作真实 DB | `ModuleNotFoundError`；无 DB/无可执行路径 | 若模块/DB 可达 → FAIL |
| D2-05 | 绕过 Controller 用旧 v1 unbound claim 到 Fake | Broker socket `ENOENT`；bridge 伪造帧被 controller 拒绝；Fake 0 | 若 claim 成功/Fake 收据 → FAIL |
| D2-06 | 伪造 Admission/Policy/Route/Tool/UDS | `UNKNOWN_FIELD`/`REQUEST_INVALID`/`ADMISSION_*`；Fake 0、无 reservation | 若 Fake 收据/新 reservation → FAIL |
| D2-07 | 外部 TCP/HTTP/DNS/任意 Unix socket | `EPERM(13)` 或 `ENETUNREACH(101)`；Podman/Docker socket `ENOENT` | 若连上外部/宿主 socket → FAIL |
| D2-08 | 读 trusted `/proc/<pid>/environ|fd|cwd|root`、内核接口 | pid 不可见 `ENOENT`；masked 路径 `ENOENT/EPERM`；core_pattern 写 `EACCES` | 若读到 trusted 数据 → FAIL |
| D2-09 | 任意工具/Guard 不加载/插件注入 | tool 可本地执行，但 Provider 调用被 controller 拒绝；Fake 0 | 若未授权外呼 → FAIL |
| D2-10 | SIGKILL/Crash/UDS 断连/重启 | Attempt/Journal 保守；无自动重发；socket/进程清理 | 若重复发送/自动重试 → FAIL |
| D2-11 | 正向 DSH Echo/Tool/Resume | 1/2 call；receipt+settle；无隔离误伤 | 若正向失败 → FAIL（隔离误伤） |
| D2-12 | 并发/慢请求/资源耗尽 | cgroup `EAGAIN(11)`/OOM；连接/帧上限；无跨流 | 若逃过配额/串流 → FAIL |

### D2-01 读 Broker SQLite/WAL/SHM

```python
import os
for p in ("/work/state/broker.sqlite3", "/work/state/broker.sqlite3-wal",
          "/work/state/broker.sqlite3-shm", "/state/broker.sqlite3"):
    try:
        fd = os.open(p, os.O_RDONLY); os.close(fd); print(p, "OPENED")
    except OSError as e:
        print(p, "ERRNO=%d:%s" % (e.errno, e.strerror))
print("STATE_MOUNTS", [l.split()[4] for l in open("/proc/self/mountinfo") if "state" in l])
```

- **期望**：全部 `ENOENT(2)`；`STATE_MOUNTS` 为空；`/proc/self/mountinfo` 无 `$RUN/state`。
- **证据**：attack stdout；candidate mountinfo；攻击前后 `sha256sum $RUN/state/broker.sqlite3*`（trusted/host 侧）；Broker `snapshot` 行数不变。
- **BLOCKED**：若 candidate 能 `OPENED` 或 mountinfo 出现 state → 不是 PASS，D1 mount 表错误，FAIL。

### D2-02 写 Broker DB

```python
import os
for p in ("/work/state/broker.sqlite3", "/state/broker.sqlite3"):
    for flags, name in ((os.O_RDWR, "RDWR"), (os.O_CREAT | os.O_WRONLY, "CREATE")):
        try:
            fd = os.open(p, flags, 0o600); os.write(fd, b"x"); os.close(fd)
            print(p, name, "WROTE")
        except OSError as e:
            print(p, name, "ERRNO=%d:%s" % (e.errno, e.strerror))
```

- **期望**：`ENOENT(2)`；若故意做控制组把 state ro 挂入（D2 防御纵深对照），则 `EACCES(13)`/`EROFS(30)`，且 DB hash 不变。
- **证据**：前后 DB/WAL/SHM hash、`PRAGMA integrity_check`、reservation 行数；Fake counter 不变。
- **BLOCKED**：任何 `WROTE` → FAIL。

### D2-03 Policy/Admission/Attempt/Receipt

```python
import os
paths = ["/work/state/admission.json", "/work/state/broker.json",
         "/work/state/policy.json", "/work/state/attempts.sqlite3",
         "/work/state/receipts", "/work/state/received-count.json"]
for p in paths:
    for op in ("read", "write"):
        try:
            if op == "read":
                with open(p, "rb") as f: data = f.read(32)
                print(p, "READ", len(data))
            else:
                fd = os.open(p, os.O_WRONLY | os.O_APPEND); os.close(fd); print(p, "WROTE")
        except OSError as e:
            print(p, op, "ERRNO=%d:%s" % (e.errno, e.strerror))
```

- **期望**：全部 `ENOENT(2)`；误挂 ro 控制组时读 `EACCES(13)`、写 `EROFS(30)`。
- **证据**：文件 hash、admission/policy 原文不出现在 candidate stdout；attempt 行数/Fake 收据数不变。
- **BLOCKED**：读到 `admission_id`/limits/policy 内容 → FAIL。

### D2-04 直接启动 Broker

```bash
# 内核层：broker 代码/DB 路径在 candidate mount namespace 中不存在
podman exec "$CAND" /opt/python/bin/python3.11 -B -c '
import os
for p in ("/project/src/autoteacher_m0/accounting/broker.py",
          "/work/state/broker.sqlite3"):
    try: os.close(os.open(p, os.O_RDONLY)); print(p,"OPENED")
    except OSError as e: print(p,"ERRNO=%d:%s"%(e.errno,e.strerror))
'
# 语言层：即使路径存在，candidate stage 也没有 broker 模块
podman exec "$CAND" /opt/python/bin/python3.11 -B -c \
  'import autoteacher_m0.accounting.broker as b; print("IMPORTED", b.__file__)'
```

- **期望**：两条路径 `ENOENT(2)`（内核 mount namespace 拒绝）；`import` 为 `ModuleNotFoundError: No module named 'autoteacher_m0'`（exit 1）；`sys.path` 不含 `/project/src`。
- **证据**：stderr traceback、candidate `sys.path`、`find /project -name 'broker*.py'`（candidate 内 Python `os.walk`）为空。
- **BLOCKED**：若可 import/执行 → candidate stage 混入 trusted 代码，D1 FAIL。

### D2-05 绕过 Controller 直接 claim / 到达 Fake

```python
import socket, json
for p in ("/work/g3b/controller.sock", "/work/g3b/broker.sock", "/work/private/controller.sock"):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        s.connect(p); print(p, "CONNECTED")
    except OSError as e:
        print(p, "ERRNO=%d:%s" % (e.errno, e.strerror))
    finally:
        s.close()

# 发送伪造的 reserve/claim 帧到唯一允许的 bridge.sock
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect("/work/g3b/bridge.sock")
frame = {"v":1,"kind":"request","transport_id":"tr-"+"ab"*16,"seq":0,
         "payload":{"call_id":"call-"+"cd"*24,"reservation_id":"forged",
                    "route_id":"offline-test-only-g3b","model":"fixture-bridge-v1"}}
s.sendall((json.dumps(frame, separators=(",",":")) + "\n").encode())
print("REPLY", s.recv(4096))
```

- **期望**：`controller.sock`/`broker.sock` 为 `ENOENT(2)`（未挂载/不存在）；`bridge.sock` 的伪造 request 被 controller 拒绝（`UNKNOWN_FIELD`/`REQUEST_INVALID`，具体以 G3-C 冻结错误码为准），不产生 ack 成功后的 chunk/finish，Fake counter 0、无新 reservation。
- **证据**：Fake `received-count.json` 前后、Broker reservation 行数、controller 日志、socket 连接数。
- **BLOCKED**：若 candidate 得到 `CLAIMED`/`dispatch_allowed=true` 或 Fake 收据 → FAIL（正是旧 Reviewer 的绕过 4）。

### D2-06 伪造 Admission/Policy/Route/Tool/UDS

构造多个劣化 request（逐个发送，不要并发）：

1. 额外字段：`call_id`、`reservation_id`、`admission_id`、`approved_payload`、`authorized`、`request_digest`；
2. `maxTokens=1025` 或 > admission `max_output_tokens`；
3. `tools` 含 admission `tool_schemas` 未列出的工具；
4. 错误 `seq`、重复 `transport_id`、坏 `hash`、超大 frame、深嵌套；
5. 无 `finish` 的 EOF、半帧、`kind:"finish"` 伪造。

```python
import socket, json
base = {"sessionId":"s","provider":"offline-test-only-g3b","model":"fixture-bridge-v1",
        "messages":[],"tools":[],"system":None,"maxTokens":256,"stream":True,"purpose":None}
cases = [
    {"call_id":"call-"+"ab"*24, **base},
    {**base, "maxTokens":1025},
    {**base, "tools":[{"name":"not-allowed"}]},
]
for i, payload in enumerate(cases):
    env = {"v":1,"kind":"request","transport_id":"tr-"+("%032x"%i),"seq":0,"payload":payload}
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect("/work/g3b/bridge.sock")
    s.sendall((json.dumps(env, separators=(",",":"))+"\n").encode())
    print("CASE", i, s.recv(4096)); s.close()
# bad hash / seq / oversized / half frame 各再发一次，读取 error 或观察 server 关闭
bad = {"v":1,"kind":"request","transport_id":"tr-"+"cd"*16,"seq":1,
       "payload":base,"hash":"0"*64}
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM); s.connect("/work/g3b/bridge.sock")
s.sendall((json.dumps(bad, separators=(",",":"))+"\n").encode())
print("BAD", s.recv(4096)); s.close()
```

- **期望**：controller 在 Fake 前拒绝；错误码为 C 冻结集合中的 `UNKNOWN_FIELD`/`REQUEST_INVALID`/`ADMISSION_SELF_AUTH_DENIED`/`ADMISSION_ROUTE_NOT_ALLOWED`/`ADMISSION_TOOL_SCHEMA_MISMATCH`/`SEQ_OUT_OF_ORDER`/`FRAME_TOO_LARGE` 等；Fake 0、新 reservation 0、无 settle。
- **证据**：每个 payload 的完整 frame、controller error frame、Fake counter、Broker 行、attempt 行。
- **BLOCKED**：若伪造字段被当作授权、或 Fake 收到 bytes、或错误退化为 `UNKNOWN_FIELD` 但实际已发送 → FAIL/PARTIAL（按 C 的 P2-1 修复状态）。

### D2-07 外部网络 / 任意 Socket

```python
import socket
for fam, name in ((socket.AF_INET,"AF_INET"), (socket.AF_INET6,"AF_INET6")):
    try:
        s = socket.socket(fam, socket.SOCK_STREAM); print(name, "CREATE_OK")
        s.settimeout(1)
        try: s.connect(("1.1.1.1",443)); print(name, "CONNECTED")
        except OSError as e: print(name, "CONNECT_ERRNO=%d:%s" % (e.errno, e.strerror))
        s.close()
    except OSError as e:
        print(name, "CREATE_ERRNO=%d:%s" % (e.errno, e.strerror))
for p in ("/run/podman/podman.sock", "/var/run/docker.sock", "/work/g3b/bridge.sock"):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try: s.connect(p); print(p, "CONNECTED")
    except OSError as e: print(p, "ERRNO=%d:%s" % (e.errno, e.strerror))
    finally: s.close()
```

- **期望**：AF_INET/AF_INET6 `EPERM(13)`（本机实测；换机若创建成功，`connect` 必须 `ENETUNREACH/EACCES`）；DNS `EAI_AGAIN`；Podman/Docker socket `ENOENT(2)`；只有 `bridge.sock` 可连。
- **证据**：上述 stdout；`socket.if_nameindex()` 仅 `lo`；`/proc/net/route` 空；host `ss -tnp` 无 candidate 外部连接；Fake/Controller 无 HTTP。
- **BLOCKED**：若外部 TCP/HTTP/DNS 成功，或可连宿主 engine socket → FAIL。

### D2-08 `/proc`、FD、环境、内核接口

```python
import os
TPID = 0  # 由 launcher 替换为 trusted 的 host pid（podman inspect .State.Pid）
print("PIDS", sorted(int(p) for p in os.listdir("/proc") if p.isdigit()))
for p in ("/proc/1/environ", "/proc/1/cmdline", f"/proc/{TPID}/environ",
          f"/proc/{TPID}/root", "/proc/kcore", "/proc/keys", "/proc/sysrq-trigger"):
    try:
        data = open(p,"rb").read(64); print(p, "READ", data[:32])
    except OSError as e:
        print(p, "ERRNO=%d:%s" % (e.errno, e.strerror))
try:
    open("/proc/sys/kernel/core_pattern","wb").write(b"|/tmp/x")
    print("CORE_PATTERN WROTE")
except OSError as e:
    print("CORE_PATTERN ERRNO=%d:%s" % (e.errno, e.strerror))
```

- **期望**：`PIDS` 只含自己的 pid（通常 `[1]` 或 exec 进程）；trusted host pid `TPID` 在 candidate `/proc` 中 `ENOENT(2)`；`/proc/1/environ` 只显示 candidate 自己的最小 env；`/proc/kcore`、`/proc/keys`、`/proc/sysrq-trigger` 为 `ENOENT/EPERM/EACCES`；`core_pattern` 写 `EACCES(13)`/`EROFS(30)`；自己的 `/proc/1/root` 只能指向 candidate root。
- **证据**：candidate `uid_map`、`mountinfo`、`/proc` 列表；host `podman inspect -f '{{.State.Pid}}'` 的 trusted/candidate pid；candidate 读到的 environ 变量名列表（不得含 trusted 变量）。
- **BLOCKED**：若能看到 trusted pid/environ/fd，或写 core_pattern → FAIL。

### D2-09 工具执行 / Guard 不加载 / 插件注入

- 在 candidate 内用 DSH 内置 tool 执行本地命令（如 `echo`、文件读写）；同时：
  - 不加载 Guard；
  - 加载错误 hash/无效 Guard patch；
  - 尝试加载 candidate 自己写的“批准”插件/路由；
  - 尝试让 tool 直接发 HTTP/连 Broker。

```bash
# 本地工具允许执行；Provider 调用仍须 Controller
podman exec "$CAND" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
  --scenario tool --no-guard --tool "local-echo"
# 未授权外呼/直连 Broker 应失败
podman exec "$CAND" /opt/python/bin/python3.11 -B -c '
import socket, subprocess
print(subprocess.run(["/usr/bin/node","-e","require(\"http\").get(\"http://1.1.1.1/\")"],
                     capture_output=True, text=True).stderr[:200])
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
try: s.connect("/work/g3b/broker.sock"); print("CONNECTED")
except OSError as e: print("ERRNO=%d:%s"%(e.errno,e.strerror))
'
```

- **期望**：本地 tool 可在 candidate 沙箱内执行（这是允许的），但任何 Provider 调用必须由 controller 的 admission/claim/attempt 决定；Guard 缺失不导致未授权外呼；Fake 0；controller 返回 `ADMISSION_TOOL_SCHEMA_MISMATCH`/`CLAIM_DENIED`/`FAKE_UNAVAILABLE` 等错误；candidate 自写 Guard 不影响 controller。
- **证据**：DSH events/error、tool result、controller 日志、Fake counter、Broker 行；candidate 的 patch 文件 hash（证明只是本地文件）。
- **BLOCKED**：若 Guard 缺失时 Fake 收到 bytes 或 Broker 新 reservation → FAIL。

### D2-10 崩溃 / 断连 / 重启

执行窗口（每个独立 run）：

1. candidate 主进程在发 request 前 `os._exit(137)`；
2. candidate 发 request 后、收到 ack 前 `os.kill(os.getpid(), 9)`；
3. candidate 收到 chunk 后、finish 前 `os.kill(os.getpid(), 9)`；
4. candidate `Ctrl-C`/`SIGINT`，adapter 发 cancel；
5. trusted controller 在 `ATTEMPT_STARTED` 后、Fake send 前被 `podman kill`（可信故障注入，不是 candidate 攻击）；
6. trusted 在 Fake 已写 receipt、settle 前被 `podman kill`（同上）；
7. trusted 重启，`reconcile_on_startup`；
8. candidate 重启（同一 session，新 transport_id）。

```bash
# 真实 candidate 主进程在指定窗口自毁（candidate_entry.py 提供 --crash-window）
podman exec "$CAND" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
  --scenario echo --session g3d-crash --crash-window after_ack
# 或用宿主 kill 在外部窗口终止 candidate 主进程（仅故障注入，不作为 candidate 攻击证据）
podman kill "$CAND"
# trusted 故障注入（可信侧，不是 candidate 攻击）
podman kill "$TRUSTED"
# 重启 trusted：同一 state + 新 admission_id，argv 同 §4.2
```

- **期望**：无自动重发；旧 attempt 为 `ATTEMPT_STARTED`/`SETTLEMENT_UNCERTAIN`/`WORST_CASE_HELD`（按窗口）；Broker 保持 PENDING/FAILED，不出现免费/0；Fake receipt 最多一个；socket 最终不存在；无孤儿进程。
- **证据**：attempt/broker DB 前后行、receipt/counter、controller/launcher 日志、`podman ps -a`、`ss -xl`、进程表、candidate exit。
- **BLOCKED**：若同一 `call_id` 出现第二次 Fake send、或自动 retry、或把已发送记为免费 → FAIL。

### D2-11 正向 DSH Echo/Tool/Resume（隔离不误伤）

- Echo：1 个 request → 1 reservation/claim/attempt/receipt → `SETTLED`；DSH 收到合法 text/usage/finish。
- Tool：真实两轮 → 2 个独立 call/reservation/claim/attempt/receipt；tool 结果进入下一轮；无跨 call 复用。
- Resume：第二个 candidate 进程用同一 session 恢复，历史 call 不变，新 call 新增；不重复旧 call。

```bash
podman exec "$CAND" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
  --scenario echo --session g3d-s1
podman exec "$CAND" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
  --scenario tool --session g3d-s1
podman exec "$CAND" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
  --scenario resume --session g3d-s1
```

- **期望**：仍使用真实 DSH SDK + adapter + UDS；Fake usage synthetic；无 Key/HTTP；DB/Receipt 链一致。
- **证据**：SDK events、Fake receipts、Broker/attempt 行、`prepared_digest != payload_digest == receipt.raw_sha256`、session 文件、进程/挂载。
- **BLOCKED**：若因隔离权限导致合法 UDS 失败 → `BLOCKED_NEEDS_FIX`（不能把“全部禁用”当 PASS）。

### D2-12 并发 / 慢请求 / 资源

- 两个 candidate 容器（或两个 `podman exec` 客户端）同时连 `bridge.sock`；一个发慢请求/半帧；一个 fork 循环；一个分配大内存；重复连接。为可复现，资源子用例可用单独的 `at-g3d-attack-<run>` 容器（安全参数相同，`--pids-limit 8 --memory 128m`）；它不是正向 candidate，不得冒充 D2-11。

```bash
# 在 pids-limit=8 的 attack 容器内 fork 到 EAGAIN
podman exec "$ATK" /opt/python/bin/python3.11 -B -c '
import os,time
kids=[]; err=None
for _ in range(32):
    try: pid=os.fork()
    except OSError as e: err=(e.errno,e.strerror); break
    if pid==0: time.sleep(2); os._exit(0)
    kids.append(pid)
print("FORKED",len(kids),"ERR",err)
'
# 两个客户端同时发慢帧/大帧，观察 controller 连接/字节上限
```

- **期望**：
  - `pids.max` 触发 `EAGAIN(11)`；
  - `memory.max` 触发 OOM kill（cgroup `memory.events` 增加）；
  - `cpu.max` 限制 CPU；`ulimit -n`/`RLIMIT_NOFILE` 限制 FD；
  - controller 连接/线程/帧/总量上限（C3-03）拒绝超额，返回错误或关闭；
  - 无跨 stream 的 chunk/finish；无额外 reservation/Fake。
- **证据**：cgroup 文件、`podman stats --no-stream`、controller 日志、DB 行、连接数、进程数。
- **BLOCKED**：若超额连接被静默接受、跨流、或资源限制未生效 → PARTIAL/FAIL。

---

## 6. D3 组合回归计划

### 6.1 正向组合

在 D1 双主体配置下，用真实 DSH SDK 跑：

| 场景 | 期望 |
|---|---|
| Echo 1 call | 1 reservation/claim/attempt/receipt/SETTLED；DSH text+usage+finish；Fake 1 |
| Tool 两轮 | 2 个独立 call/reservation/claim/attempt/receipt；tool result 进入第二轮；无跨 call 复用 |
| Session Resume | 新 candidate 进程恢复同一 session；旧 call 行不变；新 call 新增；无重复旧 attempt |
| Guard precheck | Guard 只做本地 precheck，Controller 仍是唯一 Reserve/Claim/Attempt 发起者 |
| Guard 缺失/无效 | Controller 拒绝或 fail-closed；Fake 0；不得因 candidate 内 Guard 放行而外呼 |

### 6.2 跨主体故障矩阵

| 窗口 | 动作 | 期望 Journal/Broker/Fake |
|---|---|---|
| W1 candidate 发 request 前 | SIGKILL candidate | 无 reservation/attempt；Fake 0 |
| W2 request 后 ack 前 | SIGKILL candidate | 无发送；attempt 不产生或保守；Fake 0 |
| W3 ATTEMPT_STARTED 后、Fake send 前 | kill trusted | reservation PENDING/CLAIMED；attempt STARTED；Fake 0；重启 reconcile → UNCERTAIN/held；不重发 |
| W4 Fake receipt 后、response 前 | kill trusted | receipt 1；attempt 无 settle；重启 reconcile 保守；Broker PENDING/FAILED；不重发 |
| W5 response 后、settle 前 | kill trusted | receipt 1；attempt WORST_CASE_HELD/UNCERTAIN；Broker 不 0；不重发 |
| W6 candidate finish 前断连 | candidate SIGKILL/close | controller 保守；不自动 retry；无第二 receipt |
| W7 cancel mid-stream | adapter cancel | 进入 transport 控制；若已发送，保守；不免费 |
| W8 trusted 正常停止 | SIGTERM | socket unlink；无 orphan；candidate EOF fail-closed |
| W9 重启 controller | 新 admission_id | 旧 attempt reconcile；不 `ADMISSION_REPLAYED`；不重发旧 call |
| W10 重启 candidate | 同 session 新进程 | 新 transport_id；旧 call 不复用；Resume 正向 |

### 6.3 无残余检查

D3 每个 run 结束必须断言：

1. `podman ps -a --filter name=at-g3d-` 为空；`podman ps -a` 全局为空（本轮要求）。
2. `$RUN/ipc/bridge.sock` 不存在；`ss -xl` 无残留；IPC 目录为空。
3. `pgrep -af 'autoteacher_m0.accounting.broker|fake_provider|at-g3d'` 为空。
4. candidate mountinfo 无 `$RUN/state`、无 `$RUN/evidence`、无 `/project/src`、无 Podman socket、无 Key。
5. candidate env 无 `*KEY*/*TOKEN*/*SECRET*`；candidate/trusted 日志无 Key/Authorization。
6. Broker DB/WAL/SHM、attempt、receipt 快照一致；`PRAGMA integrity_check=ok`；无孤立 reservation/claim/attempt。
7. `prepared_digest != payload_digest == receipt.raw_sha256` 对每个 settled call 成立；Fake counter == receipt 数。
8. rootfs `25491e45…`、deps `e07729d7…` 前后一致；无新增 mount target；只删可证明空目录。
9. 无外部 HTTP/模型/Key：Fake/Controller 计数、host `ss`、日志。
10. 证据路径/权限：`$RUN/evidence` 0700 root；candidate 不可读。
11. evidence 采集未跟随 candidate session 的 symlink/FIFO（`tar` 不解引用或 `O_NOFOLLOW`）；没有宿主文件被 root launcher 读入 evidence。

### 6.4 D3 通过条件

- 内核拒绝真实发生（D2 高风险项）；
- 正向 Echo/Tool/Resume 仍可用（不是“全部禁用”）；
- 跨主体 crash/cancel/cleanup 保守一致、无重发；
- 同一冻结 SHA/rootfs/deps 可复现；
- 0 Key/0 HTTP/no-live 不变量不变；
- 独立 Reviewer 用新攻击脚本复验 D2-01/02/03/04/07/08 高风险项。

否则 `FAIL`/`BLOCKED`，不得签 G4/Live。

---

## 7. 旧 Reviewer 四个成功绕过的逐条关闭

### 7.1 旧证据（G3-B，同一容器同一 uid 65534）

| 绕过 | 旧结果（`artifacts/reviewer-g3b/r3/`） | 含义 |
|---|---|---|
| B-1 读 Broker DB | `broker_db_read.ok=true`，`reservations=1`；actual-db 读到真实 `9ae93f05…` cost `0.001022` | 候选可读账本 |
| B-2 写 Broker DB | `broker_db_write=true`；actual-db 向真实 DB 写新表 `write=true` | 候选可改账本 |
| B-3 写 Policy | `policy_write=true`；actual-db 重写 policy `true` | 候选可改策略 |
| B-4 绕过 Controller 直接 claim | `reserve_reply.code=RESERVED`、`claim_reply.code=CLAIMED`、`dispatch_allowed=true`；无 durable attempt | 候选可获本地发送许可 |

旧 Reviewer 同时记录：网络 `PermissionError:13`、rootfs/probe 写 `EROFS`；这两项不是“绕过”，但说明只有网络/只读挂载，没有文件/控制面隔离。详见 [REVIEW_G3B_INDEPENDENT.md §4](<REVIEW_G3B_INDEPENDENT.md#L353-L380>)、[boundary-result.json](<../artifacts/reviewer-g3b/r3/boundary-result.json>)、[actual-db-result.json](<../artifacts/reviewer-g3b/r3/actual-db-result.json>)。

### 7.2 新设计映射（逐条改为内核拒绝）

| 旧绕过 | 新 Principal/控制 | 期望新结果 | 复现路径 |
|---|---|---|---|
| B-1 读 DB | candidate 不挂 `$RUN/state`；state 0700 root；DB 0600 root | `open` → `ENOENT(2)`；误挂 ro 控制组 → `EACCES(13)`；DB hash 不变 | D2-01；`/work/state/broker.sqlite3` |
| B-2 写 DB | 同上 + 所有 state 挂载 ro/不存在 | `open(O_RDWR/O_CREAT)` → `ENOENT(2)`；误挂 → `EACCES/EROFS`；hash 不变 | D2-02；同一路径 |
| B-3 写 Policy | policy 只在 trusted `/work/state`，0400 root；candidate 无副本 | `ENOENT(2)`；误挂 → `EACCES(13)`；policy hash 不变 | D2-03；`/work/state/{admission,broker,policy}.json` |
| B-4 直接 claim | candidate stage 无 `accounting/broker`、无 DB、无 Broker socket；adapter 只允许 bridge.sock；controller 校验 schema/identity | `import` → `ModuleNotFoundError`；`connect` broker.sock → `ENOENT(2)`；bridge 伪造 request → controller error；Fake 0、reservation 0 | D2-04/05/06 |

**关键点**：B-1..B-3 的“内核拒绝”不是一句 `chmod 600`，而是 **mount namespace 中不存在该路径（ENOENT）**，加上 **DAC 0700 root 的 EACCES 后备**；B-4 的“内核拒绝”是 `execve/open/connect` 对未挂载路径/不存在 socket 的 `ENOENT`，加上 controller 的协议拒绝。D2 必须同时记录 `mountinfo`（证明没挂）与 errno（证明即使路径存在也被 DAC 拒绝）。

### 7.3 复现命令（从 candidate 身份）

```bash
CAND="at-g3d-candidate-<run>"

# B-1/B-2/B-3：读/写 state
podman exec "$CAND" /opt/python/bin/python3.11 -B -c '
import os
for p in ("/work/state/broker.sqlite3","/work/state/broker.sqlite3-wal",
          "/work/state/broker.sqlite3-shm","/work/state/admission.json",
          "/work/state/broker.json","/work/state/attempts.sqlite3",
          "/work/state/receipts","/work/state/received-count.json"):
    for mode in ("r","w"):
        try:
            fd = os.open(p, os.O_RDONLY if mode=="r" else (os.O_WRONLY|os.O_APPEND))
            os.close(fd); print(p, mode, "OK")
        except OSError as e: print(p, mode, "ERRNO=%d:%s"%(e.errno,e.strerror))
'

# B-4：直接 Broker
podman exec "$CAND" /opt/python/bin/python3.11 -B -c \
  'import autoteacher_m0.accounting.broker'   # 期望 ModuleNotFoundError

# B-4：Broker/bridge socket
podman exec "$CAND" /opt/python/bin/python3.11 -B -c '
import socket
for p in ("/work/g3b/broker.sock","/work/g3b/controller.sock","/work/private/controller.sock"):
    s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try: s.connect(p); print(p,"CONNECTED")
    except OSError as e: print(p,"ERRNO=%d:%s"%(e.errno,e.strerror))
    finally: s.close()
'
```

### 7.4 防御纵深对照（必须与真实 candidate 区分）

为了证明“即使 D1 误把 state 挂给 candidate，DAC 仍拒绝”，D2 可额外启动一个**一次性控制容器**（相同 candidate uid/userns/mount 配置，但故意 ro 挂 `$RUN/state` 到 `/work/trusted`），执行 B-1..B-3；期望 `EACCES(13)`，DB/policy hash 不变。该控制容器：

- 不参与正向链路；
- 不把结果冒充“真实 candidate 配置”；
- 只证明 DAC 后备，不替代 D2-01..03 的 mount 检查。

### 7.5 仍然会 FAIL 的情形

- candidate stage 混入 `src/autoteacher_m0`/`fake/`/admission/broker 配置；
- `$RUN/state` 被挂到 candidate（哪怕 ro 但 0700 root 仍 EACCES 只是后备；设计已违反最小挂载）；
- socket 被改成 0666 或 candidate 可写 IPC 目录；
- trusted 与 candidate 同 UID/同 user namespace；
- 用 mock UDS/模拟 Broker 代替真实内核拒绝；
- 只展示文件权限表，没有 errno/mountinfo/peercred/hash。

---

## 8. 风险与待 Lead/维护者签核项（6 条）

| # | 风险/决策 | 影响 | 建议/签核 |
|---|---|---|---|
| 1 | **本机 `CAN_ISOLATE` 不可外推**：rootful Podman + LXC + 嵌套 userns；换 Runner 可能无 subuid/uidmap/cgroup v2 | 换机可能 `BLOCKED_NEEDS_ENVIRONMENT`；不能用 mock 冒充 | 请维护者确认目标 Runner 与 §3.3 最小需求；D1 前重跑探针并记录；不满足则 G3-D=BLOCKED |
| 2 | **B1 socket 0600 / 无 peercred 缺口**：`ipc_server.py` 的 `serve_forever()` 仍固定 0600（C 冻结版须复核）；直接连通需要 additive 改动或 proxy | 不处理则正向链路必失败；改 0666 则失去最小权限 | 请 Lead 在 G3-C 冻结后批准方案 A（socket mode/gid/on_ready + SO_PEERCRED，默认 0600）或方案 B（trusted proxy）；不允许 0666/同 UID |
| 3 | **rootful engine / LXC 运行时逃逸不在边界内** | candidate→trusted 内核隔离成立，但 runtime/kernel 0day 可越界 | 明确 residual；高风险场景用 VM；D2/D3 结论只覆盖候选攻击面，不签“生产安全” |
| 4 | **启动参数/挂载目标敏感**：缺 `--read-only-tmpfs=false` 会 crun EACCES；uid 0 需 synthetic passwd；rootfs bind target 会漂移 | D1 可能“看似隔离但起不来”或污染 canonical rootfs | 固定 §4.2/4.3 argv；D1 加 preflight/after hash；只删可证明空目录；把参数写入脚本而非手工 |
| 5 | **candidate session 磁盘 DoS 与共享 deps 并发**：session host 目录未做磁盘 quota；deps 可能被并行 Agent 写 `__pycache__` | 可耗尽宿主磁盘；deps canonical 漂移导致证据失效 | D1 用有界 tmpfs 或 launcher 配额/清理；D1 前串行化共享 deps；每次前后重算 `e07729d7…`；发现漂移先停跑 |
| 6 | **D2/D3 依赖 G3-C 冻结语义**：错误码、cancel、deadline、连接/帧上限可能随 C 改变 | D2 的“期望错误码”可能过期；C 未 PASS 时 D 结果不可签 | D2/D3 只在 C 冻结 SHA 上跑；以 C 的 error set/limits 为准；C 若 FAIL/BLOCKED，D 同步 BLOCKED，不提前宣称 OS PASS |

**明确规则**：如果这台机器或目标 Runner 无法建立**不同内核 UID + 独立 mount/namespace**，G3-D 只能报 `BLOCKED_NEEDS_ENVIRONMENT`；**不得用 mock、同 UID、chmod 表、日志文字冒充内核拒绝**。

---

## 9. 冻结输入与 D0 验收清单

### 9.1 冻结输入

- Git base：`bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`（本地 `HEAD`；本轮未 commit）。
- 历史实现：`90402929c710a046e23dd3a3c3dd108b641bc981`；历史 docs：`b4a2d774d97242974fcadd21166292dd3b988339`（仅引用，不重写）。
- rootfs：`25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`。
- deps：`e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`。
- Podman `4.9.3`、crun `1.14.1`、kernel `6.17.13-2-pve`、Python `3.11.15`、SQLite `3.50.4`、Node `v22.23.2`。
- 本地 image `localhost/autoteacher-local-oci:rootfs` `c83e44ab…`（未用）。
- 本文件 sha256：见 Lead 提交前 `sha256sum docs/M0_G3D_OS_BOUNDARY_DESIGN.md`（本轮不 commit）。

### 9.2 D0 验收

- [x] 威胁模型、双 Principal、存储/挂载/UDS/生命周期设计；
- [x] 本机只读/临时探针（Podman/unshare/cgroup/uidmap/setfacl/sudo/caps/rootfs 复用）；
- [x] D1 启动 argv 草案；
- [x] D2-01..D2-12 攻击计划（命令/errno/证据/BLOCKED）；
- [x] D3 正向 + 跨主体故障 + 无残余；
- [x] 旧 Reviewer 四个绕过逐条映射；
- [x] 风险/签核 ≤6；
- [x] 无本 Agent 的产品代码/已有 docs/artifacts/packet 修改；无 commit；无 Key/模型/外部 HTTP/Live；工作树中 G3-C 并行改动（§0.4）不属于本 Agent；
- [x] `podman ps -a` 为空；rootfs/deps canonical 已复核。

### 9.3 交给 D1 的第一屏

1. 先按 §3.3 重跑本机探针；若 uidmap/userns/cgroup 不满足，直接 `BLOCKED_NEEDS_ENVIRONMENT`。
2. 按 §4 建 stage/run 目录；先做**一个** Echo 正向，不做攻击。
3. 解决 §2.5 的 socket 0600 缺口（方案 A 或 B），再开 candidate 连接；没有这一步不要继续 D2。
4. 正向通过后，按 §5 顺序跑 D2-01→D2-12；每个用例独立 run/独立容器名/独立 state 快照。
5. 最后按 §6 跑 D3；提交 D Packet 并 STOP，等独立 Reviewer。

---

## 附录 A：本机探针原始命令索引

以下命令均在 `/root/Autonomous Teacher` 执行，`ROOTFS="$PWD/artifacts/security/rootfs"`；容器名带唯一后缀并在同命令内清理。

```bash
# 0) 身份/内核/容器
id; cat /proc/self/uid_map; grep -E 'CapEff|CapBnd' /proc/self/status
podman --version; podman info
stat -fc %T /sys/fs/cgroup; cat /sys/fs/cgroup/cgroup.controllers
cat /etc/subuid /etc/subgid; sysctl kernel.unprivileged_userns_clone user.max_user_namespaces

# 1) namespace
unshare --user --map-root-user --mount --pid --net --fork --mount-proc \
  sh -c 'id; cat /proc/self/uid_map; echo pid=$$'

# 2) rootfs 基本
podman run --rm --name g3d0-basic --rootfs \
  --network none --http-proxy=false --unsetenv-all --no-hosts \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --uidmap 0:65534:1 --gidmap 0:65534:1 --user 0:0 \
  --pids-limit 16 --memory 256m --cpus 1 \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work --env TMPDIR=/tmp \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=16m,mode=1777 \
  --workdir /work "$ROOTFS" /opt/python/bin/python3.11 -B -c \
  'import os; print(os.getuid(), os.getgroups())'

# 3) 双容器 UDS（trusted server + candidate client）
#    $BASE/ipc 2750 root:2000；server umask 007；socket 0770 root:2000
#    candidate --uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1 --group-add 2000
#    结果：UDS_REPLY b'OK'；PEERCRED pid=0 uid=65534 gid=65534

# 4) 网络/资源/环境
#    AF_INET/6 EPERM(13)；AF_UNIX OK；DNS EAI_AGAIN；IFACES lo
#    pids.max=8 → FORKED 7, EAGAIN(11)；memory.max=134217728；cpu.max=50000 100000
#    ENV ['HOME','HOSTNAME','PATH','TMPDIR']；FD 0..3；PROC_PIDS [1]

# 5) 清理与 hash
podman ps -a
tar -C "$ROOTFS" --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
tar -C artifacts/foundation/deps --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
```

## 附录 B：错误码/errno 对照（本轮实测 + D2 期望）

| 场景 | 期望 | 来源 |
|---|---|---|
| 读/写 trusted 0700 root 目录 | `EACCES(13)` | P-06 实测 |
| 写只读 rootfs / ro 挂载 | `EROFS(30)` | P-02/P-06 实测 |
| 写只读 IPC 目录/socket | `EROFS(30)`；已存在 socket bind `EADDRINUSE(98)` | P-05 实测 |
| 读不存在的 trusted 路径 | `ENOENT(2)` | P-06/P-11 实测 |
| AF_INET/AF_INET6 socket | `EPERM(13)` | P-07 实测 |
| 外部 TCP（若 socket 可建） | `ENETUNREACH(101)`/`EACCES(13)` | D2-07 期望；换机重测 |
| DNS | `EAI_AGAIN(-3)` | P-07 实测 |
| pids 限制 | `EAGAIN(11)` | P-08 实测 |
| 跨 pidns peer pid | `pid=0`（不可鉴权） | P-05 实测 |
| 伪造 UDS 字段 | `UNKNOWN_FIELD`/`REQUEST_INVALID`/`ADMISSION_*` | D2-05/06 期望（以 G3-C 冻结为准） |
| 直接 Broker import | `ModuleNotFoundError` | D2-04 期望 |
| 同 UID/同容器 | 不作为证据 | 旧 G3-B B0-02=BLOCKED |

---

## 附录 C：术语与边界

- **Candidate**：运行 DSH/插件/工具的不可信主体。
- **Trusted Controller/Launcher**：持有 Broker/Policy/Admission/Attempt/Receipt/Fake/可执行路径的主体。
- **B0-02**：G3-B 的 OS 信任边界项；在本文件写作时仍为 `BLOCKED`。
- **D2 PASS**：必须同时有真实 candidate errno、mountinfo/uid_map、hash 前后一致、Fake/Broker 未变；缺一不可。
- **D3 PASS**：D2 高风险项内核拒绝 + 正向 Echo/Tool/Resume + 跨主体故障一致 + 无残余 + 同 SHA 可复现。
- **no-live**：0 Key、0 真实模型、0 外部付费 HTTP、0 LiveGate 解除；本文件所有探针遵守。

> **结束原则**：G3-C 修真实语义，G3-D 验操作系统拒绝。本文件只冻结设计与环境可行性；在 D1/D2/D3 真实证据与独立复核之前，不得把 `OS_TRUST_BOUNDARY` 从 `BLOCKED` 改为 PASS，也不得据此进入 G4/Live。
