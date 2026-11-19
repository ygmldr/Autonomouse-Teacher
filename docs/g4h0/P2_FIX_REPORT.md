# G4-H0 — P2 定向修复报告（P2-03/04/05/06 + A-07 负例）

- 工作树：`/root/Autonomous Teacher/worktrees/m0-g4h0-fix`（分支 `work/m0-g4h0-fix`）
- 基线：`3e7afee077845a071cd364e93ab209cac20b2d5f`
- 范围：仅本机、无 Key、无真实 Provider/HTTP/付费调用；未修改 `gates.py`/`run_live.sh`/
  `dsh_adapter.py`/`cli.py`，未修改冻结 Packet/Stage/证据，未改 `tests/integration/g4_a/test_a12_replay_epoch.py`。
- 环境：Python 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`）、ruff 0.17.5、pytest
  `pythonpath=src`（已确认 `autoteacher_m0.__file__` 指向本 worktree）。

## 0. 结论总表

| ID | 处置 | 摘要 |
|---|---|---|
| **P2-03** | **FIXED** | use record 改为“同目录临时文件写全 + fsync + `os.link` 原子发布”；loser 稳定 `AUTHORIZATION_REPLAYED`；2 进程压测 before 1/30（自然）与 30/30（放大写入窗口）`AUTHORIZATION_USE_RECORD_INVALID` → after 40/40 + 40/40 全绿、0 双消费、0 残留临时文件 |
| **P2-04** | **FIXED** | 删除 `tests/security/test_scan_git_secrets.py::test_positive_detectors` 中未使用的 `material = _synthetic_material()`（F841 一行）；`ruff check tests/security/` = All checks passed |
| **P2-05** | **FIXED（观测补丁）** | 在 Client 侧 envelope deadline 分支新增 **observation-only** dispatch-window 记录（`dispatch_seq=None`、`reserved/dispatched` 记录 worker 进度、不参与任何 allow/deny）；worker 正常路径记录不变 |
| **P2-06** | **FIXED** | recovery 不再把原始窗口原因重写为 `RECEIPT_DOCUMENT_SCHEMA_INVALID`：保留原 reason 为主标签并追加 `\|RECOVERY_EVIDENCE:<reason>`；状态/held/不重发语义不变 |
| **A-07** | **EVIDENCE DONE** | `scripts/g4h0/no_key_probes.py`：22/22 PASS（LiveGate 恒 BLOCKED、require_live 恒抛、run_live/CLI exit 3、0 网络系统调用、0 Key/env、新增代码无网络/凭据；详见 `NO_KEY_AND_LIVEGATE_EVIDENCE.md`） |

安全姿态未放松：恰好一次消费、0 双消费、fail-closed 错误码、授权/预算/路由/绑定校验、LiveGate 恒 BLOCKED、`E5_PRELIVE_FULL` 等状态常量全部不变。

---

## 1. P2-03 — 授权并发消费 use record 原子发布

### 1.1 根因（先确认）

旧实现（`authorization.py::consume_execution_authorization`）先 `os.open(O_CREAT|O_EXCL)`
创建最终记录，**之后**才 `os.write` 写 body。两个 consumer 竞争时：

1. A 创建空记录（size 0），尚未写完 body；
2. B 的 `record_path.exists()` 为真（或 B 的 `O_EXCL` 得 `FileExistsError`）→ 读记录；
3. B 读到空/部分文件 → `_read_use_record` 判 size 0 / JSON 解析失败 →
   `AUTHORIZATION_USE_RECORD_INVALID`（期望 `AUTHORIZATION_REPLAYED`）。

恰好一个 consume 成功、0 双消费，安全仍 fail-closed，但错误码/证据不稳定（P2-03）。

### 1.2 修复（`src/autoteacher_m0/security/authorization.py`）

- 新增 `_publish_use_record(record_path, body) -> bool`：
  1. 在**同一目录**以 `os.urandom(16)` 生成临时名（`.use-record-tmp-<hex>.tmp`）；
  2. `os.open(temp, O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0o600)`；
  3. 循环 `os.write` 写全 + `os.fsync`；
  4. `os.link(temp, record_path)` **原子发布**；`FileExistsError` 即另一 consumer 已成功（返回 `False`）；
  5. `finally` 清理临时文件（成功/失败/EEXIST 均清理；清理失败不影响结果，因为临时文件不是 use record）。
- 原子发布失败（`os.link` 非 EEXIST 的 `OSError`）→ 清理 temp、**不创建记录**、抛
  `AUTHORIZATION_USE_LOG_WRITE_FAILED`（fail-closed；授权未被消费，后续可重试）。
- loser 读取使用 `_read_use_record_settled()`：仅在 `AUTHORIZATION_USE_RECORD_INVALID`
  （空/部分/坏 JSON，即旧版本可能留下的半写记录）时有界重试
  `_USE_RECORD_READ_ATTEMPTS=20 × 10ms`；超界/其它错误码/符号链接仍立即 fail-closed。
  重试只影响“读记录并判 replay”的分类，**不授予任何权限**。
- `_read_use_record` 加固为 `os.open(O_RDONLY|O_NOFOLLOW|O_CLOEXEC)` + `fstat` + 定长读取
  （结束再验 size），杜绝 stat/read 之间被 symlink/类型替换（旧检查保留）。
- `MAX_AUTHORIZATION_USES` 计数排除临时文件：只统计名字**不以**
  `_USE_RECORD_TEMP_PREFIX` 开头的条目 → 崩溃残留临时文件不会污染容量计数/锁死授权。
- 不变项：恰好一次（`link(2)` 不可能覆盖已存在名字 → 恰好一个 publisher 返回成功）；
  记录 0600；目录仍必须为仓库外、非 symlink、operator-owned、非 group/other 可写；
  symlink record 仍 `AUTHORIZATION_USE_RECORD_INVALID`；无任何校验被放宽。

### 1.3 定向测试（新增，未改旧 a12）

`tests/integration/g4_h0/conftest.py` + `tests/integration/g4_h0/test_p2_03_concurrent_consume.py`
（TEST_ONLY 合成签名 fixture，复用 `g4a_support`；autouse socket guard 禁 IP 网络）：
**14 passed**。

覆盖：`os.link` 内 `threading.Barrier` 强制双 consumer 在 link 处会合后竞争；延时 body 写入
（旧实现可见空记录的回归形态）；短写循环；link `EEXIST` 后读完整记录（同 epoch →
`AUTHORIZATION_REPLAYED`，不同 epoch → `AUTHORIZATION_EPOCH_MISMATCH`）；link 失败
fail-closed 且未消费；临时/记录 open flags 与 0600；空/半写 legacy 记录在重试窗口内 →
`REPLAYED`、窗口外/持续坏 → `INVALID`；陈旧临时文件不计入 MAX 计数（MAX=1 仍可消费一次、第二次
`AUTHORIZATION_USE_LOG_FULL`）；符号链接记录永不跟随；20 轮并发稳定性（本文件内 8 轮内存版 +
脚本 40 轮进程版）。

### 1.4 压测（`scripts/g4h0/p2_03_stress.py`，2 进程 × ≥30 轮，本地 /tmp，无网络）

脚本：parent 一次构造 TEST_ONLY `TrustedFixture`；每轮重新签名唯一 `authorization_id`，fork 2 个
consumer 进程在 `multiprocessing.Barrier` 后竞争 consume；逐轮记录 winner/loser 码、双消费、
`*.json` 记录数、残留非记录文件、记录 0600、耗时；`--widen-write-ms` 是 **TEST_ONLY 竞态放大器**
（在每个 consumer 的记录 body `os.write` 前 sleep，仅用于让修复前的“创建后未写”窗口可确定性观测，
不修改被测实现）。修复前证据在 `/tmp` 的 `git archive 3e7afee` 干净副本中运行（不动主工作树/其它 worktree）。

| 运行 | 代码 | 轮数 | 失败轮 | loser 码分布 | 双消费 | 残留临时/非记录文件 | 记录权限 |
|---|---|---|---:|---|---:|---|---|
| `p2_03_stress_before_fix_natural` | 基线 `3e7afee` | 30 | **1** | `REPLAYED`×29, **`AUTHORIZATION_USE_RECORD_INVALID`×1** | 0 | 0 | 0600 |
| `p2_03_stress_before_fix_widened` | 基线 `3e7afee` | 30 | **30** | **`AUTHORIZATION_USE_RECORD_INVALID`×30** | 0 | 0 | 0600 |
| `p2_03_stress_after_fix_natural` | 本修复 | **40** | **0** | `AUTHORIZATION_REPLAYED`×40 | **0** | 0 | 0600 |
| `p2_03_stress_after_fix_widened` | 本修复 | **40** | **0** | `AUTHORIZATION_REPLAYED`×40 | **0** | 0 | 0600 |

命令（after）：

```bash
cd "/root/Autonomous Teacher/worktrees/m0-g4h0-fix"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/g4h0/p2_03_stress.py \
  --rounds 40 --label after-fix-natural --output docs/g4h0/evidence/p2_03_stress_after_fix_natural.json
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/g4h0/p2_03_stress.py \
  --rounds 40 --widen-write-ms 100 --label after-fix-widened \
  --output docs/g4h0/evidence/p2_03_stress_after_fix_widened.json
