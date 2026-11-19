# M0 G4-F1 Secret Scanner Closeout Report

- **任务**：G4-F1 Secret Scanner Closeout（收紧测试哨兵规则、补齐漏报负例、复核 G4 最新提交）。
- **基线**：`bb2e9142a4e96e2b8fbe65bb99f1b4c045260251`（父提交）；F1 开始时工作区 clean。
- **约束**：0 真实 Key、0 模型调用、0 外网、0 Live/Provider 调用；未执行 `podman pull`；全部扫描与测试使用本机 Python `-B`、标准库，不读取环境变量中的真实密钥。
- **结论**：**PASS_FOR_G4F_F1_SCOPE**。全历史/工作树扫描 0 findings；未发现真实密钥泄漏；未把真实格式误当哨兵；`--self-test` PASS；临时负例仓库 exit 1；临时干净仓库 exit 0。**未 push**。

> 本文件与 scanner/tests 同一提交归档。提交 SHA 见 Lead 的 F1 收口报告或 `git log -1`；父提交固定为 `bb2e914`。

## 1. 规则审计与变更

### 1.1 哨兵判断（核心修复）

原实现 `_is_env_test_sentinel()` 只判断值是否以白名单前缀开头，导致 `SENTINEL<高熵>`、`SENTINELsk-...`、`TEST_ONLY_<base64>` 都可能被整体排除。现改为**整值语法**：

1. 先做值装饰剥离：去首尾引号/反引号、截断非 ASCII 散文、去尾部 `\n`/`\r`/`\t` 转义、去尾部标点（`) . , ; : ! ?`）。该步骤只用于分类与掩码，不会把真实 token 变成哨兵。
2. 值必须以前缀开头；前缀大小写不敏感，`-` 与 `_` 归一化。
3. 前缀之后只允许分隔符（`_`、`-`、`.`、`:`）与以下 token：
   - 已登记的哨兵词（如 `SENTINEL`、`TEST`、`ONLY`、`NEVER`、`VALID`、`SECRET`、`VALUE`、`SELFTEST`、`FAKE`、`PLACEHOLDER`、`NOT_REAL` 等，共 81 个）；
   - 纯数字；
   - 单字符重复串（如 `xxxx`、`0000`）。
4. 任何其它 tail token（随机串、`sk`、base64/hex、`deadbeef`、`abc123` 等）都不再被排除。

合法前缀共 14 个：`sentinel`、`test_only`、`test-only`、`testonly`、`fake`、`placeholder`、`example`、`not_a_real`、`not-a-real`、`notareal`、`invalid`、`dummy`、`mock`、`sample`。

**关键负例（必须命中）**：

| 形态 | 结果 |
|---|---|
| `SENTINEL` + 64 位 hex | 命中 `env-key-assignment` |
| `SENTINEL` + `sk-` token | 命中（env 与 openai 检测器均命中） |
| `TEST_ONLY_` + 64 位 hex | 命中 `env-key-assignment` |
| `TEST_ONLY_` + base64 | 命中 `env-key-assignment` |
| `sentinel_abc123`、`SENTINEL_` + 60 位数字 | 命中 `env-key-assignment` |
| `ZzSENTINEL` + 随机尾串（前缀不在开头） | 命中 `env-key-assignment` |

**合法哨兵（必须排除）**：`SENTINEL`、`sentinel`、`SeNtInEl`、`SENTINEL)`、``SENTINEL` ``、源码转义 `SENTINEL\n`、`TEST_ONLY_NEVER_VALID_SECRET_SENTINEL`、`sentinel_fake_value`、每个前缀 + `_SELFTEST_VALUE`。以上均通过。

### 1.2 赋值检测范围（`ENV_RE` / `GENERIC_ENV_RE`）

| 项目 | 变更 |
|---|---|
| `KNOWN_ENV_NAMES` | 3 → 23：新增 `AWS_SECRET_ACCESS_KEY`/`AWS_ACCESS_KEY_ID`/`AWS_SESSION_TOKEN`、`AZURE_OPENAI_API_KEY`/`AZURE_CLIENT_SECRET`/`AZURE_STORAGE_KEY`、`GCP_API_KEY`/`GOOGLE_API_KEY`/`GCP_SERVICE_ACCOUNT_KEY`、`HF_TOKEN`/`HUGGINGFACE_TOKEN`、`GITLAB_TOKEN`、`NPM_TOKEN`、`SLACK_BOT_TOKEN`/`SLACK_USER_TOKEN`/`SLACK_WEBHOOK_URL`、`GITHUB_TOKEN`/`GH_TOKEN`、`OPENCODE_API_KEY`、`DATABASE_URL` |
| `ENV_RE` | 已知名称大小写不敏感；值可带 `"`/`'`/反引号；值在反引号、引号、空白、`#` 处截断；至少 6 字符；清理尾部标点/散文 |
| `GENERIC_ENV_RE` | 大小写不敏感；支持多段名称前缀（`MY_SERVICE_TOKEN`）、JSON 引号 key（`"api_key": ...`）、YAML/`.env` 的 `:`/`=`；值至少 16 字符进入校验 |
| 值校验 | 新增 `_looks_like_secret_value()`：≥20 字符、token 字符集、字母+数字，或 ≥32 字符且字符多样性 ≥8；短类型注解（`TOKEN: string`）与代码表达式不报 |
| 哨兵例外 | 只作用于赋值值；不再作用于 `sk-`/AWS/GCP/Slack/GitHub/JWT/PEM/Bearer/DB URL 等原始检测器 |

