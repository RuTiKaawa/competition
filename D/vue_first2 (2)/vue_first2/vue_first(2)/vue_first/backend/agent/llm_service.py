"""LLMService — 单一流式流水线（参考 SQLBot LLMService 架构）

所有 LLM 调用均为流式 .stream()，进度在每步之间 yield。
分析、预测、推荐问题拆为独立方法，不在主流程中阻塞。
"""

import json
import re
import time
from typing import Generator, Any

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessageChunk

from config import LLM_CONFIG
from db.tools import match_tables_by_query, get_table_detail
from db.executor import execute_sql
from db.metadata import TABLES as METADATA_TABLES
from agent.chart_agent import generate_chart
from agent.prompts import SQL_SYSTEM_PROMPT, ANALYSIS_SYSTEM_PROMPT, RECOMMEND_QUESTIONS_PROMPT


# ── LLM 工厂 ─────────────────────────────────────────────

def _make_llm(temp: float = None, max_tokens: int = 2048):
    return ChatOpenAI(
        model=LLM_CONFIG["model"],
        api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"],
        temperature=temp if temp is not None else LLM_CONFIG["temperature"],
        max_tokens=max_tokens,
    )


# ── 意图分类（纯关键词，0 次 LLM 调用）──────────────────

def _classify_intent(query: str) -> str:
    q = query.strip()
    if not q:
        return "gibberish"
    if re.match(r'^[\d\s,.!?;:，。！？；：…]+$', q) and len(q) <= 6:
        return "gibberish"
    if re.match(r'^[a-z]{1,5}$', q, re.IGNORECASE):
        return "gibberish"

    # 闲聊（判断顺序：先 chat 关键词 → analyze_db → lookup → data → 兜底 chat）
    data_keywords = ["分析","统计","排行","排名","良率","不良","库存","停机","产量","产能",
                     "趋势","对比","汇总","占比","最高","最低","平均","列出","查询","显示",
                     "预警","TOP","top","各工序","各产线","各产品","每个","多少","工单","设备","表"]
    chat_words = ["你好","谢谢","再见","嗨","hello","hi","早上好","晚上好","下午好",
                  "哈哈","嘿嘿","你是谁","你能做什么","你会什么","在吗","怎么样","可以吗",
                  "谢谢啊","多谢","辛苦","不错","厉害","好的","ok","OK","嗯","收到","了解",
                  "介绍","帮助","功能","能力","有什么功能","怎么用","帮助我",
                  "等于","计算","为什么","怎么","如何",
                  "帮忙","告诉我","讲一下","解释","说明","聊","对不对","有没有","能不能",
                  "可不可以","好不好","行不行","会吗","讲个","来点","说",
                  "笑死","有意思","好玩","哦","啊","额","嗯嗯"]
    for w in chat_words:
        if w in q:
            return "chat"

    # ML
    for w in ["训练模型","预测","聚类","异常检测","回归","分类","机器学习","随机森林","决策树","KMeans","孤立森林","建模","线性回归"]:
        if w in q:
            return "ml"

    # 查表：只说"查/看某某表"，不涉及数据内容
    for w in ["是什么表","什么表","有哪些字段","有哪些表","表结构"]:
        if w in q:
            return "lookup"

    # 数据库分析（含"查看数据库""库结构""数据库结构"等变体）
    for w in ["数据库","什么数据","数据总览","数据概览","库结构","库里有","看看库","看看数据库","所有表","全部表","所有表结构"]:
        if w in q:
            # "数据库 + 具体分析词" → 仍是 data
            if any(d in q for d in ["良率","不良","停机","产量","库存预警","趋势","排行","统计"]):
                return "data"
            return "analyze_db"

    # 数据查询
    data_words = ["分析","统计","排行","排名","良率","不良","库存","停机","产量","产能","趋势","对比",
                  "汇总","占比","最高","最低","平均","列出","查询","显示","预警","TOP","top",
                  "各工序","各产线","各产品","每个","多少","关键","状态","类别","哪些","数量",
                  "工单","设备","在制","闲置","启用","停用","合格","不合格","完成","情况","前","后"]
    for w in data_words:
        if w in q:
            return "data"

    # 兜底：短句、知识问答题 → 闲聊
    if len(q) <= 8 and not any(d in q for d in data_keywords):
        return "chat"
    if any(w in q for w in ["等于","计算","为什么","怎么","如何","谁","?"]):
        return "chat"
    if "什么" in q and not any(d in q for d in ["状态","数量","多少","哪些","情况","关键"]):
        return "chat"

    return "data"


