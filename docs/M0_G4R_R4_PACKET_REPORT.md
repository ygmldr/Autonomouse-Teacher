# G4-R / PR-R4 — Packet v2 Builder & Verifier 报告（阶段一）

- 范围：G4-R §7 / §10 R4-01..R4-13 中的 builder/verifier、严格全树 inventory、mutation suite、
  证据一致性设计、P2-04 lint。
- 状态：**阶段一完成（builder/verifier + synthetic mutation suite 全绿）**；**最终 v2 Packet 的
  真实构建/全树校验/真实 mutation 证据为 `PENDING_FROZEN_IMPL_SHA`（阶段二，等 Lead 冻结 impl SHA）**。
- 工作树：`/root/Autonomous Teacher/worktrees/g4r-packet`；分支 `chore/g4r-packet-v2`。
- Parent/base：`3e7afee077845a071cd364e93ab209cac20b2d5f`（= main，clean）。
- 环境：Python 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`）、ruff 0.17.5。
- 0 真实 Key / 0 Provider / 0 外部 HTTP/TCP / 0 容器 / 0 网络 fetch；LiveGate 未修改。

## 1. 交付物

| 文件 | sha256（阶段一） | 说明 |
|---|---|---|
| `scripts/g4r/build_packet_g4r.py` | `d6dc98bc…2737fbb` | v2 builder：SQLite `Connection.backup()` 快照 → 全树严格 inventory → manifest/hashes/report → 自检 → 原子 rename |
| `scripts/g4r/verify_packet_g4r.py` | `9d103fb0…98f324` | 独立 verifier：不 import builder、不 import/打开 sqlite3；全树 lstat 遍历 + 明确 reason codes |
| `tests/g4r_packet/support.py` | `6fc8a0c0…a539646` | TEST_ONLY synthetic staging/SQLite/LiveGate fixture + subprocess 调用 |
| `tests/g4r_packet/test_packet_v2.py` | `d70541e3…cf57f39` | R4-01..R4-06 + 证据一致性 mutation suite（9 项） |
| `tests/security/test_scan_git_secrets.py` | （仅删 1 行） | R4-08 / P2-04：删除未使用 `material` 变量，测试强度不变 |
| `docs/M0_G4R_SOURCE_ERRATA_APPEND.md` | — | P2-02 / P2-07 append-only errata |

## 2. v2 Packet schema（`m0.g4r.packet.manifest/v2`）

目录（与执行计划 §10 建议一致，payload 内容由 staging 决定）：

```text
artifacts/review-packet-g4r-v2-<impl_sha>/
  manifest.json                  # 被 hashes.sha256 覆盖
  hashes.sha256                  # 覆盖 payload + manifest.json；排除自身与 integrity report
  packet-integrity-report.txt    # 未哈希 anchor：记录 manifest/hashes/tree/counts 摘要
  README.md, identity/{git,stage,runtime,livegate}.json, env/zero-key.json,
  source/, cases/…, regressions/…, matrix/, review/
