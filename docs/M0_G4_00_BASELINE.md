# M0 G4-00 — 基线、环境与能力测绘报告（No-Key）

- **任务**：G4-00-01..10（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §3）
- **执行者**：G4-00 Baseline/Capability Mapping Agent（只读核验 + docs/证据；不改产品代码、测试、脚本）
- **执行时间（UTC）**：2026-11-18T15:25Z → 15:43Z
- **性质**：**no-key / no-model / no-network / no-container-start**。0 真实 Key、0 模型调用、0 外部 HTTP/TCP、0 真实计费请求；未执行 `podman pull`、未启动任何容器；`podman ps -a` 全程为空。
- **本轮裁定**：G4-00 基线**成立**，未触发任何 STOP 条件；`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING` 不变。
- **本文件不是**授权、不是 G4 PASS、不是 E5-PreLive Full、不是 Live 批准。

---

## 0. 裁定摘要

| 项 | 结果 |
|---|---|
| 基线 HEAD | `810e313c3e3d459db8b1c5517366e33ae0154811`（= 任务书期望值，**未漂移**） |
| 工作区 | `git status --porcelain=v1 -uall` = **0 行**（clean） |
| G3-D 冻结实现 | `cf40c6bfb84ceae98e795db19efa955aa3035991`；`src/ tests/ config/ plugins/` 子树哈希与 HEAD **完全相同** |
| 环境 canonical | rootfs `25491e45…`、deps `e07729d7…`、D3 stage tree `e1ff1449…`、stage manifest `644823d4…`、DSH runtime `1cc41d5a…` → **全部重算一致，0 drift** |
| 实际加载模块 | 容器内 **10/10** 模块 SHA = `git show cf40c6b:<path>` = stage trusted 副本；宿主新进程 **17/17** 模块 `inspect.getfile` 均来自 `src/` 且匹配 HEAD blob |
| OS 主体 | Candidate 宿主 kuid **65534**（独立 userns）/ Trusted 宿主 uid **0**（host userns）；UDS `0660 root:2000`；`SO_PEERCRED uid=65534`；Candidate mount 无 `/work/state` |
| Live 负例 | `LiveGate` 恒 `BLOCKED`（**即使把所有可诊断证据都满足，仍只剩外部人类边界一条理由**）；`run_live.sh` exit **3**；CLI/env/Markdown/Adapter 全部阻断；真实计费调用 **0** |
| 组件 wiring | 7 个 security 模块：`implemented` 7/7、`tested_in_isolation` 7/7、`wired_into_trusted_process` **仅 `egress.py`**、`externally_deployed` **0/7** |
| P2 | P2-DISK / P2-USERNS / P2-RUN-IDENTITY 全部**仍为维护者待决**，本轮**不默认批准** |
| Tool registry | DSH 0.2.2-rc.2 **不存在**权威 merged tool registry/schema 导出 API → **`UNVERIFIED`**；需 Controller 严格 schema/白名单兜底 |
| 基础回归 | `299 passed`（exit 0）；security 隔离集 `165 passed, 1 failed`（host-only 环境失败，OPS-P2-b 已知项，**非安全回归**） |
| STOP | **未触发**（逐项见 §11） |

---

## 1. G4-00-01 — Git 身份与代码漂移

### 1.1 身份

| 项 | 值 | 命令 / 来源 |
|---|---|---|
| HEAD | `810e313c3e3d459db8b1c5517366e33ae0154811` | `git rev-parse HEAD` |
| 父提交 | `017c747631cae1e7788014c4ef9e6056c141fecd` | `git rev-list --parents -n 1 HEAD` |
| HEAD tree | `10f68f1284a4908aa8af4d44abba8de0a73a0924` | `git rev-parse HEAD^{tree}` |
| 工作区 | clean（0 行，`-uall`） | `git status --porcelain=v1 -uall` |
| remote | `origin git@github.com:ygmldr/Autonomouse-Teacher.git`（fetch/push） | `git remote -v` |
| 参考远程 HEAD（任务书） | `017c7476…`；实际本地 HEAD 比它多 1 个 docs 归档提交 | `docs/Autonomous_Teacher_M0_G4_START_HERE.md:4` |

`git log -15`（最新在上）：

| SHA | UTC | 主题 |
|---|---|---|
| `810e313` | 2026-11-18T15:20:57Z | docs: archive G4 prelive no-key plan, start-here and test matrix (verbatim) |
| `017c747` | 2026-11-18T00:31:22Z | docs: archive G3-D independent review (PASS) and final errata (no-key) |
| `ce4979e` | 2026-11-17T23:26:02Z | docs: fix G3-D commit attribution and record regression head (no-key) |
| `f18c239` | 2026-11-17T23:19:38Z | fix: G3-D packet old-bypass denial table (no-key) |
| `0f21df7` | 2026-11-17T23:12:44Z | fix: G3-D packet D2 probe sources self-contained (no-key) |
| `c3be694` | 2026-11-17T23:11:49Z | fix: G3-D packet verifier path ordering (no-key) |
| `7043ab9` | 2026-11-17T23:11:28Z | fix: G3-D packet payload-tree verifier ordering (no-key) |
| `4e40acf` | 2026-11-17T23:10:45Z | fix: G3-D packet builder D3 cleanup duplicate (no-key) |
| `0131726` | 2026-11-17T23:10:24Z | fix: G3-D packet builder D2 duplicate selection (no-key) |
| `b0c2a57` | 2026-11-17T23:09:58Z | docs: G3-D implementation report, review request and review packet (no-key) |
| `97230a0` | 2026-11-17T22:36:18Z | docs: D3 gate report and matrix (no-key) |
| `cf40c6b` | 2026-11-17T22:19:50Z | fix: D3 OCI known host-root/tar deselects; leave frozen D1-A tests untouched (no-key) |
| `dc8214e` | 2026-11-17T22:15:33Z | fix: D3 OCI portability skips and rootfs canonical cleanup (no-key) |
| `ef84f57` | 2026-11-17T22:03:33Z | feat: D3 cross-principal crash, cancel and concurrency evidence (no-key) |
| `bb34931` | 2026-11-17T21:21:06Z | docs: fix D2 report residual cross-reference (no-key) |

