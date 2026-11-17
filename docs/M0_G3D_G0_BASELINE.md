# M0 G3-D — D-G0 基线冻结与环境证据（无 Key）

> **状态**：`D-G0_PARTIAL_BLOCKED_WORKSPACE_CONFLICT`（环境与身份证据已取，但冻结时刻工作树被并行 D1-A/D-P0 改动污染；**不是** G3-D PASS，**不是** D1 实施授权）。
> **基线**：HEAD `d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d`（本文件提交前）；产品冻结点 `b2f6af054555705192c4e1ae3019a68078764736`；工作树 `/root/Autonomous Teacher`。
> **范围**：只读 Git/Stage/Runtime/环境核验与 docs/evidence；不改产品代码、测试、scripts、旧 evidence、Packet 或历史 docs；不实现 D1；不启动 Live/Key/模型/外部 HTTP；不 `podman pull`。
> **结论先行**：本机 `CAN_ISOLATE` 仍成立（rootful Podman 4.9.3 + crun 1.14.1 + LXC 嵌套 UID map），rootfs/deps/stage 最终 canonical 与冻结值一致；但 **Git 工作区在 18:33Z 后出现并行未提交改动**（`ipc_server.py`、`controller.py` 与两个 G3-C 测试，另加一个未跟踪的 G3-D 测试），因此 D-G0-01 的“clean baseline”不能成立，按 §4.3 的 **工作区来源冲突 STOP** 处理。**D1 不得在本次结论下开始**，需 Lead 先隔离/串行化并行实施。
> **不变量**：`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；LiveGate 仍 BLOCKED；本文件不授予 Live/G4/G5。

---

## 0. 摘要

| 项 | 现场结果 |
|---|---|
| 基线 HEAD（本文件提交前） | `d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d`，父 `1274280` |
| `origin/main`（远端跟踪，未 fetch） | `fff36232687afb779befb49fb6e2a10cedbcb7fd`（本地领先 2 个 docs 提交） |
| 产品基线 `b2f6af0` | `git cat-file -t` = `commit`；`git diff --stat b2f6af0..HEAD -- src tests spikes plugins` **空**（exit 0） |
| 初始 `git status` | 2026-11-17T18:23:42Z **clean（0 行）** |
| 后续 `git status` | 2026-11-17T18:33:41Z 起 **5 行 dirty**（4 modified + 1 untracked）；非本 Agent 改动 |
| rootfs canonical | 前/后均 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` |
| deps canonical | 前/后均 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| stage canonical | 前/后均 `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`；49 个 `.py` 全部 = `e6fde1c`，**不是** `b2f6af0` |
| 双 Principal | container UID 0 → host UID **65534**；trusted host UID 0；独立 user/mount/pid/net/ipc/uts/cgroup |
| UDS / peercred | host 目录 `2750 root:2000`；socket `770 root:2000`；trusted 侧 `PEERCRED pid=0 uid=65534 gid=65534` |
| 网络 | candidate `--network none`：`AF_INET`/`AF_INET6` `EPERM(13)`，仅 `lo`，无路由；`AF_UNIX` 可用 |
| cgroup v2 | `pids.max=8` → fork 7 后 `EAGAIN(11)`；`memory.max=134217728`；`cpu.max=50000 100000` |
| DSH runtime | `1cc41d5a…`，182,717,632 B，`--version=0.2.2-rc.2`；系统 `/usr/bin/dsh` 是 `0.2.1-rc.2`，不得替代 |
| Node / Adapter | Node `v22.23.2`；adapter `lib/index.js` `2cb42461…`（20,321 B），build-meta `dshLlmVersion=0.2.2-rc.2` |
| 0-Key / Live | key-like env 名 **0/46**；无 `.env`；`bash scripts/run_live.sh` **exit 3**；`LiveGate.inspect(live_requested=True)` = **BLOCKED** |
| 容器清理 | 最终 `podman ps -a` 空；无 `at-g3d-*`；无 pull；无外部 HTTP 命令 |

---

## 1. 基线与时间线

### 1.1 只读约束

- 本 Agent 未修改任何产品代码、测试、scripts、冻结 evidence 或 Packet；产物只写 `artifacts/g3d/`（gitignored）与本文档。
- 宿主 Python 全部使用 `-B`；容器只用固定 rootfs、`--network none`、`--cap-drop ALL`、`no-new-privileges`、`--unsetenv-all`。
- 未执行 `podman pull`、`git fetch`、`curl`、`wget`、模型调用或 LiveGate 解锁。
- 探针容器名统一 `at-g3d-*`，结束时全部删除；不删除其他 Agent 的容器或文件。

### 1.2 关键时间线（UTC）

