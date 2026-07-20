"""Multi-Agent NL2SQL System — 优化版: 防幻觉 + 高准确率"""

import json, re, time
from typing import TypedDict

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import LLM_CONFIG
from db.metadata import TABLES, QUICK_JUMP_RULES, find_table_by_name
from db.tools import match_tables_by_query, get_table_detail
from db.executor import execute_sql
from agent.chart_agent import generate_chart


class AgentState(TypedDict):
    query: str
    intent: str
    keywords: list[str]
    rag_tables: list[dict]
    matched_tables: list[dict]
    schema_context: str
    sql: str
    sql_result: dict
    chart: dict
    response: dict
    steps: list[dict]
    error: str
    retry_count: int


def _llm(temp: float = None):
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=temp if temp is not None else LLM_CONFIG["temperature"],
        max_tokens=LLM_CONFIG["max_tokens"],
    )


# ====== PROMPTS ===========================================

SQL_SYSTEM_PROMPT = """你是一个 PostgreSQL SQL 生成器。你必须严格按照以下规则输出。

## 规则（违反任何一条都会导致 SQL 执行失败）
1. **只输出** 一条合法的 PostgreSQL SELECT 语句，不要加任何解释、注释或 markdown 代码块
2. 表名和字段名**只能使用**下面「可用表结构」中列出的，**绝对禁止**编造不存在的表名或字段名
3. 所有聚合查询必须带 GROUP BY
4. JOIN 使用 `USING(column)` 或 `ON a.col = b.col` 语法
5. **别名规则**: 使用双引号包裹含特殊字符的别名，如 AS "停机时长(分)"；或直接用纯中文不加括号，如 AS 停机时长
6. 如果用户没有指定 LIMIT，默认加 `LIMIT 30`
7. 禁止使用子查询中的 ORDER BY（除非有 LIMIT）
8. 数值计算使用 `::numeric` 转换避免整数除法
9. **绝对禁止** 输出 INSERT / UPDATE / DELETE / DROP / CREATE
10. **确保 SQL 完整**，不要因长度截断

## 常见查询模板参考
- 排行: `SELECT col, COUNT(*) AS 数量 FROM t GROUP BY col ORDER BY COUNT(*) DESC LIMIT N`
- 良率: `SELECT ... ROUND(SUM(good_qty)::numeric / SUM(input_qty) * 100, 2) AS 良率 FROM ...`
- 趋势: `SELECT stat_date, SUM(...) FROM ... GROUP BY stat_date ORDER BY stat_date`
- 关联: `SELECT a.x, b.y FROM fact JOIN dim USING(id)`

## Few-Shot 示例
Q: 分析各工序良率
A: SELECT p.process_name AS 工序, SUM(o.good_qty) AS 合格, SUM(o.defect_qty) AS 不良, ROUND(SUM(o.good_qty)::numeric/SUM(o.input_qty)*100,2) AS 良率 FROM mes_process_output o JOIN dim_process p USING(process_id) GROUP BY p.process_name, p.process_seq ORDER BY p.process_seq

Q: 不良类型排行
A: SELECT defect_type AS 不良类型, COUNT(*) AS 数量 FROM qms_defect_detail GROUP BY defect_type ORDER BY COUNT(*) DESC LIMIT 10

Q: 库存低于安全库存的产品
A: SELECT p.product_name AS 产品, i.available_qty AS 可用库存, i.safety_stock_qty AS 安全库存 FROM inv_inventory_snapshot i JOIN dim_product p USING(product_id) WHERE i.available_qty < i.safety_stock_qty ORDER BY i.available_qty ASC
"""


# ====== SQL Validator =====================================

