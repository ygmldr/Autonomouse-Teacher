# PR3 独立审计 — 可信 Live Controller 设计 + 无 Key 失败演练

- 版本：REVIEW-CLOSEOUT-PR3-v1（2026-11-14 UTC）
- 审计者：`verify2`（非实现者，未参与 PR3 实现；PR3 由 `sdk-docs` 实现）
- 审计对象：冻结提交 **`9b77a3786c72a0f509f4c21d34f27314a92f3563`**（PR3，父 `fdcfdc9`）
  与 owner 证据 **`artifacts/m0-controller-no-key/manifest.json`**（sha256 `b5c16f81704a4d8c0aa51c2c525afae1405dfb63ad0ef636bc3cc033920ed597`，
  `evidence.sha256` 17/17）。
- 原始证据：[`artifacts/reviewer-closeout-pr3/`](../artifacts/reviewer-closeout-pr3/)（独立 stage、argv/UTC/exit/日志、静态核对、运行计数、Ruff 双 scope、容器 absence）。

## 0. 结论

**PASS_FOR_DECLARED_NO_KEY_PR3_SCOPE_WITH_E5_BLOCKED**：PR3 冻结提交的 security 设计代码/负测/证据在其声明的**无 Key 子集**内成立；未发现阻断性实现/测试缺陷。**E5-PreLive 整体仍 NOT PASS、Live/E1–E5/总体判定仍 BLOCKED/DECISION PENDING**（本审计不改变该结论）。

**一项非阻断发现 V-PR3-1（证据 scope 准确性）**：owner manifest/两份 docs 泛写 “Ruff `All checks passed!`”，但按项目既有 lint 约定（phase5 `ruff check --no-cache .`，repo-wide）在 PR3 冻结 stage 上独立复跑得到 **4 个 F401**——全部来自 **PR1 提交的两个测试文件**（`tests/integration/budget_bridge/test_stdio_capacity_f2.py`、`tests/unit/accounting/test_broker_capacity_f1_f2.py`），PR3 新增 security 文件本身 Ruff 干净（scoped 运行 `ruff check src/autoteacher_m0/security tests/unit/security tests/integration/sandbox scripts` = All checks passed）。建议：**PR3 文档/manifest 明确 Ruff scope** 且 **PR1 测试文件清理未用 import**（微小、无行为变更）后重跑 repo-wide Ruff；不需要新安全 SHA 或重跑 security 测试。见 §6。

## 1. 方法与隔离边界

- 仅使用固定 digest 无 Key/禁网隔离 OCI（image `localhost/autoteacher-local-oci@sha256:62d3569e…`、image id `56db1e2a…`；`--network none`、`--http-proxy=false`、`--unsetenv-all`、uid 65534、`--read-only`、cap-drop ALL、no-new-privileges、pids/cpu/memory 限制、`/tmp`+`/work` noexec tmpfs）。宿主只做 Git/哈希/JSON 与 podman launcher；**未在宿主执行项目 Python/pytest**。
- 用 `git archive 9b77a37` 生成**独立 stage**（146 文件，tar sha256 `1d3a132d…`），未使用 owner `stage/` 作为真值（owner stage 69 文件 normalized `5c27c021…`，与 manifest 一致；仅 `tests/unit/accounting/test_broker_capacity_f1_f2.py` 一个文件与冻结提交不同，属 PR1 定稿前快照，不在 PR3 测试 scope）。
- 所有运行使用审计者新 argv/新日志/独立容器名 `at-m0-rev-pr3-*`；0 真实 Key（仅 `oc_sk_FAKE_REHEARSAL_…` 假值）、0 模型/HTTP；未读 `/root/.config/autoteacher`。

## 2. Git / 提交范围

