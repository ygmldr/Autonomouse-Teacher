# M0 G3-D1 — 实施计划（可执行草案；不含代码改动）

> **状态**：`D1_PLAN_ONLY_PENDING_MAINTAINER_AUTHORIZATION`。本文件是 D1 的实施计划，**不是**已实施、不是 G3-D PASS、不是 D2/D3 证据。
> **日期**：2026-11-17 ｜ **工作树**：`/root/Autonomous Teacher` ｜ **执行者（授权后）**：D1 Implementation Agent；Lead 只编排/审计。
> **代码基线**：`b2f6af054555705192c4e1ae3019a68078764736`（G3-C PR1 fix）；**docs/归档基线**：`fff36232687afb779befb49fb6e2a10cedbcb7fd`（HEAD）。现场已核对 `git diff --stat b2f6af0..HEAD -- src tests` 为空，因此“代码用 `b2f6af0`、docs 用 `fff3623`”成立。
> **设计依据**：`docs/M0_G3D_OS_BOUNDARY_DESIGN.md`（1326 行，sha256 `2cf03c99…`）、`docs/M0_G3D_D0_SIGNOFF.md`（本任务签核草案）、`docs/REVIEW_G3C_INDEPENDENT_v2.md`。
> **硬约束**：无真实 Key/模型/外部付费 HTTP/Live；不修改 `gates.py`/`dsh_adapter.py`/`run_live.sh`/DSH 核心；不改 G3-C 协议字段/语义；D1 必须从未被污染的冻结基线开始。**本文件不启动任何容器、不实现任何代码、不 commit/push。**

---

## 0. 目标、出口与不做

### 0.1 目标

在 G3-C 冻结代码上建立一个**真实双 Principal**的一次性运行层：

1. **D1**：trusted 容器（host uid 0）与 candidate 容器（host uid 65534，嵌套 userns）通过唯一 UDS 完成真实 DSH **Echo / Tool / Resume**；candidate 只有 group 2000 的 socket 连接权，没有 state/DB/Policy/Admission/Receipt/Key/launcher 控制面。
2. **D2**：从**真实 candidate 身份/容器**执行 D2-01..D2-12，记录真实 errno/协议拒绝与前后 hash，复现旧 Reviewer 四个绕过并证明被内核/协议拒绝。
3. **D3**：双 Principal 下的正向组合 + 跨主体 crash/cancel/cleanup + 无残余 + 同 SHA 复现；提交 D Packet，交独立 D Reviewer 后 **STOP**。

### 0.2 出口（D1 完成定义）

- `BridgeServer` 的 additive socket 变更合入 D1 分支，默认行为与 G3-C 旧测试完全一致；
- candidate 能通过 `LlmAdapter` 连接 `/work/g3b/bridge.sock`，trusted 在 `on_ready` 后写 ready；
- D1 正向 Echo/Tool/Resume 至少各 1 次成功，Broker/Attempt/Receipt/Fake 链一致；
- `$RUN/ipc` 2750 root:2000、socket 0770 root:2000、peercred uid 65534/gid 65534 有现场证据；
- 清理后 `podman ps -a` 空、无 socket/孤儿、rootfs/deps canonical 不变；
- 无 Key/无外网/无 LiveGate 解除；
- 以上全部由 **D1 证据**支撑，不以“代码已改”代替运行证据。

### 0.3 明确不做

- 不实现真实 Provider/Key/模型/外部 HTTP/DNS；不做 G4/G5/Live。
- 不修改 `src/autoteacher_m0/security/gates.py`、`dsh_adapter.py`、`scripts/run_live.sh`、DSH 核心、G3-C 协议/错误码/状态机。
- 不把 socket 改成 0666、不让 candidate 可写 IPC 目录、不让 candidate 与 trusted 同 UID/同 user namespace。
- 不用 mock/同 UID/chmod 表/日志文字冒充内核拒绝；环境不满足即 `BLOCKED_NEEDS_ENVIRONMENT`。
- 不在本计划阶段 commit/push/启动容器。

---

## 1. 基线与分支/提交序列

### 1.1 基线冻结

D1 实施第一步只做只读冻结，不做代码：

```bash
cd "/root/Autonomous Teacher"
test "$(git rev-parse HEAD)" = "fff36232687afb779befb49fb6e2a10cedbcb7fd"
test -z "$(git status --porcelain)"
test -z "$(git diff b2f6af0..HEAD -- src tests)"
test "$(git rev-parse origin/main)" = "$(git rev-parse HEAD)"
sha256sum docs/M0_G3D_OS_BOUNDARY_DESIGN.md   # 2cf03c99…
tar -C artifacts/security/rootfs --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
tar -C artifacts/foundation/deps --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
podman ps -a
```

期望：HEAD `fff3623`、clean、`src/tests` 与 `b2f6af0` 无 diff、rootfs `25491e45…`、deps `e07729d7…`、`podman ps -a` 空。任何一项不符 → **STOP**（`PREFLIGHT_IDENTITY`），不得“先改再查”。若工作树出现其它 Agent 的未跟踪 docs/artifacts，D1 **不得删除、移动或提交**它们；等 Lead 归档/确认后再重跑 preflight。

### 1.2 分支与 commit 序列（授权后）

从 `fff3623` 新建分支 `g3d/impl`（不要从 `b2f6af0` 分支，否则 docs/归档缺失；代码基线仍以 `b2f6af0` 为准，提交前再次断言 `src/tests` 未漂移）。

| 顺序 | commit 主题（建议） | 内容 | 停止点 |
|---|---|---|---|
| **D1-0** | `chore(g3d): freeze baseline`（可空提交/仅记录） | `artifacts/g3d/env/{identity,canonical-pre,podman-info}.json`；不碰产品代码 | Lead 确认身份/环境 |
| **D1-1** | `feat(g3d): additive bridge socket boundary knobs` | `ipc_server.py`、`controller.py`、host 测试；默认 0600 回归 | Lead 审 diff + host 测试；失败即停 |
| **D1-2** | `feat(g3d): dual-principal launcher and entries` | `scripts/g3d/*`、`config/g3d/*`、stage entrypoints；无产品协议变更 | Lead 审 argv/挂载/清理契约 |
| **D1-3** | `test(g3d): D1 positive evidence` | D1 runner + Echo/Tool/Resume 证据；不把 evidence 提交（`artifacts/` gitignored） | Lead 审正向；失败先修 D1，不进 D2 |
| **D2-1** | `test(g3d): D2 candidate attack matrix` | D2 probes/runner；D2-01..D2-12 证据 | Lead 审高风险；任何 FAIL/PARTIAL 停 |
| **D3-1** | `test(g3d): D3 combined regression` | D3 W1..W10/无残余/复现 | Lead 审 D3；提交 D Packet |
| **D-DOC** | `docs(g3d): report, review request, matrix` | `docs/M0_G3D_IMPLEMENTATION_REPORT.md`、`docs/M0_G3D_REVIEW_REQUEST.md`、矩阵 | **STOP** 等独立 D Reviewer |

