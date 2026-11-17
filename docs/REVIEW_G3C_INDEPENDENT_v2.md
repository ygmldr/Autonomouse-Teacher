# M0 G3-C 独立复核 v2（Reviewer #2，二次复核）

> **Reviewer 身份**：Autonomous Teacher M0 **独立 G3-C Reviewer #2**。未参与 G3-C 实现、证据生成、PR1 修复或 Packet 构建；未复用 Owner / v1 Reviewer 的结论文字作为本报告判定。本报告所有结论来自 Reviewer #2 自己的命令、探针、真实 DSH 复跑与只读对账。
>
> **复核窗口（UTC）**：2026-11-17T16:31Z – 2026-11-17T17:05Z。
> **输入身份**：Base `bb5bd0bf83e22130ed0d81c54f54a4673654cfe3`；G0 `e107e22d32ee0fd25c597a95ae447898f4a52a85`；v1 impl `e6fde1c`；**PR1 impl `b2f6af054555705192c4e1ae3019a68078764736`**；docs HEAD `751af360bce1824e6e7facc0a0f8578e6aa44596`。
> **Packet**：`artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/`（2017 files，`sha256sum -c` 2015/2015 OK）；v1 Packet `…-e6fde1c…` 冻结（1713/1713 OK）。
> **最终裁定**：**`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`**。
> **范围限制**：仅覆盖 G3-C 无 Key / Fake Provider / 固定 rootfs 的契约、恢复、取消、deadline、IPC 资源与增量流。**G3-D 16 行仍 NOT_RUN、`OS_TRUST_BOUNDARY=B0-02=BLOCKED`、无 Live/GO**；不签 G3-D/Live/G4/G5/M0 GO。
>
> 本报告只写 `docs/REVIEW_G3C_INDEPENDENT_v2.md` 与 `artifacts/reviewer-g3c-v2/`；未修改任何产品代码、测试、脚本、已有 docs/artifacts/Packet；未 commit、未 push。

---

## 0. 裁定摘要

| 项 | 判定 |
|---|---|
| v1 P1-1（真实 DSH 覆盖过度声明 / C1-01A） | **CLOSED** |
| v1 P1-2（双 Controller 冷启动 `database is locked`） | **CLOSED** |
| v1 P1-3（矩阵 25/53 路径不存在） | **CLOSED** |
| 新 P0（未授权/重复发送、假结算、丢保守账本、假成功 finish、绕过 Claim） | **0** |
| 新 P1 | **0** |
| P2（记录性，不阻断本裁定） | **5 项**，见 §3 |
| §8.3 五条 | 满足（逐条见 §9） |
| 结论 | **`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`** |

**独立性要点**：本轮的 20 轮 host 冷启动、5 轮固定 rootfs 冷启动、20 轮 journal 初始化竞争、5 个 crash 窗口、8 类恶意/负例探针、10 个真实 DSH worker 运行（+1 次 container reconcile）、6 组 DB/Receipt 对账与全部矩阵审计均由 Reviewer #2 自建脚本产生；未调用 Owner 测试函数，未把 Owner JSON 当作自己的结果。Owner 的 `concurrency-coldstart-*.json` 只用于事后比对数字。

---

## 1. R0 — 身份、完整性与环境

### 1.1 Git / Packet 身份（证据：`artifacts/reviewer-g3c-v2/r0-identity/identity.txt`）

| 检查 | 命令 | 结果 |
|---|---|---|
| HEAD | `git rev-parse HEAD` | `751af360bce1824e6e7facc0a0f8578e6aa44596` == manifest.docs_sha |
| impl | `git cat-file -t b2f6af0` | commit；父 `78be77c` |
| 实现 diff | `git diff --binary bb5bd0b..b2f6af0 \| sha256sum` | `d655ac8b2824862006f59ff5e350db579b4e00e458556b17c0ec50d26e9eedae` == manifest.diff_sha256 == `diff.patch` |
| docs diff | `git diff --binary bb5bd0b..751af36 \| sha256sum` | `2e8af18faa51e4f6d2f7e2054e6464514ffc489ab8876132fa3a688898d23fe4` == manifest.docs_diff_sha256 == `docs-diff.patch` |
| Packet 校验 | `sha256sum -c hashes.sha256` | **2015/2015 OK，0 FAILED** |
| 文件数 | `find … -type f` | 2017 == manifest.file_count；0 symlink |
| v1 Packet | `sha256sum -c`（v1 根） | **1713/1713 OK**（1715 files），未改 |
| v1 报告 | `sha256sum docs/REVIEW_G3C_INDEPENDENT.md` | `4744c61f1561c6f92634b29ef9a6a0f7ca82c4627aef31ba3d0163e4886d23b1`（339 行）；v2 Packet `review/` 内字节相同（`cmp`） |
| Errata | `sha256sum docs/M0_G3C_REVIEW_ERRATA.md` | `b263c7d8…`；与 Packet `review/REVIEW_ERRATA.md` 相同 |

### 1.2 环境 / LiveGate（证据：`r0-identity/env.txt`、`livegate-run.txt`、`canonical-pre.txt`、`canonical-post.txt`）

