# 第四阶段独立审计 — SDK 离线会话闭环 + stdio 账本桥集成（非 Live）

- 审计者：`verify2`（非实现者；本任务只写审计报告/证据，不改实现、测试、Gate、Adapter 或历史证据）
- 日期：2026-11-14 UTC
- 审计对象：第四阶段冻结提交 `f674403d12a6b51249b772090b7b004013d4ceb1` 与其外部集成证据
  [`artifacts/phase4-integration/manifest.json`](../artifacts/phase4-integration/manifest.json)
  （SHA-256 `bfea6fa1d4cb3d144879b784aeb76c73f1fee3ef0842034b37dba939e90a2df5`）
- 原始审计证据：本目录 [`artifacts/reviewer-phase4/`](../artifacts/reviewer-phase4/)
  （argv/UTC/exit/日志/语义校验/容器 absence/hash）；证据总清单见
  [`evidence.sha256`](../artifacts/reviewer-phase4/evidence.sha256)。

## 0. 结论

**第四阶段冻结交付在其声明的离线范围内通过独立复核；未发现阻断性实现缺陷。**
本次审计独立重跑了全量 pytest（326）、专门 E1-02 子集（89）、stdio 账本 148 回归、Ruff、
wheel 构建、wheel-only 无源码安装 CLI/E1 API、真实 Cordis 插件 strict 构建 + 8 项 registry 测试、
SDK 17 用例 suite 与其 strict build；并对阶段 1/2/3 历史证据、冻结 manifest 的 53+42 项
artifact/key hash、SDK fixture 与 broker 的边界声明做了交叉核对。

**边界不变**：SDK fixture 是「真实锁定 DSH 引擎/真实 Python SDK/RPC/Session/工具注册与执行
链路 + 显式 `offline-test-only`/`fixture-v1` 确定性脚本 provider」，**不是模型、不是 E1b/E2/E3
Live、不是生产 Adapter、不是人类授权**；stdio broker 是固定 scope 的 **bookkeeping**，
`dispatch_allowed` 仅表示该逻辑请求首次被记录，**不是授权、Key 代理、provider usage 认证或
真实账单上限**；**task22 公开 `llm/stream` 预算预留/结算 middleware 未实现、未接线**。
真实模型/E1/E2/E3/E5、P03 独立人类授权、外部 watchdog、真实 usage/逐 step 记账仍
**BLOCKED/NOT RUN**，总体 **DECISION PENDING**；生产 Gate/Adapter/默认 primary 路由未改。

## 1. 审计方法

- 全部项目代码只在既有固定 digest、无 Key、禁网、非 root、只读 rootfs、cap-drop ALL、
  no-new-privileges、cgroup 受限的本地 OCI 容器执行（`localhost/autoteacher-local-oci@sha256:62d3569e…`，
  image id `56db1e2a…`，运行后独立 inspect 的 digest 与 argv pin 一致）；宿主只做 Git/哈希/JSON 证据整理与
  podman launcher，**未在宿主执行项目 Python/pytest/import/TS**。
- 审计者用 `git archive f674403 -- <公开可执行路径>` 重建公开 stage（94 文件），逐文件核对
  冻结 Git blob 与 `final-stage` 字节一致后再用于重跑；不信任 owner 生成的 stage 作为执行输入。
- 对 owner 已冻结、无法“从零重建”的重放输入（插件依赖闭包、SDK replay stage、build input），
  先按 manifest 记录的 normalized-tar/key hashes 做**只读交叉核对**，再在其冻结字节上独立执行
  argv 并写新日志；报告中逐项标注“独立重跑”或“交叉核对”。
- 所有重跑使用独立容器名 `at-m0-reviewer-phase4-*`，运行后按精确名前缀与全局 `podman ps -a`
  查询 absence；每次运行的 argv、UTC、exit 与日志 hash 均落盘。

## 2. 源快照、Git 与历史证据