### 1.2 冻结三提交与 HEAD 的子树对照

| 提交 | 角色 | `src` | `tests` | `config` | `plugins` | `scripts` |
|---|---|---|---|---|---|---|
| `cf40c6b` | **G3-D 代码冻结** | `09c6a20d…` | `f291dcdd…` | `63a9fb23…` | `f1572042…` | `b1525ac6…` |
| `97230a0` | D3 报告/矩阵 | 同上 | 同上 | 同上 | 同上 | 同上 |
| `017c747` | 独立复核归档 | 同上 | 同上 | 同上 | 同上 | `5fdf0b03…` |
| `810e313` | G4 任务书归档（HEAD） | 同上 | 同上 | 同上 | 同上 | `5fdf0b03…` |

**结论**：`src/ tests/ config/ plugins/` 在 `cf40c6b..HEAD` 之间**字节完全一致**（子树哈希逐项相等）。

### 1.3 `git diff cf40c6b..HEAD`（paths: src scripts config plugins docs）

`--stat`：**12 files changed, 3673 insertions(+), 19 deletions(-)**；`--name-status`：

```text
M  docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv
A  docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md
A  docs/Autonomous_Teacher_M0_G4_PreLive_Test_Evidence_Matrix_v1.0.csv
A  docs/Autonomous_Teacher_M0_G4_START_HERE.md
A  docs/M0_G3D_D3_REPORT.md
A  docs/M0_G3D_D3_REVIEW_REQUEST.md
A  docs/M0_G3D_FINDINGS_AND_DISPOSITION.md
A  docs/M0_G3D_IMPLEMENTATION_REPORT.md
A  docs/M0_G3D_REVIEW_ERRATA.md
A  docs/M0_G3D_REVIEW_REQUEST.md
A  docs/REVIEW_G3D_INDEPENDENT.md
A  scripts/g3d/build_packet.py
```

`git diff --name-status cf40c6b..HEAD -- src tests config plugins` → **空**。

**未解释漂移：无。** 两处需要显式解释的漂移已解释：

1. `scripts/g3d/build_packet.py`（+1269 行）在代码冻结后加入，是 G3-D 复核包的**证据工具**；`grep` 全仓无任何产品/测试/脚本 import 它，不进入运行时路径。归因提交为 `b0c2a57` 及后续 5 个 `fix:`（提交主题写 `docs:`/`fix:`，但实际新增脚本——**证据卫生观察 OBS-1**，不影响产品面）。
2. `docs/` 仅新增 G3-D 报告/复核/errata 与 G4 任务书三件套，属计划内归档。

### 1.4 旧 G3-C stage 反例（不得被加载）

| 对象 | SHA-256 | 说明 |
|---|---|---|
| 旧 G3-C stage canonical | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` | `docs/M0_G3D_G0_BASELINE.md:22` |
| 旧 `attempts.py`（`e6fde1c` 批次） | `33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167` | `docs/M0_G3D_D_P0_ERRATA.md:241` |
| 当前 `attempts.py`（`cf40c6b` blob） | `ccd008bd55bda8d344152856912dbde9dfe1e29d5accb53973a938e1e4b59795` | 本报告 §2.3 实测 |
| 当前 stage trusted 副本 | `ccd008bd…`（同上） | 本报告 §2.3 实测 |

三者互不相同 ⇒ **当前 stage 加载的不是旧 G3-C 源码**（`attempts.py` 新旧 hash 明确不同），且 stage manifest `head_at_build=cf40c6b`、`product_src_identical_to_base=true`。

证据：`artifacts/g4/baseline/identity.json`、`artifacts/g4/baseline/commands.jsonl`。

---

## 2. G4-00-02 — 环境、Stage、Runtime 与实际加载模块

### 2.1 根文件系统 / 依赖 / Stage / Runtime canonical（本次重算）

重算配方（与冻结文档一致）：`tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C <dir> . | sha256sum`

| 对象 | 期望值 | 本次实测 | 结论 | UTC |
|---|---|---|---|---|
| OCI rootfs（`artifacts/security/rootfs`） | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0` | 同左 | **NO_DRIFT** | 2026-11-18T15:27:37Z |
| Python deps（`artifacts/foundation/deps`） | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | 同左 | **NO_DRIFT** | 2026-11-18T15:27:37Z |
| D3 stage tree（`artifacts/g3d/stage-20261117T221955Z`） | `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5` | 同左 | **NO_DRIFT** | 2026-11-18T15:27:49Z |
| D3 stage manifest | `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03` | 同左 | **NO_DRIFT** | 2026-11-18T15:27:49Z |
| DSH runtime（`…/deepseek-harness-sdk-runtime-linux-x64`，182,717,632 B） | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` | 同左 | **NO_DRIFT** | 2026-11-18T15:41:50Z |

`tar` 退出码：rootfs 0 / deps 0 / stage 0。**本轮未启动任何容器**，也未产生新的空挂载点（无 `rmdir` 操作）。

### 2.2 运行时与平台

| 项 | 值 |
|---|---|
| Node | `v22.23.2` |
| Python（宿主，锁定） | `3.11.15`（`/root/.local/bin/python3.11`） |
| Python（系统） | `3.12.3`（仅用于无关 shell 工具，不用于产品测试） |
| Podman | `4.9.3`（rootful；`/etc/subuid`、`/etc/subgid` **为空** ⇒ rootless 不可用） |
| crun | `1.14.1`（commit `de537a79…`） |
| 内核 | `Linux 6.17.13-2-pve #1 SMP PREEMPT_DYNAMIC PMX 6.17.13-2 x86_64` |
| OS | Ubuntu 24.04.4 LTS（Proxmox LXC） |
| cgroup | v2；controllers `cpuset cpu io memory hugetlb pids rdma misc dmem` |
| DSH runtime 自报版本 | `0.2.2-rc.2`（`env -i … --version`，exit 0） |
| 宿主 `/usr/bin/dsh` | `0.2.1-rc.2` —— **不是**锁定 runtime，禁止替代（`docs/M0_G3C_G0_BASELINE.md:102`） |
| 容器 | `podman ps -a` → **0 个**（全程） |
| 本地镜像 | 4 个；`localhost/autoteacher-local-oci:candidate` digest `sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`（与 `live_controller.py` 默认 image 一致） |

