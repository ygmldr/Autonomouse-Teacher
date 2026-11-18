# M0 G4 — 人工交接清单（未签署）

- **性质**：**未签署、未批准、未授权**。本文件只列维护者未来必须亲自完成的事项与所需证据。
- **当前状态**：`G4-H-01..06 = BLOCKED / NOT_AUTHORIZED`；`G5 = BLOCKED`；`G6 = NOT_RUN`；`LiveGate = BLOCKED`；`M0 = DECISION_PENDING`；`E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
- **纪律**：任何一项都标记 `PENDING_HUMAN_ACTION`；**不得**由 Agent 写 `APPROVED`、`PASS`、`AUTHORIZED` 或等价字样替代真实人类决策；不得复用测试私钥、测试签名或本 Packet 作为授权凭据。
- **依据**：G4 任务书 §11、`docs/SECURITY_APPROVALS.md`、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`、`docs/E5_PRELIVE_NO_KEY_REPORT.md`、`docs/M0_G4_FINDINGS_AND_DISPOSITION.md`。

---

## 总表

| ID | 人工专属项 | 当前状态 | 阻断的后续 |
|---|---|---|---|
| G4-H-01 | 冻结提交/依赖/配置/路由/预算的独立二次审阅 | `PENDING_HUMAN_ACTION` | E5 Full、G5 |
| G4-H-02 | 人类持有的审批信任根、公钥注册/轮换/撤销、私钥离线保管 | `PENDING_HUMAN_ACTION` | 任何真实授权 |
| G4-H-03 | 独立 Key Broker / 可信 Egress 部署与网络策略 | `PENDING_HUMAN_ACTION` | 任何联网执行 |
| G4-H-04 | 官方模型/Endpoint/价格/Usage/额度/Key 作用域核验 | `PENDING_HUMAN_ACTION` | 真实计费 |
| G4-H-05 | P2 签收 + E5-PreLive 全量独立安全 Review | `PENDING_HUMAN_ACTION` | E5 Full、G5 |
| G4-H-06 | 一次范围严格限定的 G5 试验授权 | `PENDING_HUMAN_ACTION` | 任何 Live |
| — | 供应商硬额度/降级计划（若无法硬封顶） | `PENDING_HUMAN_ACTION` | 真实付费运行 |

---

## G4-H-01 — 冻结提交与全量输入的独立二次审阅

**必须由人类完成**：

1. 独立核对精确冻结 SHA：base `017c747`、impl `a6f3e0a`、code `d3d429c`、docs（Packet `docs_sha`）。
2. 审阅完整 diff、依赖锁、Stage/rootfs/deps、DSH profile/merged registry、工具白名单、route/model、预算/价格快照、Watchdog/撤销配置。
3. 在 Agent 不可写权限域独立复算 canonical 哈希；不得只信任 Agent 生成的 manifest 或“选择性文件子集”。
4. 记录审阅人、日期、范围、发现的 P0/P1/P2、结论与失效条件。

**所需证据**：

- 独立复算的 SHA/哈希清单与命令；
- 完整 diff 与依赖/配置清单；
- 与 Packet `manifest.json` 的逐项对照；
- 任何偏差的处置。

**失效条件**：任何代码、依赖、profile、tool list、route、budget/policy、配置变化都使本次审阅失效，必须重新审阅。

**当前状态**：`PENDING_HUMAN_ACTION`。Agent 未执行、未代替签署。

---

## G4-H-02 — 人类持有的审批信任根与密钥生命周期

**必须由人类完成**：

1. 在 Agent 不可写的独立权限域创建/保护审批公钥注册表、撤销文件、授权文件目录。
2. 定义 Ed25519 公钥注册、轮换、撤销、私钥离线保管、授权 ID/scope/有效期、单次使用与审计流程。
3. 确保私钥不由授权 API、Candidate、Controller 或测试代码生成/保存；测试私钥不得复用。
4. 定义“谁可以签、签什么、签多久、如何撤销、事故如何处置”。

**所需证据**：

- 公钥指纹/注册记录、撤销流程、私钥托管方式；
- 目录 owner/mode/只读挂载证明；
- 一次**非生产**的签名/验签/撤销演练记录（不得使用真实付费 Key）。

**禁止**：Agent 生成正式审批密钥、把私钥提交仓库、把自签测试 JSON 当人类批准、在 Markdown 中写 `APPROVED`。

**当前状态**：`PENDING_HUMAN_ACTION`；`HUMAN_AUTHORIZATION_DEPLOYED` **未达成**。

---

## G4-H-03 — 独立 Key Broker / 可信 Egress 部署

**必须由人类完成**：

1. 选择并部署独立 Key Broker/可信 Egress（独立进程/权限域/网络命名空间），只让 Egress 有出口，Candidate 永久禁网。
2. 使用专用、可撤销、最小权限、供应商作用域受限的 Key；Key 不进入镜像、Stage、Prompt、Trace、日志、Receipt、JUnit、Packet 或 Candidate env。
3. 校验 DNS/TLS/证书、redirect、代理 env、额外 POST/fallback、请求路径解析；禁止通用 URL 代理与直连官方域名之外的路径。
4. 定义 Key 轮换/吊销、Egress 故障、出口审计与人工熔断流程。

