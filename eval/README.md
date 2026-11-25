# eval — 黄金集与回归评测

职责：让“变好了”可被证明。

## 黄金集

`eval/golden/*.jsonl`，每行：

```json
{"q": "问题", "answer": "标准答案", "evidence": ["chunk_id"], "type": "lookup|multi-hop|numeric|unanswerable"}
```

规模目标 100–300 条，按真实问题分布配比，必须含“该拒答”的样本。

## 指标

| 侧 | 指标 |
|---|---|
| 检索 | Recall@k、MRR、上下文命中率 |
| 生成 | 忠实度、引用准确率、答案正确率、拒答正确率 |
| 图谱 | 三元组准确率、实体重复率、多跳命中率 |

## 规则

- 换模型、换切分、换 prompt，都必须跑同一套回归。
- 线上点踩与 badcase 定期回流进黄金集。
