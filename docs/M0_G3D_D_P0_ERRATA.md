# M0 G3-D D-P0 证据勘误与 OCI 可移植性收口

> **性质**：append-only 新文件。只记录 D-P0-01/02/03 的勘误、测试移植与复现事实；**不修改** `docs/REVIEW_G3C_INDEPENDENT.md`、`docs/REVIEW_G3C_INDEPENDENT_v2.md`、`docs/M0_G3C_REVIEW_ERRATA.md`、G3-C Packet v1/v2、旧矩阵或旧日志的任何字节。
> **不是** G3-D/D1/D2/D3、Live、G4/G5、M0 GO 的授权。`OS_TRUST_BOUNDARY=B0-02=BLOCKED` 与 G3-D 16 行 `NOT_RUN` 继续成立。D-P0 结束后 **STOP**，不进入 D1 实测。
> **范围**：只改测试、文档、可选 `scripts/g3c/` 辅助；**0 行 `src/` 改动**，0 Key、0 真实模型、0 外网、0 Live、无 `podman pull`。
> **开工基线**：`d74f2ff7a7477094b0a3ac68ea7d51fa2c30f22d`（开工时 `git status` clean）。产品源码在该提交与 `b2f6af054555705192c4e1ae3019a68078764736` 之间无差异（`git diff --stat b2f6af0 d74f2ff -- src` 为空；`src` 树 sha256 `934d73bd90a2d132707973aa349a558050ada3d020f9fb103b82e1c1a86d3bff`）。
> **并发工作区说明**：D-P0 执行期间，其他 Agent 在共享工作区先后产生未提交 `src/` 改动并提交了 `645190e`（D-G0）与 `51abc66`（D1-A）。本文件提交时的父提交因此不是 `d74f2ff`；D-P0 的**全量证据仍绑定 `d74f2ff` 冻结树**（见 §1.2），不受并发改动污染。

---

## 0. 结论摘要

| Case | 结论 | 关键事实 |
|---|---|---|
| **D-P0-01** | `DOCS_ONLY`，建议 `PASS` | v2 报告 §7 第 258 行把两对 Digest 串成一条等式；R4 代码实际分开比较，未比较错字段。新勘误 + 6 数据集/7 Attempt 独立探针，无 `src` 改动、无新增负例需求。 |
| **D-P0-02** | 建议 `PASS` | 两项 OCI 环境失败已消除：`pgrep` → `/proc`+`os.kill(pid,0)` 且有正/负对照；`/tmp` noexec wrapper → 可信 Python 解释器 + `PYTHONPATH` 只读导入。固定 OCI full **775 passed / 1 skipped / 0 failed，exit 0**；沙箱 flags 一条未减。 |
| **D-P0-03** | 建议 `PASS` | Packet v2 旧 R5 stage-only 命令仍冻结存在；仓库 overlay 脚本 `--rounds 1` 实测 1/1、loser exit 5、`CONTROLLER_SINGLETON_LOCKED`、0 traceback、Fake=1、Attempt `SETTLED`、canonical 前后一致。容器内 `inspect.getfile` 证明实际加载 `/probe/src` 的 `b2f6af0` blob，不是旧 stage `e6fde1c`。 |

**同一基线上的对照计数**（`d74f2ff` + 仅本 D-P0 两处测试改动）：

| 套件 | 结果 | exit | 说明 |
|---|---|---|---|
| 固定 OCI full | **775 passed / 1 skipped / 0 failed** | **0** | 0 意外失败；1 skip 是既有外部 probe mount skip。 |
| host full | **773 passed / 2 failed / 1 skipped** | **1** | 2 failed 仍是既有 host-only 环境限制（可写 config、硬编码 `/project`），**不是** D-P0 回归，也不称“全绿”。 |

---

## 1. 冻结输入、工作区隔离与身份

### 1.1 不修改的冻结对象

