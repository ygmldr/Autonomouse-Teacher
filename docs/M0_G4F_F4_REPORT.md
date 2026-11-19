# M0 G4-F4 — 真实双 Principal DSH Session Resume 验证（No-Key）

- **任务**：G4-F 指令 F4 —— 在 G4 双 Principal + G4 stage（含 F3 code）下补真实 DSH
  Session Resume 联合验证，处置 `docs/REVIEW_G4_INDEPENDENT.md` 的 P2-6/C16
  （`DSH resume L2 UNVERIFIED`）。
- **基线**：`7000f727d0e5926b0bd95574f3c587a2707da6d8`（F1/F3 已完成；工作区起点 clean）。
- **性质**：**no-key / no-model / no-network / no-live**。0 真实 Key、0 模型调用、0 外部
  HTTP/TCP、0 真实计费；未执行 `podman pull`；全部 provider 请求为 synthetic Fake。
- **隔离说明**：运行 F4 时共享工作区已有另一 workstream 的未提交 G4-F2 改动
  （`src/autoteacher_m0/bridge/*`、`scripts/g4/launch_c.py` 等）。为避免把未提交代码装入
  stage/污染账本，F4 证据在 **HEAD 7000f72 的独立 clean git worktree**（`/root/at-f4-clean`，
  artifacts 以 bind mount 指向主 artifacts）中产生；stage 仍由 HEAD 7000f72 构建并逐 blob
  验证。未改动、未 stage、未 revert 任何他人文件。

---

## 0. 结论摘要

| 项 | 结论 |
|---|---|
| 真实 DSH resume（正向） | **PASS**：两个独立 Candidate 容器；turn1 `start_session` Echo，turn2 `resume_session`；DSH session 14→24 行，`reason:"resume"` 1 次 |
| 每个 provider request 独立账本 | **PASS**：2 Reservation / 2 Claim / 2 Attempt / 2 Receipt / Fake counter=2 / gate 2 authorized + 2 consumed |
| 新 resume 请求复用旧 Attempt / 重放旧 call_id | **PASS（未发生）**：两个 call_id/attempt_id/reservation_id/receipt_id 均不同；phase1 old Attempt 行在 phase2 后逐字段不变 |
| 二次结算 | **PASS（未发生）**：4 条 broker message = 2 RESERVED + 2 SETTLED；每 reservation 恰 1 次 settlement |
| usage/receipt 一致 | **PASS**：两请求 DSH usage 与对应 Fake receipt usage 字段级相等；`input_used=13`（11+2 cache read），`output_used=5` |
| 账本总数 | **PASS**：committed=spent=`0.002044`，reserved=0，pending=0，costs 各 `0.001022` |
| Resume 未重发旧请求 | **PASS**：Fake counter 从 1→2，只增加 1；旧 receipt SHA 不变；旧 Attempt 未改写 |
| 崩溃后 resume 负例 | **PASS（限定范围）**：trusted test-only crash 后旧 Attempt `SETTLEMENT_UNCERTAIN`、Reservation `PENDING`、Fake=0；恢复 Controller exit 3 `ADMISSION_REPLAYED`；真实 resume Candidate 失败于 `G3B_BRIDGE_CONNECT_FAILED`，未新增 Attempt/Claim/Reservation/Receipt，账本保守 |
| 容器/rootfs/deps | **PASS**：运行后 `podman ps -a` 空；rootfs `25491e45…`、deps `e07729d7…` canonical |
| 结论标签 | **`RESUME_L2_VERIFIED`**（本报告 §7 的限定范围内；candidate-crash + live-controller 子场景仍 `UNVERIFIED`） |

---

## 1. 基线与运行边界

### 1.1 与真实组件

