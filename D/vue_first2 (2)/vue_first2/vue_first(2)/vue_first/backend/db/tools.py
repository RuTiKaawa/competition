"""数据库工具 — 元数据查询 & 关键词匹配表 & 动态扫表"""

from .metadata import TABLES, find_table_by_name, search_tables
from database import get_db_type


def _schema_filter() -> str:
    return "table_schema='public'" if get_db_type() != "mysql" else "table_schema=DATABASE()"


def get_real_tables() -> list[dict]:
    """动态查询当前数据库的真实表列表（information_schema，PG/MySQL 通用）"""
    try:
        from .executor import execute_sql
        result = execute_sql(
            f"SELECT table_name, "
            f"(SELECT COUNT(*) FROM information_schema.columns WHERE table_name=t.table_name AND {_schema_filter()}) AS field_count "
            f"FROM information_schema.tables t "
            f"WHERE {_schema_filter()} AND table_type='BASE TABLE' "
            f"ORDER BY table_name"
        )
        if result["success"] and result["rows"]:
            return [{"table_name": r["table_name"], "field_count": r["field_count"]} for r in result["rows"]]
    except Exception:
        pass
    return []


def _merge_tables_with_metadata(real_tables: list[dict]) -> list[dict]:
    """将真实表与硬编码元数据合并"""
    meta_map = {t["table_name"]: t for t in TABLES}
    merged = []
    for rt in real_tables:
        name = rt["table_name"]
        meta = meta_map.get(name)
        if meta:
            merged.append({
                "table_name": name,
                "table_alias": meta["table_alias"],
                "category": meta.get("category", "dim"),
                "description": meta.get("description", ""),
                "row_count": meta.get("row_count", 0),
                "field_count": rt["field_count"],  # 真实字段数优先
            })
        else:
            # 真实库有但元数据没有的表
            merged.append({
                "table_name": name,
                "table_alias": name,
                "category": "dim",
                "description": "",
                "row_count": 0,
                "field_count": rt["field_count"],
            })
    return merged


def get_all_tables() -> list[dict]:
    """返回所有表的摘要信息 — 优先真实库，回退元数据"""
    real = get_real_tables()
    if real:
        return _merge_tables_with_metadata(real)
    # 数据库不可用时回退到硬编码元数据
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
    """返回单表完整详情 — 优先真实DB字段，回退元数据"""
    meta = find_table_by_name(table_name)
    real_fields = _get_real_fields(table_name)

    if not meta and not real_fields:
        return None

    fields = real_fields if real_fields else (meta["fields"] if meta else [])
    return {
        "table_name": table_name,
        "table_alias": meta["table_alias"] if meta else table_name,
        "category": meta["category"] if meta else "dim",
        "description": meta["description"] if meta else "",
        "row_count": meta["row_count"] if meta else 0,
        "field_count": len(fields),
        "keywords": meta.get("keywords", []) if meta else [],
        "related_tables": meta.get("related_tables", []) if meta else [],
        "fields": fields,
    }


def _get_real_fields(table_name: str) -> list[dict] | None:
    """查询真实数据库的表字段（PG/MySQL 通用）"""
    try:
        from .executor import execute_sql
        # 仅允许安全的表名（字母数字下划线）
        if not table_name.replace("_", "").isalnum():
            return None
        if get_db_type() == "mysql":
            result = execute_sql(
                f"SELECT column_name, data_type, "
                f"CASE WHEN column_name IN ("
                f"  SELECT column_name FROM information_schema.key_column_usage "
                f"  WHERE table_name='{table_name}' AND table_schema=DATABASE() AND constraint_name='PRIMARY'"
                f") THEN 'PK' ELSE '' END AS key_type "
                f"FROM information_schema.columns "
                f"WHERE table_name='{table_name}' AND table_schema=DATABASE() "
                f"ORDER BY ordinal_position"
            )
        else:
            result = execute_sql(
                f"SELECT column_name, data_type, "
                f"CASE WHEN column_name IN ("
                f"  SELECT kcu.column_name FROM information_schema.table_constraints tc "
                f"  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                f"  WHERE tc.table_name='{table_name}' AND tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'"
                f") THEN 'PK' ELSE '' END AS key_type "
                f"FROM information_schema.columns "
                f"WHERE table_name='{table_name}' AND table_schema='public' "
                f"ORDER BY ordinal_position"
            )
        if result["success"] and result["rows"]:
            return [
                {
                    "name": r["column_name"],
                    "type": r["data_type"],
                    "key": r["key_type"],
                    "description": "",
                    "sample": "",
                }
                for r in result["rows"]
            ]
    except Exception:
        pass
    return None


