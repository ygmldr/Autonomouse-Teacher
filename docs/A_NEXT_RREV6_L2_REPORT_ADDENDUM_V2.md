# A-NEXT A-PR3 / R-REV6 — L2 报告 Append-only Addendum V2（P2-A4-2 / P2-A4-3 修正）

- **类型**：append-only addendum V2。**不修改** `docs/A_NEXT_RREV6_L2_REPORT.md`
  冻结字节（`95a020b27ccf05ae3cd504d8c138bc279706fee2`），也**不修改**
  `docs/A_NEXT_RREV6_L2_REPORT_ADDENDUM.md`（`0735d7b8f11770586dda5acf2caf756d81cffd1b`）
  与 `artifacts/a_next/rrev6/l2/run-20261120T202039Z/` 下任何既有证据文件。
- **起因**：Reviewer 独立 OCI 复跑（Reviewer 自有窗口）已达到 **R-REV6 = PASS**，同时以
  **P2-A4-2**（runner fail-open）、**P2-A4-3**（fresh worktree 前置未文档化）与
  **P3-A4-4**（Reviewer 程序性偏差披露）要求 append-only 修正。
- **本次动作**：修改 runner/audit 的 fail-closed 行为 + 新增 host 单测 + 本 addendum。
- **未运行 OCI**：本次修正不启动任何容器、不执行 podman run/exec、不占用 Integrator
  20:55–21:25Z 的 OCI 窗口；仅运行 host 单测（`tests/a_next_rrev6/`）。未 push。
- **证据等级不变**：窗口 L2 证据仍为 **Implementer/Owner 证据**；R-REV6 的 PASS 来自
  **Reviewer 独立 OCI 复跑**（不是本 Agent 的复跑）。本 addendum 只记录修正与状态。

---

## 1. Reviewer 独立 L2 结论（原样记录，不扩写）

- **Reviewer 独立 OCI 复跑 R-REV6 = PASS**（限定 **L2-REAL-DSH-FAKE / no-key** scope）：
  - 14/14 case 状态 PASS；
  - T0 = T1（frozen rootfs `25491e45…`、deps `e07729d7…` 一致）；
  - digest 绑定 11/9（`prepared_digest == claim.request_digest` 11 行、
    `payload_digest == receipt.raw_sha256` 9 个 receipt，0 mismatch；两个 digest
    分别绑定、不互相等同）；
  - Stage SHA 与 Owner 声明一致（manifest `34b3db73…` / tree `2b9edab8…`，
    base = run HEAD `d083c54…`）。
- 该 PASS **仅限** Fake-only / no-key / 真实 DSH + 真实本地 Broker+Fake 的 L2 scope；
  **不等于** E5-Full、G4-H、G5、Live、真实 Provider/计费或生产信任根的任何批准。
- 历史状态更新（Reviewer 独立结果）：**A4-01 / A4-02 / A4-03 = PASS**；
  **R-REV6：NOT_RUN → PASS**（同上限定）。矩阵 CSV 由 Lead/Integration 维护，本 Agent 未改
  任何 CSV 字节。

## 2. P2-A4-2 修正：runner / audit fail-closed（不再 fail-open）

- **问题（Reviewer 发现）**：Reviewer 临时 worktree 缺少 `artifacts/g4/c/runs` fixture，
  attempt1 的 13 个 case 全部落为 INTERNAL/PARTIAL，但 `run_l2_matrix.py` 仅以
  “T0/T1 frozen 门 + 容器数”作为 `ok`，仍输出 `ok=true` / **EXIT=0**（fail-open）。