| 时间 | 事件 | 结果 |
|---|---|---|
| 18:23:42Z | 首次 Git 身份检查 | HEAD `d74f2ff`；`git status --porcelain=v1` **0 行**；`git remote -v` 指向 `origin` |
| 18:24:27Z | rootfs/deps/stage canonical 前置 | `25491e45…` / `e07729d7…` / `fcdb0de4…`；`podman ps -a` 空 |
| 18:24:48Z | Stage 逐文件比对 | 49 个 `.py` 全部 = `e6fde1c`；`attempts.py`/`controller.py` ≠ `b2f6af0` |
| 18:26–18:27Z | Podman/cgroup/userns/安全面 | rootful 4.9.3、crun 1.14.1、cgroup v2；userns/uidmap 可用 |
| 18:27:26Z | 嵌套 map 容器 | host `Uid/Gid=65534`，container uid 0，`uid_map=0 65534 1` |
| 18:28:51Z | UDS 探针首次尝试 | exit 2：candidate 脚本 0400 对 host uid 0 不可读；改为 0444 后重跑 |
| 18:29:17Z | UDS/peercred 探针 | exit 0；socket `770 0:2000`；peercred `0/65534/65534`；candidate 侧 `EROFS/EADDRINUSE/EPERM` |
| 18:29:56Z | 清理 rootfs 空目录 | 仅删除**空** `rootfs/evidence`；canonical 恢复 `25491e45…` |
| 18:30:30Z | cgroup 资源探针 | pids 8 → 7 + `EAGAIN(11)`；memory/cpu 限制可见 |
| 18:33:41Z | **工作树冲突发现** | 4 modified（D1-A/D-P0 形态）+ 1 untracked；HEAD 仍 `d74f2ff` |
| 18:34:52Z | 从 `b2f6af0` 临时 archive 加载模块 | 6 个模块全部匹配 `b2f6af0` blob；临时目录已删除 |
| 18:36–18:37Z | 并行 `g3d-dp0-oci-full` 短容器 | 非本 Agent；自行退出；rootfs 短暂出现 `97d723ab` 后恢复 canonical |
| 18:37:49Z | 最终状态 | rootfs/deps/stage canonical；`podman ps -a` 空；工作树仍 dirty（并行 WIP） |

---

## 2. Git / 源码身份

### 2.1 固定输出

```bash
git status --porcelain=v1        # 18:23:42Z: 空（exit 0）
git remote -v                    # origin git@github.com:ygmldr/Autonomouse-Teacher.git
git rev-parse HEAD               # d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d
git rev-parse origin/main        # fff36232687afb779befb49fb6e2a10cedbcb7fd
git cat-file -t b2f6af0…         # commit (exit 0)
git diff --stat b2f6af0..HEAD -- src tests spikes plugins
                                 # 空输出；DIFF_EXIT=0
```

`git log -10` 顶部：

```text
d74f2ff docs: add G3-D0 sign-off and D1 implementation plan (no-key)
1274280 docs: archive G3-D dual-principal plan and matrix (verbatim)
fff3623 docs: archive G3-C independent review v2 (PASS) and final errata (no-key)
751af36 docs: archive G3-C independent review v1 and PR1 errata (no-key)
...
```

`git diff --stat b2f6af0..HEAD`（全路径）只涉及 docs 与 `scripts/g3c`：15 files, +4083/-171；`src/`、`tests/`、`spikes/`、`plugins/` **无差异**。`git diff --name-status` 也确认没有这四个目录的条目。

### 2.2 关键文件 Blob SHA（HEAD = `d74f2ff`）

| 文件 | mode | blob sha | 工作树 `git hash-object` |
|---|---|---|---|
| `src/autoteacher_m0/bridge/controller.py` | 100644 | `4baa85f74ae830a911d197621e85645be9c1a608` | 同左（初始 clean 时） |
| `src/autoteacher_m0/bridge/attempts.py` | 100644 | `d54ce4a9b93836934b8a9a788f41b46993f1c6cb` | 同左 |
| `src/autoteacher_m0/bridge/ipc_server.py` | 100644 | `790ae93030e890096c41b1572e0d1dbbb076fca0` | 初始同左；18:33Z 后被并行改为 `03daae1b…` |
| `src/autoteacher_m0/bridge/admission.py` | 100644 | `273c2676cdcdf3683bacaca807a21911ac89d7a9` | 同左 |
| `src/autoteacher_m0/accounting/broker.py` | 100644 | `6b3813c0c3edac5f43be5fe09ae5bed3e09190ea` | 同左 |
| `src/autoteacher_m0/accounting/ledger.py` | 100644 | `aa5e7c11688597d64179b46bd2ad6cf64ac927dc` | 同左 |
| `spikes/g3b-trusted-bridge/fake/fake_provider.py` | 100644 | `11f1541292bf79b0f5409322b0bfea183c1c384c` | 同左 |
| `spikes/g3b-trusted-bridge/src/index.ts` | 100644 | `e82a497ef33f28c4b8756a7d55fb2a381c62ca4f` | 同左 |

`b2f6af0` 与 HEAD 的 8 个 blob 逐一相同；G3-C PR1 修复只改变 `attempts.py` 与 `controller.py`（相对 `e6fde1c`），已包含在 HEAD。

### 2.3 工作区来源冲突（D-G0-01 的阻断项）

2026-11-17T18:33:41Z 现场：

