# E5-PreLive — 无 Key 子集验证报告（PR3）

- 任务：`task-36`（v0.5 PR3）；基线 `HEAD=e8b6e45…`；被测实现 SHA 仍 `feb7118…`
- 结论：**E5-PreLive 无 Key 子集 = PASS（仅限本报告列出的子集）；人类授权/凭据/egress/
  真实 Runtime 边界 = BLOCKED；E5-PreLive 整体 NOT PASS；Live 与总体判定仍 BLOCKED**
- 证据：`artifacts/m0-controller-no-key/`（manifest/hash/argv/UTC/exit/镜像/日志）
- 设计：[`LIVE_CONTROLLER_SECURITY_DESIGN.md`](LIVE_CONTROLLER_SECURITY_DESIGN.md)

> 本报告不得被引用为 Live 批准、E5 通过、GO 或“官方主路由可用”。未读取任何真实
> Key；0 模型调用、0 真实 HTTP；仅使用假 Key 与 mock/hung 子进程。

## 1. 执行环境（固定 digest、无 Key、禁网）

| 项 | 值 |
|---|---|
| 镜像 | `localhost/autoteacher-local-oci@sha256:62d3569ec38e27ed16fa3147515c1c78d993bb7df831cc1fe29811f3fe64667b` |
| image id | `56db1e2ad5ab29d3f39304d4fc9d0584d90e6bb90ffb657f31f3c5b77f9a7715` |
| Python / pytest | 3.11.15 / 9.2.0（`/opt/python/bin/python3.11`，`PYTHONPATH=/project/src:/deps`） |
| 隔离 | `--network none`、`--http-proxy=false`、`--unsetenv-all`、`--read-only`、只读输入 mount、`--cap-drop ALL`、`no-new-privileges`、`--user 65534:65534`、pids/cpu/memory 上限、`/tmp`+`/work` 有界 tmpfs（noexec）、宿主不执行 pytest |
| 测试输入 | 仅当前工作树的 `src/`、`tests/`、`scripts/`、`pyproject.toml` 的只读 stage（69 files，normalized tar sha256 `5c27c021…d19a`） |
| 凭据 | 无真实 Key；测试仅用固定假值 `oc_sk_FAKE_REHEARSAL_…` 做泄漏负测 |
| 时间 | 2026-11-14T15:00:14Z → 15:00:33Z（UTC） |
| exit | 0 |
| 结果 | **104 passed, 1 skipped**（105 collected）；Ruff：**PR3 scoped**（security/unit/sandbox/scripts）`All checks passed!`；repo-wide 当时有未用 import/赋值（与 PR3 security 无关），已由 V-PR3-1 修复，修复后 repo-wide `All checks passed!`（见 `artifacts/m0-controller-no-key/manifest-errata.json`） |
| skip | `tests/integration/sandbox/test_probe_contract.py`（需外部 `/input` 探针 mount，既有契约，与本 PR 无关） |

argv：`artifacts/m0-controller-no-key/argv/no-key-tests.argv.json`；
日志：`logs/no-key-tests.{stdout,stderr}.log`、`logs/no-key-tests.collect.log`、`logs/ruff.stdout.log`。

测试分布：`test_authorization.py` 28、`test_credential_boundary.py` 13、
`test_watchdog.py` 8、`test_live_controller_no_key.py` 5（新增/本 PR 相关 54）；
既有 `test_docker_runner.py` 36、`test_gates.py` 14 仍通过（回归）。

## 2. E5-P01..P05 逐项结果

| 项 | 要求（v0.4 §E5-PreLive） | 本 PR 证据 | 状态 |
|---|---|---|---|
| E5-P01 | 审批文件 SHA/配置哈希与实际运行一致 | `ExecutionAuthorization` 强制 5 个 binding SHA 与实际 expected 逐项相等；任一不符拒绝（28 项授权测试）；正例用仓库外签名字节 | **NO-KEY SUBSET PASS**；真实人类签核文件/实际 run 仍 **BLOCKED** |
| E5-P02 | 任何未审批文件变更导致 Live Gate 关闭 | 绑定 mismatch/route/tools/budget/deadline 全拒绝；`LiveGate` 既有 baseline mismatch 测试继续通过 | **NO-KEY SUBSET PASS**（逻辑层）；部署层只读/merge 校验 **BLOCKED** |
| E5-P03 | Agent 更改 `SECURITY_APPROVALS.md`/环境/flag 不能触发凭据注入或绕过独立人类授权 | Markdown/仓库内 JSON/symlink/自签 JSON 拒绝；`AT_M0_LIVE_APPROVED` 等 env 无效；`--live` CLI 返回 BLOCKED/3；Controller 无执行方法；Fake Key 不进入候选 env/日志 | **NO-KEY SUBSET PASS**；独立 OS 授权边界 **BLOCKED**（无部署、无私钥托管） |
| E5-P04 | DSH 可用工具白名单不含未批准 Shell/代码执行 | 授权 `allowed_tools` 仅允许 `skill_lookup` 且必须与实际 registry 完全一致；其他工具/重复项拒绝 | **NO-KEY SUBSET PASS**（校验器）；真实 merged registry **UNVERIFIED/BLOCKED** |
| E5-P05 | 日志/子进程 env/工作目录/插件路径不含候选可访问真实 Key | 候选 env 仅 allowlist；假 Key/env/token/proxy 被丢弃并记违规；日志脱敏/scan；mount 拒绝 `/root`、home、`.config`、credentials、socket、repo；hung 进程树被 kill；容器 absence 观测 | **NO-KEY SUBSET PASS**（rehearsal）；真实 launcher/egress/OS 权限 **BLOCKED**（PR4） |

