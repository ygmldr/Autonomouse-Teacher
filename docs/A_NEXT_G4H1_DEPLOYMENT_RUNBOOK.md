# A-NEXT — G4-H1 无 Key 受信部署 Runbook（设计稿，未执行）

- **文档 ID**：`A-NEXT-G4H1-DEPLOYMENT-RUNBOOK-v1`
- **性质**：`DESIGN_PENDING_HUMAN`。面向维护者/受信 Operator 的人工执行手册；**不是授权凭据、不是审批、
  不是部署证据、不是 G4-H1/H2/G5/Live 已执行的证明**。仓库内**没有**真实信任根、真实 Key、真实 Egress、
  真实 Watchdog 服务，也没有真实 Provider 调用。
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/a-next-handoff` / `docs/a-next-handoff`
- **canonical 基线**：`work/g4r=fd1d3a6`；frozen src impl `d33e0aa`；base/main `3e7afee`
- **适配来源**：旧 `work/m0-g4h0:docs/g4h0/DEPLOYMENT_RUNBOOK.md`（sha256 `b780aa54…8092`）+ G4-R 新代码
  （`security/authorization.py`、`security/gates.py`、`security/live_controller.py`、`security/egress.py`、
  `security/credential_boundary.py`、`security/watchdog.py`、`bridge/{controller,admission,request_lifecycle,
  recovery_diagnostics}.py`）+ `docs/M0_G4R_HUMAN_HANDOFF.md` / `docs/M0_G4R_REVIEW_ERRATA.md`。
- **当前不变量（不得因本文件改变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
  `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

> **一句话**：本 Runbook 把“G4-H1 真实部署需要什么、谁做、证据是什么、在哪里必须失败关闭”写成可审计步骤；
> 它**只能执行到维护者签名前一步**。真实签名根/Key 注入/真实出站/E5-Full/G5 均属人类专属动作，不在 Agent 授权内。

## 0. 强制规则（P0）

| # | 规则 | 依据（本工作树实测） |
|---|---|---|
| R1 | 唯一授权介质是维护者在**仓库外**生成的 `at-m0/execution-authorization/v1` Ed25519 签名文件；Markdown、仓库内 JSON、env、`--live`、测试种子、自签文件一律不能解锁 Live | `security/gates.py:1-6,63-86`；`security/authorization.py:37,478-700`；`scripts/run_live.sh:1-5` |
| R2 | 本文件不提供可执行 Live 开关/真实 Key 注入命令；所有路径为 `<TRUSTED_DEPLOY_ROOT>` 占位 | 本文件 §3-§10 |
| R3 | 失败关闭：缺证据=失败；未知=最坏情况；不自动重试计费 attempt；不 fallback；不把“看起来成功”当证据 | `security/live_controller.py:249-279`；`security/egress.py:1-10`；`bridge/recovery_diagnostics.py:38-51` |
| R4 | 每步记录 负责人/输入 SHA/argv/UTC/exit/原始日志/证据 SHA-256；没有证据=`NOT_RUN` | 旧 G4-H0 Runbook §0；G4-R Reviewer 证据要求 |
| R5 | 任一代码/依赖/配置/profile/工具/route/预算/policy 变化使已签授权与发布**立即失效** | `authorization.py:439-447`（`binding_drift` 三检查点）；`live_controller.py:59,143-204` |
| R6 | Agent 不得签发/代签/注入 Key/执行真实出站/删除 `LiveGate` BLOCKED；发现真实 Key/未知 egress → STOP 保全证据 | 本包 `A_NEXT_HUMAN_HANDOFF.md` §7 |

状态标签（全文统一）：`VERIFIED`｜`PARTIAL`｜`UNVERIFIED`｜`NOT_RUN`｜`BLOCKED`｜`DESIGN_PENDING_HUMAN`｜`HUMAN_REQUIRED`。

## 1. 部署目标形态与组件现状（适配 G4-R/A-NEXT 代码）

