# 第五阶段独立审计 — runtime budget guard 离线候选集成（非 Live）

- 审计者：`verify2`（非实现者；只写审计报告/证据，不改实现、测试、Gate、Adapter 或历史证据）
- 日期：2026-11-14 UTC
- 审计对象：第五阶段冻结提交 `feb7118f9aff20c681cc651812b30315288080f1`（父 `ec1128b`）与其外部集成证据
  [`artifacts/phase5-integration/manifest.json`](../artifacts/phase5-integration/manifest.json)
  （SHA-256 `391767d3b073d239fded57299c5149d91130a9e476a53b525f4f22f4e69b646f`）；
  候选中间件 `plugins/runtime-budget-guard/`、[RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>)。
- 原始审计证据：[`artifacts/reviewer-phase5/`](../artifacts/reviewer-phase5/)
  （argv/UTC/exit/日志/语义校验 rootfs 实测/容器 absence/hash）。

## 0. 结论

**第五阶段冻结交付在声明的离线范围内通过独立复核；未发现代码、隔离、安全或账本语义阻断缺陷。**
审计者独立重跑了：全量 pytest 326、89 专门子集、broker 148、Ruff、wheel 构建、wheel-only 无源码安装
CLI/E1 API、插件 strict build + 8 registry、SDK strict rebuild、SDK 17 用例 suite、guard strict build、
guard 12 用例 suite + in-process 18/18 selftest（全部 exit 0），并用与 owner 相同的宿主 data-only
校验器对 guard/sdk 日志做语义重算（guard 28/28、SDK 25/25），对 owner 证据/历史证据做 hash 交叉核对。

**发现一项低严重度“文档声明超出已测证据”准确性问题（V1，非代码/隔离缺陷，不阻断核心
reserve-before-provider 安全性质）；该问题已由 owner 完成文档纠错（task31：无代码变更、无新 SHA、未重跑 suite）
并在本轮轻量复核中确认关闭（见 §6.1）**。核心结论：
guard 在 provider 之前预留、deny/unavailable/tamper 时 provider 不进入、settle/fail 恰好一次且不退款、
worst-case 计费、broker 持久 pending 语义均真实成立；**但它仍是 logical-stream 级 bookkeeping 中间件，
不是每内部 HTTP/wire/billable attempt 控制，不是授权/Key 代理/provider usage 认证/真实账单上限，
task22 尚未接入生产 Runtime/真实 provider，Live/P03/watchdog 仍 BLOCKED，整体 DECISION PENDING。**

## 1. 审计方法与隔离边界

- 全部项目代码/TS 编译/guard suite 只在既有固定 digest 无 Key、禁网、非 root、只读 rootfs、
  cap-drop ALL、no-new-privileges、cgroup 受限的本地 OCI 边界内执行（`localhost/autoteacher-local-oci@sha256:62d3569e…`，
  image id `56db1e2a…`；rootfs 运行使用 `artifacts/security/rootfs`）；宿主只做 Git/哈希/JSON 证据整理与
  podman launcher，**未执行项目 Python/pytest/node 生成代码**。
- 审计者用 `git archive feb7118` 独立重建公开 stage（121 文件，tar SHA `7bde63cc…`，归一化 tar
  `c68b3a1b…`），逐文件核对 `stage-inventory` 121/121 后用于项目 pytest/wheel/安装重跑；project/guard
  运行使用新 argv、新日志、独立容器名 `at-m0-reviewer-phase5-*`。
- 对冻结不变的 phase4 插件/SDK 输入与 guard 构建/运行输入，先按 phase5/owner manifest 记录的
  normalized-tar/key hashes 做只读交叉核对，再在冻结字节上独立执行并写新日志；逐项标注
  “独立重跑”或“交叉核对”。
- owner 的 task22 guard 证据环境字段 errata（rootfs after/match）按 Lead 指示仅作观察项处理：
  旧 manifest 字节未改，`manifest-errata.json`（sha256 `83ec2433…`）记录正确 before/after 均为
  `25491e45…`；审计者独立实测 canonical rootfs 在本次所有运行前后均为 `25491e45…`、deps 均为 `e07729d7…`、
  `/var`、`/var/tmp` 不存在，旧 after `9d1d4e84…` 仅来自一次中间 build attempt 的空 `/var/tmp`，不作为
  相等证据。

## 2. Git、源快照与历史证据