| 对象 | 身份 / 处理 |
|---|---|
| v2 报告 `docs/REVIEW_G3C_INDEPENDENT_v2.md` | 341 行，sha256 `f66f58c7b518a84117e520c220be907e885dde296d53eec503c8dc8091c7f71d`；本次**未改任何字节**。§7 原文行号按该 blob 计。 |
| `docs/M0_G3C_REVIEW_ERRATA.md` | sha256 `11c15db8e247485dd86af8abc90c2be3e89b710c0306be7004fa916cf8f3ba36`；未改。 |
| G3-D 任务书 `docs/Autonomous_Teacher_M0_G3D_Dual_Principal_Agent_Execution_Plan_v1.0.md` | sha256 `847deeacf127faee24e39a987361a192045906942979e84174cc5ad0c8321a02`；只读引用 §5/§12。 |
| G3-C Packet v2 `artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/` | 冻结；其 `reproduce/README.md` R5 原文保持旧 stage-only 命令，本文件只解释、不重写。 |
| 历史矩阵 / 旧日志 / v1 报告 | 未改；D-P0 不就地覆写任何历史证据。 |

### 1.2 全量证据的冻结树

并行 Agent 在共享工作区修改 `src/autoteacher_m0/bridge/controller.py`、`ipc_server.py` 并新增 `tests/integration/g3d/test_d1_socket_boundary.py` 后，工作区不再等于 `d74f2ff`。为满足“D-P0 证据不得混入 D1 实现”，全量套件在 **`git archive d74f2ff` 冻结树**中重跑，只覆盖本 D-P0 的两个测试文件：

```text
CLEAN_ROOT=/tmp/dp0-clean-HEAD
CLEAN_SRC_SHA=934d73bd90a2d132707973aa349a558050ada3d020f9fb103b82e1c1a86d3bff  # == b2f6af0 src tree
# 冻结树内 tests 只有本 D-P0 两文件相对 d74f2ff 变化；工作区额外的
# tests/integration/g3d/ 与 __pycache__ 未进入冻结树。
```

首次在工作区跑的 full 因已被并发 `src` 污染，**不作为 D-P0 证据**，隔离于 `artifacts/g3d/d-p0/contaminated/` 并在其 `README.md` 说明；D-P0 的有效 full 证据是 `oci-full-clean/` 与 `host-full-clean/`。

### 1.3 环境

| 项 | 值 |
|---|---|
| 主机 Python | `/root/.local/bin/python3.11`（3.11.15），所有 host 命令带 `-B`，`PYTHONDONTWRITEBYTECODE=1` |
| Podman | 4.9.3（固定 rootfs，rootful） |
| rootfs | `25491e45aa3dc54c526db9b9d46d18b31c7840150473e2fdb4d8b882f02fe9c0`（运行前后一致） |
| deps | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98`（运行前后一致） |
| G3-C stage | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0`（运行前后一致；D-P0 不写 canonical stage） |
| `podman ps -a` | 全部 D-P0 运行前后为空 |
| 0-Key / 网络 | 所有容器 `--network none --http-proxy=false --unsetenv-all`；未 `podman pull`；无真实 Key/模型/外网/Live |

---

## 2. D-P0-01：两种 Digest 的规范关系与 v2 §7 勘误

### 2.1 规范关系（以此为准）

```text
PreparedProviderRequest.request_digest == BrokerClaim.request_digest
FakeOutboundPayload_SHA256            == FakeReceipt.raw_sha256
```

两对 Digest 用途不同：

| 对 | 保护的字节 | 产出 / 存储 | 核对位置 |
|---|---|---|---|
| Prepared 对 | 语义请求（`PreparedProviderRequest` 的 canonical 文档，决定 Claim 语义） | Controller `prepared_request_digest(prepared)`；`budget_dispatch_claims.request_digest`；`g3b_attempts.prepared_digest` | claim 请求与 Attempt 记录 |
| Payload 对 | **实际获准发送的 Fake 出站字节**（含 `nonce`、`mode`、`prepared_digest` 等） | `sha256(payload_bytes)`；`g3b_attempts.payload_digest`；Fake 的 `rcpt-<nonce>.json.raw_sha256`；journal 文档 `receipt.raw_sha256` | Fake receipt 校验与 reconcile |

**禁止**把两对合并为一条等式，或要求 `Prepared.request_digest == FakeReceipt.raw_sha256`。二者输入字节不同，实际也全部不相等（§2.4 探针 7/7）。**必须**保留关联字段：