| 核对项 | 结果 |
|---|---|
| PR3 commit | `9b77a37`，父 `fdcfdc9`，`2026-11-14 15:08:21 +0000` |
| 变更文件 | **12 个**（`git diff --name-status fdcfdc9 9b77a37`）：6 个 security 文件（`__init__` + authorization/ed25519/credential_boundary/watchdog/live_controller）、4 个测试、2 个 docs |
| 禁止改动混入 | **无**：`git diff --name-only` 中无 `accounting/`、`runtime-budget-guard/`、`scripts/`；`gates.py`/`docker_runner.py`/`scripts/run_live.sh`/`runtime/dsh_adapter.py` 的 commit blob 与父提交逐一相同（0 changed） |
| `git diff --check` | exit 0 |
| 历史证据 | 未改：phase5 manifest `391767d3…`、phase5 evidence `df63e46f…`、guard manifest `05224052…`、PR0 baseline `d252c82b…`、PR1 manifest `df14f3c1…` 均不变 |
| 证据锚 | owner manifest `b5c16f81…`；`evidence.sha256` **17/17 OK**；image inspect id/digest/uid 与 manifest 一致 |

## 3. 独立重跑（固定 digest 无 Key OCI；新 argv/UTC/exit/日志）

| 用例 | 命令要点 | UTC | exit | 实际日志 | 判定 |
|---|---|---|---|---|---|
| PR3 安全全套 | `pytest tests/unit/security tests/integration/sandbox -q -p no:cacheprovider`（stage=PR3 commit） | 15:24:50–15:25:09 | 0 | **104 passed, 1 skipped**（105 collected） | PASS（与 owner 数字一致） |
| 既有 security 回归 50 | `pytest tests/unit/security/test_docker_runner.py tests/unit/security/test_gates.py -q` | 15:25:09–15:25:10 | 0 | **50 passed** | PASS（36+14） |
| 带 `/input` 探针复跑 | 同上全套 + `probe-input` mount | 15:25:10–15:25:29 | 0 | **105 passed** | PASS（证明 1 skipped 仅因未挂 `/input`，非 PR3 失败） |
| Ruff（PR3 scoped） | `ruff check --no-cache src/autoteacher_m0/security tests/unit/security tests/integration/sandbox scripts` | 15:27:25 | 0 | `All checks passed!` | PASS（PR3 新文件干净） |
| Ruff（repo-wide，项目既有约定） | `ruff check --no-cache .` | 15:27:25 | 1 | **4 errors（F401）**，全部为 PR1 测试文件未使用 import | **V-PR3-1**（scope/跨 PR；见 §6） |

> `pytest` 与上表 UTC 为审计者独立运行的 start–end；日志 SHA/字节、argv 见 `artifacts/reviewer-closeout-pr3/{commands.jsonl,logs/}`。skip 为既有 `tests/integration/sandbox/test_probe_contract.py`（需外部 `/input` 探针，owner 文案亦如此标注）。

## 4. 安全负测真实性（静态 + 测试执行核对）

