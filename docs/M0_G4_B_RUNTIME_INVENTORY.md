# M0 G4-B — 冻结运行时清单、实际加载模块与 Tool Registry 探针（No-Key）

- **任务**：G4-B-01..11（`docs/Autonomous_Teacher_M0_G4_PreLive_NoKey_Agent_Execution_Plan_v1.0.md` §5 / §8 / §10 / §12–§14；矩阵 `G4-B-01..11`）
- **执行者**：G4-B Frozen Inventory / Tool Registry Agent（实现 + 证据，不改 `src/`）
- **执行时间（UTC）**：2026-11-18T15:56Z → 17:0xZ
- **性质**：**no-key / no-model / no-network / no-live**。0 真实 Key、0 模型调用、0 外部 HTTP/TCP、0 计费请求；未执行 `podman pull`；容器全程 `--network none`，结束 `podman ps -a` 为空。
- **本轮裁定**：G4-B 的 **B01/B02/B04/B05/B06/B08/B09/B10/B11 成立**；**B03 为 `UNVERIFIED`（DSH 无权威 merged registry 导出）+ Controller 严格白名单兜底成立**；**B07 部分成立**（compaction/files/fallback PASS，session-log `PARTIAL`，session-title `BLOCKED`，mcp-resources `UNVERIFIED`，全部要求 Controller per-dispatch 兜底）。
- **本文件不是**授权、不是 G4 PASS、不是 E5-PreLive Full、不是 Live 批准。`LiveGate` 仍 `BLOCKED`，`G4-H` 仍 `NOT_AUTHORIZED`。

---

## 0. 结论先行

| 行 | 主题 | 本轮实际结果 | 证据级别 | 残余 |
|---|---|---|---|---|
| **B01** | 完整输入清单 + 确定性 canonicalization + fail-closed 校验 | **PASS** | L0/HOST | 仅覆盖声明的 root；rebuild 未做（见 B10） |
| **B02** | 实际加载模块 / Adapter（非旧 stage） | **PASS** | L1-HOST + L2（容器内 10 模块） | Adapter 用「加载自报 + 三方字节一致」而非 JS `inspect.getfile` |
| **B03** | 权威 merged Tool Registry | **`UNVERIFIED`（不可导出）** + 兜底 **PASS** | L0 合并 dump + L1 请求观测 + L2 拒绝 | 无法证明「registry 只有 skill_lookup」 |
| **B04** | 未批准 tool / 额外 tool / 改 schema | **PASS**（host 7 例 + 真实 raw UDS 6 例，全部 Reserve/Claim 前拒绝，Fake=0） | L1-HOST + L2 | 无 |
| **B05** | 真实 DSH Tool 两轮 | **PASS**（2 独立 Reserve/Claim/Intent/Attempt/Receipt/Settlement，counter=2） | L2 | 单次 run |
| **B06** | 额外 provider request 注入 | **PASS**（配额内各自建账；超配额 `BUDGET_DENIED` 且 0 发送；辅助 purpose 协议层 `BAD_TYPE`） | L1-HOST + L2 | 「所有插件路径」不可穷举，靠单一 adapter/单一 UDS 兜底 |
| **B07** | compaction / judge / files / fallback | **PARTIAL**：5 PASS / 1 `PARTIAL` / 1 `BLOCKED` / 1 `UNVERIFIED` | L0 合并 dump + L1 trace | session-title、session-log、mcp 需 Controller 兜底 |
| **B08** | logs / telemetry / upload / network | **PASS**（`--network none`、`AF_INET/AF_INET6 EACCES`、DNS 失败、无默认路由、无 proxy/key env、0 网络标记、session 仅本地 JSONL） | L2 | 「插件没有上传意图」不可证明，只能证明「没有可用外发路径且未观测到外发」 |
| **B09** | Candidate stage 无 trusted code / Key / import | **PASS**（6549 文件结构化扫描 + 导入语句扫描 + 无 key 物质） | L0 + L1（运行期 principal） | 第三方 bundle 由子树摘要覆盖，不做逐名判定 |
| **B10** | Worker 构建 canonical 不漂移 | **PASS（校验既有）**：stage tree/manifest 两次重算一致 = 冻结值；6606 行逐文件复核 | L0 | **未二次 build stage**（`UNVERIFIED` 跨构建可复现性） |
| **B11** | 代码/registry/deps/profile 变更 → 下一次 dispatch fail-closed | **PASS**（manifest drift 测试 + `require_manifest_match` 逐项理由 + policy 绑定） | L1 | 与 G4-A 的实际接线在 G4-C 集成时验证 |

**关键定量断言**：`real_provider_calls=0`、`real_external_http_calls=0`、`provider_keys_seen=0`、`billable_send_allowed=0`、`LiveGate.status=BLOCKED`、真实容器 2 个 run 全部 `exit 0`、`podman ps -a` 结束为空。

---

## 1. 身份、基线与工作树策略

