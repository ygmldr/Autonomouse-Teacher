# M0 G3-D1 — Review Request（D1 Gate 最小复核请求）

> **对象**：Lead / 维护者；后续 D4 Independent Reviewer 只可在 Lead 授权后使用本材料。
> **性质**：这是**材料清单与最小复核请求**，不是 Independent Review 报告，不代表 G3-D PASS，不解锁 D2/D3/Live。
> **D1-C 实现**：`46e2407ab14a1867fddc7c3df17b72bdd0fb0bc7`（父 `aacb1d01d979a0d7140bce0311e39b4a03009637`）
> **Gate 运行 HEAD**：`46e2407`；**产品基线**：`4bd4803`；**D1-C Stage**：`artifacts/g3d/stage-20261117T195831Z`
> **Gate verdict（自评）**：`D1_GATE_PASS`；**复核状态**：`PENDING_LEAD_AUDIT`
> **Review Packet**：`artifacts/review-packet-g3d-d1-aacb1d0/`（START_HERE 首交）

---

## 0. 请求的最小裁定

请只对本 D1 Gate 作以下之一：

| 裁定 | 含义 |
|---|---|
| `D1_GATE_PASS` | R0–R5 全部成立；Echo + Tool 真实 PASS；账本/清理/0-Key 满足；允许进入 D2（仍需 Lead 另行授权）。 |
| `D1_GATE_PARTIAL` | Echo 真实 PASS，但 Tool / Resume / 某些证据不足；**不得**进入 D2，先决定修复或范围收缩。 |
| `D1_GATE_FAIL` | 任一 P0：Echo 失败、需放松安全限制、账本不一致、Cleanup/Canonical 失败、0-Key 失败、真实 DSH 无法连接。 |
| `BLOCKED_NEEDS_ENVIRONMENT` | 复核环境不满足（rootful Podman、cgroup v2、固定 rootfs/deps、空容器等）；不得用 Mock 替换。 |

**不接受**：仅凭 Owner 的 `summary.json` 标 PASS、用 host/raw-UDS/Mock 证据替代 real-DSH、把 D1-B 的旧 Run 当作 D1-C 证据、把未执行的 Resume/D2/D3 写成 PASS。

---

## 1. R0 — 身份、Stage 与不可变输入

请独立复算并确认：

| 检查 | 期望 |
|---|---|
| Git | 产品基线 `4bd4803…`；D1-A `51abc66`；D1-B `aacb1d0`；D1-C `46e2407`；`46e2407` 的父为 `aacb1d0`。 |
| `src/` | `git diff --stat 4bd4803 46e2407 -- src` 为空；D1-A 的 socket/peercred 改动只来自 `51abc66`。 |
| 冻结文件 | `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge` 相对基线无 diff。 |
| Stage | `artifacts/g3d/stage-20261117T195831Z/manifest.json` SHA-256 = `83b241c7…`；整体 tree = `9b6fc7b4…`；trusted/candidate = `c1c27eb5…` / `1474002f…`；57 / 6529 文件。 |
| Stage 来源 | Trusted 产品来自 `git archive 4bd4803`；Candidate 显式白名单；不是 G3-C `e6fde1c` stage，也不是 D1-B `b14de55a` stage。 |
| Rootfs / deps | `25491e45…` / `e07729d7…`，Run 前后一致。 |
| 容器 | 复核时 `podman ps -a` 空；无 `at-g3d-*`；无 `at-g3d` 进程/socket。 |

复核命令示例：

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD 46e2407 46e2407^
git diff --stat 4bd4803 46e2407 -- src spikes plugins scripts/g3c \
  tests/integration/g3c tests/integration/g3_bridge
