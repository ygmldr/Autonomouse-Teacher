# M0 G4-R — 联合回归与实现报告（Integration，无 Key）

- **文档 ID**：`M0-G4R-IMPLEMENTATION-REPORT-v1`
- **实施者**：Integration 子 Agent（`a-impl-core`；非 Lead、非 Independent Reviewer）
- **工作树/分支**：`/root/Autonomous Teacher/worktrees/g4r-phase2` / `work/g4r-phase2`
- **base**：`3e7afee077845a071cd364e93ab209cac20b2d5f`；**冻结 impl**：`d33e0aabd1714a486325b745c436cb59855d6539`
- **环境**：本机、无 Key、无真实 Provider/外部 HTTP/计费；`podman 4.9.3`、Node `v22.23.2`、Python `3.11.15`（venv）
- **证据根（gitignored）**：`artifacts/g4r/integration/`、`artifacts/g4r/integration-regressions/`、`artifacts/g4r/logs/`；结构化索引 `artifacts/g4r/integration/integration-env.json`、`integration-stage.json`

## 0. 摘要

- 冻结 impl `d33e0aa`（相对 `5bf9b8b` 仅 PR-R4 test/tooling 2 补丁：`tests/g4r_packet/support.py→packet_support.py` + import、builder `--impl-sha` 接受 40-hex git commit + content sha；**`git diff 5bf9b8b..d33e0aa -- src/` 为空**）。
- 从 `d33e0aa` 重建**最终 Stage**：`stage-20261120T165407Z`（base/head=`d33e0aa`）在 rootfs canonical 状态下构建成功；早期一次构建因并发容器造成 rootfs 漂移而 **fail-closed**（exit 1，“rootfs is not canonical before build”），属正确行为。
- 联合回归：Host 单进程 **1420 collected / 1412 passed / 5 failed / 3 skipped**（失败逐 nodeid 分类为 ENVIRONMENT_ONLY/FLAKY，0 REAL_REGRESSION）；OCI filtered（rootfs 副本）**1081 tests / 1052 passed / 1 failed / 28 skipped / 69 deselected**（1 failed=ENVIRONMENT_ONLY，legacy 43 deselects 不变 + 显式新增 g4r_auth 26 项）；Node TAP **36/36**；Ruff 变更范围 All checks passed；Scanner 0 findings + positive-control 有效；LiveGate 四入口/strace 全拒绝。
- 关键 L2（独占窗口，逐条串行）：F2 `ok=true`（Echo dispatch=1、Tool two rounds dispatch=2、consistency 全 true、0 real model/HTTP/key）；F5 3/3 case true（timeout-pre-send、revocation-post-reserve、timeout-post-send）；每条前后 rootfs canonical 快照一致。
- **本报告不签发 PASS**；最终裁定由 Independent Reviewer 给出。R5-01..03（F4-06 candidate crash + live Controller）保持 UNVERIFIED（无可控注入）。

## 1. 冻结身份与交付范围

| 项 | 值 |
|---|---|
| base_sha | `3e7afee…` |
| impl_sha（冻结） | `d33e0aabd1714a486325b745c436cb59855d6539` |
| 本分支 HEAD（提交前） | `d33e0aabd1714a486325b745c436cb59855d6539` + 本轮 docs/矩阵提交（见报告消息） |
| 集成分支 | `work/g4r`（Lead 维护） |
| 本 Agent 写入面 | 仅 `docs/…G4R…` 与 `artifacts/g4r/`（gitignored）；**未改 src/tests/scripts/冻结件** |

### 1.1 本轮新增/更新文档

`docs/M0_G4R_IMPLEMENTATION_REPORT.md`（本文件）、`docs/M0_G4R_FINDINGS_AND_DISPOSITION.md`、`docs/M0_G4R_REVIEW_REQUEST.md`、`docs/M0_G4R_HUMAN_HANDOFF.md`、`docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（终稿，唯一 writer）。

## 2. 最终 Stage 身份（`stage-20261120T165407Z`）

| 字段 | 值 |
|---|---|
| stage_dir | `artifacts/g4/c/stages/stage-20261120T165407Z` |
| base_sha = head_at_build | `d33e0aabd1714a486325b745c436cb59855d6539` |
| manifest_sha256 | `cc7ccb61bc4df76675b14e1f73bdd9209d3a13eeda7e79193e913ea284874d03` |
| stage_tree_sha256 | `933f2c07a6c79415183a4d3f1db1ba19249b95d96ee88334bd43e71dd40d3882` |
| trusted_tree_sha256 | `f10053d4107170b0b53362dbc9d1c0120d07dd7ee35339a315749de4b3431add` |
| candidate_tree_sha256 | `131ab68e10f25d4aa893348754100c0fb0e221059b3fa79e3f7be9547c219006` |
| trusted/candidate files | 60 / 6549 |
| loaded source identity | stage trusted **52/52** `.py` == `git show d33e0aa:<path>` blobs |
| adapter built JS | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |
| DSH runtime | `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（`0.2.2-rc.2`，182,717,632 B） |
| Node | `v22.23.2` |
| rootfs / deps | `25491e45…` / `e07729d7…`（构建时 canonical；`stage-summary.rootfs_canonical=true`） |
| 历史 Stage | `stage-20261119T142828Z`（manifest `82e10c6f…`）仅 **HISTORICAL_REFERENCE**，不用于本轮证据 |

