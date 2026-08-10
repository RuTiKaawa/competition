"""数据预测 + 推荐问题节点"""

from .prompts import RECOMMEND_QUESTIONS_PROMPT
from .multi_agent import _llm, AgentState
from langchain_core.messages import HumanMessage
import json


# ── 数据预测 ─────────────────────────────────────────────

PREDICT_PROMPT = """你是一个数据趋势预测专家。根据历史数据预测未来趋势。

## 历史数据
{data_json}

## 字段
{fields_info}

## 要求
1. 分析历史数据的趋势（上升/下降/波动）
2. 预测未来 2-3 个周期的数据
3. 返回与输入格式一致的 JSON 数组（追加到历史数据后面）
4. 如果数据量不足（<2行）或无明显趋势，返回空数组 []

输出 JSON:"""


def generate_prediction(query: str, sql_result: dict) -> list:
    """对 SQL 查询结果做趋势预测"""
    if not sql_result.get("rows") or len(sql_result["rows"]) < 3:
        return []

    rows = sql_result["rows"][-10:]  # 取最后10行
    data_json = json.dumps(rows, ensure_ascii=False, default=str)
    fields_info = ", ".join(sql_result["columns"])

    try:
        llm = _llm(temp=0.3, max_tokens=1024)
        prompt = PREDICT_PROMPT.format(data_json=data_json, fields_info=fields_info)
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()

        # 解析 JSON
        import re
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []


# ── 推荐问题 ─────────────────────────────────────────────

def generate_recommend_questions(query: str, sql: str, sql_result: dict, schema_context: str) -> list[str]:
    """根据当前对话生成推荐问题"""
    if not sql_result.get("rows"):
        return []

    # 结果摘要
    rows = sql_result["rows"][:5]
    result_summary = f"{len(sql_result['rows'])} rows, columns: {', '.join(sql_result['columns'])}"
    if rows:
        result_summary += f", sample: {json.dumps(rows[0], ensure_ascii=False, default=str)[:100]}"

    try:
        llm = _llm(temp=0.5, max_tokens=512)
        prompt = RECOMMEND_QUESTIONS_PROMPT.format(
            query=query, sql=sql[:200],
            result_summary=result_summary,
            schema_context=schema_context[:800],
        )
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()

        import re
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []
