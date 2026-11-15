# G1 独立审计增量复验（B-G1-1 / errata）— task-70

- 日期：2026-11-15 UTC；审计者：`verify2`（非实现者）
- 基线：原 G1 审计 `docs/REVIEW_G1.md` sha256 `3c082720…`（**FAIL_FOR_DECLARED_G1_SCOPE**，唯一阻断 B-G1-1）；本 addendum 不改原报告字节，只追加增量结论与证据。
- 审计对象：B-G1-1 修复冻结 commit **`4d715305022bdbaa437488a7224d33305324f034`**（父 `00df577`；3 files：`live_controller.py` `3f11e4e0…`、`test_live_controller_no_key.py` `0b71f3c7…`、`docs/M0_G1_ERRATA.md` `6f85565c…`）。
- **结论：B-G1-1 功能关闭；G1 最终状态 `PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA_PENDING`**：代码/测试/隔离/离线 PASS 已独立复核，但**冻结 errata 尚未记录 fix commit `4d71530`**（仍写“待冻结”/`PENDING_FREEZE_TASK_69`），不满足 task-70 的 errata 核对项；需 owner 以 post-freeze errata/addendum 更正后，final G1 才可写 `PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA`。**Live/E1–E5/真实 egress/Key/usage/账单仍 BLOCKED；DECISION PENDING，不签发 GO。**

## 1. Git/范围与环境

| 项 | 结果 |
|---|---|
| HEAD | `4d71530`；父 `00df577`；3 files；`git diff --check` 0 |
| 范围 | 仅 `src/autoteacher_m0/security/live_controller.py`、`tests/integration/sandbox/test_live_controller_no_key.py`、`docs/M0_G1_ERRATA.md`；无 accounting/egress/gates/adapter/run_live/历史证据改动 |
| worktree | audit 开始时 clean（仅原 `?? docs/REVIEW_G1.md`）；本 addendum 为新增未跟踪文档，不 commit |
| 独立 stage | `git archive 4d71530`，175 files，tar sha256 `f9f0a74738b7b05155939b042c7c2cd2effe8eaa3b9b93ac220492f05b2bf195` |
| 固定 OCI | rootfs `25491e45…`、deps `e07729d7…`、network none、uid 65534、read-only、cap-drop ALL、no-new-privileges；宿主未跑 pytest/项目代码；容器 absence=0；0 真实 Key/模型/HTTP |
| 未解锁面 | `security/gates.py`/`runtime/dsh_adapter.py`/`scripts/run_live.sh`/`authorization.py` 相对 `00df577` **0 改动**（LiveGate 仍 BLOCKED、adapter `SECURITY_BLOCKED`、run_live exit 3） |

## 2. B-G1-1 修复语义（源码）

- `security/live_controller.py:41-48`：`M0_APPROVED_BUDGET_PER_CALL_CAP_USD=0.20`、`TOTAL_CAP=10.00`、`MAX_CALLS=50`；`BUDGET_POLICY_FIELDS=("scope","per_call_cap_usd","total_cap_usd","max_calls")`。
- `:78-110`：Controller 新增 `expected_budget: BudgetLimits | None`；未显式传入时固定 `BudgetLimits(budget_scope, 0.20, 10.00, 50)`；**scope 来自 Controller 的 `budget_scope`，caps 来自固定策略，不取授权自报**。
- `:112-138`：先按原逻辑解析授权；然后逐字段比较 `ExecutionAuthorization.budget` 与 `self.expected_budget`，不匹配 append `BUDGET_POLICY_MISMATCH:<field>` 并返回 `AuthorizationDecision(False, ..., None)`；Controller 仍 inspect-only/恒 BLOCKED。
- `config/budgets.yaml:3-6`：`hard_total_usd=10.0`、`hard_call_usd=0.20`、`max_live_requests=50`，与常量一致；该文件本身不强制执行（仍由 Controller/未来外部边界负责）。
- `tests/integration/sandbox/test_live_controller_no_key.py:219-245` 保留原 AUTH-08 8 个 EgressPolicy 字段测试；`:248-298` 新增 6 组 budget-only mutation（per_call 0.10/0.05、total 9.00/5.00、max_calls 25/10）、explicit expected budget 对照、approved budget 对照（`authorization_approved=True`、无 BUDGET mismatch、整体仍 BLOCKED）。

