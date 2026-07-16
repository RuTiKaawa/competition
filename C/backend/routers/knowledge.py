import json
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from database import run_raw_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


class KnowledgeObjectCreate(BaseModel):
    object_name: str
    object_type: str | None = None
    description: str | None = None
    related_tables: str | None = None
    attributes: dict | None = None


class KnowledgeObjectUpdate(BaseModel):
    object_name: str | None = None
    object_type: str | None = None
    description: str | None = None
    related_tables: str | None = None
    attributes: dict | None = None


class KnowledgeIndicatorCreate(BaseModel):
    indicator_name: str
    formula: str | None = None
    description: str | None = None
    unit: str | None = None
    category: str | None = None
    related_tables: str | None = None


class KnowledgeIndicatorUpdate(BaseModel):
    indicator_name: str | None = None
    formula: str | None = None
    description: str | None = None
    unit: str | None = None
    category: str | None = None
    related_tables: str | None = None


# ==================== Business Objects ====================

@router.get("/objects")
def list_objects():
    sql = "SELECT * FROM knowledge_objects ORDER BY id"
    rows = run_raw_query(sql)

    objects = []
    for row in rows:
        objects.append({
            "id": row["id"],
            "object_name": row["object_name"],
            "object_type": row["object_type"],
            "description": row["description"],
            "related_tables": row["related_tables"],
            "attributes": row["attributes"],
            "created_at": str(row["created_at"]) if row["created_at"] else None,
            "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
        })

    return {"code": 200, "data": objects, "message": "success"}


@router.post("/objects")
def create_object(body: KnowledgeObjectCreate):
    attrs_json = json.dumps(body.attributes) if body.attributes else None
    sql = """
        INSERT INTO knowledge_objects
            (object_name, object_type, description, related_tables, attributes)
        VALUES (%(object_name)s, %(object_type)s, %(description)s, %(related_tables)s, %(attributes)s)
        RETURNING id
    """
    rows = run_raw_query(sql, {
        "object_name": body.object_name,
        "object_type": body.object_type,
        "description": body.description,
        "related_tables": body.related_tables,
        "attributes": attrs_json,
    })

    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


@router.put("/objects/{object_id}")
def update_object(object_id: int, body: KnowledgeObjectUpdate):
    set_clauses = []
    params = {"object_id": object_id}

    if body.object_name is not None:
        set_clauses.append("object_name = %(object_name)s")
        params["object_name"] = body.object_name
    if body.object_type is not None:
        set_clauses.append("object_type = %(object_type)s")
        params["object_type"] = body.object_type
    if body.description is not None:
        set_clauses.append("description = %(description)s")
        params["description"] = body.description
    if body.related_tables is not None:
        set_clauses.append("related_tables = %(related_tables)s")
        params["related_tables"] = body.related_tables
    if body.attributes is not None:
        set_clauses.append("attributes = %(attributes)s")
        params["attributes"] = json.dumps(body.attributes)

    if not set_clauses:
        return {"code": 200, "data": None, "message": "nothing to update"}

    set_clauses.append("updated_at = NOW()")
    sql = f"UPDATE knowledge_objects SET {', '.join(set_clauses)} WHERE id = %(object_id)s RETURNING id"
    rows = run_raw_query(sql, params)

    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


@router.delete("/objects/{object_id}")
def delete_object(object_id: int):
    sql = "DELETE FROM knowledge_objects WHERE id = %(object_id)s RETURNING id"
    rows = run_raw_query(sql, {"object_id": object_id})
    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


# ==================== Indicators ====================

@router.get("/indicators")
def list_indicators():
    sql = "SELECT * FROM knowledge_indicators ORDER BY id"
    rows = run_raw_query(sql)

    indicators = []
    for row in rows:
        indicators.append({
            "id": row["id"],
            "indicator_name": row["indicator_name"],
            "formula": row["formula"],
            "description": row["description"],
            "unit": row["unit"],
            "category": row["category"],
            "related_tables": row["related_tables"],
            "created_at": str(row["created_at"]) if row["created_at"] else None,
            "updated_at": str(row["updated_at"]) if row["updated_at"] else None,
        })

    return {"code": 200, "data": indicators, "message": "success"}


