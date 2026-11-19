# 受信部署 Runbook — G4-H0 无 Key 准入准备（设计稿，未执行）

- **文档性质**：`DESIGN_PENDING_HUMAN`。本文件是**面向维护者/受信 Operator 的人工执行手册**，不是授权凭据、
  不是审批、不是部署证据，也**不是** G4-H1/H2 或 G5 已执行的证明。当前仓库内**没有**真实信任根、真实 Key、
  真实 Egress、真实 Watchdog 部署，也没有任何真实 Provider 调用。
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`（本工作树起点）；文中 `path:line` 行号均以该基线为准。
- **依据**：执行方案（仓库外只读副本 `Autonomous_Teacher_M0_M1_Parallel_Execution_Plan_v1.0.md`）§4 A3、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、
  `docs/SECURITY_APPROVALS.md`、`docs/BUDGET_BROKER.md`、`docs/M0_G4_A_AUTHORITY_CONTRACT.md`、
  `docs/M0_G4_C_EGRESS_CONTRACT.md`、`docs/M0_G4_D_E5_NO_KEY_REPORT.md`、`docs/M0_G4F_REVIEW_ERRATA.md`、
  `docs/M0_G4_HUMAN_HANDOFF.md`、`docs/M0_G4F_HUMAN_HANDOFF.md`。
- **当前不变量**（不得因本文件存在而改变）：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
  `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`
  （`docs/M0_G4F_REVIEW_ERRATA.md:89-98`）。

> **一句话**：本 Runbook 把“真实部署需要什么、谁来做、留下什么证据、哪里必须失败关闭”写成可审计步骤；
> 它只能执行到**维护者签名之前一步**。签名、Key 注入、真实出站与 G5 均属人类专属动作，不在 Agent 授权内。

---

## 0. 强制规则（P0，任何一步违反即 STOP）

| # | 规则 | 依据 |
|---|---|---|
| R1 | 唯一授权介质是维护者在**仓库外**生成的 `at-m0/execution-authorization/v1` Ed25519 签名文件。Markdown、仓库内 JSON、环境变量、`--live` flag、测试种子、自签文件**一律不能**解锁任何 Live 路径。 | `src/autoteacher_m0/security/gates.py:1-6,63-86`；`scripts/run_live.sh:1-5`；`docs/SECURITY_APPROVALS.md:3-10` |
| R2 | 本文件**不提供**任何可执行 Live 开关或真实 Key 注入命令。所有路径均为 `<TRUSTED_DEPLOY_ROOT>` 占位；真实命令由维护者在受信环境准备并复核。 | 本文件 §3、§10 |
| R3 | 失败关闭：缺证据 = 失败；未知 = 最坏情况；不自动重试计费 attempt；不 fallback 到备用路由；不把“看起来成功”当证据。 | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:27-36,121-145`；`docs/M0_G4_C_EGRESS_CONTRACT.md:23-35` |
| R4 | 每一步都必须记录：负责人、输入 SHA、精确 argv、UTC 起止、exit code、原始日志、证据 SHA-256。**没有证据 = `NOT_RUN`**，不得用文字结论代替。 | 执行方案 §7；`docs/M0_G4F_REVIEW_ERRATA.md:287-293` |
| R5 | 任一代码/依赖/配置/profile/工具清单/route/预算/policy 变化都使已签授权与本次发布**立即失效**，必须重新独立复核与重新签名。 | `docs/M0_G4_A_AUTHORITY_CONTRACT.md:178-226,247-273`；`docs/SECURITY_APPROVALS.md:55-59` |
| R6 | Agent 不得签发/代签/注入 Key/执行真实出站/删除 `LiveGate` 的 `BLOCKED`。发现真实 Key、未知网络出口、未授权发送、证据路径错位 → STOP 并保全证据。 | 执行方案 §4 关键禁止；`docs/M0_G4_HUMAN_HANDOFF.md:46-63` |

**状态标签**（全文统一，顺序即证据强度）：
`VERIFIED`（仓库内可复算证据）｜`PARTIAL`｜`UNVERIFIED`｜`NOT_RUN`｜`BLOCKED`｜
`DESIGN_PENDING_HUMAN`（设计完成、待人类执行）｜`HUMAN_REQUIRED`（只能由人类完成的动作）。

---

## 1. 部署目标形态与组件现状

目标形态（与现状严格区分；详图见 [`TRUST_BOUNDARY_DIAGRAM.md`](TRUST_BOUNDARY_DIAGRAM.md)）：

| 组件 | 目标信任属性 | 当前状态 | 设计/证据依据 |
|---|---|---|---|
| 人类签名根（Ed25519） | 私钥离线、公钥注册表与撤销列表在仓库外、Controller 只读加载 | `BLOCKED`（未部署） | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:38-60,169-179` |
| Approval 目录（授权/公钥/撤销/单次消费记录） | root 所有、只读、非候选可写、非候选 Stage | `DESIGN_PENDING_HUMAN`；代码侧拒绝逻辑 `VERIFIED`（L1/L2 负测） | `docs/M0_G4_A_AUTHORITY_CONTRACT.md:105-123,277-286` |
| 独立 Credential Broker | 真实 Key 仅存在于维护者可控可信域；候选零 Key、零直连、不可见宿主 Secret | `BLOCKED`（未部署；现仅有 bookkeeping broker） | `docs/BUDGET_BROKER.md:3-17,232-262`；`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:89-110` |
| 独立 Egress（受控发送路径） | 只有固定 model+method+endpoint + 持久预留 + 正确 Claim + 请求摘要的调用可发出 | `BLOCKED`（未部署；`egress.py` 仅描述符级原型） | `docs/M0_G4_C_EGRESS_CONTRACT.md:23-35,121-178`；`docs/BILLABLE_PATH_INVENTORY.md:24-52,66-73` |
| 可信 Controller（外部 OS 身份） | inspect-only；即使授权完全有效仍 BLOCKED，直到外部边界部署 | `DESIGN_PENDING_HUMAN`；inspect-only `VERIFIED` | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:134-145,169-179` |
| Candidate Runtime/容器 | `--network none`、只读、非 root、无宿主 home/socket、无 Key | `VERIFIED`（no-key/G4-F 范围 L2） | `docs/E5_PRELIVE_NO_KEY_REPORT.md:12-28`；`docs/M0_G4F_REVIEW_ERRATA.md:104-120` |
| Budget broker / ledger | 固定 scope、reserve-before-dispatch、未知保守占用、无 reset/refund | `VERIFIED`（synthetic/offline 范围） | `docs/BUDGET_BROKER.md:74-169,232-262,422-460` |
| 外部 Watchdog | 独立进程、deadline、进程树 kill、观测 absence、人工 Kill Switch | `PARTIAL`（no-key 演练通过；真实部署未做） | `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`；`docs/M0_G4_D_E5_NO_KEY_REPORT.md:67-121,289-298` |
| 发布 Packet / 证据目录 | 可追溯 SHA、不可变、仓库外持久、0 真实 Secret | `PARTIAL`（v1 有 P2-01/P2-02/P2-07 缺陷） | `docs/M0_G4F_REVIEW_ERRATA.md:128-166,231-259` |