- **修正**：
  1. `scripts/a_next/rrev6/run_l2_matrix.py` 新增纯函数
     `decide_run(...)` / `evaluate_audit(...)`：audit 缺失、任一 case 状态非 PASS
     （INTERNAL/PARTIAL/FAIL/NOT_RUN/TIMEOUT/BLOCKED/ERROR 等）、counts 不一致、
     预期 case 缺失、容器残留、frozen 漂移 → `ok=false` + 明确 `failure_reasons`，
     **进程返回非零**；`summary.json` 新增 `audit_ok`、`audit_problems`、
     `prerequisites_ok`、`fail_closed`、`ok`、`failure_reasons` 字段，并写
     `run_status.json`。
  2. `scripts/a_next/rrev6/evidence_audit.py` 顶层输出 `ok`/`failure_reasons`，
     standalone CLI 在 audit 非全 PASS 或空 suite 时**非零退出**（不再恒 0）。
  3. 验收路径由 host 单测覆盖（见 §4）：全 PASS→ok；任一非 PASS→fail-closed；
     audit 缺失/空→fail-closed；counts 不一致/缺 case→fail-closed；frozen 漂移/
     容器残留→fail-closed；audit CLI 空 run→非零退出。

## 3. P2-A4-3 修正：fresh worktree 前置 fail-fast + 文档化

- **问题（Reviewer 发现）**：独立复跑在 fresh worktree 中缺少 staged fixture
  （如 `artifacts/g4/c/runs`）时，runner 没有前置检查，导致所有 case 以
  INTERNAL 失败后才暴露，前置条件未文档化。
- **修正**：`run_l2_matrix.py` 新增 `prerequisite_problems(...)`，在 T0/建 run 目录**之前**
  fail-fast 检查并以 `RUNNER_PREREQ_MISSING` + problem list（id/path/message/remediation）
  非零退出。检查项：
  - `artifacts/security/rootfs`（存在且 `sha256 == 25491e45…`）
  - `artifacts/foundation/deps`（存在且 `sha256 == e07729d7…`）
  - `artifacts/g4/c`（存在）与 `artifacts/g4/c/runs`（存在且可写；缺失 remediation 明示
    `mkdir -p`）
  - `plugins/offline-fixture/node_modules`
  - Stage 目录与 `manifest.json`（且后续 T0 继续 `validate_stage_g4`）
  - `scripts/a_next/rrev6/{launch_case,evidence_audit}.py`、`case_matrix.json`

### 3.1 独立复跑前置清单（fresh worktree）

```bash
# 0) 准备 fresh worktree 后，以下 staged 目录必须存在（gitignored，需从经哈希验证的
#    recovery copy 复制；rootfs/deps 的 canonical 值见下）：
#    artifacts/security/rootfs         sha256(tar canonical) = 25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0
#    artifacts/foundation/deps         sha256(tar canonical) = e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98
#    artifacts/g4/c/                    （G4-C 构建/运行根）
#    artifacts/g4/c/runs/               （必须已存在且可写；缺失则 runner 明确报错）
#    plugins/offline-fixture/node_modules
#    artifacts/g3a-provider-bridge/stage, artifacts/g3c/stage   （仅在需要重建 Stage 时）
#    另需：podman 4.9.3、0 容器、worktree clean、HEAD == 预期 run HEAD、
#          冻结 node_modules 对应的 DSH runtime（1cc41d5a…）

cd "/root/Autonomous Teacher/worktrees/a-next-rrev6"
# 1) 前置自检（host-only，含 rootfs copy-test）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" \
  scripts/a_next/rrev6/env_check.py --copy-test
# 2)（如需）在 run HEAD 重建 Stage（rootfs 只用工作副本）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" \
  scripts/a_next/rrev6/build_stage.py
# 3) 跑矩阵（fail-closed：任一非 PASS 或 audit 缺失 → 非零退出）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" \
  scripts/a_next/rrev6/run_l2_matrix.py \
  --stage artifacts/g4/c/stages/<stage> --expected-head <run-head>
# 4) 事后独立审计（fail-closed）
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" \
  scripts/a_next/rrev6/evidence_audit.py --run artifacts/a_next/rrev6/l2/<run>
# 5) 验收：run 退出码 0 且 summary.json ok=true、audit.counts.pass==total、
#    t0/t1 frozen 哈希一致、podman ps -a 空；否则按 failure_reasons 修正前置/环境。
```

## 4. Host 单测（本次新增，未跑 OCI）

