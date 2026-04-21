"""系统配置"""
# ============================= 版本补丁 =============================
def patch_paddleocr_langchain():
    """
        =========================BEGIN==========================
        丑陋的修复：paddle ocr 没有跟上 langchain v1.0 节奏
        参考：https://github.com/PaddlePaddle/PaddleOCR/issues/16711#issuecomment-3446427004
        思路：Provide old import paths expected by paddlex:
    """
    import types
    import sys
    
    # langchain.docstore.document -> Document
    m1 = types.ModuleType("langchain.docstore.document")
    from langchain_core.documents import Document  # noqa: E402, I001

    m1.Document = Document
    sys.modules["langchain.docstore.document"] = m1

    # langchain.text_splitter -> RecursiveCharacterTextSplitter
    m2 = types.ModuleType("langchain.text_splitter")
    from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: E402, I001

    m2.RecursiveCharacterTextSplitter = RecursiveCharacterTextSplitter  # type: ignore
    sys.modules["langchain.text_splitter"] = m2
    """ =========================END============================ """

# ============================= 工作目录 =============================
from pathlib import Path
DATA_ROOT = Path("data")

def workdir(file_id: str) -> Path:
    p = DATA_ROOT / file_id
    p.mkdir(parents=True, exist_ok=True)
    return p

# ============================= 环境变量 =============================
import os
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

os.environ["HF_HOME"] = os.getenv("HF_HOME")
os.environ["TRANSFORMERS_CACHE"] = os.getenv("TRANSFORMERS_CACHE")
os.environ["OPENAI_BASE_URL"] = os.getenv("OPENAI_BASE_URL")
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

# ============================= 设备配置 =============================
import torch.cuda as cuda
DEVICE = "cuda" if cuda.is_available() else "cpu"

# ============================= 模型配置 =============================
# 问答模型
MODEL_NAME = os.getenv("MODEL_NAME")
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER")
TEMPERATURE = os.getenv("TEMPERATURE")

# 评分器温度
GRADER_TEMPERATURE = 0

# 嵌入模型
EMBED_MODEL = "BAAI/bge-m3"

# 重排序模型（本地 HuggingFaceCrossEncoder）
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
RERANKER_TOP_N = 3

# 摘要模型（本地 BART seq2seq）
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "facebook/bart-large-cnn")

# ============================= 检索配置 =============================
# 初步召回数量（rerank 前），应大于最终需要的 K 以给重排序留出筛选空间
RECALL_K = 10
# 最终保留数量（rerank 后）
K = 3
# 相似度检索阈值 → FAISS L2：越小越相似；数值可以灵活调整（Top1 和 Mean3）
SCORE_TAU_TOP1 = 0.30
SCORE_TAU_MEAN3 = 0.40

# ============================= Prompt 提示词配置 =============================
# 系统提示词配置
SYSTEM_INSTRUCTION = (
    "你是一个多模态 PDF 检索 RAG 聊天机器人，可以围绕学术文献进行解析、检索和问答。\n"
    "请优先使用当前上传并已解析/索引的学术文献来回答问题；若未检索到相关内容，则基于通识知识作答，"
    "并**明确说明未找到匹配的文献片段**。\n"
    "当检索到的上下文中包含与答案直接相关的图片时，请在回答中一并给出这些图片的 Markdown 引用，"
    "例如：`![参考图1](图片URL)`。如果没有合适的图片，也就是如果没有检索到图片，或者用户只是让你介绍自己的功能，勿强行添加图片路径。绝不伪造图片或路径。"
)

# 评分器提示词配置
GRADE_PROMPT = (
    "你是一个判定器，评估检索到的上下文是否有助于回答用户问题。\n"
    "上下文片段：\n{context}\n\n问题：{question}\n"
    "如果上下文对回答该问题有帮助，返回 'yes'；否则返回 'no'。"
)

# 回答上下文提示词配置
ANSWER_WITH_CONTEXT = (
    "请使用提供的上下文回答用户的问题。\n\n"
    "问题：\n{question}\n\n上下文：\n{context}\n\n"
    "要求：使用 Markdown；表达简洁但完整；如需给出代码，请使用三引号代码块（```）。\n"
    "若上下文包含与答案直接相关的图片，请在相关段落后内联给出 1–3 张图片（Markdown 语法），"
    "作为一名助人为乐的助手，你需要仔细详细的感受用户的需求，并作出详细的回答。如果有图片，请在回答中给出图片的Markdown引用。"
)

# 回答无上下文提示词配置
ANSWER_NO_CONTEXT = (
    "当前未找到与学术文献直接相关的片段，将基于通识知识作答。\n"
    "问题：\n{question}"
)

# 路由器提示词配置
ROUTER_PROMPT = (
    "你是一个查询分类器，判断用户问题是否需要检索已上传的学术文献来回答。\n"
    "只输出 RETRIEVE 或 NO_RETRIEVE，不要解释。\n\n"
    "规则：\n"
    "- 问题涉及文档内容、论文方法、实验结果、作者观点 → RETRIEVE\n"
    "- 包含指示代词（这篇、该文、文中、论文中）→ RETRIEVE\n"
    "- 通识知识（解释概念、定义术语）→ NO_RETRIEVE\n"
    "- 闲聊寒暄（你好、谢谢、天气）→ NO_RETRIEVE\n"
    "- 问AI自身（你是谁、你能做什么）→ NO_RETRIEVE\n\n"
    "问题：{query}"
)