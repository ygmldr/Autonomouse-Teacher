# M0 G3-D — Independent Review（独立复核）

> **Reviewer identity**：本复核由 **未参与** G3-D0/D1/D2/D3 实现、证据生成、矩阵填写或 D4 Review Packet 构建的 Independent D Reviewer 执行；不复用 Owner 的 `summary.json`/`checks.json` 结论文字作为判定，所有关键结论来自本 Reviewer 自建 Probe、独立复跑与原始字节/SQLite 副本复核。
> **复核时间**：2026-11-17T23:33Z – 2026-11-18T00:20Z（UTC）。**工作树**：`/root/Autonomous Teacher`。
> **冻结身份**：base `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`；implementation `97230a0ba40f5f2dec98a426676fbe81a5157a26`；code `cf40c6bfb84ceae98e795db19efa955aa3035991`；docs `ce4979eb1c28f5d03efe4cb3dade5d200003b8e2`；D3 Stage `artifacts/g3d/stage-20261117T221955Z`（manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`，tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5`）；rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`。
> **全程约束**：0 真实 Key / 0 真实模型 / 0 外部付费 HTTP / 0 Live；未 `podman pull`；未修改 `src/`、`scripts/g3d/`、Stage、Rootfs/Deps、D1–D3 证据、矩阵、历史 docs 或 Packet；未 commit / push。
> **本报告的唯二写入**：`docs/REVIEW_G3D_INDEPENDENT.md`（本文件）与 `artifacts/reviewer-g3d/`。

---

## 0. 唯一裁定

# `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`

**范围限定（与裁定同义，不可省略）**：该 PASS **仅限本机（`192.168.1.101` / rootful Podman 4.9.3 + crun 1.14.1 + kernel `6.17.13-2-pve` + 冻结 rootfs/deps/stage/DSH `0.2.2-rc.2` SHA）已实测的双 OS Principal 隔离、真实 DSH（Fake Provider）正向、真实 Candidate 攻击拒绝与崩溃/恢复一致性**。它**不主张**：内核/容器运行时 0day 防护、宿主 root 被攻陷后的安全、生产部署安全、真实 Provider/Invoice/exactly-once、跨 Runner 可移植性；**不授权** Live、G4、G5、M0 GO。

| 复核域 | 结论 | 关键依据 |
|---|---|---|
| **R0 身份/Packet/漂移** | **PASS** | 1041/1041 哈希 OK；1043 文件/1040 payload/0 symlink；两种 Patch 字节一致；Stage/Rootfs/Deps/DSH/Node/Podman 身份全部复算一致；旧 `e6fde1c` Stage 未被加载 |
| **R1 静态复验** | **PASS** | D1-A mode/peercred/ready/stale 逻辑逐行核验；Candidate argv 契约与白名单；Admission UID 与 OS peer UID 分离；G3-C 语义未削弱（`src` 相对 base 0 改动） |
| **R2 自建真实 Candidate 攻击** | **PASS**（15 类均覆盖；cgroup pids/memory 压测部分 **UNVERIFIED**，见 §9） | 8 个自建 Run 全部 `exit 0`、`cleanup.ok=true`、canonical；旧 G3-B 四个同 UID 绕过与当前真实拒绝成对记录；24 个负例后账本仍为 0；同 payload 重放 → `ATTEMPT_ALREADY_STARTED`、只 1 套账本 |
| **R3 真实 DSH 双主体** | **PASS** | Echo 1/1/1/1/1；Tool 2/2/2/2/2 且 tool result 进入第二请求；Resume 两个真实 Candidate 进程、`resume_session`、不重放旧 Attempt；usage 与 receipt 字段级相等 |
| **R4 故障/并发** | **PASS** | C04/C05/C06 三个真实崩溃窗口（trusted `exit 97` + 对应 hook）；C07 取消；C08 断连；C10 自算时钟 T1<T2；C11-same 恰 1 finish + 1 `ATTEMPT_ALREADY_STARTED`；C11-real 两独立请求分级单列 |
| **R5 回归/清理** | **PASS**（Host full 2 个已知环境失败、OCI 4 deselect/7 skip 如实保留） | 固定 OCI **916 tests / 909 passed / 0 failed / 7 skipped / 4 deselects**，exit 0；Host targeted 144/31/110/14 全过；Node 19/19 + 8/8；Ruff 0；LiveGate BLOCKED；`podman ps -a` 空；0 残留；三 Hash canonical |

**P0：0 项。P1：0 项。** P2 残余见 §8。

---

## 1. R0 — 身份、Packet 与真实加载 Blob

### 1.1 Git 身份与不可变面（独立命令）

| 对象 | 值 | 核验 |
|---|---|---|
| HEAD | `ce4979eb1c28f5d03efe4cb3dade5d200003b8e2` | `git rev-parse HEAD`；`git status --porcelain -uall` = 0 行 |
| base | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b` | `git rev-parse`；`src` 自 base 0 改动 |
| implementation | `97230a0ba40f5f2dec98a426676fbe81a5157a26` | 与 Packet `manifest.json` 一致 |
| code | `cf40c6bfb84ceae98e795db19efa955aa3035991` | `git rev-parse cf40c6b` |
| docs | `ce4979eb1c28f5d03efe4cb3dade5d200003b8e2` | 与 Packet `docs_sha` 一致 |
| D1-A | `51abc6619ef87ad7b93aa3162fed52ab14df6e56` | base 祖先；`src` 改动只在此提交 |

| 保护面 | 结果 |
|---|---|
| `git diff 4bd4803 97230a0 -- src` | 0 行 |
| `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge` | 0 行 |
| `AGENTS.md`、`scripts/run_live.sh`、`README.md`、`SECURITY.md`、`pyproject.toml`、`Dockerfile.m0` 相对 base | 0 行 |
| G3-C 历史 docs（v1/v2/report/errata/matrix） | `git diff 4bd4803 ce4979e` 与 `git diff 97230a0` 均 0 行 |
| `tests/integration/g3d/test_d1_socket_boundary.py`（D1-A 冻结字节） | `git diff cf40c6b 97230a0` 0 行 |
| 变更范围 | 仅 `scripts/g3d/**`、`tests/integration/g3d/**`、`config/g3d/**`、`docs/**` |
| 工作矩阵 | 53 行 = **52 PASS / 1 NOT_RUN**；`D-REVIEW-01` 仍 `NOT_RUN`；Packet `matrix/G3D_Test_Evidence_Matrix.csv` 与仓库矩阵逐字节相同（sha256 `e846d68f…875f`）；历史 G3-C 矩阵未改 |

### 1.2 `changes/*.diff.patch` 字节一致