| 组件 | 目标信任属性 | 当前状态（本工作树实测） | 代码/证据 |
|---|---|---|---|
| 人类签名根（Ed25519） | 私钥离线；公钥注册表/撤销列表在仓库外；Controller 只读加载 | `BLOCKED`（未部署；代码仅离线验签，无 seed/签名路径） | `security/ed25519.py`、`authorization.py:450-700`；`live_controller.py:66-70` |
| Approval/Use-log 目录 | root 所有、只读、非候选可写；use record 单次消费 | `DESIGN_PENDING_HUMAN`；**原子发布代码已验证（L1）** | `authorization.py:795-1097`（temp→fsync→`os.link`→dir fsync）；G4-R R-REV2 PASS |
| 单次授权消费（run-level） | 每个 Run 恰一次；拒绝 replay/epoch/durability unknown | **模块级 PASS / 端到端未接线**：production `src/` 无调用方（P2-02 OPEN） | `authorization.py:988`；caller grep 仅 scripts/tests；`REVIEW_G4R §9 P2-02` |
| 人类 Run Admission（可信 Launcher） | 验签/绑定→一次性消费→Run Admission→再进 Reserve/Claim | **未实现（设计/人类部署项）**；本轮只允许 Fake-only 测试接线（A-NEXT A1/A2） | 本文件 §4；G4-R P2-02 |
| 独立 Credential Broker | 真实 Key 仅在维护者可信域；候选零 Key/零直连/不可见宿主 Secret | `BLOCKED`（未部署；现有 broker 仅是 bookkeeping，不是 Key Broker） | `security/credential_boundary.py:28,64-128`；`docs/BUDGET_BROKER.md:3-17` |
| 独立 Egress（唯一发送路径） | 固定 method/host/path/route/model + 持久预留 + Claim + 摘要 | `BLOCKED`（`egress.py` 仅描述符/claim 准入，**不是网络代理**；且 allowlist 是第三方 OpenCode Go，与默认官方路由冲突） | `security/egress.py:1-10,31-34,95-124,339+`；`live_controller.py:43,199-204` |
| 可信 Controller | inspect-only；即使授权有效仍 BLOCKED 直到外部边界部署 | `VERIFIED`（inspect-only，无 run/execute） | `security/live_controller.py:249-287` |
| LiveGate | 恒 BLOCKED；无 approve/unlock | `VERIFIED`（设计闭锁） | `security/gates.py:63-86`；`scripts/run_live.sh` exit 3；`cli.py:95-101`；`dsh_adapter.py:101-110` |
| Candidate Runtime/容器 | `--network none`、只读、非 root、无宿主 home/socket、无 Key | `VERIFIED`（no-key 范围 L2） | `security/docker_runner.py:49-80`；旧 E5 no-key 报告 |
| Budget broker/ledger | 固定 scope、reserve-before-dispatch、未知保守、无 reset/refund | `VERIFIED`（synthetic/offline 范围） | `docs/BUDGET_BROKER.md`；`config/dsh/target-broker-policy.json` |
| 外部 Watchdog | 独立进程、deadline、进程树 kill、absence、人工 Kill Switch | `PARTIAL`（本机 no-key 演练；真实服务未部署） | `security/watchdog.py:44-110,156-360`；`live_controller.py:66-70` |
| DSH target profile | 真实 provider 路由 + 工具/compaction/upload 控制 | **无官方真实 route**：`llm-deepseek` disabled；仅 synthetic `offline-test-only/fixture-v1`；OpenCode Go 仅 STATIC-ONLY | `config/dsh/target-runtime.patch.yml:4-57`；`target-runtime-opencode-go.patch.yml:1-16` |
| 观测（request lifecycle/recovery） | 请求层 vs dispatch 层分离；first cause 保留；未知不重发 | `VERIFIED`（L1 代码 + G4-R 原始文件独立解析；L2 未复跑） | `bridge/request_lifecycle.py:52-75`；`bridge/recovery_diagnostics.py:38-51,66-117`；`bridge/controller.py:69-80` |

**默认结论**：§10 全部步骤完成 + 维护者仓库外签署前，不得声称“已部署 / E5 Full PASS / G5 已获批 / G4-H1 通过”。

### 1.1 旧 G4-H0 文档与实际 G4-R 代码的差异（必读；旧文档不自动适用于 A-NEXT）

