# M0 G4-R — Findings 与处置（Agent 建议，未签核）

- **文档 ID**：`M0-G4R-FINDINGS-v1`
- **性质**：Agent 只建议，**不代签 ACCEPT**；所有“维护者决策”栏保持空白。
- **冻结 impl**：`d33e0aabd1714a486325b745c436cb59855d6539`；base `3e7afee…`
- **证据**：`artifacts/g4r/integration/`、`artifacts/g4r/integration-regressions/`（gitignored）；矩阵终稿 `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`

## 1. G4-F P2-01..P2-08 处置（本轮）

| ID | 现状 | 本轮处置/证据 | 建议 | 维护者决策（空） |
|---|---|---|---|---|
| P2-01 Packet sidecar/tree 漂移 | v1 保持不可变；旧问题记录于 `M0_G4F_REVIEW_ERRATA.md` §4.1 | 新 builder/verifier（`scripts/g4r/build_packet_g4r.py`/`verify_packet_g4r.py`）严格全树 + mutation suite：sidecar/隐藏/未知/symlink/mode/tamper 全部 fail（host `tests/g4r_packet` 9 passed）；最终 v2 Packet 由 F-C 构建，本文只提供 manifest 所需计数与 Stage 身份 | **FIX（新 v2 包）+ 旧包只读** | ☐ 采用 v2  ☐ 保留 v1+errata  ☐ 其它 |
| P2-02 F2-07 证据路径 | 旧矩阵字节不改 | `docs/M0_G4R_SOURCE_ERRATA_APPEND.md` 记录旧路径/事实；本矩阵所有 `source_evidence` 指向本轮实际 `artifacts/g4r/…` 运行 | **FIX（新矩阵/errata）** | ☐ 接受  ☐ 要求修正  ☐ 其它 |
| P2-03 A12 并发 consume | `FIXED`（R1 原子 no-replace 发布：tmp→fsync→os.link→fsync(dir) + loser 有界读重试） | R1 suite 26 passed（d33e0aa）、独立探针 50/50（0 双授权/0 temp）、a12 30/30；L1-HOST | **ACCEPT（需 Reviewer 独立复测）** | ☐ 接受  ☐ 要求补测  ☐ 其它 |
| P2-04 F841 lint | `FIXED` | 变更范围 Ruff All checks passed；仅删 1 行未使用变量 | **ACCEPT** | ☐ 接受  ☐ 其它 |
| P2-05 timeout-pre-send 观测缺口 | `FIXED`（request-lifecycle 与 dispatch-window 分离；未进入 Controller 不伪造 dispatch） | R2 19 passed；F5 timeout-pre-send L2 ok（Real DSH，0 reserve/Fake） | **ACCEPT（需 Reviewer 抽查）** | ☐ 接受  ☐ 要求补测  ☐ 其它 |
| P2-06 recovery reason 覆盖 | `FIXED`（保留 first cause + 独立 recovery diagnostic；Broker 仍唯一费用权威） | R2 19 passed；F5 revocation-post-reserve L2；`M0_G4R_R2_RECOVERY_REPORT.md` | **ACCEPT（需 Reviewer 抽查）** | ☐ 接受  ☐ 要求补测  ☐ 其它 |
| P2-07 LiveGate reasons 1/4 | 新 builder 在同一次 `inspect` 输入下交叉引用 manifest/env/review reasons；mutation test 证明差异即 fail（R4-13 PARTIAL，等最终 Packet） | `tests/g4r_packet` design-level 通过；最终 v2 包待 F-C | **FIX（最终 Packet 内一致性）+ Reviewer 签收** | ☐ 接受  ☐ 要求补验  ☐ 其它 |
| P2-08 host 失败集合/归因 | 逐 nodeid 分类完成：1420 collected/1412 passed/5 failed/3 skipped；**0 REAL_REGRESSION**（1 stale-baseline、1 flaky-order、3 漂移窗口/config-mode 环境，复核通过） | `integration-regressions/host.json` | **ACCEPT（含分类记录）** | ☐ 接受  ☐ 其它 |

## 2. 本轮新发现