| 要求 | 结论 | 证据（源码/测试） |
|---|---|---|
| ExecutionAuthorization 仅仓库外 JSON + Ed25519 验签 + 撤销文件 | **成立** | `authorization.py`：`_external_regular_file`（绝对路径、拒 symlink、resolve 后在 repo 外、regular file、大小界；`:94-112`）；`_parse_json_object` 拒 Markdown/重复 key/非严格 JSON（`:73-91`）；`load_execution_authorization` 强制外部三文件（`:236-258`） |
| 五 SHA/route/tools/budget/deadline 绑定 | **成立** | `BINDING_NAMES` 5 项（`:37-43`），逐项 mismatch（`:290-304`）；route 精确匹配（`:306-319`）；tools 只允许 `skill_lookup` 且与实际 registry 完全一致（`:321-332`）；budget scope/上限/max_calls/per-call≤total/total≤$10（`:334-357`）；deadline 范围（`:359-377`） |
| Markdown/env/`--live`/仓库内 JSON/symlink/重复 key/未知字段/过期/撤销 → 拒绝 | **成立** | 上述源码 + 测试 `test_authorization.py` 28 项（正例 1、负例覆盖全部类别）+ 集成测试 CLI `--live` 返回 BLOCKED/3、HarnessAdapter 恒 `SECURITY_BLOCKED`、ENV 变量不可解锁 |
| 有效外部签名仍 BLOCKED | **成立** | `TrustedLiveController.inspect` 恒加入 `ALWAYS_BLOCKED_REASONS`（`live_controller.py:38-44,128-147`），无 run/execute 方法；集成测试 `test_signed_authorization_is_valid_but_controller_still_blocked` 通过 |
| 伪造/篡改签名拒绝 | **成立** | ed25519 `verify` 长度/曲线点/`S<L` 检查（`ed25519.py:127-140`）；测试 `test_tampered_payload_or_signature_is_rejected`、`test_self_signed_and_unknown_key_are_rejected` |
| 假 Key 不入 candidate env/日志/audit | **成立（fake 哨兵）** | `credential_boundary.py` allowlist/secret 命名/值模式/`redact_secrets`/`assert_log_clean`（`:28-134`）；`LauncherOnlySecret` repr 恒 redacted（`:63-87`）；测试 13 项 + 集成 `test_fake_launcher_key_never_reaches_candidate_or_audit_log` |
| mount/argv/egress allowlist 拒危险路径 | **成立（helper 层）** | `validate_candidate_mounts`（只读、仅 `dst=/input`、stage root 内、拒 `/root`/home/.config/credentials/socket）；`validate_candidate_argv`（network none/read-only/cap ALL/no-new-priv/uid、`--unsetenv-all`、`--http-proxy=false`、禁 `--env` 非 allowlist、禁 publish/privileged/socket）；`EgressPolicy` 仅 `opencode.ai:443` POST `/inference/go/`（`:214-238`） |
| watchdog kill 进程树 + absence + PENDING 保守不重试 | **成立（rehearsal）** | `kill_process_tree` SIGTERM→grace→SIGKILL + survivors 断言（`watchdog.py:129-166`）；`confirm_container_absence` 用 `ps` 观测而非 `rm rc`（`:169-193`）；`PendingConservative(retry_allowed=False, worst_case_reserved=True)`（`:64-71`）；超时/step/dispatch → kill + pending；测试 8 项 |
| Controller 无 run/execute；CLI/run_live/Adapter 入口仍 BLOCKED；不改 LiveGate | **成立** | `live_controller.py` 无执行方法、`inspect` 恒 BLOCKED；`assert_live_entrypoints_blocked` 静态核对 run_live.sh exit3、adapter `_require_live_authorization`/SECURITY_BLOCKED、CLI LiveGate；集成测试实际执行 CLI `--live`=BLOCKED/3、Adapter 抛 SECURITY_BLOCKED；`gates.py`/`run_live.sh`/`dsh_adapter.py` commit blob 0 改动 |
| 不把 NO-KEY 子集写成 E5-PreLive PASS | **成立** | `E5_PRELIVE_NO_KEY_REPORT.md` 明确 “E5-PreLive 整体 NOT PASS / Live BLOCKED”；manifest `e5_prelive.overall=E5_PRELIVE_NOT_PASS`，逐项仅 “NO-KEY SUBSET PASS” |

**残余风险（owner 已如实列出，审计确认）**：Ed25519 为自研 RFC8032 参考实现，**非常数时间且未经独立审计**（静态观察其 verify 未做 cofactor/small-order 归一化；在“密钥由维护者固定 pin、只验 detached 授权”的模型下风险有限，但不得当作生产级签名库）；OS 只读挂载/进程身份/egress/Key custody 属部署工作，未证明；watchdog 测试用 fake 容器 engine（真实 podman cleanup 由既有 ContainerRunner 测试覆盖）；`/input` 真 OS 负向探针本次 skip；测试 stage 为 root-owned 世界可读副本，生产必须不可变受控输入。以上均不改变“NO-KEY 子集 PASS、E5 整体 BLOCKED”。

## 5. 证据链与计数一致性

