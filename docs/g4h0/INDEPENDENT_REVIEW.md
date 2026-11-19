# G4-H0 独立审查报告（A4 / A-08）

- **报告 ID**：`G4H0-INDEPENDENT-REVIEW-v1`
- **Reviewer**：`a-reviewer`（独立 Agent，Team member；**未参与**本轮任何实现、证据生成或文档撰写）
- **独立性声明**：本报告的全部结论来自 Reviewer 自己的命令、原始字节与原始日志；**未采信**
  Owner/Implementer 的 PASS 文字，未修改任何实现代码、冻结 docs/Packet/矩阵、主工作树或其它
  worktree，未执行 `push`/`merge`，未使用真实 Key、未做真实 Provider 调用。本报告不构成任何部署、
  授权或“已通过”凭据。
- **审查时间（UTC）**：`2026-11-19T18:16Z` 起（时间盒 30–40 分钟；未完成项在文末明确标
  `UNVERIFIED`/`NOT_RUN`）
- **审查对象（冻结）**：
  - base：`3e7afee077845a071cd364e93ab209cac20b2d5f`（主工作树 HEAD，clean）
  - frozen impl：`813e6a680399ba245bd0e76296e1212118a83460`
    （`merge(g4h0): A0-A3 wave — baseline, risk disposition, provider research, deployment runbook, P2 fixes (no-key)`，
    43 files，`+7703/-35`）
  - review 工作树：`/root/Autonomous Teacher/worktrees/m0-g4h0-review`，分支 `work/m0-g4h0-review`，
    HEAD 审查开始时 = 冻结 SHA；审查产物提交在本分支（基于冻结 SHA 之上，不合并、不推送）
  - 只读参考（观察值）：base worktree `.../m0-g4h0-base` @ `3e7afee`（clean，只读复用）；
    集成 worktree `.../m0-g4h0` 审查期间已前进到 `bb35a013d0aa62f29b77dc6db6733aa72052e3e3`
    （`git merge-base --is-ancestor 813e6a6 bb35a01` = YES；`artifacts/g4h0/packet-v2` 未变，
    mtime 仍为 `2026-11-19 17:40:16Z`）
  - 只读 Packet：v1 = 主工作树 gitignored
    `artifacts/review-packet-g4f-e7d92967ec0ece80de4a1a3705f637e8eb9bde99`（**未改写**）；
    v2 = 集成 worktree gitignored `artifacts/g4h0/packet-v2`
- **运行环境**：`/root/Autonomous Teacher/.venv/bin/python` = Python 3.11.15；pytest 9.2.0；
  ruff 0.17.5；`pythonpath=src`；已确认 `PYTHONPATH=src python -c "import autoteacher_m0"` 指向
  **本 review worktree** 的 `src/autoteacher_m0/__init__.py`。原始环境记录：
  `docs/g4h0/review-evidence/environment.log`。

---

## 0. 最高裁定

> # `PASS_FOR_G4H0_READINESS_NO_KEY_SCOPE`
>
> **仅限“G4-H0 无 Key 准入准备/证据就绪”范围。** 本裁定意味着：冻结实现 P2-03 修复经独立复验
> 成立、变更范围无安全语义放松、LiveGate 仍恒 `BLOCKED`、v1 Packet 未改写且 v2 包自校验一致、
> A-03/A-04/A-07/A-08 的证据可由 Reviewer 独立复现。
>
> **本裁定明确不表示、且禁止据此宣称**：`E5_PRELIVE_FULL PASS` / `E5-P04 PASS` / G4-H1（正式受信
> 部署）已部署 / H-01/H-02 已完成 / G5 已获批 / G6 GO / `M0 GO` / Live 可运行。这些状态保持：
> `LiveGate=BLOCKED`、`G4-H=NOT_AUTHORIZED`、`G5=BLOCKED`、`G6=NOT_RUN`、`M0=DECISION_PENDING`、
> `E5_PRELIVE_FULL=BLOCKED_PENDING_HUMAN_DEPLOYMENT`。
>
> **STOP**：立即停止，等待维护者独立选择风险处置（见 `docs/g4h0/HUMAN_DECISIONS.md`）、正式受信
> 部署与单次 G5 授权；Agent 不代签、不部署、不注入 Key。

**P0/P1**：本次独立审查 **0 个 P0、0 个 P1**（未发现安全语义放松、双消费、Key/网络、冻结改写）。
**P2**：4 条（1 条 high：`F-01` g4_h0 新测试时序缺陷；3 条 low/nit：`F-02` 目录项未 fsync、
`F-03` Runbook 与 P2-03 修复口径不一致、`F-04`/`F-05` 加固 nit）。详见 §7。

---

## 1. 变更范围 / 冻结保护审计（Case `R-C01`）

原始命令与输出：`docs/g4h0/review-evidence/diff_scope.log`。

