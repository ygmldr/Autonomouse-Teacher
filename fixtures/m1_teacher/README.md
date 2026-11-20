# M1A Teacher Fixtures — CF Binary Search Domain

本目录是 M1A 教师闭环使用的离线合成领域 fixture。它用一组固定 schema 的 JSON 文档描述一个「二分查找」教学领域：知识图谱、教学目标、评估题与教学内容，供契约加载器与 fixture 校验测试使用。全部内容为自编合成数据，不连接网络，可离线确定性复现。

## 目录结构

```
fixtures/m1_teacher/
├── README.md
└── domains/
    └── cf_binary_search/
        ├── knowledge_graph.json      # 8 节点 / 9 条有向边（DAG）
        ├── objectives.json           # 教学目标与成功标准
        ├── assessment_items.json     # 评估题（MCQ / CODE / SHORT_ANSWER）
        ├── teaching_content.json     # 8 个节点各自的讲解、分层提示与复习要点
        └── scoring/                  # 隐藏评分规格，仅评分器读取
            ├── item.bs.mcq.001.json
            ├── ...
            ├── item.bs.code.001.json
            ├── ...
            └── item.bs.short.001.json
```

## 通用约定

- 所有文件编码为 UTF-8（无 BOM）。
- 四个领域文档均包含 `schema_version` = `m1a.v0` 与 `domain_id` = `cf_binary_search`，用于关联到同一领域契约。
- `domain_version` 是领域级版本，只在 `knowledge_graph.json` 顶层声明一次（当前 `0.1.0`）；其余文档通过 `schema_version` + `domain_id` 关联该领域。适配器对其余文档使用严格白名单键集合（出现未知键即 fail-closed 拒绝）。
- 知识图谱恰好 8 个节点、9 条边，构成有向无环图（DAG）。
- 评估题不少于 12 道（当前 16 道：MCQ 8、CODE 5、SHORT_ANSWER 3），覆盖全部 8 个节点。
- 每道评估题恰好对应一份评分规格：`scoring/<item_id>.json`，且评分规格与题目一一对应，没有多余文件。

## 文件格式

### knowledge_graph.json

```json
{
  "schema_version": "m1a.v0",
  "domain_id": "cf_binary_search",
  "domain_version": "0.1.0",
  "nodes": [
    {
      "node_id": "cf.array.basics",
      "title": "数组基础与索引",
      "description": "……",
      "difficulty": 1,
      "assessment_mode": "DETERMINISTIC_JUDGE",
      "tags": ["array", "indexing"],
      "content_ref": "cf.array.basics"
    }
  ],
  "edges": [
    {
      "source_node_id": "cf.array.basics",
      "target_node_id": "cf.sort.sortedness",
      "kind": "HARD",
      "weight": 1.0
    }
  ]
}
```

- `difficulty` 为 1 到 5 的整数；`assessment_mode` 取值 `DETERMINISTIC_JUDGE` / `RULE_RUBRIC` / `HUMAN_REVIEW_REQUIRED`。
- `content_ref` 指向 `teaching_content.json` 中同名节点键。
- 边 `kind` 取值 `HARD` / `SOFT`；`weight` 为 0 到 1 之间的数值。

### objectives.json

```json
{
  "schema_version": "m1a.v0",
  "domain_id": "cf_binary_search",
  "objectives": [
    {
      "objective_id": "obj.cf.binary_search.mastery",
      "title": "掌握二分查找与边界处理",
      "description": "……",
      "target_node_ids": ["cf.search.binary"],
      "success_criteria": {
        "min_mastery": 0.7,
        "required_node_ids": ["cf.search.binary"],
        "max_error_rate": 0.3
      },
      "estimated_minutes": 120
    }
  ]
}
```

- `target_node_ids` 与 `required_node_ids` 中的节点必须存在于知识图谱；`min_mastery`、`max_error_rate` 均在 0 到 1 之间。

### assessment_items.json