# ── 快速 Schema 构建（纯内存，0 次 DB 查询）─────────────

def _build_schema_fast(candidate_names: list[str]) -> str:
    """从当前连接的 DB 获取真实字段结构构建 schema 上下文。
    优先查 information_schema，失败时回退到硬编码元数据。"""
    lines = ["# 可用表\n"]
    meta_map = {t["table_name"]: t for t in METADATA_TABLES}
    count = 0

    for name in candidate_names[:8]:
        if count >= 8:
            break
        fields = _get_db_columns(name)  # 优先真实 DB
        meta = meta_map.get(name)
        alias = meta["table_alias"] if meta else name
        category = meta["category"] if meta else "unknown"
        desc = meta["description"] if meta else ""

        if fields:
            lines.append(f"## {name} [{category}] — {alias}")
            if desc:
                lines.append(f"  描述: {desc}")
            if meta and meta.get("related_tables"):
                lines.append(f"  关联表: {', '.join(meta['related_tables'])}")
            for f in fields[:20]:
                key = f.get("key", "")
                key_str = f", {key}" if key else ""
                lines.append(f"  {f['name']}({f['type']}{key_str})")
            lines.append("")
            count += 1
        elif meta:
            # DB 不可用时回退到元数据
            lines.append(f"## {name} [{category}] — {alias}")
            if desc:
                lines.append(f"  描述: {desc}")
            if meta.get("related_tables"):
                lines.append(f"  关联表: {', '.join(meta['related_tables'])}")
            for f in meta["fields"][:15]:
                key = f.get("key", "")
                key_str = f", {key}" if key else ""
                lines.append(f"  {f['name']}({f['type']}{key_str})")
            lines.append("")
            count += 1

    return "\n".join(lines)


def _get_db_columns(table_name: str) -> list[dict] | None:
    """从 information_schema 获取真实字段（轻量单次查询，PG/MySQL 通用）"""
    from database import get_db_type
    try:
        if get_db_type() == "mysql":
            r = execute_sql(
                f"SELECT column_name AS name, data_type AS type, "
                f"CASE WHEN column_name IN ("
                f"  SELECT column_name FROM information_schema.key_column_usage "
                f"  WHERE table_name='{table_name}' AND table_schema=DATABASE() AND constraint_name='PRIMARY'"
                f") THEN 'PK' ELSE '' END AS key_type "
                f"FROM information_schema.columns "
                f"WHERE table_name='{table_name}' AND table_schema=DATABASE() "
                f"ORDER BY ordinal_position"
            )
        else:
            r = execute_sql(
                f"SELECT column_name AS name, data_type AS type, "
                f"CASE WHEN column_name IN ("
                f"  SELECT kcu.column_name FROM information_schema.table_constraints tc "
                f"  JOIN information_schema.key_column_usage kcu ON tc.constraint_name=kcu.constraint_name "
                f"  WHERE tc.table_name='{table_name}' AND tc.table_schema='public' AND tc.constraint_type='PRIMARY KEY'"
                f") THEN 'PK' ELSE '' END AS key_type "
                f"FROM information_schema.columns "
                f"WHERE table_name='{table_name}' AND table_schema='public' "
                f"ORDER BY ordinal_position"
            )
        if r["success"] and r["rows"]:
            return [{"name": row["name"], "type": row["type"], "key": row.get("key_type", "")} for row in r["rows"]]
    except Exception:
        pass
    return None


# ── 主流水线 ─────────────────────────────────────────────

