# M0 G4-R R1 — Atomic No-Replace Authorization Use Record (P2-03)

**Report owner**：F-A implementation agent `a-g4r-auth`（非独立 Reviewer；独立复算由 R5 Reviewer 负责）
**日期（UTC）**：2026-11-20
**范围**：G4-R PR-R1 / `fix/g4r-auth-use-record`，仅 `src/autoteacher_m0/security/authorization.py` 的
`consume_execution_authorization()` 原子单次消费与对应 L1-HOST 测试。0 Key、0 Provider、0 外部
HTTP/TCP、Fake/合成-only；不改 LiveGate/Broker 商业语义/冻结 Packet/旧 Reviewer 报告。

## 1. 身份

| 项 | 值 |
|---|---|
| repository | `/root/Autonomous Teacher`（含空格路径，所有命令加引号） |
| worktree | `/root/Autonomous Teacher/worktrees/g4r-auth` |
| branch | `fix/g4r-auth-use-record` |
| Parent SHA（base = `main` = `origin/main`） | `3e7afee077845a071cd364e93ab209cac20b2d5f` |
| Implementation HEAD SHA（code+tests，证据采集对象） | `f026036cfdc33252a10bc07248a1b08da6693681` |
| Commits | `df3573e` fix(g4r): atomic no-replace authorization use record (P2-03)；`f026036` test(g4r): R1 atomic single-use suite and independent probe；本报告文档提交其后（不改 code/test 字节） |
| Python | 3.11.15（`/root/Autonomous Teacher/.venv/bin/python`） |
| pytest / ruff | pytest 9.2.0 / ruff 0.17.5 |
| OS / 文件系统 | Linux 6.17.13-2-pve x86_64；root ext4；uid 0；nproc 12 |
| 证据根（gitignored，不入库） | `artifacts/g4r/r1/` |
| 无网络/无 Key 证据 | `tests/integration/g4r_auth/conftest.py` autouse socket guard（任何 AF_INET/AF_INET6 connect 即断言失败）；全部 fixture 为 `TEST_ONLY_` 合成 Ed25519 seed 与 pytest 临时目录 |

## 2. 变更表（Parent..HEAD）

| 文件 | 变更 | sha256 |
|---|---|---|
| `src/autoteacher_m0/security/authorization.py` | +243/−28：`consume_execution_authorization` 改为 temp→fsync(file)→`os.link`(no-replace)→fsync(dir)→回收 temp；新增 `_read_use_record_settled`、`_open_use_record_temp`、`_write_use_record_body`、`_link_use_record_no_replace`、`_fsync_directory`、`_safe_unlink_temp`、`_count_use_log_entries`、`_reap_stale_use_record_temps`；`_read_use_record` 改为 `O_NOFOLLOW`+`fstat`（symlink/0B/>4KiB/`nlink>2`/group-world-writable → INVALID） | `c22038a60e40a79a87c7f2056a42e068ce333348162d1458f0a1c15b428e2d9d` |
| `tests/integration/g4r_auth/conftest.py` | 新建：合成 `trusted` fixture（只读复用 `g4a_support.TrustedFixture`）+ 禁网 guard | `9f5a7c4b4aff2b8f385653ee8c1ebdaa4c69a184f2bf45465862ccef03730df9` |
| `tests/integration/g4r_auth/test_r1_atomic_use_record.py` | 新建：R1-01..R1-06 共 26 个 case（200 线程轮、50 进程轮、跨 epoch、腐坏 final、crash 注入+真实 `os._exit` 进程死亡、fail-closed 负例） | `0b68a00d8c12a376ca0bdd56cd5459a50bae5f32d785e736e7e3f1d5298ec3ea` |
| `scripts/g4r/r1_independent_probe.py` | 新建：R1-08 非 pytest 独立多进程探针（Reviewer 可复用，默认 50 轮） | `86ece37be170a334cbbffec482d364581451891682cc1bfe24a6452e3d24634c` |

受保护文件 diff 检查：`git diff --name-only 3e7afee..HEAD -- src/autoteacher_m0/security/gates.py scripts/g4/run_live.sh src/autoteacher_m0/runtime/dsh_adapter.py src/autoteacher_m0/cli.py docs/REVIEW_G4F_INDEPENDENT.md docs/REVIEW_G4_INDEPENDENT.md tests/integration/g4_a/ artifacts/` = **0 个文件**（证据：`artifacts/g4r/r1/change-inventory.txt`）。旧 `tests/integration/g4_a/test_a12_replay_epoch.py` **未修改**。

