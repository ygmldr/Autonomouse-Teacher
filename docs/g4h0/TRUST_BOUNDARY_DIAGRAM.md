# 信任边界与数据流（G4-H0 设计稿）

- **文档性质**：`DESIGN_PENDING_HUMAN`。描述**目标**受信部署的信任边界与数据流，并明确区分
  “当前实际状态（无 Key）”与“目标状态（未部署）”。本文件不是授权、不是部署证据、不是 E5 Full PASS。
- **基线**：`3e7afee077845a071cd364e93ab209cac20b2d5f`；文中 `path:line` 行号以该基线为准。
- **上游设计**：`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`（PR3，当前主安全设计）、
  `docs/M0_G4_A_AUTHORITY_CONTRACT.md`（授权/绑定闭包）、`docs/M0_G4_C_EGRESS_CONTRACT.md`（发送授权）、
  `docs/BUDGET_BROKER.md`（bookkeeping）、`docs/M0_G4_D_E5_NO_KEY_REPORT.md`（watchdog/撤销/no-key 证据）、
  `docs/THREAT_MODEL.md`（基础威胁模型）、`docs/M0_G4F_REVIEW_ERRATA.md`（最终状态常量与残余）。
- **状态常量**（不得改写）：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`
  （`docs/M0_G4F_REVIEW_ERRATA.md:89-98`）。

---

## 1. 图 1 — 当前实际边界（无 Key / 未部署，`VERIFIED`）

```
┌─────────────────────────── 仓库 / 本机（Agent 可写，非受信部署域）───────────────────────────┐
│  docs / Packet / artifacts（只读证据）        src/（代码默认可审、尚未独立审阅）              │
│                                                                                              │
│  ┌─────────────────────────────┐        ┌──────────────────────────────────────────────┐    │
│  │ LiveGate.inspect()          │        │ TrustedLiveController.inspect()（无 run/execute）│
│  │ 恒 BLOCKED                   │◄──────│ 恒 BLOCKED；即使签名有效也追加 4 条未部署原因   │    │
│  │ 无 authorize/approve 方法    │        └──────────────────────────────────────────────┘    │
│  └─────────────┬───────────────┘                                                            │
│                │ 拒绝                                                                       │
│  run_live.sh──►exit 3；CLI --live──►exit 3；HarnessAdapter──►SECURITY_BLOCKED                │
└──────────────────────────────────────────────────────────────────────────────────────────────┘
                     │  （无真实 Key；无真实出站路径存在）
                     ▼
      ┌──────────────────────────────────────────────────────────┐
      │ Candidate 容器（LOCKED OCI，no-key 已验证）               │
      │  --network none  --read-only  --cap-drop ALL             │
      │  --user 65534:65534  no-new-privileges  --unsetenv-all   │
      │  env 仅 allowlist；无真实 Secret；无 host home/socket     │
      └───────────────────────┬──────────────────────────────────┘
                              │ 仅 stdio/raw-UDS 到 Fake Provider（合成 fixture）
                              ▼
      ┌──────────────────────────────────────────────────────────┐
      │ Fake Provider / synthetic fixture（容器内子进程）         │
      │  0 真实模型、0 真实 HTTP、0 计费                          │
      └──────────────────────────────────────────────────────────┘
```

关键事实：当前**没有**可用的外部授权边界、Key Broker、Egress 或部署态 Watchdog；`LiveGate` 仍恒 `BLOCKED`
并输出 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`（`src/autoteacher_m0/security/gates.py:63-86`；
`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:134-145`）。候选容器与 Fake Provider 的隔离属 no-key 已测范围，
**不能**外推为真实 Provider/生产安全（`docs/M0_G4F_REVIEW_ERRATA.md:71-98`）。

---

## 2. 图 2 — 目标受信边界（`DESIGN_PENDING_HUMAN`，全部未部署）

