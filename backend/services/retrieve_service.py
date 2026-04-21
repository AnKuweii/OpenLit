"""检索服务：纯能力层，提供混合检索、评分、引用构建等原子操作。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_classic.retrievers import EnsembleRetriever
from langchain_community.retrievers import BM25Retriever
from langchain_community.vectorstores import FAISS

from config import RECALL_K, SCORE_TAU_MEAN3, SCORE_TAU_TOP1
from model import get_embeddings
from services.index_service import markdown_path, split_markdown


def vector_store_dir(file_id: str) -> Path:
    return Path("data") / file_id / "index_faiss"


def load_vector_store(file_id: str) -> FAISS:
    vs_path = vector_store_dir(file_id)
    idx_file = vs_path / "index.faiss"
    if not idx_file.exists():
        raise FileNotFoundError(f"FAISS index not found at {vs_path}; build index first.")
    return FAISS.load_local(
        str(vs_path),
        get_embeddings(),
        allow_dangerous_deserialization=True,
    )


def load_bm25_documents(file_id: str) -> list[Any]:
    md_file = markdown_path(file_id)
    if not md_file.exists():
        raise FileNotFoundError(f"Markdown not found at {md_file}; parse pdf first.")
    md_text = md_file.read_text(encoding="utf-8")
    return split_markdown(md_text)


def score_ok(scores: list[float]) -> bool:
    if not scores:
        return False
    top1 = scores[0]
    mean3 = sum(scores[:3]) / min(3, len(scores))
    return (top1 <= SCORE_TAU_TOP1) or (mean3 <= SCORE_TAU_MEAN3)


def build_hybrid_retriever(file_id: str, vector_store: FAISS | None = None, recall_k: int = RECALL_K) -> EnsembleRetriever:
    vector_store = vector_store or load_vector_store(file_id)
    vector_retriever = vector_store.as_retriever(search_kwargs={"k": recall_k})

    bm25_documents = load_bm25_documents(file_id)
    bm25_retriever = BM25Retriever.from_documents(bm25_documents)
    bm25_retriever.k = recall_k

    return EnsembleRetriever(
        retrievers=[vector_retriever, bm25_retriever],
        weights=[0.8, 0.2],
    )


def build_doc_key(doc: Any) -> tuple[str, tuple[tuple[str, str], ...]]:
    metadata = tuple(sorted((str(k), str(v)) for k, v in (doc.metadata or {}).items()))
    return ((doc.page_content or "").strip(), metadata)


def build_vector_score_map(vector_hits: list[tuple[Any, float]]) -> dict[tuple[str, tuple[tuple[str, str], ...]], float]:
    score_map: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
    for doc, score in vector_hits:
        key = build_doc_key(doc)
        value = float(score)
        previous = score_map.get(key)
        if previous is None or value < previous:
            score_map[key] = value
    return score_map


def build_citations(file_id: str, docs: list[Any], score_map: dict[tuple[str, tuple[tuple[str, str], ...]], float]) -> tuple[list[dict], str, list[float]]:
    citations: list[dict] = []
    ctx_snippets: list[str] = []
    scores: list[float] = []

    for i, doc in enumerate(docs, start=1):
        snippet_short = (doc.page_content or "").strip()
        if len(snippet_short) > 500:
            snippet_short = snippet_short[:500] + "..."

        page = doc.metadata.get("page") or doc.metadata.get("page_number")
        score = score_map.get(build_doc_key(doc), float("inf"))

        citations.append(
            {
                "citation_id": f"{file_id}-c{i}",
                "fileId": file_id,
                "rank": i,
                "page": page,
                "snippet": (doc.page_content or "")[:4000],
                "score": score,
                "previewUrl": f"/api/v1/pdf/page?fileId={file_id}&page={(page or 1)}&type=original",
            }
        )
        ctx_snippets.append(f"[{i}] {snippet_short}")
        scores.append(score)

    context_text = "\n\n".join(ctx_snippets) if ctx_snippets else "(no hits)"
    return citations, context_text, scores