## 3. 独立重跑（固定 digest；新 argv/UTC/exit 见 `artifacts/reviewer-g1/addendum-4d71530/raw/commands.jsonl`）

| 用例 | 独立结果 | owner 声称/说明 |
|---|---|---|
| `test_live_controller_no_key.py -k auth08`（新代码） | **16 passed, 5 deselected** | 16 passed（一致；含原 8 + 新 6 + 2 对照） |
| 同选择（旧 `00df577` live_controller + 新测试，fail-first） | **7 failed, 9 passed, 5 deselected**（7 个新 budget/explicit 用例失败） | owner manifest 称 7 failed/1 passed/13 deselected；核心 7 个失败一致，numerator/selection 记录不同（O-G1-1） |
| broader security targeted `-k auth02/auth05/auth06/auth08/wd03/wd04` | **38 passed, 40 deselected** | —（独立补充；原 30 + 8 新） |
| full security+sandbox | **165 passed, 1 skipped** | 165 passed, 1 skipped（一致；skip 为既有 `/input` 探针） |
| Ruff scoped `src scripts tests` | **All checks passed!** | All checks passed（一致） |
| Ruff repo-wide `.` | **All checks passed!** | All checks passed（一致） |
| owner fix evidence | `artifacts/m0-g1-fix-bg11/` 自校验 **40/40 OK**；manifest `9f92b3db…`、evidence `80d2ff59…` | 与 owner 声称一致 |

## 4. 原 AUTH-08 8 字段与批准预算对照

- 原 8 字段（methods/path_prefix/approved_routes/max_tokens/require_reservation/files/images/store）测试全部通过（16 passed 内）。
- 6 组 budget-only mutation：每份授权重新签名（签名有效）、host/path/route 不变，仅改 budget；全部 `authorization_approved=False`、`status=BLOCKED`、`BUDGET_POLICY_MISMATCH:` 出现。
- approved budget 对照：`authorization_approved=True`；`BUDGET_POLICY_MISMATCH` 不出现；`status=BLOCKED`、`boundary_deployed=False`、`ALWAYS_BLOCKED_REASONS` 仍在——**未把整体 BLOCKED 当作预算检测**。
- explicit expected budget 对照：授权仍是批准的 0.20/10.00/50，仅 Controller expected 改为 total 5.00 → 被拒绝，证明比较来自 expected policy，不只来自授权字段变化。
- 结论：**B-G1-1 功能关闭**（旧缺口的具体检测与负测已补）。

## 5. Errata 核对

| 项 | 结果 |
|---|---|
| `docs/M0_G1_ERRATA.md` | sha256 `6f85565c…`，正确记录 G1-SEC `842583d`、G1-ACC `00df577`、V-G1-1/V-G1-2/V-G1-3、B-G1-1 缺口与修复语义 |
| `artifacts/m0-g1-security/manifest-errata.json` | sha256 `9128621e…`；`errata.sha256`（`77948f21…`）自洽（repo-root `sha256sum -c` OK） |
| 旧 G1-SEC 冻结 | manifest `4ef23f69…`、report `0a8f6e18…` 字节未改；旧 evidence **36/36 OK** |
| Accounting errata 引用 | `artifacts/m0-g1-accounting/manifest-errata.json` `55af59d4…` 引用正确；旧 evidence 16/16 OK |
| 历史 G1/G2 证据 | phase5/PR1/PR2/PR3/PR4a/PR4b 等锚未改 |

