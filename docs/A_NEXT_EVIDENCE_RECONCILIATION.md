# A-NEXT 证据矩阵 v2 — 对账方法与占位（append-only）

- **文档 ID**：`A-NEXT-EVIDENCE-RECONCILIATION-v2-draft`
- **状态**：`DRAFT_PENDING_INDEPENDENT_REVIEW`（本文件不预填任何 PASS；所有 reviewer 列保持 TBD）
- **基线**：`work/g4r = fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；冻结 impl `d33e0aabd1714a486325b745c436cb59855d6539`；main `3e7afee077845a071cd364e93ab209cac20b2d5f`
- **旧矩阵（冻结，不可改）**：`docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`（65 cases；sha256 `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382`）
- **A-NEXT 19 项矩阵**：`/root/handoffs/AT_LeadA_G4R_Next/TEST_EVIDENCE_MATRIX.csv`（sha256 `efdae927008ce4fe282b9f5175f9a308a4ab0482bb49116237afa7807464aa19`）

## 1. 规则（append-only 与状态词表）

1. 旧 65 行矩阵与旧 Packet/Review **字节冻结**，本文件只做 append-only 对账，不回写旧 CSV。
2. 每个旧行的 `reviewer_final_status` 必须由 Independent Reviewer 亲自运行/核对后填写，并绑定 `evidence_ref` + `sha` + `reviewer_ran`；Owner 不得预填 PASS。
3. 状态只允许：`PASS` / `PARTIAL` / `NOT_RUN` / `UNVERIFIED` / `BLOCKED`（大小写固定）。
4. 缺证据的行必须保留 `NOT_RUN`/`UNVERIFIED`；不得用“没有回归”之类的总结替代逐 ID 证据。
5. 任何新的 v3 Packet 证据只引用新的 Packet 身份（`artifacts/review-packet-a-next-v3-<impl_sha>/`）；旧 v1/v2 只允许 SHA-only 历史引用。
6. A-NEXT 19 行中的 `initial_status` 来自交接包，仅为**初始**状态；`final_status` 在本轮仍为 TBD（除 HUMAN/BLOCKED 维持 BLOCKED）。

## 2. 当前快照（非终审）

| 集合 | 计数 | 说明 |
|---|---|---|
| 旧 65 行（G4-R 快照） | 65 | BLOCKED=6 / NOT_RUN=12 / PARTIAL=14 / PASS=29 / UNVERIFIED=4 |
| A-NEXT 19 行（交接初始） | 19 | BLOCKED=2 / NOT_RUN=17 |

> 上述计数是**待对账的输入快照**，不是 A-NEXT 终态，也不是最终 Review 结论。

## 3. INCIDENT_20261121 — 环境事件（强制披露）

- **时间**：2026-11-20T19:53Z 前后，repo `artifacts/`（含冻结 rootfs 副本、foundation/deps、G4-R 证据目录）被误删。
- **恢复来源**：`/root/a-next-artifacts-restored-20261121.tar`，sha256 `11172f0268cdf2dc2bde08e90d9d93c0a444b134f8eaab9a712057c9d5159d42`。
- **恢复后复验**：rootfs canonical = `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`；deps canonical = `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（与冻结声明一致）。
- **损失**：**v1 Packet 原始字节 LOST**（`artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99`），不可再独立核验/逐字节比对；只保留 SHA-only 历史引用。v2 Packet 保持历史引用，v3 构建不修改其字节。
- **禁止声明**：不得写“全程 NO_DRIFT”或“证据完整/无缺失”。v3 Packet 的 manifest/README 必须内嵌本披露（见第 6 节）。
- **A-NEXT 影响**：任何引用旧 artifacts 的证据行必须注明“恢复后重验（rootfs/deps 哈希一致）”，并区分“恢复前原始字节”与“当前哈希可验证内容”。

## 4. 旧 65 行 append-only 对账（Reviewer 填终态）

列：`case_id`、旧快照状态（冻结 CSV 原值，只读）、`reviewer_final_status`（TBD）、`evidence_ref`（TBD）、`evidence_level`（TBD）、`sha`（TBD）、`reviewer_ran`（TBD）。