| 检查项 | 实测 | 结论 |
|---|---|---|
| `git diff --name-status 3e7afee..813e6a6` | 43 files：**A=39 / M=4**，无删除；`+7703/-35` | 与冻结声明一致 |
| 受保护文件零 diff | `gates.py`、`dsh_adapter.py`、`cli.py`、`scripts/run_live.sh`、`tests/integration/g4_a/`（含旧 a12 测试）→ `git diff --stat` **输出为空** | PASS |
| 冻结 docs/Packet/矩阵零 diff | `REVIEW_G4F_INDEPENDENT.md`、`M0_G4F_REVIEW_ERRATA.md`、`...Closeout_Test_Evidence_Matrix_v1.0.csv` 等 → 空 diff | PASS |
| `src/` 改动面 | 仅 `security/authorization.py`（+153/-32）× 1 语义重写 + `bridge/controller.py`（+86 行）| PASS；无安全语义放松（§3/§4） |
| 新增文件可解释 | `docs/g4h0/` 13 md + 20 evidence（13 md + 20 evidence = 33 A）→ 本线文档/证据；`scripts/g4h0/{no_key_probes,p2_03_stress}.py`；`tests/integration/g4_h0/{conftest,test_p2_03_concurrent_consume}.py`；`tests/integration/g4_f5/test_f5_{pre_send_timeout_observation,recovery_reason}.py`；2 个 M 测试支撑文件（`g4f5_support.py` 仅加可选 `dispatch_journal` 参数；`tests/security/test_scan_git_secrets.py` 删 1 行未使用变量）| PASS（逐类解释见下） |
| 主工作树 clean | `git -C /root/Autonomous\ Teacher status --porcelain -uall` → 0 行 | PASS |
| base worktree 只读复用 | 30 次 a12 复现期间 `status --porcelain -uall` → 0 行（`-p no:cacheprovider` + `PYTHONDONTWRITEBYTECODE=1`）| PASS |
| 受保护文件字节身份 | `sha256sum` = `3ed08634…`(gates.py) / `88891149…`(dsh_adapter.py) / `31555386…`(cli.py) / `a8a2753f…`(run_live.sh)，与 `docs/g4h0/BASELINE.md` §1.3 及 `REVIEW_G4F_INDEPENDENT.md` §2.1 记录一致 | PASS |
| 新增 `src/` 行静态扫描 | 无 `requests/httpx/aiohttp/urllib/socket/openai/anthropic/deepseek_harness/http.client`；无 `os.environ/getenv/dotenv`；无 Key/凭据模式 | PASS（`secret_static_scan.log`） |

**新增文件逐类说明**（Reviewer 判定均可解释、均属本轮 A 线交付面）：
- `docs/g4h0/*.md`：A0 基线、A1 风险处置、A2 Provider 研究、A3 部署 Runbook/信任边界/E5 清单、
  P2 修复报告、No-Key 证据、人类签核模板（均声明“非授权/非部署证据”）。
- `docs/g4h0/evidence/*`：上述文档的原始日志/JSON/sha256 清单（文本；无二进制、无 Key）。
- `scripts/g4h0/no_key_probes.py`：A-07 本地负例探针（纯本地、无网络）。
- `scripts/g4h0/p2_03_stress.py`：P2-03 双进程压测（TEST_ONLY 合成签名 fixture，`/tmp` 临时目录）。
- `tests/integration/g4_h0/`：P2-03 原子发布定向回归（14 项，TEST_ONLY；含 autouse socket guard）。
- `tests/integration/g4_f5/test_f5_{pre_send_timeout_observation,recovery_reason}.py`：P2-05 观测 / P2-06 reason 保留回归。
- M `tests/integration/g4_f5/g4f5_support.py`：仅新增可选 `dispatch_journal=` 参数透传；既有调用默认行为不变。
- M `tests/security/test_scan_git_secrets.py`：删除未被使用的 `material = _synthetic_material()` 一行（F841），
  检测逻辑/断言未改（`_positive_cases()` 自身仍调用 `_synthetic_material()`）。

---

## 2. P2-03（核心）：旧竞态独立复现 + 修复独立复验（Case `R-C02`/`R-C03`/`R-C04`）

### 2.1 修复前独立复现（base `3e7afee`，只读复用 base worktree）

命令（30 次 standalone，每次全新 pytest 进程）：

```bash
cd "/root/Autonomous Teacher/worktrees/m0-g4h0-base"
for i in $(seq 1 30); do PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 \
  "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/integration/g4_a/test_a12_replay_epoch.py::test_a12_concurrent_consumption_admits_exactly_one \
  -q -p no:cacheprovider 2>&1 | tail -2; done
```

**实测：27 passed / 3 failed**（ITER 18、19、24）。失败形态（另跑捕获完整 traceback，
`base_a12_failure_detail.log`，ITER 3 复现）：

```text
E   AssertionError: assert 'AUTHORIZATION_REPLAYED' in ('AUTHORIZATION_USE_RECORD_INVALID',)
```

即旧竞态在本机自然复现（错误码不稳定、fail-closed 不变、恰好一个 consume 成功）。
日志：`docs/g4h0/review-evidence/base_a12_loop30.log`、`base_a12_failure_detail.log`。

放大写窗口复现（Reviewer 自建 `/tmp/at-p203-before` = `git archive 3e7afee` 干净副本，
用冻结树 `scripts/g4h0/p2_03_stress.py`，`sys.path` 指向**base** 的 `src`；`module_path`
在 JSON 中可证）：

