# M0 G4-F — 独立复核请求（No-Key Closeout Scope）

- **请求方**：G4-F6 Integration / Freeze / Review-Packet Agent（Lead 委派）
- **复核对象**：G4-F1..F5 的实现与证据，以及 G4-F6 的联合重跑、全量回归、矩阵与
  Review Packet。
- **复核性质**：**未参与 F1–F6 实现、证据生成、矩阵填写或 Packet 构建的独立 Reviewer**。
  必须自建 Probe、自跑命令、独立解析原始字节/账本；**不得**把 Owner 的
  `summary.json`/`checks.json`/`matrix.json` 结论文字当作独立证据。
- **允许的最终裁定（四选一，不得新增）**：

```text
PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
PARTIAL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
FAIL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE
BLOCKED_NEEDS_ENVIRONMENT
```

- **不允许的结论**：G4 Full PASS、E5-PreLive Full、G4-H/G5/G6 通过、Live 授权、`M0_GO`。
- **状态常量（必须原样写入报告）**：

```text
G4-H = NOT_AUTHORIZED
G5   = BLOCKED
G6   = NOT_RUN
LiveGate = BLOCKED
M0   = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

---

## 0. 独立性声明（Reviewer 报告开头必须写）

1. 未参与 G4-F1..F6 的实现、证据生成、矩阵填写或 Packet 构建；
2. 未修改 `src/`、`scripts/`、`tests/`、`config/`、`plugins/`、Stage、rootfs/deps、
   历史证据、矩阵或 Packet；
3. 所有关键结论来自自己的命令、Probe、原始字节/DB 副本与独立对账；
4. 运行环境、UTC 窗口、工作树状态、实际 HEAD 与 `git status`；
5. 0 真实 Key / 0 真实模型 / 0 外部 HTTP / 0 `podman pull` / 0 Live；
6. 唯一允许的写入：`docs/REVIEW_G4F_INDEPENDENT.md` 与 `artifacts/reviewer-g4f/`
   （gitignored）。**不得 commit / amend / push**。

---

## 1. 冻结输入核验

| 对象 | 期望值 |
|---|---|
| base | `bb2e9142a4e96e2b8fbe65bb99f1b4c045260251` |
| impl（证据 HEAD） | `e7d92967ec0ece80de4a1a3705f637e8eb9bde99` |
| code（最后 `src` 提交） | `dbacb76f98a1a91559ff70e02bf544ace76ed7b5`；`git diff dbacb76..e7d9296 -- src` 为空 |
| docs | `git log -1 --format=%H -- docs`，必须等于 Packet `manifest.json` 的 `docs_sha` |
| build | Packet `manifest.json` 的 `build_sha`，必须等于构建时 HEAD |
| G4-F stage | `artifacts/g4/c/stages/stage-20261119T142828Z`；manifest `82e10c6ffe37e401a58730e9abcaa691f19d6702a7276c03df625d5b4636e501`；tree `7d32ec1d8b02726ba52ef8303e8677b46384e9954559e838b31bb8c58f222068` |
| stage base | `head_at_build == e7d9296`；`trusted_tree 6d887bbf…`、`candidate_tree 2459db9d…` |
| rootfs / deps | `25491e45…` / `e07729d7…`（canonical；OCI 后检查） |
| DSH runtime | `1cc41d5a…`，版本 `0.2.2rc2` |
| Node / adapter | `v22.23.2` / `2cb42461…` |
| Packet | `artifacts/review-packet-g4f-e7d92967ec0e/`；`sha256sum -c hashes.sha256` 100%；payload tree 复算一致；0 symlink |
| 矩阵 | `docs/Autonomous_Teacher_M0_G4F_Closeout_Test_Evidence_Matrix_v1.0.csv`；46 行 = 38 PASS / 2 UNVERIFIED / 5 NOT_RUN / 1 BLOCKED |

任何不一致先记录、不要 reset/force；若漂移导致无法复核，裁定
`BLOCKED_NEEDS_ENVIRONMENT` 并给出具体 SHA/路径。

---

## 2. 必须完成的复核域（R0–R8）

### R0 — Packet / Stage / loaded modules / 旧 Stage fail-closed

- 独立复算 base/impl/code/docs、`src` 树、protected files、source blobs、rootfs/deps/
  stage/runtime canonical。
- 逐文件验证 Packet：`sha256sum -c`、payload tree、manifest count、无 symlink、
  无真实 Key/用户 Session/宿主个人路径（`<WORKSPACE>`/`<HOST_PYTHON>` 等占位符除外）。
- **不要只看“文件在目录里”**：从真实 P2 证据读取 `inspect.getfile`/容器 self-report，
  证明实际加载的是 `stage-20261119T142828Z`，不是旧 G3-C/G3-D stage；逐模块比对
  `sha256 == HEAD blob == stage 副本`（18/18）。
- 自建“旧 Stage”重跑：用旧 stage/旧源码路径启动必须 fail-closed（`stage_base_not_head`
  或 manifest 校验失败）；不能复现 G3-C 的 stage-old-code 错位。
- 复算 F6-01/F6-02 的 base/head/manifest/tree/loaded modules 与“stage unchanged”。

### R1 — 静态复验（不受 F6 改动影响）

- 核验 `gates.py` 恒 BLOCKED、`run_live.sh` 仍 exit 3、`dsh_adapter.py` 四个 live 入口
  仍先 `_require_live_authorization()`、`cli.py --live` 仍先 `LiveGate.require_live()`。
- 核验 `authorization.py` 严格解析/可信文件边界/5 绑定根/预算镜像/单次消费；
  `egress.py` 的 `TrustedSendAuthorization` 无 JSON 构造入口、一次性 consume、real route
  恒 BLOCKED；`watchdog.py` absence 语义。
- 核验 `controller.py` 的 `dispatch_gate=None` 时 G3-C/D 行为不变；门开启时
  `authorize→consume→dispatch` 是唯一发送路径；F2 的 per-dispatch 校验先于 Reserve/Claim。
- 检查是否存在第二条未记账 provider 路径、可打开 Live 的 env/flag/JSON、Candidate 可
  调用的可信 API；核验 `scripts/g4/launch_c.py` 的 `getattr` 兼容不改变 F5 显式传参语义。

### R2 — 自建 scanner / 负例（不得复用 Owner 测试）

- 自建临时 git 仓库：真实格式 token 必须 exit 1 且输出掩码（不得打印完整 Secret）；
  仅哨兵/占位符必须 exit 0。
- 覆盖 F1 的 fail-closed 形态：`SENTINEL`+hex、`SENTINEL`+`sk-`、`TEST_ONLY_`+hex/base64、
  `sentinel_abc123`、前缀不在开头；以及合法哨兵（大小写/引号/`\n`/`_SELFTEST_VALUE`）不报。
- 覆盖 AWS/Azure/GCP/HF/GitLab/npm/Slack/JWT/JWE/Bearer/Basic/DB URL/连接串/PEM 变体；
  记录 `kind` 与掩码，不输出完整值。
- 对工作树与全历史跑一次独立扫描；与 Owner 的 `findings=0` 对比，任何差异按 P0/P1 记录。

### R3 — auth / OS / 工具面 / 辅助请求攻击

- 以真实 Candidate UID `65534`/mount namespace 尝试读写可信 Approval/Keys/Revocations/
  Policy/Broker DB/Secret sentinel；必须 OS/Protocol 拒绝。
- 重跑 G3-B 旧四类绕过（读 DB、写 DB、写 Policy、绕过 Controller Claim）与
  G4-D 的 D15 同 UID 已知路径攻击；必须指认 mount/DAC/namespace 机制。
- 工具面：未批准 tool、修改 schema、额外 tool、重复 tool、message tool-call/addition/
  removal、purpose title/judge/compaction、foreign origin、journal 写失败；
  必须稳定错误码 + 账本 0 + Fake 0 + dispatch-window `reserved=false`。
- 辅助请求：自建 probe 证明 title 在 IPC/adapter 层被拒；真实 run 中
  dispatch == assistant == receipt == Fake；不要仅引用 Owner 的 `NO_EXTRA_PROVIDER_REQUEST_OBSERVED`。

### R4 — 真实 DSH resume + Tool 账本

- 在冻结 stage 上运行真实 DSH Echo、Tool 两轮、`start_session`→`resume_session`。
- 逐一比较：不同 `call_id`；`Prepared.request_digest == BrokerClaim.request_digest`；
  `Attempt.payload_digest == FakeReceipt.raw_sha256`；两组独立
  Reserve/Claim/Attempt/Receipt/Settlement；不重发、不合并计费。
- 校验第二请求包含第一轮 `skill_lookup` 结果/上下文；额外 provider 请求为 0；
  F4 旧 Attempt 行在 resume 后逐字段不变（用 phase DB 备份，不信任 runner checks）。
- 核对 usage：`input_used = input + cacheRead + cacheWrite`，`output_used = output`；
  与 receipt 字段级相等。

### R5 — revocation / timeout / crash 窗口

- 自建/复用真实双 Principal 运行：pre-reserve、post-reserve pre-send、post-send；
  pre-send/post-send timeout；`authorize`/`consume`/`send`/`receipt` 各窗口 crash。
- 判定规则：wire 前可停止时不得创建 reservation/attempt/Fake；已 Reserve 未跨 wire
  只能保守（`held=reserved>0`、不 settle/fail、不重发）；已跨 wire 只能按 Broker 终态
  结算一次，不撤回、不二次结算。
- 独立检查：无 `Fee=0`、无双重发送、无“held=0 且 Broker PENDING”、replay 为 no-op。
- 对比 `artifacts/g4f/f6/integration/f5/matrix.json` 的 13 case/162 checks，任何差异
  按 P0/P1 记录（不得把环境失败写成产品失败）。

### R6 — LiveGate / Key / 网络负例

- 独立执行：`LiveGate.inspect`（含“所有证据满足”）、`require_live`、
  `/bin/sh scripts/run_live.sh`、CLI `smoke --live`、adapter `_require_live_authorization`。
- 注入 `AT_M0_LIVE_APPROVED`、`AT_M0_ALLOW_LIVE`、`AT_M0_APPROVAL*`、假
  `DEEPSEEK_API_KEY`、Markdown 批准、自签 JSON；必须全部无效。
- 检查不存在 Key-like env 泄漏、真实外部 socket 尝试、`podman pull`；记录 LiveGate reasons。
- 比对 `gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py` 与 base 的字节；任何新的
  allow/旁路路径是 **P0**。

### R7 — 独立解析 SQLite / Receipt / DSH Trace / OCI 计数

- 用独立脚本解析原始 SQLite（只读副本到 `/tmp`，不在原路径打开）、Fake Receipt、
  Fake counter、DSH Trace、JSON/JUnit；不得复用 Owner `checks.json` 的 status。
- 对账：Reservation/Claim/Attempt/Receipt 行数、`call_id`、`reservation_id`、
  `receipt_id`、usage/cost、两对 Digest、Fake counter；负例后账本 0；重放后 Fake 不增；
  崩溃后 Attempt/Receipt 状态符合保守规则。
- 复核 F6 的 host/OCI/Node 计数：host 1357 = 1352/4/1；OCI raw 1087 =
  1018/26/43；OCI filtered 1044 = 1018/26/43/0；root replay 351/8/0；
  Node 9+19+8=36。若 Reviewer 环境不同，先记录环境差异再分类，不得改写 Owner 数字。
- 复核 43 项 OCI deselect 是否全部为环境类（git/tar/sh、root-only、host uid 0
  peercred、relative deps、frozen stage absent），且显式包含
  `test_digest_sidecar_contract`。

### R8 — 回归、清理、证据分级与裁定

- 复跑（或抽查）host full、固定 OCI、Node、Ruff、scanner；逐项归因已知 4 项 host 失败
  （frozen-src、D15 0700-home、host config mode、sandbox hardcoded PYTHONPATH），
  不得静默 deselect。
- 检查清理：`podman ps -a` 空、rootfs/deps canonical、stage tree 运行前后一致、
  socket/run-dir absence；`rm -f rc=0` 不作为 absence。
- 证据分级：L2-REAL-DSH / L2-RAW-UDS / L2-OS / L1-HOST / L1-STATIC / L1-PACKET /
  UNVERIFIED / HUMAN-REQUIRED；任何跨级拼接成“全链 PASS”必须降级。
- 复核矩阵 46 行状态是否与真实证据一致；E5 两列（`F2-08`/`E5-P04` 必须 UNVERIFIED；
  E5 FULL 必须 `BLOCKED_PENDING_HUMAN_DEPLOYMENT`）；`G4-H-01..06` 仍 BLOCKED。

---

## 3. 证据分级与禁止事项

| 级别 | 含义 | 本轮示例 |
|---|---|---|
| L2-REAL-DSH | 真实双 Principal 容器 + 真实 DSH + Fake Provider | F2 Echo/Tool、F4 resume、F5 7 个 DSH case |
| L2-RAW-UDS | 真实容器 raw UDS（hold mode） | F2 raw 矩阵、F5 6 个 hold case |
| L2-OS | 真实容器/OS 负例、OCI | 固定 OCI、Node、root replay |
| L1-HOST | 宿主真实进程/产品代码 | F3 host 8 case、pytest 套件 |
| L1-STATIC | 静态/AST/字节比对 | scanner、protected files |
| L1-PACKET | Packet 自校验 | F6-05 |
| UNVERIFIED | 无法证明 | B03/E5-P04、F4 字节级/子场景 |
| HUMAN-REQUIRED | 只能由维护者 | E5 Full、G4-H |

禁止：

1. 不跑真实 Provider/模型/外部 HTTP；不读取/注入/输出真实 Key、账户 Cookie、用户 Session。
2. 不修改实现、测试、矩阵、历史证据、Stage、rootfs/deps、历史 Packet。
3. 不把 Owner 的 `summary.json`/`checks.json`/`matrix.json` 当独立证据；必须自建 Probe。
4. 不把“无 Key 子集 PASS”写成 E5 Full / G4 Full / Live 授权。
5. 不为了“让测试绿”而放宽断言、`chmod 777`、开放 TCP、启用 Host fallback、伪造签名/账本。
6. 不 commit/amend/push；只写 `docs/REVIEW_G4F_INDEPENDENT.md` 与
   `artifacts/reviewer-g4f/`。
7. 不将环境失败（git/tar/sh 缺失、root-only、rootfs 挂载点）写成产品失败；反之也不得隐藏。
8. 若发现 STOP 条件（真实 Key/外网、LiveGate 可放行、Candidate 可写可信状态、
   账本 FREE/双发送、Watchdog 失效仍继续），立即停止、保全证据、报告 Lead。

---

## 4. 必须产出的 Reviewer 报告

`docs/REVIEW_G4F_INDEPENDENT.md` 至少包含：

1. 独立性声明、环境、UTC、冻结 SHA、`git status`；
2. R0–R8 逐项结论（PASS/FAIL/UNVERIFIED）与自建命令/证据路径；
3. **P0/P1/P2 清单**（P0/P1 必须给出可复制的反例与原始字节/DB 行）；
4. 对 46 行矩阵的独立复核（状态是否与证据一致；REV 行的填写由 Reviewer 自行完成）；
5. E5 两列表（P04 必须 UNVERIFIED；FULL 五项 BLOCKED_PENDING_HUMAN_DEPLOYMENT）；
6. Packet 哈希/API 复核（`impl_sha`/`docs_sha`/`build_sha`/`runtime_sha`/
   `stage_manifest_sha256`/`source_blobs`/`actual_loaded_modules`/changes diff/hashes）；
7. 残余风险与 human-required 项；
8. **唯一裁定**（四选一）及范围限定；
9. 明确声明 `G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
   `LiveGate=BLOCKED`、`M0=DECISION_PENDING`、
   `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

---

## 5. 裁定枚举与含义

### `PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE`

F1–F6 的工程/隔离/合成账本/授权校验/失败窗口/冻结材料被独立复验，**P0=0、P1=0**。
仅限本机冻结环境；**不代表** E5 Full、人类授权、真实 Provider/计费、G4-H/G5/G6/Live。

### `PARTIAL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE`

有功能证据但重要项未验证（例如无法重跑关键 L2、Packet 哈希不符、F5 某窗口无法复核、
F4 sub-case 无法独立确认）。必须列出缺失测试与真实原因。

### `FAIL_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE`

存在可复制的安全或账本反例（权限绕过、可计费出站、Key 泄漏、未授权 Fake send、
账本 FREE、双发送等）。

### `BLOCKED_NEEDS_ENVIRONMENT`

无法构建真实 OS 隔离/受审 Runtime；不许用 mock 替代。必须给出具体缺失环境与已尝试命令。

---

## 6. 交接与 STOP

- Reviewer 开始前确认工作树 clean、`podman ps -a` 空、rootfs/deps canonical；
  结束时再次确认（Node/OCI 后清理 rootfs 挂载点）。
- 复核完成后 **STOP**：不自动进入 G4-H/G5/G6，不签发任何 Live 授权，不改写历史裁定。
- Lead 收到 Reviewer 报告后才决定是否发起维护者决策；**Agent 不得自行把无 Key PASS
  映射为 Live 权限**。

---

*本请求只覆盖 G4-F 无 Key closeout 范围；不构成授权、不构成 E5-PreLive Full、
不构成 Live/G5/G6 许可。*
