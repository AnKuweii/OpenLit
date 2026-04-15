from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from router.chat import router as chat_router
from router.pdf import router as pdf_router
from schema import BuildIndexRequest, SearchRequest
from services.index_service import build_faiss_index, search_faiss
from state import current_pdf
from utils import err

app = FastAPI(
    title="OpenLit",
    version="1.0.0",
    description="OpenLit is a multi-modal Advanced RAG System.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_PREFIX = "/api/v1"

app.include_router(chat_router, prefix=API_PREFIX)
app.include_router(pdf_router, prefix=API_PREFIX)


@app.get(f"{API_PREFIX}/health", tags=["Health"])
async def health():
    return {"ok": True, "version": "1.0.0"}


@app.post(f"{API_PREFIX}/index/build", tags=["Index"])
async def index_build(req: BuildIndexRequest):
    if not current_pdf["fileId"] or current_pdf["fileId"] != req.fileId:
        raise HTTPException(status_code=400, detail="FILE_NOT_FOUND_OR_NOT_CURRENT")
    if current_pdf["status"] != "ready":
        raise HTTPException(status_code=409, detail="NEED_PARSE_FIRST")

    out = build_faiss_index(req.fileId)
    if not out.get("ok"):
        return JSONResponse(err(out.get("error", "INDEX_BUILD_ERROR"), "索引构建失败"), status_code=500)
    return {"ok": True, "chunks": out["chunks"]}


@app.post(f"{API_PREFIX}/index/search", tags=["Index"])
async def index_search(req: SearchRequest):
    out = search_faiss(req.fileId, req.query, req.k or 5)
    if not out.get("ok"):
        code = out.get("error", "INDEX_NOT_FOUND")
        return JSONResponse(err(code, "请先构建索引"), status_code=400)
    return out