- 无 `.env`；`env` 中无 `DEEPSEEK_API_KEY`/`*_TOKEN`/`*_SECRET` 名字（只有 `no_proxy`）。
- `bash scripts/run_live.sh` → **exit 3**（`BLOCKED SECURITY_BLOCKED`）。
- `LiveGate().inspect(live_requested=True)` → `status=BLOCKED`，reasons 四项（授权边界/基线证据/工具注册/会话上传）。
- canonical（前后各一次）：
  - rootfs `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`
  - deps `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`
  - stage `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`
- `podman ps -a` 空；无残留 broker/fake/controller/DSH 进程。
- 说明：Reviewer 容器运行在 rootfs 内临时创建了空挂载点 `rv2/`、`evidence/`、`seed/`、`var/tmp`；运行后**只 rmdir 这些空目录**，rootfs 恢复 canonical（`canonical-post.txt` 记录了恢复前后两次 hash 与删除项）。未触碰 rootfs 既有文件。

### 1.3 Errata 内容核对

`docs/M0_G3C_REVIEW_ERRATA.md` 的关键事实经抽查一致：v1 报告 339 行/sha、v1 Packet 1713/1713、PR1 `b2f6af0` 3 files +662/−45、P1-2 Owner 20 轮 JSON 存在且 20/20、矩阵审计 25→0、D 行 hash 前后一致、v1 report 行号 221/225/232/238/259/280 与 v1 原文对得上、v1 Report 第 83 行与 Findings 第 61 行确为 P1-1 所指声明。未发现 errata 与 PR1 实际不符的陈述。

### 1.4 Packet 内证据与仓库 artifacts 的一致性

对 Packet 内 8 个关键证据文件做 `cmp`：`traces/echo-fixed/dsh-result.json`、`traces/tool-fixed/dsh-result.json`、`traces/stream-slow-fixed/dsh-result.json`、`traces/probe-replay/probe-result.json`、`evidence/concurrency-coldstart-20261117T161008Z.json`、`regression/pr1-g3c-junit.xml`、`pr1/traces/echo/dsh-result.json`、`pr1/traces/tool/dsh-result.json` —— **8/8 与仓库 `artifacts/g3c/` 字节相同**；Packet 内 docs 矩阵、工作矩阵、Report、Review Request、Findings、Errata、`matrix-path-audit-pr1.txt` 也与仓库同名文件 **逐字节相同**。Packet 内 sqlite 一律未在包内打开，只做 `sha256sum`；需要查询时复制到 `/tmp` 只读副本。

---

## 2. v1 P1 逐项判定

### 2.1 P1-1 — 真实 DSH 覆盖过度声明 → **CLOSED**

**独立方法**：解析 docs 矩阵 53 个 PASS 行，按 `db_or_receipt_path` 展开到磁盘，判定每个路径实际包含 `dsh-result.json` / `probe-result.json` / `reconcile-result.json` / junit/log；再与 `observed` 的声明类型比对（脚本 `r1-static/audit_matrix.py`，输出 `matrix-audit.json/txt`）。

**结果**：

| 实际证据类型 | 行数 | case |
|---|---:|---|
| real DSH（有 `dsh-result.json` + DSH 事件） | 19 | C1-02、C1-03A/C/E/F、C2-01A..D、C2-02A/B/C/F、C3-01D、C3-02C、C3-04A/B/C/E |
| real DSH summary（链接 4 个 DSH trace） | 1 | C-END-01（echo-fixed/tool-fixed/resume-first/resume-second） |
| raw-UDS probe（有 `probe-result.json`，无 DSH） | 6 | C1-01A、C1-04、C3-01B、C3-01C、C3-02A、C3-02B |
| container reconcile（有 `reconcile-result.json`，无 DSH） | 2 | C2-02D、C2-02E |
| host pytest | 23 | C1-01B/C/D、C1-03B/D、C2-03A..E、C2-04、C3-01A/E、C3-02D/E、C3-03A..G、C3-04D |
| G0 / regression | 2 | G0-01、C-END-02 |
| **合计** | **53** | |

- **C1-01A 独立核验**：`artifacts/g3c/traces/probe-replay/` 只有 `argv.json`、`db-snapshot.json`、`probe-result.json`、`work/`、`work-snapshot.json`；`find … -name dsh-result.json` = **0**。`probe-result.json` 的 `first=[ack,chunk,chunk,finish]`、`replay=[ack,error]`、code `ATTEMPT_ALREADY_STARTED`，与 C1-04 共用该证据。
- **8 行更正核验**：C1-01A/C1-04/C3-01B/C3-01C/C3-02A/C3-02B 均无 `dsh-result.json`；C2-02D/E 只有 `reconcile-result.json`；C2-02A/B/C/F 的 crash 目录有 `dsh-result.json`、reconcile 目录只有 `reconcile-result.json`（混合证据，报告已如实拆分）。**没有任何非 DSH 行仍被写成 real DSH**。
- **反向检查**：不存在“声明为 raw-UDS/reconcile/host 却含 `dsh-result.json`”的行（`dsh_leaks=[]`）。C3-03F 是 host pytest + 容器 `probe-ipc-bounds` 的混合行，`observed` 明写 `host=PASS; container_probe=PASS`，不是 DSH 声明。
- **Docs 文本抽查**：Report 第 12/90/96/102/110/112/144/156/271/283 行、Findings §4 第 61–76 行均把 C1-01A/C1-04/C3-01B/C/C3-02A/B 标为 raw-UDS，把 C2-02D/E 标为 container reconcile，把 C1-01D/C2-04 标为 host-level；未发现残留的“C1-01A 是真实 DSH”表述。
- **结论**：P1-1 的“过度声明”已消除；这是标注更正，不是新增 replay，与 Errata 的限定一致。**CLOSED**。

