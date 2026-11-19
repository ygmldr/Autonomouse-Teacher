# M0 G4-F — Findings and Disposition（No-Key Closeout）

- **范围**：G4-F F1–F5 的既有残余 + G4-F6 集成/冻结阶段的新发现。
- **性质**：no-key / no-model / no-external-network / no-live。本文件不构成 Live 授权、
  不构成 G4 Full / E5 Full / G4-H/G5/G6 通过。
- **裁定状态**：F1–F5 各自范围 PASS（见各自报告）；F6 候选裁定
  `PASS_FOR_G4F_NO_KEY_CLOSEOUT_SCOPE`，待独立 Reviewer。
- **P0 定义**：可复制的安全/账本反例（权限绕过、可计费出站、Key 泄漏、未授权发送、
  Fee=0/双发送）。**P1**：范围重要未证项。**P2**：记录性/维护性残余。

---

## 0. 结论速览

| 级别 | 数量 | 条目 |
|---|---:|---|
| **P0** | **0** | 本轮未发现 P0 |
| **P1** | 3 | B03/E5-P04 registry 不可导出；F4 candidate-crash/live-Controller 子场景；F5 撤销文档无签名/外部 SIGKILL 窗口 |
| **P2** | 12 | F1 扫描器启发式、B07 未来配置、F3 process-local 视图、Ruff F841、OCI 环境 deselect、rootfs 挂载点副作用等 |

---

## 1. F1 — Secret Scanner 残余

| ID | 残余 | 处置 |
|---|---|---|
| **F1-R1** | 启发式防线，不是泄漏保证；不能替代人工复核/Provider 吊销/托管 Secret Scanning | 保留；scanner 仅作 defense-in-depth |
| **F1-R2** | 通用赋值检测要求值 ≥20 字符；短于 20 的未知名称密钥可能漏报（已知 provider 名阈值 6+） | 保留；已知 provider 名覆盖优先 |
| **F1-R3** | 哨兵 tail 词表是封闭集合；未知但合法的哨兵词会被报告（fail-closed） | 维护时显式补充词表 |
| **F1-R4** | `_is_placeholder()` 的子串/前缀启发式（`fake`/`example`/`sample`/`xxxx` 等）可能误排除极端构造的真实 token | 本轮全历史审计未发现；保留并记录 |
| **F1-R5** | 未增加裸高熵检测器（历史含 635 个 32+ hex 指纹，会产生大量误报） | 有意不做；仅在赋值/URL/Bearer/DB 等上下文检测 |
| **F1-R6** | Basic/URL query/连接串有长度与上下文条件 | 记录；不宣称全覆盖 |
| **F1-R7** | 本轮未验证真实 Provider/billing/Live | 与 G4-H-04 一致，BLOCKED |

本轮复核：`--self-test` PASS、全历史 `467 files / 739 blobs / 165 commits / 0 findings`、
`tests/security` 7/7 PASS。**F1 范围内无新发现**。

---

## 2. F2 — 工具面 / 辅助请求残余

| ID | 残余 | 处置 |
|---|---|---|
| **F2-R1** | 任意未来 DSH 配置/动态注册可能新增 provider/tool 条目；“永不出现辅助请求”不能证明 | B07 仅对冻结配置成立；per-dispatch 校验与 adapter purpose guard 仍是兜底 |
| **F2-R2** | merged entry list 不是 registry；`!!js` 求值后的插件图不可观测 | B03/E5-P04 维持 UNVERIFIED |
| **F2-R3** | title 请求在 IPC `parse_envelope` 层被拒，不写 dispatch journal | 以 raw-UDS 响应 + 账本零增量 + journal 无增量三方面记录 |
| **F2-R4** | origin 身份只取 uid；容器 PID namespace 中 `pid=0` | 与 G3-D/G4 D1-A 语义一致；PID 仅证据 |
| **F2-R5** | journal 写失败不 fail-closed（仅计数） | 安全判定独立于 journal；L2 证据要求 journal 存在 |
| **F2-R6** | 未重跑 G4-C 的完整 crash/replay/quota/watchdog 矩阵 | 本轮 F3 L2 与 F5 覆盖相关控制器路径；G4-C 旧证据未改 |
| **F2-R7** | F2 首次 g4_b 失败为并行 session rootfs 临时非 canonical | 干净重跑通过；本轮每批运行后复核 canonical |