### 1.3 新增/增强检测器

| 检测器 | Kind | 说明 |
|---|---|---|
| `SLACK_WEBHOOK_RE` | `slack-webhook` | `https://hooks.slack.com/services/...` |
| `GITLAB_RE` | `gitlab-token` | `glpat-` + 20+ |
| `NPM_RE` | `npm-token` | `npm_` + 30+ |
| `HF_RE` | `huggingface-token` | `hf_` + 30+ |
| `AZURE_ACCOUNT_KEY_RE` | `azure-account-key` | `AccountKey=` + 40+ base64 |
| `BASIC_RE` | `basic-auth` | `(Proxy-)Authorization: Basic`，16+，且 base64 解码后必须含 `user:pass` 的 `:` |
| `URL_QUERY_RE` | `url-query-secret` | `http(s)://...?key=`/`token=`/`api_key=` 等，16+ 且值形态像 secret |
| `CONN_*` | `connection-string-password` | 同一行有 `Server`/`Data Source`/`Host` 等上下文时，检测口令字段（6+） |
| `DB_URL_RE` | `db-url-password` | 新增 `mariadb`/`rediss`/`amqps`/`mssql`/`sqlserver`/`oracle`/`cockroachdb`/`clickhouse` |
| `JWE_RE` | `jwe` | `eyJ` 五段；JWT 三段检测增加 lookahead，避免把 JWE 前三段误报为 JWT |
| `PEM_RE` | `private-key-header` | `RSA`/`EC`/`DSA`/`OPENSSH`/`ENCRYPTED`/`PGP ... BLOCK`/无标签 |

`sk-`、AWS、GCP、Slack、GitHub、JWT、Bearer、DB URL、PEM 原有检测均保留；PEM 正则仍用字符串拼接避免扫描器自报。

## 2. 合成负例表

所有值为测试内运行时生成或拼接的**明显假值**，不写入工作区，不含真实 Secret。共 43 个正例（standalone/pytest）与 48 个 self-test 正例。

| 类别 | 合成负例形态（示例） | 预期 kind | 结果 |
|---|---|---|---|
| OpenAI | `sk-` + 20+ 合成字符 | `openai-key` | PASS |
| AWS | `AKIA` + 16 大写字母 | `aws-access-key` | PASS |
| GCP | `AIza` + 35 字符 | `gcp-api-key` | PASS |
| Slack token/webhook | `xoxb-` + 20；`hooks.slack.com/services/...` | `slack-token` / `slack-webhook` | PASS |
| GitHub/GitLab/npm/HF | `ghp_`/`glpat-`/`npm_`/`hf_` + 合成尾串 | 对应 raw kind | PASS |
| Azure 连接串 | `AccountKey=` + 40+ 合成 base64 | `azure-account-key` | PASS |
| JWT/JWE | `eyJ` 三段 / 五段 | `jwt` / `jwe` | PASS |
| Bearer/Basic | `Authorization: Bearer` + 40；Basic 为运行时 `base64(user:合成口令)` | `bearer-token` / `basic-auth` | PASS |
| 已知 env 名 | `AWS_SECRET_ACCESS_KEY=`/`AZURE_CLIENT_SECRET=`/`GCP_API_KEY=`/`HF_TOKEN=`/`GITLAB_TOKEN=`/`NPM_TOKEN=`/`SLACK_BOT_TOKEN=`/`DATABASE_PASSWORD=` + 64-hex | `env-key-assignment` | PASS |
| 任意多段 env 名 | `MY_SERVICE_TOKEN=` + 64-hex | `env-key-assignment` | PASS |
| `.env`/YAML/JSON | `HF_TOKEN=...`；`password: "<64-hex>"`；`"api_key": "<base64>"`；`client_secret: <base64>` | `env-key-assignment` | PASS |
| 长 hex/base64 | `SIGNING_KEY=` + 64-hex；`CLIENT_SECRET=` + base64 | `env-key-assignment` | PASS |
| DB URL | PostgreSQL/MySQL/MongoDB 连接串的合成口令 | `db-url-password` | PASS |
| 连接串 | `Server=...;Password=<64-hex>;` | `connection-string-password` | PASS |
| URL query | `https://203.0.113.10/...?token=<64-hex>`、`?api_key=...` | `url-query-secret` | PASS |
| PEM 变体 | PEM 头：无标签/RSA/EC/DSA/OPENSSH/ENCRYPTED/PGP BLOCK | `private-key-header` | PASS |
| 大小写/引号/尾标点 | 小写 env 名 + 64-hex + `;`；`DEEPSEEK_API_KEY = "<64-hex>"` | `env-key-assignment` | PASS |
| 哨兵 look-alike | `SENTINEL`+hex、`SENTINEL`+`sk-`、`TEST_ONLY_`+hex/base64 | `env-key-assignment` | PASS |
| 合法哨兵 | `SENTINEL`/`SENTINEL)`/``SENTINEL` ``/`SENTINEL\n`/大小写变体/`TEST_ONLY_NEVER_VALID_SECRET_SENTINEL` | 无 finding | PASS |
| `sk-FAKE` | `sk-FAKE-` + 32 字符；env 形式 | 无 finding | PASS |
| 短非 secret | `TOKEN = "session-token"`、`Authorization: Bearer abc...`、非法 Basic base64 | 无 finding | PASS |

## 3. 测试与验证

执行命令（`.venv/bin/python` = Python 3.11.15；同时用 host `python3` 3.12.3 复验）：

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/security/scan_git_secrets.py --self-test
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/security/scan_git_secrets.py
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/security/scan_git_secrets.py --no-history
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B scripts/security/scan_git_secrets.py --json
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -B tests/security/test_scan_git_secrets.py
```

