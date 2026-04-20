"""构建图、路由函数和应用程序单例。"""
from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from graph.nodes import generate_no_context, generate_with_context, retrieve_node
from graph.state import GraphState


# ── routing functions 路由函数 ───────────────────────

def should_retrieve(state: GraphState) -> str:
    """入口路由：当没有file_id时跳过检索。"""
    return "retrieve" if state.get("file_id") else "generate_no_context"


def route_after_retrieve(state: GraphState) -> str:
    """后检索路由：根据分支选择生成变体。"""
    return (
        "generate_with_context"
        if state.get("branch") == "with_context"
        else "generate_no_context"
    )


# ── graph construction 图构造 ──────────────────────────────────────────────

def build_graph() -> StateGraph:
    """构造RAG状态图（尚未编译）。"""
    builder = StateGraph(GraphState)

    builder.add_node("retrieve", retrieve_node)
    builder.add_node("generate_with_context", generate_with_context)
    builder.add_node("generate_no_context", generate_no_context)

    builder.add_conditional_edges(
        "__start__",
        should_retrieve,
        {"retrieve": "retrieve", "generate_no_context": "generate_no_context"},
    )

    builder.add_conditional_edges(
        "retrieve",
        route_after_retrieve,
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
