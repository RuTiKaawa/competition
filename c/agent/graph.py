"""LangGraph NL2SQL Agent — 自然语言 → 表定位 → SQL生成 → 执行 → 响应"""

from typing import TypedDict, Annotated, Sequence
import operator
import json

from langgraph.graph import StateGraph, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import LLM_CONFIG
from db.metadata import TABLES, QUICK_JUMP_RULES, find_table_by_name
from db.tools import match_tables_by_query, get_table_detail
from db.executor import execute_sql


# ── State 定义 ───────────────────────────────────────────
class AgentState(TypedDict):
    query: str                          # 用户原始输入
    intent: str                         # 意图类型: table_lookup | data_query
    keywords: list[str]                 # 提取的关键词
    matched_tables: list[dict]          # 匹配到的表列表
    sql: str                            # 生成的 SQL
    sql_result: dict                    # SQL 执行结果
    response: dict                      # 最终响应 (返回前端)
    error: str                          # 错误信息


# ── LLM 实例 ─────────────────────────────────────────────
def _build_llm():
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=LLM_CONFIG["temperature"],
        max_tokens=LLM_CONFIG["max_tokens"],
    )


# ── 系统 Prompt: 表结构上下文 ─────────────────────────────
def _build_table_context() -> str:
    """构建所有表的精简上下文,注入 LLM Prompt"""
    lines = ["# 可用数据表 (数据库: manufacturing_db)\n"]
    for t in TABLES:
        fields_str = ", ".join(f"{f['name']}({f['type']})" for f in t["fields"])
        lines.append(
            f"## {t['table_name']} [{t['category']}] — {t['table_alias']}\n"
            f"描述: {t['description']}\n"
            f"字段: {fields_str}\n"
            f"关联表: {', '.join(t['related_tables']) if t['related_tables'] else '无'}\n"
        )
    return "\n".join(lines)


TABLE_CONTEXT = _build_table_context()

SQL_SYSTEM_PROMPT = f"""{TABLE_CONTEXT}

你是一个制造业数据库的 SQL 专家。请根据用户的自然语言问题,生成对应的 PostgreSQL SQL 查询。

规则:
# 角色与目标
你是一个专门服务于制造业企业数据底座的智能问析首席分析师，代号“DataCopilot”。
你的核心使命是：接收业务人员的自然语言提问，通过严谨的推理，生成准确的可执行代码（SQL/Python），并提供可解释的分析结论。你绝不猜测，绝不懂装懂。

# 硬性约束规则（必须遵守）
1. **只读原则**：你只能生成 SELECT 查询语句，严禁生成 DELETE、DROP、UPDATE、INSERT 等写入或破坏性操作。
2. **防幻觉原则**：如果用户提问中涉及的指标或字段在【业务知识库】和【数据字典】中不存在，你必须明确告知“找不到对应字段”，并给出最接近的候选字段建议，严禁捏造字段名。
3. **分步执行**：对于复杂问题（如归因分析、多表关联），必须先输出“分析步骤计划”，再生成代码。

# 核心推理工作流（Chain of Thought）
在生成最终代码前，你必须在 `<thinking>` 标签内进行如下结构化思考（但思考过程对用户简洁展示）：

**Step 1: 意图拆解**
- 判定问题类型：[统计查询 / 趋势分析 / 异常归因 / 机器学习建模 / 报告生成]
- 提取核心实体：涉及哪些业务对象？（如：工单、工序、产品、设备）

**Step 2: 语义映射（最关键）**
- 将用户自然语言映射到具体的【数据字典】字段。
- *示例映射*：“良率” → `qualified_qty / total_qty`；“停机时长” → `downtime_minutes`。
- 如果用户说“最近”，默认定义为最近7天（或根据当前日期推算）。

**Step 3: 技术选型**
- 若只需查、统、排 -> 选用 **SQL**。
- 若涉及预测、聚类、异常检测或相关性分析（如“分析A和B是否相关”） -> 选用 **Python (Pandas + Scikit-learn)**。
- 若需要美观图表 -> 生成 Base64 编码的 Matplotlib 图表。

**Step 4: 代码生成与校验**
- 检查表名和字段名是否完全匹配【数据字典】。
- 检查 SQL 中是否包含必要的 WHERE 条件（防止全表扫描超时）。

# 业务知识库上下文（此处由后端动态注入）
【当前可用的数据表结构】
-- 这里由你的后端程序动态替换为实际的表结构、字段注释和样例值
-- 例如：
-- 表名: production_order (生产工单表)
-- 字段: order_id, product_code, plan_qty, actual_qty, start_time, end_time
-- 表名: quality_inspection (质量检验表)
-- 字段: id, order_id,工序(process), 合格数(qualified_qty), 不良数(defect_qty), 检验日期(inspect_date)

【业务指标口径说明】
-- 这里注入预定义的指标计算逻辑
-- 良率 (%) = qualified_qty / (qualified_qty + defect_qty) * 100
-- 设备综合效率(OEE) = ...

# 少样本示例（Few-shot Examples）
当用户问“分析各工序良率”时：
<示例思考>
意图：分组统计。实体：工序、良率。
映射：工序 -> process；良率 -> 计算口径为 sum(合格数)/sum(总数)。
SQL生成策略：按 process 分组，聚合计算。
</示例思考>
输出：
1. 理解确认：我将按“工序”分组，计算每个工序的良率（合格数/总数）。
2. SQL代码：
   SELECT process, 
          ROUND(SUM(qualified_qty) * 100.0 / SUM(qualified_qty + defect_qty), 2) as yield_rate
   FROM quality_inspection
   GROUP BY process ORDER BY yield_rate DESC;

# 输出格式规范（必须严格按照此结构返回给前端）
请始终以 JSON 或严格的 Markdown 结构返回，以便前端解析：

**返回结构：**
1. **意图理解**：（用一句话向用户确认你理解的意思，例如：“您是想查看近7天各产线的产量对吧？”）
2. **分析思路**：（简要说明你的操作步骤，例如：“我将关联工单表和产量表，按日期分组求和”）
3. **生成的代码块**：（```sql ... ``` 或 ```python ... ```）
4. **执行结果摘要**：（在代码执行并拿到数据后，生成总结，例如：“A产线产量最高，B产线本周波动较大”）
5. **下一步追问建议**：（生成 2 个相关追问，例如：“需要我进一步分析B产线波动的原因吗？”）

# 异常处理机制
- 如果用户意图模糊（例如只说了“分析设备”），不要瞎猜。请回复：
  “检测到关键词‘设备’，设备数据涉及停机时长、报警次数、运行效率等多个维度，请问您具体想关注哪个方面？或者您可以参考以下问法：[问法1], [问法2]。”
- 如果生成的 SQL 涉及多表连接，请优先使用 LEFT JOIN，并注明连接键。
"""