def _validate_sql(sql: str, schema_context: str) -> tuple[bool, str, str]:
    """SQL 后校验 + 自动修复"""
    if not sql or not sql.strip().upper().startswith("SELECT"):
        return False, "SQL 必须以 SELECT 开头", sql

    # 修复：AS 别名中的括号 → 双引号包裹
    import re
    sql = re.sub(r'\bAS\s+(\w+)\(([^)]*)\)', r'AS "\1(\2)"', sql, flags=re.IGNORECASE)
    sql = re.sub(r'(\w+)\(([^)]*)\)\s*,', r'"\1(\2)"', sql)
    sql = re.sub(r'(\w+)\(([^)]*)\)\s*FROM', r'"\1(\2)" FROM', sql)

    # 从 schema 提取所有合法表名和字段
    valid_tables = set(re.findall(r'## (\w+)', schema_context))
    valid_fields = set()
    for f in re.findall(r'(\w+)\(', schema_context):
        valid_fields.add(f)
    # 字段描述里也有括号，更精确地提取
    field_pattern = re.findall(r'(\w+)\(\w+\)', schema_context)
    for f in field_pattern:
        valid_fields.add(f)

    # 提取 SQL 中的表名
    sql_upper = sql.upper()
    tables_in_sql = set()

    # FROM / JOIN 后面的表名
    for m in re.finditer(r'(?:FROM|JOIN)\s+(\w+)', sql_upper):
        tables_in_sql.add(m.group(1))

    # USING() 中的表名可以去重，忽略

    # 检查是否有非法表名
    for t in tables_in_sql:
        t_lower = t.lower()
        if t_lower not in valid_tables and t_lower not in ['USING', 'ON']:
            # 可能是别名，放过短名称
            if len(t) <= 3:
                continue
            return False, f"SQL 引用了不存在的表: {t}，可用表: {valid_tables}", sql

    # 检查危险关键词
    dangerous = ["INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE"]
    for d in dangerous:
        if d in sql_upper:
            return False, f"SQL 包含危险操作: {d}", sql

    return True, "", sql


# ====== NODES =============================================

def supervisor(state: AgentState) -> AgentState:
    query = state["query"]
    steps = [{"step": 1, "name": "意图理解", "status": "done", "detail": query[:60]}]

    # 意图检测
    data_words = ["分析", "统计", "趋势", "对比", "汇总", "排名", "排行", "最高", "最低", "平均", "占比",
                  "找出", "列出", "显示", "查询", "告诉我", "低于", "高于", "预警", "大于", "小于",
                  "最近", "所有", "全部", "每个", "各", "多少", "记录"]
    lookup_words = ["查", "看看", "字段", "结构", "元数据", "是什么表", "表结构", "有哪些表", "有哪些字段", "表", "什么表"]
    is_data = any(w in query for w in data_words)
    is_lookup = any(w in query for w in lookup_words)
    keywords = [kw for kw in QUICK_JUMP_RULES if kw in query]

    # 数据类问题优先 data_query，纯查表才走 table_lookup
    if is_data:
        state["intent"] = "data_query"
    elif is_lookup and not is_data:
        state["intent"] = "table_lookup"
    elif keywords and is_lookup:
        state["intent"] = "table_lookup"
    else:
        state["intent"] = "data_query"

    state["keywords"] = list(set(keywords))
    state["steps"] = steps
    state["retry_count"] = 0

    # 表匹配
    rule_matched = match_tables_by_query(query)
    rag_matched = []
    try:
        from agent.rag import search_tables
        for r in search_tables(query, k=5):
            detail = get_table_detail(r["table_name"])
            if detail:
                rag_matched.append({
                    "table_name": detail["table_name"],
                    "table_alias": detail["table_alias"],
                    "category": detail["category"],
                    "description": detail["description"],
                    "row_count": detail["row_count"],
                    "field_count": detail["field_count"],
                    "score": r["score"],
                })
    except Exception:
        pass

    seen = set()
    merged = []
    for t in rag_matched:
        if t["table_name"] not in seen:
            merged.append(t); seen.add(t["table_name"])
    for t in rule_matched:
        if t["table_name"] not in seen:
            merged.append(t); seen.add(t["table_name"])

    if state["intent"] == "table_lookup" and state["keywords"]:
        for kw in state["keywords"]:
            target = QUICK_JUMP_RULES.get(kw)
            if target and target in seen:
                merged = [t for t in merged if t["table_name"] == target] + [t for t in merged if t["table_name"] != target]
                break

    state["matched_tables"] = merged[:5] if merged else match_tables_by_query("")
    steps.append({"step": 2, "name": "表匹配", "status": "done", "detail": f"规则+RAG → {len(merged)} 张候选表"})
    state["steps"] = steps
    return state


def schema_agent(state: AgentState) -> AgentState:
    """根据匹配的表,构建注入 LLM 的完整 schema 上下文"""
    tables = state["matched_tables"]
    ctx_lines = ["# 可用表（只能使用下面的表名和字段名）\n"]
    all_fields = set()
    for t in tables[:3]:  # 只送 top 3，避免 prompt 过长
        detail = find_table_by_name(t["table_name"])
        if not detail:
            continue
        f_lines = [f"  {f['name']} {f['type']}" for f in detail["fields"][:8]]  # 只取前8个核心字段
        ctx_lines.append(
            f"## {detail['table_name']} — {detail['table_alias']}\n"
            + "\n".join(f_lines)
        )
        # 加关联提示
        if detail['related_tables']:
            ctx_lines.append(f"关联: {', '.join(detail['related_tables'])}")
        ctx_lines.append("")
        all_fields.update(f['name'] for f in detail['fields'])
    state["schema_context"] = "\n".join(ctx_lines)
    state["steps"].append({"step": 3, "name": "Schema分析", "status": "done", "detail": f"{min(len(tables),3)} 张表, {len(all_fields)} 个字段"})
    return state