```json
{
  "schema_version": "m1a.v0",
  "domain_id": "cf_binary_search",
  "items": [
    {
      "item_id": "item.bs.mcq.001",
      "node_ids": ["cf.array.basics"],
      "item_type": "MCQ",
      "difficulty": 1,
      "prompt": "……",
      "options": ["选项 A", "选项 B", "选项 C", "选项 D"],
      "max_score": 1.0,
      "deterministic": true,
      "scoring_spec_ref": "scoring/item.bs.mcq.001.json",
      "public": true
    }
  ]
}
```

- `item_type` 取值 `MCQ` / `CODE` / `SHORT_ANSWER`。
- MCQ 题目提供 `options`（至少 2 个）；CODE 题目提供 `function_name`；SHORT_ANSWER 为开放式题，`deterministic` 为 `false`。
- `scoring_spec_ref` 固定为 `scoring/<item_id>.json`，即隐藏评分规格的相对路径。
- 题面与公开字段中不得包含答案、期望输出或隐藏测试用例；`public` 表示该题面可以展示给学生。

### teaching_content.json

```json
{
  "schema_version": "m1a.v0",
  "domain_id": "cf_binary_search",
  "nodes": {
    "cf.search.binary": {
      "EXPLAIN": "……",
      "HINT_L1": "……",
      "HINT_L2": "……",
      "HINT_L3": "……",
      "PRACTICE_ITEM_IDS": ["item.bs.code.001"],
      "REVIEW": "……"
    }
  }
}
```

- 节点键必须覆盖知识图谱全部 8 个节点。
- `HINT_L1` 只给思考方向，不泄露最终答案或代码；`HINT_L2`、`HINT_L3` 逐层具体。
- `PRACTICE_ITEM_IDS` 指向 `assessment_items.json` 中真实存在的题目，且该题包含当前节点。
- 教学内容不得包含评分规格内容、答案键或隐藏测试用例，也不得出现 `scoring/` 目录路径。

### scoring/<item_id>.json（隐藏）

评分规格仅供评分器读取，题面与教学内容绝不引用。三种形态：

- MCQ：

```json
{"kind": "MCQ", "correct_option_index": 0, "explanation": "……"}
```

`correct_option_index` 为 0-based 下标，必须落在该题选项范围内，且单选题只有一个正确项。

- CODE：

```json
{
  "kind": "PYTHON_FUNCTION",
  "function_name": "lower_bound",
  "tests": [
    {"args": [[1, 2, 2, 2, 3], 2], "expected": 1}
  ],
  "timeout_s": 2
}
```

`args` 为按位置传入的参数列表；`tests` 至少 6 条，覆盖空数组、单元素、重复值与未命中边界。

- SHORT_ANSWER：

```json
{
  "kind": "SEMANTIC_RUBRIC",
  "required_concept_groups": [["单调", "有序"], ["前提", "条件"]],
  "allow_correct": false,
  "on_insufficient": "NEEDS_REVIEW"
}
```

开放题不得依靠简单字符串匹配假装语义理解：`allow_correct` 为 `false`，证据不足时评分结果为 `NEEDS_REVIEW`（转人工复核），而不是判定为正确。

## 隐藏评分规格边界

`scoring/` 目录属于隐藏区域，只有评分器/校验器可以读取。`assessment_items.json` 中的题面、`teaching_content.json` 中的教学内容以及任何公开输出都不得引用该目录，也不得包含正确答案、期望输出或隐藏测试用例。

## 来源、许可与数据声明

- 来源：本目录全部内容由 M1A 团队自编，为合成（synthetic）教学数据；题目与讲解均为原创，不含任何受版权保护的题面、教材或第三方数据集。
- 许可：CC0-1.0（Creative Commons Zero v1.0 Universal，公共领域贡献）。
- 数据声明：全部为合成数据，不含真实用户、真实公司、真实人名、真实评测记录或任何个人身份信息。
- 离线确定性：不依赖网络与外部服务，不含凭证、密钥或环境变量配置；相同输入在任何环境下产生相同结果。