class LLMService:
    """流式 NL2SQL 流水线：意图 → 选表 → Schema → SQL → 执行 → 图表"""

    def __init__(self, query: str, history: list[dict] | None = None):
        self.query = query
        self.history = history or []
        self.intent = ""
        self.sql = ""
        self.sql_result: dict = {}
        self.chart: dict = {"type": "none", "svg": ""}
        self.matched_tables: list[dict] = []
        self.schema_context = ""
        self.chart_type = "bar"
        self.title = ""
        self.error = ""

    def run(self) -> Generator[dict[str, Any], None, None]:
        """主入口 — yield 进度事件（每步含耗时）"""
        t0 = time.time()
        t_step = t0

        def _step(name: str, detail: str) -> dict:
            nonlocal t_step
            now = time.time()
            ms = int((now - t_step) * 1000)
            t_step = now
            return {"type": "step", "name": name, "detail": detail, "elapsed_ms": ms}

        # ── Step 1: 意图分类 ──
        self.intent = _classify_intent(self.query)
        yield _step("意图理解", self.query[:60])

        if self.intent == "chat":
            yield from self._respond_chat()
            return
        if self.intent == "gibberish":
            yield from self._respond_gibberish()
            return
        if self.intent == "analyze_db":
            yield from self._respond_analyze_db()
            return
        if self.intent == "ml":
            yield from self._respond_ml()
            return
        if self.intent == "lookup":
            yield from self._respond_lookup()
            return

        # ── Step 2: 表匹配 ──
        self.matched_tables = match_tables_by_query(self.query)[:8]
        if not self.matched_tables:
            self.matched_tables = match_tables_by_query("")[:8]

        # 补充当前 DB 中真实存在的表（切换数据库后元数据可能不匹配）
        try:
            from db.tools import get_real_tables
            existing = {t["table_name"] for t in self.matched_tables}
            for rt in get_real_tables():
                if rt["table_name"] not in existing:
                    self.matched_tables.append({
                        "table_name": rt["table_name"],
                        "table_alias": rt["table_name"],
                        "category": "unknown",
                        "description": "",
                        "row_count": 0,
                        "field_count": rt.get("field_count", 0),
                    })
        except Exception:
            pass

        yield _step("表匹配", f"定位到 {len(self.matched_tables)} 张候选表")

        # ── Step 3: Schema 上下文 ──
        candidate_names = [t["table_name"] for t in self.matched_tables]
        self.schema_context = _build_schema_fast(candidate_names)
        yield _step("Schema分析", f"{len(self.schema_context)} 字符")

        # ── Step 4: SQL 生成（流式）──
        yield _step("SQL生成", "AI 正在生成查询语句…")
        yield from self._generate_sql_stream()

        if self.error:
            yield {"type": "error", "message": self.error}
            return

        yield {"type": "sql", "sql": self.sql}

        # ── Step 5: SQL 执行 ──
        t_exec = time.time()
        self.sql_result = execute_sql(self.sql)
        exec_ms = int((time.time() - t_exec) * 1000)
        ok = self.sql_result.get("success", False)
        yield _step("SQL执行", f"{exec_ms}ms · {'成功' if ok else '失败'} · {self.sql_result.get('row_count', 0)} 行")

        if ok and self.sql_result.get("rows"):
            yield {"type": "sql_result",
                   "columns": self.sql_result["columns"],
                   "rows": self.sql_result["rows"],
                   "row_count": self.sql_result["row_count"]}

        if not ok:
            # ── 自动重试：把错误信息发回 LLM 修复 ──
            yield _step("SQL重试", "首次执行失败，AI 正在修复…")
            retry_sql = self._retry_sql_fix(self.sql_result.get("error", ""))
            if retry_sql:
                self.sql = retry_sql
                yield {"type": "sql", "sql": self.sql}
                self.sql_result = execute_sql(self.sql)
                ok = self.sql_result.get("success", False)
                yield _step("SQL执行", f"{int((time.time()-t_exec)*1000)}ms · {'成功' if ok else '失败'} · {self.sql_result.get('row_count', 0)} 行")
                if ok and self.sql_result.get("rows"):
                    yield {"type": "sql_result",
                           "columns": self.sql_result["columns"],
                           "rows": self.sql_result["rows"],
                           "row_count": self.sql_result["row_count"]}

            if not ok:
                # ── 重试仍失败：用 fallback ──
                fallback_sql = _fallback_sql(self.query, self.matched_tables)
                if fallback_sql and fallback_sql != self.sql:
                    self.sql = fallback_sql
                    yield _step("兜底SQL", "AI 生成的 SQL 有误，使用备选查询")
                    yield {"type": "sql", "sql": self.sql}
                    self.sql_result = execute_sql(self.sql)
                    ok = self.sql_result.get("success", False)
                    yield _step("SQL执行", f"{int((time.time()-t_exec)*1000)}ms · {'成功' if ok else '失败'} · {self.sql_result.get('row_count', 0)} 行")
                    if ok and self.sql_result.get("rows"):
                        yield {"type": "sql_result",
                               "columns": self.sql_result["columns"],
                               "rows": self.sql_result["rows"],
                               "row_count": self.sql_result["row_count"]}

            if not ok:
                self.error = self.sql_result.get("error", "SQL 执行失败")
                yield {"type": "error", "message": self.error}
                return

        # ── Step 6: 图表生成 ──
        if self.sql_result.get("rows") and len(self.sql_result["rows"]) >= 2:
            self.chart = generate_chart(
                self.sql_result["columns"],
                self.sql_result["rows"],
                self.query,
                force_type=self.chart_type,
            )
            if self.chart["type"] not in ("none", "table", None):
                yield _step("图表生成", f"生成 {self.chart['type']} 图")
                yield {"type": "chart", "svg": self.chart.get("svg", ""), "chart_type": self.chart["type"]}

        elapsed = int((time.time() - t0) * 1000)
        yield {"type": "done", "elapsed_ms": elapsed,
               "response": self._build_response()}

    # ── SQL 生成（流式）──────────────────────────────────

    def _build_history_text(self) -> str:
        """构建多轮对话历史上下文（供 SQL 生成/闲聊使用）"""
        if not self.history:
            return ""
        lines = []
        for h in self.history[-6:]:
            role = "用户" if h.get("role") == "user" else "AI"
            lines.append(f"{role}: {h.get('content', '')[:200]}")
        return "\n".join(lines)

    def _generate_sql_stream(self) -> Generator[dict, None, None]:
        """流式调用 LLM 生成 SQL + 图表类型"""
        history_text = self._build_history_text()
        prompt = SQL_SYSTEM_PROMPT.format(
            schema_context=self.schema_context,
            query=self.query,
        )
        if history_text:
            prompt += '\n\n## 对话历史（用于理解指代，如"他们""上面""它"等）\n' + history_text + '\n\n只针对用户最新问题生成 SQL，不要重复回答历史问题。'
        llm = _make_llm(temp=0.0, max_tokens=2048)

        full_text = ""
        try:
            for chunk in llm.stream([SystemMessage(content=prompt)]):
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    t = chunk.content
                    full_text += t
                    yield {"type": "thought", "step": "SQL生成", "text": t}
        except Exception as e:
            # LLM 不可用（如未配置 API Key / 网络异常）→ 降级为规则 SQL，保证功能可用
            self.sql = _fallback_sql(self.query, self.matched_tables)
            yield {"type": "thought_done", "step": "SQL生成", "fallback": True}
            yield {"type": "step", "name": "SQL生成", "detail": "LLM 不可用，使用规则兜底 SQL", "elapsed_ms": 0}
            return

        yield {"type": "thought_done", "step": "SQL生成"}

        # 解析 JSON 响应
        sql, chart_type, title = self._parse_sql_response(full_text)
        self.sql = sql
        self.chart_type = chart_type
        self.title = title

    def _retry_sql_fix(self, error_msg: str) -> str:
        """SQL 执行失败后，把错误发回 LLM 修复；LLM 不可用返回空串（走兜底）"""
        if not self.sql or not error_msg:
            return ""
        try:
            llm = _make_llm(temp=0.0, max_tokens=2048)
            prompt = SQL_SYSTEM_PROMPT.format(
                schema_context=self.schema_context,
                query=self.query,
            )
            fix_prompt = (
                f"{prompt}\n\n上次生成的 SQL 执行失败，错误: {error_msg}\n"
                f"原始 SQL: {self.sql}\n\n请修正 SQL 后重新输出 JSON。"
            )
            resp = llm.invoke([SystemMessage(content=fix_prompt)])
            raw = resp.content.strip()
            sql, _, _ = self._parse_sql_response(raw)
            return sql
        except Exception:
            return ""

    def _parse_sql_response(self, raw: str) -> tuple[str, str, str]:
        """从 LLM 流式输出中提取 SQL + chart_type + title"""
        sql = raw
        chart_type = "bar"
        title = ""

        # 清理 markdown
        if sql.startswith("```"):
            lines = sql.split("\n")
            sql = "\n".join(lines[1:]) if lines[0].startswith("```") else sql
            if sql.endswith("```"):
                sql = sql.rstrip("```").rstrip()

        # 尝试 JSON
        json_match = re.search(r'\{[\s\S]*\}', sql)
        if json_match:
            try:
                parsed = json.loads(json_match.group(0))
                sql = parsed.get("sql", sql)
                chart_type = parsed.get("chart_type", "bar")
                title = parsed.get("title", "")
            except Exception:
                pass

        # 如果还是整段文本，提取 SQL
        if sql and sql.strip().upper().startswith("SELECT"):
            pass
        else:
            # 尝试从文本中找 SELECT
            sel_match = re.search(r'(SELECT[\s\S]*?)(?:```|$)', sql, re.IGNORECASE)
            if sel_match:
                sql = sel_match.group(1).strip()
            else:
                sql = _fallback_sql(self.query, self.matched_tables)

        return sql.strip(), chart_type, title

    # ── 回复构造 ─────────────────────────────────────────

    def _build_response(self) -> dict:
        matched = self.matched_tables
        # 无数值列的结果（纯列表）→ 标记 table 类型展示
        chart_type_final = self.chart.get("type", "none")
        if chart_type_final == "none" and self.sql_result.get("rows"):
            rows = self.sql_result["rows"]
            cols = self.sql_result.get("columns", [])
            # 首行所有列都是非数值 → 纯字符串列表，按 table 展示
            if cols and not any(
                str(rows[0].get(c, "")).replace(".", "").replace("-", "").isdigit() for c in cols
            ):
                chart_type_final = "table"
        return {
            "type": "data_query",
            "query": self.query,
            "sql": self.sql,
            "matched_tables": [{"table_name": t["table_name"], "table_alias": t["table_alias"]} for t in matched[:5]],
            "result": self.sql_result,
            "chart": {"type": chart_type_final},  # SVG 已单独发，这里只记类型
            "chart_config": {"type": chart_type_final, "title": self.title},
            "analysis": self._quick_analysis(),
            "recommended": self._quick_recommended(),
            "prediction": [],
            "steps": [
                {"step": 1, "name": "意图理解", "status": "done", "detail": self.query[:60]},
                {"step": 2, "name": "表匹配", "status": "done", "detail": f"定位到 {len(matched)} 张候选表"},
                {"step": 3, "name": "SQL生成", "status": "done", "detail": "AI 已生成 SQL"},
                {"step": 4, "name": "SQL执行", "status": "done", "detail": f"{self.sql_result.get('row_count', 0)} 行结果"},
            ],
        }

    def _quick_analysis(self) -> str:
        """基于查询结果快速生成规则分析（不依赖 LLM，保证稳定）"""
        rows = self.sql_result.get("rows") or []
        cols = self.sql_result.get("columns") or []
        if not rows:
            return "查询执行成功，但当前数据范围内没有匹配的记录。可以调整时间范围或换个条件再试。"
        parts = [f"共查询到 {len(rows)} 条记录，{len(cols)} 个字段。"]
        # 找数值列做统计
        for col in cols[:6]:
            vals = []
            for r in rows[:100]:
                v = r.get(col)
                if v is not None:
                    try:
                        vals.append(float(v))
                    except (ValueError, TypeError):
                        break
            if len(vals) >= 2:
                parts.append(f"{col} 最大 {max(vals):g}，最小 {min(vals):g}，平均 {sum(vals)/len(vals):.2f}。")
                break
        return "".join(parts)

    def _quick_recommended(self) -> list[str]:
        """根据当前查询生成 2-3 个推荐追问（规则版，避免额外 LLM 调用）"""
        rows = self.sql_result.get("rows") or []
        if not rows:
            return []
        query = self.query
        recs = []
        for kw, follow in [
            ("良率", "各工序的产量趋势"),
            ("不良", "各工序的不良分布"),
            ("停机", "停机原因排行"),
            ("库存", "库存预警产品清单"),
            ("产量", "各产线的产量对比"),
            ("排行", "最近7天的变化趋势"),
        ]:
            if kw in query:
                recs.append(follow)
                break
        recs.append(f"查看 {len(self.sql_result.get('columns', []))} 个字段的完整数据")
        recs.append("生成一份数据分析报告")
        return recs[:3]

    # ── 意图处理器 ───────────────────────────────────────

    def _respond_chat(self) -> Generator[dict, None, None]:
        # 常见问候免 LLM，秒回
        quick_replies = {
            "你好": "你好！我是数智问析 AI 助手，专注于数据分析。有什么可以帮你的？",
            "在吗": "在的！随时为你服务。有什么想了解的？",
            "谢谢": "不客气！有问题随时问我。",
            "再见": "再见！祝工作顺利。",
            "你是谁": "我是数智问析（NL2SQL Agent），一个智能数据分析助手。你可以用自然语言向我提问，我会自动查询数据库并生成图表来回答。",
            "你能做什么": "我可以帮你：\n· 用自然语言查询数据库（说人话就行）\n· 自动生成统计图表\n· 分析数据趋势和异常\n· 回答关于数据库结构的问题\n\n试试问我：「分析各工序良率」「最近设备停机记录」「查看所有表」",
            "你会什么": "我可以帮你：\n· 用自然语言查询数据库（说人话就行）\n· 自动生成统计图表\n· 分析数据趋势和异常\n· 回答关于数据库结构的问题\n\n试试问我：「分析各工序良率」「最近设备停机记录」「查看所有表」",
        }
        for key, reply in quick_replies.items():
            if key in self.query:
                yield {"type": "answer", "text": reply}
                yield {"type": "done", "elapsed_ms": 0,
                       "response": {"type": "general_chat", "answer": reply}}
                return

        # 其他闲聊用 LLM 流式回复
        yield {"type": "step", "name": "思考中", "detail": "AI 正在回复…"}
        system_prompt = (
            "你是数智问析（NL2SQL Agent），一个智能数据分析助手。"
            "你帮助用户用自然语言查询数据库、生成图表、分析数据。"
            "请用第一人称「我」来称呼自己。回答简洁友好，控制在100字以内。"
        )
        history_text = self._build_history_text()
        if history_text:
            system_prompt += f"\n\n对话历史：\n{history_text}\n请结合历史上下文回答最新问题。"
        llm = _make_llm(temp=0.7, max_tokens=256)
        full = ""
        try:
            for chunk in llm.stream([SystemMessage(content=system_prompt), HumanMessage(content=self.query)]):
                if isinstance(chunk, AIMessageChunk) and chunk.content:
                    t = chunk.content
                    full += t
                    yield {"type": "thought", "step": "回复", "text": t}
        except Exception:
            full = "您好！我是数智问析 AI 助手，专注于数据分析。您可以问我：分析各工序良率、不良类型排行、库存预警等。"
        yield {"type": "thought_done", "step": "回复"}
        yield {"type": "done", "elapsed_ms": 0,
               "response": {"type": "general_chat", "answer": full}}

    def _respond_gibberish(self) -> Generator[dict, None, None]:
        yield {"type": "done", "elapsed_ms": 0,
               "response": {"type": "general_chat",
                            "answer": "输入的内容我不太理解。您可以尝试问我：\n· 分析各工序良率\n· 不良类型排行\n· 库存预警分析"}}

    def _respond_analyze_db(self) -> Generator[dict, None, None]:
        """分析当前数据库 — 只显示当前连接 DB 中真实存在的表"""
        from db.metadata import TABLES as META

        meta_map = {t["table_name"]: t for t in META}
        lines = []
        total_rows = 0

        # 只列当前 DB 中真实存在的表
        try:
            r = execute_sql(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
            )
            db_tables = [row["table_name"] for row in r["rows"]] if r["success"] else []
        except Exception:
            db_tables = []

        if not db_tables:
            # DB 不可用时回退到元数据
            for t in META:
                rows = t.get("row_count", 0)
                total_rows += rows
                lines.append(f"· {t['table_alias']}（{t['table_name']}）: {rows}行（参考）")
        else:
            for tname in db_tables:
                meta = meta_map.get(tname)
                alias = meta["table_alias"] if meta else tname
                rows = 0
                try:
                    rr = execute_sql(f"SELECT COUNT(*) AS cnt FROM \"{tname}\"")
                    if rr["success"] and rr["rows"]:
                        rows = rr["rows"][0]["cnt"]
                        total_rows += rows
                except Exception:
                    pass
                lines.append(f"· {alias}（{tname}）: {rows}行")

        answer = f"共 {len(lines)} 张表，约 {total_rows} 条数据：\n\n" + "\n".join(lines)
        answer += "\n\n你可以直接问我：\n· 查询某张表的数据\n· 统计分析（排行、汇总、趋势）"

        yield {"type": "done", "elapsed_ms": 0,
               "response": {"type": "analyze_db", "answer": answer,
                            "tables": db_tables,
                            "total_rows": total_rows}}

    def _respond_ml(self) -> Generator[dict, None, None]:
        yield {"type": "done", "elapsed_ms": 0,
               "response": {"type": "ml_error", "error": "ML 建模功能请通过 /api/ml/train 接口使用"}}

    def _respond_lookup(self) -> Generator[dict, None, None]:
        self.matched_tables = match_tables_by_query(self.query)[:5]
        # 关键词匹配不到表（如"有哪些表"）→ 回退列出当前数据库全部表
        if not self.matched_tables:
            try:
                from db.tools import get_all_tables
                self.matched_tables = get_all_tables()[:5]
            except Exception:
                pass
        if self.matched_tables:
            top = self.matched_tables[0]
            detail = get_table_detail(top["table_name"])
            yield {"type": "done", "elapsed_ms": 0,
                   "response": {
                       "type": "table_lookup",
                       "matched_table": {
                           "table_name": top["table_name"], "table_alias": top["table_alias"],
                           "category": top["category"], "description": top["description"],
                           "row_count": top["row_count"], "field_count": top["field_count"],
                       },
                       "detail": detail,
                       "related_tables": self.matched_tables[1:4],
                   }}
        else:
            yield {"type": "done", "elapsed_ms": 0,
                   "response": {"type": "table_lookup", "matched_table": None, "detail": None, "related_tables": []}}


