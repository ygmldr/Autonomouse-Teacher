# M0 G3-D — Independent Review Request（R0–R5）

> **接收对象**：Lead 指派的 **Independent D Reviewer**，必须**未参与** G3-D1/D2/D3 的任一实现、证据生成或 D4 Packet 编写。
> **性质**：这是**材料清单与复核指令**，不是 Independent Review，不代表 `G3-D PASS`，不解锁 Live/G4/G5。
> **Owner 自评**：`D-G0=PASS_AT_4BD4803`、`D-P0=PASS`、`D1_GATE_PASS`、`D2_GATE_PASS`、`D3_GATE_PASS`；**最终状态待本复核**。
> **冻结身份**：base `4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`；implementation `97230a0ba40f5f2dec98a426676fbe81a5157a26`（code 等同 `cf40c6b`）；`docs_sha` 见 Packet manifest；`src/` 自 base 无变化（D1-A 在 `51abc66`）。
> **最终 Stage**：`artifacts/g3d/stage-20261117T221955Z`，manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`，tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5`。
> **Review Packet**：`artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26/`
> **矩阵**：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv`（53 行 = **52 PASS / 1 NOT_RUN**；`D-REVIEW-01` 保持 `NOT_RUN`）。
> **全程约束**：0 Key / 0 真实模型 / 0 外部 HTTP / 0 Live；不 `podman pull`；不修改实现、Stage、证据、矩阵或 Packet。

---

## 0. 唯一可接受的裁定

复核结束后，请只给出以下之一（写在 `docs/REVIEW_G3D_INDEPENDENT.md`，由 Reviewer 新建；不要改本文件）：

| 裁定 | 含义 |
|---|---|
| **`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE`** | R0–R5 全部成立；D1 真实双 Principal 正向、D2 真实 Candidate 拒绝、D3 无 Key 恢复一致性、独立自建 Probe 均通过；且仅限本机已验 Runtime/内核与冻结 SHA。 |
| **`PARTIAL`** | 主链可工作，但至少一个 Gate 的证据/用例未完全满足；不得说“已建立可信 OS 边界”。 |
| **`FAIL`** | 任一 P0：未授权 Fake 发送、同一 Claim 重复 Fake、Candidate 读/写可信状态、无 Claim 直达 Fake、伪造成功结算、错误释放费用、需放松边界才能连通。 |
| **`BLOCKED` / `BLOCKED_NEEDS_ENVIRONMENT`** | 双 Principal/namespace/UID map/cgroup/UDS 无法真实建立；不得用 Mock 替代。 |

**永远不是** `M0_GO`、`LIVE_APPROVED`、`G4_PASS`、`G5_PASS`。

**禁止**：
1. 修改 `src/`、`scripts/g3d/`、Stage、Rootfs/Deps、D1-D3 证据、G3-C/G3-D 历史 docs 或 Packet；
2. 把 Owner 的 `summary.json`/`checks.json` 直接当独立结论，或只重放 Owner 脚本输出；
3. 使用真实 Key/模型/Provider API/外部 HTTP/Live，或 `podman pull`；
4. 无证据升级裁定，或把 `PATCH`/`PARTIAL` 写成 `PASS`；
5. 在独立复核完成前把 `D-REVIEW-01` 从 `NOT_RUN` 改成 PASS。

---

## 1. R0 — 身份、Packet、Stage 与实际加载 Blob

### 1.1 Packet 完整性

```bash
cd "/root/Autonomous Teacher/artifacts/review-packet-g3d-97230a0ba40f5f2dec98a426676fbe81a5157a26"
sha256sum -c hashes.sha256
python3 -B - <<'PY'
import json
m = json.load(open("manifest.json"))
for k in ("base_sha","implementation_sha","implementation_code_sha","docs_sha",
          "stage_manifests_sha256","runtime_rootfs_sha256","deps_sha256",
          "packet_file_count","packet_payload_tree_sha256","live_gate_status"):
    print(k, "=", m[k])
print("payload files =", m["packet_payload_file_count"])
print("real_model_calls =", m["real_model_calls"], "http =", m["real_external_http_calls"],
      "has_real_key =", m["has_real_key"])
