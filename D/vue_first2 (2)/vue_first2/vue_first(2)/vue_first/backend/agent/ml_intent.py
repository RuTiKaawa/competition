"""ML 意图生成 Agent — 受限输出，不接触真实数据"""

import json, re
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from config import LLM_CONFIG

# ====== 白名单 ============================================

# 允许的特征工程操作
ALLOWED_OPERATIONS = {
    "dropna":       {"desc": "删除含空值行",   "params": {"max_drop_ratio": {"type": "number", "min": 0.0, "max": 0.5}}},
    "log_transform": {"desc": "对数变换",       "params": {"columns": {"type": "list[str]"}}},
    "standardize":   {"desc": "标准化",         "params": {"columns": {"type": "list[str]"}}},
    "label_encode":  {"desc": "标签编码",       "params": {"columns": {"type": "list[str]"}}},
    "resample":      {"desc": "时间重采样",     "params": {"rule": {"type": "str"}, "agg": {"type": "str"}}},
}

# 允许的模型 + 参数约束
ALLOWED_MODELS = {
    "LinearRegression":      {"name": "线性回归",        "task": "regression",      "params": {}},
    "LogisticRegression":    {"name": "逻辑回归",        "task": "classification",  "params": {"max_iter": {"min": 100, "max": 5000}}},
    "DecisionTreeClassifier": {"name": "决策树分类",     "task": "classification",  "params": {"max_depth": {"min": 1, "max": 20}}},
    "DecisionTreeRegressor":  {"name": "决策树回归",     "task": "regression",      "params": {"max_depth": {"min": 1, "max": 20}}},
    "RandomForestClassifier": {"name": "随机森林分类",   "task": "classification",  "params": {"n_estimators": {"min": 10, "max": 500}, "max_depth": {"min": 1, "max": 20}}},
    "RandomForestRegressor":  {"name": "随机森林回归",   "task": "regression",      "params": {"n_estimators": {"min": 10, "max": 500}, "max_depth": {"min": 1, "max": 20}}},
    "KMeans":                {"name": "KMeans聚类",      "task": "clustering",       "params": {"n_clusters": {"min": 2, "max": 20}}},
    "IsolationForest":      {"name": "孤立森林",        "task": "anomaly_detection","params": {"n_estimators": {"min": 10, "max": 500}, "contamination": {"min": 0.01, "max": 0.5}}},
}

# 允许的重采样聚合函数
ALLOWED_RESAMPLE_AGGS = {"mean", "sum", "min", "max", "count", "std", "first", "last"}


# ====== Prompt ===========================================

ML_INTENT_PROMPT = """你是一个机器学习建模助手。根据用户需求和可用数据，生成一个严格符合 JSON Schema 的建模意图。

## 可用数据源
**你只能使用下面这一张表，表名已经是固定的！不要改表名！**

{schema_context}

## JSON Schema（必须严格遵守）

{{
  "intent_type": "train",
  "user_summary": "一句话概括用户的建模需求",
  "data_request": {{
    "table": "{table_name}",
    "fields": ["从上方表中选择的字段名"],
    "target": "目标字段名（选一个数值字段作为预测目标，聚类/异常检测留空）",
    "filter": "",
    "limit": 5000
  }},
  "feature_engineering": [
    {{"op": "操作名", "params": {{...}}}}
  ],
  "model_training": {{
    "model": "模型名（从允许列表选）",
    "params": {{...}}
  }},
  "output_spec": {{
    "metrics": ["指标名"],
    "max_rows": 100
  }}
}}

## 你只能使用的字段（从上方复制）
## 表名固定为：{table_name}

任务：从上方字段中选择合适的 feature 和 target 字段，选择模型，设计特征工程步骤。

## 允许的模型
{model_list}

## 关键规则
1. 只输出 JSON
2. table 字段必须是 "{table_name}"，不要修改
3. **绝对不要改写字段名！字段名必须和上面「字段列表」中的一模一样，直接复制粘贴！例如上面写的是 line_id 你就填 line_id，不要写成 production_line**
4. 聚类/异常检测时 target 留空字符串 ""
5. 如果用户需求模糊，选择最合理的默认值
6. 特征工程中的 columns 也要用和字段列表一致的名字

用户需求: {query}

输出 JSON:"""


# ====== 校验 =============================================

def _llm(temp: float = 0.0):
    return ChatOpenAI(
        model=LLM_CONFIG["model"], api_key=LLM_CONFIG["api_key"],
        base_url=LLM_CONFIG["base_url"], temperature=temp, max_tokens=LLM_CONFIG["max_tokens"],
    )