**默认结论**：在 §10 全部步骤完成并由维护者按 [`HUMAN_SIGNOFF_TEMPLATE.md`](HUMAN_SIGNOFF_TEMPLATE.md)
签署之前，**不得**声称“已部署”“E5 Full PASS”“G5 已获批”。`E5_PRELIVE_FULL` 保持
`BLOCKED_PENDING_HUMAN_DEPLOYMENT`（`docs/M0_G4F_REVIEW_ERRATA.md:170-185`）。

---

## 2. 角色与职责（RACI）

| 角色 | 可以做 | 不可以做 |
|---|---|---|
| 项目维护者（人类） | 冻结/签核、批准风险、创建并离线保管信任根私钥、注入真实 Key、授权单次 G5、执行 Kill Switch | 把 Agent 生成的 Markdown/Packet/自签 JSON 当授权 |
| 独立 Reviewer（未参与实现） | 从冻结 SHA + 清洁 Stage 独立复算/重跑负例、出具 PASS/PARTIAL/BLOCKED | 用 Owner 的结论文字代替自己的复验；代签 |
| 受信 Operator（人类，可兼任维护者） | 在独立 OS 身份部署 Controller/Broker/Egress/Watchdog、采集证据、执行 Runbook 步骤 | 读取/复制候选可写域中的 Key；跳过失败关闭点 |
| A-Lead（Agent） | 协调、范围审计、审核提交与证据、触发 STOP | 直接部署/签名/注入 Key；代写 APPROVED |
| A-Implementer（Agent） | 在授权工作树写代码/测试/文档 | 打开 LiveGate、改 `run_live.sh`、持有真实 Key |

独立性要求沿用 G4-F 独立复核先例：Reviewer 不得参与被审实现、测试编写、证据生成或 Packet 构建
（`docs/M0_G4F_REVIEW_ERRATA.md:12-19`）。

---

## 3. 部署前置工件（全部 `HUMAN_REQUIRED` / `DESIGN_PENDING_HUMAN`）

本 Runbook 的输入是 A 线并行交付物与维护者决定；**任一项缺失，对应步骤为 `BLOCKED`，不得用推测补齐**：

| # | 前置工件 | 来源 | 缺失时的处置 |
|---|---|---|---|
| P-1 | 冻结发布清单：完整 Git SHA 与 5 个绑定根、完整文件清单、依赖/镜像/工具/route/预算快照 | A0/A4 交付物（`docs/g4h0/BASELINE.md`、`REVIEW_REQUEST.md` 等，按执行方案 §9 由 A 线其他任务产出） | STOP |
| P-2 | 独立 H0 Review 报告（最高 `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`） | 独立 Reviewer | STOP |
| P-3 | Provider 契约/价格/Usage/额度核验（官方来源快照 + `UNVERIFIED` 项） | A2 交付物（`PROVIDER_CONTRACT_DRAFT.md`、`PRICE_AND_USAGE_VERIFICATION.md`、`BILLABLE_PATH_INVENTORY.md`） | 真实计费步骤 BLOCKED |
| P-4 | 风险处置表（P2 八项与残余逐项 FIX/ACCEPT/BLOCK + 维护者决定栏） | A1 交付物 `docs/g4h0/RISK_DISPOSITION.md` | STOP；Agent 只能写建议、不得代签 ACCEPT |
| P-5 | E5 PreLive Full 检查清单与独立复核结论 | [`E5_PRELIVE_FULL_CHECKLIST.md`](E5_PRELIVE_FULL_CHECKLIST.md) | E5 Full 保持 BLOCKED |
| P-6 | 供应商账户/Key 作用域/额度/停用/撤销路径的 Console 快照（UTC、URL、版本） | 维护者 | 真实出站 BLOCKED |
| P-7 | 仓库外证据根目录（root 所有、权限受限、持久、远离候选可写域） | 维护者 | 不得开始任何部署步骤 |

---

## 4. 人类信任根：Ed25519 签名 / 注册 / 轮换 / 撤销

### 4.1 密钥材料与职责分界

- 维护者生成 Ed25519 密钥对：**私钥离线保管**（硬件令牌/离线机器/密封介质，至少两人分管或等同控制），
  仅用于签署 `ExecutionAuthorization`；公钥写入仓库外 `trusted-keys.json`。
- Controller 只持有公钥，只做 `verify`/`is_valid_public_key`；生产 `src/` 无签名路径、无 seed 字段
  （`docs/M0_G4_A_AUTHORITY_CONTRACT.md:64-70,344`；`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:62-87`）。
- **测试种子不得成为正式根**：`tests/integration/g4_a/g4a_support.py` 中的 `TEST_ONLY_` 合成种子仅存在于
  测试进程内存，禁止写入 `trusted-keys.json`、禁止复用为正式 key、禁止进入仓库/Stage/Packet/日志
  （`docs/M0_G4_A_AUTHORITY_CONTRACT.md:66-70`）。正式根与测试根必须在 `key_id` 命名空间上可区分
  （例如正式 `root-2026-*`，测试 `test-only-*`），并在注册表中显式拒绝测试命名空间。

### 4.2 注册表与撤销列表（仓库外、只读挂载）

| 文件 | 目标要求 | 代码侧现状 |
|---|---|---|
| `trusted-keys.json` | 仓库外绝对路径、非 symlink、普通文件、0<size≤16 KiB、目录 owner 非候选 uid 且非 group/other 可写；`key_id` 必须存在才能验签 | `VERIFIED`（L1 负例；路径边界见 `docs/M0_G4_A_AUTHORITY_CONTRACT.md:105-123`；字段语义见 `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:71-87`） |
| `revocations.json` | 同上（≤64 KiB）；按 `authorization_id`/key 状态撤销 | `VERIFIED`（逻辑层：过期/撤销拒绝，`docs/M0_G4_A_AUTHORITY_CONTRACT.md:167-171,277-286`；真实部署撤销链 `BLOCKED`） |
| `execution-authorization.json` | 由维护者签名、单次消费、绑定 5 个 root、有效期 ≤24h、签发 ≤7 天前、零 skew | `VERIFIED`（离线校验器）；真实人类签名 `BLOCKED` |

