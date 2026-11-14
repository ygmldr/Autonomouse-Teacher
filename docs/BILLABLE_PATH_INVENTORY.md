# Billable Path Inventory（PR4a，mock/local，无 Key）

- 任务 `task-39`；基线 HEAD `9b77a37`（PR1 `fdcfdc9`、PR3 已冻结）；本任务不 commit
- 结论：**egress 原型/失败矩阵/计费路径清单完成；真实 provider wire/内部 retry/cache/Files 未观测（锁定 OCI 拒绝 socket）；Live 与硬预算仍 BLOCKED，未知≠0**
- 证据：`artifacts/m0-egress-validation/`（mock transport 报告、pytest、socket 拒绝证据、manifest/evidence hash）

> LIMITATION 优先声明：锁定 rootfs/image OCI 内 `socket()` 直接 `PermissionError`（已记录），因此不能启动本地 HTTP/连接 mock endpoint；本 PR 的“mock/local egress”是**进程内 transport 观察器**（脚本化 attempt 描述），不是真实 provider 传输观测。不得把本文件当真实账单/硬上限证明。

## 1. 一个 logical stream 内可能出现的计费路径

| # | 路径 | 触发条件 | 是否可能计费 | guard/broker 覆盖 | 本 PR 观测/证据 | 缺口 |
|---|---|---|---|---|---|---|
| B1 | 主对话 provider attempt | 正常 `llm/stream` | 是 | guard 在 `next()` 前预存（logical stream 级） | mock transport `ok_usage` = 1 attempt, SETTLED | 真实 wire/HTTP 未观测；provider 内 retry 未知 |
| B2 | provider 内部自动重试 | SDK/adapter retry 策略 | 是（可能多次） | guard PR1 已拒绝 `maxProviderRetries>0`；关闭自动重试 | `must_not_retry` 断言：mock `retry_attempted=False`；guard 配置固定 0 | 真实 adapters 是否完全遵守未验证（F3 残留） |
| B3 | 工具轮次（第二个 attempt） | 模型发出 tool-call 后回灌 | 是 | 每次 logical stream dispatch 独立 reservation（PR1/phase5 证据 s2） | transport observer 可生成 attempt_ordinal=2；call ID 变化且稳定 | 未在真实 fixture tool 轮中联测 egress 计数器（PR2 已测 fixture 工具） |
| B4 | cache hit / cached tokens | provider implicit cache | 不额外请求（计费单价可能不同） | 不适用（无额外 dispatch） | mock `ok_usage` usage 字段仅作形状；cacheRead 未以真实 response 验证 | 真实 cached tokens 字段与计费未知（F9） |
| B5 | Files/attachments | 向 provider 上传文件/stale-ID 二次 POST | 是（可能额外请求） | guard 仅在 logical stream 上拒绝/限制；provider Files 内部请求未覆盖（F3） | 原型显式 deny `FILES_NOT_PERMITTED`/`IMAGES_NOT_PERMITTED` | 真实 Files 行为、二次 POST、计费未知；egress 只有描述符级 deny |
| B6 | compaction 专用调用 | 会话压缩触发 purpose=compaction | 是 | guard 对 compaction purpose 独立预存（phase5 证据） | `purposes` 固定 conversation（PR2 target）；本 PR 未触发真实 compaction | 真实 compaction/Judge 生命周期、次数与 usage 未知 |
| B7 | Judge/session-title 等辅助请求 | 标题/评审等内部调用 | 是 | 不在主 logical stream 的 guard 覆盖内 | 计入“未知路径”，按 worst-case；不假设为 0 | 调用次数/触发条件未知；需 PR4b/PR5 观测 |
| B8 | 重连/stream resume 二次 POST | 客户端/网络中断重试 | 是（可能重复计费） | guard 不控制 provider 传输层 | `timeout/hang/disconnect/unknown_transport` → BILLABLE_UNKNOWN + worst-case held | 真实断连与服务端是否已计费未知 |
| B9 | 超时/无 usage/部分 usage | provider 异常/未知 | 未知，按最坏保留 | broker settle 侧存在；本 PR 只做 egress 计数/状态 | mock `ok_no_usage`/`ok_partial_usage`/`timeout`/`hang` → BILLABLE_UNKNOWN，`worst_case_held_usd>0` | 真实 settlement 联动在 PR4b |
| B10 | 未批准 route/超参数/无预留 | 任何出站 attempt | 不应发生（egress deny） | 本 PR 原型 deny；PR1 guard 预存先于 dispatch | 10 类 deny 用例全部在 dispatch 前拒绝 | 真实 OS 层强制由 PR4b 外部代理完成 |

## 2. 外部边界原型（egress 侧，不含 accounting）

