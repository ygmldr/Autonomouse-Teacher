# M0 G3-D2 — Review Request（D2 Gate 最小复核请求）

> **对象**：Lead / 维护者；D4 Independent Reviewer 只能在 Lead 授权后使用本材料。
> **性质**：这是**材料清单与最小复核请求**，不是 Independent Review 报告，不代表 G3-D PASS，不解锁 D3/Live。
> **D2 实现提交**：`6e02c72836f1ade38ff65f7fa2ffa32826b1998a`（父 `5c12851284d0a9416f9ca38bac1b3a0a61e6c0d0`）
> **产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`（`src/` 0 改动）
> **Stage**：`artifacts/g3d/stage-20261117T210738Z`（manifest `6f8f0490…`，整体 tree `e0ef085a…`）
> **Gate verdict（自评）**：`D2_GATE_PASS`；**复核状态**：`PENDING_LEAD_AUDIT`
> **证据根**：`artifacts/g3d/d2/`（19 个 Run，全部 exit 0）

---

## 0. 请求的最小裁定

| 裁定 | 含义 |
|---|---|
| `D2_GATE_PASS` | D2-01..15 全部成立；旧四绕过关闭；D2-11 Echo/Tool/Resume 真实 PASS；账本/清理/0-Key 满足；允许进入 D3（仍需 Lead 另行授权）。 |
| `D2_GATE_PARTIAL` | 大部分攻击 PASS，但某项证据不足（例如 Resume / cgroup / stale Run）；**不得**进入 D3，先决定修复或范围收缩。 |
| `D2_GATE_FAIL` | 任一 P0：Candidate 直接读/写可信资产、借 Broker Claim、重绑 Trusted Socket、正向 DSH 被误伤、账本不可信变化、清理/Canonical/0-Key 失败。 |
| `BLOCKED_NEEDS_ENVIRONMENT` | 复核环境不满足（rootful Podman、cgroup v2、固定 rootfs/deps、空容器）；不得用 Mock/同 UID 替换。 |

**不接受**：只看 Owner `summary.json` 标 PASS；用 host/raw-UDS/Mock 替代 real-Candidate；把 D2-13 CONTROL 当作正式 Candidate 配置；把未执行的 D3/reconcile 写成 PASS。

---

## 1. R0 — 身份、Stage 与不可变输入

| 检查 | 期望 |
|---|---|
| Git | HEAD/实现 `6e02c72`；父 `5c12851`；`src/` 相对 `4bd4803` 无 diff。 |
| 冻结文件 | `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge` 无 diff；G3-C 矩阵未改。 |
| Stage | manifest SHA-256 `6f8f0490…`；整体 tree `e0ef085a…`；trusted/candidate `b17a8f6d…` / `3e6adc9f…`；57 / 6543 文件。 |
| Stage 来源 | Trusted 来自 `git archive 4bd4803`；Candidate 显式白名单 + 14 个 `run/probes/*.py`；adapter `2cb42461…`。 |
| 容器 | 复核开始时 `podman ps -a` 空；无 `at-g3d-*`。 |
| 证据 | 19 个 Run 的 `summary.json` `status=PASS`、`exit_code=0`、`cleanup.ok=true`、`canonical=true`。 |

```bash
cd "/root/Autonomous Teacher"
git rev-parse HEAD HEAD^
git diff --stat 4bd4803 HEAD -- src spikes plugins scripts/g3c \
  tests/integration/g3c tests/integration/g3_bridge
sha256sum artifacts/g3d/stage-20261117T210738Z/manifest.json
podman ps -a --format '{{.Names}}'
cat artifacts/g3d/d2/results.jsonl
```

---

## 2. R1 — Attack 身份真实性与 Probe 白名单

请确认：

- `artifacts/g3d/d2/d2-0*/run/argv-candidate.json` 中 hold 容器 argv 含 `--uidmap 0:65534:1 --gidmap 0:65534:1 --gidmap 2000:2000:1 --group-add 2000`、`--network none`、`--cap-drop ALL`、`--read-only`；无 `/work/state`、`/output`、`/project/src`。
- `uid-map/candidate-uid_map.txt` = `0 65534 1`；`uid-map/candidate-status.txt` 的 Host `Uid/Gid` = 65534、`CapEff=0…0`、`NoNewPrivs=1`、`Seccomp=2`。
- `mountinfo/candidate.txt` 无 state/output/src。
- 每个 `attacks/d2_*.json` 的 `record.argv` 是真实 `podman exec … /project/run/probes/<audited>.py`，且 `document.identity` 记录同一 UID map/挂载。
- Stage 中只有 `run/candidate_entry.py` + `run/probes/{probe_common,d2_01..d2_14}.py` 是 Python；`forbidden_candidate_reasons` 白名单测试通过。

```bash
python3 - <<'PY'
import json, pathlib
p = pathlib.Path('artifacts/g3d/d2/d2-01')
print(json.loads((p/'run/argv-candidate.json').read_text())['argv'])
print((p/'uid-map/candidate-uid_map.txt').read_text())
print((p/'uid-map/candidate-status.txt').read_text())
PY
grep -n "work/state\|output\|project/src" artifacts/g3d/d2/d2-01/mountinfo/candidate.txt || echo "no forbidden mount"
PYTHONPATH="/root/Autonomous Teacher/src:/root/Autonomous Teacher/artifacts/foundation/deps" \
  /root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider \
  tests/integration/g3d/test_d2_contract.py
