"""页面接口回归：起真实 HTTP server，用 urllib 打接口。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

import pytest

from aiknow.serve import KnowledgeApp, make_server


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _app(tmp_path: Path) -> KnowledgeApp:
    _write(tmp_path / "kb/life/a.md", "# 生活\n周末想去爬山。")
    _write(tmp_path / "kb/work/b.md", "# 工作\n周末要交项目周报。")
    (tmp_path / "zones.toml").write_text(
        '[zones.life]\nname = "生活区"\nsources = ["kb/life"]\n\n'
        '[zones.work]\nname = "工作区"\nsources = ["kb/work"]\n',
        encoding="utf-8",
    )
    return KnowledgeApp(tmp_path / "zones.toml")


@pytest.fixture()
def base_url(tmp_path: Path):
    server = make_server(_app(tmp_path), "127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address[0], server.server_address[1]
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get_json(url: str) -> tuple[int, dict]:
    try:
        with urllib.request.urlopen(url, timeout=5) as res:
            return res.status, json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read().decode("utf-8"))


def _post_json(url: str) -> tuple[int, dict]:
    req = urllib.request.Request(url, method="POST", data=b"")
    with urllib.request.urlopen(req, timeout=5) as res:
        return res.status, json.loads(res.read().decode("utf-8"))


def test_page_is_served(base_url: str):
    with urllib.request.urlopen(base_url + "/", timeout=5) as res:
        body = res.read().decode("utf-8")
    assert res.status == 200
    assert "AIKnow" in body
    assert "/app.js" in body


def test_zones_api_reports_counts(base_url: str):
    status, data = _get_json(base_url + "/api/zones")
    assert status == 200
    by_id = {z["id"]: z for z in data}
    assert set(by_id) == {"life", "work"}
    assert by_id["life"]["documents"] == 1
    assert by_id["life"]["name"] == "生活区"
    assert by_id["life"]["sources"] == ["kb/life"]


def test_search_requires_zone(base_url: str):
    status, data = _get_json(base_url + "/api/search?" + urlencode({"q": "周末"}))
    assert status == 400
    assert "zone" in data["error"]


def test_search_is_zone_isolated(base_url: str):
    status, data = _get_json(base_url + "/api/search?" + urlencode({"q": "周末", "zone": "life"}))
    assert status == 200
    assert data["count"] == 1
    assert {h["zone"] for h in data["hits"]} == {"life"}
    assert "周报" not in data["hits"][0]["text"]


def test_search_cross_zone_lists_both(base_url: str):
    status, data = _get_json(
        base_url + "/api/search?" + urlencode({"q": "周末", "zones": "life,work"})
    )
    assert status == 200
    assert {h["zone"] for h in data["hits"]} == {"life", "work"}


def test_unknown_zone_is_rejected(base_url: str):
    status, data = _get_json(base_url + "/api/search?" + urlencode({"q": "周末", "zone": "nope"}))
    assert status == 400
    assert "未知分区" in data["error"]


def test_reindex_picks_up_new_document(base_url: str, tmp_path: Path):
    _write(tmp_path / "kb/study/c.md", "# 学习\n论文里的注意力机制。")
    (tmp_path / "zones.toml").write_text(
        (tmp_path / "zones.toml").read_text(encoding="utf-8")
        + '\n[zones.study]\nname = "学习区"\nsources = ["kb/study"]\n',
        encoding="utf-8",
    )
    status, data = _post_json(base_url + "/api/reindex")
    assert status == 200
    assert data["documents"] == 3
    assert {z["id"] for z in data["zones"]} == {"life", "work", "study"}


def test_doc_api_returns_text(base_url: str):
    _status, found = _get_json(base_url + "/api/search?" + urlencode({"q": "爬山", "zone": "life"}))
    hit = found["hits"][0]
    doc_url = base_url + "/api/doc?" + urlencode({"zone": "life", "doc_id": hit["doc_id"]})
    status, doc = _get_json(doc_url)
    assert status == 200
    assert doc["zone"] == "life"
    assert "爬山" in doc["text"]
    assert doc["chunks"]


def test_doc_api_404_for_missing(base_url: str):
    status, data = _get_json(base_url + "/api/doc?" + urlencode({"zone": "life", "doc_id": "nope"}))
    assert status == 404
    assert "找不到" in data["error"]
