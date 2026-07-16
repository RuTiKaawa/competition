import logging

from fastapi import APIRouter
from pydantic import BaseModel

from services.chart_builder import build_echarts_option

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chart", tags=["chart"])


class ChartRequest(BaseModel):
    type: str
    title: str
    data: dict | list


@router.post("/build")
def build_chart(body: ChartRequest):
    logger.info(f"Building chart: type={body.type}, title={body.title}")
    option = build_echarts_option(body.type, body.title, body.data)

    if "error" in option:
        return {"code": 400, "data": None, "message": option["error"]}

    return {"code": 200, "data": option, "message": "success"}