```text
HEAD=d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d
 M src/autoteacher_m0/bridge/controller.py
 M src/autoteacher_m0/bridge/ipc_server.py
 M tests/integration/g3c/test_c1_03_admission.py
 M tests/integration/g3c/test_c3_02_deadline.py
?? tests/integration/g3d/test_d1_socket_boundary.py
```

`git diff --stat`：4 files changed, 342 insertions(+), 31 deletions(-)。现场内容显示 `ipc_server.py` 增加了 D1-A 的 socket mode/gid、`SO_PEERCRED`、`on_ready`、stale-socket 检查；`controller.py` 配套修改；两个 G3-C 测试是 D-P0 的可移植性改动。**这些改动不是本 Agent 做的**；本 Agent 只读取并记录，没有 `git add`/`checkout`/`restore` 它们。

在 18:33:19Z 的“已加载模块”检查中，当前工作树 `ipc_server.py` 的**文件内容 SHA-256** 为 `e0d62e49…`，HEAD 内容 SHA-256 为 `168bcc02…`（对应 git blob 分别为 `03daae1b…`/`790ae930…`），所以“当前 worktree 加载模块 = 批准 SHA”不成立。为区分**提交基线**与**并行 WIP**，18:34:52Z 用 `git archive b2f6af0 src` 到 `/tmp` 独立加载，6 个模块全部匹配 `b2f6af0`：

| 模块 | `inspect.getfile`（临时 archive） | SHA-256 = `b2f6af0` |
|---|---|---|
| `bridge.controller` | `/tmp/g3d-approved.*/src/.../controller.py` | ✅ `cbec21f7…` |
| `bridge.attempts` | 同上 | ✅ `ccd008bd…` |
| `bridge.ipc_server` | 同上 | ✅ `168bcc02…` |
| `bridge.admission` | 同上 | ✅ `174358c8…` |
| `accounting.broker` | 同上 | ✅ `0016304a…` |
| `accounting.ledger` | 同上 | ✅ `15b3cf9d…` |

结论：**提交的 `b2f6af0` 身份可证明；当前 worktree 不是批准的 clean 基线**。按任务书 §4.3“工作区来源冲突”应 STOP，不能把并行 WIP 当作 D-G0 冻结输入。

---

## 3. Stage 身份（旧 G3-C stage 是 `e6fde1c`，不是 `b2f6af0`）

### 3.1 Canonical 与逐文件比对

| 项 | 值 |
|---|---|
| stage 路径 | `artifacts/g3c/stage` |
| stage canonical（tar，sort/mtime=0/owner=0） | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` |
| `stage/src` 文件数 | 86（含 37 个 `__pycache__`；49 个 `.py` 源文件） |
| 49 个 `.py` 与 `e6fde1c` 比对 | **全部相等**（`all_py_match_e6fde1c=true`） |
| 是否有仅匹配 `b2f6af0` 的 `.py` | 否 |
| `e6fde1c → b2f6af0` 改变的文件 | `bridge/attempts.py`、`bridge/controller.py` |

关键文件：

| 文件 | stage SHA-256 | `e6fde1c` | `b2f6af0` | 结论 |
|---|---|---|---|---|
| `bridge/attempts.py` | `33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167` | `33017e75…` | `ccd008bd…` | stage = 旧 `e6fde1c` |
| `bridge/controller.py` | `8d7e204158e7820514353c871bfc66debd41c2e34000a4ce95ab4b324a202d06` | `8d7e2041…` | `cbec21f7…` | stage = 旧 `e6fde1c` |

PR1 标记在 stage 中**不存在**：

```text
grep INIT_BUSY_TIMEOUT_MS|def _initialize|CONTROLLER_SINGLETON_LOCKED artifacts/g3c/stage/src/...
# NO_PR1_MARKERS_IN_STAGE

git show b2f6af0:src/autoteacher_m0/bridge/attempts.py | grep ...
# 40:INIT_BUSY_TIMEOUT_MS = 250
# 109:    def _initialize(...)
git show b2f6af0:src/autoteacher_m0/bridge/controller.py | grep ...
# 78:ERROR_CONTROLLER_SINGLETON_LOCKED = "CONTROLLER_SINGLETON_LOCKED"
# 1570: return EXIT_CONTROLLER_SINGLETON_LOCKED
```

因此，旧 stage 的 `stage/src` 是 **pre-PR1（`e6fde1c`）批次**；旧 Packet 的 R5 命令挂这个 stage 时会加载旧 `attempts.py`，不能作为 D1 的 approved source。

### 3.2 源码 overlay 机制（`scripts/g3c/reproduce-coldstart-with-src-overlay.sh`）

脚本 SHA-256：`93e6c5e39b86c70fd19ac4329213119831c7f6e5d5d59846ac324c2807856b95`；`bash -n` exit 0。

机制（只读复核，未运行完整 overlay）：

1. 校验 rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…`；
2. `cp -a "$STAGE/." "$OVERLAY/"` 复制 frozen stage 到临时目录；
3. `rm -rf "$OVERLAY/src"`；`git archive "$IMPL" src | tar -x -C "$OVERLAY"`；
4. 断言 overlay `attempts.py` 的 SHA = `git show "$IMPL:src/.../attempts.py"`，且 **不等于** stage 的旧 SHA；
5. 断言 overlay 含 `INIT_BUSY_TIMEOUT_MS = 250`、`def _initialize`、`CONTROLLER_SINGLETON_LOCKED`；
6. 把 `coldstart_overlay_probe.py` 复制进 overlay，挂到 `/probe`（ro），在固定 rootfs 内跑两 Controller；不改 repo/stage/旧 evidence；
7. 运行后重算 rootfs/deps/stage canonical 并删除临时 overlay。

