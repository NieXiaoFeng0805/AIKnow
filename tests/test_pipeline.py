"""切分与检索的最小回归测试。"""

from __future__ import annotations

from pathlib import Path

from ingest.loader import load_directory, load_file
from pipeline.chunker import chunk_document
from retrieval.index import KnowledgeIndex

FIXTURES = Path(__file__).parent / "fixtures" / "kb"


def test_chunk_keeps_heading_path():
    doc = load_file(FIXTURES / "报销制度.md", "life")
    chunks = chunk_document(doc)
    assert chunks
    assert any("差旅费" in c.heading_path for c in chunks)
    assert all(c.chunk_id.startswith(doc.doc_id) for c in chunks)


def test_table_is_separate_chunk():
    doc = load_file(FIXTURES / "报销制度.md", "life")
    tables = [c for c in chunk_document(doc) if c.kind == "table"]
    assert len(tables) == 1
    assert "一线城市" in tables[0].text
    assert "600" in tables[0].text


def test_offsets_are_monotonic():
    doc = load_file(FIXTURES / "请假规定.md", "life")
    chunks = chunk_document(doc)
    assert all(c.start < c.end for c in chunks)
    assert [c.start for c in chunks] == sorted(c.start for c in chunks)


def test_search_returns_relevant_source():
    idx = KnowledgeIndex.from_directory(str(FIXTURES), "life")
    hits = idx.search("一线城市住宿上限是多少", "life", k=3)
    assert hits
    assert "报销制度" in hits[0].chunk.meta["source"]
    assert "600" in "".join(h.chunk.text for h in hits)


def test_search_no_hit_returns_empty():
    idx = KnowledgeIndex.from_directory(str(FIXTURES), "life")
    assert idx.search("量子纠缠退相干时间", "life", k=3) == []


def test_loader_filters_unsupported(tmp_path: Path):
    (tmp_path / "a.md").write_text("# A\n内容", encoding="utf-8")
    (tmp_path / "b.xyz").write_bytes(b"binary")
    docs = load_directory(tmp_path, "life")
    assert [d.path for d in docs] == [str(tmp_path / "a.md")]
