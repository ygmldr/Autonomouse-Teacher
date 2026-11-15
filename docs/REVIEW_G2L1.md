# G2-L1-FIX 独立审阅与复跑 — egress claim bypass / approved request route-model binding

- 任务：`task-80` 独立 Reviewer（与实现者 `verify2` 不同身份）；日期：2026-11-15 UTC
- 对象：G2 代码基线 `32bea5bcf8d35d778a54c04cebb0ae08fb1f849c`；实现 `2786e25a9e5bd590255026d76fc362abb16d0e7b`（9 files，父 `688ed01`）；docs `19f5270141a3a8cb59049df73755a27751ee29f1`（3 files，父 `2786e25`）；审阅时 HEAD=`19f5270`，worktree clean
- 归档状态：审阅完成后维护者 docs-only 提交 `c52b173`（仅新增本文件，不改代码）；当前工作树只有本文件审阅后文字修订（4 insertions/3 deletions；归档说明/absence 措辞）。**评审对象仍是 `2786e25`/`19f5270`；`c52b173` 不改变被审代码。**
- 契约：`docs/M0_REQUEST_BINDING_CONTRACT.md`（APPROVED Option A）；报告：`docs/M0_G2L1_FIX_REPORT.md`；findings：`docs/M0_G2L1_FINDINGS.md`；任务书：v0.7 §8
- 证据根：`artifacts/reviewer-g2l1/`（reviewer 自建，未复用 owner 的运行结果作为结论）
- 边界：只做离线/无 Key 审阅；**不进入 G3/G4/Live，不签发 GO**；未修改 `src/`、`tests/`、`scripts/` 或 Git 历史；仅新增本文件与 `artifacts/reviewer-g2l1/`；宿主未运行 pytest；未读取 `/root/.config/autoteacher`
- **结论：`PASS_FOR_DECLARED_G2L1_SCOPE`**

## 1. 裁定摘要

**A 阶段声明范围内的阻断项：无。** P0 入口（descriptor-only 放行、无 Claimer fallback、伪造/重放 permission、Reservation=A/实际=B）经静态追踪、独立 RED/GREEN、真实 SQLite/stdio Broker 复跑均未复现放行；`gates.py`/`dsh_adapter.py`/`run_live.sh` 仍硬阻断。

**非阻断发现：** 1 项 Medium（真实 provider 异常时 `provider_calls`/结算归因为 0，属 G3 真实 wire/usage 前置）；若干 Low（`PreparedProviderRequest.schema_version` 固定值未强制、Review Packet 证据完整性、owner stage 归一化 tar hash 仅能由部分 chmod 的 stage 复现、OBS-1 顶层 stream 归因、INT-11 仍为 descriptor-only）。详见 §6。

**G3 前置仍阻断：** 真实 wire/digest、正式 tool 注册表、远端 exactly-once/usage/invoice、旧 v1 omission 残余、同进程 provenance capability、生产 `BoundBrokerClaimer` 接线均未验证；本次 PASS **不**构成 G3 执行批准或 Live 解锁。详见 §7。

## 2. 身份重建（全部独立重算，非照抄 manifest）

