"""数据库工具 — 元数据查询 & 关键词匹配表"""

from .metadata import TABLES, find_table_by_name, search_tables


def get_all_tables() -> list[dict]:
    """返回所有表的摘要信息"""
    return [
        {
            "table_name": t["table_name"],
            "table_alias": t["table_alias"],
            "category": t["category"],
            "description": t["description"],
            "row_count": t["row_count"],
            "field_count": len(t["fields"]),
        }
        for t in TABLES
    ]


def get_table_detail(table_name: str) -> dict | None:
    """返回单表完整详情"""
    t = find_table_by_name(table_name)
    if not t:
        return None
    return {
        "table_name": t["table_name"],
        "table_alias": t["table_alias"],
        "category": t["category"],
        "description": t["description"],
        "row_count": t["row_count"],
        "field_count": len(t["fields"]),
        "keywords": t["keywords"],
        "related_tables": t["related_tables"],
        "fields": t["fields"],
    }


def get_table_fields(table_name: str) -> list[dict] | None:
    """返回单表字段列表"""
    t = find_table_by_name(table_name)
    if not t:
        return None
    return t["fields"]


def match_tables_by_query(query: str) -> list[dict]:
    """根据自然语言查询匹配相关表,返回匹配度排序的表列表"""
    matched = search_tables(query)
    return [
        {
            "table_name": t["table_name"],
            "table_alias": t["table_alias"],
            "category": t["category"],
            "description": t["description"],
            "row_count": t["row_count"],
            "field_count": len(t["fields"]),
            "keywords_matched": [kw for kw in t["keywords"] if kw in query or query in kw],
        }
        for t in matched
    ]
