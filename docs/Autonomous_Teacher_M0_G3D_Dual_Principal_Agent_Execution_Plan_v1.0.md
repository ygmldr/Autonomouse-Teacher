# Autonomous Teacher M0 — G3-D 双 Principal 隔离实施与独立审阅任务书

**版本**：v1.0 · 2026-11-18 · **执行对象**：Lead Agent / Implementation Agents / Independent Reviewer  
**仓库**：[`ygmldr/Autonomouse-Teacher`](https://github.com/ygmldr/Autonomouse-Teacher) · **制定时远程 HEAD**：`fff36232687afb779befb49fb6e2a10cedbcb7fd`  
**G3-C 已验收产品实现**：`b2f6af054555705192c4e1ae3019a68078764736` · **G3-C verdict**：`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`  
**设计依据**：`docs/M0_G3D_OS_BOUNDARY_DESIGN.md`（D0，commit `981e4ed016ed689118428a6f1d0ffdfe17af5e51`）；本文件作为 **D1/D2/D3 的实施补充规范**，不重写 D0 的威胁模型、12 项攻击计划与已记录的本机可行性探针。  
**本轮授权范围**：仅无 Key / Fake Provider / 断网 / 隔离实施、真实 OS 拒绝测试、跨主体合成回归、独立审阅。**G4/G5/Live/真实模型/真实 HTTP/注入 API Key 均未授权。**

> **唯一目标**：让不可信真实 DSH Candidate 在独立 OS Principal 内仍能通过固定 AF_UNIX Socket 完成受控合成调用，但无法读取、修改、启动或绕过 Trusted Controller / Broker / Policy / Admission / Attempt Journal / Receipt；用实际 UID/Namespace/Mount/errno/SQLite/Trace 证明，而不是靠架构图或 Mock。  
> **验收分界**：G3-C 已通过不等于 G3-D 已通过；D0 `CAN_ISOLATE`（本机可行性）不等于 D1 部署通过；D1 能 Echo 不等于 D2 恶意候选被阻断；D2 拒绝不等于 D3 崩溃/恢复正确。禁止跨级签 PASS。

---

## 0. 给 Lead 的首屏（必须先读）

1. **遵守仓库 `AGENTS.md`**：Lead 只协调、分派、代码审阅、复现与 Gate 决策；具体修改必须委派给子 Agent。独立 Reviewer 与实现者分离；不得用同一 Agent 的自测冒充独立证据。
2. **先进行 D-G0 基线核对**：读取现有 HEAD、`AGENTS.md`、G3-C v2 报告、Errata、D0 设计、G3-C 最新 Controller/IPC 代码；如工作区有未提交改动，先停并报告，不得覆盖。
3. **实施顺序**：`D-G0 → D-P0（小型证据/环境收口）→ D1（隔离 + 真实 DSH 正向）→ D1 Gate → D2（12 类真实攻击）→ D2 Gate → D3（跨主体故障/资源回归）→ D3 Gate → Independent Review → STOP`。D-P0 可与 D1 的只读 Stage 设计并行，但不能因并行共享可变 rootfs/deps。
4. **D1 必须先跑通正向**，再做 D2。D1 连接失败不得用 Socket `0666`、合并 UID、挂载可信 DB 给 Candidate、关闭 peercred 或改用 Mock 等方式“修好”。环境不满足则标 `BLOCKED_NEEDS_ENVIRONMENT` 并 STOP。
5. **本轮全部调用 synthetic**。没有真实 Key、实际 Provider API、外部网络、自动 LiveGate 解锁；`run_live.sh` 仍 exit 3，`LiveGate` 仍 BLOCKED。禁 `podman pull`，禁外部下载依赖。
6. **交付**：实施报告、源码 Diff、冻结 SHA、逐案矩阵、命令/UTC/退出码、Candidate 原始攻击 Probe、内核身份/拒绝证据、DSH 事件、DB/Receipt 对账、Review Packet。独立 Reviewer 出具限定范围裁定后 **STOP**，不进入 G4。

### 0.1 最终允许的裁定

- `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`：**必须**同时具备 D1 正向跨 Principal、D2 实测拒绝、D3 无 Key 恢复一致性、独立复核；仅限本机已验 Runtime/内核及已冻结 SHA。
- `PARTIAL`：主链可工作，但至少一个 Gate 的证据/用例未完全满足；不得说“已建立可信 OS 边界”。
- `FAIL`：复现未授权 Fake 发送、同一 Claim 重复 Fake、Candidate 可读/写可信状态、无 Claim 直达 Fake、伪造成功结算、错误释放费用等。
- `BLOCKED_NEEDS_ENVIRONMENT`：双 Principal / namespace / UID map / cgroup / UDS 根本无法真实建立；不得用模拟权限替代。
- **永远不是** `M0_GO` / `LIVE_APPROVED` / `G4_PASS` / `G5_PASS`。

---

## 1. 冻结输入、历史结论和不可混淆的证据

### 1.1 Git 身份

| 对象 | 固定值 / 操作 |
|---|---|
| 上轮 G3-B Base | `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3` |
| G3-C v1 实现 | `e6fde1cdf0bec9e957e98d569b257c8f17dfa363` |
| G3-C PR1 / D1 必须基于的产品实现 | `b2f6af054555705192c4e1ae3019a68078764736` |
| D0 设计归档 | `981e4ed016ed689118428a6f1d0ffdfe17af5e51` |
| 本任务制定时 `main` | `fff36232687afb779befb49fb6e2a10cedbcb7fd`；执行时须重新读取，不得盲信 |
| G3-C v2 报告 | `docs/REVIEW_G3C_INDEPENDENT_v2.md` |
| D0 设计 | `docs/M0_G3D_OS_BOUNDARY_DESIGN.md` |
| 历史矩阵 | `docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv`：**C 53 PASS / D 16 NOT_RUN（历史状态，不得就地覆写历史证据）** |

Lead 必须保存以下输出的原始字节和 UTC：

```bash
set -euo pipefail
git status --porcelain=v1
git remote -v
git rev-parse HEAD
git cat-file -t b2f6af054555705192c4e1ae3019a68078764736
git diff --stat b2f6af054555705192c4e1ae3019a68078764736 HEAD -- src tests spikes plugins
git log -10 --format='%H %s'
```

制定本文件时已查过远程 `b2f6af0..fff3623`：在 `src/`、`tests/`、`spikes/`、`plugins/` 没有后续改动，后续变化在文档/复现脚本。**执行时再次核验**，若不同必须记 Drift，不能默认以旧 SHA 覆盖新代码。实现使用独立分支/Worktree，Agent 并行时分别锁定输入 Commit；冻结前不得将不确定子 Agent 改动直接合并到主分支。

### 1.2 G3-C 已证实与尚未证实

- G3-C v2 独立 Reviewer：v1 三项 P1（DSH 证据误标、双 Controller SQLite 冷启动竞态、矩阵 25 个坏路径）均关闭；无新 P0/P1。独立 Host 冷启动 20/20、固定 Rootfs 5/5、Journal 竞争 20/20，原始结果需沿报告追索。
- 功能/账本的 G3-C PASS 仅限 **同容器/无 Key/Fake** 下的 Claim、Recovery、Cancel、Deadline、Usage 和 Streaming；OS 信任边界仍 `B0-02=BLOCKED`。两个真实 DSH Candidate 同 Claim 的实验尚未完成。
- G3-C v2 的主机回归记录 `773 passed / 2 failed / 1 skipped`：两个失败属于已披露的测试环境兼容性，不得隐去；固定 OCI 有 `pgrep` 缺失与 `/tmp` noexec 下 Wrapper 无法执行的用例（本轮 D-P0 收口）。
- G3-C Packet v2 `2017 files / 2015 hashes OK` **是归档报告的核验声明**，本任务不要求重新打包或改写旧 Packet；Review Packet 本身的哈希不能证明使用了正确实现版本。
- G3-C v2 Reviewer 的 `R4` 摘要写出了易混淆的等式。实际代码只有两对身份关系，参见下一节；以真实 Controller 代码和 Broker Claim 字段为准。

### 1.3 两种 Digest 不得合并（G3-C 报告勘误）

```text
PreparedProviderRequest.request_digest == BrokerClaim.request_digest
FakeOutboundPayload_SHA256           == FakeReceipt.raw_sha256
```

这两种 Digest 用途不同：Prepared 摘要保护授予 Claim 的语义请求；出站字节摘要保护获准的实际 Fake Payload（包含 Nonce）。**不得**要求两个摘要互相相等，也不得省略关联它们的 `call_id/reservation_id/attempt_id/nonce/receipt_id`。要求 D-P0 增加 append-only 勘误，并让 Reviewer 核对原始 R4 脚本的真实比较逻辑；严禁改写 v2 Reviewer 原文。

---

## 2. 安全模型与 OS 可信边界（直接沿用 D0）

### 2.1 可信与不可信主体

| 属性 | Candidate（恶意代码可执行） | Trusted Controller / Launcher |
|---|---|---|
| 部署 | 独立 Podman 容器；container UID 0 映射到 LXC UID **65534** | 独立 Podman 容器；LXC UID **0**，Host Root Launcher |
| Namespace | 独立 user/mount/pid/net/ipc/uts/cgroup | 独立 mount/pid/net/ipc/uts/cgroup；不得与 Candidate 共 mount/uid |
| 代码 | 真实 DSH SDK + 官方接口 `LlmAdapter` +最小 Runner / Adapter | Controller、Broker、Fake、Admission、Attempt、Receipt 处理 |
| 文件 | 只读 Candidate Stage、受限 Session、只读 IPC 挂载、无 `state` | 私有 `state` RW、IPC RW、Evidence 私有、Broker/Fake 代码 |
| 网络 | `--network none`，不持有 Provider Key | 本 Gate 亦 `--network none`，Fake stdio |
| 通信 | 唯一批准通道 `/work/g3b/bridge.sock` | 以 `SO_PEERCRED` 验证候选身份，Controller 独占 Reserve/Claim/Attempt/Settlement |
| 工具 | Candidate 可执行本地工具（按不可信任意代码对待） | 不读取/执行不可信 Candidate Session 数据，不把其文件作为 trusted 配置 |

**保护资产**：Broker DB/WAL/SHM、Admission、Policy、Attempt Journal、Receipt/received-count、Controller 配置、未来 Key 路径、Launcher 控制接口、宿主 Podman Socket。Candidate 不得见到完整 repo、`.git`、`artifacts`、`/work/state`、Trusted 源码或 Broker 进程/FD。

**安全不主张**：不验证内核/容器运行时 0day、宿主 root 攻陷、供应链完整性、真实 Provider invoice、远端 exactly-once；Rootful Podman 是已记录的受信基础。不同 Runner 需重测 D0 §3 探针；本机 `CAN_ISOLATE` 不可迁移为通用 PASS。

### 2.2 OS 权限不变量

1. Candidate 的真实宿主 UID 与 Trusted 不同；**不能**只看容器内 `id -u`，必须保存 uid_map/gid_map 与 trusted 侧 `SO_PEERCRED`。
2. Candidate 从挂载树中看不到受保护状态：`/work/state` 与 Provider/Controller/Broker 私有路径应 `ENOENT`；防御纵深的额外故意挂载探针应得 `EACCES/EROFS`，并分别标注，不得混淆。
3. Candidate 只能经已审核目录和 `bridge.sock` 与 Trusted 通信：IPC 目录 Candidate 侧只读；目录不得 Candidate 可写，Socket 不得 `0666`；私有其他 UDS 不暴露。
4. 即使 Candidate 知道 `call_id`、Reservation ID 或 Admission 信息，也不能修改 Broker 状态；发送者必须是 Trusted Controller，且每次 Provider 请求独立 Reserve、Bound Claim、持久 Attempt。
5. `Guard` 是辅助检查、**不是**可信授权边界。Guard 缺失不能让 Candidate 获得 DB/Policy/Claim 权限；Guard 配置非法应失败关闭。
6. 账本保守状态不能因 SIGKILL/EOF/取消重启变成 `FREE/NOT_DISPATCHED`；Claim/Receipt 不得跨恢复重放导致第二次 Fake。

---

## 3. 工作分派、PR 顺序与阶段边界

| 包 | 实施 Owner | 可并行 | 主要输入 → 输出 | STOP 点 |
|---|---|---|---|---|
| `D-G0` | Lead + Evidence Agent（只读） | 否 | SHA/OCI/DSH/Rootfs/Deps/Stage 真实身份；无凭据/LiveGate | Drift/环境异常 STOP |
| `D-P0` | Docs/Test Agent | 是（不得改共享 Stage） | Digest 勘误；两项 OCI 测试移植；正确源码 Overlay | 结果写入 D1 前置证据 |
| `D1-A` | IPC Contract Agent | 可与 Stage Agent 并行 | `BridgeServer` 最小 Socket Mode/GID/Peercred/Ready | 单测/旧兼容回归 |
| `D1-B` | Stage/Launcher Agent | 可与 IPC 并行 | 不同 Principal 启动、Mount/UID/Env 检查、Cleanup | 双主体正连运行 |
| `D1-C` | Integration Agent | D1-A/B 合并后 | 真实 DSH Echo + Tool；Ledger/Receipt 双端证据 | **D1 Gate：FAIL 即 STOP，不开 D2** |
| `D2` | Adversarial Agent（非 D1 实现者） | D1 PASS 后 | D2-01..12 真实候选攻击、系统调用结果、内核拒绝 | **D2 Gate：越权即 FAIL/STOP** |
| `D3` | Recovery/Regression Agent | D2 PASS 后 | Crash/Cancel/Replay/Stream/Stress，固定 OCI 全量 | D3 Gate |
| `D4` | Evidence/Reviewer Agent | D3 冻结后 | 复现命令、Packet、独立审阅；不改生产源码 | **最终 STOP** |

每包实现分开 Commit，Lead 审核最小 Diff 与升级路径。不以 Agent 自称完成代替动态验证；不自动进入 G4。对任一 Gate 存在 P0/P1：锁定当前不通过结论、停止后续实测、按最小补丁重新审核该 Gate；无需扩大成新的全量架构项目。

---

## 4. D-G0：环境、源码与威胁假设冻结

### 4.1 必须记录

- `git status/HEAD/merge-base/PR diff`；Controller、IPC Server、Admission、Broker、Fake、Node Adapter 实际 Blob SHA。
- Podman/crun/kernel/LXC 身份，主机真实 uidmap/gidmap，`/etc/subuid`、`/etc/subgid` 可用性，namespace、SELinux/AppArmor/seccomp 配置，cgroup v2 controllers。
- 固定 Runtime：rootfs（报告 `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`）、deps（`e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`）；G3-C 旧 stage（`fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`）**不是** PR1 源码 Stage。
- D0 报告中本机 Rootful Podman `4.9.3` + crun `1.14.1` + LXC 嵌套 UIDMAP 是当日环境事实，**不要写死为今天的 PASS**；必须实际跑一遍 `CAN_ISOLATE` 前置探针。
- `run_live.sh` exit 3；`LiveGate.inspect` BLOCKED；环境中没有真实 Key/Token 注入；`--network none` 与关键文件权限可复验。记录环境变量**名称集合或敏感变量数量**，不打印任何值。
- 被测 DSH 必须是真实 `0.2.2-rc.2` 固定版本；不能用自建“Fake SDK”证明公开 Provider 扩展成功。Node/Adapter 产物及编译 SHA 固定。

### 4.2 Stage identity 硬要求（前次踩坑）

旧 G3-C v2 Packet 的 R5 示例只挂冻结 Stage，加载 `e6fde1c` 的旧 `attempts.py`；本仓库后来新增的 `scripts/g3c/reproduce-coldstart-with-src-overlay.sh` 是已提供的纠错辅助。**D1 不得重复这个错误。**

D1 要生成新的独立 `{trusted,candidate}` Stage；Trusted 产品模块必须来自同一经批准实施 SHA，不能从未更新的旧 `stage/src` 混装。运行时至少记录并测试：

```python
import inspect
from autoteacher_m0.bridge import controller, attempts, ipc_server
print(inspect.getfile(controller), inspect.getfile(attempts), inspect.getfile(ipc_server))
```

然后对每个已加载模块的实际文件原始字节 SHA 与 `git show <approved-impl>:<path>` 比较；允许 Stage 中受控构建的文件，但需独立 Manifest 列出源 Blob、编译产物哈希、Runtime 版本。**仅仅 `git rev-parse` 与 Packet hash 一致，不算通过**。

### 4.3 D-G0 STOP

任何 UID Map/Namespace/Rootfs/Deps 实测与 D0 不兼容、出现凭据/外网、Stage 身份不可证明、工作区来源冲突，均 `BLOCKED` 并停止。不要为了通过环境测试，在宿主上直接运行未经隔离的 DSH 插件。

---

## 5. D-P0：证据勘误与 G3-C 测试可移植性收口

### 5.1 维护历史不变量

- 不改写 `docs/REVIEW_G3C_INDEPENDENT.md`（v1 PARTIAL）、`docs/REVIEW_G3C_INDEPENDENT_v2.md`（v2 PASS）、已冻结 Packet v1/v2、旧矩阵/旧日志；创建 append-only 说明。
- 修正 Reviewer v2 §7 的 Digest 文字，把两对 Digest 分开，并核对其原始 R4 对账程序到底对比了哪些字段。仅是报告不准确时，按 `DOCS_ONLY`；若对账代码真的比较了错误字段，增补真实负例，不能只改文字。
- G3-C v2 Packet `reproduce/README.md` 旧 R5 命令将继续存在；主入口统一指向仓库现有 **源码 Overlay** 脚本，D1 Packet 不得复制旧命令。
- 标注历史 C 53 / D 16，G3-D 使用**新**工作矩阵单独填写，不在原历史 CSV 上直接将 D 项冒充早前已跑。

### 5.2 固定 OCI 两项失败

1. 进程清理用例不得依赖不存在的 `pgrep`：优先由 Python `os.kill(pid,0)`、`/proc`（检查命名空间可见性）、`subprocess` PID/Wait 等构造可移植检查；既检查没有残余子进程，也防止因为 `/proc` 探针本身失败产生假 PASS。
2. Broker timeout 测试在 `/tmp noexec` 下不得直接执行 Wrapper 文件：用可信 Python 解释器执行测试脚本，或移到经审核的可执行只读 Stage；**不能**为了通过而去掉 `/tmp noexec`。补失败前/修复后证明、全量 OCI 重跑。
3. 若两项在新 Runner 依然因明确环境原因不能运行，记录精确 argv/exit、替代等效独立探针与 `KNOWN_ENV_LIMITATION`；不可称“OCI 全绿”。理想 D3 门槛为固定 OCI 0 意外失败；不允许扩大容器权限掩盖失败。

D-P0 **不能重新开启 G3-C 的通用架构重构**；只修测试/追溯/文档和执行环境不匹配。

---

## 6. D1-A：IPC 最小 Additive 修改（选择 D0 方案 A）

**首选**：直接复用 `src/autoteacher_m0/bridge/ipc_server.py` 的 `BridgeServer`，不引入新可信 Proxy；仅当 D0 的方案 A 在这台 Runner 上无法正确实现 `SO_PEERCRED` 和最小权限时，提交原因与最小替代方案 B 由维护者审批。**禁止**直接降级 `0666` 或同 UID 运行。

### 6.1 API 建议（具体签名由子 Agent 在源码约束下确定）

```python
BridgeServer(
    controller,
    socket_path=...,             # 保留现有固定地址策略
    socket_mode=0o600,          # 旧调用默认不变
    socket_gid=None,             # 旧调用默认不变
    expected_peer_uid=None,      # 无隔离部署的旧测试兼容
    on_ready=None,               # bind/listen + 完成权限验证之后才通知
    ...  # 原有 first_frame_deadline、request_deadline、max_connections 不变
)
```

- 严格参数校验：只接受有明确授权的 Mode（D1 建议 **`0660`**）；禁止 `0666`、`0777`，拒绝 bool/int 混用、未知 UID/GID。默认 `0600` 的老用例必须继续 PASS。
- `bind` 后设置并检查 Owner/GID/Mode。考虑 `--cap-drop ALL` 导致 Trusted 不一定具备 `CAP_CHOWN`：**优先使用 Host Launcher 事先创建的 `root:2000` setgid 目录让 Socket 继承组**，只在合法且必需时执行 `chown`；任何权限操作失败都必须拒绝 Ready/停止，不得静默放宽权限。
- 取 `SO_PEERCRED`（`SOL_SOCKET/SO_PEERCRED`），在接受连接、读取第一帧或产生 `ack` **之前**校验 `uid == expected_peer_uid=65534`；不匹配关闭并记录脱敏拒绝码（如 `PEER_UID_DENIED`）。必须保留实际 `uid/gid` 证据；不同 PID namespace 看到 `pid=0` 是已知正常情况，**PID 不得作为身份判断**。
- 这里 `expected_peer_uid` 是 OS Socket 凭据，`Admission.launcher_uid` 是业务契约字段；不要混用/偷偷改成 Trusted root `0`。显式测试两者一致性及不同字段失败情形。
- `SO_PEERCRED` 不可用/返回长度错误/异常 → **fail-closed**；不能退化为只看文件路径。候选 UID 不等于预期 UID 的连接不能收到授权 `ack`。
- `on_ready` 必须在 `listen()` 真正完成且 Mode/GID/peercred 检查能力已经就绪后调用；避免“socket 文件存在但尚未监听”的竞态。Ready 文件写在 Trusted-only State，由可信 Controller/Launcher 创建、fsync；不能让 Candidate 写 Ready。
- 保留 G3-C 已完成的 Deadline、取消、Frame Size、连接数、Streaming 契约，不加入第二套传输协议。
- Stale socket 清理只允许可信 Launcher/Controller 操作受控专属路径；使用 `lstat`、Owner/类型检查、防 Symlink 和 Run Path 逃逸。禁止 Candidate 可写父目录、符号链接替换与跨 Run 误删。

### 6.2 D1-A 测试

- `socket_mode` 默认 `0600`；显式 `0660` 时 `st_uid/st_gid/st_mode` 精确符合预期；`0666` 拒绝。
- Peer UID 65534 允许；Peer UID 0/其他值拒绝且**无 Ack / 无 Broker / 无 Fake**；若本机只能以特定身份构造探针，缺失用例标 BLOCKED，不用 Mock 冒充真实凭据测试。
- 最小权限目录 `root:2000 mode 2750`；Candidate Group 2000 可连接但无法创建/unlink/rename Socket（实际 `EROFS/EACCES`）。
- 服务重启、SIGTERM、连接超限、首帧不完整，Socket 清理与连接回收；日志不得泄漏 Prompt/Key/完整 Admission。

### 6.3 D1-A STOP

若必须把 Socket 设置为全员可写、开启共享 UID、关闭 Peercred、让 Candidate 访问 Broker DB 才能连通，直接判 **D1 FAIL/BLOCKED**。不得为跑 Echo 牺牲边界。

---

## 7. D1-B：Stage、Launcher、实际隔离容器

### 7.1 Stage 构建

产生独立 `$STAGE/trusted` 与 `$STAGE/candidate`；建议新增 `scripts/g3d/build-stage.*`、`scripts/g3d/run-*`，与现有 G3-C Stage 分离。

**Trusted Stage 允许**：冻结 SHA 对应的 `autoteacher_m0` Controller/Broker/Accounting/Bridge、Fake Provider、受控入口、必要依赖/Runtime、只读配置模板。Trusted State 单独 RW，密钥类仍不存在。

**Candidate Stage 允许**：真实 DSH 运行时、`LlmAdapter` 已审构建产物、所需配置与纯 synthetic fixture、Candidate Entrypoint 和最少公共工具；**禁止** `bridge.controller`、`accounting.broker`、`fake_backend`、`admission.json`、`policy.json`、`broker.json`、Receipt、DB/WAL/SHM、私钥、完整 repo、Launcher 脚本。

- 以**白名单**构建 Candidate Stage；不要先复制整个 `src/` 或仓库再删除“敏感文件”。
- 用 Manifest 记录每一个文件的路径、SHA、来源 Commit、构建命令和产物 Hash；验证无未知文件、Symlink 越界、未审依赖中的可写启动脚本。
- 运行 Candidate 内 `importlib.util.find_spec` 检查无法导入 Trusted Python 模块（仅静态少代码不算 OS 边界，但属 Stage 完整性证据）；Candidate Python `PYTHONPATH` 不得指向 Trusted `src`。
- Candidate 的 DSH Session 目录保留仅给 Candidate；Trusted/Launcher 不以 root 跟随 Candidate 写入的 symlink/FIFO/hardlink，不解引用归档。
- 使用一次性 Overlay/不可变构建基底，禁止在共享 Rootfs/Deps 运行时写 `.pyc`、node_modules 更新或生成挂载目标垃圾。前后完整性不一致必须追溯并 STOP。

### 7.2 宿主目录与权限

沿用 D0 §2.4：

```text
$RUN/                            # 独立随机 run_id，父目录 root 限权
  state/          0700 root:root       Trusted-only，DB/WAL/SHM/Policy/Admission/Attempt/Receipt
  ipc/            2750 root:2000       仅共享受控 Socket（候选挂载 ro）
  candidate-session/ 0700 65534:65534  仅 Candidate RW
  evidence/       0700 root:root       仅 Trusted/Launcher RW
  logs/           0700 root:root       仅 Launcher RW
```

- `$RUN` 上级目录不能被 Candidate 遍历或写入（防它在宿主扫描其他 Run 的 Socket）。IPC group 2000 在 Runner 上不得赋予其它未审身份访问资格。
- `state` 不挂载给 Candidate，连只读也不能成为**正式正向配置**；只在刻意构造的 DAC 控制探针里做“额外临时只读挂载”，严格区分证据层级。
- Candidate 容器 `uidmap 0:65534:1`，gidmap `0:65534:1` 和 `2000:2000:1`，补充组 2000；Trusted root 位于独立 Host/LXC principal。必须核对实际 `uid_map/gid_map`、`CapEff`、`NoNewPrivs`、`mountinfo`、Network Namespace、`cgroup`，不得只记录 `podman run argv`。
- 只读 Rootfs + rootfs/deps SHA；`--network none --http-proxy=false --unsetenv-all --no-hosts --cap-drop ALL --security-opt no-new-privileges`；固定 CPU/Memory/PIDs/FD；无 Podman Socket。
- Candidate Session 宿主目录可能耗尽磁盘：优先配置强制容量上限（Quota、受控的有界 tmpfs、独立限制卷等）。如本机无法提供硬上限，必须在 D2/D3 标明该 DoS 威胁为 P2 残余，并记录实际用量/监控/清理，**不得**宣称完整磁盘 DoS 防护。

### 7.3 启动顺序与清理

1. **Preflight**：冻结 SHA + Manifest、Podman/Namespace/Cgroup、无 Key、Rootfs/Deps hash、旧 Run/Socket 是否残留；验 `root:2000`、Rootfs 只读目标已存在。
2. Host Launcher 以 root 构造 `$RUN` 与配置（全部 synthetic）；权限/路径原子写入；Admission `launcher.uid=65534`、Broker 路由仍为 `offline-test-only-g3b / fixture-bridge-v1`，没有真正付款 Provider 配置。
3. 启动 Trusted 容器（限定资源，`--network none`），Controller 绑定 Socket `0660 root:2000`，Peer UID 限 65534；Server `listen` 成功后产生受保护 Ready 证据。
4. Host Launcher 仅凭可信 Ready 与实际 `listen` 检查进入下一步；不得以 Socket 文件存在或 Candidate 自写 Ready 作为成功信号。
5. 启动 Candidate（`--uidmap` + Group 2000，独立 Namespace），实际运行真实 DSH `0.2.2-rc.2`；不启动任何 Trusted 组件。
6. Candidate 正常退出/Crash 后，Trusted 独立完成 Accounting/Reconcile，Launcher 采集退出码、UID Map、Mountinfo、DSH 原始 events、Broker DB 与 Receipt（SQLite 查询只读副本）、所有关键 Raw Hash。
7. 先停止 Candidate、再停止 Trusted；`SIGTERM` 有界等待后 `SIGKILL`，清理对应 Podman 容器和 Socket；精确限制清理作用域为该 `$RUN`，绝不对不可信 Session 做跟随链接的 root 递归读取。
8. `podman ps -a --filter name=at-g3d-` 无残留、`/proc` 无孤儿进程、Socket 消失，Rootfs/Deps/Stage 前后 Hash 相等；任何异常原样写日志，不报 Clean。

不要把 Launcher 的 Host Root 与 Candidate 的 Container UID 0 混为同一 OS principal；用真实映射数值说明。

### 7.4 D1 正向 Gate（先 Echo，再 Tool）

**D1-01：真实 DSH Echo**（必须）：两个不同 Principal 存在；Candidate 只可连 `bridge.sock`；真实 DSH 输出正确；DSH usage 与 Fake 可信 Receipt 对应；Broker 1 Reservation / 1 Bound Claim / 1 Attempt / 1 Receipt / 1 Settlement，Fake received-count=1；`prepared_digest` 与 `claim.request_digest` 对应、`payload_digest` 与 Receipt `raw_sha256` 对应；无凭据/外网。

**D1-02：真实 Tool Loop**（强烈建议作为 D1 Gate 强制）：同一真实 Turn 两次 Provider 请求，**2 次独立** Reserve/Claim/Attempt/Receipt/Settlement；实际 `skill_lookup` 执行结果可以回到第二次请求，不能只数 `request/header`；Fake counter=2。

D1 若 Echo 无法真实连接（或需要放松安全限制）→ STOP。D1 如果 Echo 通过而 Tool 因 DSH 固定版本插件兼容性未通过，只可得到 D1 `PARTIAL`，不得直接开始宣称 G3-D 完成；Lead 先决定修复插件还是明确范围收缩。

---

## 8. D2：真实 Candidate 攻击用例（D2-01..D2-12）

**原则**：Probe 由与 D1 实现者不同的 Adversarial Agent 编写/执行；从 **Candidate 实际容器身份** 中发起，不在 Host Root 或 Trusted 侧模拟恶意行为。每个用例独立 Run / Container 名称 / State 快照。每次至少提交：完整但脱敏的 `argv`、实际 UID/GID/Map、Mountinfo、操作及 errno/结果、前后目标 Hash、Broker/Attempt/Receipt/Counter/Claim 行数、时间/退出码。

| 用例 | 攻击向量 | 成功防御的必要观测 |
|---|---|---|
| **D2-01** | Candidate 读取 Broker SQLite、`-wal`、`-shm` | 正式挂载树中路径不可见；读取 `ENOENT` 或 `EACCES`；DB 前后 Hash 不变。DAC 对照额外挂载必须单列，不能代替正式配置 |
| **D2-02** | 直接写、修改、截断、替换 Broker DB | `ENOENT/EACCES/EROFS`，没有事务/文件哈希变化；不能只报 SQL 操作报错 |
| **D2-03** | 读取/写入 Policy、Admission、Attempt Journal、Receipt、Fake Counter、Trusted Config | Candidate 无这些文件的实际 Mount；探针读写拒绝，Hashes/Rows 不变 |
| **D2-04** | 从 Candidate 直接执行 Broker/Python 包、连接 Broker 私有 stdio/Socket、窥 FD | 模块和二进制入口不可达，Trusted PID/FD 不可见；无 Broker 命令被接收 |
| **D2-05** | 不经 Controller 直接 Reserve/Claim/Fake；向唯一 UDS 注入 Broker 操作字典 | 业务错误或协议拒绝；Fake=0，不能出现未授权 Reservation/Claim/Attempt；真实正向请求仍成功 |
| **D2-06** | 伪造 `admission`、`authorized`、`call_id`、route/model/tools、坏 Hash/Seq/JSON、大 Frame、Socket 替换 | 受保护配置不可改；协议负例无 Claim/Fake；Candidate 无权 unlink/bind Socket；精确错误码与证据 |
| **D2-07** | 候选直接 `AF_INET/AF_INET6`、DNS、外部 TCP；探测其他 Unix Socket | 外网 `EPERM`（或相同强度的内核限制证据），DNS 不通；只有批准 Socket 可连接；不可把 `network none` 文本当作唯一证据 |
| **D2-08** | `/proc`, FD, `environ`, `/sys`, `/dev`, Mount, `ptrace`, cap, userns，访问 Podman/Docker Socket | Trusted PID/FD/Env 不可见/不可访问；不能拿到 host root/容器控制 Socket；权限/Capability/Namespace 拒绝，有真实系统调用结果 |
| **D2-09** | 不可信 Tool 执行、本地插件注入、Guard 缺失/错误配置 | Tool 只在 Candidate 沙箱活动；不能读/写 Trusted；Guard 失效不产生 Controller 之外的发送权限；非法配置失败关闭 |
| **D2-10** | Candidate SIGKILL、自我终止、半关闭 Socket、断连后重连/重启、Trusted 故障后重连 | 有序保守状态；无重发；有可信 Receipt 时按协议恢复，缺证据则 `SETTLEMENT_UNCERTAIN/PENDING`，绝不记 FREE |
| **D2-11** | 真实 Candidate DSH 正向 Echo/Tool/Resume（反误伤） | 隔离不阻断合规业务；1、2、Session 恢复分别对应正确 Calling/Cost；工具循环无漏记账 |
| **D2-12** | 并发连接、Slowloris、超大帧、子进程/FD/Memory/CPU 压力、Socket 资源耗尽 | C3 限额 + cgroup 有效；不给 Broker 越权；释放线程/FD/子进程；同 Claim At-most-one；是否具磁盘硬限额单列 |

### 8.1 D2 Attack 证据分级

- **Level A（必须）**：真实 Candidate Shell/Python/Node 进程、真实 Syscall 结果、Kernel 凭据、真实 Mount/Namespace 与前后 DB/Hash。用于 OS 边界结论。
- **Level B（必须）**：真实 DSH SDK / Adapter 的合规正向调用、真实 Controller / Broker / Fake Trace。用于证明安全没有误伤。
- **Level C（辅助）**：测试内 Mock、静态权限表、grep/配置描述、候选未挂载路径的 `find`。只能辅助，不能代替 Level A/B。

### 8.2 判定标准

D2-01..12 每项至少一个**可复验**的攻击和对应不变量。D2-01/02/03/04 是当年 G3-B Reviewer 已证明同 UID 环境可行的越权类型，必须把旧“读取/写入 DB/Policy/直接 Claim”成功结果，与当前受限身份下的实际拒绝成对展示。

`read denied` 还不够：如果 Candidate 在同一 Run 中还能修改 Broker 或发起无 Controller 许可的 Fake，应直接 P0 FAIL。不允许用“禁用所有 UDS”来取得安全 PASS，因为 D2-11 正向必须成功。

### 8.3 D2 Gate

- 12 类攻击均有代码与实际拒绝证据，尤其旧四个越权已关闭；Broker DB/Policy/Admission/Attempt/Receipt 无不可信更改；仅一个合法受控 Socket 正连。
- 无额外 Candidate/Trusted 容器与孤儿子进程；Cgroup/Network 实测有效；合规 DSH 正向仍通过。
- 若发现任一 Candidate 直接读/写可信资产、借用 Broker Claim、可重新绑定 Trusted Socket，立即停止 D2/D3 并报告 **P0 OS_BOUNDARY_FAIL**。

---

## 9. D3：跨 Principal Crash / Cancel / Replay / Recovery / Streaming

D3 所有场景使用 D1 两个真实容器、固定 Commit 的真实 DSH，**不**退化到同容器 Host Pytest；Host 单测仅作补充。

### 9.1 必须覆盖的复合场景

| 场景 | 触发 | 核心断言 |
|---|---|---|
| D3-C01 | 正常 Echo/Tool/Resume | Echo 1、Tool 2、Session Resume 不回放旧 Attempt；DSH Usage / Broker / Receipt 一一对应 |
| D3-C02 | Candidate 在 Reserve 前被 SIGKILL | Fake=0，无未授权 Claim，Controller 独立存活、清理受控 |
| D3-C03 | Claim 后、`ATTEMPT_STARTED` 前 Controller Crash | 没有 Fake，不自动补发；Reservation/Intent 保守且不能误记已发送 |
| D3-C04 | `ATTEMPT_STARTED` 后、Fake 收到前 Crash | Journal 可读、无 Fake 收据则 UNCERTAIN/PENDING、重启不自动发送 |
| D3-C05 | Fake 已写收据、Broker 未结算时 Crash | 可信收据与 Usage 被验证；重启最多一次结算，Fake Counter 不增 |
| D3-C06 | Broker 已结算、Attempt 未标 `SETTLED` 时 Crash | 重启以 Broker 已完成状态为权威，不降级成 `WORST_CASE_HELD`；不二次 settle |
| D3-C07 | 取消在发送前 / 发送后 / 双流中只取消一条 | 不发送不该发送的 Fake；已发送保持保守费用；另一条流独立完成 |
| D3-C08 | 客户端断连、半关闭 UDS、Trusted SIGTERM | 进程/Socket/线程清理，保守状态；不得伪造 Cancel 保证或 Fee=0 |
| D3-C09 | Broker `SIGSTOP`、Fake 卡死、首帧 Stall | 真实 Deadline/Watchdog 生效；不允许永久阻塞 Trusted 或丢失保守账本 |
| D3-C10 | 流式首 Chunk 先于 Fake 退出 | 捕获 Monotonic 时间戳证明 T(first DSH chunk) < T(Fake exit)；不是 buffered replay |
| D3-C11 | 两个 Candidate 并发相同逻辑 Request/同 Claim | 至多一个 Claim/Attempt/Fake；输家有精确受控错误码；旧 G3-C 不曾证明两真实 DSH，同 Gate 补足 |
| D3-C12 | 启动/关闭/恢复 10+ 次，资源压力 | Snapshot 中无额外 Receipt/Claim；每次清理对象、Rootfs/Deps/Stage 不漂移；Cgroup cap 确实生效 |

注意：G3-C 的 `flock` 修复的是 **同一 Socket 的双 Controller 冷启动**，不是两个真实 DSH Candidate 对同一 Claim 的竞争；D3-C11 不得以旧 20/20 启动证据代替。实施前必须明确如何构造**真实相同的 business-request identity 或同一 claim**：两个独立 DSH 客户端分别发送相同消息并不自动等于共享 `call_id`；在同一 Controller 的 `logical_step` 递增情况下可能形成不同 CallIdentity。实验需同时记录两端的 business digest、scope/run/step、CallIdentity、Reservation/Claim，并区分“同请求重放”与“两个合法独立请求”。如果 DSH 公共接口无法重现同一 Claim，必须补一个受控的可信 Controller/UDS 同身份竞争负例，分别上报 real-DSH 并发与 same-claim 负例的证据级别，不能拼接成一次不存在的 real-DSH same-claim PASS。

### 9.2 全量回归

- G3-C 定向 (`tests/integration/g3c`)、G3-B (`tests/integration/g3_bridge`)、G2 Accounting/Claim/LiveGate、Node Adapter/Guard/Skill（受冻结 Runtime 兼容限制时标 `BLOCKED/UNVERIFIED`，不伪造 PASS）。
- 固定 OCI `pytest tests -q` 需要可重复；优先修正上轮 `pgrep`/`noexec` 两项环境兼容问题。任何测试失败必须保存完整 argv/Exit/Stdout/Stderr/UTC/关联 Commit，不能只摘录 Passed 数。
- 旧的 2 个 Host 环境失败（Config 文件 mode、硬编码 `/project`）不能在证据中消失：若仍存在明确标为 host-only 限制，并以固定 OCI 作为标准真值；新引入的产品失败一律不能按环境问题接受。
- Rootfs/Deps/Stage 的前后 SHA 必须相同；不允许测试完成后偷偷清理非空/非本人产生的可疑目录以恢复 Hash，发现漂移即保留现场、说明原因并 STOP。
- 实际错误码/Finish Schema、Usage -> DSH、Receipt -> Broker、精确两个 Digest 关系应做至少一项跨 Principal 断言；单一计数 PASS 不足以代替账本关联。

### 9.3 G3-D 最终验收的硬门槛

**全部必需**：

1. D-G0 身份可复现、冻结实现 Stage 真实加载正确源码；G3-C 历史 Packet 和 v1/v2 归档不变。
2. D1 真实双 Principal 的 Echo + Tool 两轮正向通过；真实 Node SDK、真实 Broker、Fake Provider 账本一致，0-Key、0 外网。
3. D2 全部 12 项真实 Candidate 攻击有核验，旧四项 OS 绕过被内核拒绝；额外 Controller-level Protocol 负例也拒绝；并且 D2-11 正向成功。
4. D3 真实跨容器 Crash/Cancel/Replay/Deadline/Streaming/恢复、双 Candidate 竞争完整执行，费用不低估、无自动重发、无误记 FREE；高风险窗口日志原始可复现。
5. `LiveGate` 仍 BLOCKED；未注入凭据；没有任何真实 HTTP 请求。Host Root/运行时逃逸不在该 Gate 的安全主张内。
6. 标准固定 OCI 测试 0 **意外**失败且全部例外有明确分类；不以高计数掩盖失败；至少一名未参与实现的 Reviewer 自建关键恶意 Probe、正向 DSH 和跨账本核对。
7. 全流程清理/Rootfs/Deps/Stage 完整性和保留证据一致；Review Packet 自校验并且源码 Runtime/Manifest 真实对应。

若其中一项没有确证，裁定为 `PARTIAL/BLOCKED`，不要压成总 PASS；风险 5（Candidate Session 磁盘 DoS）若暂时不具备硬配额，只能在此威胁模型之外作为**明确 P2 残余**，并需独立 Reviewer/维护者明示接受才可签受限 OS Boundary PASS。

---

## 10. 重要安全与工程细节（实现者不许省略）

### 10.1 `SO_PEERCRED` 是辅助真实性，不是 per-run Auth Token

Peer UID 65534 证明连接来自允许的 OS 身份，不能区分所有 UID 65534 的 Candidate、同一候选内不同进程或旧 Run；Unix Socket 目录应该在 Host Root 限制访问的随机 Run Path 中，仅挂载给本 Run 的 Candidate。Server 自身仍要保留 Admission / Route / Tool / Identity / Claim 语义验证。若平台不支持 Peercred，不能只靠 Socket mode 宣称信任边界通过。

### 10.2 `Trusted root` 要限制能力并清晰声明 TCB

Rootful Podman、LXC root、Trusted Python/Node 代码都属于受信基础；`--cap-drop ALL` 与 `no-new-privileges` 实测验证。不要为了 Socket `chown` 加回 `CAP_CHOWN`：先用 Host Launcher 构造 group setgid 目录并验证 inode Group；如果不能满足，报环境/实现失败。真实 Key 仍不存在；本 Gate 的“Trusted”只是 OS 主体边界，不代表经过 G4 的安全部署。

### 10.3 不可信 Session → Trusted 的 Confused Deputy

不可信 Candidate Session 可能包含 Symlink、FIFO、Hardlink、大量文件和超长路径；Host Root Launcher 不得读取或跟随其路径后写入可信 Evidence、直接 `tar -h`、递归 chmod/chown、运行 Session 中的脚本。采集只读、限文件数/大小、禁跟随 Symlink/需特殊文件类型拒绝。攻击测试必须验证此边界。

### 10.4 UDS 正向链和协议拒绝要同时测

Socket `0660 + GID 2000` 只说明某类进程可连接，并不意味着有权调用任意 Provider；同 UID 连接可以发送坏 `call_id/admission` 等，必须由 Controller 拒绝且 Fake=0。不要将所有业务拒绝都归类成“内核 EACCES”，也不要因有 `SO_PEERCRED` 就省略 Protocol/Bound Claim。

### 10.5 崩溃窗口的费用归属

`ATTEMPT_STARTED` 与真实发送之间存在不可避免的不确定窗口；Remote exactly-once 没有被证明。无需强制在此阶段实现外部付费出口；保留 `SETTLEMENT_UNCERTAIN/PENDING`、非零保守占用、无自动重发即可。具有可信 Receipt 的已发送成功请求允许恢复到 `SETTLED`；Broker 已 OK 时不能被 Journal 标成 Held。

### 10.6 证据身份必须分五层

1. Git **Code SHA**（实现的哪一批代码）；
2. Stage **实际字节 SHA**（加载的模块、Adapter 编译产物）；
3. Runtime **环境 SHA/版本**（Rootfs、Deps、Node、DSH SDK、Podman/crun、Kernel）；
4. Test **命令和真实 Trace**（argv/UTC/exit/Context、失败 stdout/stderr）；
5. Review **证据哈希与独立身份**（包不可变、重复哈希校验、Reviewer 自建探针）。

这五层任一缺失，不得用“Packet xx/xx OK”代替。

---

## 11. 实施 PR 建议与审阅边界

- `D-PR0 / evidence`: append-only G3-C Digest errata、已存在源码 Overlay 辅助说明、两项 OCI 测试可移植性修补；无产品 API 设计变更。
- `D-PR1 / ipc`: `BridgeServer` additive socket Mode/GID、peercred、ready、安全路径/测试；必须保留默认 0600、已有协议及错误码。
- `D-PR2 / launch`: Candidate/Trusted Stage 白名单构建、Manifest、无 Key 资源/UID/Mount 检测、独立 Root Launcher、Echo/Tool 正向。
- `D-PR3 / adversarial`: D2-01..12 恶意候选代码/真实 Probe/原始结果/清理和状态对账。
- `D-PR4 / recovery`: D3 复合崩溃、取消、并发、Streaming、固定 OCI 回归，证据脚本。
- `D-PR5 / docs`: Implementation Report、Review Request、测试矩阵、Review Packet Builder、冻结 Manifest；代码和文档 SHA 分离，Reviewer 独立签字。

PR 名称只是建议。**先做 D1 Gate，审过再开攻击批次**；不可为 12 个攻击场景预先修改生产权限让测试通过。每个 PR 保留 Target Files、Reason、Red/Green、Ruff/Test、Impact to Boundaries、Commit SHA、Rollback Strategy。

---

## 12. Evidence Matrix 规则

随附 `Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`。D0/D1/D2/D3 16 个历史 ID 一一保留，并加入更细分的 UID/Socket/Stage、Crash、Usage、Review 用例。**全部初始 `NOT_RUN`**；不能因为 G3-C 53 PASS、D0 写完方案就提前标 `PASS`。

每行至少填写：

`case_id, phase, severity, scenario, expected, status, observed, command_argv, utc_start, utc_end, exit_code, code_sha, stage_sha, env_sha, evidence_paths, owner, reviewer_status, residual`。

规则：

- `PASS` 必须真实执行，且有正向/反向结果与可用证据路径；`PARTIAL`、`FAIL`、`BLOCKED`、`UNVERIFIED` 原样保留。`NOT_RUN` 只在未执行时使用。
- 正向 DSH 与 raw-UDS/Host Mock 不可合并为同一类型；标注 `real-DSH`, `real-Candidate-OS`, `raw-UDS`, `host pytest`, `container reconcile`。
- 每个 Case 绑定生成时的 `code_sha`、实际 `stage_sha`、运行环境 SHA，不能把旧 `e6fde1c` Trace 标成新 D 实现。
- 原始文件名/Hash 保持不动，任何修正建 `ERRATA` 或新版本 Packet，不篡改冻结证据；不得将软链接跨出包根。
- 为旧的四个 OS 绕过附 G3-B 同 UID 测试证据与当前 Kernel Deny 的一一对应表。

---

## 13. Review Packet（完成 D3 后）

建议：`artifacts/review-packet-g3d-<implementation-full-sha>/`。至少：

```text
review-packet-g3d-<implsha>/
  README.md
  manifest.json                   # repo/base/impl/docs/runtime/stage/dirs/counts/nonclaims
  hashes.sha256
  packet-integrity-report.txt
  changes/
    implementation.diff.patch
    docs.diff.patch
    protected-files-diff.txt
  source/
    ipc_server.py, controller.py  # 真正变更或关键源码的 blob/行号索引
    launcher/, stage-builder/, candidate-entry/, trusted-entry/
  env/
    git.txt, image-runtime.txt, uid-map.txt, gid-map.txt,
    mountinfo-candidate.txt, mountinfo-trusted.txt,
    peercred.txt, socket-stat.txt, cgroup-limits.txt,
    rootfs-pre-post.txt, deps-pre-post.txt, stage-pre-post.txt,
    livegate.txt, zero-key-network.txt
  d1/
    echo/, tool/, stage-manifests/, ready-and-cleanup/
  d2/
    d2-01/ ... d2-12/            # attack source + stdout/stderr + errno + DB delta
    old-bypass-to-new-denial.csv
  d3/
    crash-*.json, cancel-*.json, replay-*.json,
    stream-timestamps.json, concurrency-two-candidates.json,
    sqlite-readonly-snapshots/, fake-receipts/
  regressions/
    oci-full.log, host-full.log, node-tests.log, ruff.log,
    argv-and-exit.jsonl, test-junit.xml
  matrix/
    G3D_Test_Evidence_Matrix.csv
  review/
    reviewer-reproduction.md
    security-nonclaims.md
    remaining-risk-register.md
```

**Manifest 至少字段**：`base_sha`, `implementation_sha`, `docs_sha`, `stage_manifests_sha256`, `runtime_rootfs_sha256`, `deps_sha256`, `candidate_uid_map`, `trusted_uid_map`, `peercred`, `socket_mode`, `socket_gid`, `network_mode`, `test_stats`, `real_model_calls=0`, `real_external_http_calls=0`, `has_real_key=false`, `os_boundary_status`, `live_gate_status=BLOCKED`, `packet_file_count`, `packet_payload_tree_sha256`（只覆盖 payload，排除 manifest/hash 文件以避免自引用）, `previous_g3c_review_ref`。

**Integrity 检查**：包的 JSON manifest/全部文件逐一哈希；将 SQLite 拷贝到一次性只读副本再查询，不在原始 Packet 内打开活跃数据库。Tar 建议不含 Symlink（或仅经白名单明确记录），归档前后再次复算文件数/Hash。不要把任何真实秘钥/Token 值写进日志或 Packet。

---

## 14. Independent Reviewer（必须不同身份）

Lead 指派未参与 D1/D2/D3 的 Reviewer；其任务不是简单“检查 53+16 行 PASS”，而是基于冻结源码构建和自己的原始 Probe 做反证：

1. 复算 Git SHA、实施 Diff、Stage Manifest、实际加载模块 Blob、Rootfs/Deps/Runtime、Packet 内容哈希；尤其独立验证**没有旧 G3-C Stage 源码漂移**。
2. 按自己创建的恶意 Candidate 测试 **Broker DB 读/写、Policy/Admission/Attempt/Receipt、直接 Claim/Fake、Socket 替换/Peer UID 伪造、`/proc`/FD、外部网络**；记录真实 errno、UID Map、Mountinfo；不能只复制 Owner JSON。
3. 以真实 DSH 在两 OS 主体下至少重跑 Echo、Tool 两轮、Session Resume，核对 Fake Count、Claim、Attempt、Prepared/Raw Digest、Usage、Settlement。
4. 独立做 2 个 Crash（至少 after_attempt、after_broker_settle）和 1 次 Cancel/Disconnect，验证不自动重发且 Conservative；再做同 Claim 双 Candidate 并发。
5. Reviewer 自己运行至少一套固定 OCI Python/Node 核心回归和 LiveGate Check，核对容器 Clean；未跑的项写 `UNVERIFIED`。
6. 明确区分 `Kernel Deny`、`Protocol Deny`、`Guard Deny`、`No Mount`。不要把后者冒充内核文件拒绝，也不要将有业务错误的合规 UDS 当作无法建立正向通道。
7. 出具 `docs/REVIEW_G3D_INDEPENDENT.md`，列 P0/P1/P2、原始地址/文件行号、命令/UTC/Exit、最小重现和唯一裁定（PASS/PARTIAL/FAIL/BLOCKED），不能替实现者修改代码或证明自己代码的 PASS。

任何 P0（OS 越权/未授权发送/重发/虚假账本）立即 FAIL；P1 修复后需最小复审；P2 可在明确风险登记和维护者批准下接受，但不能影响 G3-D 的威胁模型核心不变量。

---

## 15. 立即执行的最小首批（避免无限规划）

**Batch 1：D-G0 + D1-A + D1-B 的最小正向。**

- Day/迭代概念不绑定实际耗时；不用先拆数十个新 ADR。
- 先完成当前 SHA/环境核验，修 Socket `0600` 的直接连接约束，构建两个 Stage，首次**跨容器真实 Echo**，产生 UID Map + Peercred + Socket Stat + Broker Snapshot + Receipt。成功后立刻让 Lead 审查 D1 Gate；失败直接在 D1 STOP，禁止改弱安全边界。
- 在 D1 通过之前不要运行 D2 大规模攻击；但可以离线准备 Probe 源码和 Matrix（不能提前标 PASS）。
- D-P0 的 OCI 两项兼容问题可以由独立 Test Agent 修，但不要共享并行可写 Rootfs/Deps/Stage。

**Batch 2：D2 12 类实际攻击与 D3 关键故障。** 只有在 D1 Gate 已通过且实施基线冻结后执行；优先 D2-01..05（旧绕过），再 D2-06..12；然后 D3 Crash/Cancel/两 Candidate/资源/Usage 全量。

**Batch 3：Independent Review + STOP**。不得自动继续 G4/G5；M0 GO 决策独立进行。

---

## 16. Lead Agent 可直接复制的任务指令

> **目标**：依据 `docs/M0_G3D_OS_BOUNDARY_DESIGN.md` 与本任务书，完成 Autonomous Teacher M0 G3-D 无 Key / Fake Provider 双 OS Principal 隔离、真实 DSH 正向、12 类恶意候选 Kernel/Protocol Deny、跨容器 Crash/Cancel/Replay/Streaming/资源回归、独立 Review。  
> **输入**：G3-C 产品实现 `b2f6af054555705192c4e1ae3019a68078764736`（当时远程 HEAD `fff362326…` 后续无产品源码变化，运行时核验）、`docs/REVIEW_G3C_INDEPENDENT_v2.md`、`docs/M0_G3C_REVIEW_ERRATA.md`、D0 原始 1326 行设计、`AGENTS.md`。  
> **职责**：我是 Lead，只做协调/审阅/独立复跑，代码交给子 Agent。  
> **执行**：先 D-G0 核验与 D-P0 小型收口；D1 用 D0 方案 A 为 BridgeServer 增加 backward-compatible Socket Mode/GID、Peercred 与 Ready，构建不同 UID/Namespace/Mount 的 Candidate/Trusted Stage，并在 `--network none`、0-Key、只读 Rootfs 下以真实 DSH 跑通 Echo + Tool；D1 不过则 STOP。D1 PASS 后开展 D2-01..D2-12 实际恶意 Candidate Probe（重点关闭旧 DB/Policy/直接 Claim 绕过），再进行 D3 双容器 Crash/Cancel/Replay/Streaming/两 Candidate 争用、固定 OCI 全量；每项提供原始 errno、Map/Mountinfo、Broker/Receipt 对账和源码 SHA。  
> **绝对禁止**：真实 Key、Provider API、外部网络/HTTP、`podman pull`、解除 LiveGate、G4/G5/Live 自动继续、同 UID/0666/向 Candidate 挂 Trusted State 来换取 PASS、修改冻结 G3-C Packet 或 v1/v2 审阅字节。  
> **交付**：冻结 Commit/最小 Diff、D1/D2/D3 原始 Trace/DB/Receipt/Exit、逐项填充的 G3-D 矩阵、Implementation Report、Review Packet、独立 Reviewer 结果、剩余风险。按 `AGENTS.md` 分工；独立 Reviewer 不参与实现。完成 G3-D 独立复核后 **STOP**，由维护者决定是否启动 G4。

---

## 17. D0 与本任务书的权威关系

- G3-D0 的**事实性本机可行性结果**与其威胁模型、12 项 D2 细节，以原文件为权威；本书将其组织为 D1/D2/D3 可执行交接，并增加 G3-C v2 最新身份、Digest 勘误、旧 Stage 污染预防、OCI 可移植性与 Gate 分级。
- D0 的 `CAN_ISOLATE` 是已记录的**当时**探针；每台机器每次执行仍需 Preflight。
- 如 D0 的行号/Socket 代码与当前 G3-C `b2f6af0` 冲突，以真实冻结源码为准；**不能**用旧 G3-B 行号臆测已经修好。
- 本任务书不是 G4 的 Credential/Key 安全设计；未来真实 Provider/网络/Invoice、签名 Approval、外部 Watchdog/Key 隔离、第三方账单核对，全部独立评审，不可由 G3-D PASS 自动开通。

**最终 STOP 状态**：交付 `PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE` 或明确 `PARTIAL/FAIL/BLOCKED` + 全部证据；**不宣称 Live/GO**。