| 检查 | 独立结果 |
|---|---|
| `diff.patch` == `git diff 32bea5b 2786e25` | **byte-identical**；sha256 `3491c84bb55e6d9e4023fb3eb60a8540b21f28610061d3d0c37f0d58afb29ef0` |
| `evidence/manifest.json` 绑定 | `manifest.sha256` 校验通过：`f7deb567…`；manifest 内 base/impl/docs/parents 与 git 一致 |
| `evidence/hashes.sha256` | **38/38 OK**；含 packet 内 sources/tests/docs/logs/commands/matrix/manifest（不含自引用文件） |
| packet 源文件 == git blob | 15/15 OK：`sources/*`（egress/broker/ledger/__init__/call_identity/contracts/observation/verify_script）与 `tests/*`、`docs/*` 全部等于 `2786e25:<path>` 或 `19f5270:<path>` 的 blob（见 `identity/blob-check.txt`） |
| 实现/文档 commit 文件集 | impl **9 files**（`scripts/verify_egress_policy.py`、egress/__init__/broker/ledger、4 个测试）；docs **3 files**（findings/contract/fix report）；与声明一致 |
| 禁改文件 | `security/gates.py`、`runtime/dsh_adapter.py`、`scripts/run_live.sh` 在 base/impl/HEAD/worktree 四处 blob 完全相同：`edf7f45f…` / `86ae5d6e…` / `dd0814e1…`；`32bea5b..2786e25` 无这些路径 |
| 历史/血缘 | `32bea5b` 是 `2786e25` 祖先；impl/doc parent 正确；HEAD=`19f5270`；worktree clean；`git fsck` 无异常；无重写迹象 |
| stage 内容 | 新 stage 192 files；逐 blob 对比 `git ls-tree -r 2786e25`：**192/192 相同，0 mismatch**；tree `ef246ebc6e6990996d1cbacc9a3216459a0e38cf` |
| deps | 归一化 tar sha256 `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`，与 manifest 一致 |
| 镜像 | `localhost/autoteacher-local-oci@sha256:62d3569e…`；image id `56db1e2ad5ab…`；`--pull=never`；审阅结束时容器数 0 |
| owner stage hash | manifest 的 `e7861641…` 能由 `artifacts/g2l1/stage` 复现；但该目录仅 4 个文件为 0444、其余 0664；**新 `git archive` 抽取为 `47a71779…`，再 `chmod -R a-w` 为 `a146e5c7…`**。这是元数据差异，内容 192 blobs 已独立验证（见 §6 F-4） |

身份证据：`artifacts/reviewer-g2l1/identity/identity-report.txt`（脚本 `verify_identity.sh`，0 failures）、`blob-check.txt`、`packet-audit.txt`、`static-trace.txt`、`stage-identity.txt`。

## 3. 静态追踪（从 Provider Dispatch 入口逆向找 Claim）

命令（完整输出见 `identity/static-trace.txt`）：

```text
rg -n 'authorize\(|require\(|claim_dispatch\(|claim_dispatch_for_request\(|MockEgressTransport|TrustedEgressTransport|claim_bound|consume_permission' src tests scripts
```

| 入口/符号 | 独立结论 |
|---|---|
| `EgressBoundary.authorize()` / `require()`（`egress.py:396-411`） | 只返回 `PolicyEvaluation`；不创建 `DispatchPermission`；`require()` 仅 descriptor deny 时抛 `EgressViolation`；**不是发送许可**。`src/` 无 egress authorize/require 的生产调用点，仅 `scripts/verify_egress_policy.py` 与测试作诊断 |
| `claim_dispatch()`（`egress.py:471-478`） | 唯一 legacy claim 路径；`claimer is None` → `BROKER_CLAIMER_UNAVAILABLE`，`allowed=False`，无 permission；claimer 抛异常/坏回复/`claimed=False` 均 fail-closed（`egress.py:432-456`） |
| `claim_dispatch_for_request()`（`egress.py:486-545`） | 在调用 claimer **之前**重算 prepared digest/call_id，并逐项比较 route/model/host/port/method/path/stream/max_tokens/flags/call_id/digest；再检查 `expected_reservation_route_model` 与 tools；失败直接 `_prepared_denied`，**claimer 调用数=0**；通过后才调用 `claim_bound` |
| `TrustedEgressTransport.dispatch()`（`egress.py:638-702`） | 唯一 provider 调用包装器；先 `boundary.consume_permission(permission, request)`，无真实 permission/跨 boundary/重放/字段不匹配均 0 provider；provider 只在 consume 成功后调用 |
| `MockEgressTransport`（`egress.py:705-742`） | 继承 `TrustedEgressTransport`，必须传 permission；不再有“无 claimer → authorize”回退；`PolicyOnlyFakeTransport` 显式不发送 |
| `consume_permission()`（`egress.py:605-635`） | 私有 registry 按对象 identity + 字段匹配；成功后立即删除；伪造/`dataclasses.replace`/跨 boundary/二次消费均拒绝 |
| broker `claim`（`broker.py:169-189, 297-311`） | `expected_route_id`/`expected_model` 必须成对；成功响应 additive 返回 ledger 的 `route_id/model`；旧客户端省略仍合法 |
| ledger `claim_dispatch()`（`ledger.py:199-280`） | 同一事务内先校验 scope/reservation/allowed_routes，再比较 `(row.route_id,row.model)` 与 expected → `ROUTE_MISMATCH`；**比较在 INSERT 之前**；claim 表结构/迁移不变；返回 route/model |
| 旧 v1 残余 | `claim_dispatch()`/`require_claim()` 仍可用无 `claim_bound` 的 legacy claimer 获得可消费 permission；`claim_dispatch_for_request()` 对无 `claim_bound` 显式 `CLAIM_BINDING_UNSUPPORTED`。该残余已在 contract/report/findings 披露，属 G3 迁移项（§7） |
| `gates.py` / `dsh_adapter.py` / `run_live.sh` | 未改动；`LiveGate.inspect` 恒 `BLOCKED`，`HarnessAdapter._require_live_authorization()` 恒抛 `SECURITY_BLOCKED`，`run_live.sh` exit 3；测试 `hardblock-and-profile` 59 passed 复证 |
| 真实 Key/网络 | `src/` 无 socket/requests/httpx/urlopen 发送代码；OCI `--network none` + socket probe PermissionError；无 key env；无 host config mount |