**明确 UNVERIFIED**：B03 merged registry、E5-P04、任意未来配置的 session-title。
**B07 = FALLBACK_ONLY @ frozen config**（2 次 `session/title` 均 `source.kind=fallback`；
3 dispatch = 3 assistant = 3 Receipt = Fake 3）。

---

## 3. F3 — 费用权威残余

| ID | 残余 | 处置 |
|---|---|---|
| **F3-R1** | L2 的 unknown-cost 只覆盖 crash→Broker PENDING；无 usage/timeout/断连的 L2 场景 | L1 host 覆盖；L2 以 crash PENDING 证明 held>0；本轮重跑保持 |
| **F3-R2** | 视图 process-local；Reserve ack 与 intent 落盘之间的极小窗口不可枚举，可能低估 held | Broker 仍以 PENDING 全额占用，不会超卖；未新增 Broker op |
| **F3-R3** | `known_cost_usd` 含 FAILED settlement 的 committed cost | 已按 committed 表述，避免误读 |
| **F3-R4** | 独立 gate 调用以 `hard_call_usd`（0.20）为保守上界，可能提前触发硬顶 | 容器路径始终传 Broker `reserved_cost` |
| **F3-R5** | Broker 不可用时 reconcile 无法建立/校验 hold | 已有 hold 不释放；`reconciled_with_broker=false` 可见 |
| **F3-R6** | `record_broker_status` 信任 stdio/UDS 回复，无独立签名 | 与既有 reservation_status/settle 同一信任边界 |
| **F3-R7** | 4xx 在 gate 视图仍保持 hold 直到 Broker 终态 | 有意保守 |
| **F3-R8** | reconcile 多一次只读 round-trip | 只读、有 deadline，不改恢复状态机 |
| **F3-R9** | L2 证据在 gitignored `artifacts/` | 报告记录 argv/UTC/exit/DB/receipt/SHA |
| **F3-R10** | 未验证真实 Provider/计费/额度 | 与 G4-H-04 一致，BLOCKED |

本轮重跑：host 8/8、L2 7/7（89 checks）；`held>0` 与 Broker PENDING 对齐；
`known==spent==committed`；无二次结算。

---

## 4. F4 — 真实 Resumé 残余

| ID | 残余 | 处置 |
|---|---|---|
| **F4-R1** | context replay 是语义证据（session JSONL + payload length/digest），Fake receipt 只存 `sha256/length`，无字节级包含证明 | 矩阵 `F4-06=UNVERIFIED`；不宣称字节包含 |
| **F4-R2** | Candidate crash + live Controller 子场景未覆盖（负例用 trusted test-only crash hook） | 明确 UNVERIFIED；不声称 DSH 自动重试语义 |
| **F4-R3** | synthetic-only usage/cost；非真实 Provider/TLS/DNS/账单/额度 | LiveGate BLOCKED |
| **F4-R4** | session-log-deepseek 仍 `enabled=false`；未证明任意未来会话无辅助 LLM 调用 | 与 B07 同残余 |
| **F4-R5** | 旧证据绑定 `7000f72`；本轮已在新 stage 重跑并重新绑定 `e7d9296` | 旧证据保留，不覆盖 |
| **F4-R6** | host residual 扫描口径为全 host marker；非本 run 的进程单独记录 | 与 G4-D 口径一致 |

本轮重跑：resume 38/38、crash-resume 22/22、独立审计 19/19 + 12/12；
2 请求独立账本、旧 Attempt 不变、无二次结算、usage 一致。

---

## 5. F5 — 撤销/超时/在途失败残余

