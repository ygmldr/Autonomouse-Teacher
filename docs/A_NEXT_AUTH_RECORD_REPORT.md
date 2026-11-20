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
| L809 `os.open(... O_RDONLY \| O_NOFOLLOW \| O_CLOEXEC)` | 追加 `O_NONBLOCK`（FIFO 不阻塞） |

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
