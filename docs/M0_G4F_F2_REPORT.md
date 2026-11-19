# M0 G4-F2 — 实际工具面与辅助模型请求可观测性（No-Key）

- **任务**：G4-F 指令 F2 —— 验证/补齐 Controller 在每次 dispatch 前的实际 tool 校验；
  用真实 DSH 确认 session-title/compaction/judge/retry/subagent 等辅助路径是否产生
  provider 请求；对绕过 Reserve/Claim 的路径 fail-closed；真实双 Principal 两轮 +
  raw-UDS 负例 + 证据 + 回归。
- **基线**：`7000f72`（F1/F3 完成、工作区 clean 已核实）。
- **实现提交**：`40af7b1`（parent `b963ad4`）、`64d32cb`、`339312b`；
  本文件随 docs 提交归档。证据运行 HEAD 为 `339312b`，stage base 与 HEAD 相同。
- **性质**：**no-key / no-model / no-external-network / no-live**。0 真实 Key、0 模型调用、
  0 外部 HTTP/TCP、0 `podman pull`、0 Live；真实 DSH 为 `0.2.2-rc.2` + Fake Provider，
  `--network none`，固定 rootfs/deps canonical。
- **不声明**：本文件不构成 G4 Full / E5-PreLive Full / G4-H/G5/G6 / Live 授权；
  **不声称 DSH 存在权威 merged tool registry 导出**；B03/E5-P04 仍为 `UNVERIFIED`。

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| 实际工具面 | **可观测**：每次进入 Controller 的请求写一条 `dispatch-window.jsonl`（tool 名 + canonical schema SHA-256 + Admission approved SHA-256 + purpose + peer origin + outcome） |
| per-dispatch 校验 | 复用既有 **B04** 白名单（name + canonical digest，Reserve/Claim 之前）；本轮补齐：**重复 tool 名、messages 内 tool-call/tool-addition/tool-removal 引用、Controller 侧 purpose 复核、声明了 `expected_peer_uid` 时的 origin 校验**；均以稳定错误码拒绝且 0 预留/0 Claim/0 Attempt/Fake 0 |
| 真实 DSH 账本 | Echo **1/1/1/1/1**（Reservation/Claim/Attempt/Receipt/Fake）；Tool 两轮 **2/2/2/2/2**；两套 call_id/reservation_id 独立；DSH usage == Receipt usage（launcher 20 项检查全 PASS） |
| 辅助请求 | 冻结配置下 **`NO_EXTRA_PROVIDER_REQUEST_OBSERVED`**：2 个真实 run 共 3 次 dispatch == 3 条 assistant message == 3 个 Receipt == Fake 3；`session/title` 2 次均为 `source.kind=fallback`；adapter 对 `purpose="title"` 在 UDS 之前拒绝（`G3B_BRIDGE_PURPOSE`） |
| B07 session-title | 不再是“未证明”：**冻结配置下未产生 provider 请求，且有机制证据**（merged entry list 无 `session-title-*` provider、插件仅在 `register()` 后调用 provider、adapter purpose guard、真实 trace fallback、0 extra dispatch）。**仍不能证明**任意未来配置/动态注册；该残余明确保留 |
| registry | DSH `0.2.2-rc.2` **仍无权威 merged registry/schema 导出**；本轮只证明“实际请求的工具面可观测 + 未批准工具无法进入 dispatch”，**不把 merged entry list 冒充 registry**；B03/E5-P04 维持 `UNVERIFIED` |
| 负例 | host 30 tests PASS；真实 Candidate UID raw-UDS 7 个 tool 负例全拒绝且账本 0，2 个 title 请求在 IPC schema 层 `BAD_TYPE` 且账本/日志零增量，1 个批准请求正常记账 |
| 回归 | g4_a 223 / g4_b 38 / g4_c 78 / g4_d 25(+1 host-env) / g4_f3 23 / g4_f2 30 / g3c 110 / g3d 143(+1 frozen-src 预期) / g3_bridge 31 / gates 14；ruff 0.17.5 scoped PASS |
| 终态 | HEAD `339312b` + docs 提交；`podman ps -a` 空；rootfs `25491e45…`、deps `e07729d7…` canonical；LiveGate 仍 `BLOCKED` |