| 项 | 值 |
|---|---|
| 会话起始 HEAD | `e3d270e2277087e0642dda8803111885d0dbad3f`（G4-00 完成），工作区 clean |
| G4-B 主分支提交 | `feat` `376012cf96f91bc97ac3b2d8ad9304f74c90f864`（父 `e3d270e`）；追加修正提交 `5559013`、`32acce9`、`76f2b18`、`c29cabc`（见 §12.2） |
| 证据基线提交（本地，非 main） | `2f1e41f4476bd137e03a551ab5e6654a249f71ad`（父 `e3d270e`）= 上述 5 个提交的字节在当前 `src/` 冻结基线上的等价树 |
| 冻结产品实现 | `cf40c6bfb84ceae98e795db19efa955aa3035991`（stage 由它构建） |
| 运行时字节 | rootfs `25491e45…`、deps `e07729d7…`、DSH runtime `1cc41d5a…`、stage tree `e1ff1449…`、stage manifest `644823d4…`（**全部本轮重算一致**） |
| 容器 | 2 次（tool run / raw-UDS run），均 `--network none`，结束后 `podman ps -a` 空 |

### 1.1 为什么证据绑定在「证据基线提交」而不是当时的 main HEAD

G4-B 期间，**另一个 Agent（G4-A）在同一工作区并行修改 `src/autoteacher_m0/security/{authorization,ed25519,live_controller}.py` 并随后提交**（`382b4ee`、`ac7cb08`）。这不是本包的改动，本包全程未触碰这些文件。

影响是硬的：冻结的 `scripts/g3d/launch.py` preflight 要求 `git diff cf40c6b -- src` 为空、且工作区只有它自己的允许路径——否则 `PREFLIGHT_IDENTITY` 拒绝启动。G4-B 的真实容器证据必须由该 launcher 产生（不允许改写 g3d），因此：

1. 本包先在 main 上提交自己的 `scripts/g4/**`、`config/g4/**`、`tests/integration/g4_b/**`（只 add 自己的路径，未触碰 G4-A 文件）；
2. 从 `e3d270e` 建**独立 git worktree**，把这 5 个提交的字节 cherry-pick 上去（`src/` 仍为 `cf40c6b` 冻结字节），提交为 `2f1e41f`，`artifacts/` 用符号链接指回真实证据目录；
3. 所有容器 run / 探针 / 回归计数都在该 worktree 内、`git status` clean 的状态下产生，`env/git.json` 记录 `status_entries=[]`。

**这带来一个必须说清的性质**：本 manifest/approval baseline 绑定的是**冻结 `src`（`cf40c6b`）**。在包含 G4-A 改动的 main HEAD 上运行 `verify_manifest.py` **会（且应当）失败**——`trusted_src:git_blob_mismatch:*`。这不是缺陷，而是 B11 要求的 fail-closed 行为：代码变了，旧批准自动失效。

---

## 2. B01 — 完整输入清单（`manifest.json`）

### 2.1 清单结构

`schema = m0.g4b.inventory.v1`，五个被摘要覆盖的顶层键：`schema`、`canonicalization`、`anchor`、`inputs`、`derived`；`provenance` 与 `digest` **不参与**摘要。

```text
canonicalization = {
  json: sort_keys=true, separators=(",",":"), ensure_ascii=false, allow_nan=false,
  trailing_newline=true, path_sort=码点升序, path_separator="/",
  mode=四位八进制(lstat 不跟随), digest=sha256(canonical_json(schema+canonicalization+anchor+inputs+derived)),
  self_reference=manifest.json / manifest.sha256 永不自列、永不自哈希
}
```

**自引用排除**：manifest 不包含自身哈希；摘要写在旁边的 `manifest.sha256`（`"<digest>  manifest.json"`）与 `digest.value` 中，`verify_manifest.py` 用同一投影重算。

### 2.2 覆盖矩阵（实测计数）

| root_id | 种类 | 覆盖 | 计数 |
|---|---|---|---|
| `trusted_src` | worktree_tree | `src/autoteacher_m0/**/*.py`，每行 pin `source_commit=cf40c6b` + git blob | 49 文件 / 474,908 B |
| `trusted_stage` | stage_section | 实际挂载的 trusted stage（`/project`），逐行与 stage manifest 交叉校验 | 57 文件 |
| `candidate_stage` | stage_section | 控制面逐文件 + 三个依赖子树摘要 | 34 逐文件；`node_modules` 1657 / `native-cache` 1 / `pkg-cache` 4857（合计 6515） |
| `adapter_build` | file_set | adapter 源 `spikes/…/src/index.ts`、fake provider、`build-adapter.mjs` | 3 文件 / 31,044 B |
| `repo_config` | file_set | `config/budgets.yaml`、`config/dsh/**`、`config/models.example.yaml` | 6 文件 |
| `plugins` | file_set | skill-lookup / offline-fixture / runtime-budget-guard 的 manifest+源码 | 8 文件 / 64,090 B |
| `policy` | file_set | `config/g4/*`、`config/g3d/**` 覆盖层与模板 | 6 文件 |
| `harness` | file_set | `scripts/g3d/{launch,build_stage,lib_g3d,stage/*}` + `scripts/g4/*` | 11 文件 / 376,963 B |
| `stage_manifest` | file_set | G3-D stage manifest 本体 | 1 文件 / 4,224,177 B |
| `runtime_rootfs` | canonical_tree | OCI rootfs（G3-D canonical tar 配方） | `25491e45…` |
| `runtime_deps` | canonical_tree | Python deps 树 | `e07729d7…` |
| `runtime_dsh` | file | DSH 0.2.2-rc.2 runtime 二进制 | 182,717,632 B / `1cc41d5a…` |
| `runtime_node` | file | 容器内 Node 二进制 | 124,836,408 B / `3517c2df…` |

