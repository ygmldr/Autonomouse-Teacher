# PR1 独立审计 — Broker/Guard 预算不变量修复（F1–F6，离线）

- 版本：REVIEW-CLOSEOUT-PR1-v1（2026-11-14 UTC）
- 审计者：`verify2`（非实现者，未参与 PR1 实现）
- 审计对象：冻结提交 **`fdcfdc965a4eaf092badcdaab4ad44fd06b68607`**（PR1，父 `e8b6e45b19d9001231323c76bc71fa4886be3439`）
  与 owner manifest **`artifacts/m0-closeout-fix-tests/manifest.json`**（sha256 `df14f3c14349f789f5ea6e0c583373f009586b06cabcc105ca7b63beb1510823`，task-41 修正后版本）。
- 审计时仓库 TOP：`9b77a378…`（PR3）→ 最终 `7d2cd3e…`（PR2，并行冻结；**PR1 提交与 PR1 路径未被后续提交改写**，见 §2）。
- 原始证据：[`artifacts/reviewer-closeout-pr1/`](../artifacts/reviewer-closeout-pr1/)（独立 stage、argv/UTC/exit/日志、独立构建、语义核对、环境清理、容器 absence）。

## 0. 结论

**PASS_FOR_DECLARED_OFFLINE_PR1_SCOPE**：PR1 冻结提交与 owner 证据在其声明的离线范围内成立；F1–F6 修复、fail-first、协议 v1 兼容、隔离/无 Key/无真实模型/HTTP、历史 phase5 字节未改均通过独立复核。**未发现阻断性实现/测试/隔离/协议缺陷。**

**一项非阻断证据记录准确性问题 V-PR1-1**：owner manifest 与仓库 `docs/RUNTIME_BUDGET_GUARD.md` 的 Python fail-first/pass 计数与原始日志不一致（manifest：`8 failed, 3 passed` 与 `130 passed`；仓库 docs 该处亦写 `8 failed/3 passed`；而原始日志与独立复跑均为 **`9 failed, 3 passed`** 与 **`131 passed`**；`docs/BUDGET_BROKER.md` 已正确写 `9 failed / 3 passed` 与 `131 passed`）。属文档/证据准确性，需 owner errata/修正；**无需代码变更或新 SHA/重跑 suite**，不改变 PR1 代码结论。见 §7。

## 1. 方法与隔离边界

- 只在既有 fixed-digest 无 Key/禁网隔离 OCI 内执行项目代码（rootfs `25491e45…`、deps `e07729d7…`、image digest `62d3569e…`，nonroot uid 65534、只读 rootfs、cap-drop ALL、no-new-privileges、cgroup 受限、network none、`--unsetenv-all` + 显式 env 白名单）；宿主只做 Git/哈希/数据整理与 podman launcher。
- 审计者用 `git archive fdcfdc9` 生成**独立 stage**（tar sha256 `bb39b395…`，135 文件），未使用 owner 的 `stage-pr1` 作为真值（该目录是 PR1 定稿前的 worktree 快照，与提交存在 5 个 final-docs/src 差异；仅作差异观察，见 §2）。
- 所有运行使用审计者新 argv/新日志/独立容器名 `at-m0-rev-pr1-*`；运行后查询容器 absence；共享 rootfs/deps 实测并在审计窗口内清理 podman 产生的空 mountpoint 目录，恢复 canonical `25491e45…`（§9）。
- 未通过 CLI flag/Markdown/env 解锁任何 Live；未读取真实凭据；未联网/未发真实模型请求。

## 2. Git / 提交范围 / 身份

| 核对项 | 结果 |
|---|---|
| PR1 commit | `fdcfdc9`，父 `e8b6e45`，author/date `2026-11-14 15:07:05 +0000` |
| 变更文件 | **14 个**（`git diff --name-only e8b6e45 fdcfdc9 | wc -l` = 14）：`accounting/broker.py`、`tests/unit/accounting/test_broker.py`、guard `src/index.ts`/README/package.json、`docs/BUDGET_BROKER.md`、`docs/RUNTIME_BUDGET_GUARD.md` + 7 个新文件（2 个容量测试、guard 测试、scripted fixture、fake broker package 3 个） |
| 混入 security/gov | **无**：`--name-only` 中无 `src/.../security/`、`scripts/`、`SECURITY_APPROVALS*`、LiveGate 文件 |
| `git diff --check` | exit 0 |
| phase5 历史字节 | 未改（见 §8）：phase5 manifest `391767d3…`、evidence `df63e46f…`、guard manifest `05224052…`、PR0 baseline `d252c82b…`、v0.5/PR0 docs 均保持 |
| 后续提交影响 | `git diff fdcfdc9 <later HEAD> -- src/.../accounting plugins/runtime-budget-guard tests/unit/accounting tests/integration/budget_bridge docs/BUDGET_BROKER.md docs/RUNTIME_BUDGET_GUARD.md` 为空 → PR1 路径未被 PR2/PR3 改写 |
| 身份变更 | broker `9dce2f93…`→`e0bf1cf8…`；guard src `1ccdb658…`→`0ee49111…`；guard built lib `3c184a62…`→`3d2b9cf5…`；`package-lock.json` 未变 `119ee480…` |
| 14 文件 hash vs manifest | **14/14 与 owner manifest 一致**（独立 sha256 逐项核对，见 evidence manifest） |
| 独立构建 | 从提交 src 在隔离 OCI 重新 tsc：PR1 lib `3d2b9cf5…`（index.d.ts `ad06bc05…`）、旧 lib 从 `e8b6e45` 源码重建 `3c184a62…`（d.ts `125393ad…`），与 owner/历史一致 |