| # | 旧 G4-H0 文档声称（`work/m0-g4h0:docs/g4h0/`） | G4-R 实际代码/评审（本工作树） | 处置 |
|---|---|---|---|
| X-01 | 单次消费用 `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` 落 use record（旧 Runbook §4.3） | `authorization.py:988-1097`：同目录 temp（O_EXCL 0600）→ 写完整 body → fsync 文件 → `os.link` **no-replace** → fsync 目录；**无 direct-final 回退** | 旧描述作废；§4/§5 按新机制 |
| X-02 | P2-03（并发消费错误码竞态）未修复，不得写并发 PASS（旧 Runbook §12 U-09） | G4-R R-REV2 Reviewer 自建探针 PASS（10 轮×4线程/10 轮×3进程/跨 epoch/8 类腐坏/crash/dir-fsync-EIO/temp 上限/link 不可用）；P2-03 取证已 CLOSED（G4-R 的 P2-03 是 collection 缺陷，与旧 P2-03 ID 冲突） | 旧 ID 不再使用；并发模块级证据以 `REVIEW_G4R_INDEPENDENT` §2 为准 |
| X-03 | 未提及目录 fsync 失败语义 | 新码有 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`：link 后 dir fsync 失败 → fail-closed 拒绝、use 已花、不得发送、后续判 replay；**当前无 Controller 消费方**（G4-R 观察-2） | §4.2/§4.3：接线时必须映射“不确定/不发送”+补测 |
| X-04 | 旧包只覆盖“模块级”单次消费；未给 run-level admission 设计 | P2-02 `OPEN`：production `src/` 无 `consume_execution_authorization` 调用方（仅 scripts/tests）；R-REV3 L2/端到端 `UNVERIFIED` | §4 新增 run-level admission 设计 + BLK-07 |
| X-05 | 旧 `HUMAN_DECISIONS.md` 用 `HD-01..HD-20`；G4-F Review 用 `F-xx`/`P2-xx` | G4-R 人类交接用 `D-01..D-13`；A-NEXT 新增 `D-14..D-22` | 本包 Handoff §1/§2 统一 canonical ID；旧 ID 仅历史引用 |
| X-06 | 旧 Runbook 的 LiveGate 说明基于 G4-F errata（P2-07 reasons 1/4） | `gates.py:63-86` 当前 reasons 集合：`EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`、`LIVE_NOT_EXPLICITLY_REQUESTED`、`BASELINE_EVIDENCE_MISSING`、`BASELINE_OR_CONFIGURATION_CHANGED`、`ACTUAL_TOOL_REGISTRY_NOT_APPROVED`、`SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED`；`live_controller.py:66-70` 另有 5 项 `EXTERNAL_*` 恒 BLOCKED | §1 表按当前 reasons；不得沿用旧 reason 计数/文案 |
| X-07 | 旧 Runbook 未提 G4-R 观测模块 | `bridge/request_lifecycle.py`（`m0.g4r.request-lifecycle.v1`，6 事件）、`bridge/recovery_diagnostics.py`（`m0.g4r.recovery-diagnostic.v1`，4 动作、first-cause 封闭枚举）、`bridge/controller.py`（synthetic route、`SYNTHETIC_FIXTURE_ONLY=True`） | §4.3；证据采集 §12 增加这两类 JSONL |
| X-08 | 旧 Runbook 对 egress 只写“固定 endpoint/白名单”通用要求 | 当前 `egress.py:31-34,101-124` 仍是**第三方** `opencode.ai` allowlist；`live_controller.py:43,199-204` 以此校验 approved route；默认设置却是官方 `settings.py:5-6` | **BLK-01**：D-15/D-16 先决；§7.2 |


## 2. 角色与职责（RACI）

| 角色 | 可以做 | 不可以做 |
|---|---|---|
| 项目维护者（人类） | 冻结/签核、批准风险、创建并离线保管信任根私钥、注入真实 Key、授权单次 G5、执行 Kill Switch | 把 Agent Markdown/Packet/自签 JSON 当授权 |
| 独立 Reviewer（未参与实现） | 从冻结 SHA + 清洁 Stage 独立复算/重跑负例，出 PASS/PARTIAL/FAIL/BLOCKED | 用 Owner 文字代替复验；代签 |
| 受信 Operator（人类） | 在独立 OS 身份部署 Controller/Broker/Egress/Watchdog、采证、执行 Runbook | 读取/复制候选可写域 Key；跳过 fail-closed 点 |
| A-Lead（Agent） | 协调、范围审计、审核提交/证据、触发 STOP | 直接部署/签名/注入 Key；代写 APPROVED |
| A-Implementer（Agent） | 在授权工作树写代码/测试/文档 | 打开 LiveGate、改 `run_live.sh`、持有真实 Key |

## 3. 部署前置工件（全部 HUMAN_REQUIRED / DESIGN_PENDING_HUMAN）

| # | 前置工件 | 来源 | 缺失处置 |
|---|---|---|---|
| P-1 | 冻结发布清单：Git SHA + 5 绑定根 + 完整文件/依赖/镜像/工具/route/预算/policy 快照 | A-NEXT A-PR0/A-PR4；G4-R Packet v2 | STOP |
| P-2 | G4-R 独立 Review + append-only 勘误（裁定/REV 状态/D-01..D-13） | `REVIEW_G4R_INDEPENDENT.md`、`M0_G4R_REVIEW_ERRATA.md` | STOP |
| P-3 | A-NEXT 文档包：Human Handoff/Provider/Price/Runbook（本包）+ Reviewer 指派 | 本包 4 文件；D-20 | 真实计费步骤 BLOCKED |
| P-4 | **P2-01/P2-02 人类处置 + Fake-only 接线证据** | D-14；A-NEXT A1/A2 | G4-H1 前 BLOCKED |
| P-5 | **目标路由 + egress allowlist 统一签核** | D-15/D-16 | G4-H1 BLOCKED |
| P-6 | **官方价格/usage 快照重核 + usage mapping v2** | D-17/D-18 | G5 BLOCKED |
| P-7 | 供应商账户/Key 作用域/额度/撤销路径 Console 快照（UTC/URL） | 维护者 | 真实出站 BLOCKED |
| P-8 | 仓库外证据根（root 所有、权限受限、持久、远离候选可写域） | 维护者 | 不得开始任何部署步骤 |
| P-9 | E5-PreLive Full 检查清单与独立复核结论 | 旧 `E5_PRELIVE_FULL_CHECKLIST.md`（只读参考）+ 人类部署 | E5-Full 保持 BLOCKED |

## 4. 人类 Run Admission 与单次授权接线（A-NEXT 核心设计；本轮只 Fake-only）

> 目标：把模块级 `consume_execution_authorization()` 变成**真实 Run 的唯一一次性授权入口**，且不新增任何 Live allow path。

### 4.1 执行时序（必须按序，任何失败 → 不进入 Reserve）

```
受信 Launcher（仓库外，人类部署）
  1) 验签/绑定：load_execution_authorization() + binding_drift("pre_start"/"pre_reserve"/"pre_dispatch")
  2) trusted file/授权有效期/撤销检查（load 内含；失败 → 拒绝）
  3) run_epoch 校验（`authorization.py:1001` 格式；非法 → RUN_EPOCH_INVALID）
  4) consume_execution_authorization(use_log_dir, run_epoch, ...)  ← **恰一次**
       - 成功：返回 AuthorizationUse（authorization_id/run_epoch/consumed_utc/record_path）
       - loser：AUTHORIZATION_REPLAYED / AUTHORIZATION_EPOCH_MISMATCH
       - dir fsync 失败：AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN（**已消费、不得发送**）
  5) 生成 Run Admission token（仅受信 principal；绑定 run_id/epoch/授权摘要/闭包 SHA）
  6) 进入受限 Broker Reserve/Claim/Fake Dispatch；每个 dispatch 校验 admission token