| ID | 残余 | 处置 |
|---|---|---|
| **F5-R1** | post-reserve pre-send 真实窗口微秒级；L2 用 env-gated test-only delay 拉宽 | 不跳过任何 checkpoint；L1 用 gate wrapper 不依赖 delay |
| **F5-R2** | 撤销文档 root-owned，但无独立签名/审计链 | 与 policy/admission 同信任边界；P1 残余 |
| **F5-R3** | 删除撤销文件或恢复 `revoked=false` 后，新 `pre_reserve` 会再次放行 | 撤销状态的真实语义；已 consume 的 capability 不复活 |
| **F5-R4** | `timeout-pre-send` 的 dispatch-window 记录缺失（worker 未及落盘） | 账本 0 行/Fake 0/DSH error 仍可证；未为取证改产品路径 |
| **F5-R5** | post-reserve/timeout 恢复时 reconcile 以 `RECEIPT_DOCUMENT_SCHEMA_INVALID` 重写 attempt reason | 仍 `SETTLEMENT_UNCERTAIN`、held>0；原始原因在 gate journal/dispatch-window |
| **F5-R6** | crash 使用 `os._exit(97)` test-only hook，非外部 SIGKILL | 与 G3-D/G4-C 同机制；纳秒窗口未枚举（P1） |
| **F5-R7** | in-flight 撤销的时间顺序为“先观察 receipt 再写文档”，UTC 秒级 | 因果证据成立；无纳秒级断言 |
| **F5-R8** | 未覆盖真实 Provider/计费/供应商侧撤销 | 与 G4-H-04 一致，BLOCKED |
| **F5-R9** | 证据在 gitignored `artifacts/` | 报告记录 argv/UTC/exit/DB/receipt/SHA |
| **F5-R10** | 未验证“撤销后未来配置永不发起请求” | 与本轮无关；B03/E5-P04 不变 |

本轮重跑：13/13、162/162 checks；pre-reserve/pre-send 可停止，wire 后只能保守；
`held=reserved>0`、不 FREE、不重发、不二次结算。

---

## 6. 新发现：G4-F6 集成/冻结

| ID | 级别 | 发现 | 处置 |
|---|---|---|---|
| **F6-01** | **P1（已修复）** | F5 的 `launch_c.G4CLauncher` 新增 argv 属性与 `deadline_ms` 覆盖，使 F4/F2 raw-UDS 在最终 HEAD 构造 Namespace 时 `AttributeError`（真实集成回归） | 最小 additive `getattr` 兼容；F2 evidence runner 增 `--out-dir`；提交 `e7d9296`；RED 日志保留；GREEN：F4 38+22、F2 raw、F5 13/13、F3 7/7 |
| **F6-02** | **P2** | Podman `--rootfs` 会在共享 rootfs 内创建 `/var/tmp` 与 `/evidence` 等挂载点目录，tree hash 漂移 | 每批清理并复核 canonical；host full 与 OCI 不并发；最终 canonical |
| **F6-03** | **P2（未复现）** | “F2 raw-UDS 与 F5 同批 1 次失败”无法复现：F2+F5 批处理 5 连跑 + 全量 host（同 session）均 42/42 与全绿 | 不推测性改测试；记录：最可能的上下文是容器/rootfs 竞态（F6-02）而非 socket/port/tmp 残留；F2 raw 证据 runner 的 preflight 会在有容器时拒绝启动 |
| **F6-04** | **P2** | 固定 OCI 环境无 git/tar/sh 与 root capabilities；本轮新增测试使 deselect 从 G4-E 的 34 变为 43 | 逐项显式分类（含 `test_digest_sidecar_contract`），0 静默 deselect；root replay 覆盖 8 项 |
| **F6-05** | **P2** | adapter Node 测试的 `@deepseek-ai/cordis`/`dsh-llm` 不在 `spikes/.../node_modules`，需用插件 `node_modules` 挂载 | 证据脚本显式挂载；记录复现环境 |
| **F6-06** | **P2** | Ruff `tests/security/test_scan_git_secrets.py:169 F841`（F1 引入的未使用变量） | 未在 F6 修（避免改动 F1 归档测试）；G4-E 口径 scoped 0 findings；repo-wide 1 项新增，按 P2 记录 |
| **F6-07** | **P2** | host full 4 项已知失败（frozen-src、D15 0700-home、host config mode、sandbox 硬编码 PYTHONPATH） | 逐项归因，未 deselect 隐藏；OCI/独立 probe 覆盖其中 3 项 |
| **F6-08** | **P2** | F2 pre-fix 证据与 95ae99a 证据目录需新旧并存 | 保留 `prefix-95ae99a/` 与 `f4-regression-before-fix/`；最终矩阵只引用最终 HEAD 证据 |
| **F6-09** | **P1** | B03/E5-P04 仍无权威 merged registry；F4 字节级/子场景仍 UNVERIFIED | 矩阵 `F2-08`/`F4-06` = UNVERIFIED；不升级 |
| **F6-10** | **P2** | Packet 构建在 docs 提交之后，矩阵不能自包含最终 Packet 的 hash/UTC | Packet manifest/integrity report 记录实际值；矩阵 F6-05 说明 post-commit 构建 |