合计 **6,690 个文件条目**（含 6,515 个依赖树文件），覆盖代码、stage、adapter 源与产物、配置合并输入、内置/插件工具、tool schema、budget/route/price、stage manifest、rootfs/deps/runtime。

### 2.3 `derived`：只能从字节推导的事实

| 事实 | 来源（同时被 manifest 覆盖） | 值 |
|---|---|---|
| 批准 tool schema | `candidate/fixtures/capture-tools.json`（G3-C 真实 DSH 请求抓包） | `skill_lookup` = `c984bef0ae31771da16a12ef2e7972b289cde6014b7f8ad12349f16c4f77b704` |
| Admission 绑定 | `trusted/templates/admission.template.json` | route `offline-test-only-g3b/fixture-bridge-v1`、`max_calls=8`、`max_attempts=1`、`max_input_tokens=100000`、`max_output_tokens=1024`、`deadline_ms=30000`、`launcher.uid=65534` |
| Controller 绑定 | `controller.template.json` | socket `/work/g3b/bridge.sock`、`expected_peer_uid=65534`、`socket_mode=0o660`、`socket_gid=null` |
| Broker 策略/价格 | `broker.template.json` | soft `$3` / hard `$10` / per-call `$0.2` / 50 请求；价格 `fixture-v1`（input 1 / output 2 / cached 0.5 per M，`known_extra_fee_usd=0.001`） |
| **配置合并顺序** | 运行时性质，非猜测 | ① runtime profile `sdk-minimal` → ② `--patch /project/config/bridge.patch.yml` → ③ candidate env（`HOME`/`DSH_HOME`…） → ④ trusted admission/broker/controller |
| Registry 状态 | 恒为 `UNVERIFIED_NO_AUTHORITATIVE_MERGED_EXPORT` | 见 §4 |

**注**：`config/budgets.yaml` 仍**没有任何运行时解析代码**（G4-00 §12.1 同一结论）；它是「声明性策略输入」，真正的限额来自 stage 模板 → Admission/Broker 配置。manifest 同时记录两者，避免把 YAML 当成已生效上限。

### 2.4 校验器（fail-closed）

`scripts/g4/verify_manifest.py` 顺序检查：自身摘要 → 每文件 sha/size/mode → root 内新增/删除 → 子树/tar 摘要 → `derived` 重算 → `require_manifest_match()`。退出码：`0` 干净，`4` 漂移，`5` 自摘要不符，`6` spec/policy 非法，`7` 环境不可读。

**实测**：`OK digest=6ca1aca34a36c564aa59976fd53b0ba74be6d66afacabfce9308f2540a0f1b25 problems=0 dispatch_ok=True`。

`tests/integration/g4_b/test_verifier_fail_closed.py`（10 例）逐项证明以下变异**全部被检出**：修改字节、新增文件、删除文件、改 mode、子树摘要变化、`capture-tools`（derived）变化、manifest 自身篡改、policy 的 tool/route/limit/price/registry 字段变化。

**Manifest 产物**：`artifacts/g4/runtime/manifest.json`（99,723 B，sha256 `6101b6751e00a069fd59ac0dd2aca06f9d9b1f63c73db522a29b18e08942715a`）+ `manifest.sha256`。

---

## 3. B02 — 实际加载的模块与 Adapter

### 3.1 Host（L1-HOST，新进程，`inspect.getfile`）

17 个 trusted 模块在全新 CPython 3.11.15 进程中导入；`real_path` 全部位于 `src/`，加载字节 sha256 == `git show cf40c6b:` == `git show HEAD:`（17/17）。

`bridge/{controller,ipc_server,attempts,admission,broker_client,fake_backend,protocol}`、`accounting/{broker,usage,observation}`、`security/{gates,egress,authorization,ed25519,credential_boundary,watchdog,live_controller}`。

### 3.2 容器内真实 trusted 进程（L2）

由容器内 `trusted_entry.module_identity()`（`importlib.import_module` + `inspect.getfile`）生成 `peercred/trusted-modules.json`：**10/10** 模块文件位于 `/project/src/autoteacher_m0/...`，sha256 全部等于 `git show cf40c6b:`（`container_modules.ok=true`）。

**限制（不得外推）**：该清单是 `trusted_entry.py` 的硬编码 10 模块清单，不含 `security.*`；「不在清单」≠「未加载」。

### 3.3 Adapter（真实加载的是冻结产物）

| 检查 | 值 |
|---|---|
| stage 产物 `candidate/runtime/bridge/lib/index.js` | `2cb424616b7380bff61f8ce760e229a0c1d2b32c4a5f2954cdf66c3937bf74ba` |
| `build-meta.json` 的 `builtJs.sha256` | 同上（三方一致：stage 字节 = build-meta = `config/g4/runtime-policy.json`） |
| `build-meta.inputSourceSha256` == `spikes/g3b-trusted-bridge/src/index.ts` | 一致（`input_source_matches=true`） |
| 运行期自报 | 真实 run 的 candidate stderr/trace 含 `G3B_BRIDGE_REGISTRY {"provider":"offline-test-only-g3b",…,"realModelCalls":0,"httpCalls":0}` |
| 唯一 provider 守卫 | `apply()` 在已有 provider 时抛 `G3B_BRIDGE_EXISTING_PROVIDER_PRESENT`（任何真实 provider 若启用则该 run 直接失败） |