# ── Node 1: 意图理解 ─────────────────────────────────────
def understand_intent(state: AgentState) -> AgentState:
    """解析用户意图: 是查表(table_lookup)还是查数据(data_query)"""
    query = state["query"]

    # 数据查询关键词 (优先级更高)
    data_query_patterns = [
        "分析", "统计", "趋势", "对比", "汇总", "计算",
        "排名", "排行", "最高", "最低", "平均", "占比",
        "图表", "可视化", "报告", "预测", "关联",
    ]

    # 查表关键词
    lookup_patterns = [
        "查", "看看", "有哪些字段", "字段", "结构", "元数据",
        "是什么表", "什么表", "有哪些表", "表结构", "描述",
        "介绍", "说明",
    ]

    is_data_query = any(p in query for p in data_query_patterns)
    is_lookup = any(p in query for p in lookup_patterns)

    # 快速跳转规则匹配
    keywords = []
    for kw, tbl in QUICK_JUMP_RULES.items():
        if kw in query:
            keywords.append(kw)

    # 数据查询优先于查表
    if is_data_query:
        state["intent"] = "data_query"
    elif is_lookup or keywords:
        state["intent"] = "table_lookup"
    else:
        state["intent"] = "data_query"

    state["keywords"] = list(set(keywords))  # 去重
    return state


# ── Node 2: 表匹配 ───────────────────────────────────────
def match_tables(state: AgentState) -> AgentState:
    """根据关键词匹配数据库表,优先使用快速跳转规则"""
    query = state["query"]
    keywords = state["keywords"]
    matched = match_tables_by_query(query)

    # 快速跳转规则优先: 将匹配的跳转目标表提到第一位
    if keywords and state["intent"] == "table_lookup":
        for kw in keywords:
            target_table = QUICK_JUMP_RULES.get(kw)
            if target_table:
                detail = get_table_detail(target_table)
                if detail:
                    jump_entry = {
                        "table_name": detail["table_name"],
                        "table_alias": detail["table_alias"],
                        "category": detail["category"],
                        "description": detail["description"],
                        "row_count": detail["row_count"],
                        "field_count": detail["field_count"],
                        "keywords_matched": [kw],
                    }
                    # 如果目标表不在匹配列表中,插入到第一位
                    existing_names = {t["table_name"] for t in matched}
                    if target_table not in existing_names:
                        matched.insert(0, jump_entry)
                    else:
                        # 移到第一位
                        matched = [t for t in matched if t["table_name"] != target_table]
                        matched.insert(0, jump_entry)
                    break

    if not matched:
        state["matched_tables"] = match_tables_by_query("")
    else:
        state["matched_tables"] = matched

    return state