| 组件 | 值 |
|---|---|
| HEAD / stage base | `7000f727d0e5926b0bd95574f3c587a2707da6d8`（含 F3 `3edf48c` code） |
| G4 stage | `artifacts/g4/c/stages/stage-20261119T115142Z` |
| stage manifest SHA-256 | `3878e5f1734ee7ccb9ef337ee4d3cd5a17e6991efa98cbd0d7e0f4a88e1bd2e8` |
| stage tree SHA-256（运行前后一致） | `0206d9696c85b1ccba163ea4dd963cc325581721558442f4884287e6963a6b20` |
| DSH | `0.2.2rc2`，runtime SHA `1cc41d5a8745a5b9d47c8604e44f23eb8af2d8ca02b2afa0be101d5f71be6ea4` |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（canonical） |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（canonical） |
| Fake provider | `spikes/g3b-trusted-bridge/fake/fake_provider.py`（stage 内只读） |
| LiveGate | `BLOCKED`（未改变） |

### 1.2 双 Principal 与容器边界（实测）

两个 Candidate 容器均使用：

```text
--network none
--read-only --cap-drop ALL --security-opt no-new-privileges
--uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1
--group-add 2000
mount /project ro, /deps ro, /work/session rw, /work/g3b ro
```

逐 phase 证据中的实际值：

| 项 | turn1 | turn2 |
|---|---|---|
| Candidate container uid_map | `0 65534 1` | `0 65534 1` |
| Candidate container gid_map | `0 65534 1`；`2000 2000 1` | 同左 |
| Candidate `/proc/self/status` | CapEff=0、NoNewPrivs=1、Seccomp=2 | 同左 |
| Trusted peercred（日志） | `uid=65534 gid=65534` ×1 | `uid=65534 gid=65534` ×2 |
| Bridge socket | `0660`、uid 0、gid 2000、type socket | 同左（同一 inode） |
| Candidate mountinfo | 含 `/work/g3b` ro、`/work/session` rw；**不含** `/work/state` | 同左 |
| exit | 0 | 0 |

Trusted Controller 以 `--userns=host --user 0:0` 运行；Candidate 不能读 trusted state，
也不挂载 trusted stage。两个 Candidate 进程彼此独立，只共享 host 侧 Candidate session 目录
（`$RUN/candidate-session`，宿主 uid 65534）。

---

## 2. 正向场景：真实 DSH Resume

### 2.1 运行时间线

| Phase | UTC | Candidate container | Scenario / DSH API | Session | Exit |
|---|---|---|---|---|---|
| turn1 | 12:14:05–12:14:07Z | `…-turn1` | `echo` / `start_session` | `g4f-f4-s1` | 0 |
| turn2 | 12:14:08–12:14:10Z | `…-turn2` | `resume` / `resume_session` | 同一 `g4f-f4-s1` | 0 |

- turn1 prompt SHA-256 `cf451a8d2f945a3b919b95316af915c812a76efcacd5bf6274dd5c340d5e6aea`；
  turn2 prompt SHA-256 `85cf6667b745f8090f0faaef82c46d0f54b2bb89a4743a1e6abba151bd0464f4`。
- 两 phase 的 DSH result 都是 `final_response="ok"`、`finish_reason="completed"`、无 error；
  turn2 DSH result 明确 `resume.used=true`、`sdk_call="resume_session"`。
- 真实 DSH session 文件 `dsh-home/sessions/--work-session-workspace--/g4f-f4-s1/session.v4.jsonl`
  由 turn1 的 14 行 / 3597 bytes 增长为 turn2 的 24 行 / 6005 bytes；`reason:"resume"` 计数 1。

### 2.2 每个 provider request 的独立账本

完整值见 `per-request.json`；下表为便于审计的截断值（完整 ID 在 JSON 中）。

| Phase | logical_step | call_id | Reservation | Claim | Attempt | Receipt | gate payload | cost | usage |
|---|---:|---|---|---|---|---|---|---:|---|
| turn1 | 0 | `call-eb018d27…` | `38cc0256-…` OK | `COMPLETED` | `att-7dd95d74…` SETTLED | `rcpt-feaca0a6…` | length 1509，digest `7dd65be2…` | 0.001022 | 11/2/0/5/0/18 |
| turn2 | 1 | `call-a4af9c8b…` | `21338748-…` OK | `COMPLETED` | `att-13787167…` SETTLED | `rcpt-49354cfd…` | length 1875，digest `501320dd…` | 0.001022 | 11/2/0/5/0/18 |

