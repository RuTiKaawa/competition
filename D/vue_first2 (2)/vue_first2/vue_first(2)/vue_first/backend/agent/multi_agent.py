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
    chart_config: dict   # sql_agent 输出的图表配置 (type + title)
    response: dict
    steps: list[dict]
    error: str
    retry_count: int
    history: list[dict]
    ml_intent: dict      # ML 建模意图 JSON
    ml_result: dict      # ML 执行结果


def _llm(temp: float = None):
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=temp if temp is not None else LLM_CONFIG["temperature"],
        max_tokens=LLM_CONFIG["max_tokens"],
    )


# ====== PROMPTS ===========================================

CHAT_CLASSIFY_PROMPT = """你是一个智能路由器。判断用户输入属于以下哪一类，只输出类别关键词:

- "chat": 问候、闲聊、自我介绍、问能力、感谢、再见、天气、笑话、翻译、写文字、哲学问题等不需要查数据库的问题
- "gibberish": 乱码、纯数字、纯符号、纯表情、无意义字母组合（如 asdf、aaaa、1111）、单个随机字符
- "analyze_db": 用户想了解当前数据库整体情况（"分析数据库""看看有什么数据""有哪些表""数据库概览""当前库""数据总览"）
- "data": 需要通过 SQL 查询数据库内容来回答的问题（查具体数据、统计、排行、趋势）
- "lookup": 仅限查看表结构/字段定义/元数据
- "ml": 机器学习建模请求（训练模型、预测、聚类、异常检测、回归、分类）

关键区分:
- "分析数据库" "有什么数据" "看看数据库" "当前数据库" "数据总览" → analyze_db
- "有哪些表" "表结构" → lookup（只查单表结构）
- "查机械表" "查产品表" "看看XX表" "XX表有什么字段" → lookup（查表结构）
- "列出所有设备" "显示产品列表" "查询产量" "分析良率" → data（查数据内容）
- 如果用户提到了具体数据列的筛选/排序/统计/名字/数量 → data
- "查/看看 + 表名" → lookup
- "列出/显示/查询/分析 + 内容" → data
- "训练模型" "预测" "聚类" "异常检测" "回归分析" "分类" "机器学习" "随机森林" "决策树" "KMeans" "建模" → ml
- "用XX模型预测/分析/训练" → ml

用户输入: {query}
分类:"""


CHAT_SYSTEM_PROMPT = """你是"数智问析"平台的 AI 助手，一个专业的制造业数据分析平台。

身份: 你集成在制造企业数据中台，连接了工序产量、不良缺陷、库存、设备停机、工单、检验等制造数据表。

能力:
- 智能问析：自然语言查询数据库，自动生成 SQL 并执行
- 数据可视化：自动生成柱状图、折线图、饼图等图表
- AI 报告生成：一键生成行业专家级数据分析报告
- 机器学习建模：支持线性回归、决策树、随机森林、聚类等

回复规则:
1. 用户问"你是谁"/"你是什么" → 简短介绍身份和核心能力
2. 用户问"你能做什么"/"你会什么" → 列举核心功能
3. 用户输入乱码/无意义文字 → 友好提示"输入的内容我不太理解，您可以尝试问我：分析各工序良率、不良类型排行、库存预警等"
4. 用户发纯表情/单个字 → 友好回复"您好！有什么数据问题需要帮您分析吗？"
5. 用户问与制造数据无关的问题 → 礼貌说明你的专业领域是制造数据分析，并引导可用功能
6. 用户说"谢谢"/"再见"等礼貌用语 → 友好回应
7. 保持回复简洁，2-5 句话为宜，不要长篇大论"""