```

关键字段：`identity`（impl/base/parent/code/docs/build/git head）、`stage`、`rootfs_sha256`、
`deps_sha256`、`runtime`、`environment`、`tests`（rows/status）、`inventory`（payload_count、
hash_manifest_entry_count、total_regular_files、payload_tree_sha256、file_modes、固定
metadata_exceptions、file_mode）、`live_gate`（status/snapshot_path/reason_count/reasons_sha256）、
`status`、`external_network_calls=0`、`real_model_calls=0`、`provider_keys_seen=0`、`limitations`。

不可循环哈希的设计：

- `payload_tree_sha256` 只覆盖 payload（canonical `[[relpath, sha256]]` 排序 JSON 的 SHA-256）；
- `hashes.sha256` 覆盖 payload **+ manifest.json**，**仅**排除 `hashes.sha256` 自身与
  `packet-integrity-report.txt`；两个例外是代码内固定常量，不是可增长白名单；
- manifest 内**不保存** hashes 文件摘要（避免循环）；integrity report 作为未哈希 anchor 记录
  `manifest_sha256` 与 `hashes_sha256`，verifier 会重新计算并逐项比对。

Builder 安全点：

1. 输出根已存在（含空目录）→ `PACKET_ROOT_EXISTS` 拒绝，绝不修改/删除既有 Packet；
2. staging 全树 lstat：隐藏文件 → `HIDDEN_PATH`、symlink → `SYMLINK_PATH`、非普通文件 →
   `NOT_REGULAR_FILE`、`st_nlink != 1` → `HARDLINK_ANOMALY`、未规范化/穿越路径 →
   `BAD_RELATIVE_PATH`；staging 不得预置 manifest/hashes/report/`identity/livegate.json`；
3. SQLite：`--sqlite dest.sqlite3=source.sqlite3`；先 `sqlite3.connect("file:…?mode=ro", uri=True)`
   再 `Connection.backup()` 到临时快照，**所有连接关闭后**才复制快照字节进 build tree（build
   tree/Packet 内从不 `sqlite3.connect`）；源为 symlink/sidecar 文件名直接拒绝；
4. 所有 payload/元文件固定 `0444`；manifest 记录 `file_modes`（payload+manifest），verifier 校验；
5. 构建最后在 build 目录上用 builder 自己的严格遍历重算 counts/tree/hashes coverage/report 摘要，
   全部一致才 `os.rename` 到最终根；失败则清理临时目录、不留下半成品 Packet。

Verifier reason codes（FAIL 时明确输出，含 path/detail）：

`UNLISTED_PATH`、`MISSING_PATH`、`HIDDEN_PATH`、`SYMLINK_PATH`、`NOT_REGULAR_FILE`、
`SQLITE_SIDECAR_PRESENT`、`HARDLINK_ANOMALY`、`PATH_NOT_NORMALIZED`、`HASH_MISMATCH`、
`MODE_MISMATCH`、`PAYLOAD_TREE_MISMATCH`、`COUNT_MISMATCH`、`HASHES_FILE_INVALID`、
`HASHES_ENTRY_EXTRA`、`MANIFEST_INVALID`、`IMPL_SHA_MISMATCH`、`INTEGRITY_REPORT_MISMATCH`、
`LIVEGATE_CROSSREF_MISMATCH`、`PACKET_ROOT_INVALID`、`TREE_UNREADABLE`。
Verifier 只读 bytes，不打开 SQLite，因此校验动作本身不会生成 sidecar。

## 3. 实测命令与结果（阶段一）

| 命令（worktree 内） | 结果 |
|---|---|
| `pytest tests/g4r_packet -q -p no:cacheprovider` | **9 passed**（1.70s） |
| `pytest tests/security -q -p no:cacheprovider` | **7 passed**（7.66s，P2-04 后） |
| `ruff check scripts/g4r/ tests/g4r_packet/ tests/security/test_scan_git_secrets.py` | **All checks passed** |
| 旧 v1 Packet `hashes.sha256` SHA-256（测试前后） | `421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d`（**前后一致，未改**） |

原始日志：`artifacts/g4r/r4/tests-and-ruff.log`（gitignored）。

## 4. Mutation suite → R4 case 映射（synthetic fixture，均在临时副本上注入）

| R4 case | 测试 | 实测结果 |
|---|---|---|
| R4-01 | `test_r4_01_pristine_packet_verifies_and_counts_are_consistent`；`test_r4_01_builder_refuses_existing_root_and_bad_staging` | 原包 `PASS`、0 issue、0 symlink、0 unlisted、0 mismatch；payload/hash entry/total counts 与独立遍历一致；payload tree 与独立重算一致；mode 0444；`PACKET_ROOT_EXISTS`/`SYMLINK_PATH`/`HIDDEN_PATH` 均拒绝且不破坏既有包 |
| R4-02 | `test_r4_02_unlisted_sidecar_hidden_and_unknown_files_fail` | 注入 `-wal`/`-shm` → `SQLITE_SIDECAR_PRESENT`；隐藏文件 → `HIDDEN_PATH`；未知 `cases/unknown.json` → `UNLISTED_PATH`；exit 1 |
| R4-03 | `test_r4_03_delete_change_byte_mode_symlink_hardlink_fail` | 删除 → `MISSING_PATH`；改字节 → `HASH_MISMATCH`；改 mode → `MODE_MISMATCH`；symlink → `SYMLINK_PATH`；硬链异常 → `HARDLINK_ANOMALY`；全部 exit 1 |
| R4-04 | `test_r4_04_manifest_and_hashes_tamper_fail` | 改 manifest 字段 / 改 hashes 行 / 删 hashes 行 / 伪造 hashes 行 / 把元文件加入 hashes → 全部 exit 1（`HASH_MISMATCH`/`COUNT_MISMATCH`/`MISSING_PATH`/`HASHES_ENTRY_EXTRA`） |
| R4-05 | `test_r4_05_sqlite_snapshot_consistent_and_read_sidecars_detected` | WAL 源库 + 未提交事务下构建：快照只含已提交行、Packet 内无 `-wal/-shm`、readonly immutable URI 可读；对副本做普通 WAL 读取产生 sidecar 后 verifier exit 1（`SQLITE_SIDECAR_PRESENT`/`UNLISTED_PATH`）；verifier 对原包前后文件集合不变（自身不产生 sidecar） |
| R4-06 | `test_r4_06_independent_traversal_and_source_guards` | 测试内独立 lstat 遍历器（不 import verifier）复算 set/hash/tree/modes 与 manifest 一致；sidecar 源被 `SQLITE_SOURCE_INVALID` 拒绝 |
| R4-13（设计验证） | `test_livegate_snapshot_crossref_mismatch_fails` | 篡改 `snapshot_ref` 或 snapshot reasons → `LIVEGATE_CROSSREF_MISMATCH`；snapshot 用 3 条原因（非 4）证明未硬编码 |
| 不变性 | `test_v1_packet_is_untouched_by_v2_build` | v1 Packet `hashes.sha256` 前后 SHA-256 相同 |

## 5. R4 case 状态（Owner 侧，阶段一）

| case | 状态 | 说明 |
|---|---|---|
| R4-01 | **PARTIAL** | builder/verifier + synthetic 全树校验 PASS；**最终 v2 包尚未构建**（等冻结 impl SHA） |
| R4-02 | **PARTIAL** | sidecar/隐藏/未知文件拒绝已实现并测试；最终包上的 mutation 待阶段二 |
| R4-03 | **PARTIAL** | 删除/字节/mode/symlink/硬链拒绝已实现并测试；最终包待阶段二 |
| R4-04 | **PARTIAL** | manifest/hashes 篡改拒绝已实现并测试；最终包待阶段二 |
| R4-05 | **PARTIAL** | `Connection.backup()` 一致性快照 + 无 sidecar 已测试；真实证据 DB 快照待阶段二 |
| R4-06 | **PARTIAL** | 独立遍历器复算 PASS（synthetic）；Reviewer 独立机器复算待独立 Review |
| R4-07 | **NOT_RUN** | 合并后 A12 稳定性（需 R1 代码冻结，Lead/Integration 负责） |
| R4-08 | **PASS** | F841 已删除；变更范围 ruff 0 finding |
| R4-09 | **NOT_RUN** | Host full 逐 nodeid 归类（Lead/Integration） |
| R4-10 | **NOT_RUN** | OCI/Node 计数对比（Lead/Integration） |
| R4-11 | **NOT_RUN** | LiveGate 四入口负例（本轮只读 `gates.py`，未改；由 R0/Integration 复跑） |
| R4-12 | **PARTIAL** | `docs/M0_G4R_SOURCE_ERRATA_APPEND.md` 已交付；新矩阵路径存在性在最终证据采集后校验 |
| R4-13 | **PARTIAL** | crossref schema + verifier 设计/测试完成；最终 Packet 三处交叉引用待阶段二构建产物验证 |

## 6. 阶段二待办（等 Lead “G4-R impl SHA 已冻结”）

1. 在 Lead 指定的集成分支/代码树（含 R1/R2/R3 冻结代码）上采集真实证据 payload（identity/
   source/cases/regressions/matrix/review）与各 SQLite 工作副本；
2. 用冻结 impl SHA 运行 `build_packet_g4r.py` 生成 `artifacts/review-packet-g4r-v2-<impl_sha>/`；
3. 运行 `verify_packet_g4r.py --expected-impl-sha`（全树 0 issue）并在**验证副本**上跑
   sidecar/隐藏/未知/删除/字节/mode/symlink/硬链/manifest/hashes 注入 mutation，记录每条
   `code`/path/UTC/exit 到 `artifacts/g4r/r4/`；
4. 由独立 Reviewer 用自建遍历器复算 packet hash/tree/SHA，不采信本 verifier 结论；
5. 将真实 manifest/hashes/tree/counts/`PENDING_INDEPENDENT_REVIEW` 状态写入本报告 append 章节
   （append-only，不改写本阶段文字）。

## 7. 未验证 / 限制

- 最终 v2 Packet 尚未生成：packet root、manifest sha256、hashes sha256、payload tree、真实 payload
  计数均 **NOT_RUN**（不得以 synthetic fixture 数字代替）。
- `gates.py`/LiveGate 未修改也未被本轮重新负测（R0/E5 证据沿用既有，R4-11 仍 NOT_RUN）；
  本报告不宣称任何 Live 授权。
- 独立 Reviewer 的独立机器/独立遍历器复算未发生；本报告 PASS 仅指 Owner 侧 synthetic 测试。
- 旧 v1 Packet 与旧 Reviewer 报告/矩阵未修改；本阶段不归档任何 Reviewer 结论，不改变
  `G4-H/G5/G6/LiveGate/M0/E5_PRELIVE_FULL` 状态常量。

---

## 8. 阶段二（append-only）— 最终 Packet v2 真实构建与独立全树校验（冻结 impl `d33e0aa`）

> 本节为阶段一之后的 append-only 记录，不改写上文阶段一文字。所有数字为本机 Owner 侧实测；
> Independent Review 仍为 `PENDING_INDEPENDENT_REVIEW`。

### 8.1 冻结输入

| 项 | 值 |
|---|---|
| frozen impl commit（packet impl id） | `d33e0aabd1714a486325b745c436cb59855d6539` |
| impl content sha256（canonical src tar） | `5551078a284a40da9b6049c4f7bc5d3abfacfa8f364bc4949b44999257922e45` |
| base commit | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| docs commit（docs-only child of impl） | `bc08bdd3f6cceb73462c33acd98bda276d0b1fbf`（parent=`d33e0aa`；仅 docs/ 变化：joint regression report / review request / final matrix 等；无 code 变化） |
| 终稿矩阵 | `docs/Autonomous_Teacher_M0_G4R_Test_Evidence_Matrix_v1.0.csv`，sha256 `741d7d5598cb9357c9ec9126ebcc277d504af93c0bc591af0d0c395b303d1382`，65 case 行 |
| new Stage | `stage-20261120T165407Z`，base/head_at_build=`d33e0aa`，manifest `cc7ccb61bc4df76675b14e1f73bdd9209d3a13eeda7e79193e913ea284874d03`，stage tree `933f2c07a6c79415183a4d3f1db1ba19249b95d96ee88334bd43e71dd40d3882`，trusted `f10053d4107170b0b53362dbc9d1c0120d07dd7ee35339a315749de4b3431add`，candidate `131ab68e10f25d4aa893348754100c0fb0e221059b3fa79e3f7be9547c219006`，loaded src 52/52 == git d33e0aa blobs |
| environment（exclusive window 17:05:50–17:08:20Z，T0/T1 一致） | rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（清理后）、deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`、DSH runtime `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4`（0.2.2-rc.2, 182,717,632B）、adapter built JS `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |

环境漂移与清理记录（**不写“全程 NO_DRIFT”**）：`16:43:53 25491e45 → 16:52–16:53 0340fb78
（并发 OCI/full-suite 活动）→ 16:53:34 恢复 25491e45 → 16:54:07 Stage build（canonical）→
16:55–16:59 a6737150/e1a8fcf9（OCI 直接 `--rootfs` 造成空挂载点 + probe/ 污染）→ 17:01:49
清理并复算恢复 25491e45`。漂移窗口内 Stage build 被 fail-closed 拒绝（`rootfs is not canonical
before build`，行为正确）；16:55Z OCI 结果作废（污染 rootfs + 2 个 f2 collection errors）。
L2 证据在独占窗口串行采集（T0/T1 rootfs 相等、`podman ps -a` 前后为空）。
以上均为已记录的瞬时漂移与恢复，**不得外推为生产/持续 NO_DRIFT**。

### 8.2 Packet 构建与全树校验（Owner 实测）

- Packet 根：`/root/Autonomous Teacher/worktrees/g4r-packet-final/artifacts/review-packet-g4r-v2-d33e0aabd1714a486325b745c436cb59855d6539`
  （gitignored；旧 v1 Packet 与旧 Reviewer 报告未复制进 Packet，仅以 SHA 引用）
- frozen UTC：`2026-11-20T17:22:37Z`；构建命令：`scripts/g4r/build_packet_g4r.py --impl-sha d33e0aa… --impl-content-sha256 5551078a… --staging … --metadata … --livegate-snapshot …`（exit 0，`BUILT_AND_SELF_CHECKED`）
- counts：`payload_count=40`、`hash_manifest_entry_count=41`、`total_regular_files=43`；`file_mode=0444`；metadata 例外固定为 `hashes.sha256,manifest.json,packet-integrity-report.txt`
- `payload_tree_sha256`=`4300a7c67a031136cd52f46b44d325db7a5dd14df82f409d25d6a2247737c1f6`
- `manifest_sha256`=`fe45d7602bd7a115cfdc3dd3a85e889c0f7b4fa642c03a54717c06f0bcf403a9`
- `hashes_sha256`=`e7a67c77b8e213fac32cb4aabeae56075dcf4982c0281479fae25cca1c4bdddb`
- manifest identity：`impl_sha=impl_git_commit=d33e0aa…`、`impl_content_sha256=5551078a…`、`code_sha=5551078a…`、`docs_sha`（canonical docs tar digest）、`git_head_at_build=d33e0aa…`；`live_gate=BLOCKED`（single snapshot，`reason_count=1`，由 verifier 重算 `reasons_sha256`，不硬编码）
- 全树 verify：`scripts/g4r/verify_packet_g4r.py --packet-root <root> --expected-impl-sha d33e0aa…`
  → **exit 0，`PASS`，0 issues，0 symlink，0 unlisted，0 mismatch，counts 一致**；verifier 不 import/打开 sqlite3。
- v1 Packet 前后不变：**177 files / 0 symlink / `sha256sum -c hashes.sha256` 173/173 OK exit 0 /
  `hashes.sha256`=`421b07ae3ad0eac2d36c032cd384d252dfda4ac521e193577aed56fc60ca9d3d`**（未写入/未重打包）。

### 8.3 验证副本 mutation suite（原 Packet 未被修改）

在 `/tmp` 验证副本上逐项注入，**12/12 全部按预期 FAIL**（原 Packet 保持 PASS）：

| mutation | 预期/实测 reason code |
|---|---|
| 新增 `*.sqlite3-wal`/`-shm` | `SQLITE_SIDECAR_PRESENT`（+`UNLISTED_PATH`） |
| 隐藏文件 | `HIDDEN_PATH` |
| 未知文件 | `UNLISTED_PATH` |
| 删除 payload | `MISSING_PATH` |
| 改字节 | `HASH_MISMATCH` |
| 改 mode | `MODE_MISMATCH` |
| symlink 替换 | `SYMLINK_PATH` |
| 硬链异常（st_nlink>1） | `HARDLINK_ANOMALY` |
| 改 manifest | `HASH_MISMATCH` / `COUNT_MISMATCH` / `INTEGRITY_REPORT_MISMATCH` |
| 改 hashes 行 | `HASH_MISMATCH` |
| 改 LiveGate snapshot reasons | `LIVEGATE_CROSSREF_MISMATCH`（+`HASH_MISMATCH`） |
| 改 manifest impl identity | `HASH_MISMATCH` / `MANIFEST_INVALID` |

原始日志：`artifacts/g4r/r4/final-build-and-verify.log`、`artifacts/g4r/r4/final-mutation.log`、
`artifacts/g4r/r4/{final-build-result,final-verify-result,metadata,livegate-snapshot}.json`、
`artifacts/g4r/r4/{manifest.json,hashes.sha256,packet-integrity-report.txt}`（gitignored）。

### 8.4 引用的 Integration 联合回归（独立证据根 `artifacts/g4r/`）

- Host 单进程 1420 collected / 1412 passed / 5 failed / 3 skipped（0 collection error）；5 项
  逐 nodeid 分类 0 REAL_REGRESSION（ENVIRONMENT_ONLY / FLAKY_ORDER_DEPENDENT）。
- OCI filtered（清理后、rootfs copy、`--network none --read-only --user 65534:65534`）：
  total 1081 / passed 1052 / failed 1 / skipped 28 / deselected 69；唯一 fail 为 runtime
  target-profile ENV；R1 auth 26 tests 因 OCI uid Owner 语义显式 deselect（L1-HOST 26/26 PASS）。
- Node TAP 36/36；Scanner self-test PASS + 0 findings（503 files/1070 blobs/208 commits）；
  LiveGate BLOCKED / require_live SECURITY_BLOCKED / run_live exit3 / CLI --live exit3 /
  Adapter 4/4 SECURITY_BLOCKED / strace 0 network lines；L2 exclusive：F2 ok、F5 3/3 true、
  containers_after=[]、0 real model/HTTP/key。
- 计数与失败分类原始文件：`regressions/{host,oci,node,ruff,scanner,livegate}/counts.json`、
  `regressions/index.json`（含 `exclusive_window_oci_rootfs_copy` 与 official OCI counts 的区分）。

### 8.5 未验证 / 限制（阶段二更新）

- Independent Reviewer 的独立遍历器复算、真实原始包审计与 Verdict：**未发生**，状态
  `PENDING_INDEPENDENT_REVIEW`。
- `B03`/`E5-P04` 仍 **UNVERIFIED**；本 Packet 不宣称 E5-PreLive Full / G4-H / G5 / G6 / Live /
  生产安全；0 真实 Key/Provider/外部 HTTP。
- 环境身份来自一次性独占窗口与清理后复算，存在已记录的瞬时漂移历史；不得外推为生产或
  持续 NO_DRIFT。
- 旧 v1 Packet、旧 Reviewer 报告、旧 46 行矩阵均未修改；状态常量不变
  （`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`LiveGate=BLOCKED`、
  `M0=DECISION_PENDING`、`E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`）。