## 3. 独立重跑（新 stage / 新 argv / 新日志，全部隔离内）

| # | 用例 | 命令要点 | UTC（start–end） | exit | 实际日志计数 | 判定 |
|---|---|---|---|---|---|---|
| 1 | PR1 全套 accounting+budget_bridge | `/opt/python/bin/python3.11 -m pytest /project/tests/unit/accounting /project/tests/integration/budget_bridge -q -p no:cacheprovider`（stage=PR1 commit） | 12:12:37–12:12:39 | 0 | **131 passed** | PASS |
| 2 | Python fail-first（旧 broker `9dce2f93…`） | 只跑新增 `test_broker_capacity_f1_f2.py` + `test_stdio_capacity_f2.py`（stage=PR1 stage with e8b6e45 broker） | 12:12:39–12:12:41 | 1 | **9 failed, 3 passed** | PASS（fail-first 成立） |
| 3 | guard 15/15（真实 Cordis public waterfall + committed fake broker fixture） | `/usr/bin/node --test /probe/tests/guard-pr1.test.mjs`（probe=PR1 src+tests+独立 built lib，node_modules `cab77a60…`） | 12:12:51–12:12:53 | 0 | **15/15 pass** | PASS |
| 4 | guard fail-first（旧 lib `3c184a62…`，同 15 用例） | 同上 probe 换成旧 src 重建 lib | 12:12:52–12:12:54 | 1 | **13 failed, 2 passed** | PASS（fail-first 成立） |
| 5 | phase5 broker 148 回归（历史复跑） | phase5 原 argv/scope，stage=phase5 冻结 stage | 12:14:00–12:14:06 | 0 | **148 passed** | PASS（历史可复现） |
| 6 | 协议 v1 兼容回归（PR1 stage 跑 phase5 同 scope） | 同 #5 scope，stage=PR1 commit stage | 12:15:13–12:15:19 | 0 | **161 passed**（148 + PR1 新增 13） | PASS（v1 兼容） |
| 7 | phase5 guard 12+18（历史复跑） | phase5 原 argv（rbg/phase4 stage），历史 plugin/harness | 12:15:42–12:16:07 | 0 | **12/12 case、18/18 selftest**、summary 与历史一致 | PASS（历史可复现；非 PR1 插件） |

> 说明：#2/#4 的 exit=1 是 fail-first 预期失败（新增测试在旧代码上必须失败），不是审计失败；#1/#3/#5/#6/#7 exit=0。所有日志 SHA/字节见 evidence manifest。

## 4. 协议 v1 兼容性

- `git diff e8b6e45 fdcfdc9 -- src/autoteacher_m0/accounting/broker.py` 显示：**消息/响应 schema、op 集合（reserve/settle/fail/snapshot）、envelope 字段未变**；变化仅是服务端容量/幂等语义（F2）与 guard 日志/状态字段（F1/F3–F6）。
- 实测：phase5 原 148 scope 在 PR1 broker 上 **161 passed**（148 旧用例 + PR1 新增 13，全部通过）；旧 phase5 冻结 stage 复跑仍 148 passed；guard 15/15 使用 v1 fake broker 成功。**无需 `protocol_version`/capabilities 握手，未破坏历史 fixture。**
- 只新增内部错误码 `UNKNOWN_OPERATION`（非法 op；不影响合法 v1 客户端）；历史冻结日志/DB 未改写。

## 5. F1–F6 语义核验（源码 + 新增测试 + 独立运行）

