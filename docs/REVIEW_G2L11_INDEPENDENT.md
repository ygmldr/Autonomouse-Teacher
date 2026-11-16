# Independent Review: G2-L1.1 (`bf1e84d`)

- Gate：**G2-L1.1**（M0，离线/无 Key）
- Base：`76f1c52d156d0c5e9e3834afc8d2ea35555e7626`
- Implementation：`bf1e84dab9c74f1bec919633672dc29abfa7a77b`（父 `76f1c52`；6 files）
- Docs HEAD（审阅现场观察值）：`1d2efe2a2bd61275db725860235e820a360dc39b`
- Reviewer：独立身份（与实现者 verify2、G0/docs owner broker-docs 分离）
- 审阅日期：2026-11-16 UTC
- 证据目录：`artifacts/reviewer-g2l11-independent/`

## 0. 裁定摘要

**最终限定范围裁定：`PASS_FOR_DECLARED_G2L11_SCOPE`**（Python 离线 T1–T6；带 P2 非阻断发现）。

独立重跑结果：

| 项 | 独立结果 |
|---|---|
| RED2（base `76f1c52` + `bf1e84d` 的两个 committed 测试） | **8 failed / 16 passed**，exit 1 |
| 其中行为 RED | **6**：L11-ATT-03/04/06、L11-ID-02、L11-JRN-01、L11-DIAG-01 |
| 其中 API-shape RED | **2**：L11-ATT-01（`classification` 缺失）、L11-DIAG-02（`policy_checks` 缺失） |
| GREEN L11（exact stage `bf1e84d`） | **24 passed** |
| 全量 `tests/` | **625 passed, 1 skipped** |
| G2 核心选择集 | **15 passed**（BIND-01/06/07/08、INT-05/06/17、bound/unbound、v1 兼容） |
| `scripts/verify_egress_policy.py` | **PASS**（61 checks） |
| Ruff repo-wide | **All checks passed!** |
| Reviewer 独立机制 probe | **73/73 checks PASS**（T1/T2/T3/T4/T5/T6） |
| LiveGate / Adapter | 动态 **BLOCKED**（15/15 probe checks） |
| Node B（DSH Plugin/SDK） | **BLOCKED / UNVERIFIED**（固定 OCI 无 node；宿主 Node 未使用） |
| Live / GO | **未授权、未执行**；G3 未启动 |

本裁定**不是** Live/GO 授权，也**不覆盖** Node B、真实 provider wire/usage/invoice/exactly-once、ATTEMPT_STARTED 跨进程持久化、旧 v1 unbound claim 的生产迁移。

## 1. 声明范围 vs 独立核实范围

| 类别 | 内容 |
|---|---|
| Owner 声明范围 | T1–T6 的 G2-L1.1 最小修复；固定无 Key OCI；不改 `gates.py` / `dsh_adapter.py` / `run_live.sh`；不进入 G3+；Node B 标 BLOCKED |
| Reviewer 独立核实 | Git/base/impl/docs 身份；完整 diff 与 packet `diff.patch` 字节一致；source/tests blob；packet manifest/hashes/tar；RED2/GREEN/全量/G2 核心/verify/Ruff；T1–T6 独立 probe；LiveGate/Adapter；run_live 静态；Node B 环境缺失；packet 证据一致性 |
| 未独立证明 | 真实 provider wire/HTTP/usage/invoice/billing/exactly-once；DSH Plugin/SDK B 层；真实工具 registry；ATTEMPT_STARTED 崩溃持久化；真实 Key/模型；G3/G4/G5/G6；`run_live.sh` 的动态 exit 3（见 §7） |
| 约束遵守 | 未修改生产源码/tests/scripts；未 commit；未读真实凭据；未使用真实模型/外网；未进入 G3/G4/G5/G6；仅新增本文件与 `artifacts/reviewer-g2l11-independent/` |

## 2. 身份 / 证据 identity

### 2.1 Git 身份

| 项 | 实测值 |
|---|---|
| `git rev-parse HEAD`（审阅时） | `1d2efe2a2bd61275db725860235e820a360dc39b` |
| Base | `76f1c52d156d0c5e9e3834afc8d2ea35555e7626` |
| Implementation | `bf1e84dab9c74f1bec919633672dc29abfa7a77b` |
| Impl parent | `76f1c52`（`git cat-file -p` 现场核对） |
| Impl tree | `46f3e1cdf3c828e84452ba3927e34f88c96cccf2` |
| Impl 文件数 | 6（`git diff --name-status 76f1c52 bf1e84d`） |
| 祖先关系 | `git merge-base --is-ancestor 76f1c52 bf1e84d` = 0；`bf1e84d` 是 HEAD 祖先 = 0 |
| Impl 后 docs commits | `c140541`（packet docs）、`0729cea`（errata）、`1d2efe2`（alignment）；合计只涉及 3 个 docs 文件 |
| Tracked worktree（审阅开始时） | clean（`git status --porcelain -uno` 空；reviewer 新增文件在 ignored evidence 目录） |

