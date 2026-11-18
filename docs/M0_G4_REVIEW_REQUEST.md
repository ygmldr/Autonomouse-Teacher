# M0 G4 — 独立复核请求（No-Key PreLive Engineering Scope）

- **请求方**：G4-E Freeze / Review-Packet Agent（Lead 委派）
- **复核对象**：G4-A/B/C/D/E 的无 Key 工程与冻结 Packet
- **复核性质**：**未参与实现与证据生成的 Independent Reviewer**，必须自建 Probe、自跑命令、独立解析原始字节/账本；不得复用 Owner 的 `summary.json`/`checks.json` 结论文字作为判定。
- **冻结身份**：base `017c747`、impl `a6f3e0a`、code `d3d429c`、docs `本 G4-E 文档提交`；Packet `artifacts/review-packet-g4-a6f3e0a27a516534803a1e3549dc60fbd107583c/`。
- **允许的最终裁定**（只能四选一）：

```text
PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
PARTIAL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
FAIL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE
BLOCKED_NEEDS_ENVIRONMENT
```

- **不允许**：G4 Full PASS、E5-PreLive Full、G4-H/G5/G6 通过、Live 授权、`M0_GO`。
- **状态常量**：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

---

## 0. 身份与独立性声明（Reviewer 必须先写）

Reviewer 在报告开头必须声明：

1. 未参与 G4-00/A/B/C/D 的实现、证据生成、矩阵填写或 Packet 构建；
2. 未修改 `src/`、`scripts/`、`tests/`、`config/`、`plugins/`、Stage、rootfs/deps、历史证据、矩阵或 Packet；
3. 所有关键结论来自自己的命令、Probe、原始字节/DB 副本与独立对账；
4. 运行环境、UTC 窗口、工作树状态、实际 HEAD 与 `git status`；
5. 0 真实 Key / 0 真实模型 / 0 外部 HTTP / 0 `podman pull` / 0 Live；
6. 唯一允许的写入：`docs/REVIEW_G4_INDEPENDENT.md` 与 `artifacts/reviewer-g4/`（gitignored）。**不得 commit/amend/push**。

---

## 1. 冻结输入核验

| 对象 | 期望值 |
|---|---|
| base | `017c747631cae1e7788014c4ef9e6056c141fecd` |
| impl | `a6f3e0a27a516534803a1e3549dc60fbd107583c` |
| code | `d3d429cf9d0cb1e9dbc68317928631db413be309` |
| docs | Packet `manifest.json` 的 `docs_sha`（必须等于 `git log -1 -- docs`） |
| 最后 `src` 提交 | `d8a8dc83673d6236884bb41574214e5b2106fcd4`；`git diff d3d429c..HEAD -- src` 为空 |
| Packet | `artifacts/review-packet-g4-a6f3e0a.../`；`sha256sum -c hashes.sha256` 100%；payload tree 复算一致；0 symlink |
| G4 stage | `artifacts/g4/c/stages/stage-20261118T193401Z`；manifest `85353018…17de48`；tree `9c9ce313…358762b` |
| G3-D stage | `e1ff1449…` / `644823d4…`，必须未被 G4 修改 |
| rootfs / deps | `25491e45…` / `e07729d7…` |
| DSH runtime | `1cc41d5a…`，版本 `0.2.2-rc.2` |
| Node / adapter | `v22.23.2` / `2cb42461…` |
| 矩阵 | 85 行；E 后统计 62 PASS / 10 PARTIAL / 2 UNVERIFIED / 5 NOT_RUN / 6 BLOCKED |

任何不一致先记录，不要 reset/force；若漂移导致无法复核，裁定 `BLOCKED_NEEDS_ENVIRONMENT` 并给出具体 SHA/路径。

---

## 2. 必须完成的复核域（R0–R8）

### R0 — 身份、Packet、Stage 加载、旧 Stage fail-closed

- 独立复算 base/impl/code/docs、`src` 树、protected files、source blobs、rootfs/deps/stage/runtime canonical。
- 逐文件验证 Packet：`sha256sum -c`、payload tree、manifest count、无 symlink、无真实 Key/用户 Session/宿主个人路径。
- **不要只看“文件在目录里”**：从真实运行中读取 `inspect.getfile`/等价证据，证明实际加载的是 G4 stage，不是旧 G3-C stage（旧 tree `fcdb0de4…`、旧 `attempts.py` `33017e75…`）。
- 自建“旧 Stage”重跑：用旧 stage/旧源码路径尝试启动，必须 fail-closed；不能复现 G3-C 的 stage-old-code 错位。

### R1 — 静态复验

