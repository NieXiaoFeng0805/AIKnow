"""命令行：aiknow ask "问题" --zone life / aiknow serve。

分区驱动（docs/design-v3 §10）：ask 必须带 --zone；跨区必须显式 --zones。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ingest.zones import DEFAULT_ZONES_FILE, Zone, load_zones, require_zone
from retrieval.index import Hit, KnowledgeIndex


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        default=DEFAULT_ZONES_FILE,
        help=f"分区注册表（默认 {DEFAULT_ZONES_FILE}）",
    )


def _load(config: str) -> tuple[dict[str, Zone], Path] | None:
    try:
        zones = load_zones(config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"配置错误: {exc}", file=sys.stderr)
        return None
    return zones, Path(config).resolve().parent


def _print_hits(hits: list[Hit], tag_zone: bool) -> None:
    for i, hit in enumerate(hits, 1):
        tag = f"[{hit.zone_id}] " if tag_zone else ""
        print(f"[{i}] {tag}score={hit.score:.3f}  {hit.citation()}")
        heading = " > ".join(hit.chunk.heading_path)
        if heading:
            print(f"    章节: {heading}")
        print(f"    {hit.chunk.text[:160].replace(chr(10), ' ')}")


def _cmd_index(zones: dict[str, Zone], base: Path, only: str | None) -> int:
    if only is not None:
        try:
            require_zone(zones, only)
        except ValueError as exc:
            print(f"配置错误: {exc}", file=sys.stderr)
            return 2
        zones = {only: zones[only]}
    index = KnowledgeIndex.from_zones(zones, str(base))
    counts = index.count_by_zone()
    total_docs = total_chunks = 0
    for zone in zones.values():
        docs, chunks = counts.get(zone.zone_id, (0, 0))
        total_docs += docs
        total_chunks += chunks
        label = f"{zone.zone_id:<8}"
        print(f"{label}{zone.name}: 文档 {docs} 篇，切块 {chunks} 个")
    print(f"合计: 文档 {total_docs} 篇，切块 {total_chunks} 个")
    return 0


def _cmd_ask(zones: dict[str, Zone], base: Path, args: argparse.Namespace) -> int:
    wanted = [z.strip() for z in (args.zones or "").split(",") if z.strip()]
    cross = bool(wanted)
    if cross is False and not args.zone:
        print("必须指定 --zone（跨区检索用 --zones life,work）", file=sys.stderr)
        return 2
    if not cross:
        wanted = [args.zone]
    for zone_id in wanted:
        try:
            require_zone(zones, zone_id)
        except ValueError as exc:
            print(f"配置错误: {exc}", file=sys.stderr)
            return 2

    index = KnowledgeIndex.from_zones(zones, str(base))
    try:
        hits = index.search(
            args.question,
            zone=None if cross else args.zone,
            k=args.k,
            since=args.since,
            zones=wanted if cross else None,
        )
    except ValueError as exc:
        print(f"参数错误: {exc}", file=sys.stderr)
        return 2
    if not hits:
        print("没有命中任何证据。")
        return 1
    _print_hits(hits, tag_zone=cross)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiknow", description="本地知识库检索（分区驱动）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="在指定分区内检索证据")
    ask.add_argument("question", help="问题")
    ask.add_argument("--zone", help="分区 id（必填；跨区用 --zones）")
    ask.add_argument("--zones", help="跨区检索，逗号分隔，例如 life,work")
    ask.add_argument("--since", help="只看该日期（YYYY-MM-DD）之后的文档")
    ask.add_argument("-k", type=int, default=5, help="返回条数")
    _add_common(ask)

    index = sub.add_parser("index", help="按分区统计文档与切块")
    index.add_argument("--zone", help="只统计该分区")
    _add_common(index)

    live = sub.add_parser("serve", help="起本地页面（分区检索）")
    live.add_argument("--host", default="127.0.0.1", help="监听地址（默认只本机）")
    live.add_argument("--port", type=int, default=8000, help="端口（默认 8000）")
    live.add_argument("--open", action="store_true", help="启动后打开浏览器")
    _add_common(live)

    args = parser.parse_args(argv)
    if args.cmd == "serve":
        from aiknow.serve import serve

        return serve(args.config, args.host, args.port, args.open)

    loaded = _load(args.config)
    if loaded is None:
        return 2
    zones, base = loaded
    if args.cmd == "index":
        return _cmd_index(zones, base, args.zone)
    return _cmd_ask(zones, base, args)


if __name__ == "__main__":
    sys.exit(main())
