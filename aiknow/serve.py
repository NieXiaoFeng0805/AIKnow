"""本地页面：分区检索的只读 Web UI + JSON 接口。

只用 stdlib（http.server + json），不引框架、不建前端构建链（见 README「页面」）。
接口同时是将来挂到 DSH 面板上的那一层。
"""

from __future__ import annotations

import json
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from ingest.loader import Document, load_all_zones
from ingest.zones import load_zones, require_zone
from retrieval.index import KnowledgeIndex

SERVER_VERSION = "aiknow/0.2"
WEB_DIR = Path(__file__).with_name("web")
STATIC_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
}
STATIC_FILES = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
MAX_K = 50


class KnowledgeApp:
    """页面背后的状态：分区注册表 + 文档 + 索引，reindex 时整体重建。"""

    def __init__(self, config: str | Path = "zones.toml", base: str | Path | None = None) -> None:
        self.config = Path(config)
        self.base = Path(base) if base is not None else self.config.resolve().parent
        self.zones = {}
        self.documents: dict[tuple[str, str], Document] = {}
        self.missing: list[str] = []
        self.index = KnowledgeIndex([])
        self.reload()

    def reload(self) -> None:
        self.zones = load_zones(self.config)
        docs, missing = load_all_zones(self.zones, self.base)
        self.documents = {(d.zone_id, d.doc_id): d for d in docs}
        self.missing = missing
        self.index = KnowledgeIndex.from_documents(docs)

    def zones_payload(self) -> list[dict]:
        counts = self.index.count_by_zone()
        out = []
        for zone in self.zones.values():
            documents, chunks = counts.get(zone.zone_id, (0, 0))
            out.append(
                {
                    "id": zone.zone_id,
                    "name": zone.name,
                    "purpose": zone.purpose,
                    "sources": list(zone.sources),
                    "documents": documents,
                    "chunks": chunks,
                    "missing": [m for m in self.missing if m.startswith(zone.zone_id + ":")],
                }
            )
        return out

    def search_payload(
        self,
        question: str,
        zone: str | None,
        zones: list[str] | None,
        since: str | None,
        k: int,
    ) -> dict:
        hits = self.index.search(question, zone=zone, k=k, since=since, zones=zones)
        payload = []
        for hit in hits:
            chunk = hit.chunk
            doc = self.documents.get((chunk.zone_id, chunk.doc_id))
            payload.append(
                {
                    "score": round(hit.score, 4),
                    "zone": chunk.zone_id,
                    "zone_name": self.zones[chunk.zone_id].name
                    if chunk.zone_id in self.zones
                    else chunk.zone_id,
                    "title": (doc.title if doc else chunk.meta.get("title", "")),
                    "source": chunk.meta.get("source", ""),
                    "heading_path": list(chunk.heading_path),
                    "text": chunk.text,
                    "kind": chunk.kind,
                    "date": chunk.meta.get("date", ""),
                    "doc_id": chunk.doc_id,
                    "chunk_id": chunk.chunk_id,
                    "start": chunk.start,
                    "end": chunk.end,
                }
            )
        return {"query": question, "count": len(payload), "hits": payload}

    def doc_payload(self, zone: str, doc_id: str) -> dict | None:
        doc = self.documents.get((zone, doc_id))
        if doc is None:
            return None
        chunks = [
            {
                "chunk_id": c.chunk_id,
                "heading_path": list(c.heading_path),
                "text": c.text,
                "start": c.start,
                "end": c.end,
                "kind": c.kind,
            }
            for c in self.index.chunks
            if c.zone_id == zone and c.doc_id == doc_id
        ]
        chunks.sort(key=lambda c: c["start"])
        return {
            "zone": zone,
            "doc_id": doc_id,
            "title": doc.title,
            "path": doc.path,
            "source_type": doc.source_type,
            "date": doc.meta.get("date", ""),
            "backend": doc.meta.get("backend", ""),
            "text": doc.text,
            "chunks": chunks,
        }