- Packet 的 `implementation.diff.patch` 由 builder 以 `git diff --binary 4bd4803..97230a0 -- src scripts tests config plugins spikes` 生成；我以 `git diff --binary 4bd4803 97230a0 -- . ':(exclude)docs'` 独立复算，**两者 sha256 均为 `2a72efe8…a54391`**，字节一致。
- Packet 的 `docs.diff.patch` 等于 `git diff --binary 4bd4803 ce4979e -- docs`，**sha256 `0d3f19de…3040d8`**，字节一致。
- 说明：直接运行 `git diff --binary 4bd4803 97230a0`（含 docs）**不会**与拆分后的 patch 字节相等；这是 Packet 有意的 code/docs 分离，不是内容缺失。我用 `-- . ':(exclude)docs'` 证明非 docs 变更**全部**在 Packet 内，无遗漏路径。

证据：`artifacts/reviewer-g3d/r0-identity/git-identity.txt`。

### 1.3 Packet 完整性

| 检查 | 结果 |
|---|---|
| `sha256sum -c hashes.sha256` | **1041/1041 `OK`**，exit 0（无 FAILED） |
| 磁盘文件数 / `packet_file_count` | **1043 / 1043** |
| payload 文件数 / `packet_payload_file_count` | **1040 / 1040** |
| `hashes.sha256` 覆盖 | 1040 payload + `manifest.json`；自身与 `packet-integrity-report.txt` 为自引用例外，均不缺失 |
| `packet_payload_tree_sha256` | 包内 `review/verify_payload_tree.py` 复算 = **`aa2a955df7dc245b47ca50fc0e70596bf1804122c25570e7513da97177cbed02`**，与 manifest 一致 |
| symlink | **0** |
| 体积/危险内容 | 24 MB；无 `.git`、`node_modules`、rootfs、完整 repo；无 `.env`/私钥文件；key-like 字面量仅 `sk-INVENTED_ONLY`/`sk-register` 等 sentinel/文案，无真实 Key |
| `manifest.json` 自述 | `real_model_calls=0`、`real_external_http_calls=0`、`has_real_key=false`、`live_gate_status=BLOCKED`、socket 0660/GID 2000、peercred uid 65534、network none |
| Packet 内副本 | D3 manifest、矩阵、`ipc_server.py`、`controller.py` 与仓库文件逐字节相同 |

证据：`r0-identity/packet-integrity.txt`、`packet-hashes-verify.log`、`packet-manifest-fields.txt`、`packet-copies.txt`。

### 1.4 Stage / Runtime / 真实加载模块（不是“文件在目录里”）

- Stage manifest `644823d4…`；整体 tree `e1ff1449…`；trusted 57 文件 / tree `3a004bee…`；candidate 6549 文件 / tree `6c850e4b…`。
- Trusted stage 的 **49/49 个 `.py`** 字节 SHA 等于 `git show 4bd4803:src/...`（`r1-static/trusted-src-vs-base.txt`）。
- 实际加载：我的 Echo/Tool/Resume Run 中 `inspect.getfile` 的 **10 个模块**均位于 `/project/src/autoteacher_m0/...`，其文件 SHA 同时等于 `git show 97230a0` 与 `git show 4bd4803`；其中 `controller`/`ipc_server`/`attempts` 与旧 G3-C `e6fde1c` **不同**（证明没有加载旧 Stage 的这三个关键模块）。
- 旧 G3-C Stage tree `fcdb0de4…` 未被使用；D3 stage summary 记录 `base_sha=4bd4803`、`head=cf40c6b`。
- Runtime：DSH SDK `0.2.2rc2`、runtime SHA `1cc41d5a…`、Node `v22.23.2`、adapter `2cb42461…`（`deterministic_match=true`）、Python `3.11.15`、Podman `4.9.3` rootful、crun `1.14.1`、kernel `6.17.13-2-pve`、cgroup v2。
- Rootfs/deps 在所有 Reviewer Run 前后等于 canonical（preflight/cleanup 均记录）。

证据：`r0-identity/canonical-identity.txt`、`loaded-modules-vs-refs.txt`、`r1-static/candidate-stage-inventory.txt`。

### 1.5 0-Key / LiveGate / 干净起点

- key-like 环境变量名 **0**；无 `.env`（仅 `.env.example`）。
- `bash scripts/run_live.sh` → **exit 3**。
- `LiveGate().inspect(live_requested=True)` → **BLOCKED**，4 reasons 不变（`EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`、`BASELINE_EVIDENCE_MISSING`、`ACTUAL_TOOL_REGISTRY_NOT_APPROVED`、`SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED`）。
- Reviewer 开始时 `podman ps -a` 空。
- **环境事实（非产品漂移）**：我运行固定 OCI 命令时，podman 为缺失的 `/evidence` bind mount 在 rootfs 内创建了空目录 `artifacts/security/rootfs/evidence`（root:root 1755，空）。这与 Packet `regressions/rootfs-runtime-cleanup.txt` 记录一致；我确认其为空后 `rmdir`，rootfs 立即回到 `25491e45…`，并在 `r0-identity/rootfs-evidence-artifact.txt` 记录。

### 1.6 历史冻结物

G3-C/G3-B 历史 docs 由 git 证明 0 改动；`artifacts/` 被 gitignore，以其最新 mtime 全部早于 D1 实现（G3-C Packet 2026-11-17 16:28、G3-B Packet 2026-11-16 21:08）；旧 G3-B 同 UID 绕过证据 `artifacts/reviewer-g3b/r3/boundary-result.json` 的 sha256 `5bfde0d0…b5e46` 记录在配对表中。证据：`r0-identity/frozen-history.txt`。

---

## 2. R1 — 静态复验

完整逐项分析见 `artifacts/reviewer-g3d/r1-static/STATIC_FINDINGS.md`；源片段见同目录 `ipc-server-key-sections.txt`、`ipc-server-peercred-ready.txt`、`controller-key-sections.txt`、`launcher-candidate-contract.txt`、`build-stage-allowlist.txt`。要点：

### 2.1 D1-A `BridgeServer`（additive）