**结论：** 正式发送路径没有 descriptor/无 Claimer fallback；permission 只能由成功 claim 登记并单次消费；调用点层面 `src/` 尚无生产 Bridge 调用新 bound API（见 §7）。

## 4. 独立复跑（新 stage + 固定无 Key OCI；宿主未跑 pytest）

- 审阅 stage：`git archive 2786e25 | tar -x` → `artifacts/reviewer-g2l1/stage`；`chmod -R a-w`；192 files。
- 镜像：`localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`；deps 挂 `/deps`；`--network none`、`--read-only`、`--user 65534:65534`、`--cap-drop ALL`、`no-new-privileges`、pids/cpu/mem 限制、`/tmp`+`/work` noexec tmpfs、`PYTHONPATH=/project/src:/deps`；完整 argv 在 `artifacts/reviewer-g2l1/argv/*.json`。
- UTC/exit/stdout/stderr：`artifacts/reviewer-g2l1/logs/exit.jsonl` 与同名 `.stdout.log`/`.stderr.log`。

| 选择集 | 独立结果 | 与 owner 对照 | 日志 |
|---|---|---|---|
| 必测定向（FIX-01/02/04/05/06/07/08、BIND-01/02/03/06/07/08、STRICT-01/02、TRACE-01、PROC-01、INT-05/06/11/17） | **38 passed, exit 0** | 逐用例均有 owner 声明 | `logs/targeted-required.stdout.log` |
| 其余 FIX/BIND/STRICT/v1（FIX-03/09、BIND-04/05、STRICT-03/03b/04/04b、v1 old/new、RED 全文件） | **39 passed, exit 0** | 覆盖补全 | `logs/targeted-extra.stdout.log` |
| focused：`test_g2l1_red.py` + `test_g2l1_fix.py` + sandbox `test_egress_boundary.py` | **98 passed, exit 0** | owner 98 | `logs/focused-all.stdout.log` |
| 既有 G2 INT：`test_g2_closure.py`（INT-01..18） | **17 passed, exit 0** | owner 回归子集 | `logs/int05-restart17.stdout.log` |
| 回归：`g2_closure` + `sandbox` + `unit/security` | **256 passed, 1 skipped, exit 0** | owner 256/1 | `logs/regression-g2-security.stdout.log` |
| 全量 `tests/` | **601 passed, 1 skipped, exit 0**（67.55s） | owner 601/1 | `logs/full-tests.stdout.log` |
| 全量 `-rs`（skip 原因） | **601 passed, 1 skipped**；SKIP `tests/integration/sandbox/test_probe_contract.py:14` “Requires external public probe input mount; no host fallback” | 环境 skip，非产品 skip | `logs/full-tests-rs.stdout.log` |
| hard-block/profile（gates/adapter/run_live static） | **59 passed, exit 0** | — | `logs/hardblock-and-profile.stdout.log` |
| `scripts/verify_egress_policy.py` | **status=PASS, exit 0** | owner PASS | `logs/verify-script.stdout.log` |
| Ruff repo-wide | **All checks passed!, exit 0** | owner clean | `logs/ruff-repo.stdout.log` |
| 独立 RED：`32bea5b` stage + 最终 `test_g2l1_red.py` | **11 failed, exit 1**（全部当前 RED 用例在旧代码失败） | 历史 A0 日志为 10 failed/2 xfailed（旧版含 2 xfail 占位，现已移除；旧版文件未入库，无法逐字节复现） | `logs/baseline-red.stdout.log` |