def _read_query(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    return {k: v[-1] for k, v in parsed.items()}


def make_handler(app: KnowledgeApp) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = SERVER_VERSION

        def log_message(self, fmt: str, *args) -> None:
            return

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, payload: dict | list, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self._send(body, "application/json; charset=utf-8", status)

        def _fail(self, message: str, status: int = HTTPStatus.BAD_REQUEST) -> None:
            self._json({"error": message}, status)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path in STATIC_FILES:
                self._serve_static(STATIC_FILES[parsed.path])
                return
            params = _read_query(parsed.query)
            if parsed.path == "/api/zones":
                self._json(app.zones_payload())
                return
            if parsed.path == "/api/search":
                self._handle_search(params)
                return
            if parsed.path == "/api/doc":
                self._handle_doc(params)
                return
            self._fail("没有这个接口: " + parsed.path, HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path != "/api/reindex":
                self._fail("没有这个接口: " + parsed.path, HTTPStatus.NOT_FOUND)
                return
            app.reload()
            zones = app.zones_payload()
            self._json(
                {
                    "documents": sum(z["documents"] for z in zones),
                    "chunks": sum(z["chunks"] for z in zones),
                    "zones": zones,
                }
            )

        def _serve_static(self, name: str) -> None:
            path = WEB_DIR / name
            if not path.is_file():
                self._fail("缺少静态文件: " + name, HTTPStatus.NOT_FOUND)
                return
            content_type = STATIC_TYPES.get(path.suffix, "application/octet-stream")
            self._send(path.read_bytes(), content_type)

        def _handle_search(self, params: dict[str, str]) -> None:
            question = (params.get("q") or "").strip()
            if not question:
                self._fail("缺少 q（要检索的问题）")
                return
            zone = (params.get("zone") or "").strip() or None
            zones_raw = (params.get("zones") or "").strip()
            zones = [z.strip() for z in zones_raw.split(",") if z.strip()] or None
            if zones is None and zone is None:
                self._fail("必须指定 zone（跨区用 zones=life,work）")
                return
            for zone_id in zones or [zone]:
                try:
                    require_zone(app.zones, zone_id)
                except ValueError as exc:
                    self._fail(str(exc))
                    return
            try:
                k = int(params.get("k") or 5)
            except ValueError:
                self._fail("k 必须是整数")
                return
            k = max(1, min(k, MAX_K))
            try:
                payload = app.search_payload(question, zone, zones, params.get("since"), k)
            except ValueError as exc:
                self._fail(str(exc))
                return
            self._json(payload)

        def _handle_doc(self, params: dict[str, str]) -> None:
            zone = (params.get("zone") or "").strip()
            doc_id = (params.get("doc_id") or "").strip()
            if not zone or not doc_id:
                self._fail("缺少 zone 或 doc_id")
                return
            payload = app.doc_payload(zone, doc_id)
            if payload is None:
                self._fail("找不到这份文档", HTTPStatus.NOT_FOUND)
                return
            self._json(payload)

    return Handler


def make_server(
    app: KnowledgeApp, host: str = "127.0.0.1", port: int = 8000
) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(app))
    return server


def serve(
    config: str = "zones.toml",
    host: str = "127.0.0.1",
    port: int = 8000,
    open_browser: bool = False,
) -> int:
    app = KnowledgeApp(config)
    server = make_server(app, host, port)
    actual_port = server.server_address[1]
    url = f"http://{host}:{actual_port}/"
    zones = app.zones_payload()
    total = sum(z["documents"] for z in zones)
    print(f"AIKnow 页面: {url}")
    print(f"分区 {len(zones)} 个，文档 {total} 篇；Ctrl-C 停止")
    if app.missing:
        print("缺目录（未扫描）: " + "；".join(app.missing))
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("已停止")
    finally:
        server.server_close()
    return 0
