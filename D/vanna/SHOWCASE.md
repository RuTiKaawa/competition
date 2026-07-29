# Vanna 2.0 展示首页与富聊天入口

这个入口独立于 `src/vanna`，不会修改 Vanna 包内部实现。它提供：

- `/`：响应式能力展示首页。
- `/chat/`：官方 `<vanna-chat>` 富聊天页面。
- `/health` 与 `/chat/health`：外层和 Vanna 子应用健康检查。
- Chinook 只读 SQL、交互数据表、共享隔离 CSV 与 Plotly 图表。

## 启动

确认仓库根目录存在非空的 `Chinook.sqlite`，并在 `.env` 中配置：

```dotenv
DEEPSEEK_API_KEY=your-key
DEEPSEEK_MODEL=deepseek-v4-flash
```

从仓库根目录运行：

```bash
.venv/bin/uvicorn vanna_showcase.app:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000/>。建议验收问题：

1. `列出数据库所有表`
2. `按国家统计销售额并绘制柱状图`

## 测试

```bash
.venv/bin/python -m pytest -q tests/test_showcase_app.py
```

启动校验会在数据库缺失、为空、损坏、不是 Chinook，或 API key 未配置时立即失败；检查数据库前不会创建 SQLite 文件。