```
╔════════════════════════════════════ 人类可信域（HUMAN_REQUIRED）════════════════════════════════╗
║  维护者（人类，离线私钥）                                                                        ║
║   ┌────────────────────────────┐     ┌───────────────────────────────────────────────────┐    ║
║   │ Ed25519 私钥（离线/硬件）   │     │ 审批工件（仓库外 root 只读）                        │    ║
║   │ 仅签 ExecutionAuthorization│     │  execution-authorization.json（单次消费、≤24h）     │    ║
║   └────────────┬───────────────┘     │  trusted-keys.json（公钥注册）                      │    ║
║                │ 签                   │  revocations.json（撤销）                          │    ║
║                └────────────────────►│  use-records/（单次消费记录，append-only）          │    ║
║                                      └───────────────────────┬───────────────────────────┘    ║
╚══════════════════════════════════════════════════════════════╪════════════════════════════════╝
                                                               │ 只读加载 / 每次检查重跑
╔══════════════════════════════════════ 受信部署域 ═════════════════════════════════════════════╗
║  （独立 OS 身份；Agent 不可写；root 只读挂载）                                                  ║
║                                                                                              ║
║  ┌──────────────────────────────────────────────┐    ┌─────────────────────────────────────┐ ║
║  │ 可信 Controller（inspect + 受审执行外壳）      │───►│ 外部 Watchdog（独立进程）            │ ║
║  │  · 5 绑定根 / 15 组件校验                     │    │  · deadline/step/dispatch 上限        │ ║
║  │  · pre_start / pre_reserve / pre_dispatch     │    │  · 进程树 kill + absence 观测         │ ║
║  │  · 只按已签授权放行                            │    │  · PENDING 保守占用 / 绝不自动重试      │ ║
║  └──────┬───────────────────────────┬───────────┘    └─────────────────────────────────────┘ ║
║         │                           │                                                        ║
║         │ 预留/结算（stdio）          │ 发送授权（内存、一次性）                                 ║
║         ▼                           ▼                                                        ║
║  ┌──────────────────────────┐   ┌──────────────────────────────────────────────────────────┐  ║
║  │ Budget broker / ledger   │   │ 独立 Egress（唯一出网路径）                                │  ║
║  │  · 固定 scope/DB/policy  │   │  只允许：固定 route/model + 固定 method/endpoint/path      │  ║
║  │  · reserve-before-send   │   │  + 持久预留 + 正确 Claim + 请求摘要一致                    │  ║
║  │  · 未知=worst-case 占用   │   │  TLS/DNS/Proxy 改写/Redirect/Retry 全部 fail-closed       │  ║
║  └──────────┬───────────────┘   └───────────────────────────┬──────────────────────────────┘  ║
╚═════════════╪═══════════════════════════════════════════════╪═════════════════════════════════╝
              │ 账本/预留结果（仅受信侧可见）                       │ 唯一真实出站（受控 Key 由 Broker/Launcher 持有）
              ▼                                                   ▼
┌───────────────────────────────────────────┐       ┌─────────────────────────────────────────┐
│ 仓库外证据根（append-only，root 受限）       │       │ 真实 Provider（供应商）                  │
│ 授权/撤销/use-log/journal/dispatch-window/  │       │  真实 usage/账单/TLS/额度                │
│ ledger 只读副本/告警/事故记录/哈希清单        │       │  （价格与字段需 A2 核验，UNVERIFIED）     │
└───────────────────────────────────────────┘       └─────────────────────────────────────────┘

              ┌─────────────────────────────────────────────────────────────────────┐
              │ Candidate Runtime/容器（不可信、无凭据）                              │
              │  --network none / 只读 / 非 root / 无 host home·socket / 无 Key        │
              │  只能通过 stdio/raw-UDS 与受信 Controller 会话；不能直连 Egress        │
              └─────────────────────────────────────────────────────────────────────┘
```