> 部署侧可另建**人类登记簿**（`key-register.md`/`custody-record.json`）记录指纹、保管人、启用/退役时间；
> 它不参与代码验签，不得冒充授权。任何扩展 `trusted-keys.json` 解析格式的行为都是代码变更，需重新审批。

### 4.3 签名流程（SIGN-1..SIGN-6；每一步 `HUMAN_REQUIRED`）

| 步骤 | 动作 | 负责人 | 证据采集 | 失败关闭点 |
|---|---|---|---|---|
| SIGN-1 | 从清洁 Stage 复算发布清单的 5 个绑定根与完整文件清单，人工逐项与 Packet 对照 | Reviewer | 复算命令+输出、UTC、diff | 任一不一致 → STOP |
| SIGN-2 | 核对 route/provider/model/endpoint/method/path、token 上限、工具白名单与 §9 发布清单逐字段一致 | 维护者 | 字段对照表 | 不一致 → 不签 |
| SIGN-3 | 核对预算与次数（§7）、有效期（≤24h，建议更短）、单次消费、撤销方式 | 维护者 + 独立复核人 | 对照表 + 复核签字 | 任一项缺失 → 不签 |
| SIGN-4 | 在离线环境用正式私钥对“除 `signature` 外字段的 canonical JSON”签名，写入仓库外授权文件 | 维护者 | 授权文件 SHA-256、key_id、签名时间 | 私钥接触网络/Agent → STOP |
| SIGN-5 | 独立复核人用**只读**方式验签并核对绑定的 5 根，记录复核意见 | 独立 Reviewer | 验签输出、复核意见 | 验签失败 → 不部署 |
| SIGN-6 | 将授权与登记簿副本归档到仓库外证据根；**不得**提交真实授权到 Git | Operator | 证据清单+hash | 真实授权进入 Git/日志 → STOP |

### 4.4 轮换（ROT-1..ROT-4）

1. **ROT-1**：新密钥对生成并登记新 `key_id`；`trusted-keys.json` 在受控时刻同时包含新旧公钥（重叠窗口）。
2. **ROT-2**：新授权只用新私钥；旧授权在 `expires` 前可继续，但不得续期/复用；重叠窗口长度由维护者设定并记录。
3. **ROT-3**：重叠期结束，从 `trusted-keys.json` 移除旧公钥 → 旧签名立即 `UNKNOWN_APPROVAL_KEY`
   （行为已由 A14 覆盖，`docs/M0_G4_A_AUTHORITY_CONTRACT.md:343`）。
4. **ROT-4**：撤销列表保留旧 `authorization_id`；所有使用记录（use record）只增不改；轮换全过程归档。
   **任何 Key 轮换都使当前发布绑定失效**，需重新走 §9.3。

### 4.5 撤销（REV-1..REV-4）

| 步骤 | 动作 | 观测点 |
|---|---|---|
| REV-1 | 在 `revocations.json` 写入目标 `authorization_id`（必要时同步撤销公钥） | 必须原子写入并记录 SHA；撤销文件缺失/不可读 → 全拒 |
| REV-2 | 触发下一次检查：`pre_start`/`pre_reserve`/`pre_dispatch` 均拒绝；已消费不产生第二次记录 | `BINDING_DRIFT`/`AUTHORIZATION_REVOKED`；参考 `docs/M0_G4_A_AUTHORITY_CONTRACT.md:277-286` |
| REV-3 | 若已有在途 attempt：保持 `ATTEMPT_STARTED`、第二次 `begin_attempt` 拒绝、无重发；未决费用保守占用 | `docs/M0_G4_D_E5_NO_KEY_REPORT.md:159-174`（D05 PARTIAL：容器内人类撤销入口尚不存在） |
| REV-4 | 证据归档：撤销前后 use-log 计数、journal、账本 pending；12h 内复核 | `docs/M0_G4F_REVIEW_ERRATA.md:128-137`（P2-05/P2-06 观察缺口需人工确认） |

**已知缺陷/缺口（明示，不得当 PASS）**：
- P2-03 并发消费 loser 偶发 `AUTHORIZATION_USE_RECORD_INVALID` 而非 `AUTHORIZATION_REPLAYED`；fail-closed、
  恰一次 consume，无发送/计费，但错误码分类不稳定。执行方案 §4 A1 建议 G4-H1 前修复
  （`docs/M0_G4F_REVIEW_ERRATA.md:152-158`；执行方案 A1 表 P2-03）。**未修复前不得把并发撤销/消费演练写成 PASS。**
- P2-05 `timeout-pre-send` 无 dispatch-window 记录、P2-06 撤销 reason 被 recovery 重写：属观察缺口，
  部署前需在 dispatch-window 中补齐或由维护者明示接受（`docs/M0_G4F_REVIEW_ERRATA.md:134-135,160-166`）。
- 撤销链无独立签名：`revocation` 文档本身不是签名账本（`docs/M0_G4F_HUMAN_HANDOFF.md:22` H-08）。

### 4.6 审批 ID、有效期、单次消费（冻结语义）

- `authorization_id` 仅限 `[A-Za-z0-9._:-]{1,128}`；`issued_utc ≤ not_before_utc < expires_utc`；生命周期 ≤24h；
  签发时间不得早于 7 天前；零 clock skew（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:76-87`；
  `docs/M0_G4_A_AUTHORITY_CONTRACT.md:147-174`）。
- **单次消费**：`consume_execution_authorization()` 在 `pre_reserve` 重跑全量校验后用
  `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC` 落 use record；同 epoch 复用 → `AUTHORIZATION_REPLAYED`；
  跨 run/epoch → `AUTHORIZATION_EPOCH_MISMATCH`；记录 ≥4096 → `AUTHORIZATION_USE_LOG_FULL`
  （`docs/M0_G4_A_AUTHORITY_CONTRACT.md:277-286`）。
- 一次授权内的多次调用只受 `max_calls≤50`、`max_dispatch_attempts≤50`、deadline 约束，**不存在无限复用许可**。
- G5 首次授权建议**独立新 ID、极短有效期**（例如数小时以内）且 ≤3 次请求（§7.2）。

---

## 5. 独立 Credential Broker（真实 Key 边界）

### 5.1 不可妥协的边界

1. 真实 Key **只**存在于维护者可控可信域（独立 OS 身份 + 独立网络命名空间的 Broker/Launcher），
   不进入 Candidate、镜像、Stage、Prompt、Trace、日志、Receipt、JUnit、Packet 或候选环境
   （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:27-36,89-110`；`docs/M0_G4_HUMAN_HANDOFF.md:67-83`）。
