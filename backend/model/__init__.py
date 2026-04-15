"""模型实例工厂：LLM / Embedding / 评分器。"""
from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_openai import OpenAIEmbeddings

from config import (
    EMBED_DEFAULT_BASE_URL,
    EMBED_MODEL,
    GRADER_TEMPERATURE,
    MODEL_NAME,
    MODEL_PROVIDER,
    TEMPERATURE,
)


def get_llm():
    return init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, temperature=TEMPERATURE)


def get_grader():
    return init_chat_model(model=MODEL_NAME, model_provider=MODEL_PROVIDER, temperature=GRADER_TEMPERATURE)


def get_embeddings() -> OpenAIEmbeddings:
    """加载嵌入模型（Embedding）"""
    return OpenAIEmbeddings(
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL") or os.getenv("OPENAI_EMBEDDING_BASE_URL") or EMBED_DEFAULT_BASE_URL,
        model=EMBED_MODEL
    )