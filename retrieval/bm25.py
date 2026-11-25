"""纯 Python BM25，中文按字符二元组、英文按单词切分。

不依赖分词库，先跑通闭环；后续换成 jieba / 弹性检索只需替换 tokenize 与实现。
"""

from __future__ import annotations

import math
import re
from collections import Counter

_ASCII_WORD = re.compile(r"[a-z0-9_]+")
_CJK = re.compile(r"[\u4e00-\u9fff]+")


def tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens: list[str] = list(_ASCII_WORD.findall(text))
    for run in _CJK.findall(text):
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
    return tokens


class BM25Index:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.doc_freqs = [Counter(d) for d in docs]
        self.lengths = [len(d) for d in docs]
        self.avg_len = (sum(self.lengths) / len(docs)) if docs else 0.0
        self.df: Counter = Counter()
        for d in self.doc_freqs:
            self.df.update(d.keys())
        self.n = len(docs)

    def idf(self, term: str) -> float:
        df = self.df.get(term, 0)
        return math.log(1 + (self.n - df + 0.5) / (df + 0.5))

    def scores(self, query_tokens: list[str]) -> list[float]:
        q = [t for t in query_tokens if t in self.df]
        out = []
        for i, freqs in enumerate(self.doc_freqs):
            score = 0.0
            dl = self.lengths[i] or 1
            for t in q:
                f = freqs.get(t, 0)
                if f == 0:
                    continue
                denom = f + self.k1 * (1 - self.b + self.b * dl / (self.avg_len or 1))
                score += self.idf(t) * f * (self.k1 + 1) / denom
            out.append(score)
        return out
