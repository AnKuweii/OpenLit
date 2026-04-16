"""模型实例工厂：LLM / Embedding / 评分器。"""
from __future__ import annotations

import os
from config import (
    EMBED_MODEL,
    GRADER_TEMPERATURE,
    MODEL_NAME,
    MODEL_PROVIDER,
    TEMPERATURE,
)

import torch.cuda as cuda
from langchain.chat_models import init_chat_model
from langchain_huggingface import HuggingFaceEmbeddings


def get_llm():
    return init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, temperature=TEMPERATURE)


def get_grader():
    return init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, temperature=GRADER_TEMPERATURE)


def get_embeddings() -> HuggingFaceEmbeddings:
    """加载嵌入模型（Embedding）"""
    return HuggingFaceEmbeddings(
        model_name=EMBED_MODEL,
        model_kwargs={"device": "cuda" if cuda.is_available() else "cpu"},
        encode_kwargs={"normalize_embeddings": True}
    )