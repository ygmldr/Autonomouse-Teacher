# A-NEXT 集成报告（work/a-next，无 Key）

- **文档 ID**：`A-NEXT-IMPLEMENTATION-REPORT-v1`
- **Integrator**：a-impl-core（Integrator；非 Owner 实现者、非 Reviewer）
- **目标分支/工作树**：`work/a-next` / `/root/Autonomous Teacher/worktrees/a-next`
- **base**：`fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`；**最终集成 HEAD（含 #8.2 rrev6 addendum V2）**：`4d7c2821e7907be7fa846855e7df25e3616c9fa1`；Host 回归运行 HEAD：`1dfb24cd33da5a25129cf132365e7f297a7d617e`（其后为 docs-only addendum 与 #8.2 scripts/tests/docs 修正，见 §6）
- **内容**：A1/A2/A0/hygiene/A6/registry/packet-v3/rrev6 按 Lead green 清单合并；联合回归（Host/Node/ruff/scanner/LiveGate/SQLite）；OCI filtered 未运行（等 Lead 批准）。

## 0. 摘要

- 8 个分支 + 1 个 docs addendum 按序 merge，**0 文本冲突**，未改写 Owner 提交，未修改冻结 v1/v2 Packet 字节。
- Host 全量：**1626 collected / 1601 passed / 7 failed / 18 skipped / 688.5s / 0 collection error**；7 个失败逐 nodeid 归类为 **ENVIRONMENT_ONLY / EXISTING（0 REAL_REGRESSION）**。
- Node TAP **36/36**（container + `cp -a` rootfs 副本；冻结 rootfs 不变）。
- Ruff 变更范围 **All checks passed**；Scanner self-test PASS、工作树 0 findings、positive control PASS、history 2 findings 属 **EXISTING（LeadB m1_teacher 合成 sentinel 历史 blob）**。
- LiveGate/四入口/strace 全拒绝且 0 网络；SQLite 只读/immutable 抽查通过。
- **OCI filtered = NOT_RUN**（遵守 Reviewer 20:45–21:10Z 独占窗口；待 Lead 批准后按 43 legacy + 26 explicit g4r_auth deselect 登记执行）。

## 1. 合并记录（merge 时 `git rev-parse` 实核）

| # | 分支 | green SHA | 实核 SHA | merge commit | 文件数 |
|---|---|---|---|---|---|
| 1 | fix/a-next-auth-record | e6f3aa6 | e6f3aa6cdaacec8d2e219fe44fd8640b5e036567 | b7c1261 | 4 |
| 2 | feat/a-next-run-admission | c7eb74e | c7eb74e1c2192d3b3732e780e019456d4a47aa3f | 82b8aef | 17 |
| 3 | docs/a-next-baseline | bf312c8 | bf312c8eecf87facc6592d955baf50e9d933c23d | 6fcb87a | 7 |
| 4 | chore/a-next-oci-hygiene | 7d7c0a5（原 16a4187） | 7d7c0a52abd2a14775795115b8b375c6796bdebb | d505f43 | 10 |
| 5 | docs/a-next-handoff | 13e39a4 | 13e39a4c18df1bfa6e8c226bcba1b13966af6347 | 26ee69f | 4 |
| 6 | feat/a-next-registry | 748fd0a | 748fd0a529270a11b42ca4be23c096fb1b6f9e14 | bedd5c5 | 6 |
| 7 | chore/a-next-packet | ce914c1（原 b4b88a5） | ce914c1005cf67d24c2836cd3487ca68e331d21e | 19a8650 | 8 |
| 8 | test/a-next-rrev6 | 95a020b | 95a020b27ccf05ae3cd504d8c138bc279706fee2 | 1dfb24c | 8 |
| 8.1 | test/a-next-rrev6 addendum | 0735d7b | 0735d7b8f11770586dda5acf2caf756d81cffd1b | d553bba | 1 |

**SHA 替换说明（经 Lead 批准）**：hygiene 16a4187→7d7c0a5、packet b4b88a5→ce914c1，均**仅 test-helper 模块重命名**（两个新套件均 `from conftest import ...`，合并后全量 pytest 收集会相互遮蔽 → ImportError）；各套件仍 38/37 全绿、ruff 干净，变化范围仅 `tests/a_next_hygiene/*` 与 `tests/a_next_packet/*`（+新增 helper 文件）。