- 2 个 call_id、attempt_id、reservation_id、receipt_id 两两不同；两个 Prepared digest 分别
  等于各自 Claim `request_digest`；两个 payload digest 分别等于各自 Receipt `raw_sha256`。
- Fake counter=2；实际 4 条 broker message：2 `RESERVED` + 2 `SETTLED`；无 `FAILED`/`RELEASED`。
- 账本 totals：`committed_usd=0.002044`、`spent_usd=0.002044`、`reserved_usd=0`、`pending=0`；
  每个 reservation `cost=0.001022`，settlement `cost_usd` 与 reservation cost 相等。

### 2.3 旧 Attempt / 旧 call_id 检查

- phase1 snapshot 中恰有 1 个 Attempt；phase2 snapshot 中恰有 2 个，且 phase1 的 Attempt
  行（attempt_id/call_id/reservation_id/receipt_id/state/updated_utc/settlement_json 等）在
  phase2 后 **逐字段不变**。
- phase1 的 reservation 与 receipt 文件（SHA-256）在 phase2 后保持不变。
- 旧 call_id 在最终 attempts 中只出现 1 次；新 resume 请求使用不同 call_id/Attempt。
- trusted log 中无 `ATTEMPT_ALREADY_STARTED`；gate journal 无 denied；Fake counter 只增加 1。
- 因此：**resume 未复用旧 Attempt、未重放旧 call_id、未二次结算、未重发旧 Session 请求**。

### 2.4 usage / receipt / settlement

两请求的 DSH result usage 与对应 Fake receipt usage **字段级相等**：

```json
{"cacheReadTokens":2,"cacheWriteTokens":0,"inputTokens":11,
 "outputTokens":5,"reasoningTokens":0,"totalTokens":18}
```

Broker 映射：`input_used=13`（11 uncached + 2 cache read + 0 cache write），`output_used=5`；
每个 reservation 的 `settlement.status=OK`，`cost_kind="estimated"`（synthetic fixture），
`cost_usd=0.001022`。`docs/REVIEW_G4_INDEPENDENT.md` §7 的 c01/c02 口径在本 run 上保持。

### 2.5 Session trace 与“上下文重放但只发新请求”

真实 DSH session JSONL（turn2 文件）的直接证据：

- `request/header` 事件：`seq=7 reason="initial"`，`seq=19 reason="resume"`；
- `assistant/message`：turn 1 与 turn 2 各 1 条，usage 均与 receipt 一致；
- `user/message`：包含 turn1 prompt、runtime-context、turn2 prompt；
- turn1 的 assistant 消息位于 turn2 `turn/start` 之前；turn2 session 文件包含 turn1 全部历史。

Provider 侧更强证据：gate journal 的两个授权 payload：

```text
turn1 payload_length=1509  payload_digest=7dd65be2…  prepared_digest=c1fc3c9f…
turn2 payload_length=1875  payload_digest=501320dd…  prepared_digest=476cabba…
```

turn2 的 provider payload 比 turn1 **长 366 bytes**，且 digest 不同；结合 DSH
`reason:"resume"` 与 session 文件中的 turn1 assistant 消息，可证明 **DSH 重放了会话上下文，
但 provider 只收到一个新的 turn2 请求**。限制：Fake receipt 只落 `raw_sha256`/`raw_length`，
不保存原始 payload 字节，因此这是 **L2 语义证据**，不是“turn2 payload 字节包含 turn1 答案”的
字节级包含证明（与 G4 Review §7 对 c02 的限制同类）。

---

## 3. 负向场景：崩溃后 Resume（旧 Attempt 未决）

### 3.1 注入与时间线

使用产品已有的 **test-only crash hook**（不新增产品语义）：

```text
G3B_TEST_MODE=1
G3B_CRASH_HOOK=after_attempt_start_before_fake_send
```

| 步骤 | UTC | 结果 |
|---|---|---|
| turn1 Candidate（echo） | 12:14:16–12:14:18Z | exit 7；trusted Controller `os._exit(97)` |
| recovery Controller（同 state，无 hook） | 12:14:19Z | exit 3 `ADMISSION_REPLAYED`；仅执行 reconcile |
| turn2 Candidate（resume 同一 session） | 12:14:19–12:14:22Z | exit 7；`resume_session` 已调用，但 bridge 无监听者 → `G3B_BRIDGE_CONNECT_FAILED` |