```

### 4.2 不可妥协点

1. **run-level 消费，不是每 dispatch 消费**：一次授权可预留多次已签预算内合法 calls；不得把 run-epoch 与 business call id 混淆（`authorization.py:795-800,988-1001`）。
2. **消费前失败 = 0 Reserve / 0 Fake / 0 new attempt**；消费后失败（含 durability unknown）不得发送、不得重试，保留 PENDING/不确定并人工复核。
3. **AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN 无 Controller 消费方**（G4-R 观察-2）：接线时必须映射为“不确定/不发送”，并补测试。
4. **P2-01 未修**：`_read_use_record` 尚不校验 body `authorization_id` 与路径 digest 对应（`authorization.py:802-848`）；接线前须 FIX 或明确接受审计不可区分风险。
5. **P2-02 未接线**：production `src/` 无调用方（仅 `scripts/g4r/r1_independent_probe.py`、`scripts/g4/e5_probe.py`、tests）；本 Runbook 不得把模块级 PASS 当端到端 PASS。
6. **admission token ≠ 人类授权**：它只能由受信 Launcher/Controller 生成；跨 Run 不可复用；候选不可生成/验证。
7. 本轮只允许 **测试专用/无 Key** 的 Trusted Admission harness（受保护临时签名 fixture + Fake Broker）；系统 `LiveGate` 始终 BLOCKED。

### 4.3 观测（G4-R 已提供）

- `bridge/request_lifecycle.py`（schema `m0.g4r.request-lifecycle.v1`）：事件 `received`/`protocol_rejected`/`cancel_before_controller`/`deadline_before_controller`/`controller_entered`/`failed_before_reserve`；pre-Controller 事件 `dispatch_seq=null`、`reserved=false`。
- `bridge/recovery_diagnostics.py`（schema `m0.g4r.recovery-diagnostic.v1`）：动作 `MARK_SETTLED`/`MARK_WORST_CASE`/`MARK_SETTLEMENT_UNCERTAIN`/`SKIP_ALREADY_TERMINAL`；仅 `RUN_AUTHORIZATION_REVOKED` 与 `REVOKED_PRE_SEND:` 前缀可保留为 first cause；Broker `OK/FAILED` 终态权威。
- `bridge/controller.py`：synthetic route `offline-test-only-g3b/fixture-bridge-v1`，`SYNTHETIC_FIXTURE_ONLY=True`，`ALLOWED_PURPOSES={None,"conversation"}`；title/compaction/judge 在 Reserve 前被拒（F2 语义）。

## 5. 人类信任根：Ed25519 签名 / 注册 / 轮换 / 撤销

### 5.1 密钥材料与职责分界

- 维护者生成 Ed25519 密钥对：**私钥离线保管**（硬件令牌/离线机器/密封介质，至少两人分管或等同控制），仅用于签 `ExecutionAuthorization`；公钥写入仓库外 `trusted-keys.json`。
- Controller 只持有公钥、只做 `verify`/`is_valid_public_key`；生产 `src/` 无签名路径、无 seed 字段（`authorization.py:289-350,450-470`；`ed25519.py`）。
- **测试种子不得成为正式根**：`tests/integration/g4_a/g4a_support.py` 的 `TEST_ONLY_` 合成种子仅测试进程内存；禁止写入 `trusted-keys.json`/仓库/Stage/Packet/日志；正式/测试 key_id 命名空间必须区分。
- 旧 G4-H0 Runbook §4 的签名/注册/轮换/撤销流程仍适用；本 A-NEXT 仅补充：**签署对象必须绑定 A-NEXT 的 canonical 文档/实现 SHA 与本文件 §9 发布清单**。

### 5.2 注册表/撤销/审批文件（仓库外、只读）

| 文件 | 目标要求 | 代码侧现状 |
|---|---|---|
| `trusted-keys.json` | 仓库外绝对路径、非 symlink、普通文件、0<size≤16 KiB；目录 owner 非候选 uid 且非 group/other 可写 | `authorization.py:203-252,450-470`（`VERIFIED` L1 负例） |
| `revocations.json` | 同上（≤64 KiB）；按 key_id/authorization_id 撤销 | `authorization.py:468-477,686-690`（逻辑层 `VERIFIED`；真实撤销链 `BLOCKED`） |
| `execution-authorization.json` | 仓库外、维护者签名、单次消费、5 个绑定根、≤24h、签发≤7 天前、零 skew | `authorization.py:333-700`（离线校验器 `VERIFIED`；真实签名 `BLOCKED`） |
| use-log 目录 | root 所有、非候选可写；单次消费记录 0600、不可改 | `authorization.py:872-1097`（原子发布 L1 PASS；目录权限部署 `DESIGN_PENDING_HUMAN`） |

### 5.3 签发流程 SIGN-1..SIGN-6（全部 HUMAN_REQUIRED）

1. **SIGN-1** 从清洁 Stage 复算 5 个绑定根/完整文件清单，人工与 Packet 对照；任一不符 → STOP。
2. **SIGN-2** 核对 route/provider/model/endpoint/method/path、token 上限、工具白名单与发布清单一致；**当前 D-15/D-16 未签 ⇒ 不签**。
3. **SIGN-3** 核对预算/次数（§7）、有效期（≤24h，建议更短）、单次消费、撤销方式；缺一不签。
4. **SIGN-4** 核对 P2-01/P2-02 处置、usage mapping v2、价格快照重核（D-14/D-17/D-18）；缺一不签。
5. **SIGN-5** 核对 E5-PreLive Full 前置与独立复核结论（当前 `BLOCKED`）。
6. **SIGN-6** 维护者在仓库外签发授权并登记编号；Agent 只可起草模板，不得代签。

## 6. 独立 Credential Broker（真实 Key 边界）

沿用旧 G4-H0 Runbook §5 的 KB-1..KB-8，并适配 A-NEXT：

- 现有 `security/credential_boundary.py` 仅提供候选 env allowlist（`CANDIDATE_ENV_ALLOWLIST`）、secret 丢弃/脱敏（`scrub_candidate_env`/`redact_secrets`/`assert_log_clean`）、mount/argv 校验；**不是** Key Broker（`credential_boundary.py:28,90-128,137-215`）。
- 现有 bookkeeping broker（`docs/BUDGET_BROKER.md:3-17`）明确不是 Key proxy / 人类授权 broker / OS sandbox / provider usage authenticator；`dispatch_allowed` 只表示首次记账。
- **真实 Key 从未存在**；候选容器必须保持 `--network none`、`--read-only`、`--cap-drop=ALL`、`no-new-privileges`、`--user=65534:65534`、`--unsetenv-all`、`--http-proxy=false`（`docker_runner.py:49-80`）。
- KB-1..KB-8 的状态：KB-1/2/3 **BLOCKED（人类）**；KB-5/KB-6 假 Key 负例为 no-key `PARTIAL` 证据；KB-8 真实 usage/账单对账 `UNVERIFIED`（见本包 PRICE 文档）。

## 7. 独立 Egress（唯一可发送路径）——含 BLK-01 未解

### 7.1 必要条件（全部满足才可 dispatch）

1. 固定 route/provider/model 与冻结 `ProviderRouteContract` 逐字段相等；real route 在人工核验前恒 `BLOCKED_REQUIRES_HUMAN_VERIFICATION`。
2. 固定 method（仅 POST）+ **精确 host/port/path**；真实出站只经受控 Egress/Proxy。
3. 持久预留：先 broker `reserve` 成功（有 ack）再 claim；重放/无 ack 不 dispatch。
4. 正确 Claim：`dispatch_allowed=true`、Claim 与 Prepared 摘要一致；未 Claim 发送 = `DISPATCH_PERMISSION_REQUIRED`。
5. 请求摘要：发送前重算 payload SHA/`prepared_digest`/`payload_length`；发送后 Receipt `raw_sha256` 必须等于 payload digest。
6. 发送前 `binding_drift("pre_dispatch", approved, observed)`；任何 `<ROOT>_MISMATCH` → 不发送。
7. 工具白名单 `skill_lookup` 且与实际 registry 一致；DSH merged registry 仍 `UNVERIFIED`（B03/E5-P04）。

### 7.2 **BLK-01：默认路由与 egress allowlist 不一致（必须 D-15/D-16 先决）**

| 声明处 | 值 |
|---|---|
| `src/autoteacher_m0/settings.py:5-6` | `PRIMARY_ROUTE="deepseek-official"`、`MODEL="deepseek-flash"`（官方，未被 egress 接受） |
| `config/models.example.yaml` / `docs/ROUTE_DECISION.md` | 官方主路由设计默认，`approval: PENDING_INDEPENDENT_HUMAN_REVIEW` |
| `src/autoteacher_m0/security/egress.py:31-34,101-124` | host `opencode.ai`、port 443、path 前缀 `/inference/go/`、approved route `("opencode-go","deepseek-v4.1-flash")`（第三方） |
| `src/autoteacher_m0/security/live_controller.py:43,199-204` | `EXPECTED_EGRESS_POLICY = EgressPolicy()`（即上述 opencode 白名单）；approved route 不在其中 → `ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST` |

> 结论：当前代码**不能**用默认官方路由通过 Controller 的 route 校验；第三方白名单也不是官方契约。
> 在 D-15/D-16 签核并统一 allowlist 前，任何“真实出站已准备”说法都不成立。若选官方路由，需改 allowlist 为
> `api.deepseek.com:443` + 精确 `/chat/completions`（2026-11-19 研究快照，须当日重核）并重跑受影响测试；
> 若选 OpenCode Go，则必须承认第三方契约，不能记官方 PASS。

### 7.3 TLS/DNS/Proxy/Redirect/Retry（全部 fail-closed，`DESIGN_PENDING_HUMAN`）

TLS 证书链/主机名校验且不可关闭；DNS 固定解析/受控 resolver、拒绝 hosts 注入/重绑定；禁止通用 URL 代理；
3xx 一律拒绝或仅允许显式批准；`maxRetries=0`，429/5xx/timeout/disconnect 不自动重试；未知结果 → `BILLABLE_UNKNOWN` + worst-case held；
只允许一条受控 transport，禁止 SDK fallback/备用 provider/Files 二次 POST。当前 `egress.py` 仅描述符级，**不是**真实代理。

## 8. 预算与次数（M0 工程目标，不是供应商硬封顶）

- 值：soft `$3.00` / hard `$10.00` / soft-call `$0.10` / hard-call `$0.20` / `max_calls=50` / `max_input_tokens=2,500,000` / `max_output_tokens=600,000` / `max_steps=8` / `max_retries_per_task=1`；guard `maxProviderRetries=0`。
  证据：`config/budgets.yaml:1-13`；`security/live_controller.py:53-58`；`config/dsh/target-runtime.patch.yml:42-45`；`config/dsh/target-broker-policy.json:7-16`。
- **语义限定**：全部是**本地工程目标**；没有供应商侧强制机制时不得称“绝对硬封顶”，不得承诺“不会超过 $10”；`live_pricing_snapshot: REQUIRED_UNVERIFIED`（`config/budgets.yaml:11`）。
- 未知/部分 usage、5xx、超时、断连一律 worst-case 占用，不当作 0；G5 首次建议 ≤3 次请求（最终值由人类授权逐项写明）。
- 预留先于发送；失败/崩溃 pending 不自动退款；`dispatch_allowed` 不是人类授权；预算拒绝会持久 latch 该 scope。

## 9. Watchdog、资源上限与 Kill Switch

- `security/watchdog.py:44-110,156-360`：`WatchdogPolicy`（总 deadline/max_steps/max_dispatch_attempts）、`kill_process_tree`、`confirm_container_absence`/`confirm_process_absence`/`confirm_path_absence`、`ExternalWatchdog`（latch、不重试）。
- 超时/超 step/超 dispatch → latch → kill 进程组 + `/proc` 后代树（SIGTERM→宽限→SIGKILL）→ survivors 为空；容器清理必须**观测 absence**；异常 → `PendingConservative(retry_allowed=False, worst_case_reserved=True)`。
- 真实外部 Watchdog 服务未部署 → `live_controller.py:66-70` 恒 `EXTERNAL_WATCHDOG_NOT_DEPLOYED_REHEARSAL_ONLY`。人工 Kill Switch KILL-1..KILL-5 沿用旧 G4-H0 Runbook §8.4；演练必须假 Key/合成 fixture 并独立复核。
- 残余：P2-RUN-IDENTITY/USERNS/DISK、host `RLIMIT_NPROC`、F4 candidate-crash + live Controller 组合仍 `UNVERIFIED`/待签收（D-05/D-07）。

## 10. 发布与审批（可追溯、变更即失效、独立签核）

1. **发布输入**：Git SHA（impl/docs/base）、5 个绑定根（code/lock/runtime/plugin/merged_profile）、Stage/rootfs/deps 身份、DSH runtime/插件版本、工具/配置清单、完整文件清单+不可变副本。
2. **证据卫生**：Packet 只读不可变；新更正 append-only/新 Packet；禁止写入旧证据路径（D-10 事件）；**禁止直接对冻结 rootfs `--rootfs`**，OCI/L2 用 `cp -a` 可写副本 + 独占窗口串行（D-08）。
3. **变更即失效**：代码/依赖/镜像/rootfs/profile/工具/route/预算/policy/价格快照/Controller 常量任一变化 → 重新独立复核+重新签名；运行期由 `pre_start`/`pre_reserve`/`pre_dispatch` 三检查点发现漂移（`authorization.py:103,439-447`）。
4. **独立签核**：实现方冻结并提交审核请求 → 独立 Reviewer 复跑/复算（不得用 Owner 结论代替）→ 维护者按 `HUMAN_SIGNOFF_TEMPLATE` 逐项核对并签署仓库外授权。
5. **未通过项不得以其他项通过为由放行**；H/I（人类/整合）行不得由 Agent 改 PASS。

## 11. 分步部署流程 S0–S12（当前全部 NOT_RUN / BLOCKED / DESIGN_PENDING_HUMAN）

| 步骤 | 内容 | 负责人 | 当前状态 |
|---|---|---|---|
| S0 | 核对 HEAD/基线/工作区 clean；A-NEXT 交付物齐全（§3） | A-Lead+维护者 | `NOT_RUN` |
| S1 | 独立复核发布清单/5 绑定根（清洁 Stage 复算） | Reviewer | `NOT_RUN` |
| S2 | 构建/校验 frozen Stage、rootfs、deps、工具清单；可写副本政策 | Operator | `NOT_RUN` |
| S3 | 部署人类信任根（公钥注册/撤销/审批目录，root 只读、仓库外） | 维护者 | `DESIGN_PENDING_HUMAN` |
| S4 | 部署 Credential Broker + 低额度可撤销 Key | 维护者+Operator | `BLOCKED` |
| S5 | 部署独立 Egress（先 D-15/D-16 统一 route+allowlist；TLS/DNS/proxy/redirect/retry fail-closed） | Operator | `BLOCKED` |
| S6 | 部署外部 Watchdog + Kill Switch 演练（假 Key/合成 fixture） | Operator | `PARTIAL`（仅 no-key 演练） |
| S7 | 初始化固定 scope broker/ledger，验证漂移拒绝/重启保留 | Operator | `VERIFIED`（offline 范围） |
| S8 | A-NEXT 修复验证（P2-01/P2-02 Fake-only、R-REV6/L2） | A-NEXT Owner+Reviewer | `NOT_RUN`（P2 仍 OPEN） |
| S9 | 生成发布 Packet/证据归档；独立签核；维护者仓库外授权 | Reviewer+维护者 | `DESIGN_PENDING_HUMAN` |
| S10 | 签名前预检：`run_live.sh` exit 3、CLI `--live` exit 3、Adapter `SECURITY_BLOCKED`、LiveGate BLOCKED；0 Key/0 真实 HTTP 扫描 | Operator+Reviewer | `VERIFIED`（no-key 基线） |
| S11 | **G5 首次真实有界调用**（≤3 请求、极短有效期、无工具/文件、固定 prompt、`maxRetries=0`、记录 request id/usage） | 维护者授权+Operator | `BLOCKED`（未授权） |
| S12 | 对账/归档/撤销/STOP；出具限定范围结论 | Operator+维护者 | `NOT_RUN` |

**部署完成 ≠ Live 批准**：S11 成功最多证明“该配置在该次有界授权下可连通并可追踪 usage”；E5-Full、G4-H1/H2、G5 后续、G6、M0 GO 均需新的独立证据与人类决定。

## 12. 证据采集与归档规范

- 仓库外证据根 `<TRUSTED_DEPLOY_ROOT>/evidence/<run-id>/`：root 所有、权限受限、持久、append-only；`artifacts/` 是本机 gitignored 中间产物，不能作为最终部署证据。
- 每次运行至少：`argv/`、`logs/`、`utc-start/end`、`exit-code`、`identity/`（SHA/哈希/镜像 digest）、`journal/`、`ledger-copy/`、`absence/`、`provider/`（request id/usage 脱敏）、`request-lifecycle.jsonl`、`recovery-diagnostics.jsonl`、`manifest.json`、`evidence.sha256`。
- 禁止落入证据：真实 Key/Secret、Authorization header 原文、个人/学生数据、未脱敏 Provider 响应；示例凭据只能是明显占位符。
- 脱敏：`redact_secrets()`/`assert_log_clean()` 覆盖已知值与 `oc_sk_`/`sk-`/`Bearer` 模式；扫描器正控必须命中，否则“0 命中”无效（`credential_boundary.py:118-128`）。
- 观测关联：`prepared_digest == claim.request_digest` 与 `payload_digest == receipt.raw_sha256` 必须分别绑定，不得混为同一 digest；每 attempt 记录 `call_id`/`attempt_ordinal`。

## 13. 未实现 / 未验证总表（部署前必须逐项处置）

| ID | 项 | 现状（本工作树） | 关闭条件 |
|---|---|---|---|
| U-01 | 人类 Ed25519 信任根/注册/轮换/撤销部署 | `BLOCKED` | S3 + 独立复核 |
| U-02 | 独立 Credential Broker + 真实 Key | `BLOCKED` | S4 + 负例证据 |
| U-03 | 独立 Egress（真实 proxy/TLS/DNS/redirect/retry） | `BLOCKED`；且 BLK-01 route 冲突未解 | S5 + D-15/D-16 |
| U-04 | 真实 Provider wire/usage/账单/价格 | `UNVERIFIED`（2026-11-19 研究快照，未真实调用） | G5 当日重采 + 对账（D-17/D-22） |
| U-05 | 供应商侧硬额度/停用/降级计划 | `UNVERIFIED` | Console 证据或明示接受 |
| U-06 | DSH merged Registry / E5-P04 / B03 | `UNVERIFIED` | 权威导出或人类签收残余（D-04） |
| U-07 | P2-01 body id 交叉校验 | `OPEN`（`authorization.py:802-848`） | D-14 FIX + Reviewer |
| U-08 | P2-02 consume 端到端接线 / run admission | `OPEN`（`authorization.py:988` 无 production caller） | D-14 Fake-only 接线 + L2 复验 |
| U-09 | `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 消费方映射 | 无 Controller 消费方（G4-R 观察-2） | 接线映射“不确定/不发送”+ 测试 |
| U-10 | R-REV6 真实双 Principal DSH two-turn/Replay/usage 对账 | `NOT_RUN` | 独立 L2 取证（D-07） |
| U-11 | OCI deselect 43→69 人类签收 | 未签收（D-09） | 逐项签收原因/列表/总数 |
| U-12 | 环境漂移/junit 误覆盖事件确认 | 已恢复并记录（D-08/D-10）；不得写全程 NO_DRIFT | 维护者确认 |
| U-13 | P2-RUN-IDENTITY/USERNS/DISK | 未签收（D-05） | 签收或加固 |
| U-14 | F4-R1/F5-R6/F1-R4/F2-R5/B07 残余 | 未签收（D-06） | 补测或明示接受 |
| U-15 | R5-01..03（F4-06 candidate crash + live Controller） | `UNVERIFIED`（D-07） | 可控注入补测或登记残余 |
| U-16 | test-only crash/delay hooks、撤销链签名 | 仍存在（D-13） | 移除/隔离/签名或明示接受 |
| U-17 | 真实人类审批与独立 Reviewer 指派 | `NOT_ASSIGNED`（D-20） | 指派并完成复核 |
| U-18 | LiveGate/入口现状 | 恒 BLOCKED（`gates.py:63-86`；`run_live.sh` exit 3；CLI/Adapter BLOCKED） | **保持，不改** |

