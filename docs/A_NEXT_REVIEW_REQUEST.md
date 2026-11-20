# A-NEXT Independent Review Request（work/a-next，无 Key）

- **文档 ID**：`A-NEXT-REVIEW-REQUEST-v1`
- **发起**：Integrator（a-impl-core）；本文不构成自证/PASS。
- **base**：`fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；**最终集成 HEAD（代码+合并，含 #8.2）**：`4d7c2821e7907be7fa846855e7df25e3616c9fa1`；Host 回归运行 HEAD `1dfb24c`；OCI 有效 run 执行树 `c687738`（随后 #8.2 scripts/tests/docs 修正；OCI 未在最终 HEAD 复跑）。
- **分支/工作树**：`work/a-next` / `/root/Autonomous Teacher/worktrees/a-next`
- **范围**：本机、无真实 Key/Provider/外部 HTTP/Live；`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、`M0=DECISION_PENDING`。

## 1. 合并身份（Reviewer 需实核）

| # | 分支 | SHA |
|---|---|---|
| 1 | fix/a-next-auth-record | e6f3aa6cdaacec8d2e219fe44fd8640b5e036567 |
| 2 | feat/a-next-run-admission | c7eb74e1c2192d3b3732e780e019456d4a47aa3f |
| 3 | docs/a-next-baseline | bf312c8eecf87facc6592d955baf50e9d933c23d |
| 4 | chore/a-next-oci-hygiene | 7d7c0a52abd2a14775795115b8b375c6796bdebb |
| 5 | docs/a-next-handoff | 13e39a4c18df1bfa6e8c226bcba1b13966af6347 |
| 6 | feat/a-next-registry | 748fd0a529270a11b42ca4be23c096fb1b6f9e14 |
| 7 | chore/a-next-packet | ce914c1005cf67d24c2836cd3487ca68e331d21e |
| 8 | test/a-next-rrev6 | 95a020b27ccf05ae3cd504d8c138bc279706fee2 |
| 8.1 | rrev6 docs addendum | 0735d7b8f11770586dda5acf2caf756d81cffd1b |

- 目标 `work/a-next`：`git merge --no-ff` 顺序合并；期望 `git log --first-parent --merges fd1d3a6d101f17e6a86d7c43f06c630326e3e3af..HEAD` 显示 9 个 merge commit（含 addendum），无其它合并。
- 变更清单：`git diff --name-only fd1d3a6d101f17e6a86d7c43f06c630326e3e3af..HEAD` 65 files；`artifacts/a_next/integration/provenance.txt` 有来源 PR 标注；受保护文件仅 authorization.py/controller.py（审计过的 A1/A2 变更）+ 新增 run_admission.py。
- 未修改冻结 v1/v2 Packet 字节、未改旧 Reviewer 报告；未 push。

## 2. Owner 侧证据（已生成，gitignored）

| 证据 | 路径 |
|---|---|
| Host full（1626/1601/7/18，688.5s）+ junit | `artifacts/a_next/integration/host-full.log`、`host-full-junit.xml` |
| Host 失败归类（逐 nodeid） | `artifacts/a_next/integration/summary.json`、本目录 report §2.1 |
| Node TAP 36/36 | `artifacts/a_next/integration/node/{adapter,guard,skill}.log` + `summary.txt` |
| Ruff 变更范围/仓库级 | `ruff-changed.log`、`ruff-repo.log` |
| Scanner self-test/nohist/history/positive control | `scanner-*.log` |
| LiveGate + Adapter 四入口 + strace | `livegate.json`、`adapter-livegate.json` |
| SQLite 只读/immutable 抽查 | `sqlite-probe.json` |
| 合并 provenance/受保护 diff/合并日志 | `provenance.txt`、`protected-diff.txt`、`merge-log*.log` |
| A6 append-only 更新 | `docs/A_NEXT_HUMAN_HANDOFF.md` §9、`docs/A_NEXT_G4H1_DEPLOYMENT_RUNBOOK.md` §16 |

## 3. 请求 Reviewer 复核范围（建议优先级）

1. **合并正确性**：9 个 merge commit 是否与 green 清单一致；无未授权合并；rebase/改写检查；`git diff fd1d3a6d101f17e6a86d7c43f06c630326e3e3af..HEAD` 中每个文件归属 PR；两处 green SHA 替换（16a4187→7d7c0a5、b4b88a5→ce914c1）是否仅 test-helper。
2. **A1/A2 语义**：authorization.py body-id 交叉校验、controller.py run admission 接线；A2 的 P3（ordinal 消耗、`_map_consume_reasons` 子串匹配）是否被正确记录为 fail-closed/非阻断；A2-01..03 保持 NOT_RUN。
3. **受保护文件**：gates/live_controller/cli/dsh_adapter/run_live.sh/config 零改动；新增 run_admission.py 是否在 A2 授权范围内被审阅。
4. **Host 异常等价**：7 个失败逐项复核是否均为 ENVIRONMENT_ONLY/EXISTING（含 3 个 missing G3-D stage、config mode、venv PermissionError、m1_teacher sentinel history）；不得用“没有回归”带过。
5. **Node 36/36**：容器命令、rootfs 副本 T0/T1、frozen rootfs 未变、容器清理。
6. **Scanner/history**：2 个 EXISTING finding 与 baseline 对照；positive control 有效；工作树 0 findings。
7. **LiveGate/四入口/strace**：确认 LiveGate 仍 BLOCKED、0 外部网络、Adapter 四入口 SECURITY_BLOCKED；状态常量未变。
8. **SQLite**：immutable 只读抽查方法是否可接受；证据副本未被修改。
9. **OCI filtered**：等 Lead 安排（不得静默扩大 deselect；legacy 43 + explicit g4r_auth 26 需登记必要性/host 覆盖）。
10. **文档/矩阵**：`A_NEXT_EVIDENCE_RECONCILIATION.md` §9 Owner-measured 状态是否无预填 PASS；incident 披露、v1 LOST、A4 NOT_RUN、EXISTING finding 是否完整。

## 4. 允许裁定（限定 no-key 范围）

`PASS` / `PARTIAL` / `FAIL` / `BLOCKED`（可带严格 scope 与条件）。不得给出 `E5_PRELIVE_FULL PASS`、`G4-H/G5/G6 PASS`、`LIVE_APPROVED`、`M0_GO` 或等价表述；不得代替维护者签 D-14..D-22/G4-H-01..06/G5。

## 5. 已知限制（主动披露）

- OCI filtered 联合回归已完成但 151 failure/error 全为 ENVIRONMENT_ONLY（新测试 OCI 不可移植 → A-NEXT OCI 覆盖 NOT_VERIFIED）；A4-01..03 已按 Reviewer 独立 L2 结论 **PASS（限 L2-REAL-DSH-FAKE/no-key）**、A2-01..03 保持 **NOT_RUN**；B03/E5-P04 UNVERIFIED。P2-ENV-1/失效尝试见 report §6.2。
- Host 7 failures 为环境/既有类；G3-D stage artifact 在本 worktree 缺失（不可重建）。
- 本集成环境为 INCIDENT_20261121 恢复后环境；v1 Packet LOST、v2 historical；不声明全程 NO_DRIFT/完整性。
- Packet v3 最终包尚未构建（等冻结 SHA/staging 清单）；D-14 等人类决策仍 UNSIGNED。

> Reviewer 必须从上述 SHA 独立复现，不得采信 Owner summary；发现 P0/P1/真实 Key/网络/证据篡改 → STOP 并保全证据。