```

---

## 3. R2 — 旧四绕过关闭（D2-01/02/03/04/05/06）

| 断言 | 证据 |
|---|---|
| Candidate 无 state 挂载 | `d2-01/d2/probe-d2_01.json` `state_mounts=[]`；`mountinfo/candidate.txt` |
| 读 DB/WAL/SHM 全部 `ENOENT(2)` | `probe-d2_01.json` 的 7 个 `open_rdonly:*` |
| 写/截断/替换 DB 全部拒绝 | `d2-02/d2/probe-d2_02.json` 42 ops，`ENOENT/EROFS/EXDEV` |
| Policy/Admission/Attempt/Receipt 拒绝 | `d2-03` 60 ops 全 `ENOENT(2)`；`state/pre.json` vs `state/final.json` |
| Broker 模块/入口/私有 Socket 不可达 | `d2-04` imports、`connect:*`、`code_search`、`fd_targets` |
| 直接 Reserve/Claim/Fake 被拒 | `d2-05` `negatives`：`UNKNOWN_KIND`/`UNKNOWN_FIELD`；负例后 0 行；随后正向 1 行 |
| 伪造 admission/authorized/call_id/route/tools/坏帧被拒 | `d2-06` 18 个负例 code 与 `socket_ops` |
| DB 前后 Hash 不变 | 各 Run `state/pre.json` vs `state/final.json` 的 `data_digest`、`broker.sqlite3` 逐文件 SHA |

```bash
for c in d2-01 d2-02 d2-03; do
  python3 - <<PY
import json
p='artifacts/g3d/d2/$c'
pre=json.load(open(p+'/state/pre.json')); post=json.load(open(p+'/state/final.json'))
print('$c', pre['data_digest']==post['data_digest'],
      [r for r in post['files'] if r['path'].endswith('broker.sqlite3')])
PY
done
```

---

## 4. R3 — D2-11 正向 + Resume + D2-15 Digest

| 项 | 期望 |
|---|---|
| Echo | 1 Reservation/Claim/Attempt/Receipt/Settlement、counter=1；DSH usage == receipt usage。 |
| Tool | 2 套独立账本、`mode={tool_once,tool_final}`、counter=2；第二请求含 `binary_search`/`m0-skills-v1`。 |
| Resume | 两个不同容器/进程共享同一 session；turn2 `resume.used=true`、SDK `resume_session`、session JSONL 14→24 行、`reason:"resume"` ≥1；2 SETTLED、counter=2、input_bound 增大、无旧 Attempt 重放。 |
| D2-15 | `claim.request_digest == attempt.prepared_digest`；`receipt.raw_sha256 == attempt.payload_digest`；两对不合并。 |

```bash
for c in d2-11-echo d2-11-tool d2-11-resume d2-15; do
  python3 -c "import json;d=json.load(open('artifacts/g3d/d2/$c/db/snapshot.json'));print('$c',len(d['reservations']),len(d['attempts']))" 2>/dev/null || \
  python3 -c "import json;d=json.load(open('artifacts/g3d/d2/$c/db/final.json'));print('$c',len(d['reservations']),len(d['attempts']))"
done
cat artifacts/g3d/d2/d2-11-resume/traces/dsh-result-turn2.json | \
  python3 -c "import json,sys;d=json.load(sys.stdin);print(d['resume'])"
