# M0 G3-D3 — Review Request（D4 Reviewer 输入）

> **目的**：把 D3 Recovery/Regression 的原始证据、复现命令和未合并的边界交给**未参与 D1/D2/D3 实现**的 Reviewer。本文不是 Independent Review，不代表 G3-D 总 PASS。
> **D3 自评**：`D3_GATE_PASS`（待 Lead 审计）；17/17 矩阵行 PASS。
> **最终代码**：`cf40c6bfb84ceae98e795db19efa955aa3035991`（实现 `ef84f57`，父 `bb34931`；测试/OCI 修正 `dc8214e`、`cf40c6b`）
> **产品基线**：`4bd48037d98e081c8fb96a246f3fbf3cf60eb38b`；`src/` 0 改动
> **Stage**：`artifacts/g3d/stage-20261117T221955Z`
> - manifest `644823d46adaef28810ba13bb97547371616177bbc4b8138b1eaed5d9a28eb03`
> - tree `e1ff14496e06dcb1c887badfb93b858012373be9fe739e61bb04587885e9f9c5`
> - candidate `6c850e4b1fb746314df2ebccfca7789179412e6797f35d78d53dfe2f239a0dc7` / trusted `3a004bee14b412151f21abf2964c84d08528b4dc0c83835b694cf29784f33272`
> **证据根**：`artifacts/g3d/d3/`
> **矩阵**：`docs/Autonomous_Teacher_M0_G3D_Test_Evidence_Matrix_v1.0.csv` 中 D3-01、D3-C01..C12、D3-REG-01..04 共 17 行；D-REVIEW-01 仍 `NOT_RUN`。

---

## 1. 请 Reviewer 先做的 7 件事

1. **身份复核**：确认 `cf40c6b` 的父/祖先、`src` 与 `4bd4803` 一致、Stage manifest/tree 与报告一致；确认 D1-A `test_d1_socket_boundary.py` 未被 D3 改动。
2. **重跑至少一个正向**：独立跑一个真实 DSH Echo（可复用 `d3_runner.py --case d3-c01-echo`），亲自核对 DSH usage/receipt/Broker/Attempt/Claim 和 Fake counter。
3. **重跑至少一个崩溃窗口**：建议 C04（`ATTEMPT_STARTED` 前 crash）或 C05（receipt-before-settle）；必须确认**新 Trusted 进程**读同一 state，而不是旧进程/mock；核对 reconcile 前后的 receipt/broker message/Attempt 行。
4. **自建一个关键负例**：Reviewer 自己写探针（不复用 D3 探针）验证“没有 receipt 不自动发送/不误结算”或“same-claim 输家不产生 Fake”；记录真实进程/协议结果。
5. **C11 分开审计**：分别看 `d3-c11/11-real` 与 `d3-c11/11-same`；确认报告没有把“两个 real-DSH 独立请求”说成“real-DSH 同 Claim PASS”，并核对输家错误码。
6. **C10 原始时间**：从 `stream/timing.json`、Fake timing sidecar、DSH `events[].data.stream[].time0` 自己重算 `T1<T2`，确认不是后处理伪造的 buffered replay。
7. **清理/canonical/0-Key**：复核 REG-03、`podman ps -a`、rootfs/deps/stage hash、LiveGate BLOCKED、0 key-like env；确认 REG-01 的 deselect/skip 分类没有被写成“全绿”。

Reviewer 必须使用**自己的身份和自建探针**；不能只阅读本报告或重放 D3 脚本输出就签“独立复核”。

---

## 2. 复现命令

### 2.1 全量 D3 suite（会重建 13 个 case/suite；约 5–8 分钟）

```bash
cd "/root/Autonomous Teacher"
rm -rf artifacts/g3d/d3
/root/.local/bin/python3.11 -B scripts/g3d/run_d3_suite.py \
  --stage artifacts/g3d/stage-20261117T221955Z \
  --root artifacts/g3d/d3
```

该命令按顺序执行：

```text
d3-01  = d3-c01-echo + d3-c04 + d3-c05
d3-c01 = d3-c01-echo + d3-c01-tool + d3-c01-resume
d3-c07 = d3-c07-before + d3-c07-after + d3-c07-two
d3-c08 = d3-c08-half + d3-c08-disconnect + d3-c08-sigterm
d3-c09 = d3-c09-broker + d3-c09-fake + d3-c09-stall
d3-c11 = d3-c11-real + d3-c11-same
singles: d3-c02, d3-c03, d3-c04, d3-c05, d3-c06, d3-c10, d3-c12
REG: reg-01 OCI full, reg-02 Node, reg-03 cleanup/canonical, reg-04 accounting
```

### 2.2 单 case（便于 Reviewer 自建对照组）

```bash
/root/.local/bin/python3.11 -B scripts/g3d/d3_runner.py \
  --case d3-c04 \
  --stage artifacts/g3d/stage-20261117T221955Z \
  --evidence-dir artifacts/g3d/d3/reviewer-c04
```

可用 `--case`：`d3-c01-echo`、`d3-c01-tool`、`d3-c01-resume`、`d3-c02..d3-c06`、`d3-c07-{before,after,two}`、`d3-c08-{half,disconnect,sigterm}`、`d3-c09-{broker,fake,stall}`、`d3-c10`、`d3-c11-{real,same}`、`d3-c12`。

### 2.3 Host 补充测试