- `socket_mode` 仅接受 `0o600`/`0o660`，`type(mode) is not int` 拒绝 bool；`socket_gid`/`expected_peer_uid` 拒绝 bool/越界；`socket_gid` 在无 group 位的 mode 下拒绝（`ipc_server.py:53-55,176-194`）。
- `accept()` 后、读取首帧、占用连接配额、发送 `ack` **之前**执行 `SO_PEERCRED` 校验（`ipc_server.py:241-252`；ack 在 `539-543`）。任何 `getsockopt` 异常、短读、选项缺失均 fail-closed（`419-455`）；`PEER_UID_DENIED`/`PEERCRED_UNAVAILABLE` 只做脱敏诊断，不写入协议错误码，被拒 peer **收不到 ack**。
- stale socket 仅当 `lstat` 为 socket 且 owner == euid 才 unlink；symlink/普通文件/目录/异主一律抛错而不是删除（`329-350`）；父目录必须是真实目录（`314-327`）。`ipc` 目录为 `2750 root:2000`，group 2000 无写位，故 Candidate 无法在 lstat/unlink 之间做替换。
- `bind → chmod → (可选 chown) → 精确校验 mode/uid/gid → listen → on_ready`（`231-239,352-410`）。没有 `CAP_CHOWN` 时依赖 Host 预建的 setgid 目录继承 group，**不静默放宽**；任何不一致 aborts。
- 退出时只删除自己拥有的 socket（`412-417`）。
- `_bridge_options` **不读取** Admission 的 `expected_uid`（业务 contract）；`controller.py:1550-1563`、`1634-1635`。部署配置中 `expected_peer_uid`（OS 凭据）与 `expected_uid`/`admission.launcher.uid`（业务）是三个独立键，本 fixture 数值都为 65534；Host 测试 `test_admission_launcher_uid_is_not_the_socket_peer_uid` 以 `expected_peer_uid=0` + 业务 65534 正向成功、再以 `load_admission(expected_uid=0)` 失败 `ADMISSION_LAUNCHER_MISMATCH`，证明两者不互相赋值（该测试在 Host 全量中实际执行并通过，OCI 中因需 host root 被显式 deselect）。

### 2.2 Launcher / Stage

- Candidate argv：`--uidmap 0:65534:1`、`--gidmap 0:65534:1`、`--gidmap 2000:2000:1`、`--group-add 2000`、`--network none`、`--read-only`、`--cap-drop ALL`、`no-new-privileges`、`--userns` 非 host；挂载仅 `/project` ro、`/deps` ro、`/work/g3b` ro、`/work/session` rw、passwd/group ro（`lib_g3d.py:732-767`）。`argv_contract_problems` 对 state/evidence/`/project/src`/trusted entry 等显式 fail-closed（`979-1015`）。
- Trusted argv：`--userns=host --user 0:0`，独占 `/work/state` rw、`/work/g3b` rw，无 candidate 挂载（`690-731`）。
- Ready 顺序：Trusted 写 ready 文件（在其 `on_ready` 内先校验 socket 0660/root:2000）；Launcher 同时验证 ready 内容、`/proc/<trusted_pid>/net/unix` 中真实 listening 项、socket `lstat`，三者一致才启动 Candidate（`launch.py:860-963`；我的 Echo Run `socket-stat/listening.json` + `run/launcher-ready.json`，`candidate_started=false`）。
- Candidate Stage 是**显式白名单**（`build_stage.py:437-560`）；构建树 6549 文件，`autoteacher_m0` 路径 0、controller/broker/fake/admission/policy/DB/key 0；只有 `run/candidate_entry.py`、审计过的 D2/D3 probe、DSH runtime/node_modules/adapters/config/etc。
- 清理限定作用域：`safe_delete_tree` 仅允许 `artifacts/g3d/runs` 之下且拒绝删除 root/symlink；`unlink_socket` 校验类型与 owner（`lib_g3d.py:1068-1155`）。

### 2.3 Candidate 自检（纵深，不是边界本身）

`candidate_entry.py:194-280` 在启动时自检 uid_map/gid_map/组 2000、`/work/state` 不可见、`/project/src` 不可见、`PYTHONPATH=/deps`、`autoteacher_m0*` 不可导入、socket 0660/gid 2000、unlink/rename/create 被拒、禁止挂载存在、自身 PID namespace 无 trusted 组件。我的 Run `uid-map/candidate-principal.json` 显示 `problems=[]`、26 项全 true。该自检仅作佐证，判定仍以 mount/UID/内核 errno 为准。

### 2.4 未发现可绕过/放宽容忍路径

逐项排查见 `STATIC_FINDINGS.md:§4`，包括：`expected_peer_uid` 缺省、`socket_gid` 缺省、父目录缺失时 0700 创建、stale lstat/unlink TOCTOU、`/work/state` 同名 tmpfs 文件、嵌套 userns、同 UID 旧 Run 路径、磁盘配额、Guard 缺失。结论：没有一条能让 Candidate 读/写 trusted state、获得 Controller 之外的发送能力或伪造结算；其中嵌套 userns、同 UID 路径、磁盘配额属**已登记 P2**（§8），不是本配置下的边界绕过。

### 2.5 G3-C 语义未削弱

`src/` 相对 base 0 改动，故 framing/deadline/cancel/streaming 仍是被冻结的 G3-C 代码。我的 Candidate 线协议负例复现了冻结错误词汇（§3.4）；`tests/integration/g3_bridge` 31/31、`tests/integration/g3c` 110/110 在 Host 通过；固定 OCI 916 全量通过。

---

## 3. R2 — Reviewer 自建真实 Candidate 攻击（Level A）

### 3.1 方法与身份真实性

- 自建 Probe：`artifacts/reviewer-g3d/r2-probes/rv_probe.py` + `rv_common.py`（未 import `autoteacher_m0`，未复用 Owner probe 源码）；自建 runner：`r2_runner.py`（只复用冻结 Launcher 的 preflight/create_run/write_configs/start_trusted/collect/cleanup 生命周期）。
- 主攻击 Probe 通过 `podman exec` 进入真实 Candidate 容器（同一 user/mount/pid/net/ipc/uts/cgroup namespace、同一 uid_map/gid_map、同一只读挂载与 capability/seccomp），argv/UTC/exit 记录在 `probes/record-*.json`。
- CONTROL/stale/foreign 使用 Reviewer 自建 argv 的真实容器：相同 `--uidmap 0:65534:1`、`--gidmap 0:65534:1 + 2000:2000:1`、`--group-add 2000`、`--network none`、`--read-only`、`--cap-drop ALL`、`no-new-privileges`；CONTROL 额外**只读**挂载 `$RUN/state`（明确标注 CONTROL，不作为正式 Candidate 配置）；stale 挂载另一个空 IPC 目录；foreign 用 host UID **65533**（同组 2000）连接 live UDS，以真实内核凭据触发 `PEER_UID_DENIED`。
- 8 个 Run 全部 `exit 0`、`cleanup.ok=true`、rootfs/deps/stage canonical；run id/UTC 见 `r2-probes/RUNS.md`。

### 3.2 保护资产（No Mount / Kernel DAC）