### V-G1-4（非功能阻断；必须在 final G1 PASS 前更正）
`docs/M0_G1_ERRATA.md:17` 仍写 `B-G1-1 fix | 待冻结（task-69 占位）`，`:55-56` 仍写“等待 task-69 冻结与 task-70 独立复验”；`artifacts/m0-g1-security/manifest-errata.json:24` 仍为 `"b_g1_1_fix": "PENDING_FREEZE_TASK_69"`。冻结 commit `4d71530` 未出现在 errata 中，**不满足 task-70 的“errata 正确记录 fix 4d71530”核对项**。原因是 errata 与 fix 同一 commit，无法在自身内容里写自身 commit hash；应由 owner 以 **post-freeze errata/addendum**（不改旧字节）记录 `4d71530` 与 task-70 结果。代码/测试结论不受影响，但在完成该 errata 前不能写“PASS_WITH_ERRATA”为已完成。

### O-G1-1（信息性证据计数差异）
owner `artifacts/m0-g1-fix-bg11/manifest.json` 记录 fail-first **7 failed / 1 passed / 13 deselected**；我用同一 argv 选择（`auth08 or budget_only or explicit_expected_budget or approved_budget`）在独立旧 stage（`00df577` live_controller + `4d71530` 测试）上得到 **7 failed / 9 passed / 5 deselected**。两者都复现 **7 个失败**（6 组 budget mutation + explicit expected），但 owner 的 1 passed/13 deselected 记录与冻结字节不一致。建议 owner 修正 evidence 计数/选择集说明；不影响 fail-first 真实性或功能结论。

## 6. 残余 UNVERIFIED / BLOCKED（不夸大）

- Live/真实 Key/模型/HTTP、真实 egress/Key Broker、E5-P01–P05 仍 **BLOCKED**；LiveGate/adapter/run_live 未改。
- AUTH-08 仍 inspect-only；无真实 egress/Key Broker；AUTH-02 仍纯 Python 参考实现、非常数时间/未独立密码学审计；WD-03/04 仍 fake/hung 子进程与 synthetic cleanup。
- `TrustedEgressProvenance` 仍是同进程 capability，不是密码学来源认证（V-G1-3，G2 收口）。
- 真实 provider wire/usage/invoice 未观测；provider_invoice 仅离线契约。
- G2 的 A9–A11、broker claim、统一 call ID、真实 SQLite/stdio Broker/FakeProvider 闭环未做。
- **V-G1-4**：errata 尚未记录 fix commit；final G1 PASS_WITH_ERRATA 需 owner 补 post-freeze errata。
- **O-G1-1**：owner fail-first 计数记录与独立复现不一致（核心 7 失败一致）。

## 7. 结论

- **B-G1-1 功能修复 PASS**（独立 16/16 targeted、165/1 full、7 个 fail-first 用例失败、6 组 budget-only mutation + 对照全部通过；expected budget 0.20/10.00/50 与 config 一致，Controller 仍 BLOCKED）。
- **G1 最终状态：`PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA_PENDING`**：只剩 V-G1-4（errata 未记录 `4d71530`）这一**非功能证据阻断**；owner 追加 post-freeze errata 并自洽后，G1 可记为 `PASS_FOR_DECLARED_G1_SCOPE_WITH_ERRATA`。O-G1-1 证据计数差异同步修正。
- **Live/E1–E5/真实 egress/Key/usage/账单仍 BLOCKED；DECISION PENDING；不签发 GO。**

## 8. 证据索引

- 本 addendum：`docs/REVIEW_G1_ADDENDUM.md`；原 `docs/REVIEW_G1.md` 未改（`3c082720…`）。
- 独立 stage：`artifacts/reviewer-g1/addendum-4d71530/stage.tar`（`f9f0a747…`，175 files）+ `stage/`；fail-first 旧 stage `stage-old/`（`00df577` live_controller + `4d71530` tests）。
- 运行/日志：`artifacts/reviewer-g1/addendum-4d71530/logs/`、`raw/commands.jsonl`。
- 审计 manifest/evidence：`artifacts/reviewer-g1/addendum-4d71530/manifest.json`、`evidence.sha256`。
- owner fix 证据：`artifacts/m0-g1-fix-bg11/`（manifest `9f92b3db…`、evidence `80d2ff59…`，40/40 OK）。