---

## 7. G4 遗留 P2-1..P2-8 状态

| ID | 状态 | 本轮处置 |
|---|---|---|
| **P2-1** 测试种子可重建推导 | 仍存在（合成、未注册、不可开 LiveGate） | Packet 不复制可重建种子源码；记录 |
| **P2-2** OCI deselect 30/34 不一致 | **已消除** | 本轮 43 项显式清单，含 `test_digest_sidecar_contract`；raw/filtered 计数一致 |
| **P2-3** 产品内 test-only crash/delay hooks | 仍存在（仅 launcher 可信 env 可触发） | 未扩展生产后门；F6 未新增 hook；建议 G4-H 评估移除 |
| **P2-4** P2-RUN-IDENTITY（同 UID 非 per-run 身份） | 仍为维护者待决 | 本轮未改变；如实记录 |
| **P2-5** `worst_case_held_usd` 恒 0 | **已关闭**（F3） | host+L2 的 held>0 重跑确认 |
| **P2-6** DSH resume L2 缺失 | **已关闭**（F4，限域） | 最终 HEAD 重跑 + 审计；子场景仍 UNVERIFIED |
| **P2-7** Packet reviewer=PENDING | 本轮 `reviewer=NOT_ASSIGNED` | 不修改历史 Packet |
| **P2-8** OCI raw failure 数字差异 | 本轮重新分类 | raw 43 / filtered 0；比 G4-E 多出 F1–F5 新测试 |

---

## 8. 队列中未解决项（交付维护者/Reviewer）

1. **独立复核**：`docs/M0_G4F_REVIEW_REQUEST.md` R0–R8；本包不自证。
2. **人类部署**：真实 Key/Provider/价格/额度/Ed25519 信任根/E5 Full（E5-FULL=BLOCKED）。
3. **P2-RUN-IDENTITY / P2-USERNS / P2-DISK**：维护者签收或加 per-run capability/UID。
4. **F4 candidate-crash + live Controller** 子场景与字节级 context 证明。
5. **F5 撤销文档签名链** 与外部 SIGKILL 纳秒窗口枚举。
6. **B03 merged registry** 与 **E5-P04**：在 DSH 提供权威导出或人类接受残余前保持 UNVERIFIED。
7. **F6-06 Ruff F841**：可在后续 docs/test 清理中修复（纯 lint，不改断言）。
8. **F6-03 flake**：若再次出现，按“容器/rootfs 并发”上下文记录并保留失败日志，不静默重跑。

---

## 9. 处置结论

```text
P0 = 0
P1 = 3 (B03/E5-P04; F4 sub-case; F5 unsigned revocation / external SIGKILL)
P2 = 12
LiveGate = BLOCKED; G4-H = NOT_AUTHORIZED; G5 = BLOCKED; G6 = NOT_RUN; M0 = DECISION_PENDING
E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

本文件与矩阵、实现报告、复核请求、人工交接单同一 docs 提交归档；未 push/amend。