> **边界要点**：真实 Key 只在「受信部署域」的 Credential Broker/Launcher 中；候选容器与真实 Key 之间
> 隔着 **Controller 校验 + Broker 预留 + Egress 发送授权** 三道 fail-closed 检查。任何“候选 → 真实 Key”
> 或“候选 → 真实网络”的直接路径都必须不存在（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:27-36,89-110`）。

---

## 3. 图 3 — 单次受控发送的数据流与检查点

```
Human maintainer                Trusted Controller                Broker/Ledger              Egress            Provider
     │                                │                            │                        │                 │
     │ 1. 签署 ExecutionAuthorization  │                            │                        │                 │
     │    （仓库外；不含机器可执行开关）│                            │                        │                 │
     ├───────────────授权文件────────►│                            │                        │                 │
     │                                │ 2. pre_start: 5 根/工具/路由/预算/时限/签名/撤销     │                 │
     │                                │    ↓ 任一失败 → SECURITY_BLOCKED（无部分批准）        │                 │
     │                                │ 3. prepare → prepared_digest/call_id                 │                 │
     │                                │ 4. pre_reserve: 重跑全量校验                          │                 │
     │                                │    + 单次消费记录（O_EXCL）                           │                 │
     │                                ├──── reserve（完整上下文上界/输出上界）──────────────►│                 │
     │                                │◄──── RESERVED / dispatch_allowed=true ────────────────┤                 │
     │                                │ 5. claim → Claim 内容与 prepared 摘要逐项一致          │                 │
     │                                │ 6. begin_attempt: ATTEMPT_STARTED(payload_digest)     │                 │
     │                                │ 7. pre_dispatch: binding_drift(approved vs observed)  │                 │
     │                                │ 8. TrustedSendGate.authorize → 一次性内存授权          │                 │
     │                                │    （无 from_json；Consume 时重算 payload 字节 SHA）   │                 │
     │                                │ 9. consume（一次性）── 授权不可重放/不可复制            │                 │
     │                                ├──── 固定 route/model/method/endpoint/path ─────────────────────────►│
     │                                │                                                      │ 10. TLS/证书校验
     │                                │                                                      │     DNS 固定
     │                                │                                                      │     no proxy/redirect/retry
     │                                │                                                      │     网络异常 → 终态失败
     │                                │◄─────── response / usage / error（原始 request id）──────────────────┤
     │                                │ 11. settle/fail：完整 usage 按快照；缺失/未知 → worst-case held       │
     │                                │     （永不自动重试计费 attempt；unknown ≠ 0）                          │
     │                                │ 12. 证据：journal/dispatch-window/账本备份/hash → 仓库外证据根        │
     ▼                                ▼                            ▼                        ▼                 ▼
  人类签核归档                  gate journal                 ledger + snapshot       egress audit       Provider Console
```

**检查点 2/4/7/8/11/12 任一失败 = fail-closed**：不发送、不重试、不回退、不把未知当 0
（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:212-226,277-286`；`docs/M0_G4_C_EGRESS_CONTRACT.md:121-178`；
`docs/BUDGET_BROKER.md:90-147`）。

---

## 4. 资产、持有者与读写权限矩阵（目标）

| 资产 | 持有者 | 谁可读 | 谁可写 | 候选容器可见 | 当前状态 |
|---|---|---|---|---|---|
| Ed25519 私钥 | 维护者（离线） | 仅维护者/分管人 | 仅维护者 | 否 | `BLOCKED`（未生成正式根） |
| 公钥注册表/撤销列表 | 受信部署域（仓库外只读） | Controller | 维护者（受控变更） | 否 | `DESIGN_PENDING_HUMAN` |
| 授权文件 | 仓库外审批目录 | Controller | 维护者（签名后） | 否 | `DESIGN_PENDING_HUMAN` |
| 单次消费记录 | 仓库外 use-records | Controller/审计 | Controller（O_EXCL） | 否 | 逻辑验证 `VERIFIED`；部署 `BLOCKED` |
| 真实 Provider Key | Credential Broker | Broker/Egress 进程 | 维护者注入 | **否** | `BLOCKED` |
| Budget DB/journal | 受信部署域 | Controller/审计 | Broker | 否 | offline `VERIFIED`；部署 `BLOCKED` |
| 真实 Provider 请求/usage | Egress/Provider | Operator/审计（脱敏） | Provider | 否 | `UNVERIFIED` |
| Candidate 输出/session | Candidate 自有面 | 受信 Controller | Candidate（自有） | 是（自有） | `VERIFIED`（no-key） |
| Packet/证据根 | 仓库外/只读 | Reviewer/维护者 | 维护者/Operator | 否 | `PARTIAL`（v1 有 P2 缺陷） |
| Test-only 合成种子 | 测试进程内存 | 测试进程 | 测试 | 否 | `VERIFIED`；不得注册为正式根 |

---

## 5. 信任假设（显式列出；任一不成立则整个边界失效）

1. **人类可信**：维护者私钥离线、签名代表真实意图；Agent 不能接触私钥、不能代签
   （`docs/M0_G4_A_AUTHORITY_CONTRACT.md:64-70,359-367`）。
2. **Controller/校验代码按冻结 SHA 运行**：代码、依赖、profile、工具清单被独立复核且运行期由 5 根绑定；
   任一变化触发 `BINDING_DRIFT`（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:178-226`；`docs/SECURITY_APPROVALS.md:55-59`）。
3. **OS 强制边界成立**：只读挂载、独立 UID/namespace、root-owned 目录、candidate 不可写审批/账本/Key；
   这是**部署层假设**，Python 无法自证（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:105-123,212-226,350-367` R6/R7/R12）。