| case_id | old_status | reviewer_final_status | evidence_ref | evidence_level | sha | reviewer_ran |
|---|---|---|---|---|---|---|
| R0-01 | PASS | TBD | TBD | L0-STATIC | TBD | TBD |
| R0-02 | PASS | TBD | TBD | L0-STATIC | TBD | TBD |
| R0-03 | PASS | TBD | TBD | L0-STATIC | TBD | TBD |
| R0-04 | PASS | TBD | TBD | L0-STATIC | TBD | TBD |
| R0-05 | PASS | TBD | TBD | L0-STATIC | TBD | TBD |
| R1-01 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-02 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-03 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-04 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-05 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-06 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-07 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R1-08 | PASS | TBD | TBD | L1-HOST | TBD | TBD |
| R2-01 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-02 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-03 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-04 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-05 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-06 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-07 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-08 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R2-09 | PASS | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| RG-00 | PASS | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-01 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-02 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-03 | PASS | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-04 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-05 | NOT_RUN | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-06 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-07 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-08 | UNVERIFIED | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-09 | NOT_RUN | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-10 | NOT_RUN | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-11 | PARTIAL | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| RG-12 | NOT_RUN | TBD | TBD | L2-REGISTRY-RUNTIME | TBD | TBD |
| R4-01 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-02 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-03 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-04 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-05 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-06 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-07 | PASS | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-08 | PASS | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-09 | PASS | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-10 | PASS | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-11 | PASS | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-12 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R4-13 | PARTIAL | TBD | TBD | L1-PACKET | TBD | TBD |
| R5-01 | UNVERIFIED | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R5-02 | UNVERIFIED | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| R5-03 | UNVERIFIED | TBD | TBD | L2-REAL-DSH | TBD | TBD |
| REV-01 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-02 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-03 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-04 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-05 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-06 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-07 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| REV-08 | NOT_RUN | TBD | TBD | L2-MIXED | TBD | TBD |
| G4-H-01 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |
| G4-H-02 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |
| G4-H-03 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |
| G4-H-04 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |
| G4-H-05 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |
| G4-H-06 | BLOCKED | TBD | TBD | HUMAN-REQUIRED | TBD | TBD |

## 5. A-NEXT 19 行（A0-01..A6-02、X-01/02）

`final_status` 初始：除 HUMAN 行维持 `BLOCKED` 外，其余统一 `NOT_RUN`（待 Reviewer 证据）；Owner 不得自行升级为 PASS。

| case_id | line | priority | goal | acceptance | evidence_level | initial_status | owner | final_status | evidence_ref | sha |
|---|---|---|---|---|---|---|---|---|---|---|
| A0-01 | A | P1 | Branch arbitration | Diff and conflict matrix for work/g4r vs work/m0-g4h0 with no safety regression | SOURCE+TEST | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A0-02 | A | P1 | Reviewer matrix reconciliation | Append-only reconciliation of all 65 matrix rows with final Reviewer and SHA evidence | REVIEW+EVIDENCE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A0-03 | A | P1 | Immutable rootfs | No --rootfs frozen mount; tests use fresh writable copies and SHA T0/T1 consistent | L2-OS | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A1-01 | A | P1 | Use record body ID | Body authorization_id must match path and approved auth id or INVALID | L1-HOST | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A1-02 | A | P1 | Use record crash windows | Exactly one accept and stable loser fail-closed across concurrency/link/fsync/crash | L1-HOST | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A2-01 | A | P1 | Run admission binding | Trusted test-only run gate consumes once before reserve; no bypass | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A2-02 | A | P1 | Multi call per run | Authorized multi step calls work while reuse across run/epoch is denied | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A2-03 | A | P1 | Missing authorization | Invalid/revoked/unbound auth yields 0 Reserve 0 Fake 0 Attempt | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A3-01 | A | P1 | Runtime registry authority | Either independent trusted snapshot and tool-exec deny or explicitly UNVERIFIED | L2-REGISTRY | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A3-02 | A | P1 | Registry adversarial | Two-turn resumed late registration and observer-loss attacks classified honestly | L2-REGISTRY | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A4-01 | A | P1 | R-REV6 dual principal | Reviewer independently reruns Echo Tool Resume Replay and authentic digest joins | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A4-02 | A | P1 | Candidate crash Controller alive | Injection proves no duplicate dispatch and held unknown cost | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A4-03 | A | P1 | Broker crash/restart | Reserve/Claim/receipt/settlement conservation with no double charge | L2-REAL-DSH-FAKE | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A5-01 | A | P1 | Packet full inventory | No unlisted sidecar symlink hardlink mode or hash mutation accepted | L1-PACKET | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A5-02 | A | P2 | Host/OCI exceptions | 5 host failures and 69 deselects individually documented and reviewer-classified | L1-HOST+OCI | NOT_RUN | LeadA | NOT_RUN | TBD | TBD |
| A6-01 | A | HUMAN | Trust root and live G4-H1 | Human signs off and deploys trust root key broker egress watchdog E5-Full | HUMAN | BLOCKED | Maintainer | BLOCKED | TBD | TBD |
| A6-02 | A | HUMAN | One bounded real G5 trial | Separate human explicit approval after full gates | HUMAN | BLOCKED | Maintainer | BLOCKED | TBD | TBD |
| X-01 | CROSS | P1 | No runtime scope drift | M1 commits never modify security bridge or LiveGate and A commits never modify M1 code | STATIC | NOT_RUN | LeadA+LeadB | NOT_RUN | TBD | TBD |
| X-02 | CROSS | P1 | No Live credentials or external network | All new tests synthetic with 0 paid model and clear blocked gates | STATIC+OS | NOT_RUN | LeadA+LeadB | NOT_RUN | TBD | TBD |