---

## 1. 基线与提交链

| 对象 | 值 |
|---|---|
| 起点 | `7000f72`（F1/F3 完成；工作区 clean） |
| 并行 F4 提交（非本包） | `b963ad4`（F4 feat）、`2ff60c0`/`25fb9a2`（F4 docs） |
| 本包 feat | **`40af7b1`** `feat: G4-F2 per-dispatch tool and auxiliary request observability (no-key)`；parent `b963ad4` |
| 本包 fix | **`64d32cb`** `fix: G4-F2 evidence runner frozen case names and lazy claim table (no-key)` |
| 本包 fix | **`339312b`** `fix: G4-F2 evidence analysis handles reused DSH request headers (no-key)` |
| 证据运行 HEAD | `339312b`；G4-C stage `stage-20261119T123154Z`（base `339312b`，manifest `3914bb47…`，tree `29967d32…`） |
| docs | 本文件（docs 提交），不 amend / 不 push |

> 说明：`7000f72` 之后 F4 在同一工作区提交了 docs/脚本（未改 `src/`），所以
> 本包 feat 的 parent 是 `b963ad4` 而不是 `7000f72`。本包只 `git add` 自己的
> `src/autoteacher_m0/bridge/*`、`scripts/g4/{launch_c,probe_runtime,stage/trusted_entry_g4c}.py`、
> `tests/integration/g4_f2/**` 与本报告；未 stage/修改 F4 的文件。

---

## 2. 范围、证据分级与“观测”定义

本包把证据分成三档，报告与 `summary.json` 都按此表述：

| 档 | 内容 |
|---|---|
| **L2-REAL-DSH** | 固定 rootfs/deps/stage、真实 DSH `0.2.2-rc.2`、真实双 Principal、`--network none`、Fake Provider；Echo + Tool 两轮 |
| **L2-RAW-UDS** | 真实 Candidate 容器（uid 65534）经真实 `/work/g3b/bridge.sock` 发送 raw frame；真实 Controller/Broker/Fake；快照为只读 SQLite 副本 |
| **L1-HOST / L1-PROBE** | `tests/integration/g4_f2` 的 30 个 host 测试；内置/独立 adapter purpose probe；merged entry list 与 DSH trace 的静态/动态交叉 |

**“实际工具面”定义**：一次 dispatch 中，Controller 实际接收并允许（或拒绝）的
tool 定义集合（`tools[]` 的 name + canonical schema SHA-256），加上 conversation
history 中引用的 tool 名（`tool-call` / `tool-addition` / `tool-removal` 块的
`name`/`toolName`）。它不是 DSH 内部 registry 的导出，也不是 merged config 的推断。

---

## 3. 实际工具面：Controller per-dispatch journal

### 3.1 记录位置与 schema

- 文件：`<attempt_db 同目录>/dispatch-window.jsonl`（真实容器为
  `/work/state/dispatch-window.jsonl`，root:root 0600，Candidate 不可读）。
- 写入：每条记录 `O_WRONLY|O_APPEND|O_CREAT|O_NOFOLLOW` + `fsync`；最多一次
  dispatch 一条；字段不含 prompt/message 文本、tool 参数、Key 或凭据。
- schema：`m0.g4f.dispatch-window.v1`，主要字段：