def get_dynamic_table_detail(table_name: str) -> dict | None:
    """动态获取未知表的详细信息，包括字段结构，无需硬编码元数据（PG/MySQL 通用）"""
    try:
        from .executor import execute_sql
        
        # 1. 获取表的基本信息（MySQL 无 pg_class 描述，忽略描述查询）
        table_desc = ""
        if get_db_type() != "mysql":
            table_info_result = execute_sql(
                f"SELECT table_name, obj_description(c.oid) as description "
                f"FROM information_schema.tables t "
                f"JOIN pg_class c ON c.relname = t.table_name "
                f"WHERE t.table_name = '{table_name}' AND t.table_schema = 'public'"
            )
            if table_info_result["success"] and table_info_result["rows"]:
                table_desc = table_info_result["rows"][0]["description"] or ""
        
        # 2. 获取字段信息（已实现的函数）
        fields = _get_real_fields(table_name)
        if not fields:
            return None
            
        # 3. 获取行数（估算）
        from database import quote_ident
        row_count_result = execute_sql(f"SELECT COUNT(*) as row_count FROM {quote_ident(table_name)} LIMIT 100000")
        row_count = row_count_result["rows"][0]["row_count"] if row_count_result["success"] and row_count_result["rows"] else 0
        
        # 4. 获取相关表（基于外键关系）
        related_tables = []
        try:
            fk_result = execute_sql(
                f"SELECT "
                f"  tc.table_name, "
                f"  kcu.column_name, "
                f"  ccu.table_name AS foreign_table_name, "
                f"  ccu.column_name AS foreign_column_name "
                f"FROM information_schema.table_constraints AS tc "
                f"JOIN information_schema.key_column_usage AS kcu "
                f"  ON tc.constraint_name = kcu.constraint_name "
                f"  AND tc.table_schema = kcu.table_schema "
                f"JOIN information_schema.constraint_column_usage AS ccu "
                f"  ON ccu.constraint_name = tc.constraint_name "
                f"  AND ccu.table_schema = tc.table_schema "
                f"WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name = '{table_name}'"
            )
            if fk_result["success"] and fk_result["rows"]:
                for row in fk_result["rows"]:
                    if row["foreign_table_name"] != table_name:  # Avoid self-references
                        related_tables.append(row["foreign_table_name"])
        except Exception:
            pass
        
        # 5. 构建表描述
        if not table_desc:
            # 尝试基于表名生成一个基本描述
            if table_name.startswith('dim_') or table_name.endswith('_dim'):
                table_desc = f"维度表 - {table_name}"
            elif table_name.startswith('fact_') or table_name.endswith('_fact'):
                table_desc = f"事实表 - {table_name}"
            else:
                table_desc = f"表 - {table_name}"
        
        # 6. 确定表类别
        if table_name.startswith('dim_') or table_name.endswith('_dim'):
            category = "master"
        elif table_name.startswith('fact_') or table_name.endswith('_fact'):
            category = "fact"
        else:
            category = "dim"
            
        return {
            "table_name": table_name,
            "table_alias": table_name,
            "category": category,
            "description": table_desc,
            "row_count": row_count,
            "field_count": len(fields),
            "keywords": [table_name],  # Use table name as keyword
            "related_tables": list(set(related_tables)),  # Remove duplicates
            "fields": fields,
        }
    except Exception as e:
        print(f"Error getting dynamic table detail for {table_name}: {str(e)}")
        return None


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
