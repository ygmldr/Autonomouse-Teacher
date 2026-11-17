# M0 G3-D1 — 双 Principal 正向集成与 D1 Gate 报告

> **状态**：`D1_GATE_PASS`（Echo 与 Tool 两轮均为真实 DSH + 真实双容器正向；账本、清理、0-Key 全部满足）
> **不是**：D2 攻击通过、D3 故障恢复通过、G3-D 完成、Live、G4/G5、M0 GO。`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 继续成立。
> **日期**：2026-11-17 ｜ **执行 Agent**：D1-C Integration/Gate Agent ｜ **工作树**：`/root/Autonomous Teacher`
> **产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`（D-P0；`src` 与 `51abc66` 相同）
> **D1-C 实现提交**：`46e2407ab14a1867fddc7c3df17b72bdd0fb0bc7`，父 `aacb1d01d979a0d7140bce0311e39b4a03009637`（D1-B）
> **Gate 运行 HEAD**：`46e2407`（正式 Stage 构建与两次 Run 时工作树 clean；docs 改动在 Run 之后提交）
> **证据根**：`artifacts/g3d/d1/`（`artifacts/` 被 gitignore，不进入产品 commit）

---

## 0. 结论先行

| 项 | 结论 |
|---|---|
| **D1-01 真实 DSH Echo** | **PASS**。两个 OS Principal、真实 DSH、1 Reservation/Claim/Attempt/Receipt/Settlement、Fake counter=1；DSH usage 与 Fake receipt usage 字段级相等；两对 Digest 分别成立。 |
| **D1-02 真实 DSH Tool 两轮** | **PASS**。同一真实 Turn 两次 Provider 请求；2 套独立 Reservation/Claim/Attempt/Receipt/Settlement；Fake counter=2；第二请求携带真实 `skill_lookup` 结果；两轮 DSH usage 分别等于对应 receipt usage；两对 Digest 各自成立。 |
| **D1 Gate** | **`D1_GATE_PASS`**。Echo + Tool 均真实 PASS，账本/清理/0-Key/Peercred/Socket/Mount/Network/Cgroup 全部满足；未使用 Mock、同 UID、0666、挂 state 或关闭 peercred。 |
| **未验证** | Session Resume（D1-03）、D2-01..12 攻击、D3 Crash/Cancel/Replay/Recovery/Streaming、Independent Review、Live。 |
| **下一步** | **STOP**。等 Lead 审计 D1 Gate 后授权 D2；本 Agent 不进入 D2。 |

---

## 1. 身份与 Stage

### 1.1 Git / 运行身份

| 项 | 值 |
|---|---|
| 产品基线 | `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b` |
| D1-A | `51abc6619ef87ad7b93aa3162fed52ab14df6e56`（additive socket mode/peercred/ready；已批准） |
| D1-B | `aacb1d01d979a0d7140bce0311e39b4a03009637`（stage/launcher/Echo；已批准） |
| D1-C | `46e2407ab14a1867fddc7c3df17b72bdd0fb0bc7`（本报告实现；父 `aacb1d0`） |
| Gate 运行 HEAD | `46e2407`（Stage 构建与 Echo/Tool Run 时 clean） |
| `src/` 改动 | **0**。`git diff --stat 4bd4803 46e2407 -- src` 为空；D1-A 的 `src` 改动已在 `51abc66` 中，属于获批基线。 |
| 冻结文件 | 未改 `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge`、G3-C 冻结证据/Packet/历史 docs。 |

### 1.2 Stage（D1-C 新建，未复用 G3-C/D1-B stage）

