"""文档模型。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class Document:
    doc_id: str
    path: str
    title: str
    text: str
    meta: dict = field(default_factory=dict)


def doc_id_for(path: Path | str, text: str) -> str:
    h = hashlib.sha256()
    h.update(str(path).encode("utf-8"))
    h.update(b"\0")
    h.update(text.encode("utf-8"))
    return h.hexdigest()[:16]
