"""数智问析 · Multi-Agent NL2SQL — FastAPI 后端"""

import time
import json as json_mod
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import SERVER_HOST, SERVER_PORT, UI_DIR, LLM_CONFIG
from db.tools import get_all_tables, get_table_detail
from db.executor import execute_sql, get_table_row_counts
from db.connection_manager import (
    test_connection, list_connections, save_connection, delete_connection,
    switch_connection, get_connection_status,
)
from agent.multi_agent import ask as agent_ask
from agent.chart_agent import generate_chart
from ml.trainer import (
    MODEL_TYPES, train_model, predict, list_trained_models, get_numeric_tables,
)

app = FastAPI(title="数智问析 NL2SQL Agent", version="2.0.0")

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


class AskRequest(BaseModel):
    query: str


class AskResponse(BaseModel):
    type: str
    query: str
    data: dict
    elapsed_ms: int


# ── API ──────────────────────────────────────────────────

@app.get("/api/metadata/tables")
def list_tables():
    try:
        counts = get_table_row_counts()
    except Exception:
        counts = {}
    tables = get_all_tables()
    for t in tables:
        t["row_count"] = counts.get(t["table_name"], t.get("row_count", 0))
    return {"tables": tables}


@app.get("/api/metadata/tables/{table_name}")
def table_detail(table_name: str):
    detail = get_table_detail(table_name)
    if not detail:
        raise HTTPException(status_code=404, detail=f"表 {table_name} 不存在")
    return detail


@app.get("/api/dashboard")
def dashboard():
    """仪表盘: 返回关键指标 + 图表"""
    try:
        counts = get_table_row_counts()
    except Exception:
        counts = {}
    return {
        "stats": {
            "total_tables": len(counts),
            "total_products": counts.get("dim_product", 0),
            "total_processes": counts.get("dim_process", 0),
            "total_output_records": counts.get("mes_process_output", 0),
            "total_defects": counts.get("qms_defect_detail", 0),
        }
    }


@app.get("/api/dashboard/charts")
def dashboard_charts():
    """仪表盘图表数据"""
    charts = []
    # 工序良率柱状图
    try:
        result = execute_sql(
            "SELECT p.process_name AS 工序, ROUND(AVG(o.good_qty::numeric/o.input_qty)*100,1) AS 良率 "
            "FROM mes_process_output o JOIN dim_process p USING(process_id) "
            "GROUP BY p.process_name, p.process_seq ORDER BY p.process_seq"
        )
        if result["success"] and result["rows"]:
            chart = generate_chart(result["columns"], result["rows"], "工序良率排行")
            charts.append({"title": "各工序良率", "chart": chart, "data": result})
    except Exception:
        pass

    # 不良类型饼图
    try:
        result2 = execute_sql(
            "SELECT defect_type AS 类型, COUNT(*) AS 数量 "
            "FROM qms_defect_detail GROUP BY defect_type ORDER BY COUNT(*) DESC"
        )
        if result2["success"] and result2["rows"]:
            chart2 = generate_chart(result2["columns"], result2["rows"], "不良类型占比")
            charts.append({"title": "不良类型分布", "chart": chart2, "data": result2})
    except Exception:
        pass

    # 库存预警
    try:
        result3 = execute_sql(
            "SELECT p.product_name AS 产品, i.available_qty AS 可用, i.safety_stock_qty AS 安全库存 "
            "FROM inv_inventory_snapshot i JOIN dim_product p USING(product_id) "
            "ORDER BY i.available_qty ASC LIMIT 10"
        )
        if result3["success"] and result3["rows"]:
            chart3 = generate_chart(result3["columns"], result3["rows"], "库存水位")
            charts.append({"title": "库存水位 (最低10项)", "chart": chart3, "data": result3})
    except Exception:
        pass

    return {"charts": charts}


@app.post("/api/agent/ask")
def agent_ask_api(req: AskRequest):
    t0 = time.time()
    result = agent_ask(req.query)
    elapsed = int((time.time() - t0) * 1000)
    return AskResponse(type=result["type"], query=req.query, data=result, elapsed_ms=elapsed)


# ── 图表生成 ────────────────────────────────────────────

class ChartRequest(BaseModel):
    columns: list[str]
    rows: list[dict]
    title: str = ""
    force_type: str = ""  # bar | line | pie


class CustomChartRequest(BaseModel):
    title: str
    chart_type: str = "bar"
    description: str


class RecommendChartRequest(BaseModel):
    query: str
    columns: list[str]
    rows: list[dict]


@app.post("/api/chart/generate")
def chart_generate(cfg: ChartRequest):
    return generate_chart(cfg.columns, cfg.rows, cfg.title, force_type=cfg.force_type)