| 关联字段 | 位置（至少） |
|---|---|
| `call_id` | Prepared / EgressRequest / `g3b_attempts` / `budget_dispatch_claims` |
| `reservation_id` | `g3b_attempts` / `budget_reservations` / `budget_dispatch_claims` |
| `attempt_id` | `g3b_attempts` / journal 文档 |
| `nonce` | journal `receipt.nonce` / `rcpt-<nonce>.json` / payload 内容 |
| `receipt_id` | journal `receipt.receipt_id` / `rcpt-<nonce>.json` / `g3b_attempts.receipt_id` |

源码依据（`d74f2ff`，与 `b2f6af0` 相同）：

| 位置 | 事实 |
|---|---|
| `src/autoteacher_m0/bridge/controller.py:376-377` | 由 canonical Prepared 请求计算 `prepared.request_digest`。 |
| `controller.py:647` | Fake payload 文档写入 `"prepared_digest": prepared.request_digest`（关联，不是相等）。 |
| `controller.py:655` | `payload_digest = sha256(payload_bytes)`。 |
| `controller.py:790-792` | 收到 Fake 后校验 `receipt.raw_sha256 == payload_digest`、`sent_digest == payload_digest`、长度与 nonce；不比对 claim digest。 |
| `controller.py:1121-1143` | journal 文档分别保存 `prepared_digest`、`payload_digest`、`receipt.raw_sha256` 与关联字段。 |
| `src/autoteacher_m0/bridge/attempts.py:406` | reconcile 用 `doc.raw_sha256 == row.payload_digest` 认领 receipt。 |
| `src/autoteacher_m0/accounting/broker.py:338` | Broker 把 claim 的 `request_digest` 传给 `claim_dispatch` 持久化。 |

### 2.2 v2 报告 §7 原文行号与勘误对照

v2 报告原文（`docs/REVIEW_G3C_INDEPENDENT_v2.md`）§7 位于 **第 242–264 行**；本次**不修改**其文字/字节。

| v2 行号 | 原文（保持不变） | 判定 |
|---|---|---|
| **258** | ``- `payload_digest == prepared.receipt.raw_sha256 == broker claim.request_digest`；`raw_length` 与 payload_length/receipt 文件一致；`` | **文字错误**：把 Payload 对与 `claim.request_digest` 串成一条链；且 `prepared.receipt` 不是 Prepared 的字段。应按 §2.1 拆成两对。 |
| 248 | `raw_sha=payload_digest，nonce 匹配` | 正确：属于 Payload 对。 |
| 257 | `usage_digest == sha256(canonical(usage))`；`observation_digest == ...` | 正确，与 Digest 两对无关。 |
| 259 | receipt 文件 nonce/receipt_id/raw_sha256/usage 与 journal 一致 | 正确：属于 Payload 对 + 关联字段。 |
| 264 | `call→reservation→claim→attempt→receipt→observation→broker→cost 一一映射` | 正确：这正是“两对不同、关联字段保留”的结论。 |

**v2 报告字节不变**：341 行，sha256 `f66f58c7b518a84117e520c220be907e885dde296d53eec503c8dc8091c7f71d`。

### 2.3 R4 脚本实际比较逻辑（DOCS_ONLY 判定）

`artifacts/reviewer-g3c-v2/r4-crosscheck/r4_crosscheck.py` 的实际字段比较：

| R4 行号 | 代码比较 | 对应关系 |
|---|---|---|
| 115-117 | `claim["request_digest"] == row["prepared_digest"]` | **Prepared 对**（Claim ↔ Attempt），正确。 |
| 122-124 | `doc["payload_digest"] == row["payload_digest"] == doc["receipt"]["raw_sha256"]` | **Payload 对**（journal ↔ Attempt ↔ receipt），正确。 |
| 125-126 | `doc["prepared_digest"] == row["prepared_digest"]` | Prepared 对在 journal 侧的一致性，正确。 |
| 138-145 | `receipt_file.raw_sha256/nonce/receipt_id/raw_length/usage` 与 journal 比对 | Payload 对 + 关联字段，正确。 |
| 197-201 | `all_digests_ok` 仅聚合 `usage_digest`、`observation_digest`、`payload_digest_chain`、`prepared_digest_chain` | **未**把 `claim_digest_matches` 纳入总 `pass`；这是覆盖度注记，不是“比较错字段”。 |