> 每个 commit 只包含该步文件；**不把 evidence/Packet 与产品代码混提交**。`artifacts/` 被 `.gitignore` 忽略，D Packet 由后续 builder 归档；Lead 统一处理合入/归档。

### 1.3 G3-C 复核 v2 的 P2 残余对 D1 的约束

| P2 | 对 D1 的约束 |
|---|---|
| P2-1 Packet/stage 示例使用 e6fde1c 旧源码 | **不复用 `artifacts/g3c/stage` 的 `stage/src`**；D1 trusted stage 从当前 `b2f6af0` 源码重建，记录 `stage_hash` 与 `attempts.py`/`controller.py` hash，断言含 PR1 的 `bridge.sock.lock`/singleton 行为 |
| P2-2 guard-invalid 表述不精确 | D3 Guard 缺失/无效只记录实际 controller exit、DSH error、attempt/receipt 数，不沿用旧文字结论 |
| P2-3 证据计数陈旧 | D1/D2/D3 矩阵计数从磁盘证据重新生成，不复制 G3-C 的 51/55/75/77 等历史计数 |
| P2-4 压力轮次无 JSON/日志 | 只把 D1 自己产生的轮次写入证据；不引用无法复核的“另 3×20 轮”文字 |
| P2-5 矩阵 `impl_sha` 与 trace 批次不一致 | 每个 D case 同时记录 `base_sha`/`impl_sha`/`test_sha`/`stage_hash`/`commands.jsonl`，明确该 trace 由哪次 D1 运行产生 |

---

## 2. 文件清单与最小 diff 轮廓（不含实现）

### 2.1 产品代码（仅 2 个文件，additive）

#### A. `src/autoteacher_m0/bridge/ipc_server.py`（当前 521 行）

| 位置 | 变更 |
|---|---|
| `:127-131` `BridgeServer.__init__` | 追加 5 个 keyword-only 参数（`socket_mode`/`socket_gid`/`on_ready`/`peer_uid`/`peer_gids`），精确签名见下方代码块 |
| `:132-149` 校验/赋值 | mode 只允许 `{0o600, 0o660, 0o770}`；拒绝 0666；gid/uid 非负 int；`peer_gids` 非空 int tuple 且仅当 `peer_uid` 配置时允许；`on_ready` 必须 callable；`peer_uid` 配置时 `SO_PEERCRED` 必须存在（否则启动失败）；保存字段 |
| `:178-181` `serve_forever` | `bind` → `os.chmod(path, socket_mode)` → 仅当 `socket_gid is not None` 时 `os.chown(path, -1, socket_gid)` → `listen` → `settimeout` → `on_ready()`（一次，accept 前） |
| `:255-268` `_connection_thread` | 在 `handle_connection` 前调用 `_authorize_peer(sock)`；失败记录 `PEER_REJECTED`、关闭、返回；不发送协议 error（错误码集合无 peer-auth 码） |
| `:280-283` 附近 | 新增 `_authorize_peer`：`struct.unpack("3i", getsockopt(SOL_SOCKET, SO_PEERCRED, 12))`；校验 uid / 可选 gid；忽略 pid（跨 pidns 为 0）；`getsockopt` 失败也拒绝 |

新增参数精确签名（仅轮廓，不实现）：

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

**不改变**：`handle_connection` 的 framing/ack/seq/chunk/finish/error 语义；`FrameReader`；连接/帧/总量上限；`shutdown`/finally unlink；协议常量。默认参数下行为与当前逐字节等价（除新增校验分支不触发）。

#### B. `src/autoteacher_m0/bridge/controller.py`（当前 1640 行）

| 位置 | 变更 |
|---|---|
| `:1550` `main` | 签名追加 keyword-only `on_ready`（默认 `None`）；`python -m` 调用不受影响 |
| `:1555-1560` | 可选配置集合加入 `socket_mode`/`socket_gid`/`peer_uid`/`peer_gids`；仍拒绝未知字段；做类型/范围校验 |
| `:1608` | `BridgeServer(..., socket_mode=..., socket_gid=..., peer_uid=..., peer_gids=..., on_ready=on_ready)` |
| `:1578-1596` | 不改 admission/controller 的 `expected_uid=65534` 语义；**不要**把 `expected_uid` 与 `peer_uid` 合并 |

**不改**：`_prepare_checked`、`handle_envelope`、`begin_attempt`、`reconcile_on_startup`、cancel、streaming、Fake/Broker 逻辑、退出码 3/4/5。

#### C. 明确不改的文件

`src/autoteacher_m0/security/{gates.py,egress.py}`、`src/autoteacher_m0/accounting/*`、`src/autoteacher_m0/bridge/{protocol.py,admission.py,attempts.py,broker_client.py,fake_backend.py}`、`dsh_adapter.py`、`scripts/run_live.sh`、DSH 核心/plugins。若 D1 发现必须改，**STOP** 回 Lead/维护者重新签核。

### 2.2 D1 启动器/入口/配置（新增）

```text
scripts/g3d/
  launch.py                  # host launcher：preflight/建目录/生成配置/起停容器/收集/清理
  lib_g3d.py                 # hash_tree、run_cmd、commands.jsonl、容器名、证据 helper
  build_stage.py             # 在固定 rootfs 内构建 adapter + 组装 candidate/trusted stage
  stage/
    trusted_entry.py         # umask 007；校验目录；controller.main(on_ready=...)
    candidate_entry.py       # 断言 principal；DSH Echo/Tool/Resume/hold/crash
  probes/
    candidate_probe.py       # D2 用 stdlib 探针；只读挂载到 /probe-attacks，不进入 candidate stage
  d2_attacks.py              # host 编排 D2-01..D2-12；每条从 candidate 容器执行
  d3_regression.py           # host 编排 D3 W1..W10 + 无残余/复现
  templates/
    admission.template.json
    broker.template.json
    controller.template.json
config/g3d/
  candidate/etc/{passwd,group}
  trusted/etc/{passwd,group}
  candidate/config/bridge.patch.yml   # 路径由 /probe 改为 /project
```

> 也可以把 `templates/` 放 `config/g3d/`；关键是**只新增 D 专用文件**，不复用/修改 G3-C stage 的只读副本。`artifacts/g3d/` 只放运行产物，不提交。

### 2.3 测试

```text
tests/integration/g3d/
  test_socket_boundary.py      # host：默认 0600；0770/gid 2000；on_ready 恰一次；
                               # peer uid 65534 接受 / uid 0 拒绝且无协议帧；
                               # 0666 配置拒绝；SO_PEERCRED 缺失 fail-closed
  test_controller_config.py    # host：controller.main 接受新可选字段；
                               # 未知字段/坏类型仍 CONFIG_INVALID；expected_uid 仍 65534
  test_launcher_contract.py    # host：argv/挂载/权限/清理计划的纯函数测试；
                               # 不启动容器
```

