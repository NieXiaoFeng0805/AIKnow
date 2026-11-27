"""文档模型。

文档带 zone_id（分区）与 source_type（来源类型），二者都是索引的一等维度。
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

NOTE = "note"
DOCUMENT = "doc"
SOURCE_TYPES = (NOTE, DOCUMENT)

_TEXT_SUFFIXES = {".md", ".markdown", ".txt"}


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: str
    title: str
    text: str
    zone_id: str
    source_type: str = NOTE
    meta: dict = field(default_factory=dict)


def source_type_for(path: Path | str) -> str:
    return NOTE if Path(path).suffix.lower() in _TEXT_SUFFIXES else DOCUMENT


def doc_id_for(zone_id: str, path: Path | str, text: str) -> str:
    """doc_id 含 zone_id：同一份文件放进不同分区是两份不同的文档。"""
    h = hashlib.sha256()
    h.update(zone_id.encode("utf-8"))
    h.update(b"\0")
    h.update(str(path).encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]