**证据级别声明**：JS 没有 Python 的 `inspect.getfile`；这里是「加载时自报 + 产物/构建元数据/策略三方字节一致」。不宣称「从 JS 进程内部读到代码段」。

### 3.4 证明不是旧 `e6fde1c` / G3-C stage

| 对象 | 值 | 结论 |
|---|---|---|
| 旧 G3-C stage tree | `fcdb0de442d455f89fe849c736679f831c15c50f76e3e4844d38f2963e3735b0` | 当前 `e1ff1449…` ≠ |
| 旧 `attempts.py`（`e6fde1c` 批次） | `33017e75871714f8d97d409ff6f26f4848c9d22de4b0bc002c9e6bb39de99167` | 当前 `ccd008bd…` = `git show cf40c6b:` ≠ |
| 容器内 `bridge.attempts` 实测 sha | `ccd008bd…` | = 冻结对象，**不是旧批次** |

---

## 4. B03 — Registry：`UNVERIFIED` + 兜底

### 4.1 权威导出不存在（引用 + 本轮复测）

DSH `0.2.2-rc.2` 无「merged tool registry / tool JSON Schema」导出 API：`--dump-config` 导出的是 **Cordis 插件条目列表**，`--dump-config-schema` 是条目列表的 schema（643,872 B），不是 tool schema。`grep -rni "registry|tool_schema|list_tools" deps/deepseek_harness/*.py` = 0 命中（G4-00 §9.1）。

### 4.2 本轮新增的 L0 合并证据（不是 registry）

以 `env -i`（无 proxy 变量）+ 隔离 `HOME`/`DSH_HOME` 运行：

```text
<dsh-runtime> --profile sdk-minimal --patch config/g3d/candidate/bridge.patch.yml --dump-config
```

- exit 0，**39 个条目**，落盘 `artifacts/g4/runtime/merged-config.yml`（`0d525f44…`）；
- `$DSH_HOME/profiles/` 物化 **4 个文件**（`cordis.yml`/`cordis.patch.yml`/`package.json`/`pnpm-workspace.yaml`），已记录并隔离（`materialised_count=4`），未写入宿主 `~/.dsh`；
- 合并结果里 `llm-deepseek`、`plugin-package-inventory-deepseek`、`tool-fs`、`tool-working-directory`、`subprocess`、`pty`、`terminal-bash`、`terminal-pwsh`、`persistent-bash`、`persistent-pwsh`、`jobs`、`compaction-basic`、`image-offload` 均为 `disabled: true`；`session-log-deepseek` 为 `config.enabled: false`；末尾插入 `g3b-trusted-bridge-provider` 与 `offline-public-skill`。

**仍不等于 registry**：`!!js` 表达式在加载期求值，条目列表不能证明某插件「运行时确实没注册工具」。故整体 `status=UNVERIFIED`。

### 4.3 无法证明项（逐条）

1. DSH 进程内 `ctx.tools.schemas()` 的**完整集合**没有任何公开导出；
2. `!!js` 求值后的实际插件图不可观测（除非改 runtime）；
3. 在 bridge adapter **之后**才注册 provider/tool 的插件不会被 `apply()` 的启动守卫看到；
4. Candidate 的本地 tool **执行**只能通过「到达 Controller 的请求 `tools` 数组」间接观测。

### 4.4 兜底链（可执行、已实测）

| 层 | 机制 | 位置 |
|---|---|---|
| 1 | provider 唯一：`apply()` 发现已有 provider 即抛错 → 该 run 无法启动 | `spikes/g3b-trusted-bridge/src/index.ts` |
| 2 | 路由固定：只允许 `offline-test-only-g3b` / `fixture-bridge-v1`，`purpose ∈ {null,"conversation"}` | 同上 + `bridge/protocol.py` |
| 3 | 单一发送路径：固定 `/work/g3b/bridge.sock`，无其它出站 API | adapter + Controller |
| 4 | **Tool 白名单**：请求中每个 tool 的 `canonical_json` sha256 必须命中 Admission 批准集合，否则 `ADMISSION_TOOL_SCHEMA_MISMATCH`（Reserve/Claim 之前） | `bridge/controller.py::_prepare_checked` |
| 5 | 内容限制：image/file/attachment/store 块 → `REQUEST_INVALID`；`has_files/images/store=false` 写入 prepared | 同上 |

**结论**：`registry == skill_lookup only` **未被证明，也未声称**；但「未批准 tool 进入一次 synthetic provider send」已被 §5 的两级证据关闭。

---

## 5. B04 — 未批准 Tool / 额外 Tool / 改 Schema：必须拒绝

### 5.1 Host 契约（真实 Controller/Broker/AttemptJournal/Fake，in-process）

`artifacts/g4/runtime/admission-contract.json`（13 例全 PASS，`ok=true`）：

| 用例 | 期望 | 实际 | ledger 增量 |
|---|---|---|---|
| 未批准名 `bash` | reject | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 0/0/0/0，Fake 0 |
| 修改已批准 schema（加 `path`） | reject | 同上 | 0，Fake 0 |
| 已批准 + 额外 `fs_read` | reject | 同上 | 0，Fake 0 |
| 同名换名 `skill_lookup_shadow` | reject | 同上 | 0，Fake 0 |
| `file` 块 | reject | `REQUEST_INVALID` | 0，Fake 0 |
| `image` 块 | reject | `REQUEST_INVALID` | 0，Fake 0 |
| 自授权字段 `authorized:true` | reject | `ADMISSION_SELF_AUTH_DENIED` | 0，Fake 0 |
| 辅助 purpose `title` | reject | `BAD_TYPE`（协议层） | 0，Fake 0 |
| 已批准 tool 正常 | accept | `finish` | +1 reservation/claim/attempt/receipt |

