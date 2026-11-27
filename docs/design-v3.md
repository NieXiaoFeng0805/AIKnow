# 方案 v3.1：分区驱动（冻结）

- 状态：**已冻结**（2026-11-27），可作为实施依据
- 变更来源：主人对 D1–D3 的答复（分区 / 不要全局问答 / 抽取走 API），
  以及 Q1–Q3 的裁决（见 §9）

## 0. 结论

**分区（zone）升级为一等公民；社区层与全局问答砍掉；抽取全走 API。**

三个决定互相咬合：不做全局问答 → 不需要社区摘要层 → 但必须有分区来回答"这批资料讲了什么"这类问题（按区答，而不是按库答）。

## 1. 分区模型

| zone_id | 定位 | 典型内容 | 来源类型 | 默认检索 |
|---|---|---|---|---|
| `life` | 生活区：日常、灵感 | 随手记、想法、片段 | 笔记（md/txt） | 仅本区 |
| `work` | 工作区：技能与实战 | 帖子、git 仓库、网站、AI 应用与测试开发 | 网页、git、文档 | 仅本区 |
| `study` | 学习区：提醒自己 | AI 前沿、技术突破、论文 | 网页、PDF、文章 | 仅本区 |

分区不是文件夹，是**一等数据维度**：

- 每个 chunk、实体、三元组都带 `zone_id`
- 检索默认硬过滤本区，**不允许串区**
- 实体命名空间按区隔离（生活区的"张伟"和工作区的"张伟"是两个实体）

## 2. 砍掉的东西

| 砍掉 | 理由 | 代价与替代 |
|---|---|---|
| community 层（社区检测 + 摘要） | 不做全局问答，社区层唯一用途消失，而它是最贵的一块（+20–30% token） | 无法回答"我所有笔记总体讲了什么"；替代：**按区月度摘要**（每区几百字，成本极低） |
| global / drift 查询模式 | 同上 | 保留 local 模式；跨区只做显式开关 |
| 全库合并索引 | 分区语义会被稀释 | 索引结构按 zone 分片，物理上可同库不同表 |

## 3. 来源适配（按区分工）

| 来源 | 处理 | 注意 |
|---|---|---|
| 笔记 md/txt | 现有 loader + 结构切分 | 生活区内容短，chunk 可更小（200–400 字） |
| 网页 / 帖子 | 抓正文 → 转 Markdown → 保留 URL、标题、抓取时间、站点 | 论坛帖子要保留楼层结构 |
| git 仓库 | README、docs/、可选 commit message | **代码文件暂不进主索引**（见 Q1） |
| PDF / 论文 | docling（已有）或 pymupdf 降级 | 学习区主力 |

**同一 zone 内允许多来源混存**，靠 `source_type` 区分，检索时可加权（笔记 > 网页 > 代码）。

## 4. 数据模型

```
zones(id, name, purpose, config_json)
documents(id, zone_id, source_type, uri, title, fetched_at, hash, meta)
chunks(id, doc_id, zone_id, seq, text, heading_path, start, end, kind)
entities(id, zone_id, type, name, description, updated_at)      -- 区内唯一
relations(id, zone_id, src_id, dst_id, predicate, confidence, evidence_chunk_id, valid_from, valid_to)
mentions(chunk_id, entity_id)
links(id, from_entity_id, to_entity_id, kind)                  -- 跨区连接，可选，后置
```

要点：

- `zone_id` 冗余在 chunks / entities 上，避免每次 join 才能过滤
- 实体唯一键是 `(zone_id, type, normalized_name)`
- `relations.evidence_chunk_id` 非空约束——没证据的关系不许入库

## 5. 抽取（走 API）