| 运行 | 代码 | 轮数 | loser 码分布 | 双消费 | 记录/权限/残留 |
|---|---|---|---|---:|---|
| natural | base `3e7afee` | 30 | `REPLAYED`×30（本机自然 0 复现）| 0 | 30 / 0600 / 0 |
| `--widen-write-ms 100` | base `3e7afee` | 30 | **`USE_RECORD_INVALID`×25**、`REPLAYED`×5 | 0 | 30 / 0600 / 0 |

日志：`p2_03_before_natural_reviewer.{log,json}`、`p2_03_before_widened_reviewer.{log,json}`。
结论：旧缺陷可独立复现（自然 3/30；放大窗口 25/30），并如实记录“自然压测 0/30”不夸大。

### 2.2 冻结修复后独立复验（review worktree @ `813e6a6`）

| 运行/命令 | 轮数 | 结果 |
|---|---|---|
| 旧 a12 standalone 循环（目录测试**未修改**）| 30 | **30/30 passed**（`impl_a12_loop30.log`）|
| `scripts/g4h0/p2_03_stress.py --rounds 40`（natural）| 40 | failure_count=0，loser `REPLAYED`×40，double_consume=0，record_count=40，record_modes=`["0o600"]`，residual=[] |
| 同上 `--widen-write-ms 100` | 40 | 同上（`REPLAYED`×40，0 双消费，0600，0 残留）|
| `pytest tests/integration/g4_a -q` | 全目录 | **223 passed**（`g4_a_suite.log`）|

日志：`p2_03_after_natural_reviewer.{log,json}`、`p2_03_after_widened_reviewer.{log,json}`、
`impl_a12_loop30.log`。两次 after JSON 的 `module_path` 均指向 review worktree
`src/autoteacher_m0/security/authorization.py`，非其它 worktree。

**契约复核项**：0 双消费 ✓；loser 全 `AUTHORIZATION_REPLAYED` ✓；use record JSON 完整
（`authorization_id` 匹配）✓；记录权限 0600 ✓；`*.use-record-tmp-*`/非记录文件残留 = 0 ✓；
`MAX_AUTHORIZATION_USES` 语义无回退（见 §2.3）✓。

### 2.3 `authorization.py` 原子发布实现独立审读（Reviewer 代码级结论）

实现要点（`_publish_use_record` / `_read_use_record` / `_read_use_record_settled`）：
1. 临时文件与记录**同目录**，`os.urandom(16)` 随机名，前缀 `.use-record-tmp-` 不可能与最终
   `<sha256>.json` 冲突；`O_WRONLY|O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC, 0o600`。
2. 循环写全 body → `fsync(fd)` → `os.link(temp, record_path)` **原子发布**；
   `link(2)` 不覆盖既有名字 ⇒ 至多一个 publisher 成功，恰好一次消费成立。
3. `FileExistsError` → loser 读记录并映射 `AUTHORIZATION_REPLAYED`/`AUTHORIZATION_EPOCH_MISMATCH`；
   非 EEXIST 的 `OSError` → 清理 temp、抛 `AUTHORIZATION_USE_LOG_WRITE_FAILED`
   （**授权未被消费**，fail-closed，可重试）。
4. `finally` 总清理临时名（成功/失败/EEXIST 均清理；清理失败不影响结果——temp 不是 use record）。
5. `_read_use_record` 改为 `O_RDONLY|O_NOFOLLOW|O_CLOEXEC` 单描述符 + `fstat` + 定长读取 +
   末尾 size 校验，杜绝 stat/read 间 symlink/类型替换；symlink/非普通文件/空/超限 → `INVALID`。
6. `_read_use_record_settled`：仅在 `AUTHORIZATION_USE_RECORD_INVALID` 时 **有界** 重试
   （20×10ms），用于旧版半写记录的 replay 分类；其它错误码/symlink/超界立即 fail-closed；
   重试**只影响错误码分类，不授予任何权限**。
7. `MAX_AUTHORIZATION_USES` 计数排除 `.use-record-tmp-*` ⇒ 崩溃残留 temp 不会污染容量/锁死授权；
   记录仍 0600、目录仍须仓库外/非 symlink/operator-owned/非 group-other 可写、symlink 记录仍 INVALID。
8. **未发现安全语义放松**：所有既有校验（签名/绑定/路由/工具/预算/时限/撤销/epoch）不变；
   记录发布失败不会“降级放行”；重试路径无授权副作用。

**可改进点（均非 H0 阻断，见 §7 `F-02`/`F-04`）**：发布后未 `fsync` 目录项（掉电持久性，旧语义同样
未做）；`_read_use_record` 未加 `O_NONBLOCK`（记录路径若被换成 FIFO 时读端可能阻塞，需可信目录写权限，
残余 DoS 类）；`_preserved_uncertain_reason` 反复恢复时 reason 追加可能触发 256 字符截断（仅证据文本）。

---

## 3. P2-04 / P2-05 / P2-06（Case `R-C05`/`R-C06`）

### 3.1 P2-04（ruff / F841）— PASS（独立复跑）
- `ruff check tests/security/` → **All checks passed!**（`ruff_security.log`，exit 0）。
- 全仓 `ruff check src tests scripts` → 5 errors，全部在**未改动的旧脚本**（`scripts/g3b|g3c|g4/build_packet*.py`）；
  同一命令在 `3e7afee` 干净副本上为 6 errors（`/tmp/at-base-ruff`），即本轮净减少 1 条（F841），无新增。
