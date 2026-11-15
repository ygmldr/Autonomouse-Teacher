# M0 G0–G2 closeout 报告 — 审计归档与状态汇总（离线/无 Key）

- 任务：`task-76`（G2 docs-only 收口）；日期：2026-11-15 UTC；当前实现 HEAD：`32bea5b`
- 总体判定：**DECISION PENDING**；G0/G1/G2 离线完成并冻结；**G3+ 未授权**；Live/E1–E5/LiveGate/真实 Key/egress/usage/账单仍 **BLOCKED**；**不签发 GO**。
- 本文件只归档已发生事实；离线 PASS 不等于 Live PASS。

## 1. Commit 链（实际历史）

| 阶段 | commit | 说明 |
|---|---|---|
| G0 前实现基线 | `87f44e1227f38e454c4dc418b0e289df85721fb5` | V-PR3-1 Ruff hygiene；G1 前基线，**不是 G1/G2 实现** |
| G0 docs（历史基线） | `e8b6e45b19d9001231323c76bc71fa4886be3439` | M0 收尾基线/v0.5 归档（PR0 docs） |
| G0 docs（v0.6 手册） | `abbc6bc` | execution validation review playbook v0.6 |
| G0 docs（基线/blockers/裁定） | `92c9f71` | `M0_G0_BASELINE`/`OPEN_BLOCKERS`/`M0_G0_DECISIONS` |
| G1-SEC | `842583d` | security/authorization/watchdog 确定性修复（task-60） |
| G1-ACC | `00df577` | observation usage provenance/conservative bounds（task-64） |
| G1 fix B-G1-1 | `4d71530` | AUTH-08 budget policy gap（task-68） |
| G1 docs/errata | `70cb574` | G1 audit、errata、closure 归档 |
| G2-BROKER | `ada8e28` | canonical CallIdentity + persistent dispatch claim（task-74，父 `70cb574`） |
| G2-EGRESS | `32bea5b` | egress claim gate + closed-loop integration（task-66，父 `ada8e28`） |
| G2 docs 收口 | 本提交（见 git log） | `REVIEW_G2` + 本报告 + ROADMAP/README |

当前 HEAD `32bea5b`（G2 实现最终 commit）；G2 docs 收口 commit 为父 `32bea5b` 的下一个 docs-only commit。

## 2. G0/G1/G2 审计结论

| Gate | 结论 | 关键证据 |
|---|---|---|
| G0 | **通过 Lead 审计**（baseline/source inventory 接受；映射/证据边界准确；V-G0 无阻断） | baseline `M0_G0_BASELINE.md` `0923d002…`、blockers `OPEN_BLOCKERS.md` `0002beb1…`、`artifacts/g0-baseline/manifest.json` `6634c004…`（evidence 2/2 OK）；裁定 `M0_G0_DECISIONS.md` |
| G1 | **`PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA`**（B-G1-1 已关闭；V-G1-1/V-G1-2/V-G1-4、O-G1-1 已记录） | `docs/REVIEW_G1.md` `3c082720…`、`docs/REVIEW_G1_ADDENDUM.md` `6618edfd…`、`docs/M0_G1_ERRATA_POSTFREEZE.md` `9ba17660…`；G1 evidence 36/36、fix 40/40、复审 370/370 |
| G2 | **`PASS_FOR_DECLARED_G2_SCOPE`**（仅离线/无 Key；条件性遗留 G2-L1） | `docs/REVIEW_G2.md` `dc71fda8…`；`artifacts/reviewer-g2/manifest.json` `d4b8f495…`、evidence 200/200；owner broker manifest `c237d950…`（26/26）、integration manifest `1b59180e…`（40/40） |

## 3. G2 实现摘要（ONLY offline / no-key）

