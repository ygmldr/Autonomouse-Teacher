# M1-B Judge Certification Fixtures（可信判题认证语料）

本目录是 M1-B「可信判题边界」（B-PR1 / B1-01..B1-06、B-Q1）的**合成判题认证语料**。它只提供数据：参考解、隐藏期望用例、错误提交负例、信任边界 sentinel 与攻击模板；**不包含任何判题实现、scorer、session 逻辑或 Worker 代码**。

- Evidence class：`MOCK` / `DETERMINISTIC`（仅离线、可复现的合成证据；不是真实恶意代码评测，也不代表真实用户代码已安全）。
- 许可：`CC0-1.0`。
- 安全基线：无网络、无真实 Key/凭据、无真实个人数据、无真实外部攻击载荷；所有 sentinel 值均为自编合成字符串。

## 用途与边界

1. **用途**：为「可信 Judge Supervisor + 不可信 Worker」的隔离认证提供固定语料——
   - 参考解必须全部 PASS（判题正确性基线，B1-05）；
   - 错误/异常/超时/缺函数提交必须被稳定分类为 WA / RE / TLE（B1-05）；
   - hidden expected、sentinel、结果文件与 Worker 协议边界可用于验证 expected 不可达、verdict 不可伪造、宿主文件不可读、无网络、资源受控（B1-02/B1-03/B1-04、B-Q1）。
2. **不是**教学 mastery 证据：本语料**不参与** Learner Mastery 计算、诊断或教学决策；它不是教学 fixture，也不得作为教学评估输出。
3. **Teacher 不可见**：本目录属于 JUDGE 信任边界内部资产。Teacher 可见 API / DomainAdapter / 教学 fixture（`fixtures/m1_teacher/domains/**`、`fixtures/m1_teacher/README.md`）不得读取、引用、嵌入或转发本目录的任何内容；隐藏 expected 值、sentinel 值、攻击模板与负例仅供判题认证测试使用。
4. **不改动域 fixture 格式**：本目录与 `m1a.v0` 教学域 fixture 相互独立；新增本目录不改变既有 domain fixture 的 schema 或语义。

## 目录结构

```
fixtures/m1_teacher/judge/
├── README.md
├── certification/
│   ├── cases.json       # 14 个参考题：reference_solution + 全部 hidden tests
│   └── negatives.json   # 错误/异常/超时/缺函数/边界正确解负例
└── sentinels/
    └── sentinels.json   # 合成 sentinel 值 + 信任边界攻击模板
```

## 来源与改编（provenance）

- 题目元数据、`reference_solution` 与 hidden tests：来自 `m1_offline` 的 CF 合成 fixtures（`fixtures/m1/cf/problems/*.json` 与 `fixtures/m1/cf/hidden/*.json`，均为 `synthetic: true`、`license: CC0-1.0`）。本目录**逐字复制**参考解与对应 hidden tests（`args`/`expected`/`kind`），以保证判题认证语料与既有离线实现一致。
- `boundary_note`、`negatives.json` 与 `sentinels.json`：由 M1-B fixtures 工作线自编（synthetic），不含第三方版权内容。
- 语料为 14 题、112 条隐藏用例；顺序与字段均为稳定排序/固定值，无时间戳、无绝对路径、无随机种子。

## 文件格式（严格 schema，禁止未知字段）

### `certification/cases.json`

```json
{
  "schema_version": "m1b.judge.certification.v0",
  "evidence_class": "MOCK",
  "synthetic": true,
  "license": "CC0-1.0",
  "provenance": "copied_verbatim_from_m1_offline_cc0_synthetic_fixtures",
  "cases": [
    {
      "case_id": "cf_array_max_subarray",
      "title": "最大子数组和",
      "function_name": "max_subarray_sum",
      "timeout_s": 2.0,
      "expected_classification": "PASS",
      "boundary_note": "边界：……",
      "reference_solution": "def max_subarray_sum(nums): …",
      "tests": [
        {"args": [[-2, 1, -3, 4]], "expected": 4, "kind": "normal"}
      ]
    }
  ]
}
```

- 恰好 14 个 `case_id`（对应 `cf_*` 14 题），唯一且稳定排序；`function_name` 为 Python 标识符。
- `reference_solution` 是可信参考实现，`expected_classification` 固定为 `PASS`。
- `tests` 为对应 hidden fixture 的全部用例（不做抽样），`kind ∈ {normal, edge, large}`，每题为 7–10 条且三种 kind 均出现；`args` 必须与参考解形参数量一致。
- `boundary_note` 描述该题的空数组/单元素/重复元素/全负数/不可达/无解等边界语义。