## 3. 实现要点（与计划 §4.2 对应）

1. 完整验证（签名/绑定/撤销/时间窗/预算/工具/route）与 `_trusted_directory`（绝对路径、非仓库内、非 symlink、0700/非 group-world writable、非 candidate-uid）保持原语义，全部在发布前完成。
2. 最终名 `sha256(authorization_id).json`；发布前发现已存在 final → `_read_use_record_settled` 分类 `REPLAYED`/`EPOCH_MISMATCH`，持续非法 → `AUTHORIZATION_USE_RECORD_INVALID`。
3. 正文写入同目录随机临时名：`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0600`，写满 + `fsync(fd)`。
4. **唯一线性化点 = `os.link(tmp, final, follow_symlinks=False)`**：原子 create-if-absent，绝不覆盖。`FileExistsError` → loser 读取已完整发布的 final 分类（永不 INVALID 半成品）；其他 `OSError`/`NotImplementedError`（不支持 link/EXDEV/权限）→ fail-closed `AUTHORIZATION_USE_LOG_WRITE_FAILED`，**无“直接写 final”回退**，且清理 tmp、final 名不动。
5. link 成功后 `fsync` 目录；失败 → fail-closed `AUTHORIZATION_USE_LOG_DURABILITY_UNKNOWN`，**保留 final、不返回成功**（use 已花掉，重启后按 REPLAYED 处理，不双授权、不发送）。
6. temp 回收仅删除保留前缀 `.use-record-tmp-` 的普通文件；容量统计只计完整 final（`MAX_AUTHORIZATION_USES`），temp 单独上限 `MAX_USE_RECORD_TEMPS=256` + 300s TTL 回收，崩溃残留不锁死/DoS。
7. `os.replace` 未使用（全文件 grep 0 处）；link 前不 Reserve/Claim/发送（本模块无 accounting/bridge import、无 reserve/claim/settle/dispatch/send 调用，AST 测试 `test_r1_04_consume_has_no_reserve_claim_or_broker_path` 断言）。
8. `_read_use_record` 增加 `nlink > 2` 拒绝（硬链接异常 fail-closed；`nlink == 2` 容忍“final+崩溃残留 temp”窗口）。

## 4. 逐 case 结果（全部在 HEAD `f026036` 采集）

环境 SHA：Python 3.11.15 / pytest 9.2.0 / ruff 0.17.5 / base `3e7afee` / HEAD `f026036`；每条证据 metadata 见 `artifacts/g4r/r1/*.meta.json`（含 command/start_utc/end_utc/exit_code/head/branch/python/pytest/ruff/source）。