D1 运行证据由 `scripts/g3d/launch.py` 产生，不依赖 pytest 通过来冒充容器证据。原 `tests/integration/g3_bridge`、`tests/integration/g3c` 必须全绿；旧测试不得因默认参数变化而改。

### 2.4 Stage 布局

```text
$STAGE/
  candidate/
    run/candidate_entry.py
    config/bridge.patch.yml          # 只引用 /project/...，不含 /probe
    runtime/bridge/lib/index.js      # 由 build-adapter.mjs 构建
    runtime/bridge/package.json
    runtime/skill/lib/index.js
    native/guard/lib/index.js        # D3 Guard 场景需要
    native-cache/  pkg-cache/  node_modules/
    fixtures/skills.json  fixtures/capture-tools.json
    etc/passwd  etc/group
  trusted/
    run/trusted_entry.py
    src/autoteacher_m0/...           # controller/broker/admission/attempts/fake/security/accounting
    fake/fake_provider.py
    etc/passwd  etc/group
```

**candidate stage 排除（构建后必须 `find`/`grep` 断言）**：
`autoteacher_m0/accounting/`、`bridge/{controller,admission,attempts,broker_client,fake_backend}.py`、`fake/`、`config/{admission,broker,controller}.json`、任何 `*.sqlite*`、WAL/SHM、receipts、Key、launcher 脚本、repo `.git`、`src/` 原始路径。
**trusted stage 排除**：candidate session、candidate stage、repo、宿主 home、Podman socket、Key；`/output` 只挂 trusted。

**构建方式（复用 G3-C 的已验证机制，不修改 G3-C stage）**：
- 在固定 rootfs 内以 `--network none` 运行 `scripts/g3c/build-adapter.mjs`，输出到 `artifacts/g3d/build`；记录 `build-meta.json` 与 adapter `lib/index.js` hash。
- `build_stage.py` 复制 `spikes/g3b-trusted-bridge/{config/bridge.patch.yml,fake/fake_provider.py}`、G3-C 已验证的 runtime/native/node_modules/fixtures 资产、当前 `src/autoteacher_m0`（只到 trusted）；重写 patch 的 `/probe/...` 为 `/project/...`。从 `artifacts/g3c/stage` 只复制**不含项目源码**的 DSH/runtime 资产，并断言没有 `src/autoteacher_m0`、`run_c3/worker_c3.py`、controller/fake 旧副本。
- **不要复用 `artifacts/g3c/stage` 作为 D1 源码**（G3-C v2 P2-1：旧 stage 的 `stage/src` 是 e6fde1c 批次，不含 PR1 修复）。D1 必须从当前冻结 `src` 重新组装 trusted stage，并记录 `stage_hash`。
- `chmod -R a+rX`；passwd/group 0444；stage 不写回仓库。

---

## 3. 启动器契约

### 3.1 预检（任一失败即 STOP）

```text
[ ] HEAD == fff3623；工作树 clean；src/tests 与 b2f6af0 无 diff
[ ] rootfs == 25491e45…；deps == e07729d7…
[ ] podman 4.9.3 rootful；crun；cgroup v2；pids/memory 可用
[ ] user namespace/--uidmap 可用；SO_PEERCRED 可用；gid 2000 未被占用
[ ] podman ps -a 空；无 at-g3d-* 容器；无 stale $RUN/ipc/bridge.sock
[ ] env 无 *KEY*/*TOKEN*/*SECRET*；无 .env；未调用 LiveGate 解锁
[ ] artifacts/g3d 不存在或为空；并发锁 artifacts/g3d/.g3d.lock 可获取
```

环境探针必须是**真实最小容器**（rootfs + `--uidmap 0:65534:1` + `--network none` + `--read-only-tmpfs=false` + `--cap-drop ALL`），只打印 `uid_map`/`gid_map`/`getgroups`/peercred 能力；不跑 DSH、不读 Key。失败 → `exit 3 BLOCKED_NEEDS_ENVIRONMENT`，不 mock。

### 3.2 `$RUN` 与权限

```text
$RUN = artifacts/g3d/runs/<run_id>/
  state/                   0700 root:root
  ipc/                     2750 root:2000
  candidate-session/       0700 65534:65534
  evidence/                0700 root:root
  logs/                    0700 root:root
```

`run_id` 建议 `YYYYMMDDTHHMMSSZ-<case>-<8hex>`；容器名 `at-g3d-{trusted,candidate,attack}-<run_id>`。每次 run 独立 state；不重用上一次的 DB/socket/attempt。

#### 3.2.1 Launcher 生成的配置文件（trusted 侧）

| 文件 | 关键字段 | mode |
|---|---|---|
| `$RUN/state/admission.json` | `schema=m0.g3b.admission.v1`；`synthetic=true`；route `offline-test-only-g3b/fixture-bridge-v1`；`launcher.uid=65534`、`container=true`、随机 `admission_nonce`；`limits.max_attempts=1`；`fake_scenario` 按用例；`expiry_utc` +1h | 0400 root |
| `$RUN/state/broker.json` | synthetic policy；DB/日志路径为容器内 `/work/state/...`（host `$RUN/state/...`）；无真实 provider/Key | 0400 root |
| `$RUN/state/controller.json` | 见 §3.2.1 下方精确 JSON；`expected_uid=65534`、`socket_mode=504`、`socket_gid=null`、`peer_uid=65534`、`peer_gids=[65534]` | 0400 root |
| `$RUN/state/{ready}` | trusted `on_ready` 写 pid/UTC/instance；launcher 等它 | 0600 root |
| `$STAGE/*/etc/passwd`、`group` | root/nobody/socket 2000；candidate root home `/work/session`，trusted `/work` | 0444 |

> admission 的 `launcher.uid` 是 **Controller 期望的容器 peer uid**，必须 65534；不是 host launcher 的 0。D1 生成后要 `grep` 断言没有 `"uid": 0`。

controller 配置精确形状（与 `docs/M0_G3D_D0_SIGNOFF.md` §2.1.2 一致）：

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

### 3.3 Trusted argv（D0 §4.2 基线，逐项固定）