**必测项逐项证据：** `targeted-required.stdout.log` 含 `FIX-01/02/04/05/06/07/08`、`BIND-01/02/03/06/07/08`、`STRICT-01/02`、`TRACE-01`、`PROC-01`、`INT-05/06/11/17` 的 PASSED 行（38 passed）。

**没有使用 skip/xfail 掩盖：** 当前 GREEN 选择集无 xfail；唯一 skip 是既有 probe-contract 环境 skip（`-rs` 明示）；A0 设计占位已在实现中移除（`test_g2l1_red.py` docstring 与 commit 内容一致）。

## 5. 机制核对（真实 SQLite/stdio + 实际 provider 计数）

独立 probe：`artifacts/reviewer-g2l1/probe/mechanism_probe.py`（OCI 内运行，不导入项目 tests；`logs/mechanism-probe.stdout.log`）。它创建**真实 SQLite 文件 + 真实 `autoteacher_m0.accounting.broker` 子进程**，不是只读 owner 日志。

| 机制 | 独立实际观测 |
|---|---|
| 无 Claimer | `claim_dispatch` → `BROKER_CLAIMER_UNAVAILABLE`，permission=None |
| descriptor deny | claimer.calls=0；permission=None |
| 伪造/重放 permission | forged → provider_calls=0；真实 permission 首次 → 1；同 permission 二次 → 仍 1（单次消费） |
| **BIND-01（Reservation=A，实际=B，均 allowlist）** | prepared/actual route B，reserve route A → `CLAIM_REJECTED:ROUTE_MISMATCH`；**provider_calls=0**；broker snapshot `claims.total=0`；broker 原始 claim（expected B）返回 `ROUTE_MISMATCH`；broker 停止后直接查 SQLite：**无 CALL_A 的 claim 行** |
| **FIX-08（恰好一次）** | 真实 bound claim 成功；`TrustedEgressTransport` 派发 **provider_calls=1**；重复 claim → `ALREADY_CLAIMED`，重复 dispatch → False；provider 仍 1；broker snapshot `claims.total=1`；broker 关闭后直接 SQLite 查询，claim 行仍在且关联 reservation |
| claim 表结构 | `PRAGMA table_info(budget_dispatch_claims)` 仍是 5 列（scope_id/call_id/reservation_id/request_digest/status），无迁移 |
| 并发/崩溃/重启 | INT-05 两真实 broker 进程争一 license → 恰 1 `CLAIMED`；INT-06 SIGKILL 后重启 replay → `ALREADY_CLAIMED`、`dispatch_allowed=False`、claims=1；INT-17 同 reservation 第二 call → `RESERVATION_ALREADY_CLAIMED`；均在本轮 `targeted-required` 重跑 PASS |
| v1 兼容 | 旧调用不带 expected 字段 → `CLAIMED`（claims 总数 2）；新 egress + 无 `claim_bound` claimer → `CLAIM_BINDING_UNSUPPORTED`，claimer_calls=0、provider=0 |
| 环境 absence | 容器内 uid=65534；无 `*_KEY/*_TOKEN` env；`/root/.config/autoteacher` 不存在；`socket.socket()` → PermissionError；宿主 `podman ps -a` 0 容器；无 host broker/probe 进程（`logs/absence-after.txt`） |
| 真实 Key/模型/网络 | 0；所有 provider 为 in-process synthetic/scripted，Broker 为本地 stdio + 本地 SQLite |