- 本轮改动/新增文件（`authorization.py`、`controller.py`、`g4_h0/`、`g4_f5/`、`tests/security/`、
  `scripts/g4h0/`）→ `ruff check` **All checks passed!**。
- 该修改仅删 1 行未使用变量，scanner 检测逻辑/断言零改动（`tests/security` 在合并回归中通过；
  `test_positive_detectors` 仍覆盖同一批正例）。

### 3.2 P2-05（dispatch-window 观测补丁）— PASS（代码级 + 测试）
- 观测记录只出现在 envelope deadline 分支（`_observe_envelope_deadline` 唯一调用点
  `controller.py:648`）；`dispatch_seq=None`、`observation_only=true`、
  `observation_phase="envelope_deadline_no_terminal_frame"`、`settled=false`；
  `reserved/dispatched` 仅由 `_CancelState` 两个观测标记赋值（`998`/`1101`）并仅在观测记录中读取
  （`433`/`434`），**不参与任何 allow/deny/预算/发送判断**；`_dispatch_seq` 自增点（`379`）不变，
  观测不消耗序号；观测调用包在独立 `try/except` 中，绝不掩盖真实 abort。
- 正常 worker 最终记录逻辑/字段不变（测试断言 observation+1 条正常记录、正常记录 `dispatch_seq=1`）。
- 新增 2 项测试通过（`tests/integration/g4_f5` 全目录 **17 passed**，`g4_f5_suite.log`）。
- 注：`dispatch-window.jsonl` 的唯一消费者是可信证据采集（`DispatchAudit` append-only），
  未发现按 `dispatch_seq` 强校验的下游解析器会把 observation 行当最终记录。

### 3.3 P2-06（recovery reason 保留）— PASS（代码级 + 测试）
- 新增 `_preserved_uncertain_reason(row, fallback)`：仅当行已是 `SETTLEMENT_UNCERTAIN` 且有非空
  reason 时保留原标签并追加 `|RECOVERY_EVIDENCE:<fallback>`（≤256 字符）；否则回退 fallback。
- 应用于 `reconcile_on_startup` 的 5 处“再次确认不确定”写入；Broker 终态 OK/FAILED 的
  `SETTLED`/`WORST_CASE_HELD` 路径完全不变 ⇒ 状态/held/known/不重发/不双结算语义不变（仅证据标签）。
- 新增 3 项测试通过（f5 17 passed 内含）；测试断言 reason 以原 `REVOKED_PRE_SEND:` 开头、
  含 `RUN_AUTHORIZATION_REVOKED`、含 `|RECOVERY_EVIDENCE:`、状态仍 `SETTLEMENT_UNCERTAIN`、
  held=reserved、Fake=0、Broker 1 PENDING。
- 残余 nit：重复恢复会继续追加证据标签并受 256 字符上限截断（`F-05`，仅可读性）。

---

## 4. A-07：无 Key / LiveGate 恒 BLOCKED 独立负例（Case `R-C07`）

- 独立运行冻结树探针：`PYTHONPATH=src python scripts/g4h0/no_key_probes.py` → **exit 0，
  `{"failed":0,"passed":22,"status":"PASS","total":22}`**，22/22 逐项 PASS
  （`no_key_probes_reviewer.log`，Reviewer 自己的运行，不引用 Owner 数字）。
- Reviewer 另做最小直连负例（不复用探针封装）：
  - `LiveGate().inspect()` → `status=BLOCKED`，reasons 含
    `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED`、`BASELINE_EVIDENCE_MISSING`、
    `ACTUAL_TOOL_REGISTRY_NOT_APPROVED`、`SESSION_LOG_UPLOAD_NOT_VERIFIED_DISABLED`、
    `LIVE_NOT_EXPLICITLY_REQUESTED`；`external_boundary_deployed=False`。
  - `LiveGate().require_live()` → 抛 `SecurityBlocked`，`code=SECURITY_BLOCKED`；对象无
    `authorize/approve/open/unlock` 入口。
  - `/bin/sh scripts/run_live.sh` → **exit 3**，stderr `BLOCKED SECURITY_BLOCKED: ...`，stdout 为空。
  - `python -m autoteacher_m0.cli smoke --live` → **exit 3**，stdout JSON
    `{"status":"BLOCKED","error_code":"SECURITY_BLOCKED","reason":"EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED; ..."}`；
    `smoke --mock` → exit 0（离线 mock 路径正常）。
  - env key-like 变量 **0**；仓库无 `.env`（仅文档性 `.env.example`）；`src/` 无新增 env 解锁/凭据读取；
    新增 `src/` 行无网络/Provider import；`git diff` 无 `sk-*/PEM/AKIA` 模式（0 命中）。
  - `cli.py`/`run_live.sh`/`gates.py`/`dsh_adapter.py` 相对 `3e7afee` 逐字节相同。
  - 原始日志：`run_live_direct.log`、`cli_smoke_live_direct.log`、`cli_smoke_mock_direct.log`、
    `livegate_direct_probe.log`、`secret_static_scan.log`。
