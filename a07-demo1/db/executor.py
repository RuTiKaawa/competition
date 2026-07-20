"""SQL 执行器 — 支持动态数据库连接"""

import time
import psycopg2
from psycopg2.extras import RealDictCursor
from db.connection_manager import get_active_config


def execute_sql(sql: str) -> dict:
    """
    执行 SQL 查询,返回结果。
    只允许 SELECT,阻止写操作。
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
    conn = None
    try:
        conn = psycopg2.connect(**get_active_config())
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql)
            rows = [dict(r) for r in cur.fetchall()]
            columns = [d.name for d in cur.description] if cur.description else []
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
    finally:
        if conn:
            conn.close()


def get_table_row_counts() -> dict[str, int]:
    """获取所有表的行数"""
    tables = [
        "dim_product", "dim_process", "dim_production_line", "dim_equipment",
        "mes_work_order", "mes_process_output", "qms_inspection",
        "qms_defect_detail", "eqp_downtime_record", "inv_inventory_snapshot",
    ]
    counts = {}
    conn = psycopg2.connect(**get_active_config())
    try:
        with conn.cursor() as cur:
            for t in tables:
                try:
                    cur.execute(f"SELECT COUNT(*) FROM {t}")
                    counts[t] = cur.fetchone()[0]
                except Exception:
                    counts[t] = 0
    finally:
        conn.close()
    return counts
