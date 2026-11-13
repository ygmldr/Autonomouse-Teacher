# E4 — 公开 Mock 配对设施与预算账本

## 结论与边界

- **E4 Mock：已执行**。20 个公开虚构案例 × 两策略 = 40 次独立运行、40 个新 Session、40 个 Run ID；同输入的固定 Mock 输出可重复。
- **E4 Live：BLOCKED**。没有人类安全审批、真实 Key 或真实模型调用；官方渠道和可选渠道均未获得本报告的 Live PASS。
- 两个公开分区是 12 开发例和 8 **模拟保留例**，不是隐藏集。真实私有评估集必须在仓库及候选挂载之外，本次 NOT RUN；不会读取 `AT_M0_PRIVATE_EVAL_DIR`。
- 固定脚本响应只验证管线、评分和记账，**不证明教学效果、真人学习增益或模型优劣**。Mock 两策略规则分数全部 1，差分全部 0，是有意的确定性夹具结果，不是教育实验。
- 本模块不提供 Live 解锁路径。SDK 自主内部 steps 的逐次请求拦截尚未得到证明；SQLite 账本通过不代表该缺口已解决。整体选型仍需 Lead 按所有硬门槛判断，本报告不签发 GO。

## 已实现范围

- [预算守卫](</root/Autonomous Teacher/src/autoteacher_m0/accounting/budget.py>)：每次请求前最坏费用/Token 预留，线程安全处理在途累计；每次重试也计 request 和 step，默认任务 8 steps、1 retry，总计 50 requests、250 万输入和 60 万输出；软预算 $3、硬预算 $10、调用 $0.20，并支持更严格的 case cap。
- [持久账本](</root/Autonomous Teacher/src/autoteacher_m0/accounting/ledger.py>)：SQLite `BEGIN IMMEDIATE` 跨进程原子预留/结算；固定 scope 的策略不允许重启时悄悄放宽；官方/可选路线共享同一 scope 总额。崩溃留下的 pending reservation 不自动退款，后续必须显式按实际或保守值结算。
- [渠道价格快照](</root/Autonomous Teacher/src/autoteacher_m0/accounting/pricing.py>) 与 [Usage](</root/Autonomous Teacher/src/autoteacher_m0/accounting/usage.py>)：Decimal、cached/uncached/output/extra fee，实际总账单优先；None usage 用预留的完整缺失维度估算，不作为 0。已知额外费用在失败、部分 usage 和缺账单时保留，actual total invoice 不重复加费。实耗超过预留如实记账并 fail closed。所有 Mock 价格明确 synthetic，并非 DeepSeek 当日实时售价。
- [评估契约](</root/Autonomous Teacher/src/autoteacher_m0/evaluation/contracts.py>) 与 [独立评分器](</root/Autonomous Teacher/src/autoteacher_m0/evaluation/graders.py>)：契约仅在评分平面，候选只收公共 `RunRequest`。不仅检查概念词，还检查关系句、诊断和必要动作；两例必须先追问。错误是 `EVAL_ERROR`/`RUN_ERROR`、score=null，不用 0 分掩盖；不确定格式/边界代码/否定语义是 `NEEDS_REVIEW`。
- [泄露检查](</root/Autonomous Teacher/src/autoteacher_m0/evaluation/leakage_checks.py>)：完整 Python 函数、C++/Java 风格程序及输入输出算法负例；片段/伪码进入 review。它不是通用语义正确性或无泄露证明，必须独立人类抽查。
- [20 例公开数据](</root/Autonomous Teacher/fixtures/teacher_cases.jsonl>)：单调性 5、边界 5、复杂度/先修 4、代码/溢出 4、信息不足 2。安装后 loader 优先读 package data，源码再回退到公开根 fixture；不读取私有源。
- [配对执行](</root/Autonomous Teacher/src/autoteacher_m0/experiments/paired.py>)、[固定 Mock 候选](</root/Autonomous Teacher/src/autoteacher_m0/experiments/mock.py>) 与 [持久报告](</root/Autonomous Teacher/src/autoteacher_m0/experiments/report.py>)：相同模型标签/Mock route、输出 Token 上限 2048、固定采样/无工具；两策略独立 runtime 实例和 session。JSON/SQLite/Markdown 均先走 foundation 的公共 sanitize；评分逐例差分、失败原因、trace、prompt 指纹、价格版本、实际 Mock 零账单与非零 synthetic 估算分开保存。

**安全说明**：候选输入不含标签的 API 测试不是恶意代码文件系统隔离证明。公开测试容器为离线评测目的可读公共评分器和 Mock 标签；动态敌对候选不得挂载它们、私有集、账本或控制策略，应使用 security 的独立受限执行边界。当前独立 SDK Live 隔离与人类授权仍 BLOCKED。

## API / CLI 接入（已通知 foundation）

```python
from pathlib import Path
from autoteacher_m0.experiments.cli import run_paired, render_report

output_directory = run_paired(artifact_dir=Path('/work/artifacts'))
report_path = render_report(artifact_dir=Path('/work/artifacts'), experiment='latest')
```

- `run_paired` 仅 Mock，返回含三种产物的实验目录；不允许使用它运行 Live。
- `run_mock_pairs(fixture_path=None, runtime_factory=TeachingMockRuntime, grader=None)` 返回纯项目数据，方便确定性故障注入。
- 公共 CLI 由 foundation 负责 `paired --mock` / `report --experiment latest` 接入；本任务未修改 CLI、根依赖、锁或公共 runtime contracts；无新增第三方依赖。