sha256sum artifacts/g3d/stage-20261117T195831Z/manifest.json
python3 - <<'PY'
import sys; sys.path.insert(0, 'scripts/g3d')
import lib_g3d as lib
print(lib.sha256_tree('artifacts/g3d/stage-20261117T195831Z'))
print(lib.sha256_tree(lib.ROOTFS), lib.sha256_tree(lib.DEPS))
PY
podman ps -a --format '{{.Names}}'
```

---

## 2. R1 — Stage 实际加载 blob（不是“文件在目录里”）

请确认：

- `artifacts/g3d/d1/echo/peercred/trusted-modules.json`（及 tool 同名文件）中 10 个模块的 `file`/`real_path` 都在 `/project/src/autoteacher_m0/...`；
- 每个 `sha256` 等于 `git show 4bd4803:<path>` 的字节 SHA；
- `run/checks.json` 的 `trusted_modules_from_stage_and_git_blobs` 为 PASS；
- Candidate 的 `traces/principal.json` 中 `find_spec` 对 `autoteacher_m0`、`controller`、`broker`、`fake_backend` 均为 `None`，且 `/project/src` 不在 mountinfo。

建议独立从 Stage manifest 取 expected hash，再与容器内记录比对；不要只看 Launcher 的 `checks.json`。

---

## 3. R2 — Peercred / UID / Socket / Mount

请确认 D1-C 两次 Run 的以下原始证据（Echo 与 Tool 各一套）：

| 断言 | 证据 |
|---|---|
| socket `S_ISSOCK 0660 uid=0 gid=2000` | `socket-stat/before-candidate.json` |
| `ipc/` `2750 root:2000`（setgid） | `env/run-layout.json`、`env/preflight.json` |
| Trusted 日志 `mode=0660 gid=2000 uid=0 peer_uid=65534` | `peercred/trusted-log.json` / `trusted-log-extract.txt` |
| `bridge peer accepted uid=65534 gid=65534 pid=0` | 同上 |
| 无 `PEER_UID_DENIED` / `PEERCRED_UNAVAILABLE` | 同上 |
| Candidate host `Uid/Gid 65534`、`CapEff=0`、`NoNewPrivs=1` | `uid-map/runtime-identity.json`、`inspect-candidate.json` |
| Candidate `uid_map=0 65534 1`；`gid_map=0 65534 1` + `2000 2000 1` | `uid-map/candidate-*` |
| 挂载无 `/work/state`、`/output`、`/project/src`；`/work/g3b` 为 ro | `mountinfo/candidate.txt`、`traces/principal.json` |
| `--network none`；AF_INET/AF_INET6 `EACCES`；DNS 失败 | `run/inspect-*.json`、`network-probe/candidate-network.json` |
| cgroup `pids.max=256`、`memory.max=1073741824`、`cpu.max=100000 100000` | `uid-map/*-cgroup.json` |

**注意**：`pid=0` 在跨 PID namespace 时正常，不是“无 peer”；不要把它当失败，也不要把它当鉴权依据。

---

## 4. R3 — Echo / Tool 独立复跑

### 4.1 Echo

```bash
cd "/root/Autonomous Teacher"
/root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case d1-echo-review --scenario echo --session g3d-d1-review \
  --stage artifacts/g3d/stage-20261117T195831Z \
  --evidence-dir artifacts/g3d/review-d1/echo
```

预期：`exit 0`；`summary.status=PASS`；29 项检查全 PASS；1 Reservation/Claim/Attempt/Receipt/Settlement；Fake counter=1；DSH usage == receipt usage；`prepared==claim.request_digest`；`payload==receipt.raw_sha256`；`podman ps -a` 空。

### 4.2 Tool 两轮

```bash
/root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case d1-tool-review --scenario tool --session g3d-d1-review \
  --stage artifacts/g3d/stage-20261117T195831Z \
  --evidence-dir artifacts/g3d/review-d1/tool
```

预期：`exit 0`；`summary.status=PASS`；33 项检查全 PASS；2 Reservation/Claim/Attempt/Receipt/Settlement；Fake counter=2；`mode={tool_once,tool_final}`；DSH step 1/2 usage 分别等于对应 receipt usage；两对 Digest 各自成立；第二请求包含真实 `skill_lookup` 结果（`binary_search` / `m0-skills-v1`）。

> 每次复跑必须使用新的 `--evidence-dir`；Launcher 拒绝在已有数据的目录上覆盖。
> Reviewer 不得修改 Stage、Rootfs、Deps、`src/` 或 G3-C 冻结证据；复跑只读 Stage + 新建 `$RUN`。

### 4.3 Resume（可选，不阻塞 D1 Gate）

D1-C **未实现/未执行** Session Resume。Reviewer 若要检查，只能作为 D1 附加证据；失败不得被写成 PASS，也不得因此把 D1 Gate 从 PASS 降为 FAIL（按任务书：Resume 为可选附加）。

---

## 5. R4 — 账本对账

请独立从 `db/broker.sqlite3`、`db/attempts.sqlite3`、`receipt/rcpt-*.json` 复算，而不是只读 `checks.json`：

| 对象 | Echo 期望 | Tool 期望 |
|---|---|---|
| Reservation | 1 条，`status=OK`，`settlement.status=OK`，`reservation_exceeded=false`，cost>0 | 2 条，均 `OK`，各自 settlement OK，cost>0 |
| Claim | 1 条 `COMPLETED` | 2 条 `COMPLETED`，call/reservation 不重复 |
| Attempt | 1 条 `SETTLED` | 2 条 `SETTLED`，`mode=tool_once/tool_final`，attempt/call/reservation/receipt 两两不同 |
| Receipt / counter | 1 / 1 | 2 / 2 |
| Prepared 对 | `claim.request_digest == attempt.prepared_digest` | 逐 Attempt 成立，且两值不同 |
| Payload 对 | `attempt.payload_digest == receipt.raw_sha256` | 逐 Attempt 成立，且两值不同 |
| Usage | DSH usage == receipt usage | 两轮 DSH usage 分别 == 对应 receipt usage |
| 关联 | `attempt.reservation_id == claim.reservation_id`；`attempt.receipt_id` 指向对应 receipt | 同左，逐条成立 |
| 完整性 | `PRAGMA integrity_check=ok` | 同左 |

必须区分两对 Digest：**不得**要求 `claim.request_digest == receipt.raw_sha256`，也**不得**把两者合并成一条等式。

---

## 6. R5 — 清理、Canonical、0-Key / 0 网络 / LiveGate

| 检查 | 期望 |
|---|---|
| 容器清理 | `podman ps -a` 空；`at-g3d-*` 0；socket 不存在；run dir 不存在 |
| 进程 | 无 `autoteacher_m0.bridge.controller`、`fake_provider.py`、`candidate_entry.py`、`trusted_entry.py`、DSH runtime 残留 |
| Canonical | rootfs `25491e45…`、deps `e07729d7…`、stage tree `9b6fc7b4…` 前后相等 |
| 0-Key | host key-like env 0；容器 env 名白名单；无 `.env` 值 |
| 0 外网 | 两容器 `--network none --http-proxy=false --unsetenv-all`；无真实模型/HTTP |
| LiveGate | `run_live.sh` exit 3；`LiveGate().inspect(live_requested=True)=BLOCKED` |
| 证据级别 | real-DSH 证据放 `echo/`、`tool/`；host 测试证据单独放 `tests/`，不得混写为 real-DSH |

---

## 7. 禁止事项（复核者自身也不得做）

1. 不修改 `src/`、Stage、Rootfs、Deps、G3-C 冻结证据/Packet、历史 docs、D1-B 旧 Run。
2. 不 `podman pull`；不联网；不使用真实 Key/模型/外部付费 HTTP/Live。
3. 不通过以下方式“修好”失败：放宽 socket 到 0666、使用同 UID、挂载 `/work/state`、Mock DSH、关闭 peercred、把 host/raw-UDS 证据标成 real-DSH。
4. 不把 D1-B 的 `aacb1d0`/`b14de55a` 结果直接当 D1-C 结果；D1-C 必须绑定 `46e2407` + `stage-20261117T195831Z`（manifest `83b241c7…`）。
5. 不把 `D1_GATE_PASS` 解释为 D2/D3/G3-D/Live/G4/G5 授权。

---

## 8. 可接受裁定与后续

- 若 R0–R5 全部成立：Lead 可记录 `D1_GATE_PASS`，再单独授权 D2。
- 若 Tool 证据不足但 Echo 真实：只可 `D1_GATE_PARTIAL`；先修复/收缩范围。
- 若 Echo 失败或需放松安全：`D1_GATE_FAIL`；立即 STOP。
- 若环境不满足：`BLOCKED_NEEDS_ENVIRONMENT`；不得用 Mock 替代。
- 本请求不授权 push/amend；D1-C 提交保持线性和只含自己的路径。

**当前请求方结论**：`D1_GATE_PASS`，等待 Lead 审计。**STOP，不进入 D2。**