> **观察 OBS-2（供 G4-B）**：宿主 `dsh`（0.2.1-rc.2）启动时会由环境变量构造 `EnvHttpProxyAgent`（`UNDICI-EHPA` 警告）。所有 runtime probe 一律用 `env -i`（无 proxy 变量）执行，避免任何隐式代理初始化。

### 2.3 实际加载模块（不能只列 stage 文件）

**(A) 容器内真实进程（L2，历史冻结证据，24 个证据文件）**

来源：`artifacts/g3d/d3/**/peercred/trusted-modules.json`（24 个 D3 case 目录），由容器内 `trusted_entry.module_identity()` 用 `importlib.import_module` + `inspect.getfile` 生成。

| 模块 | 容器内 file | 容器 SHA-256 | `git show cf40c6b:` | stage 副本 | 一致 |
|---|---|---|---|---|---|
| `bridge.controller` | `/project/src/…/controller.py` | `2ea1a962…` | `2ea1a962…` | `2ea1a962…` | ✅ |
| `bridge.ipc_server` | `/project/src/…/ipc_server.py` | `a257627b…` | `a257627b…` | `a257627b…` | ✅ |
| `bridge.attempts` | `/project/src/…/attempts.py` | `ccd008bd…` | `ccd008bd…` | `ccd008bd…` | ✅ |
| `bridge.admission` | `/project/src/…/admission.py` | `174358c8…` | `174358c8…` | `174358c8…` | ✅ |
| `bridge.broker_client` | `/project/src/…/broker_client.py` | `1fb8f8ca…` | `1fb8f8ca…` | `1fb8f8ca…` | ✅ |
| `bridge.fake_backend` | `/project/src/…/fake_backend.py` | `29645bce…` | `29645bce…` | `29645bce…` | ✅ |
| `bridge.protocol` | `/project/src/…/protocol.py` | `49cc1e83…` | `49cc1e83…` | `49cc1e83…` | ✅ |
| `accounting.broker` | `/project/src/…/broker.py` | `0016304a…` | `0016304a…` | `0016304a…` | ✅ |
| `accounting.usage` | `/project/src/…/usage.py` | `923ebca9…` | `923ebca9…` | `923ebca9…` | ✅ |
| `accounting.observation` | `/project/src/…/observation.py` | `90a35561…` | `90a35561…` | `90a35561…` | ✅ |

**重要限制（不得外推）**：`trusted_entry.module_identity()` 遍历的是**硬编码 10 模块清单**（`trusted_entry.py:50-61`），因此“某模块不在 `trusted-modules.json`”**不等于**它没被加载。该清单不含 `security.*`。

**(B) 源码对照 —— controller/ipc_server/attempts/admission/broker/egress/authorization/watchdog/ed25519**

`security/egress.py` 必然被 trusted 进程加载：`bridge/controller.py:49` 模块级 `from autoteacher_m0.security.egress import …`，而 controller 是上表实测加载的模块。其余 `security.*` 通过 `security/__init__.py` 的包级 import 亦会随 `security.egress` 一起进入 `sys.modules`（Python 语义），但**加载 ≠ 被调用**（见 §6 wiring）。

**(C) 宿主新进程（L1-HOST，本次实测，17 模块）**

在全新 CPython 3.11.15 进程中 `importlib.import_module`，记录 `inspect.getfile` + 文件字节 SHA-256：

| 结果 | 值 |
|---|---|
| 成功导入 | **17/17** |
| 全部 `real_path` 位于 `src/`（`loaded_from_repo_src=true`） | **17/17** |
| 加载字节 SHA-256 == `git show HEAD:<path>` | **17/17** |
| 加载字节 SHA-256 == `git show cf40c6b:<path>` | **17/17**（因 src 子树未变） |

含 `bridge.{controller,ipc_server,attempts,admission,broker_client,fake_backend,protocol}`、`accounting.{broker,usage,observation}`、`security.{gates,authorization,ed25519,credential_boundary,watchdog,egress,live_controller}`。

**证据等级声明**：(A) 是真实容器内进程（L2，来自 G3-D 冻结运行，本轮未重跑容器）；(C) 是本轮真实进程但为宿主 CPython（L1-HOST），**不能**替代容器内证据。二者与 `git show cf40c6b` 三方一致，故“未加载旧 G3-C stage”成立。

证据：`artifacts/g4/baseline/env.json`、`module-container-evidence.json`、`module-host-import.json`。

---

## 3. G4-00-03 — OS Principal 现状（D1/D2/D3 复算与引用）

**本轮不启动新 D1 全链**；以下数值逐项读自 G3-D 冻结证据树（`artifacts/g3d/d3/d3-c02`，真实 D3 run，2026-11-17T22:24Z），并与 G3-D 报告/独立复核结论一致。

| 维度 | Candidate | Trusted | 来源 |
|---|---|---|---|
| 宿主 uid（`/proc/<pid>/status`） | **65534**（`65534 65534 65534 65534`） | **0**（`0 0 0 0`） | `uid-map/runtime-identity.json` |
| 宿主 gid | 65534 | 0 | 同上 |
| `uid_map` | `0 65534 1`（独立 userns） | `0 100000 65536`（= 外层 LXC userns，host userns） | 同上；`docs/M0_G3D_OS_BOUNDARY_DESIGN.md:31` |
| `gid_map` | `0 65534 1` + `2000 2000 1` | `0 100000 65536` | 同上 |
| `CapEff/CapPrm/CapBnd` | `0000000000000000` | 全 0 | 同上 |
| `NoNewPrivs` | `1` | `1` | 同上 |
| `Seccomp` | `2`（filter） | `2` | 同上 |
| cgroup v2 | `…/libpod-4806c3ae….scope/container`，`memory.max=1073741824`、`pids.max=256`、`cpu.max=100000 100000` | 对应 scope | `uid-map/*-cgroup.json` |
| UDS | `bridge.sock` `uid=0 gid=2000 mode=0660`（`mode_octal 0660`，inode 2511622） | 同左（创建者） | `socket-stat/listening.json`、`G3D_TRUSTED_READY` |
| `SO_PEERCRED` | trusted 侧日志：`bridge peer accepted uid=65534 gid=65534 pid=0` | — | `peercred/trusted-log-extract.txt` |
| 网络 | 全部容器 `--network none`；`AF_INET/AF_INET6` → `EACCES(13)`，DNS `EAI_AGAIN`，无默认路由 | 同左 | `docs/M0_G3D_D2_REPORT.md:126`（D2-07 28/28 PASS） |
| mount namespace | 仅 `/work/g3b`（**ro**）、`/work/session`（rw）、`/work` tmpfs；**无 `/work/state`** | `/work/g3b`（rw）+ `/work/state`（rw） | `mountinfo/candidate.txt`、`mountinfo/trusted.txt` |
| 独立命名空间 | user/mount/pid/net/ipc/uts/cgroup 独立 | host userns（rootful） | `docs/M0_G3D_OS_BOUNDARY_DESIGN.md:128-129` |