@app.post("/api/chart/custom")
def chart_custom(cfg: CustomChartRequest):
    """自定义图表: 用户描述 → 复用 multi_agent SQL 生成 → 执行 → 生成图表"""
    from db.executor import execute_sql
    from agent.multi_agent import sql_agent, schema_agent, supervisor

    # 用 multi_agent 的前半段: supervisor → schema_agent → sql_agent
    state = {
        "query": cfg.description, "intent": "data_query", "keywords": [],
        "rag_tables": [], "matched_tables": [], "schema_context": "", "sql": "",
        "sql_result": {}, "chart": {}, "response": {}, "steps": [], "error": "", "retry_count": 0,
    }
    state = supervisor(state)
    state = schema_agent(state)
    state = sql_agent(state)
    sql = state["sql"]
    if not sql or not sql.strip().upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="无法生成有效的SQL，请换一种描述方式")

    result = execute_sql(sql)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=f"SQL执行失败: {result.get('error','')}")

    if not result["rows"] or len(result["rows"]) == 0:
        raise HTTPException(status_code=400, detail="查询无数据，请调整描述")

    chart = generate_chart(result["columns"], result["rows"], cfg.title, force_type=cfg.chart_type)
    return {
        "title": cfg.title,
        "chart": chart,
        "sql": sql,
        "data": {"columns": result["columns"], "rows": result["rows"][:20]},
    }


@app.post("/api/chart/recommend-type")
def chart_recommend_type(cfg: RecommendChartRequest):
    """AI 推荐最佳图表类型"""
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import SystemMessage, HumanMessage

    col_info = ", ".join(cfg.columns)
    row_count = len(cfg.rows)
    # 统计数值列
    num_cols = cfg.columns[1:]
    try:
        llm = ChatOpenAI(model=LLM_CONFIG["model"], api_key=LLM_CONFIG["api_key"],
                         base_url=LLM_CONFIG["base_url"], temperature=0)
        prompt = f"""你是数据可视化专家。根据以下信息推荐最佳图表类型。

可用类型: bar(柱状图), barh(横向柱状图), stacked(堆叠柱状图), line(折线图), area(面积图), pie(饼图), donut(环形图), scatter(散点图)

规则:
- 排名/对比多类 → barh
- 多指标对比 → bar
- 堆叠组成/占比对比 → stacked
- 趋势/时间序列 → line 或 area
- 占比/分布(<8类) → donut
- 两数值列相关性 → scatter
- 默认 → bar

只输出类型关键词,不解释。"""
        resp = llm.invoke([SystemMessage(content=prompt), HumanMessage(
            content=f"查询: {cfg.query}\n列: {col_info}\n共{row_count}行, 示例行: {str(cfg.rows[0])}")])
        rec = resp.content.strip().lower()
        valid = ["bar", "barh", "stacked", "line", "area", "pie", "donut", "scatter"]
        if rec not in valid:
            rec = "bar"
    except Exception:
        rec = "bar"
    return {"recommended": rec}


# ── 数据库连接管理 ──────────────────────────────────────

class ConnectionConfig(BaseModel):
    name: str = "默认连接"
    host: str = "localhost"
    port: int = 5432
    user: str = "postgres"
    password: str = ""
    dbname: str = "postgres"


@app.get("/api/db/status")
def db_status():
    return get_connection_status()


@app.get("/api/db/connections")
def db_list_connections():
    return {"connections": list_connections()}


@app.post("/api/db/test-connection")
def db_test_connection(cfg: ConnectionConfig):
    ok, msg = test_connection(cfg.model_dump())
    return {"success": ok, "message": msg}


@app.post("/api/db/connections")
def db_save_connection(cfg: ConnectionConfig):
    return save_connection(cfg.model_dump())


@app.delete("/api/db/connections/{name}")
def db_delete_connection(name: str):
    return delete_connection(name)


@app.post("/api/db/switch/{name}")
def db_switch_connection(name: str):
    result = switch_connection(name)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


# ── ML 建模 ─────────────────────────────────────────────

class TrainRequest(BaseModel):
    table: str
    target: str
    features: list[str]
    model_type: str  # linear/decision_tree/random_forest/logistic/kmeans/isolation
    params: dict | None = None


class PredictRequest(BaseModel):
    model_name: str
    data: dict


@app.get("/api/ml/tables")
def ml_tables():
    return {"tables": get_numeric_tables()}


@app.get("/api/ml/models")
def ml_models():
    return {"model_types": MODEL_TYPES, "trained": list_trained_models()}


@app.post("/api/ml/train")
def ml_train(req: TrainRequest):
    if req.model_type not in MODEL_TYPES:
        raise HTTPException(status_code=400, detail=f"不支持的模型类型: {req.model_type}")
    try:
        result = train_model(req.table, req.target, req.features, req.model_type, req.params)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ml/predict")