### 2.2 Diff / 源码 / 测试绑定

| 检查 | 结果 |
|---|---|
| `git diff --no-ext-diff --binary 76f1c52 bf1e84d` vs packet `diff.patch` | **字节一致**（`cmp` exit 0；sha256 `e273df6ef5abbc64a433b9165028eb9cf1e33f967d68cc06cb02bf2dc31cf60f`） |
| `git diff --check 76f1c52 bf1e84d` | exit 0 |
| packet `source/`、`tests/` 六个副本 vs `bf1e84d` blobs | 全部 `OK`（`source-file-list.txt` 的 blob SHA 与 commit 一致） |
| `gates.py` / `dsh_adapter.py` / `run_live.sh` | base = impl = HEAD，blob 与 SHA-256 全部相同（见 §2.3） |
| 历史冻结旧 RED 日志 | packet `logs/red.stdout.log` 与 `artifacts/g2l11/logs/red.stdout.log` 字节一致；仅作 superseded 历史 |

### 2.3 环境 / stage / 依赖 / 镜像

| 项 | 实测值 |
|---|---|
| Fixed OCI | `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b` |
| Image ID | `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715` |
| Python（OCI） | CPython 3.11.15 |
| Deps normalized tar | `e07729d7997944417b1c25531749b3e6e5e34aa4248f01dc8f370282082ecb98` |
| GREEN stage | `git archive bf1e84d`；198 files；normalized tar `ab95ffb46e070f3c166f9b1a22a9a18af6bc56aa3fe83f1397ba83abcbd201c1` |
| RED2 stage | `git archive 76f1c52` + 从 `bf1e84d` 覆盖两个测试；198 files；normalized tar `865c3993c97c981bc464bfb377101ca587fc2259900894aca66a3e7005a79603` |
| Stage mode | GREEN：`chmod -R a+rX` + 4 个 config 文件 `444`；RED2：`chmod -R a-w` + `chmod -R a+rX`；独立重建与 packet 声明 hash 一致 |
| 容器安全 | `--network none --http-proxy=false --unsetenv-all --read-only --cap-drop ALL --security-opt no-new-privileges --user 65534:65534`；无 Key/credential mount |
| 冻结文件 SHA-256 | `gates.py` `3ed08634…`；`dsh_adapter.py` `88891149…`；`run_live.sh` `a8a2753f…`（base/impl/HEAD 均相同） |

### 2.4 Packet 完整性

| 项 | 实测 |
|---|---|
| 文件数 | 49 |
| `manifest.sha256` | `2200af1077719df05be2ea9ea27b3d6348c2ae9681fe57d6557a299c22db9865  manifest.json`，**匹配** |
| `hashes.sha256` | 46 行；`sha256sum -c` 46/46 `OK`（排除自身、manifest.sha256、integrity report） |
| `manifest.json` 关键字段 | base/impl/source_tree_hash/image/deps/stage 均现场可复算；`docs_commit=c140541` 见 §5 R-01 |
| `diff.patch` | 与现场 `git diff` 字节一致 |
| `packet tar` | **未交付 tar 文件**；errata 引用的 tar hash 与当前 packet 不一致（见 §5 R-01） |
| `evidence-matrix.csv` | 28 行 = 24 L11 + 3 T6 Python + 1 Node B；27 PASS / 1 BLOCKED |

## 3. 源码级 dispatch / claim / settlement 路径定位

以下行号均指 `bf1e84d` 现场源码。

### 3.1 Descriptor-only 诊断（无发送能力）

