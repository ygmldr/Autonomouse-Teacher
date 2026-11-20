# M1-B 评测报告模板（B-PR5，评审骨架）

> **模板说明（必读）**：本文件是 **B-PR5 最终评测报告的空骨架**，不是最终报告。所有实测数字/状态初始为 `TBD / NOT_RUN`；只能由**独立 Reviewer 在冻结 SHA 上本轮真实复跑**后替换。禁止填造、禁止把历史 536/365 相加、禁止把 `MOCK` 结果写成真实收益。
>
> 本模板与 `docs/M1_B_EVALUATION_PROTOCOL.md`（协议，位于同级 PR 分支 `b-next/pr5-eval-protocol`）配套使用；证据包格式见 `docs/M1_B_EVIDENCE_PACKET.md`；收集器为 `scripts/m1b/collect_evidence.py`。

| 字段 | 值 |
|---|---|
| 报告状态 | `TBD`（`DRAFT_TEMPLATE` → 填充后 `FINAL`） |
| 报告版本 | `m1b.eval-report.v0-template` |
| 工作区/分支 | `<WORKTREE>` / `<BRANCH>` |
| 冻结 SHA（被测） | `<FROZEN_40_HEX_SHA>` |
| 基线 | `main@3e7afee077845a071cd364e93ab209cac20b2d5f` |
| Reviewer | `<REVIEWER_NAME>`（独立；未参与实现；不得修改被审实现） |
| 评审时间 | `<YYYY-MM-DD UTC>` |
| 证据包路径 | `<EVIDENCE_OUT_DIR>`（`audit-index.jsonl` + `raw/` + `README.md`） |
| 覆盖范围 | 离线、合成 fixtures、确定性/mock E2E、B-PR0…B-PR5 验收门；**不含**真人学习收益/联网/真实 Provider/Live |
| 结论类型 | `<PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE \| PARTIAL_FOR_... \| FAIL \| BLOCKED>`（TBD） |

---

## 0. 最终裁定摘要（填充前全为 TBD）

| 项 | 结果 | 证据位置 |
|---|---|---|
| P0 findings | `TBD` | `<audit-index case_id>` |
| P1 findings | `TBD` | `<...>` |
| P2 findings | `TBD` | `<...>` |
| B0-01 合同唯一性 | `TBD / NOT_RUN` | `<...>` |
| B1-01…B1-06 Judge 信任边界 | `TBD / NOT_RUN` | `<...>` |
| B2-01…B2-03 事务/崩溃恢复 | `TBD / NOT_RUN` | `<...>` |
| B3-01/B3-02 幂等范围 | `TBD / NOT_RUN` | `<...>` |
| B4-01…B4-03 统一教学闭环 | `TBD / NOT_RUN` | `<...>` |
| B5-01 独立产品评审 | `TBD / NOT_RUN` | `<...>` |
| X-01 无范围漂移 | `TBD / NOT_RUN` | `<...>` |
| X-02 无 Key/网络/付费 | `TBD / NOT_RUN` | `<...>` |
| Gate G1–G8（协议 §4.1） | `TBD` | `<...>` |
| **最终裁定** | **`TBD`** | 本报告 §12 |

> 只有全部 Gate 通过且无 STOP 触发，才允许写 `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`；否则必须写 `PARTIAL_FOR_...` / `FAIL` / `BLOCKED` 并逐项列出未关闭证据。

---

## 1. 方法与独立性（Reviewer 填写）

- [ ] Reviewer 未参与 `<实现/测试/fixtures/docs>` 编写；未修改被审对象；仅写入本报告与 `/tmp` 探针。
- [ ] 在 `<FROZEN_SHA>` 的 clean archive 副本（`git archive <SHA> | tar -x`）上复跑，未在 Owner worktree 上验收。
- [ ] Owner 报告只作 `OWNER_REPORTED` 引用；本轮结论均来自 `INDEPENDENTLY_REEXECUTED_THIS_TURN` 命令。
- [ ] 所有运行记录已写入 `audit-index.jsonl`（命令、环境、utc、exit code、raw sha256）。
- [ ] 历史 536/365 只作 `REVIEWER_REPORTED` 历史冻结引用，未相加（§4）。
- [ ] 无真实 Key/网络/Provider/真实个人数据；恶意代码负例仅在隔离 Worker 执行（协议 §5）。

