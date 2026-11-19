# 知识时效性与来源策略（Freshness & Source Policy）

- 版本：`m1.offline.v0`
- 所有者：B 线 `b-interview`（task-3）
- 代码：`m1_offline/freshness.py`；类型：`m1_offline/types.py`（b-core 单写者，只读）
- Fixtures：`fixtures/m1/interview/knowledge/`（9 组合成更新/冲突条目）
- 状态：**OFFLINE-ONLY / SYNTHETIC**。所有来源均为自编 Synthetic、许可 CC0-1.0；不抓取真实网页，不声称真实时效已同步。

## 1. 知识时效元数据

每条知识来源 `KnowledgeSource` 必须携带以下字段（`m1_offline/types.py`）：

| 字段 | 类型 | 含义 | 约束 |
|------|------|------|------|
| `source_id` | str | 来源/文档稳定标识 | 非空 |
| `uri` | str | 来源地址（合成域名为 `.invalid`） | 非空；不访问网络 |
| `publisher` | str | 发布者（用于来源分层推断） | 非空 |
| `published_at` | str | **来源发布时间**（文档自己声明的发布时间） | ISO-8601 |
| `observed_at` | str | **观测时间**（我们抓取/核对到它的时间） | ISO-8601；与 `published_at` 显式区分 |
| `valid_until` | str \| None | 来源有效期截止时间 | ISO-8601 或 None |
| `confidence` | float | 置信度 | `[0,1]` |
| `claim_status` | str | 声明状态 | `VERIFIED / REPORTED / CONFLICT / EXPIRED / UNKNOWN` |

分类结果 `KnowledgeRevision` 记录 `revision_id, source_id, old_hash, new_hash, change_kind, detected_at, claim_status, notes`。
`detected_at` 取 `new.observed_at`（观测时间），并在 `notes` 中记录：

- `published_at=<old>-><new>`、`observed_at=<old>-><new>`；
- `publish_delta_seconds=<int>`（两版发布时间差）、`observation_lag_seconds=<int>`（发布到观测的延迟）；
- `observed_after_old_valid_until`、`published_after_observed` 等布尔标记；
- `time_semantics=published_at 为来源发布时间，observed_at 为抓取/观测时间，二者显式区分`。

因此“来源改版了”与“我们今天才看到/才发现过期”在审计记录中不会混淆。

## 2. KEEP / RECHECK / UPDATE 规则

`FreshnessManager.classify(old, new)` 按以下**失败优先（fail-closed）**顺序判定：

1. `new.published_at > new.observed_at`（未来时间/时钟异常）→ **RECHECK**；
2. 任一 `claim_status == CONFLICT` → **RECHECK**（不得静默覆盖）；
3. 任一 `claim_status == EXPIRED` → **RECHECK**；
4. `new.observed_at > old.valid_until`（旧版本已过期后才观测到）→ **RECHECK**；
5. `new.observed_at > new.valid_until`（新版本自身已过期）→ **RECHECK**；
6. `new.published_at < old.published_at`（新数据比旧数据更旧：镜像/缓存/乱序）→ **RECHECK**；
7. 内容指纹相同（`old_hash == new_hash`）→ **KEEP**；
8. `new.published_at > old.published_at` 且来源权威度不下降、且权威层级或置信度提升 → **UPDATE**；
9. 其余情况 → **RECHECK**（含“发布更新但权威/置信度不变或更低”“发布时间相同但内容不同”等歧义场景）。

内容指纹（`content_hash`）在 v0 中由
`sha256(canonical_json(uri, publisher, published_at, claim_status))` 计算（见 §6 限制）。
`KEEP` 仅表示“内容指纹未变化，无需课程动作”，不表示来源一定权威。

## 3. 冲突与过期处置

- **冲突**：`claim_status=CONFLICT` 或官方来源与社区来源结论冲突时，生成 `RECHECK`，revision `claim_status=CONFLICT`；
  notes 写 `recheck_required=true`。冲突项只能进入人工复核队列。
- **过期**：`valid_until` 已过（旧版或新版）或 `claim_status=EXPIRED` 时，revision `claim_status=EXPIRED`；
  必须复核后重新取源，不得把过期内容继续当有效知识。
- **更旧/镜像**：`published_at` 更旧或来源层级更低（如镜像站、社区帖）时一律 `RECHECK`；
  社区帖可以“提示去核对”，但不能覆盖官方文档。
- 所有 `RECHECK` 的 notes 均包含 `recheck_required=true` 与“必须人工复核后才能更新主课程，禁止静默写入”。

## 4. 课程污染防护

- `FreshnessManager.apply(revisions)` **只做分组**（`{"KEEP": [...], "UPDATE": [...], "RECHECK": [...]}`），
  不写任何课程/知识库状态。
- 唯一可能进入主课程的是 `UPDATE` 且 `curriculum_eligible(revision) is True`：
  - `change_kind == "UPDATE"`；
  - revision `claim_status == "VERIFIED"`（`REPORTED` 更新同样需要复核）；
  - 新来源层级 `SOURCE_TIERS[new_tier]["may_update_curriculum"] is True`（JD/社区/镜像/未知层级一律不可写课程）。
- `KEEP` 不产生课程变更；`RECHECK` 永不进入课程写入集合。
- 测试用“只物化 eligible UPDATE”的方式构造课程写入集合，断言其与 `RECHECK` 的 `source_id` 集合不相交
  （`test_apply_groups_revisions_and_blocks_silent_pollution`）。