**结论**：R4 **没有**把 `claim.request_digest` 与 `receipt.raw_sha256` 相比，也没有把 `payload_digest` 与 `claim.request_digest` 相比。代码正确，仅 v2 §7 第 258 行文字错误 → **`DOCS_ONLY`**；不新增产品负例测试，不改 `src/`。`claim_digest_matches` 已逐 Attempt 写入 `r4-crosscheck.json` 且 7/7 为 true；D3 若需要“总闸门”，应显式把它加入聚合（遗留建议，不阻断）。

### 2.4 独立探针（不修改冻结证据）

探针 `artifacts/g3d/d-p0/digest_pair_probe.py` 把 SQLite 复制到临时目录后只读查询（不在 Packet/证据副本上打开），覆盖 v2 R4 同六组：

```text
datasets=6  attempts_checked=7  datasets_passed=6  pass=true
checks per attempt (7/7 true):
  prepared_eq_claim_request   doc.prepared_digest == row.prepared_digest == claim.request_digest
  payload_eq_receipt_raw      doc.payload_digest == row.payload_digest == doc.receipt.raw_sha256 == rcpt.raw_sha256
  prepared_ne_payload         prepared_digest != payload_digest
  claim_ne_receipt_raw        claim.request_digest != receipt.raw_sha256
  ids_linked                  call_id / reservation_id / attempt_id / nonce / receipt_id 五字段跨表一致
```

示例（`rv2-echo`，仅前缀）：prepared=claim=`23a0673fa21e23b6…`，payload=receipt=`f99e53b9b64252b1…`；两对各自相等、互不相等。原始输出：`artifacts/g3d/d-p0/digest-pair-probe.json`（sha256 `1f10fbfdcf45de6570931325873ff79641100f88b15db0c2569b8af5222d0443`）。

---

## 3. D-P0-02：OCI 两项可移植性修复（不放宽沙箱）

### 3.1 RED（修复前，固定 OCI）

| 证据 | argv / 结果 |
|---|---|
| 新跑 RED `artifacts/g3d/d-p0/red-oci-targeted/red-oci-targeted.log`（sha256 `176addf8…`） | `pytest` 两个 node id，固定 rootfs、`--read-only --read-only-tmpfs=false`、`--user 65534`、`/tmp` noexec；**2 failed，exit 1**。错误分别是 `FileNotFoundError: 'pgrep'` 与 `PermissionError: '/tmp/.../slow-broker-wrapper'`。 |
| 历史 RED `artifacts/g3c/regression/pr1-oci-full.log` | 同一根因：`773 passed / 2 failed / 1 skipped`，exit 1；`pgrep` 不存在、wrapper noexec。 |

历史/新 RED 的完整 argv、UTC、exit、rootfs-after 均保存在上述日志；RED 运行前同一环境 hash 已核验 canonical（§1.3），log 记录的 `ROOTFS_AFTER` 也回到 canonical。

### 3.2 修复 1：进程清理不依赖 `pgrep`

文件 `tests/integration/g3c/test_c1_03_admission.py`（+68/−3）：

- 新增 `_proc_cmdline_snapshot()`（第 626 行）：枚举 `/proc/<pid>/cmdline`；`/proc` 不可读、没有数字 PID、或全部 `cmdline` 不可读时 **`pytest.fail("ENV_PROBE_UNAVAILABLE: …")`**，不产生假 PASS。
- 新增 `_pids_matching(marker)`（第 660 行）：用 `cmdline` 匹配 + `os.kill(pid, 0)` 确认存活；`ProcessLookupError`/`PermissionError` 跳过。
- `test_c3_01e…`（第 674 行）增加**正对照**：SIGTERM 前必须用同一 `/proc` 探针找到 broker 子进程（`broker.json` marker），否则 `ENV_PROBE_NO_BROKER` 显式失败；SIGTERM 后再轮询到 0 个匹配 PID。这样“找不到 broker”不会因 `/proc` 探针坏掉而假 PASS。
- 该检查不依赖容器内工具，也不读取/修改 `/proc` 以外的状态；`os.kill(pid, 0)` 仅做存在性检查，不发信号。