@router.post("/indicators")
def create_indicator(body: KnowledgeIndicatorCreate):
    sql = """
        INSERT INTO knowledge_indicators
            (indicator_name, formula, description, unit, category, related_tables)
        VALUES (%(indicator_name)s, %(formula)s, %(description)s, %(unit)s, %(category)s, %(related_tables)s)
        RETURNING id
    """
    rows = run_raw_query(sql, {
        "indicator_name": body.indicator_name,
        "formula": body.formula,
        "description": body.description,
        "unit": body.unit,
        "category": body.category,
        "related_tables": body.related_tables,
    })

    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


@router.put("/indicators/{indicator_id}")
def update_indicator(indicator_id: int, body: KnowledgeIndicatorUpdate):
    set_clauses = []
    params = {"indicator_id": indicator_id}

    if body.indicator_name is not None:
        set_clauses.append("indicator_name = %(indicator_name)s")
        params["indicator_name"] = body.indicator_name
    if body.formula is not None:
        set_clauses.append("formula = %(formula)s")
        params["formula"] = body.formula
    if body.description is not None:
        set_clauses.append("description = %(description)s")
        params["description"] = body.description
    if body.unit is not None:
        set_clauses.append("unit = %(unit)s")
        params["unit"] = body.unit
    if body.category is not None:
        set_clauses.append("category = %(category)s")
        params["category"] = body.category
    if body.related_tables is not None:
        set_clauses.append("related_tables = %(related_tables)s")
        params["related_tables"] = body.related_tables

    if not set_clauses:
        return {"code": 200, "data": None, "message": "nothing to update"}

    set_clauses.append("updated_at = NOW()")
    sql = f"UPDATE knowledge_indicators SET {', '.join(set_clauses)} WHERE id = %(indicator_id)s RETURNING id"
    rows = run_raw_query(sql, params)

    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


@router.delete("/indicators/{indicator_id}")
def delete_indicator(indicator_id: int):
    sql = "DELETE FROM knowledge_indicators WHERE id = %(indicator_id)s RETURNING id"
    rows = run_raw_query(sql, {"indicator_id": indicator_id})
    result = {"id": rows[0]["id"]} if rows else {}
    return {"code": 200, "data": result, "message": "success"}


# ==================== Themes ====================

@router.get("/themes")
def list_themes():
    sql = "SELECT * FROM knowledge_themes ORDER BY id"
    rows = run_raw_query(sql)

    themes = []
    for row in rows:
        themes.append({
            "id": row["id"],
            "theme_name": row["theme_name"],
            "description": row["description"],
            "question_templates": row["question_templates"],
            "created_at": str(row["created_at"]) if row["created_at"] else None,
        })

    return {"code": 200, "data": themes, "message": "success"}


# ==================== Knowledge Graph ====================

@router.get("/graph")
def get_knowledge_graph():
    objects_sql = "SELECT id, object_name, object_type, related_tables FROM knowledge_objects ORDER BY id"
    objects_rows = run_raw_query(objects_sql)

    nodes = []
    for row in objects_rows:
        nodes.append({
            "id": f"obj_{row['id']}",
            "name": row["object_name"],
            "type": row["object_type"],
            "group": "object",
        })

    edges = []
    for row in objects_rows:
        if row["related_tables"]:
            tables = [t.strip() for t in row["related_tables"].split(",") if t.strip()]
            for table in tables:
                edges.append({
                    "source": f"obj_{row['id']}",
                    "target": f"tbl_{table}",
                    "relation": "references",
                })
                node_exists = any(n["id"] == f"tbl_{table}" for n in nodes)
                if not node_exists:
                    nodes.append({
                        "id": f"tbl_{table}",
                        "name": table,
                        "type": "table",
                        "group": "table",
                    })

    return {"code": 200, "data": {"nodes": nodes, "edges": edges}, "message": "success"}