- [`EgressBoundary._evaluate`](../src/autoteacher_m0/security/egress.py#L337)：纯 policy/identity 评估；attempt 配额按 `claims_granted` 而非诊断次数（`:387`）。
- [`_record_policy`](../src/autoteacher_m0/security/egress.py#L394)：只增加 `policy_checks` / `policy_allowed` / `policy_denied`，追加 `attempts_detail`；不产生 permission。
- [`evaluate_descriptor` / `authorize` / `require`](../src/autoteacher_m0/security/egress.py#L428)：只做 descriptor 诊断；`require` 只抛 `EgressViolation`，不发送。
- [`PolicyOnlyFakeTransport`](../src/autoteacher_m0/security/egress.py#L841)：显式 `dispatched=False`。

### 3.2 Prepared 严格化与 claim 前检查

- [`prepared_schema_error`](../src/autoteacher_m0/security/egress.py#L166)：先强制 `schema_version == "m0.prepared.v1"`（`:168`），再校验字段类型、path、bool/int、nested Mapping、canonical JSON。
- [`prepared_request_digest`](../src/autoteacher_m0/security/egress.py#L215) / [`prepared_call_id`](../src/autoteacher_m0/security/egress.py#L219)：从 prepared 内容重算；call-id 材料包含 `v/run_id/logical_step/attempt_index/request_digest`。
- [`claim_dispatch_for_request`](../src/autoteacher_m0/security/egress.py#L531)：`schema_error` 在任何 claimer 调用前返回（`:545-547`）；随后重算 digest/call-id，核对 prepared/request 的 route/model/host/port/method/path/stream/max_tokens/flags/digest（`:554-591`）；tools 需 `approved_tool_schemas`（`:585-591`）；全部通过后才进入 `_claim_with`（`:593`）。
- [`_claim_with`](../src/autoteacher_m0/security/egress.py#L477)：先 `evaluate_descriptor`；无 claimer → `BROKER_CLAIMER_UNAVAILABLE`；`expected_binding` 非空时要求 `claim_bound`，缺失 → `CLAIM_BINDING_UNSUPPORTED`（`:488-491`）；`ClaimResult.claimed` 为真才创建 [`DispatchPermission`](../src/autoteacher_m0/security/egress.py#L502)。
- 旧 v1 路径 [`claim_dispatch`](../src/autoteacher_m0/security/egress.py#L516) 仍允许无 expected route/model 的 claimer；[`require_claim`](../src/autoteacher_m0/security/egress.py#L595) 仍调用该 legacy 路径——这是维护者已裁定的 G3 迁移残余，不是本轮新增绕过。

### 3.3 Permission 单次消费与 provider attempt

- [`consume_permission`](../src/autoteacher_m0/security/egress.py#L673)：对象 identity + 字段匹配 + registry 删除；伪造/复制/跨 boundary/重放均失败。
- [`TrustedEgressTransport.dispatch`](../src/autoteacher_m0/security/egress.py#L739)：
  1. `consume_permission` 失败 → `PRE_DISPATCH_DENIED`，provider=0；
  2. provider 存在时，**先** [`mark_dispatch_attempt_started`](../src/autoteacher_m0/security/egress.py#L748) 再调用 provider（`:752`）；
  3. `KeyboardInterrupt` / `SystemExit` → `_started_failure` 归因后原样 re-raise（`:753-756`）；
  4. 其他 `BaseException` / 非 Mapping 返回 → [`_started_failure`](../src/autoteacher_m0/security/egress.py#L718)：`dispatched=True`、`classification=ATTEMPT_STARTED`、`BILLABLE_UNKNOWN`、worst-case held、无 retry；
  5. 正常返回 → `record_outcome`（`:762`）并写 success audit。
- [`record_outcome`](../src/autoteacher_m0/security/egress.py#L602)：`provider_invocations` / `provider_dispatched` 递增；按 usage/HTTP/error 决定 `SETTLED_USAGE` / `NOT_BILLABLE_HTTP_ERROR` / `BILLABLE_UNKNOWN`。

### 3.4 Broker claim / completion / journal

- [`BookkeepingBroker.handle`](../src/autoteacher_m0/accounting/broker.py#L280)：`snapshot` 不写 journal；`claim` 走独立 `budget_dispatch_claims`；`settle/fail` 在 journaling 前预检（`:314-342`）：unknown reservation → `UNKNOWN_RESERVATION`；非 PENDING → `ALREADY_SETTLED`；route 缺失 → `ROUTE_BLOCKED`；`official_usage` 失败 → `INVALID_USAGE`；均不写新 journal 行。
- 通过预检后 [`journal_once`](../src/autoteacher_m0/accounting/ledger.py#L307) 在同一事务中查重、执行、写 `budget_broker_messages`；同 message id 幂等。
- [`_complete`](../src/autoteacher_m0/accounting/broker.py#L253) 复核 reservation/route/usage 后调用 `ledger.settle`，并 `mark_claim_completed`。
- Reserve 容量：`count + pending + 2 <= max_messages`（`broker.py:227`）；completion 本身不再受该 reserve 检查，但 admission 已为每个 PENDING 预留 completion slot。

## 4. 独立执行命令与原始结果

所有项目 Python 均在 fixed OCI 内执行；宿主未直接运行 pytest。完整 argv/UTC/exit 见 [`commands.jsonl`](../artifacts/reviewer-g2l11-independent/commands.jsonl)。

| Run | 关键 argv | UTC | exit | 结果 | 证据 |
|---|---|---|---|---|---|
| RED2 | `pytest tests/integration/g2_closure/test_g2l1_fix.py -k l11_ -q` on `/project` = base+tests | 16:56:34–16:56:38 | 1 | **8 failed, 16 passed, 62 deselected** | [red2.stdout.log](../artifacts/reviewer-g2l11-independent/logs/red2.stdout.log) |
| GREEN L11 | 同上 on exact `bf1e84d` stage | 16:57:52–16:57:55 | 0 | **24 passed, 62 deselected** | [green-l11.stdout.log](../artifacts/reviewer-g2l11-independent/logs/green-l11.stdout.log) |
| FULL | `pytest tests -q` on exact stage | 16:58:24–16:59:32 | 0 | **625 passed, 1 skipped** | [full.stdout.log](../artifacts/reviewer-g2l11-independent/logs/full.stdout.log) |
| G2 core | 15-test selection（见下） | 16:59:42–16:59:49 | 0 | **15 passed, 97 deselected** | [g2-core.stdout.log](../artifacts/reviewer-g2l11-independent/logs/g2-core.stdout.log) |
| verify | `python -B scripts/verify_egress_policy.py` | 17:00:05 | 0 | **PASS，61 checks，socket denied** | [verify.stdout.log](../artifacts/reviewer-g2l11-independent/logs/verify.stdout.log) |
| Ruff | `ruff check --no-cache .` | 17:00:14 | 0 | **All checks passed!** | [ruff.stdout.log](../artifacts/reviewer-g2l11-independent/logs/ruff.stdout.log) |
| Probe | `/probe/independent_probe.py` | 17:03:34–17:03:38 | 0 | **73/73 checks PASS** | [probe.stdout.log](../artifacts/reviewer-g2l11-independent/logs/probe.stdout.log) |
| T3 base/impl | `t3_failfirst_probe.py` on base / impl | 17:09:10 | 0/0 | base `allowed=true, claimer=1`；impl `PREPARED_SCHEMA_VERSION_MISMATCH, claimer=0` | [t3-base](../artifacts/reviewer-g2l11-independent/logs/t3-base.stdout.log)、[t3-impl](../artifacts/reviewer-g2l11-independent/logs/t3-impl.stdout.log) |
| LiveGate/Adapter | `livegate_adapter_probe.py` | 17:07:13 | 0 | **15/15 PASS**；gate/adapter BLOCKED；SDK 未 import | [livegate-adapter.stdout.log](../artifacts/reviewer-g2l11-independent/logs/livegate-adapter.stdout.log) |
| Node B / absence | 只读检查 / `podman ps -a` / `pgrep` | 17:09:28 | 0 | Node BLOCKED；无容器/残留进程 | [node-b-blocked.txt](../artifacts/reviewer-g2l11-independent/logs/node-b-blocked.txt)、[no-key-absence.txt](../artifacts/reviewer-g2l11-independent/logs/no-key-absence.txt) |

G2 core 15 个实际测试名（独立 `--collect-only` 确认）：

`test_int01_closed_loop_settles_once`、`test_int03_unbound_call_never_dispatches`、`test_int17_second_call_for_same_reservation_is_rejected`、`test_int06_sigkill_restart_does_not_replay_dispatch`、`test_int05_two_broker_processes_race_one_license`、`test_int01_claim_once_settle_and_claim_completion`、`test_int05_two_broker_processes_concurrent_claim_single_grant`、`test_int06_sigkill_after_claim_restart_replay_no_regrant`、`test_legacy_egress_ids_are_rejected_as_settlement_ids`、`test_bind01_reservation_a_actual_b_route_mismatch_ledger`、`test_bind06_duplicate_bound_claim_at_most_once`、`test_bind07_unmodified_success_once_and_ledger_link`、`test_bind08_reserve_dispatch_allowed_without_claim_zero_dispatch`、`test_v1_old_claim_without_expected_fields_still_succeeds`、`test_v1_new_egress_rejects_unbound_claimer`。

### 4.1 RED2 分类（独立核对）

| 失败 | 类型 | 独立观察 |
|---|---|---|
| L11-ATT-01 | API-shape | `KeyError: 'classification'` |
| L11-ATT-03 | 行为 | provider 实际 1 次，旧 `provider_calls=0`；断言失败 |
| L11-ATT-04 | 行为 | 旧 `NOT_DISPATCHED` vs 期望 `BILLABLE_UNKNOWN` |
| L11-ATT-06 | 行为 | `DID NOT RAISE KeyboardInterrupt` |
| L11-ID-02 | 行为 | 中文 run_id 两侧 call-id 不等 |
| L11-JRN-01 | 行为 | 6 条 unknown completion 后 journal 行数 6 ≠ 0 |
| L11-DIAG-01 | 行为 | 诊断后 `ATTEMPT_LIMIT_EXCEEDED` |
| L11-DIAG-02 | API-shape | `AttributeError: 'LogicalStreamEgress' object has no attribute 'policy_checks'` |

旧 `logs/red.stdout.log` 的 **10 failed / 14 passed** 仅作历史保留：其 argv 指向 `stage-old`，失败含 `NameError: AttemptState` / `KeyError: classification` / 旧 diag policy，不是 exact-base 证据；packet 已标 superseded，本审阅不采用其计数。

### 4.2 独立 probe 覆盖

`independent_probe.py` 为 reviewer 自写，只 import production modules，不 import owner tests，73 checks 全部 PASS：

- **T3**：self-consistent `m0.prepared.v0` / `m0.prepared.v999` → reject `PREPARED_SCHEMA_VERSION_MISMATCH`，permission None，claimer 0；合法 v1 → allowed，claimer 1；nested mapping 修改 → `PREPARED_DIGEST_MISMATCH`，claimer 0。
- **T1**：provider 进入 1 次后 `RuntimeError` → `BILLABLE_UNKNOWN`、held>0、非 `NOT_DISPATCHED`、无 retry、permission 二次 dispatch provider 0；`KeyboardInterrupt` → re-raise，state `BILLABLE_UNKNOWN`。
- **T2**：中文 run_id 下 `prepared_call_id == derive_call_id`；跨进程一致；真实 stdio Broker reserve/claim/settle 接受同一 ID。
- **T4**：6 个 unique unknown reservation + 6 个 invalid completion → journal 0 增长；`max_messages=2` cap 下合法 settle/fail 成功；同 message id 幂等；新 id 已结算不增长。
- **T5**：10 次 descriptor diagnostics 后 claim/dispatch 仍成功；`policy_checks=11`（10+claim admission）、`claims_granted=1`、`dispatch_attempted=1`、`provider_invocations=1`；`attempts_detail` 逐条分离；两个 reservation 的 claim/attempt 归属正确。
- **T6**：同一 permission 第二次 dispatch provider 0。

## 5. 发现（ID / severity / evidence）

以下均为 **P2、非阻断**；不影响 `PASS_FOR_DECLARED_G2L11_SCOPE`，但应记录/在 G3 前处理。

### R-01 [P2, Evidence] Packet 元数据/交付物漂移

- **Packet tar**：`docs/M0_G2L11_ERRATA.md` 声称 packet tar=`96ca6959d643064896c1f93c2d683594fadaac671a98b221ae2aa1d3144b16b7`，但仓库内**没有交付该 tar**；对当前 49-file packet 做 `tar --sort=name --mtime=@0 --owner=0 --group=0 --numeric-owner` 得 `35b9f8b6…`，plain tar 得 `102c02c1…`，均不等于声明值。errata 的 `manifest.sha256`/`hashes.sha256` 数值也与当前 packet 不同（当前 `2200af10…`/`4fae0a70…`），说明 errata 引用的是 16:31 旧 packet，16:35 重新生成后未同步。
- **`docs_commit` 绑定**：manifest 写 `docs_commit=c140541`，但 packet 内两份 docs 副本与 worktree 均为 `1d2efe2` 内容（`M0_G2L11_FIX_REPORT.md` `8129be14…`；`M0_G2L11_REVIEW_REQUEST.md` `9117f078…`），并非 `c140541`；manifest 另列 `docs_alignment_commit=1d2efe2`，属于披露但仍存在主字段歧义。
- **`evidence_end_utc`**：manifest 写 `16:24:11Z`，而 RED2 的 argv 起始为 `16:30:00Z`、packet 文档在 `16:35` 重新生成；证据时间窗未覆盖 RED2/errata。
- **GREEN2 stage 绑定**：`logs/green2.argv.json` mount 的是 `artifacts/g2l11/stage-new`（6140 files；normalized `989cf90a…`），不是 manifest 声明的 `artifacts/g2l11/stage`（198 files；`ab95ffb4…`）。两 stage 的 `src/tests/config/scripts` 逐文件一致；reviewer 在 exact 198-file stage 重跑 L11 仍 **24 passed**，所以计数/代码结论不受影响，但 owner 日志与声明 stage 的绑定不精确。
- **证据**：[packet-audit.json](../artifacts/reviewer-g2l11-independent/packet-audit.json)、[identity-audit.txt](../artifacts/reviewer-g2l11-independent/logs/identity-audit.txt)、[green2-stage-binding.txt](../artifacts/reviewer-g2l11-independent/logs/green2-stage-binding.txt)、[packet manifest](../artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b/manifest.json)、[errata:40](../docs/M0_G2L11_ERRATA.md#L40)。
- **影响**：不影响代码/测试计数；影响 packet 的“单字节可复验”与维护者归档。建议重新生成 packet 后统一 `docs_commit`、evidence window、tar 交付与 hash，或明确 tar 为可选。

### R-02 [P2, Code/API-doc] `dispatch_count` 注释与契约语义相反

- [`egress.py:705`](../src/autoteacher_m0/security/egress.py#L705) 注释写 “confirmed completed provider returns”；但 [`_started_failure`](../src/autoteacher_m0/security/egress.py#L721) 在 provider after-entry 失败时也 `+= 1`。Owner 的 Review Request 已明确 `dispatch_count` = provider callable entry/attempt-start（含 after-entry 异常），并非 completed returns。
- 当前仓库无 `dispatch_count` 消费者；属 API 文档/注释漂移，不是功能绕过。
- **证据**：源码行；[review request](../docs/M0_G2L11_REVIEW_REQUEST.md#L24)。建议改注释或改名，避免后续消费者误解。

### R-03 [P2, Code/Residual] 取消/中断语义只覆盖 provider 路径的 KI/SystemExit

- provider 路径：`KeyboardInterrupt`/`SystemExit` re-raise（[`egress.py:753`](../src/autoteacher_m0/security/egress.py#L753)）；但 `except BaseException` 会把 `asyncio.CancelledError` 转为 `BILLABLE_UNKNOWN` 并正常返回。独立 probe 实测：`raised=null, state=BILLABLE_UNKNOWN, provider_calls=1`（[cancel-probe](../artifacts/reviewer-g2l11-independent/logs/cancel-probe.stdout.log)）。
- claimer 路径：`_claim_with` 的 `except BaseException`（[`egress.py:494`](../src/autoteacher_m0/security/egress.py#L494)）会把 claimer 抛出的 `KeyboardInterrupt` 吞成 `BROKER_CLAIMER_ERROR`；独立 probe 实测 `raised=null, decision_allowed=false`（[claimer-interrupt](../artifacts/reviewer-g2l11-independent/logs/claimer-interrupt-probe.stdout.log)）。
- 当前 G2-L1.1 无 asyncio/controller 接线，provider 是同步 callable，故按 **P2/G3 条件** 处理：不阻断本轮离线收尾，但 G3 接 controller/cancel 前必须显式 re-raise cancellation/中断异常，并补测试。若 G3 引入异步或 SIGINT 路径，此项应升级为阻断。
- **证据**：上述 probe；playbook §5.1.5。

### R-04 [P2, Code/Validation] Egress 对 `run_id` 的边界与 `CallIdentity` 不一致

- [`prepared_schema_error`](../src/autoteacher_m0/security/egress.py#L166) 仅要求 `run_id` 非空/无首尾空格；[`CallIdentity._bounded_text`](../src/autoteacher_m0/accounting/call_identity.py#L58) 要求 1..128 且禁止控制字符。
- 独立 probe：200 字符 `run_id` 的 self-consistent prepared 在 egress 得到 `allowed=true, claimer_calls=1`；同一 run_id 的 `derive_call_id` 抛 `IdentitySchemaError`（[runid-validation](../artifacts/reviewer-g2l11-independent/logs/runid-validation-probe.stdout.log)）。
- 影响：egress 可能接受 accounting 判定为非法的 identity；当前由 trusted Controller 构造，未观察到实际绕过；属 P2 校验一致性缺口。建议 egress 复用 `CallIdentity` 的 run_id 校验（或调用 `derive_call_id` 做最终核对）。

### R-05 [P2, Code/Concurrency] T4 precheck 与 journal 写入不是同一事务

- `handle` 的 settle/fail precheck 在一个 `_transaction()` 中（[`broker.py:314-342`](../src/autoteacher_m0/accounting/broker.py#L314)），随后 `journal_once` 另开事务（[`broker.py:343`](../src/autoteacher_m0/accounting/broker.py#L343)）。多 Broker 进程场景下，precheck 之后、journal 之前 reservation 被另一进程结算/改状态，新的 message id 仍可能把 `ALREADY_SETTLED`/`INVALID_USAGE` 响应写进 journal；`journal_once` 本身没有 `max_messages` 上界（[`ledger.py:307`](../src/autoteacher_m0/accounting/ledger.py#L307)）。
- 本审阅的串行 probe（6 unknown + 6 invalid）结果为 0 增长，且 cap 下 settle/fail 成功；未独立复现该并发窗口。T4 为维护者批准的 P2 最小修复，故列为非阻断残余，建议 G3 前把 precheck 与 journal insert 合并到同一事务，或在 journal 层加硬上界。
- **证据**：[probe](../artifacts/reviewer-g2l11-independent/logs/probe.stdout.log)、源码行；[T4 说明](../docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md#L251)。

### R-06 [P2, Evidence/Test-quality] Owner RED 证据仍有旧数字；T3 PREP-01 不是行为 RED

- [`docs/M0_G2L11_FIX_REPORT.md:23`](../docs/M0_G2L11_FIX_REPORT.md#L23) 仍写 “**10 failed / 14 passed**”（旧日志），与 errata/README/review request 的 **8 failed / 16 passed** 矛盾；文末虽有 errata 注记，但未改该行。
- `L11-PREP-01` 在 base 上会因 digest 不一致先行拒绝（测试用 `replace` 改了 `schema_version` 但未重算 digest），所以它在 red2 中 PASS 不等于 T3 行为已 RED；errata 已说明。reviewer 用 self-consistent v0/v999 的独立 probe 证明 base 实际 `allowed=true, claimer=1`，impl 才拒绝（[t3-base](../artifacts/reviewer-g2l11-independent/logs/t3-base.stdout.log)、[t3-impl](../artifacts/reviewer-g2l11-independent/logs/t3-impl.stdout.log)）。
- 影响：不影响 GREEN/计数；影响证据解释与 fail-first 的严格性。建议修正 fix report 的旧数字，并把 self-consistent schema probe 加入 L11-PREP-01。

## 6. T1–T6 / T4–T5 独立回归结论

| 工作包 | 独立结论 | 依据 / 备注 |
|---|---|---|
| T1 provider after-entry 归因 | **PASS（required scope）** | ATT-01..06 在 GREEN 24P；probe 记录 RuntimeError/KI、held>0、no retry、single-use permission；R-03 为更广义 cancellation 的 P2/G3 残余 |
| T2 canonical Unicode call-id | **PASS** | 中文 run_id 下 prepared/accounting 一致；跨进程一致；真实 Broker reserve/claim/settle 同一 ID；R-04 为 invalid/extreme run_id 的 P2 校验缺口 |
| T3 Prepared strict schema | **PASS** | self-consistent v0/v999 在 claimer 前拒绝；合法 v1 通过；nested mutation 拒绝；base/impl fail-first 独立复现；R-06 记录 owner PREP-01 证据弱点 |
| T4 journal 有界/completion | **PASS（serial/minimal）** | 6 unknown + 6 invalid 不增长；cap 下 settle/fail；同 id 幂等；新 id 不增长；R-05 为多进程 race 的 P2 残余 |
| T5 descriptor 计数/归因 | **PASS** | 10 diagnostics 不影响后续 claim；`policy_checks/policy_allowed/claims_granted/dispatch_attempted/provider_invocations` 分离；`attempts_detail` 逐 attempt 正确；legacy `attempts` = claims |
| T6 Python/G2 回归 | **PASS** | 625/1 skip；G2 core 15P；verify PASS；Ruff clean；gates/adapter 动态 BLOCKED；Node B BLOCKED；run_live 动态 UNVERIFIED（静态硬停） |

**维护者 T4/T5 非阻断前提**：独立回归已通过（T4 serial 0 增长、cap completion、幂等；T5 counters/quota/details）。因此可接受 T4/T5 的 P2 最小修复为非阻断，但 R-05 应列为 G3 hardening。

**旧 v1 Unbound Claim**：`claim_dispatch` / `require_claim` 仍保留无 expected binding 的 legacy 路径（[`egress.py:516`](../src/autoteacher_m0/security/egress.py#L516)、[`:595`](../src/autoteacher_m0/security/egress.py#L595)）；按维护者裁定，它是 **G3 安全迁移要求**，不阻止 G2-L1.1 离线收尾；不得将其用于生产 Bridge。

## 7. Node B 与 G3 缺口（不得 PASS）

### Node B — BLOCKED / UNVERIFIED

- 固定 OCI 内 `shutil.which("node")`、`npm`、`npx` 均为 `None`（无 `/bin`/`/bin/sh`）；**未**在宿主直接运行项目 Node 代码。
- 仓库发现的真实命令（未执行）：
  - `plugins/runtime-budget-guard`: `node --test tests/*.test.mjs`
  - `plugins/skill-lookup`: `node --test test/*.test.mjs`
  - `plugins/offline-fixture`: build-only（`tsc`）
- 宿主有 `node v22.23.2`，但按约束**未使用**；不能用宿主结果替代固定环境。
- 结论：**BLOCKED/UNVERIFIED，不写 PASS**。需要维护者提供受审、固定版本的 Node 环境后再跑。

### `run_live.sh` — 静态硬停，动态 exit 3 UNVERIFIED

- 文件与 base 字节一致（SHA-256 `a8a2753f…`）；内容只有 2 条 `printf` + **无条件 `exit 3`**，无分支/无 Key 读取/无 HTTP。
- 固定 OCI 无 `/bin/sh`/`/bin`，无法在受审固定环境执行 shell 脚本；本审阅**未**用宿主 shell 或 host binary 伪装执行。
- 结论：静态行为仍为硬停；**动态 exit 3 = UNVERIFIED**，不伪造 PASS。LiveGate/Adapter 已动态验证 BLOCKED（`gates.inspect` 即使给足 evidence 仍 BLOCKED；`HarnessAdapter.run/resume/_new_harness` 在 import SDK 前抛 `SECURITY_BLOCKED`）。

### G3+ 缺口

- 真实 provider wire / HTTP attempt / usage / invoice / exactly-once / 远端账单：**未验证**。
- ATTEMPT_STARTED 仅内存诊断；跨进程 crash 持久化未实现（G3 硬门槛）。
- 真实工具 registry / DSH Plugin / SDK B 层：BLOCKED。
- 旧 v1 unbound claim 的生产迁移、cancellation 语义（R-03）、T4 并发原子性（R-05）、run_id 校验（R-04）：G3 前处理。
- **G3/G4/G5/G6 未启动；Live/GO 未授权。**

## 8. 最终裁定与下一步条件

**`PASS_FOR_DECLARED_G2L11_SCOPE`** — 仅覆盖：

- Python 离线 T1–T6（含 G2 核心回归、full tests、verify、Ruff）；
- T4/T5 按维护者批准的 P2 最小修复，独立回归通过；
- 不改 `gates.py` / `dsh_adapter.py` / `run_live.sh`，LiveGate/Adapter 保持 BLOCKED。

**不覆盖 / 不得据此升级**：

- Node B（BLOCKED/UNVERIFIED）；
- `run_live.sh` 动态 exit 3（UNVERIFIED；静态硬停）；
- 真实 provider/Key/模型/HTTP/usage/invoice/exactly-once；
- G3/G4/G5/G6、Live、GO。

**进入 G3-A 前建议**：修复/记录 R-01（packet 元数据）、R-03（cancellation）、R-04（run_id 校验）、R-05（T4 事务原子性）；提供受审 Node 环境；保持旧 v1 unbound claim 不进入生产 Bridge。

## 9. 证据索引

- 本审阅证据：[manifest.json](../artifacts/reviewer-g2l11-independent/manifest.json)、[hashes.sha256](../artifacts/reviewer-g2l11-independent/hashes.sha256)、[commands.jsonl](../artifacts/reviewer-g2l11-independent/commands.jsonl)、[stage-identity.txt](../artifacts/reviewer-g2l11-independent/stage-identity.txt)、[packet-audit.json](../artifacts/reviewer-g2l11-independent/packet-audit.json)
- Stage：[green stage](../artifacts/reviewer-g2l11-independent/stage)、[red2 stage](../artifacts/reviewer-g2l11-independent/stage-red2)
- Probe：[independent_probe.py](../artifacts/reviewer-g2l11-independent/probe/independent_probe.py)、[t3_failfirst_probe.py](../artifacts/reviewer-g2l11-independent/probe/t3_failfirst_probe.py)、[cancel_probe.py](../artifacts/reviewer-g2l11-independent/probe/cancel_probe.py)、[claimer_interrupt_probe.py](../artifacts/reviewer-g2l11-independent/probe/claimer_interrupt_probe.py)、[runid_validation_probe.py](../artifacts/reviewer-g2l11-independent/probe/runid_validation_probe.py)、[livegate_adapter_probe.py](../artifacts/reviewer-g2l11-independent/probe/livegate_adapter_probe.py)
- Packet：[README](../artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b/README.md)、[manifest](../artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b/manifest.json)、[diff.patch](../artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b/diff.patch)、[evidence-matrix](../artifacts/review-packet-g2l11-bf1e84dab9c74f1bec919633672dc29abfa7a77b/evidence-matrix.csv)
- Docs：[fix report](../docs/M0_G2L11_FIX_REPORT.md)、[errata](../docs/M0_G2L11_ERRATA.md)、[review request](../docs/M0_G2L11_REVIEW_REQUEST.md)、[G0 baseline](../docs/M0_G0_CURRENT_BASELINE.md)、[playbook](../docs/Autonomous_Teacher_M0_G2L11_to_G6_Agent_Playbook_2026-11-16.md)

**本审阅未修改生产源码/tests/scripts，未 commit，未读真实凭据，未使用真实模型或外网，未进入 G3/G4/G5/G6。**