`src/autoteacher_m0/security/egress.py`：
- allowlist：host `opencode.ai`、port 443、method POST、path 前缀 `/inference/go/`；approved route/model 仅 `opencode-go/deepseek-v4.1-flash`；`max_tokens` ≤1024；禁止 files/images/store；`max_attempts`≤4。
- 拒绝原因：NO_RESERVATION、ROUTE_MODEL_NOT_APPROVED、HOST_PORT_NOT_ALLOWED、METHOD_NOT_ALLOWED、PATH_NOT_ALLOWED、MAX_TOKENS_*、FILES/IMAGES/STORE_NOT_PERMITTED、ATTEMPT_LIMIT_EXCEEDED——全部在 dispatch 前。
- 计数：每 logical stream 记录 attempts/denied/known_cost/worst_case_held；`snapshot()` 可审计。
- 稳定 ID：`eg-<sha256(logical_stream,reservation,attempt,route,model,host,port,path)[:24]>`；同一 attempt 稳定、不同 attempt 不同。reservation id 仅作为 PR4b accounting 关联接口占位（本任务不写 accounting/DB）。
- OpenCode Go 未来内部路由约束来自 `docs/OPENCODE_GO_ACCESS.md §4`：真实 Key 只由仓库外 launcher/proxy 持有，candidate 无 key/无网络；本原型只做描述符级 allowlist/deny，不做真实代理。

### 2.1 egress ↔ reservation ID 关联接口（本任务只实现 egress 侧）

- `logical_stream_id`：调用方（SDK/agent loop）为一次 logical stream 分配的稳定 ID；
- `reservation_id`：由 accounting/broker 侧（PR4b）生成的 opaque ID，egress 只读取、绝不写入/修改；
- `attempt_ordinal`：同一 logical stream 内第 N 次**已授权** attempt（含工具轮次/provider retry，如果发生）；
- `call_id = "eg-" + sha256(logical_stream_id|reservation_id|attempt_ordinal|route|model|host|port|path)[:24]`：
  同一 attempt 稳定、可重复计算；不同 attempt 不同；不包含密钥/usage/费用。
- 审计 join key 建议：`(logical_stream_id, reservation_id, attempt_ordinal, call_id)`；
  一个 reservation 对应多个 attempt 时，reservation_id 相同、call_id 每 attempt 唯一；
  `EgressBoundary.snapshot()` 中每条 decision 均带 `call_id`/`stream`/`reservation`/`attempt`，
  供审计阶段与 PR4b 的 provider observation / ledger reservation 交叉核对。
- 本 PR 不生成、不结算、不修改 reservation；PR4b 如改变 reservation 语义，需重新核对本接口。

示例（egress decision，不含敏感值）：

```json
{"call_id": "eg-<24 hex>", "logical_stream_id": "stream-...", "reservation_id": "res-...",
 "attempt_ordinal": 1, "route": "opencode-go", "model": "deepseek-v4.1-flash",
 "allowed": true, "denied_reasons": []}
```

## 3. 失败矩阵（mock transport，实际执行）

| 场景 | 状态 | worst-case held | 自动重试 |
|---|---|---|---|
| ok_usage | SETTLED_USAGE | 0（已知 usage） | 否 |
| ok_no_usage / ok_partial_usage | BILLABLE_UNKNOWN | >0 | 否 |
| http_401 / http_429 | NOT_BILLABLE_HTTP_ERROR | 0（未计费错误，保守仍标记不确定成本链路） | 否 |
| http_500 / http_503 | BILLABLE_UNKNOWN | >0 | 否 |
| timeout / hang / disconnect / unknown_transport | BILLABLE_UNKNOWN | >0 | 否 |

口径：未知/部分 usage、5xx、超时、断连、未知 transport 一律**不当作 0**，按 worst-case held；不自动重试（`retry_attempted=False`）；401/429 视为未计费错误但不据此放宽预算。真实账单/结算核对不在本 PR（PR4b）。

## 4. 明确 UNVERIFIED / LIMITATION（Live 保持 BLOCKED）

1. 锁定 OCI 拒绝 socket（`PermissionError` 已记录），无法建立本地 HTTP mock，也无法观测真实 DSH/SDK provider 的 HTTP attempt、内部 retry、cache 标记、Files stale-ID 二次 POST、断连计费——本 PR 所有 attempt 均为描述符/脚本化观测。
2. 未在真实 provider wire 上验证 `maxRetries=0` 的实际进程行为；guard PR1 只证明配置拒绝与 in-process scripted retry。
3. 真实 usage/账单、cache 单价、Files/compaction/Judge 触发条件与次数、provider 内部 retry 不可控性仍未证明（F3/F9 残留）。
4. 本 PR 不修改 accounting/broker，不实现 reservation 关联、DB 预留/结算、真实 egress proxy、Key Broker；这些属 PR4b/PR5。
5. 不得声称“真实硬预算/账单上限已证明”；未批准 route/超预算/无预留只在原型层拒绝，OS 层强制需 PR4b 外部代理 + 独立审计。
6. LiveGate/E1–E5/Live 仍 BLOCKED / DECISION PENDING。

## 5. 复验

- `python3 scripts/verify_egress_policy.py`（固定 OCI 内，PYTHONPATH=/project/src:/deps）→ JSON `status=PASS`，失败 exit 30。
- `pytest tests/integration/sandbox/test_egress_boundary.py`（固定 OCI 内）。
- 证据 hash：`cd artifacts/m0-egress-validation && sha256sum -c evidence.sha256`；manifest 含 argv/UTC/exit/镜像/stage hash/结果。