| 项 | 结论 | 关键证据 |
|---|---|---|
| **F1** provider 内部 retry 禁用；每 logical stream 独立消耗 step/request；`retry` 仅归因 | **成立** | guard `PROVIDER_AUTO_RETRY_LIMIT=0`（`index.ts:49`）；config 强制 `maxProviderRetries=0`（`:217,220`）；`retry.mode==='always'||maxRetries>0` → `RBG_PROVIDER_RETRY_POLICY_UNSAFE`（`:320`）；reserve 固定 `retry:false` 且日志 `retry_field:'attribution-only'`/`task_steps_charged:1`（`:485-498`）。独立跑：guard tests 1–3（15/15 内）、Python capacity 测试（131 内），旧 lib/broker fail-first 9+13 个失败。 |
| **F2** reserve 为完成操作预留容量；PENDING 满额后 settle/fail 仍可；重复完成幂等；snapshot 不占 journal | **成立** | broker `_operate`：snapshot 直接返回、不 journal（`:179-184`）；settle/fail 走 `_complete`、绕过 cap（`:186-191`）；reserve 准入 `count+pending+2 > max_messages` 拒绝（`:200`）为每个 reservation 预留 1 个完成 slot；`_complete` 对已 settle 返回 `ALREADY_SETTLED`、不新增行（`:227-228`）；handle 中 snapshot 不 journal、new-id 重复完成幂等（`:250-274`）；guard max_messages 上界对齐 100,000（`index.ts:259`）。独立跑：容量测试（max_messages=1/2/3、满额后 settle/fail、snapshot after cap、重复/并发、SIGKILL 重启）全通过；guard 接受 100000/拒绝 100001 用例通过。 |
| **F3** mutation 仅事后审计，不再宣称发包前拦截 | **成立** | guard 在流结束后比较 digest，`RBG_REQUEST_INTEGRITY_UNCERTAIN` + `interception:'post-hoc-only'`（`:804-825`）；文档 §10 明确“不是发包前拦截”；测试断言 provider 可能已进入（`adapterState.invocations==1`）、accounting=WORST_CASE_HELD；无任何代码/文档声称事前费用上限。 |
| **F4** `accounting_status` 机器可读；settle 失败 fail-closed latch；后续 dispatch=0 | **成立** | guard `SETTLE`/`RESULT` 输出 accounting_status（`:524,842-843`）；settle 未知/失败 → `SETTLEMENT_UNCERTAIN`、抛错、`latchSettlementUncertain()`（`:553,836`）；测试：fake broker 在 settle 死亡 → 第一次调用失败、`RBG_RESULT.accounting_status='SETTLEMENT_UNCERTAIN'`、后续 stream provider invocations 仍 1（0 次新 dispatch）、`RBG_UNAVAILABLE{phase:'SETTLING',latch:true}`。 |
| **F5** task id 为 sha256 单射 | **成立** | `encodeTaskId = 'rbg-'+sha256(NFC(sessionId))[0:64]`（`:366`）；测试覆盖 `a/b` vs `a_b`、长公共前缀、Unicode、跨进程稳定、跨 scope 稳定，并断言格式/长度；guard RESERVE 中 task_id 均为 64-hex。 |
| **F6** phase 准确/日志 allowlist/raw stderr 仅受限 0600 文件 | **成立** | 只允许 `BEFORE_DISPATCH/DISPATCHED/SETTLING/UNKNOWN`（`:455,495,512,575,693`）；`#fail` 输出 phase/dispatched/dispatched_count、删除固定 `reservations_not_dispatched`（`:693-711`）；公开日志 ID 全部 hash（`hashId` `:372`）；broker codes allowlist（`:413-420`）；raw stderr 仅在 `RBG_RAW_DIAGNOSTICS_PATH` 显式设置时写 `mode:0o600` 文件，公开只含 count/bytes/sha256（`:424-437`）。测试：`sk-FAKE-SECRET` 哨兵不入公开日志；raw 文件内容命中但 mode 0600；phase 断言正确。 |

**边界/残留（与 PR1 声明一致，不夸大）**：guard 仍只是 logical-stream pre-dispatch；per-internal HTTP/Files/wire attempt 未观测；F3 被篡改请求仍可能已发包；F4 fake broker 是 scripted test double（真实 ack-loss/crash 时序 UNVERIFIED，PENDING 持久性由 Python 测试覆盖）；F2 snapshot 无显式 rate-limit，长期 scope journal 需轮换/评审。无 Live/真实 Key/HTTP。

## 6. fail-first 与通过计数核对

| 项 | 原始日志（owner artifact，hash 校验 OK） | 独立复跑 | owner manifest 记录 | 仓库文档记录 |
|---|---|---|---|---|
| Python fail-first（旧 broker `9dce2f93…`） | `raw/py-old-failfirst3.log`：**9 failed, 3 passed**（sha `518cffab…`） | **9 failed, 3 passed** | ❌ `8 failed, 3 passed`（`fail_first.detail`） | `docs/BUDGET_BROKER.md:457` ✅ 9/3；`docs/RUNTIME_BUDGET_GUARD.md:263` ❌ 8/3 |
| Python 通过（PR1 broker） | `raw/py-new-all4.log`：**131 passed**（sha `528b7caf…`，exit 0） | **131 passed** | ❌ `130 passed`（`pass.detail`） | 两处 docs 均 ✅ 131 |
| Guard fail-first（旧 lib `3c184a62…`） | `raw/node-old-failfirst2.log`：**13 failed, 2 passed**（sha `f4ca6684…`） | **13 failed, 2 passed** | ✅ 13/2 | ✅ 13/2 |
| Guard 通过（PR1 lib） | `raw/node-tests-final.log`：**15/15 pass**（sha `5472c49b…`） | **15/15 pass** | ✅ 15/15 | ✅ 15/15 |