```python
from autoteacher_m0.accounting import BudgetLedger, BudgetLimits, Usage

# 路径、scope_id 和审批过的预算策略由外部可信控制器固定；候选不能选
# 新数据库/新scope来重置预算，不能写入或删除账本。以下仅为API示例。
ledger = BudgetLedger('/work/controller/budget.sqlite3',
                      scope_id='maintainer-fixed-budget', limits=BudgetLimits())
reservation = ledger.reserve(task_id='stable-agent-task', prices=approved_price_snapshot,
                             input_tokens=complete_context_bound,
                             output_tokens=enforced_output_bound, retry=False,
                             extra_fees_usd=known_max_extra_fees, max_cost_usd='0.10')
# 只有 reserve 成功才可以发起该次请求；每个 retry/step/Judge 都重新预留。
# 无响应/异常：ledger.fail(reservation)；已知usage：ledger.settle(reservation, Usage(...))。
# request需要携带与snapshot一致的实际route/model；不得自动fallback。
```

`PriceSnapshot` 必须包含 route/model/version/source/captured_at 及输入、缓存、输出费率。没有执行当日真实价目证据，不得把 synthetic 快照用于 Live。输入估算 helper 以 UTF-8 bytes+overhead 为保守工程占位，调用方必须提供所有 system/history/tool/context 的完整上界，并强制输出上界（含供应商计费 reasoning/压缩等）。未验证内部调用、额外费用或隐藏上下文上界时，应阻断 Live，不能宣称仅靠 Python 超时保证账单。账本不是权限开关，也不替代供应商低额度限额或外部停机保护。

## 实际容器测试与原始证据

所有项目代码、Python/pytest/ruff 执行均在 security 验证过的 Podman 容器，宿主没有 import/执行新代码：

- 本地公开 runtime rootfs；CPython 3.11.15；foundation 提供锁 hash 校验后的依赖只读挂载。
- `--network none --http-proxy=false --unsetenv-all --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges --read-only`。
- `--pids-limit 32 --memory 512m --memory-swap 512m --cpus 1`，只读公开 staging；`/tmp` 32m、`/work` 64m tmpfs；外层 timeout 75s，Podman timeout 60s；不挂凭据、宿主私有目录、docker.sock 或真实私有集。
- 隔离模板与镜像/本地 rootfs 残余风险见 [THREAT_MODEL](</root/Autonomous Teacher/docs/THREAT_MODEL.md>)。本地 rootfs 不是已发布的 digest-pinned 镜像，不能把本次环境当作已完成最终镜像可复现验收。

| 检查 | 实际结果 | 证据 |
|---|---|---|
| 首轮定向 pytest | 49 PASS / 1 FAIL；误将自然语言 `return the first position` 当代码，已修规则为行首 return | [首轮日志](</root/Autonomous Teacher/artifacts/evaluation/first-test.log>) |
| 修复 + 持久账本测试 | 62 PASS | [第二轮日志](</root/Autonomous Teacher/artifacts/evaluation/second-test.log>) |
| 最新回归与lint | **63 PASS，ruff All checks passed，exit 0**（0.47s） | [最终日志](</root/Autonomous Teacher/artifacts/evaluation/final-tests.log>) |
| Ledger 重启/四独立 OS 进程争用 | 包含在测试内，跨 route scope 总预算不可重置，pending/费用不丢失 | [账本测试](</root/Autonomous Teacher/tests/unit/accounting/test_ledger.py>) |
| 20×2 Mock 全自动 | 40 SCORED，40独立session/run，开发12/12、模拟保留8/8可比；API账单$0，synthetic估计$0.030316 | [生成比较](</root/Autonomous Teacher/artifacts/evaluation/e4-public-mock-evidence/comparison.md>) |
| 评分器故障、无效结果、runtime失败 | score=null；配对标INCOMPLETE，不伪造delta=0 | [评估测试](</root/Autonomous Teacher/tests/unit/evaluation/test_evaluation.py>)、[实验测试](</root/Autonomous Teacher/tests/unit/experiments/test_experiments.py>) |
| 明确完整答案与片段 | 明确负例LEAK；边界NEEDS_REVIEW | [评估测试](</root/Autonomous Teacher/tests/unit/evaluation/test_evaluation.py>) |
| 候选无标签输入 | API input最小化PASS；恶意文件访问隔离不从此推导 | [配对测试](</root/Autonomous Teacher/tests/integration/paired/test_paired_mock.py>) |
| 真正隐藏集 / 人类语义盲审 / Live≥6对 | NOT RUN / NOT RUN / BLOCKED | 不用公开Mock替代 |

三种原始配对产物均在容器内生成，以只含三个固定普通文件的 tar 取回；宿主先检查成员、大小、类型，再只提取精确白名单；数据不在宿主执行：

- [完整JSON](</root/Autonomous Teacher/artifacts/evaluation/e4-public-mock-evidence/experiment.json>)，SHA256 `5c4448fc783e2e9d9d756230f8da1646a91fc8bf67ec5fbdce9a1841a81c6ba0`
- [SQLite](</root/Autonomous Teacher/artifacts/evaluation/e4-public-mock-evidence/experiment.sqlite3>)，SHA256 `070274ec9289cd039f2ce3e9b15b784557fafcc447d1da54726798e3a19299e2`
- [比较Markdown](</root/Autonomous Teacher/artifacts/evaluation/e4-public-mock-evidence/comparison.md>)，SHA256 `d70adf852ae29af9d6a2bea82cd9e6953ff72b12c79d37e549c8a834df575ad9`

产物中 Git SHA 标记 UNRECORDED、SDK/Profile NOT_USED，未假造执行版本。artifact 是本机原始证据且可能被 Git ignore；提交/归档时维护者需另行保留它们。具体控制器基线仍需维护者冻结 SHA、配置和审核后重新准入。
