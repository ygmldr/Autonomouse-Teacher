# A-NEXT A-PR1 / A1 — Use Record Body `authorization_id` Integrity (P2-01)

**Owner**：Implementer-Security `a-g4r-auth`（非独立 Reviewer；独立复算由 Reviewer-Independent 负责）
**日期（UTC）**：2026-11-20
**基线**：`work/g4r` = `fd1d3a6d101f17e6a86d7c43f06c630326e3e3af`（`main` = `3e7afee` + G4-R 合并）
**工作树 / 分支**：`/root/Autonomous Teacher/worktrees/a-next-auth-record` / `fix/a-next-auth-record`
**范围**：仅 P2-01 use-record body 完整性；A2（Run Admission 接线）不在本 PR。
**约束**：0 Key、0 Provider、0 外部 HTTP/TCP、LiveGate 恒 BLOCKED；不改冻结 Packet/Review 字节、不改 `m1_*`、不 push。

> 本文件分两次提交：**Commit 1（设计+测试骨架）** = 本文 §1–§5 与
> `tests/integration/a_next_auth/` 的可用测试（未实现部分用 `xfail(strict=True)` 标注，
> 便于 Reviewer 早审契约）；**Commit 2（实现）** = `authorization.py` 修改 + 取消 xfail +
> §6 实测结果。行号均指基线 `fd1d3a6` 的 `src/autoteacher_m0/security/authorization.py`。

## 1. 问题（G4-R 独立 Review P2-01）

`docs/REVIEW_G4R_INDEPENDENT.md` §11 P2-01：`_read_use_record` 只校验
schema/字段集合/`run_epoch`，不校验 body 的 `authorization_id`。Reviewer 探针实测
“schema 合法但属于其它授权 id 的记录”被判为 `AUTHORIZATION_REPLAYED`：
准入是保守的（无第二成功），但**审计上错配记录与真实 replay 不可区分**，且
“记录属于哪个授权”这一数据完整性约束完全未校验。要求：body id 与路径/预期不符 →
稳定 `AUTHORIZATION_USE_RECORD_INVALID`，不得误报 replay；不得放宽为只查 `run_epoch`。

## 2. 现状（基线行号）

| 位置 | 现状 |
|---|---|
| `_read_use_record(path) -> str`（L802–L847） | O_NOFOLLOW/fstat 类型/大小/nlink/权限校验后解析 JSON；校验字段集合、`schema`、`run_epoch` 格式，**忽略** `authorization_id` 的值/类型；返回 epoch 字符串 |
| `_read_use_record_settled(path) -> str`（L850–L870） | 对纯 `USE_RECORD_INVALID` 做 5×10ms 重试（容忍旧半写 publisher），持久非法仍 INVALID |
| `_replay_reason(previous_epoch, run_epoch)`（L872–L874） | 仅按 epoch 分类 |
| `consume_execution_authorization()`（L988+） | L1034 由已验证签名的 `authorization.authorization_id` 推导 `record_path = sha256(id)+".json"`；L1038–L1041 快路径与 L1082–L1089 `link` EEXIST 分支调用 `_read_use_record_settled(record_path)` 后分类 |
| `authorization_id` 的写入侧校验（L521–L525） | 签名文档加载时 `isinstance(str) and _IDENTIFIER.fullmatch(...)`，否则 `AUTHORIZATION_ID_INVALID` |

**结论**：写入侧 id 只允许 `_IDENTIFIER`（`[A-Za-z0-9._:-]{1,128}`，即现有 G4-A
合成 id 如 `auth-g4a-synthetic-1` 合法，不是 32-hex）；读取侧却完全不校验，形成不对称。

## 3. 设计决策

### 3.1 校验规则（新增于 `_read_use_record`）

1. `authorization_id` 必须是 `str` 且 `_IDENTIFIER.fullmatch`（与 L521–L525 写入侧完全一致；
   不接受 32-hex 之外/之内的额外放宽，也不改用 32-hex——现有 schema 是标识符）。
2. **路径绑定**：`path.name == sha256(authorization_id.encode("ascii")).hexdigest() + ".json"`。
   这直接覆盖“body id A 写入 B 的 record file”与 Reviewer 探针变体。