# ── Node 3: SQL 生成 ─────────────────────────────────────
def generate_sql(state: AgentState) -> AgentState:
    """用 LLM 生成 SQL (仅 data_query 模式)"""
    if state["intent"] == "table_lookup":
        state["sql"] = ""
        return state

    query = state["query"]
    matched = state["matched_tables"]
    if not matched:
        state["sql"] = ""
        state["error"] = "未找到匹配的数据表,请尝试更具体的查询"
        return state

    # 构建匹配表的上下文
    matched_ctx = "\n".join(
        f"- {t['table_name']}: {t['description']}" for t in matched[:5]
    )

    try:
        llm = _build_llm()
        messages = [
            SystemMessage(content=SQL_SYSTEM_PROMPT),
            HumanMessage(
                content=f"用户问题: {query}\n\n"
                f"匹配到的相关表:\n{matched_ctx}\n\n"
                f"请生成对应的 SQL 查询语句:"
            ),
        ]
        response = llm.invoke(messages)
        sql = response.content.strip()

        # 清理可能的 markdown 包裹
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1]
            if sql.endswith("```"):
                sql = sql[:-3]
        sql = sql.strip()

        if sql == "TABLE_LOOKUP":
            state["intent"] = "table_lookup"
            state["sql"] = ""
        else:
            state["sql"] = sql
    except Exception as e:
        # LLM 不可用时,回退到基于规则的模拟逻辑
        state["sql"] = _fallback_sql(query, matched)

    return state


def _fallback_sql(query: str, matched: list[dict]) -> str:
    """LLM 不可用时的规则回退 SQL 生成"""
    top_table = matched[0]["table_name"] if matched else ""
    fields = []
    t = find_table_by_name(top_table)
    if t:
        fields = [f["name"] for f in t["fields"]]

    if "良率" in query or "工序" in query:
        return (
            "SELECT p.process_name AS 工序,\n"
            "       SUM(o.input_qty) AS 投入,\n"
            "       SUM(o.good_qty) AS 合格,\n"
            "       SUM(o.defect_qty) AS 不良,\n"
            "       ROUND(SUM(o.good_qty)::numeric/SUM(o.input_qty)*100,2) AS 良率\n"
            "FROM mes_process_output o\n"
            "JOIN dim_process p USING(process_id)\n"
            "GROUP BY p.process_name, p.process_seq\n"
            "ORDER BY p.process_seq"
        )
    elif "不良" in query or "缺陷" in query:
        return (
            "SELECT defect_type AS 不良类型,\n"
            "       COUNT(*) AS 数量,\n"
            "       ROUND(COUNT(*)::numeric/SUM(COUNT(*)) OVER()*100,1) AS 占比\n"
            "FROM qms_defect_detail\n"
            "GROUP BY defect_type\n"
            "ORDER BY COUNT(*) DESC\n"
            "LIMIT 10"
        )
    elif "停机" in query or "设备" in query:
        return (
            "SELECT e.equipment_name AS 设备,\n"
            "       l.line_name AS 产线,\n"
            "       d.start_time AS 停机开始,\n"
            "       d.downtime_minutes AS 持续分钟,\n"
            "       CASE WHEN d.is_planned THEN '计划' ELSE '非计划' END AS 类型,\n"
            "       d.reason AS 原因\n"
            "FROM eqp_downtime_record d\n"
            "JOIN dim_equipment e USING(equipment_id)\n"
            "JOIN dim_production_line l USING(line_id)\n"
            "ORDER BY d.start_time DESC\n"
            "LIMIT 20"
        )
    elif "库存" in query:
        return (
            "SELECT p.product_code AS 产品编码,\n"
            "       i.warehouse_code AS 仓库,\n"
            "       i.available_qty AS 可用库存,\n"
            "       i.safety_stock_qty AS 安全库存\n"
            "FROM inv_inventory_snapshot i\n"
            "JOIN dim_product p USING(product_id)\n"
            "WHERE i.snapshot_date = (SELECT MAX(snapshot_date) FROM inv_inventory_snapshot)\n"
            "ORDER BY i.available_qty ASC\n"
            "LIMIT 20"
        )
    else:
        field_list = ", ".join(fields[:6]) if fields else "*"
        return f"SELECT {field_list}\nFROM {top_table}\nLIMIT 20"


# ── Node 4: SQL 执行 ─────────────────────────────────────
def execute_query(state: AgentState) -> AgentState:
    """执行 SQL (模拟)"""
    if state["intent"] == "table_lookup":
        state["sql_result"] = {}
        return state

    sql = state["sql"]
    if not sql:
        state["sql_result"] = {}
        return state

    state["sql_result"] = execute_sql(sql)
    return state