**denied 场景 provider 实际调用=0 的证据不是只靠 `decision.allowed`：** BIND-01/FIX-05/09/BIND-08 均使用带内部计数的 provider；probe 中 `provider_calls=0`/`1` 为实际函数调用计数，且 BIND-01 在真实 SQLite 中无 claim 行。

## 6. 发现（severity + 证据；均非 A 范围阻断）

### F-1 · Low · `PreparedProviderRequest.schema_version` 固定值未被强制
- 契约 §2 规定 `schema_version` 固定 `"m0.prepared.v1"`；代码仅定义常量/默认值（`egress.py:115,126`），`claim_dispatch_for_request`（`:486-545`）从未校验该字段。
- 独立 probe：`schema_version="m0.prepared.v0"`，digest/call_id 由该 prepared 重算，`claim_dispatch_for_request` 返回 **allowed=True**、claimer_calls=1（`SCHEMA_VERSION_PROBE`，`logs/mechanism-probe.stdout.log:27`）。
- 影响：prepared 由受信 Bridge 构造，非候选直接控制；digest 仍覆盖版本，因此不是发送绕过或摘要碰撞。但 malformed/future schema 会被当作 v1 接受。**建议在 G3 前增加固定版本校验**；不影响 A 声明结论。

### F-2 · Medium（G3 前置）· provider 异常时实际调用被计为 0，结算归因为 NOT_DISPATCHED
- `TrustedEgressTransport.dispatch` 在 `selected(request)` 返回 Mapping 后才 `provider_calls += 1`/`record_outcome`（`egress.py:670-686`）；provider 抛异常时直接 `_denied`，不记录 attempt。
- 独立 probe：provider 实际被调用 1 次后抛 `RuntimeError`；返回 `dispatched=False, denied_reasons=["PROVIDER_ERROR:RuntimeError"], state=NOT_DISPATCHED, provider_calls=0`（`PROVIDER_EXCEPTION_PROBE`，`logs/mechanism-probe.stdout.log:28`）。
- 影响：当前 A 阶段 provider 为 synthetic，所有 denied 路径都在 provider 之前拒绝，故不改变 A 的 0 调用证据；但 G3 接真实 provider 后，若“已发送后读响应超时/断连”以致 provider 抛异常，可能把可计费尝试记成未派发，违反保守结算预期。**必须在 G3 真实 wire 接线前修复**（记录 attempt、BILLABLE_UNKNOWN/最坏成本；permission 已单次消费，不会二次发送）。

### F-3 · Low · Review Packet 证据完整性（不影响功能结论）
- Packet 的 `evidence/logs` 只有 GREEN/full/Ruff/script（8 stdout + 8 stderr），**没有 RED log**；RED 证据只在 owner 工作区 `artifacts/g2l1/logs/red.stdout.log`（非 packet、非 Git）。历史 A0 的 2 个 xfail 占位版本未入库，无法从 packet 逐字节复现 10 failed/2 xfailed。
- 没有独立的 concurrency/crash/process-absence log；这些行为只由 full/focused 中的 INT-05/06/17、PROC-01 覆盖。
- `evidence/commands.jsonl` 8 行是摘要（selection 字符串），缺 §8 要求的完整 argv/cwd/隔离参数/逐行 UTC；实际 argv 只在 `artifacts/g2l1/argv/`。
- `evidence/matrix.json` 是 7 个组级条目，未逐条映射到具体 pytest node/日志行。
- 影响：可追溯性/可复验性不足；本轮独立重跑已补齐结论。建议 Packet errata（不重写旧字节）：补 RED/并发/崩溃/absence 日志、完整 argv/UTC、per-ID matrix。