# ── 分析 & 预测（独立调用，不阻塞主流程）────────────────

def generate_analysis(query: str, sql: str, sql_result: dict) -> Generator[dict, None, None]:
    """流式生成数据分析解读"""
    if not sql_result.get("rows") or len(sql_result["rows"]) < 2:
        yield {"type": "done", "content": "数据不足，无法生成分析"}
        return

    rows = sql_result["rows"][:15]
    data_json = json.dumps(rows, ensure_ascii=False, default=str)
    fields_info = ", ".join(sql_result["columns"])

    prompt = ANALYSIS_SYSTEM_PROMPT.format(
        data_json=data_json[:1500],
        fields_info=fields_info,
        query=query,
    )
    llm = _make_llm(temp=0.3, max_tokens=512)
    full = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            t = chunk.content
            full += t
            yield {"type": "thought", "step": "数据分析", "text": t}
    yield {"type": "done", "content": full}


def generate_predict(sql_result: dict) -> Generator[dict, None, None]:
    """流式生成趋势预测"""
    if not sql_result.get("rows") or len(sql_result["rows"]) < 3:
        yield {"type": "done", "content": "", "prediction": []}
        return

    rows = sql_result["rows"][-10:]
    data_json = json.dumps(rows, ensure_ascii=False, default=str)
    fields_info = ", ".join(sql_result["columns"])

    prompt = f"""你是一个数据趋势预测专家。根据历史数据预测未来趋势。

## 历史数据
{data_json}

## 字段
{fields_info}

## 要求
1. 分析历史数据的趋势（上升/下降/波动）
2. 预测未来 2-3 个周期的数据
3. 返回与输入格式一致的 JSON 数组（追加到历史数据后面）
4. 如果数据量不足或无明显趋势，返回空数组 []

输出 JSON 数组:"""

    llm = _make_llm(temp=0.3, max_tokens=1024)
    full = ""
    for chunk in llm.stream([HumanMessage(content=prompt)]):
        if isinstance(chunk, AIMessageChunk) and chunk.content:
            t = chunk.content
            full += t
            yield {"type": "thought", "step": "趋势预测", "text": t}

    # 解析预测数据
    prediction = []
    try:
        match = re.search(r'\[[\s\S]*\]', full)
        if match:
            prediction = json.loads(match.group(0))
    except Exception:
        pass

    yield {"type": "done", "content": full, "prediction": prediction}