PY
```

**期望**：`hashes.sha256` 逐行 `OK`（100%）；`packet_file_count` 等于包内实际文件数；`manifest.json` 与 `packet-integrity-report.txt` 是自引用例外，不被自身哈希；`packet_payload_tree_sha256` 可用包内 `review/verify_payload_tree.py` 复算；无 symlink；不含 rootfs/完整 repo/真实 Key。

### 1.2 Git 身份与不可变面

```bash
cd "/root/Autonomous Teacher"
git status --porcelain -uall
git rev-parse HEAD 97230a0 4bd4803 cf40c6b 51abc66
git diff --stat 4bd4803 97230a0 -- src spikes plugins scripts/g3c \
  tests/integration/g3c tests/integration/g3_bridge
git diff --stat 97230a0 -- docs/M0_G3C_IMPLEMENTATION_REPORT.md \
  docs/REVIEW_G3C_INDEPENDENT_v2.md docs/M0_G3C_REVIEW_ERRATA.md
git log --oneline -14
```

**期望**：
- `4bd4803 → 51abc66 → aacb1d0 → 46e2407 → 6e02c72 → … → cf40c6b → 97230a0`；`src` 在 `97230a0` 与 `4bd4803` 相同；
- `spikes/`、`plugins/`、`scripts/g3c/`、`tests/integration/g3c`、`tests/integration/g3_bridge` 相对 base 无 diff；
- G3-C 历史报告/errata 字节未改。

### 1.3 Stage 与真实加载模块（不是“文件在目录里”）

```bash
cd "/root/Autonomous Teacher"
sha256sum artifacts/g3d/stage-20261117T221955Z/manifest.json
python3 -B - <<'PY'
import sys; sys.path.insert(0, 'scripts/g3d')
import lib_g3d as lib
print("stage", lib.sha256_tree('artifacts/g3d/stage-20261117T221955Z'))
print("rootfs", lib.sha256_tree(lib.ROOTFS))
print("deps", lib.sha256_tree(lib.DEPS))
PY
cat artifacts/g3d/d3/d3-c05/peercred/trusted-modules.json
```

**期望**：manifest = `644823d4…`、stage tree = `e1ff1449…`、rootfs = `25491e45…`、deps = `e07729d7…`；Trusted 模块的 `file` 位于 `/project/src/autoteacher_m0/...`，每个 `sha256` 等于 `git show 4bd4803:<path>`；**不是**旧 G3-C `e6fde1c` 的 `fcdb0de4…` Stage。请独立从 Stage manifest 取 expected hash，再与容器内记录比对，不只看 Owner 的 `checks.json`。

---

## 2. R1 — 静态与回归审计

| 检查 | 期望 |
|---|---|
| `src/` | `git diff --stat 4bd4803 97230a0 -- src` 空 |
| 受保护文件 | `AGENTS.md`、`scripts/run_live.sh` 等相对 base 无未审修改 |
| D1-A 测试 | `tests/integration/g3d/test_d1_socket_boundary.py` 保持 D1-A 冻结字节（D3 `cf40c6b` 明确恢复） |
| 矩阵 | 53 行；52 PASS / 1 NOT_RUN；`D-REVIEW-01` 仍 `NOT_RUN`；历史 G3-C 矩阵未改 |
| Host 测试 | `tests/integration/g3d` 144、`g3_bridge` 31、`g3c` 110、`gates` 14；Ruff pass |
| 固定 OCI | **916 tests / 0 failed / 7 skipped / 4 explicit deselects**；不得把 916 说成“920 全跑” |
| Host full | 917 passed / **2 既有 host-only env failures** / 1 skipped；不得隐藏或改断言 |

```bash
cd "/root/Autonomous Teacher"
export PYTHONPATH="$PWD/src:$PWD/artifacts/foundation/deps" PYTHONDONTWRITEBYTECODE=1
/root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d
/root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3_bridge
/root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3c
/root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/unit/security/test_gates.py
/root/.cache/uv/archive-v0/oAfur17xwsCxzC-G4AMaM/bin/ruff check scripts/g3d tests/integration/g3d
```

---

## 3. R2 — Reviewer **自建** Candidate 攻击（核心）

**要求**：从**真实 Candidate 容器**（`uid_map=0 65534 1`、`gid_map=0 65534 1 + 2000 2000 1`、`--network none`、`--cap-drop ALL`）内发起；每条记录真实 `argv`、`errno`、UID/GID/Map、Mountinfo、前后 DB/文件 Hash、Broker/Attempt/Receipt 行数、UTC/exit。**不得**只重放 `artifacts/g3d/d2/**` 的 JSON；不得在 Host Root 模拟。

允许复用 Launcher/Runner 的**容器生命周期**（例如把 `scripts/g3d/d2_runner.py` 复制到 `/tmp`，保留其启动/清理/快照逻辑，把 Probe 指向你自写的 `/tmp/reviewer_probe_*.py`）；**不允许**把 Owner 的 Probe 当成你的独立证据。

必须至少覆盖：

| # | 攻击 | 你的判据 |
|---|---|---|
| R2-1 | 读 Broker SQLite、`-wal`、`-shm`、Attempt Journal、Receipt、Policy、Admission、Fake Counter、Controller 配置 | 正式 Candidate 挂载树中不存在；`ENOENT(2)` 或 `EACCES(13)`；DB/文件 SHA 与行数不变；不得把 D2-13 的只读 `state` 挂载当成正式配置 |
| R2-2 | 写/截断/替换/`unlink`/`chmod`/hardlink/symlink DB 与 state | `ENOENT/EROFS(30)/EXDEV(18)`；无事务/哈希变化；0 新行 |
| R2-3 | 不经 Controller 直接 Reserve/Claim/Fake；注入 `kind=reserve/claim/settle`、`authorized`、`dispatch_allowed`、伪造 `call_id/reservation_id` | 协议拒绝（`UNKNOWN_KIND/UNKNOWN_FIELD/ROUTE_MISMATCH/PREPARED_DIGEST_MISMATCH` 等）；Fake=0、无未授权 Claim/Attempt；随后真实正向仍成功 |
| R2-4 | 伪造 admission/policy/route/tools/nonce、坏 JSON、大 Frame、Seq 乱序、Socket 替换（unlink/rename/bind/chmod） | 拒绝且不产生 Claim/Fake；socket 仍 `0660 root:2000`；Candidate 不能 unlink/bind |
| R2-5 | 替换 Socket 后伪造 `SO_PEERCRED`：以 UID 0/其它 UID 连接，或让 Candidate 直接 bind 一个同路径 fake socket | `PEER_UID_DENIED`/`PEERCRED_UNAVAILABLE`，无 ack、无 Broker/Fake；**不得**用同 UID 或 0666 通过 |
| R2-6 | `/proc`、FD、`environ`、`/sys`、`/dev`、mount、ptrace、cap、userns、Podman/Docker Socket | Trusted PID/FD/Env 不可见；host root/容器控制 socket 不可达；`EACCES/EPERM/ENOENT` 真实；嵌套 userns 若可建，仍不得拿到 Host root/state |
| R2-7 | `AF_INET/AF_INET6/UDP`、DNS、外部 TCP、其它 UDS | `EACCES(13)`/同等强度内核限制；DNS 失败；唯一可连 `/work/g3b/bridge.sock`；不得只看 `--network none` 文本 |
| R2-8 | 本地工具/插件/伪造 Guard：自写 `evil_guard.py`、`forged-admission.json` | 仅本地生效；Controller 仍唯一发送路径；Trusted state 哈希不变 |
| R2-9 | Candidate SIGKILL/断连/同 call 重发 | 无自动重发；重复 `call_id` → `ATTEMPT_ALREADY_STARTED`；有 receipt 才可恢复 settle，没有则 `SETTLEMENT_UNCERTAIN/PENDING`，绝不 `FREE` |

建议最小命令骨架（请自建 `$RUN`/Probe，不复用 Owner 的 evidence-dir）：

```bash
cd "/root/Autonomous Teacher"
# 1) 先跑一次 Owner harness 确认容器环境（不作为独立证据）
/root/.local/bin/python3.11 -B scripts/g3d/d2_runner.py \
  --case d2-08 --stage artifacts/g3d/stage-20261117T210738Z \
  --evidence-dir artifacts/reviewer-g3d/selfcheck-d2-08

# 2) 自建 harness：复制 runner 到 /tmp，替换 probe 路径/源码后运行
cp scripts/g3d/d2_runner.py /tmp/reviewer_d2_runner.py
# 编辑 /tmp/reviewer_d2_runner.py 的 probe 映射，指向 /tmp/reviewer_probe_db.py 等
/root/.local/bin/python3.11 -B /tmp/reviewer_d2_runner.py \
  --case d2-01 --stage artifacts/g3d/stage-20261117T210738Z \
  --evidence-dir artifacts/reviewer-g3d/self-db-read
```

**注意**：`d2_runner.py` 的 `--case` 列表固定；你可以在 `/tmp` 的副本中新增自己的 case 映射，但**不要**修改仓库内 `scripts/g3d/**`。任何 Candidate 内 Probe 只读 Stage（`/project` ro、`/deps` ro），不得写 `/work/state`。

---

## 4. R3 — 真实双主体 DSH Echo / Tool / Resume

使用**真实 DSH `0.2.2-rc.2`**、真实 Candidate/Trusted 容器、Fake Provider（0 Key）。每次使用新的 `--evidence-dir`。

```bash
cd "/root/Autonomous Teacher"
# Echo
/root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case reviewer-echo --scenario echo --session reviewer-g3d-s1 \
  --stage artifacts/g3d/stage-20261117T221955Z \
  --evidence-dir artifacts/reviewer-g3d/echo

# Tool（同一真实 Turn 两轮）
/root/.local/bin/python3.11 -B scripts/g3d/launch.py \
  --case reviewer-tool --scenario tool --session reviewer-g3d-s1 \
  --stage artifacts/g3d/stage-20261117T221955Z \
  --evidence-dir artifacts/reviewer-g3d/tool

# Resume（两次真实 Candidate 进程共享同一 session）
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py \
  --case d3-c01-resume --stage artifacts/g3d/stage-20261117T221955Z \
  --evidence-dir artifacts/reviewer-g3d/resume
```

**期望**：Echo = 1 Reservation/Claim/Attempt/Receipt/Settlement、counter=1；Tool = 2 套独立账本（`tool_once`/`tool_final`）、counter=2；Resume = 两个真实 Candidate 进程、session `reason:"resume"`、无旧 Attempt 重放。每个正向都要核对：
- `claim.request_digest == attempt.prepared_digest`；
- `receipt.raw_sha256 == attempt.payload_digest`；
- 两对不互等；
- DSH usage 与 receipt usage 字段级相等；
- `podman ps -a` 空、socket 消失、rootfs/deps/stage canonical。

---

## 5. R4 — Crash / Cancel / Disconnect / 同 Claim 并发

至少 **2 个真实 Crash** + **1 次 Cancel/Disconnect** + **同 Claim 双 Candidate**：

```bash
cd "/root/Autonomous Teacher"
S=artifacts/g3d/stage-20261117T221955Z
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c04 --stage $S \
  --evidence-dir artifacts/reviewer-g3d/c04
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c05 --stage $S \
  --evidence-dir artifacts/reviewer-g3d/c05
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c07-before --stage $S \
  --evidence-dir artifacts/reviewer-g3d/c07-before
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c08-disconnect --stage $S \
  --evidence-dir artifacts/reviewer-g3d/c08-disconnect
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py --case d3-c11-same --stage $S \
  --evidence-dir artifacts/reviewer-g3d/c11-same
```

**独立判据**：
- C04：新 Trusted 进程读同一 state → `SETTLEMENT_UNCERTAIN/NO_RECEIPT_AFTER_CRASH`，receipt/counter 不增，无自动发送；
- C05：新 Trusted 验证 receipt+usage → **恰好 1 次** settle（`budget_broker_messages` 1→2）；第二次重启 +0；
- C07：发送前 cancel → 0 Attempt/0 Fake，Reservation 保守 `PENDING`；
- C08：断连后 1 Receipt、保守结算，无 `FREE`、无伪造 Fee=0；
- C11-same：恰好 1 finish、1 `ATTEMPT_ALREADY_STARTED`、1 套账本/counter=1。**不得**要求“real-DSH same-claim PASS”；C11-real 是两个独立 business request，证据级别必须分开。

**加分但非强制**：自己写一个“没有 receipt 不自动发送/不误结算”的负例，记录真实进程/协议结果。

---

## 6. R5 — 固定 OCI / Node / LiveGate / 清理

```bash
cd "/root/Autonomous Teacher"
# 固定 OCI full（必须使用只读物化树；不要用可写 checkout 的 0644 模式）
# 参考 Packet 的 regressions/oci-full.log 与 argv-and-exit.jsonl；下面是最小等价命令：
rm -rf /tmp/reviewer-g3d-oci && mkdir -p /tmp/reviewer-g3d-oci/evidence
git archive 97230a0 | tar -x -C /tmp/reviewer-g3d-oci/project
chmod -R a-w /tmp/reviewer-g3d-oci/project
chmod 0777 /tmp/reviewer-g3d-oci/evidence
podman run --rm --name reviewer-g3d-oci --network none --http-proxy=false \
  --unsetenv-all --env PATH=/opt/python/bin:/usr/bin --env HOME=/work \
  --env PYTHONPATH=/project/src:/deps --env PYTHONDONTWRITEBYTECODE=1 --env TMPDIR=/tmp \
  --read-only --read-only-tmpfs=false --cap-drop ALL --security-opt no-new-privileges \
  --user 65534:65534 --pids-limit 192 --memory 1500m --memory-swap 1500m --cpus 1 \
  --tmpfs /tmp:rw,noexec,nosuid,nodev,size=256m,mode=1777 \
  --tmpfs /work:rw,noexec,nosuid,nodev,size=64m,mode=1777 \
  --workdir /project --timeout 900 --systemd=false \
  --mount type=bind,src=/tmp/reviewer-g3d-oci/project,dst=/project,rw=true \
  --mount type=bind,src="$PWD/artifacts/foundation/deps",dst=/deps,ro=true \
  --mount type=bind,src="$PWD/artifacts/foundation/deps",dst=/project/artifacts/foundation/deps,ro=true \
  --mount type=bind,src=/tmp/reviewer-g3d-oci/evidence,dst=/evidence,rw=true \
  --rootfs "$PWD/artifacts/security/rootfs" \
  /opt/python/bin/python3.11 -B -m pytest tests/ -q -p no:cacheprovider \
  --junitxml=/evidence/junit.xml \
  --deselect tests/integration/g3d/test_d1_launcher_contract.py::test_manifest_tree_accepts_matching_stage \
  --deselect tests/integration/g3d/test_d1_launcher_contract.py::test_manifest_tree_detects_unknown_extra_and_tamper \
  --deselect tests/integration/g3d/test_d1_launcher_contract.py::test_manifest_tree_detects_symlink \
  --deselect tests/integration/g3d/test_d1_socket_boundary.py::test_admission_launcher_uid_is_not_the_socket_peer_uid
```

**期望**：**916 tests / 0 failed / 7 skipped / 4 deselected / exit 0**；若你用普通 `git archive`（`0644`）得到 `target_profile_static` 失败，那是**既有 host-only 环境语义**，不是产品失败；请记录你的物化方式并说明。

```bash
# Node（host；guard 必须给 host python；skill build 后跑 8/8）
cd plugins/runtime-budget-guard && RBG_TEST_PYTHON=/root/.local/bin/python3.11 \
  node --test tests/precheck.test.mjs tests/guard-pr1.test.mjs
cd ../skill-lookup && npm run build && node --test test/plugin.test.mjs

# LiveGate / run_live / 0-key / 清理
cd "/root/Autonomous Teacher"
env | cut -d= -f1 | grep -Ei 'KEY|TOKEN|SECRET|CREDENTIAL|PASSWORD|AUTH|API' || echo NONE
find . -maxdepth 2 -name .env -not -name .env.example
bash scripts/run_live.sh; echo RUN_LIVE_EXIT=$?
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src /root/.local/bin/python3.11 -B -c \
  "from autoteacher_m0.security.gates import LiveGate; print(LiveGate().inspect(live_requested=True))"
podman ps -a --format '{{.Names}}'
ps -eo pid,args | grep -E 'at-g3d|controller_entry|trusted_entry|candidate_entry|fake_backend' | grep -v grep
```

**期望**：key-like env 0；无 `.env`；`RUN_LIVE_EXIT=3`；`LiveGate` `BLOCKED`（4 reasons）；`podman ps -a` 空；0 残留；rootfs `25491e45…`、deps `e07729d7…`、stage `e1ff1449…`；如出现空 `rootfs/evidence` 只允许确认 root-owned/empty 后 `rmdir`，并记录。

---

## 7. 需要 Reviewer 特别挑战的点

1. **C11 不得合并**：`d3-c11-real` 是两个真实 DSH 的**独立** business request（`sessionId` 进入 digest，identity 不同）；`d3-c11-same` 是受控双真实 Controller/UDS 负例。任何“real-DSH same-claim PASS”都必须被拒绝，除非你能构造两个真实 DSH 客户端共享同一 business identity 并复现。
2. **C10 时钟**：DSH `time0` 是 epoch ms；Host 用 realtime/monotonic 对换算。请自己取同一 Host 的时钟对重算；若 `T1 >= T2` 或 Fake 首 chunk 不早于 exit，应判 FAIL。
3. **C05/C06 的“最多一次”**：不只看 Attempt 最终 `SETTLED`，要看 `budget_broker_messages` 增量（C05 第一次 +1、第二次 +0；C06 两次 +0）。第二次 settle 属 P0。
4. **C03 PENDING 是故意保守**：没有可信 receipt 时不得要求立即 FREE；`0.00155` 是保守占用。
5. **C08 SIGTERM**：不得要求立即 FREE 或伪造 Cancel 成功；本 Gate 只证明有界清理与保守状态。
6. **D2-13 是 CONTROL**：只读 `state` 挂载是故意构造的 DAC 对照，不是正式 Candidate 配置；正式 Candidate 无 state 挂载。
7. **D2-14 是 per-Run 路径，不是 per-Run token**：同 UID 65534/group 2000 的 stale Candidate 若拿到 live 路径仍可连接；`SO_PEERCRED` 只证明允许的 OS 身份，不区分 Run。
8. **OCI 4 deselect / 7 skip**：rootfs 无 `tar`/`git`、uid 65534；Host pytest 覆盖 tar/root 契约，但那 4 个测试在 OCI 中**没有执行**。不得写成“全部 920 全绿”。
9. **Trusted root 是 TCB**：本 Gate 的“Trusted”只是 OS 主体边界，不是 G4 安全部署；不得外推。
10. **磁盘硬配额**：Candidate session 无硬配额（P2）；不得宣称完整磁盘 DoS 防护。

---

## 8. 输出要求

请在 `docs/REVIEW_G3D_INDEPENDENT.md` 中给出：

- `reviewer_identity`（与 D1/D2/D3 实现者不同）、时间、HEAD/Stage/rootfs/deps hash、Packet 校验结果；
- 自建 Probe 的 `argv`/UTC/exit/stdout/stderr/hash、真实 errno/UID Map/Mountinfo；
- R0–R5 每项独立 PASS/FAIL/PARTIAL/UNVERIFIED；
- 是否发现 P0（未授权发送/重发/假结算/误 FREE/读可信状态）；
- 对 C11 两个证据级别的独立结论；
- 对残余（C07 单飞、C09 Broker 不重启、C10 时钟、C12 重启不接单、OCI 例外、Host Node、磁盘配额、嵌套 userns、per-Run 路径）的接受/拒绝；
- 唯一裁定（`PASS_FOR_G3D_NO_KEY_OS_BOUNDARY_SCOPE` / `PARTIAL` / `FAIL` / `BLOCKED`）；
- 是否允许 Lead 继续（仅限本 Gate；仍不得自动进入 G4/G5/Live）。

**当前状态**：等待 Lead 指派 Independent D Reviewer；Owner 不请求、不执行独立复核；`D-REVIEW-01` 保持 `NOT_RUN`。