### 3.3 修复 2：`/tmp` noexec 下不 exec wrapper

文件 `tests/integration/g3c/test_c3_02_deadline.py`（+25/−12；两文件合计 +93/−15）：

- `_make_slow_broker(tmp_path, monkeypatch)`（第 53 行）不再写 `#!/bin/sh` 并 `chmod +x` 的 wrapper。改为在 `tmp_path/shadow/autoteacher_m0/accounting/broker.py` 放慢 Broker 模块，`monkeypatch.setenv("PYTHONPATH", shadow)` 后由 **`sys.executable`（固定 rootfs 的可信 Python）** 以 `-B -m autoteacher_m0.accounting.broker` 读取并执行。
- Python 只 **read** 该模块，不 `execve` 它；因此在 noexec `/tmp` 上可运行，且不需要任何额外可执行文件、不需要把 wrapper 拷到可执行 stage。
- `monkeypatch` 在测试结束恢复 `PYTHONPATH`；pytest 进程本身不被 shadow 包影响。
- 测试断言（`BrokerTimeoutError.code == "BROKER_TIMEOUT"`、0.80–3.0 s、只 1 次 `REQ`、超时后 fail-closed 不重发）全部保留。

### 3.4 沙箱 flags 未放宽（逐项）

| flag | D-P0 后 |
|---|---|
| `--read-only` / `--read-only-tmpfs=false` | 保留 |
| `--tmpfs /tmp:rw,noexec,nosuid,nodev,…` | 保留 noexec（**没有**为了 wrapper 去掉 noexec） |
| `--cap-drop ALL`、`--security-opt no-new-privileges` | 保留 |
| `--network none --http-proxy=false --unsetenv-all` | 保留 |
| `--user 65534:65534`、`--pids-limit`、`--memory`、`--cpus`、`--timeout` | 保留 |
| 容器内新增安装/包/pull | 无 |

### 3.5 GREEN

| 检查 | 结果 |
|---|---|
| 固定 OCI targeted（RED 同一 argv） | **2 passed，exit 0**；`green-oci-targeted.log`（sha256 `760ea100…`），rootfs before/after canonical。 |
| host targeted（clean HEAD 树） | **2 passed，exit 0**；`host-targeted/host-targeted.log`。 |
| 固定 OCI full（clean 冻结树 + 本 D-P0 测试） | **775 passed / 1 skipped / 0 failed，exit 0**；`oci-full-clean/oci-full-clean.log`（sha256 `19b99145…`）；rootfs/deps/stage 前后 canonical；`podman ps -a` 空。1 skipped 为既有外部 probe mount skip，不是失败。 |
| host full（clean 冻结树 + 本 D-P0 测试） | **773 passed / 2 failed / 1 skipped，exit 1**；`host-full-clean/host-full.log`（sha256 `54545ee6…`）。2 failed 是既有 host-only 环境限制，**host 不称全绿**。 |

### 3.6 环境探针（证明 RED 根因与修复可行）

`artifacts/g3d/d-p0/env-probe-raw.log`（容器内，uid 65534）：

```text
pgrep                      = null
proc_mounted               = true
tmp_exec                   = PermissionError: [Errno 13] Permission denied (noexec)
python_script_from_tmp     = rc 0, "PYTHON_READ_FROM_TMP_OK"
shadow_module_from_tmp     = rc 0, "SHADOW_BROKER_IMPORT_OK"
os_kill0_alive             = true
uid                        = 65534
```

### 3.7 `KNOWN_ENV_LIMITATION` / 残余

