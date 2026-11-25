"""文档加载：把本地文件读成 Document。

具体格式交给 ingest/parsers.py，这里只负责遍历与过滤。
"""

from __future__ import annotations

from pathlib import Path

from ingest.model import Document, doc_id_for

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx"}


def load_file(path: str | Path) -> Document:
    from ingest.parsers import parse_file

    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持的文件类型: {p.suffix} ({p})")
    return parse_file(p)


def load_directory(root: str | Path) -> list[Document]:
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    docs: list[Document] = []
    for p in sorted(root_path.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            docs.append(load_file(p))
    return docs


__all__ = ["SUPPORTED_SUFFIXES", "Document", "doc_id_for", "load_directory", "load_file"]