正确用法：

```bash
bash scripts/g3c/reproduce-coldstart-with-src-overlay.sh \
  --impl b2f6af054555705192c4e1ae3019a68078764736 \
  --rounds 5 \
  --out artifacts/g3c/repro-coldstart-$(date -u +%Y%m%dT%H%M%SZ)
```

`--help` exit 0；脚本明确要求 **impl 必须是 post-PR1**，否则 `attempts.py` 与 stage 相同会直接报错。该脚本用于纠正旧 R5，不是 D1 的最终 Stage 构建器。

### 3.3 D1 规则

- **D1 必须新建独立 `{trusted,candidate}` Stage**，trusted 产品模块来自同一经批准实施 SHA；不得复用 `artifacts/g3c/stage/src`，不得把旧 stage 的 `run_c3`/fake/controller 旧副本混入。
- D1 必须记录新 Stage 的 Manifest：源 blob、构建产物哈希、Runtime 版本；用 `inspect.getfile` + 逐文件 SHA 证明实际加载模块。
- 本次未修改 stage；stage canonical 前/后一致（`fcdb0de4…`）。

---

## 4. 环境前置与 `CAN_ISOLATE` 复测

### 4.1 宿主/内核/OS

| 项 | 值 | 命令/证据 |
|---|---|---|
| OS | Ubuntu 24.04.4 LTS (Noble) | `env-03-kernel-os` |
| 虚拟化 | **LXC**（`container=lxc`；`systemd-detect-virt=lxc`） | `env-03-kernel-os` |
| kernel | `6.17.13-2-pve`，x86_64，Proxmox 构建 | `uname -a` |
| 宿主身份 | `uid=0(root) gid=0(root)`；LXC userns `0 100000 65536` | `env-11-userns` |
| CapEff | `000001ffffffffff`（宿主）；容器内 candidate `0` | `env-10-security` / `probe-02` |
| LSM | `lockdown,capability,yama,apparmor,ima,evm`；AppArmor enabled，SELinux N/A | `env-10-security` |
| seccomp | 宿主 `Seccomp: 2`；Podman `seccompEnabled=true`，profile `/usr/share/containers/seccomp.json` | `env-10-security` / `env-04` |

### 4.2 Podman / OCI / cgroup

| 项 | 值 |
|---|---|
| Podman | `4.9.3`，**rootful**（`rootless=false`），cgroup manager `systemd`，cgroup `v2` |
| OCI runtime | `crun 1.14.1`，`/usr/bin/crun`，`crun_1.14.1-1_amd64`；`+SECCOMP +APPARMOR +SELINUX +EBPF` |
| conmon | `2.1.10`，`/usr/bin/conmon` |
| cgroup fs | `cgroup2fs`；controllers `cpuset cpu io memory hugetlb pids rdma misc dmem`；subtree `cpuset cpu io memory hugetlb pids` |
| Podman 报告 controllers | `memory,pids` |
| `/etc/subuid` | **0 字节**（sha256 `e3b0c442…`），内容为空 |
| `/etc/subgid` | **0 字节**（sha256 `e3b0c442…`），内容为空 |
| rootless / `keep-id` / `auto` | 不可用（`podman unshare id` exit 125“please use unshare with rootless”；idmap 为空） |
| userns sysctls | `kernel.unprivileged_userns_clone=1`；`user.max_user_namespaces=2147483647` |
| gid 2000 | 宿主 `getent group 2000` 无输出（可用） |
| 本地 image | `localhost/autoteacher-local-oci:rootfs` 等 4 个已存在；本任务**未用 image、未 pull** |

### 4.3 探针结果（每项含 UTC / exit / 证据）

所有容器均 `--rootfs artifacts/security/rootfs`、`--network none`、`--http-proxy=false`、`--unsetenv-all`、`--no-hosts`、`--read-only`、`--read-only-tmpfs=false`、`--cap-drop ALL`、`--security-opt no-new-privileges`，结束后 `podman ps -a` 检查。