| 字段 | 含义 |
|---|---|
| `dispatch_seq` / `instance_id` | Controller 实例内单调序号 / 实例 id |
| `transport_id` | UDS transport（客户端生成，仅作关联） |
| `origin` | `SO_PEERCRED` 的 `{kind:"unix_peer", uid, gid, pid}`；in-process 调用为 `{kind:"in_process"}`；PID 在 PID namespace 内可为 0（身份只取 uid） |
| `purpose` | 实际请求的 purpose（真实 DSH conversation 为 `null`；缺失为 `"<missing>"`） |
| `tools[]` | 每个请求 tool 的 `{name, schema_sha256, approved_sha256, approved, origin:"request.tools"}`（最多 16 行，`tool_count` 为真实数量） |
| `message_tool_refs[]` | conversation 中的 `tool-call`/`tool-addition`/`tool-removal` 引用 `{origin:"messages[i].content[j]", kind, name, approved}` |
| `approved_tool_set_sha256` | 本次 dispatch 使用的 Admission approved `(name,sha)` 集合摘要 |
| `outcome` | `completed` / `rejected` / `failed_after_reserve` / `reserved` / `dispatched` |
| `reserved`/`dispatched`/`settled` | Reserve / Fake 发送边界 / Broker 终态是否实际发生 |
| `error_code` / `call_id` / `reservation_id` / `receipt_id` | 与 IPC 错误帧和账本关联 |

### 3.2 真实 DSH 观测（L2-REAL-DSH）

证据：`artifacts/g4f/f2/runs/{echo,tool}-20261119123213/run/dispatch-window.jsonl`。

| run | journal 记录 | outcome | purpose | origin | tools | approved | call_id / reservation |
|---|---|---|---|---|---|---|---|
| Echo | 1 | completed | `null` | uid/gid 65534, pid 0 | `skill_lookup` | ✅ | `call-e109d…` / 1 个 reservation |
| Tool | 2 | completed ×2 | `null` ×2 | uid/gid 65534, pid 0 | `skill_lookup` ×2 | ✅ | 2 个不同 call_id / 2 个不同 reservation |

- `schema_sha256 == approved_sha256 == c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704`
  （与 G3-D/G4 stage 的 `capture-tools.json` 冻结值一致）。
- 无 `rejected` 记录；无 tool-call/tool-addition/tool-removal 消息引用（真实 Tool 轮次的
  tool-call 块由 DSH 组装，但 provider 请求的 `messages` 里只出现 tool 结果；见 §3.4）。
- 每条记录的 `reserved/dispatched/settled` 均为 `true`，并带 reservation_id；
  与 DB 的 `budget_reservations`、`budget_dispatch_claims`、`g3b_attempts` 一一对应。

### 3.3 raw-UDS 矩阵（L2-RAW-UDS，真实 Candidate UID 65534）

证据：`artifacts/g4f/f2/raw-uds-20261119123213.json` + `raw-uds-20261119123213/`。

| 阶段 | 用例 | 期望 | 实际 | 账本 |
|---|---|---|---|---|
| negatives | unapproved_tool_name (`bash`) | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 同 | 0/0/0，Fake 0 |
| negatives | modified_approved_schema（嵌套加 `path`） | 同上 | 同 | 0/0/0 |
| negatives | extra_tool_alongside_approved (`fs_read`) | 同上 | 同 | 0/0/0 |
| negatives | duplicate_approved_tool（同名两份） | 同上 | 同 | 0/0/0 |
| negatives | message_tool_call_bash | 同上 | 同 | 0/0/0 |
| negatives | message_tool_addition_bash | 同上 | 同 | 0/0/0 |
| negatives | message_tool_removal_bash | 同上 | 同 | 0/0/0 |
| positive | approved_tool (`skill_lookup`) | `finish` | ack+chunk+chunk+finish | **1/1/1**，Fake 1，Receipt 1 |
| auxiliary | auxiliary_purpose_title | `BAD_TYPE` | `BAD_TYPE`（IPC parse，无 ack） | 与 positive 相同，journal 无新增 |
| auxiliary | auxiliary_purpose_title_replay | `BAD_TYPE` | 同 | 同上 |

负例阶段后快照：`reservations=0, claims=0, attempts=0, intents=0, receipts=0, journal=7`；
positive 后：`1/1/1/1, receipts=1, journal=8`；auxiliary 后：与 positive **逐字段相同**，
journal 仍为 8（title 请求未进入 Controller）。