### 2.2 P1-2 — 双 Controller 冷启动崩溃 → **CLOSED**

**代码独立核对**（`src/autoteacher_m0/bridge/attempts.py:38-180`、`controller.py:79-83,1516-1637`）：

1. `_initialize()` 在 `journal_mode=WAL` **之前**执行 `PRAGMA busy_timeout=250`（`attempts.py:121`），成功后恢复 10 s 运行时 timeout（`:126`）；WAL/DDL 对 `SQLITE_BUSY/SQLITE_LOCKED` 有界重试（默认 10 s / 50 ms），耗尽抛 `AttemptJournalUnavailable`（`:45-51`），**不再泄漏裸 `OperationalError`**。
2. `_is_retryable_lock_error` 只认 SQLite busy/locked（含 extended code 低字节 5/6 与文本），真实错误原样抛出（`:54-61`）。
3. 两初始化器竞争 `ADD COLUMN` 的 `duplicate column name` 在列已存在时视为成功（`:168-180`）。
4. `_acquire_controller_singleton()` 在 **stale socket unlink / admission / Broker / Fake / journal 之前**对 `<socket>.lock` 持 `flock(LOCK_EX|LOCK_NB)`，`O_NOFOLLOW`，进程生命周期持有；失败固定 stderr `CONTROLLER_SINGLETON_LOCKED` + exit 5（`controller.py:1516-1571`）。
5. journal 耗尽固定 `ATTEMPT_JOURNAL_UNAVAILABLE` + exit 4（`:1586-1592`），且 no socket bound；Admission replay 仍保持 reconcile 先于登记、exit 3（`:1599-1606`）。
6. 启动清理走 `finally` + `_close_quietly`，受控路径无 traceback；正常 SIGTERM 仍 exit 0。

**独立实测**（证据 `r2-probes/coldstart-host-20.json`、`coldstart-host-logs/`）：

- **host 20 轮**，每轮两个真实 Controller 进程 + 真实 socket/Broker/Fake/SQLite 同时冷启动：
  - 20/20 轮 **1 winner + 1 loser**；winner 分布 `proc1=11 / proc2=9`；
  - loser **全部 exit 5**，stderr 全部 `CONTROLLER_SINGLETON_LOCKED`，**traceback=0**；
  - 每轮 Fake counter=1、receipt 文件=1、Attempt=1 且 `SETTLED`、reservation=1 `OK`、claim=1 `COMPLETED`、admission=1；
  - 轮时长 377–422 ms（中位 399 ms）。
- **固定 rootfs 5 轮**（`r2-probes/rootfs-out/coldstart-rootfs-5.json`，uid 65534、只读 rootfs、`--network none`、当前 `src` overlay）：5/5 exit 5、0 traceback、Fake=1、SETTLED，203–206 ms。
- **journal 根因层 20 轮**（`r2-probes/journal-race.json`）：20/20 两进程同冷文件初始化均成功；最多 `init_attempts=2`（真实触发过一次重试）；**0 次 `OperationalError`**。
- **迁移竞争**：旧 schema 两进程同时初始化 → 双方成功、20 列齐全、`duplicate column` 被吸收。
- **耗尽路径**：真实 `BEGIN EXCLUSIVE` 持有者 → 子进程得到 `AttemptJournalUnavailable`（无 traceback）。
- **Controller exit 4 路径**：真实 Controller 在 journal 被独占锁定时 **exit 4**、stderr `ATTEMPT_JOURNAL_UNAVAILABLE`、**未绑定 socket、0 receipt**，10.38 s 后受控退出。
- **crash 恢复后 lock 可重取**：crash_probe 每轮 crash 后新进程都能重新拿锁并完成 reconcile（5/5）。

**边界**：P1-2 只覆盖“同 socket 路径第二 Controller 冷启动”；**不覆盖两个真实 DSH 客户端同 Claim**（worker 每进程自带 Controller/admission）。该残余未被 PR1 消除，Errata/Report 已如实限定；本报告不将其解释为已覆盖。**CLOSED**（针对 v1 P1-2 的问题本身）。

### 2.3 P1-3 — 矩阵证据索引 25/53 → **CLOSED**

**独立审计**（`r1-static/audit_matrix.py`）：