- `git diff --name-only fd1d3a6d101f17e6a86d7c43f06c630326e3e3af..HEAD` = **65 files**（+16423 / −22）；全量清单与来源 PR 标注见 `artifacts/a_next/integration/provenance.txt`。
- 受保护文件核对：仅 `src/autoteacher_m0/security/authorization.py`（A1，+69/−18）、`src/autoteacher_m0/bridge/controller.py`（A2，+82/−4）、新增 `src/autoteacher_m0/bridge/run_admission.py`（A2 新入口）；**gates/live_controller/cli/dsh_adapter/run_live.sh/config 零改动**，无未审受保护变更。

## 2. 联合回归（Host，无 OCI）

环境快照（host 开始/结束）：rootfs `25491e45…`、deps `e07729d7…` 前后一致；`config/dsh/*.yml|json`、`scripts/verify_runtime_profile.py` 的临时 `chmod 0444` 仅用于环境类复现，运行后恢复 0644（`git status` clean）。

### 2.1 Host full

`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps python -B -m pytest tests -q -p no:cacheprovider --junitxml=artifacts/a_next/integration/host-full-junit.xml`

**1626 collected / 1601 passed / 7 failed / 18 skipped / 688.5s；0 collection error**（`--collect-only` 1626，0 error）。

| nodeid | 分类 | 基线/环境等价说明 |
|---|---|---|
| g3d/test_d3_contract.py::test_runner_does_not_modify_product_src | ENVIRONMENT_ONLY | stale-baseline 断言 src==4bd4803；G4-R 已知同类 host-env |
| g4_b/test_manifest_contract.py::test_build_is_deterministic_and_excludes_provenance | ENVIRONMENT_ONLY | `stage manifest unreadable`：本 worktree 缺 gitignored `artifacts/g3d/stage-20261117T221955Z`（STAGE_DEFAULT）；跨 worktree 均不可得，非产品回归 |
| g4_b/...::test_rows_are_sorted_and_record_mode_and_size | ENVIRONMENT_ONLY | 同上 |
| g4_b/...::test_manifest_does_not_reference_itself | ENVIRONMENT_ONLY | 同上 |
| g4_d/test_d10_d15_e5_subset.py::test_d15_same_uid_known_path_is_denied_by_mode_not_name | ENVIRONMENT_ONLY | PermissionError `/root/.../.venv/bin/python`；G4-R host-env 同类（delta-pre 亦失败） |
| runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text | ENVIRONMENT_ONLY | checkout 模式 0644；对 4 个期望只读文件 `chmod 0444` 后 **4 passed**（`artifacts/a_next/integration/target-profile-env-demo.log`） |
| security/test_scan_git_secrets.py::test_repository_worktree_and_history_is_clean | EXISTING/ENVIRONMENT | scanner `rev-list --objects --all` 扫到共享 repo 中 **LeadB `fixtures/m1_teacher/judge/sentinels/sentinels.json`** 合成 sentinel 历史 blob（be92c3f/c993519d；masked，line 101/112）；非 A-NEXT 改动文件、非 A2 回归；工作树扫描 0 findings、positive control PASS。与 Reviewer batch-3「三处复现」一致 |

**REAL_REGRESSION = 0。**

### 2.2 其它

| 项 | 结果 | 证据 |
|---|---|---|
| Node TAP（fixed rootfs 副本） | adapter **9/9** + guard **19/19** + skill **8/8** = **36/36**；frozen rootfs 前后 `25491e45…`，副本删除，podman 空 | `artifacts/a_next/integration/node/` |
| Ruff 变更范围（43 py） | **All checks passed** | `artifacts/a_next/integration/ruff-changed.log` |
| Ruff repo-wide | 38 errors，全部 pre-existing（`spikes/g3b-trusted-bridge/*`、旧 `scripts/g3b|g3c|g4/*`），无变更文件错误 | `ruff-repo.log` |
| Secret scanner | self-test PASS；`--no-history` 0 findings；history 2（EXISTING，见上）；positive control 检出伪造 `sk-`（exit1，masked） | `scanner-*.log` |
| LiveGate / 四入口 | inspect **BLOCKED**（首 reason `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`）；require_live **SECURITY_BLOCKED**；run_live.sh **exit 3**；CLI smoke --live **exit 3**（4 reasons）；Adapter 四入口 **4/4 SECURITY_BLOCKED**；strace run_live/CLI **0** 网络行 | `livegate.json`、`adapter-livegate.json` |
| SQLite 只读/immutable | rrev6 L2 evidence 4 DB：`mode=ro&immutable=1` 打开、integrity ok、写被拒（`attempt to write a readonly data`）、副本与原件 sha256 不变 | `sqlite-probe.json` |
| OCI filtered（**有效 run 2026-11-20T21:10:04Z**，窗口延长至 21:45Z，单写者） | **tests 1287 / failures 97 / errors 54 / skipped 31 / deselected 69 cases（44 deselect 条目：43 legacy + 26 tests/integration/g4r_auth 目录）/ exit 1 / 112.4s**；151 个 failure+error 全部 **ENVIRONMENT_ONLY**：64 因 OCI rootfs 无 host 工具 `tar`/`git`（A-NEXT 新增测试为主机工具假设）、61 因 uid 65534 授权目录 owner 校验（`EXTERNAL_AUTHORIZATION_INVALID`）、26 为其断言衍生的 env（uid/tool/mode）；**未发现产品代码失败**；但 A-NEXT 新增测试套件**不具备 OCI 可移植性** → A-NEXT 的真实 OCI 覆盖 = **NOT_VERIFIED**（host 覆盖见 §2） | `artifacts/a_next/integration/oci2/junit-oci-filtered.xml`、`oci-meta-20261120T211004Z.json`、`oci-stdout-20261120T211004Z.log` |

