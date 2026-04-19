"""索引服务：将 Markdown 文本转换为 FAISS 索引"""
from __future__ import annotations
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from config import patch_paddleocr_langchain, workdir
patch_paddleocr_langchain() # 修补 paddle ocr 与 langchain 的兼容性问题

from langchain_text_splitters import MarkdownHeaderTextSplitter
# from langchain.docstore.document import Document
from langchain_classic.schema import Document
from langchain_community.vectorstores import FAISS

from model import get_embeddings


def markdown_path(file_id: str) -> Path:
    return workdir(file_id) / "output.md"

def index_dir(file_id: str) -> Path:
    p = workdir(file_id) / "index_faiss"
    p.mkdir(parents=True, exist_ok=True)
    return p

def split_markdown(md_text: str) -> List[Document]:
    """索引前的拆分处理（Chunking） 按语义拆分将每个标题层级都是一个独立的Chunk，并注入页码metadata"""
    # 先移除注释标记，记录页码映射
    page_markers = re.findall(r'<!-- PAGE (\d+) -->', md_text)
    md_text_clean = re.sub(r'<!-- PAGE \d+ -->', '', md_text)
    
    headers_to_split_on = [
        ("#", "Header 1"),
        ("##", "Header 2"),
        ("###", "Header 3")
    ]
    splitter = MarkdownHeaderTextSplitter(headers_to_split_on=headers_to_split_on)
    docs = splitter.split_text(md_text_clean)
    
    # 为每个 chunk 添加页码：通过在原始文本中查找该内容的位置
    for doc in docs:
        chunk_text = doc.page_content[:100]  # 用前100字符查找
        # 在原始文本中找这个 chunk 的位置
        pos = md_text.find(chunk_text)
        if pos >= 0:
            # 找这个位置之前最后一个 PAGE 标记
            before_text = md_text[:pos]
            matches = list(re.finditer(r'<!-- PAGE (\d+) -->', before_text))
            if matches:
                page_num = int(matches[-1].group(1))
                doc.metadata["page_number"] = page_num
    
    return clean_chunks(docs)

def clean_chunks(docs: List[Document]) -> List[Document]:
    """
    清洗 OCR 拆分后的 Markdown chunk：
    - 去除首尾空白
    - 过滤过短、无连续单词、由单字符空格分隔的脏数据
    """
    cleaned = []
    
    for doc in docs:
        text = (doc.page_content or "").strip()
        if not text:
            continue
        
        # 1. 长度过短（且不含有效连续字符）-> 丢弃
        if len(text) < 3:
            continue
        
        # 2. 检测是否包含连续字母/数字（至少 3 个字符）
        has_word = bool(re.search(r'[A-Za-z0-9]{3,}', text))
        if not has_word:
            # 如果没有连续字符，例如纯符号 "## @$%"，丢弃
            continue
        
        # 3. 检测“空格分隔的单字符”模式
        #    特征：去除空格后长度 > 10，但按空格切分后大部分 token 长度为 1
        tokens = text.split()
        if len(tokens) >= 5:
            single_char_tokens = sum(1 for t in tokens if len(t) == 1)
            # 如果超过 70% 的 token 都是单字符，认为是 OCR 碎片
            if single_char_tokens / len(tokens) > 0.7:
                continue
        
        # 通过所有检查，保留
        cleaned.append(Document(page_content=text, metadata=doc.metadata))
    
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
