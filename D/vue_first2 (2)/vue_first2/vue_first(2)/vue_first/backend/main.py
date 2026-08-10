"""数智问析 · NL2SQL Agent — FastAPI 后端（流式 LLMService + 动态数据库连接）"""

import time
import json as json_mod
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from routers import tables, knowledge, config
from database import get_database_config, switch_database, test_database_connection
from agent.llm_service import (
    LLMService, generate_analysis, generate_predict,
    generate_recommend_questions, cache_result, get_cached_result,
)
from agent.chart_agent import generate_chart
from ml.trainer import (
    MODEL_TYPES, train_model, predict, list_trained_models, get_numeric_tables,
)
import uvicorn

app = FastAPI(title="数智问析 NL2SQL Agent", version="2.0.0")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tables.router)
app.include_router(knowledge.router)
app.include_router(config.router)


class AskRequest(BaseModel):
    query: str
    history: list[dict] | None = None  # [{role, content}, ...]


class AskResponse(BaseModel):
    type: str
    query: str
    data: dict
    elapsed_ms: int


class AnalysisRequest(BaseModel):
    query: str
    sql: str = ""
    result: dict | None = None


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


class TrainRequest(BaseModel):
    table: str
    target: str
    features: list[str]
    model_type: str  # linear/decision_tree/random_forest/logistic/kmeans/isolation
    params: dict | None = None


class PredictRequest(BaseModel):
    model_name: str
    data: dict


class DatabaseConfig(BaseModel):
    db_type: str = "postgresql"
    host: str
    port: int = 5432
    database: str
    user: str
    password: str


# ── 数据库连接（当前项目 pg8000/SQLAlchemy 体系）────────────

@app.get("/api/database/config")
def database_config():
    return get_database_config()


@app.post("/api/database/test")
def test_database(config: DatabaseConfig):
    try:
        test_database_connection(config.model_dump())
        return {"success": True, "message": "数据库连接成功"}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据库连接失败：{exc}") from exc


@app.post("/api/database/switch")
def switch_database_connection(config: DatabaseConfig):
    try:
        switch_database(config.model_dump())
        # 同步 agent 的连接池（psycopg2 体系）
        try:
            from db.executor import reload_pool
            from db.connection_manager import clear_active_cache
            clear_active_cache()
            reload_pool()
        except Exception:
            pass
        return {"success": True, "message": "数据库已切换", "config": get_database_config()}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"数据库切换失败：{exc}") from exc


# ── Agent 主接口 ─────────────────────────────────────────

@app.post("/api/agent/ask")
def agent_ask_api(req: AskRequest):
    t0 = time.time()
    service = LLMService(req.query, req.history)
    final_response = {}
    for event in service.run():
        if event["type"] == "done":
            final_response = event.get("response", {})
        elif event["type"] == "error":
            raise HTTPException(status_code=500, detail=event.get("content", "未知错误"))
    elapsed = int((time.time() - t0) * 1000)

    # 缓存结果供分析/预测端点复用
    if service.sql_result.get("rows"):
        cache_result(req.query, service.sql, service.sql_result, service.schema_context)

    return AskResponse(type=final_response.get("type", ""), query=req.query, data=final_response, elapsed_ms=elapsed)


@app.post("/api/agent/stream")
async def agent_stream_api(req: AskRequest):
    """流式输出端点 — SSE 协议"""
    from agent.stream import ask_stream
    return StreamingResponse(
        ask_stream(req.query, req.history),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )


# ── 分析 / 预测 / 推荐（独立端点，不阻塞主查询）────────

