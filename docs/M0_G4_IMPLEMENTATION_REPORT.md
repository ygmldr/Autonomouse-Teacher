# M0 G4 — 无 Key 预上线工程实现报告（G4-E 冻结）

- **任务**：G4-E-01..E-05（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §9/§14/§15）
- **执行者**：G4-E Freeze / Review-Packet Agent（只做报告、矩阵、Packet 与复现材料；不修改产品代码/执行语义）
- **执行时间（UTC）**：2026-11-18T19:48Z → 20:25Z
- **冻结点**：base `017c747`（G3-D final）→ impl HEAD `a6f3e0a`（G4-D final，docs-only after code）→ code `d3d429c` → docs `本 G4-E 文档提交`（Packet `manifest.json` 固定其完整 SHA）
- **性质**：**no-key / no-model / no-network / no-container-pull / no-Live**。0 真实 Key、0 真实 Provider、0 外部 HTTP/TCP、0 计费发送；全部容器 `--network none`、`--read-only`、`--cap-drop ALL`、`--user 65534:65534`；结束时 `podman ps -a` 为空。
- **本轮状态**：G4-A/B/C/D 已实现并自测；G4-E-01..05 冻结证据已生成；**独立 Review 尚未执行**。允许的最高裁定为 `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`（由独立 Reviewer 出具），**本报告不自行给出该裁定**。
- **明确不声明**：G4 Full PASS、`E5_PRELIVE_FULL`、`HUMAN_AUTHORIZATION_DEPLOYED`、真实计费可控、供应商硬额度、G4-H/G5/G6 授权、Live 许可。

---

## 0. 结论摘要

| 项 | 结果 |
|---|---|
| G4-00 | 基线成立；rootfs/deps/stage/runtime canonical 0 drift；LiveGate BLOCKED；P2 三项仍待维护者 |
| G4-A | 15/15 矩阵行 PASS（L1-HOST + G4-E OCI uid-0 replay）；223 tests；`signature_valid` 与 `billable_send_authorized` 分列，后者恒 False |
| G4-B | B01/B02/B04/B05/B06/B08/B09/B10/B11 PASS；**B03 UNVERIFIED**（无可导出 merged registry）；**B07 PARTIAL**（session-title BLOCKED） |
| G4-C | 18 行 = **11 PASS / 7 PARTIAL**；9 次真实双 Principal 容器运行 PASS；C01/C02 两套账本与两对 Digest 逐项相等 |
| G4-D | 15 行 = **12 PASS / 2 PARTIAL / 1 UNVERIFIED**；真实外部 watchdog、撤销、哨兵、E5 子集 |
| G4 矩阵（E 前） | 85 行 = 57 PASS / 10 PARTIAL / 2 UNVERIFIED / 10 NOT_RUN / 6 BLOCKED |
| G4 矩阵（E 后） | 85 行 = **62 PASS / 10 PARTIAL / 2 UNVERIFIED / 5 NOT_RUN / 6 BLOCKED**；E06..E10 仍 `NOT_RUN` |
| 全量回归（host） | 原始：1285 = **1280 passed / 4 failed / 1 skipped**；4 项均为已知 frozen-src 或 host-only 环境（§11.1） |
| 全量回归（固定 OCI） | 过滤后 **957 passed / 24 skipped / 34 environment deselects / 0 failed**；另以 uid 0 replay **294 passed / 2 deselects** |
| Node | adapter 9/9、guard 19/19、skill 8/8 = **36 passed / 0 failed** |
| Ruff | G4 scoped **All checks passed**；repo-wide **37 项既有 findings**（绝大多数 `spikes/`，`src/tests` 0） |
| 真实计数 | `real_provider_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`LiveGate=BLOCKED`、`run_live_exit=3` |
| E5 两列 | P01/P02/P03/P05 的 `NO_KEY_SUBSET=PASS`；**P04 子集=UNVERIFIED**；五项 `FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` |
| G4-H | 六项全部 `BLOCKED / NOT_AUTHORIZED` |
| Review Packet | `artifacts/review-packet-g4-a6f3e0a27a516534803a1e3549dc60fbd107583c/`；自校验 100%（见 §14） |

---

## 1. 身份、提交链与不可变面

### 1.1 冻结身份

| 角色 | SHA | 说明 |
|---|---|---|
| base | `017c747631cae1e7788014c4ef9e6056c141fecd` | G3-D final docs archive |
| G4 docs 归档 | `810e313c3e3d459db8b1c5517366e33ae0154811` | G4 任务书 / START_HERE / matrix |
| G4-00 | `e3d270e2277087e0642dda8803111885d0dbad3f` | 基线/能力测绘 |
| G4-A | `382b4ee27eba3d31f17ca2c9cd36b1d6332c559c` | 授权契约实现；`ac7cb08` 为 A docs |
| G4-B | `376012c` → `5559013` → `32acce9` → `76f2b18` → `c29cabc` | 运行时清单/registry 探针；docs `9397fe1`/`e7033cc`/`795c263` |
| G4-C | `3fd0d8569dd10f931231ee65a6a506b2f6c85577` | synthetic egress；docs `4521561` |
| G4-D | `d8a8dc8` → `718b44e` → `4622389` → `0975412` → `2019c49` → `d8e71a8` → `d3d429c` | watchdog/撤销/E5；docs `0feb123`、`a6f3e0a` |
| **impl HEAD** | **`a6f3e0a27a516534803a1e3549dc60fbd107583c`** | G4-D 报告计数修正（docs-only） |
| **code 实现** | **`d3d429cf9d0cb1e9dbc68317928631db413be309`** | G4-D 最终实现提交；`src/` 树与 HEAD 相同 |
| 最后 `src` 提交 | `d8a8dc83673d6236884bb41574214e5b2106fcd4` | `git log -1 -- src`；`d3d429c` 只改 `scripts/g4/run_g4_d.py` |
| docs（G4-E） | 本提交（Packet manifest 记录完整 SHA） | 4 份报告 + matrix + packet builder |

> **身份说明**：`a6f3e0a` 与 `d3d429c` 的 `src/` 完全一致（`git diff d3d429c..a6f3e0a -- src` 为空）。因此“impl=`a6f3e0a`、code=`d3d429c`”不是两个不同的代码状态，而是同一冻结代码的 docs HEAD 与实现 HEAD 两个锚点。

### 1.2 改动范围（base → impl）

```text
git diff --stat 017c747..a6f3e0a -- src scripts config plugins docs
  src: 6 files, +1590/−42
  scripts/g4: 18 files（builder/launcher/probe/runner）
  config/g4: 2 files
  tests/integration/g4_a|b|c|d: 34 files
  docs: G4-00/A/B/C/D 报告与 matrix
