"""PDF 上传、解析与资源访问的路由。"""
import asyncio
import json
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, File, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from schema import PdfParseRequest, SummaryRequest
from services.pdf_service import (
    dir_original_pages,
    dir_parsed_pages,
    images_dir,
    markdown_output,
    run_full_parse_pipeline,
    save_upload,
)
from services.summary_service import clear_summary_cache, generate_summary
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
    clear_summary_cache()
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


@router.post("/summary")
async def pdf_summary(payload: SummaryRequest):
    """对已解析的 PDF Markdown 文本生成摘要。

    集成流程：用户上传 PDF → 解析生成 output.md → 调用本端点 → 返回 BART 摘要。
    """
    file_id = payload.fileId
    if not current_pdf["fileId"] or current_pdf["fileId"] != file_id:
        return JSONResponse(err("FILE_NOT_FOUND", "未找到该文件"), status_code=404)

    if current_pdf["status"] != "ready":
        return JSONResponse(
            err("NOT_READY", "文档尚未解析完成，请先完成解析"),
            status_code=409,
        )

    md_path = markdown_output(file_id)
    if not md_path.exists():
        return JSONResponse(
            err("MARKDOWN_NOT_FOUND", "未找到解析后的 Markdown 文件"),
            status_code=404,
        )

    md_text = md_path.read_text(encoding="utf-8")
    if not md_text.strip():
        return JSONResponse(err("EMPTY_CONTENT", "文档内容为空"), status_code=400)

    try:
        summary = await generate_summary(
            md_text,
            max_length=payload.maxLength,
            min_length=payload.minLength,
        )
        return {"ok": True, "summary": summary}
    except ValueError as e:
        return JSONResponse(err("INVALID_INPUT", str(e)), status_code=400)
    except RuntimeError as e:
        return JSONResponse(err("MODEL_ERROR", str(e)), status_code=500)
    except Exception as e:
        return JSONResponse(err("SUMMARY_FAILED", f"摘要生成失败: {e}"), status_code=500)