- 新增 `tests/a_next_rrev6/test_runner_fail_closed.py`（**18 个测试**），覆盖：
  - `decide_run`：全 PASS → ok；任一非 PASS（7 种状态参数化）→ fail-closed；
    audit 缺失/空 → fail-closed；缺预期 case → fail-closed；counts 不一致 →
    fail-closed；容器残留 / rootfs 或 deps 漂移 → fail-closed；
  - `prerequisite_problems`：缺 rootfs/deps/g4c/plugin/stage 时逐项具名报错；
    **缺 `artifacts/g4/c/runs` 时唯一明确报错并给出 `mkdir -p` remediation**；
    前置齐全时 ok；当前 worktree 真实前置（canonical 复算）通过；
  - `evidence_audit` standalone CLI：空 run → 非零退出 + `ok=false`；
  - 静态契约：runner 源码必须含 `audit_ok`/`fail_closed`/`failure_reasons`/
    `RUNNER_PREREQ_MISSING`/`prerequisite_problems`/`decide_run` 标记。
- **测试计数**：`tests/a_next_rrev6/` 运行结果 **28 passed**（原 10 + 新增 18），
  host-only、无容器、无网络；命令：
  `PYTHONPATH=src .venv/bin/python -m pytest tests/a_next_rrev6 -q -p no:cacheprovider`。
- 未运行 OCI：Integrator 20:55–21:25Z 窗口期间本 Agent 未执行任何 podman run/exec。

## 5. P3-A4-4 登记（Reviewer 披露，Implementer 不处理）

- Reviewer 披露其 attempt1 比约定窗口**早 17 秒**启动（程序性偏差）。按任务要求，
  该偏差由 Reviewer 在自有报告/披露中登记，Implementer **不做处理、不追改证据**；
  本 addendum 仅作 append-only 登记，供维护者审阅时对齐时间线。

## 6. 限制不变（不得因 R-REV6 PASS 外推）

以下限制与冻结报告 §5.3 / addendum V1 一致，**未改变**：
- Fake-only、无真实 Provider/Key/HTTP(TCP)、synthetic prompts；R-REV6 PASS 仅限
  `L2-REAL-DSH-FAKE / no-key` scope；
- R6-04（DSH 层同 session 重放）受 SDK `session already exists` 边界限制，
  由 R6-04B（字节级 candidate-UDS replay）补充；
- R6-09（Controller 硬停）SIGKILL 落在 pre-attempt 窗口，ATTEMPT_STARTED 后窗口由
  R6-08 hook 覆盖；外部 SIGKILL 纳秒级全窗口未穷举（F5-R6 限制保留）；
- R6-11（Fake crash）后 Broker 已证 `FAILED` 终态 + `WORST_CASE_HELD` 保守归档，
  属 Broker 权威终态优先，非 FREE/held；
- Registry 权威性 `B03/E5-P04 = UNVERIFIED`；LiveGate=`BLOCKED`、G4-H=`NOT_AUTHORIZED`、
  G5=`BLOCKED`、M0=`DECISION_PENDING` 不变；
- 本次修正不改变任何原始证据字节、不重跑 OCI。

## 7. 本次变更文件

| 文件 | 状态 |
|---|---|
| `scripts/a_next/rrev6/run_l2_matrix.py` | 修改：fail-closed `decide_run`/`evaluate_audit` + `prerequisite_problems` fail-fast + summary/run_status 字段 |
| `scripts/a_next/rrev6/evidence_audit.py` | 修改：audit `ok`/`failure_reasons` + standalone CLI 非零退出 |
| `tests/a_next_rrev6/test_runner_fail_closed.py` | 新增（18 tests） |
| `docs/A_NEXT_RREV6_L2_REPORT_ADDENDUM_V2.md` | 新增（本文件，被提交） |
| `docs/A_NEXT_RREV6_L2_REPORT.md` / `ADDENDUM.md` / 原始证据 / evidence-index v1&v2 | **未改字节**（保留历史；本 addendum append-only） |

- 本 addendum 的 commit SHA 由交付消息给出；未 push。
- 只读复核命令：

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-rrev6"
sha256sum docs/A_NEXT_RREV6_L2_REPORT.md \
  artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index.json \
  artifacts/a_next/rrev6/l2/run-20261120T202039Z/evidence-index-v2.json
PYTHONPATH=src .venv/bin/python -m pytest tests/a_next_rrev6 -q -p no:cacheprovider
git log -1 --oneline
```