### 5.2 真实 raw-UDS（Candidate 容器内，真实 UID 65534）

`artifacts/g4/runtime/run.json → raw_uds_run`（`run_id=g4b-raw-20261118164755`）：hold candidate 容器（同 stage/同 uidmap/`--network none`）用 `podman exec` 连真实 socket：

| 用例 | 实际 code | ledger |
|---|---|---|
| unapproved_tool_name | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 0 |
| modified_approved_schema | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 0 |
| extra_tool_alongside_approved | `ADMISSION_TOOL_SCHEMA_MISMATCH` | 0 |
| file_block | `REQUEST_INVALID` | 0 |
| self_authorization_field | `UNKNOWN_FIELD` | 0 |
| auxiliary_purpose_title | `BAD_TYPE` | 0 |

负例阶段后**快照**：`reservations=0, claims=0, attempts=0, intents=0, fake_counter=0` → **在 Reserve/Claim 之前被拒，Fake=0**。

---

## 6. B05 — 真实 DSH Tool 两轮账本

`run_id=g4b-tool-20261118164749`，冻结 launcher、真实 DSH、真实双 principal、`exit 0`；launcher 自身 12 项检查全 PASS（`run-tool/run/checks.json`）。

| 项 | 值 |
|---|---|
| Reservations | **2**（`distinct_reservation_ids=2`） |
| Claims | **2**（`budget_dispatch_claims`，均 `COMPLETED`） |
| Send intents / Attempts | **2 / 2**（`tool_once` + `tool_final`，均 settled） |
| Receipts | **2**（`rcpt-*.json`），Fake `received-count=2` |
| `Prepared.request_digest` == `Claim.request_digest` | 2/2 ✓ |
| `Attempt.payload_digest` == `Receipt.raw_sha256` | 2/2 ✓ |
| 两个 `call_id` / `reservation_id` / `receipt_id` 互不相同 | ✓ |
| 每个 cycle 的 `reservation_id` 链路一致（claim↔attempt↔reservation） | 2/2 ✓ |
| Candidate 侧观测 | `G3B_BRIDGE_REGISTRY` 1 条；真实 `skill_lookup` 调用 1 次、结果含 `binary_search`/`m0-skills-v1` |
| 额外 provider 请求 | **0**（receipts=2 = assistant_messages=2 = fake counter=2） |

> 两对摘要分别映射，二者**不要求**彼此相等（G4 计划 §14 明确禁止把它当密码学条件）。

---

## 7. B06 — 额外 Provider 请求注入

| 场景 | 结果 | 证据 |
|---|---|---|
| 配额内第 2 个独立请求 | 独立 Reserve/Claim/Attempt/Receipt（+1/+1/+1，Fake +1） | raw-UDS `positive` 阶段；host `B06-second-independent-request` |
| 超配额（echo，`max_calls=1`）第 3 个请求 | `BUDGET_DENIED`，ledger 与 Fake **不变**（0 发送） | raw-UDS `quota` 阶段；host `B06-over-quota-extra-request` |
| 辅助 llm 路径（`purpose="title"`） | 协议层 `BAD_TYPE`（`purpose` 只允许 `null`/`conversation`） | host + raw-UDS |
| 真实 provider 兜底（`llm-deepseek`） | 合并配置 `disabled:true`；adapter 若发现已有 provider 直接抛错 | 合并 dump + adapter 源码 + 真实 run |
| 重试 | `max_attempts=1`（Admission+Controller）、adapter `maxRetries=0`；任何重试仍需新 Reserve/Claim | 模板 + adapter `providerRetryPolicy` |

**「无法注入」的诚实说明**：`session-title`、`mcp-resources` 等插件路径无法从外部逐条触发（需要改 runtime/配置，超出写域）。因此本行的结论不是「这些路径不存在」，而是：**它们即使存在，也只能经过唯一 adapter → 唯一 UDS → Controller Reserve/Claim，或被拒/0 发送**。这一点由 §4.4 的 5 层兜底 + §7 的配额/协议负例共同支撑。

---

## 8. B07 — compaction / judge / files / fallback 逐项

`artifacts/g4/runtime/runtime-probe.json → features`（合并 dump + 真实 run trace 佐证）。

| 功能 | 配置状态（合并 dump） | 真实 run 佐证 | 状态 | 是否需要 Controller 兜底 |
|---|---|---|---|---|
| `compaction-basic` | `disabled: true` | `compaction_events=0`；仅 2 次请求 | **PASS** | 是 |
| `image-offload` | `disabled: true` | 无 image/file 块到达 Controller | **PASS** | 是 |
| `llm-deepseek`（真实 provider/fallback） | `disabled: true` | adapter 唯一 provider 守卫；`realModelCalls=0` | **PASS** | 是 |
| `llm-retry` | 启用，但 `max_attempts=1` + `maxRetries=0` | 无重发；attempt 与 receipt 1:1 | **PASS** | 是 |
| files / multimodal | `tool-fs`/`tool-working-directory` 禁用；Controller 拒绝 file/image 块 | `has_files/images/store=false` | **PASS** | 否 |
| `session-log-deepseek` | `config.enabled: false`（**未** `disabled: true`） | 无上传路径、无网络标记、session 仅本地 JSONL | **PARTIAL** | **是** |
| `session-title` | **未禁用**（`fallbackMaxWords/Bytes` 配置） | 1 个 `session/title` 事件；**无第 3 次 provider 请求**；无 adapter 错误标记 | **BLOCKED** | **是** |
| `mcp-resources` | 启用，未见 server 配置 | 无外部资源访问证据 | **UNVERIFIED** | **是** |

