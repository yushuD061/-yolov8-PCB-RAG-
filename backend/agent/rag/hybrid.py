"""
RRF 多查询融合 — Reciprocal Rank Fusion 用于多路检索结果合并。

从 example/hybrid.py 提取 RRF 核心算法，适配当前 TF-IDF 单引擎架构。
与 rewriter 配合：rewriter 生成多个子查询 → 各自 TF-IDF 检索 → RRF 融合排序。

用法：
    from agent.rag.hybrid import multi_query_search, rrf_fuse

    fused = multi_query_search(engine._search, ["query1", "query2"], top_k=6)
    # 或直接用 rrf_fuse 手动控制：
    fused = rrf_fuse([hits1, hits2], k=60, top_k=6)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, List

if TYPE_CHECKING:
    from agent.rag.rag_engine import RetrievalHit

logger = logging.getLogger(__name__)

# 默认 RRF 常数（与 example/hybrid.py 一致）
DEFAULT_RRF_K = 60


def rrf_fuse(
    results_by_query: List[List[RetrievalHit]],
    k: int = DEFAULT_RRF_K,
    top_k: int = 0,
) -> List[RetrievalHit]:
    """Reciprocal Rank Fusion — 基于 rank 而非 raw score 的多路融合。

    输入多组检索结果，按 chunk.id 去重，每路按 rank 贡献 score = 1/(k + rank_i + 1)，
    聚合后按总分降序排列，返回 top_k。

    参数：
        results_by_query: 每组查询的检索结果列表（rank 顺序，第 0 条最相关）
        k:                RRF 常数（默认 60）
        top_k:            返回前 N 条（0 表示返回全部）
    返回：
        融合后的结果列表，score 替换为 RRF 总分，source 标记为 "tfidf+rrf"
    """
    if not results_by_query:
        return []

    # 过滤掉空结果组
    non_empty = [hits for hits in results_by_query if hits]
    if not non_empty:
        return []

    k = k if k > 0 else DEFAULT_RRF_K

    # 按稳定的文档/块标识聚合。Chroma 命中的本地 id 可能为 0，不能只用 chunk.id。
    id_to_result: dict[tuple, RetrievalHit] = {}
    rrf_scores: dict[tuple, float] = {}
    sources_seen = set()

    for query_results in non_empty:
        for rank, hit in enumerate(query_results):
            cid = (
                hit.chunk.doc_id,
                hit.chunk.chunk_index,
                hit.chunk.parent_content or hit.chunk.content,
            )
            rrf_scores[cid] = rrf_scores.get(cid, 0.0) + 1.0 / (k + rank + 1)
            sources_seen.add(hit.source)
            # 保留第一次出现的 result 引用（用于取 chunk 数据）
            if cid not in id_to_result:
                id_to_result[cid] = hit

    # 按 RRF 分降序排列
    sorted_ids = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    # 构建结果，替换 score 为 RRF 分
    out: List[RetrievalHit] = []
    for cid, score in sorted_ids:
        result = id_to_result[cid]
        result.score = round(score, 6)
        result.source = (
            "hybrid+rrf" if len(sources_seen) > 1 else f"{result.source}+rrf"
        )
        out.append(result)

    if top_k > 0 and len(out) > top_k:
        out = out[:top_k]

    logger.debug("RRF 融合: %d 组查询 → %d 个结果", len(non_empty), len(out))
    return out


def multi_query_search(
    search_fn: Callable[[str, int], List[RetrievalHit]],
    queries: List[str],
    top_k: int,
    rrf_k: int = DEFAULT_RRF_K,
) -> List[RetrievalHit]:
    """多路检索 + RRF 融合。

    对每个查询分别调用 search_fn 检索，结果汇总后做 RRF 融合。
    顺序执行（sklearn TfidfVectorizer.transform 非线程安全）。

    参数：
        search_fn: 检索函数，签名 (query: str, fetch_k: int) -> List[RetrievalHit]
        queries:   多个查询字符串
        top_k:     最终返回前 N 条
        rrf_k:     RRF 常数
    返回：
        融合排序后的结果列表
    """
    queries = [q for q in (queries or []) if q]
    if not queries:
        return []
    if len(queries) == 1:
        return search_fn(queries[0], top_k)

    fetch_k = max(top_k, 10)
    results_by_query: List[List[RetrievalHit]] = []
    for q in queries:
        hits = search_fn(q, fetch_k)
        results_by_query.append(hits)

    logger.info("多路检索: %d 个子查询 → 收集完成，开始 RRF 融合", len(queries))
    return rrf_fuse(results_by_query, k=rrf_k, top_k=top_k)
