"""ML 建模引擎 — 分类 / 回归 / 聚类 / 异常检测"""

import json, io, base64
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.tree import DecisionTreeClassifier, DecisionTreeRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor, IsolationForest
from sklearn.cluster import KMeans
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, accuracy_score, precision_score, recall_score, f1_score, confusion_matrix, silhouette_score
from sklearn.preprocessing import LabelEncoder, StandardScaler
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties

from db.executor import execute_sql, get_active_config

_zh_font = None
_MODEL_STORE = {}  # 内存模型存储: {name: {model, encoder, scaler, ...}}

def _get_zh_font():
    global _zh_font
    if _zh_font is not None: return _zh_font
    for p in ["C:/Windows/Fonts/msyh.ttc","C:/Windows/Fonts/simhei.ttf"]:
        import os
        if os.path.exists(p): _zh_font = FontProperties(fname=p); return _zh_font
    _zh_font = FontProperties(); return _zh_font

MODEL_TYPES = {
    "linear":       {"name": "线性回归",    "type": "regression"},
    "decision_tree": {"name": "决策树",      "type": "both"},
    "random_forest": {"name": "随机森林",    "type": "both"},
    "logistic":     {"name": "逻辑回归",    "type": "classification"},
    "kmeans":       {"name": "KMeans聚类",  "type": "clustering"},
    "isolation":    {"name": "孤立森林",     "type": "anomaly"},
}

def _load_data(table_name: str, columns: list[str], limit: int = 5000) -> pd.DataFrame:
    cols = ", ".join(columns)
    result = execute_sql(f"SELECT {cols} FROM {table_name} LIMIT {limit}")
    if not result["success"] or not result["rows"]:
        raise ValueError(f"数据加载失败: {result.get('error','')}")
    return pd.DataFrame(result["rows"])

def train_model(table: str, target: str, features: list[str], model_type: str, params: dict = None) -> dict:
    """训练模型,返回指标和可视化"""
    info = MODEL_TYPES[model_type]
    task = info["type"]
    all_cols = features + [target] if target and task != "clustering" else features
    df = _load_data(table, all_cols).dropna()
    if len(df) < 10:
        raise ValueError(f"有效数据不足({len(df)}行)，至少需要10行")

    X = df[features].copy()
    le_target = None
    scaler = StandardScaler()

    # 编码分类特征
    encoders = {}
    for col in X.columns:
        if X[col].dtype == object or X[col].dtype.name == "category":
            le = LabelEncoder()
            X[col] = le.fit_transform(X[col].astype(str))
            encoders[col] = le
    X_scaled = scaler.fit_transform(X)

    y = None
    if target and task != "clustering":
        y_raw = df[target]
        if task == "classification" or (task == "both" and y_raw.dtype == object):
            le_target = LabelEncoder()
            y = le_target.fit_transform(y_raw.astype(str))
        else:
            y = y_raw.values

    # 选模型
    if model_type == "linear":
        m = LinearRegression()
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
        m.fit(X_train, y_train)
        y_pred = m.predict(X_test)
        metrics = {"R²": round(r2_score(y_test, y_pred), 4)}

    elif model_type == "decision_tree":
        is_clf = task == "classification" or (le_target is not None)
        if is_clf:
            m = DecisionTreeClassifier(max_depth=5, random_state=42)
            X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
            m.fit(X_train, y_train)
            y_pred = m.predict(X_test)
            metrics = {"准确率": round(accuracy_score(y_test, y_pred), 4), "F1": round(f1_score(y_test, y_pred, average="weighted"), 4)}
        else:
            m = DecisionTreeRegressor(max_depth=5, random_state=42)
            X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
            m.fit(X_train, y_train)
            y_pred = m.predict(X_test)
            metrics = {"R²": round(r2_score(y_test, y_pred), 4)}

    elif model_type == "random_forest":
        is_clf = task == "classification" or (le_target is not None)
        if is_clf:
            m = RandomForestClassifier(n_estimators=100, max_depth=8, random_state=42)
            X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
            m.fit(X_train, y_train)
            y_pred = m.predict(X_test)
            metrics = {"准确率": round(accuracy_score(y_test, y_pred), 4), "F1": round(f1_score(y_test, y_pred, average="weighted"), 4)}
        else:
            m = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42)
            X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
            m.fit(X_train, y_train)
            y_pred = m.predict(X_test)
            metrics = {"R²": round(r2_score(y_test, y_pred), 4)}

    elif model_type == "logistic":
        m = LogisticRegression(max_iter=1000, random_state=42)
        X_train, X_test, y_train, y_test = train_test_split(X_scaled, y, test_size=0.2, random_state=42)
        m.fit(X_train, y_train)
        y_pred = m.predict(X_test)
        metrics = {"准确率": round(accuracy_score(y_test, y_pred), 4), "F1": round(f1_score(y_test, y_pred, average="weighted"), 4)}

    elif model_type == "kmeans":
        k = params.get("n_clusters", 3) if params else 3
        m = KMeans(n_clusters=k, random_state=42, n_init=10)
        m.fit(X_scaled)
        y_pred = m.labels_
        sil = silhouette_score(X_scaled, y_pred) if len(set(y_pred)) > 1 else -1
        metrics = {"轮廓系数": round(sil, 4), "聚类数": k}
        le_target = None  # 无监督，不存

    elif model_type == "isolation":
        contam = params.get("contamination", 0.1) if params else 0.1
        m = IsolationForest(contamination=contam, random_state=42)
        m.fit(X_scaled)
        y_pred = m.predict(X_scaled)  # 1=正常, -1=异常
        n_outliers = int((y_pred == -1).sum())
        metrics = {"异常比例": round(n_outliers / len(y_pred), 4), "异常数": int(n_outliers), "总样本": len(y_pred)}
        le_target = None

    else:
        raise ValueError(f"未知模型类型: {model_type}")

    # 特征重要性
    importance = {}
    if hasattr(m, "feature_importances_"):
        importance = {features[i]: round(m.feature_importances_[i], 4) for i in range(len(features))}
    elif hasattr(m, "coef_"):
        coef = m.coef_[0] if m.coef_.ndim > 1 else m.coef_
        importance = {features[i]: round(coef[i], 4) for i in range(len(features))}

    # 保存模型
    name = f"{model_type}_{table}_{target or 'nosup'}"
    _MODEL_STORE[name] = {
        "model": m, "encoders": encoders, "scaler": scaler,
        "le_target": le_target, "features": features, "model_type": model_type,
        "task": task,
    }

    # 可视化
    charts = {}
    charts["importance"] = _plot_importance(importance, info["name"])
    if model_type not in ("kmeans", "isolation") and y_test is not None and y_pred is not None:
        charts["pred_vs_actual"] = _plot_pred_vs_actual(y_test[:50], y_pred[:50])

    return {
        "model_name": name,
        "model_type": model_type,
        "model_label": info["name"],
        "metrics": metrics,
        "importance": importance,
        "features": features,
        "samples": len(df),
        "charts": charts,
    }

