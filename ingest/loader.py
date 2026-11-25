"""文档加载：把本地文件读成 Document。

第一阶段只支持纯文本与 Markdown；PDF/Word 后续接入 Docling 等解析器，
对外接口保持不变（输入路径，输出 Document）。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: str
    title: str
    text: str
    meta: dict = field(default_factory=dict)


def _doc_id(path: Path, text: str) -> str:
    h = hashlib.sha256()
    h.update(str(path).encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]


def _title(path: Path, text: str) -> str:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return path.stem


def load_file(path: str | Path) -> Document:
    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持的文件类型: {p.suffix} ({p})")
    text = p.read_text(encoding="utf-8")
    return Document(
        doc_id=_doc_id(p, text),
        path=str(p),
        title=_title(p, text),
        text=text,
        meta={"suffix": p.suffix.lower(), "size": len(text)},
    )


def load_directory(root: str | Path) -> list[Document]:
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    docs: list[Document] = []
    for p in sorted(root_path.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            docs.append(load_file(p))
    return docs
