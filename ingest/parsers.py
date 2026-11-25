"""多格式解析：文件 -> Markdown 文本。

统一出口是 Markdown，下游 chunker 不需要知道来源格式。

后端优先级：
1. docling（若已安装）：版面/表格感知，质量最好，依赖较重
2. pymupdf：纯文本 + 字号启发式识别标题，快
3. python-docx：按样式还原标题与表格

后端缺失时按后缀降级，不抛 ImportError。
"""

from __future__ import annotations

import os
from pathlib import Path

from ingest.model import Document, doc_id_for

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def _make_document(path: Path, text: str, backend: str) -> Document:
    title = path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return Document(
        doc_id=doc_id_for(path, text),
        path=str(path),
        title=title,
        text=text,
        meta={"suffix": path.suffix.lower(), "size": len(text), "backend": backend},
    )


def _parse_text(path: Path) -> Document:
    return _make_document(path, path.read_text(encoding="utf-8"), "text")


def docling_available() -> bool:
    if os.environ.get("AIKNOW_DOCLING", "") == "0":
        return False
    try:
        import docling  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _parse_docling(path: Path) -> Document:
    from docling.document_converter import DocumentConverter

    result = DocumentConverter().convert(str(path))
    md = result.document.export_to_markdown()
    return _make_document(path, md, "docling")


def _pdf_block_lines(page) -> list[tuple[float, str]]:
    blocks: list[tuple[float, str]] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(s.get("text", "") for s in spans).strip()
            if not text:
                continue
            blocks.append((max(s.get("size", 0) for s in spans), text))
    return blocks


def _pdf_heading_level(size: float, median: float, distinct: list[float]) -> int:
    if size < median * 1.15:
        return 0
    rank = sum(1 for d in distinct if d > round(size, 1) + 0.5)
    return min(rank + 1, 6)


def _parse_pdf(path: Path) -> Document:
    import pymupdf

    parts: list[str] = []
    with pymupdf.open(path) as pdf:
        for page in pdf:
            blocks = _pdf_block_lines(page)
            if not blocks:
                continue
            sizes = sorted(s for s, _ in blocks)
            median = sizes[len(sizes) // 2]
            distinct = sorted({round(s, 1) for s in sizes}, reverse=True)

            for size, text in blocks:
                level = _pdf_heading_level(size, median, distinct)
                if level and len(text) <= 60 and not text.endswith(("。", ".", "，", ",")):
                    parts.append(f"{'#' * level} {text}")
                else:
                    parts.append(text)
            parts.append("")
    return _make_document(path, "\n".join(parts), "pymupdf")


def _parse_docx(path: Path) -> Document:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    parts: list[str] = []
    for item in d.element.body.iterchildren():
        tag = item.tag.split("}")[-1]
        if tag == "p":
            p = Paragraph(item, d)
            text = p.text.strip()
            if not text:
                continue
            style = (p.style.name or "").lower()
            if style.startswith("heading"):
                level = "".join(ch for ch in style if ch.isdigit()) or "1"
                parts.append(f"{'#' * min(int(level), 6)} {text}")
            elif style.startswith("title"):
                parts.append(f"# {text}")
            else:
                parts.append(text)
        elif tag == "tbl":
            t = Table(item, d)
            rows = [[c.text.strip().replace("\n", " ") for c in r.cells] for r in t.rows]
            if not rows:
                continue
            parts.append("| " + " | ".join(rows[0]) + " |")
            parts.append("|" + "---|" * len(rows[0]))
            for r in rows[1:]:
                parts.append("| " + " | ".join(r) + " |")
    return _make_document(path, "\n\n".join(parts), "python-docx")


def parse_file(path: str | Path, prefer_docling: bool | None = None) -> Document:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    suffix = p.suffix.lower()
    use_docling = docling_available() if prefer_docling is None else prefer_docling

    if suffix in TEXT_SUFFIXES:
        return _parse_text(p)
    if suffix == ".pdf":
        if use_docling and docling_available():
            return _parse_docling(p)
        return _parse_pdf(p)
    if suffix in {".docx", ".doc"}:
        if use_docling and docling_available():
            return _parse_docling(p)
        if suffix == ".doc":
            raise ValueError("旧版 .doc 需要先另存为 .docx 或安装 docling")
        return _parse_docx(p)
    raise ValueError(f"不支持的格式: {suffix} ({p})")
