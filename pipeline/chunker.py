"""按 Markdown 结构切分文档。

原则（对齐 docs/decision/0001、0002）：
- 优先按标题层级切，chunk 保留 heading_path
- 表格单独成块，不与正文混切
- 超长段落在句末切分，带少量重叠
- 保留字符偏移，便于引用回链
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ingest.loader import Document

MAX_CHARS = 600
MIN_CHARS = 30
OVERLAP = 80

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_SENT_SPLIT = re.compile(r"(?<=[。！？!?；;])|(?<=\.)\s+")


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    text: str
    heading_path: tuple[str, ...] = ()
    start: int = 0
    end: int = 0
    kind: str = "text"  # text | table
    zone_id: str = ""
    meta: dict = field(default_factory=dict)


@dataclass
class _Block:
    text: str
    heading_path: tuple[str, ...]
    start: int
    end: int
    kind: str


def _split_long(text: str, limit: int = MAX_CHARS, overlap: int = OVERLAP) -> list[str]:
    if len(text) <= limit:
        return [text]
    parts = [s for s in _SENT_SPLIT.split(text) if s]
    out: list[str] = []
    buf = ""
    for s in parts:
        if len(buf) + len(s) <= limit:
            buf += s
            continue
        if buf:
            out.append(buf)
        buf = s if len(s) <= limit else ""
        if len(s) > limit:
            # 单句仍超长：硬切
            for i in range(0, len(s), limit):
                out.append(s[i : i + limit])
    if buf:
        out.append(buf)

    merged: list[str] = []
    for piece in out:
        if merged and len(merged[-1]) < MIN_CHARS:
            merged[-1] += piece
        else:
            merged.append(piece)
    if overlap > 0 and len(merged) > 1:
        merged = [merged[0]] + [merged[i - 1][-overlap:] + merged[i] for i in range(1, len(merged))]
    return merged


def _parse_blocks(doc: Document) -> list[_Block]:
    blocks: list[_Block] = []
    headings: list[tuple[int, str]] = []
    buf: list[str] = []
    buf_start = 0
    offset = 0
    kind = "text"

    def flush(end: int) -> None:
        nonlocal buf
        text = "".join(buf).strip()
        if text:
            blocks.append(
                _Block(
                    text=text,
                    heading_path=tuple(h for _, h in headings if h),
                    start=buf_start,
                    end=end,
                    kind=kind,
                )
            )
        buf = []

    for raw in doc.text.splitlines(keepends=True):
        line_start = offset
        offset += len(raw)
        line = raw.rstrip("\n")

        if line.startswith("|") and line.count("|") >= 2:
            if kind != "table":
                flush(line_start)
                kind = "table"
                buf_start = line_start
            buf.append(raw)
            continue

        m = _HEADING_RE.match(line)
        if m:
            flush(line_start)
            level = len(m.group(1))
            while headings and headings[-1][0] >= level:
                headings.pop()
            headings.append((level, m.group(2).strip()))
            kind = "text"
            buf_start = offset
            continue

        if kind == "table":
            flush(line_start)
            kind = "text"
            buf_start = line_start

        if not buf:
            buf_start = line_start
        buf.append(raw)

    flush(offset)
    return blocks


def chunk_document(doc: Document) -> list[Chunk]:
    chunks: list[Chunk] = []
    for b_idx, block in enumerate(_parse_blocks(doc)):
        pieces = [block.text] if block.kind == "table" else _split_long(block.text)
        cursor = block.start
        for p_idx, piece in enumerate(pieces):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc.doc_id}-{b_idx:03d}-{p_idx:02d}",
                    doc_id=doc.doc_id,
                    text=piece,
                    heading_path=block.heading_path,
                    start=cursor,
                    end=cursor + len(piece),
                    kind=block.kind,
                    zone_id=doc.zone_id,
                    meta={
                        "source": doc.path,
                        "title": doc.title,
                        "zone": doc.zone_id,
                        "source_type": doc.source_type,
                        "date": doc.meta.get("date", ""),
                    },
                )
            )
            cursor += len(piece)
    return chunks