| # | UTC | 探针 | exit | 关键输出 | 证据 |
|---|---|---|---|---|---|
| P1 | 18:27:11Z | rootfs smoke + Python/SQLite + rootfs 写 | 0 | Python `3.11.15`、SQLite `3.50.4`；`WRITE / ERR 30` (`EROFS`)；`/work`/`/tmp` OK | `probe-01-smoke` |
| P2 | 18:27:26Z | 嵌套 `--uidmap 0:65534:1 --gidmap 0:65534:1` | 0 | host `/proc/<pid>/status` `Uid/Gid=65534`；container `uid=0 gid=0`；`uid_map=0 65534 1`；`gid_map=0 65534 1`；`CapEff=0`、`NoNewPrivs=1` | `probe-02-map-container` |
| P3 | 18:29:17Z | 双容器 UDS + `SO_PEERCRED` + 文件/网络 | 0 | 目录 `2750 root:2000`；socket `770 root:2000`；peercred `pid=0 uid=65534 gid=65534`；candidate `uid_map=0 65534 1`，`gid_map=0 65534 1 / 2000 2000 1`；`groups=[2000,0]`；connect OK；unlink `EROFS(30)`；rebind `EADDRINUSE(98)`；IPC 写 `EROFS(30)`；`/work/state` `ENOENT`；`AF_INET/6 EPERM(13)`；`AF_UNIX OK`；`ifaces=lo`；`proc_pids=[1]` | `probe-04-uds-peercred` |
| P4 | 18:32:46Z | 干净 `--network none` 网络面 | 0 | `AF_INET/6 EPERM(13)`；`AF_UNIX CREATE_OK`；仅 `lo`；`/proc/net/route` 无条目；env 仅 `HOME/HOSTNAME/PATH/TMPDIR` | `probe-06-network` |
| P5 | 18:30:30Z | cgroup pids/mem/cpu | 0 | `pids.max=8`；fork 7 个后第 8 个 `EAGAIN(11)`；`memory.max=134217728`；64 MiB 分配后 `memory.peak=74825728`；`cpu.max=50000 100000`；`cgroup_self=0::/` | `probe-05-cgroup-resources` |
| P6 | 18:29:56Z | rootfs 空目录清理 | 0 | 仅删除**空** `rootfs/evidence`（1755）；canonical 恢复 `25491e45…` | `cleanup-01-rootfs-empty-evidence` |

**关键解读**：

- 候选容器的 **container uid 0 不是宿主 root**：宿主 `/proc/<pid>/status` 的 `Uid/Gid` 为 65534；trusted 侧 `SO_PEERCRED` 也看到 65534（不同 PID namespace 时 `pid=0`，不能用于鉴权）。
- UDS 目录/ socket 的组权限来自 host 预创建的 **setgid 目录**；trusted 以 `--cap-drop ALL` 运行时不依赖 `CAP_CHOWN`。
- candidate 侧 socket `stat` 显示 `uid=65534 gid=2000 mode=0770`（host uid 0 在其 userns 中未映射，显示为 overflow 65534），但**连接成功**；host 侧权威 stat 为 `770 0:2000`。
- candidate 对 IPC 目录的 `unlink`/写入分别得到 `EROFS(30)`；同路径 `bind` 得 `EADDRINUSE(98)`，符合 D0 P-05。
- `AF_NETLINK` 用 `SOCK_STREAM` 得 errno 94（“Socket type not supported”），不是网络放行；不作为 `AF_INET` 证据。
- 第一次 UDS 尝试（`probe-03`，18:28:51Z）exit 2：candidate 脚本 0400 属 host root，在 candidate userns 中不可读；把候选脚本改 `0444` 后 `probe-04` exit 0。该失败仅影响探针脚本权限，不影响内核结论。

### 4.4 rootfs 漂移/清理与并发

- UDS 探针后 rootfs 出现一个 **空目录** `artifacts/security/rootfs/evidence`（1755 root:root），canonical 变为 `97d723ab…`。本 Agent 验证其 `entries=0` 后仅 `rmdir` 该空目录，canonical 恢复 `25491e45…`；未删除/改写任何运行时文件。
- 18:30–18:36Z 另一个并行 Agent 的短容器 `g3d-dp0-oci-full` 出现（非本 Agent 创建），rootfs 又短暂出现 `97d723ab…`；该容器自行退出后，18:36:58Z canonical 恢复 `25491e45…`。本 Agent 未删除该容器或它的文件。
- 该现象说明 **rootfs 是共享可写目录，D-G0/D-P0/D1 并行会竞争 hash**；D1 必须使用独立 run 目录、串行化 rootfs 重算，不能把瞬时 hash 当作稳定证据。

---

## 5. Rootfs / Deps / DSH / Adapter 身份

### 5.1 Canonical 前后