## 6. A5-02：Host / OCI 例外逐项文档化（不静默扩大）

### 6.1 Host 5 failures（G4-R 恢复后重验口径：1420 collected / 1412 passed / 5 failed / 3 skipped）

| # | nodeid | 分类 | 基线/环境等价说明 | Reviewer 复跑要求 |
|---|---|---|---|---|
| 1 | tests/integration/g3d/test_d3_contract.py::test_runner_does_not_modify_product_src | ENVIRONMENT_ONLY（stale-baseline） | 断言要求 src == 4bd4803；G4-R 实现必然改动 src；与 G4-F 已知 host failure 同类，单测独立仍失败属基线过期，不是产品回归。 | 在干净 worktree 复核 src 基线断言；确认属于过期基线而非 G4-R 引入。 |
| 2 | tests/integration/budget_bridge/test_g2_dispatch_claim | FLAKY_ORDER_DEPENDENT | full suite 一次失败；单文件独立运行 9 passed（G4-R 记录）。 | 重复 10 次单文件与 full suite，统计 flake 率；确认无产品路径差异。 |
| 3 | tests/integration/g4_b/test_manifest_contract.py::test_real_spec_derived_facts_match_policy | ENVIRONMENT_ONLY（rootfs 漂移窗口） | 运行时 rootfs canonical=a6737150（16:55–16:59Z 漂移窗口）；清理恢复 25491e45 后单测 PASS。 | 在 canonical rootfs + 独占窗口复跑；记录 T0/T1。 |
| 4 | tests/integration/g4_b/test_manifest_contract.py::test_real_anchor_is_the_frozen_baseline | ENVIRONMENT_ONLY（rootfs 漂移窗口） | 同上；恢复后单测 PASS。 | 同上。 |
| 5 | tests/integration/g4_f2/test_f2_adapter_purpose | ENVIRONMENT_ONLY（config mode 0644） | config/dsh/target-runtime.patch.yml mode 0644 与冻结 0444 不符；chmod 0444 后 PASS（G4-F P2-08 同类）。 | 复核 config mode 并复跑。 |

结论：0 REAL_REGRESSION（G4-R Owner 分类）；A-NEXT 仍要求 Reviewer 逐项复跑，不得用“没有回归”一句话带过。

### 6.2 OCI 69 deselects（43 legacy + 26 explicit g4r_auth）

