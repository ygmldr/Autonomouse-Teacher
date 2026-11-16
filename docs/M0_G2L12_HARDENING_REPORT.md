# M0 G2-L1.2 Hardening Report — R-01..R-06

- 任务：`task-85`；日期：2026-11-16 UTC；实现者：verify2
- Base：`ce899ec11b6ce4f02cd91afdf285ec23b593ccb3`（docs-only）
- 实现基线：`bf1e84dab9c74f1bec919633672dc29abfa7a77b`（G2-L1.1）
- Implementation commit：`53d7ba54591798ff3cd6791ea881063351b74dcb`（父 `ce899ec`）
- Docs commit：本报告所属 docs commit（见 git log）
- Scope：**仅 G2-L1.2 R-01..R-06**；不进入 G3；0 真实 Key/模型/网络；固定无 Key OCI（image `62d3569e…`，deps `e07729d7…`，network none/read-only/uid65534/cap-drop ALL）。

## 1. 变更文件
- `src/autoteacher_m0/security/egress.py`（R-02 comment、R-03 cancellation、R-04 run_id 复用、Test-only fields 无行为回归）
- `src/autoteacher_m0/accounting/call_identity.py`（导出 `validate_run_id`）
- `src/autoteacher_m0/accounting/broker.py`（R-05 precheck 进入 journal 事务）
- `src/autoteacher_m0/accounting/ledger.py`（R-05 `journal_once(..., precheck=...)` 同事务 hook）
- `tests/integration/g2_closure/test_g2l1_fix.py`（L11 R-03/R-04/R-05/R-06 用例）
- 未改 `gates.py`/`dsh_adapter.py`/`run_live.sh`；未改历史冻结证据字节；未进入 G3。

> 注：task 清单只列 broker/call_identity，但 R-05 的同事务 precheck 需要 `ledger.journal_once` 可选 hook；该文件为最小必要变更，已在 implementation commit 中冻结并在此明示。

## 2. R-01 — G2-L1.1 Review Packet 元数据 errata（docs/evidence-only）

原问题（独立 Reviewer）：
1. 无实际 packet tar；旧 errata 引用的 tar hash 无交付物。
2. `docs_commit=c140541` 与 packet 内 docs 副本实际 `1d2efe2` 不一致。
3. `evidence_end_utc`（16:24:11Z）早于 RED2（16:30:00Z）。
4. `logs/green2.argv.json` mount `stage-new`（6140 files），非声明 198-file stage。

修复（保留旧文件字节，append-only）：
- Packet 新增 `ERRATA.md`、`ERRATA-MANIFEST.json`、`ERRATA-hashes.sha256`、`ERRATA-packet-integrity.txt`、`ERRATA-TAR.sha256`；旧 `manifest.json`/`hashes.sha256`/`manifest.sha256`/`packet-integrity-report.txt` 和旧 red 日志字节未重写。
- 实际 tar：`artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b.tar`，sha256 `d9f1695127902316c813ea9d310d73a49a6908252b0abfe4f0118187cce11a66`（记录在 `ERRATA-TAR.sha256`）。
- 修正 docs commit：packet docs 副本对应 `1d2efe2`；历史 `c140541` 保留字段；errata `0729cea`/alignment `1d2efe2` 均记录。
- 修正时间窗：`2026-11-16T16:30:00Z`–`2026-11-16T17:40:32Z`（RED2 start → exact-198 green end）。
- 新增 exact-198 GREEN 证据：`logs/green2-exact.{stdout,stderr}.log` + `green2-exact.argv.json`，stage `artifacts/g2l11/stage`（198 files），**24 passed**；旧 green2 日志保留为历史。
- Packet 当前 57 files；`ERRATA-MANIFEST.json` sha256 `8b13f0a7f5f0e750b7f7334dbc7360ef8005df62998f67ea2baf76871b2372c6`；`ERRATA-hashes.sha256` sha256 `bcc9d440dc3516fc3c0b0228bb1f19e953722d58918fd6bb634c9caeb3d4c11f`。

结论：R-01 **FIXED（证据元数据）**；不影响代码/计数结论；原始旧字节保留。

## 3. R-02 — dispatch_count 语义