clean archive 命令模板：

```bash
rm -rf /tmp/m1b-final-review && mkdir -p /tmp/m1b-final-review
git -C <REPO> archive <FROZEN_SHA> | tar -x -C /tmp/m1b-final-review
cd /tmp/m1b-final-review
```

---

## 2. 环境记录（必须原样填写；评审环境快照）

| 项 | 值 |
|---|---|
| OS / platform | `<TBD>` |
| Python | `/root/Autonomous Teacher/.venv/bin/python`（`<TBD>`） |
| pytest | `<TBD>` |
| TZ / LANG / LC_ALL / PYTHONHASHSEED | `UTC` / `C.UTF-8` / `C.UTF-8` / `0` |
| 网络 | 已阻断（socket `sitecustomize` 或 `--network none`）：`<TBD>` |
| API Key / Provider | 无（已清空敏感环境变量）：`<TBD>` |

---

## 3. 命令矩阵 C1–C16（本报告的核心；填充前全为 `TBD / NOT_RUN`）

> 每行必须由 Reviewer 本轮真实执行；`status` 只能是 `EXECUTED_PASS / EXECUTED_FAIL / NOT_RUN`（收集器执行状态），证据类另行标注。历史期望值列（`REVIEWER_REPORTED`）仅作参考，**不得直接抄为本轮结果**。

| # | 对象 | 命令（模板） | 本轮状态 | 本轮实测（填写真实末行/哈希） | 证据（audit-index case_id / raw sha256） | 历史期望（仅参考） |
|---|---|---|---|---|---|---|
| C-01 | M1-A 全套 | `pytest tests/m1_teacher -q` | `TBD / NOT_RUN` | `<TBD>` | `<B5-01-m1a>` | 536 passed（历史） |
| C-02 | M1-A 分 PR 计数 | `pytest tests/m1_teacher --collect-only -q` + 按文件统计 | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 268/100/50/75/43（历史） |
| C-03 | M1-A demo 双跑 | `python -m m1_teacher.demo` ×2 + `diff`/`sha256sum` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | `b08ceee9…`（历史） |
| C-04 | M1-A evidence 复跑 | `python -m m1_teacher.demo --write-evidence` + `sha256sum docs/m1a_evidence/*` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | `171cc654…`/`5e84229e…`/`23b871a3…`（历史） |
| C-05 | M1-A CLI | `python -m m1_teacher.cli --help/--student both --json/--demo` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 行为与文档一致（历史） |
| C-06 | M1-A no-.git 复跑 | 复制 `m1_teacher/`+`fixtures/m1_teacher/` 到无 `.git` 目录重跑 C-03/C-04 | `TBD / NOT_RUN` | `<TBD>` | `<...>` | P1-1 修复后字节一致（历史） |
| C-07 | M1-Offline 全套 | `pytest tests/m1_offline -q` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 365 passed（历史） |
| C-08 | M1-Offline 评测子集 | `pytest tests/m1_offline/test_{closed_loop,evaluation_protocol,negatives,contamination,compare_v0_v1}.py -q` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 76 passed（历史） |
| C-09 | M1-Offline CF/Interview 子集 | `pytest tests/m1_offline/test_{cf_judge,cf_teacher,cf_negatives}.py -q`；`test_{interview_coach,interview_rubric,freshness}.py -q` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 75 / 49 passed（历史） |
| C-10 | M1-Offline demo 双跑 | `python -m m1_offline.demo` ×2 + `diff`/`sha256sum` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | clean C2 `1d57ca62…`；artifact 上下文 `2282caff…`（历史，需上下文） |
| C-11 | M1-Offline artifacts | `python -m m1_offline.demo --write-artifacts` + `sha256sum docs/m1/traces/* docs/m1/reports/*` | `TBD / NOT_RUN` | `<TBD>` | `<...>` | `25ed416a…`/`154ef1d8…`/`8b80a6f3…`（历史；report JSON 含 volatile timestamp，需分字段） |
| C-12 | M1-Offline canonical 回放 | 用 `m1_offline.evaluation.harness.replay_trace` 重建 canonical trace；断言 events/assessments/evidence/final_state | `TBD / NOT_RUN` | `<TBD>` | `<...>` | 19 事件/3 assessments/6 evidence、逐字节等于 live（历史） |
| C-13 | M1-Offline contamination | `run_contamination_suite(...)`（C1–C4） | `TBD / NOT_RUN` | `<TBD>` | `<...>` | C1–C4 PASS、NOT_RUN=0（历史） |
| C-14 | 新 B 集成套件（默认离线） | `pytest tests/m1b_integration -q -m "not live and not network and not requires_isolation_worker"` | `NOT_RUN`（套件未落地；B-PR0 ADR 冻结路径/标记） | `<TBD>` | `<...>` | 新套件独立计数（不得用历史数） |
| C-15 | 隔离 Worker 安全负例 | 仅隔离容器内：`pytest tests/m1b_integration -q -m requires_isolation_worker` | `NOT_RUN` | `<TBD>` | `<...>` | B1-01…06 负例矩阵（协议 §5） |
| C-16 | B 线 demo/UI | `<B-PR5 冻结的命令>`（如 `python -m m1b.demo`） | `NOT_RUN` | `<TBD>` | `<...>` | 新 demo 双跑确定性（TBD） |