- **A-07 判定：PASS（本机无 Key 范围）**；真实人类授权边界/Key Broker/受信 Egress/Watchdog
  部署仍 **NOT DEPLOYED = BLOCKED（HUMAN）**，不是 PASS 范围。

---

## 5. Packet v1 / v2 与文档一致性（Case `R-C08`/`R-C09`）

Reviewer 自建只读校验脚本：`scripts/g4h0-review/verify_packet_integrity.py`
（按冻结 builder 的 tree 方法：对 `hashes.sha256` 中 172 个 payload 条目重算
`sha256(sorted("<sha256>  <relpath>\n"))`，manifest 单列）。原始输出
`docs/g4h0/review-evidence/packet_v1_v2_verify_reviewer.log`。

| 项 | v1（主工作树，未改写）| v2（集成 worktree，重建包）|
|---|---|---|
| 文件 / 符号链接 | **177 / 0** | **175 / 0** |
| `sha256sum -c hashes.sha256` | **173/173 OK**（Reviewer 亲自执行）| **173/173 OK** |
| hashes 条目 / payload 哈希条目 / manifest `files.count` | 173 / 172 / 172 | 173 / 172 / 172 |
| 逐文件 sha256 复算 mismatches | **0** | **0** |
| payload tree（剔除 manifest）| `e464b9b1…` = manifest 值 | `ffae8b3b…` = manifest 值 |
| sidecar（`-shm/-wal/-journal`）| **2 个**：`f4/sqlite-readonly/resume-attempts.sqlite3-{shm,wal}` | **0** |
| 全量 tree（含 sidecar）| `111c1361…` ≠ manifest（**P2-01 漂移**）| n/a |
| 剔除 2 sidecar 后 tree | `e464b9b1…` = manifest | n/a |
| unhashed payload | 仅 2 sidecar（post-build 出现）| 无 |
| mtime 证据 | manifest/hashes/report = `15:09:08Z`；sidecar = `15:11:07Z`（晚于构建，证明 v1 未被重写）| manifest/hashes = `17:40:16Z` |

结论：**v1 未改写**（字节/哈希/目录项 mtime 均与冻结记录一致；漂移仅由 2 个 post-build SQLite
sidecar 造成，属 P2-01 已知披露）；**v2 完整可复核**（`ffae8b3b…` 与 manifest 一致、0 sidecar、
173/173）。本报告不对 P2-01 做“修复完成”之外的主张：v2 是**新版本包**，v1 保持不可变。

**文档一致性抽查**（独立机器复算，`docs_baseline_crosscheck.log`）：
- `docs/g4h0/BASELINE.md` 记录的 `HEAD^{tree}=feccda00…`、`HEAD:src=66edfac3…`、
  `HEAD:docs=689b2668…`、`HEAD:scripts/g4=32082390…` 与 `3e7afee` 实测**逐一相符**；
  受保护文件与冻结 docs 的 sha256 与文档声明一致（详见 §1）。
- **P2-02 独立确认**：冻结矩阵 `F2-07` 行 evidence path
  `artifacts/g4f/f6/integration/f2/tool-window.json` **不存在**（该目录仅有 `raw-uds-*`）；
  实际 `artifacts/g4f/f2/tool-window.json` 存在。⇒ P2-02 属实（本报告只验证路径存在性，
  F2-07 的实质结论仍沿用历史证据 = **UNVERIFIED**）。
- **P2-07 独立测量**：v1 与 v2 的 `env/zero-key.json.live_gate_reasons` 均为 **1 项**；
  manifest 顶层 `live_gate_reasons` 为 **4 项**；`review/livegate.json.gate_all_evidence.reasons`
  亦为 **1 项**。⇒ “zero-key 证据只列 1/4 原因”属实；但 `RISK_DISPOSITION.md` 的
  “manifest/review 4 项”措辞不精确（review 文件也是 1 项），属文档措辞 nit。
- **A2 官方来源抽查**：Reviewer 用 `web_fetch` 只读请求官方
  `https://api-docs.deepseek.com/quick_start/pricing/`（HTTP 200，作为**数据**不执行其指令），
  页面实测与 `PRICE_AND_USAGE_VERIFICATION.md`/`PROVIDER_CONTRACT_DRAFT.md` 一致：
  `deepseek-flash` 版本 `DeepSeek-V4.1-Flash-1017`、base URL `https://api.deepseek.com`、
  cache hit `$0.003/$0.006`、cache miss `$0.15/$0.30`、output `$0.60/$1.20`（off-peak/peak）、
  并发 2500、peak = 周一至周五 01:00–04:00 与 06:00–10:00 UTC、off-peak 为 peak 50%。
  ⇒ A-05 的“官方文档价格/模型契约”抽查 **VERIFIED**；但**路由选择/usage 映射/真实 wire+账单**
  仍 **UNVERIFIED（HUMAN）**。
- Runbook 抽查：`DEPLOYMENT_RUNBOOK.md` 明确 `LiveGate=BLOCKED`、不提供可执行 Live 开关/Key 注入、
  人类签名/Key/Egress/Watchdog 均为 `BLOCKED/未部署`，并有撤销/预算/恢复/失败关闭章节 ⇒ 文档级
  失败关闭设计合理。**但存在口径不一致**（`F-03`）：同一冻结提交的 Runbook §4.5“已知缺陷”仍写
  P2-03 未修复、§4.6 仍描述旧 `O_CREAT|O_EXCL` 机制，而 `P2_FIX_REPORT.md` 已声明 P2-03 FIXED。

