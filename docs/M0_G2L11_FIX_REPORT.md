# M0 G2-L1.1 Fix Report — Provider 异常归因、Canonical ID、Prepared 严格化、Journal/Diag 最小修复

- 任务：`task-83`；日期：2026-11-16 UTC；实现者：verify2（与 G0/docs owner 分离）
- 基线：`76f1c52d156d0c5e9e3834afc8d2ea35555e7626`（G2-L1.1 Playbook + G0 baseline docs）
- 实现 commit：`bf1e84dab9c74f1bec919633672dc29abfa7a77b`（父 `76f1c52`，6 files，仅代码/测试/script）
- 范围：**仅 G2-L1.1 T1–T6**；不进入 G3/G4/G5/G6；不 commit G3 内容；0 真实 Key/模型/外部 HTTP；未读 `/root/.config/autoteacher`。
- 安全边界：固定无 Key/禁网 OCI（image `62d3569e…`，uid 65534，read-only，cap-drop ALL，network none）；宿主未跑 pytest。
- 免责：本地 claim ≠ 远端/provider exactly-once；FakeProvider 是 synthetic；真实 wire/usage/invoice 未验证。

## 1. 基线/身份

| 项 | 值 |
|---|---|
| Playbook | `docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md` |
| G0 baseline | `docs/M0_G0_CURRENT_BASELINE.md`（T1–T5 OPEN，行号已核） |
| Base | `76f1c52` |
| Implementation | `bf1e84d`（父 `76f1c52`） |
| Docs | 本报告所属 docs commit（见 git log） |
| Stage | `git archive bf1e84d`，198 files，normalized sha256 `ab95ffb46e070f3c166f9b1a22a9a18af6bc56aa3fe83f1397ba83abcbd201c1` |

## 2. RED → GREEN

- RED（精确基线 `76f1c52` + 当前已提交测试）：**8 failed / 16 passed**，exit 1；日志 `artifacts/g2l11/logs/red2.stdout.log`（旧 `red.stdout.log` 10/14 已 superseded，见 `M0_G2L11_ERRATA.md`）。行为 RED：T1 provider after-entry、T2 Unicode call-id、T4 journal、T5 descriptors；API-shape RED 另记。
- GREEN（实现 commit `bf1e84d` git-archive stage）：L11 定向 **24 passed**；全量 **625 passed, 1 skipped**；verify script **PASS**；Ruff repo-wide **All checks passed!**；日志 `artifacts/g2l11/logs/{green2,impl-full,impl-script,impl-ruff}.stdout.log`。

## 3. T1 — Provider after-entry 异常归因（P1）

修复：
- `TrustedEgressTransport.dispatch` 在进入 provider callable **之前** `boundary.mark_dispatch_attempt_started()`，`provider_calls` 按函数进入次数递增，`attempt_started`/`provider_invoked` 明确输出；`classification` 区分 `PRE_DISPATCH_DENIED` / `ATTEMPT_STARTED` / `RESPONSE_COMPLETED` / `RESPONSE_PARTIAL` / `RESPONSE_UNKNOWN`。
- provider 抛异常/无效返回 → `state=BILLABLE_UNKNOWN` + worst-case held，返回 `dispatched=True`（可能已发送），不是 `NOT_DISPATCHED`；禁自动重试。
- `KeyboardInterrupt`/`SystemExit`：先归因 `ATTEMPT_STARTED` 后原样 re-raise，保留清理/中断语义。
- provider 原始异常文本不进入输出（只输出安全枚举/类型）；HTTP Attempt 标记 `UNVERIFIED`，不把 provider_calls 当 HTTP 数。
- 测试：`L11-ATT-01..06` 全 PASS（provider entry 1 次后 RuntimeError/invalid result → BILLABLE_UNKNOWN；fake/no permission 0 calls；二次 permission 0 calls；KeyboardInterrupt 保留）。

## 4. T2 — 统一 call_id canonicalization（P1）

修复：
- 单一实现 `accounting/call_identity.py` 导出 `canonical_json`（UTF-8、sort_keys、紧凑 separators、ensure_ascii=False、严格类型、拒 NaN/Inf、非字符串 mapping key）；`CallIdentity.call_id` 与 `derive_call_id` 使用它；`security/egress.py` 直接 import，不再本地实现。
- 中文/非 ASCII run_id 的 Accounting/Egress 输出一致；跨进程计算相同；单字段变化产生不同 ID；旧 ASCII/fixture ID 不静默改写。
- 测试：`L11-ID-01..06` 全 PASS。

## 5. T3 — Prepared schema/严格字段（P1）

