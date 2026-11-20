# A-NEXT — 人类交接包（G4-H1 决策准备，全部未签核）

- **文档 ID**：`A-NEXT-HUMAN-HANDOFF-v1`
- **性质**：仅列**必须由维护者（必要时联签 Independent Security Reviewer）亲自决定/签核**的事项。
  **全部决策状态 = `UNSIGNED` / `PENDING_HUMAN_ACTION`**；本文件是草案，不是授权、不是批准、不是部署证据、
  不是 G4-H1/G5/Live 许可。**Agent 不得代签、代勾、代填任何 ACCEPT / APPROVED / AUTHORIZED。**
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/a-next-handoff` / `docs/a-next-handoff`；
  canonical 基线 `work/g4r=fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；
  frozen src impl `d33e0aabd1714a486325b745c436cb59855d6539`；
  base/main `3e7afee077845a071cd364e93ab209cac20b2d5f`。
- **当前状态常量（未因本文件改变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
  `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
- **配套文件**：
  - 本包 `docs/A_NEXT_G4H1_DEPLOYMENT_RUNBOOK.md`（无 Key 部署设计，`DESIGN_PENDING_HUMAN`）
  - 本包 `docs/A_NEXT_PROVIDER_CONTRACT_DRAFT.md`（外部事实 = **2026-11-19 研究快照、未获批、未真实调用**）
  - 本包 `docs/A_NEXT_PRICE_AND_USAGE_VERIFICATION.md`（同上）
  - G4-R 人类交接：`docs/M0_G4R_HUMAN_HANDOFF.md`（`M0-G4R-HUMAN-HANDOFF-v1`，表格 `D-01..D-13`）
  - G4-R 独立 Review / 勘误：`docs/REVIEW_G4R_INDEPENDENT.md`（sha256 `0599856a…446c`，禁改）、
    `docs/M0_G4R_REVIEW_ERRATA.md`（append-only）
  - 旧 G4-H0 交付（**只读引用，不重新签核为 A-NEXT 依据**）：`work/m0-g4h0:docs/g4h0/`
    （`HUMAN_DECISIONS.md` sha256 `1dd2dac9…1f80`；`HUMAN_DECISIONS_PROPOSED.md` sha256 `9c1d3d54…c9ca`；
    `DEPLOYMENT_RUNBOOK.md` sha256 `b780aa54…8092`；`PROVIDER_CONTRACT_DRAFT.md` sha256 `ed720978…6f2b`；
    `PRICE_AND_USAGE_VERIFICATION.md` sha256 `40a7b7dd…4fec`；`A2_SOURCES.md` sha256 `77a5ead5…f018`）

> 签核方式：每行填 `决定（ACCEPT / FIX / BLOCK / DEFER）` + `签核人（印刷名/角色）` + `UTC 日期` +
> `依据/条件` +（如适用）独立 Security Reviewer 联签 + 仓库外签名/审批引用。未填行视为未签核，相关门保持 BLOCKED。
> 任何 Markdown、仓库内 JSON、Packet、Agent 生成的“已通过/已批准”文字都不构成授权。

## 0. 摘要

| 项 | 值 |
|---|---|
| 继承的 G4-R 人类决策（本包 canonical ID） | **D-01..D-13**（13 项，全部 `UNSIGNED`，见 §1） |
| A-NEXT 新增决策 | **D-14..D-22**（9 项，全部 `UNSIGNED`，见 §2） |
| 旧 G4-H0 决策处置 | `HD-01..HD-20` 与 `PROPOSED D-01..D-12`：继承/合并/取代/需重新签核（见 §3） |
| 总决策项计数 | **22**（D-01..D-22） |
| 单独 BLOCKER 清单 | **18 项**（BLK-01..BLK-18，见 §4） |
| 必须先由人类确认的部署类项 | 信任根/Key Broker/Egress/Watchdog 部署、E5-Full、G5 单次授权、P2 残余、B03/E5-P04、OCI deselect 43→69、环境事故（全部未签） |
| Agent 已代签/代批项 | **0**；本文件全部空白 |

## 1. 继承的 G4-R 决策 D-01..D-13（来源：`docs/M0_G4R_HUMAN_HANDOFF.md`）

> 标注说明：`继承` = ID/内容直接沿用，A-NEXT 不改变其语义，但**必须重新签署**（旧签署不存在）；
> `继承+扩展` = 原 ID 保留，A-NEXT 增加适配/前置条件；`需重新签核` = 原 G4-R 状态不得外推，必须按本表重签。

| ID | 决策事项 | 继承状态 | A-NEXT 适配/前置条件 | 当前状态 |
|---|---|---|---|---|
| D-01 | 接受/不接受 G4-R 裁定与范围（`PASS_FOR_G4R_NO_KEY_REMEDIATION_SCOPE` / PARTIAL / FAIL / BLOCKED，限定 no-key） | 继承 | 须同时审阅 `REVIEW_G4R_INDEPENDENT.md` 与 append-only `M0_G4R_REVIEW_ERRATA.md`；不得外推 E5-Full/G5/Live | **UNSIGNED** |
| D-02 | 最终 Packet v2 是否采用（v1 不可变只读；拒绝静默扩 deselect/未哈希文件） | 继承 | 引用 G4-R Packet v2（43 files/0 symlink/payload 40/hashes 41，tree `4300a7c6…`）；A-NEXT 新证据须新包/新身份，不改旧字节 | **UNSIGNED** |
| D-03 | P2-03/04/05/06 修复签收（以 Reviewer 独立复测为准） | 继承 | G4-R 中 P2-03 已 `CLOSED`；P2-04/05/06 按 Reviewer 报告；不得写“全部关闭”超出范围 | **UNSIGNED** |
| D-04 | B03 / E5-P04 Registry 残余（`UNVERIFIED` + per-dispatch 白名单补偿控制，或要求权威导出） | 继承+扩展 | A-NEXT Registry 决策（A3）仍 `UNVERIFIED`；不得把 R3 `API_AVAILABLE` 当权威 attestation | **UNSIGNED** |
| D-05 | P2-RUN-IDENTITY / P2-USERNS / P2-DISK 残余 | 继承 | 维持原残余；真实部署前不得放宽 DAC/mount/磁盘模型 | **UNSIGNED** |
| D-06 | F4-R1 / F5-R6 / F1-R4 / F2-R5 / B07 残余处置 | 继承 | 禁止把语义证据写成字节级/穷举证明；B07 title fallback-only 仍属残余 | **UNSIGNED** |
| D-07 | R5-01..03（F4-06 candidate crash + live Controller）`UNVERIFIED` | 继承 | 无可控注入证据；不得承诺“全部恢复语义” | **UNSIGNED** |
| D-08 | 环境漂移/清理事件确认（rootfs 16:52–16:59Z；恢复、Stage fail-closed、rootfs 可写副本政策；不得宣称全程 NO_DRIFT） | 继承+扩展 | A-NEXT Runbook §9 已写入“禁止直接 `--rootfs` 冻结件、独占窗口串行”；A-NEXT 任何新 L2/OCI 必须遵守 | **UNSIGNED** |
| D-09 | OCI deselect 差异（legacy 43 未扩大 + 26 explicit `tests/integration/g4r_auth`；43→69）签收 | 继承+扩展 | 须逐项签收原因/列表/总数与失败分类；A-NEXT 不得静默扩 deselect | **UNSIGNED** |
| D-10 | 历史 junit 误覆盖事件知悉/接受（已从冻结 Packet 原字节恢复，sha `7f25ba83…`） | 继承 | 证据卫生事件；不得再发生写入旧证据路径 | **UNSIGNED** |
| D-11 | G4-H-01..06 人工项：独立二次审阅、人类信任根、Key Broker/Egress、官方价格/Usage、E5-Full Review、单次 G5 授权 | 继承+扩展 | A-NEXT 拆分为 D-14..D-22 的可执行子项；**部署本身仍只能人类执行** | **UNSIGNED** |
| D-12 | G5 bounded real request（模型/Key/预算/次数/期限 + E5-Full 前置） | 继承 | 当前 **BLOCKED**；价格/路由/usage 均为研究快照，未重核；不得默认开启 | **UNSIGNED** |
| D-13 | 其它真正开放风险（`M0_G4R_FINDINGS_AND_DISPOSITION.md` §4） | 继承+扩展 | 并入 BLK-10..BLK-18；A-NEXT 新发现（P2-01/P2-02/route/usage/DSH target profile）见 §2/§4 | **UNSIGNED** |

## 2. A-NEXT 新增决策 D-14..D-22（全部 UNSIGNED）

| ID | 决策事项 | 背景（本工作树实测） | 备选/建议（Agent 建议，非签核） | 阻塞对象 | 当前状态 |
|---|---|---|---|---|---|
| D-14 | **P2-01 / P2-02 处置**：`_read_use_record` 增加 body `authorization_id` 交叉校验；`consume_execution_authorization` 接入 run-level 受信 admission（Fake-only） | P2-01 `OPEN`：`authorization.py:802-848` 只校验 schema/epoch，不校验 body id == `sha256(id)+'.json'`；P2-02 `OPEN`：`authorization.py:988` 在 production `src/` 内**无调用方**（仅 `scripts/g4r/r1_independent_probe.py`、`scripts/g4/e5_probe.py`、tests） | 建议：H1 前 FIX（小补丁 + Reviewer 复测），或写明“以独立压力证据替代”；**不得**以模块级 PASS 外推 dispatch 链 | G4-H1 / G5 | **UNSIGNED** |
| D-15 | **Provider 主路由最终选择**：官方 `deepseek-official/deepseek-flash` vs 第三方 OpenCode Go vs 双路由隔离 | `settings.py:5-6`、`config/models.example.yaml`、`docs/ROUTE_DECISION.md` 声明官方；`egress.py:31-34,121-122` 硬编码 `opencode.ai:443` + `opencode-go/deepseek-v4.1-flash`；旧 A2 研究已于 2026-11-19 记录官方契约（未获批） | 建议 A：官方主路由（与 v0.4/ROUTE_DECISION 一致）；B：第三方（须重新评估 ToS/额度/隐私且不能记官方 PASS）；C：双路由隔离（复杂度最高） | D-16 / D-17 / G5 | **UNSIGNED** |
| D-16 | **Egress allowlist 与所选路由统一**（`api.deepseek.com:443` + `/chat/completions` vs `opencode.ai:443` + `/inference/go/`） | `live_controller.py:43,199-204`：Controller 的 approved route 必须在冻结 egress allowlist 中，否则 `ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST`；当前默认 `EXPECTED_EGRESS_POLICY = EgressPolicy()` 仍是 opencode-go allowlist | 建议：H1 前统一为**受批准的单一路由+单一大白名单**并全量重验；不得同时放任两条真实路径 | G4-H1 / G5 | **UNSIGNED** |
| D-17 | **官方价格快照与 usage 字段在 G5 前重新核实/签收** | A2/本包价格 = **2026-11-19T17:47:09Z 研究快照**；`config/budgets.yaml:11` `live_pricing_snapshot: REQUIRED_UNVERIFIED`；官方页面声明价格可变；无真实账单 | 建议：G5 执行当日重新采集官方价格/模型/usage 字段，维护者逐项签收；不得把旧快照当“当前价” | G5 / 预算可信 | **UNSIGNED** |
| D-18 | **usage 映射 v2 修复范围**：官方 Chat Completions `prompt_cache_hit_tokens`/`prompt_cache_miss_tokens` 无 `cache_write` 字段，与本地三桶映射不兼容 | `broker_usage.py:3,15,69-98` 要求 `inputTokens/cacheReadTokens/cacheWriteTokens` 三桶齐全才 `complete_input`；`observation.py:38-46,258` 同；官方字段见旧 A2 研究 S04/S05 | 建议：批准 `official-route usage mapping v2`（miss→input、hit→cache_read、cache_write=None）并补测试；否则官方 route 观测会按 PARTIAL 最坏结算 | G5 / 对账 | **UNSIGNED** |
| D-19 | **DSH target profile 是否启用官方 `llm-deepseek` route** | 当前 `config/dsh/target-runtime.patch.yml:4-5` **禁用 `llm-deepseek`**，只启用 synthetic fixture route；`target-runtime-opencode-go.patch.yml` 仅 STATIC-ONLY、第三方、无 Key/网络 | 建议：M0/no-key 期间保持禁用；若 H1 选官方路由，需新增经审计的 `llm-deepseek` 行 + 仓库外 Key Broker + 外部 egress，并重跑受影响验收 | G4-H1 / G5 | **UNSIGNED** |
| D-20 | **A-NEXT 验收门槛与独立 Reviewer 指派**：`S1_A_NO_KEY_HARDENING_PASS` 的判定主体/范围 | 当前无 A-NEXT 独立 Reviewer 指派；`REVIEW_G4R` 的 Reviewer 不自动成为 A-NEXT Reviewer；Agent 不能自审 | 建议：维护者指派未参与 A-NEXT 实现的独立 Reviewer；只允许 `PASS/PARTIAL/FAIL/BLOCKED`（no-key 限定） | A-NEXT 收口 | **UNSIGNED** |
| D-21 | **M0/G6 状态维持**：`M0=DECISION_PENDING`、`G6=NOT_RUN` | 旧 A2 研究/本包均不构成 M0 GO；B 线 M1 验收也不能替代 A 线 | 建议：保持 DECISION_PENDING/NOT_RUN，直到 G4-H1+E5-Full+独立证据齐备 | G6 / M1 接入 | **UNSIGNED** |
| D-22 | **外部事实快照有效期与重验责任**：本包 provider/price 文档仅 2026-11-19 研究快照，未获批/未真实调用 | 旧 A2 文档与官方页面 sha256 均已记录；本包不重采（A6 是文档适配，无网络调用） | 建议：指定重验责任人与日期（建议 G5 前 24h 内），过期快照自动不得用于预算/契约 | G5 / A-05 | **UNSIGNED** |

> **计数口径**：本包共 **22** 项决策（D-01..D-22，全部 `UNSIGNED`）。任何把其中某项写成 `ACCEPT/APPROVED`
> 的文字都只能来自维护者亲笔签署的**仓库外**文件，Agent 文档不算。

## 3. 旧 G4-H0 决策处置表（继承/合并/取代/需重新签核）

> 旧来源：`work/m0-g4h0:docs/g4h0/HUMAN_DECISIONS.md`（Reviewer 版 `HD-01..HD-20`）与
> `HUMAN_DECISIONS_PROPOSED.md`（`D-01..D-12`）。**旧分支/旧签核不自动成为 A-NEXT 依据。**

| 旧 ID | 旧事项摘要 | 处置 | 映射到本包 |
|---|---|---|---|
| HD-01 | G4-F 16 条风险处置总签收 | **取代**（G4-R 已重做 P0/P1/P2 矩阵） | D-01 / D-13 |
| HD-02 | G4-F Packet v1 vs v2 | **取代**（G4-R Packet v2 已独立复核） | D-02 |
| HD-03 | 矩阵 F2-07 evidence path 修正 | **合并** | D-02 |
| HD-04 | P2-03 并发消费修复验收 | **继承+需重新签核**（G4-R Reviewer 已 CLOSED；仍须人类签收） | D-03 |
| HD-05 | P2-04 测试清理 | **继承+需重新签核** | D-03 |
| HD-06 | P2-05 dispatch-window 观察 | **继承+需重新签核** | D-03 |
| HD-07 | P2-06 recovery reason 保留 | **继承+需重新签核** | D-03 |
| HD-08 | P2-07 zero-key reasons 不一致 | **继承+需重新签核** | D-02 |
| HD-09 | P2-08 host 失败集合归因 | **继承+需重新签核** | D-08 |
| HD-10 | F-01 g4_h0 测试时序缺陷 | **合并**（G4-R R-REV2 压力证据覆盖模块级；不得写“测试全绿”） | D-03 |
| HD-11 | F-02 use-record 目录未 fsync | **已由 G4-R 原子 consume 实现**（`authorization.py:988-1097`；dir fsync 失败→`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`）；但**无 Controller 消费方** | D-14 |
| HD-12 | F-03 Runbook 与 P2-03 口径不一致 | **取代**（本包 Runbook 重写；旧 Runbook 仅历史） | D-20 |
| HD-13 | F-04/F-05 nit（FIFO/截断） | **继承+需重新签核**（仍 OPEN/LOW） | D-13 |
| HD-14 | E5-P04 / DSH Registry 残余 | **继承+需重新签核**（仍 UNVERIFIED） | D-04 |
| HD-15 | 正式受信部署（G4-H1/H2） | **继承+需重新签核**（本轮仍不部署） | D-11 |
| HD-16 | E5-PreLive Full | **继承+需重新签核**（仍 BLOCKED） | D-11 |
| HD-17 | 单次 G5 授权 | **继承+需重新签核**（仍 BLOCKED） | D-12 |
| HD-18 | Provider 主路由选择 | **继承+扩展**（新增 egress allowlist 统一/价格重核） | D-15 / D-16 / D-17 |
| HD-19 | 双路由/egress 冲突 | **继承+扩展** | D-16 |
| HD-20 | M0 GO / G6 选型 | **继承+需重新签核** | D-21 |
| PD-01..PD-12 | 旧 `HUMAN_DECISIONS_PROPOSED.md` | **全部需重新签核**：PD-01→D-01、PD-02→D-02、PD-03/04→D-03、PD-05→D-02、PD-06→D-04、PD-07→D-05、PD-08→D-06/D-07、PD-09→D-15/D-17、PD-10→D-11、PD-11→D-12、PD-12→D-21 | 见左 |

## 4. BLOCKER 清单（单独列示；任何一项未解除，不得进入 G4-H1/G5/Live）

| ID | BLOCKER | 当前证据（本工作树实测，`fd1d3a6`/`d33e0aa`） | 解除条件（人类/工程） |
|---|---|---|---|
| BLK-01 | **默认路由与 egress allowlist 不一致** | `settings.py:5-6` 默认官方 `deepseek-official/deepseek-flash`；`egress.py:31-34,121-122` 硬编码 `opencode.ai:443` + `opencode-go/deepseek-v4.1-flash`；`live_controller.py:43,199-204` 要求 approved route ∈ `EXPECTED_EGRESS_POLICY.approved_routes`，否则 `ROUTE_NOT_IN_FROZEN_EGRESS_ALLOWLIST` | D-15/D-16 人类选定并签核单一路由+allowlist；全量重验 |
| BLK-02 | **真实人类信任根未部署** | `live_controller.py:66-70` `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`；`gates.py:70` 恒含该 reason；无真实公钥注册/撤销链 | 维护者部署信任根（仓库外）并出部署证据 |
| BLK-03 | **真实 Key Broker 未部署** | `live_controller.py:66-70` `EXTERNAL_CREDENTIAL_BROKER_NOT_DEPLOYED`；`docs/BUDGET_BROKER.md:3-17` 明确现有 broker 只是 bookkeeping，不是 Key proxy；`credential_boundary.py:28,64-111` 仅 env allowlist/脱敏 | 维护者以独立 OS 身份部署 Key Broker + 低额度可撤销 Key |
| BLK-04 | **真实 Egress 代理/服务未部署** | `live_controller.py:66-70` `EXTERNAL_EGRESS_PROXY_NOT_DEPLOYED`；`egress.py:1-10` 自述 descriptor diagnostics，不是 network proxy；`TrustedEgressTransport` 仅注入接口 | 部署受控 Egress（TLS/DNS/proxy/redirect/retry fail-closed）+ 独立审计 |
| BLK-05 | **外部 Watchdog 未部署** | `live_controller.py:66-70` `EXTERNAL_WATCHDOG_NOT_DEPLOYED_REHEARSAL_ONLY`；`watchdog.py:327+` 为进程内状态机/演练 | 独立 Watchdog 服务 + Kill Switch 演练证据 |
| BLK-06 | **LiveGate 恒 BLOCKED（设计使然）** | `gates.py:63-86`：`LiveGate.inspect()` 恒 `BLOCKED`，无 approve/unlock；`require_live()` 恒抛 `SecurityBlocked`；`live_controller.py` 无 `run()/execute()`；`scripts/run_live.sh` exit 3；CLI `--live` BLOCKED/3；`dsh_adapter.py:101-110` 恒 `SECURITY_BLOCKED` | **不得改动**；只能由人类部署外部边界后另立新审批路径（本轮不做） |
| BLK-07 | **P2-02：consume 无生产调用方（run-level 单次授权未接线）** | `authorization.py:988` `consume_execution_authorization` 仅在 `scripts/g4r/r1_independent_probe.py`、`scripts/g4/e5_probe.py`、tests 中被调用；`docs/REVIEW_G4R_INDEPENDENT.md` P2-02 OPEN | D-14：Fake-only 接线 + Reviewer 复测后才可 H1 |
| BLK-08 | **P2-01：body authorization_id 未交叉校验** | `authorization.py:802-848` 只校验 schema/epoch；Reviewer 探针实测“异 id 记录”判 `AUTHORIZATION_REPLAYED`（保守但审计不可区分） | D-14：读取时交叉校验 + 测试 |
| BLK-09 | **`AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN` 无 Controller 消费方** | `authorization.py:1088-1096` 目录 fsync 失败→该码；G4-R Review 观察-2 指出当前无 Controller 映射 | D-14/接线：映射为“不确定/不发送”，补测 |
| BLK-10 | **B03 / E5-P04 Registry `UNVERIFIED`** | `docs/REVIEW_G4R_INDEPENDENT.md` §4：仅 L1 instrumentation，无权威 merged registry/trusted channel；`config/g4/runtime-policy.json` `registry_status=UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` | 权威导出或人类签收残余 + per-dispatch 白名单补偿（D-04） |
| BLK-11 | **E5-Full 未授权/未执行** | `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`（旧 g4h0 E5 清单）；`docs/M0_G4R_HUMAN_HANDOFF.md` D-11 | 人类部署后逐项执行并独立复核 |
| BLK-12 | **G5 单次真实模型授权未签发** | `docs/M0_G4R_HUMAN_HANDOFF.md` D-12；无真实 Key/Provider/HTTP | 人类单次、有界、可撤销授权（模型/Key/预算/次数/期限） |
| BLK-13 | **真实 Provider wire/usage/账单未验证** | 本包 PROVIDER/PRICE 文档 = **2026-11-19 研究快照**，未真实调用；`REVIEW_G4R` 范围明确无 Key/模型 | G5 当日重采 + 真实 usage/Console 对账（D-17/D-22） |
| BLK-14 | **DSH target profile 无官方 route** | `config/dsh/target-runtime.patch.yml:4-5` 禁用 `llm-deepseek`；`:34-57` 仅 synthetic `offline-test-only/fixture-v1`；OpenCode Go overlay STATIC-ONLY | D-19：人类批准并审计新 profile（含 Key/egress 边界） |
| BLK-15 | **usage 映射与官方字段不兼容** | `broker_usage.py:3,15,69-98` 要求三桶齐全；官方 Chat Completions 无 cache-write 字段（旧 A2 S04/S05，2026-11-19） | D-18：usage mapping v2 修复/测试 |
| BLK-16 | **OCI deselect 43→69 未签收** | `docs/M0_G4R_REVIEW_ERRATA.md` §0/§3；G4-R D-09；26 explicit `tests/integration/g4r_auth` 为环境类 | 人类逐项签收原因/列表/总数（D-09） |
| BLK-17 | **R-REV6（真实 DSH two-turn/Replay/usage 对账）未执行** | `docs/REVIEW_G4R_INDEPENDENT.md` §8/§10：`R-REV6=NOT_RUN`；Owner RG-05 亦 NOT_RUN | D-07：独立 L2 取证后重签 |
| BLK-18 | **环境漂移/历史 junit 事件不可宣称全程干净** | `docs/M0_G4R_REVIEW_ERRATA.md` §4：rootfs 漂移窗口 16:52–16:59Z、清理恢复、`cp -a` 副本政策；D-10 junit 误覆盖已恢复 | 人类确认事件与恢复记录（D-08/D-10）；A-NEXT 不写“全程 NO_DRIFT” |

> 附加风险（非独立 BLOCKER，但必须在 H1 前处置）：P2-RUN-IDENTITY/USERNS/DISK（D-05）；
> F4/F5/F1/F2/B07 残余（D-06）；test-only crash/delay hooks、撤销链签名、F4 字节级 context（D-13）；
> `nlink==2` 容忍与 `nlink>2` 拒绝的设计边界（G4-R 观察-2）。

## 5. 必须先由人类确认的事项（按门分组）

| 门 | 必须人类确认 | 对应决策 | 当前 |
|---|---|---|---|
| **部署（G4-H1）** | 信任根（Ed25519 私钥/公钥注册/撤销）、Key Broker、Egress、外部 Watchdog 的部署批准与执行；独立 OS 身份/权限域 | D-11 / D-14..D-19 | **未授权/未部署** |
| **证据/口径** | G4-R 裁定范围、Packet v2、P2 残余、B03/E5-P04、OCI 43→69、环境漂移、junit 事件 | D-01..D-13 | **UNSIGNED** |
| **E5-Full** | E5-P01..P05 全项真实部署验证的签收与独立复核 | D-11 | **BLOCKED** |
| **G5** | 单次真实模型授权：provider/model/endpoint/Key/预算/次数/期限/撤销 | D-12 / D-15 / D-17 / D-22 | **BLOCKED** |
| **A-NEXT 收口** | S1_A_NO_KEY_HARDENING_PASS 的 Reviewer 指派与判定 | D-20 | **UNSIGNED** |
| **M0/G6** | M0 GO / G6 选型维持 `DECISION_PENDING/NOT_RUN` | D-21 | **未变** |

## 6. 签核记录（维护者填写；初始全空；禁止 Agent 填写）

```text
Maintainer（印刷名 / 角色）：____________________
Independent Security Reviewer（如适用）：____________________
UTC 日期：____________________
审查的 frozen SHA / Stage / Packet：____________________