| 核对项 | 结果 |
|---|---|
| `git rev-parse HEAD` | `f674403d12a6b51249b772090b7b004013d4ceb1` |
| working tree | `git status --porcelain` 为空；`git diff --check` exit 0 |
| 相对父提交 `e0ce9c8` 变更 | 17 文件（README/runbook/2 docs/离线 fixture 插件/accounting 4 文件/2 测试）；生产 Gate/Adapter/config/lock/Dockerfile **diff 为空** |
| 公开 stage 重建 | `git archive` tar SHA-256 `408ee0682a47357bd3a481b7a8ca2fe36aec33d29e06a2e0082f0841e6b1f7fb`；94/94 文件与 `source-inventory.sha256` 一致；与 owner `final-stage` 逐字节相同 |
| stage 归一化 tar | `67fffd666ae4bd2b4046501fbcb9559546912a5c3723e436086913c118d1d696`，与 manifest 记录一致 |
| 本次被审实现字节 | accounting 6 文件 + 2 测试 + 2 docs + 离线插件源 hash 与提交/frozen 值逐一相符（例如 broker.py `9dce2f93…`、test_broker.py `c51d5a1f…`） |
| 阶段 1/2/3 历史 manifest | integration `711b02b4…`、phase2 `c512d653…`、phase3 `f4021242…` 均经各自 `.sha256` 校验 OK，未改写 |
| 历史原始证据 | sdk-fixture evidence **65/65 OK**；budget-broker `evidence-fixed` **24/24 OK**（旧 `manifest.json` `08572a…` 仍 OK）；reviewer-phase3 evidence **83/83 OK**；reviewer-broker-pre after-fix closure `91178a0c…`（evidence 75/75 OK） |
| lineage commits | `d5db491…`/`c155789…`/`5df4f3b…`/`e0ce9c8…`/`f674403…` 均存在且 subject 匹配 |

未把第四阶段结果倒填进任何历史报告；旧 manifest/log/phase 文档保持原字节。

## 3. 独立重跑（新容器、新日志、新 argv/UTC/exit）

所有重跑均 exit 0、无真实 Key/模型/HTTP；隔离参数与 owner 原始 argv 一致（仅容器名与
输入/输出挂载根改为审计者独立 stage/目录），完整 argv 与日志 hash 见
[`artifacts/reviewer-phase4/`](../artifacts/reviewer-phase4/)。

| # | 用例 | 独立重跑结果（2026-11-14 UTC） | 与 owner 声明 |
|---|---|---|---|
| 1 | 全量 pytest `tests/unit tests/integration` | **326 passed in 4.26s**，exit 0（10:47:40–45Z） | 326 passed in 4.29s |
| 2 | 专门 E1-02 子集（89） | **89 passed in 0.20s**，exit 0 | 89 passed（326 子集，不相加） |
| 3 | stdio broker 148 回归重放 | **148 passed in 3.96s**，exit 0；stage 中 broker.py/test 字节 = 前一轮独立闭环的 fixed 源码 | 148 passed in 3.97s |
| 4 | Ruff | **All checks passed!**，exit 0；日志与 owner `final-lint.log` **逐字节相同**（`82b3e6a6…`） | All checks passed |
| 5 | wheel 构建 | exit 0；wheel SHA-256 **`07fcb9e5…9b0ed` 与 owner 完全一致**；构建日志与 owner `final-build.log` 逐字节相同（`0e7e82d7…`） | `07fcb9e5…` |
| 6 | wheel-only 无源码安装 CLI/E1 API | exit 0（10:48:13–15Z）；`INSTALLED_WHEEL_VERIFICATION_PASS` + `PHASE2_INSTALLED_API_AND_SCRIPT_PASS`；5/5 payload 解码自校验 OK | 同左 |
| 7 | 真实插件 strict build + 8 registry | exit 0（10:49:49–56Z）；3 个 isolated command exit 0；**TAP tests 8 / pass 8 / fail 0**；4 个 built 产物 hash 与阶段 3 冻结值一致 | 8/8 |
| 8 | SDK fixture strict rebuild | exit 0（10:50:05–19Z）；`BUILD_EXIT 0`×2、6 个 `BUILT_FILE` sha256 与 task20/phase4 期望逐一相等；**日志与 task20 `build-context-aware.log` 及 phase4 `sdk-build.log` 逐字节相同**（`cd44b06f…`） | 6 built files |
| 9 | SDK 17 用例 suite | exit 0（10:50:31–10:51:07Z）；summary 与 owner/phase4 完全相同：`cases17, sdk_run15, synthetic_adapter_invocations16, resume_pairs3, dual_home_bidirectional true, real_model_calls0, http_calls0, production_adapter_used false` | 同左 |

## 4. 交叉核对（不重跑或需先核验冻结输入的部分）

1. **phase4 manifest 完整性**：`manifest.sha256` OK；`artifact-hashes.sha256` **53/53 OK**；
   `key-hashes.sha256` **42/42 OK**；`final-wheel.sha256`、`final-plugin-built.sha256`、
   `installed-input.sha256` 均 OK；`executed-image-inspect.json` hash 与运行所用 image 一致。
2. **重放输入树身份**：`final-stage` 归一化 tar `67fffd66…`；`sdk-build/probe` 归一化 tar
   `ad041386…`（= manifest build-input）；`sdk-replay` 归一化 tar `f438c048…`，且
   `diff -r artifacts/phase4-integration/sdk-replay artifacts/sdk-fixture/stage` 无差异
   （= task20 冻结 stage）；共享 `security/rootfs` `25491e45…`、`foundation/deps` `e07729d7…`、
   插件 `node_modules` `026a7a15…` 均与历史/phase4 记录一致。