2. Candidate **无 Key、无直连、无宿主 Secret 可见**：候选 env 只从 `CANDIDATE_ENV_ALLOWLIST` 重建；
   secret 命名项被丢弃并记违规；`LauncherOnlySecret` 的 `repr/str` 恒 `[REDACTED:n]`；日志脱敏 +
   `assert_log_clean()`（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:91-99`）。
3. Candidate 容器保持 `--network none`、`--read-only`、`--cap-drop=ALL`、`no-new-privileges`、
   `--user=65534:65534`、`--unsetenv-all`、`--http-proxy=false`；禁止 privileged/端口发布/任意 `--env`/
   socket/root mount（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:101-110`）。
4. **现有 broker 不是 Key Broker**：`docs/BUDGET_BROKER.md` 明确其为 fixed-policy bookkeeping bridge，
   不是 Key proxy/human-authorization broker/OS sandbox/provider usage authenticator；`dispatch_allowed`
   只表示该 logical request 首次被记录（`docs/BUDGET_BROKER.md:3-17,162-169`）。

### 5.2 部署步骤（KB-1..KB-8；全部 `HUMAN_REQUIRED`）

| 步骤 | 动作 | 证据 | 失败关闭点 |
|---|---|---|---|
| KB-1 | 在供应商 Console 创建**专用、最小作用域、低额度、可撤销** Key；关闭自动充值/Extra Usage；记录 UTC/URL/账户状态快照 | Console 快照 SHA + 时间 | 无法确认作用域/额度 → 不部署 |
| KB-2 | 在 Broker 主机以独立 OS 身份创建私有目录（root 0700），Key 仅写入受保护文件/进程内存；不落 shell history | 目录/文件 mode/owner 记录 | 目录可被 candidate uid 读 → STOP |
| KB-3 | 配置 Broker 启动参数（固定 scope、DB 路径、策略哈希）并持久化；重启时策略漂移必须启动失败 | 启动 argv、policy hash、启动日志 | 漂移未拒绝 → STOP |
| KB-4 | 仅 Broker/Egress 进程可读 Key；用 `env` allowlist 向 Broker 注入，禁止把 Key 作为 argv/文件名 | proc environ 快照（值脱敏） | Key 出现在 argv/log → STOP |
| KB-5 | 负例：候选容器内 grep env/argv/mount/proc 无 Key；假 Key 注入不进入候选 env/日志 | 扫描输出（0 命中 + 正控命中） | 任一命中 → STOP |
| KB-6 | Key 轮换演练：新旧 Key 重叠、旧 Key 撤销、旧授权失效 | 轮换记录 + 失败负例 | 旧 Key 仍可用 → STOP |
| KB-7 | 泄露响应：撤销 Key → 停 Egress → 撤销授权 → 保全证据 → 对账（不得先在日志里重建 Key） | 事故记录 | — |
| KB-8 | 与 Provider 侧 usage/账单对账流程演练（无真实调用时用 Console 只读快照核对字段） | 对账记录 | 无法对账 → 真实计费 BLOCKED |

### 5.3 未实现 / 未验证（明示）

- 真实 Key 从未存在；Broker 的 OS 身份隔离、只读挂载强制、真实 Key 注入均未部署（`BLOCKED`；
  `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:169-179` §8）。
- 候选 env allowlist、假 Key 负测、日志脱敏为 no-key 范围 `PARTIAL` 证据
  （`docs/E5_PRELIVE_NO_KEY_REPORT.md:40-42`；`docs/M0_G4_D_E5_NO_KEY_REPORT.md:132-145` 哨兵扫描）。
- 真实 Provider 鉴权位置/请求字段/401/429/5xx/Timeout/usage 字段仍 `UNVERIFIED`（见 A2 交付物；
  `docs/SECURITY_APPROVALS.md:44-53`）。

---

## 6. 独立 Egress（唯一可发送路径）

### 6.1 允许发送的必要条件（全部满足才可 dispatch）

1. **固定模型**：`route_id`/`provider`/`model_id` 与冻结 `ProviderRouteContract` 逐字段相等；real route
   在人工核验前恒 `BLOCKED_REQUIRES_HUMAN_VERIFICATION`（`docs/M0_G4_C_EGRESS_CONTRACT.md:39-118`）。
2. **固定方法 + 端点的精确匹配**：`method` 仅 `POST`；`exact_path` 为精确路径（非前缀）；host/port 精确，
   占用 `--network none` 之外唯一受控出口（`docs/M0_G4_C_EGRESS_CONTRACT.md:39-118`；
   `docs/BILLABLE_PATH_INVENTORY.md:26-31`）。
3. **持久预留**：先经 broker `reserve` 成功（且响应确认）才可 claim；重放/无 ack 一律不 dispatch
   （`docs/BUDGET_BROKER.md:90-138`）。
4. **正确 Claim**：`dispatch_allowed=true`、Claim 内容与 Prepared 摘要一致；未 Claim 发送 =
   `DISPATCH_PERMISSION_REQUIRED`（`docs/M0_G4_C_EGRESS_CONTRACT.md:121-178`）。
5. **请求摘要**：发送前重算 payload 字节 SHA、`prepared_digest`、`payload_length`；`TrustedSendAuthorization`
   一次性 `consume()`；发送后 Fake Receipt `raw_sha256` 必须等于 payload digest
   （`docs/M0_G4_C_EGRESS_CONTRACT.md:23-35,121-178`）。
6. **发送前绑定检查**：`binding_drift("pre_dispatch", approved, observed)`；任何 `<ROOT>_MISMATCH` →
   Fake/Provider 不被调用（`docs/M0_G4_C_EGRESS_CONTRACT.md:210-247`）。