## 3. Reviewer batch-3 结论登记（引用，不改判）

- **A2 c7eb74e = PASS（条件）**：Reviewer 独立 73 passed；pre-existing security history finding 三处复现（main@3e7afee、fd1d3a6、A2）→ 矩阵/handoff 记 **EXISTING/ENVIRONMENT**。
- **P3（A2 非阻断）**：被拒 payload 也消耗 ordinal（fail-closed；`effective_max_calls` 计 dispatch 尝试）；`_map_consume_reasons` 子串匹配较脆（非阻断）。
- **A4/R-REV6 = PARTIAL**：Owner L2 host 级 PASS；Reviewer 独立 OCI 复跑 **NOT_RUN** → A4-01..03 保持 **NOT_RUN**；`A2-01..03` 也保持 **NOT_RUN**。
- **P2-A4-1**：evidence-index 路径键修正由 rrev6 addendum `0735d7b` 完成；`evidence-index-v2.json` sha256 `bac7b550b653079fc382fb702be2374526af10d6c99c976935732b80747f2832`，已随 #8 合并。

## 4. INCIDENT_20261121 环境事件披露（强制）

- 2026-11-20T19:53Z 前后 repo `artifacts/`（含冻结 rootfs 副本、deps、G4-R 证据）被误删，随后从哈希验证副本恢复：backup tar sha256 `11172f02…`；恢复后 rootfs `25491e45…`、deps `e07729d7…`（与冻结声明一致）。
- **v1 Packet 原始字节 LOST**（原路径 `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99`），不可再独立核验；v2 Packet 仅 HISTORICAL_REFERENCE，未修改字节。
- 本集成在该恢复后的环境运行；**不得**声明“全程 NO_DRIFT”或“证据完整/无缺失”。最终 Packet v3 必须内嵌本披露与恢复 provenance。

## 5. 未验证 / 待办 / 限制

- **OCI filtered 联合回归已完成**（有效 run 21:10:04Z；151 failure/error 全 ENVIRONMENT_ONLY，无产品代码失败；A-NEXT 测试 OCI 可移植性 NOT_VERIFIED；详见 §6）。
- **A4-01..03、A2-01..03 = NOT_RUN**；`B03/E5-P04 = UNVERIFIED`（registry decision 为 UNVERIFIED + 补偿控制）。
- **Packet v3 最终包未构建**：等集成冻结 SHA + staging payload 清单；builder/verifier 已就绪（`scripts/a_next/build_packet_v3.py`、`scripts/a_next/verify_packet_v3.py`，37 tests）。
- Host 7 failures 为环境/既有类（已逐项演示/解释）；OCI deselect/失败待 OCI run 登记。
- A6 人类决策 D-14..D-22、G4-H-01..06、G5 仍 **UNSIGNED / NOT AUTHORIZED**；状态常量不变。
- 证据根（gitignored）：`artifacts/a_next/integration/`（host-full.log/junit、node/、scanner-*.log、livegate.json、adapter-livegate.json、sqlite-probe.json、provenance.txt、protected-diff.txt、summary.json、merge-log*.log、target-profile-env-demo.log）。


## 6. OCI filtered 联合回归（有效 run 与失效尝试如实披露）

### 6.1 有效 run（21:10:04Z，窗口延长至 21:45Z，单写者）