### 3.1 证据登记要求

每个 C 行都必须登记到证据包：

```bash
PY="/root/Autonomous Teacher/.venv/bin/python"
"$PY" scripts/m1b/collect_evidence.py \
  --out <EVIDENCE_OUT_DIR> \
  --case-id <CASE_ID> \
  --command "$( ... )" \
  --expected-exit 0 \
  --artifact <若适用> \
  --limitation "<本行限制>"
```

- 无 `--command` / 无 `sha256` 的记录不得进入 PASS 判定（收集器会拒绝；见证据包文档 §4）。
- `EXECUTED_PASS` 只表示命令成功，不等于产品 PASS；证据类需 Reviewer 标注（`evidence_class`）。
- 历史两条线的数字必须分开引用；新套件计数单独统计（§5）。

---

## 4. 历史冻结参考（只引用，不相加）

| 历史线 | 冻结 SHA | 历史结论（引用标签） | 历史数值（`REVIEWER_REPORTED`，仅参考） |
|---|---|---|---|
| M1-A | C6 `3010426…`（C5 `d4f10f3…` + 证据修复） | `PASS_FOR_M1A_OFFLINE_MVP` | 536 tests；demo `b08ceee9…`；evidence `171cc654…`/`5e84229e…`/`23b871a3…` |
| M1-Offline | C2 `052d980d…` | `PASS_FOR_M1_OFFLINE_DESIGN_AND_EVALUATION_SCOPE` | 365 tests；demo hash 依赖公开面上下文（`1d57ca62…`/`2282caff…`）；artifact 见历史 Review |

**强制规则**：

- [ ] 未把 536 与 365 相加，未写"901 tests 统一通过"。
- [ ] 未把历史 PASS 当作本轮集成 PASS；两条线是不同基线/合同/分支，不是连续 PR 链。
- [ ] 历史引用均带 `REVIEWER_REPORTED`/`OWNER_REPORTED` 标签与本报告 §4 表格。
- [ ] 历史 artifact 哈希附生成上下文（冻结 SHA/文件集合），未静默改期望值。

---

## 5. 新 B 集成套件（独立计数；填充前 `NOT_RUN`）

| 项 | 值 |
|---|---|
| 套件路径/标记 | `<B-PR0 ADR 冻结：tests/m1b_integration/ ...>` |
| 本轮执行状态 | `NOT_RUN`（套件未落地） |
| 新套件测试数（独立统计） | `<TBD>`（**不得**写成 536+365 或其它相加数） |
| 分文件计数 | `<TBD>` |
| 失败/跳过明细 | `<TBD>`（每个 skip 必须写理由；静默过滤=弱化行为） |
| evidence case_id | `<B5-01-integration>` |

---

## 6. B4/B5 验收矩阵（填充前全为 `TBD / NOT_RUN`）

