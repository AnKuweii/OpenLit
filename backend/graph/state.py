"""LangGraph 全局状态定义。"""
from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class GraphState(TypedDict):
    """所有数据流动通过RAG图的State字段。"""

    question: str # 用户问题
    file_id: str # 文件ID
    needs_retrieve: bool # 路由器判定是否需要检索
    raw_docs: list # 混合检索原始文档（retrieve → rerank 中间态）
    citations: list[dict] # 引用列表
    context_text: str # 上下文文本
    branch: str  # "with_context" | "no_context"
    response: str # 响应文本
    messages: Annotated[list, add_messages] # 消息列表