```

产品改动仅六个文件：

| 文件 | 作用 |
|---|---|
| `src/autoteacher_m0/security/authorization.py` | 可信文件边界、严格 JSON、15→5 绑定闭包、预算镜像、单次消费 |
| `src/autoteacher_m0/security/ed25519.py` | verify 输入归一化与异常捕获（签名数学未改） |
| `src/autoteacher_m0/security/live_controller.py` | inspect-only 组合、预算/route/候选 Stage 拒绝原因 |
| `src/autoteacher_m0/security/egress.py` | `ProviderRouteContract`、`TrustedSendAuthorization`、`TrustedSendGate` |
| `src/autoteacher_m0/security/watchdog.py` | 外部 absence/路径复核原语（既有状态机未改） |
| `src/autoteacher_m0/bridge/controller.py` | 可选 `dispatch_gate`；默认 `None` 时 G3-C/D 行为不变 |

**未改**：`security/gates.py`、`scripts/run_live.sh`、`runtime/dsh_adapter.py`、`cli.py`、DSH 核心、`scripts/g3d/**`、G3-D stage、历史证据/Packet。Packet 的 `changes/protected-files-diff.txt` 给出逐文件 `UNCHANGED` 与 blob。

### 1.3 G4-A/B 并行导致的提交交错

G4-A 与 G4-B 同时进行：G4-A 的实现提交 `382b4ee` 父为 `76f2b18`（G4-B fix），其 docs 为 `ac7cb08`；G4-B 的主提交 `376012c` 父为 `e3d270e`（G4-00）。G4-B 的真实容器证据在独立 worktree `2f1e41f`（`src=cf40c6b`）产生，因为冻结的 G3-D launcher 要求 `src` 相对 `cf40c6b` 无 diff；该 worktree 提交不在 main 上。此交错已在 G4-B 报告 §1/§12 显式披露，本报告不追溯改写。

---

## 2. 本轮范围与不批准事项

**批准范围（仅本报告覆盖）**：无 Key 的授权校验、冻结清单、synthetic egress、外部 watchdog、E5 无 Key 子集、冻结/复核材料。最高可交付裁定为 `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`（独立 Reviewer 出具）。

**未批准、未部署、不得推断为已通过**：

1. 真实人类 Ed25519 信任根、私钥托管、公钥轮换/撤销 SOP；
2. 真实 Key Broker / 凭据注入 / 供应商账户；
3. 真实 Egress Proxy、DNS/TLS/redirect/代理验证；
4. 官方 DeepSeek 模型 ID、Endpoint、价格、Usage、限流、供应商硬额度；
5. E5-PreLive Full；
6. G4-H、G5、G6、任何 Live 运行。

`docs/SECURITY_APPROVALS.md` 仍是 **BLOCKED / NOT APPROVED** 模板；本轮没有写入任何 `APPROVED` 状态。

---

## 3. G4-00 — 基线与环境

- HEAD `810e313`（当时），`src/tests/config/plugins` 与 `cf40c6b` 字节一致；工作区 clean。
- canonical 五件套重算全部一致：rootfs `25491e45…`、deps `e07729d7…`、D3 stage `e1ff1449…`、stage manifest `644823d4…`、DSH runtime `1cc41d5a…`。
- 容器内实际加载 10/10 模块 = `cf40c6b` blob = stage 副本；宿主新进程 17/17 模块来自 `src/` 且匹配 HEAD。
- Candidate 宿主 uid `65534` / Trusted uid `0`；UDS `0660 root:2000`；`SO_PEERCRED uid=65534`；Candidate mount 无 `/work/state`。
- LiveGate 恒 BLOCKED；`run_live.sh` exit 3；CLI/env/Markdown/Adapter 全部阻断；真实计费 0。
- 组件 wiring 四列：`implemented 7/7`、`tested_in_isolation 7/7`、`wired_into_trusted_process` 仅 `egress.py`、`externally_deployed 0/7`。
- P2-DISK / P2-USERNS / P2-RUN-IDENTITY 全部保持维护者待决，本轮不签收。

详见 `docs/M0_G4_00_BASELINE.md`。

---

## 4. G4-A — 可信批准契约（无真密钥）

**实现**：复用 `at-m0/execution-authorization/v1`，未新建第二套格式。`ExpectedBindings` 扩展为 15 组件 → 5 个既有聚合根；新增 `binding_drift(pre_start|pre_reserve|pre_dispatch)`、严格预算镜像解析、`consume_execution_authorization`（`O_CREAT|O_EXCL|O_NOFOLLOW` 单次记录）。

**关键语义**：

| 字段 | 行为 |
|---|---|
| `signature_valid` | Ed25519 数学验证通过（仅准入诊断） |
| `approved` | 整份离线文档通过全部策略检查 |
| `billable_send_authorized` | **恒 False**；构造 True 直接 `ValueError` |

- 合成 `TEST_ONLY_` 签名可得到 `approved=True, signature_valid=True`，但 `LiveGate`/CLI/`run_live.sh`/Adapter 仍全部 BLOCKED/exit 3。
- Ed25519 负例：小阶/identity、order-4/8、torsion/mixed-order、非 canonical 公钥与 R、`S>=L`、短/长签名、非 bytes 输入，全部 `False` 且无 traceback。
- 严格 JSON：重复 key、NaN/Infinity、bool-as-int、float-as-int、unknown fields、未知 route/model、工具白名单变化、过期/未生效/零 skew、撤销、重放逐条拒绝。
- 可信文件必须在仓库外、目录私有、非 symlink、非 candidate uid、常规文件、有大小上限；`O_NOFOLLOW` + `fstat` 复核。
- 预算权威源 = 冻结代码常量（soft 3 / hard 10 / soft-call 0.10 / hard-call 0.20 / 50），经 `code_sha256` 绑定；`config/budgets.yaml` 是声明镜像，逐字段漂移即 deny。
- 重放：同一 `authorization_id` 全局单次消费；同 epoch 复用 → `AUTHORIZATION_REPLAYED`；跨 run/epoch → `AUTHORIZATION_EPOCH_MISMATCH`。

**实际测试**：G4-A 套件 **223 passed / 0 failed**（host）；G4-E 在固定 OCI 以 uid 0 replay 221 passed（1 项 CAP_CHOWN、1 项 `/bin/sh` 环境 deselect）。矩阵 15 行全 PASS。

**残余（详见 findings）**：只有 L1-HOST 全量证据（G4-E 已补 OCI uid-0 replay）；闭包路径表是契约声明；单次使用日志未签名；检查点到发送之间的 OS 不可变属 G4-H；pricing 恒 `REQUIRED_UNVERIFIED`。

---

## 5. G4-B — 冻结清单、实际加载与 Tool Registry

- **B01**：`manifest.json`（`m0.g4b.inventory.v1`）覆盖 13 个 root、**6,690 个文件条目**（含 6,515 依赖树文件）；确定性 canonicalization；`manifest.digest=6ca1aca3…`、文件 sha256 `6101b675…`；校验器 fail-closed（0/4/5/6/7 退出码）。
- **B02**：容器内 trusted 10/10 模块 = `cf40c6b` blob；宿主 17/17；adapter 产物三方一致（`2cb42461…`）；不是旧 G3-C stage。
- **B03**：DSH 0.2.2-rc.2 **没有** merged tool registry/schema 导出 API → `UNVERIFIED`；由 Controller 的 per-dispatch tool-schema 白名单兜底（在 Reserve/Claim 之前拒绝）。
- **B04**：host 7 例 + 真实 raw-UDS 6 例，未批准/额外/改 schema/file/self-auth/purpose 全部拒绝，ledger 0、Fake 0。
- **B05**：真实 DSH Tool 两轮：2 Reservation / 2 Claim / 2 Attempt（SETTLED）/ 2 Receipt / Fake=2；两个 `call_id` 不同；两组摘要分别映射；额外 provider 请求 0。
- **B06**：配额内第二个请求独立建账；超配额 `BUDGET_DENIED` 且 0 发送；辅助 `purpose=title` 协议层拒绝。
- **B07**：compaction/image-offload/fallback PASS；`session-log` PARTIAL；**`session-title` BLOCKED**（未禁用，但本轮 0 额外请求；依赖 Controller 兜底）；`mcp-resources` UNVERIFIED。
- **B08**：`--network none`、`AF_INET/AF_INET6 EACCES`、DNS 失败、无默认路由、0 proxy/key env、0 网络标记。
- **B09/B10/B11**：候选 stage 无 trusted code/Key/import；stage canonical 两次重算一致（未二次 build → 跨构建可复现 UNVERIFIED）；任何字节/树/derived 变化 fail-closed。

**实际测试**：G4-B 套件 38 passed（host）。

**残余**：B03 registry UNVERIFIED；B07 session-title BLOCKED / session-log PARTIAL；未做二次 stage build；G4-A 改码使旧 manifest 在 HEAD 上 verify 失败（这是 B11 的预期 fail-closed，不是缺陷）。

---

## 6. G4-C — Trusted Synthetic Egress

**实现**：`ProviderRouteContract` + `TrustedSendAuthorization` + `TrustedSendGate`；唯一 ACTIVE route 为 `offline-test-only-g3b/fixture-bridge-v1`；real route 模板恒 `BLOCKED_REQUIRES_HUMAN_VERIFICATION`。`TrustedSendGate.authorize()` 只存在于可信域内存；`consume()` 按对象身份一次性移除；无 JSON 反序列化入口。

**9 次真实双 Principal 容器运行全部 PASS**：

| Case | 场景 | 账本/发送 |
|---|---|---|
| c01 | 真实 DSH Echo | 1 Reservation/Claim/Attempt(SETTLED)/Receipt；Fake=1；gate 1/1 |
| c02 | 真实 DSH Tool 两轮 | 2 套独立账本；Fake=2；distinct call_id；tool result 进入第二请求 |
| c18 | 真实 DSH Stream | 1 套账本；`first_chunk_flushed < exit_after_finish` |
| negatives | 8 个 UDS 负例 + 网络探针 | 全部 error；ledger 0；Fake=0；AF_INET EACCES、DNS EAI_AGAIN |
| replay | 字节相同重放 | 第一次 finish/Fake=1；重放 `ATTEMPT_ALREADY_STARTED`；Fake 仍 1 |
| crash-before-send | ATTEMPT 后发送前崩溃 | Attempt=1 持久；Fake=0；恢复扩展 exit 3 |
| crash-after-receive | Fake 收到后崩溃 | Receipt=1；Fake=1；无第二次发送/结算 |
| broker-down | SIGKILL Broker | `BROKER_ERROR`；Fake=0；Attempt=0 |
| quota | `max_calls=1` 第二请求 | `BUDGET_DENIED`；Fake 不变 |

**C01/C02 摘要（实测）**：

```text
C01 call-cc8de3d3… prepared=a29f84d7a5b5 claim=a29f84d7a5b5
    payload=8ea503367cb5 receipt=8ea503367cb5
C02 call-30e8b383… prepared=044cd7d75d27 claim=044cd7d75d27
    payload=d13df0cb916d receipt=d13df0cb916d
    call-f198f95b… prepared=e0a2dca0bcbe claim=e0a2dca0bcbe
    payload=7868da9e0e76 receipt=7868da9e0e76
```

规则不是“两个摘要必须相等”，而是：`Prepared.request_digest == Claim.request_digest` 且 `Attempt.payload_digest == Receipt.raw_sha256`，两组分别映射、逐字节一致。

**矩阵**：18 行 = 11 PASS / 7 PARTIAL（C04/C05/C10/C11/C14/C15/C16 的决定性断言在 L1-HOST；未新增产品测试钩子）。

**残余**：容器内只能独立复算 `src/**`/`fake/**`；config/plugins/lock 由 Launcher 声明；pre_dispatch 与 dispatch 之间仍有 Python 内存窗口；真实 route/TLS/DNS/proxy 未证。

---

## 7. G4-D — 外部 Watchdog、撤销与 E5 无 Key 子集

- **外部 Watchdog**：宿主独立进程（`watchdog_runner.py`，`start_new_session=True`），不属于 Candidate/Trusted，也不是容器内守护线程。SIGTERM→有界 SIGKILL→`/proc` 复查→`podman ps -a` 全表复查→`inspect` 必须失败→socket/run-dir/rootfs-target `lstat` 复查；`rm -f` 返回 0 从不当作 absence。
- **D01**：真实双容器 kill/absence；watchdog exit 0、24/24 checks；target exit `-15`；无自动重发。
- **D02**：host SIGSTOP trusted init（`/proc/<pid>/stat` 复核 `T`）；deadline kill/cleanup；本 run 无 attempt/receipt，未伪造。
- **D03/D04**：哨兵未进入 Candidate env/argv/mount/`/proc`/session/log/receipt；运行期 8,804 文件、最终 8,815 文件 0 命中；扫描器正控必须命中。
- **D05**：撤销后 `AUTHORIZATION_REVOKED`；use-log 保持 1；pending attempt 保持 `ATTEMPT_STARTED`；第二次 `begin_attempt` 拒绝。
- **D06**：同 gate 改 epoch → `AUTH_EPOCH_MISMATCH`；跨 run → `AUTHORIZATION_UNKNOWN`；契约层 → `AUTHORIZATION_EPOCH_MISMATCH`。
- **D07**：`run_live.sh`/CLI/Adapter/LiveGate 全阻断；注入假 Key/代理/审批 flag 无效。
- **D08a/D08b**：清理失败 / podman 查询失败 → watchdog exit 4 `FAIL_CLOSED` + 人工清理 + 二次复查空。
- **D09**：CPU `-24`、AS exit 1、NOFILE exit 2、容器 cgroup `pids.max/memory.max/cpu.max` 实测；host root 不受 `RLIMIT_NPROC` → PARTIAL。
- **D15**：容器内 + host 同 UID known-path 全 `EACCES/ENOENT`；拒绝依赖 mount/DAC，不是目录名随机性；P2-RUN-IDENTITY 仍未决。
- **F1–F5**：实现期发现并修复的自身工具缺陷（podman pause 残留、inspect 截断、RLIM_INFINITY、exec PID namespace SIGSTOP、NUL 分隔 environ），均有 RED→GREEN 证据。

**矩阵**：12 PASS / 2 PARTIAL（D05、D09）/ 1 UNVERIFIED（D13）。

---

## 8. G4 矩阵统计（E 前 → E 后）

| 时点 | 行数 | PASS | PARTIAL | UNVERIFIED | NOT_RUN | BLOCKED |
|---|---:|---:|---:|---:|---:|---:|
| G4-E 前（HEAD `a6f3e0a`） | 85 | 57 | 10 | 2 | 10 | 6 |
| G4-E 后（本提交） | 85 | **62** | **10** | **2** | **5** | **6** |

- 新增 5 个 PASS：`G4-E-01` 源码 diff、`G4-E-02` Packet、`G4-E-03` host+OCI 回归、`G4-E-04` Node、`G4-E-05` runtime overlay。
- `G4-E-06..E-10` 保持 `NOT_RUN`：必须由未参与实现的独立 Reviewer 自建 Probe、独立运行并填写。
- `G4-H-01..06` 保持 `BLOCKED`。
- E5 FULL 在矩阵中仍以 `G4-D-10..14` 的 `FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 记录，禁止合并成单列 PASS。

---

## 9. Echo / Tool / Stream / 负例 / 账本 / Digest

| 维度 | 实测 |
|---|---|
| Echo | 1 Reservation、1 Claim、1 Attempt `SETTLED`、1 Receipt、Fake=1；usage `input 11/output 5/total 18`；cost `0.001022` |
| Tool 两轮 | 2 Reservation、2 Claim、2 Attempt、2 Receipt、Fake=2；两个不同 `call_id`；两套独立结算 |
| Stream | 1 套账本、Fake=1、gate 1/1；首帧时间早于 Fake 退出 |
| 负例 | 8 个 UDS 负例全部 error、ledger 0、Fake=0；broker-down Fake=0；prepared/payload 变更 Fake=0 |
| 重放 | 同业务身份最多一次；第二次 `ATTEMPT_ALREADY_STARTED`，Fake 不增 |
| 崩溃 | 发送前崩溃 Attempt 持久/Fake=0；收到后崩溃 Receipt=1/Fake=1，无第二次发送 |
| 账本 | Reservation/Claim/Attempt/Receipt 逐行按 `call_id`/`reservation_id`/`receipt_id` 配对 |
| Digest | Prepared=Claim；Payload=Receipt；两组分别校验；不把“两值不相等”当密码学条件 |

---

## 10. G4 stage / launcher 偏差（不修改 G3-D）

G3-D 冻结 launcher 在 preflight 要求 `git diff cf40c6b -- src` 为空。G4-A/C 按授权修改 `src/` 后，该条件必然失败；本轮处理：

1. **不修改** `scripts/g3d/**`、G3-D stage、G3-D 测试/证据/矩阵。
2. 新增 `scripts/g4/build_stage_c.py`：在进程内重绑定 `lib_g3d.PRODUCT_BASE/G3D_ROOT`，调用同一 G3-D 组装代码；stage manifest 的 `base_sha/head_at_build` 指向 G4 实现提交；产物只落 `artifacts/g4/c/stages/`。
3. 新增 `scripts/g4/launch_c.py`：复用 `lib_g3d` 的 run layout、UID/mount/`--network none`、socket/peercred/identity 与清理辅助；trusted 入口改为 `/g4c/trusted_entry.py`（run-dir 副本），不改 stage 内冻结的 `trusted_entry.py`。
4. `controller.py` 只增加可选 `dispatch_gate`；默认 `None` 时 G3-C/D 行为逐字节不变。
5. G4-D 新增 `launch_d.py` hold-open 驱动与 `watchdog_runner.py` 外部监管；teardown 明确归外部 watchdog。

**冻结 stage**：`artifacts/g4/c/stages/stage-20261118T193401Z`，base `d3d429c`，manifest `85353018…`，tree `9c9ce313…`。G3-D 冻结 stage `e1ff1449…`/`644823d4…` 未改。举证时严格区分“G3-D 冻结 launcher 证据”与“G4 专用 launcher 证据”。

---

## 11. 测试、OCI、Node、Ruff 实际计数

### 11.1 Host full（`pytest tests -q`）

| 运行 | 结果 | exit | 说明 |
|---|---|---:|---|
| 原始 | **1285 = 1280 passed / 4 failed / 1 skipped** | 1 | 4 项均在下方逐条归因 |
| 显式 deselect 已知项 | **1281 selected = 1280 passed / 1 skipped / 4 deselected** | 0 | 4 项 deselect 有明确理由，不静默 |

四项失败分类（`regressions/host-failure-classification.json`）：

1. `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` — **frozen-src 断言**：G4-A/C 授权改码使 `git diff 4bd4803 -- src` 非空；历史测试不修。
2. `tests/integration/g4_d/...::test_d15_same_uid_known_path_is_denied_by_mode_not_name` — **host-only 解释器路径**：测试降权到 uid 65534，而 宿主 home 下的 Python 安装目录为 0700，3.11 解释器不可穿越；用 G4-D 的 `/opt/miniconda3/envs/quant/bin/python` 重跑 **1 passed**。
3. `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text` — **host checkout mode**：工作树 config 为 0644，OCI stage 会 chmod 0444；G3-D `OPS-P2-b` 已知 host-only。
4. `tests/integration/sandbox/...::test_all_live_entrypoints_remain_blocked` — **host-only 子进程 PYTHONPATH**：硬编码 `/project/src:/deps`；OCI 内通过；独立 LiveGate probe 复算 exit 3。

### 11.2 固定 OCI full

| 运行 | 结果 | exit | 说明 |
|---|---|---:|---|
| 原始（uid 65534） | 1008 selected = **957 passed / 27 failed / 24 skipped / 7 deselected** | 1 | 27 项全部为环境不兼容（git/tar/`/bin/sh` 缺失、trusted dir 需 root） |
| 过滤（uid 65534） | 981 selected = **957 passed / 0 failed / 24 skipped / 34 environment deselects** | 0 | G4-A/unit-auth 以 uid 0 replay 覆盖 |
| Root replay（uid 0） | **294 passed / 0 failed / 2 deselected** | 0 | G4-A + unit auth + D05/D06 + sandbox；2 项为 CAP_CHOWN/`/bin/sh` |

OCI 配置：rootfs `25491e45…`、`--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534`、`/tmp`/`/work` 有界 tmpfs。34 项 deselect 的完整清单与原因见 `regressions/oci-env-deselects.json`。**没有把环境失败写成产品 PASS。**

### 11.3 各 G4 套件（host）

| 套件 | tests |
|---|---:|
| `tests/integration/g4_a` | 223 |
| `tests/integration/g4_b` | 38 |
| `tests/integration/g4_c` | 78 |
| `tests/integration/g4_d` | 26 |

### 11.4 Node（固定 rootfs，真实 TAP）

| 套件 | 结果 |
|---|---|
| adapter `adapter-signal.test.mjs` | **9 pass / 0 fail** |
| guard `guard-pr1.test.mjs` + `precheck.test.mjs` | **19 pass / 0 fail** |
| skill `plugin.test.mjs` | **8 pass / 0 fail** |
| **合计** | **36 pass / 0 fail** |

### 11.5 Ruff

- pinned `ruff 0.17.5`。
- G4 scoped（`src/autoteacher_m0` + `tests/integration/g4_*` + `scripts/g4`）：**All checks passed**。
- repo-wide：**37 findings**（绝大多数 `spikes/`，含 5 个可自动修复；`src/tests` 0），为既有历史告警，不属 G4 范围。

### 11.6 原始材料

`artifacts/g4/e/regression/`：`host-full.log`、`host-full-filtered.log`、`oci-full.log`、`oci-full-filtered.log`、`oci-root-replay.log`、`node-*.log`、`ruff.log`、`junit-*.xml`、`argv-and-exit.jsonl`、`SUMMARY.json`、分类 JSON。

---

## 12. 0-Key / LiveGate / 环境终态

| 断言 | 证据 |
|---|---|
| 0 真实 Key / 0 `.env` | 仅 `.env.example`；key-like 环境变量名 **0** |
| 仓库 secret 扫描 | 2 条 **false positive**（`DEEPSEEK_API_KEY=SENTINEL` 符号常量，非字面凭据）；详见 `regressions/zero-key.json` |
| 0 真实模型 / 0 外部 HTTP | G4-C/D 证据与 LiveGate probe：`real_model_calls=0`、`real_external_http_calls=0`、socket 外连尝试 `[]` |
| LiveGate | `BLOCKED`；即使所有可诊断证据满足，只剩 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` |
| `run_live.sh` | `/bin/sh` 执行 exit **3**，stderr `BLOCKED SECURITY_BLOCKED` |
| CLI `--live` | exit **3**；`AT_M0_LIVE_APPROVED`/`AT_M0_ALLOW_LIVE`/`AT_M0_APPROVAL_MD`/`AT_M0_APPROVAL`/假 `DEEPSEEK_API_KEY` 全部无效果 |
| Markdown 批准 | 仓库内路径被拒绝：`authorization must live outside the repository` |
| Adapter | `_require_live_authorization` → `SECURITY_BLOCKED` |
| rootfs/deps/stage | rootfs `25491e45…`、deps `e07729d7…`、G4 stage `9c9ce313…`、G3-D stage `e1ff1449…`，全部 canonical |
| 容器 | `podman ps -a` 空；未执行 `podman pull` |

---

## 13. E5-PreLive 两列状态

| Gate | NO_KEY_SUBSET | FULL_STATUS | 本轮能证明 / 不能证明 |
|---|---|---|---|
| E5-P01 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 测试签名与真实冻结字节 5 个根一致、漂移拒绝 / 外部人类签名未部署 |
| E5-P02 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | stage/runtime/lock/code/profile/plugin/tool schema 漂移均 pre-dispatch 拒绝 / 部署后动态文件不可写未证 |
| E5-P03 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | Markdown/env/CLI/自签 JSON 均不能开 gate / 正式审批与独立 trust root 未上线 |
| E5-P04 | **UNVERIFIED** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 捕获 schema 与白名单一致、仅 `skill_lookup` / 无可导出 merged registry，未知动态 tools 不可枚举 |
| E5-P05 | **PASS** | `BLOCKED_PENDING_HUMAN_DEPLOYMENT` | 哨兵跨 mount/env/log/IPC 拒绝、扫描器正控、watchdog 清理 / 真实 Key/TLS/账单/供应商硬额未证 |

`E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT` 固定不变；任何“无 Key 子集 PASS”不得写成 Full PASS。

---

## 14. Review Packet

- 路径：`artifacts/review-packet-g4-a6f3e0a27a516534803a1e3549dc60fbd107583c/`
- 内容：`changes/`（implementation/docs/protected diff）、`source/`（A/B/C/D 关键源码 + 行号索引 + builder/verifier）、`env/`、`auth/`、`runtime/`、`egress/`（真实 runs/DB/receipt/负例）、`e5/`（watchdog/revocation/sentinel/E5 两列）、`regressions/`、`matrix/`、`review/`、`manifest.json`、`hashes.sha256`、`packet-integrity-report.txt`。
- `manifest.json` 明确 `base_sha`、`impl_sha`、`code_impl_sha`、`docs_sha`、`build_sha`、`source_blobs`、`rootfs_sha256`、`deps_sha256`、`stage_manifest_sha256`、`runtime_sha`、`actual_loaded_modules`、`provider_route_kind=synthetic_only`、`real_model_calls=0`、`real_external_http_calls=0`、`key_present=false`、`live_gate=BLOCKED`、`evidence_levels`、`case_statuses`、`residual_risks`、`reviewer=NOT_ASSIGNED`、`previous_review=G3-D PASS`。
- 自校验：`sha256sum -c hashes.sha256` 100%、payload tree 复算一致、文件计数一致、0 symlink、secret scan PASS。实际数字记录在 Packet 的 `packet-integrity-report.txt` 与本文件所在的矩阵 `G4-E-02` 行。
- SQLite 为只读字节副本，builder 从未打开；包内不包含真实 Key、用户 Session、真实批准私钥或 rootfs/repo 全量副本。

---

## 15. 非主张与 STOP

1. 本报告**不是** G4 Full PASS；只有独立 Reviewer 可出具 `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`。
2. **不是** E5-PreLive Full；**不是** Live 授权；**不是** G4-H/G5/G6 批准。
3. 不主张真实 Provider/模型/计费/发票/exactly-once、供应商硬额度、真实 TLS/DNS/proxy、跨宿主可移植性。
4. 不主张 `registry == skill_lookup only`；B03 仍 `UNVERIFIED`。
5. 不主张已解决 P2-DISK/USERNS/RUN-IDENTITY；三项仍待维护者签收。
6. `G4-H-01..06` 全部 `BLOCKED`；`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`。
7. **STOP**：完成本提交与 Packet 后停止，不请求/不执行独立复核；由 Lead 指派 Reviewer。

---

*证据根：`artifacts/g4/`（gitignored）。原始日志、JUnit、argv/exit 与 Packet 均在本地；提交只含 docs、matrix 与 builder 脚本。*
