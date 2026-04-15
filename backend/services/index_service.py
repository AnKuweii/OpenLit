"""索引服务：将 Markdown 文本转换为 FAISS 索引"""
from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any, Optional

from langchain_text_splitters import MarkdownHeaderTextSplitter
from langchain.docstore.document import Document
from langchain_community.vectorstores import FAISS

from model import get_embeddings
from config import patch_paddleocr_langchain, workdir
patch_paddleocr_langchain() # 修补 paddle ocr 与 langchain 的兼容性问题


def markdown_path(file_id: str) -> Path:
    return workdir(file_id) / "output.md"

def index_dir(file_id: str) -> Path:
    p = workdir(file_id) / "index_faiss"
    p.mkdir(parents=True, exist_ok=True)
    return p

def split_markdown(md_text: str) -> List[Document]:
    """索引前的拆分处理（Chunking） 按语义拆分将每个标题层级都是一个独立的Chunk"""
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3")
    ]
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    docs = splitter.split_text(md_text)
    return clean_chunks(docs)

def clean_chunks(docs: List[Document]) -> List[Document]:
    """清洗拆分后的Chunk"""
    cleaned = []
    for d in docs:
        txt = (d.page_content or "").strip()
        if not txt:
            continue
        cleaned.append(Document(page_content=txt, metadata=d.metadata))
    return cleaned

def build_faiss_index(file_id: str) -> Dict[str, Any]:
    """Markdown 文本 → 嵌入向量 → FAISS 索引（Indexing）"""
    md_file = markdown_path(file_id)
    if not md_file.exists():
        return {"ok": False, "error": "MARKDOWN_NOT_FOUND"}
    md_text = md_file.read_text(encoding="utf-8")

    docs = split_markdown(md_text)
    if not docs:
        return {"ok": False, "error": "EMPTY_MD"}

    embeddings = get_embeddings()
    vs = FAISS.from_documents(docs, embedding=embeddings)
    vs.save_local(str(index_dir(file_id)))
    return {"ok": True, "chunks": len(docs)}

def search_faiss(file_id: str, query: str, k: int = 5) -> Dict[str, Any]:
    """FAISS 索引 → 相似度搜索（Retrieval）返回 Top-K 结果"""
    idx = index_dir(file_id)
    if not (idx / "index.faiss").exists():
        return {"ok": False, "error": "INDEX_NOT_FOUND"}

    embeddings = get_embeddings()
    vs = FAISS.load_local(str(idx), embeddings, allow_dangerous_deserialization=True)
    hits = vs.similarity_search_with_score(query, k=k)
    results = []
    for doc, score in hits:
        results.append({
            "text": doc.page_content,
            "score": float(score),
            "metadata": doc.metadata,
        })
    return {"ok": True, "results": results}