[ ] D-01 G4-R 裁定与范围          决定：________  条件：____________________
[ ] D-02 最终 Packet v2           决定：________  条件：____________________
[ ] D-03 P2-03/04/05/06 签收      决定：________
[ ] D-04 B03/E5-P04 残余          决定：________  条件：____________________
[ ] D-05 RUN-IDENTITY/USERNS/DISK 决定：________
[ ] D-06 F4-R1/F5-R6/F1-R4/F2-R5/B07 决定：________
[ ] D-07 R5-01..03 / F4-06        决定：________
[ ] D-08 环境漂移/清理事件        决定：________
[ ] D-09 OCI deselect 43→69       决定：________
[ ] D-10 历史 junit 事件          决定：________
[ ] D-11 G4-H-01..06 人工项       决定：________（本轮默认：不做）
[ ] D-12 G5 bounded real request  决定：________（默认：BLOCKED）
[ ] D-13 其它开放风险             决定：________
[ ] D-14 P2-01/P2-02 FIX/接线     决定：________  条件：____________________
[ ] D-15 Provider 主路由选择      决定：官方 / OpenCode Go / 双路由 / DEFER
[ ] D-16 Egress allowlist 统一    决定：________
[ ] D-17 官方价格快照重核/签收    决定：________  有效期：____________________
[ ] D-18 usage mapping v2 范围    决定：________
[ ] D-19 DSH target profile route 决定：________
[ ] D-20 A-NEXT Reviewer/门槛     决定：________  指派：____________________
[ ] D-21 M0/G6 状态               决定：________（默认：DECISION_PENDING/NOT_RUN）
[ ] D-22 外部快照有效期/重验责任人 决定：________  截止：____________________