- 原注释写 “confirmed completed provider returns”，与 `_started_failure` 在 after-entry 失败也递增矛盾。
- 修复：注释改为 “provider callable entry/attempt-start count (including after-entry failures); not confirmed HTTP/completed returns”。行为未改。
- 状态 **FIXED**。

## 4. R-03 — cancellation/interrupt 传播

- provider 路径：`KeyboardInterrupt`/`SystemExit`/`asyncio.CancelledError` 在调用已开始后先 `_started_failure`（保守归因/held/worst-case、无 retry），再原样 re-raise。
- claimer 路径：三类异常先 fail-closed（不产生 permission），再原样传播；不再转为 `BROKER_CLAIMER_ERROR`。
- 测试：R 定向 9 passed（含 provider CancelledError、claimer KI/SE/CancelledError、run_id、PREP-06、JRN-05）。
- RED：旧基线 R 定向 **5 failed / 4 passed**（provider/claimer 中断传播、200 字符 run_id）；旧代码未抛/接受。JRN-05 旧基线通过（并发无效 completion 为运行时竞态，不能稳定复现 RED），不作为行为 RED。
- 状态 **FIXED**（cancellation KPI；G3 的跨进程持久 cancellation 语义仍依赖后续 gate）。

## 5. R-04 — Prepared run_id 复用 CallIdentity 校验

- `accounting/call_identity.py` 新增 `validate_run_id`（非空、≤128、无控制字符；Unicode 允许）。
- egress `prepared_schema_error` 调用该唯一校验；200 字符 run_id 在 claimer 前拒绝；Unicode 合法 run_id 通过。
- 测试：`L11-R04` 两例 PASS；旧基线 200 字符被接受（RED）。
- 状态 **FIXED**。

## 6. R-05 — completion precheck 与 journal 同事务

- `ledger.journal_once(message_id,digest,operation,precheck=None)`：同一事务内先查同 id，再执行 precheck；precheck 拒绝则不插 journal 行；合法才执行 operation+insert。
- broker 的 unknown/non-PENDING/route/usage precheck 移入该回调，消除“预检后事务外插入”的竞态。
- 测试：`L11-JRN-05` 双 Broker 并发 unknown completion 后 journal 行 0；原有 JRN-01..04、v1 幂等回归通过。
- 旧基线 JRN-05 通过（竞态未稳定触发），因此 R-05 RED 证据为**非确定性/不可伪造**；实现采用同事务硬上界并由 GREEN/回归证明。
- 状态 **FIXED（事务原子性）**；不声称远端费用原子性。

## 7. R-06 — RED2 计数与 self-consistent schema 负例

- `docs/M0_G2L11_FIX_REPORT.md` 旧 RED 10/14 已改为 **8/16 red2**，并指向 errata；Review Request 此前已为 red2 表述。
- 新增 `L11-PREP-06`：v0/v999 + 重算 digest/call_id 自洽，仍必须在 claimer 前拒绝。该测试在 `bf1e84d` 已通过（T3 schema 检查已存在），属回归/质量加固；在更早 base 不是行为 RED，不伪造。
- 状态 **FIXED（docs/test quality）**。

## 8. 验证（fixed no-key OCI）

- R 定向 RED（bf1e84d + committed tests）：**5 failed / 4 passed**（`artifacts/g2l12/logs/red.stdout.log`）。
- R 定向 GREEN：**9 passed**（`impl-targeted.stdout.log`）。
- 全量 `tests/`：**634 passed, 1 skipped**（`impl-full.stdout.log`）。
- verify script：**status=PASS**；Ruff repo-wide：**All checks passed!**
- Stage `git archive 53d7ba5`：202 files，normalized `3b12e6fbb4d2dc990314860cde91157f6264344900971f1f74d6c17fefca9dc9`。
- 容器 absence=0；0 真实 Key/模型/外部 HTTP。

## 9. 残余 / G3

- T6 DSH Plugin/SDK Node B 层仍 BLOCKED（OCI 无 node；未伪造 PASS）。
- cancellation 跨进程持久语义、真实 wire/usage/invoice/exactly-once、远端 tool registry、旧 v1 unbound claim 属 G3。
- R-01 仅修正证据元数据，不改变 bf1e84d 历史字节或既有结论。

## 10. STOP

G2-L1.2 R-01..R-06 完成；G3 未启动；等待 Lead 审计后派独立 Reviewer。无 Live/GO。