**判读**：`session-title` 是唯一「配置未禁用且可能产生辅助 LLM 调用」的项。它没有产生额外请求（receipts=2），但**不能证明**它永不尝试；只能证明「尝试也只会被 adapter 的 `purpose` 校验拒绝或走 Reserve/Claim」。**不得声称该路径安全**，必须保留 Controller per-dispatch 兜底（G4-C 落点）。

---

## 9. B08 — Logs / Telemetry / Upload / Network

真实 run（`network_mode=none`）的 Candidate 侧证据：

| 项 | 值 |
|---|---|
| 容器网络 | `NetworkMode=none`、`Dns=[]`、`ExtraHosts=[]` |
| `AF_INET` / `AF_INET6` | `EACCES(13)`（`stage=socket`） |
| DNS | `gaierror -3`（Temporary failure in name resolution） |
| 接口 / 默认路由 | 仅 `lo`；无默认路由（`default_route_present=false`） |
| Candidate env 名 | 11 个（`HOME/PATH/PYTHONPATH/TMPDIR/DSH_*/NARB_*/PKG_*/NO_COLOR/HOSTNAME`）；**0 个 proxy**、**0 个 key-like** |
| 运行日志网络标记（`http://`/`https://`/`api.deepseek`/`upload`/`telemetry`/`POST /v1`） | **0 命中**（扫描 `run/*.log` + `traces/*.json`；`inspect-*.json` 是 podman 元数据，已排除） |
| Session 持久化 | 1 个本地 JSONL（`dsh-home/sessions/…/session.v4.jsonl`，5,820 B，19 行），路径为相对路径 |
| 上传证据 | 无（既无外发路径，也无外发尝试） |

**边界**：这证明「没有可用外发路径，且本轮真实运行中未观测到任何外发」，**不**证明「某插件的代码里没有上传意图」。该项按 G4 计划 §5.2 标为「已证明无路径 + 未观测」，不升级为「插件已确认无上传逻辑」。

日志泄漏面：`stderr_markers` 只含 1 条 synthetic registry 行；无 Key/token 值；证据目录不含 `sk-` 物质（见 B09 内容扫描）。

---

## 10. B09 / B10 / B11

### 10.1 B09 — Candidate stage 无 trusted code / Key / import

| 检查 | 结果 |
|---|---|
| 6,549 个 candidate 条目中的 `src/` / `trusted/` 路径 | **0** |
| Candidate 自有 `.py`（21 个）中的 `import autoteacher_m0` 语句 | **0** |
| 提及 `autoteacher_m0` 的文件 | 仅 `run/candidate_entry.py`（负向 import 探针）与 `run/probes/d2_04_broker_access.py`（负向探针） |
| 非依赖路径中的 key-like 文件名 | **0**（`etc/passwd`/`etc/group` 为合成文件，内容无 `BEGIN … PRIVATE KEY`） |
| 非依赖文本文件中的 `BEGIN … PRIVATE KEY` / `sk-<16+>` | **0** |
| 覆盖层引用 `/work/state`、`/project/src` | **0**（注释行之外） |
| 第三方 bundle（`node_modules`/`pkg-cache`/`native-cache`） | 由子树摘要覆盖（6,515 文件），不做逐名判定（其文件名合法包含 `api-key`/`token`） |
| 运行期复核 | Candidate principal：`uid_map=0 65534 1`，无 `/work/state` 挂载（G3-D D2 证据 + 本轮 principal.json） |

### 10.2 B10 — canonical 不漂移

| 项 | 值 |
|---|---|
| stage tree（canonical tar，**两次重算**） | `e1ff1449…` == `e1ff1449…` == 冻结值 |
| stage manifest | `644823d4…` == 冻结值 |
| 逐文件复核 | trusted 57 + candidate 6549 = **6606 行**全部与 stage manifest 一致 |
| rootfs / deps / DSH runtime | `25491e45…` / `e07729d7…` / `1cc41d5a…`（重算一致） |
| **未做** | 二次 `build_stage.py`（需容器内重编译 adapter，约 2 min）；因此「跨 worker 构建可复现」仍为 **`UNVERIFIED`**，本行只证明「既有 stage 的 canonical 与字面一致且可重复读取」 |

Worker/共享 stage 副作用：`--dump-config` 物化的 `$DSH_HOME/profiles`（4 文件）已计入证据并在隔离目录中产生，未污染 canonical rootfs/deps/stage。

### 10.3 B11 — 变更 → 下一次 dispatch fail-closed

| 变更 | 检出方式 | 结果 |
|---|---|---|
| 任意被覆盖文件字节变化 | 逐文件 sha256 | `modified:<path>` |
| 新增/删除文件 | root 枚举集合差 | `added:` / `removed:` |
| mode 变化 | lstat 四位八进制 | `mode_changed:` |
| 依赖树变化 | 子树摘要（path+sha+mode） | `tree_changed` |
| rootfs/deps/stage/runtime 变化 | canonical tar 摘要 | `*_not_canonical` |
| tool schema / route / limits / price / registry 状态变化 | `derived` 重算 + policy 比对 | `tool_schema_changed` 等 6 类理由 |
| manifest 自身被改 | 摘要重算 | `manifest_digest_mismatch`（exit 5） |