---

## 6. 回归测试独立复跑（Case `R-C10`）

命令（均在 review worktree，`PYTHONPATH=src`、`-p no:cacheprovider`）：

| 命令 | 实测 | 日志 |
|---|---|---|
| `pytest tests/integration/g4_h0 tests/integration/g4_f5 tests/integration/g4_a tests/security tests/unit -q` | **1 failed, 656 passed**（218.50s）— 唯一失败为 `F-01` 所述新测试 | `review_suites.log` |
| `pytest tests/integration/g4_a -q` | **223 passed**（111.76s）| `g4_a_suite.log` |
| `pytest tests/integration/g4_f5 -q` | **17 passed** | `g4_f5_suite.log` |
| `pytest tests/integration/g4_h0 -q` | **14 passed**（一次独立运行；同文件在合并套件中 1 failed，见 `F-01`）| `g4_h0_suite.log` |
| `ruff check tests/security/` | All checks passed! | `ruff_security.log` |
| `pytest ...test_a12...` ×30 | 30/30 passed | `impl_a12_loop30.log` |
| `scripts/g4h0/p2_03_stress.py` natural/widened ×40 | 0 失败、0 双消费 | `p2_03_after_*_reviewer.*` |
| `scripts/g4h0/no_key_probes.py` | 22/22 PASS | `no_key_probes_reviewer.log` |

`tests/security`、`tests/unit` 已包含在合并套件内（无失败）；未单独拆分统计，如实记录。

---

## 7. 发现（P0/P1/P2）

### P0（阻断安全）：**0**
### P1（必须在 H1/发布前修复）：**0**

> 未发现安全语义放松、双消费、Key/网络、冻结改写、LiveGate 开启。P2-03 的安全契约
> （恰好一次、fail-closed、0 双消费）经独立压力复验成立。

### P2-01（high）· `F-01` — 新增 g4_h0 测试存在时序缺陷，`tests/integration/g4_h0` 非确定性
- **文件**：`tests/integration/g4_h0/test_p2_03_concurrent_consume.py::test_retry_bound_stays_fail_closed_for_a_late_publisher`。
- **实测**（Reviewer 多次独立运行，日志 `review_suites.log`、`flaky_retry_test_full.log`、
  `flaky_test_rate.log`、`probe_retry_bound_timing.log`）：
  - 合并套件：**1 failed, 656 passed**，断言 `('AUTHORIZATION_REPLAYED',) == ('AUTHORIZATION_USE_RECORD_INVALID',)` 失败；
  - 仅该用例单独循环 10 次：**0 passed / 10 failed**（同断言）；
  - `g4_h0` 全目录单独运行一次：**14 passed**；`g4_f5`/`g4_a`/a12 压测全部通过。
- **根因（Reviewer 自建探针测定，非猜测）**：该用例用固定 `time.sleep(0.3)` 的 “late writer”
  模拟旧版半写发布者，并期望 reader 的有界重试先结束（`elapsed < 0.3`、reason=INVALID）。
  但本机 `consume_execution_authorization()` 基线耗时（纯 Python Ed25519 等离线校验）实测
  **332–337 ms**（3 次基线；`probe_retry_bound_timing.log`），已超过 300 ms；于是 writer 在 reader
  读记录前写完 body ⇒ reader 读到完整记录返回 `REPLAYED`，用例失败。能否通过取决于宿主 CPU 频率
  （目录整跑时 CPU 升频可使基线 <300 ms）⇒ **非确定性、边界零余量**。
- **影响**：不改变安全结论（两种结果都是 fail-closed 拒绝、0 双消费）；但 `P2_FIX_REPORT` 的
  “`pytest tests/integration/g4_h0` = 14 passed” **在本机不可稳定复现**，g4_h0 作为 H0 证据套件的
  绿色状态不可依赖。
- **最小修复建议（不代改）**：把 late writer 延迟改为显著大于基线（如 2.0 s）并把断言改为
  `elapsed < 1.0`；或用 monkeypatch 测量/固定基线耗时后再延迟写入；或改为断言“重试次数有界”
  而非挂钟时间。修复后需重跑 g4_h0 全目录 ≥10 次确认稳定。
- **处置**：列入 `HUMAN_DECISIONS.md`（HD-10），建议 Lead 在冻结前决定“接受测试缺陷 + 以独立压力证据
  替代”还是“出新小补丁修复测试”。

### P2-02（low）· `F-02` — use record 发布后未 fsync 目录项（掉电持久性）
- `_publish_use_record` 对记录 body `fsync(fd)` 后 `os.link` 发布，但**未 fsync 父目录**；
  `P2_FIX_REPORT` §7 已自认“与旧语义一致、不在本修复范围”。
- **影响**：正常运行时无影响；掉电/崩溃后目录项可能未持久化，已返回成功的 consume 在重启后
  可能允许同一授权再次消费（历史语义相同，非本轮回归）。无 Key H0 无影响；**G4-H1 前**建议
  `fsync` 目录或在人类签收中明确接受。最小建议：link 成功后 `os.open(dir, O_RDONLY|O_DIRECTORY)`
  + `os.fsync`（失败按 fail-closed 或记录告警）。

