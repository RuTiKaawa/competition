def build_echarts_option(chart_type: str, title: str, data: dict | list) -> dict:
    base = {
        "title": {"text": title, "left": "center"},
        "tooltip": {},
        "toolbox": {"feature": {"saveAsImage": {}, "dataView": {"readOnly": False}}},
    }

    if chart_type == "bar":
        x_data = data.get("x", [])
        y_data = data.get("y", [])
        series_name = data.get("series_name", "")

        return {
            **base,
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": x_data},
            "yAxis": {"type": "value"},
            "series": [{"name": series_name, "type": "bar", "data": y_data}],
        }

    elif chart_type == "line":
        x_data = data.get("x", [])
        y_data = data.get("y", [])
        series_name = data.get("series_name", "")

        return {
            **base,
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category", "data": x_data, "boundaryGap": False},
            "yAxis": {"type": "value"},
            "series": [{"name": series_name, "type": "line", "data": y_data, "smooth": True}],
        }

    elif chart_type == "pie":
        pie_data = data

        return {
            **base,
            "tooltip": {"trigger": "item", "formatter": "{a} <br/>{b}: {c} ({d}%)"},
            "legend": {
                "orient": "vertical",
                "left": "left",
                "data": [item["name"] for item in pie_data] if pie_data else [],
            },
            "series": [
                {
                    "name": title,
                    "type": "pie",
                    "radius": "55%",
                    "center": ["50%", "60%"],
                    "data": pie_data,
                    "emphasis": {
                        "itemStyle": {
                            "shadowBlur": 10,
                            "shadowOffsetX": 0,
                            "shadowColor": "rgba(0, 0, 0, 0.5)",
                        }
                    },
                }
            ],
        }

    elif chart_type == "scatter":
        scatter_data = data

        return {
            **base,
            "tooltip": {"trigger": "item"},
            "xAxis": {"type": "value"},
            "yAxis": {"type": "value"},
            "series": [
                {
                    "name": title,
                    "type": "scatter",
                    "data": scatter_data,
                    "symbolSize": 10,
                }
            ],
        }

    else:
        return {"error": f"Unsupported chart type: {chart_type}"}