| 攻击 | 真实结果 | 分类 |
|---|---|---|
| 读 `/work/state/{broker.sqlite3,-wal,-shm,attempts.sqlite3,admission.json,broker.json,controller.json,policy.json,ready,receipts/**}` 及 `/state`、`/output` 副本 | 全部 `ENOENT(2)`；`/work` 仅 `g3b`+`session`；mountinfo 无 state；5589 个条目 bounded name search **0** 命中 | **No Mount** |
| 写/截断 DB/WAL/SHM、写 policy/admission/receipts、unlink/chmod/mkdir/rename/symlink/hardlink | 全部 `ENOENT(2)`（含 `open_dir`）；无任何事务/行变化 | **No Mount** |
| CONTROL：同 uid 容器额外**只读**挂载 `$RUN/state` | `lstat` 可见 0700，但 `open_rdonly`/`open_wronly` 全部 `EACCES(13)`；`EISDIR` 仅对目录本身 | **DAC Deny（CONTROL）** |
| CONTROL + `unshare(CLONE_NEWUSER)` 后读/写 state | 子进程 `uid_map=""`、euid 65534；仍全部 `EACCES(13)` | **DAC Deny（userns 不绕过）** |
| Candidate 在自己的 `/work` tmpfs 创建同名 `/work/state` 文件 | 成功创建（tmpfs 可写），`lstat` 为普通文件；随后 unlink；trusted state 字节/行完全不变 | **No Mount**（不是 DAC 拒绝） |

状态前后：负例 Run 的 `state/pre.json` 与 `state/after_negatives.json` **完全一致（全 0）**；含合法请求的 Run 只按合法请求数精确变化（attack：4 笔合法请求 → 4 Attempt/Claim/Reservation、8 messages、counter 4）。

### 3.3 代码/进程/内核面

| 攻击 | 真实结果 | 分类 |
|---|---|---|
| `find_spec`/`import` `autoteacher_m0`、`.bridge.controller`、`.accounting.broker`、`.bridge.fake_backend` 等 | 全部不可导入；`ModuleNotFoundError`；`/project/src`、`/project/fake`、`/deps/autoteacher_m0` 均不存在 | **No Mount** |
| 直接执行 trusted 入口/包（`/project/fake/fake_provider.py`、`/project/src/...`、`/project/run/trusted_entry.py`、`-m autoteacher_m0.bridge.controller`） | 前三个 `python: can't open file`（exit 2）；模块 `exit 1`（No module named） | **No Mount** |
| `/proc/<trusted_pid>/{status,environ,fd,root,cmdline}`、`/proc/1/environ`、`/proc/self/fd`、`/proc/net/{unix,tcp,route}` | trusted PID 全部 `ENOENT(2)`（不同 PID namespace）；可见 PID 仅本容器；`/proc/net/unix` 为空；无 trusted FD | **Kernel Deny** |
| `ptrace(ATTACH)` trusted / `process_vm_readv` trusted | `ESRCH(3)`；对 pid 1 `EPERM(1)`；`CapEff=0`、`NoNewPrivs=1`、`Seccomp=2` | **Kernel Deny** |
| `mknod`、`mount`、`/proc/sysrq-trigger` 写、`/sys/kernel/uevent_helper` 写 | `mknod EPERM`；`mount tmpfs` 仅在**新建 userns/mount ns 的子进程**内成功；sysrq/uevent `EACCES` | **Kernel Deny / userns 局限** |
| `/dev/{mem,kmsg,sda,vda,console}`、Podman/Docker/overlay socket、`/run/systemd/private`、`/dev/log` | 全部 `ENOENT(2)`；`/sys/class/net` 仅 `lo`（+`bonding_masters`） | **No Mount** |
| 嵌套 `unshare(CLONE_NEWUSER)` | **允许**（内核事实）；子进程 `uid_map=""`、euid 65534；无 host root、无 state 访问 | **内核攻击面 P2** |
| `AF_INET`/`AF_INET6` `SOCK_STREAM`/`SOCK_DGRAM`、DNS、TCP/UDP 外部 | `socket()` **`EACCES(13)`**（4/4）；`getaddrinfo` `EAI_AGAIN(-3)`；`gethostbyname` `-2`；`connect 1.1.1.1:80` / `sendto 1.1.1.1:53` `EACCES` | **Kernel Deny** |
| 其他 UDS（docker/podman/systemd/dev/log） | 全部 `ENOENT(2)`；唯一可连 `/work/g3b/bridge.sock` | **No Mount** |

### 3.4 协议/伪造/唯一 UDS

**负例集合**（每个都是一次真实 UDS 交换；`artifacts/reviewer-g3d/r2-probes/runs/negatives/probes/probe-negatives.json`）：

| 负例 | 真实响应 |
|---|---|
| `kind=reserve` / `claim` / `settle` | `error UNKNOWN_KIND`（无 ack） |
| `kind=receipt` / 首帧 `ack` | `error UNKNOWN_FIELD` |
| payload 加 `authorized` / `call_id` / `reservation_id` / `admission` / `dispatch_allowed` | `error UNKNOWN_FIELD`（解析期拒绝，无 ack） |
| envelope 加 `dispatch_allowed` | `error UNKNOWN_FIELD` |
| `provider` / `model` 伪造 | `ack` + `error ROUTE_MISMATCH` |
| 伪造 `skill_lookup` tool schema | `ack` + `error ADMISSION_TOOL_SCHEMA_MISMATCH` |
| 坏 envelope hash（全 0 / 非 hex） | `PREPARED_DIGEST_MISMATCH` / `BAD_TYPE` |
| `seq=1` 首帧 / 未知 kind | `SEQ_OUT_OF_ORDER` / `UNKNOWN_KIND` |
| 坏 JSON / 空行 / CRLF / 重复 key / NaN | `REQUEST_INVALID` / `DUPLICATE_KEY` / `NAN_OR_INF` |
| 262 200 bytes 大帧 | `error FRAME_TOO_LARGE` |
| 半帧后客户端超时 | 客户端未收到任何帧（首帧截止期内），无业务、无账本行 |
| 8 个 slowloris 连接 held + 第 9 个 | 第 9 个 `TOO_MANY_CONNECTIONS`；释放后新连接 `ack+chunk+chunk+finish`（服务恢复） |

**账本零增量**（`runs/negatives`，2026-11-18T00:16:39Z，exit 0）：

```
pre            attempts=0 claims=0 reservations=0 broker_messages=0 receipts=0 counter=None
after 24 负例   attempts=0 claims=0 reservations=0 broker_messages=0 receipts=0 counter=None
之后两次正向    attempts=2 claims=2 reservations=2 broker_messages=4 receipts=5 counter=count:2
```