def generate_recommend_questions(query: str, sql: str, sql_result: dict, schema_context: str) -> list[str]:
    """生成推荐问题（非流式，快速返回）"""
    if not sql_result.get("rows"):
        return []

    result_summary = f"{len(sql_result['rows'])} rows, columns: {', '.join(sql_result['columns'])}"
    prompt = RECOMMEND_QUESTIONS_PROMPT.format(
        query=query, sql=sql[:200],
        result_summary=result_summary,
        schema_context=schema_context[:800],
    )

    try:
        llm = _make_llm(temp=0.5, max_tokens=512)
        resp = llm.invoke([HumanMessage(content=prompt)])
        raw = resp.content.strip()
        match = re.search(r'\[[\s\S]*\]', raw)
        if match:
            return json.loads(match.group(0))
    except Exception:
        pass
    return []


# ── Fallback SQL（用元数据，不查 DB）─────────────────────

def _fallback_sql(query: str, tables: list[dict]) -> str:
    """常见查询兜底 SQL — 优先查真实 DB 字段"""
    if not tables:
        return "SELECT 1"
    top = tables[0]["table_name"]

    # 优先从真实 DB 获取字段
    fields = _get_db_columns(top)
    if not fields:
        meta = _find_meta(top)
        fields = meta.get("fields", []) if meta else []

    if not fields:
        return f"SELECT * FROM \"{top}\" LIMIT 20"

    num_cols = [f["name"] for f in fields if f["type"] in ("integer","bigint","numeric","real","double precision","smallint")][:3]
    str_cols = [f["name"] for f in fields if f["name"] not in num_cols][:3]

    # 停机设备 → 按时间倒序
    if any(w in query for w in ["停机", "设备停机"]):
        time_col = "start_time" if any(f["name"] == "start_time" for f in fields) else ""
        if time_col:
            return f"SELECT * FROM \"{top}\" ORDER BY \"{time_col}\" DESC LIMIT 20"
        return f"SELECT * FROM \"{top}\" LIMIT 20"

    # 最近 → 按时间/日期倒序
    if any(w in query for w in ["最近", "最新", "近7天", "本周", "过去"]):
        for candidate in ["start_time", "stat_date", "create_time", "inspect_date", "snapshot_date"]:
            if any(f["name"] == candidate for f in fields):
                return f"SELECT * FROM \"{top}\" ORDER BY \"{candidate}\" DESC LIMIT 20"

    # 聚合场景
    if str_cols and num_cols:
        group_col = str_cols[0]
        agg_col = num_cols[0]
        return f"SELECT \"{group_col}\", SUM(\"{agg_col}\")::integer AS 汇总 FROM \"{top}\" GROUP BY \"{group_col}\" ORDER BY 汇总 DESC LIMIT 20"

    # 兜底：取前几列
    all_cols = [f["name"] for f in fields[:6]]
    col_str = ", ".join(f'"{c}"' for c in all_cols) if all_cols else "*"
    return f"SELECT {col_str} FROM \"{top}\" LIMIT 20"


def _find_meta(table_name: str) -> dict | None:
    """从 TABLES 元数据中找表"""
    for t in METADATA_TABLES:
        if t["table_name"] == table_name:
            return t
    return None


# ── 结果缓存（内存，供独立端点复用）─────────────────────

_last_results: dict[str, dict] = {}


def cache_result(query: str, sql: str, sql_result: dict, schema_context: str):
    key = query.strip()[:50]
    _last_results[key] = {"sql": sql, "sql_result": sql_result, "schema_context": schema_context}


def get_cached_result(query: str) -> dict | None:
    key = query.strip()[:50]
    return _last_results.get(key)