```bash
ROOTFS="/root/Autonomous Teacher/artifacts/security/rootfs"
DEPS="/root/Autonomous Teacher/artifacts/foundation/deps"
RUN="/root/Autonomous Teacher/artifacts/g3d/runs/$RUN_ID"
STAGE="/root/Autonomous Teacher/artifacts/g3d/stage/$RUN_ID"
TRUSTED="at-g3d-trusted-$RUN_ID"

podman run -d --name "$TRUSTED" --rootfs --timeout 300 \
  --userns=host --user 0:0 \
  --network none --http-proxy=false --unsetenv-all --no-hosts \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --memory-swap 1g --cpus 1 \
  --ulimit nofile=4096:4096 \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/project/src:/deps \
  --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --mount "type=bind,src=$STAGE/trusted,dst=/project,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$STAGE/trusted/etc/passwd,dst=/etc/passwd,ro=true" \
  --mount "type=bind,src=$STAGE/trusted/etc/group,dst=/etc/group,ro=true" \
  --mount "type=bind,src=$RUN/state,dst=/work/state,rw=true" \
  --mount "type=bind,src=$RUN/ipc,dst=/work/g3b,rw=true" \
  --mount "type=bind,src=$RUN/evidence,dst=/output,rw=true" \
  --workdir /project --systemd=false \
  "$ROOTFS" /opt/python/bin/python3.11 -B /project/run/trusted_entry.py \
    --config /work/state/controller.json
```

- `--systemd=false` 与 G3-C 容器运行一致；`--timeout 300` 为 D0 草案参数；D1 preflight 记录实际 `podman run` 返回与版本。
- `--cap-drop ALL` 下 **不要**期望 `chown`；socket gid 由 `$RUN/ipc` 2750 root:2000 的 setgid 继承。
- trusted 不挂 candidate session/candidate stage/repo/宿主 home/Podman socket/Key。

### 3.4 Candidate argv（D0 §4.3 基线；精确 UID/GID 映射）

```bash
CAND="at-g3d-candidate-$RUN_ID"

podman run -d --name "$CAND" --rootfs --timeout 300 \
  --uidmap 0:65534:1 \
  --gidmap 0:65534:1 --gidmap 2000:2000:1 \
  --user 0:0 --group-add 2000 \
  --network none --http-proxy=false --unsetenv-all --no-hosts \
  --read-only --read-only-tmpfs=false --cap-drop ALL \
  --security-opt no-new-privileges \
  --pids-limit 256 --memory 1g --memory-swap 1g --cpus 1 \
  --ulimit nofile=4096:4096 \
  --env PATH=/opt/python/bin:/usr/bin --env HOME=/work/session \
  --env PYTHONPATH=/deps --env PYTHONDONTWRITEBYTECODE=1 \
  --env TMPDIR=/tmp \
  --env DSH_RUNTIME_MODE=exe --env DSH_RESOURCE_CACHE=/work/resources \
  --env NARB_NATIVE_CACHE_DIR=/project/native-cache \
  --env PKG_NATIVE_CACHE_PATH=/project/pkg-cache --env NO_COLOR=1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=128m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=512m,mode=1777 \
  --mount "type=bind,src=$STAGE/candidate,dst=/project,ro=true" \
  --mount "type=bind,src=$DEPS,dst=/deps,ro=true" \
  --mount "type=bind,src=$STAGE/candidate/etc/passwd,dst=/etc/passwd,ro=true" \
  --mount "type=bind,src=$STAGE/candidate/etc/group,dst=/etc/group,ro=true" \
  --mount "type=bind,src=$RUN/candidate-session,dst=/work/session,rw=true" \
  --mount "type=bind,src=$RUN/ipc,dst=/work/g3b,ro=true" \
  --workdir /work/session --systemd=false \
  "$ROOTFS" /opt/python/bin/python3.11 -B /project/run/candidate_entry.py \
    --scenario echo --session g3d-d1-s1
```

**参数敏感性（D0 P-12）**：缺 `--read-only-tmpfs=false` 会 `crun: open run/.containerenv: Permission denied`；缺 synthetic passwd 会让 Node `os.userInfo()` `ENOENT`；D1 必须固定完整 argv，不能临时增删。D1 首次运行先跑最小 `id`/`uid_map` 探针，再加 DSH。

**D2 变体**：D2 的 candidate 容器在相同 argv 基础上额外挂载只读 probe 目录：
`--mount "type=bind,src=$RUN/probes,dst=/probe-attacks,ro=true"`；该目录只含 stdlib 探针，不含 `src/autoteacher_m0`/controller/fake/Key，不进入 candidate stage；D1 正向不挂。资源子用例 `at-g3d-attack-<run>` 另加 `--pids-limit 8 --memory 128m`，其余安全参数相同。

### 3.5 Candidate 入口断言（失败即退出，不进入 DSH）

```text
[ ] os.getuid() == 0（容器 userns 内；宿主 kuid 65534 由 host /proc 证明）
[ ] 2000 in os.getgroups()
[ ] /work/state 不存在；/output 不是 $RUN/evidence 的挂载（rootfs 自带空目录可存在，不可写）；/project/src 不存在
[ ] PYTHONPATH 不含 /project/src；import autoteacher_m0 失败
[ ] /work/g3b 是目录；/work/g3b/bridge.sock 是 S_IFSOCK；
    stat mode == 0770、gid == 2000；不能 unlink/rename（ro 挂载）
[ ] env 无 *KEY*/*TOKEN*/*SECRET*
[ ] 启动 DSH SDK + adapter；不 spawn controller/broker/fake
```

### 3.6 Readiness / health / 启动顺序

1. 启动 trusted（detached）。
2. `trusted_entry`：`umask 007`；校验 `/work/state` 0700 root、`/work/g3b` 2750 root:2000；调用 `controller.main(["--config", ...], on_ready=write_ready)`。
3. `write_ready`（在 `BridgeServer.listen` 之后）：
   - `os.stat("/work/g3b/bridge.sock")`：`S_ISSOCK`、mode `0770`、gid `2000`；
   - 以 `O_WRONLY|O_CREAT|O_TRUNC|O_NOFOLLOW`（0600）写 `/work/state/ready`，内容含 pid/UTC/instance；
   - `fsync` 文件 + 目录；失败则抛异常，server 关闭，trusted 退出非 0。
4. host launcher 等待 `$RUN/state/ready`（≤15 s）；再 `stat` socket 断言 `S_ISSOCK/0770/gid 2000`；检查 trusted `podman inspect` 仍 running；读取 `podman logs`（无 traceback）。
5. **不要**以 host root 连接 socket 做“健康检查”：peer uid 0 会被拒绝，且不代表 candidate。fallback 只用 `ss -xl` 看 LISTEN。
6. 启动 candidate；等待退出/超时；采集证据；停止 candidate 后再停止 trusted。

### 3.7 清理与退出码

**顺序**（`trap EXIT INT TERM` 必须覆盖失败/超时）：