**E5-PreLive 整体：NOT PASS。** 原因不是逻辑负测失败，而是 v0.4 要求的人类独立授权、
可信控制器部署、真实凭据边界与真实 Runtime/工具 registry 证据均未提供（本 PR 不授权）。

## 3. 负测矩阵（摘要）

| 类别 | 用例数 | 结果 |
|---|---:|---|
| 授权来源/签名/绑定/时间/撤销/预算/时限/工具/路由 | 28 | 全部按预期拒绝；正例通过 |
| 假 Key、env 继承、日志脱敏、mount/argv、OpenCode Go egress 策略 | 13 | 全部拦截；合法 `ContainerRunner` 命令通过 |
| watchdog：hung 进程/孙进程、deadline、step/dispatch、非零退出、清理异常 | 8 | 全部 kill/确认 absence/PENDING 保守；不重试 |
| 端到端无 Key rehearsal（有效签名仍 BLOCKED、Live 入口、假 Key 不泄漏） | 5 | 全部 BLOCKED/无泄漏 |
| 既有 security 回归（docker_runner/gates） | 50 | 全部通过 |

明细见 [`LIVE_CONTROLLER_SECURITY_DESIGN.md`](LIVE_CONTROLLER_SECURITY_DESIGN.md) §7 与
测试文件本身；这里不把“逻辑测试通过”写成“部署安全已验证”。

## 4. 本次新增/修改（scope 内，未 commit）

- 新增：`src/autoteacher_m0/security/{authorization,ed25519,credential_boundary,watchdog,live_controller}.py`
- 更新：`src/autoteacher_m0/security/__init__.py`（仅导出，无 Live allow 路径）
- 新增测试：`tests/unit/security/test_{authorization,credential_boundary,watchdog}.py`、
  `tests/integration/sandbox/test_live_controller_no_key.py`
- 未改动：`gates.py`、`docker_runner.py`、`scripts/run_live.sh`、`runtime/dsh_adapter.py`、
  其他 agent 的 `src/autoteacher_m0/accounting`、`tests/unit/accounting`、
  `tests/integration/budget_bridge`（工作树中其 in-progress 修改只记录、未 stage/commit）

## 5. 仍缺的人类前置 / 后续 PR

1. 维护者独立审阅本 PR 代码/依赖/部署清单，确认 Ed25519 公钥/私钥托管与撤销流程；
2. E5-P03 真实独立授权边界：Controller 以独立 OS 身份/权限部署，只读冻结 profile，
   候选不可写授权/配置；
3. PR4：真实 egress/Key Broker、候选禁网强制、billable-path inventory、预算/usage 预留
   与请求级上限；本 PR 只提供设计约束与负测，**不宣称真实硬费用上限**；
4. PR2/PR5：真实 merged Profile/工具 registry/插件加载失败模式，以及 OpenCode Go
   smoke（在 PR1–PR4 + 人工批准后才可执行）；
5. 真实 Provider wire/usage/账单/错误与模型映射仍 UNVERIFIED；任何 Live 运行前必须补齐。

## 6. 证据与复验

- 设计：`docs/LIVE_CONTROLLER_SECURITY_DESIGN.md`
- 证据目录：`artifacts/m0-controller-no-key/`（gitignored）
- 清单：`manifest.json`；哈希：`evidence.sha256`
  → `cd artifacts/m0-controller-no-key && sha256sum -c evidence.sha256`
- 容器 absence：`container-absence-after.txt`（无 `at-m0-pr3-no-key-tests` 容器）
- 本轮结论仅覆盖 **NO-KEY 子集**：E5-PreLive 整体、Live、E1–E5、总体 GO 判定仍
  **BLOCKED / DECISION PENDING**。
