"""Chart Agent — 根据查询结果生成多种图表"""

import io
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.font_manager import FontProperties

_zh_font = None
_COLORS = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#06b6d4", "#ec4899", "#f97316", "#84cc16", "#14b8a6"]


def _get_zh_font():
    global _zh_font
    if _zh_font is not None:
        return _zh_font
    for path in ["C:/Windows/Fonts/msyh.ttc", "C:/Windows/Fonts/simhei.ttf", "C:/Windows/Fonts/simsun.ttc"]:
        import os
        if os.path.exists(path):
            _zh_font = FontProperties(fname=path)
            return _zh_font
    _zh_font = FontProperties()
    return _zh_font


def _fig_to_svg(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="svg", bbox_inches="tight", transparent=True)
    buf.seek(0)
    svg = buf.read().decode("utf-8")
    if svg.startswith("<?xml"):
        svg = svg[svg.index("<svg"):]
    plt.close(fig)
    return svg


def _get_cats(rows, columns, limit=15):
    return [str(row[columns[0]]) for row in rows[:limit]]


def _get_vals(rows, col, limit=15):
    return [float(str(row.get(col, 0) or 0)) for row in rows[:limit]]


# ── 柱状图 ──────────────────────────────────────────────
def _bar_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    cats = _get_cats(rows, columns)
    num_cols = columns[1:]
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 0.5), 4))
    x = range(len(cats))
    width = 0.8 / len(num_cols) if len(num_cols) > 1 else 0.6
    for i, col in enumerate(num_cols):
        vals = _get_vals(rows, col)
        ax.bar([xi + i * width for xi in x], vals, width, label=col, color=_COLORS[i % 10])
    ax.set_xticks([xi + width * (len(num_cols) - 1) / 2 for xi in x])
    ax.set_xticklabels(cats, fontproperties=font, rotation=30, ha="right", fontsize=9)
    if len(num_cols) > 1: ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    return _fig_to_svg(fig)


# ── 横向柱状图 ──────────────────────────────────────────
def _barh_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    cats = _get_cats(rows, columns)
    num_cols = columns[1:]
    fig, ax = plt.subplots(figsize=(6, max(3, len(cats) * 0.4)))
    y = range(len(cats))
    height = 0.7 / len(num_cols) if len(num_cols) > 1 else 0.5
    for i, col in enumerate(num_cols):
        vals = _get_vals(rows, col)
        ax.barh([yi + i * height for yi in y], vals, height, label=col, color=_COLORS[i % 10])
    ax.set_yticks([yi + height * (len(num_cols) - 1) / 2 for yi in y])
    ax.set_yticklabels(cats, fontproperties=font, fontsize=10)
    ax.invert_yaxis()
    if len(num_cols) > 1: ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    return _fig_to_svg(fig)


# ── 堆叠柱状图 ──────────────────────────────────────────
def _stacked_bar_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    cats = _get_cats(rows, columns)
    num_cols = columns[1:]
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 0.5), 4))
    x = range(len(cats))
    bottom = np.zeros(len(cats))
    for i, col in enumerate(num_cols):
        vals = _get_vals(rows, col)
        ax.bar(x, vals, 0.6, bottom=bottom, label=col, color=_COLORS[i % 10])
        bottom += np.array(vals)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontproperties=font, rotation=30, ha="right", fontsize=9)
    ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    return _fig_to_svg(fig)


# ── 折线图 ──────────────────────────────────────────────
def _line_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    cats = _get_cats(rows, columns, 30)
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 0.3), 4))
    x = range(len(cats))
    for i, col in enumerate(columns[1:]):
        vals = _get_vals(rows, col, 30)
        ax.plot(x, vals, marker="o", color=_COLORS[i % 10], linewidth=2, markersize=4, label=col)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontproperties=font, rotation=30, ha="right", fontsize=9)
    ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    return _fig_to_svg(fig)


# ── 面积图 ──────────────────────────────────────────────
def _area_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    cats = _get_cats(rows, columns, 30)
    fig, ax = plt.subplots(figsize=(max(6, len(cats) * 0.3), 4))
    x = range(len(cats))
    for i, col in enumerate(columns[1:]):
        vals = _get_vals(rows, col, 30)
        ax.fill_between(x, vals, alpha=0.3, color=_COLORS[i % 10], label=col)
        ax.plot(x, vals, color=_COLORS[i % 10], linewidth=2)
    ax.set_xticks(x)
    ax.set_xticklabels(cats, fontproperties=font, rotation=30, ha="right", fontsize=9)
    ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    return _fig_to_svg(fig)