| 项 | 值 |
|---|---|
| 目录 | `artifacts/g3d/stage-20261117T195831Z` |
| Manifest SHA-256 | `83b241c77b28813b1d1b55ed96b7f940027a0bd8f2b4eefbbb14b0c4cf09110e` |
| 整体 tree SHA-256 | `9b6fc7b4d22cb2cbf5c21c1c6dc0714646a651280056cc5426f248b6fdb2548b` |
| Trusted / Candidate tree SHA | `c1c27eb56fde61316d39d77c8e67d8c230c1dff179f179d2773f5d17ac56276b` / `1474002f27a1ec583380c411cbfa83b950d43f07489a80479e5be0a7216509ef` |
| 文件数 | trusted 57 / candidate 6529（含 node_modules/pkg-cache；逐文件 path/sha256/bytes/mode/source） |
| 构建 | `git archive 4bd4803` 取 Trusted 产品；Candidate 显式白名单；固定 rootfs 内 `--network none --cap-drop ALL` 重编译 adapter |
| Adapter | `builtJs.sha256=2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba`，`deterministic_match=true` |
| 运行时 | rootfs `25491e45…`、deps `e07729d7…`、Node `v22.23.2`、DSH SDK `0.2.2rc2`、runtime `1cc41d5a…` |
| 与 D1-B Stage | D1-B 为 `stage-20261117T192708Z` / manifest `09851276…` / tree `b14de55a…`；D1-C 因 `candidate_entry.py` 增加 tool 场景而重建，**不是**同一 tree，Run 证据只绑定新 Stage。 |

Trusted 模块加载：`trusted/evidence/trusted-modules.json` 由容器内 `inspect.getfile` 生成；10 个模块全部从 `/project/src/autoteacher_m0/...` 加载，字节 SHA 与 `git show 4bd4803:<path>` 一致（check `trusted_modules_from_stage_and_git_blobs`）。

---

## 2. D1-C Launcher / Candidate 实现

D1-C 只在 `scripts/g3d/**`、`config/g3d/**`、`tests/integration/g3d/**`、`docs/M0_G3D_D1*` 写域内工作；未改协议、未改 `src/`。

| 变更 | 说明 |
|---|---|
| `scripts/g3d/launch.py` | 新增 scenario 映射：`echo` → `fake_scenario=ok_usage,max_calls=1`；`tool` → `fake_scenario=tool,max_calls=2`；默认 prompt 按 scenario 注入；新增 `pair_tool_ledger()`，按 `call_id`/`receipt_id` 而不是列表位置关联 Attempt/Claim/Receipt。 |
| `scripts/g3d/stage/candidate_entry.py` | 允许 `echo`/`tool`；`scenario_verdict()` 对 Tool 强制校验“两个 assistant message、第一含 tool-call、第二为 text、真实 skill_lookup 结果含 `binary_search`/`m0-skills-v1`、两段 usage”。 |
| `config/g3d/**` | **未改**。Admission 的 `max_calls`/`fake_scenario` 在 Launcher 解析模板后按 scenario 覆写，冻结模板保持字节不变。 |
| `tests/integration/g3d/test_d1_launcher_contract.py` | 新增 scenario admission/prompt、ledger 正/负关联、poisoned candidate-session 捕获拒绝等 host contract 测试。 |

Trusted 侧本身已支持 `fake_scenario="tool"`（Controller 按 `logical_step` 映射 `tool_once`/`tool_final`），Fake Provider 已有对应帧；D1-C 没有改协议或 Fake 逻辑。

---

## 3. 双 Principal / Socket / Peercred / Mount / Network / Cgroup

### 3.1 两个真实 Principal

| 观测 | Trusted | Candidate |
|---|---|---|
| 容器 argv | `--userns=host --user 0:0`、`--network none`、`--read-only`、`--cap-drop ALL`、`no-new-privileges` | `--uidmap 0:65534:1`、`--gidmap 0:65534:1`、`--gidmap 2000:2000:1`、`--group-add 2000`、`--user 0:0`、同上安全参数 |
| Host `/proc/<pid>/status` | `Uid/Gid 0/0`，`CapEff=000…0`，`NoNewPrivs=1`，`Seccomp=2` | `Uid/Gid 65534/65534`，`CapEff=000…0`，`NoNewPrivs=1`，`Seccomp=2` |
| uid_map / gid_map | `0 100000 65536`（Runner 自身嵌套 LXC 视角） | `0 65534 1` / `0 65534 1` + `2000 2000 1` |
| cgroup | `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000` | 同左；`memory.current≈10–12MB`、`pids.current=1` |
| 网络 | `NetworkMode=none` | `NetworkMode=none`；`AF_INET/AF_INET6 socket()` → `EACCES(13)`，DNS → `EAI_AGAIN(-3)`，仅 `lo` |