### P2-03（low）· `F-03` — Runbook 与 P2-03 修复口径不一致
- `docs/g4h0/DEPLOYMENT_RUNBOOK.md` §4.5“已知缺陷”仍写 P2-03“未修复前不得把并发撤销/消费演练写成
  PASS”，§4.6 仍描述旧 `O_CREAT|O_EXCL` 落记录机制；而 `P2_FIX_REPORT.md` 声明 P2-03 FIXED
  且本报告独立复验成立。同一冻结提交内文档互相矛盾，维护者按 Runbook 签核/部署时会读到过时缺陷状态。
- **建议**：以 append-only errata / 下一版 Runbook 更新 P2-03 状态与机制描述（禁止原地改写冻结证据）。

### P2-04（nit）· `F-04` — `_read_use_record` 未加 `O_NONBLOCK`
- 若可信 use-log 目录（operator-owned、非 group/other 可写）内的记录名被替换为 FIFO，读端
  `os.open(O_RDONLY|O_NOFOLLOW)` 可能阻塞（DoS 类；旧实现 `stat+read_bytes` 同样会阻塞，非回归）。
  建议下个加固窗口加 `O_NONBLOCK` 并在 fstat 后按普通文件读取。

### P2-05（nit）· `F-05` — 重复 recovery 的 reason 追加/截断
- `_preserved_uncertain_reason` 在多次恢复时会重复追加 `|RECOVERY_EVIDENCE:` 并受 256 字符上限
  截断，可能截断最新证据文本；仅可读性，无状态/安全影响。建议记录完整证据到独立字段而非拼接 reason。

**另记录（不计 finding）**：`RISK_DISPOSITION.md` 的 P2-07 行称 “v1/v2 的 zero-key 与
manifest/review 4 项不一致”，实测 `review/livegate.json.gate_all_evidence.reasons` 也是 1 项
（仅 manifest 为 4 项）——措辞不精确，事实（1/4 原因）成立。

---

## 8. A-01..A-08 验收矩阵（Reviewer 独立状态）

| ID | 验收对象 | 独立状态 | 证据/说明 |
|---|---|---|---|
| A-01 | SHA/代码/Stage/依赖冻结身份 | **PARTIAL** | Git 身份、diff 面、受保护文件/冻结 docs 哈希、module path=本 worktree、主树 clean → 独立 VERIFIED；**Stage 重建/rootfs/deps canonical 哈希未复算 = NOT_RUN**（需容器/依赖环境），未写 PASS |
| A-02 | P2 与历史残余逐项 disposition | **PARTIAL** | `RISK_DISPOSITION.md` 存在、16 条 finding 均有建议且维护者决策栏全空；P2-02/03/07 独立复验属实，P2-01 v2 独立复验；P2-05/06 代码+测试复验；P2-04 ruff 复验。但 P2-02/08 的 F2/F6 实质证据未重跑 = UNVERIFIED；全部处置仍待人类签核 ⇒ PARTIAL |
| A-03 | 并发 consume 恰一次/失败码稳定 | **PASS** | 2.1/2.2：base 3/30 自然复现 + 25/30 放大复现；impl 40+40 轮 0 双消费、loser 全 REPLAYED、0600、0 残留；旧 a12 30/30。证据：`base_a12_*`、`p2_03_*_reviewer.*` |
| A-04 | 旧 Packet 不改写；新包完整性可复核 | **PASS** | v1 177/0/173 OK/tree=`e464b9b1`/sidecar 漂移仅 post-build 2 文件/mtime 未变；v2 175/0/173 OK/tree=`ffae8b3b`/0 sidecar。证据：`packet_v1_v2_verify_reviewer.log` |
| A-05 | 正式 Provider 契约不借 Synthetic 充数 | **PARTIAL** | 官方价格/模型/base URL/峰谷/并发经 web_fetch 抽查与文档一致（VERIFIED）；路由选择、usage 映射 v2、真实 wire/账单 = UNVERIFIED/HUMAN；文档自评 PARTIAL/PASS_FOR_RESEARCH_SCOPE，Reviewer 不升格 |
| A-06 | 签名/Key/Egress/预算/Watchdog Runbook | **PARTIAL** | Runbook/信任边界/E5 清单存在且文档级失败关闭设计合理（抽查）；真实信任根/Key Broker/Egress/Watchdog 部署 = BLOCKED（HUMAN，NOT_RUN）；另发现 `F-03` 口径不一致 |
| A-07 | LiveGate 恒 BLOCKED、0 真 Key/真 HTTP | **PASS** | 22/22 独立探针 + Reviewer 直连负例（inspect BLOCKED、require_live 抛 SECURITY_BLOCKED、run_live/CLI exit 3、0 key/env/.env、新增代码无网络/凭据、4 受保护文件字节相同）；真实部署仍 BLOCKED |
| A-08 | 独立 H0 Review，随后 STOP | **PASS** | 本报告 + `HUMAN_DECISIONS.md` + `scripts/g4h0-review/` + `docs/g4h0/review-evidence/`；固定 SHA `813e6a6`；STOP。**不代表 G4-H0 被批准** |

