"""PDF 上传、解析与资源访问的服务。"""
from __future__ import annotations
import os, io, math, json
from pathlib import Path
from typing import Dict, Any, List
import fitz
from PIL import Image
import matplotlib
matplotlib.use("Agg")  # 服务器无头
import matplotlib.pyplot as plt
import matplotlib.patches as patches

from langchain_unstructured import UnstructuredLoader
from unstructured.partition.pdf import partition_pdf
from html2text import html2text

import sys

from config import patch_paddleocr_langchain, workdir
patch_paddleocr_langchain() # 修补 paddle ocr 与 langchain 的兼容性问题


def dir_original_pages(file_id: str) -> Path:
    p = workdir(file_id) / "pages" / "original"
    p.mkdir(parents=True, exist_ok=True); return p

def dir_parsed_pages(file_id: str) -> Path:
    p = workdir(file_id) / "pages" / "parsed"
    p.mkdir(parents=True, exist_ok=True); return p

def original_pdf_path(file_id: str) -> Path:
    return workdir(file_id) / "original.pdf"

def markdown_output(file_id: str) -> Path:
    return workdir(file_id) / "output.md"

def images_dir(file_id: str) -> Path:
    p = workdir(file_id) / "images"
    p.mkdir(parents=True, exist_ok=True); return p

def save_upload(file_id: str, upload_bytes: bytes, filename: str) -> Dict[str, Any]:
    """保存上传的 PDF，并返回页数"""
    pdf_path = original_pdf_path(file_id)
    pdf_path.write_bytes(upload_bytes)
    with fitz.open(pdf_path) as doc:
        pages = doc.page_count
    return {"fileId": file_id, "name": filename, "pages": pages}

def render_original_pages(file_id: str, dpi: int = 144):
    """把原始 PDF 渲染为 PNG，存到 pages/original/"""
    pdf_path = original_pdf_path(file_id)
    out_dir = dir_original_pages(file_id)
    with fitz.open(pdf_path) as doc:
        for idx, page in enumerate(doc, start=1):
            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat)
            (out_dir / f"page-{idx:04d}.png").write_bytes(pix.tobytes("png"))

def _plot_boxes_to_ax(ax, pix, segments):
    category_to_color = {
        "Title": "orchid",
        "Image": "forestgreen",
        "Table": "tomato",
    }
    categories = set()
    for seg in segments:
        points = seg["coordinates"]["points"]
        lw = seg["coordinates"]["layout_width"]
        lh = seg["coordinates"]["layout_height"]
        scaled = [(x * pix.width / lw, y * pix.height / lh) for x, y in points]
        color = category_to_color.get(seg.get("category"), "deepskyblue")
        categories.add(seg.get("category", "Text"))
        poly = patches.Polygon(scaled, linewidth=1, edgecolor=color, facecolor="none")
        ax.add_patch(poly)

    legend_handles = [patches.Patch(color="deepskyblue", label="Text")]
    for cat, color in category_to_color.items():
        if cat in categories:
            legend_handles.append(patches.Patch(color=color, label=cat))
    ax.legend(handles=legend_handles, loc="upper right")

def render_parsed_pages_with_boxes(file_id: str, docs_local: List[Dict[str, Any]], dpi: int = 144):
    """
    根据 UnstructuredLoader 的 metadata（含坐标）在原图上叠框，输出到 pages/parsed/
    """
    pdf_path = original_pdf_path(file_id)
    out_dir = dir_parsed_pages(file_id)
    with fitz.open(pdf_path) as doc:
        # 预聚合：按 page_number 分组 segments
        segments_by_page: Dict[int, List[Dict[str, Any]]] = {}
        for d in docs_local:
            meta = d.metadata if hasattr(d, "metadata") else d["metadata"]
            pno = meta.get("page_number")
            if pno is None: continue
            segments_by_page.setdefault(pno, []).append(meta)

        for page_number in range(1, doc.page_count + 1):
            page = doc.load_page(page_number - 1)
            mat = fitz.Matrix(dpi/72, dpi/72)
            pix = page.get_pixmap(matrix=mat)
            pil = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            fig, ax = plt.subplots(1, figsize=(10, 10))
            ax.imshow(pil)
            ax.axis("off")
            _plot_boxes_to_ax(ax, pix, segments_by_page.get(page_number, []))
            fig.tight_layout()
            fig.savefig(out_dir / f"page-{page_number:04d}.png", bbox_inches="tight", pad_inches=0)
            plt.close(fig)

