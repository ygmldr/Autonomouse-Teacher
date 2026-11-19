# G4-H0 — 维护者决策表（全部初始未签核）

- **文档 ID**：`G4H0-HUMAN-DECISIONS-v1`
- **生成者**：`a-reviewer`（独立 Reviewer，A4/A-08）
- **性质**：只列**必须由维护者（必要时加独立 Security Reviewer）亲自决定/签核**的事项。
  **所有行初始为 `未签核（UNSIGNED）`**；本表不是授权、不是部署记录、不是 G5 许可，
  Agent 不得代签、不得以 Markdown/Packet 充当授权。
- **基线/对象**：base `3e7afee…`；frozen impl `813e6a6…`；v1 Packet
  `artifacts/review-packet-g4f-e7d92967…`（未改写）；v2 Packet
  `worktrees/m0-g4h0/artifacts/g4h0/packet-v2`（`ffae8b3b…`）。
- **配套阅读**：`docs/g4h0/INDEPENDENT_REVIEW.md`、`docs/g4h0/RISK_DISPOSITION.md`、
  `docs/g4h0/DEPLOYMENT_RUNBOOK.md`、`docs/g4h0/HUMAN_SIGNOFF_TEMPLATE.md`。
- **当前门状态（冻结，未因本表改变）**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、
  `G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、
  `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。

> 签核方式：每个决策行填写 `决定（ACCEPT / FIX / BLOCK / DEFER）` + `签核人` + `UTC 日期` +
> `依据/条件`；未填写行视为未签核，相关门保持 BLOCKED。

## 1. A 线 H0 相关决策

