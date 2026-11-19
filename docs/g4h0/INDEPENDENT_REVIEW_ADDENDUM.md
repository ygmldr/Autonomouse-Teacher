# G4-H0 独立审查增补报告 — test-only delta 复核（F-01 关闭）

- **Addendum ID**：`G4H0-INDEPENDENT-REVIEW-ADDENDUM-v1`
- **Reviewer**：`a-reviewer`（同主审；独立 Agent，未参与实现/证据生成/文档撰写）
- **独立性声明**：本增补只基于 Reviewer 自己的命令与原始日志；**未采信** Lead/Implementer 的
  “已修复/42/42 PASS”文字，未修改实现、delta worktree（只读）、主工作树或其它 worktree；
  未 `push`/`merge`；0 真实 Key、0 真实 Provider/付费调用。
- **时间（UTC）**：`2026-11-19T18:37Z`–`18:47Z`（时间盒 ≤15 分钟）
- **主审报告**：`G4H0-INDEPENDENT-REVIEW-v1`（`docs/g4h0/INDEPENDENT_REVIEW.md`，提交
  `77b3159aadb5298c6b30f69a8624d4e61fd025cc`，文件 blob `8ad140193bb8f76d790adc907108bc7c44120ac8`），
  主审对象 = 冻结 impl `813e6a680399ba245bd0e76296e1212118a83460`；主审裁定
  `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`，F-01 = 新 g4_h0 用例时序缺陷（单独 10/10 fail）。
- **本次 delta 复审对象（只读）**：
  - 实施者 test-only 修复提交：`87aa52f34eab0185d3512a6e62e5b075748b5bbb`
    （父 `ff9afd0b592a34e12f27860a3363c8a84b58b18a`；`git diff --name-status 87aa52f^..87aa52f`
    实测**仅 2 文件**：`tests/integration/g4_h0/test_p2_03_concurrent_consume.py` +
    `docs/g4h0/evidence/p2_03_g4h0_standalone_3x.log`）。
  - 最终交付集成 HEAD：`b57494a5eecb2406d5a20605b04e2a54cda0dae8`
    （`git rev-list --parents -n 1` 实测父提交 = `bb35a01…` + `87aa52f…`）。
  - delta 复审工作树：`/root/Autonomous Teacher/worktrees/m0-g4h0-review-delta`（detached @ b57494a，
    `status --porcelain -uall` = 0 行；Reviewer 只读使用，未在该树提交）。

---

## 1. Delta 范围复核（`R-C12`）

原始记录：`docs/g4h0/review-evidence/delta_scope.log`（Reviewer 本人命令输出）。

`git diff --stat 813e6a6..b57494a` = **6 files，+560/-20**：

| 文件 | 变更 | 归属 | Reviewer 判定 |
|---|---|---|---|
| `tests/integration/g4_h0/test_p2_03_concurrent_consume.py` | M +106/-20 | 87aa52f（test-only 修复）| 仅测试；实现语义未动 |
| `docs/g4h0/evidence/p2_03_g4h0_standalone_3x.log` | A +18 | 87aa52f（实施者证据，**Reviewer 不采信其数字**）| 证据文本 |
| `docs/g4h0/REVIEW_REQUEST.md`、`EVIDENCE_INDEX.md`、`PACKET_SUMMARY.md`、`HUMAN_DECISIONS_PROPOSED.md` | A（+77/+100/+55/+224）| bb35a01（core Review Packet docs）| 文档；spot check 见 §4 |

**冻结对象保护（关键结论）**：
- `git diff --stat 813e6a6..b57494a -- src/ scripts/ tests/security/ scripts/run_live.sh` →
  **空**（零 diff）⇒ 主审覆盖的 `813e6a6` 实现对象（`authorization.py`/`controller.py` 及全部受保护
  文件）**未被 delta 改动**，主审关于 P2-03/05/06、A-07、LiveGate、冻结文件的结论继续适用于最终
  HEAD `b57494a`。
- 主审产物在工作树 `.../m0-g4h0-review` 分支 `work/m0-g4h0-review` @ `77b3159` 保留；delta 树只读。

## 2. F-01 独立重跑（`R-C13`）

环境：cwd = delta worktree；`PYTHONPATH=src`，已确认 `import autoteacher_m0` 指向**delta worktree**
的 `src/autoteacher_m0/__init__.py`；pytest 9.2.0；全程 `-p no:cacheprovider`、
`PYTHONDONTWRITEBYTECODE=1`。原始日志：`docs/g4h0/review-evidence/delta_*.log`。