### 3.2 账本与“不重发”

| 时点 | Attempt | Reservation | Claim | Receipt | Fake | gate auth |
|---|---|---|---|---|---|---|
| crash 后、恢复前 | `ATTEMPT_STARTED`，reason null | `PENDING`，cost=0.002731 | `CLAIMED` | 0 | 0 | 0 |
| recovery 后 | `SETTLEMENT_UNCERTAIN`，reason `NO_RECEIPT_AFTER_CRASH` | `PENDING`，cost=0.002731 | `CLAIMED` | 0 | 0 | 0 |
| resume turn2 后（final） | 与 recovery 后逐字段相同 | 同左 | 同左 | 0 | 0 | 0 |

- final：1 Attempt / 1 Claim / 1 Reservation / 0 Receipt / Fake=0；broker messages 仅 1 条
  `RESERVED`，0 条 `SETTLED`、0 条 `FAILED`。
- totals：`committed_usd=0.002731`、`reserved_usd=0.002731`、`spent_usd=0`、`pending=1`。
  这是保守账本：旧 reservation 未被释放、未被结算、未被第二次 reserve。
- 旧 Attempt/call_id 只有 1 个；resume 未新增 Attempt、Claim、Reservation、Receipt；
  旧 Attempt 在 resume 前后逐字段不变（recovery 的 `SETTLEMENT_UNCERTAIN` 注释除外，且发生在
  resume 之前）。
- resume result：`resume.used=true`、`sdk_call="resume_session"`、`finish_reason="error"`、
  `turn_end.error={code:SERVER,message:G3B_BRIDGE_CONNECT_FAILED}`；无 assistant message。
  DSH session 文件从 14 行增长到 24 行（记录了 resume turn 的失败），但 **Fake counter=0**
  证明没有 provider 发送。

**结论（限定）**：崩溃后旧 Attempt 未自动重发、账本保守。该负例证明的是“**无存活
Controller 时，真实 resume 不会重发旧 PENDING/未知 Attempt，也不会产生新请求**”。它没有
证明“Candidate 进程崩溃但 Controller 仍存活时，DSH 是否会自动重试同一 turn”，该子场景
见 §7，标 **`UNVERIFIED`**。

---

## 4. 证据

### 4.1 顶层

| 路径（`artifacts/g4f/f4/`） | 内容 |
|---|---|
| `summary.json` | 两 phase 汇总：stage base/tree、rootfs/deps canonical、containers_after=[]、`conclusion=RESUME_L2_VERIFIED` |
| `audit.json` | 独立审计：resume 19 checks + crash-resume 12 checks，全部 PASS |
| `manifest.json` | 两 run 共 390 个证据文件的 path/bytes/SHA-256 |
| `logs/resume-20261119T121402Z.log` | 正向 runner log |
| `logs/crash-resume-20261119T121413Z.log` | 负向 runner log |
| `regression/g4_c_f3_d.txt` | G4-C/F3/D host pytest：127 passed |
| `regression/g4c/summary.json` | G4-C 完整容器 runner：9/9 cases、106 checks、容器空、canonical |

### 4.2 正向 run

`artifacts/g4f/f4/runs/resume-20261119T121402Z/`

| 要求 | 文件 |
|---|---|
| 每 phase argv | `phases/turn1/argv.json`、`phases/turn2/argv.json`、`run/argv-candidate-turn{1,2}.json` |
| UTC / exit | `phases/turn{1,2}/phase.json` |
| uid_map / mountinfo | `phases/turn{1,2}/identity.json`、`phases/turn{1,2}/uid-map.txt`、`mountinfo.txt` |
| peercred / socket | `phases/turn{1,2}/peercred.json`、`socket-stat/turn{1,2}-*.json` |
| DSH trace | `phases/turn{1,2}/dsh-result.json`、`traces/dsh-result-turn{1,2}.json` |
| session 文件清单 + 原始 JSONL | `phases/turn{1,2}/session.json`、`phases/turn{1,2}/session/…/session.v4.jsonl` |
| DB（phase 备份 + final） | `phases/turn{1,2}/db/*.sqlite3`、`db/broker.sqlite3`、`db/attempts.sqlite3`、`db/snapshot.json` |
| receipt / Fake counter | `phases/turn{1,2}/receipt/*`、`receipt/*`、`db/snapshot.json.fake_counter` |
| 对账 | `per-request.json`、`reconciliation.json`、`checks/checks.json` |
| 清理 | `cleanup/cleanup.json`、`cleanup/ps-after.txt`、`env/canonical-post.json` |