| 验证 | 结果 |
|---|---|
| `--self-test` | **PASS**，exit 0 |
| 全历史 + 工作树 + commit message 扫描（基线提交） | **0 findings**，exit 0；441 tracked files / 689 blobs / 150 commits |
| `--no-history` | 0 findings，exit 0 |
| 独立测试 `tests/security/test_scan_git_secrets.py` | **7/7 PASS**（pytest 兼容，也可直接运行） |
| /tmp 正例 git 仓库 | scanner **exit 1**；stdout/stderr 均不含完整秘密值；掩码含 `…(len N)` |
| /tmp 干净 git 仓库（仅哨兵/占位符） | **exit 0**，`SECRET SCAN OK` |

> 本机未安装 pytest；测试文件同时提供 `main()` 运行器，已用 Python 3.11 `-B` 直接执行 7/7 通过，不依赖第三方包。

## 4. 最新 G4 提交影响复核

- 范围：`a2c8424..bb2e914`。该区间只有 **`bb2e914`** 一个提交（父 `a2c8424`），改动仅 `scripts/security/scan_git_secrets.py`。
- 复核对象：`a2c8424` 与 `bb2e914` 两个端点的**全部 tree blob**（每端点 441 个 path），逐行跑全部检测器；来源 `artifacts/g4f/f1/latest-commits-audit.json`。
- 结果：**0 findings**，0 个 `would_be_reported`/risk；`scanner_change_only_in_range=true`。
- 赋值形态记录：87 条（两提交合计）；分类：`explicit_test_sentinel` 18、`placeholder_marker` 21、`not_secret_shaped` 48、`would_be_reported` 0。
- G4 范围（`docs/`、`tests/`、`scripts/`）：85 条记录；18 条显式哨兵、21 条占位符、46 条非 secret 形态代码表达式；0 条真实格式被排除。

被排除值全部可解释：

| 被排除值（掩码） | 位置示例 | 分类 | 说明 |
|---|---|---|---|
| `DEEPSEEK_API_KEY=SENTINEL`（len 8） | `docs/M0_G4_FINDINGS_AND_DISPOSITION.md:149`、`docs/REVIEW_G4_INDEPENDENT.md:92`、`tests/integration/g4_d/test_d07_live_entrances.py:45/57` | explicit test sentinel | 符号常量 `SENTINEL`，非字面凭据 |
| `DEEPSEEK_API_KEY=SENTINEL`（len 8） | `scripts/security/scan_git_secrets.py`（历史 blob） | explicit test sentinel | self-test 源码中的字符串（`\n` 转义） |
| `MY_SERVICE_TOKEN=TEST_O…(len 37)` | `scripts/security/scan_git_secrets.py`（历史 blob） | explicit test sentinel | `TEST_ONLY_NEVER_VALID_SECRET_SENTINEL`，self-test 字符串 |
| `OPENCODE_API_KEY=<injec…(len 22)` | `docs/OPENCODE_GO_ACCESS.md:256` | placeholder | `<injected-by-launcher>` |
| `DEEPSEEK_API_KEY=sk-livefake...`（len 21） | `tests/unit/security/test_credential_boundary.py:59` | placeholder | `sk-livefake...`，SECURITY.md 明确允许的测试值 |
| `OPENCODE_API_KEY={FAKE_…(len 19)` | `tests/unit/security/test_credential_boundary.py:57` | placeholder | f-string/占位符 |
| `API_KEY=sk-INV…(len 16)` 等 | `tests/unit/runtime/test_structured_output.py` | placeholder | `sk-INVENTED_ONLY` / `sk-FAKE_SECRET_ONLY` |
| `CREDENTIAL={probe…` | `tests/integration/g4_d/test_d03_d04_sentinel.py` | placeholder | 符号引用 |
| `TOKEN=...`/`SECRET=...` | 若干 tests/scripts | not secret shaped | 代码表达式/类名，非密钥值 |

