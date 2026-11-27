"""知识索引：文档 -> chunk -> BM25 检索 -> 带出处的证据。

分区（zone）是一等维度：检索必须显式指定分区，跨区必须显式开闸
（docs/design-v3 §10 的 #4 与 #6）。对外仍是 search(...) -> list[Hit]，
换向量检索、rerank 或图谱都在这一层之内替换，调用方不变（ADR-0002）。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from ingest.loader import Document, load_all_zones, load_directory
from ingest.zones import Zone
from pipeline.chunker import Chunk, chunk_document
from retrieval.bm25 import BM25Index, tokenize


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float

    @property
    def zone_id(self) -> str:
        return self.chunk.zone_id

    def citation(self) -> str:
        heading = " > ".join(self.chunk.heading_path) or self.chunk.meta.get("title", "")
        src = self.chunk.meta.get("source", "")
        return f"{src}#{heading}"


def _as_date(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError(f"日期格式应为 YYYY-MM-DD: {value}") from exc


class KnowledgeIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._bm25 = BM25Index([tokenize(c.text) for c in chunks])

    @property
    def zone_ids(self) -> list[str]:
        return sorted({c.zone_id for c in self.chunks})

    def count_by_zone(self) -> dict[str, tuple[int, int]]:
        """每个分区 (文档数, 切块数)。"""
        docs: dict[str, set[str]] = {}
        chunks: dict[str, int] = {}
        for c in self.chunks:
            docs.setdefault(c.zone_id, set()).add(c.doc_id)
            chunks[c.zone_id] = chunks.get(c.zone_id, 0) + 1
        return {z: (len(docs[z]), chunks[z]) for z in docs}

    @classmethod
    def from_documents(cls, docs: Sequence[Document]) -> KnowledgeIndex:
        chunks: list[Chunk] = []
        for d in docs:
            chunks.extend(chunk_document(d))
        return cls(chunks)

    @classmethod
    def from_directory(cls, root: str, zone_id: str) -> KnowledgeIndex:
        return cls.from_documents(load_directory(root, zone_id))

    @classmethod
    def from_zones(cls, zones: Mapping[str, Zone], base: str = ".") -> KnowledgeIndex:
        docs, _missing = load_all_zones(zones, base)
        return cls.from_documents(docs)

    def search(
        self,
        question: str,
        zone: str | None = None,
        k: int = 5,
        since: str | date | None = None,
        zones: Sequence[str] | None = None,
    ) -> list[Hit]:
        """分区内检索。不传 zone 且不传 zones 直接报错：不允许默认全库。"""
        wanted = tuple(zones) if zones else ((zone,) if zone else ())
        if not wanted:
            raise ValueError("检索必须指定分区 zone（跨区请显式传 zones）")
        since_date = _as_date(since)
        scores = self._bm25.scores(tokenize(question))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[Hit] = []
        for i in ranked:
            if scores[i] <= 0:
                continue
            chunk = self.chunks[i]
            if chunk.zone_id not in wanted:
                continue
            if since_date is not None:
                doc_date = _as_date(chunk.meta.get("date"))
                if doc_date is None or doc_date < since_date:
                    continue
            hits.append(Hit(chunk, scores[i]))
            if len(hits) >= k:
                break
        return hits