```text
1. podman stop -t 3 "$CAND"（若 running）→ podman rm -f "$CAND"
2. podman stop -t 5 "$TRUSTED" → podman rm -f "$TRUSTED"
3. 仅当 trusted 已停止：`lstat` 确认 `S_ISSOCK` 后 `unlink` `$RUN/ipc/bridge.sock`；再 `lstat` 确认 `bridge.sock.lock` 是普通文件（owner root）后 unlink（controller singleton 不会自己删 lock，必须由 launcher 清理）
4. rmdir "$RUN/ipc"（仅空目录）
5. podman ps -a --filter name=at-g3d- 为空；全局 podman ps -a 为空
6. pgrep -af 'at-g3d|autoteacher_m0.bridge.controller|fake_provider' 为空
7. ss -xl 无 $RUN/ipc/bridge.sock；socket 不存在
8. 重算 rootfs/deps canonical；只删除可证明为空的 Podman 自动 mount target
9. 写 cleanup.json / commands.jsonl；任何清理失败 → 非 0，不写 PASS
```

| exit | 含义 |
|---:|---|
| 0 | 用例按预期完成（正向成功 / 负向真实拒绝） |
| 2 | `PREFLIGHT_IDENTITY`：git/hash/clean 不符 |
| 3 | `BLOCKED_NEEDS_ENVIRONMENT`：userns/uidmap/cgroup/SO_PEERCRED/setgid 不满足 |
| 4 | `STAGE_INVALID`：stage 缺文件/混入 trusted 代码/hash 不符 |
| 5 | `TRUSTED_START_FAILED`：ready 超时/socket 权限不符/controller 退出 |
| 6 | `CANDIDATE_START_FAILED`：principal 断言失败/DSH 启动失败 |
| 7 | `CASE_FAILED`：期望的拒绝未发生，或正向失败 |
| 8 | `CLEANUP_RESIDUAL`：容器/socket/进程/挂载残留 |
| 9 | `EVIDENCE_INTEGRITY`：rootfs/deps 漂移、证据缺失/hash 不符 |
| 10 | `NO_LIVE_VIOLATION`：发现 Key/外网/付费 HTTP/LiveGate 解除 |

---

## 4. 测试矩阵

### 4.1 D1 正向（先做，不先做攻击）

| ID | 场景 | 命令（授权后） | 期望 |
|---|---|---|---|
| **D1-01** | Echo 1 call | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-echo --scenario echo --session g3d-d1-s1` | candidate exit 0；1 reservation OK、1 claim COMPLETED、1 attempt SETTLED、1 receipt、Fake 1；DSH `finish=completed`；usage == receipt；无 Key/HTTP |
| **D1-02** | Tool 两轮 | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-tool --scenario tool --session g3d-d1-s1` | 2 个独立 call/reservation/claim/attempt/receipt；tool result 进入第二轮；无跨 call 复用；Fake 2 |
| **D1-03** | Resume | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-resume --scenario resume --session g3d-d1-s1` | `mode=resume`、turn=2；旧 attempt 不变；新 call 新增；不重复旧 call；Fake 2（1+1） |
| **D1-04** | Principal 证据 | 在 D1-01 运行时采集 | candidate `uid_map=0 65534 1`、`gid_map=0 65534 1/2000 2000 1`；host `/proc/<cand-pid>/status Uid:65534`；trusted Uid 0；socket `S_ISSOCK 0770 gid 2000`；peercred `uid=65534 gid=65534 pid=0`；candidate `mountinfo` 无 state/evidence 挂载、无 `/project/src` |
| **D1-05** | 默认 0600 回归 | host pytest `test_socket_boundary.py` | 不传新参数：socket 0600 root、无 peer 校验；G3-C 旧测试全绿 |
| **D1-06** | 隔离模式 socket | host pytest 覆盖 mode/on_ready/reject/mock；D1-01 容器证据覆盖真实 65534 接受 | `socket_mode=0o770/socket_gid=None/peer_uid=65534/peer_gids=[65534]`：socket 0770 gid 2000；`on_ready` 恰一次；peer uid 0 被关闭；0666 被拒绝 |
| **D1-07** | no-key/no-net | D1-01 环境快照 | env 无 Key；`--network none`；AF_INET/AF_INET6 EPERM；无外部 HTTP/模型；`podman ps -a` 空 |

**D1 证据格式**：每个 case 一个 `case-<id>.json`（见 §5.2），并保存 candidate/trusted `uid_map`、`gid_map`、`mountinfo`、socket `stat`、trusted peercred 日志、DSH events、Broker/Attempt/Receipt 查询、Fake counter、清理快照。

> **Resume 语义**：`D1-03` 必须复用 `D1-02`（或 `D1-01`）的 `$RUN/candidate-session` 与 trusted state（同一 `$RUN`，新 candidate 容器/新 transport_id），不是新建空 session 的独立 run；旧 attempt 行必须保持不变。若 launcher 用新 `$RUN`，必须显式复制 session 并保留旧 DB，否则不构成 Resume 证据。

### 4.2 D2 负向（D2-01..D2-12）

> 统一约定：candidate 容器以 `candidate_entry.py --scenario hold` 保持运行；所有攻击用 `podman exec "$CAND" /opt/python/bin/python3.11 -B /probe-attacks/candidate_probe.py --case <ID>`（`/probe-attacks` 是只读挂载的 D2 probe 目录，**不是** candidate stage）。不得从 host/trusted 执行；不得用 mock client。

| ID | 攻击（candidate 内） | 期望（真实 errno/协议） | 证据 |
|---|---|---|---|
| **D2-01** | 读 `/work/state/broker.sqlite3{,-wal,-shm}`、`/state/broker.sqlite3` | 全部 `ENOENT(2)`；误挂 ro 控制组 `EACCES(13)` | stdout errno；`mountinfo` 无 state；DB/WAL/SHM hash 不变；Broker 行数不变 |
| **D2-02** | 以 `O_RDWR`/`O_CREAT` 打开并写 DB | `ENOENT(2)`；误挂 `EROFS(30)`/`EACCES(13)` | 前后 DB hash、`PRAGMA integrity_check=ok`、reservation 行数、Fake 0 |
| **D2-03** | 读/写 `admission.json`、`broker.json`、`policy.json`、`attempts.sqlite3`、`receipts/`、`received-count.json` | 全部 `ENOENT(2)`；误挂读 `EACCES(13)`、写 `EROFS(30)` | 文件 hash、attempt 行数、receipt 数；candidate stdout 无 admission_id/limits/policy 内容 |
| **D2-04** | `import autoteacher_m0.accounting.broker`；打开 `/project/src/.../broker.py` | `ModuleNotFoundError`（exit 1）；路径 `ENOENT(2)`；`sys.path` 无 `/project/src` | stderr traceback、`sys.path`、candidate 内 `os.walk('/project')` 无 broker/controller/fake |
| **D2-05** | connect `/work/g3b/{controller,broker}.sock`、`/work/private/controller.sock`；向 `bridge.sock` 发伪造 `reservation_id/call_id` 帧 | 私有 socket `ENOENT(2)`；bridge 伪造帧被 controller 拒绝（G3-C 冻结错误码）；Fake 0、reservation 0 | Fake counter、Broker 行、controller 日志、连接数 |
| **D2-06** | 额外 `call_id/reservation_id/admission_id/authorized/approved_payload/request_digest`；`maxTokens=1025`；未授权 tool；错 `seq`；坏 `hash`；超大/深嵌套/半帧/伪造 finish | controller 在 Fake 前拒绝；错误码在 G3-C 集合内；Fake 0、无新 reservation/settle | 每个完整 frame、error frame、Fake/DB/attempt 行 |
| **D2-07** | AF_INET/AF_INET6；DNS `example.invalid`；connect `192.0.2.1:9`（TEST-NET-1，不发 HTTP）；connect `/run/podman/podman.sock`、`/var/run/docker.sock`；只允许 bridge | `EPERM(13)`（换机若可建，connect 必须 `ENETUNREACH/EACCES`）；DNS `EAI_AGAIN`；engine socket `ENOENT(2)` | stdout、`if_nameindex()` 仅 lo、`/proc/net/route`、host `ss` 无外部连接 |
| **D2-08** | 列 `/proc`；读 trusted host pid `/proc/<pid>/{environ,fd,cwd,root}`；`/proc/kcore`、`/proc/keys`、`/proc/sysrq-trigger`；写 `core_pattern` | trusted pid `ENOENT(2)`；masked `ENOENT/EPERM/EACCES`；写 `EACCES(13)`/`EROFS(30)`；只见自己 pid | candidate `/proc` 列表、trusted host pid、`uid_map`、env 名、errno |
| **D2-09** | DSH tool 本地执行；不加载 Guard/坏 Guard/自写 patch；tool 尝试直连 Broker/HTTP | 本地 tool 允许；Provider 调用仍由 controller 拒绝；Fake 0；无外呼 | DSH events、tool result、controller 日志、Fake、Broker 行、patch hash |
| **D2-10** | candidate 发 request 前/ack 前/chunk 后 `os._exit(137)`/SIGKILL；Ctrl-C/cancel；trusted 在 ATTEMPT_STARTED 后/Fake send 前/后 `podman kill`；重启 reconcile | 无自动重发；attempt 保守（STARTED/UNCERTAIN/HELD）；Broker 不免费/不 0；Fake ≤1 receipt；socket 最终不存在；无孤儿 | attempt/broker 前后行、receipt/counter、日志、`podman ps -a`、`ss -xl`、进程表 |
| **D2-11** | Echo/Tool/Resume 正向（与 D1-01..03 同） | 1/2 个 reservation/claim/attempt/receipt；SETTLED；DSH 合法；隔离不误伤 | 同 D1-01..03；D2-11 只作为“攻击矩阵中的正向对照” |
| **D2-12** | 两个 candidate/客户端并发；慢请求/半帧；fork 循环；大内存；重复连接（资源子用例 `at-g3d-attack-<run>`，相同 UID/userns/network/mount，`--pids-limit 8 --memory 128m`） | `pids.max` → `EAGAIN(11)`；`memory.max` → OOM kill；连接/帧/总量上限拒绝；无跨 stream、无额外 reservation/Fake | cgroup 文件、`podman stats`、controller 日志、DB 行、连接数、进程数 |

**每个 D2 case 的判定规则**：
- 负向 case 只有在**期望的真实拒绝发生**且 DB/Receipt/Fake 未变时才是 `PASS`；
- 路径可读/可写、伪造帧产生成功 ack 后的 chunk/finish、Fake 收到 bytes、reservation 新增 → `FAIL`；
- 环境不具备（如 SO_PEERCRED 不可用、无法 exec 到 candidate）→ `BLOCKED`，不得记 `PASS`；
- 只做 `chmod`/权限表/日志文字 → 不是证据。

**D2 统一调用形状**（host 只编排；攻击在 candidate 内执行）：

```bash
# host：启动 trusted + candidate（hold）+ 只读 probe，然后逐条 exec
/root/.local/bin/python3.11 -B scripts/g3d/d2_attacks.py --case D2-01 --run-id "$RUN_ID"
podman exec "$CAND" /opt/python/bin/python3.11 -B \
  /probe-attacks/candidate_probe.py --case D2-01