| Case | 状态 | 实测数字 | 命令（worktree 根，`PYTHONPATH=src`） | UTC | exit | 证据 |
|---|---|---|---|---|---|---|
| R1-01 | **PASS** | 200/200 轮 = 恰 1 accepted + 1 `AUTHORIZATION_REPLAYED`，0 INVALID；final JSON/0600/无 temp 残留 | `.venv/bin/python -m pytest tests/integration/g4r_auth -k r1_01 -q`（默认 `G4R_R1_THREAD_ROUNDS=200`） | 16:24:33–16:27:55（全 suite） | 0 | `r1_05_06_g4r_auth_suite.log`, `r1_per_case_verbose.log` |
| R1-02 | **PASS** | 50/50 轮 = 恰 1 accepted + 1 REPLAYED；每轮 fork 2 个独立进程/独立 FD，assert 子进程 exitcode 0 | 同上 `-k r1_02`（默认 `G4R_R1_PROCESS_ROUNDS=50`） | 同上 | 0 | 同上 |
| R1-03 | **PASS** | 20/20 轮跨 epoch 竞争：恰 1 accepted，loser 恰 `AUTHORIZATION_EPOCH_MISMATCH`；winner record epoch 一致 | 同上 `-k r1_03`（默认 `G4R_R1_EPOCH_ROUNDS=20`） | 同上 | 0 | 同上 |
| R1-04 | **PASS** | 6 种持久腐坏 final（0B / 非法 JSON / `{}` / `[]` / 缺字段 / 错 schema）各重复 2 次均 `AUTHORIZATION_USE_RECORD_INVALID`（非 REPLAYED），无新 final、0 temp；AST 断言无 Reserve/Claim/Broker/网络调用（结构上 0 Reserve） | 同上 `-k r1_04`；静态 `test_r1_04_consume_has_no_reserve_claim_or_broker_path` | 同上 | 0 | 同上 |
| R1-05 | **PASS** | 注入点 3 个（write 前 / fsync 后 link 前 / link 后 dir fsync 前）+ 真实 `os._exit(23)` 进程死亡同 3 点：before-write 无 final→重启恰 1 次成功；after-fsync 留 1 个完整 temp、无 final→重启恰 1 次成功；after-link final 完整（use 已花）→重启 REPLAYED，绝不第二次成功；dir fsync `EIO` → `DURABILITY_UNKNOWN` 拒绝、final 保留、重启 REPLAYED | 同上 `-k r1_05`（4 seam + 3 hard-death） | 同上 | 0 | 同上 |
| R1-06 | **PASS** | link EOPNOTSUPP/ENOSYS/EXDEV/EACCES + `NotImplementedError` → `WRITE_FAILED` 且无 final（无直接写回退）、无 temp；temp 创建权限拒绝 → `WRITE_FAILED`；final symlink → INVALID；`nlink==3` 硬链接异常 → INVALID；dir fsync EIO → `DURABILITY_UNKNOWN` + final 保留 + 重启 REPLAYED | 同上 `-k r1_06` | 同上 | 0 | 同上 |
| R1-07 | **PASS** | 旧 `tests/integration/g4_a` 全套 **223 passed / 0 failed**（104.59s）；旧 a12 并发用例独立循环 **30/30 passed**（修复前同命令 **23/30 passed、7/30 failed**，复现 P2-03） | `.venv/bin/python -m pytest tests/integration/g4_a -q`；`for i in $(seq 1 30); do pytest ...::test_a12_concurrent_consumption_admits_exactly_one -q; done` | 16:24:33–16:26:18 / 16:24:41–16:25:16 | 0 / 0 | `r1_07_g4a_old_suite.*`, `r1_07_a12_determinism_30.*`, `r1_07_a12_BEFORE_fix_30runs.*` |
| R1-08 | **PASS（Owner 侧探针；Reviewer 独立复算仍待 R5）** | 自写 fork 探针 50/50 轮恰 1 accepted+REPLAYED，100 个不同 worker PID，0 double authorization，0 temp 残留；跨 epoch 模式 25/25 轮恰 1 accepted+EPOCH_MISMATCH | `.venv/bin/python scripts/g4r/r1_independent_probe.py --rounds 50`；`... --rounds 25 --cross-epoch` | 16:24:33–16:25:08 / 16:24:33–16:24:51 | 0 / 0 | `r1_08_independent_probe.log`, `r1_08_independent_probe_cross_epoch.log` |

汇总：新 suite **26 passed / 0 failed**（201.46s）；旧 suite **223 passed / 0 failed**；ruff 变更范围 **All checks passed**。所有证据命令 exit=0，均在 `artifacts/g4r/r1/`。

## 5. 与历史 P2-03 证据的关系

- `docs/REVIEW_G4F_INDEPENDENT.md` §10.1 P2-03：Reviewer 独立 2/30 失败、full suite 2/2 失败，失败形态为 loser 读到未写完 use record 返回 `AUTHORIZATION_USE_RECORD_INVALID`。本报告不改写该历史判定。
- 本工作树在 **未修改的 parent `3e7afee`** 上以同一旧 a12 命令复现 **7/30 failed**（`r1_07_a12_BEFORE_fix_30runs.log`），与 P2-03 形态一致（恰 1 成功 + loser 错误码不稳定），作为修复前基线。
- 修复后同一旧测试 **30/30 passed** 且新 suite 26/26 passed；旧测试本身未改动，a12 的断言（len(results)==1、len(errors)==1、REPLAYED、1 个 use record）原样保留。
- 根因处理：final 名在 link 时一次性可见且内容已完整 fsync，因此不存在“loser 读到半成品 final”的窗口；真正持久腐坏的 final 仍 INVALID，未把 INVALID 伪装成 REPLAYED。