## 14. 本文件“没有做什么”

- 没有修改 `src/`、`scripts/`、`LiveGate`、`run_live.sh`、DSH 配置、冻结 Packet/Review/证据字节。
- 没有生成/读取真实 Key、没有发起真实 HTTP/TLS、没有部署任何组件、没有执行 G4-H1/H2 或 G5。
- 没有代替维护者签核、没有把 Markdown/Packet 当授权、没有声称 E5 Full / G4-R/G4-H1 PASS / M0 GO。
- 没有提供真实可执行命令；§11 命令列是受控占位，需维护者在受信环境按独立审批准备。

## 15. STOP

本 Runbook 执行到 **S9 维护者签名前一步**必须 STOP；S11 需要新的、单独的人类签署 G5 单次授权。
当前默认状态：**未授权、未部署、未调用、LiveGate=BLOCKED、M0=DECISION_PENDING**。

## 16. 集成阶段 append-only 追加：环境事件与防再发（不覆盖上文）

> 本节为 append-only 追加；本 Runbook 仍是**未执行设计稿**，不构成部署/授权。

### 16.1 INCIDENT_20261121（环境事件）

- 2026-11-20T19:53Z 前后 repo `artifacts/` 被误删，随后自哈希验证副本恢复：backup tar sha256 `11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42`；恢复后 rootfs canonical `25491e45…`、deps canonical `e07729d7…`（与冻结声明一致）。
- **v1 Packet 原始字节 LOST**（不可再独立核验）；v2 Packet 仅历史引用且未修改字节。事故与恢复详见 `docs/A_NEXT_ENVIRONMENT_INCIDENT.md`；**不得**声明“全程 NO_DRIFT/证据完整”。