## 3. 环境 canonical 与漂移/清理记录（不得声称全程 NO_DRIFT）

漂移链（完整记录见 `artifacts/g4r/integration/integration-env.json`）：

| UTC | rootfs canonical | 说明 |
|---|---|---|
| 2026-11-20T16:43:53Z | `25491e45…` | 冻结值（Reviewer/Lead 观测） |
| 16:52–16:53Z | `0340fb78…` | **漂移窗口**：容器/OCI 活动在冻结 rootfs 创建空挂载点；deps/runtime/stage manifest/adapter 未变 |
| 16:53:34Z | `25491e45…` | Integration cleanup #1 恢复（仅删空 `evidence/var/var/tmp`） |
| 16:54:07–16:54:20Z | `25491e45…` | **最终 Stage 构建成功**（16:52:24 那次 fail-closed 构建因漂移被拒绝） |
| 16:55–16:59Z | `a6737150…` → `e1a8fcf9…` | **漂移窗口 #2**：OCI filtered 直接 `--rootfs` 冻结 rootfs 产生 `evidence/fixtures/plugin/skill/var/var/tmp` + `probe/{lib,node_modules,test,package.json}` |
| 17:01:49Z | `25491e45…` | **cleanup #P0b 精确清理**（6 目录 + probe 污染；保留 probe/、output/ 等既有目录）→ 与冻结值一致 |
| 17:05:50–17:08:20Z | `25491e45…`（T0=T1） | **独占窗口**：无其它容器/suite；L2 串行；OCI 改在 `cp -a` rootfs 副本上运行（运行后删除） |

- 政策：**冻结 rootfs 不再允许直接 `podman --rootfs`**；任何 OCI/容器运行使用 `cp -a` 副本并记录副本创建/删除。
- 事故记录：`artifacts/g4r/integration/INCIDENT_oci_junit_restore_*.log` —— 一次 argv 替换遗漏导致历史证据 `artifacts/g4f/f6/integration/oci/junit-oci-filtered.xml` 被覆盖，已从冻结 Packet 中 `regressions/oci/junit-oci-filtered.xml` **原字节恢复**（sha `7f25ba83…`）；旧 Packet 未改。

## 4. 联合回归计数与失败分类

### 4.1 Host full（单进程，d33e0aa）

- 命令：`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps /root/Autonomous Teacher/.venv/bin/python -B -m pytest tests -q -p no:cacheprovider --junitxml=artifacts/g4r/integration/host-full-junit-20261120T165224Z.xml`
- 计数：**1420 collected / 1412 passed / 5 failed / 3 skipped / 510.8s**（0 collection error；对比 delta 前 5bf9b8b 双 session 的 collection error=REAL_REGRESSION(test-only)，已在 d33e0aa 修复）。
- 失败逐 nodeid 与分类（见 `artifacts/g4r/integration-regressions/host.json`）：

| nodeid | 分类 | 复核 |
|---|---|---|
| `tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src` | **ENVIRONMENT_ONLY**（stale-baseline 断言要求 src==4bd4803；实现必然改动；G4-F 同类 known host failure） | stand-alone FAIL（预期） |
| `tests/integration/budget_bridge/test_g2_dispatch_claim` | **FLAKY_ORDER_DEPENDENT** | 单文件独立运行 9 passed |
| `tests/integration/g4_b/test_manifest_contract.py::test_real_spec_derived_facts_match_policy` | **ENVIRONMENT_ONLY**（漂移窗口 rootfs=a6737150 被断言读到） | 清理后单测 PASS |
| `tests/integration/g4_b/test_manifest_contract.py::test_real_anchor_is_the_frozen_baseline` | **ENVIRONMENT_ONLY**（同上） | 清理后单测 PASS |
| `tests/integration/g4_f2/test_f2_adapter_purpose` | **ENVIRONMENT_ONLY**（config `target-runtime.patch.yml` mode 0644；G4-F P2-08 同类） | `chmod 0444` 后单测 PASS |