## 5. 来源可信度分层与许可

层级由 `publisher/uri/source_id` 关键词推断（`infer_source_tier`），策略表 `SOURCE_TIERS` 与下表一一对应（测试会断言 rank 一致）。

| tier | rank | 描述 | 可进入主课程 | 是否代表题目热度 |
|------|------|------|--------------|------------------|
| official_document | 3 | 官方文档/规范/内部权威 wiki；可进入主课程（仅当 UPDATE 且 claim_status=VERIFIED） | 是（严格条件） | 否 |
| paper | 2 | 论文/预印本；可作更新来源，必须标注未复现，且需复核 | 是（严格条件） | 否 |
| engineering_blog | 2 | 工程团队博客；可作更新来源，需标注实践经验未经独立验证 | 是（严格条件） | 否 |
| jd | 2 | 招聘 JD；只表示岗位要求变化，不代表题目热度或知识更新 | 否 | 否 |
| community | 1 | 社区讨论/论坛；只能作为线索触发 RECHECK，不能单独驱动课程更新 | 否 | 否 |
| mirror | 0 | 镜像/转载站点；旧内容风险高，默认 RECHECK | 否 | 否 |
| unknown | 0 | 未知来源；默认 RECHECK，禁止进入主课程 | 否 | 否 |

关键结论：

- **JD 变化 ≠ 题目热度**。JD 版本更新只说明岗位要求变化；`classify()` 在涉及 JD 层级时显式写入
  `jd_change_does_not_imply_topic_popularity=true`，且 `SOURCE_TIERS["jd"]["may_update_curriculum"] = False`。
  不允许把 JD 更新折算成“题目变热门/话题热度上升”。
- 论文 / 官方文档 / 社区讨论**分层使用**：官方文档 > 论文（需复现标注）> 社区讨论（仅线索）。
- 所有 fixture 为自编 Synthetic / CC0-1.0，不含真实公司、真实人名、真实 URL（合成域名 `.invalid`）。

## 6. 内容指纹 v0 限制

`KnowledgeSource` 在 `m1.offline.v0` 中**没有正文/摘要哈希字段**，因此内容指纹退化为对
`(uri, publisher, published_at, claim_status)` 的 canonical sha256（64 位十六进制）。
这意味着：若上游不提供正文 digest，正文级改动但元数据完全相同的两次观测会被判为 `KEEP`。
真实集成必须由抓取层传入正文 digest 或扩展 schema（**UNVERIFIED**，需 schema 变更流程）。本限制在代码 docstring、
本文件与测试（`test_content_fingerprint_hash_rule` 检查 KEEP/UPDATE 哈希行为）中显式记录。

## 7. Fixture 清单（knowledge，9 组）

| update_id | 场景 | expected_change_kind |
|-----------|------|----------------------|
| k-keep-001 | 官方文档重观测，指纹相同 | KEEP |
| k-keep-002 | 镜像同内容重观测 | KEEP |
| k-update-001 | 官方文档新版，发布时间更新 + 置信度提升 | UPDATE |
| k-update-002 | 论文 v2，发布时间更新 + 置信度提升 | UPDATE |
| k-recheck-expired-001 | 旧版本 `valid_until` 已过 | RECHECK/EXPIRED |
| k-recheck-conflict-001 | 社区来源与官方冲突（CONFLICT） | RECHECK/CONFLICT |
| k-recheck-older-001 | 镜像发布时间早于旧版本 | RECHECK |
| k-recheck-community-001 | 社区来源更新但权威/置信度更低 | RECHECK |
| k-recheck-futuredate-001 | 发布时间晚于观测时间（未来时间/时钟异常） | RECHECK |

## 8. 校验命令与真实结果

```bash
cd /root/at-m1-offline && "/root/Autonomous Teacher/.venv/bin/python" -m pytest \
  tests/m1_offline/test_freshness.py -q
```

真实运行结果（2026-11-19，Python 3.11.15 / pytest 9.2.0）：`test_freshness.py` 17 个测试通过；
三个测试文件合计 `49 passed in 0.07s`。逐条分类结果 9/9 与 fixture 的 `expected_change_kind` 一致（KEEP 2 / UPDATE 2 / RECHECK 5）；
可进入课程写入门禁的来源仅 `doc:auc-001`、`paper:ns-001`，5 个 RECHECK 来源全部被阻断。详细记录见
`docs/m1/INTERVIEW_COACH_SPEC.md` §12 与 `docs/m1/traces/interview_demo.jsonl`。

## 9. 已知限制 / UNVERIFIED

- 无真实外部数据源与调度器：`observed_at` 由 fixture/调用方给定，真实抓取/定时重检 UNVERIFIED。
- 来源分层靠合成 `publisher/uri/source_id` 关键词推断，真实来源命名千差万别，生产环境需要显式 tier 元数据字段（未实现，UNVERIFIED）。
- `confidence` 为调用方给定，无自动来源可信度评估算法。
- 冲突仲裁只做“标记 RECHECK”，不做自动事实裁决；人工复核流程未实现（UNVERIFIED）。
- 课程写入只是策略门禁（`curriculum_eligible`），未连接真实课程数据库；跨模块写边界由 b-eval/Lead 验收。
- `KEEP/UPDATE/RECHECK` 分类覆盖 9 个合成场景；真实长尾（撤回、勘误、多来源并发冲突、时区/夏令时）未验证。
