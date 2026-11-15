# M0 G0 — 当前基线与 v0.6/历史 findings 差异审计

- 任务：`task-58`（v0.6 G0）；日期：2026-11-15 UTC；审计者：`verify2`（非实现者）
- 性质：**只读静态核对 + 文档/证据固化**。未运行项目代码/pytest/TS/容器；0 真实 Key、0 模型、0 网络/HTTP；未读取凭据；未改源码/测试/配置/历史证据；未 `git add/commit`。
- 关键边界：本文件中的“CONFIRMED”仅表示**静态事实或风险推导成立**，不是运行 PASS；G1–G6 的 PASS 必须按 v0.6 各自 gate 重新执行并独立审阅。
- 交付证据：[`artifacts/g0-baseline/manifest.json`](../artifacts/g0-baseline/manifest.json)、`source-inventory.tsv`、`evidence.sha256`；当前阻塞：[`OPEN_BLOCKERS.md`](OPEN_BLOCKERS.md)。

## 1. 基线身份（实现 SHA 与 docs SHA 分开）

| 项 | 值 |
|---|---|
| 当前 HEAD | `abbc6bcd2a2128456627d9370465323b505aafd9`（**docs-only**：v0.6 手册归档） |
| HEAD 父 | `4c0419d206f01278205b8d2cc0b6de64baa13ed8`（M0 docs 收口） |
| **实现代码冻结 SHA** | **`87f44e1227f38e454c4dc418b0e289df85721fb5`**（V-PR3-1/Ruff hygiene；`abbc6bc` 与 `4c0419d` 仅改 docs/README） |
| 工作树 | clean（`git status --porcelain -uall` 为空；gitignored evidence 除外） |
| tracked 文件 | **169**（`git ls-files`：src 40、docs 40、plugins 34、tests 28、scripts 10、config 6、fixtures 4、根文件 7） |
| v0.6 手册 | `docs/Autonomous_Teacher_M0_Execution_Validation_Review_Playbook_v0.6.md`，1097 行，sha256 `a34177261a81bb06e778bbaa32b603cdd6557d31ce7f1e9cb6fada689cf57c4b` |
| docs 收口 commit | `4c0419d`（9 files +509/−1，仅 docs/README；5 份 REVIEW_CLOSEOUT + M0_CLOSEOUT_REPORT/ROADMAP + RUNTIME_BUDGET_GUARD + README） |

### 1.1 冻结 commit 链（历史，不重算旧证据）

| 阶段 | commit | 父 | 说明 |
|---|---|---|---|
| PR0 docs | `e8b6e45` | `7c3806b` | v0.5 基线/审查/路线图/OpenCode 调查 |
| PR1 | `fdcfdc9` | `e8b6e45` | broker/guard F1–F6（离线） |
| PR3 | `9b77a37` | `fdcfdc9` | 可信 Live Controller 设计 + 无 Key 演练 |
| PR2 | `7d2cd3e` | `9b77a37` | 目标 Runtime/Profile + F7 gap |
| PR4a | `8cf2476` | `7d2cd3e` | mock egress/失败矩阵/billable inventory |
| PR4b | `c802a32` | `8cf2476` | ProviderObservation/usage 映射/call identity |
| Ruff hygiene | `87f44e1` | `c802a32` | 8 文件 lint/证据 scope 修正（无行为变更） |
| M0 docs | `4c0419d` | `87f44e1` | 5 审计报告 + closeout 文档 |
| v0.6 手册 | `abbc6bc` | `4c0419d` | 本次 G0 输入；**实现代码不变** |

### 1.2 关键源文件 sha256（当前实现 SHA 87f44e1 的字节）