- 用 `git show 78be77c:docs/…csv` 重建 v1 矩阵，独立解析每个 PASS 行 `db_or_receipt_path`/`log_path` → **25 missing**，与 v1 报告及 Owner 审计的 25 一致（`matrix-audit.txt` 列出同样 25 个 case）。
- 当前 docs 矩阵与工作矩阵：**missing_paths=0**；所有 PASS 行 `command_argv` 非空、`log_path` 存在。
- **D 行 16 条**：按原始 CSV 行拼接的 sha256：
  - docs 矩阵：`db7b5fd92ff4d8d5343a9d9e5f170bf327a64a04ce55843577bf1be3ec36ec6e`（v1 与当前**相同**）；
  - 工作矩阵：`13510d161275164ed2ab8eb29ca2b791874a399d83c1a1fca39ad009ac0e37a9`（v1 Packet 副本与当前**相同**）。
  - 两个 hash 与 Owner `matrix-path-audit-pr1.txt` 记录逐字一致；docs-vs-work 的 hash 不同仅因 schema 列不同（docs 12 列 / work 11 列），不是 D 行内容漂移。
- **抽查**：C1-01A 现指向 `probe-replay/probe-result.json` + `db-snapshot.json`，argv 为完整 `podman run … probes_c3.py --probe replay`，log 存在；C-END-01 argv 含 echo/tool/resume-first/resume-second 四条命令，DB 指向 4 个 DSH trace；C2-04 `db_or_receipt_path=artifacts/g3c/evidence/junit-g3c.xml` 实际存在，该 junit 含 `test_c2_04a/b/c` 三个用例。
- **结论**：25→0 可独立复算，D 行未改，C2-04/C1-01A/C-END-01 索引正确。**CLOSED**。

---

## 3. Findings（P0/P1/P2）

### P0

**无。** 未发现：未授权发送、重复发送、Fake 已收却写 FREE/NOT_DISPATCHED、假成功 finish、绕过 Claim/Reservation、丢失保守账本。证据：§5 的 8 类探针、§6 的 9 次真实 DSH、§7 的 6 组对账。

### P1

**无。** v1 三个 P1 均 CLOSED；未发现新的语义/证据 P1。

### P2（记录性；不阻断本裁定，建议后续归档修正）

| ID | 问题 | 证据 | 影响 |
|---|---|---|---|
| P2-1 | **Packet `reproduce/README.md` R5 与 Review Request §2.3 的示例 DSH 命令只挂 `artifacts/g3c/stage` 到 `/probe`，而该 stage 的 `stage/src` 是 e6fde1c 时代源码（`attempts.py` sha `33017e75…`，无 `_initialize`）**。照抄命令会跑旧 Controller，无法复现 b2f6af0。 | 我用 stage-only 在 rootfs 跑同一 5 轮冷启动：**0/5**，loser exit 1，traceback 停在 `attempts.py:58 PRAGMA journal_mode=WAL`（`r2-probes/rootfs-stale-stage/`）；同一命令加当前 `src` overlay 后 **5/5**（`r2-probes/rootfs-out/`）。Owner 的 PR1 DSH trace 含 `bridge.sock.lock`（新代码指纹，旧 trace 无），说明其产物来自新代码批次（很可能通过 `pr1/src` overlay），**trace 本身不是旧代码产物**。 | 影响“按 Packet 复现”的可操作性，不影响已归档证据与产品语义；建议 Packet v3/repro 脚本显式 overlay `src` 或重建 stage。 |
| P2-2 | Report §8.1 的“guard-invalid 是 Controller 启动失败关闭（无 DSH）”不准确：实际 Controller exit 0、DSH 客户端启动、guard precheck 以 `RBG_GUARD_BOOT_INVALID` 失败关闭，admission 被消费，attempts/receipts=0。 | Owner `traces/guard-invalid`；我的 `rv2-guard-invalid` 复跑结果相同（`turn/end error RBG_GUARD_BOOT_INVALID`、0 attempts）。 | 表述精度问题；不构成 real-DSH 过度声明（反而是低报），不改变 guard 失败关闭语义。 |
| P2-3 | 证据索引计数陈旧：Report §13 写“75 目录；51 DSH + 12 reconcile + 6 raw-UDS”，磁盘实为 **77 目录、55 个 `dsh-result.json`**（新增 `pr1v2-echo/tool` 与 `pr1/traces/{echo,tool}` 四个 DSH 结果）；§12 只列“51 + pr1/traces 2”，漏计 pr1v2 两轮。 | `find artifacts/g3c -name dsh-result.json \| wc -l` = 55；`find traces -maxdepth 1 -type d` = 77。 | 计数低报，不是过度声明；建议更新索引。 |
| P2-4 | Findings §8 称“另 3×20 轮压力复跑同结果”，Packet 内无对应 JSON/日志文件可核。 | `find artifacts/g3c -name '*coldstart*'` 只有 2 个 JSON（15:32/16:10），均 20 轮。 | 不影响本轮（我有独立 20 轮）；该句不可复核，建议补证据或删除。 |
| P2-5 | 矩阵 `impl_sha` 统一写 `b2f6af0`，但多数 trace 实际由 `e6fde1c` 产生；C2-04 指向 105 用例的 `evidence/junit-g3c.xml`（13:47，e6fde1c 批次），而非 PR1 的 110 用例 junit。 | Errata §4.4 已披露批次差异；我的矩阵审计确认路径存在且含 c2_04。 | 已披露的追溯性限制；二次复核按 `argv.json`/`commands.jsonl` 区分批次，不把它当作 b2f6af0 新运行。 |

