import logging

from fastapi import APIRouter

from database import run_raw_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metadata", tags=["metadata"])


@router.get("/tables")
def get_tables():
    sql = """
        SELECT table_name, table_comment
        FROM metadata_config
        GROUP BY table_name, table_comment
        ORDER BY table_name
    """
    rows = run_raw_query(sql)

    tables = []
    for row in rows:
        tables.append({
            "table_name": row["table_name"],
            "table_comment": row["table_comment"],
        })

    return {"code": 200, "data": tables, "message": "success"}


@router.get("/tables/{table_name}")
def get_table_fields(table_name: str):
    sql = """
        SELECT id, table_name, table_comment, field_name, field_type,
               field_comment, sample_values, relationship_desc, created_at
        FROM metadata_config
        WHERE table_name = %(table_name)s
        ORDER BY id
    """
    rows = run_raw_query(sql, {"table_name": table_name})

    if not rows:
        return {"code": 200, "data": [], "message": "success"}

    fields = []
    for row in rows:
        fields.append({
            "id": row["id"],
            "table_name": row["table_name"],
            "table_comment": row["table_comment"],
            "field_name": row["field_name"],
            "field_type": row["field_type"],
            "field_comment": row["field_comment"],
            "sample_values": row["sample_values"],
            "relationship_desc": row["relationship_desc"],
            "created_at": str(row["created_at"]) if row["created_at"] else None,
        })

    return {"code": 200, "data": fields, "message": "success"}


@router.get("/relationships")
def get_relationships():
    sql = """
        SELECT
            tc.table_name AS source_table,
            kcu.column_name AS source_column,
            ccu.table_name AS target_table,
            ccu.column_name AS target_column,
            tc.constraint_name
        FROM information_schema.table_constraints AS tc
        JOIN information_schema.key_column_usage AS kcu
            ON tc.constraint_name = kcu.constraint_name
            AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage AS ccu
            ON ccu.constraint_name = tc.constraint_name
            AND ccu.table_schema = tc.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY'
          AND tc.table_schema = 'public'
        ORDER BY tc.table_name
    """
    rows = run_raw_query(sql)

    nodes_set = set()
    edges = []

    for row in rows:
        source = row["source_table"]
        target = row["target_table"]
        nodes_set.add(source)
        nodes_set.add(target)
        edges.append({
            "source": source,
            "target": target,
            "source_column": row["source_column"],
            "target_column": row["target_column"],
            "constraint_name": row["constraint_name"],
        })

    nodes = [{"id": n, "label": n} for n in sorted(nodes_set)]

    return {"code": 200, "data": {"nodes": nodes, "edges": edges}, "message": "success"}