| 核对项 | 结果 |
|---|---|
| `git rev-parse HEAD` | `feb7118f9aff20c681cc651812b30315288080f1`；父 `ec1128b…`；commit subject 匹配 |
| 相对父提交变更 | 仅 9 文件：README/runbook/RUNTIME_BUDGET_GUARD/6 个新插件文件；`src/`、`tests/`、`config/`、`Dockerfile.m0`、`pyproject.toml`、`uv.lock`、`scripts/`、`fixtures/` **diff 为空** |
| worktree | 冻结时 clean（后经 task30 追加 docs errata 指针，见 §5） |
| 审计者 stage | `git archive` tar SHA `7bde63cc576537293c8aa1e3dde932d8440b5df9923bf93c525291ace5963f55`；121/121 与 `stage-inventory.sha256` 一致；归一化 `c68b3a1b1645a05dc5db759f561405a2b7473ccfee350ac3d750f880cf3ca45d` 与 phase5 manifest 一致；与 owner `phase5-integration/stage` 逐字节相同 |
| 历史四阶段 | integration `711b02b4…`、phase2 `c512d653…`、phase3 `f4021242…`、phase4 `bfea6fa1…` 及 e1-json manifest 经各自 `.sha256` 校验 OK；phase4 artifact-hashes **53/53**、key-hashes **42/42**；reviewer-phase4 evidence **168/168**；sdk-fixture evidence **65/65**；budget-broker evidence-fixed **24/24**；broker after-fix closure **75/75**；reviewer-phase3 evidence **83/83**。历史文件未被本阶段改写 |
| phase5 manifest | `manifest.sha256` OK；manifest SHA `391767d3…` 与 Lead 基线一致；11 个 argv 文件 hash 与 manifest `runs` 逐项相符 |

## 3. 独立重跑（新 argv/新日志，全部 exit 0）

| # | 用例 | 独立重跑结果（2026-11-14 UTC） | 与 owner 声明 |
|---|---|---|---|
| 1 | 全量 pytest `tests/unit tests/integration` | **326 passed in 4.30s**，exit 0（12:11:48–53Z） | 326 passed |
| 2 | 专门 E1-02 子集 | **89 passed**，exit 0 | 89（326 子集，不相加） |
| 3 | stdio broker 148 回归 | **148 passed in 4.00s**，exit 0 | 148（独立 scope，不相加） |
| 4 | Ruff | **All checks passed!** | 同左 |
| 5 | wheel 构建 | exit 0；SHA-256 **`07fcb9e5…9b0ed` 与 owner 一致** | 同左 |
| 6 | wheel-only 无源码安装 CLI/E1 API | exit 0；`INSTALLED_WHEEL_VERIFICATION_PASS` + `PHASE2_INSTALLED_API_AND_SCRIPT_PASS`；5/5 payload 自校验；`installed-summary.json` 与历史 owner 产物**逐字节相同**，其余 4 产物仅随机 UUID/时间不同、归一化后语义相同（experiment/comparison/e1-02/sqlite） | 同左 |
| 7 | 真实 Cordis 插件 strict build + 8 registry | exit 0；3 个 isolated command exit0；**TAP 8/8 pass**；built hash = 阶段 3/4 冻结值 | 8/8 |
| 8 | SDK fixture strict rebuild | exit 0；2×`BUILD_EXIT 0`、6 个 BUILT_FILE hash 与 task20/phase4 一致；**日志与 task20 build 日志逐字节相同**（`cd44b06f…`） | 6 built files |
| 9 | SDK 17 用例 suite | exit 0；summary `cases17/sdk_run15/synthetic16/real0/http0/resume3/dual_home true`；宿主 data-only 语义校验 **25/25 PASS**，与 owner 日志 case 级 parity PASS | 同左 |
| 10 | guard strict build | exit 0（12:13:34–41Z）；3 个 BUILT_FILE（`index.js 3c184a62…`、`index.d.ts 125393ad…`、`package.json 5724ebf9…`）与 owner 一致；**构建日志与 owner `build3.out` 逐字节相同**（`92ea7c57…`） | 3/3 |
| 11 | guard 12-case suite + in-process 18/18 selftest | exit 0（12:13:41–12:14:05Z）；10 worker 全 exit0；12/12 case、18/18 selftest；summary 与 owner 完全相同（`real_runtime 7/7/$0.007198`）；宿主 data-only 语义校验 **28/28 PASS**（对本次、phase5 owner 日志、owner suite-final.log 三者均 PASS） | 12/12 + 18/18 |

## 4. 交叉核对（不能/不必重跑项）