> 说明：`PASS` 仅指该验收项的**客观证据可由 Reviewer 独立复现**；A-01/A-02/A-05/A-06 的剩余部分
> 明确保留 `PARTIAL/UNVERIFIED/NOT_RUN`，不得引用为完成。

---

## 9. 环境限制与未复验项（诚实登记）

| 项 | 状态 | 原因 |
|---|---|---|
| OCI/Podman L2 容器用例、DSH Runtime、Session/TLS/wire | **NOT_RUN** | 需容器/DSH/真实运行时；本审查时间盒内未启动，且无 Key 范围不做真实调用 |
| 真实 Provider HTTP / 账单 / 价格快照人工签收 | **NOT_RUN / HUMAN** | 禁止真实 Key/付费调用；仅官方文档只读抽查 |
| rootfs/deps canonical 哈希、Stage 重建、packet v2 重新打包 | **NOT_RUN** | Reviewer 只做只读复算；未执行 builder/依赖环境 |
| F2/F6 L2 证据实质结论（P2-02/P2-08） | **UNVERIFIED** | 未重跑 F2/F6 容器证据；仅验证矩阵路径缺失属实 |
| 跨 UID/容器内并发 consume 竞争 | **NOT_RUN** | 本审查为同宿主 2 进程压测 + 线程测试；不改变契约结论 |
| `tests/integration/g4_b|g4_c|g4_d|f2|f3` 全量 | **NOT_RUN** | 时间盒内仅跑 g4_a/g4_f5/g4_h0/security/unit 合并集；未跑部分不声称通过 |
| E5-P04 / DSH 权威 merged registry | **UNVERIFIED** | 无权威导出，`E5_PRELIVE_FULL` 保持 BLOCKED |

---

## 10. 残余风险（Headline）

1. **g4_h0 绿色状态不可稳定复现**（`F-01`）：H0 证据引用该套件前必须先修复或由维护者明确签署
   “以独立压力证据替代该用例”；否则任何“14 passed”声明都可被 10/10 失败复跑推翻。
2. **崩溃持久性**（`F-02`）：use record 目录项未 fsync；H1/G5 前需处置。
3. **文档口径**（`F-03`）：Runbook 仍把 P2-03 当未修复/旧机制；人类签核前需 errata。
4. **证据包版本**：v1 完整但含 2 post-build sidecar 漂移；v2 自校验一致；**维护者必须明确接受哪一个
   作为 H1 依据**（`HUMAN_DECISIONS.md` HD-02），Reviewer 不替人类选择。
5. **人类专属边界全部未部署**：信任根、Key Broker、受信 Egress、Watchdog、独立人类授权全部
   `BLOCKED/NOT DEPLOYED`；`E5_PRELIVE_FULL`、G4-H1/H2、G5、G6、M0 GO 均未授权。

---

## 11. 证据索引（可复现）

`scripts/g4h0-review/`（Reviewer 自建探针/校验脚本）：
- `verify_packet_integrity.py` — v1/v2 Packet 只读复算（文件/哈希/tree/sidecar/mtime 语义）。
- `probe_retry_bound_timing.py` — `F-01` 基线耗时与 late-writer 场景测定（TEST_ONLY 合成 fixture）。

`docs/g4h0/review-evidence/`（原始文本日志/JSON，均来自 Reviewer 本人命令）：
- 范围/环境：`environment.log`、`diff_scope.log`、`docs_baseline_crosscheck.log`、`secret_static_scan.log`
- P2-03：`base_a12_loop30.log`、`base_a12_failure_detail.log`、`impl_a12_loop30.log`、
  `p2_03_before_{natural,widened}_reviewer.{log,json}`、`p2_03_after_{natural,widened}_reviewer.{log,json}`
- P2-04/05/06：`ruff_check.log`、`ruff_security.log`、`g4_f5_suite.log`（含 2+3 新测试）、`flaky_retry_test_full.log`、`flaky_test_rate.log`、`probe_retry_bound_timing.log`
- A-07：`no_key_probes_reviewer.log`、`run_live_direct.log`、`cli_smoke_live_direct.log`、
  `cli_smoke_mock_direct.log`、`livegate_direct_probe.log`
- Packet/回归：`packet_v1_v2_verify_reviewer.log`、`review_suites.log`、`g4_a_suite.log`、`g4_h0_suite.log`

> 所有证据为**本机、无 Key、无网络付费调用**的原始文本；未包含任何真实凭据。

---

## 12. STOP

本报告提交于 review 分支 `work/m0-g4h0-review`（基于冻结 SHA `813e6a6`，不合并、不推送）。
**STOP**：等待维护者在 `docs/g4h0/HUMAN_DECISIONS.md` 上逐项签核（风险处置、正式受信部署、
G5 单次授权、Registry/E5-P04、P2 逐项、Packet v1/v2、双路由冲突、`F-01..F-05` 处置）。
在维护者作出独立选择之前，不得部署、不得注入 Key、不得发起真实 Provider 调用、不得宣称
`E5_PRELIVE_FULL PASS` / G4-H1 已部署 / G5 已获批 / M0 GO。