> **口径说明**：`purpose` 是冻结 request schema 的字段，`parse_envelope` 在
> `_VALIDATORS["request"]` 中只允许 `null|"conversation"`，因此 title 请求在 IPC
> 解析层就被拒绝（比 Controller 更早）。Controller 自己的 conversation-only 复核
> 用于 in-process/未来路径，host 测试覆盖（§5）。

### 3.4 DSH 侧交叉核对

DSH session trace 的 `request/header` 是 candidate 侧实际组装请求头；
`summary.json → runs[*].dsh.request_header_tools` 与 Controller journal 的
`tools[].schema_sha256` 逐项比较：

- Echo：1 个 header（`skill_lookup`）== 1 次 dispatch；
- Tool：DSH 只在 surface 变化时写 header，因此 **1 个 header 对应 2 次 dispatch**；
  两次 dispatch 的 tool 名/digest 都与该 header 相同 → `dsh_request_header_tools_match_dispatch=true`。
- 该比较证明：**同一 adapter 调用的两侧（candidate trace 与 trusted journal）看到的
  tool 面一致**，而不是只看日志某一侧。

---

## 4. per-dispatch 校验：既有覆盖与本轮最小增量

### 4.1 既有机制（复用，不新增白名单项）

`TrustedController._prepare_checked`（`bridge/controller.py`）在 `_broker_reserve`
与 `claim_dispatch_for_request` **之前**：

1. `validate_request_payload`（协议严格 schema）；
2. route/model 固定（`ROUTE`/`MODEL`）；
3. `maxTokens` 与 Admission output bound；
4. messages 中 `image/file/attachment/store` 块拒绝；
5. `tools[]` 每项的 `name` + `canonical_json(tool)` SHA-256 必须命中
   `Admission.tool_schemas`，否则 `ADMISSION_TOOL_SCHEMA_MISMATCH`；
6. 保守 input bound；
7. `claim_dispatch_for_request(..., approved_tool_schemas=...)` 再次校验 prepared tools。

### 4.2 本轮补齐的缺口（同一处、同一错误码族、Reserve/Claim 之前）

| 缺口 | 处理 | 稳定码 | 证据 |
|---|---|---|---|
| 同一请求内 **重复 tool 名**（两份同名定义可能让“实际 tool”歧义） | 第二个同名项直接拒绝 | `ADMISSION_TOOL_SCHEMA_MISMATCH` | host + raw UDS |
| **messages 内 tool 引用**（`tool-call.name`、`tool-addition/removal.toolName`）可指向未批准工具，原校验完全忽略 conversation history | 非 str/空 → `REQUEST_INVALID`；str 但不在 approved 集合 → schema mismatch | `REQUEST_INVALID` / `ADMISSION_TOOL_SCHEMA_MISMATCH` | host + raw UDS（3 类块） |
| **Controller 侧 purpose 复核**（协议层已拒绝非 conversation，但 Controller 自身未声明该规则） | `ALLOWED_PURPOSES={None,"conversation"}`，其它 → BAD_TYPE（仍先于 Reserve） | `BAD_TYPE` | host（title/judge/compaction/missing） |
| **未知/外来 origin**（legacy 0600/root 或未来路径可能没有 peer 校验） | `BridgeServer` 把 `SO_PEERCRED` 传给 `Controller.observe_peer`；当部署声明了 `expected_peer_uid` 时（G4-C 配置为 65534）缺 origin 或 uid != Admission launcher uid → 拒绝；记录始终写入 journal | `ADMISSION_LAUNCHER_MISMATCH` | host + raw UDS（foreign uid 0） |
| Admission 文件内 **重复 tool 名 / 非 hex digest** | `load_admission` 拒绝整份文档（避免 dict 覆盖歧义） | `ADMISSION_INVALID` | host |
| tool 面**不可观测** | 每次 dispatch 写 journal（§3） | — | L2 |

### 4.3 明确的边界（不夸大）

