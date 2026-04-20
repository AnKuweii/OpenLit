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

import logging
import torch.cuda as cuda
from langchain.chat_models import init_chat_model
from langchain_huggingface import HuggingFaceEmbeddings
logger = logging.getLogger(__name__)


class ModelFactory:
    """模型实例工厂：LLM / Embedding / 评分器。缓存实例，避免重复加载模型。"""

    _embeddings: HuggingFaceEmbeddings | None = None
    _llm = None
    _grader = None

    @classmethod
    def init(cls) -> None:
        """提前加载所有模型。必须在第一次请求之前调用。"""
        device = "cuda" if cuda.is_available() else "cpu"
        logger.info("[ModelFactory] loading embedding model %s on %s …", EMBED_MODEL, device)
        cls._embeddings = HuggingFaceEmbeddings(
            model_name=EMBED_MODEL,
            model_kwargs={"device": device},
            encode_kwargs={"normalize_embeddings": True},
        )
        logger.info("[ModelFactory] embedding model ready.")

        logger.info("[ModelFactory] initializing LLM (%s / %s) …", MODEL_PROVIDER, MODEL_NAME)
        cls._llm = init_chat_model(
            model=MODEL_NAME,
            model_provider=MODEL_PROVIDER,
            temperature=TEMPERATURE,
        )
        logger.info("[ModelFactory] LLM ready.")

        logger.info("[ModelFactory] initializing grader …")
        cls._grader = init_chat_model(
            model=MODEL_NAME,
            model_provider=MODEL_PROVIDER,
            temperature=GRADER_TEMPERATURE,
        )
        logger.info("[ModelFactory] grader ready.")

    @classmethod
    def embeddings(cls) -> HuggingFaceEmbeddings:
        if cls._embeddings is None:
            raise RuntimeError("ModelFactory not initialized – call ModelFactory.init() first")
        return cls._embeddings

    @classmethod
    def llm(cls):
        if cls._llm is None:
            raise RuntimeError("ModelFactory not initialized – call ModelFactory.init() first")
        return cls._llm

    @classmethod
    def grader(cls):
        if cls._grader is None:
            raise RuntimeError("ModelFactory not initialized – call ModelFactory.init() first")
        return cls._grader


# ModelFactory 是内部实现细节，业务层不需要知道"工厂"存在。
def get_embeddings() -> HuggingFaceEmbeddings:
    """获取嵌入模型实例。"""
    return ModelFactory.embeddings()


def get_llm(): 
    """获取问答模型实例。"""
    return ModelFactory.llm()


def get_grader():
    """获取评分器实例。"""
    return ModelFactory.grader()