def route_after_schema(state: AgentState) -> str:
    return "build_response" if state["intent"] == "table_lookup" else "sql_agent"


def sql_agent(state: AgentState) -> AgentState:
    query = state["query"]
    schema = state["schema_context"]

    sql = ""
    try:
        llm = _llm(temp=0.0)  # temperature=0 大幅减少幻觉
        full_prompt = f"{SQL_SYSTEM_PROMPT}\n\n{schema}"
        resp = llm.invoke([SystemMessage(content=full_prompt), HumanMessage(content=f"用户问题: {query}")])
        sql = resp.content.strip()
        # 清理 markdown
        if sql.startswith("```"):
            lines = sql.split("\n")
            sql = "\n".join(lines[1:]) if lines[0].startswith("```") else sql
            if sql.endswith("```"):
                sql = sql.rstrip("```").rstrip()
        sql = sql.strip()

        # 后校验（同时修复括号别名问题）
        valid, err, cleaned = _validate_sql(sql, schema)
        sql = cleaned  # 使用修复后的 SQL
        if not valid and state["retry_count"] < 2:
            state["retry_count"] += 1
            # 重试一次
            resp2 = llm.invoke([
                SystemMessage(content=f"{full_prompt}\n\n上次生成的 SQL 有错误: {err}\n请修正后重新生成。"),
                HumanMessage(content=query)
            ])
            sql2 = resp2.content.strip()
            if sql2.startswith("```"):
                lines = sql2.split("\n")
                sql2 = "\n".join(lines[1:]) if lines[0].startswith("```") else sql2
                if sql2.endswith("```"):
                    sql2 = sql2.rstrip("```").rstrip()
            v2, _, c2 = _validate_sql(sql2.strip(), schema)
            sql = c2  # 使用修复后的 SQL
            if v2:
                sql = sql2.strip()
    except Exception:
        sql = ""

    if not sql or not sql.strip().upper().startswith("SELECT"):
        sql = _fallback_sql(query, state["matched_tables"])

    state["sql"] = sql
    status = "done" if sql.strip().upper().startswith("SELECT") else "fallback"
    state["steps"].append({"step": 4, "name": "SQL生成", "status": status, "detail": f"{'AI生成' if status=='done' else '规则回退'} SQL"})
    return state


def _fallback_sql(query: str, tables: list[dict]) -> str:
    if not tables:
        return "SELECT 1"
    top = tables[0]["table_name"]
    detail = find_table_by_name(top)
    fields = [f["name"] for f in detail["fields"]] if detail else ["*"]
    field_str = ", ".join(fields[:6])

    q = query
    if any(w in q for w in ["良率", "工序"]):
        return "SELECT p.process_name AS 工序, SUM(o.input_qty) AS 投入, SUM(o.good_qty) AS 合格, SUM(o.defect_qty) AS 不良, ROUND(SUM(o.good_qty)::numeric/NULLIF(SUM(o.input_qty),0)*100,2) AS 良率 FROM mes_process_output o JOIN dim_process p USING(process_id) GROUP BY p.process_name, p.process_seq ORDER BY p.process_seq"
    if any(w in q for w in ["不良", "缺陷"]):
        return "SELECT defect_type AS 不良类型, COUNT(*) AS 数量 FROM qms_defect_detail GROUP BY defect_type ORDER BY COUNT(*) DESC LIMIT 10"
    if any(w in q for w in ["停机", "宕机"]):
        return "SELECT e.equipment_name AS 设备, l.line_name AS 产线, d.downtime_minutes AS 停机分钟, CASE WHEN d.is_planned THEN '计划' ELSE '非计划' END AS 类型, d.reason AS 原因 FROM eqp_downtime_record d JOIN dim_equipment e USING(equipment_id) JOIN dim_production_line l USING(line_id) ORDER BY d.start_time DESC LIMIT 10"
    if any(w in q for w in ["库存", "仓储"]):
        return "SELECT p.product_name AS 产品, i.available_qty AS 可用库存, i.safety_stock_qty AS 安全库存, CASE WHEN i.available_qty < i.safety_stock_qty THEN '预警' ELSE '正常' END AS 状态 FROM inv_inventory_snapshot i JOIN dim_product p USING(product_id) ORDER BY i.available_qty ASC"
    if any(w in q for w in ["工单"]):
        return "SELECT work_order_id AS 工单号, plan_qty AS 计划产量, actual_qty AS 实际产量, status AS 状态 FROM mes_work_order ORDER BY start_date DESC LIMIT 20"
    if any(w in q for w in ["检验", "质检", "质量"]):
        return "SELECT inspection_date AS 日期, sample_qty AS 抽检数, defect_qty AS 不良数, result AS 结果 FROM qms_inspection ORDER BY inspection_date DESC LIMIT 20"
    if any(w in q for w in ["产品", "物料"]):
        return f"SELECT product_name AS 产品, category AS 分类, spec AS 规格 FROM dim_product ORDER BY product_id"
    if any(w in q for w in ["设备", "机械", "机器"]):
        return f"SELECT equipment_name AS 设备, equipment_type AS 类型, model AS 型号, status AS 状态 FROM dim_equipment ORDER BY equipment_id"
    if any(w in q for w in ["产线", "车间", "生产线"]):
        return f"SELECT line_name AS 产线, workshop AS 车间, supervisor AS 主管, status AS 状态 FROM dim_production_line ORDER BY line_id"
    return f"SELECT {field_str} FROM {top} LIMIT 20"