- `require_origin` 只在配置声明 `expected_peer_uid` 时启用（G4-C 容器即如此）；
  legacy 0600/root 部署保持原行为，只记录 origin 作为证据。这样避免把 G3-B/G3-C
  既有 in-process/root 测试路径误杀（回归中已验证）。
- 校验仍以 **Admission approved 集合**为准；没有新增/扩大任何 tool 或路由白名单，
  没有修改 `ERROR_CODES`、G3-C/G4-C 协议帧或账本状态机。
- journal 写失败（磁盘/权限）只计数，不改变 dispatch 决定；证据缺失由 L2 证据脚本
  的“journal 必须存在”判定暴露，而不是静默成功。

---

## 5. 辅助模型请求矩阵

### 5.1 方法与证据源

1. **merged entry list**（`artifacts/g4/runtime/merged-config.yml`，sha `0d525f44…`，
   39 entries）：**只是合并后的 Cordis 条目列表，不是 registry，也不是运行期
   tool 导出**；
2. 冻结插件源码（`@deepseek-ai/dsh-session-title` 等）的调用条件；
3. 真实 run 的 DSH trace（`session/title` 事件、assistant messages、usage）；
4. Controller journal（每次实际 dispatch 的 purpose/origin）；
5. 真实 built adapter 的 purpose probe（`G3B_BRIDGE_PURPOSE` / `G3B_BRIDGE_CONNECT_FAILED`）。

### 5.2 矩阵（冻结配置 + 真实运行）

| 路径 | 配置/条目 | 是否可能产生 provider 请求 | 本轮观测 | 结论 |
|---|---|---|---|---|
| `session-title` | 1 个 `session-title` service 条目；**0 个 `session-title-*` provider 条目** | 仅在 `register(provider)` 后：源码 `runProvider()` 才调用 `provider.generate()`；无注册时只走确定性 fallback | 2 个真实 run 各 1 个 `session/title`，`source.kind=fallback`；无额外 assistant/usage；无 `G3B_BRIDGE_PURPOSE` stderr | **不产生 provider 请求**（本配置）；fallback-only |
| `compaction-basic` | 条目存在，merged config `disabled: true`（G4-B §4.2） | 是（若启用） | 2 个 run 的 DSH trace 无 compaction 请求；dispatch 数与 assistant 数一致 | 未产生；残余见 §10 |
| `judge` | merged entry list 无 judge 条目 | 是（若注册） | 无 | 未注册/未观测 |
| `llm-retry` | 条目存在；adapter `providerRetryPolicy.maxRetries=0`、Admission `max_attempts=1` | 每次重试都必须是新 dispatch（Reserve/Claim） | 3 次 dispatch = 3 次 assistant = 3 个 Receipt；无重发/额外 attempt | 无未记账重试 |
| `subagent` | merged entry list 无 subagent 条目 | 是（若注册） | 无 | 未注册/未观测 |
| `mcp-resources` | 条目存在；未见 server 配置 | 本身不是 LLM 调用；资源访问无网络 | 无外部资源/网络证据 | 非 provider 请求路径 |
| adapter 兜底（**唯一 provider**） | `/project/runtime/bridge/lib/index.js` | 任何 purpose != null/conversation 在 `buildRequestPayload` 抛 `G3B_BRIDGE_PURPOSE`，**在 `createConnection` 之前** | 真实 built adapter probe：title → `G3B_BRIDGE_PURPOSE`；conversation → `G3B_BRIDGE_CONNECT_FAILED`（仅在 guard 之后才尝试 socket） | 辅助 purpose 无法到达 UDS/Reserve/Claim |

### 5.3 B07 判定（不再留“未证明”）

```text
session-title @ frozen config = FALLBACK_ONLY, NO PROVIDER REQUEST OBSERVED
```

依据链（独立、可复跑）：

1. merged entry list 中只有 `session-title` service，没有
   `dsh-session-title-llm` / `-first-prompt-llm` / `-all-prompts-llm` provider 条目；
2. 冻结插件源码：无 `register()` 时 `refresh()/onUserMessage` 只调用
   `ensureFallback()`，`runProvider()`/`provider.generate()` 不会被调用；