SQL_SYSTEM_PROMPT = """你是一个 PostgreSQL SQL 生成器。你必须严格按照以下规则输出。

## 核心原则
**仔细阅读所有可用表**，根据用户问题的语义选择最相关的表和字段。不要只盯着第一张表，要找到含义最匹配的表。
- 例如用户问"工厂"，而可用表中有 test_factories 包含 factory_name 字段，就应该用 test_factories
- 例如用户问"订单"，而可用表中有 test_orders 包含 order_id 字段，就应该用 test_orders
- 例如用户问"材料/物料/供应商"，而可用表中有 test_materials，就应该用 test_materials

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
    # 只修复紧跟 AS 的别名，不碰 SQL 函数
    import re
    sql = re.sub(r'\bAS\s+(\w+)\(([^)]*)\)', r'AS "\1(\2)"', sql, flags=re.IGNORECASE)

    # SQL 函数白名单，这些不能碰
    SQL_FUNCS = {'NULLIF','SUM','COUNT','AVG','MAX','MIN','ROUND','COALESCE','CAST','EXTRACT',
                 'DATE_TRUNC','LOWER','UPPER','TRIM','LENGTH','REPLACE','CONCAT','SUBSTRING',
                 'ABS','CEIL','FLOOR','POWER','SQRT','MOD','GREATEST','LEAST','NOW','CURRENT_DATE'}

    # 修复裸别名中的括号（不在 SQL 函数白名单中的才处理）
    def _fix_bare_alias(m):
        word = m.group(1)
        inner = m.group(2)
        if word.upper() in SQL_FUNCS:
            return f'{word}({inner})'  # SQL 函数原样保留
        return f'"{word}({inner})"'    # 别名加双引号
    sql = re.sub(r'(\w+)\(([^)]*)\)\s*FROM', lambda m: _fix_bare_alias(m) + ' FROM', sql)
    sql = re.sub(r'(\w+)\(([^)]*)\)\s*,', lambda m: _fix_bare_alias(m) + ' ,', sql)

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

def _classify_intent(query: str) -> str:
    """使用 LLM 智能分类用户意图"""
    # 先快速关键词检测，避免常见场景浪费 LLM 调用
    q = query.strip()
    if not q:
        return "gibberish"
    # 纯符号/纯数字检测
    if re.match(r'^[\d\s,.!?;:，。！？；：…]+$', q) and len(q) <= 6:
        return "gibberish"
    if re.match(r'^[a-z]{1,5}$', q, re.IGNORECASE):
        return "gibberish"

    # 优先关键词快速通道
    chat_quick = ["你是谁","你好","谢谢","再见","嗨","hello","hi","早上好","晚上好","哈哈","嘿嘿","你能做什么","你会什么","你是谁"]
    for w in chat_quick:
        if w in q:
            return "chat"

    # ML 快速通道
    ml_quick = ["训练模型","预测","聚类","异常检测","回归","分类","机器学习","随机森林","决策树","KMeans","孤立森林","建模","线性回归"]
    for w in ml_quick:
        if w in q:
            return "ml"

    # 数据库分析快速通道
    db_analyze = ["分析数据库","看看数据库","当前数据库","数据库概览","有什么数据","数据总览","看看有什么","看看库"]
    for w in db_analyze:
        if w in q:
            return "analyze_db"

    # 查表快速通道（仅当明确提及表/结构/字段时才是 lookup）
    lookup_quick = ["有哪些表","表结构","字段","是什么表","什么表","什么样的表","有哪些字段"]
    for w in lookup_quick:
        if w in q:
            return "lookup"

    # "看看XX" / "查XX" / "查询XX" → 看后面跟什么
    if any(k in q for k in ["看看", "查", "查询"]):
        if any(dw in q for dw in ["结构", "字段", "有哪些表"]):
            return "lookup"
        return "data"

    # data 快速通道：高频数据查询关键词
    data_quick = ["分析","统计","排行","排名","良率","不良","库存","停机","产量","产能","趋势","对比",
                  "汇总","占比","最高","最低","平均","列出","查询","显示","预警","TOP","top",
                  "各工序","各产线","各产品","各工厂","各设备","每个","多少","有哪些",
                  "关键","状态","启用","停用","合格","不合格","完成","进行中","数量","情况"]
    for w in data_quick:
        if w in q:
            return "data"

    # 实体属性查询：如"哪些工序是关键的" "X设备的Y" → data
    if re.search(r"哪些.+是.+|.+是.+(关键|重要|启用|正常)", q):
        return "data"

    try:
        llm = _llm(temp=0.0)
        prompt = CHAT_CLASSIFY_PROMPT.format(query=q)
        resp = llm.invoke([HumanMessage(content=prompt)])
        result = resp.content.strip().lower()
        if result in ("chat", "gibberish", "data", "lookup", "ml", "analyze_db"):
            return result
    except Exception:
        pass
    return "chat"  # 兜底


def supervisor(state: AgentState) -> AgentState:
    query = state["query"]
    steps = [{"step": 1, "name": "意图理解", "status": "done", "detail": query[:60]}]

    intent = _classify_intent(query)

    # 闲聊/乱码：直接走 chat_responder
    if intent in ("chat", "gibberish"):
        state["intent"] = intent
        state["keywords"] = []
        state["steps"] = steps
        state["matched_tables"] = []
        steps.append({"step": 2, "name": "意图分类", "status": "done", "detail": f"识别为 {intent}"})
        state["steps"] = steps
        return state

    # ML 建模：走 ml 流水线
    if intent == "ml":
        state["intent"] = "ml"
        state["keywords"] = []
        state["steps"] = steps
        steps.append({"step": 2, "name": "意图分类", "status": "done", "detail": "识别为 ML 建模"})
        state["steps"] = steps
        return state

    # 分析数据库：走 analyze_db 处理器
    if intent == "analyze_db":
        state["intent"] = "analyze_db"
        state["keywords"] = []
        state["steps"] = steps
        steps.append({"step": 2, "name": "意图分类", "status": "done", "detail": "识别为 分析数据库"})
        state["steps"] = steps
        return state

    # data 或 lookup：走数据库流水线
    keywords = [kw for kw in QUICK_JUMP_RULES if kw in query]

    # 标记 intent
    if intent == "lookup":
        state["intent"] = "table_lookup"
    else:
        state["intent"] = "data_query"

    state["keywords"] = list(set(keywords))
    steps.append({"step": 2, "name": "意图分类", "status": "done", "detail": f"识别为 {intent}"})
    state["steps"] = steps
    state["retry_count"] = 0

    # 表匹配（复用现有逻辑）
    rule_matched = match_tables_by_query(query)
    rag_matched = []

    # 规则匹配命中率高时跳过 RAG 向量检索（省一次 Embedding API 调用）
    if len(rule_matched) >= 3 and rule_matched[0].get("keywords_matched"):
        pass  # 规则已经足够，跳过 RAG
    else:
        try:
            from agent.rag import search_tables
            for r in search_tables(query, k=5):
                detail = get_table_detail(r["table_name"])
                if detail:
                    rag_matched.append({
                        "table_name": detail["table_name"], "table_alias": detail["table_alias"],
                        "category": detail["category"], "description": detail["description"],
                        "row_count": detail["row_count"], "field_count": detail["field_count"],
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
    # 4. 补充所有真实表到候选，并做模糊表名匹配提升排名
    try:
        from db.tools import get_real_tables
        extra = []
        for rt in get_real_tables():
            name = rt["table_name"]
            # 模糊匹配：表名包含用户查询中的词则提升
            score = 0
            for word in query:
                if word in name.lower():
                    score += 1
            if name not in {t["table_name"] for t in merged}:
                merged.append({
                    "table_name": name, "table_alias": name, "category": "dim",
                    "description": "", "row_count": 0, "field_count": rt["field_count"],
                })
        # 按相关度排序：有元数据的排前面
        state["matched_tables"] = merged[:15]
    except Exception:
        pass
    steps.append({"step": 3, "name": "表匹配", "status": "done", "detail": f"规则+RAG → {len(merged)} 张候选表"})
    state["steps"] = steps
    return state


def schema_agent(state: AgentState) -> AgentState:
    """构建 schema 上下文（缓存版：首次查询后缓存 5 分钟）"""
    ctx_lines = ["# 可用表\n"]

    # 用缓存避免每次都查 DB
    real = _cached_get_real_tables()
    all_fields = set()
    count = 0
    for r in sorted(real, key=lambda x: x["table_name"]):
        name = r["table_name"]
        if count >= 15:
            break
        detail = find_table_by_name(name)
        alias = detail["table_alias"] if detail else name
        desc = detail["description"] if detail else ""
        fields = _cached_get_fields(name)

        if fields:
            f_lines = [f"  {f['name']} {f['type']} {f.get('key','')}" for f in fields[:15]]
            ctx_lines.append(f"## {name} — {alias}")
            if desc:
                ctx_lines.append(f"  描述: {desc}")
            ctx_lines.append("\n".join(f_lines))
            if detail and detail.get('related_tables'):
                ctx_lines.append(f"关联: {', '.join(detail['related_tables'])}")
            ctx_lines.append("")
            all_fields.update(f['name'] for f in fields)
            count += 1

    state["schema_context"] = "\n".join(ctx_lines)
    state["steps"].append({
        "step": 3, "name": "Schema分析", "status": "done",
        "detail": f"{count} 张表, {len(all_fields)} 个字段"
    })
    return state


def _get_real_table_fields(table_name: str) -> list[dict]:
    """从真实 DB 获取表字段"""
    try:
        from db.executor import execute_sql
        result = execute_sql(
            f"SELECT column_name AS name, data_type AS type, "
            f"CASE WHEN column_name IN ("
            f"  SELECT kcu.column_name FROM information_schema.table_constraints tc "
            f"  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
            f"  WHERE tc.table_name='{table_name}' AND tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'"
            f") THEN 'PK' ELSE '' END AS key, "
            f"'' AS description "
            f"FROM information_schema.columns "
            f"WHERE table_name='{table_name}' AND table_schema='public' "
            f"ORDER BY ordinal_position"
        )
        if result["success"] and result["rows"]:
            return [dict(r) for r in result["rows"]]
    except Exception:
        pass
    return []


# ── Schema 缓存（5分钟有效，避免每次查询都扫全部表）──

_schema_cache: dict = {}
_schema_cache_time: float = 0
_CACHE_TTL = 300  # 5分钟


def _cached_get_real_tables() -> list[dict]:
    global _schema_cache, _schema_cache_time
    now = time.time()
    if _schema_cache and (now - _schema_cache_time) < _CACHE_TTL:
        return _schema_cache.get("tables", [])
    try:
        from db.tools import get_real_tables
        tables = get_real_tables()
        _schema_cache = {"tables": tables}
        _schema_cache_time = now
        return tables
    except Exception:
        return _schema_cache.get("tables", [])


def _cached_get_fields(table_name: str) -> list[dict]:
    global _schema_cache, _schema_cache_time
    now = time.time()
    cache_key = f"fields_{table_name}"
    if _schema_cache and (now - _schema_cache_time) < _CACHE_TTL and cache_key in _schema_cache:
        return _schema_cache[cache_key]
    fields = _get_real_table_fields(table_name)
    _schema_cache[cache_key] = fields
    return fields


# ====== ML 建模节点 ======================================

def ml_intent_agent(state: AgentState) -> AgentState:
    """生成受限 ML 意图 JSON（不接触真实数据）- 程序选表/字段, LLM 只选模型"""
    from agent.ml_intent import generate_ml_intent, ALLOWED_MODELS

    query = state["query"]
    candidate_tables = []

    # 1. RAG 匹配
    try:
        from agent.rag import search_tables as rag_search
        for r in rag_search(query, k=5):
            candidate_tables.append(r["table_name"])
    except Exception:
        pass

    # 2. 关键词匹配
    from db.metadata import QUICK_JUMP_RULES, find_table_by_name
    for kw, tbl in QUICK_JUMP_RULES.items():
        if kw in query and tbl not in candidate_tables:
            candidate_tables.insert(0, tbl)

    # 3. 没匹配到就用数值表
    if not candidate_tables:
        try:
            from ml.trainer import get_numeric_tables
            nt = get_numeric_tables()
            candidate_tables = [t["table"] for t in nt[:5]]
        except Exception:
            pass

    best_table = candidate_tables[0] if candidate_tables else ""
    if not best_table:
        state["response"] = {"type": "ml_error", "error": "未找到可建模的数据表", "steps": state["steps"]}
        return state

    detail = find_table_by_name(best_table)
    alias = detail["table_alias"] if detail else best_table

    # 获取真实字段并分类（DB 不可用时回退到 metadata）
    all_fields = _get_real_table_fields(best_table)
    if not all_fields and detail:
        all_fields = [{"name": f["name"], "type": f["type"]} for f in detail.get("fields", [])]
    numeric_cols = [f["name"] for f in all_fields if f["type"] in ("integer","bigint","numeric","real","double precision","smallint","decimal")]
    all_cols = [f["name"] for f in all_fields]

    # 程序化选字段：数值列作特征，优先用最后一个数值列作 target
    features = numeric_cols[:-1] if len(numeric_cols) >= 2 else numeric_cols
    target = numeric_cols[-1] if len(numeric_cols) >= 2 else ""

    # 构建简化的 schema 上下文（只选模型和特征工程）
    ctx_lines = [f"# 表: {best_table} ({alias})"]
    ctx_lines.append(f"# 已自动选的 feature 字段: {json.dumps(features, ensure_ascii=False)}")
    ctx_lines.append(f"# 已自动选的 target 字段: {target}")
    ctx_lines.append(f"# 所有可用字段: {json.dumps(all_cols, ensure_ascii=False)}")
    ctx_lines.append("")
    ctx_lines.append("你的任务：选择最合适的模型类型和特征工程步骤。数据请求的 table/fields/target 已由系统自动填入。")

    schema_context = "\n".join(ctx_lines)

    # 只用 LLM 选模型 + 特征工程
    simple_prompt = """你是一个机器学习建模助手。