| 对象 | 前置（18:24:27Z） | 最终（18:37:49Z） | 结论 |
|---|---|---|---|
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | 同左 | NO_DRIFT（中间有空目录瞬时漂移并已清理） |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同左 | NO_DRIFT |
| stage | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` | 同左 | NO_DRIFT（旧 stage 未被修改） |

canonical 命令：

```bash
tar -C <path> --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
```

### 5.2 DSH runtime 与 Node

| 项 | 值 |
|---|---|
| 固定 runtime 路径 | `artifacts/foundation/deps/deepseek_harness_runtime/runtime/deepseek-harness-sdk-runtime-linux-x64` |
| SHA-256 / 大小 | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` / `182,717,632 B` |
| `--version` | `0.2.2-rc.2`（exit 0） |
| 系统 `/usr/bin/dsh` | `0.2.1-rc.2`，SHA-256 `80112efe368efb1a39720c7ada0af00442e5131fb2744edaaff8a3e8bb499e6f`；**不得替代** |
| Node（host / rootfs） | `v22.23.2`；`/usr/bin/node` 与 `rootfs/usr/bin/node` SHA-256 均为 `3517c2df…` |
| Adapter build meta | `artifacts/g3c/build/bridge/build-meta.json`；`createdUtc=2026-11-17T13:40:24.374Z`，`node=v22.23.2`，`typescript=5.9.3`，`dshLlmVersion=0.2.2-rc.2` |
| Adapter 产物 | `lib/index.js` SHA-256 `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba`，20,321 B；`lib/index.d.ts` `d72067d3…`；build 与 stage 的 `index.js` 一致 |
| Adapter 输入源 | `inputSourceSha256=b0f0e8a7…`；`dshLlmPackageJsonSha256=88e094f5…` |

说明：`--version` 只执行 runtime 自报版本，不加载插件、不访问网络；运行时输出的 `UNDICI-EHPA` warning 来自 Node 的 EnvHttpProxyAgent 提示，未产生 HTTP 请求。系统 `dsh` 与锁定 runtime 的版本/哈希都不同，D1 必须用 deps 内 runtime。

---

## 6. 0-Key / No-Live / 网络面

### 6.1 Key 与 dotenv

| 项 | 结果 |
|---|---|
| 当前 shell 环境变量名总数 | 46 |
| 匹配 `KEY/TOKEN/SECRET/CREDENTIAL/PASSWORD/AUTH/API_KEY...` 的变量名数 | **0**（只打印名称，未打印任何值） |
| proxy-like 变量名 | 9 个（`HTTP_PROXY`、`HTTPS_PROXY`、`ALL_PROXY`、`NO_PROXY` 及小写等）；**只记录名称，未打印值**；容器内 `--unsetenv-all` 后无这些变量 |
| `.env` | **不存在**（`find . -name .env` 无结果） |
| `.env.example` | 存在，sha256 `440251f47b22b8e61f128b28efd0d338fd74e4c9b65306be25023258b3cf64dd`（示例，不是 Key） |
| Key/Token 值扫描 | `artifacts/g3d/logs` 中 `sk-…`/`Bearer …`/`API_KEY=` 模式计数均为 0 |

### 6.2 LiveGate 与 run_live

```text
$ bash scripts/run_live.sh
BLOCKED SECURITY_BLOCKED: no independent authorization/controller boundary.
Review docs/M0_RUNBOOK.md; a Markdown approval is not an execution capability.
exit 3
```

`LiveGate().inspect(live_requested=True)`：

```json
{
  "status": "BLOCKED",
  "reasons": [
    "EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED",
    "BASELINE_EVIDENCE_MISSING",
    "ACTUAL_TOOL_REGISTRY_NOT_APPROVED",
    "SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED"
  ],
  "external_boundary_deployed": false
}
```

`scripts/run_live.sh` 是硬停止脚本（不是读 Key 的 convenience wrapper）；本 Agent 未修改它。

### 6.3 网络面

- 静态：`src/` 中无 `AF_INET`/`AF_INET6`/`create_connection`/`http.client`/`urllib.request`/`requests`/`httpx`/`aiohttp` 匹配；bridge 只使用 `socket.AF_UNIX`。
- 容器：所有探针 `--network none`；candidate `AF_INET/6` 实测 `EPERM(13)`，仅 `lo`，无 route；`AF_UNIX` 仅用于批准 UDS。
- 主机：未执行 `curl`/`wget`/`git fetch`/`podman pull`；`commands.jsonl` 中这些 token 计数均为 0；`podman images` 与初始一致（4 个本地 image，无新 pull）。
- 说明：宿主环境存在 proxy 变量名，但本任务未用它们发起外部 HTTP；锁定的 DSH 只执行了 `--version`，未加载插件、未走 provider 路径。

---

## 7. D-G0-01..05 状态