| ID | 决策事项 | Reviewer 建议 | 必须由谁确认 | 当前状态 | 阻断范围 | 证据/参考 |
|---|---|---|---|---|---|---|
| HD-01 | **风险处置总签收**：`RISK_DISPOSITION.md` 16 条 finding 的 FIX/ACCEPT/BLOCK 建议 | 逐条签署，不接受“空白即默认”；`BLOCK` 项（Registry/E5-P04）在 E5-Full/G5 前不得豁免 | 维护者（Security Reviewer 联签） | **未签核** | G4-H1 / G5 / E5-Full | `docs/g4h0/RISK_DISPOSITION.md` §0/§6；`INDEPENDENT_REVIEW.md` §8 |
| HD-02 | **Packet v1 vs v2**：接受哪个作为 H1 依据（v1+errata 或采用/复核 v2；禁止原地修补 v1） | 建议：保留 v1 不可变 + 披露 P2-01；v2 已独立复算自校验一致，可作新版本候选 | 维护者 + 独立 Reviewer | **未签核** | G4-H1 证据基础 | `INDEPENDENT_REVIEW.md` §5；`BASELINE.md` §3 |
| HD-03 | **P2-02**：矩阵 `F2-07` evidence path 修正（append-only errata / 下一版矩阵） | 建议下一版修正路径并加 existence lint；不改冻结矩阵字节 | 维护者 | **未签核** | 证据可复核性（非安全阻断） | `INDEPENDENT_REVIEW.md` §5 |
| HD-04 | **P2-03 修复验收**：接受原子发布修复 + 独立 Reviewer 压力复验（本报告） | 建议 **ACCEPT**（安全契约独立复验成立：0 双消费、loser 全 REPLAYED、0600、0 残留） | 维护者 + A 独立 Reviewer | **未签核** | G4-H1 并发/撤销演练 | `INDEPENDENT_REVIEW.md` §2；`p2_03_*_reviewer.*` |
| HD-05 | **P2-04**：接受删除 F841 一行的测试清理 | 建议 ACCEPT（不影响 scanner 语义；ruff tests/security 已复跑通过） | 维护者 | **未签核** | 无硬阻断 | `INDEPENDENT_REVIEW.md` §3.1 |
| HD-06 | **P2-05**：接受 observation-only dispatch-window 记录（`dispatch_seq=null`，不参与 allow/deny） | 建议 ACCEPT（独立代码/测试复核不改变 fail-closed 与发送语义） | 维护者（Security Reviewer 联签） | **未签核** | G4-H1 窗口审计口径 | `INDEPENDENT_REVIEW.md` §3.2 |
| HD-07 | **P2-06**：接受 recovery 保留原 reason + `|RECOVERY_EVIDENCE:` 追加 | 建议 ACCEPT（状态/held/不重发语义不变；仅证据标签） | 维护者 | **未签核** | G4-H1 事故归因 | `INDEPENDENT_REVIEW.md` §3.3 |
| HD-08 | **P2-07**：zero-key 证据 reasons 1/4 项不一致的处置（接受以 manifest 为权威 / 下一版统一） | 建议下一版统一生成器；当前引用必须同时引用 manifest 4 项 | 维护者 | **未签核** | 证据一致性（非安全阻断） | `INDEPENDENT_REVIEW.md` §5 |
| HD-09 | **P2-08**：Full host 失败集合归因与环境固定（run1/run2 计数差异） | 建议 ACCEPT 为环境类记录 + 后续固定 `config` 权限/clean worktree 归档 | 维护者 | **未签核** | 证据可复现性 | `RISK_DISPOSITION.md` P2-08 |
| HD-10 | **`F-01`（本次新增，high）**：g4_h0 新测试时序缺陷（单独复跑 10/10 失败、目录整跑 14 passed；根因基线 consume ≈332–337ms > 300ms 延迟） | 建议 **FIX（小补丁，只改测试时序）** 后再把 g4_h0 作绿色证据；若决定接受，必须书面写明“以独立压力证据替代该用例” | 维护者 + A 独立 Reviewer | **未签核** | H0 证据可信度；**不阻断安全语义** | `INDEPENDENT_REVIEW.md` §7 F-01；`probe_retry_bound_timing.log` |
| HD-11 | **`F-02`**：use record 目录项未 fsync 的崩溃持久性处置（G4-H1 前修复或明示接受） | 建议 **FIX（H1 前）**：link 后 fsync 目录；H0 无 Key 范围可 DEFER | 维护者（Security Reviewer 联签） | **未签核** | G4-H1 / G5 | `INDEPENDENT_REVIEW.md` §7 F-02 |
| HD-12 | **`F-03`**：Runbook 与 P2-03 修复口径不一致（§4.5 仍写未修复、§4.6 旧机制） | 建议 append-only errata 或下一版 Runbook 更正；不改冻结证据 | 维护者 | **未签核** | 人类签核/部署理解 | `INDEPENDENT_REVIEW.md` §5/§7 F-03 |
| HD-13 | **`F-04/F-05` nit**：FIFO 读阻塞加固、重复 recovery reason 截断 | 建议记为下个加固窗口项；H0 可 ACCEPT 为 nit | 维护者 | **未签核** | 无硬阻断 | `INDEPENDENT_REVIEW.md` §7 F-04/F-05 |

## 2. 安全/部署/授权类决策（全部 BLOCKED，必须人类专属动作）