### F-4 · Low · manifest 的 stage 归一化 hash 不是 `git archive 2786e25` 的直接结果
- `evidence/manifest.json` 写 `stage_source="git archive 2786e25"`、`stage_normalized_tar_sha256=e7861641…`。
- 独立复算：raw `git archive` 抽取 + 声明的 tar 归一化 = `47a71779…`；再 `chmod -R a-w` = `a146e5c7…`；只有 owner 的 `artifacts/g2l1/stage`（4 个文件 0444、其余 0664、root 0755）才得到 `e7861641…`。
- 内容层面已独立验证：192/192 blobs 等于 `2786e25` tree `ef246ebc…`，所以不是源码替换；是 stage 后处理 mode 位未记录。建议记录 content-tree hash + 精确 chmod 清单，或同时列出 raw/`chmod -R a-w` hash。

### F-5 · Low · OBS-1 顶层 stream 归因仍保留首个 reservation
- `LogicalStreamEgress.reservation_id` 在创建时固定（`egress.py:242-254,300-304`），`snapshot()` 顶层仍输出首个 reservation（`:589-600`）；新增的 `attempts_detail` 才逐 attempt 正确归因。
- `TRACE-01` 只断言 `attempts_detail`（`test_g2l1_fix.py:620-631`），未断言顶层字段。影响：只读顶层 legacy 字段的消费者仍可能误归因；detail 已提供权威信息。建议在 G3/审计消费者迁移时明确 legacy 字段语义或标记 deprecated。

### F-6 · Low · INT-11 仍是 descriptor-only，真实跨 route refusal 由 BIND-01 覆盖
- `test_int11_route_path_method_mismatch_never_claims`（`test_g2_closure.py:380-391`）仍构造无 claimer 的 `EgressBoundary`，只证明 policy deny/claims=0，不是真实 Broker 跨 route 拒绝。
- BIND-01（真实 SQLite/stdio）覆盖同一风险；findings 已标 TEST-1 PARTIAL。影响：测试命名/覆盖分配，不影响 A 结论；建议后续把 INT-11 或注释明确为 policy-only，避免误读。

### F-7 · Info · prepared 描述符的其余字段级约束未在 egress 校验
- 契约 §2 对 `scope_id`/`run_id`/`logical_step`/`attempt_index`/`provider`/`system`/`messages`/`tools`/`response_format`/`retry_policy` 有类型/非空约束；`claim_dispatch_for_request` 只做 digest/固定字段交叉比较，不对这些字段逐项做契约校验。
- 这些字段由受信 Bridge 构造且被 digest 覆盖；不是候选可控输入。与 F-1 同类，建议 G3 在受信构造器/egress 入口统一校验。

### F-8 · Info · `_issued_permissions` 无过期/上限
- `egress.py:298,463,634`：每个成功 claim 写入 registry，只有 consume 才删除；claim granted 但永不 dispatch 的 permission 会留到进程结束。长生命周期 Bridge 下有内存增长风险；无安全绕过（伪造/重放仍拒绝）。建议 G3 加 TTL/上限/关闭清理。

### F-9 · Info · 新 bound API 尚无生产调用点
- `claim_dispatch_for_request` 只被测试调用；`TrustedEgressTransport` 无生产 caller；生产代码无 `BoundBrokerClaimer` 实现（只有测试 `test_g2l1_fix.py` 的 class）。这与 A 阶段“只修库/接口、不接 G3”一致，但意味着本 PASS 不能外推为“生产 Provider 路径已强制绑定”；G3 必须完成真实接线与集成测试。

## 7. 已确认的声明残余 / G3_DEPENDENCY（不得写 PASS）

