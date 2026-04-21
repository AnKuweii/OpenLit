"""LangGraph 图的节点函数。"""
from __future__ import annotations

import asyncio
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from config import (
    ANSWER_NO_CONTEXT,
    ANSWER_WITH_CONTEXT,
    GRADE_PROMPT,
    K,
    RECALL_K,
    ROUTER_PROMPT,
    SYSTEM_INSTRUCTION,
)
from graph.state import GraphState
from model import get_grader, get_llm, get_router
from services.rerank_service import rerank
from services.retrieve_service import (
    build_citations,
    build_doc_key,
    build_hybrid_retriever,
    build_vector_score_map,
    load_vector_store,
    score_ok,
)

logger = logging.getLogger(__name__)

_NODE_TIMEOUT = 300  # 单节点最大执行秒数


# 1. query router 查询路由

async def router_node(state: GraphState) -> dict:
    """检索前优化：基于 LLM 判断用户问题是否需要检索文档。

    无 file_id 时直接跳过检索；有 file_id 时调用轻量模型分类。
    """
    file_id = (state.get("file_id") or "").strip()
    if not file_id:
        logger.info("[Router] no file_id → skip retrieve")
        return {"needs_retrieve": False}

    question = state["question"]
    async with asyncio.timeout(_NODE_TIMEOUT):
        router = get_router()
        prompt = ROUTER_PROMPT.format(query=question)
        response = await router.ainvoke([{"role": "user", "content": prompt}])

    decision = (response.content or "").strip().upper()
    needs = "NO_RETRIEVE" not in decision and "RETRIEVE" in decision
    logger.info("[Router] query=%r → decision=%s → needs_retrieve=%s", question, decision, needs)
    return {"needs_retrieve": needs}


# 2. retrieve 混合检索

async def retrieve_node(state: GraphState) -> dict:
    """检索时优化：BM25 + 向量混合召回，将 FAISS 距离嵌入文档元数据。"""
    file_id = state["file_id"]
    question = state["question"]

    try:
        async with asyncio.timeout(_NODE_TIMEOUT):
            vector_store = load_vector_store(file_id)
            hybrid = build_hybrid_retriever(file_id, vector_store=vector_store)
            raw_docs = hybrid.invoke(question)[:RECALL_K]

            vector_hits = vector_store.similarity_search_with_score(question, k=RECALL_K)
            score_map = build_vector_score_map(vector_hits)
            for doc in raw_docs:
                doc.metadata["_faiss_score"] = score_map.get(
                    build_doc_key(doc), float("inf")
                )
    except FileNotFoundError:
        logger.warning("[Retrieve] index not found for file_id=%s", file_id)
        return {"raw_docs": []}

    logger.info("[Retrieve] recalled %d docs for file_id=%s", len(raw_docs), file_id)
    return {"raw_docs": raw_docs}


# 3. rerank 重排序

async def rerank_node(state: GraphState) -> dict:
    """检索后优化（阶段一）：调用本地 CrossEncoder 对候选文档精细排序，构建引用。"""
    question = state["question"]
    file_id = state["file_id"]
    raw_docs = state.get("raw_docs") or []

    async with asyncio.timeout(_NODE_TIMEOUT):
        docs = await rerank(question, raw_docs, top_n=K)

    score_map = {
        build_doc_key(d): d.metadata.get("_faiss_score", float("inf"))
        for d in docs
    }
    citations, context_text, _ = build_citations(file_id, docs, score_map)

    logger.info("[Rerank] %d → %d docs", len(raw_docs), len(docs))
    return {"citations": citations, "context_text": context_text}


# 4. grade 相关性评分

async def grade_node(state: GraphState) -> dict:
    """检索后优化（阶段二）：阈值 + LLM 评分器判定上下文相关性，决定分支。"""
    citations = state.get("citations") or []
    context_text = state.get("context_text") or ""
    question = state["question"]

    scores = [c.get("score", float("inf")) for c in citations]

    if score_ok(scores):
        is_relevant = True
    else:
        async with asyncio.timeout(_NODE_TIMEOUT):
            grader = get_grader()
            prompt = GRADE_PROMPT.format(context=context_text, question=question)
            decision = await grader.ainvoke([{"role": "user", "content": prompt}])
        is_relevant = "yes" in (decision.content or "").lower()

    if is_relevant:
        logger.info("[Grade] context relevant → with_context")
        return {"branch": "with_context", "citations": citations}

    logger.info("[Grade] context not relevant → no_context")
    return {"branch": "no_context", "citations": [], "context_text": ""}


# 5. generate (with context) 生成（有上下文）

async def generate_with_context(state: GraphState) -> dict:
    """基于检索到的上下文生成答案。"""
    llm = get_llm()

    user_prompt = ANSWER_WITH_CONTEXT.format(
        question=state["question"], context=state["context_text"]
    )

    llm_messages = [SystemMessage(content=SYSTEM_INSTRUCTION)]
    llm_messages.extend(state.get("messages") or [])
    llm_messages.append(HumanMessage(content=user_prompt))

    response = await llm.ainvoke(llm_messages)

    return {
        "response": response.content,
        "branch": "with_context",
        "messages": [
            HumanMessage(content=state["question"]),
            response,
        ],
    }


# 6. generate (no context) 生成（无上下文）

async def generate_no_context(state: GraphState) -> dict:
    """从通用知识生成答案（没有检索到的上下文）。"""
    llm = get_llm()

    user_prompt = ANSWER_NO_CONTEXT.format(question=state["question"])

    llm_messages = [SystemMessage(content=SYSTEM_INSTRUCTION)]
    llm_messages.extend(state.get("messages") or [])
    llm_messages.append(HumanMessage(content=user_prompt))

    response = await llm.ainvoke(llm_messages)

    return {
        "response": response.content,
        "branch": "no_context",
        "citations": [],
        "context_text": "",
        "messages": [
            HumanMessage(content=state["question"]),
            response,
        ],
    }