**判读**：两主体宿主 UID 不同（65534 vs 0）且 mount namespace 不同；Candidate 的 mount 树中根本不存在 trusted state 路径，故“Candidate 不能访问 trusted state”是**内核/挂载面**结论，不是靠文件权限“碰巧拒绝”。

**旧四绕过（G3-B 同 UID 时代）证据路径**（本轮仅登记，未重跑）：

| 旧绕过 | D2 用例 | 证据路径 | 当前结果 |
|---|---|---|---|
| B-1 读 Broker DB | D2-01 | `artifacts/g3d/d2/d2-01` | `ENOENT(2)`，DB SHA 不变，0 行 |
| B-2 写 Broker DB | D2-02 | `artifacts/g3d/d2/d2-02` | `ENOENT/EROFS/EXDEV` 全拒绝 |
| B-3 写 Policy | D2-03 | `artifacts/g3d/d2/d2-03` | 60 个探针全 `ENOENT(2)` |
| B-4 绕过 Controller 直接 Claim | D2-04/05/06 | `artifacts/g3d/d2/d2-04` … | import 失败 + `UNKNOWN_KIND`/`UNKNOWN_FIELD`，Fake=0 |

证据：`artifacts/g4/baseline/os-principal.json`。

---

## 4. G4-00-04 — LiveGate / CLI / Script / Adapter 负例（动态）

所有命令均在宿主执行，`PYTHONDONTWRITEBYTECODE=1 … python3.11 -B`，无容器、无 SDK 导入、无网络。

