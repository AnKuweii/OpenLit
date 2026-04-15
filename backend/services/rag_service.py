"""RAG 服务：检索 + 判定 + 生成"""
from __future__ import annotations
import os, asyncio, textwrap
from typing import List, Dict, Any, Tuple, AsyncGenerator
from typing_extensions import TypedDict

from langchain_community.vectorstores import FAISS
from collections import defaultdict

from model import get_embeddings, get_grader, get_llm
from config import (
    ANSWER_NO_CONTEXT,
    ANSWER_WITH_CONTEXT,
    GRADE_PROMPT,
    K,
    SCORE_TAU_MEAN3,
    SCORE_TAU_TOP1,
    SYSTEM_INSTRUCTION,
    patch_paddleocr_langchain
)
patch_paddleocr_langchain() # 修补 paddle ocr 与 langchain 的兼容性问题

# 存储结构：sessions[session_id] = [{"role":"user|assistant","content":"..."}...]
_sessions: dict[str, list[dict]] = defaultdict(list)

def get_history(session_id: str) -> list[dict]:
    return _sessions.get(session_id, [])

def append_history(session_id: str, role: str, content: str) -> None:
    _sessions[session_id].append({"role": role, "content": content})

def clear_history(session_id: str) -> None:
    _sessions.pop(session_id, None)

def _vs_dir(file_id: str) -> str:
    return os.path.join("data", file_id, "index_faiss")

def _load_vs(file_id: str) -> FAISS:
    vs_path = _vs_dir(file_id)
    idx_file = os.path.join(vs_path, "index.faiss")
    if not os.path.exists(idx_file):
        raise FileNotFoundError(f"FAISS index not found at {vs_path}; build index first.")
    return FAISS.load_local(vs_path, get_embeddings(), allow_dangerous_deserialization=True)

def _score_ok(scores: List[float]) -> bool:
    if not scores:
        return False
    top1 = scores[0]
    mean3 = sum(scores[:3]) / min(3, len(scores))
    return (top1 <= SCORE_TAU_TOP1) or (mean3 <= SCORE_TAU_MEAN3)

# ---------------- 主流程：检索 + 判定 + 生成 ----------------
async def retrieve(question: str, file_id: str) -> tuple[list[dict], str]:
    """
    返回 (citations, context_text)
    citations: [{citation_id, fileId, rank, page, snippet, score, previewUrl}]
    context_text: 供 LLM 使用的拼接上下文
    """
    vs = _load_vs(file_id)
    hits = vs.similarity_search_with_score(question, k=K)
    citations = []
    ctx_snippets = []
    scores = []
    for i, (doc, score) in enumerate(hits, start=1):
        snippet_short = (doc.page_content or "").strip()
        if len(snippet_short) > 500:
            snippet_short = snippet_short[:500] + "..."
        page = doc.metadata.get("page") or doc.metadata.get("page_number")
        citations.append({
            "citation_id": f"{file_id}-c{i}",
            "fileId": file_id,
            "rank": i,
            "page": page,
            "snippet": (doc.page_content or "")[:4000],
            "score": float(score),
            "previewUrl": f"/api/v1/pdf/page?fileId={file_id}&page={(page or 1)}&type=original",
        })
        ctx_snippets.append(f"[{i}] {snippet_short}")
        scores.append(float(score))
    context_text = "\n\n".join(ctx_snippets) if ctx_snippets else "(no hits)"

    # 规则 + LLM 复核
    ok_by_score = _score_ok(scores)
    if not ok_by_score:
        grader = get_grader()
        grade_prompt = GRADE_PROMPT.format(context=context_text, question=question)
        decision = await grader.ainvoke([{"role": "user", "content": grade_prompt}])
        ok_by_llm = "yes" in (decision.content or "").lower()
    else:
        ok_by_llm = True

    branch = "with_context" if ok_by_llm else "no_context"
    return citations, context_text if branch == "with_context" else ""

async def answer_stream(
    question: str,
    citations: list[dict],
    context_text: str,
    branch: str,
    session_id: str | None = None
) -> AsyncGenerator[dict, None]:
    """
    以增量事件的形式产出：
      {"type":"citation", "data": {...}}
      {"type":"token", "data": "text chunk"}
      {"type":"done", "data": {"used_retrieval": bool}}
    同时：如果提供了 session_id，会把本轮问答写入内存历史。
    """
    # 先把 citations 全部发给前端（便于角标立刻出现）
    if branch == "with_context" and citations:
        for c in citations:
            yield {"type": "citation", "data": c}

    # 组装“历史 + 本轮提示”
    llm = get_llm()
    history_msgs = get_history(session_id) if session_id else []

    if branch == "with_context" and context_text:
        user_prompt = ANSWER_WITH_CONTEXT.format(question=question, context=context_text)
    else:
        user_prompt = ANSWER_NO_CONTEXT.format(question=question)

    # 完整消息序列：system + 历史多轮 + 当前用户
    msgs = [{"role": "system", "content": SYSTEM_INSTRUCTION}]
    # 将历史逐条附加（保持 role: "user"/"assistant"）
    msgs.extend(history_msgs)
    # 当前用户问题
    msgs.append({"role": "user", "content": user_prompt})

    # 把最终生成的文本拼接出来用于写历史
    final_text_parts: list[str] = []

    # 优先使用流式
    try:
        async for chunk in llm.astream(msgs):
            delta = getattr(chunk, "content", None)
            if delta:
                final_text_parts.append(delta)
                yield {"type": "token", "data": delta}
    except Exception:
        # 回退：非流式整段生成
        resp = await llm.ainvoke(msgs)
        text = resp.content or ""
        final_text_parts.append(text)
        for i in range(0, len(text), 20):
            yield {"type": "token", "data": text[i:i+20]}
            await asyncio.sleep(0.005)

    if branch == "with_context" and citations:
        imgs = []
        # 取前 2 张，避免过多（可按需改成 3）
        for c in citations[:2]:
            url = c.get("previewUrl")
            if url:
                # 生成 Markdown 图片行
                imgs.append(f"![参考页 {c.get('rank', '')}]({url})")
        if imgs:
            tail = "\n\n---\n**相关页面预览**\n\n" + "\n\n".join(imgs)
            # 作为一个额外 token 块发给前端
            yield {"type": "token", "data": tail}

    # 将本轮问答写入历史（仅在提供 session_id 时）
    if session_id:
        append_history(session_id, "user", question)
        append_history(session_id, "assistant", "".join(final_text_parts))

    yield {"type": "done", "data": {"used_retrieval": branch == "with_context"}}