| 项 | 数量 | 必要性 | Host 覆盖 | 缺失的真 OCI 用例 |
|---|---|---|---|---|
| legacy G4-F deselect 列表 | 43 | 冻结 G4-F 实测口径，本轮**未增加**；保持原样 | G4-F 历史 host 覆盖记录 | 需维持旧列表可追溯（旧 Packet/证据） |
| 新增 `tests/integration/g4r_auth` | 26 | OCI filtered 以 `--user 65534` 运行；R1 auth fixture 授权目录 owner=65534，与“不得为 candidate host uid”的 fail-closed 校验冲突，属 harness/环境类 | L1-HOST(root) 26/26 PASS + 独立探针 50/50 | 在合理受信 OS fixture 中运行 R1 auth（需 root 或不同 uid 假设）；本轮未做 → 记 UNVERIFIED 而非 PASS |

OCI filtered 新计数（rootfs 副本、显式 deselect 后）：total 1081 / passed 1052 / failed 1 / skipped 28 / deselected 69；唯一 failed = `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`（config 权限/worktree 环境，ENVIRONMENT_ONLY）。

> 任何新增 deselect 必须在此表登记原因/列表/总数变化，并由 Reviewer 签收；禁止静默扩大。

## 7. Packet v3 身份占位（阶段 2 填写）

| 字段 | 值 |
|---|---|
| packet 目录 | `artifacts/review-packet-a-next-v3-<impl_sha>/`（新身份，不复用/覆盖 v1/v2） |
| impl SHA（冻结集成） | TBD（等 Lead 集成冻结 SHA） |
| manifest.json sha256 | TBD |
| hashes.sha256 sha256 | TBD |
| payload tree sha256 | TBD |
| payload content sha256 | TBD（payload-only，独立于 impl SHA） |
| payload 文件数 / hashes 条目数 | TBD |
| frozen rootfs T0/T1 | TBD（构建窗口 T0==T1；rootfs=25491e45…） |
| INCIDENT_20261121 披露 | 必须在 manifest/README 内嵌入（v1 LOST；恢复 provenance） |
| Reviewer 独立 verify | TBD（`scripts/a_next/verify_packet_v3.py --packet-root …`） |

## 8. 终态 reconciliation 方法（Reviewer 执行）

1. 从冻结 SHA/新 Packet 身份独立复现，不采信 Owner summary。
2. 对每个 case 记录：`reviewer_final_status`、`evidence_ref`（原始日志/JSON 路径）、`sha`（Git/Stage/Packet/rootfs/runtime）、`reviewer_ran=true/false`、`limitation`。
3. 旧 65 行与新 19 行分别 append；同 ID 冲突时保留两行（旧快照 + 新证据）并标注来源，不覆盖。
4. 维持 `B03/E5-P04 = UNVERIFIED`、`G4-H/G5/G6/LiveGate` 状态不变；任何人类同意另行留痕。
5. 本文件中的 TBD 只能由 Reviewer/维护者填写；Agent 不得代填 PASS。

> 本文件为 DRAFT 占位；不改变任何冻结字节、不改变任何门状态、不预填 PASS。

## 9. 集成阶段 Owner-measured 状态（append-only；非 Reviewer 终态）

> 追加于集成阶段。**不修改**上文任何行、不预填 PASS；所有 `reviewer_final_status` 仍为 TBD。

