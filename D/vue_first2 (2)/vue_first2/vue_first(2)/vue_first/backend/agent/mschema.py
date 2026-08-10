"""M-Schema 表结构格式生成器（缓存版）

每张表的元数据在内存中缓存 5 分钟，避免每次查询都扫全部表。
格式: # 表名 (行数)
(字段名: 类型, PK标注, examples:[样例])
"""

import json
import time
from db.executor import execute_sql
from database import get_db_type, quote_ident


def _schema_filter() -> str:
    """返回 information_schema 的表空间过滤条件（PG/MySQL 通用）"""
    return "table_schema='public'" if get_db_type() != "mysql" else "table_schema=DATABASE()"

# ── 全局缓存 ────────────────────────────────────────────

_cache: dict = {}          # key → value
_cache_time: float = 0     # 缓存创建时间
_CACHE_TTL = 300           # 5 分钟


def _cache_get(key: str):
    if _cache and (time.time() - _cache_time) < _CACHE_TTL:
        return _cache.get(key)
    return None


def _cache_set(key: str, value):
    global _cache, _cache_time
    if not _cache or (time.time() - _cache_time) >= _CACHE_TTL:
        _cache = {}
        _cache_time = time.time()
    _cache[key] = value


# ── 单表查询（带缓存）─────────────────────────────────────

def _get_table_meta(table: str) -> dict | None:
    """获取一张表的完整元数据（缓存）"""
    cached = _cache_get(f"meta_{table}")
    if cached:
        return cached

    try:
        # 1. 字段
        r = execute_sql(
            f"SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_name='{table}' AND {_schema_filter()} ORDER BY ordinal_position"
        )
        if not r["success"] or not r["rows"]:
            return None
        columns = [{"name": row["column_name"], "type": row["data_type"]} for row in r["rows"]]

        # 2. 主键
        try:
            pk_r = execute_sql(
                f"SELECT kcu.column_name FROM information_schema.table_constraints tc "
                f"JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                f"WHERE tc.table_name='{table}' AND tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'"
            )
            if not pk_r["success"] or not pk_r["rows"]:
                # MySQL 回退：key_column_usage 直接查询
                pk_r = execute_sql(
                    f"SELECT column_name FROM information_schema.key_column_usage "
                    f"WHERE table_name='{table}' AND table_schema=DATABASE() AND constraint_name='PRIMARY'"
                )
            pks = {r2["column_name"] for r2 in pk_r["rows"]} if pk_r["success"] else set()
        except Exception:
            pks = set()

        # 3. 行数
        row_count = 0
        try:
            cnt_r = execute_sql(f"SELECT COUNT(*) AS cnt FROM {quote_ident(table)}")
            if cnt_r["success"] and cnt_r["rows"]:
                row_count = cnt_r["rows"][0]["cnt"]
        except Exception:
            pass

        # 4. 样例值（只取前 5 列的 distinct 值）
        examples = {}
        for col in columns[:5]:
            cn = col["name"]
            try:
                ex_r = execute_sql(
                    f"SELECT DISTINCT CAST({quote_ident(cn)} AS CHAR) AS v FROM {quote_ident(table)} "
                    f"WHERE {quote_ident(cn)} IS NOT NULL LIMIT 3"
                )
                if ex_r["success"] and ex_r["rows"]:
                    examples[cn] = [str(row["v"] if "v" in row else list(row.values())[0]) for row in ex_r["rows"]]
            except Exception:
                pass

        meta = {
            "columns": columns, "pks": pks, "row_count": row_count, "examples": examples
        }
        _cache_set(f"meta_{table}", meta)
        return meta

    except Exception:
        return None


# ── M-Schema 生成 ────────────────────────────────────────

def build_mschema(tables: list[str]) -> str:
    """为指定表列表生成 M-Schema 文本（使用缓存）"""
    sections = []

    for table in tables:
        meta = _get_table_meta(table)
        if not meta:
            continue

        lines = [f"# {table} ({meta['row_count']} 行)"]
        for col in meta["columns"]:
            cn = col["name"]
            ct = col["type"]
            key = ", PK" if cn in meta["pks"] else ""
            ex = meta["examples"].get(cn, [])
            ex_str = f", examples:{json.dumps(ex, ensure_ascii=False)}" if ex else ""
            lines.append(f"  ({cn}: {ct}{key}{ex_str})")

        sections.append("\n".join(lines))

    return f"# 当前库 {len(sections)} 张相关表\n\n" + "\n\n".join(sections)


def build_schema_context(query: str, candidate_tables: list[str], max_tables: int = 3) -> str:
    """为 LLM 构建 schema 上下文 — 只送最相关的表（默认3张）"""
    if not candidate_tables:
        try:
            r = execute_sql(
                f"SELECT table_name FROM information_schema.tables "
                f"WHERE {_schema_filter()} AND table_type='BASE TABLE' ORDER BY table_name LIMIT 5"
            )
            if r["success"]:
                candidate_tables = [row["table_name"] for row in r["rows"]]
        except Exception:
            candidate_tables = []

    selected = candidate_tables[:max_tables]
    return build_mschema(selected)
