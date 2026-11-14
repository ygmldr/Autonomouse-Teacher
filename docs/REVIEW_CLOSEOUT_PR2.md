# PR2 独立审计 — 目标 Runtime Profile 联合验证（无 Key）

- 版本：REVIEW-CLOSEOUT-PR2-v1（2026-11-14 UTC）
- 审计者：`verify2`（非实现者；PR2 由 `sdk-docs` 实现）
- 审计对象：冻结提交 **`7d2cd3e8612212574767f0ff0ed1d1e7686bc643`**（PR2，父 `9b77a37`）与
  owner 证据 **`artifacts/m0-runtime-integration/manifest.json`**（sha256 `c6ea4e8666b3c267c9ade4f6ec11aa6450d52cdbb83d281efa87fabbeb24327a`）。
- 原始证据：[`artifacts/reviewer-closeout-pr2/`](../artifacts/reviewer-closeout-pr2/)（独立 commit stage、argv/UTC/exit/日志、3 次 verifier、变体负测、probe、Ruff、absence）。

## 0. 结论

**PASS_FOR_DECLARED_NO_KEY_PR2_SCOPE_WITH_F7_GAP**：PR2 冻结提交的目标 Profile dump-config/静态路由/负测/无 Key synthetic 运行在其声明范围内成立；**F7 缺口（guard 缺失时 synthetic fixture 仍被调用）已被如实复现并记录，未被写成 PASS 或“外部边界已解决”**；真实 Live/E1–E5 仍 BLOCKED/DECISION PENDING。

**发现 V-PR2-1（低，Ruff 门；非阻断功能/安全）**：PR2 冻结 commit 的 `scripts/verify_runtime_profile.py` 有 2 个 Ruff 错误（`F401 sys` 未用、`F841 stderr_path` 未用）；repo-wide 另有 4 个来自 PR1 测试文件的历史 F401（V-PR1-1/V-PR3-1 已报）。**post-freeze commit `87f44e1`（ruff hygiene，Lead 授权）已移除这 2 行**；对 PR2 commit 本身的审计记录该 lint 缺陷，修复已存在于当前 HEAD，无需新功能 SHA/security 重测，但 PR2 冻结证据/文档不应声称 repo-wide Ruff PASS。见 §6。

## 1. 方法与隔离边界

- 独立 `/project` stage：`git archive 7d2cd3e`（153 文件，完整 commit tree；7 个 PR2 文件 hash 与 manifest 逐一匹配）。仅对 config/scripts 的只读副本设置 0444（replicate reviewed stage；定向测试断言 `st_mode & 0o222 == 0`），不改任何字节。
- `/target` 目标 runtime 环境：owner `stage/target`（6530 文件，normalized tar `f8f75203…` 独立复算一致）。其组件均由冻结身份构成并已逐项核对：guard lib **3d2b9cf5…**（PR1 冻结 lib）、fixture `9871486f…`、skill `521bc0f1…`/`6988fc43…`、runtime node_modules normalized `2884de23…`、native cache `40c34d27…`、pkg cache **4857**、broker policy `c67d2bbf…`（=PR2 commit）。该目录来自冻结产物而非未审查 worktree；审计对 /target 的结论以这些 hash 为锚，对 /project 使用 commit archive。
- 固定 digest 无 Key 禁网 OCI（rootfs `25491e45…`、image `62d3569e…`；`--network none`、`--http-proxy=false`、`--unsetenv-all`、uid 65534、只读 rootfs、cap-drop ALL、no-new-privileges、cgroup 限制、`/tmp`+`/work` noexec tmpfs 64m）。宿主只做 Git/哈希/JSON 与 podman launcher；未读真实凭据/未联网/0 模型 HTTP。

## 2. Git / 范围

| 核对项 | 结果 |
|---|---|
| commit | `7d2cd3e`，父 `9b77a37`，`2026-11-14 15:18:23Z` |
| 变更 | **仅 7 文件**：`docs/DSH_TARGET_PROFILE.md`、`config/dsh/target-runtime.patch.yml`、`config/dsh/target-runtime-opencode-go.patch.yml`、`config/dsh/target-broker-policy.json`、`scripts/verify_runtime_profile.py/.sh`、`tests/integration/runtime/test_target_profile_static.py` |
| 混入 | 无 `src/accounting`/`security`/guard/其它实现改动；`git diff --check` exit 0 |
| 历史证据 | phase5 `391767d3…`、PR1 `df14f3c1…`、PR3 `b5c16f81…` 未改 |
| 证据身份 | owner manifest `c6ea4e86…`；image id/digest 与 manifest 一致；target stage `f8f75203…` |

## 3. 独立重跑（全部固定 digest 无 Key OCI，新 argv/UTC/exit/日志）