即：伪造/越权/大帧/慢速攻击 **0 unauthorized Fake、0 Claim、0 Attempt、0 Reservation**，且随后真实正向仍成功。

**Socket 文件面**：Host 侧 `lstat` = socket、mode `0660`、uid 0、gid 2000；Candidate 内 `lstat` 显示 uid 65534（host uid 0 在 Candidate 的 uid namespace 未映射 → overflow）、gid 2000（已映射）；`unlink/rename/chmod` 均 `EROFS(30)`，`bind` 到已存在路径 `EADDRINUSE(98)`，在 ipc 目录新建 socket/文件/目录均 `EROFS`；攻击后 socket inode/mode 不变。

**本地伪造配置**：Candidate 在 `/work/session` 写 `forged-admission.json`+`policy.json`+`evil_guard.py`+`evil_tool.py` 均成功（其自身可写区），`evil_guard.py` 本地 `exit 0`；但 `/project` 无 guard 组件，Controller 只读 `/work/state`，伪造文件不改变任何 trusted 字节/行，后续正向仍 1/2 笔正确记账。**Guard 在本 Gate 不存在**，结论是“伪造本地 Guard 不能获得 Controller 之外的发送权限”，不是“Guard 已实现”。

### 3.5 旧 G3-B 同 UID 绕过 vs 当前真实拒绝（成对）

| 旧绕过（`artifacts/reviewer-g3b/r3/boundary-result.json`，sha256 `5bfde0d0…b5e46`） | 当前真实结果 | 分类 |
|---|---|---|
| B-1 读 Broker DB：`broker_db_read.ok=true, reservations=1` | `ENOENT(2)`；无 state mount；5589 条目搜索 0 命中 | **No Mount** |
| B-2 写 Broker DB：`broker_db_write=true` | `ENOENT(2)`；DB/SHA/行不变 | **No Mount** |
| B-3 写 Policy：`policy_write=true` | `ENOENT(2)`；Candidate 无 policy 副本 | **No Mount** |
| B-4 直接 Reserve/Claim：`RESERVED`/`CLAIMED`/`dispatch_allowed=true` | `UNKNOWN_KIND`/`UNKNOWN_FIELD`；无 Broker 模块/socket；24 负例账本 0 | **Protocol Deny + No Mount** |

完整机器可读配对：`artifacts/reviewer-g3d/r2-probes/old-bypass-pairing.csv`。

### 3.6 断连 / 半关闭 / SIGKILL / 重连

- **Candidate SIGKILL mid-flight**（`runs/kill`，2026-11-17T23:52:54Z）：子进程发送一个合法请求后 50 ms 被 `SIGKILL(9)`；结果恰好 2 个 `SETTLED` Attempt/2 Receipt/counter 2（被杀的 1 笔 + 父进程后续 1 笔），无重复、无额外 Fake。
- **半帧后超时/关闭**：客户端在首帧截止期内未收到任何帧（无业务错误帧、无账本行）；**半关闭（SHUT_WR）后请求仍完成**（ack/chunk/chunk/finish，1 笔正常结算）。
- **同一 payload 重放**（`runs/duplicate`，2026-11-18T00:22:19Z）：同一 session/同一 messages 连续发两次；第一次 `finish` 并 `SETTLED`，第二次 `ack` 后 `ATTEMPT_ALREADY_STARTED`；最终只有 **1 Attempt/1 Claim/1 Reservation/1 Receipt、counter 1**——不是新账本，也没有第二次 Fake。机制是 durable `g3b_request_identities` 主键 `(scope_id, identity_digest)`（`attempts.py:159-162,196-213`）：同一业务 digest 在任何 transport 上重复出现都失败关闭，这正是 D3-C11-same 依赖的 at-most-one 不变量。
- **重连**：slowloris 释放后新连接正常完成（见 §3.4）；半关闭后请求完成（见上）。

### 3.7 未覆盖/降级项（诚实标注）

- **cgroup pids/memory 压力**：Owner D2-12 yes，本次 Reviewer **未重跑** `pids-limit=8/memory=128m` 子容器压测 → **UNVERIFIED**；我独立覆盖的是连接耗尽/slowloris/超大帧/服务恢复。
- **D2-13 state 只读挂载**是 CONTROL，不是正式 Candidate 配置；正式结论只取 No Mount 的 §3.2。
- **同 UID 旧 Run**：只证明 live 路径在其 mount namespace 不可见（`ENOENT`）；未构造“拿到 live 路径的同 UID 容器”，该残余按 P2 登记（§8）。

---

## 4. R3 — 真实 DSH 双主体正向（Echo / Tool / Resume）

全部使用真实 Stage、真实 Rootfs、真实 DSH `0.2.2-rc.2`、真实两个 OS Principal、Fake Provider、`--network none`、0 Key；每次 fresh evidence dir。账本由 `artifacts/reviewer-g3d/analyze_ledger.py` 从 evidence 内只读 DB 副本重算（不打开 live DB）。

### 4.1 Echo — `20261118T000036Z-reviewer-echo-189eb06e`，exit 0

| 项 | 值 |
|---|---|
| 账本 | Reservation 1 / Claim 1 / Attempt 1 / Receipt 1 / Settlement 1；`broker_messages=2`（1 reserve + 1 settle）；counter 1 |
| Attempt | `SETTLED`，logical_step 0，mode `ok_usage` |
| Prepared/Claim | `prepared_digest == claim.request_digest` = `e05ca501…f573` |
| Payload/Receipt | `attempt.payload_digest == receipt.raw_sha256` = `a24bcbb2…6bd9`；`prepared != payload` |
| DSH usage | `{input 11, cacheRead 2, cacheWrite 0, output 5, reasoning 0, total 18}` 与 receipt usage **字段级相等** |
| 模块身份 | 10/10 loaded module SHA == `git show 4bd4803` |

### 4.2 Tool 两轮 — `20261118T000042Z-reviewer-tool-b17a4a2d`，exit 0

| 项 | 值 |
|---|---|
| 账本 | 2 Reservation / 2 Claim / 2 Attempt / 2 Receipt / 2 Settlement；`broker_messages=4`；counter 2 |
| 两轮 | `mode=tool_once`（step 0，input_bound 1205）→ `mode=tool_final`（step 1，input_bound 1998）；prepared/payload 两对各自匹配且互不相等 |
| 工具闭环 | DSH events：`tool_calls=1`（`skill_lookup {"skill_id":"binary_search"}`）、`tool_results=1`（真实 skill JSON 内容）；第二次请求的输入上界比第一次多 793 tokens，证明 tool result 进入第二请求，不只是“计了两次 request” |
| Usage | 两条 usage 均与对应 receipt 相等 |