仓库外审批引用/签名：____________________
发放的授权范围/编号：____________________（默认：NOT ISSUED）
G4-H authorization：NOT ISSUED
G5 authorization：NOT ISSUED
```

> 在维护者真实签署前，以上全部 `UNSIGNED`；`LiveGate`、E5-Full、G4-H1/H2、G5、G6、M0 GO 状态不得改变。
> 本文件、任何 Agent Markdown、Packet 或合成测试材料都**不是**授权。

## 7. 禁止事项（Agent 侧）

1. 不得代签/代勾/代填任何 ACCEPT / APPROVED / AUTHORIZED / GO；不得把本文件当审批。
2. 不得生成/读取/注入真实 Key，不得调用真实 Provider/付费 Endpoint，不得打开 LiveGate。
3. 不得修改 `docs/REVIEW_G4R_INDEPENDENT.md`、G4-R Packet、冻结矩阵/证据字节；新证据用新包/append-only。
4. 不得把 `B03/E5-P04` 的 `UNVERIFIED`、`R-REV6=NOT_RUN`、OCI deselect/环境漂移写成 PASS。
5. 不得触碰 `m1_*`、LeadB 分支、其它 worktree 的冻结范围；不得 push/merge 到 `main`。

## 8. 证据索引

| 内容 | 路径/SHA |
|---|---|
| G4-R 独立 Review（禁改） | `docs/REVIEW_G4R_INDEPENDENT.md`，sha256 `0599856aec247d0834a88a8967db81bd68965578a35eed37dbdf45322068446c` |
| G4-R append-only 勘误 | `docs/M0_G4R_REVIEW_ERRATA.md` |
| G4-R 人类交接 D-01..D-13 | `docs/M0_G4R_HUMAN_HANDOFF.md`，sha256 `c14862ca99ce99db568ebd05a5f288b3cbb666f3a03c423b0ec6914c5e5de2fd` |
| G4-R 残余风险 | `docs/M0_G4R_FINDINGS_AND_DISPOSITION.md` §4 |
| G4-R Packet v2 | 仓库外 gitignored：tree `4300a7c6…`、manifest `fe45d760…`、hashes `e7a67c77…` |
| 旧 G4-H0 人类决策/部署/研究 | `work/m0-g4h0:docs/g4h0/{HUMAN_DECISIONS,HUMAN_DECISIONS_PROPOSED,DEPLOYMENT_RUNBOOK,PROVIDER_CONTRACT_DRAFT,PRICE_AND_USAGE_VERIFICATION,A2_SOURCES}.md`（sha256 见本文件头） |
| 本包部署设计 | `docs/A_NEXT_G4H1_DEPLOYMENT_RUNBOOK.md` |
| 本包 provider/价格适配 | `docs/A_NEXT_PROVIDER_CONTRACT_DRAFT.md`、`docs/A_NEXT_PRICE_AND_USAGE_VERIFICATION.md` |

> **STOP**：本文件不授权任何部署/真实调用；等待维护者逐项签署。当前 `G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
> `LiveGate=BLOCKED`、`M0=DECISION_PENDING` 保持不变。