def ml_predict(req: PredictRequest):
    try:
        return predict(req.model_name, req.data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── 总览 ─────────────────────────────────────────────────

@app.get("/api/overview")
def overview():
    """总览页: 数据库连接 + 数据总览 + 关键指标"""
    # DB 连接状态
    db_status = get_connection_status()

    # 表概览
    try:
        counts = get_table_row_counts()
    except Exception:
        counts = {}
    tables = get_all_tables()
    for t in tables:
        t["row_count"] = counts.get(t["table_name"], t.get("row_count", 0))

    # 关键指标
    metrics = []
    metric_queries = [
        ("整体良率", "SELECT ROUND(SUM(good_qty)::numeric/NULLIF(SUM(input_qty),0)*100,2) AS 良率 FROM mes_process_output"),
        ("不良率", "SELECT ROUND(SUM(defect_qty)::numeric/NULLIF(SUM(input_qty),0)*100,2) AS 不良率 FROM mes_process_output"),
        ("总产量", "SELECT SUM(input_qty) AS 总投入 FROM mes_process_output"),
        ("不良总数", "SELECT COUNT(*) AS 不良总数 FROM qms_defect_detail"),
        ("库存预警数", "SELECT COUNT(*) AS 预警数 FROM inv_inventory_snapshot WHERE available_qty < safety_stock_qty"),
        ("设备停机次数", "SELECT COUNT(*) AS 停机次数 FROM eqp_downtime_record"),
        ("产品种类", "SELECT COUNT(*) AS 产品数 FROM dim_product"),
        ("产线数量", "SELECT COUNT(*) AS 产线数 FROM dim_production_line"),
    ]
    for label, sql in metric_queries:
        try:
            r = execute_sql(sql)
            if r["success"] and r["rows"]:
                val = list(r["rows"][0].values())[0]
                metrics.append({"label": label, "value": val, "ok": True})
            else:
                metrics.append({"label": label, "value": "-", "ok": False})
        except Exception:
            metrics.append({"label": label, "value": "-", "ok": False})

    return {
        "db": db_status,
        "tables": tables,
        "metrics": metrics,
    }


class ReportRequest(BaseModel):
    pass


@app.post("/api/overview/report")
async def overview_report(_req: ReportRequest = None):
    """AI 快速生成数据总览报告 — 流式输出"""
    from agent.report_agent import generate_report_stream

    # 收集数据上下文
    try:
        counts = get_table_row_counts()
    except Exception:
        counts = {}
    tables = get_all_tables()
    table_info = "\n".join(
        f"- {t['table_alias']}({t['table_name']}): {counts.get(t['table_name'], t.get('row_count', '?'))} 行"
        for t in tables
    )
    data_brief = []
    key_queries = [
        ("工序良率", "SELECT p.process_name, ROUND(SUM(o.good_qty)::numeric/NULLIF(SUM(o.input_qty),0)*100,2) AS 良率 FROM mes_process_output o JOIN dim_process p USING(process_id) GROUP BY p.process_name, p.process_seq ORDER BY p.process_seq"),
        ("不良类型分布", "SELECT defect_type, COUNT(*) AS cnt FROM qms_defect_detail GROUP BY defect_type ORDER BY cnt DESC LIMIT 5"),
        ("库存预警", "SELECT p.product_name, i.available_qty, i.safety_stock_qty FROM inv_inventory_snapshot i JOIN dim_product p USING(product_id) WHERE i.available_qty < i.safety_stock_qty ORDER BY i.available_qty ASC LIMIT 5"),
        ("设备状态", "SELECT equipment_type, COUNT(*) AS cnt FROM dim_equipment GROUP BY equipment_type"),
        ("产线产量", "SELECT l.line_name, SUM(o.input_qty) AS 总投入 FROM mes_process_output o JOIN dim_production_line l USING(line_id) GROUP BY l.line_name ORDER BY 总投入 DESC"),
        ("设备停机", "SELECT e.equipment_name, d.downtime_minutes, CASE WHEN d.is_planned THEN '计划' ELSE '非计划' END AS 类型, d.reason FROM eqp_downtime_record d JOIN dim_equipment e USING(equipment_id) ORDER BY d.start_time DESC LIMIT 5"),
    ]
    for label, sql in key_queries:
        try:
            r = execute_sql(sql)
            if r["success"] and r["rows"]:
                data_brief.append(f"【{label}】\n" + "\n".join(str(row) for row in r["rows"][:5]))
        except Exception:
            pass

    context = f"""数据库包含以下表:
{table_info}

关键数据摘要:
{chr(10).join(data_brief) if data_brief else '（数据库暂不可用）'}"""

    async def event_stream():
        try:
            async for token in generate_report_stream(context):
                # JSON 编码避免换行符等特殊字符破坏 SSE 协议
                payload = json_mod.dumps({"t": token})
                yield f"data: {payload}\n\n"
            done_payload = json_mod.dumps({"done": True})
            yield f"data: {done_payload}\n\n"
        except Exception as e:
            err_payload = json_mod.dumps({"error": str(e)})
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── 静态文件 ─────────────────────────────────────────────
import os
from starlette.responses import Response

class NoCacheStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        return response

if os.path.isdir(UI_DIR):
    app.mount("/", NoCacheStaticFiles(directory=UI_DIR, html=True), name="ui")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
