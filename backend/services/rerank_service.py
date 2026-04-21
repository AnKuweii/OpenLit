"""重排序：使用预加载的 HuggingFaceCrossEncoder 对候选文档精细排序。"""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from config import RERANKER_TOP_N
from model import get_reranker

logger = logging.getLogger(__name__)


async def rerank(
    query: str,
    documents: list[Any],
    top_n: int | None = None,
) -> list[Any]:
    """
    使用本地 HuggingFaceCrossEncoder 对候选文档进行重排序。
    对每个 (query, doc) 对计算相关性分数，按分数降序取 top_n 篇返回。
    """
    if not documents:
        return documents

    top_n = min(top_n or RERANKER_TOP_N, len(documents))

    texts = [(doc.page_content or "").strip() for doc in documents]
    text_pairs = [(query, text) for text in texts]

    try:
        encoder = get_reranker()
        scores: list[float] = await asyncio.to_thread(encoder.score, text_pairs)

        scored = sorted(
            zip(scores, range(len(documents))),
            key=lambda x: x[0],
            reverse=True,
        )

        reranked = [documents[idx] for score, idx in scored[:top_n]]

        logger.info(
            "[Reranker] reranked %d → %d docs, top score=%.4f",
            len(documents),
            len(reranked),
            scored[0][0] if scored else 0,
        )
        return reranked

    except Exception as e:
        logger.error("[Reranker] scoring failed: %s", e)
        return documents