- **ADR-002 canonical CallIdentity**：`call-<48hex>`（run_id/logical_step/attempt_index/request_digest）由可信 Controller 在 reserve 前生成；`eg-` 仅 legacy 日志字段，不参与 claim/settle。
- **持久原子 dispatch claim**：broker v1 additive `claim` op；SQLite 事务内唯一 claim 表；重复/同 call 异 digest/同 reservation 第二 call/未绑定/route 不符 → 0 dispatch；v1 旧客户端兼容。
- **Egress claim gate**：`claim_dispatch()/require_claim()` 在 dispatch 前调用真实 stdio Broker claim；失败 → `CLAIM_REJECTED:<code>` 且不发包；FakeProvider 无 socket。
- **离线闭环**：真实 SQLite 文件 + 真实 stdio Broker 子进程 + in-process scripted FakeProvider；reserve→claim→fake send→trusted provenance→observation→settle；INT-01…INT-18 均有定向测试通过（42 passed targeted；全量回归 367 passed / 1 skipped；Ruff scoped/repo-wide All checks passed）。
- **G2-L1（条件性遗留，不阻断当前声明 G2）**：legacy `EgressBoundary.authorize()/require()` 与无 claimer 的 `MockEgressTransport` 回退路径仍是公开 API；当前 `src/` 无生产调用点（仅 scripts/tests），但 **G3/Live 前必须收口**：强制 claimer、私有化/移除 legacy fallback，并审计所有调用点。不得写成“所有 egress 已强制 claim”。
- **V-G2-1（证据身份，非阻断）**：broker manifest `implementation_sha=null`；integration manifest `baseline_head=ada8e28`（G2-BROKER freeze，不是最终 HEAD `32bea5b`）；实际 G2 实现为 `ada8e28`（broker）+ `32bea5b`（egress）；G3 review packet 应绑 `32bea5b`，旧字节不重写。

## 4. 残余 UNVERIFIED / BLOCKED（不夸大）

1. 本地 claim 不是远端/provider **exactly-once**；只证明本机持久 claim 的唯一性；真实 wire/usage/invoice 未验证。
2. claim granted 但发送前崩溃/ACK lost 保持 CLAIMED/pending（保守，无退款/自动重试）；**独立 reconciliation 未实现**。
3. `TrustedEgressProvenance` 是同进程 capability（V-G1-3），不是密码学来源认证；真实可信 egress/Key Broker 未部署、import 点未审计。
4. FakeProvider 是 scripted synthetic fixture；OCI 禁 socket，`network_attempts=0`；不是真实模型/HTTP/账单证据。
5. broker v1 兼容仅由离线测试证明；真实旧客户端/远程 broker 未验证。
6. G2-L1 legacy descriptor 路径未强制 claim（见 §3）。
7. Live/E1–E5/LiveGate、真实 Key/egress/usage/账单仍 **BLOCKED**；G3+ 未授权，必须维护者人工批准与外部边界；总体 **DECISION PENDING**，不签发 GO。

## 5. OpenCode Go / 预算 / 凭据边界

- OpenCode Go **凭据未使用**；0 真实 Key/模型/HTTP 调用；本 closeout 未读取 `/root/.config/autoteacher`。
- 已批准内部测试预算（如适用）：US$3 soft / US$10 hard / ≤50 次 Live 调用；本 G0–G2 全程 **0 消耗**，OpenCode Go 仍仅 INTERNAL-TEST-ONLY，未执行任何 smoke/真实调用。
- 任何 G3+/Live 动作需维护者另行授权；Agent 不得自批或自签 GO。

## 6. 参考

- [G2 审计](<REVIEW_G2.md>) `dc71fda8…`；[G1 审计](<REVIEW_G1.md>) `3c082720…` + [addendum](<REVIEW_G1_ADDENDUM.md>) `6618edfd…` + [errata](<M0_G1_ERRATA_POSTFREEZE.md>) `9ba17660…`
- [G0 baseline](<M0_G0_BASELINE.md>) `0923d002…`、[blockers](<OPEN_BLOCKERS.md>) `0002beb1…`、[G0 decisions](<M0_G0_DECISIONS.md>)
- [G2-BROKER report](<M0_G2_BROKER_REPORT.md>) `d262514b…`、[ADR-002](<ADR-002-unified-call-identity.md>) `22d277d1…`、[G2 integration report](<M0_G2_INTEGRATION_REPORT.md>) `824aef3d…`
- 证据目录（gitignored，不提交）：`artifacts/g0-baseline/`、`artifacts/m0-g1-*/`、`artifacts/m0-g2-broker/`、`artifacts/m0-g2-integration/`、`artifacts/reviewer-g1/`、`artifacts/reviewer-g2/`