3. **插件证据**：`final-plugin-stage/plugin/src/index.ts` = 提交内 `plugins/skill-lookup/src/index.ts`
   （`a618fb02…`）；4 个 built 产物 hash 与阶段 3 `plugin-payloads` 相同（`521bc0f1…` 等）。
4. **SDK 证据**：`sdk-replay/runtime` 6 个 built 文件 hash = task20 manifest `built_artifacts`；
   `suite.py/worker.py/build.mjs/patch/validator/skills/native-cache` hash 全部匹配；
   `validator/autoteacher_m0/runtime/structured_output.py` 与当前仓库源码逐字节相同；
   native cache `40c34d27…` mode 0444；pkg cache **4857/4857** 文件 `sha256sum -c` OK。
5. **owner 日志语义复核**：用与 audit 同一数据校验器对 owner 记录日志重算，17 case 名称/exit、
   summary、invocation/registry 计数、resume 双进程 PID、双 home 双向 nonce、unknown/corrupt/
   interrupt/recovery 语义、9 个 session-log base64+sha256 自校验、merged-config 39 行/13 disabled
   全部通过；独立重跑日志通过同一 **25 项** 语义检查，且与 owner 日志 case 级语义 **parity PASS**。
6. **安装产物**：owner `final-public` 5 文件与 owner `final-installed.log` 内嵌 payload 5/5 一致；
   独立重跑中 `installed-summary.json` **逐字节相同**，`e1-02-installed.json`、`experiment.json`、
   `comparison.md` 在去除每次运行随机 UUID/时间戳后与 owner **语义相同**，`experiment.sqlite3`
   表/列/行内容（时间戳归一化后）相同；差异仅为随机 run/session id 与时间。
7. **容器 absence**：重跑后 `podman ps -a --filter name=at-m0-reviewer-phase4` exit 0、输出为空；
   全局 `podman ps -a` 为空；owner `container-absence.txt` 9 个精确名查询同样全空。

## 5. SDK fixture 边界专项（重点核查是否夸大）

- **provider 不是模型**：提交内 `plugins/offline-fixture/src/index.ts` 显示 adapter 只按用户文本
  返回固定脚本（`FIXTURE_JSON`/`FIXTURE_TOOL`/`FIXTURE_REMEMBER`/`FIXTURE_RECALL`/
  `FIXTURE_INTERRUPT`），无 HTTP client、无模型、无非确定性输出；必须显式
  `AUTOTEACHER_OFFLINE_FIXTURE=1` 且 `ctx.llm.listProviders()` 为空才注册；`resolveModel` 自述
  “Deterministic offline test fixture, NOT a model”。日志中 16 次 invocation 全部
  `provider=offline-test-only, model=fixture-v1, synthetic=true, real_model_calls=0, http_calls=0`，
  registry 只含 `offline-test-only`/`skill_lookup`。
- **工具事件不是模型选择**：`tool-call` 由脚本在 `FIXTURE_TOOL` 下产生；真实的是
  `request/header.tools` 中的已注册 `skill_lookup` schema、真实 tools 执行器、
  `tool/call`→`tool/result` 的 `callId` 关联（`offline-skill-1`）、`isError=false` 且结果文本
  逐字段等于公开 `fixtures/skills.json` 的 `binary_search` 条目；不能记“模型调用了工具”或
  E1b/E2 Live。
- **resume / 双 home / 错误 / 中断语义与日志一致**：3 对跨新 worker 进程 save→recall
  （PID 两两不同、Session ID 相同、nonce 精确回显）；两个独立 `DSH_HOME` 使用同一 Session ID，
  A/B 只回忆各自 nonce 且 session JSONL 互不含对方 nonce（双向）；unknown resume 为
  `JsonRpcError: session "nonexistent-public-session" not found` 且 0 run/0 invocation、
  无历史文件；corrupt save 记录 before/after SHA-256，corrupt resume 为
  `JsonRpcError ... corrupt session log: header line is not valid JSON` 且 0 run；
  controlled-interruption 在 nonce 真实落盘后 SIGTERM，SDK 抛 `TransportClosedError`
  （phase `active-input`），turn 1 assistant 消息 `interrupted=true`、stream 无 usage/finish、
  `turn/end` 为 `aborted/disposed`；interrupted-recovery 新进程 `resume_session` 后 `request/header.reason=resume`、
  turn 2 completed、回显 `RECALLED:PUBLIC_INTERRUPT_82nm`，中断 turn 痕迹保留。
- **不是 E1/E3/E5/Live**：严格 JSON 用例只证明 `final_response` 进入既有 E1 strict
  `validate_e1_json`（worker 明确断言 Pydantic dump）；Session 双 home 只证明 API/命名空间逻辑
  隔离，不是 E5 文件系统隔离；17 个技术用例不是 E4 评估集，更不是教学效果/RSI 证据。
  `production_adapter_used=false`，HarnessAdapter 仍硬 `SECURITY_BLOCKED`（相对父提交未改）。