```bash
PYTHONPATH=src:artifacts/foundation/deps PYTHONDONTWRITEBYTECODE=1 \
  /root/.local/bin/python3.11 -B -m pytest -q -p no:cacheprovider tests/integration/g3d
ruff check scripts/g3d tests/integration/g3d
```

实际记录：g3d 144、g3_bridge 31、g3c 110、gates 14；Ruff 0.17.5 全过。Host pytest 是补充，不是 D3 的主证据。

---

## 3. 证据地图（按 Reviewer 问题）

| 问题 | 先看 |
|---|---|
| Gate 身份/Stage | `final.json`、`canonical-pre.json`、`d3-*/summary.json.env`、`d3-*/env/stage-manifest.json`、`stage-20261117T221955Z/stage-summary.json` |
| 真实 DSH 正常 | `d3-c01/01-echo|01-tool|01-resume/`、`d3-c10/traces/dsh-result.json` |
| 崩溃窗口 | `d3-c03|d3-c04|d3-c05|d3-c06/{state,recover,db,receipt}/` |
| Cancel | `d3-c07/*/probes/*-document.json`、`state/{before,after,two}.json`、`recover/` |
| 断连/SIGTERM | `d3-c08/*/recover/`、`socket-stat/after-sigterm.json`、`recover/residual-after-sigterm.json` |
| Deadline | `d3-c09/*/recover/deadline-*.json`、`probes/c09-*-document.json`、`state/final.json` |
| Streaming | `d3-c10/stream/timing.json`、`state/receipts/timing-*.json`、`traces/dsh-result.json` |
| 并发/same-claim | `d3-c11/11-real/stream/{c11-concurrent,c11-ledger}.json`、`d3-c11/11-same/recover/{same-claim-terminals,same-claim-ledger}.json` |
| 10+ 重启/压力 | `d3-c12/summary.json`（10 个 `restart-c12-*` 快照）、`stress/c12.json`、`checks.json` |
| OCI | `reg-01/result.json`、`reg-01/oci/junit-oci-full.xml`、`reg-01/oci-full.{stdout,stderr}.txt` |
| Node | `reg-02/result.json`、`guard-tests.stdout.txt`、`skill-tests.stdout.txt` |
| 清理/canonical | `reg-03/result.json`、`canonical-pre.json`、`final.json` |
| 账务 | `reg-04/result.json`、各 `state/final.json`、`receipt/` |

每个 case 的 `checks.json` 是 Host 判据的逐项结果；`summary.json` 含 run_id、UTC、exit、candidate/trusted 记录、cleanup/canonical。原始命令在 `run/argv-*.json`，原始进程/挂载/uid_map 在对应子目录。

---

## 4. 需要 Reviewer 特别挑战的点

1. **C11 不得合并**：`d3-c11-real` 是两个真实 DSH 的**独立** business request（sessionId 在 digest 中不同）；`d3-c11-same` 是受控双 Controller/UDS 负例。任何“real-DSH same-claim PASS”的说法都必须被拒绝，除非 Reviewer 自己能构造出两个真实 DSH 客户端共享同一 business identity 并复现。
2. **C10 的 monotonic 换算**：DSH `time0` 是 epoch ms；Host 用 realtime/monotonic 对换算。Reviewer 应独立取同一 host 的时钟对重算；如果 `T1>=T2` 或 Fake 首 chunk 不早于 exit，应判 FAIL。
3. **C05/C06 的“最多一次”**：不是只看 Attempt 最终 `SETTLED`，要看 `budget_broker_messages` 增量：C05 第一次重启 +1、第二次 +0；C06 两次都 +0。若发现第二次 settle，属于 P0 风险。
4. **C03 的 PENDING 是故意保守**：不得把 PENDING/0.00155 说成“漏结算”；在没有可信 receipt 的情况下这是预期状态。
5. **C08 SIGTERM 的发票**：不得要求 SIGTERM 后立即 FREE；本 Gate 只证明不伪造成功、不伪造 Fee=0、有界清理。
6. **REG-01 的 4 个 deselect**：这是固定 OCI 无 tar/git + 非 root 的环境例外，不是产品失败；但也不能把 916 tests 说成“920 全跑”。Reviewer 应在 Host 上补跑被 deselect 的 4 个测试并记录。
7. **REG-03 的 rootfs/evidence 清理**：只允许删除 root-owned 空目录；Reviewer 应确认没有删除非空/非本人产生的路径，且 rootfs hash 回到 `25491e45…`。
8. **Trusted root 是 TCB**：本 Gate 的“Trusted”只是 OS 主体边界，不是安全部署；不要把它外推成 G4/G5。

---

## 5. Reviewer 输出建议

请给出：

- `reviewer_identity`（与 D1/D2/D3 实现者不同）、时间、HEAD/Stage/rootfs/deps hash；
- 自建探针的 argv/UTC/exit/stdout/stderr/hash；
- 对 D3-01、C01..C12、REG-01..04 每项的独立 PASS/FAIL/PARTIAL；
- 是否发现 P0（未授权发送/重发/假结算/误 FREE）；
- 对 C11 两个证据级别的独立结论；
- 对残余（C07 单飞、C09 broker 不重启、C10 时钟、C12 重启不接单、OCI 例外、Host Node）的接受/拒绝；
- 最终 `D3_REVIEW_PASS` / `PARTIAL` / `FAIL`，以及是否允许 Lead 进入 D4/总 Packet。

**当前状态**：等待 Lead 审计后指派 D4 Reviewer；本 Agent 不进入 D4、不 push、不 amend。