### 4.3 负向 run

`artifacts/g4f/f4/runs/crash-resume-20261119T121413Z/`，同结构；额外：

- `run/trusted-restart.json`：recovery exit 3；
- `phases/turn1/db/attempts.sqlite3`：crash 后 `ATTEMPT_STARTED` 的中间态；
- `phases/turn2/db/attempts.sqlite3`：recovery 后 `SETTLEMENT_UNCERTAIN`；
- `traces/dsh-result-turn2.json`：resume 失败，`G3B_BRIDGE_CONNECT_FAILED`；
- `reconciliation.json`：`no_resend=true`、`conservative=true`（由实际计数计算，不是常量）。

### 4.4 容器结束空 / canonical

两个 run 的 `cleanup` 均 `ok=true`、`problems=[]`；`podman ps -a` 为空；
`rootfs/deps` canonical；`stage` tree 前后一致。正向 run 的 cleanup 另记录 1 个
`unrelated_host_processes`（另一 workstream 的 host pytest `fake_provider.py`，argv 不含本 run
id/容器名），已单独存 `cleanup/unrelated-host-processes.json`，不属于本 run 的 residual；
本 run 的 `residual-processes.json` 为 `[]`。

---

## 5. 独立审计（不信任 checks.json）

`scripts/g4/audit_g4_f4.py` 不导入产品代码，只读证据副本：

- 直接重开 `broker.sqlite3` / `attempts.sqlite3`，重新查询 reservation/claim/attempt/message；
- 重新读取 `receipt/rcpt-*.json`，按 `raw_sha256` 与 attempt payload digest 关联；
- 重新解析 `session.v4.jsonl` 的 `request/header`、`assistant/message`、`user/message`；
- 直接解析原始 gate journal，不读 runner 的 gate 汇总。

结果（`artifacts/g4f/f4/audit.json`）：

| run | checks | 结果 |
|---|---:|---|
| resume | 19 | 全 PASS（counts/status/distinct IDs/digests/usage/old row/old receipt/gate/session/totals/settlements） |
| crash-resume | 12 | 全 PASS（single attempt/PENDING/uncertain、recovery 注释、resume 未改写、no settle、gate=0、conservative totals） |

其中对旧行的比较使用 **phase1/phase2 DB backup** 与 final DB，而非 runner 的 `checks`；
`old_attempt_unchanged_after_resume`、`old_reservation_unchanged`、`old_receipt_unchanged` 均 PASS。

---

## 6. 回归与静态检查

### 6.1 Host pytest（G4-C / G4-F3 / G4-D）

```text
tests/integration/g4_c tests/integration/g4_f3 tests/integration/g4_d
→ 127 passed in 13.04s（exit 0）
```

- 首次尝试 126 passed / 1 failed：`test_d15_same_uid_known_path_is_denied_by_mode_not_name`
  因 `sys.executable` 位于 `/root/...`、uid 65534 不可执行而失败；在 `/tmp` 可访问
  interpreter + clean worktree 下重跑为 **127 passed**。归类：**环境路径问题，不是产品回归**。
- 本轮三目录不包含 G3-D 的 `git diff cf40c6b -- src` 类 frozen-src 断言，因此
  **frozen-src 预期失败数 = 0**；G3-D frozen-src 类失败按既有口径未纳入本回归（其历史断言
  因授权改码必然失败，见 G4 文档 C-R6/A-R2）。

### 6.2 G4-C 完整容器 runner（真实双 Principal）

`scripts/g4/run_g4_c.py` 在 HEAD 7000f72 的 stage（manifest `3878e5f1…`）上重跑全部 9 个 case：