def unstructured_segments(file_id: str) -> List[Any]:
    """用 UnstructuredLoader 产生高分辨率布局段"""
    pdf_path = str(original_pdf_path(file_id))
    loader = UnstructuredLoader(
        file_path=pdf_path,
        strategy="hi_res",
        infer_table_structure=True,
        languages=["chi_sim", "eng"],
        ocr_engine="paddleocr",  # 如果 paddle ocr 有问题可换成 'auto'
    )
    out = []
    for d in loader.lazy_load():
        out.append(d)
    return out

def pdf_to_markdown(file_id: str):
    """将 存储着PDF内容的Unstructured.Elements 转换为 Markdown"""
    pdf_path = str(original_pdf_path(file_id))
    out_md = markdown_output(file_id)
    img_dir = images_dir(file_id)

    elements = partition_pdf(
        filename=pdf_path,
        infer_table_structure=True,
        strategy="hi_res",
        languages=["chi_sim", "eng"],
        ocr_engine="paddleocr"  # 同上
    )

    # 提取图片
    image_map = {}
    with fitz.open(pdf_path) as doc:
        for page_num, page in enumerate(doc, start=1):
            image_map[page_num] = []
            for img_index, img in enumerate(page.get_images(full=True), start=1):
                xref = img[0]
                # pdf → image 转换
                pix = fitz.Pixmap(doc, xref)
                img_path = img_dir / f"page{page_num}_img{img_index}.png"
                if pix.n < 5:
                    pix.save(str(img_path))
                else:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                    pix.save(str(img_path))
                image_map[page_num].append(img_path.name)  # 只保存文件名

    md_lines: List[str] = []
    inserted_images = set()
    for el in elements:
        cat = getattr(el, "category", None)
        text = (getattr(el, "text", "") or "").strip()
        meta = getattr(el, "metadata", None)
        page_num = getattr(meta, "page_number", None) if meta else None

        if not text and cat != "Image":
            continue
        # 根据不同类型的 Element 进行不同 Markdown 元素的添加 （文本、标题、表格、图片）
        match cat:
            case "Title" if text.startswith("- "):
                md_lines.append(text + "\n")
            case "Title":
                md_lines.append(f"# {text}\n")
            case "Header" | "Subheader":
                md_lines.append(f"## {text}\n")
            case "Table":
                html = getattr(meta, "text_as_html", None) if meta else None
                if html:
                    md_lines.append(html2text(html) + "\n")
                else:
                    md_lines.append((text or "") + "\n")
            case "Image" if page_num:
                for name in image_map.get(page_num, []):
                    if (page_num, name) not in inserted_images:
                        md_lines.append(f"![Image](./images/{name})\n")
                        inserted_images.add((page_num, name))
            case _:
                md_lines.append(text + "\n")

    out_md.write_text("\n".join(md_lines), encoding="utf-8")
    return {"markdown": out_md.name, "images_dir": "images"}

def run_full_parse_pipeline(file_id: str) -> Dict[str, Any]:
    """
    完整流程：原始页图渲染 → Unstructured 布局段 → 叠框图 → 输出 Markdown
    返回用于 /status 的统计或元信息
    """
    render_original_pages(file_id)
    docs = unstructured_segments(file_id)
    render_parsed_pages_with_boxes(file_id, docs)
    md_info = pdf_to_markdown(file_id)
    return {"md": md_info["markdown"]}