**未独立复跑/未验证项**（不作为 P1，但明确列出）：OCI full 的 773/2/1（我跑了 host full 773/2/1 与 rootfs 5 轮，未跑完整 OCI 套件）；Node adapter/Guard 9/9+19/19（只核对 Owner junit/TAP 与容器内冷启动）；G2 280（host full 内含）；DSH SIGTERM 终态（v1 P2 残余，未重跑）；双真实 DSH 同 Claim（未做，PR1 也不覆盖）；真实 Provider/Key/远端幂等/账单（范围外）。

---

## 4. R1 — 静态复验

### 4.1 PR1 diff 范围

`git show --stat b2f6af0`：仅 3 个文件（`attempts.py` +97/−?、`controller.py` +150/−?、新测试 +460）。静态 diff 只触及 `AttemptJournal` 初始化/DDL 与 `controller.main` 启动/清理；**未改动** `_prepare_checked`、`handle_envelope`、`_handle_payload_stream`、`begin_attempt`、`reconcile_on_startup`、cancel、streaming、Admission 逻辑。因此“修复只影响启动确定性、不削弱发送许可链”在字节层面成立。

### 4.2 发送许可链抽查（`controller.py:602-760`）

`_prepare_checked` → 同 call attempt/intent 查重 → `claim_request_identity`（durable identity）→ `calls += 1` → checkpoint → Broker `reserve` → `record_intent` → checkpoint → `boundary.claim_dispatch_for_request` → `mark_intent_claimed` → checkpoint → `begin_attempt` → checkpoint → `transport.dispatch` → Fake。无 legacy `claim_dispatch` 旁路；`grep claim_dispatch` 仅 1 处（`:677`）；self-auth 字段在 `handle_envelope` 入口被 `ADMISSION_SELF_AUTH_DENIED` 拒绝（我的 pre_send 探针复现）。

### 4.3 新退出码路径

- exit 5：lock 被占/锁路径不可安全打开（`O_NOFOLLOW`、非普通文件）→ 不启动 Broker/Fake、不碰 socket。
- exit 4：journal 10 s 有界重试耗尽 → 关闭已启动的 Broker/Fake、不绑定 socket。
- exit 3：reconcile 后 admission replay → 保持已恢复 Attempt，不重发。
- 三者 stderr 均为固定单行码，无 traceback；正常 SIGTERM exit 0。

### 4.4 Docs 修正准确性

已逐条核对 Report/Findings/Review Request 中的“真实 DSH”声明与实际 artifacts（见 §2.1）。`C1-01A` 在 Report 第 90/283 行、Findings 第 71 行、矩阵 observed 均为 raw-UDS；C1-04/C3-01B/C/C3-02A/B 为 raw-UDS；C2-02D/E 为 container reconcile；C1-01D/C2-04 为 host；C2-02A/B/C/F 明确拆成 crash（DSH）+ reconcile（container）。未发现把 raw-UDS/reconcile/host 合并成 real DSH 的段落。P2-2/P2-3 是表述/计数瑕疵，不构成过度声明。

---

## 5. R2 — 独立恶意/负例探针（Reviewer 自建）

工具：`r2-probes/probe_runner.py`、`crash_probe.py`、`journal_probe.py`、`coldstart_probe.py`、`ipc_probe.py`；原始 JSON/日志在同目录。