# 每条 case 独立 run；上一条清理/哈希完成后才跑下一条
```

### 4.3 D3 组合回归

| ID | 场景 | 命令/动作 | 期望 |
|---|---|---|---|
| **D3-01** | 正向组合 | Echo 1、Tool 2 轮、Resume 第二进程 | 同 D1-01..03；DB/Receipt/Attempt 一一对应；无隔离误伤 |
| **D3-02** | 跨主体 crash/cancel | W1..W10（D0 §6.2）：candidate kill 窗口、trusted kill 窗口、cancel、trusted 停止、controller 重启、candidate 重启 | 无自动重发；attempt 保守；Broker 不免费/不 0；Fake ≤1 receipt；reconcile 不 `ADMISSION_REPLAYED`；新 admission_id |
| **D3-03** | 无残余 | 每个 run 后 11 项检查（D0 §6.3） | `podman ps -a` 空、socket 不存在、无孤儿、mountinfo 无 state/evidence 挂载、无 `/project/src`、env 无 Key、DB integrity ok、Fake counter == receipt、rootfs/deps canonical |
| **D3-04** | 同 SHA 复现 | 从同一 `b2f6af0`/stage/rootfs/deps 重跑 D1-01 + 一个 D2 高风险（D2-01/07） | 结果一致；hash 一致；无“只跑一次”的一次性行为 |
| **D3-05** | no-live | `bash scripts/run_live.sh`（预期 exit 3 `BLOCKED`）；env 快照 | LiveGate 仍 BLOCKED；无 Key/模型/外网/付费 HTTP；不解除 |

**D3 统一调用形状**：

```bash
/root/.local/bin/python3.11 -B scripts/g3d/d3_regression.py --case D3-01 --run-id "$RUN_ID"
/root/.local/bin/python3.11 -B scripts/g3d/d3_regression.py --case D3-02 --window W3 --run-id "$RUN_ID"
/root/.local/bin/python3.11 -B scripts/g3d/d3_regression.py --case D3-03 --run-id "$RUN_ID"
/root/.local/bin/python3.11 -B scripts/g3d/d3_regression.py --case D3-04 --run-id "$RUN_ID"
bash scripts/run_live.sh   # 只验证 exit 3 / BLOCKED，不启动 Live
```

**D3 停止条件**：任何未获 Bound Claim 的 Fake 发送、Claim 重放导致第二次发送、无 Attempt 却 Fake、已结算账本被非法回滚、candidate 可写 trusted state、真实 Key/付费 HTTP、或证据 SHA 无法核实 → 立即 **STOP**，按 `FAIL/BLOCKED` 记录，不进入 G4/Live。

---

## 5. 证据目录设计

### 5.1 目录

```text
artifacts/g3d/
  env/
    identity.json          # HEAD/base/docs_sha/clean/remote
    canonical-pre.json     # rootfs/deps/stage hash，UTC
    canonical-post.json
    podman-info.json       # version/rootless/cgroup/runtime
    livegate.json          # BLOCKED；无 Key
  logs/
    launcher.log
    trusted-<run>.log
    candidate-<run>.log
    d2-<case>.log
    d3-<case>.log
  traces/
    <case>/dsh-result.json
    <case>/stdout.txt
    <case>/stderr.txt
    <case>/uid_map.txt
    <case>/gid_map.txt
    <case>/mountinfo.txt
    <case>/proc.txt
  evidence/
    case-<id>.json         # 每 case 结构化结果
    matrix.csv             # D 矩阵（D1/D2/D3 实际状态）
    db-before/  db-after/  # 只读副本/hash；不原地打开
    receipts/
    cleanup.json
    errors.jsonl
  commands.jsonl           # append-only：argv/cwd/env names/UTC/exit/ref
  runs/<run_id>/{state,ipc,candidate-session,evidence,logs}
  stage/<run_id>/{candidate,trusted}
  build/                   # adapter build-meta/lib hash