3. **预期绑定**：增加关键字参数 `expected_authorization_id`，读取器要求
   `authorization_id == expected_authorization_id`。调用方（`consume_execution_authorization`）
   用**已验证签名文档**的 `authorization.authorization_id` 传入——这是唯一权威来源，
   不需要新增公开签名参数，也不从 `run_epoch`/bindings 推导（无法判定，且任务明确禁止放宽为只查 epoch）。
   由于 `record_path` 本身由同一 expected id 推导，规则 2 与 3 在 `consume` 内互为冗余；
   规则 3 是面向未来调用方的防御性约束，并可直接单测。
4. `consumed_utc` 校验为 `str` 且匹配 `_UTC_TEXT`（写入侧固定 `%Y-%m-%dT%H:%M:%SZ`；
   避免“schema 合法的任意字符串”混入审计记录）。字段集合仍精确等于 4 键
   （多 key/缺 key → INVALID；重复 key 由 `_parse_json_object` 的 object_pairs_hook 拒绝）。
5. 任何不匹配 → 单一稳定 `AUTHORIZATION_USE_RECORD_INVALID`（不建新错误码、不降级为 replay/epoch 分类）。

### 3.2 存储/节点/fail-closed 保持

- 保留现有 O_NOFOLLOW、`fstat` 常规文件、`0 < size <= 4 KiB`、`nlink > 2` 拒绝、
  group/world-writable 拒绝、目录 trusted 校验、发布 `link` 唯一线性化点、目录 fsync、
  `DURABILITY_UNKNOWN` fail-closed 语义；**不引入** `O_CREAT|O_EXCL` 直接写 final 的回退。
- FIFO 修复（新增）：`os.open(path, O_RDONLY|O_NOFOLLOW)` 对 FIFO 会**阻塞**，构成
  拒绝服务面；在打开标志中加入 `O_NONBLOCK`（对普通文件读取无语义影响），随后
  `fstat` 的 `S_ISREG` 检查将 FIFO/设备节点判为 INVALID，既不阻塞也不放行。
- `nlink == 2` 继续容忍（final + 未回收 temp 的崩溃残留），`nlink > 2` 拒绝；
  由 `test_a1_01_single_crash_residue_hardlink_is_tolerated_as_replay` 固定该边界。

### 3.3 三态语义（报告与测试必须区分）

| 状态 | 触发 | final 状态 | 之后的行为 |
|---|---|---|---|
| `REJECTED_NO_CONSUMPTION`（拒绝） | 验证失败 / body-path-expected 不匹配 / 节点异常 / link 失败 | 无（或原本就存在的腐坏文件原字节不动） | 可修复后重试；本模块无 Reserve/Fake 调用 |
| `CONSUMED_DURABILITY_UNKNOWN`（文件已消费但持久性未知） | link 成功但目录 fsync 失败 | 完整 final 已可见，**保留不删** | 返回 `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`（拒绝，绝不返回成功）；重启按 REPLAYED 处理，不双授权 |
| `NO_CONSUMPTION`（无消费） | crash before write / before link / link 失败 | 无 final（可能残留完整 temp） | 重启后可恰一次成功 |

### 3.4 最小改动清单（实现 commit 预期行号变化）

| 文件位置（基线） | 改动 |
|---|---|
| L802–L847 `_read_use_record` | 签名加 `*, expected_authorization_id: str`；返回值改为 `tuple[str, str]`（`authorization_id, run_epoch`）；新增 id 类型/格式、路径绑定、expected 绑定、`consumed_utc` 校验 |
| L850–L870 `_read_use_record_settled` | 透传 `expected_authorization_id`，返回值同 tuple |
| L1038–L1041、L1082–L1089 | 调用处传 `expected_authorization_id=authorization.authorization_id`，从 tuple 取 epoch 分类 |
| L813 `os.open(... O_RDONLY \| O_NOFOLLOW \| O_CLOEXEC)` | 追加 `O_NONBLOCK`（FIFO 不阻塞）。**Reviewer nit 已更正**：评审指出该 `os.open` 在基线 L813（设计稿误写 L809），实现与报告采用 L813 |

