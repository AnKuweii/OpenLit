"""对话与 SSE 流式接口的路由。"""
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from schema import ChatRequest, ClearChatRequest
from services.rag_service import answer_stream, clear_history, retrieve

router = APIRouter(prefix='/chat',tags=["Chat"])


@router.post("")
async def chat_stream(req: ChatRequest):
    """
    SSE 事件：token | citation | done | error
    """

    async def gen():
        try:
            question = (req.message or "").strip()
            session_id = (req.sessionId or "default").strip()
            file_id = (req.pdfFileId or "").strip()

            citations, context_text = [], ""
            branch = "no_context"
            if file_id:
                try:
                    citations, context_text = await retrieve(question, file_id)
                    branch = "with_context" if context_text else "no_context"
                except FileNotFoundError:
                    branch = "no_context"

            if branch == "with_context" and citations:
                for c in citations:
                    yield "event: citation\n"
                    yield f"data: {c}\n\n"

            async for evt in answer_stream(
                question=question,
                citations=citations,
                context_text=context_text,
                branch=branch,
                session_id=session_id,
            ):
                if evt["type"] == "token":
                    yield "event: token\n"
                    text = evt["data"].replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
                    yield f'data: {{"text":"{text}"}}\n\n'
                elif evt["type"] == "citation":
                    yield "event: citation\n"
                    yield f"data: {evt['data']}\n\n"
                elif evt["type"] == "done":
                    used = "true" if evt["data"].get("used_retrieval") else "false"
                    yield "event: done\n"
                    yield f"data: {{\"used_retrieval\": {used}}}\n\n"

        except Exception as e:
            yield "event: error\n"
            esc = str(e).replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')
            yield f'data: {{"message":"{esc}"}}\n\n'

    headers = {"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive"}
    return StreamingResponse(gen(), media_type="text/event-stream", headers=headers)


@router.post("/clear")
async def chat_clear(req: ClearChatRequest):
    sid = (req.sessionId or "default").strip()
    clear_history(sid)
    return {"ok": True, "sessionId": sid, "cleared": True}
