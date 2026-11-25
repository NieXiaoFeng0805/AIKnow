"""命令行：python -m aiknow ask "问题" --dir <知识库目录>。"""

from __future__ import annotations

import argparse
import sys

from retrieval.index import KnowledgeIndex


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aiknow", description="本地知识库检索")
    sub = parser.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="检索问题相关证据")
    ask.add_argument("question", help="问题")
    ask.add_argument("--dir", default=".", help="知识库目录（默认当前目录）")
    ask.add_argument("-k", type=int, default=5, help="返回条数")

    sub.add_parser("index", help="统计目录下的文档与切块数量").add_argument(
        "--dir", default=".", help="知识库目录"
    )

    args = parser.parse_args(argv)

    if args.cmd == "index":
        idx = KnowledgeIndex.from_directory(args.dir)
        docs = {c.doc_id for c in idx.chunks}
        print(f"文档 {len(docs)} 篇，切块 {len(idx.chunks)} 个")
        return 0

    idx = KnowledgeIndex.from_directory(args.dir)
    hits = idx.search(args.question, k=args.k)
    if not hits:
        print("没有命中任何证据。")
        return 1
    for i, hit in enumerate(hits, 1):
        head = " > ".join(hit.chunk.heading_path)
        print(f"[{i}] score={hit.score:.3f}  {hit.citation()}")
        if head:
            print(f"    章节: {head}")
        print(f"    {hit.chunk.text[:160].replace(chr(10), ' ')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