- 逐行核验 `gates.py` 仍恒 BLOCKED、`run_live.sh` 仍 exit 3、`dsh_adapter.py` 四个 live 入口仍先 `_require_live_authorization()`、`cli.py --live` 仍先 `LiveGate.require_live()`。
- 核验 `authorization.py` 的 strict parser、可信文件边界、5 个绑定根、预算镜像、单次消费；`egress.py` 的 `TrustedSendAuthorization` 无 JSON 构造入口、`TrustedSendGate` 一次性 consume、real route 恒 BLOCKED；`watchdog.py` 的 absence 语义。
- 核验 `controller.py` 的 `dispatch_gate=None` 时 G3-C/D 行为不变；门开启时 `authorize→consume→dispatch` 是唯一发送路径。
- 检查是否存在第二条未记账 provider 路径、可打开 Live 的 env/flag/JSON、Candidate 可调用的可信 API。

### R2 — 自建 auth fuzz（不得复用 Owner 测试）

至少覆盖：

- 失效/错误签名、未注册 key、轮换后旧签名、撤销；
- Ed25519 异常点：小阶/identity、torsion、mixed-order、非 canonical 公钥/R、`S>=L`、短/长签名、非 bytes；
- `bool` 限额、`float` 限额、重复 JSON key（顶层与嵌套）、NaN/Infinity、unknown fields；
- Runtime SHA / code / lock / profile / tool schema / route / budget / deadline 不匹配；
- 过期、not-before、clock skew、重放、跨 epoch；
- 仓库内 Markdown/JSON、symlink、group/other 可写、candidate uid 拥有的可信文件。

**判定**：任何失败必须 `approved=False` 且 `billable_send_authorized=False`；合法合成签名可 `approved=True`，但 `LiveGate`/CLI/Adapter/script 仍 BLOCKED。分列 `signature_valid` 与 `billable_send_authorized`，不得合并。

### R3 — 真实 Candidate UID/Mount 旧四类攻击

- 以真实 Candidate UID `65534`/mount namespace 尝试读写可信 Approval/Keys/Revocations/Policy/Broker DB/Secret sentinel；必须 OS/Protocol 拒绝。
- 重跑 G3-B 旧四类绕过（B-1 读 DB、B-2 写 DB、B-3 写 Policy、B-4 绕过 Controller Claim），必须全部关闭。
- 同 UID + 已知路径的旧 Run 攻击：`/work/state`、socket、旧 run dir；不得用“目录名随机”解释，必须指认 mount/DAC/namespace 机制。
- 记录 `SO_PEERCRED`、uid_map/gid_map、socket mode/owner、mountinfo；不得声称已有 per-run OS 身份（P2-RUN-IDENTITY）。

### R4 — 真实 DSH Tool 两轮

- 运行真实 DSH Tool 两轮，逐一比较：两个不同 `call_id`；`Prepared.request_digest == BrokerClaim.request_digest`；`Attempt.payload_digest == FakeReceipt.raw_sha256`；两组独立 Reserve/Claim/Attempt/Receipt/Settlement；不重发、不合并计费。
- 校验第二请求包含第一轮 `skill_lookup` 结果；额外 provider 请求为 0。
- 不要把“两个摘要不相等”当密码学条件；必须逐字节映射。

### R5 — 中断 Broker/Trusted/Watchdog、SIGKILL、DB Fee=0/双发送

- 在发送前/发送后/结算前中断 Broker/Trusted/Candidate；SIGKILL 进程树。
- 检查 DB 是否出现 `Fee=0`、双发送、无 Attempt 的 Receipt；未完成账本必须保守（`ATTEMPT_STARTED` / `BILLABLE_UNKNOWN` / `SETTLEMENT_UNCERTAIN`），不得 FREE。
- 检查恢复路径不自动重发；`pending.json`/`retry_allowed=false`。
- 检查 watchdog 清理：`/proc` absence、`podman ps -a` 空、socket/run-dir/rootfs-target `lstat` ENOENT；`rm -f` rc=0 不作为 absence。

### R6 — LiveGate / CLI / Adapter / run_live 字节与旁路

- 独立执行：`LiveGate.inspect`（含“所有证据满足”）、`require_live`、`/bin/sh scripts/run_live.sh`、CLI `smoke --live`、Adapter `_require_live_authorization`。
- 注入 `AT_M0_LIVE_APPROVED`、`AT_M0_ALLOW_LIVE`、`AT_M0_APPROVAL*`、假 `DEEPSEEK_API_KEY`、Markdown 批准、自签 JSON；必须全部无效。
- 比对 `gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py` 与 base/795c263 的字节；任何新的 allow/旁路路径是 **P0**。

### R7 — 独立解析 SQLite/Receipt/DSH Trace

- 用独立脚本解析原始 SQLite（只读副本到 `/tmp`，不在原路径打开）、Fake Receipt、Fake counter、DSH Trace、JSON/JUnit；不得复用 Owner `checks.json` 的 status。
- 对账：Reservation/Claim/Attempt/Receipt 行数、`call_id`、`reservation_id`、`receipt_id`、usage/cost、两对 Digest、Fake counter。
- 负例后 ledger 必须为 0；重放后 Fake 不增；崩溃后 Attempt/Receipt 状态符合保守规则。

### R8 — 证据分级、Packet 哈希/API、裁定

