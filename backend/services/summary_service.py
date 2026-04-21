"""摘要服务：使用预加载的 BART 模型对文档文本生成摘要。

依赖包：transformers, torch, accelerate（可选，用于大模型加速）
"""
from __future__ import annotations

import asyncio
import logging
import re

import torch

from model import get_summarizer

logger = logging.getLogger(__name__)

# BART 编码器最大接受 1024 tokens
_MAX_INPUT_TOKENS = 1024


def _clean_markdown(text: str) -> str:
    """去除 Markdown 标记和页码注释，保留纯文本。"""
    text = re.sub(r"<!--.*?-->", "", text)
    text = re.sub(r"!\[.*?\]\(.*?\)", "", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\*{1,2}(.*?)\*{1,2}", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _generate_sync(
    text: str,
    max_length: int = 150,
    min_length: int = 40,
) -> str:
    """同步推理入口（由 asyncio.to_thread 包装调用）。"""
    tokenizer, model = get_summarizer()
    device = next(model.parameters()).device

    inputs = tokenizer(
        text,
        max_length=_MAX_INPUT_TOKENS,
        truncation=True,
        return_tensors="pt",
    )
    inputs = {k: v.to(device) for k, v in inputs.items()}

    with torch.no_grad():
        summary_ids = model.generate(
            **inputs,
            max_length=max_length,
            min_length=min_length,
            length_penalty=2.0,
            num_beams=4,
            early_stopping=True,
        )

    summary = tokenizer.decode(summary_ids[0], skip_special_tokens=True)
    return summary


async def generate_summary(
    text: str,
    max_length: int = 150,
    min_length: int = 40,
) -> str:
    """
    异步生成文本摘要。

    Parameters
    ----------
    text : str
        原始文本（可为 Markdown 格式，函数内部会清洗）。
    max_length : int
        摘要最大 token 长度。
    min_length : int
        摘要最小 token 长度。

    Returns
    -------
    str
        生成的摘要字符串。

    Raises
    ------
    ValueError
        输入文本为空。
    RuntimeError
        摘要模型未加载。
    """
    if not text or not text.strip():
        raise ValueError("输入文本为空，无法生成摘要")

    cleaned = _clean_markdown(text)
    if not cleaned:
        raise ValueError("清洗后文本为空，无法生成摘要")

    logger.info("[Summary] generating summary for %d chars …", len(cleaned))
    summary = await asyncio.to_thread(_generate_sync, cleaned, max_length, min_length)
    logger.info("[Summary] done, summary length = %d chars", len(summary))
    return summary