## 6. 未验证项 / 残余（诚实边界）

1. **R1-05 crash 注入方式**：确定性在命名 seam 处注入（in-process `BaseException` + 真实 `os._exit` 不执行清理）。未做任意指令的随机 SIGKILL、断电/掉电、内核回写中断测试；真正的持久性依赖 ext4+fsync 语义，未在其它文件系统上复测。
2. **R1-06 文件系统/权限负例为注入式**：EXDEV 需要独立挂载文件系统、`EACCES` 在 root（uid 0）下无法用 chmod 真实触发、`EOPNOTSUPP/ENOSYS` 需不支持 link 的 FS，因此这些分支以 monkeypatch `os.link`/seam 注入验证“拒绝且无回退”，未在真实 NFS/overlayfs/tmpfs 上执行。容器/podman 环境的 R1 复跑属 R4 联合回归，本 PR 未运行（主 Host L1-HOST）。
3. **“link 前不 Reserve/Claim/发送”**：本 PR 只改授权模块；该模块静态无 accounting/bridge import、无 reserve/claim/settle/dispatch/send 调用（AST 测试断言），因此结构上不可能在 link 前 Reserve/发送。但 Controller→Broker 的端到端线性化仍由既有 g4_a 套件与 R4 联合回归覆盖，本报告不声称已做端到端 L2 取证。
4. **跨主机/并发多进程共享文件系统**的 link 语义只按本机 POSIX 验证；`MAX_AUTHORIZATION_USES` 容量判定为无锁近似（并发下最多可短暂超 1 条，和修复前一致），未做严格分布式计数。
5. **DURABILITY_UNKNOWN 新错误码**：是新增 fail-closed reason（发布后目录 fsync 失败时返回），不改变既有错误码语义；Controller 当前未消费该码（该模块尚无 Controller 调用方），若未来接入应把该原因按“不确定/不发送”处理。
6. **R1-08**：Owner 提供的独立探针已跑通，但按计划 §9/§10，**Reviewer 必须自建/复跑自己的攻击探针**，Owner 探针不能替代独立 Reviewer 裁定。
7. 0 真实 Key/Provider/HTTP/TCP、无 Live；LiveGate/G4-H/G5 状态未触碰。

## 7. 复现命令（worktree 根）

```bash
cd "/root/Autonomous Teacher/worktrees/g4r-auth"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -c "import autoteacher_m0; print(autoteacher_m0.__file__)"  # 必须指向本 worktree src
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/integration/g4r_auth -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" -m pytest tests/integration/g4_a -q -p no:cacheprovider
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" scripts/g4r/r1_independent_probe.py --rounds 50
"/root/Autonomous Teacher/.venv/bin/ruff" check src/autoteacher_m0/security/authorization.py tests/integration/g4r_auth scripts/g4r
```

轮数可用 `G4R_R1_THREAD_ROUNDS` / `G4R_R1_PROCESS_ROUNDS` / `G4R_R1_EPOCH_ROUNDS` 调整；默认值 200/50/20 为验收下限。

## 8. 证据根清单（`artifacts/g4r/r1/`，gitignored）

```text
change-inventory.txt                       base..HEAD diff、变更文件 sha256、受保护文件 0 diff
environment.txt                            worktree/branch/SHA/python/pytest/ruff/kernel/df/uid
import-and-syntax.check.txt                本 worktree 模块导入与源码路径
r1_05_06_g4r_auth_suite.log/.meta.json     新 suite 26 passed（201.46s）@ f026036
r1_per_case_verbose.log/.meta.json         逐 case PASS 名称（-v）
r1_07_g4a_old_suite.log/.meta.json         旧 G4-A 223 passed（104.59s）@ f026036
r1_07_a12_determinism_30.log/.meta.json    a12 并发 30/30 passed @ f026036
r1_07_a12_BEFORE_fix_30runs.log/.meta.json 修复前基线 23 passed / 7 failed @ 3e7afee
r1_08_independent_probe.log/.meta.json     探针 50 轮 PASS（100 distinct PIDs）
r1_08_independent_probe_cross_epoch.log/.meta.json 探针跨 epoch 25 轮 PASS
r1_ruff.log/.meta.json                     ruff 0 changed files findings
```
