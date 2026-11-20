# A-NEXT A-PR1 / A2 — Run-level 一次性授权真正接线（实现报告，no-key）

- **文档 ID**：`A-NEXT-A-PR1-A2-REPORT-v1`
- **状态**：`IMPLEMENTED_HOST_L1`（test-only / no-key）；**L2 未运行**（`A2-01..A2-03` L2 由 A-PR3 独占窗口执行）；`PENDING_INDEPENDENT_REVIEW`
- **分支**：`feat/a-next-run-admission`
- **设计 ADR**：`d7bbf3b`（`docs/A_NEXT_RUN_ADMISSION_DESIGN.md`，Reviewer 裁定 PASS 条件式 C2–C8；rebase 前为 `960724b`）
- **ADR errata**：`6556967`（行号基准/历史字符串澄清，append-only；rebase 前 `e80bc8b`）
- **实现提交**：`07eccb9`（`feat(a-next): wire run-level execution authorization admission`；rebase 前 `1f25552`）
- **A1 基座**：`e6f3aa6`（`fix/a-next-auth-record`；`authorization.py` net +51/−18，A1 所有）
- **测试补充提交**：`ff44ef6`（R-25）+ 本 commit（R-07 真实文件用例与 A1 合体核对）
- **本报告提交**：见本 commit（rebase 到 A1 之后）
- **基线**：`fd1d3a6` + **rebase onto A1 `e6f3aa6`**；`src/` 相对 A1 只改 `bridge/controller.py`、新增 `bridge/run_admission.py`，`authorization.py` 零额外改动
- **不变量**：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT` 全部未变。0 真实 Key / Provider / HTTP / Live。`authorization.py`（A1 所有）、`gates.py`、`scripts/run_live.sh`、`cli.py`、`dsh_adapter.py` 零 diff。

---

## 1. 实现内容

### 1.1 新增 `src/autoteacher_m0/bridge/run_admission.py`（trusted-domain，离线）

| 组件 | 说明 |
|---|---|
| `derive_run_epoch()` | `"run-" + sha256(canonical{schema, admission_id, admission_nonce, run_id})[:32]`；同一 Admission → 同一 epoch（重启=REPLAYED），不同 Run → 不同 epoch（复用=EPOCH_MISMATCH） |
| `RunIdentity` | 校验 run_id/32-hex admission_id/32-hex nonce/64-hex admission_sha256/派生 epoch；不匹配即 `RUN_ADMISSION_IDENTITY_INVALID` |
| `build_run_identity()` | 从受信 Admission 文档构建 identity，并复核文件 sha256（load 后文件被改 → fail-closed） |
| `begin_run_admission()` | **唯一 run-level 入口**：Admission sha 校验 → observed/expected bindings 摘要 → tool schema digest → two-phase intent 审计 → `load_execution_authorization(pre_start)` → C2 文件 digest 复核 → `consume_execution_authorization(pre_reserve)` **恰一次** → C2 post-consume identity/epoch/record-path 断言 → 授权文件二次 digest 复核 → outcome 审计 → 返回 `ACTIVE` context。任何拒绝抛稳定 code + tri-state consumed；调用方不得启动 Broker/Fake/Controller |
| `RunAdmissionContext` | 受信 principal：`ensure_startable()`（state/PID/deadline）、`begin_dispatch()`/`consume_dispatch()`（in-process identity registry、单次、默认拒绝、跨 Run 不可复用）、`close()` |
| `DispatchAdmissionToken` | frozen dataclass；无 JSON 构造路径；字段绑定 run_id/run_epoch/authorization_id/dispatch_ordinal/scope/call_id/prepared_digest/payload_digest/route/model/TTL/principal nonce digest |
| `RunAdmissionJournal` | append-only JSONL：`O_APPEND|O_CREAT|O_NOFOLLOW|O_CLOEXEC` 0600 + 逐条 fsync + 目录 fsync；封闭 allowlist；两阶段 `intent`/`outcome` + `dispatch_denied`/`final`；写失败 = fail-closed。**不含 Key/原始 prompt/messages/tool args/session 文本**（只记 bounded 标识符、枚举、hex 摘要；call_id 只记 sha256） |

### 1.2 最小接线 `src/autoteacher_m0/bridge/controller.py`（+78/−4）

- `main(..., run_admission=None)`：
  - `run_admission_required`（config 可选 bool）**fail-closed**：required 但无 context → stderr `RUN_ADMISSION_REQUIRED` + exit **6**；context 类型/active/owner-PID 校验失败 → stderr `RUN_ADMISSION_INACTIVE` + exit **7**。两者都发生在 **socket/Broker/Fake/AttemptJournal 之前**。
  - context 传入 → `TrustedController(..., run_admission=context)`。
- `TrustedController.__init__(..., run_admission=None)`：默认 `None` 保持冻结行为逐字节不变。
- `_handle_payload_serial`：`_prepare_checked` 成功后（revocation/identity-claim/**Reserve 之前**）：
  1. `begin_dispatch(...)` + `consume_dispatch(...)`；
  2. 拒绝 → dispatch journal 记录 `run_admission.denial` 精确 code（wire code 仍为冻结的 `ADMISSION_SELF_AUTH_DENIED`）→ `BridgeError`；
  3. 成功 → dispatch journal 记录 `run_admission: {run_id, run_epoch, authorization_id, dispatch_ordinal, token_consumed: true, denial: null}`。
- **C5**：全文件仅 1 处 `begin_dispatch(` 与 1 处 `consume_dispatch(`，均在该 dispatch 路径、且在唯一的 `_broker_reserve(task_id=` 调用之前；一次 payload 至多 1 token（结构测试 `test_c7_controller_diff_has_no_new_bypass_or_network`）。

### 1.3 `scripts/a_next/admission/`（test-only）

- `trusted_launcher.py`：受信 Launcher harness。顺序 = load Admission → `build_run_identity` → `begin_run_admission` → 失败 exit 20（stdout JSON DENY）/成功 `--dry-run` 只返回 ALLOW、否则调用 `controller.main(..., run_admission=context, run_admission_required=...)`。不读 Key/环境，不触网。
- `l2_admission_cases.py`：A-PR3 独占窗口可调用的 A2 L2 用例驱动（A2-01 首次 ALLOW、A2-02 同 Run 重启 REPLAYED、A2-03 不同 Run 复用同授权 EPOCH_MISMATCH；同一全局 use log；输出 `a2-admission-cases.jsonl`）。本 PR 只用 synthetic fixture 在 host 验证脚本可运行（`test_l2_case_runner_host_synthetic`）；**真实 L2 证据仍 NOT_RUN**。

### 1.4 `tests/integration/a_next_admission/`（68 passed）

覆盖矩阵 R-01..R-26、token 负例、controller 接线、launcher subprocess、审计 allowlist、静态边界；详见 §4/§6。

---

## 2. 执行顺序（实现后的真实调用链）

```text
Trusted Launcher (scripts/a_next/admission/trusted_launcher.py, test-only)
 1. load_admission() + build_run_identity()        # Admission sha256 校验
 2. begin_run_admission()                          # ★ 一次性消费
    ├─ two-phase audit: intent
    ├─ load_execution_authorization(checkpoint=pre_start)   # 验签/绑定/route/tools/期限/撤销
    ├─ consume_execution_authorization(run_epoch)  # tmp→fsync→link→dir fsync（A1/P2-03 机制）
    ├─ C2: use.authorization_id/run_epoch/record_path 断言 + 授权文件 digest 复核
    └─ two-phase audit: outcome
 3. 仅 ALLOW → controller.main(config, run_admission=context,
                                run_admission_required=<config>)
    ├─ required/inactive 检查（在 socket/Broker/Fake 之前，exit 6/7）
    ├─ start Broker → Fake → AttemptJournal → TrustedController
    └─ serve
 每 dispatch（Controller 内）：
    _prepare_checked → ★ begin_dispatch+consume_dispatch（拒绝→0 新 Reserve/0 Fake/0 Attempt）
      → 既有 revocation gate → 既有 identity claim → 唯一 Broker Reserve → Claim
      → TrustedSendGate.authorize/consume → Fake（既有）
```

任何 run admission 拒绝路径：**Broker 进程未创建**（launcher 在 `controller.main` 之前退出），
因此在结构上 `0 Reserve / 0 Fake / 0 Attempt`；dispatch token 拒绝路径：Broker 已启动但
`requests/reservations/attempts/fake=0`（测试断言）。

---

## 3. Reviewer 条件 C2–C8 逐条落地映射

| 条件 | 实现/证据 | 验证 |
|---|---|---|
| **C2 TOCTOU** | `begin_run_admission` 在 consume 返回后断言 `use.authorization_id == authorization.authorization_id`、`use.run_epoch == identity.run_epoch`、use record 文件名 == `sha256(authorization_id)+".json"`；不符 → `RUN_ADMISSION_AUTHORIZATION_DRIFT` fail-closed（`consumed=UNKNOWN`，不发送），审计记录 `authorization_file_sha256`；另在 load 前后与 consume 后两次复核授权文件 sha256（变化 → 同一 DRIFT） | `test_c2_post_consume_authorization_id_drift`、`test_c2_post_consume_epoch_drift_detected`、`test_c2_authorization_file_changed_after_consume`（均断言 code=DRIFT、consumed=UNKNOWN、record 含 authorization_file_sha256） |
| **C3 opt-in + required fail-closed + G4-H1 BLOCKER** | 默认 `run_admission=None` 行为逐字节不变（新增仅 `if self.run_admission is not None` 分支；F2 29 passed/1 skipped、g4_a 223 passed、g4_f5 12 passed）；`run_admission_required` config 实现 required-but-missing（exit 6）与 inactive/foreign context（exit 7）**在 socket/Broker 之前**；BLOCKER 写入本报告 §8 | `test_required_mode_without_context_refuses_before_start`、`test_required_mode_with_inactive_context_refuses_before_start`、`test_required_mode_rejects_foreign_object`、`test_default_path_without_run_admission_is_unchanged` |
| **C4 crash-after-consume restart** | 同 Run 重启 → `AUTHORIZATION_REPLAYED` → `RUN_ADMISSION_ALREADY_CONSUMED`（consumed=NO）；use record 永不清理/改写；launcher 拒绝路径不启动 Broker；人工对账记录在 §7 | `test_r05_same_run_restart_is_replay`（断言 final record 原样保留、epoch 一致）、`test_denied_launcher_never_creates_broker_or_attempt_db` |
| **C5 max_attempts 重试不多耗 token** | 单 dispatch 路径恰好一次 `begin_dispatch`+`consume_dispatch`（AST/文本结构测试），且位于唯一 Reserve 之前；成功 dispatch `_consumed_ordinals == {1}`；frozen Admission 合同将 max_attempts 固定为 1，故“内部重试 ≠ 额外 token”按结构证明 | `test_c5_one_token_per_payload_payload_count`、`test_c7_controller_diff_has_no_new_bypass_or_network` |
| **C6 R-01..R-26 逐行测试 + 结构断言** | §4 表逐行映射；launcher-deny 用真实 subprocess 并断言 Broker socket/attempt DB 未创建；token-deny 断言 `requests/reservations/attempts/fake receipt=0`；R-25 使用 frozen `AttemptJournal.register_admission` guard | `tests/integration/a_next_admission` 68 passed；`test_r19_token_denial_creates_zero_ledger_traces`、`test_denied_launcher_never_creates_broker_or_attempt_db`、`test_r25_admission_document_replay_is_rejected` |
| **C7 no-key 静态/负例 + 默认回归** | `authorization.py/gates.py/run_live.sh/cli.py/dsh_adapter.py` 零 diff（`git diff --name-only fd1d3a6 050411a -- …` = 0）；新增代码静态扫描无 socket/requests/urllib/http/deepseek_harness/os.environ/getenv/API_KEY；LiveGate inspect=BLOCKED；CLI `smoke --live`=exit 3；默认路径 F2/g4_a/g4_f5 全绿 | `test_c7_protected_files_have_zero_diff`、`test_c7_new_code_has_no_network_or_key_env`、`test_c7_live_gate_is_blocked`、`test_c7_cli_smoke_live_still_exits_3`、`test_c7_run_live_script_unchanged_and_closed` |
| **C8 L2 不跑 / 用例脚本给 A-PR3** | A2-01..A2-03 保持 **NOT_RUN**；本 PR 提供 `scripts/a_next/admission/l2_admission_cases.py`（同一全局 use log 的 A2-01/02/03；host synthetic 验证脚本逻辑）；真实 OCI 窗口由 A-PR3 独占执行并持证 | `test_l2_case_runner_host_synthetic`（host synthetic only）；报告 §6 声明 L2 NOT_RUN |

---

## 4. 拒绝矩阵 → 测试映射（R-01..R-26）

| # | 场景 | 测试 | 断言 |
|---|---|---|---|
| R-01 | 伪造签名 | `test_r01_forged_signature` | `RUN_ADMISSION_AUTHORIZATION_INVALID`，consumed=NO，0 use record |
| R-02 | 未知 key_id | `test_r02_unknown_approval_key` | 同上 |
| R-03 | 过期/未生效 | `test_r03_expired_and_not_yet_valid` | 同上 |
| R-04 | revoked_ids 命中 | `test_r04_revoked_authorization` | 同上 |
| R-05 | 同 Run 重启重放 | `test_r05_same_run_restart_is_replay` | `ALREADY_CONSUMED`，consumed=NO，final 保留 |
| R-06 | 别的 Run 复用同授权 | `test_r06_other_run_epoch_mismatch` | `EPOCH_MISMATCH`，consumed=NO，仅 1 final |
| R-07 | body id 与 record/期望 authorization 不符（A1/P2-01） | **A1 已合入**：`test_r07_body_id_crosscheck.py` 4 个真实文件用例（真实 consume 后把 body id 改为外来 id / body id 与存储名不符 / 非法 consumed_utc / 未篡改记录仍为 true replay 对照）+ 原 stable-code 参数化用例 | 全部 `RUN_ADMISSION_RECORD_INVALID`（consumed=NO，非 REPLAYED/EPOCH_MISMATCH），final 记录不清理；对照用例仍是 `ALREADY_CONSUMED` |
| R-08 | record 损坏/截断/多 key/非法 schema | `test_r07_r08_invalid_or_replaced_use_record`（4 参数） | `RECORD_INVALID`，consumed=NO |
| R-09 | symlink / hardlink(nlink>2) | `test_r09_symlink_and_hardlinked_use_record` | `RECORD_INVALID` |
| R-10 | 并发 8 consumers | `test_r10_concurrent_consumers_exactly_one_wins` | 恰 1 ALLOW + 7 `ALREADY_CONSUMED`；1 条 use record |
| R-11 | link 失败（真实 OSError 注入） | `test_r11_link_failure_is_not_consumed_then_retry_succeeds` | `LOG_UNAVAILABLE`，consumed=NO；恢复后重试成功 |
| R-12 | crash-before-link | `test_r12_crash_before_link_leaves_no_record_then_retry_succeeds` | 无 final；重试成功（未消费） |
| R-13 | 目录 fsync 失败 | `test_r13_durability_unknown_is_tri_state_and_replay_afterwards` | `DURABILITY_UNKNOWN`，consumed=UNKNOWN；final 存在；后续=REPLAYED |
| R-14 | use log full | `test_r14_use_log_full_is_fail_closed` | `LOG_UNAVAILABLE`，consumed=NO |
| R-15 | 预算不一致/上界 | `test_r15_budget_scope_mismatch_denied`、`test_begin_effective_calls_use_minimum` | AUTHORIZATION_INVALID / `effective_max_calls=min` |
| R-16 | Run deadline 超限 | `test_r20_deadline_exceeded_at_dispatch` | `RUN_DEADLINE_EXCEEDED`（dispatch 前，0 Reserve） |
| R-17 | binding pre_start 漂移 | `test_r17_binding_drift_pre_start` | AUTHORIZATION_INVALID（含 `*_MISMATCH` reasons） |
| R-18 | tool schema digest/名称漂移 | `test_r18_tool_schema_digest_drift`、`test_begin_requires_valid_limits_and_tool_schemas` | `TOOL_SCHEMA_MISMATCH`，consumed=NO |
| R-19 | 无/伪造 JSON/复制 token（controller 层） | `test_r19_candidate_json_and_copied_token_are_unknown`、`test_r19_token_denial_creates_zero_ledger_traces` | `UNKNOWN`；controller deny → `requests/reservations/attempts/receipt=0` |
| R-20 | token 重放/跨 Run/绑定/过期/跨进程/闭上下文/预算 | `test_token_happy_path_and_replay`、`test_r19_token_from_another_context_is_unknown`、`test_r20_binding_mismatch_is_denied`、`test_r20_expired_token_is_denied`、`test_r20_closed_context_cannot_mint_or_consume`、`test_r20_ordinal_budget_bound`、`test_r20_foreign_process_context_is_not_startable` | 对应稳定 code；0 发送 |
| R-21 | token OK 但 Broker Reserve 拒绝（max_requests） | `test_r21_token_ok_but_broker_reserve_denied` | 第 2 dispatch 被拒，requests=1、attempts=1、token 已花 |
| R-22 | post-Reserve 撤销/超时（既有 F5 路径） | **既有行为回归**：`tests/integration/g4_f5` 12 passed；`test_audit_records_are_allowlisted_and_content_free` 断言 `attempt_db_touched=false`/`historical_holds_modified=false`；run admission 模块不 import Attempt/Broker | 历史 hold 只读、不改写；A2 不介入该路径 |
| R-23 | 审计不可写/满 | `test_r23_audit_journal_unavailable`、`test_r23_audit_full_after_consume_is_tri_state` | `AUDIT_UNAVAILABLE`；consume 前失败=NO、outcome 失败=YES（tri-state） |
| R-24 | 成功消费后 crash-before-Broker 重启 | `test_r05_same_run_restart_is_replay`、`test_denied_launcher_never_creates_broker_or_attempt_db` | REPLAYED + Broker/socket/attempt 不存在 |
| R-25 | Admission 文档重放 | `test_r25_admission_document_replay_is_rejected` | 既有 `ADMISSION_REPLAYED` 仍生效 |
| R-26 | Markdown/自签 JSON/环境变量/`--live` | `test_r26_markdown_or_self_signed_document`、`test_c7_cli_smoke_live_still_exits_3`、`test_c7_new_code_has_no_network_or_key_env` | AUTHORIZATION_INVALID / exit 3 / 无 Key-env |

---

## 5. 设计开放问题（Reviewer Q2–Q6）最终取舍

| Q | 最终取舍 | 理由 |
|---|---|---|
| Q1 opt-in vs 强制 | 本轮 **opt-in 默认**（无回归）+ 实现 `run_admission_required` fail-closed 模式（exit 6/7）+ 本报告 §8 G4-H1 BLOCKER | Lead/Reviewer 已裁定；required 模式已可用且测试覆盖 |
| Q2 epoch 公式 | 维持 `admission_id + admission_nonce + run_id` → `run-<32hex>`；不绑定 authorization_id | 崩溃重启分类（同 Run=REPLAYED、跨 Run=EPOCH_MISMATCH）已证明；绑定 authorization_id 会把“换授权”变成新 Run，语义更差 |
| Q3 token mint/consume 位置 | mint+consume 均置于 `_prepare_checked` 之后、revocation/identity-claim/**Reserve** 之前；payload_digest 绑定 `prepared.request_digest`，最终 wire payload 仍由既有 `TrustedSendGate` 单独绑定 | 结构上保证 token 拒绝 → 0 Reserve/0 Attempt；避免依赖尚未构造的 fake payload |
| Q4 审计两阶段 | 实现 intent+outcome 两阶段；outcome 写失败= fail-closed + tri-state（consumed=YES 可能已花） | 崩溃可审计；R-23 测试 tri-state |
| Q5 本地预算校验 | 只做启动时一致性 + `effective_max_calls=min(auth,admission)` + Run deadline；金额/单次/总预算仍由 Broker 权威 | 不复制价格/账本逻辑；R-15/R-16/R-21 覆盖 |
| Q6 A1 校验顺序 | A2 不 import A1 私有函数；只依赖公共 consume 与稳定 reason 集合；body-id 校验由 A1 在 `_read_use_record` 内完成且必须 INVALID（非 REPLAYED） | `authorization.py` 零 diff；A1 合入后 rebase 集成（§9）；R-07 先按 stable-code 映射，A1 落地后补真实文件用例 |
| Q7 L2 归属 | L2 归 A-PR3 独占窗口；本 PR 只交 host/L1 + `scripts/a_next/admission/l2_admission_cases.py` 用例脚本；A2-01..A2-03 = **NOT_RUN** | 按 Lead 裁定；不占用 OCI 窗口 |

---

## 6. 测试证据（host/L1；命令与计数）

工作目录 `worktrees/a-next-run-admission`，环境 `PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1`，解释器
`/root/Autonomous Teacher/.venv/bin/python`。

| 命令 | 结果 |
|---|---|
| `pytest tests/integration/a_next_admission -q -p no:cacheprovider` | **73 passed**（rebase + R-07 真实文件用例后） |
| `pytest tests/integration/a_next_auth -q …`（A1 套件，合体后回归） | **39 passed** |
| `pytest tests/integration/g4_a -q …` | 223 passed |
| `pytest tests/integration/g4_f5 -q …` | 12 passed |
| `pytest tests/integration/g4_f2 -q …` | 29 passed, 1 skipped（默认 opt-in 回归） |
| `pytest tests/g4r_packet -q …` | 11 passed, 1 skipped |
| `pytest tests/security -q …` | 6 passed, **1 pre-existing failure**（见下） |
| `pytest tests/security -q … --deselect tests/security/test_scan_git_secrets.py::test_repository_worktree_and_history_is_clean` | 6 passed, 1 deselected |
| `pytest tests/unit -q …` | 396 passed |
| `pytest tests --collect-only -q …` | **1532 tests collected, exit 0** |
| `ruff check <changed scope>` | **All checks passed**（0） |
| `git diff --name-only fd1d3a6 050411a -- authorization.py gates.py run_live.sh cli.py dsh_adapter.py` | 0 行（零 diff） |

**合计（不含 pre-existing security history finding）：789 passed / 2 skipped**。

**pre-existing failure 证明（非本 PR 引入）**：`tests/security/test_scan_git_secrets.py::
test_repository_worktree_and_history_is_clean` 在 **基线 `fd1d3a6` 的独立 worktree**上以同一 scanner
复现完全相同 finding（history 中 `fixtures/m1_teacher/judge/sentinels/sentinels.json:101` 的
`SENTINEL_SECRET_TOKEN=…`，来源 LeadB m1_teacher 历史；本 PR 未改 history、未改 fixtures）。证据：
`artifacts/a-next/run-admission/20261120T201321Z/baseline-fd1d3a6-secret-scan.json` 与
`reg-tests_security.log`。该 finding 与 A2 实现文件/路径无关，本 PR 不修 m1 历史。

**证据目录（gitignored）**：`artifacts/a-next/run-admission/20261120T201321Z/`
（`a2-collect.log`、`a2-collect-final.log`、`a2-regression.log`、`reg-tests_*.log`、
`baseline-fd1d3a6-secret-scan.json`）。

---

## 7. 安全与不记录内容

- run admission 审计 allowlist：identity/epoch/admission digest/authorization id/approver/key_id/
  payload digest/bindings digest/tool_set digest/route/budget/期限/decision/reject_reasons/
  consumed(tri-state)/use_record sha/durability/historical_holds_observed=0/
  historical_holds_modified=false/attempt_db_touched=false/external_network_calls=0/
  real_model_calls=0/provider_keys_seen=0；**不含 Key/原始 prompt/messages/tool args/session 文本**；
  call_id 只记 SHA-256（`test_audit_records_are_allowlisted_and_content_free` 断言）。
- 失败路径不启动 Broker/Fake；不写 Attempt/Reservation/Claim/Fake 字节（结构断言见 §4）。
- 历史 `PENDING/SETTLEMENT_UNCERTAIN` hold：A2 只读不写（模块不 import AttemptJournal/Broker；
  audit 断言 `attempt_db_touched=false`、`historical_holds_modified=false`）。
- 新增代码无网络/Key env 读取；LiveGate/CLI/Adapter/run_live 零 diff 且负例不变。

---

## 8. G4-H1 BLOCKER（书面化，必须随 G4-H1 判定一起读）

> **G4-H1 BLOCKER**：当前实现为 **opt-in**（`run_admission=None` 时行为不变）。
> **在 G4-H1 放行之前，run admission 必须升级为唯一生产启动路径**：
> 受信 Launcher 必须先完成 `begin_run_admission()`（一次性消费成功）才能启动 Broker/Controller；
> `run_admission_required` 必须是生产配置的**唯一允许值**，且需要把 required 模式接入真实部署
> Launcher/Runbook（本轮只提供 test-only harness 与最小接线）。若在 G4-H1 时仍存在“无 run
> admission 即可启动生产链”的配置，则 **G4-H1 不得放行**。该升级与人类签名根/Key Broker/Egress/
> Watchdog 的真实部署同属人类 Gate，本 PR 未部署、未声称已完成。

---

## 9. 与 A1 合体后的接口/差异（rebase `fix/a-next-auth-record` e6f3aa6）

- **已完成 rebase**：A2 的 5 个提交重放到 A1 HEAD `e6f3aa6` 之上，**无冲突**
  （A1 只改 `authorization.py` + 新增 `a_next_auth` 测试；A2 只改 controller/新增 run_admission/
  scripts/a_next_admission 测试，双方文件集不重叠）。
- **契约验证**：A1 的 `_read_use_record(path, *, expected_authorization_id)` 返回
  `(authorization_id, epoch)`；body id 不匹配/存储名不匹配/非法 `consumed_utc` 一律
  `AUTHORIZATION_USE_RECORD_INVALID`（**非** REPLAYED/EPOCH_MISMATCH）。A2 只经公共
  `begin_run_admission()`/consume 观察，不 import A1 私有函数；`_map_consume_reasons` 将其映射为
  `RUN_ADMISSION_RECORD_INVALID`（consumed=NO）。
- **R-07 真实文件用例已补**（`tests/integration/a_next_admission/test_r07_body_id_crosscheck.py`）：
  1) 真实 consume 成功后把记录 body id 改为外来 id（文件名不变）→ `RECORD_INVALID`，不是 replay；
  2) body id 哈希与存储名不符 → `RECORD_INVALID`；
  3) 非法 `consumed_utc` → `RECORD_INVALID`；
  4) 未篡改记录 → 仍 `ALREADY_CONSUMED`（对照）。
- **diff 边界**（Lead 的核对项，实际语义如下）：
  - `git diff --name-only fix/a-next-auth-record..HEAD -- src/autoteacher_m0/security/authorization.py`
    = **0 行**（A2 在 A1 之上零额外改动）；
  - `git diff --name-only fd1d3a6..HEAD -- src/.../authorization.py` = 该文件（因为 fd1d3a6 是
    **A1 之前**的基线，A1 的 +51/−18 已作为祖先进入 HEAD；这不是 A2 的改动）。因此“相对 fd1d3a6
    为 0”仅对 A2 自身改动成立，不能字面要求整条 ancestry 为 0。
  - A1 未改 `controller.py`（`git diff fd1d3a6..fix/a-next-auth-record -- controller.py` = 0），
    A2 的接线面与 A1 完全分离。
- **合体后无回归**：A1 套件 39 passed；A2 套件 73 passed；g4_a/g4_f5/g4r_packet/unit/security
  与 rebase 前一致（§6）。

---

## 10. 残余风险与 L2 移交

1. **opt-in 未强制**：见 §8；生产强制化与真实 Launcher 部署未完成。
2. **L2 未运行**：`A2-01..A2-03` 真实 DSH/双 principal/独占 OCI 证据 = **NOT_RUN**，归 A-PR3
   （`scripts/a_next/admission/l2_admission_cases.py` 交给其窗口调用；本 PR 仅 host synthetic 验证）。
3. **审计两阶段残余**：outcome 写失败时“已消费但审计不完整”，靠 intent + use log REPLAYED 重建，
   需要人工对账流程（已在 tri-state 中暴露）。
4. **run_epoch 依赖 Admission nonce 唯一**：同 Admission 重启 = fail-closed REPLAYED（安全），
   Runbook 需写明“每个 Run 新 Admission”。
5. **token 为 in-process**：Controller 崩溃后 token 全灭；重启必须重新走 run admission（同 Run →
   REPLAYED）→ 不允许自动恢复未完成 dispatch（有意的 fail-closed）。
6. **C5 结构性证明**：frozen Admission 把 max_attempts 固定为 1；实现只保证“一条 payload 一条
   token”，未来若引入重试循环需重新评估 token 语义（Reviewer 关注点）。
7. **未验证真实 FS 故障**：`fsync/link` 注入覆盖逻辑分类，真实磁盘故障仍需部署侧证据。
8. **无需也不得外推**：host PASS ≠ L2/生产；`B03/E5-P04` 仍 UNVERIFIED；`LiveGate` 仍 BLOCKED。

---

## 11. 后续（等待 Lead/Reviewer）

1. Reviewer 审阅本实现 + A2 条件 C2–C8；可重跑 §6 命令与 `tests/integration/a_next_admission`。
2. A1 合入后 rebase + 补 R-07 真实文件用例（§9）。
3. A-PR3 在独占 OCI 窗口运行 `l2_admission_cases.py`，产出 A2-01..A2-03 L2 证据；A-PR1/A-PR3
   联合报告。
4. 人类 Gate：G4-H1 前将 run admission 升级为唯一生产路径（§8）；本 PR 不 push/不 merge。


## 12. Rebase 记录（A2 → A1 e6f3aa6）

- 命令：`git rebase fix/a-next-auth-record`（A1 HEAD `e6f3aa6`，parent `fd1d3a6`），无冲突。
- 新提交链：`d7bbf3b`（ADR）→ `07eccb9`（实现）→ `6556967`（ADR errata）→ `ff44ef6`（R-25）
  → 本报告提交（含 R-07 真实文件用例与本文档更新）。
- 变化面：仅 A1 的 `authorization.py` 进入 ancestry；A2 未重复修改该文件（相对 A1 分支 diff=0）。
- 合体后测试：A2 73 passed、A1 39 passed、g4_a 223、g4_f5 12、g4_f2 29+1 skip、
  g4r_packet 11+1 skip、unit 396、security 6+1 pre-existing（同基线证明）、collect 1532、ruff 0。
- 无新增风险：A1 仅收紧 use-record 读取（更严格 fail-closed），A2 的映射把 INVALID 当
  “不可证明/不发送”，二者语义一致。
