"""分区（zone）回归测试：对齐 docs/design-v3 §10 的八项验收。"""

from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from aiknow.__main__ import main
from ingest.loader import load_file
from ingest.model import source_type_for
from ingest.zones import load_zones, require_zone
from pipeline.chunker import chunk_document
from retrieval.index import KnowledgeIndex

FIXTURES = Path(__file__).parent / "fixtures" / "kb"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _registry(root: Path) -> Path:
    cfg = root / "zones.toml"
    cfg.write_text(
        '[zones.life]\nname = "生活区"\npurpose = "日常"\nsources = ["kb/life"]\n\n'
        '[zones.work]\nname = "工作区"\npurpose = "工作"\nsources = ["kb/work"]\n',
        encoding="utf-8",
    )
    return cfg


def test_registry_loads_and_rejects_unknown_zone(tmp_path: Path):
    zones = load_zones(_registry(tmp_path))
    assert sorted(zones) == ["life", "work"]
    assert zones["life"].name == "生活区"
    assert zones["life"].sources == ("kb/life",)
    with pytest.raises(ValueError) as err:
        require_zone(zones, "nope")
    assert "未知分区" in str(err.value)
    assert "life" in str(err.value)


def test_same_file_in_two_zones_gets_different_doc_id(tmp_path: Path):
    p = _write(tmp_path / "共享.md", "# 标题\n同一份正文")
    life = load_file(p, "life")
    work = load_file(p, "work")
    assert life.doc_id != work.doc_id
    assert (life.zone_id, work.zone_id) == ("life", "work")


def test_chunk_points_back_to_zone():
    doc = load_file(FIXTURES / "报销制度.md", "life")
    chunks = chunk_document(doc)
    assert chunks
    assert all(c.zone_id == "life" for c in chunks)
    assert all(c.meta["zone"] == "life" for c in chunks)


def test_source_type_follows_format(tmp_path: Path):
    assert source_type_for(tmp_path / "a.md") == "note"
    assert source_type_for(tmp_path / "a.pdf") == "doc"


def test_search_requires_zone():
    idx = KnowledgeIndex.from_directory(str(FIXTURES), "life")
    with pytest.raises(ValueError):
        idx.search("一线城市住宿上限是多少")


def test_no_cross_zone_leak(tmp_path: Path):
    _write(tmp_path / "kb/life/notes.md", "# 生活\n周末想去爬山，顺便买顶帐篷。")
    _write(tmp_path / "kb/work/notes.md", "# 工作\n周末要交项目周报，爬山的事先放一放。")
    zones = load_zones(_registry(tmp_path))
    idx = KnowledgeIndex.from_zones(zones, str(tmp_path))
    hits = idx.search("周末 爬山", "life", k=5)
    assert hits
    assert {h.zone_id for h in hits} == {"life"}
    assert all("周报" not in h.chunk.text for h in hits)


def test_cross_zone_is_explicit(tmp_path: Path):
    _write(tmp_path / "kb/life/notes.md", "# 生活\n周末想去爬山。")
    _write(tmp_path / "kb/work/notes.md", "# 工作\n周末要交项目周报。")
    zones = load_zones(_registry(tmp_path))
    idx = KnowledgeIndex.from_zones(zones, str(tmp_path))
    assert {h.zone_id for h in idx.search("周末", "life", k=5)} == {"life"}
    both = idx.search("周末", zones=["life", "work"], k=5)
    assert {h.zone_id for h in both} == {"life", "work"}


def test_since_filters_older_documents(tmp_path: Path):
    old = _write(tmp_path / "kb/life/old.md", "# 旧\n去年的一条记录。")
    _write(tmp_path / "kb/life/new.md", "# 新\n今天的一条记录。")
    long_ago = time.time() - 40 * 86400
    os.utime(old, (long_ago, long_ago))
    zones = load_zones(_registry(tmp_path))
    idx = KnowledgeIndex.from_zones(zones, str(tmp_path))
    since = (date.today() - timedelta(days=7)).isoformat()
    hits = idx.search("记录", "life", since=since, k=5)
    assert hits
    assert all(h.chunk.meta["date"] >= since for h in hits)
    assert all("old.md" not in h.chunk.meta["source"] for h in hits)


def test_cli_index_and_ask(tmp_path: Path, capsys):
    _write(tmp_path / "kb/life/报销.md", "# 报销\n一线城市住宿上限 600 元。")
    cfg = _registry(tmp_path)

    assert main(["index", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "life" in out and "文档 1 篇" in out

    assert main(["ask", "一线城市住宿上限", "--zone", "life", "--config", str(cfg)]) == 0
    out = capsys.readouterr().out
    assert "600" in out
    assert "[life]" not in out

    assert main(["ask", "一线城市住宿上限", "--config", str(cfg)]) == 2
    assert "必须指定 --zone" in capsys.readouterr().err

    assert main(["ask", "一线城市住宿上限", "--zone", "nope", "--config", str(cfg)]) == 2
    assert "未知分区" in capsys.readouterr().err