def validate_ml_intent(intent: dict) -> tuple[bool, str, dict]:
    """校验 ML 意图 JSON 的合法性，返回 (有效?, 错误信息, 修正后的意图)"""
    errors = []

    # 1. 基本结构
    if not isinstance(intent, dict):
        return False, "意图必须是 JSON 对象", intent
    if intent.get("intent_type") not in ("train", "predict"):
        errors.append("intent_type 必须是 train 或 predict")
    if "data_request" not in intent:
        errors.append("缺少 data_request")

    dr = intent.get("data_request", {})
    if not isinstance(dr, dict):
        errors.append("data_request 必须是对象")
    else:
        if not dr.get("table"):
            errors.append("data_request.table 不能为空")
        if not dr.get("fields") or not isinstance(dr["fields"], list):
            errors.append("data_request.fields 必须是非空数组")

    # 2. 特征工程校验
    fe_steps = intent.get("feature_engineering", [])
    if not isinstance(fe_steps, list):
        errors.append("feature_engineering 必须是数组")
    else:
        valid_steps = []
        for i, step in enumerate(fe_steps):
            op = step.get("op", "")
            if op not in ALLOWED_OPERATIONS:
                errors.append(f"feature_engineering[{i}].op='{op}' 不在白名单中")
                continue
            params = step.get("params", {})
            if op == "dropna":
                ratio = params.get("max_drop_ratio", 0.3)
                if not (0.0 <= float(ratio) <= 0.5):
                    params["max_drop_ratio"] = max(0.0, min(0.5, float(ratio)))
            elif op == "resample":
                if params.get("rule") not in ("1D", "1H", "1W", "1M", "1T"):
                    errors.append(f"resample rule='{params.get('rule')}' 不支持")
                if params.get("agg") not in ALLOWED_RESAMPLE_AGGS:
                    errors.append(f"resample agg='{params.get('agg')}' 不支持")
            valid_steps.append({"op": op, "params": params})
        intent["feature_engineering"] = valid_steps

    # 3. 模型校验
    mt = intent.get("model_training", {})
    if not isinstance(mt, dict):
        errors.append("model_training 必须是对象")
    else:
        model_name = mt.get("model", "")
        if model_name not in ALLOWED_MODELS:
            errors.append(f"模型 '{model_name}' 不在白名单中")
        else:
            model_def = ALLOWED_MODELS[model_name]
            user_params = mt.get("params", {})
            # 校验参数范围
            sanitized_params = {}
            for pname, pdef in model_def["params"].items():
                if pname in user_params:
                    try:
                        val = float(user_params[pname])
                        val = max(pdef["min"], min(pdef["max"], val))
                        sanitized_params[pname] = int(val) if isinstance(pdef["min"], int) else val
                    except (ValueError, TypeError):
                        errors.append(f"参数 {pname}={user_params[pname]} 不是合法数值")
                # 使用默认值填充必需参数
            if "n_clusters" in model_def["params"] and "n_clusters" not in sanitized_params:
                sanitized_params["n_clusters"] = 3
            if "contamination" in model_def["params"] and "contamination" not in sanitized_params:
                sanitized_params["contamination"] = 0.1
            intent["model_training"]["params"] = sanitized_params

    # 4. 输出规格校验
    os_spec = intent.get("output_spec", {})
    if not isinstance(os_spec, dict):
        errors.append("output_spec 必须是对象")
    else:
        max_rows = os_spec.get("max_rows", 100)
        try:
            max_rows = int(max_rows)
            intent["output_spec"]["max_rows"] = max(1, min(max_rows, 1000))
        except (ValueError, TypeError):
            intent["output_spec"]["max_rows"] = 100

    if errors:
        return False, "; ".join(errors), intent
    return True, "", intent


# ====== 主函数 ===========================================

def generate_ml_intent(query: str, schema_context: str, table_name: str = "") -> dict:
    """根据用户自然语言 + 可用表结构，生成受限 ML 意图 JSON"""
    model_list = "\n".join(
        f"- {name}: {info['name']} ({info['task']}), 参数约束: {info['params'] or '无'}"
        for name, info in ALLOWED_MODELS.items()
    )

    prompt = ML_INTENT_PROMPT.format(
        schema_context=schema_context,
        model_list=model_list,
        query=query,
        table_name=table_name,
    )

    raw_json = ""
    try:
        llm = _llm(temp=0.0)
        resp = llm.invoke([SystemMessage(content=prompt), HumanMessage(content=query)])
        raw = resp.content.strip()

        # 清理 markdown 代码块
        if raw.startswith("```"):
            lines = raw.split("\n")
            raw = "\n".join(lines[1:]) if lines[0].startswith("```") else raw
            if raw.endswith("```"):
                raw = raw.rstrip("```").rstrip()

        # 提取 JSON 对象
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            raw_json = match.group(0)

        intent = json.loads(raw_json)
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "error": f"LLM 生成的 JSON 格式无效: {str(e)}",
            "raw": raw_json[:500],
        }
    except Exception as e:
        return {
            "valid": False,
            "error": f"意图生成失败: {str(e)}",
            "raw": "",
        }

    # 校验
    valid, err, corrected = validate_ml_intent(intent)

    if not valid:
        # 尝试用修正后的意图继续
        return {
            "valid": True,
            "warning": err,
            "intent": corrected,
        }

    return {
        "valid": True,
        "warning": "",
        "intent": intent,
    }
