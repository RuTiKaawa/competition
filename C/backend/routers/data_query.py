import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.sql_executor import execute_query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/data", tags=["data_query"])


class QueryRequest(BaseModel):
    sql: str


@router.post("/query")
def query_data(body: QueryRequest):
    logger.info(f"Executing SQL query: {body.sql[:200]}")
    result = execute_query(body.sql)

    if "error" in result:
        logger.warning(f"Query returned error: {result['error']}")
        return {"code": 400, "data": None, "message": result["error"]}

    return {"code": 200, "data": result, "message": "success"}
