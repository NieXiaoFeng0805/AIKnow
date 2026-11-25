# 解析后端实测（2026-11-25，CPU）

样本：arXiv 1706.03762（Attention Is All You Need），14 页 PDF，2.2 MB。
机器：Ubuntu，无可用 GPU（GTX 1050 Ti 4GB，Pascal sm_61，新版 CUDA 轮子不支持）。

| 后端 | 耗时 | 每页 | 切块数 | 特点 |
|---|---|---|---|---|
| pymupdf | 0.54 s | ~0.04 s | 80 | 只抽文本 + 字号判标题；快，但无阅读顺序 |
| docling（layout，无表格） | 39.2 s | ~2.8 s | 83 | 有版面分析，标题层级完整（`## 3.1 Encoder and Decoder Stacks`），段落完整 |

约 **72 倍** 时间差。结论：

- 日常批量入库、文档本身规整（单栏、标题清晰）→ pymupdf 够用
- 双栏论文、复杂版面、需要可靠标题层级 → docling
- 表格结构需要 docling 的 table 模型（额外 ~200MB 权重，本次下载卡住未完成）

## 决策

默认走 docling（装了就用），失败自动降级到 pymupdf；`AIKNOW_DOCLING=0` 强制轻量后端。

## 踩到的坑

1. `NO_PROXY` 含 `[::1]` 会让 httpx 抛 `Invalid port: ':1]'`，docling 直接失败。已在 `_parse_docling` 里临时清理该变量并在结束后还原。
2. 直接用 PyPI 装 docling 会拉 CUDA 版 torch（含 519MB cuDNN、数 GB NVIDIA 库）。先装 CPU 版 torch 再装 docling，体积从 ~5GB 降到 ~1.5GB。
3. HuggingFace 模型下载会在中途 stall（大文件连接中断），需要重试或用镜像。