| 项 | 结果 |
|---|---|
| cases | **9/9 PASS**：c01、c02、c18、negatives、replay、crash-before-send、crash-after-receive、broker-down、quota |
| checks | **106/106 PASS**（18+20+9+8+9+12+13+8+9） |
| 容器 | 运行后 `podman ps -a` 空 |
| rootfs/deps | canonical（`25491e45…` / `e07729d7…`） |
| 真实 Key/模型/外网 | 0 / 0 / 0；LiveGate `BLOCKED` |

证据：`artifacts/g4f/f4/regression/g4c/summary.json`、`regression/g4c-run.txt`。

### 6.3 Ruff

Ruff（deps 内 0.17.5）：`scripts/g4/run_g4_f4.py`、`scripts/g4/audit_g4_f4.py`
→ **All checks passed**。

---

## 7. 残余与未验证项

1. **Context replay 的字节级证明**：session JSONL + gate payload length/digest 是 L2 语义证据；
   Fake receipt 只存 payload 的 SHA-256/length，不存原始字节，无法做“turn2 payload 包含 turn1
   答案文本”的字节级包含证明。与 G4 Review §7 c02 限制同类。
2. **Candidate crash + live Controller 子场景（`UNVERIFIED`）**：本负例用产品 test-only
   trusted crash hook 制造旧 Attempt PENDING/UNCERTAIN；没有在不修改产品的条件下让
   Candidate 进程在 provider 请求中途崩溃且 Controller 继续服务。因此“DSH 是否会对
   未完成的 Candidate turn 自动重试/重发”未被本 run 覆盖。本报告不把它写成已验证。
3. **Synthetic-only**：Fake provider 的 usage/cost 是 fixture；不是真实 Provider/TLS/DNS/账单/
   额度。`LiveGate` 仍 `BLOCKED`。
4. **session-log-deepseek**：candidate overlay 仍 `config.enabled=false`；本 run 只依赖 DSH
   core 的 `session.v4.jsonl`。未证明任意未来会话不会产生辅助 LLM 调用（B07 余项）。
5. **并发 workstream**：F4 证据在 HEAD 7000f72 的 clean worktree 产生；共享工作区的未提交
   G4-F2 改动未进入 stage/证据。若后续 F2 合并修改 `scripts/g4/launch_c.py` 或
   `scripts/g4/stage/trusted_entry_g4c.py`，F4 需在合并后 HEAD 重跑（stage base 会变）。
6. **Host residual 扫描口径**：G3-D 的清理扫描是全 host marker；本 run 已把不属于本 run 的
   1 个 host pytest 进程单独记录并排除，`residual-processes.json=[]`。这不是“host 无任何
   进程”，而是“本 run 无 residual”。
7. **证据路径**：`summary.json` 中 stage/run 路径含 `/root/at-f4-clean/...`（隔离 worktree）；
   stage tree/manifest SHA 与主 artifacts 的 `stage-20261119T115142Z` 相同，可按 SHA 复核。

---

## 8. 提交与结论

- 主提交：`b963ad4e89ade40021e78007a3f8ec61c0b6d62d`
  （`feat: G4-F4 real dual-principal DSH session resume validation (no-key)`），
  父提交 `7000f727d0e5926b0bd95574f3c587a2707da6d8`；包含 runner、audit 与本报告。
- 随后 docs-only 提交补记 G4-C 完整容器回归计数（9/9、106 checks），父为主提交。
- 只新增/修改：`scripts/g4/run_g4_f4.py`、`scripts/g4/audit_g4_f4.py`、
  `docs/M0_G4F_F4_REPORT.md`；未 push、未 amend、未 stage 任何他人文件。
- **范围结论：`RESUME_L2_VERIFIED`**。正向真实 resume + 双请求独立账本 + 旧 Attempt/
  旧 call_id 不重放 + usage/receipt/结算对账 + 崩溃后 resume 保守账本均已由真实
  dual-principal 容器证据与独立 SQLite/JSONL 审计支持；§7 的 candidate-crash live 子场景
  与字节级 context 证明仍不在本结论内。
