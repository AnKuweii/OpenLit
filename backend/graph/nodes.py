"""LangGraph图的节点函数。

每个节点遵循契约：(GraphState) -> dict  (部分状态更新)。
没有副作用，没有全局变量，没有 if/else 路由逻辑。
"""
from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from config import ANSWER_NO_CONTEXT, ANSWER_WITH_CONTEXT, SYSTEM_INSTRUCTION
from graph.state import GraphState
from model import get_llm
from services.retrieve_service import retrieve as do_retrieve


# ── retrieve 检索 ────────────────────────────────────────────────────────

async def retrieve_node(state: GraphState) -> dict:
    """调用混合检索器并生成引用和上下文文本。"""
    try:
        citations, context_text = await do_retrieve(
            state["question"], state["file_id"]
        )
    except FileNotFoundError:
        return {"citations": [], "context_text": "", "branch": "no_context"}

    return {
        "citations": citations,
        "context_text": context_text,
        "branch": "with_context" if context_text else "no_context",
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
        "messages": [
            HumanMessage(content=state["question"]),
            response,
        ],
    }