不新增公开 API、不改 `AuthorizationUse`、不改错误码集合（`USE_RECORD_INVALID` 与
`DURABILITY_UNKNOWN` 均为既有码）。

## 4. 测试计划（`tests/integration/a_next_auth/`，全部合成、禁网）

| 测试组 | 用例 | 当前基线预期 |
|---|---|---|
| 合法 replay | 同 epoch → `REPLAYED`；异 epoch → `EPOCH_MISMATCH`；记录字节不变 | PASS |
| body/path 完整性（P2-01） | A 的 body 写入 B 的 record file；body 与 path 不符；读取器 expected id 不符；body id 9 种非法类型/格式；`consumed_utc` 非法 | **xfail → 实现后 PASS** |
| 腐坏/截断/多 key/schema | 0B、非 JSON、JSON 数组、非法 UTF-8、截断、extra key、错 schema、NaN、重复 key | PASS（基线已 INVALID） |
| 节点异常 | symlink → INVALID；`nlink==3` → INVALID；`nlink==2` 崩溃残留 → REPLAYED；FIFO → INVALID 且不阻塞（fork 子进程 + 超时） | FIFO **xfail → 实现后 PASS**；其余 PASS |
| 并发 | 2/10/50 线程 barrier，恰 1 accepted + (n−1) 稳定 REPLAYED，0 INVALID | PASS |
| crash 窗口 | before write / before link / after link before dir fsync（seam 注入 + 真实 `os._exit`），重启恰一次；after-link 状态为已消费→REPLAYED | PASS |
| 三态 | `DURABILITY_UNKNOWN` 拒绝 + final 保留 + 重启 REPLAYED；link 失败 fail-closed 无回退、重启恰一次 | PASS |
| 结构 | AST：模块无 accounting/bridge 导入、无 reserve/claim/settle/send/fake 调用（无第二次 Reserve/Fake 的结构性保证） | PASS |

## 5. 残余风险 / 边界（设计时声明）

1. `expected_authorization_id` 是**内部函数**参数，唯一生产调用方是 `consume_execution_authorization`；
   未来新增调用方必须传自己验证过的 id，否则规则 2 仍会拦截 body/path 错配。
2. 路径绑定用 `path.name`；若目录内存在嵌套路径/其它目录，`_trusted_directory` 已保证
   use-log 是单一受信目录，最终名固定为 64-hex + `.json`，不接受子目录。
3. FIFO 阻断修复依赖 POSIX `O_NONBLOCK`；普通文件语义不受影响，其它特殊文件（device/socket）
   由 `S_ISREG` 拒绝；socket inode 无法通过路径打开（ENXIO），同样 fail-closed。
4. 本次不改变 `nlink==2` 容忍窗口的既有取舍（崩溃残留 final+temp）；已由 R1 报告与
   G4-R 独立 Review 观察-2 披露。
5. 并发/容量仍是单进程内无锁近似（`MAX_AUTHORIZATION_USES` 可能短暂超 1），与 G4-R R1 一致，
   不属 P2-01 范围。

## 6. 实现结果（Commit 2：实现 + 取消 xfail + 本节）

设计门：独立 Reviewer 逐行核对本文 §1–§5，裁定 **A1 设计 = PASS（条件式 C1）**；C1“设计文档先提交”由
commit `0df36de`（本文 + 测试骨架）满足。Reviewer 亲自在基线跑测试骨架：**24 passed / 15 xfailed(strict) / 93.70s**，
与 Owner 预期一致。Reviewer nit（`os.open` 基线行号 L813，非 L809）已在 §3.4 更正。

### 6.1 修改点与最终行号（`src/autoteacher_m0/security/authorization.py`，HEAD）