- **固定 OCI full：无 `KNOWN_ENV_LIMITATION`，0 意外失败**（本次已达到任务书 §5.2 的理想门槛）。不把“0 failed”写成“全部测试都跑且都 PASS”：仍有 1 个既有 skip。
- **host full：2 个既有 host-only 环境失败仍在**，逐项为：
  1. `tests/integration/runtime/test_target_profile_static.py::test_required_files_exist_and_are_read_only_text`：宿主 `config/dsh/*` 不是只读文件；OCI stage 中由 0444 满足。
  2. `tests/integration/sandbox/test_live_controller_no_key.py::test_all_live_entrypoints_remain_blocked`：测试硬编码 `PYTHONPATH=/project/src:/deps`，宿主无 `/project`。
  - 二者是 D-P0 之前即记录的环境限制，不是本次测试改动引入，也**没有**通过放宽权限/改断言掩盖。
- 一次全量尝试在 pytest `sessionfinish` 写 `/evidence` junit 时遇到 transient `EROFS`（测试进度已 100%、无 F）；同一 argv 重跑成功。该现象未复现，**不**登记为产品/环境限制；有效证据以 `oci-full-clean` 为准。

### 3.8 矩阵填表交接（D-P0 行仍 `NOT_RUN`）

按任务书 §12，历史 CSV 不就地覆写；以下值供 Lead/Evidence Owner 填入 **G3-D 工作矩阵**，D-P0 自身不把行改成 PASS。

| case_id | observed（建议） | command_argv（摘要） | exit | evidence_paths | code_sha |
|---|---|---|---|---|---|
| D-P0-01 | 两对 Digest 分开；R4 代码正确，v2 §7:258 文字勘误；6 数据集/7 Attempt 探针全 true | `python -B artifacts/g3d/d-p0/digest_pair_probe.py …` | 0 | `docs/M0_G3D_D_P0_ERRATA.md` §2；`artifacts/g3d/d-p0/digest-pair-probe.json` | `d74f2ff`（docs/test-only） |
| D-P0-02 | RED 2 failed → targeted 2 passed；固定 OCI full 775/1/0 | 见 §3.1/§3.5 日志内完整 argv | 1→0 | `red-oci-targeted/`、`green-oci-targeted/`、`oci-full-clean/`、`host-full-clean/` | `d74f2ff` + 本 D-P0 测试 |
| D-P0-03 | overlay 1/1；loser exit 5、0 traceback、Fake=1；loaded src blobs == `b2f6af0` | `bash scripts/g3c/reproduce-coldstart-with-src-overlay.sh --rounds 1 …` | 0 | `repro-overlay-1/`、`overlay-module-identity.log` | `b2f6af0`（impl） |

---

## 4. D-P0-03：源码 Overlay 复现说明

### 4.1 Packet v2 旧 R5 仍然存在（冻结，不重写）

- 冻结位置：`artifacts/review-packet-g3c-b2f6af054555705192c4e1ae3019a68078764736/reproduce/README.md`，§R5 第 97 行起。
- 旧命令仍使用 `STAGE=$PWD/artifacts/g3c/stage`（第 101 行）、`--env PYTHONPATH=/probe/src:/deps` 与 `--mount "type=bind,src=$STAGE,dst=/probe,ro=true"`（第 108 行），即**只挂冻结 stage**。
- 该 stage 的 `src/autoteacher_m0/bridge/attempts.py` sha256 为 `33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167`，属于 `e6fde1c` 旧批次（先 `journal_mode=WAL` 后 `busy_timeout`），照抄 R5 会复现 v1 P1-2 的 `database is locked` traceback；不能用它证明 PR1 后的 `b2f6af0`。
- **本 D-P0 不修改 Packet v2 的 README/manifest/hash**。旧命令“仍然存在”是一段冻结历史限制，不是当前推荐入口。

### 4.2 主入口：仓库现有 overlay 脚本

```bash
bash scripts/g3c/reproduce-coldstart-with-src-overlay.sh --rounds 1 \
  --out artifacts/g3d/d-p0/repro-overlay-1
```

脚本事实（源码已存在，本 D-P0 未改其逻辑）：