## 任务
用户需求: {query}

可用表: {table_name} ({alias})
已选特征字段: {features}
已选目标字段: {target}

## 请完成以下 JSON（只输出 JSON，不要解释）
{{
  "intent_type": "train",
  "user_summary": "一句话概括建模需求",
  "model_training": {{
    "model": "从下方列表选择一个模型名",
    "params": {{}}
  }},
  "feature_engineering": [
    {{"op": "dropna/standardize/label_encode/log_transform", "params": {{...}}}}
  ],
  "output_spec": {{
    "max_rows": 100
  }}
}}

## 可选模型
{model_list}

## 规则
- 聚类(KMeans)/异常检测(IsolationForest): target 为空字符串时使用
- 如果 target 不是空字符串且有数值列: 用 LinearRegression 或 RandomForestRegressor
- 如果 target 对应的数据看起来是分类(只有少数几个不同值): 用 RandomForestClassifier 或 LogisticRegression
- params 在约束范围内
- feature_engineering: dropna 在前, label_encode/log_transform/standardize 在后

输出 JSON:"""

    model_list = "\n".join(
        f"- {name}: {info['name']} ({info['task']})" for name, info in ALLOWED_MODELS.items()
    )

    try:
        llm = ChatOpenAI(
            model=LLM_CONFIG["model"], api_key=LLM_CONFIG["api_key"],
            base_url=LLM_CONFIG["base_url"], temperature=0.0, max_tokens=LLM_CONFIG["max_tokens"],
        )
        prompt = simple_prompt.format(
            query=query, table_name=best_table, alias=alias,
            features=json.dumps(features, ensure_ascii=False),
            target=target, model_list=model_list,
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()

        # 清理 markdown
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if lines[0].startswith("```") else raw
            if raw.endswith("```"):
                raw = raw.rstrip("```").rstrip()

        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            partial = json.loads(match.group(0))
        else:
            partial = {}
    except Exception:
        partial = {}

    # 组装完整 intent（table/fields/target 由程序填入，不可被 LLM 覆盖）
    intent = {
        "intent_type": "train",
        "user_summary": partial.get("user_summary", f"对 {alias} 进行建模分析"),
        "data_request": {
            "table": best_table,
            "fields": features,
            "target": target,
            "filter": "",
            "limit": 5000,
        },
        "feature_engineering": partial.get("feature_engineering", []),
        "model_training": partial.get("model_training", {"model": "RandomForestRegressor", "params": {}}),
        "output_spec": partial.get("output_spec", {"max_rows": 100}),
    }

    # 校验模型名
    model_name = intent["model_training"].get("model", "")
    if model_name not in ALLOWED_MODELS:
        # 根据 target 属性智能回退
        if target:
            intent["model_training"]["model"] = "RandomForestRegressor"
        else:
            intent["model_training"]["model"] = "KMeans"
        intent["model_training"]["params"] = {}

    state["ml_intent"] = intent
    summary = intent.get("user_summary", "")
    model_name = intent["model_training"]["model"]
    state["steps"].append({
        "step": 3, "name": "ML意图生成", "status": "done",
        "detail": f"{summary} → 表={best_table}, 模型={model_name}"
    })
    return state


def ml_executor(state: AgentState) -> AgentState:
    """安全执行 ML 意图"""
    from ml.executor import execute_ml_intent

    intent = state.get("ml_intent", {})
    if not intent:
        state["response"] = {
            "type": "ml_error",
            "error": "ML 意图为空，无法执行",
            "steps": state["steps"],
        }
        return state

    result = execute_ml_intent(intent)
    state["ml_result"] = result

    if result.get("success"):
        state["steps"].append({
            "step": 4, "name": "ML执行", "status": "done",
            "detail": f"模型: {result['model']['label']}, 指标: {result['metrics']}"
        })
    else:
        state["steps"].append({
            "step": 4, "name": "ML执行", "status": "error",
            "detail": result.get("error", "执行失败")
        })

    state["response"] = {
        "type": "ml_result",
        "ml_intent": intent,
        "ml_result": result,
        "steps": state["steps"],
    }
    return state


def _generate_analysis(query: str, sql_result: dict) -> str:
    """对 SQL 查询结果做 LLM 数据分析解读（失败时回退到规则生成）"""
    if not sql_result.get("rows"):
        return ""

    rows = sql_result["rows"]
    columns = sql_result["columns"]
    row_count = len(rows)

    # 规则 fallback（快速）
    fallback_parts = []
    fallback_parts.append(f"共 {row_count} 条记录，{len(columns)} 个字段")

    # 找数值列做简要统计
    for col in columns[:5]:
        vals = [float(r[col]) for r in rows if r[col] is not None and str(r[col]).replace('.','').replace('-','').isdigit()]
        if len(vals) >= 2:
            fallback_parts.append(f"{col}: 最大{max(vals):.0f}, 最小{min(vals):.0f}, 平均{sum(vals)/len(vals):.1f}")
            break

    rule_summary = "；".join(fallback_parts)

    # 尝试 LLM 增强分析（流式）
    # 简单查询跳过 LLM 分析
    if any(w in query for w in ["列出", "查看所有", "显示全部", "所有产品", "所有表"]):
        return rule_summary
    try:
        data_json = json.dumps(rows[:15], ensure_ascii=False, default=str)
        fields_info = ", ".join(columns)
        from agent.stream import make_streaming_llm
        llm = make_streaming_llm("数据洞察", temp=0.3, max_tokens=256)
        prompt = f"根据数据做3句话简洁总结:\n数据:{data_json[:800]}\n字段:{fields_info}\n用户问题:{query}"
        resp = llm.invoke([HumanMessage(content=prompt)])
        llm_text = resp.content.strip()
        if llm_text and len(llm_text) > 10:
            return llm_text
    except Exception:
        pass

    return rule_summary


# ====== 路由 =============================================

def route_after_schema(state: AgentState) -> str:
    if state["intent"] == "general_chat":
        return "chat_responder"
    return "build_response" if state["intent"] == "table_lookup" else "sql_agent"


def route_after_supervisor(state: AgentState) -> str:
    """闲聊/乱码跳过数据库管线, ML 走 ML 流水线, analyze_db 走分析流水线"""
    if state["intent"] in ("chat", "gibberish"):
        return "chat_responder"
    if state["intent"] == "ml":
        return "ml_intent_agent"
    if state["intent"] == "analyze_db":
        return "analyze_db_responder"
    return "schema_agent"


def chat_responder(state: AgentState) -> AgentState:
    """智能对话节点：处理闲聊、问候、乱输入等"""
    query = state["query"]
    intent = state["intent"]

    # gibberish 处理：不调用 LLM，直接给引导
    if intent == "gibberish":
        answer = "输入的内容我不太理解。您可以尝试问我：\n• 分析各工序良率\n• 不良类型排行\n• 库存预警分析\n• 查看数据库结构"
        state["response"] = {"type": "general_chat", "answer": answer, "steps": state["steps"]}
        state["steps"].append({"step": 3, "name": "智能回复", "status": "done", "detail": "识别为无效输入，给出引导"})
        return state

    try:
        llm = _llm(temp=0.7)
        resp = llm.invoke([SystemMessage(content=CHAT_SYSTEM_PROMPT), HumanMessage(content=query)])
        answer = resp.content.strip()
    except Exception:
        answer = "您好，我是数智问析 AI 助手，专注于制造业数据分析。请问有什么可以帮您的？"

    state["response"] = {"type": "general_chat", "answer": answer, "steps": state["steps"]}
    state["steps"].append({"step": 3, "name": "智能回复", "status": "done", "detail": "直接对话"})
    return state


def analyze_db_responder(state: AgentState) -> AgentState:
    """分析当前数据库：扫描所有表，生成中文可读摘要"""
    # 动态获取表列表和行数
    try:
        from db.executor import execute_sql
        tables_result = execute_sql(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        real_tables = [r["table_name"] for r in tables_result["rows"]] if tables_result["success"] else []
    except Exception:
        real_tables = []

    # 中文别名映射（与 main.py 保持一致）
    _CHINESE_HINTS = {
        "factory": "工厂", "factories": "工厂", "order": "订单", "orders": "订单",
        "material": "材料", "materials": "材料", "product": "产品", "products": "产品",
        "customer": "客户", "customers": "客户", "supplier": "供应商",
        "inventory": "库存", "sale": "销售", "user": "用户", "employee": "员工",
        "department": "部门", "warehouse": "仓库", "equipment": "设备",
        "sensor": "传感器", "device": "设备", "production": "生产",
        "process": "工序", "quality": "质量", "inspection": "检验",
        "defect": "不良", "downtime": "停机", "snapshot": "快照",
        "work": "工单", "line": "产线", "dim": "主数据", "mes": "制造执行",
        "qms": "质量管理", "eqp": "设备", "inv": "库存", "test": "测试",
    }

    def _guess_chinese_alias_static(name: str) -> str:
        parts = name.lower().replace("_", " ").split()
        hints = [_CHINESE_HINTS.get(p, "") for p in parts]
        hints = [h for h in hints if h]
        return "".join(hints) + "表" if hints else name

    table_info_lines = []
    for tname in real_tables[:20]:
        detail = find_table_by_name(tname)
        if detail:
            alias = detail["table_alias"]
            desc = detail["description"]
        else:
            alias = _guess_chinese_alias_static(tname)
            desc = ""

        # 获取真实行数
        rows = 0
        try:
            r = execute_sql(f"SELECT COUNT(*) AS cnt FROM \"{tname}\"")
            if r["success"] and r["rows"]:
                rows = r["rows"][0]["cnt"]
        except Exception:
            pass

        # 获取真实字段名
        cols = []
        try:
            r = execute_sql(
                f"SELECT column_name FROM information_schema.columns "
                f"WHERE table_name='{tname}' AND table_schema='public' ORDER BY ordinal_position"
            )
            if r["success"]:
                cols = [row["column_name"] for row in r["rows"][:5]]
        except Exception:
            pass

        col_str = "、".join(cols[:5]) if cols else "?"
        desc_str = f" — {desc}" if desc else ""
        table_info_lines.append(f"· {alias}（{tname}）: {rows}行, 字段: {col_str}{desc_str}")

    # 组装回复
    db_name = "当前数据库"
    try:
        from db.connection_manager import get_active_config
        cfg = get_active_config()
        db_name = cfg.get("dbname", "当前数据库")
    except Exception:
        pass

    total_rows = 0
    table_count = len(real_tables)
    for tname in real_tables:
        try:
            r = execute_sql(f"SELECT COUNT(*) AS cnt FROM \"{tname}\"")
            if r["success"] and r["rows"]:
                total_rows += r["rows"][0]["cnt"]
        except Exception:
            pass

    answer = f"当前连接数据库：{db_name}\n\n"
    answer += f"共 {table_count} 张表，约 {total_rows} 条数据：\n\n"
    answer += "\n".join(table_info_lines)
    answer += "\n\n你可以直接问我：\n" \
              "· 查询某张表的数据\n" \
              "· 统计分析（排行、汇总、趋势）\n" \
              "· 机器学习建模（预测、聚类、异常检测）"

    state["response"] = {
        "type": "analyze_db",
        "answer": answer,
        "tables": real_tables,
        "total_rows": total_rows,
        "steps": state["steps"],
    }
    state["steps"].append({"step": 3, "name": "数据库分析", "status": "done", "detail": f"{table_count}张表, {total_rows}行"})
    return state


def sql_agent(state: AgentState) -> AgentState:
    query = state["query"]
    history = state.get("history", [])

    # 用 M-Schema 格式生成 schema 上下文
    from agent.mschema import build_schema_context
    candidate_names = [t["table_name"] for t in state.get("matched_tables", [])]
    schema_context = build_schema_context(query, candidate_names)

    # 历史对话
    history_text = ""
    if history:
        history_text = "\n".join(
            f"- {'用户' if h.get('role')=='user' else 'AI'}: {h.get('content','')[:200]}"
            for h in history[-6:]
        )

    from agent.prompts import SQL_SYSTEM_PROMPT
    sql = ""
    chart_type = "bar"
    title = ""

    # 查询增强：检测业务词 → 强制聚合提示
    agg_hint = _build_agg_hint(query, state.get("matched_tables", []))

    try:
        # 流式 LLM：token 实时推送
        from agent.stream import make_streaming_llm
        llm = make_streaming_llm("SQL生成", temp=0.0, max_tokens=1024)
        prompt_text = SQL_SYSTEM_PROMPT.format(
            schema_context=schema_context,
            query=query,
        )
        if history_text:
            prompt_text += '\n\n## 对话历史（用于理解指代，如"他们""上面""它"等）\n' + history_text + '\n\n只针对用户最新问题生成 SQL，不要重复回答历史问题。'
        if agg_hint:
            prompt_text += f"\n\n## ⚠️ 强制聚合要求\n{agg_hint}\n\n**必须生成含GROUP BY的聚合SQL，不是 SELECT *！**"
        resp = llm.invoke([SystemMessage(content=prompt_text)])
        raw = resp.content.strip()

        # 清理 markdown 代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if lines[0].startswith("```") else raw
            if raw.endswith("```"):
                raw = raw.rstrip("```").rstrip()

        # 尝试解析 JSON 响应（新 Prompt 输出 JSON）
        import re as _re
        json_match = _re.search(r'\{[\s\S]*\}', raw)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                sql = parsed.get("sql", "")
                chart_type = parsed.get("chart_type", "table")
                title = parsed.get("title", "")
            except Exception:
                sql = raw  # JSON 解析失败，回退到原始输出
        else:
            sql = raw

        # sqlglot 安全校验
        from agent.sql_validator import validate_sql_safety
        valid, err, cleaned = validate_sql_safety(sql)
        sql = cleaned
        if not valid and state["retry_count"] < 2:
            state["retry_count"] += 1
            resp2 = llm.invoke([
                SystemMessage(content=f"{prompt_text}\n\n上次 SQL 错误: {err}。请修正后重新生成 JSON。"),
                HumanMessage(content=query)
            ])
            raw2 = resp2.content.strip()
            json_match2 = _re.search(r'\{[\s\S]*\}', raw2)
            if json_match2:
                try:
                    parsed2 = json.loads(json_match2.group(0))
                    sql = parsed2.get("sql", "")
                    chart_type = parsed2.get("chart_type", "table")
                    title = parsed2.get("title", "")
                except Exception:
                    pass
            _, _, cleaned2 = validate_sql_safety(sql)
            sql = cleaned2
    except Exception:
        sql = ""

    # 后校验：业务词要求聚合但 SQL 没有 → 使用 fallback
    if sql and _needs_aggregation(query) and "GROUP BY" not in sql.upper():
        sql = _fallback_sql(query, state["matched_tables"])
        chart_type = "table"

    if not sql or not sql.strip().upper().startswith("SELECT"):
        sql = _fallback_sql(query, state["matched_tables"])

    state["sql"] = sql
    state["chart_config"] = {"type": chart_type, "title": title}
    status = "done" if sql.strip().upper().startswith("SELECT") else "fallback"
    state["steps"].append({
        "step": 4, "name": "SQL生成", "status": status,
        "detail": f"{'AI生成' if status=='done' else '规则回退'} SQL · 图表={chart_type}"
    })
    return state


def _build_agg_hint(query: str, tables: list[dict]) -> str:
    """检测业务关键词 → 生成强制聚合提示"""
    hints = []
    q = query

    # 检测需要聚合的业务词，给出精确字段映射
    if any(w in q for w in ["良率"]):
        hints.append("良率 = SUM(good_qty)/NULLIF(SUM(input_qty),0)*100%")
        hints.append("需要 JOIN dim_process 获取工序名称，GROUP BY process_name")
    if any(w in q for w in ["不良"]):
        hints.append("不良统计 = COUNT(*)或SUM(defect_qty), GROUP BY defect_type/process_id")
    if any(w in q for w in ["排行", "排名", "TOP"]):
        hints.append("使用 ORDER BY 聚合值 DESC LIMIT 10")
    if any(w in q for w in ["趋势", "最近", "本周", "本月", "过去"]):
        hints.append("如果有日期字段，按日期 GROUP BY 并 ORDER BY 日期")
    if any(w in q for w in ["对比", "比较", "各", "每个", "不同"]):
        hints.append("必须用 GROUP BY 按分类字段分组")
    if any(w in q for w in ["库存", "预警"]):
        hints.append("库存预警: WHERE available_qty < safety_stock_qty")
    if any(w in q for w in ["产量", "产能"]):
        hints.append("产量/产能 = SUM(input_qty)或SUM(output相关), GROUP BY 分类字段")
    if any(w in q for w in ["停机"]):
        hints.append("停机 = SUM(downtime_minutes)或COUNT, GROUP BY reason/equipment")

    return "\n".join(hints) if hints else ""


def _needs_aggregation(query: str) -> bool:
    """检测查询是否需要聚合（含业务量化词）"""
    agg_words = ["良率", "不良", "排行", "排名", "对比", "比较",
                  "各", "每个", "不同", "产量", "产能", "统计",
                  "趋势", "占比", "汇总", "分析", "停机", "库存"]
    return any(w in query for w in agg_words)


def _fallback_sql(query: str, tables: list[dict]) -> str:
    """动态兜底 SQL — 含聚合逻辑"""
    if not tables:
        return "SELECT 1"
    top = tables[0]["table_name"]

    # 获取真实字段
    try:
        from db.executor import execute_sql
        r = execute_sql(
            f"SELECT column_name,data_type FROM information_schema.columns "
            f"WHERE table_name='{top}' AND table_schema='public' ORDER BY ordinal_position"
        )
        cols = r["rows"] if r["success"] else []
    except Exception:
        cols = []

    num_cols = [c["column_name"] for c in cols if c["data_type"] in ("integer","bigint","numeric","real","double precision","smallint")][:3]
    str_cols = [c["column_name"] for c in cols if c["column_name"] not in num_cols][:3]

    # 聚合需求：按第一个字符串列分组，第一个数值列做聚合
    if _needs_aggregation(query) and str_cols and num_cols:
        group_col = str_cols[0]
        agg_col = num_cols[0]
        return f"SELECT \"{group_col}\", SUM(\"{agg_col}\")::integer AS 汇总, COUNT(*) AS 记录数 FROM \"{top}\" GROUP BY \"{group_col}\" ORDER BY 汇总 DESC LIMIT 20"

    # 普通列表
    all_cols = [c["column_name"] for c in cols[:6]]
    col_str = ", ".join(f'"{c}"' for c in all_cols) if all_cols else "*"
    return f"SELECT {col_str} FROM \"{top}\" LIMIT 20"


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

    chart_config = state.get("chart_config", {})
    chart_type = chart_config.get("type", "table")

    # 用 LLM 生成图表配置（如果 sql_agent 已经给出了 chart_type，则直接使用）
    if chart_type and chart_type != "none":
        chart = generate_chart_by_type(result, chart_type, chart_config.get("title", state["query"]))
    else:
        chart = generate_chart(result["columns"], result["rows"], state["query"])

    state["chart"] = chart
    if chart["type"] != "none":
        state["steps"].append({"step": 6, "name": "图表生成", "status": "done", "detail": f"生成 {chart['type']} 图"})
    return state


def generate_chart_by_type(result: dict, chart_type: str, title: str = "") -> dict:
    """根据 sql_agent 输出的 chart_type 生成图表（直接本地渲染，无需外部 API）"""
    valid_types = {"bar", "barh", "line", "pie", "donut", "stacked", "scatter", "area"}
    columns = result["columns"]
    rows = result["rows"]

    # "table" 类型：直接标记为表格展示
    if chart_type == "table":
        return {"type": "table", "svg": ""}

    if chart_type not in valid_types:
        chart_type = "bar"
    if not columns or not rows:
        return {"type": "none", "svg": ""}

    # 直接使用本地 matplotlib 渲染（跳过 QuickChart 外部 API 调用）
    from agent.chart_agent import generate_chart as gen_chart_local
    return gen_chart_local(columns, rows, title or "")


def build_response(state: AgentState) -> AgentState:
    if state["intent"] in ("chat", "gibberish"):
        return state
    if state["intent"] == "ml":
        return state
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
        sql_result = state["sql_result"]
        chart = state.get("chart", {"type": "none", "svg": ""})

        # 并行执行分析、推荐、预测（三个 LLM 调用互不依赖）
        from concurrent.futures import ThreadPoolExecutor, as_completed

        analysis_text = ""
        recommended: list = []
        prediction: list = []

        def _do_analysis():
            if sql_result.get("success") and sql_result.get("rows") and len(sql_result["rows"]) >= 2:
                try:
                    return _generate_analysis(state["query"], sql_result)
                except Exception:
                    pass
            return ""

        def _do_recommend():
            if sql_result.get("success") and sql_result.get("rows"):
                try:
                    from agent.predict import generate_recommend_questions
                    return generate_recommend_questions(
                        state["query"], state["sql"], sql_result, state.get("schema_context", "")
                    )
                except Exception:
                    pass
            return []

        def _do_prediction():
            if sql_result.get("success") and len(sql_result.get("rows", [])) >= 4:
                try:
                    from agent.predict import generate_prediction
                    return generate_prediction(state["query"], sql_result)
                except Exception:
                    pass
            return []

        # 线程池并行调用 3 个 LLM
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(_do_analysis): "analysis",
                pool.submit(_do_recommend): "recommend",
                pool.submit(_do_prediction): "prediction",
            }
            for future in as_completed(futures, timeout=30):
                key = futures[future]
                try:
                    result = future.result()
                except Exception:
                    result = "" if key == "analysis" else []
                if key == "analysis":
                    analysis_text = result
                elif key == "recommend":
                    recommended = result
                elif key == "prediction":
                    prediction = result

        state["response"] = {
            "type": "data_query",
            "sql": state["sql"],
            "matched_tables": [{"table_name": t["table_name"], "table_alias": t["table_alias"]} for t in matched[:5]],
            "result": sql_result,
            "chart": chart,
            "analysis": analysis_text,
            "recommended": recommended,
            "prediction": prediction,
            "steps": state["steps"],
            "chart_config": state.get("chart_config", {}),
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
    wf.add_node("chat_responder", chat_responder)
    wf.add_node("ml_intent_agent", ml_intent_agent)
    wf.add_node("ml_executor", ml_executor)
    wf.add_node("analyze_db_responder", analyze_db_responder)

    wf.set_entry_point("supervisor")
    # supervisor 根据意图路由：闲聊→chat_responder, ML→ml_intent_agent, analyze_db→analyze_db_responder, 否则→schema
    wf.add_conditional_edges("supervisor", route_after_supervisor, {
        "chat_responder": "chat_responder",
        "ml_intent_agent": "ml_intent_agent",
        "analyze_db_responder": "analyze_db_responder",
        "schema_agent": "schema_agent",
    })
    wf.add_edge("chat_responder", END)
    wf.add_edge("ml_intent_agent", "ml_executor")
    wf.add_edge("ml_executor", END)
    wf.add_edge("analyze_db_responder", END)
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


def ask(query: str, history: list[dict] | None = None) -> dict:
    agent = get_agent()
    result = agent.invoke({
        "query": query, "intent": "", "keywords": [], "rag_tables": [],
        "matched_tables": [], "schema_context": "", "sql": "",
        "sql_result": {}, "chart": {}, "chart_config": {}, "response": {}, "steps": [], "error": "", "retry_count": 0,
        "history": history or [],
        "ml_intent": {}, "ml_result": {},
    })
    return result["response"]