修复：
- `prepared_schema_error()` 强制 `schema_version == "m0.prepared.v1"`；严格校验 scope/run/step/attempt/provider/route/model/host/port/method/path/stream/max_output_tokens/system/messages/tools/response_format/retry_policy/flags/call_id/digest；bool 不作为 int；拒 NaN/Inf/非 JSON/嵌套非法；digest 在 claimer 前重算，nested mutation 通过重序列化/旧 digest 不一致拒绝；`approved_tool_schemas` 必须显式传入，空集合不放行非空 tools。
- 所有拒绝在 claimer 调用前，provider=0。
- 测试：`L11-PREP-01..05` 全 PASS。

## 6. T4 — Broker journal 容量/completion（P2 最小）

修复：
- `handle()` 对 settle/fail 在 journaling 前预检：未知 reservation → `UNKNOWN_RESERVATION`；非 PENDING → `ALREADY_SETTLED`；route 缺失 → `ROUTE_BLOCKED`；usage 校验失败 → `INVALID_USAGE`；均不写新 journal 行。
- 同 message id 的已存在响应仍走 `journal_once` 保持幂等；合法 PENDING 的 settle/fail 不受 reserve 配额限制；snapshot 仍可读。
- 测试：`L11-JRN-01..04` 全 PASS（6 个 unique unknown completion 后 journal 行数 0；合法 settle/fail；同 id 幂等；已结算新 id 不增长）。

## 7. T5 — Descriptor 计数与归因（P2）

修复：
- `LogicalStreamEgress` 分离 `policy_checks` / `policy_allowed` / `policy_denied` / `claims_granted` / `dispatch_attempted` / `provider_invocations` / legacy `attempts`；`evaluate_descriptor` 只增加 policy 计数，不消耗发送配额；配额以 `claims_granted` 为可信上界。
- `attempts_detail` 记录 policy/claim/attempt_started/provider_invoked/provider_dispatched；snapshot 新增字段并标注 `attempts` 兼容语义（successful claims）。
- 测试：`L11-DIAG-01..03` 全 PASS（5 次诊断不阻止后续 claim；claim/dispatch 计数；多 reservation detail）。

## 8. T6 — 兼容/源码级回归

- Python 全量 `tests/`：**625 passed, 1 skipped**；Ruff repo-wide clean；verify_egress_policy PASS。
- BIND-01/BIND-06、INT-05/06/17、claim_bound、无 bound claimer `CLAIM_BINDING_UNSUPPORTED`、旧 v1 snapshot/reserve/settle/fail 均在测试集中 PASS。
- `gates.py`/`dsh_adapter.py`/`run_live.sh` 相对基线字节未改，LiveGate/Adapter/run_live 保持 BLOCKED；未解锁。
- **DSH Plugin/SDK B 层**：已 `git ls-files` 发现 `plugins/offline-fixture`（build only）、`plugins/runtime-budget-guard`（`node --test tests/*.test.mjs`）、`plugins/skill-lookup`（`node --test test/*.test.mjs`）；固定 OCI 镜像无 `node`（实测 `/usr/bin/node` 不存在），**本轮无法在既定 OCI 内执行** → 标记 **BLOCKED/UNVERIFIED，不伪造 PASS**。宿主 Node 存在但按“项目代码只在固定 OCI 执行”约束未使用。

## 9. 残余 / G3_DEPENDENCY

1. 真实 provider wire/usage/invoice/exactly-once 未验证（G3）。
2. ATTEMPT_STARTED 仅内存诊断；跨进程 crash 持久化未实现（G3 硬门槛）。
3. 旧 v1 客户端省略 bound 字段的本地 claim 残余仍存在；旧 unbound claim 仅历史兼容，不得进入生产 Bridge。
4. DSH Plugin/SDK B 层在本 OCI 无 node，UNVERIFIED；需维护者提供受审 Node 运行环境后再跑。
5. TrustedEgressProvenance 仍是同进程 capability（V-G1-3）。
6. T4 修复为进程内 broker journal 上界；不构成远端费用/账单证明。

## 10. STOP

G2-L1.1 实现与 RED/GREEN 已完成；**G3 未启动**；提交仅实现/测试与随后 docs；等待 Lead 审阅 Review Packet 后决定是否派独立 Reviewer。不得据此签发 Live/GO。

> 证据勘误：RED 日志已按精确基线重跑，见 `docs/M0_G2L11_ERRATA.md`（旧 red 日志作历史保留）。

> 语义澄清：`dispatch_count` 是 provider callable 进入/attempt 开始次数（含 after-entry 抛异常），非 confirmed HTTP/completed 次数；`provider_calls` 为函数进入次数；after-entry 异常的 `dispatched=True` 表示“可能已发送”，状态 BILLABLE_UNKNOWN。

> G2-L1.2 R-06 修正：RED2 为 8 failed / 16 passed；旧 10/14 已 superseded。详见 `docs/M0_G2L12_HARDENING_REPORT.md`。