| # | 类别 | 场景 | 结果 |
|---|---|---|---|
| 1 | 无 Claim/伪造/篡改 | route mismatch、model mismatch、tool schema 篡改、self-auth `authorized`/`call_id`、maxTokens 2048/512、超大输入、unknown field（9 例） | 全部在 Reserve 前拒绝（ROUTE_MISMATCH/ADMISSION_SELF_AUTH_DENIED/BAD_TYPE/BUDGET_DENIED/UNKNOWN_FIELD）；Fake=0、attempts=0、reservations=0、identities=0 |
| 2 | 重放/幂等 | 同 call 同 payload 两个新 transport + 第三次 | 首轮 1 Fake/1 receipt；重放 `ATTEMPT_ALREADY_STARTED`；Fake 恒 1；attempt 1 且 SETTLED；reservation/claim 各 1 |
| 3 | Crash 窗口 | after_claim_before_attempt_start、after_attempt_start_before_fake_send、after_fake_receive_before_response、after_response_before_settlement、after_broker_settle_before_journal_mark（真实进程 exit 97 + 新进程 reconcile） | 5/5 无第二次 Fake；after_claim → 无 attempt、broker PENDING；after_attempt → `SETTLEMENT_UNCERTAIN`；其余 → `SETTLED` 且 broker OK；reconcile exit 3（admission replay）无 traceback；socket 清理 |
| 4 | Cancel | pre-send / during-Fake / 双流并发 / 错误签名（int transport、空 reason、positional） | pre-send：CANCELLED、Fake=0；during-Fake：CANCELLED、Fake=1、按 receipt `SETTLED`（cost 0.001022）；双流只取消一条，另一条 finish；错误签名均 ValueError/TypeError，未静默吞；unknown id 不发送 |
| 5 | Usage 负例 | no_usage、partial、invalid、multi、after_finish、conflict、eof、error（8 例） | 全部 finish(ERROR) 或无成功 finish；attempt `WORST_CASE_HELD`；broker FAILED；cost 非零（0.001022/0.001587）；Fake=1，无免费结算 |
| 6 | Streaming | `stream_slow`；首 chunk 到达 vs Fake exit；consumer 提前 close | 首 chunk epoch 与 Fake `first_chunk_flushed` 同 ms；Fake exit 晚 2005 ms（T1<T2）；2 chunks + finish；attempt SETTLED；close 0.081 s，Fake 子进程已死 |
| 7 | 资源/超时 | 真实 Broker SIGSTOP（挂起）；Fake `timeout`（receipt 后 35 s 睡眠）；BridgeServer 首帧/连接上限/超大帧/坏帧 | Broker：1 次请求、2.51 s `BROKER_TIMEOUT`、Fake=0、无 reservation；Fake stall：1.51 s `DEADLINE_EXCEEDED`、Fake=1 receipt、attempt `SETTLEMENT_UNCERTAIN`、broker PENDING；IPC：valid→ack/finish，300 KB 帧→`FRAME_TOO_LARGE`，空闲连接→`DEADLINE_EXCEEDED`，第 9 连接→`TOO_MANY_CONNECTIONS`，坏 JSON→错误且 Controller 未被调用 |
| 8 | Guard 缺失/坏配置 | 真实 DSH `--guard-invalid`、`--bad-admission`（R3） | guard-invalid：`RBG_GUARD_BOOT_INVALID` 失败关闭、0 attempt、0 receipt；bad-admission：controller exit 1、0 attempt、0 receipt、DSH `G3B_BRIDGE_CONNECT_FAILED` |

### 5.1 P1-2 20 轮统计（自建）

```
host 20/20: loser_exit={5}, loser_code={CONTROLLER_SINGLETON_LOCKED},
            tracebacks=0, fake_counters={1}, attempt_states={SETTLED},
            winner proc1=11 / proc2=9, duration 377-422ms (median 399)
rootfs 5/5: loser_exit={5}, tracebacks=0, fake={1}, SETTLED, 203-206ms
journal 20/20: both processes OK, max init_attempts=2, OperationalError=0
migration race: OK; exhausted -> AttemptJournalUnavailable;
controller exit4: exit=4, stderr=ATTEMPT_JOURNAL_UNAVAILABLE, socket=no, receipts=0
```

### 5.2 关键 P2-1 证据（stage 源码批次）

同一 rootfs 5 轮冷启动：

- 仅挂 frozen stage（`/probe/src` = e6fde1c）：**0/5**；loser exit 1，traceback `attempts.py:58 PRAGMA journal_mode=WAL: database is locked`；loser 另有一次 exit 3。
- 加当前 `src` overlay：**5/5** exit 5，0 traceback。

该对照直接证明：Packet 的 frozen stage 不含 b2f6af0 的修复；照抄 Packet R5 命令会测试旧代码。Owner 的 PR1 DSH trace 含 `bridge.sock.lock`（PR1 singleton 代码创建），旧 `echo-fixed` 无此文件；这说明 PR1 冒烟产物来自含 singleton 锁的代码批次（很可能通过 `pr1/src` overlay），不是旧 trace 冒充。

---

## 6. R3 — 真实 DSH 复跑（固定 rootfs，无 Key）

**方法**：固定 rootfs `25491e45…` + deps `e07729d7…`；`--network none --http-proxy=false --unsetenv-all`；uid 65534、只读 rootfs、cap-drop ALL、no-new-privileges；`/probe` = frozen stage，`/probe/src` = 当前 `b2f6af0` 源码 overlay（理由见 P2-1）；Fake Provider；每个 case 独立 evidence 目录。证据：`r3-dsh/traces/*/dsh-result.json`、`run.log`、`r3-dsh/r3-runs.log`。