| 文件 | sha256 | 行数 |
|---|---|---|
| `src/autoteacher_m0/security/authorization.py` | `cce68fe1750eafaa17b558db958916c43d50ca9d2f1561da1465fda36ad64fd4` | 430 |
| `src/autoteacher_m0/security/ed25519.py` | `b71162dc88bb137ac03d2a559fcc050973d428049b3b1d23f44c16ea018e89ba` | 140 |
| `src/autoteacher_m0/security/live_controller.py` | `2fac573e18e0827dcc76bdc8d76b1217a00e49150d27a55d178f33c49f1e55d3` | 177 |
| `src/autoteacher_m0/security/watchdog.py` | `3dc5fbf65f5c308f93a96d4c52003e740fd6ffda4329454610a7f6fb4e3d1761` | 279 |
| `src/autoteacher_m0/security/egress.py` | `678f30940565385d1834ed49c1472142af1671a35a539359c216bf8ff0ea8479` | 286 |
| `src/autoteacher_m0/security/credential_boundary.py` | `f7424e7e19777702c1a109223b4d10d66c7bf2d31330c786be9b2c61d91c3abb` | — |
| `src/autoteacher_m0/security/gates.py` | `3ed0863440d26105f30f84579f07105c298ed586cbd8e4616c15fad495afb23a` | — |
| `src/autoteacher_m0/security/docker_runner.py` | `8b4c3d86be5b855f653025254a3379b3dfae24142945780d1e4b6daa18d030d1` | — |
| `src/autoteacher_m0/accounting/observation.py` | `3fd9f7932712f29fd330bf5667293ec7492d1421cb00bafd5c2ff523bc8873a0` | 324 |
| `src/autoteacher_m0/accounting/broker.py` | `78dc3bb85033e0c46c937843fc2d3814c87ed1f4aea248e6b38a70d45be4e8df` | 356 |
| `src/autoteacher_m0/accounting/ledger.py` | `6ff7210fa15764f5167908ef3b0f48c699d4460d1c168437ca148f583092c3ad` | 308 |
| `src/autoteacher_m0/accounting/budget.py` | `50e2ae7106ecf9584e9f4081a1fafa594b4b220bad9ef195c61142cac1c90e7e` | — |
| `src/autoteacher_m0/accounting/broker_usage.py` | `8be713b421052c43121dc178a11df4dea8e4be6ecf518d4a6d9232d84c70a6f8` | — |
| `src/autoteacher_m0/accounting/pricing.py` | `19f8a89300601294a829a2edb2d445699d0b0f1e1b76e03a05c462abeac22b2d` | — |
| `src/autoteacher_m0/accounting/usage.py` | `923ebca97309c41ddcc2175d94887d844f565057a70a9d417b32fb15773957c2` | — |
| `src/autoteacher_m0/runtime/dsh_adapter.py` | `888911490c936dff286af5ad823aae1007d88ab50213986c4b809d34b44cc68a` | — |
| `plugins/runtime-budget-guard/src/index.ts` | `0ee49111fbec179c3dea80dcaa11b92df194e69d78d830a154d5beafc68fe3be` | — |
| `config/dsh/target-runtime.patch.yml` | `367ec27c6130993d3968658fb278ed1837cf83f99c891a72a2c7ecb441fc7d5a` | — |
| `config/dsh/target-runtime-opencode-go.patch.yml` | `9c5fe713e5af25f47e24f4db9c4f30172c31bcfe3030301b7eeb5831c47fc652` | — |
| `config/dsh/target-broker-policy.json` | `c67d2bbfd9386fa5f2ff651ab0d9ef51a936fb67b5c8e5b96c358adb2ac78129` | — |

完整 169 个 tracked 文件的路径/sha256/字节见 `artifacts/g0-baseline/source-inventory.tsv`；其中包含 `.env.example`（仅文档模板，明确 `DEEPSEEK_API_KEY` 故意不出现；无真实凭据）。

### 1.3 锁文件、DSH/SDK、插件、镜像/rootfs/deps 身份（引用既有 manifest，不重跑）