| Case | 状态 | 依据/残余 |
|---|---|---|
| **D-G0-01** Git clean baseline | **PARTIAL / BLOCKED** | HEAD `d74f2ff`、`b2f6af0` 身份、8 个 blob、`src/tests/spikes/plugins` 零 diff 均已记录；18:23:42Z 初始 clean。但 18:33:41Z 起 worktree 有并行 D1-A/D-P0 未提交改动（4 modified + 1 untracked），clean freeze 不成立。按 §4.3 **STOP**。 |
| **D-G0-02** Podman rootful userns readiness | **PASS** | rootful 4.9.3 + crun 1.14.1；host UID 0 / candidate host UID 65534；`--uidmap 0:65534:1` + `--gidmap` 实测；peercred 65534；独立 namespace；UDS 组权限可用。 |
| **D-G0-03** Canonical rootfs/deps/stage | **PASS（身份）/ 附带旧 stage 警告** | rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…` 前后一致；stage 49 个 `.py` 全部 = `e6fde1c`；`b2f6af0` 临时 archive 加载 6 模块全匹配；旧 stage 是 pre-PR1，D1 不得复用。 |
| **D-G0-04** 0 Key / no network / LiveGate | **PASS** | key-like env 名 0；无 `.env`；`run_live` exit 3；LiveGate BLOCKED；`AF_INET/6 EPERM`；静态 AF_UNIX-only；无 pull/外部 HTTP 命令。 |
| **D-G0-05** DSH/Node/Adapter lock | **PASS** | DSH `1cc41d5a…` / `0.2.2-rc.2`；系统 dsh `0.2.1-rc.2` 不同；Node `v22.23.2`；adapter build-meta 与产物 hash 固定。 |

**总体**：`D-G0_PARTIAL_BLOCKED_WORKSPACE_CONFLICT`。环境本身 `CAN_ISOLATE`，但 clean baseline 被并行 worktree 破坏；**D1 不得在本次结论下开始**，需 Lead 先处理。

---

## 8. STOP 条件评估（任务书 §4.3）

| STOP 条件 | 实测 | 判定 |
|---|---|---|
| UID Map / Namespace / Rootfs / Deps 实测不兼容 | host 0 / candidate 65534；`--uidmap`/`--gidmap` 成功；rootfs/deps canonical；独立 namespace；AF_INET EPERM；cgroup 限制生效 | **未触发**（环境 `CAN_ISOLATE`） |
| 出现凭据/外网 | key-like env 名 0；无 `.env`；无 Key/Token 值；无 curl/wget/git fetch/podman pull；容器 network none | **未触发** |
| Stage 身份不可证明 | 旧 stage 49 py = `e6fde1c`；b2f6af0 临时 archive 6 模块匹配；PR1 标记只在 b2f6af0；overlay 脚本机制/用法已记录 | **未触发**（身份可证明；但旧 stage 不可复用） |
| 工作区来源冲突 | 18:33:41Z 起 4 modified + 1 untracked，来自并行 D1-A/D-P0；HEAD 未变；非本 Agent 改动 | **触发 → BLOCKED** |

**结论**：D-G0 环境证据足以支持“本机 CAN_ISOLATE”，但 clean baseline 冻结因工作区并行改动而 **BLOCKED**。在 Lead 将 D1-A/D-P0 移到独立 worktree/分支（或明确授权在 dirty worktree 下继续）之前，**D1 不得开始**；不得用未提交 WIP 作为 approved implementation，也不得复用旧 G3-C stage。

---

## 9. D1 前置结论

D1 启动前必须满足：

1. **工作区隔离**：D1-A/D-P0 使用独立 worktree/分支；或 Lead 明确确认当前 worktree 的 WIP 不属于 D1 基线，并重新跑 clean preflight。D-G0 不清理、不 stash、不提交他人的改动。
2. **产品 SHA 固定**：approved implementation 必须是 `b2f6af0` 或经 Lead 审批的新 SHA；`git diff <base>..<impl> -- src tests spikes plugins` 与 D1 preflight 结果记录。
3. **新 Stage**：D1 必须从 approved SHA 新建 trusted/candidate stage；**禁止**复用 `artifacts/g3c/stage/src`、旧 controller/fake/run_c3；新 stage 必须带 Manifest（源 blob、构建产物 hash、Runtime 版本）。
4. **加载证明**：`inspect.getfile` + 实际文件 SHA 对照 `git show <impl>:<path>`；仅 `git rev-parse`/Packet hash 不算通过。
5. **环境重跑**：D1 preflight 在目标 Runner 重跑 UID map/namespace/peercred/`--network none`/cgroup；本机 `CAN_ISOLATE` 不可外推。
6. **权限参数**：`$RUN/ipc` `2750 root:2000`、socket `0770 root:2000`、candidate `--group-add 2000`；禁止 0666/同 UID；candidate 不挂 state/evidence/repo/Key。
7. **No-Key/Live**：0 Key、无 `.env`、无外部 HTTP、`run_live` exit 3、LiveGate BLOCKED；不得以“D-G0 已跑”解除 LiveGate。
8. **清理**：每 run 独立目录/容器名；结束 `podman ps -a` 空、`at-g3d-*` 无残留、rootfs/deps canonical 前后一致；共享 rootfs 必须串行重算。

D1 **不做**：真实 Key/模型/Provider HTTP、`podman pull`、G4/G5/Live、复用旧 stage、修改 G3-C 协议/冻结 Packet。

---

## 10. 证据索引

### 10.1 目录

| 路径 | 内容 |
|---|---|
| `artifacts/g3d/commands.jsonl` | 56 条记录的 argv、UTC start/end、exit、stdout/stderr 路径与 SHA-256 |
| `artifacts/g3d/logs/` | 每条命令的原始 stdout/stderr（文件名 = label） |
| `artifacts/g3d/env/podman-info.json` | `podman info --format json` 原始输出 |
| `artifacts/g3d/env/stage-identity.json` | 49 个 `.py` 的 stage/e6fde1c/b2f6af0 SHA 与匹配标记 |
| `artifacts/g3d/env/final-identity.json` | 最终 HEAD/hash/status/冲突文件 |
| `artifacts/g3d/evidence/summary.json` | 机器可读的 D-G0 摘要与状态 |
| `artifacts/g3d/runs/uds-*` | UDS 探针的 host 目录、trusted.json、探针脚本 |

### 10.2 关键命令/退出码

| Label | 命令摘要 | exit | UTC |
|---|---|---|---|
| `git-01-status` | `git status --porcelain=v1`（初始） | 0（空） | 18:23:42Z |
| `git-06-catfile` | `git cat-file -t b2f6af0` | 0 | 18:23:55Z |
| `git-07-diffstat` | `git diff --stat b2f6af0..HEAD -- src tests spikes plugins` | 0（空） | 18:23:55Z |
| `canonical-pre` | rootfs/deps/stage canonical 前置 | 0 | 18:24:27Z |
| `stage-01-identity` | 49 py vs e6fde1c/b2f6af0 | 0 | 18:24:48Z |
| `env-01`/`env-02` | Podman / crun 版本 | 0 | 18:25:53Z |
| `env-04` | `podman info --format json` | 0 | 18:26:18Z |
| `env-05` | `/etc/subuid`、`/etc/subgid`、gid 2000 | 0 | 18:26:18Z |
| `env-06` | cgroup v2 controllers/limits | 0 | 18:26:31Z |
| `env-11` | `unshare --user --mount --pid --net` | 0 | 18:26:51Z |
| `probe-02` | 嵌套 UID/GID map + host `/proc` | 0 | 18:27:26Z |
| `probe-04` | 双容器 UDS/peercred/网络/文件 | 0 | 18:29:17Z |
| `probe-05` | cgroup pids/mem/cpu | 0 | 18:30:30Z |
| `probe-06` | 干净 network none socket family | 0 | 18:32:46Z |
| `runtime-01` | DSH binary SHA/--version；系统 dsh | 0 | 18:31:32Z |
| `runtime-02` | Node 版本/hash | 0 | 18:31:41Z |
| `live-08-run-live-direct` | `bash scripts/run_live.sh` | **3** | 18:38:48Z |
| `live-02-livegate` | `LiveGate.inspect(live_requested=True)` | 0（输出 BLOCKED） | 18:32:12Z |
| `g0-02-approved-modules` | 从 `b2f6af0` archive 加载 6 模块 | 0 | 18:34:52Z |
| `drift-01`/`drift-02` | 工作树冲突、blob vs worktree | 0 | 18:33–18:34Z |
| `final-01-state` | 最终 HEAD/hash/ps/status | 0 | 18:37:49Z |

> `probe-03`（18:28:51Z）exit 2 是探针脚本 0400 权限设置错误，已由 `probe-04` 修正；不纳入环境结论。`live-01` 的 wrapper exit 0 是因为脚本内 `echo $?`，真正的 `run_live` 退出码以 `live-08` 的 recorder exit 3 为准。

### 10.3 未运行/未验证

- D1/D2/D3 的真实 DSH Echo/Tool/Resume、跨容器攻击、崩溃/取消/重放、全量 OCI 回归：**未运行**（不属于 D-G0）。
- G3-C 旧 stage 的完整 coldstart overlay 运行：**未运行**；只读核验了脚本机制与用法。
- 固定 OCI 的 `pgrep`/`/tmp noexec` 两项移植性修复：**未运行**（D-P0 范围）。
- 其他 Runner 的 `CAN_ISOLATE`：**不可外推**；换机必须重跑。

---

## 11. 清理与无残余

- 所有 `at-g3d-*` 探针容器已删除；最终 `podman ps -a --filter name=at-g3d-` 为空，全局 `podman ps -a` 为空（18:37:49Z）。
- 探针使用的 `$RUN/ipc` 已删除；`bridge.sock` 已 unlink；无 `at-g3d-*` 进程。
- 最终 rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…` 与前置一致。
- `podman images` 与初始一致；无 pull；无 `at-g3d-*` 残留。
- 观察到并行 `g3d-dp0-oci-full` 短容器（非本 Agent）；本 Agent 未清理它；它自行退出。
- 未删除/移动/提交任何他人的 worktree 改动。

---

## 12. 声明与非主张

1. 本文档是 **D-G0 基线/环境证据**，不是 D1 实施、不是 D2/D3、不是 G3-D PASS，也不是 Live/GO。
2. `OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立；D-G0 的 `CAN_ISOLATE` 只适用于本机 2026-11-17 的 LXC CT101 环境，不可外推到其他 Runner。
3. 本文档不声称内核/容器运行时无 0day、不声称供应链/宿主 root/侧信道安全；这些是设计中的 residual risk。
4. 真实 Key、真实模型、Provider HTTP、`podman pull`、LiveGate 解锁、G4/G5 均未发生，也不由本文档授权。
5. 任何后续 D1 必须重新核验 HEAD/产品 SHA/Stage/环境，并在 clean/隔离的 worktree 中进行。