7. **工具白名单**：`allowed_tools` 非空、无重复、⊆ 允许集合，且与实际 registry 完全一致；DSH merged
   registry 证据仍 `UNVERIFIED`（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:80-87`；
   `docs/M0_G4F_REVIEW_ERRATA.md:170-185` E5-P04）。

### 6.2 网络强制：TLS / DNS / Proxy / Redirect / Retry（全部 fail-closed）

| 面 | 要求 | 现状 |
|---|---|---|
| TLS | 仅经受控 Egress 发起；验证证书链与主机名；禁止关闭校验/自定义不安全上下文；TLS 错误 = 不发送/终态失败，不重试 | `DESIGN_PENDING_HUMAN`（真实 wire 未观测，`docs/BILLABLE_PATH_INVENTORY.md:66-73`） |
| DNS | 固定解析结果/受控 resolver；禁止 hosts 注入、search domain 改写、DNS 重绑定；解析到非批准 IP → 拒绝 | `DESIGN_PENDING_HUMAN` |
| Proxy 改写 | 禁止 `HTTP(S)_PROXY`/`NO_PROXY`/`ALL_PROXY` 生效；禁止通用 URL 代理；只允许指向批准 endpoint 的专用出口 | `DESIGN_PENDING_HUMAN`；候选侧 `--http-proxy=false` 已 `VERIFIED`（`docs/E5_PRELIVE_NO_KEY_REPORT.md:19`） |
| Redirect | 3xx 一律拒绝或仅允许显式批准的原地跳转；不跟随到未批准 host/path | `DESIGN_PENDING_HUMAN`；A2 契约需核验 |
| Retry | `maxRetries=0`；429/5xx/timeout/disconnect/EOF 不自动重试；未知结果 → `BILLABLE_UNKNOWN` + worst-case held | 配置侧 `VERIFIED`（`docs/DSH_TARGET_PROFILE.md:6-11`）；真实 provider 行为 `UNVERIFIED` |
| 第二条发送路径 | 只有一条受控 transport；禁止 SDK 内部 fallback/备用 provider/Files 二次 POST | 原型级 `PARTIAL`（`docs/BILLABLE_PATH_INVENTORY.md:9-22`，B2/B5/B8 缺口） |

### 6.3 失败关闭与错误映射（无自动重试）

| 场景 | 处置 | 参考 |
|---|---|---|
| 401/403、4xx（非 429） | 终止，记录原始错误码/request id；不重试；不改路由 | `docs/M0_G4_C_EGRESS_CONTRACT.md:197-207`；`docs/BILLABLE_PATH_INVENTORY.md:54-64` |
| 429 | 终止并 STOP；不重试、不换 Key/路由 | 同上 |
| 5xx / timeout / disconnect / EOF / 无 Usage / 部分 Usage | `BILLABLE_UNKNOWN`，worst-case held > 0，不重试，人工对账 | 同上 |
| 未批准的 host/port/method/path/route/model | dispatch 前拒绝 | `docs/BILLABLE_PATH_INVENTORY.md:22,28` |
| TLS/DNS/proxy/redirect 异常 | 不发送或终态失败；不得回退明文/直连 | 本表 §6.2 |

### 6.4 未实现 / 未验证

- `src/autoteacher_m0/security/egress.py` 是**描述符级** allowlist/deny 原型，**不是**真实代理；锁定 OCI
  内 `socket()` 直接 `PermissionError`，真实 provider 传输/内部 retry/cache/Files 均未观测
  （`docs/BILLABLE_PATH_INVENTORY.md:5-7,66-73`）。
- 真实 TLS/DNS/证书/redirect/Proxy 强制属 **PR4b 部署项**（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:169-179`）。
- OpenCode Go 静态配置不等于已批准/可用；`x-opencode-session` 缺口仍 `UNVERIFIED`
  （`docs/OPENCODE_GO_ACCESS.md:197-207,272-303`；`docs/DSH_TARGET_PROFILE.md:41-44`）。

---

## 7. 预算与次数（M0 工程目标，不是供应商硬封顶）

### 7.1 工程目标值（冻结代码常量/声明镜像/交付契约）

| 项 | 值 | 性质 | 依据 |
|---|---|---|---|
| soft total | `$3.00` | 软上限：超过记事件，不变成 FREE | `docs/M0_G4_A_AUTHORITY_CONTRACT.md:249-273` |
| hard total | `$10.00` | M0 **本地策略**上限；超 hard 拒绝 | 同上；`docs/M0_G4_C_EGRESS_CONTRACT.md:181-195` |
| per-call | `$0.20` hard / `$0.10` soft | 单次调用上限/软线 | `docs/M0_G4_A_AUTHORITY_CONTRACT.md:251-254` |
| max requests | `50` | 总请求上限（工程目标） | 同上 |
| input/output tokens | 2,500,000 / 600,000 | 工程上界 | `docs/E4_MOCK_REPORT.md:13` |
| steps / retries | task 8 steps / 1 retry；guard 固定 `maxRetries=0` | 工程目标与配置 | `docs/E4_MOCK_REPORT.md:13`；`docs/BUDGET_BROKER.md:446-453` |
| broker journal | M0 profile `max_messages=4096`；broker 硬上界 100,000 | 容量上界 | `docs/BUDGET_BROKER.md:422-445` |

### 7.2 语义限定（不得夸大）

1. 以上**全部是本地工程目标**；没有供应商侧真实强制机制（账户硬额度/预算告警+自动停用等）时，
   **不得称作“绝对硬封顶”**，也不得承诺“不会超过 $10”
   （`docs/M0_G4_HUMAN_HANDOFF.md:87-103,146-156`；`docs/SECURITY_APPROVALS.md:52-53`）。
2. 未知/部分 Usage、5xx、超时、断连一律按 worst-case 占用，**不当作 0**
   （`docs/BILLABLE_PATH_INVENTORY.md:54-64`；`docs/BUDGET_BROKER.md:130-147`）。
3. G5 首次授权**建议 ≤3 次请求**（例如 2 次最小 smoke + 1 次严格 JSON 验证），单次 `max_tokens` 极小、
   总预算远低于 soft 线；这是建议，最终值由维护者在授权中逐项写明。
4. 预留先于发送：`reserve` 成功是 dispatch 的必要条件；失败/崩溃的 pending 不自动退款，必须显式
   settle/fail；`dispatch_allowed` 不是人类授权（`docs/BUDGET_BROKER.md:90-147,162-169`）。

### 7.3 预留、撤单与未决费用

- 取消/超时/异常不得把已预留费用当 0；必须 `fail` 或按 worst-case 结算，保持 `PENDING_CONSERVATIVE`、
  `retry_allowed=false`、`worst_case_reserved=true`（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`）。
- 任何预算拒绝会持久阻塞该 scope；compaction/error handler 不能绕过已 latched 的 blocked 状态
  （`docs/BUDGET_BROKER.md:106-115`）。
- 事后对账：以供应商侧 usage/账单为准；差异记 `PARTIAL`/`UNVERIFIED`，不得用合成 fixture 价格替代。

---

## 8. Watchdog、资源上限与 Kill Switch

### 8.1 进程树与容器资源上限

- 每 run 必须有总 deadline、`max_steps`、`max_dispatch_attempts`；超限 → latch → kill 进程组 +
  `/proc` 后代树（SIGTERM→有界宽限→SIGKILL）→ survivors 为空
  （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`）。
