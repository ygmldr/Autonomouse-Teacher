# A-07 — No-Key / LiveGate 恒 BLOCKED 负例证据（G4-H0）

- 生成时间（UTC）：2026-11-19T18:09:38Z
- 工作树：`/root/Autonomous Teacher/worktrees/m0-g4h0-fix`，基线 `3e7afee`（证据在修复提交前于工作树生成）
- 探针：`scripts/g4h0/no_key_probes.py`（纯本地负例；无真实 Key、无 Provider/HTTP/付费调用）
- 原始证据：`docs/g4h0/evidence/a07_no_key_probes.json`、`docs/g4h0/evidence/a07_no_key_probes.log`
- 结果：**22/22 PASS**（`{"failed": 0, "passed": 22, "status": "PASS", "total": 22}`）

运行命令：

```bash
cd "/root/Autonomous Teacher/worktrees/m0-g4h0-fix"
PYTHONPATH=src "/root/Autonomous Teacher/.venv/bin/python" \
  scripts/g4h0/no_key_probes.py --output docs/g4h0/evidence/a07_no_key_probes.json
# exit 0；末行：A-07 NEGATIVES OK: LiveGate BLOCKED, 0 key, 0 network/provider call
```

## 1. 固定状态常量（本轮未改）

```text
LiveGate         = BLOCKED      （inspect 恒 BLOCKED / require_live 恒抛 SECURITY_BLOCKED）
G4-H             = NOT_AUTHORIZED
G5               = BLOCKED
G6               = NOT_RUN
M0               = DECISION_PENDING
E5_PRELIVE_FULL  = BLOCKED_PENDING_HUMAN_DEPLOYMENT
```

`gates.py`、`scripts/run_live.sh`、`dsh_adapter.py`、`cli.py` 与基线 `3e7afee` **逐字节相同**
（`git diff --name-only 3e7afee -- <4 files>` 输出为空，check `frozen_live_files_unmodified` PASS）。

## 2. 逐项负例与实测结果

| # | Check | 实测证据 |
|---|---|---|
| 1 | `live_gate_inspect_always_blocked` | 即使 `live_requested=True`、actual==reviewed baseline、`actual_tools=("skill_lookup",)`、`session_log_disabled=True` 全部满足，仍 `status=BLOCKED`、`external_boundary_deployed=false`，首个 reason 为 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` |
| 2 | `live_gate_require_live_always_raises` | `require_live(**best_evidence)` 抛 `SecurityBlocked`，`code=SECURITY_BLOCKED`，reason 含 `EXTERNAL_HUMAN_AUTHORIZATION_BOUNDARY_NOT_DEPLOYED` |
| 3 | `live_gate_no_approval_entrypoint_and_never_opens` | `LiveGate` 无 `authorize/approve/open/unlock` 属性；2×2×4×2=32 种输入组合的 `inspect()` 全部返回 `BLOCKED` |
| 4 | `run_live_script_exit_3_blocked` | `/bin/sh scripts/run_live.sh`（env 含假 `DEEPSEEK_API_KEY`、`AT_M0_LIVE_APPROVED=1`、`AT_M0_ALLOW_LIVE=1`）→ exit **3**，stderr 含 `BLOCKED`，stdout 为空；假 Key 值不出现在输出 |
| 5 | `cli_live_rejected_exit_3` | `python -m autoteacher_m0.cli smoke --live`（env 含假 `DEEPSEEK_API_KEY`/`OPENCODE_API_KEY`、`AT_M0_APPROVAL_FILE` 指向自签 Markdown）→ exit **3**，stdout JSON `{"status":"BLOCKED","error_code":"SECURITY_BLOCKED",...}` |
| 6 | `cli_live_fake_key_never_printed` | 两个假 Key sentinel 均未出现在 CLI stdout/stderr |
| 7 | `no_network_syscalls_run_live` | `strace -f -e trace=network` 运行 `run_live.sh`：无 `AF_INET/AF_INET6/connect(` 行 |
| 8 | `no_network_syscalls_cli_smoke_live` | 同上对 CLI `smoke --live`：无网络系统调用 |
| 9 | `adapter_four_live_entrypoints_blocked` | `HarnessAdapter._require_live_authorization` / `_new_harness` / `run` / `resume` 四入口均返回 `SECURITY_BLOCKED`（在 SDK import 之前） |
| 10 | `provider_sdk_never_imported` | 全部探针后 `"deepseek_harness" not in sys.modules`（未 import Provider SDK） |
| 11 | `probe_process_has_no_key_like_env` | 探针进程 env 中无 key-like 变量（API_KEY/TOKEN/SECRET/PASSWORD/CREDENTIAL/PRIVATE_KEY） |
| 12 | `no_dotenv_file_in_repo` | 仓库根无 `.env`（仅文档性 `.env.example`，且 src 不加载 dotenv） |
| 13 | `source_never_reads_key_like_env` | `src/autoteacher_m0/**/*.py` 中无任何读取 key-like env 的代码行 |
| 14 | `source_never_loads_dotenv` | `src/` 无 `import dotenv/from dotenv` |
| 15 | `only_known_test_hook_env_reads` | 唯一 env 读取为既有 `bridge/controller.py` 的 `G3B_TEST_MODE`/`G3B_CRASH_HOOK`/`G3B_TEST_DELAY_*` G4-F 测试钩子（非 key、非授权开关；本轮未新增） |
| 16 | `credential_boundary_scrubs_fake_key` | `scrub_candidate_env` 丢弃 2 个假 Key 项并报 2 条 violation；`redact_secrets` 输出中无假 Key 原文 |
| 17 | `frozen_live_files_unmodified` | 4 个 Live 入口/常量文件相对 `3e7afee` 零 diff |
| 18 | `static_live_entrypoint_audit_clean` | 既有 `assert_live_entrypoints_blocked(repo_root)` 返回 `()`（脚本硬停/Adapter/CLI 静态断言全部成立） |
| 19 | `new_src_has_no_network_or_provider_client` | 新增代码（`git diff 3e7afee` 的 added lines + untracked）中 `src/` 无 requests/httpx/aiohttp/urllib/http.client/socket connect/deepseek_harness |
| 20 | `new_code_has_no_credential_material` | 新增内容中无 `sk-`/AWS/GCP/GitHub/Slack/PEM/密钥赋值模式（0 findings） |
| 21 | `new_src_has_no_env_unlock_switch_or_dotenv` | 新增 `src/` 代码中无 `os.environ`/`os.getenv`/dotenv（无新的 env 解锁开关） |
| 22 | `no_ip_socket_attempt_in_process` | 进程内 socket guard 下执行 LiveGate/Adapter 负例，IP socket 连接尝试 = 0 |

## 3. 范围与残余

- 本证据只覆盖**本机、无 Key、无真实 Provider/HTTP** 的负例；不是 E5-PreLive Full，不是 G4-H/G5/Live 授权。
- `strace` 只对 CLI/run_live 两个 hard-stop 入口执行；未对真实容器/DSH 运行做网络跟踪（G4-H0 无 Key 范围不需要，也不做真实调用）。
- `--live` 的拒绝在 SDK import、目录创建、凭据/审批读取之前发生（CLI 代码顺序 + 负例）；真实人类授权边界、Key Broker、可信 Egress 仍 **NOT DEPLOYED**，属 HUMAN-REQUIRED。
- 本文件不构成任何批准；`LiveGate=BLOCKED` 与人类待决项不变。