| 项 | 身份 | 来源（只读） |
|---|---|---|
| Python 依赖锁 | `uv.lock` sha256 `db189d41886a425480ef21e92e29935f5af078d5f67786541b1fba86d5d29155`；`pyproject.toml` `204e27292617a8b9009125da5990314ea4bd371ddb909460cb80d5297e2128b0` | 本审计直接 hash |
| Node 插件锁 | guard `plugins/runtime-budget-guard/package-lock.json` `119ee480…2b4a3`；offline-fixture `72533fa9…b4a3`；skill-lookup `8ed939c9…1c73`；对应 package.json 见 source-inventory | 本审计直接 hash |
| DSH Runtime / SDK | runtime binary `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`；Python SDK `0.2.2rc2`；runtime wheel/CLI `0.2.2rc2`/`0.2.2-rc.2` | `artifacts/phase5-integration/manifest.json` `environment_identity`（历史 evidence；未重跑） |
| guard 构建产物 | lib `3d2b9cf545fcdcac96c7858f743875e164f5eb7871b6102105664551271dd75b`；native cache `40c34d27d8339e246a8f7415a06152935496cdc06555ea8fce0e052011acc70f`；pkg cache 4857 文件 key `dfa6d5861f51ddb5112a7c92e560752d79c2a89362c0634c8d4f0fc888b21487` | PR1/PR2/PR3/phase5 manifest（历史） |
| 固定 OCI 镜像 | `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b`；image id `56db1e2a…f9a7715` | PR3/PR2/phase5 manifest（历史） |
| rootfs / deps | rootfs canonical `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；deps canonical `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` | phase5 manifest（历史；本次未启容器） |
| target stage | 6530 files，normalized tar `f8f7520364cd07084012783fd6c3c99707aac8d5b0851253375e05d6ca14901b` | `artifacts/m0-runtime-integration/manifest.json`（历史） |

> 这些是**历史证据身份引用**。G0 不重跑容器；G1/G2 修改代码后必须生成新的实现 SHA/锁/构建/镜像身份，不能沿用旧 identity 声称当前候选 PASS。

## 2. v0.6 附录 A 13 项逐项映射（当前实现 SHA 87f44e1）

状态词汇：CONFIRMED=静态事实成立；CONDITIONAL=部分/条件成立或需定向测试定性；ALREADY_FIXED=已由后续提交/errata 关闭；UNVERIFIED=当前无法静态确认或需运行证据；NOT_APPLICABLE=不适用于当前代码。**本表不是测试 PASS。**

| # | 附录 A 观察 | 当前状态 | 当前代码证据（file:line） | 既有测试/证据 | Gate | P0/P1 | 需要新代码/协议/文档 |
|---|---|---|---|---|---|---|---|
| A1 | 弱公钥验签：`verify()` 无可信公钥子群准入 | **CONFIRMED**（静态） | `security/ed25519.py:77-89` 仅长度/`y<Q`/on-curve 解码；`:127-140` verify 只检长度、`S<L`、曲线方程，无 identity/low-order/cofactor 检查；`security/authorization.py:211-223` trusted key 加载只校验 32-byte hex，无点/阶检查 | `tests/unit/security/test_authorization.py` 覆盖签名/公钥篡改，但无 identity/小阶公钥用例（未搜索到） | G1 AUTH-02 | **P0** | 新代码：注册/加载路径拒绝 identity/小阶/非规范点；verify 使用严格子群/维护实现；新增 AUTH-02 回归。仅换库不自动满足业务要求 |
| A2 | 授权 int coercion：`int(budget_payload["max_calls"])` 等 | **CONFIRMED** | `security/authorization.py:340-357` 中 `int(payload["max_calls"])`；`:359-377` 对 `total_seconds/max_steps/max_dispatch_attempts` 同样 `int(...)`；`_require_usd` 仅限制 USD 字段 | `test_authorization.py:218-228` 仅测整数/范围，无 `"10"`/`10.4`/`True` | G1 AUTH-05 | **P0** | 新代码：`type(x) is int` 严格白名单 + 定向负测 |
| A3 | `approver` 异常变量：时间/审批人同一 try，异常后变量可能未初始化 | **CONFIRMED** | `security/authorization.py:275-288`：`approver = _require_text(...)` 在 try 内；若 `_require_text` 抛异常，except 只设 `issued/not_before/expires`，未设 `approver`；`:417-418` 构造 `ExecutionAuthorization(approver=approver,...)` 会 `UnboundLocalError`（fail-open 崩溃而非明确拒绝） | 重复 JSON key 已被 `:64-91`/`test_authorization.py:174-178` 拒绝；但没有非法 approver 的安全拒绝测试 | G1 AUTH-06 | P1（v0.6 §12 矩阵未列 AUTH-06，建议 Lead 裁定是否升 P0） | 新代码：异常路径明确返回拒绝，禁止未赋值变量进入对象；补 AUTH-06 测试 |
| A4 | Controller 路由策略：`_candidate_violations()` 只比较 `host_ports` | **CONFIRMED** | `security/live_controller.py:106-126`：mount/argv/env 检查后仅在 `:124` 比较 `self.egress.host_ports != OPENCODE_GO_EGRESS.host_ports`，未比较 method/path/route/model/scope/budget/files/store；`:69` 默认 egress 为 `OPENCODE_GO_EGRESS`；Controller 仍 inspect-only/always BLOCKED（`:38-44,:128-147`） | `tests/unit/security/test_watchdog.py` 等不覆盖完整 policy 绑定；无 AUTH-08 定向测试 | G1 AUTH-08 | P1 | 新代码：完整 Route/Egress Policy 逐字段校验；先离线检测，不得新增 Live 入口 |
| A5 | reasoning 口径：`__post_init__` 无条件 `reasoning > output` 拒绝，`to_usage` 又支持额外 reasoning | **CONFIRMED（语义），但 v0.6 “无条件”措辞不完全准确** | `accounting/observation.py:133-142`：仅 **AUTHORITATIVE** 分支检查 `reasoning is not None and reasoning > output`；`:143-155` PARTIAL/MISSING/UNKNOWN 不检查；`:207-224` `to_usage(reasoning_in_output=False)` 会把独立 reasoning 加到 output。故独立计费 reasoning>output 无法通过 AUTHORITATIVE schema | `tests/unit/accounting/test_provider_observation.py:60-73` 测 inclusive 与 additional 的正常场景；无 OBS-01 独立 reasoning>output 用例 | G1 OBS-01/02 | P1 | 新代码：把 `reasoning ≤ output` 约束移到 route billing policy 语义层；补 OBS-01/02 测试 |
| A6 | partial cache：Partial input 完整时保留 `cache_read` 优惠 | **CONDITIONAL**：v0.6 所述的“只有 cache_read、缺其他 input”在当前代码中**没有**保留折扣；仅当 input/cache_read/cache_write 三者都完整时才保留 cache_read；且 ledger 对 estimated 成本有 `max(cost, reserved_cost)` 地板 | `accounting/observation.py:227-237`：`complete_input = all(input,cache_read,cache_write)`；不完整时 `total_input=max(reserved_input, known_input)`、`cache_read=0`；`accounting/ledger.py:256-276` 对 `estimated` 且无 actual 的成本取 `max(cost, reserved_cost)`。潜在残余需针对“完整 input + 缺失 output + actual/provider_invoice”路径测试 | `test_provider_observation.py:75-83`（输入不完整→full bound，cache=0）；`:86-98`（missing full bound）；无 OBS-03 定向“完整 input + partial output”用例 | G1 OBS-03 | **P0** | 需要**定向测试+政策裁决**；当前静态证据不支持“已存在低估”结论，但 v0.6 要求仍须显式证明不得低于保守上界 |
| A7 | 未经来源认证的 Observation：`deliver_observation()` 从 call link 找 reservation 后直接状态映射 | **CONFIRMED** | `accounting/observation.py:279-324`：只校验 call_id 正则、从 `budget_call_links` 找 reservation、把 caller-supplied observation 直接 `to_usage`/`settle`；无签名/可信来源/route+model+request identity 校验；`cost_source=provider_invoice` 可由调用方声明（`:225,:236`） | 测试覆盖 idempotence/conflict/UNKNOWN_CALL（`:101-135`），无伪造 observation 的 source-auth/route-mismatch 用例 | G1/G2 OBS-05/INT-15 | **P0** | 新协议/代码：OBS-05/06 来源认证、route/model/request digest 绑定、AUTHORITATIVE 只能由可信 Egress 投递；补 INT-15 |
| A8 | Watchdog 异常清理：`except BaseException` 只 kill tree 后重抛，未确保容器清理 | **CONFIRMED** | `security/watchdog.py:242-279`：`:256-261` 仅当 `process.poll() is None` kill tree 后重抛；`cleanup` 只在正常流程 `:271-272` 调用（无 `finally`）；cleanup 抛异常直接传播，未转 `SECURITY_BLOCKED`；容器 absence 只在 cleanup 内 `confirm_container_absence` | `tests/unit/security/test_watchdog.py:166-173` 期望 RuntimeError 传播（当前测试把失败语义固定为 re-raise，而不是 SECURITY_BLOCKED） | G1 WD-03/04 | **P0** | 新代码：统一 finally/外部 supervisor 清理路径；cleanup 异常/超时→SECURITY_BLOCKED；补 WD-03/04 |
| A9 | ID/Reservation 冲突：`egress.py` 派生 `eg-...`（含 reservation）；`observation.py` 派生 `call-...`（预留前） | **CONFIRMED** | `security/egress.py:103-108`：`eg-` + sha256(logical_stream_id,reservation_id,attempt_ordinal,route,model,host,port,path)[:24]；`accounting/observation.py:268-271`：`call-` + sha256(CallIdentity{run_id,logical_step,attempt_index,request_digest})[:48]；`accounting/ledger.py:122-123,134-160` 只接受 `call-[0-9a-f]{48}` 并绑定 reservation。两套 ID 不同前缀、不同材料、不同生成时点，egress ID 不能直接作为 broker call link | `test_egress_boundary.py:25` 断言 `eg-`/27 字符；`test_provider_observation.py:149-158` 断言 `call-`；无统一 ID 跨层测试 | G2 INT-01 | **P0** | 新协议/ADR-002：统一 CallIdentity（预留前由可信方生成），全链使用一个 ID；更新 egress/observation/broker/ledger 与兼容策略 |
| A10 | 仅非空 Reservation 校验：`egress.py: if not request.reservation_id.strip()` | **CONFIRMED** | `security/egress.py:125-172`：`:129` 仅拒绝空字符串；EgressBoundary 不依赖 ledger/broker，无法证明 reservation 真实/未过期/未被 claim；`MockEgressTransport.dispatch` 也只凭 boundary decision 发包 | `test_egress_boundary.py:31` 只测 `reservation_id=""`；无“非空但伪造/未绑定”用例 | G2 INT-02/03 | **P0** | 新代码/协议：dispatch 前向可信 Broker 做持久 claim/校验；仅非空字符串不得授权 |
| A11 | 非持久 Attempt 数：`EgressBoundary` 的 in-memory `attempts`，同 ordinal 重放未独立去重 | **CONFIRMED** | `security/egress.py:116-123` `_streams` 为内存 dict；`:152-160` `attempts` 内存计数；`:155` 只按累计 attempts 上限拒绝；无持久 claim/dedup；`MockEgressTransport` 进程内 | `test_egress_boundary.py:51-56` 测内存 attempt limit；无跨进程/重启/同 ordinal 重放测试 | G2 INT-04/05/17 | **P0** | 新代码：持久 claim（Reservation 只许可一次 Attempt），跨进程/崩溃/重放测试；不由进程内 set/dict 充当幂等 |
| A12 | Guard 缺失：PR2 无 Guard synthetic fixture 仍被调用，外部边界尚未实测 | **CONFIRMED（gap 存在）/ 外部闭包 UNVERIFIED** | PR2 evidence `artifacts/m0-runtime-integration/manifest.json:74-77`：`no_guard.rbg_boot=0, fixture_invocations=1, gap=F7_GUARD_ABSENT_DOES_NOT_BLOCK_SYNTHETIC_FIXTURE_DISPATCH`；`docs/DSH_TARGET_PROFILE.md:32` 明确 F7 gap；当前 runtime 无外部 egress/Key 边界，`gates.py`/`dsh_adapter.py` 仍 hard BLOCKED | PR2 manifest/日志与 PR2 独立审计；未做真实 OS direct-connect 负测 | G3 BR-06/10 | **P0** | 新网络边界/G3：受控 Fake Provider + 真实 DSH 直连拒绝 + OS 证据；不能由插件内部或静态 profile 替代 |
| A13 | OpenCode Go 默认配置：`live_controller.py`/`egress.py` 默认路由对向 OpenCode Go，不等于官方 DeepSeek 主路由 | **CONFIRMED（静态默认值）** | `security/live_controller.py:69` 默认 `egress=OPENCODE_GO_EGRESS`；`security/credential_boundary.py:232-238` 定义 `OPENCODE_GO_EGRESS`（`opencode.ai:443`, POST, `/inference/go/`）；`security/egress.py:24-28,67-78` 的 `EgressRequest/EgressPolicy` 默认 host/path/route 为 OpenCode Go；`config/dsh/target-runtime-opencode-go.patch.yml` 是 STATIC-ONLY overlay | PR4a/PR2 证据；OpenCode Go 仅 INTERNAL-TEST-ONLY，无 Key/网络；正式主路由仍固定 DeepSeek V4.1 Flash 待运行前核对 | G4 Route Policy | P1（G4 政策/部署决策） | 政策裁决+配置/测试；不得把 OpenCode Go 默认值当作官方主路由批准或 Live 许可 |

**附录 A 统计：CONFIRMED 12、CONDITIONAL 1（A6）、ALREADY_FIXED 0、UNVERIFIED 0（A12 的静态 gap 为 CONFIRMED，其外部闭包另列 UNVERIFIED）、NOT_APPLICABLE 0。P0=9（A1,A2,A6,A7,A8,A9,A10,A11,A12），P1=4（A3,A4,A5,A13）。**

## 3. v0.6 对当前代码描述准确性复核（重点）

| # | v0.6 说法 | 复核结果 |
|---|---|---|
| 1 | `ed25519.verify()` 无专门可信公钥子群准入 | **准确**：`ed25519.py:77-89,127-140` 无 identity/low-order/cofactor 检查；`authorization.py:211-223` 注册也不做点校验。 |
| 2 | `authorization.py` `int(...)` 允许非整数原始类型转换 | **准确**：`authorization.py:345,367-369`；`True`/`"10"`/`Decimal("10.4")` 可被 int 转换，缺少 `type(x) is int`。 |
| 3 | 时间/`approver` 同一 try，异常后变量可能未初始化 | **准确**：`:275-288` + `:418`，非法 approver 可触发 `UnboundLocalError`；重复 JSON key 另有拒绝（`:64-91`）。 |
| 4 | `live_controller._candidate_violations()` 只比较 `host_ports` | **准确**：`:106-126`，仅 `:124` 比较 host_ports，未校验 method/path/route/model/budget/files 等。 |
| 5 | `observation.__post_init__` 无条件 `reasoning > output` 拒绝 | **部分准确**：约束只在 AUTHORITATIVE 分支（`:133-142`）；PARTIAL/MISSING/UNKNOWN 不检查。语义风险（独立 reasoning>output 不可表示）成立，但“无条件”应改为“AUTHORITATIVE 分支”。 |
| 6 | Partial input 完整时保留 `cache_read` 优惠 | **部分准确/需测试**：仅当 input/cache_read/cache_write 全部完整才保留 `cache_read`；缺其他 input 时 `cache_read=0` 且输入用 reserved 上界（`:227-237`）；ledger 对 estimated 成本有 `max(cost,reserved_cost)` 地板（`ledger.py:272-275`）。v0.6 举例的“只有 cache_read、缺其他 input”在当前代码未复现折扣；仍需 OBS-03 定向测试和 policy 裁决，不能据此宣称已安全。 |
| 7 | `deliver_observation()` 从 call link 找 reservation 后直接状态映射（未认证来源） | **准确**：`:279-324`，无来源签名/route-model-request 校验；`provider_invoice` 可由调用方声明（`:225,:236`）。 |
| 8 | `watchdog.py` `except BaseException` 只 kill tree 后重抛，未确保容器清理 | **准确（且更具体）**：`:256-261` 仅 kill tree 后重抛；`:262-272` cleanup 非 finally，cleanup 异常不转 SECURITY_BLOCKED；测试 `:166-173` 当前固定为 RuntimeError 传播。 |
| 9 | `egress.py` 的 `eg-`（含 reservation）与 `observation.py` 的 `call-`（预留前）冲突 | **准确**：`egress.py:103-108` 与 `observation.py:268-271`；ledger 只接受 `call-`（`ledger.py:122,134-160`）。 |
| 10 | `egress.py` 仅用非空 reservation 校验 | **准确**：`egress.py:129`。 |
| 11 | `EgressBoundary` in-memory attempts，同 ordinal 重放未独立去重 | **准确**：`:116-123,152-160`；无持久/跨进程 claim。 |
| 12 | Guard 缺失时 PR2 synthetic fixture 仍被调用，外部边界未实测 | **准确（gap）**：PR2 manifest `:74-77`、`docs/DSH_TARGET_PROFILE.md:32`；外部 OS/网络闭包仍 UNVERIFIED。 |
| 13 | `live_controller.py`/`egress.py` 默认路由对向 OpenCode Go，不等于正式 DeepSeek 主路由 | **准确（静态默认）**：`live_controller.py:69` + `credential_boundary.py:232-238` + `egress.py:24-28,67-78`；正式主路由未在代码中默认为 OpenCode Go，当前仍 BLOCKED/政策待定。 |

**结论**：v0.6 附录 A 的 13 项中，11 项描述准确；A5/A6 的措辞需按当前代码收窄（A5“无条件”、A6 对具体 partial-cache 例子的折扣结论）；A6 需要定向测试，不能直接写成 CONFIRMED 缺陷，也不能写成已安全 PASS。

## 4. 此前 V-*/O-* findings 映射

| ID | 来源 | 当前状态 | 当前证据/说明 | Gate | 优先级/动作 |
|---|---|---|---|---|---|
| V-PR1-1 | PR1 审计（fail-first/pass 计数） | **ALREADY_FIXED** | errata `artifacts/m0-closeout-fix-tests/manifest-errata.json` sha256 `9fc6fb93…`；`docs/RUNTIME_BUDGET_GUARD.md:263` 已改为 9 failed/3 passed；当前 doc `25f38621…`；原始日志保留 | G0 | P3，文档；无代码 |
| V-PR2-1 | PR2 审计（`verify_runtime_profile.py` 2 Ruff errors） | **ALREADY_FIXED** | 87f44e1 删除未用 `sys`/`stderr_path`；当前 script `e2542747…`；HEAD repo-wide Ruff 证据 `vpr31-final-ruff.*` exit0 | G0 | P3，无新代码 |
| V-PR3-1 | PR3 审计（Ruff 泛写 scope） | **ALREADY_FIXED** | errata `artifacts/m0-controller-no-key/manifest-errata.json` sha256 `8aed1f84…`；E5 report `6141977f…`/design `bdeefd37…`；87f44e1 更新 docs | G0 | P3；注意 worktree evidence 15/17（O-FINAL-1） |
| V-PR4A-1 | PR4a 审计（manifest baseline.head 假 SHA） | **ALREADY_FIXED** | errata `artifacts/m0-egress-validation/manifest-errata.json` sha256 `92020bff…`；旧 manifest 字节未改 | G0 | P2，证据 errata；无代码 |
| V-PR4A-2 | PR4a 审计（7 Ruff errors） | **ALREADY_FIXED** | 87f44e1 删除未用 import/变量；当前 `egress.py:678f3094…`、`__init__.py:2f9c2a3e…`、verify script `7f95690e…` | G0 | P3 |
| V-PR4B-1 | PR4b 审计（继承 lint 13 errors） | **ALREADY_FIXED** | 87f44e1 后 HEAD repo-wide Ruff `All checks passed!`（vpr31 证据）；PR4b scoped clean | G0 | P3 |
| O-PR2-1 | PR2 证据 worktree 漂移 | **CONDITIONAL** | 对冻结 commit evidence 49/49；当前工作树 48/49（87f44e1 修改 `verify_runtime_profile.py`）；M0 report §3 已注明 | G0 | P3，可留档；不建议改写旧字节 |
| O-PR3-1 | PR3 owner stage 与 commit 1 文件快照差异 | **NOT_APPLICABLE** | 仅 PR1 测试文件快照差异，非 PR3 scope；审计已用 commit 真值 | G0 | 仅记录 |
| O-PR4A-1 | PR4a 证据 worktree 漂移 | **CONDITIONAL** | 对冻结 blob 19/19；当前工作树 16/19（87f44e1）；M0 report 已注明 | G0 | P3，留档 |
| O-PR4B-1 | PR4b 使用 artifact-hashes 而非 evidence.sha256 | **CONDITIONAL** | artifact-hashes 8/8 OK，但命名/覆盖范围未统一；不影响结论 | G0 | P3，后续 manifest 规范 |
| O-PR4B-2 | PR4b run base 7d2cd3e vs parent 8cf2476 | **NOT_APPLICABLE** | 已核对 accounting/tests 与 final commit 逐字节一致；PR4a 未改 accounting | G0 | 仅记录 |
| O-FINAL-1 | PR3 §3 evidence 17/17 未注明 worktree 15/17 | **CONDITIONAL** | V-PR3-1 修订 2 docs 后 worktree drift；errata 已记录新 hash；建议补一句/errata，不改旧字节 | G0 | P3，文档澄清 |
| O-FINAL-2 | phase5 evidence 当前 worktree 71/76 | **CONDITIONAL** | 历史 manifest/evidence 字节未改（391767d3…/df63e46…）；当前漂移来自后续授权 docs/plugin 改动；不得声称当前树全检通过 | G0 | P3，留档 |
| O-FINAL-3 | PR4B 报告中“87f44e1 仅部分修复”旧表述 | **ALREADY_FIXED** | M0 report §4/§5 明确以 HEAD 实测 supersede；审计报告按历史字节保留 | G0 | 仅记录 |

**历史 findings 统计：ALREADY_FIXED 7；CONDITIONAL 5；NOT_APPLICABLE 2；无未关闭的阻断性证据/实现缺陷。**

## 5. 需要新代码/协议 vs 仅文档

| 类别 | 内容 | Gate |
|---|---|---|
| **新代码 + 定向测试** | A1/A2/A3/A4/A5/A7/A8：公钥准入/严格整数/异常路径/完整 policy/reasoning/OBS-05 来源认证/watchdog finally；A6 需定向 OBS-03 测试并按政策裁决 | G1 |
| **新协议/ADR + 持久状态** | A9/A10/A11 + broker 无 claim：统一 CallIdentity（预留前生成）、登记/claim、持久 attempt、跨进程/崩溃/重放；ADR-002 | G2 |
| **新网络/OS 边界** | A12：受控 Fake Provider + DSH 直连拒绝 + OS/egress 证据；F7 只能由外部边界闭合 | G3 |
| **人类部署/政策** | A13 + E5-P01–P05：独立 OS 身份、外部 Key/egress、人类签核、Route Policy（OpenCode Go 仅 INTERNAL-TEST-ONLY） | G4 |
| **维护者审批后执行** | LIVE-00/01/03/04/06、E4/E5-Full；真实 Key/账单核对 | G5/G6 |
| **仅文档/证据 errata** | V-PR1-1/V-PR2-1/V-PR3-1/V-PR4A-1/V-PR4A-2/V-PR4B-1 的关闭记录；O-PR*/O-FINAL-* 的漂移/命名说明；本 G0 baseline/OPEN_BLOCKERS | G0 |

## 6. G0 结论与限制

- **G0 静态基线已记录**；**G1/G2 未实现，G3 未获授权，G4 未部署，G5/G6 未开始**；不得从本文件推导任何 Live/E1–E5/GO/PASS。
- 本次仅执行只读 git/sha256/静态阅读；**未运行 pytest/TS/容器/项目代码**；所有“代码行为”结论是静态推导，G1 必须用能失败的定向回归证明/证伪（尤其 A1/A2/A6/A7/A8）。
- 历史 evidence 身份（rootfs/deps/image/runtime/插件）来自既有 manifest，**未重验**；当前实现 SHA 87f44e1 的锁/构建身份未重新生成，G1/G2 完成后需重算。
- 未发现真实 Key/`.env` 私密内容/个人 home/凭据文件被纳入 tracked inventory；`.env.example` 仅占位说明。
- G0 Gate 仍需 Lead 确认后才允许写 G1/G2 代码；本文件不替代 Lead/维护者审批。

## 7. 证据索引

- `artifacts/g0-baseline/manifest.json`：argv/UTC/exit（仅 git/sha256/只读命令）、source inventory 摘要、身份引用、映射统计、限制。
- `artifacts/g0-baseline/source-inventory.tsv`：169 个 tracked 文件路径/sha256/字节/类别。
- `artifacts/g0-baseline/evidence.sha256`：本目录 artifact 自校验。
- 历史 evidence：`artifacts/{m0-closeout-baseline,m0-closeout-fix-tests,m0-runtime-integration,m0-controller-no-key,m0-egress-validation,m0-usage-mapping,phase5-integration}/`（只读 hash 引用，不改字节）。