- **Provider 抽象**：`base_url + api_key + model`，优先 OpenAI 兼容协议，换供应商只改配置
- **模型分档**：抽取/归并用便宜模型（gpt-4o-mini 级）；实体画像、答疑用强模型
- **缓存**：`sha256(chunk_text + schema_version + model)` 作 key，命中直接复用，改 schema 才失效
- **预算闸门**：每区先跑 50 篇，量出 token/篇；超过设定阈值暂停并报告，不静默烧钱
- **失败处理**：重试 3 次 + 指数退避；仍失败入重试队列，主流程继续

## 6. 检索（区内为主）

| 场景 | 行为 |
|---|---|
| 默认 | 只检索调用时指定的 zone；未指定则用"当前区" |
| 显式跨区 | `--zones life,study` 才合并，结果按区标注 |
| 区内无证据 | **拒答**，不跨区偷答案 |
| 输出 | 每条引用带 `zone_id + doc_id + chunk_id + 页码/字符偏移` |

## 7. 评测（按区分集）

每区独立黄金集 50 条起：

| 类型 | 例子 | 判定 |
|---|---|---|
| 区内单跳 | "住宿上限多少" | 答案 + 证据 |
| 区内多跳 | "A 工具的哪个限制导致 B 方案不可行" | 需 2 跳以上证据 |
| 区内心智 | "我之前对 X 的判断是什么" | 生活区/学习区专属 |
| 串区检测 | 问生活区问题 | **不许**返回工作区内容 |
| 该拒答 | 区内不存在 | 必须拒 |

去掉"跨主题综合"（无全局问答，不设此指标）。

## 8. 与现有代码的差距（只列，不改）

| 改动 | 影响面 |
|---|---|
| `zone_id` 贯穿 loader / chunker / index | 三个模块签名 |
| sources：web / git 适配器 | 新增 ingest/sources |
| entities / relations 表 + 区内归并 | 新增存储层 |
| API 客户端 + 缓存 + 预算闸门 | 新增 pipeline/llm |
| CLI 加 `--zone`、`--zones` | aiknow/__main__ |

**阶段 1 只做前两行**（分区 + 来源适配），其余等阶段 2 再动。

## 9. 已裁决（原 Q1–Q3）

| 编号 | 问题 | 裁决 |
|---|---|---|
| Q1 | git 仓库吃到什么粒度 | **只吃 README + docs + commit message**；代码文件不进主索引，符号级索引后置 |
| Q2 | 生活区是否需要时间维度检索 | **要**。`documents.fetched_at` + 时间过滤（`--since` / `--until`），支持"上周我在想什么" |
| Q3 | 跨区查询 | **留显式开关**，默认关闭；`--zones life,study` 才合并，结果按区标注 |

## 10. 阶段 1 实施清单（可验收）

| # | 事项 | 验收标准 |
|---|---|---|
| 1 | 分区注册表 `zones.toml`（id/name/purpose/源目录） | 启动时校验 zone 存在，未知 zone 报错 |
| 2 | loader 按 zone 扫描，`documents` 带 `zone_id` + `source_type` | 同一文件放进不同 zone 得到不同 doc_id |
| 3 | chunker 透传 `zone_id` | 每个 chunk 都能回指 zone |
| 4 | 索引按 zone 分片，检索必须带 zone | 不传 zone 直接报错，不允许默认全库 |
| 5 | 时间过滤 | `--since 2026-11-01` 只返回该日期后的文档 |
| 6 | 跨区开关 | 默认关闭；开启后结果标注来源区 |
| 7 | 串区检测测试 | 生活区查询**不得**返回工作区 chunk（断言为空或全为 life） |
| 8 | 回归 | 现有 13 个测试全绿，ruff 干净 |

## 11. 演进顺序

1. **区内 RAG 闭环**：分区 + 来源适配 + 检索带 zone 过滤 + 区内引用（= §10）
2. **区内实体图**：抽取、归并、证据链（API 抽取，预算闸门）
3. **跨区 Link**（可选）：只有出现"必须跨区才能答"的真实问题时才做

每一步独立验收，不达标不进入下一步。