- **命令**：直接构造 argv（非模板替换）：podman run — `--network none --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534`；mount `oci-stage(integration HEAD c687738 真副本):/project:ro`、`foundation/deps:/deps:ro`、`oci2:/evidence:rw`；`--rootfs /tmp/a-next-integration-rootfs-copy-<T>`（新 `cp -a` 工作副本，起跑前 hash=`25491e45…`，跑后删除）；`/opt/python/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider --tb=no --ignore=tests/integration/g4_a --ignore=tests/unit/security/test_authorization.py --junitxml=/evidence/junit-oci-filtered.xml` + 43 legacy deselects + `--deselect=tests/integration/g4r_auth`（目录级，26 tests）。
- **计数**：**tests 1287 / failures 97 / errors 54 / skipped 31 / deselected 69 cases（44 deselect 条目）/ exit 1 / 112.4s**（evidence `artifacts/a_next/integration/oci2/junit-oci-filtered.xml`）。
- **deselect 固定**：legacy 43（G4-R 冻结清单，逐条保留）+ explicit `tests/integration/g4r_auth`（26 tests，uid-owner 环境类，需 host 覆盖说明）；**未静默新增其它 deselect**。
- **失败分类**：151 = 64 ENVIRONMENT_ONLY（OCI rootfs 无 host `tar`/`git`，A-NEXT 新增测试以主机工具为前提）+ 61 ENVIRONMENT_ONLY（uid 65534 与授权目录 owner 校验 `EXTERNAL_AUTHORIZATION_INVALID`，与既有 g4r_auth 同类）+ 26 ENVIRONMENT_ONLY（上述 env 的断言衍生：uid/tool/mode）；**0 产品代码失败**。但 A-NEXT 新增测试套件在 OCI 中不可移植 → **A-NEXT 真实 OCI 覆盖 NOT_VERIFIED**。
- **Stage 身份**：`artifacts/g4/c/stages/stage-20261120T210101Z`，base/head=`c687738`，manifest `b3fd4cbcb9383b0434fc4f426b4c8976c217fe6d9c18939314c7a67219b61e62`，trusted tree `5c9b3958ab30447e54f5f39572f210e95e7aa56f7db573117a58f3bf35836c02`（集成树重新构建；非旧 Stage）。
- **环境**：frozen rootfs T0/T1 = `25491e45…`、deps T0/T1 = `e07729d7…`（未漂移）；rootfs 副本已删除；`podman ps -a` 收尾空。

### 6.2 失效尝试与 P2-ENV-1（必须披露，证据不计入）

- **P2-ENV-1（Lead 20:57Z 检测）**：`worktrees/a-next/artifacts/security` 曾是 symlink → `/root/Autonomous Teacher/artifacts/security`；早期 Stage build 命令经该 symlink 使 `podman --rootfs` resolve 到**冻结 rootfs**。冻结 hash 未变（`25491e45…`），但违反 A5/HANDOFF 规则。**纠正**：删除 symlink（不删目标），将 `artifacts/security` 与 `artifacts/foundation` 替换为真实可写副本（canonical 校验仍 `25491e45…`/`e07729d7…`）；Stage 在真实副本上重建（§6.1）；`g3a-provider-bridge`/`g3c` 仅指向 rrev6 构建产物的只读 symlink（非 rootfs），已记录。
- **INVALID_ATTEMPT_OLD_G4R_STAGE**：20:56:45/21:00/21:03 的旧脚本模板替换仍挂 g4r-phase2 旧 oci-stage/evidence → 其 1052/28/69 计数**不能作为集成 tree 证据**（证据文件保留但标 INVALID）。
- **INVALID_ATTEMPT_FROZEN_ROOTFS_SYMLINK**：21:01 尝试经上述 symlink 使用冻结 rootfs → 证据不计；对应无效 Stage 目录已删除。
- 本轮未写“全程只用副本/无事件”；上述尝试与纠正均留在证据与报告。

### 6.3 限制

- OCI 有效 run 的执行树为 `c687738`；其后 #8.2（fc935bd，仅 scripts/tests/docs）合并到 `4d7c282`，**OCI 未在最终 HEAD 复跑**（窗口/时间）→ 最终 HEAD 的 OCI = NOT_RUN（限制记录）。
- A-NEXT 测试 OCI 可移植性未解决（需后续把 host 工具假设改为纯 Python 或容器内工具；不得静默扩大 deselect）。

- **最终 docs-only commit**：`5766c33cc9516245025395a8e432e232af27e797`（本文件所在提交；其父 `4d7c282` 为代码+合并 HEAD）。Host 全量在 `1dfb24c`（1626 tests）上运行；最终树 `--collect-only` = 1644（#8.2 新增 18 个 rrev6 runner fail-closed tests），`tests/a_next_rrev6` 28 passed；**最终 HEAD 的 Host 全量 NOT_RUN**（仅 docs/scripts/tests 增量，已记录为限制）。

> 本报告不是 PASS、不是授权；最终裁定由 Independent Reviewer 从冻结 SHA 独立复现后给出。**未 push。**
