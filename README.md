# Autonomous Teacher — M0

依据 [v0.4 任务书](<docs/Autonomous_Teacher_M0_v04.md>) 的离线优先技术验证设施，不是教学产品。当前总体 **DECISION PENDING**；没有真实模型调用，也没有人类安全/路由批准。

## 安全边界

**所有本仓库生成代码仍未受信任。禁止在有凭据的宿主直接运行、import 或 pytest。** 即使是 Mock、lint 或以下 CLI，也只在无凭据独立隔离容器执行。绝不挂载真实 `.env`、个人 home、私有评估源、DSH home 或 Docker socket；不要将仓库根目录整棵挂载给候选。`.gitignore` 不是访问控制。

当前 `HarnessAdapter` 是官方 SDK 接口的**静态映射 + 无条件拒绝 Live 的基线**，不是“人类一批准即可使用”的完成版 Live 控制器。CLI `--live` 和 [Live 脚本](<scripts/run_live.sh>) 都返回 `SECURITY_BLOCKED` / exit 3；审批文档、环境变量或参数不会解锁。仍需实现外部独立授权、凭据边界、安全合并 Profile、外部进程 watchdog、真实预算/usage 集成，并重新人工审查。

## 依赖与复现

- Python **3.11.x**；[项目定义](<pyproject.toml>) 拒绝其他 minor，依赖与哈希见 [锁文件](<uv.lock>)，显式官方 PyPI。
- SDK `0.2.2rc2` + 同版本 runtime-bin；本机已有 npm DSH `0.2.1-rc.2` 是**另一发行版本**，不冒充 wheel Runtime。
- SDK 官方源码/元数据已静态核对，安装依赖不等于 H1 验证通过。
- 基础34测试通过；集成预检 **146 tests PASS、全量Ruff PASS、插件严格构建+真实官方注册表8/8 PASS**。完整wheel已在无源码挂载、`cwd=/work`、无源码PYTHONPATH的隔离容器内实际安装，四个CLI命令及包内20例资源验证通过。均为无凭据受限Podman/CPython3.11.15执行；最终冻结回归另见Runbook与原始manifest。
- 完整证据、版本与已知阻塞见 [Runbook](<docs/M0_RUNBOOK.md>)。由 security 成员提供的隔离操作步骤须先审核再执行。

以下命令**仅在已验证的无凭据隔离环境内**使用；并非宿主操作指令：

```sh
uv sync --frozen --python 3.11
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run python -m autoteacher_m0.cli inspect-runtime
uv run python -m autoteacher_m0.cli smoke --mock
uv run python -m autoteacher_m0.cli paired --mock
uv run python -m autoteacher_m0.cli report --experiment latest
```

`paired --mock` 生成20例×两策略的JSON/SQLite/比较报告（12开发+8公开模拟保留，非隐藏集）；`report`读取已有产物而不重跑。只打包公开fixture到wheel的package data。`--budget-usd`为未来获批Live控制器预留参数，不能解锁Live；Mock使用标记为synthetic的固定价目与预算守卫，API账单为零但synthetic费用单列。

离线测试与 `smoke --mock` 的 PASS 只证明项目 Mock/包装逻辑。**不代表 E1 SDK smoke、E2模型真实工具调用、E3 DSH恢复、Live配对或完整E5 PASS。** 插件原生schema不支持非空字符串：空白ID由项目语义校验拒绝，不能冒称原生schema验收通过。插件测试针对DSH0.2.1-rc.2 ABI，尚未在SDK-wheel0.2.2rc2 Runtime装载验证。镜像型candidate runner仍受无镜像/registry权限阻塞；实际OS证据来自独立本地rootfs容器。

## 公共接口

[项目契约](<src/autoteacher_m0/contracts.py>) ABI `m0-runtime-v1`：`RunRequest`、`RunRecord`、同步 `AgentRuntime.run/resume`、`RuntimeFailure.code`、`ErrorCode`。业务不暴露 SDK 对象；[Adapter](<src/autoteacher_m0/runtime/dsh_adapter.py>) 是唯一 SDK 导入位置。[MockRuntime](<src/autoteacher_m0/runtime/mock_adapter.py>) 独立 home 中的 JSONL 仅模拟持久化，不证明真实 DSH 或 OS 安全隔离。

[ArtifactStore](<src/autoteacher_m0/storage/artifacts.py>) 提供 JSON 保存/读取及 `sanitize`；[RunStore](<src/autoteacher_m0/storage/schema.py>) 提供 SQLite 索引。输出 usage/cost 缺失保留 `None`；只有显式标记的 Mock 成本为零。已知密钥形状/假哨兵会脱敏，但未知秘密不能靠正则完整检测，必须在执行边界排除真实凭据。

[路由记录](<docs/ROUTE_DECISION.md>) 保持默认官方 `deepseek-official / deepseek-flash`，没有自动 fallback、自动批准或真实型号版本验证。配置示例不授予权限。隐藏评估标签须位于仓库外，并仅授予独立可信评分器；候选不可读取评分器和预算/晋升控制策略。