1. **旧 v1 残余（已披露）**：旧客户端省略 `expected_route_id/expected_model` 时，broker/ledger 仍按旧行为 claim；`claim_dispatch()`/`require_claim()` legacy 路径可产生可消费 permission（FIX-08 即使用该路径）。新 `claim_dispatch_for_request()` 对无 `claim_bound` claimer 显式 deny，但不能替旧客户端强制 ledger 绑定。G3 前需迁移/阻断旧客户端。
2. **真实 wire/digest**：Prepared digest 在进程内重算并逐字段绑定；实际 provider wire bytes 与 prepared digest 的远端一致性未验证（BIND-2/G3）。
3. **正式 tool 注册表**：A 仅有 egress 输入负例 `approved_tool_schemas`；正式 schema 注册/审批/来源未实现。
4. **远端 exactly-once / usage / invoice**：本地 SQLite claim 至多一次 ≠ 远端只发送/只计费一次；真实 usage/账单未验证。
5. **Provenance**：`TrustedEgressProvenance`/`DispatchPermission` 仍是同进程 capability，不是跨进程密码学授权；外部 egress/Key Broker 未部署。
6. **生产 wiring**：无生产 `BoundBrokerClaimer`/`TrustedEgressTransport` 调用点（F-9）；G3 需把 bound claim + trusted transport 接入真实 Bridge。
7. **F-2**：真实 provider 异常时 attempt/usage 归因需在 G3 前修复。
8. **Live/Key/网络**：`gates.py`/`dsh_adapter.py`/`run_live.sh` 仍硬阻断；E1–E5/LiveGate/真实 Key/真实模型/外部 HTTP 均 **BLOCKED / DECISION PENDING**；本审阅不签发 GO。

## 8. 可复验路径

```bash
cd "/root/Autonomous Teacher"
# 1) 身份（不修改 repo）
artifacts/reviewer-g2l1/verify_identity.sh
artifacts/reviewer-g2l1/audit_packet.sh
# 2) 新 stage
git archive 2786e25 | tar -x -C artifacts/reviewer-g2l1/stage
chmod -R a-w artifacts/reviewer-g2l1/stage
# 3) 在固定无 Key OCI 重跑（宿主不跑 pytest）
artifacts/reviewer-g2l1/run_container.sh focused-all 300 -m pytest \
  tests/integration/g2_closure/test_g2l1_red.py \
  tests/integration/g2_closure/test_g2l1_fix.py \
  tests/integration/sandbox/test_egress_boundary.py -q -p no:cacheprovider --tb=short
artifacts/reviewer-g2l1/run_container.sh full-tests 400 -m pytest tests -q -p no:cacheprovider --tb=short
artifacts/reviewer-g2l1/run_container.sh ruff-repo 120 -m ruff check --no-cache .
# 4) 真实 SQLite/stdio 机制 probe
artifacts/reviewer-g2l1/run_probe.sh mechanism-probe 180
```

- 完整 argv：`artifacts/reviewer-g2l1/argv/`；UTC/exit：`logs/exit.jsonl`；日志：`logs/`。
- 身份/静态/证据审计：`identity/identity-report.txt`、`identity/packet-audit.txt`、`identity/static-trace.txt`、`identity/stage-identity.txt`。
- 复验注意：`stage_normalized_tar_sha256` 依赖 mode 位；本审阅同时记录 content-tree（`ef246ebc…`）与三种 tar hash（raw `47a71779…`、all-a-w `a146e5c7…`、owner `e7861641…`），避免把 mode 差异误判为源码差异。

## 9. 证据索引

- 独立 stage：`artifacts/reviewer-g2l1/stage/`（192 files，all 0444）、`stage-base-32bea5b/`（baseline RED）。
- 独立 manifest/hashes：`artifacts/reviewer-g2l1/manifest.json`、`hashes.sha256`、`commands.jsonl`、`stage-identity.txt`。
- 审阅 probe：`artifacts/reviewer-g2l1/probe/mechanism_probe.py`、`logs/mechanism-probe.stdout.log`。
- 失败/absence 证据：`logs/baseline-red.stdout.log`（旧代码 11 failed）、`logs/targeted-required.stdout.log`（38 passed）、`logs/full-tests-rs.stdout.log`（skip 原因）、`logs/absence-after.txt`（容器/进程 absence）。
- 审计报告：`identity/identity-report.txt`（0 failures）、`identity/packet-audit.txt`（RED/并发/absence/matrix 缺口如实记录）。
- **STOP**：G2-L1-FIX 独立审阅完成；G3 未启动，需维护者另行明确批准。