3. 真实 trace：`session/title` 事件 `source.kind=fallback`（title 为截断文本，
   非模型生成），无额外 `assistant/message`/usage；
4. 真实账本：3 次 dispatch = 3 条 assistant = 3 个 Receipt = Fake 3，无第 4 次；
5. adapter probe：即使未来某 provider 以 `purpose="title"` 调用，也会在 UDS 之前被
   `G3B_BRIDGE_PURPOSE` 拒绝；若以 conversation 调用，则成为一个正常 dispatch
   （Reserve/Claim/Fake 全额记账），不存在“绕过 Controller 的辅助调用”。

**仍不能证明**（明确 UNVERIFIED）：任意未来配置/动态注册/`!!js` 求值后新增的
provider 条目永不发起辅助调用；merged entry list 不是权威 registry，无法枚举运行期
动态注册的工具或 provider。该残余与 B03/E5-P04 一起保留（§10）。

---

## 6. 真实双 Principal 账本

证据：`artifacts/g4f/f2/runs/{echo,tool}-20261119123213/db/snapshot.json`、
`receipt/`、`checks/checks.json`、`traces/dsh-result.json`。

| 项 | Echo | Tool 两轮 |
|---|---|---|
| launcher exit | 0 | 0 |
| launcher checks | 18/18 PASS | 20/20 PASS |
| Reservations | **1** | **2**（2 个不同 id） |
| Claims | **1**（COMPLETED） | **2**（COMPLETED） |
| Attempts | **1**（SETTLED） | **2**（SETTLED） |
| Send intents | 1 | 2 |
| Receipts | **1** | **2** |
| Fake counter | **1** | **2** |
| DSH assistant messages / usage | 1；usage == receipt usage | 2；逐 message == receipt usage |
| provider requests（dispatch） | 1 | 2 |
| 额外 provider 请求 | **0** | **0** |
| call_id / reservation_id 唯一性 | — | 2 套互不相同，链路一致 |
| origin | uid/gid 65534，pid 0 | 同 |

两轮 Tool 的 `tool_calls=1`、`tool_results=1`、第二个 assistant message 为最终回复；
`request/header` 只有 1 条（DSH 在 surface 不变时复用），与 2 次 dispatch 的 tool 面一致。

---

## 7. 测试与负例（`tests/integration/g4_f2/`）

| 文件 | 内容 | 结果 |
|---|---|---|
| `test_f2_dispatch_window.py` | 批准/未批准/嵌套 schema/额外/重复/non-str tool；message tool-call/addition/removal；purpose title/judge/compaction/missing；origin 匹配/不匹配/eviction；重放；auxiliary 重放；journal 写失败不改变决定；Admission 重复名/非 hex | 24 passed |
| `test_f2_raw_uds.py` | 真实 `BridgeServer` + AF_UNIX raw frames：tool 面矩阵、foreign origin、malformed tool-ref、socket ready | 5 passed |
| `test_f2_adapter_purpose.py` | 真实 built adapter：title vs conversation purpose 的先后顺序 | 1 passed（有 stage 时） |
| 合计 | | **30 passed** |

所有负例同时断言：稳定错误码、`reserved/claimed/attempts/fake=0`、journal
`outcome=rejected` 且 `reserved=false`；没有新增任何 Approved tool。

---

## 8. 回归与静态检查

命令（`-B`、`PYTHONDONTWRITEBYTECODE=1`，用 deps 内 pinned pytest）：

```text
PYTHONPATH=src:artifacts/foundation/deps /root/.local/bin/python3.11 -B -m pytest \
  tests/integration/<dir> -q -p no:cacheprovider --tb=line
```