| # | 场景 | 输入 | 期望 | 实际 | exit |
|---|---|---|---|---|---|
| N1 | `LiveGate.inspect(live_requested=True)` | 默认 | BLOCKED | `BLOCKED`；4 条理由 | — |
| N2 | `LiveGate.require_live(live_requested=True)` | 默认 | 抛异常 | `SecurityBlocked`（code `SECURITY_BLOCKED`） | — |
| N3 | **“证据全部满足”** `inspect(live_requested=True, actual==reviewed, actual_tools=("skill_lookup",), session_log_disabled=True)` | 全部证据齐备 | **仍 BLOCKED** | `BLOCKED`，理由仅剩 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`；`external_boundary_deployed=false` | — |
| N4 | `scripts/run_live.sh` | — | exit 3 | `BLOCKED SECURITY_BLOCKED…`，**exit 3** | 3 |
| N5 | `at-m0 smoke --live` | — | exit 3 | JSON `{"status":"BLOCKED","error_code":"SECURITY_BLOCKED"}` | 3 |
| N6 | `at-m0 paired --live` | — | exit 3 | 同上 | 3 |
| N7 | `at-m0 smoke --live` + `AT_M0_LIVE_APPROVED=true` | env 旁路 | exit 3 | 同上（env **无效果**） | 3 |
| N8 | 同上 + `AT_M0_ALLOW_LIVE=true` + `AT_M0_APPROVAL_MD=docs/SECURITY_APPROVALS.md` | env 群 | exit 3 | 同上 | 3 |
| N9 | 同上 + `AT_M0_APPROVAL=…/APPROVED.md` | 伪 Markdown | exit 3 | 同上 | 3 |
| N10 | `load_execution_authorization(authorization_path=<repo 内 APPROVED.md>)` | 伪批准 MD | 拒绝 | `approved=false`，`EXTERNAL_AUTHORIZATION_INVALID:authorization must live outside the repository` | — |
| N11 | `HarnessAdapter._require_live_authorization()` | 静态 | 抛异常 | `RuntimeFailure` / `SECURITY_BLOCKED` | — |

补充静态事实：

- `dsh_adapter.py` 中 4 个 live 入口（`:101`、`:110`、`:126`、`:148`）都先调用 `_require_live_authorization()`；`deepseek_harness` 只在 `_new_harness()` 内部 import，探测进程**未导入 SDK**（`sdk_imported_by_this_probe=false`）。
- `cli.py:100` 在 import SDK、创建目录、解析审批文档**之前**先 `LiveGate().require_live(live_requested=True)`；因此上述 CLI case 均未产生任何 artifact 目录（实测 `probes/cli-*` 不存在）。
- `assert_live_entrypoints_blocked(repo)` 返回**空理由**（`[]`）⇒ 三个已知入口（script/adapter/CLI）的静态审计全部通过。
- `TrustedLiveController` 无 `run()`；公开方法只有 inspect 类（`authorization_decision`、`candidate_command`、`inspect`、`require_live`），且 `ALWAYS_BLOCKED_REASONS` 5 条恒被加入。
- 网络守护（进程内替换 `socket.socket`，禁止 `AF_INET/AF_INET6`）记录到 **0 次**尝试。

**真实计费调用数 = 0；真实外部 HTTP/TCP = 0；provider key 出现数 = 0；billable send allowed = 0。**

证据：`artifacts/g4/baseline/gate.json`、`negative-summary.json`、`gate-negatives.json`、`entrypoint-negatives.json`、`approval-path-negative.json`、`adapter-negatives.json`。

---

## 5. G4-00-05 — No-Key / No-Network 扫描

只做环境变量**名**、文件清单与正则**计数**；**未打印任何值**、未扫描宿主敏感目录（`/root/.config`、`/root/.dsh`、`~/.ssh` 等一律未读）、未校验任何远端 Key。

| 项 | 结果 |
|---|---|
| `.env` 真实文件 | **不存在**；仅 `.env.example`（tracked，425 B，示例值） |
| Key/证书类 tracked 文件（`id_rsa`/`*.pem`/`*.p12`/`*.pfx`/`credentials`/`.netrc`/`.npmrc`/`.pypirc`） | **0** |
| 当前 shell 中 key-like 变量名（`KEY/TOKEN/SECRET/CREDENTIAL/PASSWORD`） | **0** |
| 仓库密钥扫描器 `--no-history --json` | `ok=true`，**0 findings**，373 files（exit 0） |
| 仓库密钥扫描器 全历史 `--json` | `ok=true`，**0 findings**，575 blobs / 114 commits / 373 files（exit 0） |
| `--self-test` | `SELFTEST PASS`（detectors / sentinel exclusions / filename classifier） |
| 自建正则（tracked 373 files） | `sk-like`=3（全部为 **`sk-FAKE-…` 合成哨兵**）、`AKIA…`=0、`ghp_…`=0、`BEGIN … PRIVATE KEY`=0、`Bearer <long>`=0、`status="ALLOWED"/"GO"`=0 |
| `DEEPSEEK_API_KEY` 字样 | 24 处，全部是**变量名/文档说明**（`.env.example`、`SECURITY.md`、设计文档等），**无值** |
| 外部 HTTP | 0；所有 DSH 探测均 `env -i`（无 proxy 变量）；进程内 socket 守护拦截 0 次（因未尝试） |

---

## 6. G4-00-06 — 组件 Wiring Map（四列分开）

列定义：`implemented` = 代码存在且行为符合设计；`tested_in_isolation` = 有独立测试且本轮/冻结证据显示通过；`wired_into_trusted_process` = **在真实 trusted 运行时调用路径上存在调用点**（不是“仅被 `__init__` 导出”）；`externally_deployed` = 在 Agent 可写域之外有独立部署的信任根/进程/网络面。

| 模块 | implemented | tested_in_isolation | wired_into_trusted_process | externally_deployed |
|---|---|---|---|---|
| `security/gates.py` | ✅（86 行；`inspect` 恒 BLOCKED；`require_live` 恒抛） | ✅ `tests/unit/security/test_gates.py`(6) + `test_docker_runner.py`(12) | **PARTIAL — 仅 CLI 入口**（`cli.py:100`）；`bridge/`、`accounting/` **0 调用点** | ❌ |
| `security/authorization.py` | ✅（448 行；v1 schema / 绑定 / 撤销 / 过期 / Ed25519 verify） | ✅ `test_authorization.py`(22) + sandbox(9) | ❌ 仅被 `live_controller.py`（inspect-only）与包 `__init__` 引用 | ❌ |
| `security/ed25519.py` | ✅（174 行；verify 路径；sign 仅 test-only） | ✅ 同上 | ❌ 唯一调用者是 `authorization.py`（verify） | ❌ |
| `security/live_controller.py` | ✅（216 行；inspect-only，`ALWAYS_BLOCKED_REASONS` 5 条） | ✅ sandbox `test_live_controller_no_key.py`(9)（1 项 host-env 失败，见 §10） | ❌ **无生产调用者**（仅 `__init__` 导出） | ❌ |
| `security/watchdog.py` | ✅（322 行；进程树 kill / absence / PendingConservative） | ✅ `test_watchdog.py`(10) + sandbox(9) | ❌ `scripts/` **0 import**；launcher 用自己的清理辅助 | ❌ |
| `security/egress.py` | ✅（949 行；`EgressBoundary` + BrokerClaim 绑定 + prepared digest） | ✅ `test_egress_boundary.py`(6) + `g3c/test_c2_03`(5) + `g2_closure`(80) | **✅ 是**：`bridge/controller.py:49` 导入、`:243` 构造 `EgressBoundary(EgressPolicy(…g3b-fake.local…), claimer=_BoundClaimer(broker))`；controller blob 在容器实测加载；D3 C01/C02 每次调用 1 claim/attempt/receipt | ❌（synthetic-only；**默认 `EgressPolicy()` 仍指向 OpenCode Go 路由** `("opencode-go","deepseek-v4.1-flash")`，非官方 DeepSeek 路由） |
| `security/credential_boundary.py` | ✅（238 行；env allowlist / `LauncherOnlySecret` / argv+mount 校验 / 脱敏） | ✅ `test_credential_boundary.py`(9) | ❌ 仅 `live_controller.py`（inspect-only）；`scripts/` 0 调用点 | ❌ |

**关键结论**：

1. **只有 `egress.py` 真正接入了 trusted 运行时发送/记账路径**（且仅 synthetic 路由）。
2. `authorization / ed25519 / watchdog / credential_boundary / live_controller` 处于“已实现、已隔离测试、**未接入真实可信进程**”；`gates.py` 只接入 CLI 入口，**未接入容器内 controller**。
3. `externally_deployed` 对 7 个模块**全部为 false**：没有独立人类授权域、没有外部凭据 broker、没有外部 egress proxy、没有外部 watchdog 进程。这正是 `ALWAYS_BLOCKED_REASONS` 的 5 条事实基础。

> 对 G4-A/B/C/D 的直接含义：**“有代码/有单测”不能写成“已集成”**。G4-A 必须证明组合调用与失败关闭；G4-C 必须证明 Claim→Attempt→Receipt 全链；G4-D 必须新建**真正的外部** watchdog 进程（当前模块不是外部监管者）。

证据：`artifacts/g4/baseline/module-map.json`。

---

## 7. G4-00-07 — 旧四绕过回归（引用，不重跑）

本轮**不启动** Candidate 容器，故不重跑 B-1..B-4；引用 G3-D D2 的 L2 证据（见 §3 表），结论为“全部关闭”，且关闭机制是**内核拒绝 + 挂载缺失 + 协议白名单**，不是“禁用所有 UDS”（D2-05/06/09/11 在同一 Run/同一 Socket 上正向成功）。独立 Reviewer 已在 `docs/REVIEW_G3D_INDEPENDENT.md` §3.5 做过成对复核。

**状态**：`PASS (referenced L2 evidence; not re-executed this round)`。

---

## 8. G4-00-08 — P2 维护者待决登记（**本轮不默认批准**）

来源：`docs/REVIEW_G3D_INDEPENDENT.md` §8.3（P0=0、P1=0）与 G4 任务书 §2.1。

| 登记 ID | 内容 | 当前状态 | 对 G4 的影响 | 本轮是否批准 |
|---|---|---|---|---|
| **P2-DISK**（`R2-P2-a`） | Candidate `/work/session` 是 host bind mount，**无磁盘硬配额**；不受 `/work` tmpfs 限制 | 未修复；无配额实现 | 无 Key 的模拟测试可继续；**任何凭据联网的长期运行前**必须加配额或更强隔离，并留压力/恢复证据 | **否**（不改配置、不加参数、不声称已防护） |
| **P2-USERNS**（`R2-P2-b`） | 内核允许 Candidate 创建**嵌套 user namespace**（可在自 ns 内 mount tmpfs）；对 root-owned state 仍 `EACCES`，`mknod=EPERM`，ptrace trusted=`ESRCH` | 未修复（内核行为，非本仓代码） | 真实 Key 前维护者须选择：额外 seccomp / 禁 userns / 明确签收风险 | **否** |
| **P2-RUN-IDENTITY**（`R2-P2-c`） | `SO_PEERCRED` 只是 OS uid，**不是 per-Run token**；拿到 live 路径的**同 UID 旧 Run** 仍可连接 | 未修复；无 nonce/epoch/per-run capability | G4 必须做“知道路径/同 UID”恶意负例（G4-D-15）并审计 Admission/epoch/replay；**不得**声称已有 per-run OS 身份 | **否** |
| `D3-P2-a..d` | real-DSH same-claim 未证；C09 Broker 只 SIGSTOP 不重启；C12 不接新 admission；C07 非并发双流 | UNVERIFIED / 接受 | 不得外推“Broker 进程级 crash 恢复”“持续接单稳定性”“并发 Provider 流” | **否** |
| `OPS-P2-a..d` | OCI 4 deselect/7 skip；Host 2 项 host-only 环境失败；Node 测试在 Host；launcher cleanup 早失败计数 | 接受（环境） | 报告不得写“全绿”；OCI 为权威 | **否** |
| `ENV-P2-a` | 跑 OCI 会在 rootfs 生成空 `/evidence` 挂载点，下次 preflight 前须删除 | 已知处理流程 | 本轮未启容器 ⇒ 未产生 | 记录 |

**明确声明**：本轮继续 G4-00 无 Key 工程**不构成**对以上任一 P2 的批准、接受或风险签收；`G4-H-05`（维护者签收 P2）仍 `BLOCKED`。

---

## 9. G4-00-09 — 实际 Tool Registry 发现可行性（供 G4-B）

### 9.1 探测方法与结果

| 探测 | 命令（`env -i`，无 proxy） | 结果 |
|---|---|---|
| Python SDK 是否有 registry/tool API | `grep -rni "registry\|tool_schema\|list_tools" deps/deepseek_harness/*.py` | **0 命中**；SDK 仅暴露 `DeepSeekHarness`/`Session.run`/`start_session`/`resume_session`，无工具枚举 |
| runtime CLI 顶层 | `dsh --help` | 有 `--dump-config`、`--dump-config-schema`、`--dump-default-config`、`--patch`；**没有** tool/registry 子命令 |
| 组合 profile 导出 | `dsh --profile headless --dump-default-config` | exit 0，**101** 个 Cordis entry（`probes/headless-default-config.yml`）；`web` profile 为 1288 行 / 299 plugin entry |
| entry-list JSON Schema | `dsh --profile headless --dump-config-schema` | exit 0，643,872 B（`probes/headless-schema.json`）；schema 描述的是 **Cordis entry list**，不是 tool schema |
| 无 profile 调用 | `--dump-config-schema` | exit 1，`error: --profile <name> is required` |

### 9.2 结论：`UNVERIFIED`（权威 merged registry 不可导出）

- DSH **0.2.2-rc.2 不存在**“权威 merged tool registry / tool JSON Schema”导出 API。`--dump-config*` 导出的是**插件条目组合（Cordis entry list）**，且其中大量 `disabled:` 是 `!!js` 表达式（绑定进程序列化阶段求值），**静态 dump ≠ 运行时实际注册表**。
- 实测 `headless` 默认层就包含 `tool-bash`（Linux 下启用）、`tool-fs`、`tool-fs-search`、`tool-web`、`tool-skill`、`tool-subagent*`、`tool-workflow`、`tool-agent-team`、`tool-executor-native` 等 —— **“默认只有 `skill_lookup`”是错误假设**。
- Candidate stage 侧有书面 overlay：`candidate/config/bridge.patch.yml`（禁用 `tool-fs`/`tool-working-directory`/`terminal-bash`/`persistent-bash`/`jobs`/`pty`/`subprocess`/`compaction-basic`/`llm-deepseek`/`session-log-deepseek` 等，仅插入 bridge provider 与 `offline-public-skill`），且使用 `@deepseek-ai/dsh-sdk-minimal` 的**完整 Cordis 树**（不叠加 `dsh-base`）——但**这只是 L0 配置声明，不是 L1 运行时注册表证据**。

### 9.3 给 G4-B 的强制兜底要求（不可省略）

1. `actual_tools` 必须来自 **L1 运行时观测**（真实 Candidate 进程内 tool 注册/分发事件），否则该项只能标 `UNVERIFIED`，**不得**写 `registry=skill_lookup only`。
2. 无论 registry 是否可观测，Controller 侧必须实施**严格 Tool Schema + 发送白名单**：未在 Admission 中批准的 tool 名/schema 一律拒绝，且该拒绝必须发生在 Reserve/Claim **之前**。
3. 必须对“DSH 自动 compaction / summarization / judge / file / multimodal / fallback”逐项证明**不产生额外 Provider 调用**；不能证明的，必须有 per-dispatch Reserve/Claim 兜底 + 负例。
4. `--dump-default-config` 会在 `$DSH_HOME/profiles/` 物化 profile 模板（本轮落在 `artifacts/g4/baseline/probes/dshhome`，52 KB，gitignored）；G4-B 若重复该探针，必须用隔离 `HOME`/`DSH_HOME` 并记录副作用。

---

## 10. G4-00-10 — 基础回归与静态检查

| 检查 | 命令要点 | 结果 | exit | UTC | 日志 |
|---|---|---|---|---|---|
| 基础回归 | `python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3c tests/integration/g3d tests/integration/g3_bridge tests/unit/security/test_gates.py` | **299 passed in 63.65s** | **0** | 2026-11-18T15:35:23Z | `logs/regression-host.log` |
| 安全隔离集（补强） | `… tests/unit/security tests/integration/sandbox/test_live_controller_no_key.py tests/integration/sandbox/test_egress_boundary.py` | **165 passed, 1 failed in 41.30s** | **1** | 2026-11-18T15:38:22Z | `logs/security-isolation.log` |
| ruff（pinned `deps/bin/ruff 0.17.5`） | `ruff check src scripts tests --no-cache` | `src/` **All checks passed**；`scripts/` 4 项既有告警 | **1** | 2026-11-18T15:41:23Z | `logs/ruff.log`、`logs/ruff-src.log` |
| ruff（repo-wide） | `ruff check . --no-cache` | 37 项（绝大多数在 `spikes/`），**src/tests 0** | 1 | 2026-11-18T15:41:23Z | — |

**唯一失败项的定性**：`tests/integration/sandbox/test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked`。

```text
assert cli.returncode == 3
E  assert 1 == 3
E  ModuleNotFoundError: No module named 'autoteacher_m0'
```

原因：该用例以**硬编码容器路径**启动子进程（`PYTHONPATH=/project/src:/deps`、`HOME=/work`），在宿主上必然 import 失败 → exit 1。**不是安全回归**：同一断言在本轮独立复算中以正确 `PYTHONPATH` 执行得到 **exit 3 / BLOCKED**（§4 N5–N9），且该用例在锁定 OCI 内历史通过（`docs/E5_PRELIVE_NO_KEY_REPORT.md:24`，104 passed / 1 skipped）。此现象与 G3-D 独立复核已登记的 **`OPS-P2-b`（host-only 环境失败：子进程 PYTHONPATH）** 属同一类，本轮**未修改测试**去“修绿”。

ruff 的 4 项**全部是历史脚本的既有告警**（`scripts/g3b/build_packet.py:26,586,587`、`scripts/g3c/build_packet.py:27`；F401/F541），本轮按约束**未修**（不改脚本），也不影响产品面；`src/`、新增 `scripts/g3d/build_packet.py` 均干净。

---

## 11. STOP 条件逐项评估

| STOP 条件（任务书 §3.3 / §10） | 观测 | 判定 |
|---|---|---|
| 环境 hash 漂移且不能定位 | rootfs/deps/stage/manifest/runtime **5/5 一致**，0 drift | **未触发** |
| Stage 加载旧 G3-C 源码 | 10/10 容器证据 = `cf40c6b` blob = stage 副本；`attempts.py` ≠ 旧 `33017e75…` | **未触发** |
| Candidate 可写 state | Candidate mountinfo **无 `/work/state`**；D2-01/02/03 全 `ENOENT/EROFS` | **未触发** |
| 旧绕过重新成立 | D2 四类全拒绝（引用证据） | **未触发** |
| Runtime 有网络 | 全容器 `--network none`；`AF_INET` `EACCES`；本地探针 0 次外连 | **未触发** |
| LiveGate 非 BLOCKED | `BLOCKED`（含“证据全满足”仍只剩外部边界一条） | **未触发** |
| 权限异常 | socket `0660 root:2000`；caps 全 0；no-new-privs=1；两主体 UID 不同 | **未触发** |
| 凭据痕迹泄漏 | 0 key-like env 名、0 `.env`、0 扫描命中、0 私钥块 | **未触发** |
| `run_live.sh` 非 exit 3 / CLI 可放行 | `run_live.sh` exit 3；5 个 CLI（含 env/Markdown 旁路）变体全 exit 3 | **未触发** |
| 真实 Key / 外部 HTTP / 计费发送 | 0 / 0 / 0 | **未触发** |
| Candidate 读写 Approval/Revocation/Key/Broker | 无挂载 + 协议拒绝（D2 证据） | **未触发** |

**结论：G4-00 无 STOP，可继续 G4-A/G4-B（无 Key 范围）。**

---

## 12. 对 G4-A / G4-B 的前置结论（只给前置，不实现）

### 12.1 G4-A（Trusted Approval Contract，无真密钥）

1. **复用**：`authorization.py`（448 行）+ `ed25519.py` 已具备 schema/绑定/过期/撤销/verify 能力，**不需要**新建第二套授权格式（任务书 §4.1）。
2. **必须补的组合缺口**：
   - `Tested in isolation ≠ wired`：`load_execution_authorization` 的唯一生产调用点是 `TrustedLiveController.authorization_decision`（inspect-only）。G4-A 必须给出**组合调用**证据，并保持“签名有效 ≠ 可计费发送”的两列结论（`signature_valid` / `billable_send_authorized` 分开写）。
   - `TrustedLiveController` 的 `expected_budget` 是**代码常量**（`$0.20 / $10 / 50`）；`config/budgets.yaml` 在全仓**没有任何代码解析**（唯一出现是 `live_controller.py:41-42` 的注释）。G4-A 需说明该常量的权威来源、以及“配置改了但常量没改”如何被发现。
   - `assert_live_entrypoints_blocked` 是**文本级审计**（检查脚本含 `exit 3`、adapter 含 `_require_live_authorization`），不能替代行为测试。
3. **已有可用负例素材**：N10 证明“repo 内 Markdown/JSON 一律拒绝（必须位于仓库之外）”；`tests/unit/security/test_authorization.py`(22) 覆盖重复 key/类型/撤销/过期；G4-A 应在此基础上做 A02–A11，而不是重写。
4. **禁止**：不改 `gates.py` 为放行、不改 `run_live.sh`、不给 `HarnessAdapter` 任何 allow 分支。

### 12.2 G4-B（Frozen Inventory & Actual Registry）

1. **静态清单可做**：`src/tests/config/plugins` 子树哈希、`cf40c6b` blob、stage manifest（`head_at_build=cf40c6b`、`product_src_identical_to_base=true`）、`rootfs/deps` canonical 均已就绪，可直接进 `manifest.json`。
2. **Registry 是硬缺口**：见 §9 —— **无权威 merged registry 导出**；必须 `UNVERIFIED` + Controller 严格 schema/白名单兜底，**不得**伪造 `registry=skill_lookup only`。
3. **默认 profile 并非最小**：`headless` 默认层含 `tool-bash`/`tool-fs`/`tool-web`/`tool-subagent*`/`tool-workflow`；Candidate 之所以“看起来只有 `skill_lookup`”来自 `sdk-minimal` 完整树 + `bridge.patch.yml` overlay，需在**运行时**证明这些 `disabled` 真的生效（`!!js` 表达式）。B04/B07/B08 因此是 P0/P1 级。
4. **附加可观测面**：DSH `--dump-config` 会物化 profile 到 `$DSH_HOME/profiles`（§9.3-4）；B10 “跨 Worker 共享 Stage 不污染 canonical”必须把该副作用计入。
5. **配置常量提示**：`live_controller.py` 的默认 image digest `62d3569e…` 与本地 `localhost/autoteacher-local-oci:candidate` **当前一致**；若镜像重建，该常量与 `docs/E5_PRELIVE_NO_KEY_REPORT.md` 需同步，否则 G4-B 的 manifest 会与运行时漂移。

---

## 13. 证据清单与复现

| 证据 | 路径（`artifacts/` 已 gitignore） |
|---|---|
| 身份/漂移 | `artifacts/g4/baseline/identity.json` |
| 环境/canonical/版本 | `artifacts/g4/baseline/env.json` |
| OS principal | `artifacts/g4/baseline/os-principal.json` |
| 模块加载（容器 + 宿主） | `artifacts/g4/baseline/module-container-evidence.json`、`module-host-import.json` |
| 组件四列 | `artifacts/g4/baseline/module-map.json` |
| Live 负例汇总 | `artifacts/g4/baseline/gate.json`、`negative-summary.json` |
| 负例原始输出 | `gate-negatives.json`、`entrypoint-negatives.json`、`approval-path-negative.json`、`adapter-negatives.json`、`entrypoint-audit.json`、`network-guard.json` |
| 命令台账 | `artifacts/g4/baseline/commands.jsonl`（17 行，argv/exit/UTC/log） |
| 日志 | `artifacts/g4/baseline/logs/{regression-host,security-isolation,ruff,ruff-src,secret-scan-history,secret-scan-nohistory}.*` |
| DSH 探针输出 | `artifacts/g4/baseline/probes/{headless-default-config.yml,web-default-config.yml,headless-schema.json}` |
| 探针脚本（可重跑） | `artifacts/g4/baseline/probes/g4_00_probe.py`、`g4_00_artifacts.py` |

复现要点：

```bash
export PYTHONDONTWRITEBYTECODE=1
PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B \
  artifacts/g4/baseline/probes/g4_00_probe.py
PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B \
  artifacts/g4/baseline/probes/g4_00_artifacts.py
PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest -q \
  -p no:cacheprovider tests/integration/g3c tests/integration/g3d \
  tests/integration/g3_bridge tests/unit/security/test_gates.py
```

基线内容哈希（用于交叉核对）：

- 本文件 `sha256`：见提交说明与 Lead 报告（`docs/M0_G4_00_BASELINE.md`）。
- `artifacts/g4/baseline/` 汇总：由 `module-map.json` 与 `identity.json` 的 `utc` 字段锚定（2026-11-18T15:41:49Z–15:41:50Z）。

---

## 14. 观察项（非阻断，供后续 Gate 处理）

| ID | 观察 | 建议 |
|---|---|---|
| OBS-1 | `scripts/g3d/build_packet.py` 在代码冻结后由 `docs:`/`fix:` 主题提交引入 | G4-E 打包时在 manifest 显式登记该文件与来源，避免“冻结后无记录变更”的审计歧义 |
| OBS-2 | 宿主 `dsh`（0.2.1-rc.2）启动即构造 `EnvHttpProxyAgent` | 所有 DSH 探测/启动一律 `env -i` 或显式清空 proxy 变量；`docs/M0_G3C_G0_BASELINE.md:102` 的“不要用系统 dsh”需连带提醒 proxy 行为 |
| OBS-3 | `headless` 默认层含 `tool-bash` 等执行类工具 | G4-B 必须证明 overlay 生效（运行时），不能只看 YAML |
| OBS-4 | `--dump-config` 会物化 `$DSH_HOME/profiles` | 用隔离 HOME/DSH_HOME，并记录副作用 |
| OBS-5 | ruff 4 项既有告警（`scripts/g3b`/`g3c`） | 不属 G4 范围；若后续要“repo-wide 全绿”需单独授权修脚本 |
| OBS-6 | `test_live_controller_no_key.py` 含容器硬编码路径 | G4-D 若需宿主重跑，应在**测试层**参数化（需单独授权改测试），本轮不改 |

---

## 15. 声明

- 本报告只覆盖 **G4-00 基线/能力测绘**，不构成 G4-A/B/C/D/E 任何交付，不构成 G4 PASS。
- **`E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT`** 不变；`G4-H` 六项仍 `BLOCKED`；`G5` 不得启动。
- 全程 0 真实 Key、0 真实 Provider/模型、0 外部 HTTP/TCP、0 容器启动、0 `podman pull`；`podman ps -a` 空。
- 本轮未读取任何宿主敏感目录（`/root/.dsh`、`/root/.config`、`~/.ssh` 等）；未输出任何 Secret 值（仅名与计数）。
- 下一步：**STOP**，等待 Lead/维护者审阅后再进入 G4-A/B。