4. **只有一条发送路径**：所有 Provider 调用经受控 Egress；候选无直连、无 Key、无 host socket。
   现状原型级 `PARTIAL`，真实 OS 层强制未部署（`docs/BILLABLE_PATH_INVENTORY.md:66-73`）。
5. **供应商行为可核对**：TLS/证书、DNS 解析、redirect、代理 env、内部 retry、usage/账单字段可核验；
   当前多数字段 `UNVERIFIED`（`docs/SECURITY_APPROVALS.md:44-53`；A2 交付物）。
6. **Watchdog 独立**：deadline/kill/absence 由受信域外部进程执行，非候选自报
   （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:121-132`；`docs/M0_G4_D_E5_NO_KEY_REPORT.md:67-76`）。
7. **证据不可篡改**：证据根 append-only、哈希可复验、历史字节不改写
   （`docs/M0_G4F_REVIEW_ERRATA.md:1-6,279-293`）。
8. **合成证据不被冒充真实**：synthetic fixture/费率/usage 只证明管线，不等于真实账单或教学效果
   （`docs/E4_MOCK_REPORT.md:3-10`；`docs/BILLABLE_PATH_INVENTORY.md:5-7`）。

---

## 6. 威胁模型增量（相对 `docs/THREAT_MODEL.md` 与 PR3 设计）

| # | 威胁 | 现有覆盖 | 本 G4-H0 增量（设计与要求） | 残余/未验证 |
|---|---|---|---|---|
| T-01 | Agent 自签/自建 Markdown 解锁 Live | 代码层无 approve 路径，负测全部拒绝（`docs/M0_G4_A_AUTHORITY_CONTRACT.md:230-243`） | 人类签名根 + 仓库外审批目录 + 独立复核流程（Runbook §4/§9） | 真实信任根未部署 → `BLOCKED` |
| T-02 | 伪造/篡改授权或重放 | 签名校验、严格 JSON、单次消费、epoch（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:62-87`；G4-A §7/§11） | 撤销列表/轮换 SOP + 并发消费竞态修复（P2-03） | P2-03 错误码竞态未修（fail-closed） |
| T-03 | 候选读取真实 Key / 宿主 Secret | env allowlist、日志脱敏、mount/argv 拒绝（`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:89-110`；G4-D D03/D15） | 独立 Broker OS 身份 + Key 仅受信域 + 泄露响应 Runbook | 真实 Broker 未部署 → `BLOCKED` |
| T-04 | 候选直连 Provider/绕过 Egress | egress 描述符级 deny；候选 `--network none`（`docs/M0_G4_C_EGRESS_CONTRACT.md:23-35`） | 独立 Egress 唯一路径 + DNS/TLS/Proxy/Redirect/Retry 强制（Runbook §6.2） | 真实 OS 层强制 `UNVERIFIED` |
| T-05 | 预算/未知费用失控 | 预留、保守占用、无自动重试（`docs/BUDGET_BROKER.md:90-147`；`docs/BILLABLE_PATH_INVENTORY.md:54-64`） | 明确“无供应商硬限不得称绝对硬封顶”；G5 ≤3 次请求；对账（Runbook §7） | 供应商硬额度 `UNVERIFIED` |
| T-06 | 运行失控/残留进程/容器 | Watchdog deadline/kill/absence（PR3 §5；G4-D D01/D02/D08） | 人工 Kill Switch + 演练要求（Runbook §8.4） | 真实部署组合 `BLOCKED`；外部 SIGKILL 全窗口 `UNVERIFIED` |
| T-07 | 权限配置漂移/工具清单变化 | 5 绑定根 + pre_dispatch 漂移检查（G4-A §8；G4-C §4） | 变更即失效 + 发布 Packet/签核（Runbook §9.3） | merged registry / E5-P04 `UNVERIFIED` |
| T-08 | 同 UID 旧 Run 访问新 Run 状态 | namespace/mode 拒绝（G4-D D15） | 部署不变量：审批/账本/state 目录 root 0700、不放宽 candidate 可写 | P2-RUN-IDENTITY 待维护者签收 |
| T-09 | 证据/日志被篡改或含 Secret | 脱敏、扫描器正控、append-only errata（G4-D §3；errata §10） | 证据根独立、哈希清单、事故 Runbook、禁止真实 Secret 入库 | 撤销链无独立签名（H-08） |
| T-10 | 供应链/依赖漂移 | lock/rootfs/deps 哈希绑定（G4-A §8；G4-F R0） | 发布前独立复算；变更需重审 | 依赖安全人工审查仍 `UNVERIFIED` |
| T-11 | 崩溃恢复导致重复发送/重复计费 | crash-resume 不重发、ATTEMPT 状态机（G4-F F4） | 明确“不承诺恰好一次”；崩溃恢复需保守 PENDING | F4 candidate-crash + live Controller `UNVERIFIED` |
| T-12 | 人类误签/越权授权 | 模板 + 有效期 + 单次 + 撤销 | 签核模板字段、拒签条件、独立复核人 | 依赖流程执行，无技术强制 |