| 命令 | 实测 | 日志 |
|---|---|---|
| `pytest .../test_p2_03_concurrent_consume.py::test_retry_bound_stays_fail_closed_for_a_late_publisher` **×10** | **10 passed / 0 failed** | `delta_f01_single_10x.log` |
| `pytest tests/integration/g4_h0 -q` **连续 ×10** | **10/10 次均 `14 passed`**（每次全新进程）| `delta_g4h0_dir_10x.log` |
| `pytest tests/integration/g4_f5 -q` | **17 passed** | `delta_g4_f5.log` |
| `ruff check tests/integration/g4_h0/` | **All checks passed!**（exit 0）| `delta_ruff.log` |

对比主审：同一单测在冻结 `813e6a6` 上单独循环 10 次为 **0 passed / 10 failed**（`flaky_test_rate.log`），
根因是基线 `consume()` ≈332–337 ms > 测试固定 300 ms writer 延迟。delta 后该失败模式未再出现。

## 3. 修复确定性/断言真实性审读（Reviewer 代码级）

修复机制（`git diff 87aa52f^..87aa52f`）：
- 新增两个 `time` 代理：`_CountingSleep`（只记录 `sleep` 调用即返回，不真实等待）与
  `_ScriptedSleep`（第一次 retry sleep 时用 `threading.Event` 交棒给脚本化 legacy writer，等
  writer 完成后再返回）。**只 monkeypatch `authorization_module.time` 模块绑定，不替换全局
  `time` 模块**（`monkeypatch.setattr` 测试结束自动恢复）；`authorization.py` 内 `time` 的运行时用途
  实测只有 `time.sleep(...)`（`:865`），其余 `timezone` 来自 `datetime`，不受影响。
- **无墙钟依赖**：`test_retry_bound...` 新逻辑删除 `time.sleep(0.3)` 与 `elapsed < 0.3`，
  改为 `reader_finished`/`late_done` Event 门控——late writer 必须等 `consume()` 已返回后才发布，
  冷启动/CPU 频率不再影响“晚写”语义。
- **断言未被放宽（实测净增）**：changed hunks 中 `+assert` = 15、`-assert` = 4（移除的是墙钟
  `elapsed < 0.3` 与非确定性 `finished.is_set()`）；新增断言更强：
  `pytest.raises(AuthorizationRejected)` + 精确 reason `AUTHORIZATION_USE_RECORD_INVALID` 仍保留；
  `len(fake_time.sleep_calls) == 2`（有界重试恰好耗尽）、每个 sleep 值 ==
  `_USE_RECORD_READ_DELAY_SECONDS`、拒绝瞬间 `late_done.is_set() is False` 且 `record.stat().st_size == 0`
  （证明 reader 是“自己耗尽上界”而非被 writer 抢先）、随后 late writer 完成且
  `record.read_bytes() == body`、仅 1 条 use record、0 临时文件、**未来再次 consume →
  `AUTHORIZATION_REPLAYED`**（不消费/不修复授权）。既未被 try/except 吞掉，也没有弱化 fail-closed 语义。
- `test_partial_legacy_record_is_retried_then_replayed`：改为 Event 交棒的 half-write publisher，
  重试窗口参数由 200×5 ms 改为 **20×10 ms**（与产品默认 `_USE_RECORD_READ_ATTEMPTS=20`、
  `_USE_RECORD_READ_DELAY_SECONDS=0.01` 一致）；仍断言 `sleep_calls >= 1`（确实发生重试）、
  writer 完成、记录完整、1 条 record、0 临时文件。属确定性改造而非放宽：重试路径与 REPLAYED 分类不变。
- 无 `src/` 改动 ⇒ 不存在“为过测试而改实现”的路径。

**F-01 结论：`CLOSED`**（独立重跑 10/10 + 10/10 全过；确定性机制经代码审读成立；断言加强而非放宽）。

## 4. Delta 中 Review Packet docs 的有限核对（spot check，非完整复审）

`docs/g4h0/{REVIEW_REQUEST,EVIDENCE_INDEX,PACKET_SUMMARY,HUMAN_DECISIONS_PROPOSED}.md`：
- 未发现 `E5_PRELIVE_FULL PASS`/`G5 已获批`/`G4-H1 已部署`/`M0 GO` 等越权表述；相反均显式禁止
  外推（如 `REVIEW_REQUEST.md:189`、`EVIDENCE_INDEX.md:77`、`PACKET_SUMMARY.md:55`）。
- 状态常量保持 `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`（未变）。
- `HUMAN_DECISIONS_PROPOSED.md` 全部决策项为 `PENDING_HUMAN_ACTION`，与主审
  `HUMAN_DECISIONS.md`（HD-01..HD-20 全未签核）一致，不构成代签。
