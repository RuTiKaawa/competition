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
_index_failed = False  # embedding 不可用时降级，避免反复请求


def _get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = OpenAIEmbeddings(
            model=LLM_CONFIG.get("embedding_model", "bge-large-zh"),
            api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"],
        )
    return _embeddings


def _build_documents() -> list[Document]:
    """把每张表的元数据变成可检索的文档 — 包含真实DB表"""
    docs = []

    # 1. 先尝试获取真实DB中的表
    try:
        from db.tools import get_real_tables
        real = get_real_tables()
        real_names = {r["table_name"] for r in real}
    except Exception:
        real = []
        real_names = set()

    # 2. 合并硬编码元数据
    meta_map = {t["table_name"]: t for t in TABLES}

    # 真实表优先
    for r in real:
        name = r["table_name"]
        meta = meta_map.get(name, {})
        content = (
            f"表名: {name}\n"
            f"中文名: {meta.get('table_alias', name)}\n"
            f"分类: {meta.get('category', 'dim')}\n"
            f"描述: {meta.get('description', '')}\n"
            f"关键词: {', '.join(meta.get('keywords', []))}\n"
            f"关联表: {', '.join(meta.get('related_tables', []))}\n"
            f"字段: {json.dumps([f['name'] + '(' + f['type'] + '): ' + f['description'] for f in meta.get('fields', [])], ensure_ascii=False)}"
        )
        docs.append(Document(page_content=content, metadata={"table_name": name}))

    # 元数据中但不在真实库的表也加入（兜底）
    for t in TABLES:
        if t["table_name"] not in real_names:
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
    global _vector_store, _index_failed
    if os.path.exists(VECTOR_PATH) and not force:
        return
    if _index_failed and not force:
        return
    try:
        docs = _build_documents()
        _vector_store = FAISS.from_documents(docs, _get_embeddings())
        _vector_store.save_local(VECTOR_PATH)
        _index_failed = False
    except Exception as e:
        # embedding 服务不可用（如 DeepSeek 无 embedding 接口）→ 降级
        _index_failed = True
        _vector_store = None
        print(f"[RAG] 索引构建失败，已降级为规则匹配: {e}")


def load_index():
    """加载已有索引"""
    global _vector_store, _index_failed
    if _vector_store is not None:
        return
    if _index_failed:
        return
    if not os.path.exists(VECTOR_PATH):
        build_index()
        return
    try:
        _vector_store = FAISS.load_local(
            VECTOR_PATH,
            _get_embeddings(),
            allow_dangerous_deserialization=True,
        )
    except Exception as e:
        _index_failed = True
        print(f"[RAG] 索引加载失败，已降级为规则匹配: {e}")


def search_tables(query: str, k: int = 5) -> list[dict]:
    """
    RAG 检索: 根据用户自然语言,返回最相关的 k 张表
    返回: [{"table_name": ..., "score": ...}, ...]
    """
    load_index()
    if _vector_store is None:
        return []
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