| 行号（实现后） | 修改 |
|---|---|
| L802–L803 | `_read_use_record` 签名新增 `*, expected_authorization_id: str`，返回 `tuple[str, str]`（id, epoch） |
| L825–L827 | 防御性校验 expected id：非 `str`/非 `_IDENTIFIER` → `AUTHORIZATION_USE_RECORD_INVALID`（先于任何 I/O） |
| L829–L830 | `os.open(... O_RDONLY \| O_NOFOLLOW \| O_NONBLOCK \| O_CLOEXEC)`：FIFO/设备不再阻塞；普通文件语义不变 |
| L858–L868 | 解析后校验：`authorization_id` 为 `str` 且 `_IDENTIFIER.fullmatch`；`run_epoch` 同规则；`consumed_utc` 匹配 `_UTC_TEXT`；字段集合仍精确 4 键 |
| L869–L874 | **路径绑定**：`path.name == sha256(authorization_id) + ".json"`；**expected 绑定**：`authorization_id == expected_authorization_id`；任一不符 → 稳定 `AUTHORIZATION_USE_RECORD_INVALID`（绝不 REPLAYED/EPOCH_MISMATCH） |
| L878–L899 | `_read_use_record_settled` 透传 expected id；重试语义不变（5×10ms 仅用于旧半写 publisher，持久非法仍 INVALID） |
| L1068–L1071 | 快路径（final 已存在）用**已验证签名文档**的 `authorization.authorization_id` 作为 expected id，从 tuple 取 epoch 分类 |
| L1116–L1119 | `link` EEXIST 分支同样交叉校验；失败不再可能被误记为 replay |

未改：`os.replace` 仍 0 处；无 `O_CREAT|O_EXCL` 直写 final 回退；`AuthorizationUse`/错误码集合/公开签名不变。

### 6.2 三态语义与测试证据映射

| 状态 | 实现证据（用例） | 断言 |
|---|---|---|
| **拒绝**（`REJECTED_NO_CONSUMPTION`） | `test_a1_01_body_id_a_in_record_file_of_b_*`、`test_a1_01_foreign_body_id_*`、`test_a1_01_reader_rejects_expected_id_mismatch`、`body_id_format_invalid[10]`、`corrupt_record[9]`、symlink/hardlink/FIFO、`dir_fsync_failure`（拒绝码 `DURABILITY_UNKNOWN` 亦为拒绝） | 拒绝码精确等于 `AUTHORIZATION_USE_RECORD_INVALID`（或 `DURABILITY_UNKNOWN`），断言 `REPLAYED`/`EPOCH_MISMATCH` **不出现**；不产生新 final/temp |
| **已消费但持久性未知**（`CONSUMED_DURABILITY_UNKNOWN`） | `test_a1_02_dir_fsync_failure_is_consumed_but_durability_unknown`、`test_a1_01_hard_process_death_*[_fsync_directory]` | final 完整存在（`schema/id/epoch/consumed_utc` 精确），调用方拿到拒绝而非成功；重启 → `REPLAYED`，恰 1 条记录，无第二次成功 |
| **无消费**（`NO_CONSUMPTION`） | `crash_before_write`、`crash_before_link`、hard-death 前两窗口、`link_failure_fails_closed_without_direct_write_fallback` | 无 final（可能残留完整 temp）；重启恰一次成功，之后 `REPLAYED`；无直写回退 |

“恰一次成功 / 无第二次 Reserve/Fake”证据：(a) 全部并发/crash 用例断言恰 1 accepted、其余稳定 `REPLAYED`、恰 1 条 final；
(b) `test_a1_02_consumption_module_has_no_broker_or_fake_path` 用 AST 断言本模块无 accounting/bridge import、
无 `reserve/claim/settle/release/dispatch/send/fake/connect` 调用——该模块结构上不存在第二次 Reserve/Fake 路径。

### 6.3 测试命令与计数（实现树；`PYTHONPATH=src`，绝对解释器）