- owner manifest `b5c16f81…`：stage 69 文件 normalized `5c27c021…`（独立复算 owner stage = 该值）；image digest/id 与实测一致；run UTC `15:00:14–15:00:33Z`、exit 0、collect 105/passed 104/skipped 1/failed 0 与原始日志一致；evidence `17/17 OK`。
- 本审计独立计数：104/1（无 `/input`）、50（既有）、105（带 `/input`）与 owner 日志/manifest 一致；Ruff scoped 一致，repo-wide 见 §6。
- 身份：`gates.py`/`docker_runner.py`/`run_live.sh`/`dsh_adapter.py` 与父提交 blob 完全相同；PR3 提交仅 12 文件；无 accounting/guard 改动。
- 隔离/无 Key：`--network none`、`--unsetenv-all`、只读 rootfs、uid 65534、cap0/nnp；测试仅 fake 值；0 模型/HTTP/真实 Key；宿主未跑项目代码。
- 历史 evidence 未改（§2）；容器 absence 查询 0；本审计运行用 image（不写 rootfs）；rootfs/deps 复核 canonical `25491e45…`/`e07729d7…`。

## 6. 发现 V-PR3-1（低严重度，证据 scope 准确性；非阻断）

- owner manifest `run.ruff` 与 `docs/E5_PRELIVE_NO_KEY_REPORT.md:24`、`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md:152` 泛写 **“Ruff `All checks passed!`”**，未写 scope。
- 按项目既有 lint 门（phase5/PR0 的 `ruff check --no-cache .`，repo-wide）在 PR3 冻结 stage 上复跑：**exit 1，4 个 F401**，全部来自 **PR1 提交**的两个测试文件：
  - `tests/unit/accounting/test_broker_capacity_f1_f2.py:7,8,10`（`deepcopy`/`json`/`pytest` 未使用）
  - `tests/integration/budget_bridge/test_stdio_capacity_f2.py:7`（`pathlib.Path` 未使用）
- PR3 新增 security 文件 scoped `ruff check` 通过；PR3 security 结论不受影响。
- **建议**：① PR1/后续轻量提交移除上述未用 import（无行为变更）；② PR3 docs/manifest 将 Ruff 结果标注为 scoped（或重跑 repo-wide 后更新）；③ 无需新安全 SHA、无需重跑 security 测试。已报 Lead + sdk-docs（及 broker-docs，因文件属 PR1）。

## 7. 残余/未验证（不夸大）

1. NO-KEY 子集**不是** E5-PreLive 整体 PASS：独立人类授权/凭据托管/部署边界、真实 merged Runtime/工具 registry/插件加载失败模式、真实 egress/Key Broker 仍 BLOCKED（PR4/PR5）。
2. Ed25519 参考实现未经独立审计/非常数时间；OS 权限/只读挂载/进程隔离/容器清理为部署工作，测试用 fake engine；`/input` 真 OS 负向探针本次 skip。
3. 真实 Provider wire/usage/账单/错误/模型映射、真实 agent-loop compaction/Judge、LiveGate 允许路径仍 UNVERIFIED/BLOCKED；不改变 DECISION PENDING。
4. V-PR3-1 与 PR1 测试 lint 为记录/质量门问题，不是 security 缺陷。

## 8. 证据索引

- 审计 manifest：[`artifacts/reviewer-closeout-pr3/manifest.json`](../artifacts/reviewer-closeout-pr3/manifest.json)、`manifest.sha256`、`evidence.sha256`；独立 stage `stage/`（146 文件）+ `stage.tar`（`1d3a132d…`）。
- 运行：`logs/{pr3-security-tests,pr3-existing-security50,pr3-security-with-input,pr3-ruff-scope-pr3,pr3-ruff-repo}.{argv.json,stdout.log,stderr.log}` + `commands.jsonl`。
- owner 交叉核对：`artifacts/m0-controller-no-key/`（manifest `b5c16f81…`、evidence 17/17、independent owner-stage `5c27c021…`）。
- 环境：`containers.*`、`podman-ps-all.txt`、rootfs/deps canonical。
