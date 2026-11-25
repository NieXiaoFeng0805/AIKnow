"""知识索引：文档 -> chunk -> BM25 检索 -> 带出处的证据。

对外只暴露 search(question, k) -> list[Hit]，后续接向量检索/rerank/图谱
都在这一层之内替换，调用方不变（见 ADR-0002）。
"""

from __future__ import annotations

from dataclasses import dataclass

from ingest.loader import Document, load_directory
from pipeline.chunker import Chunk, chunk_document
from retrieval.bm25 import BM25Index, tokenize


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float

    def citation(self) -> str:
        heading = " > ".join(self.chunk.heading_path) or self.chunk.meta.get("title", "")
        src = self.chunk.meta.get("source", "")
        return f"{src}#{heading}"


class KnowledgeIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self._bm25 = BM25Index([tokenize(c.text) for c in chunks])

    @classmethod
    def from_documents(cls, docs: list[Document]) -> KnowledgeIndex:
        chunks: list[Chunk] = []
        for d in docs:
            chunks.extend(chunk_document(d))
        return cls(chunks)

    @classmethod
    def from_directory(cls, root: str) -> KnowledgeIndex:
        return cls.from_documents(load_directory(root))

    def search(self, question: str, k: int = 5) -> list[Hit]:
        scores = self._bm25.scores(tokenize(question))
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        return [Hit(self.chunks[i], scores[i]) for i in ranked[:k] if scores[i] > 0]