| 命令 | 结果 | 用时 | exit | UTC（采集窗口） | 证据 |
|---|---|---|---|---|---|
| `pytest tests/integration/a_next_auth -q -p no:cacheprovider` | **39 passed / 0 failed / 0 skipped**（含实现后取消的 15 个原 xfail） | 69.71s | 0 | ~19:40–19:41 | 控制台 + 提交后 HEAD 复跑见 §6.4 |
| `pytest tests/integration/g4r_auth -q -p no:cacheprovider`（G4-R R1 旧套件回归） | **26 passed** | 261.23s | 0 | ~19:41:46–19:46:07 | `artifacts/a_next/a1/g4r_auth-regression.log` |
| `pytest tests/integration/g4_a -q -p no:cacheprovider`（原 G4-A 回归） | **223 passed** | 139.04s | 0 | ~19:41:46–19:44:05 | `artifacts/a_next/a1/g4_a-regression.log` |
| `pytest tests/security -q -p no:cacheprovider` | **7 passed** | 10.29s | 0 | ~19:46:15–19:46:25 | `artifacts/a_next/a1/security-regression.log` |
| `pytest tests/unit -q -p no:cacheprovider` | **396 passed** | 50.59s | 0 | ~19:46:21–19:47:12 | `artifacts/a_next/a1/unit-regression.log` |
| `pytest --collect-only -q -p no:cacheprovider`（全仓） | **1459 tests collected / 0 collection error** | 3.08s | 0 | ~19:46:15–19:46:18 | `artifacts/a_next/a1/collect-only.log` |
| `ruff check src/autoteacher_m0/security/authorization.py tests/integration/a_next_auth` | **All checks passed** | <1s | 0 | 19:47 | 控制台 |

骨架基线对照（commit `0df36de` 树）：`a_next_auth` = **24 passed / 15 xfailed(strict) / 87.60s**（Owner），
与 Reviewer 独立复跑 24/15/93.70s 一致；实现后同一测试文件取消 xfail 后 **39 passed**，无任何 case 被删除或弱化。

### 6.4 提交后 HEAD 复跑

实现 commit 提交后，在同一 HEAD（tree 与证据采集树同字节，`git diff` 为空）复跑
`pytest tests/integration/a_next_auth -q -p no:cacheprovider` 以绑定 SHA；结果与 §6.3 一致（39 passed）。
完整命令/UTC/exit/HEAD 记录在 `artifacts/a_next/a1/`（gitignored）并向 Lead 汇报。

### 6.5 与历史证据的关系

- `docs/REVIEW_G4R_INDEPENDENT.md` P2-01：本 PR 只关闭“body id 未交叉校验”这一数据完整性缺口；
  不改旧 Review 字节、不改冻结 CSV、不改 R1 报告。
- P2-02（consume 无生产 Controller 调用方）**仍开放**，本 PR 不触碰；`B03/E5-P04=UNVERIFIED`、
  `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING` 不变。
- 与 G4-R R1 修复叠加：R1 的原子 no-replace 发布（temp→fsync→link→fsync(dir)）不变；本 PR 仅加严读取侧校验。

### 6.6 残余风险

1. `expected_authorization_id` 是私有读取器参数，唯一生产调用方传**已验证签名文档**的 id；
   若未来新增调用方必须自行验证来源（否则 path 绑定仍拦 body/path 错配，expected 绑定形同额外防线）。
2. `nlink == 2` 容忍窗口保留（final + 未回收 temp 的崩溃残留），`nlink > 2` 拒绝；属 R1/观察-2 既有取舍。
3. `consumed_utc` 校验采用写入侧唯一格式；若未来支持 v2 record schema，需要显式 schema 版本分流，
   本 PR 不预留隐式兼容（避免放宽为“任意字符串”）。
4. FIFO/特殊节点修复依赖 POSIX `O_NONBLOCK`+`S_ISREG`；已用 fork+timeout 证明不阻塞，但未在
   非 Linux/其它文件系统上跑（环境为 Linux ext4，L1-HOST）。
5. 并发/容量仍为单进程无锁近似（与 R1 相同），不属 P2-01 范围；跨进程共享目录语义未变。
6. 本 PR 只做 L1-HOST；真实 DSH/Controller 端到端接线（A2/P2-02）与 L2 复验仍 NOT_RUN/UNVERIFIED。

### 6.7 复现命令（worktree 根）

```bash
cd "/root/Autonomous Teacher/worktrees/a-next-auth-record"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/integration/a_next_auth -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/integration/g4r_auth -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/integration/g4_a -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/security tests/unit -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest --collect-only -q -p no:cacheprovider
"/root/Autonomous Teacher/.venv/bin/ruff" check src/autoteacher_m0/security/authorization.py tests/integration/a_next_auth
```

证据根：`artifacts/a_next/a1/`（gitignored）：`environment.txt`、`g4r_auth-regression.log`、
`g4_a-regression.log`、`security-regression.log`、`unit-regression.log`、`collect-only.log`。