### 4.3 Resume — `20261118T000049Z-d3-c01-resume-84b42ad6`，exit 0

| 项 | 值 |
|---|---|
| 进程 | 两次独立 `podman run` 的真实 Candidate 容器（`run-candidate-resume-turn1`/`turn2`，UTC 00:00:52–00:00:57），不是同一进程内模拟 |
| Session | turn1 `start_session`（resume.used=false，14 行）；turn2 `resume_session`（used=true，24 行，`resume_marker_count=1`） |
| 账本 | 2 Reservation/Claim/Attempt/Receipt，logical_step 0/1，`call_id` 不同，均 `SETTLED`；counter 2；无旧 Attempt 重放（旧 Attempt 保持 SETTLED，未新增重复行） |
| Usage | 两轮 usage 均与 receipt 相等 |

证据：`artifacts/reviewer-g3d/r3-dsh/{echo,tool,resume}`；`logs/rv-r3-*.log`。

---

## 5. R4 — 崩溃 / 取消 / 断连 / 并发 / Streaming

所有 Case 由本 Reviewer 亲自执行 `d3_runner.py`（fresh evidence dir），并从原始 `state/*.json`、`recover/inspect-*.json`、`receipt/`、DB 只读副本独立重算，不采信 Owner 的 `checks.json` 文字。

### 5.1 两个以上真实崩溃窗口 + Broker 权威

| Case | 真实崩溃证据 | 崩溃时状态 | 重启后（独立复算） |
|---|---|---|---|
| **C04** `20261118T000141Z-d3-c04-2d260f18` / `after_attempt_start_before_fake_send` | trusted 容器 `Status=exited, ExitCode=97`，env `G3B_TEST_MODE=1`+hook；客户端仅收 ack 后 EOF（0.05 s） | Attempt `ATTEMPT_STARTED`，intent `CONSUMED`，Receipt=0，counter=null，Reservation `PENDING 0.00155`，messages=1 | 新 Trusted exit 3 `ADMISSION_REPLAYED_AFTER_RECOVERY`；Attempt `SETTLEMENT_UNCERTAIN/NO_RECEIPT_AFTER_CRASH`；attempts/claims/receipts/messages **全部不变**；无自动发送 |
| **C05** `20261118T000157Z-d3-c05-49d74316` / `after_response_before_settlement` | 同上 `exit 97`，hook 对应 | Attempt `RESPONSE_OBSERVED`，Receipt=1，counter=1，Reservation `PENDING 0.00155`，messages=1 | 重启：验证 receipt+usage → `SETTLED`，Reservation `OK 0.001022`，messages **1→2（恰好一次 settle）**；第二次重启：messages 仍 2、receipt 仍 1、counter 仍 1（**0 次额外 settle**） |
| **C06** `20261118T000428Z-d3-c06-34f1657d` / `after_broker_settle_before_journal_mark` | 同上 `exit 97`，hook 对应 | Broker `OK 0.001022`，messages=2，Attempt 仍 `RESPONSE_OBSERVED` | 重启以 Broker 为权威 → `SETTLED`；messages 仍 2（无二次 settle，无 `WORST_CASE_HELD`）；第二次重启不变 |

**结论**：无自动重发；无 receipt 时保守 `PENDING 0.00155` 且不降级为 FREE；有可信 receipt 时至多一次结算；Broker 已结算时不被 Journal 降级。

### 5.2 取消 / 断连

| Case | 真实观测 |
|---|---|
| **C07-before** `20261118T000215Z-d3-c07-before-bca1683b`（Broker SIGSTOP 后发送前取消） | 客户端收 `ack` 后 `CANCELLED`；Attempt=0、Claim=0、Fake=0；Reservation `PENDING 0.00155` 保留（不是 Fee=0）；intent `HELD_UNCERTAIN` |
| **C08-disconnect** `20261118T000231Z-d3-c08-disconnect-79c56b43`（收到 ack+首个 chunk 后 mid-stream 关闭） | `closed_mid_stream=true`；最终 1 Attempt `SETTLED`、1 Receipt、Reservation `OK 0.001022`；无伪造成功、无 FREE |

### 5.3 C10 Streaming 时钟（Reviewer 自算）

- 原始 DSH event `time0 = 1794960191242` ms（`traces/dsh-result.json`）。
- 我在同一 Host 采样时钟对：`epoch=1794960254.478468`、`monotonic=1862811.479477`，offset `1793097442.998991`。
- 换算 `T(first DSH chunk) = 1862748.243009`；Fake `first_chunk_flushed = 1862748.242740`；Fake `exit_after_finish = 1862750.248273`。
- **`T1 < T2` 成立**（T1 比 Fake exit 早 **2.0053 s**；与 Fake 首 chunk 相差 0.3 ms，属毫秒取整）。不是 buffered replay。

### 5.4 C11 两级证据严格分离