### 16.2 部署/测试前强制防再发检查（P0）

1. **永远禁止** `podman run --rootfs <frozen rootfs>`；冻结 rootfs 只能被只读哈希/·识别。所有容器运行使用 `cp -a` 的工作副本（运行后删除）。
2. 预检/运行守卫：`scripts/a_next/oci_guard.py`（拒绝 frozen `--rootfs`、输出目录预检、单 writer、T0/T1 漂移 STOP、env 脱敏）、`scripts/a_next/rootfs_guard.py`（权限/只读挂载/测试 uid 不可写）、`scripts/a_next/ci_guard.py`（分支来源/受保护文件/H0 cherry-pick/未授权 merge）。
3. 每批次仅一个 writer + 全新独占 evidence 目录（不得复用旧 evidence/JUnit 路径）；批前/批后 frozen rootfs canonical SHA 对比（`25491e45…`），漂移即 STOP 并保全证据。
4. 不静默扩大 OCI deselect：legacy 43 + explicit `tests/integration/g4r_auth`（26，环境类）必须在矩阵/报告登记原因、host 覆盖与缺失真 OCI 用例，并由 Reviewer 签收。
5. 新证据/新 Packet 用**新身份**（如 `review-packet-a-next-v3-<impl_sha>`），不覆盖 v1/v2 与旧 Review 字节；最终 Packet 必须内嵌 INCIDENT_20261121 披露与恢复 provenance。
6. 任何 `artifacts/` 删除/移动前先停所有容器与测试 writer，并确认已有哈希验证备份。

