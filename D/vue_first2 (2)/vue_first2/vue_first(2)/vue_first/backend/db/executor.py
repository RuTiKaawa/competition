"""SQL 执行器 — 基于 SQLAlchemy engine（自动适配 PostgreSQL / MySQL）"""

import re
import time

from sqlalchemy import text


def get_active_config():
    """返回当前活跃的数据库配置（兼容旧调用方）"""
    try:
        from database import get_database_config
        from config import DB_CONFIG
        cfg = get_database_config()
        return {
            "dbname": cfg.get("name", DB_CONFIG.get("dbname")),
            "user": cfg.get("user", DB_CONFIG.get("user")),
            "host": cfg.get("host", DB_CONFIG.get("host")),
            "port": cfg.get("port", DB_CONFIG.get("port")),
            "password": DB_CONFIG.get("password"),
        }
    except Exception:
        from config import DB_CONFIG
        return dict(DB_CONFIG)


def _engine():
    """获取当前全局 SQLAlchemy engine（切换数据库后自动指向新库）"""
    from database import engine
    return engine


def _is_mysql() -> bool:
    try:
        from database import DB_TYPE
        return DB_TYPE == "mysql"
    except Exception:
        return False


def _pg_to_mysql(sql: str) -> str:
    """把 PG 风格的 SQL 转换为 MySQL 兼容（仅在 MySQL 下调用）"""
    s = sql

    # 1. 双引号标识符 "name" → `name`
    s = re.sub(r'"([^"]+)"', r'`\1`', s)

    # 2. ::integer / ::numeric / ::text 等类型转换 → 去掉（MySQL 用原生类型）
    s = re.sub(r'::(?:integer|int|numeric|decimal|float|double precision|text|varchar|date|timestamp|boolean|bigint|smallint|real|money)', '', s)

    # 3. ILIKE → LIKE
    s = re.sub(r'\bILIKE\b', 'LIKE', s)

    # 4. NOW() 兼容（两者都有）
    return s


def get_pooled_conn():
    """兼容旧接口：返回一个 engine 连接"""
    return _engine().connect()


def put_pooled_conn(conn):
    """兼容旧接口：关闭连接"""
    try:
        conn.close()
    except Exception:
        pass


def _normalize_value(v):
    """把 Decimal / datetime 等转成可 JSON 序列化的值"""
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if hasattr(v, "to_integral_value"):
        try:
            from decimal import Decimal
            d = Decimal(v)
            if d == d.to_integral_value():
                return int(d)
            return float(d)
        except Exception:
            return float(v)
    return v


def execute_sql(sql: str) -> dict:
    """
    执行 SQL 查询，返回结果。使用 SQLAlchemy engine（支持 PG/MySQL）。
    只允许 SELECT，阻止写操作。
    """
    sql_stripped = sql.strip().upper()
    if not sql_stripped.startswith("SELECT"):
        return {
            "success": False,
            "elapsed_ms": 0,
            "row_count": 0,
            "columns": [],
            "rows": [],
            "error": "仅允许 SELECT 查询",
        }

    t0 = time.time()
    try:
        effective_sql = _pg_to_mysql(sql) if _is_mysql() else sql
        with _engine().connect() as conn:
            result = conn.execute(text(effective_sql))
            # MySQL information_schema 返回大写列名，统一转小写
            columns = [str(c).lower() for c in result.keys()]
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
            # 数值/日期规范化
            for r in rows:
                for k, v in list(r.items()):
                    r[k] = _normalize_value(v) if v is not None else None
            elapsed_ms = int((time.time() - t0) * 1000)
            return {
                "success": True,
                "elapsed_ms": elapsed_ms,
                "row_count": len(rows),
                "columns": columns,
                "rows": rows,
            }
    except Exception as e:
        elapsed_ms = int((time.time() - t0) * 1000)
        return {
            "success": False,
            "elapsed_ms": elapsed_ms,
            "row_count": 0,
            "columns": [],
            "rows": [],
            "error": str(e),
        }


def reload_pool():
    """连接配置变更后重建连接（engine 全局共享，无需操作）"""
    pass


def get_table_row_counts() -> dict[str, int]:
    """动态获取当前数据库所有表的行数（PG/MySQL 通用）"""
    counts = {}
    try:
        from database import engine
        with engine.connect() as conn:
            # 列出业务表
            tables = []
            for (t,) in conn.execute(text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE'"
            )):
                tables.append(t)
            if not tables:
                # MySQL 路径
                for (t,) in conn.execute(text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema=DATABASE()"
                )):
                    tables.append(t)
            for t in tables:
                try:
                    count = conn.execute(text(f'SELECT COUNT(*) FROM "{t}"')).scalar()
                    counts[t] = int(count or 0)
                except Exception:
                    try:
                        count = conn.execute(text(f'SELECT COUNT(*) FROM `{t}`')).scalar()
                        counts[t] = int(count or 0)
                    except Exception:
                        counts[t] = 0
    except Exception:
        pass
    return counts
