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
