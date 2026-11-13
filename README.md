# Autonomous Teacher — M0

依据 [v0.4 任务书](<docs/Autonomous_Teacher_M0_v04.md>) 的离线优先技术验证设施，不是教学产品。当前总体 **DECISION PENDING**；没有真实模型调用，也没有人类安全/路由批准。

## 安全边界

**所有本仓库生成代码仍未受信任。禁止在有凭据的宿主直接运行、import 或 pytest。** 即使是 Mock、lint 或以下 CLI，也只在无凭据独立隔离容器执行。绝不挂载真实 `.env`、个人 home、私有评估源、DSH home 或 Docker socket；不要将仓库根目录整棵挂载给候选。`.gitignore` 不是访问控制。

当前 `HarnessAdapter` 是官方 SDK 接口的**静态映射 + 无条件拒绝 Live 的基线**，不是“人类一批准即可使用”的完成版 Live 控制器。CLI `--live` 和 [Live 脚本](<scripts/run_live.sh>) 都返回 `SECURITY_BLOCKED` / exit 3；审批文档、环境变量或参数不会解锁。仍需实现外部独立授权、凭据边界、安全合并 Profile、外部进程 watchdog、真实预算/usage 集成，并重新人工审查。

## 依赖与复现

- Python **3.11.x**；[项目定义](<pyproject.toml>) 拒绝其他 minor，依赖与哈希见 [锁文件](<uv.lock>)，显式官方 PyPI。
- SDK `0.2.2rc2` + 同版本 runtime-bin；本机已有 npm DSH `0.2.1-rc.2` 是**另一发行版本**，不冒充 wheel Runtime。
- SDK 官方源码/元数据已静态核对，安装依赖不等于 H1 验证通过。
- 基础隔离回归 **34 tests PASS**、scoped Ruff PASS、Mock 3 smoke/Live拒绝断言 PASS、foundation wheel 构建 PASS。都仅在无凭据受限 Podman/CPython3.11.15 内执行。
- 完整证据、版本与已知阻塞见 [Runbook](<docs/M0_RUNBOOK.md>)。由 security 成员提供的隔离操作步骤须先审核再执行。

以下命令**仅在已验证的无凭据隔离环境内**使用；并非宿主操作指令：

```sh
uv sync --frozen --python 3.11
uv run ruff check .
uv run pytest tests/unit -q
uv run pytest tests/integration -q
uv run python -m autoteacher_m0.cli inspect-runtime
uv run python -m autoteacher_m0.cli smoke --mock
# paired/report 在后续依赖集成任务接入；本阶段显式 BLOCKED
uv run python -m autoteacher_m0.cli paired --mock
uv run python -m autoteacher_m0.cli report --experiment latest
```

离线测试与 `smoke --mock` 的 PASS 只证明项目 Mock/包装逻辑。**不代表 E1 SDK smoke、E2 真工具、E3 DSH 恢复、Live 配对或完整 E5 PASS。** 实际运行结果另行记录，不把命令存在当成测试通过。

## 公共接口

[项目契约](<src/autoteacher_m0/contracts.py>) ABI `m0-runtime-v1`：`RunRequest`、`RunRecord`、同步 `AgentRuntime.run/resume`、`RuntimeFailure.code`、`ErrorCode`。业务不暴露 SDK 对象；[Adapter](<src/autoteacher_m0/runtime/dsh_adapter.py>) 是唯一 SDK 导入位置。[MockRuntime](<src/autoteacher_m0/runtime/mock_adapter.py>) 独立 home 中的 JSONL 仅模拟持久化，不证明真实 DSH 或 OS 安全隔离。

[ArtifactStore](<src/autoteacher_m0/storage/artifacts.py>) 提供 JSON 保存/读取及 `sanitize`；[RunStore](<src/autoteacher_m0/storage/schema.py>) 提供 SQLite 索引。输出 usage/cost 缺失保留 `None`；只有显式标记的 Mock 成本为零。已知密钥形状/假哨兵会脱敏，但未知秘密不能靠正则完整检测，必须在执行边界排除真实凭据。

[路由记录](<docs/ROUTE_DECISION.md>) 保持默认官方 `deepseek-official / deepseek-flash`，没有自动 fallback、自动批准或真实型号版本验证。配置示例不授予权限。隐藏评估标签须位于仓库外，并仅授予独立可信评分器；候选不可读取评分器和预算/晋升控制策略。