| 用例 | 结果 |
|---|---|
| restart-verifier 1/2/3（`verify_runtime_profile.py` 内部执行 `--dump-config`） | **PASS ×3**，rows `40/40/40`，exit 0 |
| OpenCode Go 静态 overlay（+`--patch target-runtime-opencode-go.patch.yml --require-opencode-go`） | **PASS**，rows 41；`apiKeyEnv=OPENCODE_API_KEY`、`baseURL` 缺失/None、`reasoning=max`、`retryPolicy.maxRetries=0` |
| 目标定向测试 `tests/integration/runtime/test_target_profile_static.py` | **4 passed**，exit0 |
| 负向变体 no-guard | **FAIL exit20**：`MISSING_REQUIRED_ROW:runtime-budget-guard` 等（39 rows） |
| extra-provider | **FAIL exit20**：`UNEXPECTED_PROVIDER_ROW:rogue-provider`（41 rows） |
| bad-guard-sha | **FAIL exit20**：`GUARD_BROKER_POLICY_HASH_MISMATCH` |
| route-mismatch | **FAIL exit20**：`GUARD_POLICY_ROUTE_MISMATCH` |
| synthetic probe valid | `RUN_COMPLETED`；RBG_BOOT=1、RBG_RESERVE=1、RBG_SETTLE=1、fixture_invocations=1、**real_model_calls/http_calls=0** |
| synthetic probe bad-guard-sha | `RBG_BOOT_INVALID`（`RBG_BROKER_POLICY_HASH_MISMATCH`, fail_closed=true）；**fixture_invocations=0** |
| synthetic probe no-guard | RBG_BOOT=0；**fixture_invocations=1** → **F7 gap 复现**（不是 PASS，不代表外部边界已解决） |

## 4. merged config 断言核对

独立 verifier PASS（每次内部 dump-config exit0、rows40）覆盖：`llm-deepseek`、`plugin-package-inventory-deepseek`、`compaction-basic`、`image-offload`、`tool-fs`、`tool-working-directory`、`persistent-bash/pwsh`、`terminal-bash/pwsh`、`pty`、`subprocess`、`jobs` **disabled**；`session-log-deepseek.config.enabled=false`；`runtime-budget-guard`/`offline-test-only-provider`/`offline-public-skill` 行存在；guard policy `offline-test-only/fixture-v1`、`maxProviderRetries=0`、broker policy path 在 `/target` 内且 `configSha256=c67d2bbf…` 与文件真实 sha 相等；`python` 绝对路径/`pythonPath` 存在；无 API_KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL 字段名；无额外 provider row（OpenCode Go 变体只允许 `llm-pi-ai`）。OpenCode Go 静态字段逐项正确（占位 env、无 baseURL、reasoning=max、maxRetries=0），无 Key/网络操作。

## 5. 证据链与边界

- owner manifest `c6ea4e86…`；evidence 49/49 **对冻结 commit 7d2cd3e 成立**（逐项核对：7 个 repo 文件 hash 与 commit blob 相等；logs/probe/variant 日志均 OK）。当前 worktree 的 `scripts/verify_runtime_profile.py` 已被 post-freeze `87f44e1` 修改（V-PR2-1 lint 修复），故按工作树直接 `sha256sum -c` 是 48/49——这是**冻结后授权修复导致的 docs/脚本漂移**，不是证据篡改；审计结论以 commit 为准（见 §6/O-PR2-1）。
- 无隐藏 Live/Key 解锁：`verify_runtime_profile.py` 只读 dump/verification，不读凭据/home、不发网络请求，`.sh` 仅 wrapper；probe 仅用固定 synthetic fixture，无真实 provider dispatch；`real_model_calls=0,http_calls=0`。
- 历史 phase5/PR1/PR3 证据未改；容器 absence=0；rootfs 因 mount target 产生空 `/target` 已清理恢复 canonical `25491e45…`，deps `e07729d7…`；未 git add/commit。

## 6. 发现/观察

- **V-PR2-1（低，lint；非阻断）**：PR2 commit `scripts/verify_runtime_profile.py` Ruff 2 errors（`F401 sys`、`F841 stderr_path`）；PR2 文档/manifest 未声称 Ruff，但 task47 要求独立 Ruff，记录为冻结提交质量缺陷。**HEAD `87f44e1`（V-PR3-1 ruff hygiene）已删除该 2 行**；建议后续以新冻结/errata 记录修复，不需要重跑功能测试。repo-wide 另有 4 个 PR1 测试 F401（V-PR1-1/V-PR3-1，已报）→ 当前 repo-wide lint 仍红，PR2 自身不再贡献。
- **O-PR2-1（信息）**：owner evidence 以仓库工作树路径绑定 `../../scripts/verify_runtime_profile.py`（期望 PR2 blob `9c7c5867…`）；post-freeze 修复后当前文件 hash 变为 `e2542747…`，导致 `sha256sum -c` 48/49。建议后续 manifest 记录 commit/blob 身份或注明 post-freeze 漂移；不否定冻结时 49/49。
- **F7**：no-guard probe 明确 boot0/fixture1 已记录为 gap；owner manifest/docs 未写成 PASS/外部边界已解决，审计确认一致。

## 7. 残余 UNVERIFIED（不夸大）

1. 真实 provider/egress/Key 边界（PR4）未实现；无真实模型/HTTP/Key。
2. merged raw tool registry 完整枚举仅为插件的间接证据；真实 loader 对 guard import 失败的行为仅复现 gap，未完成 OS 外部拒绝。
3. 真实 broker 不可用/崩溃在目标 Runtime 的时序未触发；OpenCode Go 仅静态字段（无 Key/网络/批准，需 PR5）。
4. E1–E5/LiveGate/Live 判定不变：BLOCKED/DECISION PENDING；PR2 通过不解锁任何 Live。

## 8. 证据索引

- 审计 manifest `artifacts/reviewer-closeout-pr2/manifest.json`、`manifest.sha256`、`evidence.sha256`；独立 `/project` stage（153 文件）+ `stage.tar`；logs/（verify-1..3、opencode、variants、probes、pytest、ruff）+ `commands.jsonl`（argv/UTC/exit/sha）。
- owner 交叉核对：`artifacts/m0-runtime-integration/`（manifest `c6ea4e86…`、target stage `f8f75203…`、logs）。