@app.post("/api/agent/analyze")
async def agent_analyze_api(req: AnalysisRequest):
    """独立分析端点 — 对已执行的 SQL 结果做数据解读（流式）"""
    from agent.stream import analysis_stream

    sql_result = req.result or {}
    if not sql_result.get("rows"):
        cached = get_cached_result(req.query)
        if cached:
            sql_result = cached["sql_result"]

    if not sql_result.get("rows"):
        raise HTTPException(status_code=400, detail="无可用数据，请先执行查询")

    return StreamingResponse(
        analysis_stream(req.sql, req.query, sql_result),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agent/predict")
async def agent_predict_api(req: AnalysisRequest):
    """独立预测端点 — 对已执行的 SQL 结果做趋势预测（流式）"""
    from agent.stream import predict_stream

    sql_result = req.result or {}
    if not sql_result.get("rows"):
        cached = get_cached_result(req.query)
        if cached:
            sql_result = cached["sql_result"]

    if not sql_result.get("rows"):
        raise HTTPException(status_code=400, detail="无可用数据，请先执行查询")

    return StreamingResponse(
        predict_stream(sql_result),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.post("/api/agent/recommend")
def agent_recommend_api(req: AnalysisRequest):
    """独立推荐问题端点 — 根据查询上下文生成后续问题"""
    sql_result = req.result or {}
    sql = req.sql
    schema_context = ""

    if not sql_result.get("rows"):
        cached = get_cached_result(req.query)
        if cached:
            sql_result = cached["sql_result"]
            sql = sql or cached.get("sql", "")
            schema_context = cached.get("schema_context", "")

    if not sql_result.get("rows"):
        raise HTTPException(status_code=400, detail="无可用数据，请先执行查询")

    questions = generate_recommend_questions(req.query, sql, sql_result, schema_context)
    return {"questions": questions}


# ── 图表生成 ────────────────────────────────────────────

@app.post("/api/chart/generate")
def chart_generate(cfg: ChartRequest):
    return generate_chart(cfg.columns, cfg.rows, cfg.title, force_type=cfg.force_type)


@app.post("/api/chart/custom")
def chart_custom(cfg: CustomChartRequest):
    """自定义图表: 用户描述 → LLMService SQL 生成 → 执行 → 生成图表"""
    service = LLMService(cfg.description)
    service.intent = "data"
    service.matched_tables = []
    try:
        from db.tools import match_tables_by_query
        service.matched_tables = match_tables_by_query(cfg.description)[:8]
    except Exception:
        pass

    if service.matched_tables:
        from agent.llm_service import _build_schema_fast
        candidate_names = [t["table_name"] for t in service.matched_tables]
        service.schema_context = _build_schema_fast(candidate_names)

    list(service._generate_sql_stream())  # 流式积攒 SQL
    sql = service.sql
    if not sql or not sql.strip().upper().startswith("SELECT"):
        raise HTTPException(status_code=400, detail="无法生成有效的SQL，请换一种描述方式")

    from db.executor import execute_sql
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
    from config import LLM_CONFIG

    col_info = ", ".join(cfg.columns)
    row_count = len(cfg.rows)
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


# ── ML 建模 ─────────────────────────────────────────────

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


# ── 全库分析报告（流式）────────────────────────────────

@app.post("/api/overview/report")
async def overview_report(_req: AnalysisRequest = None):
    """AI 快速生成数据总览报告 — 流式输出（动态适配当前数据库）"""
    from agent.report_agent import generate_report_stream
    from db.executor import execute_sql, get_table_row_counts

    try:
        counts = get_table_row_counts()
    except Exception:
        counts = {}
    real_tables = []
    try:
        r = execute_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        if r["success"]:
            real_tables = [row["table_name"] for row in r["rows"]]
    except Exception:
        pass

    from db.metadata import find_table_by_name
    table_info_lines = []
    for name in real_tables:
        detail = find_table_by_name(name)
        alias = detail["table_alias"] if detail else name
        table_info_lines.append(f"- {alias}({name}): {counts.get(name, '?')} 行")
    table_info = "\n".join(table_info_lines)

    data_brief = []
    for name in real_tables[:6]:
        try:
            r = execute_sql(f"SELECT * FROM \"{name}\" LIMIT 3")
            if r["success"] and r["rows"]:
                detail = find_table_by_name(name)
                alias = detail["table_alias"] if detail else name
                data_brief.append(f"【{alias}】\n" + "\n".join(str(row) for row in r["rows"]))
        except Exception:
            pass

    context = f"""数据库包含以下表:
{table_info}

关键数据摘要:
{chr(10).join(data_brief) if data_brief else '（数据库暂不可用）'}"""

    async def event_stream():
        try:
            async for token in generate_report_stream(context):
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


@app.get("/")
def root():
    return {"message": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8010)