1. **phase5 证据**：`manifest.sha256` OK；`evidence.sha256` 75/76 OK——唯一 FAILED 是 `docs/RUNTIME_BUDGET_GUARD.md`，
   原因是 task30 按 Lead 批准的 post-freeze errata 指针在 worktree 增加 3 行（未提交，待 task29 归档）；
   冻结提交 blob 的 hash 仍等于 phase5 记录 `8fa03fbe…`，**冻结证据本身一致**，不作实现变更。
2. **owner guard manifest**（`05224052…`，未改）：sha 文件 OK；artifact-hashes **42/42**、
   stage-additions **45/45**、plugin-source **5/5**、guard-built **3/3**、delivered-files 6/7
   （唯一差异同为上述 post-freeze 文档 errata 指针）；plugin node_modules 归一化 tar
   `cab77a60…` 与 manifest 一致（审计者重算）。
3. **冻结输入身份**：phase5 stage 归一化 `c68b3a1b…`；guard plugin source（git blob）`1ccdb658…`
   == owner stage/build-input；guard built `index.js 3c184a62…` == owner stage `runtime/guard/lib/index.js`
   == 审计者独立 guard-build 产物；phase4 final-stage `67fffd66…`、sdk-replay `f438c048…`（=task20 stage）、
   sdk-build input `ad041386…`、plugin stage `60938b11…`、rootfs `25491e45…`、deps `e07729d7…`、
   guard node_modules `cab77a60…` 均与 manifest/owner 记录一致。
4. **共享环境实测**：审计者在全部运行前后重算 canonical rootfs 归一化 tar 均 `25491e45…`、
   deps 均 `e07729d7…`，`/var` 与 `/var/tmp` 不存在；native cache `40c34d27…`（0444）、
   pkg cache 4857/4857（guard/sdk 容器内断言，sdk-fixture evidence 65/65 交叉核对）。
5. **容器/image**：运行后 `podman ps -a --filter name=at-m0-reviewer-phase5` 前缀查询 exit 0、
   0 字节；全局 `podman ps -a` 为空；image inspect 的 id/digest/config user 与 argv pin 一致；
   无后台 job。
6. **历史 & errata**：任务 22 旧 guard manifest 字节未改（`05224052…`），`manifest-errata.json`
   `83ec2433…` 与 `errata.sha256` 校验 OK；phase5 独立实测值与其“正确值”一致。

## 5. 观察项（非代码缺陷，不否定 guard 证据）

- **O1（Lead 已知的 owner 证据 errata）**：task22 owner manifest 的
  `shared_rootfs_normalized_tar_sha256.after/match` 记录自相矛盾（after `9d1d4e84…` 却 match=true）；
  该 after 来自早期 build attempt 创建后又被删除的空 `/var/tmp`。`manifest-errata.json` 已记录正确
  before/after 均 `25491e45…`；旧 manifest 字节未改。**仅作证据记录准确性观察，不引用旧 after/match；
  不影响 guard 代码/测试结论。** 当前 worktree `M docs/RUNTIME_BUDGET_GUARD.md` 是 errata 指向的
  post-freeze 文档 +3 行（待 task29 文档归档提交），非实现变更、不改 feb7118 被测源码。
- **O2（标注澄清，非缺陷）**：guard harness summary 的 `real_runtime_reservations/settled=7、
  committed=$0.007198` 是其扫描 s1/s2/s3 broker DB 的结果；s11 broker-restart 交叉验证复用
  `/probe/configs/s1.json`，在 s1 DB 追加 1 条 `FAILED $0.00112` 行，故 7 行/$0.007198 含该交叉
  验证行。文档 §6 的“会话级聚合 10 reservations = 7 OK + 3 FAILED、$0.018904”是排除 s11 的
  独立正确 scope。两者各自内部一致，**不可相加或混称同一 scope**。

## 6. 发现 V1 — 文档声明超出已测证据（低严重度；已由 owner 文档纠错解决，无代码变更）

以下三处 [RUNTIME_BUDGET_GUARD](<RUNTIME_BUDGET_GUARD.md>) 声明强于代码/日志实际证据（owner
manifest 的 `not_verified` 已部分承认这些缺口，但文档正文仍作了更强表述）：

1. §2 请求不可变性：文档称 mutation 检测后“按 worst-case fail 结算、**后续流 fail-closed**”。
   代码（`plugins/runtime-budget-guard/src/index.ts` 的 `apply` middleware：digest 不一致时仅
   `failed = true` 并 worst-case settle 当前 stream）**没有**为后续 stream 设置全局 deny/latch；
   selftest `detect-request-mutation` 只断言本次 stream 完成并检查日志，未测“后续流被拒”。