def executor_node(state: AgentState) -> AgentState:
    t0 = time.time()
    result = execute_sql(state["sql"])
    ms = int((time.time() - t0) * 1000)
    state["sql_result"] = result
    state["steps"].append({
        "step": 5, "name": "SQL执行", "status": "done" if result["success"] else "error",
        "detail": f"{ms}ms · {'成功' if result['success'] else '失败'} · {result['row_count']} 行"
    })
    if not result["success"]:
        state["error"] = result.get("error", "未知错误")
    return state


def chart_agent(state: AgentState) -> AgentState:
    result = state["sql_result"]
    if not result.get("success") or not result.get("rows") or len(result["rows"]) < 2:
        state["chart"] = {"type": "none", "svg": ""}
        return state
    chart = generate_chart(result["columns"], result["rows"], state["query"])
    state["chart"] = chart
    if chart["type"] != "none":
        state["steps"].append({"step": 6, "name": "图表生成", "status": "done", "detail": f"生成 {chart['type']} 图"})
    return state


def build_response(state: AgentState) -> AgentState:
    if state["intent"] == "table_lookup":
        matched = state["matched_tables"]
        if matched:
            top = matched[0]
            detail = get_table_detail(top["table_name"])
            state["response"] = {
                "type": "table_lookup",
                "matched_table": {"table_name": top["table_name"], "table_alias": top["table_alias"], "category": top["category"], "description": top["description"], "row_count": top["row_count"], "field_count": top["field_count"]},
                "detail": detail,
                "related_tables": matched[1:4],
                "steps": state["steps"],
            }
        else:
            state["response"] = {"type": "table_lookup", "matched_table": None, "detail": None, "related_tables": [], "steps": state["steps"]}
    else:
        matched = state["matched_tables"]
        state["response"] = {
            "type": "data_query",
            "sql": state["sql"],
            "matched_tables": [{"table_name": t["table_name"], "table_alias": t["table_alias"]} for t in matched[:5]],
            "result": state["sql_result"],
            "chart": state.get("chart", {"type": "none", "svg": ""}),
            "steps": state["steps"],
            "error": state.get("error", ""),
        }
    return state


def build_graph():
    wf = StateGraph(AgentState)
    wf.add_node("supervisor", supervisor)
    wf.add_node("schema_agent", schema_agent)
    wf.add_node("sql_agent", sql_agent)
    wf.add_node("executor", executor_node)
    wf.add_node("chart_agent", chart_agent)
    wf.add_node("build_response", build_response)

    wf.set_entry_point("supervisor")
    wf.add_edge("supervisor", "schema_agent")
    wf.add_conditional_edges("schema_agent", route_after_schema, {"build_response": "build_response", "sql_agent": "sql_agent"})
    wf.add_edge("sql_agent", "executor")
    wf.add_edge("executor", "chart_agent")
    wf.add_edge("chart_agent", "build_response")
    wf.add_edge("build_response", END)
    return wf.compile()


_agent = None

def get_agent():
    global _agent
    if _agent is None:
        _agent = build_graph()
    return _agent


def ask(query: str) -> dict:
    agent = get_agent()
    result = agent.invoke({
        "query": query, "intent": "", "keywords": [], "rag_tables": [],
        "matched_tables": [], "schema_context": "", "sql": "",
        "sql_result": {}, "chart": {}, "response": {}, "steps": [], "error": "", "retry_count": 0,
    })
    return result["response"]
