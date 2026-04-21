"""LangGraph图的节点函数。

每个节点遵循契约：(GraphState) -> dict  (部分状态更新)。
没有副作用，没有全局变量，没有 if/else 路由逻辑。
"""
from __future__ import annotations

import logging

from langchain_core.messages import HumanMessage, SystemMessage

from config import ANSWER_NO_CONTEXT, ANSWER_WITH_CONTEXT, ROUTER_PROMPT, SYSTEM_INSTRUCTION
from graph.state import GraphState
from model import get_llm, get_router
from services.retrieve_service import retrieve as do_retrieve

logger = logging.getLogger(__name__)


# ── query router 查询路由 ─────────────────────────────────────────────────

async def router_node(state: GraphState) -> dict:
    """Query Router：基于 LLM 判断用户问题是否需要检索文档。

    无 file_id 时直接跳过检索；有 file_id 时调用轻量模型分类。
    """
    file_id = (state.get("file_id") or "").strip()
    if not file_id:
        logger.info("[Router] no file_id → skip retrieve")
        return {"needs_retrieve": False}

    question = state["question"]
    router = get_router()
    prompt = ROUTER_PROMPT.format(query=question)
    response = await router.ainvoke([{"role": "user", "content": prompt}])
    decision = (response.content or "").strip().upper()

    needs = "NO_RETRIEVE" not in decision and "RETRIEVE" in decision
    logger.info("[Router] query=%r → decision=%s → needs_retrieve=%s", question, decision, needs)
    return {"needs_retrieve": needs}


# ── retrieve 检索 ────────────────────────────────────────────────────────

async def retrieve_node(state: GraphState) -> dict:
    """调用混合检索器并生成引用和上下文文本。"""
    try:
        citations, context_text = await do_retrieve(
            state["question"], state["file_id"]
        )
    except FileNotFoundError:
        return {"citations": [], "context_text": "", "branch": "no_context"}

    is_context_relevant = bool(context_text)
    return {
        "citations": citations if is_context_relevant else [],
        "context_text": context_text,
        "branch": "with_context" if is_context_relevant else "no_context",
    }


# ── generate (with context) 生成（有上下文） ────────────────────────────────────────

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


# ── generate (no context) 生成（无上下文） ──────────────────────────────────────────

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