1. 校验 canonical rootfs/deps/stage；不匹配 exit 2。
2. 复制冻结 stage 到临时 overlay，删除 `src/`，用 `git archive b2f6af0 src` 解出；校验 overlay `attempts.py` 与 `b2f6af0` blob 一致、含 `INIT_BUSY_TIMEOUT_MS = 250`/`_initialize`，且与 stage 旧文件不同。
3. 以固定 rootfs、`--network none`、uid 65534、只读 rootfs、`/tmp` noexec 跑双 Controller 冷启动。
4. 校验 loser exit 5 / `CONTROLLER_SINGLETON_LOCKED` / 0 traceback / Fake=1 / 1 receipt / Attempt `SETTLED` / reservation `OK` / claim `COMPLETED` / admission=1 / winner SIGTERM 0 / socket 删除。

### 4.3 实测（`--rounds 1`，UTC 2026-11-17T18:40:17Z）

```text
stage_src_attempts_sha   = 33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167  (old stage)
overlay_src_attempts_sha = ccd008bd55bda8d344152856912dbde9dfe1e29d5accb53973a938e1e4b59795  (== b2f6af0)
SUMMARY {"attempt_states": ["SETTLED"], "fail": 0, "fake_counters": [1],
         "loser_codes": ["CONTROLLER_SINGLETON_LOCKED"], "loser_exits": [5],
         "pass": 1, "rounds_completed": 1, "rounds_requested": 1, "tracebacks": 0}
COLDSTART_OVERLAY_OK rounds=1
rootfs_after=deps_after=stage_after = canonical (25491e45… / e07729d7… / fcdb0de4…)
podman_ps= (empty)   SCRIPT_EXIT=0
```

证据：`artifacts/g3d/d-p0/repro-overlay-1/run.log`（sha256 `66ff4474…`）、`repro.env`、`podman.log`、`coldstart-src-overlay-b2f6af054555-1.json`（sha256 `e4ebb1fd…`）。

### 4.4 容器内实际加载模块（补充证据）

用同一 stage+b2f6af0 overlay 构造、同一 fixed rootfs / `PYTHONPATH=/probe/src:/deps` 运行 `inspect.getfile`，结果（`artifacts/g3d/d-p0/overlay-module-identity.log`，sha256 `37da82d0…`）：

```text
sys.path      = ["", "/probe/src", "/deps", ...]
attempts.py   = /probe/src/autoteacher_m0/bridge/attempts.py   sha256 ccd008bd…  == git show b2f6af0:…
controller.py = /probe/src/autoteacher_m0/bridge/controller.py sha256 cbec21f7… == git show b2f6af0:…
ipc_server.py = /probe/src/autoteacher_m0/bridge/ipc_server.py sha256 168bcc02… == git show b2f6af0:…
```

即实际加载的是 `b2f6af0` 源码，不是旧 stage `e6fde1c`；`attempts.py` 新旧 hash 明确不同。

### 4.5 D1 Packet 规则

- D1 Packet **不得复制** Packet v2 `reproduce/README.md` 的 stage-only R5 命令。
- D1 必须构建独立的 `{trusted,candidate}` stage，并在运行期用 `inspect.getfile()` + 文件原始字节 sha256 对照经批准实施 SHA（任务书 §4.2）；仅 `git rev-parse` 或旧 Packet hash 不算。
- 冷启动/P1-2 复现主入口继续使用 `scripts/g3c/reproduce-coldstart-with-src-overlay.sh`（或 D1 自己的等价 overlay 步骤），并记录 overlay 与冻结 stage 的 hash 差异。

---

## 5. 证据索引（`artifacts/g3d/d-p0/`，新目录，不覆盖旧证据）