| ID | 决策事项 | Reviewer 建议 | 必须由谁确认 | 当前状态 | 阻断范围 | 备注 |
|---|---|---|---|---|---|---|
| HD-14 | **DSH Registry / E5-P04 残余**：接受“无权威 merged registry + per-dispatch 白名单补偿控制”，或要求权威导出 | 建议 H0 可 **ACCEPT-with-compensating-control** 并明确签收；**E5-Full/G5 前 BLOCK** | 维护者 + Security Reviewer | **未签核** | E5-P04 / E5-Full / G5 | `RISK_DISPOSITION.md` R-REG-01 |
| HD-15 | **正式受信部署（G4-H1/H2）**：人类签名根、独立 Credential Broker（真实 Key）、受信 Egress、外部 Watchdog、独立 OS 身份 | 本轮**不实施**；需新的独立审批与部署证据，Agent 不代签/不部署 | 维护者（独立运维 + Security Reviewer） | **未签核 / BLOCKED** | G4-H1 / Live | `DEPLOYMENT_RUNBOOK.md` §3/§4/§5；`LIVE_CONTROLLER_SECURITY_DESIGN.md` |
| HD-16 | **E5_PreLive Full 安全审查**：P01–P05 全项真实部署验证 | 保持 **BLOCKED_PENDING_HUMAN_DEPLOYMENT**；无人类部署证据前禁止写 PASS | 维护者 + 独立 Security Reviewer | **未签核 / BLOCKED** | E5-Full | `E5_PRELIVE_FULL_CHECKLIST.md`；当前 `E5-P04=UNVERIFIED`、E5-P05 子项 PARTIAL |
| HD-17 | **单次 G5 真实模型授权**：模型/Key/预算/次数/期限/有效期 | 保持 **BLOCKED**；未来需一次性、有界、可撤销的明确授权；禁止“默认开启” | 维护者 | **未签核 / BLOCKED** | G5 / Live / 计费 | 执行方案 §4/§11；`PRICE_AND_USAGE_VERIFICATION.md`（价格仅研究快照） |
| HD-18 | **Provider 主路由选择**：官方 `deepseek-official/deepseek-flash` vs 第三方 OpenCode Go；以及 egress 白名单/usage 映射 v2 与官方差异 | 建议人类明确选路；官方价格/模型契约已抽查一致，但**路由未获批**、仓库 usage 映射与官方字段存在差异（缺 cache-write tokens 等） | 维护者（+ 安全 Reviewer） | **未签核 / 未批准** | A-05 / G4-H1 / G5 | `PROVIDER_CONTRACT_DRAFT.md` §1/§15；`ROUTE_DECISION.md` |
| HD-19 | **双路由/egress 冲突**：`config` 默认官方主路由声明 vs `egress.py` 仅 opencode-go 第三方白名单、DSH target profile 禁用 `llm-deepseek` | 建议在 H1 前统一为受批准的单一路由与 allowlist，并全量重验；不得把 Synthetic/第三方当官方契约 | 维护者 + Security Reviewer | **未签核** | G4-H1 / G5 | `PROVIDER_CONTRACT_DRAFT.md` §2 L8/L9/L10 |
| HD-20 | **M0 GO / G6 选型** | 维持 **M0=DECISION_PENDING / G6=NOT_RUN**；需独立证据链与人类决定 | 维护者 | **未签核 / BLOCKED** | G6 / M1 接入 | 执行方案 §11 |

## 3. 签核记录（维护者填写；初始全空）

```text
决策人（印刷名 / 角色）：____________________
独立 Security Reviewer（如适用）：____________________
UTC 日期：____________________

[ ] HD-01 风险处置总签收          决定：________  条件：____________________
[ ] HD-02 Packet 版本（v1/v2/新）  决定：________  条件：____________________
[ ] HD-03 P2-02 路径修正           决定：________
[ ] HD-04 P2-03 修复验收           决定：________
[ ] HD-05 P2-04 测试清理           决定：________
[ ] HD-06 P2-05 observation 接受   决定：________
[ ] HD-07 P2-06 reason 保留接受    决定：________
[ ] HD-08 P2-07 zero-key reasons   决定：________
[ ] HD-09 P2-08 归因接受           决定：________
[ ] HD-10 F-01 g4_h0 时序测试      决定：________  条件：____________________
[ ] HD-11 F-02 目录 fsync          决定：________
[ ] HD-12 F-03 Runbook 口径        决定：________
[ ] HD-13 F-04/F-05 nit            决定：________
[ ] HD-14 E5-P04 残余接受/阻断     决定：________  条件：____________________
[ ] HD-15 G4-H1/H2 正式部署        决定：________（本轮默认：不做）
[ ] HD-16 E5-PreLive Full 审查     决定：________（默认：BLOCKED）
[ ] HD-17 单次 G5 授权             决定：________（默认：BLOCKED）
[ ] HD-18 Provider 主路由选择      决定：________
[ ] HD-19 双路由/egress 统一       决定：________
[ ] HD-20 M0 GO / G6               决定：________（默认：DECISION_PENDING/NOT_RUN）

备注/条件：
______________________________________________________________________________
```

> 维护者签字前，以上全部视为未签核；`LiveGate`、E5-Full、G4-H1/H2、G5、G6、M0 GO
> 状态不得改变。任何“已部署 / E5 Full PASS / G5 已获批 / M0 GO”的文字都不被本仓库接受。