## 6. stdio broker 边界专项

- 148 回归重放所用 stage 的 `broker.py`=`9dce2f93…`、`test_broker.py`=`c51d5a1f…`、
  `test_stdio.py`=`380ef29a…`，与前一独立闭环审计的 fixed 源码逐字节一致；16 项迁移回归 +
  历史 132 = 148 单次计数，不与 326/89 相加。
- 协议实现仍是固定 scope、持久 SQLite、NDJSON/stdin；`dispatch_allowed` 仅“首次记账”，
  `settle/fail` 用 reservation 行持久 `known_fee`/`price_json`（前一轮已由独立审计确认闭环）。
- **未接线**：`src/autoteacher_m0` 的 runtime/Gate/Adapter 不导入该 broker；仓库无
  `plugins/runtime-budget-guard`；task22 的公开 `llm/stream` 预留/结算 middleware 不存在。
  README/runbook/SDK 文档均明确写出这一限制，未把 broker 或 SDK fixture 称为运行中预算 guard。
- 无真实 Key/HTTP：容器 env 白名单与 isolation 记录、suite/worker 的 `set(os.environ)` 断言、
  invocation 计数共同支持；`.env.example` 明确不含 Key。

## 7. 观察与残余风险

**未发现需要 owner 修复的阻断性缺陷。** 以下为审计观察（不影响本阶段声明成立）：

1. **O1（证据完整性小观察）**：phase4 `results.jsonl`/`run_records` 保留了最初 4 个用例的
   operator tooling 失误（嵌套 podman argv，exit 125，容器创建前失败）记录；但这 4 个用例的
   失败尝试日志随后被成功重跑覆盖（仅 build attempt1 单独保留）。manifest 的
   `run_record_note` 已如实说明该失误并非项目代码失败；建议后续冻结保留失败尝试的独立日志，
   便于外部复核者直接看到失败原因，而不是只能依赖记录文字。
2. **残余风险（范围性，不是缺陷）**：本阶段所有 PASS 均为 B 层 synthetic + bookkeeping；
   真实 provider/模型、真实 usage/费用、逐 HTTP/retry/compaction 预算、人类授权与 Live
   watchdog 仍未实现/未验证；task22 接线未完成；SDK 内部隐藏 retry/transport 语义仍未知；
   guest tmpfs 持久性与本地 OCI 不覆盖跨机恢复；native cache/pkg cache 身份来自既有冻结
   证据（本次已逐 hash 核对，但未重新从官方发行包 export）。
3. **重放范围说明**：插件与 SDK suite 的独立重跑使用经 hash 核验的冻结输入树（插件
   node_modules、sdk-replay、build input），不是从零重新下载/编译依赖闭包；SDK strict build
   本身从冻结插件源码重新执行 tsc 且产物字节与 task20 一致，日志逐字节相同。该限制已在
   证据中显式标注。

## 8. 决策影响

第四阶段新增证据成立，但**不改变** M0 决策：仍 **DECISION PENDING**，所有 Live 仍 **BLOCKED**，
不签发 GO/CONDITIONAL GO，不把 synthetic fixture 当模型证据、不把 broker 当授权或真实账单
上限、不启用 LiveGate。下一步仍为：task22 预算 middleware 实现与独立验证、P03 独立人类授权、
真实 provider usage/逐 billable step 记账与外部 watchdog、以及被测真实主路由的 E1–E5 验收。

## 9. 审计证据索引

- 审计 manifest/清单：[`artifacts/reviewer-phase4/manifest.json`](../artifacts/reviewer-phase4/manifest.json)、
  [`manifest.sha256`](../artifacts/reviewer-phase4/manifest.sha256)、
  [`evidence.sha256`](../artifacts/reviewer-phase4/evidence.sha256)。
- 重跑证据：`artifacts/reviewer-phase4/{final-tests,dedicated-e1-02,broker-148,final-lint,build,installed,plugin,sdk-build,sdk-suite}.{argv.json,stdout.log,stderr.log,exit,result.json}`；
  独立 stage 与归档 `archive.tar`（SHA `408ee068…`）。
- 语义/交叉核对：`sdk-suite-semantics.{mine,owner}.json`（25 项检查）、`sdk-suite-parity.json`、
  `pkg-cache-verify.log`（4857/4857）、`installed-public/`（解码产物）、`containers.*`、
  `podman-ps-all.txt`、`image-inspect.json`、`argv-generation.log`、
  `verify_sdk_suite.py`（宿主 data-only 校验器，不 import 项目代码）。
- 使用前可复算：`cd artifacts/reviewer-phase4 && sha256sum -c evidence.sha256`。