`require_manifest_match(policy, manifest, verification)` 返回 `{"ok", "reasons"}`；**`ok=true` 只表示「冻结字节与策略一致，可以发生一次 synthetic dispatch」，不是 Live 授权，不解锁 `LiveGate`**。与 G4-A 的接线点在 G4-C：Approval 契约应消费本 manifest digest（`6ca1aca3…`）与 `derived` 事实。

---

## 11. 测试与回归计数

| 套件 | 命令要点 | 结果 | exit |
|---|---|---|---|
| G4-B 契约测试（新增） | `pytest -q tests/integration/g4_b` | **38 passed** | 0 |
| 基础回归 + G4-B | `pytest -q tests/integration/{g3c,g3d,g3_bridge} tests/unit/security/test_gates.py tests/integration/g4_b` | **337 passed**（= G4-00 的 299 + 38） | 0 |
| 安全隔离集 | `pytest -q tests/unit/security tests/integration/sandbox/test_live_controller_no_key.py tests/integration/sandbox/test_egress_boundary.py` | **165 passed, 1 failed** | 1 |

唯一失败与 G4-00 §10 完全相同：`test_all_live_entrypoints_remain_blocked` 以硬编码容器路径启动子进程（`PYTHONPATH=/project/src:/deps`），在宿主必然 `ModuleNotFoundError` → `exit 1` 而非 `3`。**同一断言在正确 `PYTHONPATH` 下本轮复算仍为 `exit 3 / BLOCKED`**；属既有 `OPS-P2-b`，非 G4-B 回归，也未改测试去「修绿」。

新增测试文件：

| 文件 | 覆盖 |
|---|---|
| `test_manifest_contract.py`（6） | spec 完整性、确定性、排序/mode/size、自引用排除、真实 derived 与 policy 一致、anchor 为冻结值 |
| `test_verifier_fail_closed.py`（10） | 增/删/改/mode/树/derived/manifest 篡改/policy 漂移 |
| `test_registry_contract.py`（6） | `UNVERIFIED` 不变量、overlay id 集合、真实合并 dump 解析、抓包 schema == 批准 schema、任何差异都改变摘要 |
| `test_admission_tool_schema.py`（7） | 真实 Controller：未批准/额外/改 schema/文件/图片/辅助 purpose 拒绝 + 两次独立建账 + 超配额 0 发送 |
| `test_stage_no_trusted_code.py`（9） | B09 结构检查、adapter 三方一致、stage 逐行与 canonical、非旧 G3-C stage、模板钉死沙箱 |

---

## 12. 残余、`UNVERIFIED`、`BLOCKED` 与偏差

### 12.1 残余清单

| ID | 项 | 状态 | 说明 / 下一步 |
|---|---|---|---|
| R-B-1 | 权威 merged tool registry | **`UNVERIFIED`** | DSH 无导出 API；只能靠 §4.4 兜底。G4-C 必须保留 per-dispatch 校验 |
| R-B-2 | `session-title` 是否永不发起辅助 LLM 调用 | **`BLOCKED`** | 未禁用；本轮 0 额外请求但不可证「永不尝试」；需 Controller 兜底 |
| R-B-3 | `session-log-deepseek` 上传路径是否真正 inert | **`PARTIAL`** | 仅 `config.enabled=false`；无外发路径 + 无观测外发，但不证明插件逻辑 |
| R-B-4 | `mcp-resources` 外部资源面 | **`UNVERIFIED`** | 未见 server 配置；无外发观测 |
| R-B-5 | 跨 worker 二次 build stage 的字节可复现 | **`UNVERIFIED`** | 本轮仅重算既有 stage（两次一致）；未重编译 adapter |
| R-B-6 | `config/budgets.yaml` 未接线 | 观察 | 全仓无解析代码；真实限额在 stage 模板。若 G4-A 以其为授权依据需显式说明 |
| R-B-7 | Adapter 的「实际加载」强度 | 限制 | 无 JS `inspect.getfile`；依赖加载自报 + 三方字节一致 |
| R-B-8 | G4-A 的 `src/` 改动使冻结 manifest 失效 | 设计如此 | 在含 G4-A 的 HEAD 上 `verify_manifest` 会失败（`trusted_src:git_blob_mismatch`），即 B11 的 fail-closed 行为 |
| R-B-9 | 证据提交与 main 的差异 | 已记录 | 证据在本地 worktree `2f1e41f`（`src=cf40c6b`）产生；main 上对应代码提交为 `c29cabc` |
| R-B-10 | 宿主 1 项 host-only 测试失败 | 既有 `OPS-P2-b` | 与本包无关，未修改测试 |
| R-B-11 | P2（disk/userns/run-identity） | 未变 | 本轮不批准、不签收 |

### 12.2 提交与偏差说明

