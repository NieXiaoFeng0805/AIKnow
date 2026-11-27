"""文档加载：把本地文件读成 Document。

具体格式交给 ingest/parsers.py，这里只负责遍历、过滤与按分区扫描。
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from ingest.model import Document, doc_id_for, source_type_for
from ingest.zones import Zone

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".pdf", ".docx"}


def load_file(path: str | Path, zone_id: str, source_type: str | None = None) -> Document:
    from ingest.parsers import parse_file

    p = Path(path)
    if p.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError(f"暂不支持的文件类型: {p.suffix} ({p})")
    return parse_file(p, zone_id, source_type=source_type)


def load_directory(root: str | Path, zone_id: str) -> list[Document]:
    root_path = Path(root)
    if not root_path.is_dir():
        raise NotADirectoryError(str(root_path))
    docs: list[Document] = []
    for p in sorted(root_path.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_SUFFIXES:
            docs.append(load_file(p, zone_id))
    return docs


def load_all_zones(
    zones: Mapping[str, Zone], base: str | Path = "."
) -> tuple[list[Document], list[str]]:
    """按 zones.toml 的 sources 扫描全部分区。

    返回 (文档, 缺失目录说明)。sources 相对 base（CLI 传 zones.toml 所在目录）。
    """
    base_path = Path(base)
    docs: list[Document] = []
    missing: list[str] = []
    for zone in zones.values():
        for src in zone.sources:
            root = base_path / src
            if not root.is_dir():
                missing.append(f"{zone.zone_id}: {root}")
                continue
            docs.extend(load_directory(root, zone.zone_id))
    return docs, missing


__all__ = [
    "SUPPORTED_SUFFIXES",
    "Document",
    "doc_id_for",
    "load_all_zones",
    "load_directory",
    "load_file",
    "source_type_for",
]