# ── 饼图 ────────────────────────────────────────────────
def _pie_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    labels = _get_cats(rows, columns, 10)
    vals = _get_vals(rows, columns[1], 10)
    fig, ax = plt.subplots(figsize=(5, 5))
    wedges, texts, autotexts = ax.pie(vals, labels=labels, autopct="%1.1f%%",
                                       colors=_COLORS[:len(labels)], textprops={"fontproperties": font, "fontsize": 10})
    for t in autotexts: t.set_fontsize(8)
    return _fig_to_svg(fig)


# ── 环形图 ──────────────────────────────────────────────
def _donut_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    labels = _get_cats(rows, columns, 10)
    vals = _get_vals(rows, columns[1], 10)
    fig, ax = plt.subplots(figsize=(5, 5))
    wedges, texts, autotexts = ax.pie(vals, labels=labels, autopct="%1.1f%%",
                                       colors=_COLORS[:len(labels)], pctdistance=0.75,
                                       textprops={"fontproperties": font, "fontsize": 10},
                                       wedgeprops={"width": 0.4, "edgecolor": "white"})
    for t in autotexts: t.set_fontsize(8)
    return _fig_to_svg(fig)


# ── 散点图 ──────────────────────────────────────────────
def _scatter_chart(columns, rows):
    if len(columns) < 2: return ""
    font = _get_zh_font()
    num_cols = columns[1:]
    if len(num_cols) < 1: return ""
    fig, ax = plt.subplots(figsize=(5, 5))
    for i, col in enumerate(num_cols):
        # 取两列作 x, y，或单列作索引
        if len(num_cols) >= 2 and i == 0:
            x_vals = _get_vals(rows, num_cols[0], 50)
            y_vals = _get_vals(rows, num_cols[1], 50)
            ax.scatter(x_vals, y_vals, c=_COLORS[i % 10], s=40, alpha=0.7, label=num_cols[0] + " vs " + num_cols[1])
            ax.set_xlabel(num_cols[0], fontproperties=font)
            ax.set_ylabel(num_cols[1], fontproperties=font)
            break
        else:
            x_vals = list(range(len(rows[:50])))
            y_vals = _get_vals(rows, col, 50)
            ax.scatter(x_vals, y_vals, c=_COLORS[i % 10], s=30, alpha=0.7, label=col)
    ax.legend(prop=font, fontsize=9)
    ax.spines["top"].set_visible(False); ax.spines["right"].set_visible(False)
    ax.grid(alpha=0.3)
    return _fig_to_svg(fig)


# ── Generate ─────────────────────────────────────────────
CHART_FUNCS = {
    "bar": _bar_chart,
    "barh": _barh_chart,
    "stacked": _stacked_bar_chart,
    "line": _line_chart,
    "area": _area_chart,
    "pie": _pie_chart,
    "donut": _donut_chart,
    "scatter": _scatter_chart,
}

CHART_AUTO = {
    "趋势": "line", "日": "line", "月": "line", "走势": "line", "时间": "line",
    "占比": "pie", "分布": "donut", "组成": "pie", "比例": "pie",
    "排行": "barh", "排名": "barh", "top": "barh", "最高": "barh", "最低": "barh",
    "相关": "scatter", "关联": "scatter",
}


def generate_chart(columns: list[str], rows: list[dict], query_hint: str = "", force_type: str = "") -> dict:
    """
    chart types: bar | barh | stacked | line | area | pie | donut | scatter
    """
    if not rows or len(rows) < 2 or len(columns) < 2:
        return {"type": "none", "svg": ""}

    query_lower = query_hint.lower()
    num_cols = columns[1:]

    # 检查数值
    all_numeric = True
    for col in num_cols:
        for row in rows[:3]:
            try: float(str(row.get(col, 0) or 0))
            except: all_numeric = False; break
    if not all_numeric:
        return {"type": "none", "svg": ""}

    # 决策
    if force_type in CHART_FUNCS:
        chart_type = force_type
    else:
        chart_type = "bar"
        for kw, ct in CHART_AUTO.items():
            if kw in query_lower:
                chart_type = ct
                break

    try:
        func = CHART_FUNCS.get(chart_type)
        if not func: return {"type": "none", "svg": ""}
        svg = func(columns, rows)
        return {"type": chart_type, "svg": svg}
    except Exception as e:
        return {"type": "error", "svg": "", "error": str(e)}
