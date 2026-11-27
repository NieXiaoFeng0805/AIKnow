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
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from pathlib import Path

from ingest.model import Document, doc_id_for, source_type_for

TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


def _make_document(
    path: Path, text: str, backend: str, zone_id: str, source_type: str | None = None
) -> Document:
    title = path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    st = path.stat()
    return Document(
        doc_id=doc_id_for(zone_id, path, text),
        path=str(path),
        title=title,
        text=text,
        zone_id=zone_id,
        source_type=source_type or source_type_for(path),
        meta={
            "suffix": path.suffix.lower(),
            "size": len(text),
            "backend": backend,
            "date": datetime.fromtimestamp(st.st_mtime).date().isoformat(),
        },
    )


def _parse_text(path: Path, zone_id: str) -> Document:
    return _make_document(path, path.read_text(encoding="utf-8"), "text", zone_id)


def docling_available() -> bool:
    if os.environ.get("AIKNOW_DOCLING", "") == "0":
        return False
    try:
        import docling  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


@contextmanager
def _sanitized_no_proxy() -> Iterator[None]:
    """去掉 NO_PROXY 里的 [::1] 一类条目。

    本机环境把它设成 "...,::1,[::1]"，httpx 解析时会抛 Invalid port: ':1]'，
    导致 docling/HF 直接失败。这里只在转换期间清理，结束后还原。
    """
    keys = ("NO_PROXY", "no_proxy")
    saved = {k: os.environ.get(k) for k in keys}
    for k in keys:
        raw = os.environ.get(k)
        if raw:
            kept = [item for item in raw.split(",") if item.strip() and "[" not in item]
            os.environ[k] = ",".join(kept)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _parse_docling(path: Path, zone_id: str) -> Document:
    """docling 转换。

    默认关闭表格结构模型（会额外拉 ~200MB 权重，且 CPU 上很慢）；
    AIKNOW_DOCLING_TABLES=1 打开。OCR 同理用 AIKNOW_DOCLING_OCR=1。
    """
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    use_tables = os.environ.get("AIKNOW_DOCLING_TABLES", "0") == "1"
    use_ocr = os.environ.get("AIKNOW_DOCLING_OCR", "0") == "1"

    if path.suffix.lower() == ".pdf":
        opts = PdfPipelineOptions(do_table_structure=use_tables, do_ocr=use_ocr)
        converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )
    else:
        converter = DocumentConverter()

    with _sanitized_no_proxy():
        md = converter.convert(str(path)).document.export_to_markdown()
    backend = "docling" if not use_tables else "docling+tables"
    return _make_document(path, md, backend, zone_id)


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


def _parse_pdf(path: Path, zone_id: str) -> Document:
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
    return _make_document(path, "\n".join(parts), "pymupdf", zone_id)


def _parse_docx(path: Path, zone_id: str) -> Document:
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
    return _make_document(path, "\n\n".join(parts), "python-docx", zone_id)


def parse_file(
    path: str | Path,
    zone_id: str,
    prefer_docling: bool | None = None,
    source_type: str | None = None,
) -> Document:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(str(p))
    suffix = p.suffix.lower()
    use_docling = docling_available() if prefer_docling is None else prefer_docling
    use_docling = use_docling and docling_available()

    def try_docling() -> Document | None:
        try:
            return _parse_docling(p, zone_id)
        except Exception as exc:  # noqa: BLE001
            # 模型缺失/下载失败/版本不兼容时不阻断整条流水线
            sys.stderr.write(f"[aiknow] docling 失败，降级: {exc}\n")
            return None

    if suffix in TEXT_SUFFIXES:
        doc = _parse_text(p, zone_id)
    elif suffix == ".pdf":
        doc = try_docling() if use_docling else None
        if doc is None:
            doc = _parse_pdf(p, zone_id)
    elif suffix in {".docx", ".doc"}:
        doc = try_docling() if use_docling else None
        if doc is None:
            if suffix == ".doc":
                raise ValueError("旧版 .doc 需要先另存为 .docx 或安装 docling")
            doc = _parse_docx(p, zone_id)
    else:
        raise ValueError(f"不支持的格式: {suffix} ({p})")

    if source_type is not None:
        doc = replace(doc, source_type=source_type)
    return doc