- 说明：本节只做范围/口径 spot check；这些新增 Packet docs 的**内容完整性**由 Lead/维护者最终审阅，
  本增补不为其背书。

## 5. F-02..F-05 状态（保持主审结论）

delta **未涉及**以下各项，主审结论原样保留（仍为开放 P2，非本轮关闭项）：

| ID | 项 | 状态（增补后） | 说明 |
|---|---|---|---|
| F-01 | g4_h0 新测试时序缺陷 | **CLOSED** | 本增补 §2/§3；test-only 修复经独立 10/10 复验 |
| F-02 | use record 目录项未 fsync（掉电持久性）| **OPEN（low）** | 主审结论；G4-H1 前处置（修复或人类明示接受） |
| F-03 | Runbook §4.5/§4.6 与 P2-03 修复口径不一致 | **OPEN（low，文档）** | 待 ERRATA/下一版 Runbook；不得原地改写冻结证据 |
| F-04 | `_read_use_record` 未 `O_NONBLOCK`（FIFO 读阻塞 nit）| **OPEN（nit）** | 主审结论；下个加固窗口 |
| F-05 | 重复 recovery reason 追加/256 截断 nit | **OPEN（nit）** | 主审结论；仅证据可读性 |

> 注：主审 P2 计数的更新口径 = **1 closed（F-01）+ 4 open（F-02..F-05）**；P0=0、P1=0 不变。

## 6. ERRATA 状态

按指令检查 `/root/Autonomous Teacher/worktrees/m0-g4h0-docs/docs/g4h0/ERRATA.md`：**截至本次复审
（2026-11-19T18:45Z）该文件尚未出现**（docs 线仍在产出）。因此本增补**无法**复核 ERRATA 对
F-02..F-05/F-03 的登记准确性 ⇒ **“ERRATA 待合并，由 Lead 最终核对”**。Lead 合并后应逐项核对：
F-02 是否登记为 H1 前置、F-03 是否明确以 append-only 方式更正 Runbook、F-04/F-05 是否标 nit、
且不得改写冻结 docs/Packet 字节。

## 7. 对最终交付 HEAD 的裁定增补

> 最终交付集成 HEAD = **`b57494a5eecb2406d5a20605b04e2a54cda0dae8`**（= `813e6a6` 实现 +
> `bb35a01` Review Packet docs + `87aa52f` test-only delta）。
>
> # 维持裁定：`PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`
>
> 依据：F-01 经独立复验 **CLOSED**；delta 为 test-only + docs/evidence，`src/` 与受保护文件零 diff，
> 主审安全结论（P2-03 原子发布、LiveGate 恒 BLOCKED、0 Key/网络、Packet 完整性）继续适用于最终
> HEAD；未发现新 P0/P1。
>
> 开放 P2：**F-02、F-03、F-04、F-05**（见 §5）；ERRATA 待合并由 Lead 核对（§6）。
>
> **范围限制不变**：本裁定仅覆盖“G4-H0 无 Key 准入准备/证据就绪”。**不表示、且禁止据此宣称**
> `E5_PRELIVE_FULL PASS` / `E5-P04 PASS` / G4-H1（正式受信部署）已部署 / G5 已获批 / G6 GO /
> `M0 GO` / Live 可运行。门状态保持：`LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、
> `G6=NOT_RUN`、`M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
>
> **STOP**：等待维护者在 `docs/g4h0/HUMAN_DECISIONS.md`（以及合并后 ERRATA）逐项签核；本轮仍
> 不部署、不注入 Key、不发起真实 Provider 调用。

## 8. 本增补证据索引

`docs/g4h0/review-evidence/`（Reviewer 本人命令原始输出）：
- `delta_scope.log` — delta 工作树/HEAD/父提交、`813e6a6..b57494a` 与 `87aa52f^..87aa52f`
  文件清单、src/scripts 零 diff、module path。
- `delta_f01_single_10x.log` — F-01 单测 10 次循环结果。
- `delta_g4h0_dir_10x.log` — `pytest tests/integration/g4_h0` 连续 10 次逐次结果。
- `delta_g4_f5.log` — `pytest tests/integration/g4_f5` = 17 passed。
- `delta_ruff.log` — `ruff check tests/integration/g4_h0/` = All checks passed。
- 主审日志（F-01 原始失败形态/时序探针）仍在：`flaky_test_rate.log`、`flaky_retry_test_full.log`、
  `probe_retry_bound_timing.log`、`review_suites.log`。

本增补提交于 `work/m0-g4h0-review`（基于主审 `77b3159` 之上，不合并、不 push）。