- 容器 cgroup/资源：memory/pids/cpu 上限；参考 no-key 实测（candidate/trusted `pids.max=256`、
  `memory.max=1 GiB`、`cpu.max=100000 100000`；`docs/M0_G4_D_E5_NO_KEY_REPORT.md:108-121`）。
- rlimit：CPU/AS/NOFILE 实测生效；**host `RLIMIT_NPROC` 对 root 无效 → `UNVERIFIED`**，不得声称已验证
  （`docs/M0_G4_D_E5_NO_KEY_REPORT.md:108-121,289-298` D09 PARTIAL）。

### 8.2 异常杀进程与 absence 清理

- 容器 absence 必须**观测**：`kill -s KILL` + `rm -f` 后全表 `podman ps -a` 为空、`podman inspect` 失败；
  `rm` rc=1/0 **不构成** absence 证明（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`；
  `docs/M0_G4_D_E5_NO_KEY_REPORT.md:71-76`）。
- 路径 absence：socket 仅 root-owned socket 可 unlink 后 `lstat ENOENT`；run-dir 用 safe delete 后复查；
  清理失败 → `FAIL_CLOSED` + 保留人工清理命令（`docs/M0_G4_D_E5_NO_KEY_REPORT.md:99-106` D08）。
- Controller 外壳异常也必须在 `except` 路径 kill 进程树，避免候选遗留（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:132`）。

### 8.3 取消与未决费用保守占用