## 9. 集成阶段 append-only 追加（2026-11-20 集成轮；不覆盖上文）

> 本节为 append-only 追加，不改动上文任何行/签核栏。所有人类决策仍 **UNSIGNED**；状态常量不变。

- **集成身份**：`work/a-next` HEAD `d553bba4e0cee61410f5e08a462c4ead8e7862b9`（base `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；A1 e6f3aa6 / A2 c7eb74e / A0 bf312c8 / hygiene 7d7c0a5 / A6 13e39a4 / registry 748fd0a / packet ce914c1 / rrev6 95a020b + addendum 0735d7b 已按序合并）。Host 全量 1626/1601/7/18；Node 36/36；ruff 变更范围 pass；scanner/ LiveGate / SQLite 见 `docs/A_NEXT_IMPLEMENTATION_REPORT.md` §2。
- **D-14 / BLK-07 / BLK-08 / BLK-09 状态（由 A1/A2 集成）**：代码已合并——P2-01 body `authorization_id` 交叉校验（A1）与 run-level Fake-only admission 接线（A2）；Reviewer batch-3 对 A2 给 **PASS（条件）**，独立 73 passed。**但仍 `UNSIGNED`**：人类签核栏不改；不得把代码合并当作 D-14 决策完成。A2 非阻断备注：被拒 payload 也消耗 ordinal（fail-closed；`effective_max_calls` 计 dispatch 尝试）、`_map_consume_reasons` 子串匹配较脆。
- **A4/R-REV6**：Owner L2 host 级 PASS；Reviewer 独立 OCI 复跑 **NOT_RUN** → **A4-01..03 保持 NOT_RUN**；**A2-01..03 亦 NOT_RUN**（按 Reviewer/Lead 指示）。P2-A4-1 evidence-index v2 路径键修正已由 addendum `0735d7b` 记录（sha `bac7b550…`）。
- **INCIDENT_20261121 披露**：2026-11-20T19:53Z 前后 `artifacts/` 被误删并自哈希验证副本恢复；恢复后 rootfs `25491e45…`、deps `e07729d7…`；**v1 Packet 原始字节 LOST**（不可再核验），v2 仅 HISTORICAL_REFERENCE；不得声明“全程 NO_DRIFT/证据完整”。防再发措施见 `docs/A_NEXT_G4H1_DEPLOYMENT_RUNBOOK.md` §16。
- **既有 history finding**：`fixtures/m1_teacher/judge/sentinels/sentinels.json` 的合成 sentinel 历史 blob（LeadB 线，masked）被 scanner history 模式扫到；属 **EXISTING/ENVIRONMENT**，非 A-NEXT/A2 回归（Reviewer batch-3 三处复现）。
- **OCI filtered 联合回归 NOT_RUN**（等 Lead 批准）；最终 Packet v3 未构建（等集成冻结 SHA/staging 清单）；`B03/E5-P04` 仍 UNVERIFIED；G4-H-01..06 / G5 仍 NOT AUTHORIZED。
- **请维护者决策**（仍为空栏）：D-14 P2-01/P2-02 处置、D-15..D-22、A4/A2 的 NOT_RUN 结论接受与否、incident/EXISTING finding 的处理方式。Agent 不得代填。

> 本节追加不改变任何签核状态；STOP，等待维护者。
