"""PDF 上传、解析与资源访问的路由。"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from schema import PdfParseRequest
from services.pdf_service import (
    dir_original_pages,
    dir_parsed_pages,
    images_dir,
    run_full_parse_pipeline,
    save_upload,
)
from state import citations, current_pdf
from utils import err, rid

router = APIRouter(prefix='/pdf',tags=["PDF"])


@router.post("/upload")
async def pdf_upload(file: UploadFile = File(...), replace: Optional[bool] = True):
    """接收前端上传的 PDF 文件"""
    if not file:
        return JSONResponse(err("NO_FILE", "缺少文件"), status_code=400)
    fid = rid("f")
    saved = save_upload(fid, await file.read(), file.filename)
    current_pdf.update({**saved, "status": "idle", "progress": 0})
    citations.clear()
    return saved


@router.post("/parse")
async def pdf_parse(payload: PdfParseRequest, bg: BackgroundTasks):
    """触发异步解析（Unstructured 布局提取 → 渲染 → OCR → 转换为Markdown ）"""
    file_id = payload.fileId
    if not current_pdf["fileId"] or current_pdf["fileId"] != file_id:
        return JSONResponse(err("FILE_NOT_FOUND", "未找到该文件"), status_code=400)

    if current_pdf["status"] == "parsing":
        return JSONResponse(
            err("ALREADY_PARSING", "该文件正在解析中，请勿重复提交"),
            status_code=409,
        )

    if current_pdf["status"] == "ready":
        return {"ok": True, "message": "ALREADY_PARSED", "progress": 100}

    current_pdf["status"] = "parsing"
    current_pdf["progress"] = 5

    def _job():
        try:
            current_pdf["progress"] = 20
            run_full_parse_pipeline(file_id)
            current_pdf["progress"] = 100
            current_pdf["status"] = "ready"
        except Exception as e:
            current_pdf["status"] = "error"
            current_pdf["progress"] = 0
            print("Parse error:", e)

    bg.add_task(_job)
    return {"jobId": rid("j")}


@router.get("/status")
async def pdf_status(fileId: str = Query(...)):
    """文件解析状态，供前端展示"""
    if not current_pdf["fileId"] or current_pdf["fileId"] != fileId:
        return {"status": "idle", "progress": 0}
    resp = {"status": current_pdf["status"], "progress": current_pdf["progress"]}
    if current_pdf["status"] == "error":
        resp["errorMsg"] = "解析失败"
    return resp


@router.get("/status/stream")
async def pdf_status_stream(fileId: str = Query(...)):
    """SSE push stream — replaces aggressive polling of /status.

    Emits a JSON event whenever status/progress changes, then auto-closes
    when a terminal state ("ready" / "error") is reached.

    Frontend usage:
        const src = new EventSource("/api/v1/pdf/status/stream?fileId=xxx");
        src.onmessage = (e) => updateUI(JSON.parse(e.data));
    """

    async def event_generator():
        prev = None
        while True:
            if not current_pdf["fileId"] or current_pdf["fileId"] != fileId:
                snapshot = {"status": "idle", "progress": 0}
            else:
                snapshot = {
                    "status": current_pdf["status"],
                    "progress": current_pdf["progress"],
                }
                if current_pdf["status"] == "error":
                    snapshot["errorMsg"] = "解析失败"

            if snapshot != prev:
                yield f"data: {json.dumps(snapshot, ensure_ascii=False)}\n\n"
                prev = snapshot

            if snapshot["status"] in ("ready", "error", "idle"):
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "Connection": "keep-alive"},
    )


@router.get("/page")
async def pdf_page(
    fileId: str = Query(...),
    page: int = Query(..., ge=1),
    type: str = Query(..., pattern="^(original|parsed)$"),
):
    """获取 PDF 页面的图片，供前端展示"""
    if not current_pdf["fileId"] or current_pdf["fileId"] != fileId:
        return JSONResponse(status_code=404, content=None)

    if current_pdf["status"] != "ready" and type == "parsed":
        return JSONResponse(status_code=204, content=None)

    base = dir_original_pages(fileId) if type == "original" else dir_parsed_pages(fileId)
    img = base / f"page-{page:04d}.png"
    if not img.exists():
        return JSONResponse(err("PAGE_NOT_FOUND", "页面不存在或未渲染"), status_code=404)
    return FileResponse(str(img), media_type="image/png")


@router.get("/images")
async def pdf_images(
    fileId: str = Query(...),
    imagePath: str = Query(...),
):
    """获取 PDF 内嵌的图片，供前端展示"""
    if not current_pdf["fileId"] or current_pdf["fileId"] != fileId:
        return JSONResponse(status_code=404, content=None)

    image_file = images_dir(fileId) / imagePath

    if not image_file.exists():
        return JSONResponse(err("IMAGE_NOT_FOUND", "图片文件不存在"), status_code=404)

    try:
        image_file.resolve().relative_to(images_dir(fileId).resolve())
    except ValueError:
        return JSONResponse(err("INVALID_PATH", "无效的图片路径"), status_code=400)

    return FileResponse(str(image_file), media_type="image/png")


@router.get("/chunk")
async def pdf_chunk(citationId: str = Query(...)):
    """获取引用详情，供前端展示"""
    ref = citations.get(citationId)
    if not ref:
        return JSONResponse(err("NOT_FOUND", "无该引用"), status_code=404)
    return ref