```

`artifacts/` 已被 `.gitignore` 忽略；evidence/Packet 不提交到产品 commit。D Packet 由后续 builder 复制到 `artifacts/review-packet-g3d-<impl_sha>/`。

### 5.2 `case-<id>.json` 字段（最低集，对齐任务书 §13.1）

```json
{
  "case_id": "D2-01",
  "gate": "G3-D2",
  "status": "PASS|FAIL|PARTIAL|BLOCKED|UNVERIFIED|NOT_RUN",
  "test_type": "real-candidate|host-test|container-proof",
  "base_sha": "b2f6af054555705192c4e1ae3019a68078764736",
  "impl_sha": "<D1 commit>",
  "test_sha": "<D2 runner commit>",
  "rootfs_hash": "25491e45…",
  "deps_hash": "e07729d7…",
  "podman_version": "4.9.3",
  "container_names": {"trusted": "at-g3d-trusted-…", "candidate": "at-g3d-candidate-…"},
  "command_argv": ["podman", "exec", "…"],
  "utc_start": "2026-11-17T…Z",
  "utc_end": "2026-11-17T…Z",
  "exit_code": 0,
  "expected": "all paths ENOENT(2); DB hash unchanged",
  "observed": "…",
  "errno": {"/work/state/broker.sqlite3": 2},
  "candidate": {"host_uid": 65534, "uid_map_ref": "…", "gid_map_ref": "…", "mountinfo_ref": "…"},
  "trusted": {"host_uid": 0},
  "fake_received_before": 0,
  "fake_received_after": 0,
  "db_hashes_before": {"broker.sqlite3": "…"},
  "db_hashes_after": {"broker.sqlite3": "…"},
  "artifact_refs": ["artifacts/g3d/…"],
  "notes": ""
}
```

**硬规则**：
- `PASS` 必须有真实 candidate 命令、真实 errno/协议 frame、`uid_map`/`gid_map`/`mountinfo`、DB/Receipt/Fake 前后值；缺一不可。
- `BLOCKED` 必须写具体环境原因；不能把“没跑”写成 PASS。
- 只读 SQLite 副本查询：先复制到 `/tmp` 再打开；禁止用 `sqlite3` 直接打开 Packet/evidence 内的 DB（G3-B 曾因 `-shm` 导致 hash 漂移）。
- 每个 case 独立 run/state/容器名；D2 每条前后都采 `podman ps -a`。

### 5.3 采集与 hash

- rootfs/deps：使用 G3-C 同款归一化 tar：
  `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - -C <dir> . | sha256sum`
- 运行前后各一次；不一致 → `EVIDENCE_INTEGRITY`，先停跑，只删除**可证明为空/0 字节**的 Podman 自动 mount target，并记录删除项。
- 运行 Python 一律 `-B` + `PYTHONDONTWRITEBYTECODE=1`，防止 deps `__pycache__` 漂移；发现漂移先停止，不掩盖。
- candidate session 采集：`tar` 不解引用、限制文件数/大小、`O_NOFOLLOW|O_NONBLOCK`；不把宿主文件读入 evidence。
- `commands.jsonl` 每条含：UTC、argv、cwd、env 变量名（不含值）、exit、stdout/stderr ref；不记录 Key/token。

---

## 6. 提交/审阅序列与停止点

```text
D1-0 基线冻结（只读）
  → Lead 复核：HEAD/hash/clean/rootfs/deps/podman ps
D1-1 additive socket 代码 + host 测试
  → Lead 复核：diff 仅 2 文件 + 新测试；默认 0600 回归；旧 G3-C/G3-B 测试全绿
  → 失败即 STOP（不得用改测试适配）
D1-2 launcher/entries/config/stage
  → Lead 复核：argv/挂载/权限/ready/cleanup/exit codes；candidate stage 无 trusted 代码
D1-3 D1 正向 Echo/Tool/Resume + principal 证据
  → Lead 复核：UDS 连通、socket 0770/2000、peercred 65534、DSH 链、清理
  → 正向失败先修 D1；未通过不得进 D2
D2-1 D2-01..12 攻击
  → Lead 复核：高风险项真实 errno、Fake 0/账本不变、旧 B-1..B-4 关闭
  → 任一 FAIL/PARTIAL/BLOCKED 未解释 → STOP，不写 D PASS
D3-1 D3 组合/回归/无残余/复现
  → Lead 复核：W1..W10、无残余 11 项、同 SHA
D-DOC D Report / Review Request / Matrix / Packet
  → Lead 审阅后 STOP，交独立 D Reviewer
D-REVIEW 独立复核
  → 维护者决定下一步；不得自动 G4/G5/Live