| Run | 观测 | 分级/结论 |
|---|---|---|
| **C11-same** `20261118T000250Z-d3-c11-same-db01440e`（受控双真实 Controller/UDS 同身份） | 两客户端 payload sha256 相同（`183a9e43…`）；A：ack/chunk/chunk/**finish**；B：ack + **`ATTEMPT_ALREADY_STARTED`**；1 Reservation/Claim/Attempt/Receipt，counter 1，messages 2，2 个 admission 行 | **受控 same-claim 负例**：至多一个 Claim/Attempt/Fake；输家有精确稳定错误码 |
| **C11-real** `20261118T000316Z-d3-c11-real-48e4d779`（两个真实 Candidate 同时 running） | 两个独立 DSH session → 2 个 identity（step 0/1）、`identity_digest`/`call_id` 两两不同、2 Claim/2 Attempt/2 Receipt、counter 2、均 SETTLED | **两个合法独立请求**；**不是** real-DSH same-claim，不拼接 |

我**没有**构造出“两个真实 DSH 客户端共享同一 business identity/同一 Claim”；按任务书 §9.1，该证据级别缺省，只能以受控负例覆盖 same-claim 不变量，报告不得写成 real-DSH same-claim PASS。

---

## 6. R5 — 回归、LiveGate 与清理

### 6.1 固定 OCI 全量（Reviewer 自建只读物化）

- 物化：`git archive 97230a0 | tar -x -C /tmp/reviewer-g3d-oci/project` + `chmod -R a-w`；`/project` 以 bind 挂载（文件 0555/0444，root-owned）。
- 命令：`podman run --rm --network none --http-proxy=false --unsetenv-all --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 … --rootfs artifacts/security/rootfs /opt/python/bin/python3.11 -B -m pytest tests/ -q --junitxml=/evidence/junit.xml` + 4 个显式 deselect（3 个 `test_manifest_tree_*` + 1 个 `test_admission_launcher_uid_is_not_the_socket_peer_uid`，均需 host root/tar）。
- 结果：**916 tests / 909 passed / 0 failed / 0 errors / 7 skipped / 4 deselected，exit 0**（100.69 s）。JUnit 独立解析确认。
- 7 skipped 全为环境/root-only 类别（rootfs 无 tar/git、uid 65534）：`test_create_run_layout_applies_exact_permissions`、2 个 0660 显式 gid 测试、foreign peer uid 测试、foreign-owner stale socket 测试、`test_runner_does_not_modify_product_src`、既有 external probe mount 测试；这 4 个 deselect + 7 skip **未被写成“920 全跑”**。

### 6.2 Host targeted / full / Node / Ruff

| 项 | 结果 |
|---|---|
| `tests/integration/g3d` | **144 passed**（含 4 个 OCI 中因 root 被跳过的测试） |
| `tests/integration/g3_bridge` | **31 passed** |
| `tests/integration/g3c` | **110 passed** |
| `tests/unit/security/test_gates.py` | **14 passed** |
| Host full `pytest tests -q` | **920 tests / 917 passed / 2 failed / 1 skipped**，exit 1；2 failed = `test_required_files_exist_and_are_read_only_text`（可写 checkout 的 `config/dsh/target-runtime.patch.yml` 0644）与 `test_all_live_entrypoints_remain_blocked`（子进程未继承 `PYTHONPATH`，`ModuleNotFoundError` → exit 1≠3），均为已记录的 host-only 环境语义，不是产品回归 |
| Node guard | `RBG_TEST_PYTHON=/root/.local/bin/python3.11 node --test tests/precheck.test.mjs tests/guard-pr1.test.mjs` → **19/19 pass**，exit 0 |
| Node skill | `npm run build` exit 0；`node --test test/plugin.test.mjs` → **8/8 pass**，exit 0（Host 运行，非 Candidate 沙箱，分级已注明） |
| Ruff | `ruff check scripts/g3d tests/integration/g3d` → **All checks passed**，exit 0 |
| Git 状态 | Node build 后（本报告落盘前）0 行 dirty；build 未产生 tracked 改动 |

### 6.3 LiveGate / 0-Key / 清理 / canonical

- key-like env 名 0；无 `.env`；`run_live.sh` exit 3；LiveGate BLOCKED（4 reasons）。
- 全部 Run 结束后：`podman ps -a` **空**；`at-g3d*` 容器 **0**；无 `controller_entry`/`trusted_entry`/`candidate_entry`/`fake_backend` 孤儿进程；`artifacts/g3d/runs` 只剩 2 个 D1 之前的旧 `uds-*` 目录（非本次产生）；`rootfs/evidence` 不存在。
- canonical：rootfs `25491e45…`、deps `e07729d7…`、stage `e1ff1449…` 前后一致；`git status --porcelain -uall` 在本报告落盘前为 0 行，落盘后唯一变化是新增未跟踪文件 `docs/REVIEW_G3D_INDEPENDENT.md`（无任何既有 tracked 文件改动）。
- 证据：`r5-regressions/{cleanup-and-canonical.txt,host-*.log,node-*.log,ruff.log}`、`logs/oci-*`。

---

## 7. 对 P0 的逐项证伪尝试

| P0 类型 | 我的证伪尝试 | 结果 |
|---|---|---|
| Candidate 读可信状态 | 读 DB/WAL/SHM/attempts/admission/broker/controller/policy/ready/receipts；CONTROL 只读挂载；userns 后重试 | 全部 `ENOENT` 或 `EACCES`；无 mount；**未成立** |
| Candidate 写/替换可信状态 | O_CREAT/O_TRUNC、unlink、chmod、mkdir、rename、symlink、hardlink；前后 SHA/行 | 全部 `ENOENT`；无字节/行变化；**未成立** |
| 未授权/重复 Fake | 24 个协议负例（含 262 200-byte 大帧）后账本快照；slowloris 第 9 条连接；同 payload 连续两次；Socket bind/unlink | 负例后 Attempt/Claim/Reservation/Receipt/Fake 全 0；重放第二次 `ATTEMPT_ALREADY_STARTED`、仅 1 套账本；释放后仅合法请求 1 笔；**未成立** |
| 假结算/错误释放 | C04/C05/C06；C08 断连；C07 取消 | 无 receipt 时 `PENDING 0.00155`；有 receipt 恰好一次 settle；断连不 FREE；**未成立** |
| 绕过 Controller 获得发送能力 | 导入 Broker、直连私有 socket/FD、Reserve/Claim/Settle kind、伪造 admission/call_id | ModuleNotFoundError/ENOENT/UNKNOWN_KIND/UNKNOWN_FIELD；**未成立** |
| 假成功 finish（无真实 Fake） | 所有错误路径终止于 `error`；崩溃窗口无 finish；半关闭后有真实 receipt 才 finish | 未出现无 receipt 的 success finish；**未成立** |

---

## 8. P0 / P1 / P2 清单与残余处置

### 8.1 P0（阻断）：**无**

### 8.2 P1（必须修复后复审）：**无**

### 8.3 P2（已登记、不阻断限定范围；需维护者知情/决定）

| ID | 残余 | 我的判定 |
|---|---|---|
| **R2-P2-a** | Candidate session 无磁盘硬配额（`/work/session` 是 host bind mount，不受 `/work` tmpfs 512 MiB 限制） | **接受为 P2**，但**需维护者明确接受**；本 Gate 不主张磁盘 DoS 防护 |
| **R2-P2-b** | 内核允许 Candidate 创建嵌套 userns（可挂自己 ns 的 tmpfs；`mknod` EPERM、trusted ptrace ESRCH）；对 root-owned state 仍 `EACCES`（含 unshare 后） | **接受为 P2 内核攻击面**；不作为“userns 已安全”外推 |
| **R2-P2-c** | `SO_PEERCRED` 是 OS 身份，不是 per-Run token；拿到 live 路径的同 UID 旧 Run 仍可连接 | **接受为 P2**（随机 Run 路径 + mount namespace + host 0700 父目录）；不主张 per-Run 认证 |
| **D3-P2-a** | 未证明 real-DSH same-claim；只有受控双 Controller/UDS 负例 | **接受**（按 §9.1 的允许降级；两级证据分开） |
| **D3-P2-b** | C09 Broker 仅 SIGSTOP，不重启；Reviewer **未重跑** C09 | **UNVERIFIED**；不据此主张 Broker 进程级 crash-recovery |
| **D3-P2-c** | C12 10+ 重启只恢复旧状态、不接新 admission；Reviewer **未重跑** C12 | **UNVERIFIED**；不外推持续接单稳定性 |
| **D3-P2-d** | C07 “双流”是单飞 Controller 下 1 active + 1 queued，不是两个并发 Provider 调用 | **接受**；不主张并发 Provider 流 |
| **OPS-P2-a** | 固定 OCI 4 deselect / 7 skip；rootfs 无 tar/git、uid 65534 | **接受**；Host 补跑覆盖；不写“920 全绿” |
| **OPS-P2-b** | Host full 2 个 host-only 环境失败（可写 checkout 的 config mode；子进程 PYTHONPATH） | **接受为环境**；未隐藏、未改断言；OCI 为权威 |
| **OPS-P2-c** | Node 测试在 Host 运行，不是 Candidate 内 Node | **接受**；真实 adapter 由 real-DSH 覆盖 |
| **OPS-P2-d** | Launcher cleanup 在 preflight 早失败（run dir 尚未创建）时把 `run_dir_not_deleted` 计为 problem（我首轮 OCI 后 rootfs 漂移导致的 preflight 失败中观察到；无安全影响） | **P2 证据卫生**，建议后续小修；不影响本次裁定 |
| **ENV-P2-a** | 运行固定 OCI 会在 rootfs 生成空 `/evidence` 挂载点，必须在下次 preflight 前删除 | **已按允许方式处理并记录**；非产品漂移 |

### 8.4 对 Owner 残余登记的复核结论

- `D2-R1`（嵌套 userns）：**接受**（附我自己的 userns+DAC 证据）。
- `D2-R3`（磁盘配额）：**接受为 P2，需维护者决定**。
- `D2-R6`（per-Run 路径非 token）：**接受**。
- `D3-R1`（C11 两级）：**接受**，两级严格分开。
- `D3-R3`（Broker 不重启）：**接受为“未证明”**，不当作已证明。
- `D3-R5`（C10 时钟）：**接受**；我用独立时钟对重算通过。
- `D3-R7`（OCI deselect/skip）：**接受**；Host 补跑 4 项通过。
- `D4-R1`（OCI 物化方式）：**接受**；我的 0644→`chmod -R a-w` 物化得到与 Owner 相同的 916/909/0/7/4。

---

## 9. 明确未验证项（UNVERIFIED）

1. C02（Candidate 发送前 SIGKILL）、C03（Claim 后 Attempt 前崩溃）、C09（Broker SIGSTOP/Fake 卡死/首帧 Stall）、C12（10+ 重启/资源压力）**未由 Reviewer 重跑**；其结论仅来自 Owner 证据，本报告不背书。
2. cgroup `pids-limit=8` / `memory=128m` 的 Candidate 压测（D2-12 部分）未重跑。
3. real-DSH same-claim 竞争未构造；只有受控负例。
4. Broker 进程级 crash/restart 恢复、持续接单/长期运行稳定性未证明。
5. Candidate Session 磁盘硬配额、跨 Run 同 UID 路径攻击未验证（P2）。
6. 内核/容器运行时 0day、宿主 root 攻陷、供应链、真实 Provider/Invoice/exactly-once、跨 Runner/跨内核可移植性不在主张内。
7. Node 测试仅在 Host；未在 Candidate 沙箱内重跑 Node。
8. 未覆盖的失败路径（如真实内核构造 `PEERCRED_UNAVAILABLE`）只以静态代码与 Host 单测覆盖，未在容器内制造“SO_PEERCRED 不可用”的内核状态。

---

## 10. 裁定、允许的下一步与 STOP

- **唯一裁定：`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`**。
- 该裁定允许 Lead 以“限本机、冻结 SHA、已验 Runtime/内核”的范围归档 G3-D，并**仅在此范围内**继续 G3-D 收尾；**不允许**据此进入 G4/G5/Live，**不允许**改写为 `M0_GO`、`LIVE_APPROVED`、`G4_PASS`、`G5_PASS`。
- `D-REVIEW-01` 仍为 `NOT_RUN`：本报告是 Reviewer 交付物，但矩阵/Packet 的 `D-REVIEW-01` 行由 Lead 归档时处理；我未修改矩阵（仍 52 PASS / 1 NOT_RUN，无矩阵文件改动），也不把该行改为 PASS。
- **STOP**：Reviewer 不 commit、不 push、不修改实现/证据/Packet/历史 docs；不自动继续 G4。

---

## 11. 证据索引与最小复现

| 内容 | 路径 |
|---|---|
| Run 索引 | `artifacts/reviewer-g3d/RUN_INDEX.md` |
| R0 身份/Packet/加载 | `artifacts/reviewer-g3d/r0-identity/` |
| R1 静态 | `artifacts/reviewer-g3d/r1-static/` |
| R2 自建 Probe/结果 | `artifacts/reviewer-g3d/r2-probes/{rv_probe.py,rv_common.py,r2_runner.py,RESULTS.json,RUNS.md,old-bypass-pairing.csv,runs/**}` |
| R3 真实 DSH | `artifacts/reviewer-g3d/r3-dsh/{echo,tool,resume}` |
| R4 故障/并发 | `artifacts/reviewer-g3d/r4-faults/{c04,c05,c06,c07-before,c08-disconnect,c10,c11-same,c11-real}` |
| R5 回归/清理 | `artifacts/reviewer-g3d/r5-regressions/` |
| 原始日志 | `artifacts/reviewer-g3d/logs/`（含 `oci-full.log`、`oci-junit.xml`） |
| 账本对账工具 | `artifacts/reviewer-g3d/analyze_ledger.py` |

最小复现（Reviewer 实际使用的命令形态；每条均 fresh `--evidence-dir`，`podman ps -a` 空为前置）：

```bash
cd "/root/Autonomous Teacher"
S=artifacts/g3d/stage-20261117T221955Z
# R2（自建 Probe；容器生命周期复用冻结 launcher）
PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B \
  artifacts/reviewer-g3d/r2-probes/r2_runner.py --mode attack --stage $S \
  --evidence-dir artifacts/reviewer-g3d/r2-probes/runs/attack
# R3
PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case reviewer-echo --scenario echo --session reviewer-g3d-s1 --stage $S \
  --evidence-dir artifacts/reviewer-g3d/r3-dsh/echo
# R4
PYTHONDONTWRITEBYTECODE=1 /root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py \
  --case d3-c05 --stage $S --evidence-dir artifacts/reviewer-g3d/r4-faults/c05
# R5 固定 OCI：见 §6.1 的 podman 命令；Ruff/Node 见 §6.2
```

**报告 SHA-256**：在生成后于 `artifacts/reviewer-g3d/REPORT.sha256` 与发给 Lead 的消息中记录。