- 将证据分级：real DSH/no key、raw UDS、host/unit、static、unverified、human-required；任何跨级拼接成“全链 PASS”必须降级。
- 复核 Packet 的 `impl_sha`、`docs_sha`、`build_sha`、`runtime_sha`、`stage_manifest_sha256`、`source_blobs`、`actual_loaded_modules`、变更 diff、哈希脚本。
- 复核矩阵 E01..E05 是否与真实证据一致；E06..E10 由 Reviewer 自行填写（不得只抄 Owner）。
- 复核 E5-P01..P05 两列：`NO_KEY_SUBSET` 与 `FULL_STATUS`；P04 必须保持 `UNVERIFIED`，FULL 五项必须 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
- 核验 `G4-H-01..06` 仍 BLOCKED、`G5` 未启动、`G6` 未运行、`M0` 未 GO。

---

## 3. 证据分级与禁止事项

### 3.1 分级

| 级别 | 含义 | 本轮示例 |
|---|---|---|
| L2-REAL-DSH | 真实双 Principal 容器 + 真实 DSH + Fake Provider | G4-C c01/c02/c18、G4-D D01/D02/D03 |
| L2-OS | 真实容器/OS 负例、真实 DB/absence | G4-D D01/D15、G4-C negatives |
| L1-HOST | 宿主真实进程/真实产品代码，但非容器 | G4-A、G4-D D05/D06/P01..P05 |
| L1-STATIC | 静态/AST/字节比对 | protected files、source blobs |
| L1-PACKET | Packet 自校验/哈希 | G4-E-02 |
| UNVERIFIED | 无法证明 | B03、D13、E5-P04 |
| HUMAN-REQUIRED | 只能由维护者 | G4-H-01..06 |

### 3.2 禁止

1. 不跑真实 Provider/模型/外部 HTTP；不读取/注入/输出真实 Key、账户 Cookie、用户 Session。
2. 不修改实现、测试、矩阵、历史证据、Stage、rootfs/deps、G3-D Packet。
3. 不把 Owner 的 `summary.json`/`checks.json` 当独立证据；必须自建 Probe。
4. 不把“无 Key 子集 PASS”写成 E5 Full / G4 Full / Live 授权。
5. 不为了“让测试绿”而 `chmod 777`、开放 TCP、启用 Host fallback、伪造签名/账本。
6. 不 commit/amend/push；只写 `docs/REVIEW_G4_INDEPENDENT.md` 与 `artifacts/reviewer-g4/`。
7. 不将环境失败（git/tar/sh/root-only）写成产品失败；反之也不得隐藏。

---

## 4. 必须产出的 Reviewer 报告

`docs/REVIEW_G4_INDEPENDENT.md` 至少包含：

1. 独立性声明、环境、UTC、冻结 SHA；
2. R0–R8 逐项结论（PASS/FAIL/UNVERIFIED）与自建命令/证据路径；
3. **P0/P1/P2 清单**（P0/P1 必须给出可复制的反例与原始字节/DB 行）；
4. 矩阵 E06..E10 的 Reviewer 填写（状态、命令、UTC、exit、证据、残余）；
5. E5 两列表；
6. Packet 哈希/API 复核；
7. 残余风险与 human-required 项；
8. **唯一裁定**（四选一）及范围限定；
9. 明确声明：`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

---

## 5. 裁定枚举与含义

### `PASS_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`

G4 工程/隔离/合成账本/授权校验/E5 无 Key 子集被独立复验，**P0=0、P1=0**。仅限本机冻结环境；**不代表** E5 Full、人类授权、真实 Provider/计费、G4-H/G5/G6/Live。

### `PARTIAL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`

有功能证据但重要项未验证（例如 Reviewer 无法重跑关键 L2、Packet 哈希不符、E5 某一项无法复核）。必须列出缺失测试与真实原因。

### `FAIL_FOR_G4_NO_KEY_PRELIVE_ENGINEERING_SCOPE`

存在可复制的安全或账本反例（权限绕过、可计费出站、Key 泄漏、未授权 Fake send、账本 FREE、双发送等）。

### `BLOCKED_NEEDS_ENVIRONMENT`

无法构建真实 OS 隔离/受审 Runtime；不许用 mock 替代。必须给出具体缺失环境与已尝试命令。

---

## 6. 交接与 STOP

- Reviewer 必须在开始前确认工作树 clean、`podman ps -a` 空、rootfs/deps canonical；结束时再次确认。
- 若发现 STOP 条件（真实 Key/外网、LiveGate 可放行、Candidate 可写可信状态、账本 FREE/双发送、Watchdog 失效仍继续），立即停止、保全证据、报告 Lead。
- 复核完成后 **STOP**：不自动进入 G4-H/G5/G6，不签发任何 Live 授权，不改写历史裁定。
- Lead 收到 Reviewer 报告后才决定是否发起维护者决策；**Agent 不得自行把无 Key PASS 映射为 Live 权限**。

---

*本请求只覆盖 G4 无 Key 工程范围；不构成授权、不构成 E5-PreLive Full、不构成 Live/G5/G6 许可。*