- **REAL_REGRESSION = 0**（G4-R 产品代码）；delta 前 5bf9b8b 的 collection error 为测试名遮蔽（`tests/g4r_packet/support.py`），已由 test-only 重冻结修复。

### 4.2 受影响最小集（d33e0aa）

| 套件 | 结果 | 证据 |
|---|---|---|
| `tests/g4r_packet tests/integration/g4_f2` | **42 passed**（9.6s） | `artifacts/g4r/integration/minimal-rerun-20261120T165509Z.log` |
| R1 `tests/integration/g4r_auth` | **26 passed**（206.8s） | 同上 |
| R1 独立探针 `scripts/g4r/r1_independent_probe.py --rounds 50` | **PASS**（0 双授权、0 临时残留、100 worker PID） | 同上 |
| R2 `tests/integration/g4r_recovery` | **19 passed**（11.4s） | 同上 |
| A12 稳定性（R4-07） | **30/30 loops green** | 同上 |

### 4.3 OCI filtered（rootfs 副本；显式 deselect 登记）

- 命令（关键 argv）：`podman run --rm --network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534 -v <oci-stage>:/project:ro -v <deps>:/deps:ro -v <evidence>:/evidence:rw --rootfs <cp -a rootfs copy> /opt/python/bin/python3.11 -B -m pytest tests/ ... 43 legacy --deselect + --deselect tests/integration/g4r_auth`
- 计数：**total 1081 / passed 1052 / failed 1 / skipped 28 / deselected 69 / 80.4s**
- deselect 变化：**legacy 43 不变** + 新增 `tests/integration/g4r_auth`（26 tests，**显式目录级 deselect**，原因=ENVIRONMENT_ONLY：OCI 以 uid 65534 运行使 R1 fixture 授权目录 owner == candidate host uid，产品正确 fail-closed 拒绝 `EXTERNAL_AUTHORIZATION_INVALID`；L1-HOST(root) 26/26 PASS）。
- 唯一失败：`tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text` → **ENVIRONMENT_ONLY**（config 权限/worktree 环境）。
- 旧对照：冻结 G4-F 口径 `1018 passed / 26 skipped / 43 deselected / 0 failed`；legacy deselect 未扩大，新增 deselect 已显式列明供 Reviewer 签收。
- 冻结 rootfs 前后 = `25491e45…`（未污染；副本已删除）。证据：`artifacts/g4r/logs/oci-filtered-deselect.{log,meta}`、`artifacts/g4r/integration/oci/junit-oci-filtered.xml`、`integration-regressions/oci.json`。

### 4.4 Node / Ruff / Scanner / LiveGate

| 项 | 结果 | 证据 |
|---|---|---|
| Node TAP（fixed rootfs） | adapter **9/9** + guard **19/19** + skill **8/8** = **36/36** | `artifacts/g4r/integration/node/*.log` |
| Ruff 变更范围 | **All checks passed** | `artifacts/g4r/integration/ruff-20261120T164816Z.log` |
| Ruff repo-wide | 5 个既有错误（旧 `scripts/g3b|g3c/build_packet.py`、`scripts/g4/build_packet_g4f.py` E741/F401/F541），**非本 PR 引入** | 同上 |
| Scanner self-test | PASS | `artifacts/g4r/integration/scanner-*.log` |
| Scanner 全历史/工作树 | 503 files / 1070 blobs / 208 commits → **findings=0**；`--no-history` findings=0 | 同上 |
| Scanner positive control | **PASS**（伪造 `sk-` 被检出、exit 1、值 masked） | `artifacts/g4r/integration/host-failure-classification-20261120T170902Z.log` |
| LiveGate inspect / require_live | `BLOCKED`（首 reason `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`）/ `SECURITY_BLOCKED` | `artifacts/g4r/integration/livegate-20261120T165255Z.log` |
| run_live / CLI `--live` | `exit 3` / `exit 3`（BLOCKED） | 同上 |
| Adapter 四入口 | `_require_live_authorization` / `_new_harness` / `run` / `resume` = **4/4 SECURITY_BLOCKED** | `host-failure-classification-…log` |
| strace 网络 | run_live=0、CLI=0 行 AF_INET/connect | `livegate-…log` |

## 5. 独占窗口关键 L2（最终 Stage，逐条串行 + canonical 前后快照）

