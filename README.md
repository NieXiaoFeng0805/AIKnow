# AIKnow

个人知识库 / 知识图谱项目。

## 定位

三层递进，先跑通最下层，再按需上图：

| 层 | 解决什么 | 状态 |
|---|---|---|
| ① 文档库 + RAG | 答案在一两段原文里 | 分区内已跑通（阶段 1，见 design-v3） |
| ② 结构化知识库 | 精确字段、数值、清单 | 待做 |
| ③ 知识图谱 | 多跳关系、路径、传导 | 待做 |

选型原则：从真实问题清单反推（要几段原文 / 几个字段 / 几跳关系），不先建图。

## 目录

```
zones.toml 分区注册表（life / work / study）
zones.demo.toml 演示用注册表（扫仓库自带 docs/、imports/）
kb/        各分区的原始文档（kb/life、kb/work、kb/study）
docs/      方案、决策记录（ADR）
  decision/0001 路线：先 RAG 后图谱
  decision/0002 防过时原则
  decision/0003 分区替代全局问答
ingest/    采集与解析（zones.py 注册表、loader.py、parsers.py）
pipeline/  切分（chunker.py：按标题结构、表格独立、带偏移、带 zone）
retrieval/ 检索（bm25.py 纯 Python + index.py 对外接口，按分区隔离）
eval/      黄金集与回归评测
aiknow/    CLI 入口（python -m aiknow）+ serve.py（本地页面）
  web/     页面三件套：index.html / app.js / app.css（无构建链）
tests/     回归测试与 fixtures
imports/   旧会话导入存档（历史参考，不是方案文档）
```

## 用法

```bash
aiknow index                                         # 每个分区的文档数 / 切块数
aiknow ask "一线城市住宿上限是多少" --zone life -k 3
aiknow ask "周末安排" --zones life,work               # 跨区（默认关闭）
aiknow ask "住宿上限" --zone life --since 2026-11-01   # 只看该日期之后的文档
```

输出带出处（文件 + 章节路径），便于引用回链；跨区结果会标出来源分区。

## 分区（zone）

`zones.toml` 是唯一的分区来源（见 [docs/design-v3.md](docs/design-v3.md) §1）：

```toml
[zones.life]
name = "生活区"
purpose = "日常、灵感、随手记"
sources = ["kb/life"]        # 相对 zones.toml 所在目录
```

规则：

- `doc_id` 含分区：同一份文件放进两个分区是两份文档
- 每个 chunk 都带 `zone_id`，索引按分区过滤
- 检索必须指定分区，不传 `--zone` 直接报错，不会默认全库
- 跨区必须显式 `--zones`，结果标注来源分区

## 页面

两个命令，先看效果再用真实数据：

```bash
aiknow serve --config zones.demo.toml --port 8000   # 用仓库自带文档当数据（10 篇 / 459 块）
aiknow serve --port 8000                            # 用真实数据（扫 kb/life、kb/work、kb/study）
```

然后打开 http://127.0.0.1:8000/ ：左边分区（带文档数、缺目录告警），中间检索，右边原文抽屉。

接口（页面和将来的 DSH 面板共用这一层）：

| 接口 | 作用 |
|---|---|
| `GET /api/zones` | 分区、文档数、切块数、缺目录 |
| `GET /api/search?q=&zone=&zones=&since=&k=` | 命中证据（分数、分区、出处、章节） |
| `GET /api/doc?zone=&doc_id=` | 整篇原文与切块，喂右侧抽屉 |
| `POST /api/reindex` | 重新扫描（放完新文件点「重新索引」） |

技术选择：stdlib `http.server` + 三个静态文件，不引 Web 框架、不建前端构建链（对齐 ADR-0002 防过时）。

限制（明确不做）：只做检索与出处，不做生成式问答；不做登录与多用户；单机自用不追求并发；
高亮只是子串 / 中文二元组匹配，不是语义高亮。

## 支持的格式
| 格式 | 后端 | 说明 |
|---|---|---|
| `.md` / `.txt` | 内置 | 按标题结构切分 |
| `.pdf` / `.docx` | docling（装了就用） | 有版面分析，标题层级与段落顺序可靠；CPU 上约 2.8 s/页 |
| `.pdf` | pymupdf（降级/快速） | 只抽文本 + 字号判标题，约 0.04 s/页；双栏会串 |
| `.docx` | python-docx（降级） | 按样式还原标题与表格 |

实测对比见 [docs/parsing-benchmark.md](docs/parsing-benchmark.md)。

安装可选依赖：`pip install -e ".[pdf,docx]"`，docling 用 `-e ".[docling]"`（先装 CPU 版 torch，否则会拉几 GB CUDA 库）。

环境变量：

| 变量 | 默认 | 作用 |
|---|---|---|
| `AIKNOW_DOCLING` | 自动 | `0` 强制走轻量后端 |
| `AIKNOW_DOCLING_TABLES` | `0` | `1` 启用表格结构模型（额外 ~200MB 权重） |
| `AIKNOW_DOCLING_OCR` | `0` | `1` 启用 OCR（扫描件需要） |

docling 失败会自动降级到 pymupdf，不会中断入库。

已知局限：暂不支持中英文跨语言检索（中文问、英文文档命中不了）。

## 开发

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check aiknow ingest pipeline retrieval tests   # 别扫 .venv
```

本机现状：Python 3.14.4，`.venv` 已就绪（不入库）。

## 关键约定

- 原文 + PostgreSQL 是源真相；向量库、图库都是可重建的派生索引。
- 每个 chunk / 三元组必须带来源、时间、权限元数据。
- 上线前必须有人工黄金集（问题 + 标准答案 + 应命中片段）。

## 路线

1. 第 1 周：问题清单 Top 50 + 数据摸底 + 选型结论
2. 第 2–3 周：解析/切分 + 混合检索 + 引用回链（Recall@5 ≥ 0.8）
3. 第 4 周：rerank + 拒答 + 前端引用
4. 第 5–6 周：schema v1 + 抽取 + 高价值子域图谱
5. 第 7–8 周：权限、增量更新、监控、badcase 闭环