- 集成身份：`work/a-next` HEAD `d553bba4e0cee61410f5e08a462c4ead8e7862b9`（base `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；Host 回归运行 HEAD `1dfb24c`，其后仅 docs-only addendum）。完整证据：`artifacts/a_next/integration/`（host-full.log/junit、node/、scanner-*.log、livegate.json、sqlite-probe.json、provenance.txt、summary.json）。
- Host full：**1626 collected / 1601 passed / 7 failed / 18 skipped / 0 collection error**；7 failures 逐 nodeid = ENVIRONMENT_ONLY（6）/ EXISTING（1），**0 REAL_REGRESSION**（详见 `docs/A_NEXT_IMPLEMENTATION_REPORT.md` §2.1）。
- Node TAP 36/36；Ruff 变更范围 All checks passed；Scanner self-test PASS、worktree 0、history 2（EXISTING LeadB m1_teacher sentinel）；LiveGate BLOCKED / 四入口 SECURITY_BLOCKED / strace 0；SQLite immutable 抽查通过。
- OCI filtered = **NOT_RUN**（待 Lead 批准；计划登记 legacy 43 + explicit g4r_auth 26，不静默扩大）。

### 9.1 A-NEXT 19 行 Owner-measured（Reviewer 终态仍 TBD）

| case_id | owner_measured | evidence_ref | reviewer_final |
|---|---|---|---|
| A0-01 | PARTIAL | docs/A_NEXT_BRANCH_RECONCILIATION.md（已合并）；reviewer 独立确认待办 | TBD |
| A0-02 | PARTIAL | 本文件 scaffold + §9；Reviewer 逐 ID 对账待办 | TBD |
| A0-03 | PARTIAL | oci_guard/rootfs_guard 工具（hygiene 套件 38 passed）+ 本轮 Node/OCI 均用 rootfs 副本；"全程无 frozen --rootfs" 需 Reviewer 抽查 | TBD |
| A1-01 | PARTIAL | A1 套件已合并；host full 中 a_next_auth 全绿（Reviewer 独立复测待办） | TBD |
| A1-02 | PARTIAL | 同上（并发/crash 负例由 A1 套件覆盖；Reviewer 独立复测待办） | TBD |
| A2-01 | NOT_RUN | 按 Reviewer/Lead 指示保持 NOT_RUN | TBD |
| A2-02 | NOT_RUN | 同上 | TBD |
| A2-03 | NOT_RUN | 同上 | TBD |
| A3-01 | PARTIAL | docs/A_NEXT_REGISTRY_DECISION.md（UNVERIFIED + 补偿控制；Reviewer batch-2 PASS cond，终态待办） | TBD |
| A3-02 | PARTIAL | 同上（攻击矩阵状态以 Reviewer 复核为准） | TBD |
| A4-01 | NOT_RUN | Reviewer 独立 OCI 复跑 NOT_RUN（Owner L2 host 级 PASS） | TBD |
| A4-02 | NOT_RUN | 同上 | TBD |
| A4-03 | NOT_RUN | 同上 | TBD |
| A5-01 | PARTIAL | packet v3 builder/verifier + mutation tests（37 passed）已合并；最终 Packet 未构建 | TBD |
| A5-02 | PARTIAL | Host 7 例外已逐项文档化；OCI 69 deselect 待 OCI run 登记/Reviewer 签收 | TBD |
| A6-01 | BLOCKED | HUMAN_REQUIRED；未部署/未签核 | TBD |
| A6-02 | BLOCKED | HUMAN_REQUIRED；G5 未授权 | TBD |
| X-01 | PARTIAL | 受保护文件 diff 仅 A1/A2 已审变更（见 report §1）；LeadB 侧 zero-touch 需联合确认 | TBD |
| X-02 | PARTIAL | 0 real key/network；strace 0；LiveGate BLOCKED；仍需 Reviewer 独立确认 | TBD |

### 9.2 旧 65 行

- 保持冻结 CSV 原值，`reviewer_final_status` 全部仍为 TBD；本文件不预填任何 PASS。
- 集成阶段产生的 Exception 归类（Host 7 项）与 OCI 待登记项见 `docs/A_NEXT_IMPLEMENTATION_REPORT.md` §2；Reviewer 逐项复跑后回填。

### 9.3 事件与已知既有项

- **INCIDENT_20261121**：v1 Packet 原始字节 LOST；恢复 provenance（backup tar `11172f02…`、rootfs `25491e45…`、deps `e07729d7…`）见 report §4；不得声明全程 NO_DRIFT/证据完整。
- **EXISTING history finding**：`fixtures/m1_teacher/judge/sentinels/sentinels.json` 合成 sentinel（LeadB 线，masked）；并非 A-NEXT 改动文件；Reviewer batch-3 已在 main@3e7afee / fd1d3a6 / A2 三处复现。
- **P2-A4-1**：evidence-index v2 路径键修正由 rrev6 addendum `0735d7b` 完成（evidence-index-v2 sha `bac7b550…`）。

> 本 §9 为 Owner-measured 追加；Reviewer 独立复核后才可回填终态，Agent 不得代签。