- 窗口：`2026-11-20T17:05:50Z–17:08:20Z`；无其它容器/全量 suite；`podman ps -a` 前后空；log：`artifacts/g4r/integration/exclusive-l2-retry-20261120T170550Z.log`。
- T0 与 T1 快照**完全一致**：rootfs `25491e45…`、deps `e07729d7…`、stage manifest `cc7ccb61…`、stage tree `933f2c07…`。每 case 前后 rootfs 均 `25491e45…`，**本窗口 NO_DRIFT**。
- **F2**（`run_f2_evidence.py --stage <final> --out-dir artifacts/g4r/integration/l2/f2`）：`ok=true, problems=[]`；Echo dispatch=**1**、Tool two rounds dispatch=**2**，digest/usage/ledger consistency 全 true；`real_model_calls=0`, `real_external_http_calls=0`, `provider_keys_seen=0`, `live_gate=BLOCKED`, `rootfs_canonical=true`, `deps_canonical=true`。
- **F5**（`run_g4_f5.py --only timeout-pre-send,revocation-post-reserve,timeout-post-send`）：**3/3 true**，`containers_after=[]`；证据 `artifacts/g4r/integration/l2/f5/`（DB 只读副本、dispatch-window、request-lifecycle、gate journal）。
- 详细 DB/账本数值由 Reviewer 从只读副本独立对账；Owner 不把 summary 当裁定。

## 6. P2 处置摘要（完整见 FINDINGS 文档）

| ID | 处置 | 本轮证据 |
|---|---|---|
| P2-03 并发 consume | **FIXED**（R1 原子 no-replace 发布） | R1 26 passed + 独立探针 50/50；a12 30/30 |
| P2-04 F841 | **FIXED**（删未使用变量） | 变更范围 Ruff All checks passed |
| P2-05 timeout 观测缺口 | **FIXED**（request-lifecycle vs dispatch-window 分离） | R2 19 passed；F5 timeout-pre-send L2 |
| P2-06 recovery reason 覆盖 | **FIXED**（first-cause 保留 + 独立 diagnostic） | R2 19 passed；F5 revocation-post-reserve L2 |
| P2-01 Packet v2 完整性 | **PARTIAL/待最终 Packet** | builder/verifier+mutation suite host PASS；F-C 构建最终 v2 |
| P2-02 证据路径 | **PARTIAL**（SOURCE_ERRATA_APPEND + 新矩阵只引用新证据） | `docs/M0_G4R_SOURCE_ERRATA_APPEND.md` |
| P2-07 LiveGate reasons 一致 | **PARTIAL/待最终 Packet** | cross-ref mutation test PASS（design-level） |
| P2-08 host 失败集合 | **PASS（逐 nodeid 分类）** | 本文件 §4.1 |
| B03/E5-P04 | **UNVERIFIED**（R3 `API_AVAILABLE`，L1 信任边界；不冒充 PASS） | `docs/M0_G4R_REGISTRY_FEASIBILITY.md` |

## 7. 未验证 / NOT_RUN / 风险

- **R5-01..03（F4-06 candidate crash + live Controller）**：无可控 Candidate crash 注入，保持 **UNVERIFIED**（设计记录于 `integration-regressions`/本文 §4；不虚构通过）。
- **REV-01..08**：独立 Reviewer 未开始 → NOT_RUN。
- **RG-05/09/10/12**：NOT_RUN（两轮驱动/真实账本/独立复算未做）；RG-01/02/04/06/07/11 PARTIAL（L1 hook）；RG-08 UNVERIFIED；RG-00/03 PASS。
- **P2-RUN-IDENTITY / USERNS / DISK / F4-R1 / F5-R6 / F1-R4 / F2-R5 / B07 / G4-H-01..06**：维持原有残余（见 HUMAN_HANDOFF）。
- OCI 26→显式 deselect 属**环境 harness**取舍，Reviewer 需签收（legacy 43 未扩大）。
- 本线未产生任何真实 Key/Provider/HTTP/Live；`LiveGate=BLOCKED` 等常量未变。

## 8. 复现入口

```text
cd "/root/Autonomous Teacher/worktrees/g4r-phase2"
git rev-parse HEAD   # d33e0aaa…（+ 本轮 docs 提交）
# Stage 身份：cat artifacts/g4r/integration/integration-stage.json
# 环境/漂移/清理：cat artifacts/g4r/integration/integration-env.json
# 六类回归：ls artifacts/g4r/integration-regressions/{host,oci,node,ruff,scanner,livegate}.json
# 矩阵：docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv
# L2：ls artifacts/g4r/integration/l2/{f2,f5}
```

> 本报告不是 G4-R PASS、不是 E5 Full、不是 G4-H/G5/G6/Live 授权；最终裁定由 Independent Reviewer 从冻结 SHA 独立复现后给出，随后 STOP 等维护者。