- 超时/异常/非零退出 → `PendingConservative(retry_allowed=False, worst_case_reserved=True)`，绝不自动重试
  （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`）。
- 已 Reserve 未跨 wire：保持 PENDING/UNCERTAIN/held>0；已跨 wire：按 Broker 终态结算一次
  （G4-F R5 复核结论，`docs/M0_G4F_REVIEW_ERRATA.md:111`）。

### 8.4 人工 Kill Switch（`HUMAN_REQUIRED`）

维护者在任何异常信号下按顺序执行（每一步留证据）：

1. **KILL-1** 停止接受新请求：撤销 `authorization_id`（§4.5），必要时撤销 Key（§5.2 KB-7）。
2. **KILL-2** 终止运行：停止 Egress/Broker/Controller；对容器执行 KILL+删除；对进程树 SIGTERM→SIGKILL。
3. **KILL-3** 观测 absence：`ps -a` 空、`/proc` survivors 空、socket/run-dir ENOENT；失败转人工清理并记录。
4. **KILL-4** 保全证据：复制 gate journal、dispatch-window、ledger DB 只读副本、容器 argv/mountinfo、UTC。
5. **KILL-5** 对账与复盘：以 Provider Console 为准核 usage；未知按 worst-case 记；出具事故记录与后续决定。

**演练要求**：真实部署前必须用**假 Key/合成 fixture**完整演练 Kill Switch（不得使用真实付费调用），
并记录耗时、发现的问题与修复；演练本身也需独立复核。

### 8.5 未实现 / 未验证

- 真实 Live Controller + Watchdog 组合部署未执行；外部 SIGKILL 全窗口未验证；`RLIMIT_NPROC` `UNVERIFIED`
  （`docs/M0_G4F_REVIEW_ERRATA.md:170-185,353-354`；`docs/M0_G4_D_E5_NO_KEY_REPORT.md:289-298`）。
- F4 candidate-crash + live Controller 自动重试子场景 `UNVERIFIED`（`docs/M0_G4F_HUMAN_HANDOFF.md:23` H-09；
  `docs/REVIEW_G4F_INDEPENDENT.md:185-188`）→ 不得承诺“恰好一次”或崩溃自动恢复。
- P2-RUN-IDENTITY/USERNS/DISK 仍待维护者签收（`docs/M0_G4_HUMAN_HANDOFF.md:109-116`）。

---

## 9. 发布与审批（可追溯、变更即失效、独立签核）

### 9.1 发布输入清单（全部需要 SHA-256）

1. **Git SHA**：被审实现提交、docs 提交、build/head SHA；父链可追溯，工作区 clean
   （参考 G4-F 冻结输入格式 `docs/M0_G4F_REVIEW_ERRATA.md:21-34`）。
2. **5 个绑定根**：`code_sha256`、`lock_sha256`、`runtime_sha256`、`plugin_sha256`、
   `merged_profile_sha256`，由 15 个运行时输入组件按 canonical 规则聚合
   （组件表 `docs/M0_G4_A_AUTHORITY_CONTRACT.md:178-199`）。
3. **Stage/rootfs/deps 身份**：stage manifest/tree、trusted/candidate tree、rootfs、deps canonical
   （示例格式 `docs/M0_G4F_REVIEW_ERRATA.md:30-34`）。
4. **DSH runtime/插件版本**：runtime canonical SHA、版本、实际加载模块 18/18 与 HEAD blob 一致
   （`docs/M0_G4F_REVIEW_ERRATA.md:106,214`）。
5. **工具/配置清单**：merged profile、tool registry schema、plugins、`config/*`、预算镜像、route 冻结白名单。
6. **完整文件清单 + 不可变副本**：Packet 内 177 files/0 symlink/173 校验示例；**不重打包**既有 Packet，
   新提交为 append-only（`docs/M0_G4F_REVIEW_ERRATA.md:46-53,231-239`）。

### 9.2 发布包与证据卫生

- Packet 只读、不可变；后续更正以 append-only errata/新 Packet v2 处理。已知 P2-01（2 个 SQLite sidecar
  未哈希，全量 payload tree 漂移）、P2-02（F2-07 证据路径错位）、P2-07（LiveGate reasons 只列 1/4）
  必须在发布前由维护者决定：接受并记录，或生成 v2 清理/修正；不得用“旧 Packet 全量一致”表述
  （`docs/M0_G4F_REVIEW_ERRATA.md:128-150,231-239`）。
- 新 Packet 若生成：明确 sidecar 排除规则、重算 `hashes.sha256`/tree、保留 v1 原字节。

### 9.3 变更即失效

任何以下变化使已签授权与本发布失效，必须重新独立复核+重新签名：
代码任一字节、依赖锁/依赖树、镜像/rootfs/deps、DSH runtime/插件、merged profile、工具白名单/schema、
route/model/endpoint、预算/policy/价格快照、Controller 常量、授权/撤销/信任根文件本身
（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:178-226,247-273`；`docs/SECURITY_APPROVALS.md:55-59`）。
运行期由 `pre_start`/`pre_reserve`/`pre_dispatch` 三个检查点强制发现漂移。

### 9.4 独立签核流程

1. 实现方冻结发布并提交审核请求（含 base/impl/docs SHA、argv、Case ID、时间戳、原始日志、已证实/
   未验证/阻断项、模型/费用来源分类）。
2. 独立 Reviewer（未参与实现）从冻结 SHA + 清洁 Stage 复跑定向负例与证据校验，出具
   `PASS/PARTIAL/BLOCKED`，保留原始证据。
3. 维护者按 [`HUMAN_SIGNOFF_TEMPLATE.md`](HUMAN_SIGNOFF_TEMPLATE.md) 逐项核对并签署
   **仓库外**授权文件；签核模板本身不是授权。
4. 未通过项不得以“其他项通过”为由合并放行；H/I（人类/整合）行不得由 Agent 改 PASS
   （执行方案 §8）。

### 9.5 紧急撤销与事故 Runbook

| 触发条件 | 立即动作（谁） | 证据 | 后续 |
|---|---|---|---|
| Key 疑似泄露/出现在日志 | 撤销 Key（维护者）、停 Egress、撤销授权 | 泄露位置/范围（脱敏）、Console 快照 | 全量扫描、轮换 Key、复盘 |
| 未授权出站/未知 egress | 立即 Kill Switch（§8.4）、保全网络证据 | 容器 argv/mountinfo/journals | 独立安全复核 |
| 预算异常/账单不一致 | 停止新请求、撤销授权、对账 | ledger vs Provider usage | 保守结算 + 决定降级/暂停 |
| 授权/绑定漂移 | 下一次检查自动 deny；停止发布 | `BINDING_DRIFT:*` 原因 | 重新审阅与签名 |
| 容器/进程残留 | 人工清理 + absence 复查 | `podman ps -a`、`/proc`、manual-cleanup | 修复后重新演练 |
| 证据被篡改/路径错位 | STOP、保全现场、不覆盖历史字节 | 前后 SHA 对照 | 独立审计 |

**事故记录必须由人类撰写并归档到仓库外证据根；Agent 只能起草（并明确标注“草案”）**。

---

## 10. 分步部署流程（S0–S12）

> 说明：S0–S8 是**准备与部署**；S9 是**签名前预检**（仍无真实调用）；S10 是**第一次真实有界调用**
> （G5 单次授权，`HUMAN_REQUIRED`）；S11–S12 是收尾与 STOP。每一步都记录 负责人/输入/命令(argv)/
> UTC/exit/日志/hash；“命令”列只给**受控占位**，本文件不提供可执行 Live 开关。

| 步骤 | 内容 | 负责人 | 关键输入 | 证据采集 | 失败关闭点 | 当前状态 |
|---|---|---|---|---|---|---|
| S0 | 核对 HEAD/基线、工作区 clean、冻结限制；确认 A 线交付物齐全（§3） | A-Lead + 维护者 | §3 P-1..P-7 | `git rev-parse`、`git status`、清单 | 漂移/缺失 → STOP | `NOT_RUN` |
| S1 | 独立复核发布清单与 5 个绑定根（从清洁 Stage 复算，不信任 Agent manifest） | 独立 Reviewer | 冻结 SHA | 复算命令+输出+diff | 任一不一致 → STOP | `NOT_RUN` |
| S2 | 构建/校验 frozen Stage、rootfs、deps、工具清单；记录 canonical 哈希 | Operator | §9.1 | stage manifest/tree、镜像 digest、`--pull=never` | 哈希不符 → STOP | `NOT_RUN` |
| S3 | 部署人类信任根：公钥注册表、撤销列表、审批目录（root 只读、仓库外） | 维护者 | §4 | 目录 owner/mode、只读挂载、验签/撤销演练 | 候选可写/可读 → STOP | `DESIGN_PENDING_HUMAN` |
| S4 | 部署 Credential Broker（独立 OS 身份/网络命名空间），注入专用低额度 Key | 维护者 + Operator | §5 | 启动 argv/UTC、env allowlist、Key 负例扫描 | Key 可见/可复制 → STOP | `BLOCKED` |
| S5 | 部署独立 Egress，配置固定 endpoint/method/path/model + TLS/DNS/no-proxy/no-redirect/no-retry | Operator | §6 | 配置 hash、负例（错误 host/port/path/method/redirect/proxy） | 任一未 fail-closed → STOP | `BLOCKED` |
| S6 | 部署外部 Watchdog + 人工 Kill Switch 演练（假 Key/合成 fixture） | Operator | §8 | Watchdog 日志、absence 复查、演练记录 | 残留/不可 kill → STOP | `PARTIAL`（仅 no-key 演练） |
| S7 | 初始化固定 scope 的 broker/ledger，写入冻结 policy；验证漂移拒绝与重启保留 | Operator | §7 | policy hash、启动负例、DB 只读副本 | 漂移未拒绝/可 reset → STOP | `VERIFIED`（offline 范围） |
| S8 | 生成发布 Packet/证据归档；独立签核（§9.4）；维护者签署**仓库外**授权（§4.3） | Reviewer + 维护者 | §9 | Packet hash、签核模板、授权文件 hash | 缺独立复核/签核 → STOP | `DESIGN_PENDING_HUMAN` |
| S9 | 签名前预检：`run_live.sh` 仍 exit 3、CLI `--live` exit 3、Adapter `SECURITY_BLOCKED`、LiveGate 仍 BLOCKED；0 Key/0 真实 HTTP 扫描 | Operator + Reviewer | §6/§8 负例 | 行为输出、扫描结果（正控命中） | 任一入口被打开 → STOP | `VERIFIED`（no-key 基线） |
| S10 | 第一次真实有界调用（G5 单次授权）：≤3 次请求、极短有效期、无工具/文件、固定 prompt、`maxRetries=0`、记录 request id/usage | 维护者授权 + Operator 执行 | 已签授权 + §6/§7 | argv/UTC/exit、Provider usage/Console、ledger 对账 | 401/429/5xx/未知 usage/任何异常 → 立即 KILL，不重试 | `BLOCKED`（未授权） |
| S11 | 执行后对账与证据归档：ledger vs Console、pending 结算、撤销授权/轮换 Key（按需） | Operator + 维护者 | S10 证据 | 对账报告、撤销记录、hash 清单 | 对账不一致 → 记 UNVERIFIED 并暂停 | `NOT_RUN` |
| S12 | STOP：出具部署/执行结论（只允许 PASS/PARTIAL/BLOCKED 的**限定范围**表述），等待维护者决定 G6/M1 | 维护者 + Reviewer | S0–S11 | 一页状态报告 | 不得自动进入下一门 | `NOT_RUN` |

**部署完成不等于 Live 批准**：S10 成功最多证明“该配置在该次有界授权下可连通并可追踪 usage”；
`E5 Full`、`G4-H1/H2`、G5 后续、G6、M0 GO 均需新的独立证据与人类决定
（`docs/OPENCODE_GO_ACCESS.md:272-303`；`docs/M0_G4_HUMAN_HANDOFF.md:128-142`）。

---

## 11. 证据采集与归档规范

- **仓库外证据根**：`<TRUSTED_DEPLOY_ROOT>/evidence/<run-id>/`，root 所有、权限受限、持久、append-only；
  `artifacts/` 仅是本机 gitignored 中间产物，不能作为最终部署证据（`docs/M0_RUNBOOK.md:39`）。
- **每次运行目录**至少包含：`argv/`、`logs/`、`utc-start.txt`/`utc-end.txt`、`exit-code.txt`、
  `identity/`（SHA/哈希/镜像 digest）、`journal/`、`ledger-copy/`、`absence/`、
  `provider/`（request id、usage 脱敏）、`manifest.json`、`evidence.sha256`。
- **哈希**：`sha256sum -c evidence.sha256` 必须可复验；文档不改写历史证据，更正走 append-only errata
  （参考 `docs/M0_G4F_REVIEW_ERRATA.md:1-6,279-301`）。
- **禁止落入证据**：真实 Key/Secret、Authorization header 原文、个人数据、真实学生/私有数据、
  未脱敏 Provider 响应。示例凭据只能是明显占位符（如 `oc_sk_FAKE_…`）。
- **脱敏**：使用 Controller 的 `redact_secrets()`/`assert_log_clean()` 覆盖已知值与
  `oc_sk_`/`sk-`/`Bearer` 模式（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:91-99`）；扫描器正控必须命中，
  否则“0 命中”无效（参考 D03/D04 方法 `docs/M0_G4_D_E5_NO_KEY_REPORT.md:124-153`）。

---

## 12. 未实现 / 未验证总表（部署前必须逐项处置）

| ID | 项 | 现状 | 关闭条件 | 负责人 |
|---|---|---|---|---|
| U-01 | 人类 Ed25519 信任根、公钥注册/轮换/撤销、私钥托管部署 | `BLOCKED`（仅测试种子/离线校验器） | §4 完成 + 非生产演练证据 | 维护者 |
| U-02 | 独立 Credential Broker + 真实 Key | `BLOCKED` | §5 完成 + 负例证据 | 维护者 |
| U-03 | 独立 Egress（TLS/DNS/Proxy/Redirect/Retry fail-closed） | `BLOCKED`（仅描述符级原型） | §6 完成 + 真实 wire 负例 | Operator |
| U-04 | 真实 Provider wire/usage/账单/价格/TLS | `UNVERIFIED` | A2 证据 + G5 当日官方快照 | 维护者 |
| U-05 | 供应商侧硬额度/停用/降级计划 | `UNVERIFIED` | Console 证据或明示接受风险 | 维护者 |
| U-06 | DSH merged Registry / E5-P04 | `UNVERIFIED`（DSH 0.2.2-rc.2 无权威导出；现仅 per-dispatch 白名单） | 权威导出或独立接受残余 | 维护者 + Security Reviewer |
| U-07 | F4 candidate-crash + live Controller | `UNVERIFIED` | 补测或明示残余；不得承诺恰好一次 | A/Reviewer |
| U-08 | E5-P05 watchdog 执行腿独立重跑 / 外部 SIGKILL 全窗口 | `PARTIAL`/`UNVERIFIED` | 独立 Reviewer 重跑 | Reviewer |
| U-09 | P2-03 并发消费错误码竞态 | 已知 fail-closed 缺陷 | 原子 use-record + 并发回归（建议 G4-H1 前） | Implementer + Reviewer |
| U-10 | P2-05/P2-06 dispatch-window 观察缺口 | 已知观察缺口 | 补记录/映射或明示接受 | 维护者 |
| U-11 | P2-RUN-IDENTITY / USERNS / DISK | `UNVERIFIED`/待签收 | 签收或加固并重新取证 | 维护者 |
| U-12 | host `RLIMIT_NPROC` | `UNVERIFIED` | 容器 cgroup 替代证明或签收 | 维护者 |
| U-13 | 产品内 test-only crash/delay hooks | 仍存在（仅可信 env 可触发） | 移除或隔离，或明示接受 | 维护者 |
| U-14 | 撤销链独立签名/审计链 | 无签名、root-owned 输入 | 签名撤销链或明示接受 | 维护者 |
| U-15 | Packet sidecar/路径/reasons（P2-01/02/07） | `PARTIAL`（v1 缺陷已披露） | 接受并记录或发布 v2 | 维护者 |
| U-16 | 真实人类审批与独立复核指派 | `NOT_ASSIGNED`/`PENDING` | 指派独立 Reviewer 并完成复核 | 维护者 |
| U-17 | LiveGate 语义 | 恒 `BLOCKED`（不得改动） | 不改；仅由外部边界部署后的新审批路径决定 | — |
| U-18 | `LiveGate`/入口现状 | `run_live.sh` exit 3、CLI/Adapter BLOCKED `VERIFIED` | 保持 | — |

> 表中任何 `UNVERIFIED`/`BLOCKED` 项**不得**在部署报告中写成 PASS；与
> [`E5_PRELIVE_FULL_CHECKLIST.md`](E5_PRELIVE_FULL_CHECKLIST.md) 的状态必须一致。

---

## 13. 本文件“没有做什么”（防误读）

- 没有修改 `src/`、`scripts/`、`LiveGate`、`run_live.sh`、DSH 配置、Packet 或任何证据字节。
- 没有生成/读取真实 Key、没有发起真实 HTTP/TLS、没有部署任何组件、没有执行 G4-H1/H2 或 G5。
- 没有代替维护者签核、没有把 Markdown/Packet 当授权、没有声称 E5 Full / G4 PASS / M0 GO。
- 没有提供真实可执行命令；§10 命令列是受控占位，需维护者在受信环境按独立审批准备。
- 与现有文档的差异/冲突点集中见 [`A3_REFS.md`](A3_REFS.md)。

## 14. STOP

本 Runbook 执行到 **S8 维护者签名前一步**为止必须 STOP；S10 需要新的、单独的、人类签署的 G5 单次授权。
当前默认状态：**未授权、未部署、未调用、LiveGate=BLOCKED、M0=DECISION_PENDING**。