# 两次 exit 0；summary: failure_count=0, double_consume=0, record_modes=["0o600"],
# residual_non_record_files=[], loser_code_histogram={"AUTHORIZATION_REPLAYED": 40}
```

before 证据同理在 `/tmp/at-p203-before`（`git archive 3e7afee`）中运行，日志见
`docs/g4h0/evidence/p2_03_stress_before_fix_natural.log`、`..._widened.log`、
`docs/g4h0/evidence/p2_03_stress_before_fix_natural.json`、`..._widened.json`。

### 1.5 历史复现测试（旧 a12，未修改）

- 修复前：`test_a12_concurrent_consumption_admits_exactly_one` standalone 循环 **27/30 PASS、
  3/30 FAIL**，失败形态均为 `AUTHORIZATION_USE_RECORD_INVALID`（断言期望 `AUTHORIZATION_REPLAYED`）
  → 见 `docs/g4h0/evidence/p2_03_a12_loop30_before.log`。
- 修复后：同循环 **30/30 PASS** → `docs/g4h0/evidence/p2_03_a12_loop30_after.log`；
  `pytest tests/integration/g4_a/test_a12_replay_epoch.py -q` = **19 passed**。

---

## 2. P2-04 — 扫描器测试 F841

- 命令：`"/root/Autonomous Teacher/.venv/bin/ruff" check tests/security/test_scan_git_secrets.py`
- 修复前：`F841 Local variable material is assigned to but never used`
  （`tests/security/test_scan_git_secrets.py:169`）。
- 修复：删除 `test_positive_detectors()` 中未使用的 `material = _synthetic_material()` 一行
  （`_positive_cases()` 自身会调用 `_synthetic_material()`；无行为变化）。
- 修复后：`ruff check tests/security/` → `All checks passed!`；`pytest tests/security/` → **7 passed**。
- 证据：`docs/g4h0/evidence/p2_04_ruff_test_scan_git_secrets.log`。

---

## 3. P2-05 — pre-send timeout 的 dispatch-window 观测缺口

### 3.1 根因

每个 dispatch 的最终记录由 worker 线程在 `_handle_payload_serial` 的 `finally` 中写出。
F5 `timeout-pre-send` 用例：deadline 800ms，而 worker 在注入的 `before_reserve` 测试延迟中
sleep 2500ms；client 侧 800ms 收到 `DEADLINE_EXCEEDED` 后，可信 launcher 停止进程，worker 的
finally 来不及执行 → dispatch-window 无记录。安全结论仍由 0 reservation/attempt/Fake 与
DSR error 支持，但缺少窗口观测。

### 3.2 修复（observation-only，不改变任何允许/拒绝）

- `_CancelState` 增加两个**观测用**进度标记 `reserved`/`dispatched`（默认为 False）；
  Reserve 成功后、进入 Fake 发送边界前分别置位（纯赋值，不参与任何控制流/判断）。
- 新增 `TrustedController._observe_envelope_deadline(env, state, code)`：在 client 侧
  envelope deadline 分支写一条 **observation-only** 记录：
  `observation_only=true`、`observation_phase="envelope_deadline_no_terminal_frame"`、
  `dispatch_seq=null`（不占 dispatch 序号）、`outcome="deadline_observed"`、
  `error_code=<deadline code>`、`reserved/dispatched` 记录当时 worker 进度（无 state 时为 null）。
- 仅在 deadline 分支调用并独立 try/except（观测失败绝不掩盖真实 abort）。
- 正常 worker 记录逻辑/字段不变；F2 既有“每 dispatch 一条最终记录”的证据不受影响。

### 3.3 测试（新增 `tests/integration/g4_f5/test_f5_pre_send_timeout_observation.py`，2 项）

1. deadline 在 worker 仍 sleep 于 `_prepare_checked` 时触发：在只读到 error frame 的瞬间，journal
   已有且只有 1 条 observation-only 记录（`reserved=False`、`dispatched=False`、
   `dispatch_seq=None`、`error_code=DEADLINE_EXCEEDED`）；随后 `generator.close()` 让 worker 收尾，
   journal 变 2 条（原 worker 记录未变，`dispatch_seq=1`）；整个用例 **0 reservation / 0 attempt /
   0 Fake / Broker requests=0**（fail-closed 不变）。
2. 直接调用 observation helper（state 标记 reserved/dispatched=True）：记录如实显示 True，证明它
   不会把 post-send 窗口误标成 pre-send；`_dispatch_seq` 不被消耗。

---

## 4. P2-06 — recovery 重写 revocation reason

### 4.1 根因

`revocation-post-reserve`：attempt 已 `SETTLEMENT_UNCERTAIN`，reason 为
`REVOKED_PRE_SEND:RUN_AUTHORIZATION_REVOKED`，`receipt_json=NULL`。重启 recovery 对非终态行调用
`_verify_receipt_document` → `RECEIPT_DOCUMENT_SCHEMA_INVALID`，Broker 仍 PENDING，于是
`mark_settlement_uncertain(reason=...)` 用 receipt 证据原因**覆盖**了原始撤销窗口原因。

### 4.2 修复（`src/autoteacher_m0/bridge/controller.py`）

- 新增 `_preserved_uncertain_reason(row, fallback)`：当行本来已是 `SETTLEMENT_UNCERTAIN` 且有
  非空 reason 时，保留原 reason 为主标签，追加 `|RECOVERY_EVIDENCE:<fallback>`（≤256 字符）；
  否则退回 fallback。
- 应用于 `reconcile_on_startup` 中 5 处“再次确认不确定”的写入（receipt 校验失败、Broker 状态不可用/
  未知、reconcile settle 失败/拒绝）；Broker 终态 OK/FAILED 的 `SETTLED`/`WORST_CASE_HELD`
  路径不变（Broker 仍是费用权威，A-04 语义不变）。
- 状态仍 `SETTLEMENT_UNCERTAIN`，held/known/不重发/不双结算语义完全不变；只改证据标签。

### 4.3 测试（新增 `tests/integration/g4_f5/test_f5_recovery_reason.py`，3 项）

- `RevokeOnAuthorizeGate`（post-reserve 窗口）+ 重启 recovery：attempt 仍 `SETTLEMENT_UNCERTAIN`，
  reason 仍以 `REVOKED_PRE_SEND:` 开头且含 `RUN_AUTHORIZATION_REVOKED`，含
  `|RECOVERY_EVIDENCE:`；gate held=reserved、known=0、Fake=0、Broker 1 PENDING。
- `RevokeOnConsumeGate`（consume 窗口）：同样保留原撤销原因，Fake=0、仅 1 reservation。
- 非撤销窗口（post-send deadline）：原 `DEADLINE_BEFORE_FAKE_RESULT` 类原因同样保留并追加
  recovery 证据；恢复不重发（Fake 计数不变）。

---

## 5. A-07 — 无 Key / 恒 BLOCKED 负例（摘要）

完整 22/22 证据见 `docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md` 与
`docs/g4h0/evidence/a07_no_key_probes.{json,log}`。要点：`LiveGate.inspect` 即使全部证据满足仍
`BLOCKED`（首个 reason `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`）；`require_live` 恒抛
`SECURITY_BLOCKED`；`run_live.sh`/CLI `--live` exit 3 且假 Key/env/Markdown 无效、假 Key 不打印；
Adapter 四入口在 SDK import 前拒绝、`deepseek_harness` 未 import；`strace -f -e trace=network`
对两入口 0 `AF_INET/connect`；进程 env 0 key-like、仓库无 `.env`、src 不读 key env/不加载 dotenv；
4 个冻结 Live 文件相对基线零 diff；新增代码 0 网络/Provider import、0 凭据模式、0 新 env 解锁开关。

---

## 6. 回归与命令（实测）

| 命令 | 结果 |
|---|---|
| `pytest tests/integration/g4_h0 -q` | **14 passed** |
| `pytest tests/integration/g4_f5 -q` | **17 passed**（12 既有 + 2 P2-05 + 3 P2-06） |
| `pytest tests/integration/g4_a/test_a12_replay_epoch.py -q` | **19 passed** |
| a12 并发用例 standalone ×30 | **30/30 passed** |
| `pytest tests/security -q` | **7 passed** |
| `ruff check src/autoteacher_m0/security/authorization.py src/autoteacher_m0/bridge/controller.py tests/integration/g4_h0 tests/integration/g4_f5 scripts/g4h0 tests/security` | All checks passed |
| `PYTHONPATH=src python scripts/g4h0/p2_03_stress.py --rounds 40 ...` ×2 | exit 0，0 双消费，loser 全 `REPLAYED` |
| `PYTHONPATH=src python scripts/g4h0/no_key_probes.py` | exit 0，22/22 PASS |
| `pytest tests/integration/g4_h0 tests/integration/g4_f5 tests/integration/g4_a/test_a12_replay_epoch.py tests/integration/g4_a/test_a07_trusted_file_boundary.py tests/security tests/unit/security -q` | **189 passed**（85.02s，exit 0） |

**NOT_RUN / 交由 Lead 集成复跑**：`tests/integration/g4_a/` 全目录、`tests/unit/` 全量、
`tests/integration/g4_f2`、`g4_f3`、`g4_c/d/b`、全仓 ruff——本轮时间盒内未重跑（无失败记录，
不是被掩盖的失败）。已改动的 product 代码仅 `authorization.py` 与 `controller.py`
（recovery reason + observation-only），对应定向套件已通过。

## 7. 安全论证与残余风险

**未放松的约束**：

1. 恰好一次消费：原子 `link(2)` 保证只有一个 consumer 发布成功、0 双消费（压测 40+40 轮验证）；
2. fail-closed 不变：任何记录/发布/读取异常仍拒绝（`WRITE_FAILED`/`INVALID`/`UNREADABLE`），
   持久坏记录不会变成 replay；重试只影响 loser 的错误码分类，不授予任何权限；
3. 全部既有校验不变：外部文件/仓库外/非 symlink/0600/`O_NOFOLLOW`/5 绑定根/路由/工具/预算/
   时限/签名/撤销；
4. `MAX_AUTHORIZATION_USES` 仍为 4096 上限，临时文件不计入；
5. LiveGate/`gates.py` 状态常量/`run_live.sh`/`dsh_adapter.py`/`cli.py` 零改动；
6. P2-05 观测记录不参与 allow/deny；P2-06 只改 reason 文本，状态/held 语义不变。

**残余风险**：

- 原子发布依赖同目录 `os.link`（硬链接）支持；不支持硬链接的文件系统上 consume 会
  fail-closed 为 `AUTHORIZATION_USE_LOG_WRITE_FAILED`（不会降级为不安全路径；属部署约束，
  本机 ext4/overlayfs 已验证）。
- `fsync` 覆盖记录 body；目录项未额外 `fsync`（与旧语义一致）——掉电持久性不在本修复范围。
- 旧版本遗留的半写记录：reader 有界重试（20×10ms）后可正确 replay；仍不可读则 INVALID
  （fail-closed，不消费）。
- 压测为宿主机 2 进程；未做容器内/跨 UID 竞争（G4-H0 无 Key 范围；不改变安全结论）。
- P2-05 观测记录可能在 worker 正常收尾后与最终记录同时存在（最多 1 条 observation-only +
  1 条最终记录）；以 `observation_only` 字段区分，仅在 envelope deadline 分支产生。
- 真实 Provider/CLI 全量回归、OCI/Node/DSH 运行属 NOT_RUN，交由 Lead/Reviewer 集成复跑。

## 8. 变更文件

```text
src/autoteacher_m0/security/authorization.py                  P2-03 原子发布 + 有界读取重试 + 计数排除 temp
src/autoteacher_m0/bridge/controller.py                       P2-05 观测事件 + P2-06 recovery reason 保留
tests/integration/g4_h0/conftest.py                           新 P2-03 定向测试 fixture（TEST_ONLY）
tests/integration/g4_h0/test_p2_03_concurrent_consume.py      新 P2-03 定向测试（14 项）
tests/integration/g4_f5/test_f5_pre_send_timeout_observation.py  新 P2-05 测试（2 项）
tests/integration/g4_f5/test_f5_recovery_reason.py            新 P2-06 测试（3 项）
tests/integration/g4_f5/g4f5_support.py                      仅新增可选 dispatch_journal 参数
tests/security/test_scan_git_secrets.py                       P2-04 删除 1 行未使用变量
scripts/g4h0/p2_03_stress.py                                  2 进程 30+ 轮压测
scripts/g4h0/no_key_probes.py                                 A-07 本地负例探针
docs/g4h0/P2_FIX_REPORT.md                                    本报告
docs/g4h0/NO_KEY_AND_LIVEGATE_EVIDENCE.md                     A-07 证据
docs/g4h0/evidence/*.log|json                                 原始证据
```

未修改：`tests/integration/g4_a/test_a12_replay_epoch.py`（历史复现证据，保持原样且修复后稳定通过）、
`gates.py`/`run_live.sh`/`dsh_adapter.py`/`cli.py`、冻结 Packet/Stage/矩阵、主工作树与其它 worktree。