Candidate 实际挂载：`/project`(ro)、`/deps`(ro)、`/work/g3b`(ro)、`/work/session`(rw)、`/etc/passwd`、`/etc/group`；**无** `/work/state`、`/output`、`/project/src`。Trusted 独有 `/work/state`(rw)、`/output`(rw)。

### 3.2 Socket / Ready / Peercred

- Host `ipc/` = `2750 root:2000`（setgid）；socket 在 Candidate 启动前为 `S_ISSOCK 0660 root:2000`（`socket-stat/before-candidate.json`）。
- Trusted `on_ready` 仅在 `bind` + `chmod/chown` 校验 + `listen()` 之后写 `/work/state/ready`（0600 root，`O_NOFOLLOW|O_EXCL`）。
- Launcher 独立复核 socket stat + `/proc/<trusted_pid>/net/unix` 中 LISTEN + inode 与 ready 一致 + 容器 running，四项全满足后才写 `$RUN/state/launcher-ready.json` 并启动 Candidate。
- Trusted 侧 `SO_PEERCRED`（Echo/Tool 两次 Run 均一致）：

```text
bridge socket ready mode=0660 gid=2000 uid=0 peer_uid=65534
bridge peer accepted uid=65534 gid=65534 pid=0
```

无 `PEER_UID_DENIED` / `PEERCRED_UNAVAILABLE`；`pid=0` 是跨 PID namespace 的正常值，不用于鉴权。Candidate 对 socket 的 `unlink`/`rename`/create 均为 `EROFS`，且 `/work/g3b` 为只读挂载。

### 3.3 Candidate 边界自检

`traces/principal.json` 的 `problems=[]`：未导入 `autoteacher_m0`/`controller`/`broker`/`fake_backend`（`find_spec=None`）；`PYTHONPATH=/deps`；`/work/state`、`/project/src`、`/project/trusted` 不存在；无 Key-like env；无 trusted 组件进程。

---

## 4. D1-01 真实 DSH Echo（正式 Gate Run）