| Case | 结果 |
|---|---|
| Echo `rv2-echo` | controller exit 0、`final=ok`、`finish=completed`、1 attempt SETTLED、1 reservation OK、1 claim COMPLETED、1 receipt、Fake=1；DSH usage `{input 11, cacheRead 2, output 5, total 18}` == receipt |
| Tool 两轮 `rv2-tool` | 2 attempts（step 0/1）均 SETTLED；2 reservations OK、2 claims COMPLETED、2 receipts；2 assistant messages、1 tool result；Fake=2 |
| Resume `rv2-resume-first/second` | 第二进程 `mode=resume`、同 session、**turn=2**；2 attempts SETTLED；Fake=2（1+1），旧 attempt 未重发 |
| Streaming `rv2-stream` | T1（DSH 首 chunk `time0`）= `1794934608600`，T2（Fake `exit_after_finish`）= `1794934610599`，**T1<T2，lead 1999 ms**；controller exit 0、SETTLED |
| Crash `rv2-crash` | controller exit 97、attempt `RESPONSE_OBSERVED`、broker PENDING、Fake=1 |
| Reconcile `rv2-reconcile` | 新进程把同一 attempt 恢复为 `SETTLED`、broker OK、Fake 仍=1（无重发）、新增 admission 1 条 |
| Guard on `rv2-guard-on` | `guard=true`、completed、1 attempt SETTLED |
| Guard off `rv2-guard-off` | `guard=false`、completed、1 attempt SETTLED |
| Guard invalid `rv2-guard-invalid` | turn error `RBG_GUARD_BOOT_INVALID`、0 attempt、0 receipt、Fake=0 |
| Bad admission `rv2-bad-admission` | controller exit 1、DSH `G3B_BRIDGE_CONNECT_FAILED`、0 attempt、0 receipt |

所有 `dsh-result.json` 的 `env.key_env=[]`、`unexpected_env=[]`、`readonly_rootfs=true`、`uid=65534`；无真实模型/网络调用。

---

## 7. R4 — DB / Receipt 对账

**方法**：`r4-crosscheck/r4_crosscheck.py` 把 sqlite 复制到 `/tmp` 后只读查询（不在 Packet 副本上打开）；对 Echo、Tool、crash-before、crash-after-reconcile、cancel-during-Fake、usage-negative 六组做全链核对。

| Dataset | attempt | reservation | claim | receipt | 结论 |
|---|---|---|---|---|---|
| echo | SETTLED | OK / 0.001022 | COMPLETED | 1，raw_sha=payload_digest，nonce 匹配 | 全链一致 |
| tool | SETTLED ×2 | OK ×2 | COMPLETED ×2 | 2，逐 call 独立 | 全链一致 |
| crash_before | RESPONSE_OBSERVED | PENDING / 0.002677 | CLAIMED | 1 | 崩溃诚实标 PENDING，保守成本非零 |
| crash_after_reconcile | SETTLED | OK / 0.001022 | COMPLETED | 1（同一） | 只 settle 一次，Fake 不增 |
| cancel_during_fake | SETTLED | OK / 0.001022 | COMPLETED | 1 | 按 receipt 保守结算 |
| usage_multi_rejected | WORST_CASE_HELD | FAILED / 0.001022 | COMPLETED | 1 | 无假成功，成本非零 |

对每组均验证：

- `usage_digest == sha256(canonical(usage))`；`observation_digest == sha256(canonical(observation))`；
- `payload_digest == prepared.receipt.raw_sha256 == broker claim.request_digest`；`raw_length` 与 payload_length/receipt 文件一致；
- receipt 文件 `rcpt-<nonce>.json` 的 nonce/receipt_id/raw_sha256/usage 与 journal 文档一致；
- broker 消息：每 reservation 恰 1 次 reserve、1 次 claim、至多 1 次 settle/fail；`budget_dispatch_claims` 每 call 1 条；**无重复 settle**；
- Fake counter == receipt 文件数；
- 非 SETTLED 行保留非零 cost（0.001022/0.002677）。

**结论**：call→reservation→claim→attempt→receipt→observation→broker→cost 一一映射；无二次 settle、无免费成功、无低计。

---

## 8. 回归与环境

| 检查 | 结果 |
|---|---|
| host full（Reviewer 实跑，`logs/host-full.log`） | **773 passed / 2 failed / 1 skipped**（131.03 s，776 collected）——2 个失败正是文档化的宿主环境限制（可写 config、硬编码 `/project`），与 Owner 计数一致 |
| 独立 coldstart 测试收集 | `test_c3_05` 5 个用例（1×20 轮 + 4 个 journal/exit 用例） |
| Ruff | 未单独重跑（PR1 日志 `All checks passed` 为 Owner 证据；不纳入我的结论） |
| rootfs/deps/stage | 前后 canonical（§1.2）；`podman ps -a` 空；无残留进程 |
| 0-Key/Live | 无 Key env、无 `.env`、`run_live.sh` exit 3、LiveGate BLOCKED；所有容器 `--network none` |

---

## 9. §8.3 PASS 规则逐条

