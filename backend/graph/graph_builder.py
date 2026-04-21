"""构建图、路由函数和应用程序单例。"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from graph.nodes import (
    generate_no_context,
    generate_with_context,
    grade_node,
    rerank_node,
    retrieve_node,
    router_node,
)
from graph.state import GraphState


# ── routing functions 路由函数 ───────────────────────

def route_after_router(state: GraphState) -> str:
    """Router 后路由：根据 needs_retrieve 决定走检索还是直接生成。"""
    return "retrieve" if state.get("needs_retrieve") else "generate_no_context"


def route_after_retrieve(state: GraphState) -> str:
    """检索后路由：有文档则继续重排序，否则跳过直接生成。"""
    return "rerank" if state.get("raw_docs") else "generate_no_context"


def route_after_grade(state: GraphState) -> str:
    """评分后路由：根据上下文相关性选择生成变体。"""
    return (
        "generate_with_context"
        if state.get("branch") == "with_context"
        else "generate_no_context"
    )


# ── graph construction 图构造 ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    """构造 RAG 状态图（尚未编译）。"""
    builder = StateGraph(GraphState)

    builder.add_node("router", router_node)
    builder.add_node("retrieve", retrieve_node)
    builder.add_node("rerank", rerank_node)
    builder.add_node("grade", grade_node)
    builder.add_node("generate_with_context", generate_with_context)
    builder.add_node("generate_no_context", generate_no_context)

    builder.add_edge("__start__", "router")

    builder.add_conditional_edges(
        "router",
        route_after_router,
        {"retrieve": "retrieve", "generate_no_context": "generate_no_context"},
    )

    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
        {"rerank": "rerank", "generate_no_context": "generate_no_context"},
    )

    builder.add_edge("rerank", "grade")

    builder.add_conditional_edges(
        "grade",
        route_after_grade,
        {
            "generate_with_context": "generate_with_context",
            "generate_no_context": "generate_no_context",
        },
    )

    builder.add_edge("generate_with_context", END)
    builder.add_edge("generate_no_context", END)

    return builder


# ── singleton application 单例应用程序 ──────────────────────────────────────────

_checkpointer = MemorySaver()
_app = None


def get_app():
    """返回内存检查点编译后的图（只创建一次）。"""
    global _app
    if _app is None:
        _app = build_graph().compile(checkpointer=_checkpointer)
    return _app


def get_checkpointer() -> MemorySaver:
    """返回内存检查点。"""
    return _checkpointer


def get_mermaid() -> str:
    """返回Mermaid图表字符串进行图验证。"""
    return build_graph().compile().get_graph().draw_mermaid()