| 项 | 值 |
|---|---|
| Run ID | `20261117T195848Z-d1-echo-87ab9355` |
| 命令 | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-echo --scenario echo --session g3d-d1-s1 --stage artifacts/g3d/stage-20261117T195831Z --evidence-dir artifacts/g3d/d1/echo` |
| UTC / 耗时 | `19:58:48Z` → `19:58:55Z`（约 7s） |
| 退出 | Launcher `0`；Trusted `0`；Candidate `0` |
| 断言 | **29/29 PASS**（`run/checks.json`、`run/run-summary.txt`） |
| DSH | `final_response="ok"`、`finish_reason="completed"`、13 events、session `g3d-d1-s1` |
| DSH usage | `inputTokens=11, cacheReadTokens=2, cacheWriteTokens=0, outputTokens=5, reasoningTokens=0, totalTokens=18` |
| Fake receipt | `rcpt-38ca49b2c3ac49d192abed86f5e89e67`；usage 与 DSH **字段级相等**；`synthetic=true`、`real_model_calls=0`、`http_calls=0`、`network_used=false` |
| Counter | `{"count": 1}` |

| 账本对象 | 值 |
|---|---|
| Reservation | `4010a0c0-01ad-4c6a-84eb-9af15e421d10`，`status=OK`，`input_used=13`、`output_used=5`、`cost=0.001022`、`estimated=false` |
| Claim | `call-829505b3be2fee2172af4e0a4b310f1209848e1caa7dd990`，`status=COMPLETED` |
| Attempt | `att-96b54a85481a4c17946e5e22b4187cd3`，`state=SETTLED`，`logical_step=0`，`mode=ok_usage` |
| Admission | 1 条 consumed |
| Prepared 对 | `claim.request_digest == attempt.prepared_digest == 9543ffbd5b16950a4a529a7016dbd249a9e4cea50f67a9a61c6a3ac257bf4f94` |
| Payload 对 | `attempt.payload_digest == receipt.raw_sha256 == 64f8f5552a3f10e8952b0c0f0b8b4eeb90c545650e82c8f1b10c0687bf42ed8c` |

两个 Digest 对不要求互等，本 Run 也不互等。

---

## 5. D1-02 真实 DSH Tool 两轮（强制 Gate Run）

| 项 | 值 |
|---|---|
| Run ID | `20261117T195859Z-d1-tool-38773582` |
| 命令 | `/root/.local/bin/python3.11 -B scripts/g3d/launch.py --case d1-tool --scenario tool --session g3d-d1-s1 --stage artifacts/g3d/stage-20261117T195831Z --evidence-dir artifacts/g3d/d1/tool` |
| UTC / 耗时 | `19:58:59Z` → `19:59:06Z`（约 7s） |
| 退出 | Launcher `0`；Trusted `0`；Candidate `0` |
| 断言 | **33/33 PASS**（`run/checks.json`、`run/run-summary.txt`） |
| Admission | `fake_scenario="tool"`，`limits.max_calls=2`（`run/config-admission.json`） |
| DSH | 同一真实 Turn：`turn=1`；`step=1` 产生 tool-call，`step=2` 产生最终 text；18 events；`final_response="ok"`、`finish_reason="completed"` |
| 工具 | `skill_lookup`，参数 `{"skill_id":"binary_search"}`；真实结果包含 `id=binary_search`、`title=Binary Search`、`source_version=m0-skills-v1` |
| 第二请求 | `tool/result` 进入第二轮；Attempt 输入上界从 `1205` 增至 `1998` tokens，proof `tool_second_request_includes_result` |
| Fake counter | `{"count": 2}` |

| Step | Mode | Reservation | Claim (call_id) | Attempt | Receipt | DSH usage | Prepared digest | Payload == receipt.raw_sha256 |
|---|---|---|---|---|---|---|---|---|
| 0 | `tool_once` | `9b4eb7eb-42e0-438a-859a-47390aff903c` (`OK`) | `call-4b7e1666bb27d967a4ab417a727169cf5faaa4b2c1a7291a` (`COMPLETED`) | `att-78bdc8890703432bb6f98469b0532073` (`SETTLED`) | `rcpt-a8216b237f82458889ed0befaae178e7` | 11/2/0/5/0/18 | `0c9ce033e34142d011a5f12869bc2338ec1ecd2475669b15bc6d2b9716d7d888` | `29c27986d2fc18379409a4936a0e911bbfabe6c806c4bf284b93d9fc741e75ef` |
| 1 | `tool_final` | `2c157b1b-95bf-4a1d-aef2-413fdd67ef9a` (`OK`) | `call-1b0927c0c3c05d33200470ddada41d24490195e15a5926c0` (`COMPLETED`) | `att-028d49df0ae64d24bda0921778d3a1f2` (`SETTLED`) | `rcpt-01fd328c28294d2694ddf8a8d4eada86` | 11/2/0/5/0/18 | `54ae9411baf89e42fb7bc35dd57b46b9331092d964c60a50be5d00158d18b9d0` | `ae170c3a5fd374c98a352be01bcbb96fd7f31b2fde755c8f0ff372713aefc6f1` |

Usage 缩写为 `input/cacheRead/cacheWrite/output/reasoning/total`；两轮 receipt usage 都是
`inputTokens=11, cacheReadTokens=2, cacheWriteTokens=0, outputTokens=5, reasoningTokens=0, totalTokens=18`，
分别与 DSH step 1/step 2 的 usage **字段级相等**（check `dsh_usages_equal_two_receipt_usages`）。

关联检查（全部 PASS）：
- 2 个 Reservation 均 `OK`、金额 `0.001022`、`reservation_exceeded=false`；2 个 Settlement 均 `code=SETTLED`；
- 2 个 Claim 均 `COMPLETED`，`call_id`/`reservation_id` 两两不同；
- 2 个 Attempt 均 `SETTLED`，`mode` 恰为 `{tool_once, tool_final}`；`prepared_digest`/`payload_digest` 两两不同；
- 每个 Attempt 的 `prepared_digest == claim.request_digest`、`payload_digest == receipt.raw_sha256`、`reservation_id` 与 Claim 一致；
- 1 个 Admission consumed；2 个 Receipt 与 counter=2；无重复 call / 无跨 call 复用；
- 两份 receipt 均 `synthetic=true, real_model_calls=0, http_calls=0, network_used=false`。

> 说明：第一轮 `tool_once` 与第二轮 `tool_final` 的 usage 数值相同是冻结 Fake fixture 的设计；独立性由两次不同 call/reservation/attempt/receipt、不同 nonce/digest 和 counter=2 证明，不靠 usage 数值不同。

---

## 6. 测试计数（实际执行）

| 套件 | 命令（摘要） | 结果 |
|---|---|---|
| `tests/integration/g3d` | `python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d` | **111 passed** |
| `tests/integration/g3_bridge` | 同上 `tests/integration/g3_bridge` | **31 passed** |
| `tests/integration/g3c`（冻结 G3-C） | 同上 `tests/integration/g3c` | **110 passed** |
| `tests/unit/security/test_gates.py` | 同上 | **14 passed** |
| `ruff check scripts/g3d tests/integration/g3d/test_d1_launcher_contract.py` | 0.16.2 | **All checks passed** |
| 合计 pytest | — | **266 passed / 0 failed** |

Host pytest 的 `PYTHONPATH` 为 `/root/Autonomous Teacher/src:/root/Autonomous Teacher/artifacts/foundation/deps`，`PYTHONDONTWRITEBYTECODE=1`；所有命令带 `-B`。日志/JUnit 在 `artifacts/g3d/d1/tests/`。

矩阵 D1-04 的“错误 UID 拒绝”还单独复跑：
`test_foreign_peer_uid_is_denied_without_ack_and_without_business_calls` → 真实 fork 子进程 `setuid/setgid 65534` 对 `expected_peer_uid=0` 的 socket 连接，服务端记录 `PEER_UID_DENIED`，无 ack/error frame，Broker `requests=0`（host-level，not DSH）。

---

## 7. 清理、Canonical、0-Key

### 7.1 清理 / Canonical

两次 Run 均：

- 先停 Candidate、再停 Trusted；TERM 后正常退出（未触发 KILL）；`podman rm -f`；只删除本 Run 的 `bridge.sock`/`bridge.sock.lock`；`ipc/` 仅空目录时 rmdir；`safe_delete_tree` 不跟随 symlink；删除本次 `$RUN`。
- `podman ps -a` 空；`at-g3d-*` 容器 0；无残留进程；socket 不存在；run dir 不存在（`cleanup/cleanup.json`、`cleanup/ps-after.txt`、`cleanup/residual-processes.json`）。
- Rootfs / deps / D1-C stage 前后 SHA 相等：`25491e45…` / `e07729d7…` / `9b6fc7b4…`（`env/canonical-pre.json`、`cleanup.json.canonical`）。
- 每个 Run 的 `cleanup.problems=[]`、`cleanup.ok=true`；`summary.status=PASS`、`exit_code=0`。

### 7.2 0-Key / 0 外部网络 / LiveGate

- Host key-like env 名 **0**；无 `.env`（仅 `.env.example`）；`bash scripts/run_live.sh` = **exit 3**；`LiveGate().inspect(live_requested=True)` = **BLOCKED**（4 个原因不变）。
- 两容器均 `--network none --http-proxy=false --unsetenv-all`；容器 env 名仅固定白名单；无 Key/proxy 值。
- Candidate 网络自检：`AF_INET`/`AF_INET6` `socket()` → `EACCES(13)`；DNS → `EAI_AGAIN(-3)`；仅 `lo`；`/proc/net/route` 无默认路由。
- 未执行任何真实模型/外部 HTTP；Fake receipt `real_model_calls=0`、`http_calls=0`、`network_used=false`。

---

## 8. Gate 判定与残余

### 8.1 判定

```text
D1_GATE_PASS
```

理由：D1-01 Echo 与 D1-02 Tool 两轮均为真实 DSH、真实双 Principal；账本一一对应；usage 对账成立；Digest 两对成立；Peercred/Socket/Mount/Network/Cgroup 现场证据满足；清理与 canonical 满足；0 Key/0 外网/0 Live。未使用任何降低安全边界的手段。

### 8.2 残余 / 未验证（不得写成 PASS）

| 项 | 状态 |
|---|---|
| D1-03 Session Resume | **未执行**。Launcher 当前每个 Run 使用独立 `$RUN` 并在结束时删除；Resume 需要保留 session/旧 DB 的第二 Candidate 流程，D1-C 未实现，标 `UNVERIFIED`。 |
| D2-01..12 | 未执行；本报告不提供 OS 攻击结论。 |
| D3 Crash/Cancel/Replay/Recovery/Streaming | 未执行。 |
| Independent Review | 未执行；D1 Review Request 仅提交材料给 Lead/后续 D4 Reviewer。 |
| Candidate session 磁盘硬配额 | 仍无硬上限（D0 已知 P2）；不宣称磁盘 DoS 防护。 |
| Rootful Podman / Runner LXC / Trusted root | 属受信基础；本机 `CAN_ISOLATE` 不可外推。 |
| DSH / Node / adapter | 固定 `0.2.2-rc.2` / `v22.23.2` / `2cb42461…`；无版本外推。 |
| Echo 复跑次数 | 正式 Gate 只跑 1 次 Echo；Tool 是第二个独立真实 Run。未把一次成功外推为统计稳定性。 |

---

## 9. 证据索引（`artifacts/g3d/d1/`）

```text
echo/  env/{git,preflight,podman-info,userns-probe,setgid-probe,livegate,
            canonical-pre,canonical-post,stage-manifest,stage-validation,
            run-layout}.json
       run/{argv-*,inspect-*,ready,launcher-ready,exits,checks,config-*,
            run-summary.txt,trusted.log,candidate.log}
       traces/{principal.json,dsh-result.json}
       db/{broker.sqlite3,attempts.sqlite3,snapshot.json,paths.json}
       receipt/{rcpt-*.json,received-count.json,summary.json}
       uid-map/*、mountinfo/*、socket-stat/*、peercred/*、network-probe/*
       cleanup/{cleanup.json,ps-after.txt,residual-processes.json}
       commands.jsonl、summary.json
tool/  同结构；run/config-admission.json 记录 max_calls=2/fake_scenario=tool
tests/ {g3d.log,g3_bridge.log,g3c.log,gates.log,ruff.log,
        d1-04-peer-denied.log,d1-02-05-socket-mode.log,
        d1-11-poisoned-session.log,junit-*.xml}
```

Matrix：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv` 中
`D-G0-01..05`、`D-P0-01..03`、`D1-01..11` 共 **19 行**已填；D2/D3/REVIEW 行保持 `NOT_RUN`。

**STOP**：D1 Gate 材料已交付，等待 Lead 审计；不进入 D2，不 push，不 amend。
