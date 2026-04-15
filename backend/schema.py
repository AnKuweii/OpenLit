"""API 请求/响应相关的 Pydantic 模型。"""
from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """chat路由中的对话请求体"""
    message: str
    sessionId: Optional[str] = None
    pdfFileId: Optional[str] = None


class ClearChatRequest(BaseModel):
    """chat路由中的清空对话请求体"""
    sessionId: Optional[str] = None


class PdfParseRequest(BaseModel):
    """pdf路由中的解析请求体"""
    fileId: str


class BuildIndexRequest(BaseModel):
    """pdf路由中的构建索引请求体"""
    fileId: str


class SearchRequest(BaseModel):
    """pdf路由中的相似检索请求体"""
    fileId: str
    query: str
    k: Optional[int] = 5
