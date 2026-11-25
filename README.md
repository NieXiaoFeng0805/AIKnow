# AIKnow

个人知识库 / 知识图谱项目。

## 定位

三层递进，先跑通最下层，再按需上图：

| 层 | 解决什么 | 状态 |
|---|---|---|
| ① 文档库 + RAG | 答案在一两段原文里 | 待做 |
| ② 结构化知识库 | 精确字段、数值、清单 | 待做 |
| ③ 知识图谱 | 多跳关系、路径、传导 | 待做 |

选型原则：从真实问题清单反推（要几段原文 / 几个字段 / 几跳关系），不先建图。

## 目录

```
docs/      方案、决策记录（ADR）
  decision/0001 路线：先 RAG 后图谱
  decision/0002 防过时原则
ingest/    采集与解析（loader.py：目前 .md/.txt）
pipeline/  切分（chunker.py：按标题结构、表格独立、带偏移）
retrieval/ 检索（bm25.py 纯 Python + index.py 对外接口）
eval/      黄金集与回归评测
aiknow/    CLI 入口（python -m aiknow）
tests/     回归测试与 fixtures
```

## 用法

```bash
aiknow index --dir /path/to/kb            # 文档数 / 切块数
aiknow ask "一线城市住宿上限是多少" --dir /path/to/kb -k 3
```

输出带出处（文件 + 章节路径），便于引用回链。

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
.venv/bin/ruff check .
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
