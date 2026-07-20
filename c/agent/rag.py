"""RAG 知识库 — 用 FAISS 存储表结构知识,查询时检索最相关的表"""

import os
import json
import numpy as np
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document

from config import LLM_CONFIG
from db.metadata import TABLES

VECTOR_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".faiss_store")

_embeddings = None
_vector_store = None


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model="bge-large-zh",
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
        )
    return _embeddings


def _build_documents() -> list[Document]:
    """把每张表的元数据变成可检索的文档"""
    docs = []
    for t in TABLES:
        content = (
            f"表名: {t['table_name']}\n"
            f"中文名: {t['table_alias']}\n"
            f"分类: {t['category']}\n"
            f"描述: {t['description']}\n"
            f"关键词: {', '.join(t['keywords'])}\n"
            f"关联表: {', '.join(t['related_tables'])}\n"
            f"字段: {json.dumps([f['name'] + '(' + f['type'] + '): ' + f['description'] for f in t['fields']], ensure_ascii=False)}"
        )
        docs.append(Document(page_content=content, metadata={"table_name": t["table_name"]}))
    return docs


def build_index(force: bool = False):
    """构建 FAISS 索引 (首次运行或 force=True 时调用)"""
    global _vector_store
    if os.path.exists(VECTOR_PATH) and not force:
        return
    docs = _build_documents()
    _vector_store = FAISS.from_documents(docs, _get_embeddings())
    _vector_store.save_local(VECTOR_PATH)


def load_index():
    """加载已有索引"""
    global _vector_store
    if _vector_store is not None:
        return
    if not os.path.exists(VECTOR_PATH):
        build_index()
        return
    _vector_store = FAISS.load_local(
        VECTOR_PATH,
        _get_embeddings(),
        allow_dangerous_deserialization=True,
    )


def search_tables(query: str, k: int = 5) -> list[dict]:
    """
    RAG 检索: 根据用户自然语言,返回最相关的 k 张表
    返回: [{"table_name": ..., "score": ...}, ...]
    """
    load_index()
    docs = _vector_store.similarity_search_with_score(query, k=k)
    results = []
    for doc, score in docs:
        results.append({
            "table_name": doc.metadata["table_name"],
            "score": float(score),
        })
    return results


if __name__ == "__main__":
    build_index(force=True)
    print("FAISS index built successfully")