def predict(model_name: str, data: dict) -> dict:
    """单条推理"""
    store = _MODEL_STORE.get(model_name)
    if not store:
        raise ValueError(f"模型 {model_name} 不存在，请先训练")
    m = store["model"]
    encoders = store["encoders"]
    scaler = store["scaler"]
    le_target = store["le_target"]
    features = store["features"]

    X = []
    for f in features:
        val = data.get(f, 0)
        if f in encoders:
            try: val = encoders[f].transform([str(val)])[0]
            except: val = 0
        X.append(float(val) if val is not None else 0)
    X_scaled = scaler.transform([X])

    model_type = store["model_type"]
    if model_type == "kmeans":
        pred = int(m.predict(X_scaled)[0])
        return {"prediction": pred, "label": f"簇 {pred}"}
    elif model_type == "isolation":
        pred = int(m.predict(X_scaled)[0])
        return {"prediction": pred, "label": "正常" if pred == 1 else "异常"}
    elif model_type in ("linear",):
        pred = float(m.predict(X_scaled)[0])
        return {"prediction": round(pred, 4), "label": str(round(pred, 4))}
    else:
        y_pred = m.predict(X_scaled)
        if le_target:
            label = le_target.inverse_transform([int(y_pred[0])])[0]
            return {"prediction": int(y_pred[0]), "label": str(label)}
        return {"prediction": float(y_pred[0]), "label": str(round(float(y_pred[0]), 4))}

def _plot_importance(importance: dict, title: str) -> str:
    if not importance: return ""
    font = _get_zh_font()
    items = sorted(importance.items(), key=lambda x: abs(x[1]))
    labels = [i[0] for i in items]
    vals = [abs(i[1]) for i in items]
    fig, ax = plt.subplots(figsize=(5, max(2.5, len(labels)*0.35)))
    colors = ["#ef4444" if importance[l] < 0 else "#3b82f6" for l in labels]
    ax.barh(range(len(labels)), vals, color=colors)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontproperties=font, fontsize=9)
    ax.set_title(f"{title} — 特征重要性", fontproperties=font, fontsize=11)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    buf = io.BytesIO(); fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True); plt.close(fig)
    buf.seek(0); svg = buf.read().decode()
    return svg[svg.index("<svg"):] if svg.startswith("<?xml") else svg

def _plot_pred_vs_actual(y_true, y_pred) -> str:
    font = _get_zh_font()
    fig, ax = plt.subplots(figsize=(5, 4))
    ax.scatter(range(len(y_true)), y_true, c="#3b82f6", s=20, alpha=0.7, label="真实值")
    ax.scatter(range(len(y_pred)), y_pred, c="#ef4444", s=20, alpha=0.7, label="预测值")
    ax.set_title("预测 vs 真实 (前50条)", fontproperties=font, fontsize=11)
    ax.legend(prop=font)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False); ax.grid(alpha=0.3)
    buf = io.BytesIO(); fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True); plt.close(fig)
    buf.seek(0); svg = buf.read().decode()
    return svg[svg.index("<svg"):] if svg.startswith("<?xml") else svg

def list_trained_models() -> list[dict]:
    return [{"name": k, "type": v["model_type"], "features": v["features"]} for k, v in _MODEL_STORE.items()]

def get_numeric_tables() -> list[dict]:
    tables = []
    for info in execute_sql("SELECT table_name FROM information_schema.tables WHERE table_schema='public' AND table_type='BASE TABLE'")["rows"]:
        tn = info["table_name"]
        cols = execute_sql(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name='{tn}' ORDER BY ordinal_position")
        if cols["success"]:
            numeric = [c for c in cols["rows"] if c["data_type"] in ("integer","bigint","numeric","real","double precision","smallint")]
            all_cols = [c["column_name"] for c in cols["rows"]]
            if len(numeric) >= 2 and len(cols["rows"]) >= 3:
                r = execute_sql(f"SELECT COUNT(*) as cnt FROM {tn}")
                cnt = r["rows"][0]["cnt"] if r["success"] else 0
                tables.append({"table": tn, "columns": all_cols, "numeric_columns": [c["column_name"] for c in numeric], "rows": cnt})
    return tables