**所需证据**：

- Egress 进程/网络策略/只读挂载/最小权限证明；
- Candidate 无网络、无 Key、无 Broker/Policy 挂载的真实负例；
- DNS/TLS/redirect/proxy 负例；
- Key 作用域与撤销演练。

**当前状态**：`PENDING_HUMAN_ACTION`；本地只有 synthetic Fake Provider，**没有任何真实出口**。

---

## G4-H-04 — 官方模型、Endpoint、价格、Usage、额度核验

**必须由人类完成**（执行 G5 当天取官方资料并留快照）：

1. 核实官方模型 ID、API endpoint、版本、认证方式、Stream/Tool 兼容、Usage 字段、错误码、cache/token 计费。
2. 核实官方价格与计费单位；不要硬编码旧 OpenCode Go 路由当正式主渠道。
3. 核实供应商账户额度、硬封顶、停用、Key 权限；若无法硬封顶，必须给出可信出口风险限额、降级计划与人工接受风险。
4. 明确 `$3/$10/$0.20/50` 只是工程策略，不是供应商硬限；不得承诺“不会超过 $10”。

**所需证据**：

- 官方文档/管理后台快照（UTC、URL、版本）；
- 价格/Usage 样例与字段映射；
- 供应商额度/封顶截图或 API 证据；
- 风险接受记录（如无硬封顶）。

**当前状态**：`PENDING_HUMAN_ACTION`；本 Packet 的 `price_source=REQUIRES_VERIFICATION`，`E5-P04` 仍 `UNVERIFIED`。

---

## G4-H-05 — P2 签收与 E5-PreLive 全量独立安全 Review

### 5.1 P2 签收（三项，逐项明确接受或另立工作项）

| ID | 残余 | 人类必须做的决定 |
|---|---|---|
| P2-DISK | Candidate session 无磁盘硬配额 | 加配额/更强隔离，或明确签收 DoS 风险 |
| P2-USERNS | 内核允许嵌套 user namespace | 加 seccomp/禁 userns，或明确签收内核攻击面 |
| P2-RUN-IDENTITY | `SO_PEERCRED` 不是 per-run token | 加 per-run capability/独立 UID，或明确签收同 UID 旧 Run 风险 |

### 5.2 E5-PreLive Full

1. 由**不同于 Implementation Agent** 的 Security Reviewer 独立执行 E5-P01..P05 全项真实部署验证。
2. P01：外部真实人类签名/信任根已部署；P02：部署后动态文件不可写；P03：正式审批与独立 trust root 上线；P04：权威 merged registry/未知动态 tools 可证明或被删除；P05：真实 Key 保护、TLS/账单/供应商硬额。
3. 出具正式 Full PASS 或明确 FAIL/BLOCKED；**不得**用 G4 无 Key 子集 PASS 替代。
4. 签收 P2 与残余风险；记录签收人/日期/范围。

**当前状态**：`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`；五项 `FULL_STATUS` 全部 Blocked。

---

## G4-H-06 — 一次范围严格限定的 G5 试验授权

**只有在 G4-H-01..05 全部通过后**，维护者才可另发一次 G5 授权，至少明确：

- 具体 route / provider / model / API 版本；
- 单次 run / session / 调用上限（`max_calls`、`max_dispatch_attempts`）；
- 总费用限额与 per-call 上限；
- 起止时间与有效期；
- Watchdog / 撤销 / 人工熔断 / 负责人；
- 允许的 tool schema 与禁止项；
- 失败/unknown/账单不一致时的处置。

**禁止**：把 G4 无 Key PASS、Packet、测试签名或本 handoff 当作 G5 授权；Agent 不得自行启动 G5；G5 仍需 Smoke/Tool/Session 分批人工审阅。

**当前状态**：`PENDING_HUMAN_ACTION`；`G5=BLOCKED`、`G6=NOT_RUN`。

---

## 供应商硬额度与降级计划（若无法硬封顶）

若官方账户/API 不支持硬封顶：

1. 维护者必须明确接受“本地工程上限不等于供应商硬限”的风险；
2. 给出可信出口侧的独立限额/熔断/人工监控方案；
3. 定义超支、429、5xx、未知 Usage、账单不一致时的降级与停机流程；
4. 记录接受人、日期、金额上限与复核周期。

**当前状态**：`PENDING_HUMAN_ACTION`；本 Packet 不主张任何供应商硬额度。

---

## 交接签署区（留空，禁止 Agent 填写）

```text
Reviewer / Maintainer:        ____________________
Date (UTC):                   ____________________
Scope reviewed:               ____________________
P0/P1 found:                  ____________________
P2 accepted (Y/N/conditions): ____________________
E5 Full verdict:              ____________________
G5 authorization:             NOT ISSUED
Signature / approval ref:     ____________________
```

> 在真实签署发生之前，以上所有项保持 `PENDING_HUMAN_ACTION`。本文件不是授权、不是批准、不是 Live 许可。