2. §4 单调性：文档称 scope blocked 后“后续 stream（**包括 compaction/retry 产生的新 stream**）
   继续被 broker 拒绝”。实际 s4 只测同一 blocked scope 上重复 normal/conversation stream；
   owner manifest `not_verified` 明确写“compaction-after-denial monotonic sequencing”未验证。
3. §4 重试：文档括注称“selftest/session 均验证 2 次 post-attempt reservation”；实际只有
   session-level s9（scripted transient provider）验证 2 次 reservation，selftest 18 例中没有
   retry-two-reservations 用例。

**影响评估**：这是文档/声明准确性缺陷，不是代码安全缺陷。核心安全性质仍成立——每一次后续
stream 仍会先经 guard reserve（provider 之前），被拒或 unavailable 时 provider 不进入；不存在
“无预留 dispatch”。因此不阻断本审计对代码/隔离/账本证据的 PASS 结论，也不需新代码 SHA
重测；修正前不得对外引用上述三处更强声明。

### 6.1 V1 关闭（post-audit 轻量复核，2026-11-14T12:29Z）

owner 已按本审计要求完成 **task31 文档纠错**（无代码/测试/实现变更、无新 SHA、未重跑 suite）。
本轮轻量复核（不重跑代码/suite）确认：

- 修正后 `docs/RUNTIME_BUDGET_GUARD.md` sha256 = `1d0b62a23695020d5f7216f345d43942d05695e520c86603bb66e62dab56f11d`；
  与 frozen commit `feb7118` 的 `git diff` 仅含：预存的 task30 rootfs errata 指针（+3 行）+ 三处 V1 收窄，
  未引入任何新的更强 claim；核心 reserve-before-provider / deny-before-provider 段落未被改动或削弱。
- 三处收窄与证据一致：(a) mutation 仅**当前** stream 置 failed + worst-case settle，明确“没有跨后续 stream
  的全局 latch（未实现/未验证）”；(b) blocked-scope 仅“同一 scope 的新 reserve 被拒绝（s4 重复 normal
  stream），compaction/retry 新 stream 未单独验证”；(c) retry 两次 reservation 仅“session s9 实测”，
  明确“selftest 无该用例”。
- 更新后 `artifacts/runtime-budget-guard/manifest-errata.json` sha256 =
  `362dedb32662e29b9685a76a74d8a6a51e57fa2aa8e6546e8d83624a5aa3ab2c`，新增 `RBG-V1-DOC-OVERCLAIMS`
  条目并记录 docs hash 链（`8fa03fbe…`→`ba986fb0…`→`1d0b62a2…`）；`errata.sha256`（sha256
  `9533f06f…`）自洽校验 OK；旧 `manifest.json` 字节/hash 未改（`05224052…`），phase5 manifest
  （`391767d3…`）与 `evidence.sha256`（`df63e46f…`）字节未改，phase5 evidence 仍 75/76，唯一差异为
  `docs/RUNTIME_BUDGET_GUARD.md` 的 expected docs-only delta（phase5 期望 `8fa03fbe…`，现状
  `1d0b62a2…`，由授权的 task30/31 文档 errata 造成，非证据篡改）。
- **V1 状态：CLOSED（resolved by documentation correction；无代码变更、无新 SHA、无需重跑）**；
  原审计证据、独立重跑清单与边界保持不变。残留：若未来选择实现 immutability 全局 latch 或扩展
  compaction/retry 单调验证，仍需新代码 SHA 与重测；当前仅修正文档声明，不改变实现行为。

## 7. guard 安全边界与代码核验

- **logical-stream 级、非 HTTP/wire 级**：插件只包裹全局 `llm/stream`；每次 dispatch 一次
  reservation；底层 provider transport 的隐藏 retry/二次 POST 未观测/未拦截；text-only 全 history
  白名单只是关闭项目 Files 路径的**前提**。文档 §0/§7 已明确，未夸大。
- **reserve-before-provider / deny 前不进入 provider**：代码在 `next()` 之前 `await broker.reserve`，
  仅 `dispatch_allowed=true` 继续；s1 trace 为 `RBG_BOOT→RBG_RESERVE→FIXTURE_INVOCATION→RBG_SETTLE`；
  s4/s5/s6/s7 fixtures=0，denied-requests-never-entered-provider counter 不变。
- **固定 argv / 无 shell / env 白名单**：`spawn(fixed python, ['-B','-m','autoteacher_m0.accounting.broker','--config',fixedPath], {cwd, env:{PATH,HOME,PYTHONPATH,PYTHONDONTWRITEBYTECODE,TMPDIR}, shell:false})`；
  不继承 runtime/Key/网络 env；broker policy 文件 spawn 前重读并校验 `configSha256`。