### 16.3 不改变的结论

- 本 Runbook 仍未执行；人类信任根/Key Broker/Egress/Watchdog/E5-Full/G5 均未部署、未授权；`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING` 不变。
- 集成阶段 Host/Node 证据、A1/A2 代码合并**不构成**部署批准或人类签核。

### 16.4 P2-ENV-1 追加：禁止经 symlink 间接把 frozen rootfs 用作 --rootfs

- **事件**：集成交付工作树中 `artifacts/security` 曾为 symlink → 冻结 artifacts；Stage builder 内部以 `artifacts/security/rootfs` 拼 `--rootfs`，实际 resolve 到冻结 rootfs（Lead 20:57Z 检测；frozen hash 未变 `25491e45…`，但流程违规）。已删除 symlink 并用真实可写副本替换 `artifacts/security`/`artifacts/foundation`；Stage 在副本上重建（`stage-20261120T210101Z`）。
- **P0 检查（每次容器/Stage 运行前）**：
  1. `readlink -f <rootfs-path>` 必须**不**落在 `/root/Autonomous Teacher/artifacts/`；`realpath` 后仍须是本次运行专用的 work copy。
  2. 禁止 artifacts 目录存在指向冻结树的 symlink 后再交给 builder/runner；构建工具内部路径也要审计（不能只看外层 argv）。
  3. 冻结 rootfs 只读 hash T0/T1 每批记录；工作副本起跑前 hash 应等于 canonical（`25491e45…`），跑后删除；`podman ps -a` 收尾空。
  4. 任何 `--rootfs` 参数须由显式构造 argv 给出（不要用旧模板替换）；记录 argv/UTC/exit/deselect。
- **披露要求**：失效尝试（frozen-symlink、旧 stage 模板等）必须标 INVALID 且证据不计；不得写“全程只用副本/无事件”。