# ── Node 5: 生成响应 ─────────────────────────────────────
def generate_response(state: AgentState) -> AgentState:
    """组装最终响应"""
    intent = state["intent"]
    matched_tables = state["matched_tables"]
    query = state["query"]

    if intent == "table_lookup":
        # 查表模式: 返回匹配的表详情
        if matched_tables:
            top = matched_tables[0]
            detail = get_table_detail(top["table_name"])
            state["response"] = {
                "type": "table_lookup",
                "query": query,
                "matched_table": {
                    "table_name": top["table_name"],
                    "table_alias": top["table_alias"],
                    "category": top["category"],
                    "description": top["description"],
                    "row_count": top["row_count"],
                    "field_count": top["field_count"],
                },
                "detail": detail,
                "related_tables": matched_tables[1:4] if len(matched_tables) > 1 else [],
                "steps": [
                    {"step": 1, "name": "意图理解", "status": "done", "detail": f"识别为表查询: {query}"},
                    {"step": 2, "name": "表匹配", "status": "done", "detail": f"定位到 {top['table_alias']}({top['table_name']})"},
                    {"step": 3, "name": "返回表详情", "status": "done", "detail": f"共 {top['field_count']} 个字段, {top['row_count']} 行"},
                ],
            }
        else:
            state["response"] = {
                "type": "table_lookup",
                "query": query,
                "matched_table": None,
                "detail": None,
                "related_tables": [],
                "steps": [
                    {"step": 1, "name": "意图理解", "status": "done", "detail": f"识别为表查询: {query}"},
                    {"step": 2, "name": "表匹配", "status": "error", "detail": "未找到匹配的表"},
                ],
            }
    else:
        # 数据查询模式: 返回 SQL + 执行结果
        sql = state["sql"]
        sql_result = state["sql_result"]
        steps = [
            {"step": 1, "name": "意图理解", "status": "done", "detail": f"识别为数据查询: {query}"},
            {"step": 2, "name": "表匹配", "status": "done", "detail": f"涉及 {len(matched_tables)} 张表"},
            {"step": 3, "name": "SQL生成", "status": "done", "detail": "SQL 已生成"},
            {"step": 4, "name": "执行查询", "status": "done", "detail": f"耗时 {sql_result.get('elapsed_ms', '?')}ms · {sql_result.get('row_count', 0)} 行"},
        ]

        if state.get("error"):
            steps.append({"step": 5, "name": "错误", "status": "error", "detail": state["error"]})

        state["response"] = {
            "type": "data_query",
            "query": query,
            "sql": sql,
            "matched_tables": [{"table_name": t["table_name"], "table_alias": t["table_alias"]} for t in matched_tables[:5]],
            "result": sql_result,
            "steps": steps,
        }

    return state


# ── 路由: 根据意图决定下一步 ───────────────────────────────
def route_after_match(state: AgentState) -> str:
    if state["intent"] == "table_lookup":
        return "generate_response"  # 直接跳到响应
    return "generate_sql"


def route_after_sql(state: AgentState) -> str:
    if state["intent"] == "table_lookup":
        return "generate_response"
    return "execute_sql"


# ── 构建 Graph ───────────────────────────────────────────
def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)

    workflow.add_node("understand_intent", understand_intent)
    workflow.add_node("match_tables", match_tables)
    workflow.add_node("generate_sql", generate_sql)
    workflow.add_node("execute_sql", execute_query)
    workflow.add_node("generate_response", generate_response)

    workflow.set_entry_point("understand_intent")
    workflow.add_edge("understand_intent", "match_tables")

    workflow.add_conditional_edges(
        "match_tables",
        route_after_match,
        {
            "generate_sql": "generate_sql",
            "generate_response": "generate_response",
        },
    )

    workflow.add_conditional_edges(
        "generate_sql",
        route_after_sql,
        {
            "execute_sql": "execute_sql",
            "generate_response": "generate_response",
        },
    )

    workflow.add_edge("execute_sql", "generate_response")
    workflow.add_edge("generate_response", END)

    return workflow.compile()


# ── 单例 agent ───────────────────────────────────────────
_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_graph()
    return _agent


def ask(query: str) -> dict:
    """对外暴露的主入口: 输入自然语言,返回结果"""
    agent = get_agent()
    result = agent.invoke({
        "query": query,
        "intent": "",
        "keywords": [],
        "matched_tables": [],
        "sql": "",
        "sql_result": {},
        "response": {},
        "error": "",
    })
    return result["response"]