| ID | 发现 | 性质/影响 | 处置/建议 |
|---|---|---|---|
| **NEW-01** | `tests/g4r_packet/support.py` 与 `tests/integration/g4_f2/support.py` 同名遮蔽 → `pytest tests` 2 collection error（Delta-pre `5bf9b8b`） | **REAL_REGRESSION（test-only）**；产品代码无关；Lead 已授权 test-only 修复并**重新冻结**为 `d33e0aa`（`packet_support.py`） | **FIXED（d33e0aa）**：冻结树单进程 0 collection error；记录保留于本文与矩阵 R4-09 residual |
| **NEW-02** | 冻结 rootfs 被 OCI/容器直接 `--rootfs` 运行污染（16:52–16:53、16:55–16:59 两窗口；空挂载点目录 + probe/ 污染） | **P1 环境完整性**（不是产品缺陷）；导致一次 Stage 构建正确 fail-closed | **FIXED/MITIGATED**：精确清理至 `25491e45…`；政策改为 `cp -a` rootfs 副本运行；漂移链/清理记录写入 `integration-env.json`；**不得声称全程 NO_DRIFT** |
| **NEW-03** | 历史证据 `artifacts/g4f/f6/integration/oci/junit-oci-filtered.xml` 因 argv 替换遗漏被覆盖 | 证据卫生（gitignored，非 Packet/非 Reviewer 报告） | **FIXED**：从冻结 Packet `regressions/oci/junit-oci-filtered.xml` 原字节恢复（sha `7f25ba83…`）；`INCIDENT_oci_junit_restore_*.log` 如实记录 |
| **NEW-04** | OCI filtered（`--user 65534`）下 R1 auth 测试 25+1 失败：`EXTERNAL_AUTHORIZATION_INVALID: authorization directory is owned by the candidate host uid` | **ENVIRONMENT_ONLY（harness）**：L1-HOST(root) 26/26 PASS；产品 fail-closed 行为正确 | **显式 deselect** `tests/integration/g4r_auth`（26 tests，legacy 43 不变，total 69）+ 日志/矩阵登记；Reviewer 签收 deselect 差异 |
| **NEW-05** | `budget_bridge/test_g2_dispatch_claim` 在 full suite 中一次失败、单文件 9 passed | **FLAKY_ORDER_DEPENDENT**（非产品回归；与并发/顺序相关） | 记录于 R4-09 分类；建议后续固定隔离环境复跑 |
| **NEW-06** | 最终 Stage 身份与旧 G4-F Stage（`82e10c6f…`）不同 | 预期：impl 改动 + 新测试；旧 Stage 仅 HISTORICAL_REFERENCE | 最终 Packet manifest 必须引用 `stage-20261120T165407Z`（manifest `cc7ccb61…`、tree `933f2c07…`） |

## 3. B03 / E5-P04 Registry 残余

- R3 Spike 结论：`API_AVAILABLE`（Runtime `0.2.2-rc.2` 有公开 tool registry/生命周期 API；无需 fork），但**证据等级上限 L1-instrumented**；Candidate 自报 snapshot 不能作为独立 OS attestation。
- RG：RG-00 PASS、RG-03 PASS、RG-01/02/04/06/07/11 PARTIAL（L1 hook/负例）、RG-05/09/10/12 NOT_RUN、RG-08 UNVERIFIED。
- **B03/E5-P04 仍 `UNVERIFIED`**；补偿控制 = Controller per-dispatch approved tool name+schema 白名单（Reserve/Claim 前拒绝未知/额外/重复 tool）+ Candidate `--network none`。
- 建议：**ACCEPT-with-compensating-control（G4-R/no-key）**；E5-Full/G5 前需维护者+Security Reviewer 明确签收，或由 DSH 提供权威导出。**不得把 R3 结果写成 E5-P04 PASS。**

## 4. 维持未关闭的风险（不在本轮"顺手关闭"）

`P2-RUN-IDENTITY`（SO_PEERCRED 非 per-run）、`P2-USERNS`、`P2-DISK`、`F4-R1`（字节级 context）、`F5-R6`（外部 SIGKILL 窗口）、`F1-R4`（scanner 启发式）、`F2-R5`（audit 写失败不 fail-closed）、`B07`（title fallback-only）、`G4-H-01..06`（人类信任根/Key Broker/Egress/定价/E5 Full/G5 授权）。
**R5-01..03（F4-06 candidate crash + live Controller）**：本轮无可控注入，保持 **UNVERIFIED**；不得宣称“全部恢复语义已证”。

## 5. 建议（汇总，非签核）

1. 接受 `P2-03/04/05/06` 修复，但以 Independent Reviewer 从 `d33e0aa` 的独立复测为准（R1/R2 stress、F5 L2、DB 只读对账）。
2. 采用 F-C 基于本报告 Stage/计数构建的**最终 Packet v2**；旧 Packet/报告保持只读。
3. 在 Packet/报告中**显式登记**：环境漂移窗口、清理恢复、Stage fail-closed、OCI deselect 差异（43 legacy + 26 explicit g4r_auth）、历史 junit 恢复事件。
4. `B03/E5-P04` 维持 UNVERIFIED；human signoff 前不得进入 E5-Full/G5。
5. 对 NEW-05 flake 与 NEW-02 环境纪律做后续流程项（非阻断）。

> 所有处置均待维护者/Independent Reviewer 决定；本文件不改变任何状态常量与授权。