| case_id | 目标 | 本轮状态 | 证据（命令/audit-index/raw sha256） | 备注（mock provenance/限制） |
|---|---|---|---|---|
| B4-01 | 双 CF learner 同一 canonical mastery/session journal | `TBD / NOT_RUN` | `<TBD>` | 合成 fixtures、MOCK 学生 |
| B4-02 | 双 interview learner + JD v1→v2 不同证据化计划 | `TBD / NOT_RUN` | `<TBD>` | 合成问答/JD，不编造项目事实 |
| B4-03 | freshness 过期/冲突/未授权来源不得静默进入教学 | `TBD / NOT_RUN` | `<TBD>` | 合成知识源时间语义 |
| B5-01 | Reviewer 独立重跑旧两套 + 新集成套件并标注 mock provenance | `TBD / NOT_RUN` | `<TBD>` | 旧 536/365 仅历史引用，新套件单独计数 |

---

## 7. X-01 / X-02 跨线检查（填充前 `TBD / NOT_RUN`）

| case_id | 检查 | 命令模板 | 本轮状态 | 证据 |
|---|---|---|---|---|
| X-01 | No runtime scope drift（M1 提交不改 `src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate；A 线不改 M1） | `git diff --name-only <base>..<frozen_sha>` + 保护路径过滤 | `TBD / NOT_RUN` | `<TBD>` |
| X-02 | No Live credentials or external network（合成数据、0 付费请求、LiveGate 仍 BLOCKED） | AST/文本 Key/网络扫描 + socket 阻断运行 + 环境检查 | `TBD / NOT_RUN` | `<TBD>` |

- 任一保护路径命中、真实 Key/网络/付费请求出现 → `BLOCKED/STOP`（协议 §12），不得继续写 PASS。

---

## 8. 盲评（deterministic blind-rubric；填充前 `TBD / NOT_RUN`）

- [ ] 明确声明：对确定性 mock learner **不做统计意义上的真实盲评**，只做 fixed-case/fixed-seed/blind-rubric（评分者不见策略版本）对照。
- [ ] case 集/seed/维度/评分函数 sha256 已在运行前预注册（`<TBD>`）。
- [ ] 盲视图/评分函数签名不含 policy/strategy/teacher 标识（静态检查 `<TBD>`）。
- [ ] 两跑 digest/失败清单/variance 一致（`<TBD>`）。
- [ ] 第二 Reviewer/二次 clean archive 复算 blind rubric hash（`<TBD>`）。
- [ ] 报告含 "not real teaching effect"/"no significance claimed"，未写显著提升/学习收益。

---

## 9. 证据类与来源标注（每项结论必须满足）

| 结论/数字 | 证据类 | 来源 | 命令/哈希所在 |
|---|---|---|---|
| `<示例：C-01 结果>` | `DETERMINISTIC` / `MOCK` / `NOT_VERIFIED` | `INDEPENDENTLY_REEXECUTED_THIS_TURN` / `REVIEWER_REPORTED` | `<audit-index case_id + sha256>` |

规则：`MOCK` 不与真实收益同句；`INDEPENDENTLY_REEXECUTED` 仅 Reviewer 本轮真实复跑；`NOT_RUN/BLOCKED/UNVERIFIED` 保留原样；无命令/无哈希的证据不得写 PASS。

---

## 10. STOP 检查与事件记录（全部未勾选 = 未检查）

- [ ] 无真实 API Key/凭证/Provider/付费请求。
- [ ] 无外部网络访问；socket 阻断验证通过。
- [ ] 未修改保护路径（`src/autoteacher_m0/`、`security/`、`bridge/`、`config/g*`、`scripts/g4*`、LiveGate/账本）。
- [ ] 无错误证据分类（MOCK 当收益、OWNER→INDEPENDENT、NOT_RUN/BLOCKED→PASS、536+365 相加）。
- [ ] 所有 PASS 有命令 + raw sha256 + 可复现上下文。
- [ ] 无跨 learner/session 数据泄漏；CODE Judge 未默认暴露可伪造 PASS 的路径。
- [ ] 未在主机直跑恶意/sentinel PoC；负例均在隔离 Worker。
- [ ] 未删除/跳过/弱化断言，未修改冻结期望/fixtures。
- [ ] 未解锁 LiveGate/真实模型授权/改变 M0 决策。

**事件记录模板**（无则写 "none"）：

```text
- incident_id: <TBD>
  time_utc: <TBD>
  trigger: <协议 §12.1 条目编号 + 描述>
  evidence: <路径/sha256>
  action: STOP + 保全 + 通知 Lead/Reviewer
  status: BLOCKED