| 路径 | sha256 | 内容 |
|---|---|---|
| `red-oci-targeted/red-oci-targeted.log` | `176addf802f3c251b53cc7dca1d33292c8ebf872d6c0a69e40700206c4519ebe` | 修复前固定 OCI 两失败原始 log/argv/exit。 |
| `green-oci-targeted/green-oci-targeted.log` | `760ea100c7c53ee24b294e3ddc352937d31c654462f70f8f36148edf468787b9` | 修复后同 argv 两 passed。 |
| `oci-full-clean/oci-full-clean.log` | `19b99145247af4b813cc5434d3c423fe5dded536f07e2e5eaca84d181f7ba3d2` | 冻结树固定 OCI full 775/1/0。 |
| `host-full-clean/host-full.log` | `54545ee69aa785b5f1ae69695fc3b2cb086e5ce072f8b0da448b2459e25d35b6` | 冻结树 host full 773/2/1。 |
| `host-targeted/host-targeted.log` | `d69daac911be8e49b9a179935c79c7124878eb48c50b1cb166682a2a8a7f14a1` | 冻结树 host 两 targeted passed。 |
| `digest-pair-probe.json` | `1f10fbfdcf45de6570931325873ff79641100f88b15db0c2569b8af5222d0443` | 6 数据集/7 Attempt 两对 Digest 探针。 |
| `repro-overlay-1/run.log` | `66ff447496db4485376da1efcaf2d7acd4a4d25dc67b95e47c26600fe7c36865` | overlay `--rounds 1` 实测。 |
| `repro-overlay-1/coldstart-src-overlay-b2f6af054555-1.json` | `e4ebb1fd34f18f65239d05e8c84e2ec4179b1d6716954f22212f500ad3da53e2` | 每轮/汇总 JSON。 |
| `overlay-module-identity.log` | `37da82d08265790b87de551330c9070be9256c2f67c046bd0f92fc558d8a7a1b` | `inspect.getfile` + loaded sha256。 |
| `env-probe-raw.log` | `5840a730a2f92e2fcde5c0c4702efac5d1088186dd751867dfa0c77bb63790ad` | no pgrep / noexec / `/proc` / shadow import 探针。 |
| `final-state.log` | `83d2c0532fe5a191977b19d1d603846a92e70f30da33b648cf1241832a8fd556` | 最终 canonical / podman ps / git status。 |
| `clean-tree-identity.log` | `701a906e5273b871485c3f7f64068e6602002d6e19c3f58d968ee3198113f289` | 冻结树身份与并发差异。 |
| `contaminated/README.md` | — | 工作区 full 被并发 `src` 污染，隔离且不作 D-P0 证据。 |

JUnit：`evidence/junit-red-oci-targeted.xml`、`junit-green-oci-targeted.xml`、`junit-oci-full-clean.xml`、`junit-host-full-clean.xml`。

---

## 6. 不主张 / 未验证 / 残余

1. **不主张 G3-D/D1/D2/D3 通过**：D0-01、D1-01、D2-01..12、D3-01、D-REVIEW-01 仍 `NOT_RUN`；`OS_TRUST_BOUNDARY=B0-02=BLOCKED`。本文件只完成 D-P0，STOP。
2. **不主张 Live/GO**：0 Key、0 真实模型、0 外网、0 真实 Provider HTTP；Fake usage/cost 仍是 synthetic fixture；未 `podman pull`；未启动 D1 双 Principal 实测。
3. **不主张产品行为改变**：D-P0 无 `src/` 改动；固定 OCI full 的 0 失败是“测试可移植性”结果，不是新增产品契约证据。
4. **host 仍有 2 个既有环境失败**（§3.7）；没有把它们修成通过，也没有改断言/放宽权限掩盖。
5. **R4 聚合覆盖度**：`claim_digest_matches` 未纳入 `all_digests_ok`（§2.3），属 D3 可选加固，不是本次文字勘误的阻断项。
6. **Overlay 脚本限制**：`--rounds 1` 是冒烟，不是独立复核；脚本验证的是 `b2f6af0` 源码 overlay，不能替代 D1 自己的 stage manifest 与运行期 `inspect.getfile` 证据。Packet v2 冻结字节未变。
7. **并发工作区**：D-P0 的 commit 可能落在其他 Agent 的提交之后（见文件头）；D-P0 基线证据仍以 §1.2 冻结树为准。D-P0 未 stage/提交他人的 `src/`、`tests/integration/g3d/` 或 docs 改动。

---

*本文件由 D-P0（Digest errata / OCI portability）Agent 追加；只 add 自身路径与 `tests/integration/g3c/` 两处测试修正；未 amend、未 push、未改产品源码、未改冻结报告/Packet/历史矩阵/旧日志。*
