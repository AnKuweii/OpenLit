"""对话与 SSE 流式接口的路由。"""
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessageChunk, RemoveMessage

from graph import get_app
from schema import ChatRequest, ClearChatRequest
from state import citations as citations_store

router = APIRouter(prefix="/chat", tags=["Chat"])


@router.post("")
async def chat_stream(req: ChatRequest):
    """
    SSE 事件流：token | citation | done | error
    """

    async def gen():
        try:
            question = (req.message or "").strip()
            session_id = (req.sessionId or "default").strip()
            file_id = (req.pdfFileId or "").strip()

            app = get_app()
            config = {"configurable": {"thread_id": session_id}}
            input_state = {
                "question": question,
                "file_id": file_id,
                "citations": [],
                "context_text": "",
                "branch": "",
                "response": "",
            }

            final_citations: list[dict] = []
            final_branch = "no_context"
            tokens_streamed = False

            async for stream_type, chunk in app.astream(
                input_state, config, stream_mode=["updates", "messages"]
            ):
                # 节点完成事件
                if stream_type == "updates":
                    if isinstance(chunk, dict) and "retrieve" in chunk:
                        citations = chunk["retrieve"].get("citations", [])
                        if citations:
                            final_citations = citations
                            for c in citations:
                                citations_store[c["citation_id"]] = c
                                yield "event: citation\n"
                                yield f"data: {json.dumps(c, ensure_ascii=False)}\n\n"

                    if isinstance(chunk, dict):
                        for node_name in (
                            "generate_with_context",
                            "generate_no_context",
                        ):
                            if node_name not in chunk:
                                continue
                            update = chunk[node_name]
                            final_branch = update.get("branch", final_branch)

                            if not tokens_streamed:
                                response_text = update.get("response", "")
                                for i in range(0, len(response_text), 20):
                                    part = response_text[i : i + 20]
                                    text = _sse_escape(part)
                                    yield "event: token\n"
                                    yield f'data: {{"text":"{text}"}}\n\n'

                # Token 级流式输出
                elif stream_type == "messages":
                    msg_chunk, _metadata = chunk
                    if isinstance(msg_chunk, AIMessageChunk) and msg_chunk.content:
                        tokens_streamed = True
                        text = _sse_escape(msg_chunk.content)
                        yield "event: token\n"
                        yield f'data: {{"text":"{text}"}}\n\n'

            # 图像预览
            if final_branch == "with_context" and final_citations:
                imgs = []
                for c in final_citations[:2]:
                    url = c.get("previewUrl")
                    if url:
                        imgs.append(f"![参考页 {c.get('rank', '')}]({url})")
                if imgs:
                    tail = "\n\n---\n**相关页面预览**\n\n" + "\n\n".join(imgs)
                    yield "event: token\n"
                    yield f'data: {{"text":"{_sse_escape(tail)}"}}\n\n'

            used = "true" if final_branch == "with_context" else "false"
            yield "event: done\n"
            yield f'data: {{"used_retrieval": {used}}}\n\n'

        except Exception as e:
            yield "event: error\n"
            yield f'data: {{"message":"{_sse_escape(str(e))}"}}\n\n'

    headers = {
        "Cache-Control": "no-cache, no-transform",
        "Connection": "keep-alive",
    }
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@router.post("/clear")
async def chat_clear(req: ClearChatRequest):
    """Clear LangGraph checkpoint history for the given thread."""
    sid = (req.sessionId or "default").strip()
    app = get_app()
    config = {"configurable": {"thread_id": sid}}
    try:
        state = await app.aget_state(config)
        msgs = (state.values or {}).get("messages", [])
        if msgs:
            removals = [RemoveMessage(id=m.id) for m in msgs]
            await app.aupdate_state(config, {"messages": removals})
    except Exception:
        pass
    return {"ok": True, "sessionId": sid, "cleared": True}


# helpers 帮助函数 

def _sse_escape(text: str) -> str:
    """ SSE数据中JSON字符串的安全转义 """
    return (
        text.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace('"', '\\"')
    )