| 套件 | 结果 |
|---|---|
| `g4_a` | **223 passed** |
| `g4_b` | **38 passed**（干净重跑；见下行说明） |
| `g4_c` | **78 passed** |
| `g4_d` | **25 passed / 1 failed**（D15 host-only：`/root/.local/bin/python3.11` 在 0700 home 下，降权子进程不可穿越；用 `/opt/miniconda3/envs/quant/bin/python` 重跑 **1 passed**） |
| `g4_f3` | **23 passed** |
| `g4_f2` | **30 passed** |
| `g3c` | **110 passed** |
| `g3d` | **143 passed / 1 failed**（`test_runner_does_not_modify_product_src`：frozen-src `git diff 4bd4803 -- src` 非空，G4 授权改码导致，历史报告已登记，**预期失败**） |
| `g3_bridge` | **31 passed** |
| `gates` | **14 passed** |
| **合计** | **715 passed / 2 failed / 717**（2 个失败分别为 host-env D15 与 frozen-src 预期；均可解释） |

**并发环境说明（如实记录）**：首次 `g4_b` 出现 1 个失败
`test_real_anchor_is_the_frozen_baseline`（rootfs `f791b34… ≠ 25491e45…`）。
当时另一并行 session 的 G4-C launcher 正在启动容器，rootfs 在短暂窗口被其
preflight 的 cleanup 触碰；容器退出后 rootfs 恢复 canonical，**干净重跑 38/38 PASS**。
这不是本包代码导致的漂移；证据 `artifacts/g4f/f2/` 的最终 run 快照为 canonical。

- **ruff 0.17.5（pinned，uv cache）**：
  `ruff check src/autoteacher_m0/bridge/{controller,dispatch_audit,admission,ipc_server}.py tests/integration/g4_f2 scripts/g4/{launch_c,probe_runtime,stage/trusted_entry_g4c}.py`
  → **All checks passed!**
- 全量 host 1285 项未重跑（F2 范围外的 4 个 host-only/frozen-src 失败已在 G4 独立
  复核报告中登记）；本包按 F3 的回归集合 + g4_f2 复跑并如实计数。

---

## 9. Registry 结论（必须与 B03/E5-P04 保持一致）

- **DSH 0.2.2-rc.2 没有权威 merged tool registry / merged tool JSON Schema 导出**；
  `--dump-config` 是 Cordis 条目列表，`--dump-config-schema` 是条目 schema，均不是
  tool registry；`!!js` 在加载期求值，条目列表不能证明运行期注册集合。
- 本轮**没有**声称“registry == 只有 skill_lookup”。本轮证明的是：
  1. 每次实际到达 Controller 的请求，其 `tools[]`/message tool 引用都按
     **Admission approved 集合**校验；
  2. 任何未批准/改 schema/额外/重复/未知 origin 的请求在 **Reserve/Claim 之前**被拒，
     账本 0、Fake 0；
  3. Echo/Tool 两次真实 run 的 candidate `request/header` 与 Controller journal 的
     tool 名/digest 一致。
- 因此 **B03 = `UNVERIFIED`（registry 不可导出）+ 兜底成立**；
  **E5-P04 维持 `UNVERIFIED`**，不因本轮证据升级。

---

## 10. 残余与 UNVERIFIED

| ID | 残余 | 处置/边界 |
|---|---|---|
| **F2-R1** | 任意未来 DSH 配置/动态注册可能新增 provider/tool 条目 | 单 adapter + purpose guard + Controller per-dispatch 校验仍生效；但“永不出现辅助请求”不能证明。B07 对**冻结配置**已证明，不外推 |
| **F2-R2** | merged entry list 不是 registry；`!!js` 求值后的插件图不可观测 | 与 B03/E5-P04 同；不声称权威导出 |
| **F2-R3** | title 请求在 IPC `parse_envelope` 层被拒，未写 dispatch journal | 这是协议 schema 的更强前置拒绝；journal 只记录进入 Controller 的 dispatch。证据用 raw-UDS 响应 + 账本零增量 + journal 无增量三方面记录 |
| **F2-R4** | origin 身份只取 uid；容器 PID namespace 中 `pid=0` | 与 G3-D/G4 既有 D1-A 语义一致（PID 仅证据）；`require_origin` 仅在声明 `expected_peer_uid` 时启用 |
| **F2-R5** | journal 写失败不 fail-closed（仅计数） | 安全判定独立于 journal；L2 证据脚本要求 journal 存在，否则 `ok=false`。未把观测写成新的发送前置条件，避免磁盘故障改变账本语义 |
| **F2-R6** | 未重跑 G4-C 的 crash/replay/quota/watchdog 全矩阵 | 本包只跑 Echo/Tool/raw-UDS 与 host 负例；既有 G4-C 证据未改。回归套件覆盖相关控制器路径 |
| **F2-R7** | g4_b 首次失败为并行 session rootfs 临时非 canonical | 干净重跑 38/38；最终 run 的 rootfs/deps canonical 已记录 |