---

## 7. 与 `docs/LIVE_CONTROLLER_SECURITY_DESIGN.md` 的差异（明确不同处与原因）

| # | 差异 | 原因 | 是否冲突 |
|---|---|---|---|
| D-01 | PR3 设计把 Ed25519 公钥/私钥托管列为“人类部署项”；本文件把它展开为**完整签名/注册/轮换/撤销/单次消费 Runbook** | 执行方案 A3 要求可审计部署手册；PR3 只覆盖设计与 no-key 负测 | 不冲突（增量） |
| D-02 | PR3 明确“真实费用边界留给 PR4 egress/Key Broker”；本文件把 Credential Broker、Egress 列为**一等部署组件**并给证据要求 | 实际真实部署必须回答“谁持有 Key、谁能出网” | 不冲突（补齐 PR3 §8 的 BLOCKED 项） |
| D-03 | PR3 文档中 `$3/$10/≤50` 表述为策略上限；本文件统一改述为**M0 工程目标**，并禁止“绝对硬封顶”表述 | 无供应商侧强制机制（`docs/M0_G4_HUMAN_HANDOFF.md:87-103`）；避免误导 | 不冲突（纠正表述） |
| D-04 | PR3 的 Watchdog 为代码/演练组件；本文件增加**人工 Kill Switch 与部署态演练要求** | 真实事故处置必须有人工断路 | 不冲突（增量） |
| D-05 | PR3 §2 图是“设计/接口、尚未部署”；本文件图 1 **明确标注当前实际状态**，图 2 标注 `DESIGN_PENDING_HUMAN` | 防止把设计图当成已部署证据 | 不冲突（澄清） |
| D-06 | PR3 §6 说明 `TrustedLiveController` 无 run/execute；本文件不改其语义，也不建议为 G4-H0 增加执行方法 | 执行方案禁止通过改 gate/flag 达成“部署完成” | 一致 |
| D-07 | 本文件把 E5 的 NO_KEY_SUBSET 与 FULL 状态显式分列（见 `E5_PRELIVE_FULL_CHECKLIST.md`） | G4-F errata 明确二者不可混写（`docs/M0_G4F_REVIEW_ERRATA.md:170-185`） | 一致 |
| D-08 | 本文件把撤销链“无独立签名”和 P2-03/05/06 列为已知缺口 | G4-F 已披露，执行方案 A1 要求处置 | 一致（风险登记） |

> **未改动项**：`LiveGate` 恒 `BLOCKED`、`Scripts/run_live.sh` exit 3、CLI `--live` 先拒绝、
> `HarnessAdapter._require_live_authorization()` 恒拒绝——本文件不提出任何改变
> （`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:134-145`；`src/autoteacher_m0/security/gates.py:63-86`）。

---

## 8. 不主张 / 残余

- 不主张任何真实部署已完成；不主张 E5 Full、G4-H1/H2、G5、G6、M0 GO 或生产安全。
- 不主张内核/运行时 0day 防护、宿主 root 被攻陷后的安全；不主张跨宿主/跨 Runtime 可移植。
- 不主张供应商侧硬额度、exactly-once、真实 Invoice 或供应商撤销语义。
- 图中所有“目标”组件均为 `DESIGN_PENDING_HUMAN`；所有“当前”组件仅覆盖 no-key/离线范围
  （`docs/M0_G4F_REVIEW_ERRATA.md:68-98`；`docs/SECURITY_APPROVALS.md:12-24`）。