| 提交 | 主题 | 说明 |
|---|---|---|
| `376012c` | `feat: G4-B frozen runtime inventory and registry probes (no-key)` | `scripts/g4/**`、`config/g4/**`、`tests/integration/g4_b/**`，父 `e3d270e`，只 add 自己的路径 |
| `5559013` | `fix: G4-B raw-UDS ledger snapshot tolerates lazy claim table (no-key)` | Broker 的 `budget_dispatch_claims` 是 lazy 建表，负例阶段快照会报 `no such table` |
| `32acce9` | `fix: G4-B raw-UDS transport ids and evidence-based tool ledger (no-key)` | `transport_id` 必须 `tr-<32hex>`；tool run 的 `$RUN` 会被 launcher 删除，改从 evidence 副本对账 |
| `76f2b18` | `fix: G4-B tool-run ledger join and adapter marker sources (no-key)` | receipt 按 `receipt_id` 而非 nonce 连接；adapter 标记在 `traces/*.json` 的 `stderr_markers` |
| `c29cabc` | `fix: G4-B runtime probe evidence paths and stage scan classification (no-key)` | principal/dsh-result 证据实际落在 `traces/`；stage 扫描需区分 vendored bundle 与负向 import 探针 |
| **docs（本次）** | `docs: G4-B runtime inventory and matrix rows (no-key)` | 本文件 + 矩阵 G4-B 行 |

**偏差（主动披露）**：任务书列了两个提交（feat + docs）。实际产生 **4 个 `fix:` 提交**：前一轮真实运行暴露了 runner 的 4 个真实缺陷（懒建表、传输 id 格式、run 目录被删除、证据路径/分类），必须在交付前修复。按「不 amend」约束，未改写任何已产生提交，而是追加修正提交；`2f1e41f` 仅为证据基线 worktree 的本地提交，不在 main 上。

---

## 13. 证据路径与复现

证据根：`artifacts/g4/runtime/`（`artifacts/` 已被 gitignore）。

| 证据 | 路径 |
|---|---|
| 冻结输入清单 | `manifest.json`、`manifest.sha256`、`build-summary.json` |
| 运行时探针（模块/registry/features/B09/B10/egress） | `runtime-probe.json` |
| 合并配置 dump（L0） | `merged-config.yml`、`dsh-home/`（物化副作用） |
| Controller 契约负例 | `admission-contract.json`、`admission-work/` |
| 真实 DSH Tool run | `run-tool/`（`db/`、`receipt/`、`peercred/`、`traces/`、`run/`、`env/`） |
| 真实 raw-UDS run | `raw-uds/`（`db-snapshots/`、`run/`、`peercred/`、`traces/`） |
| 汇总 | `run.json`（`tool_run` + `raw_uds_run`） |

复现（在 `src == cf40c6b` 的干净 worktree 内，root）：

```bash
git worktree add --detach /root/g4b-baseline 2f1e41f   # 或：c29cabc 之后 checkout e3d270e -- src
mkdir -p /root/g4b-baseline/artifacts && \
  for d in "/root/Autonomous Teacher"/artifacts/*; do \
    ln -sfn "$d" "/root/g4b-baseline/artifacts/$(basename "$d")"; done
cd /root/g4b-baseline

PYTHONDONTWRITEBYTECODE=1 python3.11 -B scripts/g4/build_manifest.py
PYTHONDONTWRITEBYTECODE=1 python3.11 -B scripts/g4/verify_manifest.py
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src:artifacts/foundation/deps \
  python3.11 -B scripts/g4/probe_admission_contract.py
PYTHONDONTWRITEBYTECODE=1 python3.11 -B scripts/g4/run_g4_b.py --out-dir artifacts/g4/runtime
PYTHONDONTWRITEBYTECODE=1 python3.11 -B scripts/g4/probe_runtime.py \
  --run-evidence artifacts/g4/runtime/run-tool
```

关键摘要（本轮）：

```text
manifest.digest        = 6ca1aca34a36c564aa59976fd53b0ba74be6d66afacabfce9308f2540a0f1b25
manifest.json sha256   = 6101b6751e00a069fd59ac0dd2aca06f9d9b1f63c73db522a29b18e08942715a
merged-config.yml      = 0d525f44ef3ada744a306cd471c6a737…（39 entries）
runtime-probe.json     = f7f07b3aa1418d6ea2790bac052adbb8c779929f1d052969d7b0d7b9625c14dd
admission-contract.json= 8cc3e02eda2c543b3939280ae707470fce91b563bac24549bcd4cc85caa9426d
run.json               = 2cb274b0b8bbb70c59f760071ec90fe7a62ae3eb9e81a5584a461d4b1996d2b7
```

---

## 14. 声明

- 本文件覆盖 **G4-B-01..11**，不构成 G4-A/C/D/E 交付，不构成 G4 PASS，不构成 Live 授权。
- `E5_PRELIVE_FULL = BLOCKED_PENDING_HUMAN_DEPLOYMENT`、`G4-H` 六项 `BLOCKED`、`G5` 未启动 均不变。
- 全程 **0 真实 Key / 0 模型 / 0 外部 HTTP/TCP / 0 计费发送 / 0 `podman pull`**；两次容器 run 均 `--network none`，结束 `podman ps -a` 为空；rootfs/deps/stage/runtime canonical 未漂移。
- 未修改 `src/`、`gates.py`、`dsh_adapter.py`、`run_live.sh`、DSH 核心、`scripts/g3d/**`、历史证据与 Packet。
- `UNVERIFIED` / `BLOCKED` / `PARTIAL` 项已在 §0 与 §12 逐条列出，**未**以任何形式升级为 PASS。