**明确 UNVERIFIED**：B03 merged registry；E5-P04；任意未来配置的 session-title；
DSH resume L2（F4 范围，本包未改）；Node adapter 9/9（本包只跑 built adapter 的
purpose probe，不等同完整 adapter 测试套件）。

---

## 11. 证据索引

均位于 gitignored `artifacts/g4f/f2/`（见 `RUN_INDEX.md`）：

| 路径 | 内容 |
|---|---|
| `summary.json` | 最终裁决（`ok=true`）、HEAD/stage、账本、dispatch、DSH trace、raw 矩阵、adapter、auxiliary |
| `summary-20261119123213.json` | 同一内容的时间戳快照 |
| `runs/echo-20261119123213/` | Echo：journal、DB snapshot、receipt、DSH trace、checks、trusted/candidate logs、peercred |
| `runs/tool-20261119123213/` | Tool 两轮：同上 |
| `runs/*.runner.json` | 每次 launcher 的 argv/UTC/exit/stdout/stderr |
| `raw-uds-20261119123213/` | hold Candidate + trusted：每阶段 DB 快照、journal、commands、cleanup |
| `raw-uds-20261119123213.json` | 7 negatives + 1 positive + 2 auxiliary 的逐例 code/ledger |
| `tool-window.json` | 实际 tool 面蒸馏（Admission approved set、每次 dispatch 的 tool/digest/origin/purpose、DSH header、raw 矩阵） |
| `RUN_INDEX.md` | 四次证据尝试、失败原因与最终权威 run |

**证据中的关键 SHA**：

```text
stage manifest          3914bb4795e63934f92982a6081d6932ea50bcfad90bd7bad36eb3852f70d9c1
stage tree              29967d3287add6227be49c902aab2c81015d45b334cbf2c74215840b21dcffa1
rootfs                  25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0
deps                    e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98
adapter built JS        2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba
approved skill_lookup  c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704
merged entry list      0d525f44ef3ada744a306cd471c6a7370a7e7a673b7dfd912978b0836a5ae6cf (39 entries)
```

---

## 12. 提交与 STOP

- 提交（父/链）：
  - `40af7b1`（feat；parent `b963ad4`）
  - `64d32cb`（fix；parent `40af7b1`）
  - `339312b`（fix；parent `64d32cb`）
  - docs 提交：本文件（parent `339312b` 或其后并行 docs 提交；不 amend / 不 push）
- 只 add 本包路径；未 stage 他人文件；未改 LiveGate/`run_live.sh`/`dsh_adapter.py`/
  DSH 核心/G3-C/D 协议或账本语义/历史证据。
- 终态：`podman ps -a` 空；rootfs/deps canonical；0 真实 Key / 0 模型 / 0 外网 /
  0 Live；LiveGate `BLOCKED`。

```text
G4-F2 = PASS_FOR_NO_KEY_OBSERVABILITY_SCOPE
B03   = UNVERIFIED (no authoritative merged registry) + per-dispatch guard
B07   = NO_EXTRA_PROVIDER_REQUEST_OBSERVED @ frozen config (fallback-only)
E5-P04= UNVERIFIED (unchanged)
G4-H = NOT_AUTHORIZED; G5 = BLOCKED; G6 = NOT_RUN; M0 = DECISION_PENDING
```

**STOP.**