### `certification/negatives.json`

```json
{
  "schema_version": "m1b.judge.certification.negatives.v0",
  "evidence_class": "MOCK",
  "synthetic": true,
  "license": "CC0-1.0",
  "negatives": [
    {
      "negative_id": "neg.wa.constant_return",
      "case_id": "cf_dp_climb_stairs",
      "title": "常量返回错误解",
      "description": "……",
      "failure_mode": "constant_return",
      "code": "def climb_stairs(n):\n    return 0\n",
      "expected_classification": "WA"
    }
  ]
}
```

`failure_mode` 与 `expected_classification` 的固定映射：

| failure_mode | 语义 | expected_classification |
| --- | --- | --- |
| `constant_return` | 常量返回忽略输入 | `WA` |
| `off_by_one` | 边界/差一错误 | `WA` |
| `edge_correct` | 边界题正确解（对照） | `PASS` |
| `syntax_error` | Python 语法错误 | `RE` |
| `runtime_exception` | 运行期异常 | `RE` |
| `missing_function` | 缺少目标函数 | `RE` |
| `infinite_loop` | 死循环 | `TLE` |

`infinite_loop` 负例**绝不被数据完整性测试执行**（会挂起测试进程）；它只作为判题侧超时认证的语料。其余负例由完整性测试在本地安全执行，验证其真实分类与声明一致。

### `sentinels/sentinels.json`

```json
{
  "schema_version": "m1b.judge.sentinels.v0",
  "evidence_class": "MOCK",
  "synthetic": true,
  "license": "CC0-1.0",
  "purpose": "……",
  "sentinel_expected": "SENTINEL_DO_NOT_LEAK_<hex>",
  "sentinel_secret_token": "SENTINEL_SECRET_TOKEN_DO_NOT_LEAK_<hex>",
  "host_sentinel_relative_path": "host_secret/DO_NOT_READ.txt",
  "host_sentinel_content": "SENTINEL_HOST_FILE_DO_NOT_LEAK_<hex>",
  "attack_templates": [
    {
      "attack_id": "attack.stack_frame_probe",
      "attack_family": "stack_frame_probe",
      "description": "……",
      "code": "# SYNTHETIC_TEST_ONLY\n…",
      "expected_blocked": true,
      "expected_classification": "WA",
      "synthetic_test_only": true
    }
  ]
}
```

- 三个 sentinel 值均为合成占位值（`SENTINEL_*` + 固定十六进制后缀，不含任何真实秘密），彼此唯一。
- `host_sentinel_relative_path` 为**相对路径**；宿主 sentinel 文件在 OS 隔离测试时由测试外壳在**宿主机临时目录**创建，**绝不写入仓库**。
- `attack_templates` 覆盖 10 类信任边界探测：`stack_frame_probe`、`argv_result_forgery`、`host_sentinel_read`、`socket_connect`、`fork_subprocess`、`infinite_loop`、`forged_protocol_output`、`write_runner_source`、`exit_code_tamper`、`exception_override`。
- 每个模板都必须标记 `SYNTHETIC_TEST_ONLY`、`synthetic_test_only: true`、`expected_blocked: true`，且 `expected_classification ∈ {WA, RE, TLE}`（**绝不允许 PASS**）。
- 模板代码只做本地、无害的边界探测（如读取不存在文件、连接保留的 `.invalid` 合成主机名并捕获失败），**不包含真实外联、真实凭据、个人信息或真实攻击载荷**；仅可在隔离 Worker/测试容器中执行。

## 使用与安全规则

1. 判题认证测试运行时，隐藏 expected、sentinel 值与负例代码**不得写入日志、Teacher 消息、导出 JSON 或诊断文本**；测试只比较存在性/布尔判定，不打印具体内容。
2. 攻击模板与负例只能在 OS 隔离环境（非 root 独立 principal、只读最小文件系统、`--network none`、私有临时空间、CPU/内存/pids/输出长度/时限）内执行；默认主机禁止直接运行。
3. 本目录不得被 `m1_teacher` DomainAdapter 的 fixture allow-list、教学 CLI、Teacher Core 或任何教师可见导出路径读取。
4. 若将来需要更新语料：保持 `case_id` 与来源 hidden expected 逐字一致，重新运行数据完整性测试（`tests/m1_teacher/test_judge_fixture_integrity.py`）后再提交。