```

**Lead 在每个停止点需要的产物**：
1. `git diff`（仅该步文件）+ 测试日志 + `commands.jsonl`；
2. `case-*.json` + 原始 trace/stdout/stderr + DB/Receipt hash；
3. 清理快照（`podman ps -a`/`ss -xl`/`pgrep`/hash）；
4. 本步未解决项/残余风险，明确标 `FAIL/PARTIAL/BLOCKED`。

**审阅规则**：独立 D Reviewer 必须用**自己的新攻击脚本**复验 D2-01/02/03/04/07/08 高风险项，不得只复制 Owner 矩阵；Reviewer 只写自己的 report/artifacts，不改产品代码/证据。

---

## 7. 风险与回滚

| # | 风险 | 影响 | 缓解/检测 | 回滚 |
|---|---|---|---|---|
| 1 | **rootfs 哈希漂移**：Podman 为 bind target 自动创建 `/ipc`、`/server.py` 等 | canonical 变、证据失效 | 所有新 target 放 tmpfs `/work` 下；前后 hash；只删可证明空目录/0 字节文件并记录 | 删除可证明空目标，恢复 canonical；不得删除未知文件；仍不符则 STOP |
| 2 | **socket 权限反例**：默认 0600 连不上；0666 失去最小权限；目录 0700 无法穿越 | 正向失败或权限过宽 | D1-05/06 断言 0600 默认、0770/2750；`on_ready` 内 `stat`；peercred | 回退 additive commit；恢复 0600 默认；不改 0666 |
| 3 | **peercred gid 误配**：把 2000 当 peer gid | 合法 candidate 被拒 | 现场 `PEERCRED gid=65534`；配置 `[65534]`；D1-06 负向验证 2000 拒绝 | 改回 65534；若环境不同，记录并重新签核，不放宽 |
| 4 | **cap-drop/chown 冲突**：trusted 无 CAP_CHOWN，`chown` EPERM | socket gid 错/启动失败 | setgid 目录继承；`socket_gid=null`；`on_ready` 断言 gid 2000 | 不加 cap；修目录 setgid/launcher 权限 |
| 5 | **candidate 逃逸/runtime 0day** | 越界到 trusted/宿主 | 不在本 Gate 主张；rootful Podman + LXC residual；高风险用 VM | 记录 residual；不得声称 PASS 生产安全 |
| 6 | **共享环境 podman 竞态**：并行 Agent 起容器/改 rootfs/deps | 证据污染、hash 漂移 | 每 run 唯一名；`artifacts/g3d/.g3d.lock` `flock`；`podman ps -a` 空；D 运行串行化 | 抢锁失败 → 退出；等前序完成；不并发写 rootfs |
| 7 | **deps `__pycache__` 漂移** | `e07729d7…` 失效 | `-B`/`PYTHONDONTWRITEBYTECODE=1`；前后 hash；发现漂移停跑 | 只删 `__pycache__`，重算；不掩盖 |
| 8 | **G3-C P2-1 stale stage**：旧 stage 源码是 e6fde1c | D1 测旧代码 | 从当前 `src` 重建 trusted stage；断言 `bridge.sock.lock`/PR1 指纹；记录 `stage_hash` | 重建 stage；不复用旧 stage |
| 9 | **时间预算**：D2 12 类 + D3 10 窗口 | 超时/半成品 | 每 case 硬 timeout；先 D1 正向再 D2；高风险失败即停；预计 20–40 min | 保留已完成证据，未跑标 `NOT_RUN`；不拼凑 PASS |
| 10 | **candidate session symlink/FIFO** | root launcher confused deputy/阻塞 | 不解引用、`O_NOFOLLOW` + `O_NONBLOCK`、文件数/大小上限 | 跳过恶意文件并记录；不读宿主路径 |
| 11 | **环境换机**：无 userns/uidmap/cgroup v2/SO_PEERCRED | 无法建立双 Principal | D1 preflight 真实探针；不满足 → `BLOCKED_NEEDS_ENVIRONMENT` | 不 mock；报告最小环境需求 |

**总体回滚**：D1 additive commit 可单独 `git revert`，默认行为回到 0600/无 peer 校验；D1 启动器/测试/配置均为新增文件，删除即回滚；D1 分支不合并则不影响 `main`。任何回滚都必须重跑 G3-C 回归与 rootfs/deps hash。

---

## 8. 授权后执行清单（Implementation Agent 用）

### 8.1 第一条命令（只读）

```bash
cd "/root/Autonomous Teacher"
git status --porcelain
git rev-parse HEAD
git diff --stat b2f6af0..HEAD -- src tests
tar -C artifacts/security/rootfs --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
tar -C artifacts/foundation/deps --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner -cf - . | sha256sum
podman ps -a
```

### 8.2 实施顺序

```text
1. 只读冻结 → artifacts/g3d/env/identity.json + canonical-pre.json
2. 建 g3d/impl 分支（从 fff3623）
3. D1-1：ipc_server.py/controller.py + host 测试；跑 g3_bridge/g3c 回归
4. D1-2：build_stage.py/launch.py/entries/probes/config
5. 环境探针（真实最小容器）→ 不满足 exit 3
6. D1-3：先 D1-01 Echo，单步跑通；再 Tool/Resume
7. 记录 principal/socket/peercred/DSH/DB/Receipt/清理证据
8. Lead 复核 → D2-1（D2-01..12，逐条独立 run）
9. Lead 复核 → D3-1（W1..W10/无残余/复现）
10. D Report/Review Request/Matrix/Packet → STOP 等独立 D Reviewer
```

### 8.3 绝对禁止

- 真实 Key/模型/外部付费 HTTP/Live；`run_live.sh` 只允许验证其 `BLOCKED` 退出，不解除。
- 把 socket 改 0666、candidate 加 root 组、`$RUN` 整目录挂 candidate、同 UID/同容器冒充双 Principal。
- 从 host/trusted 伪造 candidate 结果；用 mock UDS/模拟 Broker 代替内核拒绝。
- 修改 G3-C 冻结协议/错误码/状态机、G3-C Packet、历史 docs/artifacts。
- 未经 Lead 复核直接 commit/push/合并；D1/D2/D3 结果不得自判 `PASS_FOR_G3D_*`。

---

## 9. 验收清单（D1 完成时逐项打勾）

```text
[ ] HEAD/branch 固定；src/tests 与 b2f6af0 无 diff；无未解释工作树改动
[ ] 默认 0600 回归全绿；隔离模式 0770/gid 2000/peer uid 65534 有测试+现场
[ ] candidate 连接成功；trusted on_ready 写 ready；host 等 ready 后起 candidate
[ ] D1-01 Echo / D1-02 Tool / D1-03 Resume 各 1 次真实 DSH 成功
[ ] candidate uid_map/gid_map/host Uid=65534 与 trusted Uid=0 有证据
[ ] socket stat 0770 root:2000；peercred uid=65534 gid=65534 pid=0
[ ] candidate mountinfo 无 state/evidence 挂载、无 /project/src；无 Key/engine socket
[ ] DB/Attempt/Receipt/Fake 链一致；无免费/重复 settle
[ ] 清理：podman ps -a 空、socket 不存在、无孤儿、IPC 空
[ ] rootfs/deps canonical 前后一致；无未解释 mount target
[ ] `commands.jsonl`/case JSON/日志/证据路径完整；无 Key/外网
[ ] Lead 复核通过；D2 授权后才开始攻击
```

---

> **结束原则**：D1 先证明“合法 candidate 能过、trusted 仍独占控制面”，D2 再证明“恶意 candidate 被真实内核/协议拒绝”，D3 最后证明“跨主体故障与清理保守一致”。三者都通过且独立 D Reviewer 复核后，才谈 `PASS_FOR_G3D_NO_KEY_OS_TRUST_BOUNDARY_SCOPE`；本计划本身不授权任何 PASS 或 Live。