```

---

## 11. 已知限制 / NOT_RUN（逐条填写，不得省略）

1. 所有学生/教学结果来自合成 fixtures + mock runtime；`MOCK`，不是真实学习收益。
2. 真实学习者/真实教学效果/真实 provider/网络：`NOT_RUN`。
3. CODE Judge 的 OS 隔离若 B-PR1 未验收：`BLOCKED`/`NOT_RUN`，不得暴露不可信 CODE。
4. crash 证据必须真实 SIGKILL（B-PR2）；mock 异常不计入。
5. 历史两套 536/365 只作引用；新套件计数独立。
6. `<TBD: 本轮其它限制>`。

---

## 12. 最终裁定模板（只有填完 §0–§11 才允许选择）

**允许的措辞**（必须逐字包含边界声明）：

- `PASS_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`：
  > Offline synthetic only, not real teaching effect. 本报告仅覆盖离线、合成 fixtures、确定性/mock E2E 的 B 线集成范围；不构成真人学习收益、联网研究、真实 Provider/Live/生产授权，也不改变 M0 G4-H/G5/LiveGate/M0 决策。
- `PARTIAL_FOR_M1B_OFFLINE_INTEGRATION_SCOPE`：附未关闭项清单（case_id→原因→证据）。
- `FAIL`：附 P0/P1 findings 与失败样例（保留原始证据）。
- `BLOCKED`：附外部依赖/人类授权门（H-01/H-02/H-03、G5、LiveGate 等），不得自行解除。

**禁止措辞**（发现即 STOP）：真实学习收益、显著提升、可上线、可交付生产、Live 已授权、真实判题安全、536+365 统一 tests、把 MOCK 写成真实效果。

---

## 附录 A：audit-index 条目模板（占位，不是运行结果）

```json
{"schema_version":"m1b.audit-index.v0","case_id":"<CASE_ID>","run_id":"<RUN_ID>",
 "branch":"<BRANCH>","git_sha":"<FROZEN_SHA>","command":"<COMMAND>",
 "environment":{"TZ":"UTC","PYTHONHASHSEED":"0"},"utc":"<YYYY-MM-DDTHH:MM:SSZ>",
 "exit_code":null,"status":"NOT_RUN","evidence_class":"NOT_VERIFIED",
 "raw_evidence_path":"raw/<RUN_ID>/evidence.json","sha256":"<64_HEX>",
 "limitation":"template placeholder only"}
```

## 附录 B：复跑与哈希清单模板

```bash
PY="/root/Autonomous Teacher/.venv/bin/python"
OUT=<EVIDENCE_OUT_DIR>
"$PY" scripts/m1b/collect_evidence.py --out "$OUT" --case-id <CASE_ID> \
  --command "<CMD>" --expected-exit 0 --artifact <ARTIFACT>
sha256sum "$OUT"/raw/*/evidence.json "$OUT"/raw/*/stdout.log "$OUT"/raw/*/stderr.log
```

| artifact | 路径 | sha256 | 上下文（冻结 SHA/文件集合） |
|---|---|---|---|
| `<TBD>` | `<TBD>` | `<TBD>` | `<TBD>` |

## 附录 C：本报告完整性自检

- [ ] 所有 `TBD` 已被 Reviewer 本轮结果替换，或标注 `NOT_RUN` 并给出原因。
- [ ] 每条 PASS/FAIL 均可在 `audit-index.jsonl` 定位到 case_id + raw sha256。
- [ ] §4 历史引用未相加、未冒充本轮结果。
- [ ] §10 STOP 检查全部逐项勾选。
- [ ] §12 结论包含边界声明与允许措辞。