```

---

## 5. R4 — D2-12 cgroup / D2-13 CONTROL / D2-14 stale Run

| 项 | 期望 |
|---|---|
| D2-12 | stress probe 读到 `pids.max=8`、`memory.max=134217728`、`cpu.max=100000 100000`；fork 7 后 `EAGAIN`；memory 到 120MB 后 exit 137；fd 4093 后 `EMFILE`；8 连接后 `TOO_MANY_CONNECTIONS`；16 超大帧 `FRAME_TOO_LARGE`；Trusted fds/threads 12/1 不变；仅 1 套账本。 |
| D2-13 | 标记 `CONTROL`；`state_mounts` 为 `ro,relatime`；所有 state 读写 `EACCES(13)`；目录写 `EISDIR(21)`；哈希不变。**不得**当正式 Candidate 配置。 |
| D2-14 | stale 容器 UID map 相同；`/work/g3b` 为 stale-ipc；stale socket `ECONNREFUSED`；live path `/proc/1/root`/相对路径全 `ENOENT`；live inode ≠ stale inode；live listener 仍在。 |

```bash
python3 -c "import json;d=json.load(open('artifacts/g3d/d2/d2-12/d2/probe-stress-fork.json'));print(d['limits'],d['ops'])"
python3 -c "import json;d=json.load(open('artifacts/g3d/d2/d2-13/d2/probe-control-control.json'));print(d['label'],d['state_mounts'])"
python3 -c "import json;d=json.load(open('artifacts/g3d/d2/d2-14/d2/probe-stale-stale.json'));print(d['identity']['uid_map'],d['ipc_mounts'])"
```

---

## 6. R5 — 清理、Canonical、0-Key / 0 网络 / LiveGate

| 检查 | 期望 |
|---|---|
| 容器 | `podman ps -a` 空；无 `at-g3d-*`；19 个 Run 的 `cleanup/ps-after.txt` 空。 |
| 进程/Socket | 无 controller/broker/fake/candidate_entry/trusted_entry；无 `bridge.sock`。 |
| Canonical | 每 Run rootfs `25491e45…`、deps `e07729d7…`、stage `e0ef085a…` 前后相等。 |
| 0-Key | host key-like env 0；无 `.env`；容器 env 白名单。 |
| 0 外网 | 全容器 `--network none --http-proxy=false --unsetenv-all`；Fake `network_used=false`。 |
| LiveGate | `run_live.sh` exit 3；`LiveGate().inspect(live_requested=True)=BLOCKED`。 |
| 测试 | g3d 130 / g3_bridge 31 / g3c 110 / gates 14 = 285 passed；ruff clean。 |

```bash
podman ps -a --format '{{.Names}}'
pgrep -af 'autoteacher_m0.bridge.controller|fake_provider.py|candidate_entry.py|trusted_entry.py' || true
bash scripts/run_live.sh; echo "expected exit 3: $?"
python3 -c "import json;d=json.load(open('artifacts/g3d/d2/d2-01/summary.json'));print(d['cleanup'],d['canonical'])"
```

---

## 7. 复核者禁止事项

1. 不修改 `src/`、Stage、Rootfs、Deps、G3-C 冻结证据/Packet、历史 docs、D1/D2 证据 Run。
2. 不 `podman pull`；不联网；不使用真实 Key/模型/外部付费 HTTP/Live。
3. 不通过放宽 socket 到 0666、同 UID、挂 state 到 Candidate、Mock DSH、关闭 Peercred 来“修复”失败。
4. 不把 D2-13 的 CONTROL 只读挂载当作正式 Candidate 配置，也不把 D2-14 的 stale 容器当作本 Run Candidate。
5. 不把 D2 的 Trusted 故障注入（`G3B_TEST_MODE=1`/`G3B_CRASH_HOOK`）当作 Candidate 攻击能力。
6. 不把 `D2_GATE_PASS` 解释为 D3/Independent Review/G3-D/Live/G4/G5 授权。

---

## 8. 可接受裁定与后续

- R0–R5 全部成立：Lead 可记录 `D2_GATE_PASS`，再单独授权 D3。
- 若 Resume/cgroup/stale Run 证据不足：`D2_GATE_PARTIAL`，先修复或收缩范围。
- 若任一 Candidate 直接读/写可信资产、借 Claim、重绑 Trusted Socket：`D2_GATE_FAIL`，立即 STOP 并报 `P0 OS_BOUNDARY_FAIL`。
- 环境不满足：`BLOCKED_NEEDS_ENVIRONMENT`，不得 Mock 替代。
- 本请求不授权 push/amend；D2 提交保持线性和只含本 Agent 路径。

**当前请求方结论**：`D2_GATE_PASS`（自评），等待 Lead 审计。**STOP，不进入 D3。**