- **16KiB frame / 串行请求 / bounded timeout**：`MAX_BROKER_FRAME_BYTES=16384`，stdout 行超限、
  非法 JSON、未匹配 response、子进程 error/exit、写失败、timeout → `#unavailable` fail-closed，
  且不自动重启。
- **settle 恰好一次、不退款**：`finally` 对每个唯一 reservation 结算一次；无 usage/中断/abort/error/
  非权威 finish → `fail`（worst-case 全额 reserved cost）；settle 失败仅记 `SETTLE_UNCERTAIN` 并
  shutdown，不重试发放、不释放；s8/s9/s10 与 s11 的 SQLite 行/计数与日志一致。
- **config tamper→deny-all**：parse/config hash 失败时注册 deny-all middleware（`BOOT_INVALID
  fail_closed:true`），s7 provider 0；**broker unavailable/漂移 → deny**（s5/s6 provider 0）；
  **retry 两次 reservation**（s9 2 次尝试/2 行，首 FAILED 保底、次 OK 实结）；
  **SIGKILL/restart pending**（s11 pending→restart pending=1/reserved>0→fail 一次→pending=0）。
- **broker 非授权/非 Key 代理/非 usage 认证/非账单上限**：`dispatch_allowed` 仅首次记账；
  guard 未给 broker 增加任何授权/凭据/usage 认证能力；synthetic usage/cost 为夹具常量，
  `real_model_calls=0,http_calls=0`，无 Key/网络。
- **task22 生产接线未完成**：中间件仅以 profile 候选形式存在，未接入生产 Runtime/真实 provider；
  生产 Gate/Adapter/primary 未改（diff 为空）；Live/P03/watchdog/真实 usage 仍 BLOCKED。

## 8. 残余风险（范围性，非本阶段缺陷）

1. provider transport 内部隐藏 retry/Files 二次 POST、每 billable attempt 上界：未观测/未控制。
2. 真实 agent-loop compaction/Judge 全生命周期、compaction-after-denial 单调时序：未验证。
3. 模块 import 失败时上游 loader 会 warning 后继续：已用 deny-all 缓解 config 错误，但极端
   module-load 失败仍可能无 guard；集成必须显式断言 `RBG_BOOT`/`BOOT_INVALID` 后才放行 traffic。
4. 硬 SIGTERM 下 finally 是否对所有 kill 时序执行：只证明已预存 reservation 不退款（FAILED/pending）。
5. live broker crash recovery 不实现（fail-closed）；仅协议级 restart 持久性交叉验证。
6. 真实 provider usage/账单、tokenizer 精确输入上界（当前为 UTF-8 bytes+overhead 保守估计）、
   跨机 OCI 恢复与 native/pkg cache 官方重导出仍未验证。
7. 所有 PASS 均为 B 层 synthetic/scripted fixture + 本地 bookkeeping；不是真实模型/Live/E1b/E2 Live/
   生产 Adapter/人类授权；DECISION PENDING 与 Live BLOCKED 不变。

## 9. 证据索引

- 审计 manifest：[`artifacts/reviewer-phase5/manifest.json`](../artifacts/reviewer-phase5/manifest.json)、
  [`manifest.sha256`](../artifacts/reviewer-phase5/manifest.sha256)、
  [`evidence.sha256`](../artifacts/reviewer-phase5/evidence.sha256)（`cd artifacts/reviewer-phase5 && sha256sum -c evidence.sha256`）。
- 重跑：`{final-tests,dedicated-e1-02,broker-148,final-lint,build,installed,plugin,sdk-build,sdk-suite,guard-build,guard-suite}.{argv.json,stdout.log,stderr.log,exit,result.json}`；
  独立 stage/archive（`archive.tar` `7bde63cc…`）。
- 语义/交叉核对：`guard-suite-semantics.{mine,phase5,owner}.json`（28 项）、`sdk-suite-semantics.*`（25 项）、
  `installed-public/`、`rootfs-before/after` 实测、`containers.*`、`podman-ps-all.txt`、
  `image-inspect.json`、`verify_guard_suite.py`（宿主 data-only，不 import 项目代码）。
- 运行前/后 canonical rootfs `25491e45…`、deps `e07729d7…`；guard build 日志与 owner 逐字节相同
  `92ea7c57…`；SDK build 日志与 task20/owner 逐字节相同 `cd44b06f…`；wheel SHA `07fcb9e5…`。