1. **G3-B P1（Receipt/Settlement、Cancel）闭环 + 协议错误语义/Finish/Admission 限额一致**：满足。我的 replay/crash/cancel/usage 探针与 R4 对账复现了 SETTLED 幂等、`ATTEMPT_ALREADY_STARTED`、`CANCELLED`、`WORST_CASE_HELD`、`ADMISSION_SELF_AUTH_DENIED`、`BUDGET_DENIED`；`_terminal_events` 只发 error finish（usage 负例 8/8 无成功 finish）。
2. **Usage 透传、Broker Deadline、首帧 Deadline、资源上界、增量输出均有独立动态证据**：满足。usage（§5 #5）、broker hang `BROKER_TIMEOUT`（§5 #7）、fake stall `DEADLINE_EXCEEDED`（§5 #7）、首帧/连接上限/超大帧（§5 #7 IPC）、streaming T1<T2（§5 #6 + §6 DSH 1999 ms）均为我自建运行。
3. **无 Fake 已收却写 FREE、无自动重试**：满足。crash 5 窗口 + R4 显示：有 receipt 即按 receipt 结算/失败关闭，无 receipt 才 `SETTLEMENT_UNCERTAIN`；Fake counter 从不因 reconcile 增加；非 SETTLED 保留非零 cost。
4. **DSH Echo/Tool/Resume 通过 + Broker/Attempt/Receipt 关联正确 + 全量回归无意外失败**：满足。§6 的 DSH 运行 + §7 对账；host full 773/2/1，2 个失败为既有环境限制（与 PR1 前后一致，不是产品断言回归）。
5. **独立 Reviewer 复核 Commit 与关键测试并给出裁定**：满足。本报告即独立复核；身份、命令、UTC、exit、证据路径均在 §1–§7 与 `artifacts/reviewer-g3c-v2/`。

**结论**：在无 Key/Fake Provider/固定 rootfs 范围内，G3-C 契约、恢复、取消、deadline、资源与增量流证据满足 §8.3；因此判 **`PASS_FOR_G3C_NO_KEY_CONTRACT_RECOVERY_SCOPE`**。

---

## 10. 明确不主张

- 不主张 G3-D/OS 信任边界通过：16 行仍 `NOT_RUN`，`B0-02=BLOCKED`；没有候选攻击、不同 OS 主体、namespace/kernel deny 证据。
- 不主张 Live/GO、真实 Provider/Key/模型/外网、远端 exactly-once、账单准确、限流/远端超时。
- 不主张两个真实 DSH 客户端同 Claim；P1-2 只覆盖同 socket 的 Controller/socket/Broker/Fake/SQLite 冷启动。
- 不主张 host full 的 2 个环境失败已修复；不掩盖 OCI 未由我完整复跑、Node/G2 只做交叉核对。
- 不主张 SRC-12/P2-4/断连 cancel/SIGTERM 终态等 P2 残余已消除。
- 不主张 Owner/v1 的文字被本报告改写；v1 报告字节保持不变。

---

## 11. 复现与证据索引

**证据根**：`artifacts/reviewer-g3c-v2/`

| 内容 | 路径 |
|---|---|
| 运行索引 | `RUN_INDEX.md` |
| R0 身份/环境 | `r0-identity/identity.txt`、`packet-counts.txt`、`v1-invariance.txt`、`env.txt`、`livegate-run.txt`、`canonical-pre.txt`、`canonical-post.txt` |
| R1 静态/矩阵 | `r1-static/audit_matrix.py`、`matrix-audit.json`、`matrix-audit.txt` |
| R2 探针 | `r2-probes/probe_runner.py`、`crash_probe.py`、`journal_probe.py`、`coldstart_probe.py`、`ipc_probe.py`、`*.json`、`coldstart-host-logs/`、`rootfs-out/`、`rootfs-stale-stage/` |
| R3 DSH | `r3-dsh/traces/rv2-*/`、`r3-dsh/r3-runs.log`、`r3-dsh/src/`（当前源码副本） |
| R4 对账 | `r4-crosscheck/r4_crosscheck.py`、`r4-crosscheck.json` |
| 回归日志 | `logs/host-full.log` |

**关键复现命令**（均在本仓库根执行；host Python 必须 `-B`）：

```bash
export PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c-v2/r1-static/audit_matrix.py \
  --repo . --v1-matrix /tmp/matrix-v1.csv \
  --docs-matrix docs/Autonomous_Teacher_M0_G3C_G3D_Test_Evidence_Matrix_v1.0.csv \
  --work-matrix artifacts/g3c/evidence/evidence-matrix-g3c.csv \
  --out artifacts/reviewer-g3c-v2/r1-static
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c-v2/r2-probes/coldstart_probe.py \
  --out artifacts/reviewer-g3c-v2/r2-probes --rounds 20 --label host
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c-v2/r2-probes/journal_probe.py \
  --out artifacts/reviewer-g3c-v2/r2-probes --rounds 20
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c-v2/r2-probes/crash_probe.py \
  --out artifacts/reviewer-g3c-v2/r2-probes
bash artifacts/reviewer-g3c-v2/r3-dsh/run_r3_v2.sh echo   # 及 tool/stream/resume1/resume2/crash/reconcile/guard_*
/root/.local/bin/python3.11 -B artifacts/reviewer-g3c-v2/r4-crosscheck/r4_crosscheck.py \
  --out artifacts/reviewer-g3c-v2/r4-crosscheck
```

**环境**：rootfs `25491e45…`、deps `e07729d7…`、stage `fcdb0de4…`；`podman ps -a` 空；0 Key/0 外网/0 Live。

---

*Reviewer #2 独立出具；只写本文件与 `artifacts/reviewer-g3c-v2/`；未修改产品代码/测试/脚本/已有 docs/artifacts/Packet，未 commit/push。*