**全历史复核**：150 commits、689 blobs、441 files、commit messages 全扫，**0 findings**；21 条被排除记录全部为哨兵/占位符，`risk_count=0`。未发现非测试哨兵的真实泄露，因此未触发 STOP。

## 5. 误报/漏报修复摘要

- **修复误报**：`DEEPSEEK_API_KEY=SENTINEL` 等符号常量继续被排除，且不再依赖“前缀开头即放行”。
- **修复漏报**：新增 AWS/Azure/GCP/HF/GitLab/npm/Slack 等 env 名；YAML/JSON/.env 配置键；DB URL/连接串口令；Basic；URL query；JWE；PEM 变体；Slack webhook；Azure AccountKey；长 hex/base64 赋值。
- **强化 fail-closed**：哨兵前缀 + 高熵 tail、前缀 + `sk-`、`TEST_ONLY_` + base64/hex 均命中；未知哨兵词不再静默排除。
- **避免自报**：所有 PEM/raw token 正则与自测字符串均用拼接/运行时生成；scanner 扫描自身源码仍 0 findings。

## 6. 残余风险与范围限定

1. 这是启发式防线，不是密钥泄漏保证；不能替代人工复核、Provider 吊销、GitHub Secret Scanning。
2. 通用赋值检测要求值 ≥20 字符（正则捕获 16+）；短于 20 的未知名称密钥可能漏报，已知 provider 名称阈值为 6+。
3. 哨兵 tail 词表是封闭集合；未知但合法的哨兵词会被报告（fail closed），需在后续维护中显式补充。
4. `_is_placeholder()` 仍保留既有子串/前缀启发式（`fake`、`example`、`sample`、`none`、`null`、`xxxx`、`abc` 开头等），极端构造的真实 token 可能被误排除；本轮历史审计未发现这种情况。
5. 未增加“无上下文裸高熵值”检测器：仓库历史含 635 个不同 32+ hex（commit/artifact 指纹），裸熵检测会产生数千误报；长 hex/base64 仅在赋值/URL/Bearer/Basic/DB 等上下文检测。
6. Basic 需合法 base64 且解码含 `:`、长度 ≥16；URL query 仅 http(s) 且值 ≥16；连接串需同一行有 `Server=`/`Data Source=` 等上下文。
7. 本轮未验证真实 Provider/billing/Live；LiveGate 状态不变，仍 BLOCKED。工作区中其他并行任务（F3 等）的未提交改动不属于 F1，未 stage/提交。

## 7. 证据路径

均位于 gitignored 的 `artifacts/g4f/f1/`：

| 文件 | 内容 |
|---|---|
| `selftest.txt` | `--self-test` PASS 输出 |
| `full-history-scan.json` | 全历史扫描 JSON（findings 为空，含 stats） |
| `worktree-scan.txt` | `--no-history` 结果 |
| `security-tests.txt` | 7 个独立测试的 PASS 日志 |
| `history-audit.json` | 全历史 findings、150 commits、被排除值分类（commit/path/pattern/masked） |
| `latest-commits-audit.json` | `a2c8424..bb2e914` 两端点全 blob 复核、哨兵分类、0 findings |
| `git-range.txt` | 最新区间 commit/diff stat |

所有证据只含掩码值（前 6 字符 + 长度），不含完整 Secret。

## 8. 提交与结论

- 提交信息：`fix: G4-F1 tighten secret scanner sentinel rules and add missed-detection negatives (no-key)`。
- 父提交：`bb2e9142a4e96e2b8fbe65bb99f1b4c045260251`。
- 仅暂存/提交：`scripts/security/scan_git_secrets.py`、`tests/security/**`、`docs/M0_G4F_F1_REPORT.md`。
- 未 push、未 amend、未 stage 他人改动。
- **F1 范围结论：PASS**；无真实 Key/模型/外网/Live；STOP，等待 Lead 审计。