owner `artifact-hashes.sha256` **53/53 OK**（含 raw 日志/result/stage/build 清单），原始证据真实存在且可关联。**V-PR1-1**：manifest 两处 Python 计数与 raw log 不符；`docs/RUNTIME_BUDGET_GUARD.md` 的 8/3 与同 commit `docs/BUDGET_BROKER.md` 的 9/3 自相矛盾。建议 owner 以 errata/文档修正统一为 raw log 的 `9 failed, 3 passed` / `131 passed`；**无需代码变更、无新 SHA、无需重跑 suite**（数字/记录问题）。发现已发 Lead + owner（broker-docs）。

## 7. 隔离、无 Key/模型/HTTP、历史与清理

- 全部容器：`--network none`、`--http-proxy=false`、`--unsetenv-all` + 显式 env、uid 65534、只读 rootfs、cap-drop ALL、no-new-privileges、pids/cpu/memory 限制；无真实 Key/模型/HTTP（测试只用 `sk-FAKE-SECRET*` 假哨兵，公开日志断言不含；仓库测试无 URL/真实凭据）。
- 历史 phase5 字节未改：`phase5-integration/manifest.json 391767d3…`、`manifest.sha256 f2398708…`、`evidence.sha256 df63e46f…`、`runtime-budget-guard/manifest.json 05224052…`；PR0 baseline `d252c82b…`、PR0 docs hash 未变。PR1 commit 未包含任何 artifacts/历史证据路径。
- 无 `git add/commit`；worktree 中并发 PR2/PR3 的提交/文件非本审计写入；审计报告/证据仅落 gitignored `artifacts/reviewer-closeout-pr1/` 与 `docs/REVIEW_CLOSEOUT_PR1.md`。
- **环境清理**：audit 窗口内 podman 在共享 rootfs 创建了空 mountpoint 目录 `out/`、`plugin/`、`target/`（无项目字节；rootfs 文件数始终 5748）；审计结束前 `rmdir` 恢复，canonical rootfs 实测回到 **`25491e45…`**，deps 仍 `e07729d7…`；容器 exact-prefix/全局查询均 0。此为空 mountpoint 的环境卫生事件，不涉及代码/历史字节/隔离放宽。

## 8. 残余风险（范围性，非 PR1 缺陷）

1. 真实 provider 内部 HTTP/wire retry 行为仍 UNVERIFIED（M0 选择禁用而非计数）；F3 仍是事后审计，被篡改请求可能已发包；F4 真实 broker ack-loss/crash 时序 UNVERIFIED（scripted double + Python pending 测试）；F2 snapshot 无显式 rate limit；长期 scope journal cap 仍需轮换/评审。
2. phase5 guard 12+18 仅能在**历史旧 plugin/harness** 上复跑（12/12+18/18 PASS），不能直接等价于 PR1 新插件回归；PR1 新插件由 committed 15/15 覆盖。
3. PR1 仅离线，不改变 E1–E5/Live 状态；Live/P03/watchdog 仍 BLOCKED、DECISION PENDING。
4. V-PR1-1 为记录准确性问题，若未修正会影响后续引用/复核；不阻断 PR1 代码结论。

## 9. 证据索引

- 审计 manifest：[`artifacts/reviewer-closeout-pr1/manifest.json`](../artifacts/reviewer-closeout-pr1/manifest.json)、`manifest.sha256`、`evidence.sha256`；独立 stage `stage/` + `stage.tar`（sha `bb39b395…`）。
- 运行：`logs/{py-pass,py-fail-first,guard-pass,guard-fail-first,p5-broker148-oldstage,p5-broker148-pr1stage,p5-guard12-oldstage}.{argv.json,stdout.log,stderr.log}` + `commands.jsonl`（argv/UTC/exit/sha）。
- 构建：`build-pr1/`（`3d2b9cf5…`）、`build-old/`（`3c184a62…`）；probe：`guard-probe/`、`guard-probe-old/`。
- 环境：`environment-hygiene.txt`、`containers.*`、`podman-ps-all.txt`。
- owner 证据交叉核对：`artifacts/m0-closeout-fix-tests/{manifest.json df14f3c1…, artifact-hashes.sha256 53/53}`。
