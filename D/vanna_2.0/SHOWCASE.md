# Vanna 2.0 多数据源展示入口

这个入口位于 `vanna_showcase/`，不修改 `src/vanna` 内部实现。代码仓库不需要携带数据库、运行数据或 API Key：即使三者都不存在，应用也能正常启动并引导使用者完成配置。

## 页面与接口

- `/`：响应式能力首页。
- `/settings`：统一个人设置页，配置 DeepSeek Key、下载 Chinook 示例或手动导入数据。
- `/data-sources`：兼容旧链接，重定向到 `/settings#data-sources`。
- `/chat/`：官方 `<vanna-chat>` 富聊天页面；只有模型凭据和至少一个数据源都就绪时才创建聊天组件。
- `/api/readiness`：分别报告应用、模型和数据源就绪状态。
- `/health` 与 `/chat/health`：外层应用和 Vanna 子应用健康检查。

## 启动

创建环境并安装最小依赖后，从仓库根目录运行：

```bash
.venv/bin/uvicorn vanna_showcase.app:app --host 127.0.0.1 --port 8000
```

浏览器打开 <http://127.0.0.1:8000/>。第一次使用建议进入 <http://127.0.0.1:8000/settings>：

1. 输入个人 DeepSeek API Key。后端会先真实请求 DeepSeek 验证，通过后才按用户 ID 加密保存。
2. 上传一个或多个 CSV（也可上传包含 CSV 的 ZIP），或点击“下载并体验”获取官方 Chinook 示例。
3. 两项都就绪后进入 `/chat/`，选择数据源并开始查询。

`DEEPSEEK_API_KEY` 仍可作为服务器级回退配置；个人 Key 的优先级更高。接口不会回显 Key。默认会在 `.vanna_data/credential.key` 生成本机加密主密钥；多实例或需要跨部署解密时，应通过 `VANNA_CREDENTIAL_ENCRYPTION_KEY` 提供固定 Fernet key。

## 数据导入、切换与删除原理

上传文件由 FastAPI 的 multipart 接口接收，经过文件类型、总大小和 ZIP 路径检查后，服务端使用 DuckDB 的 `read_csv_auto` 推断字段并生成独立的 `database.duckdb`。注册信息和对话到数据源的绑定保存在 `.vanna_data/data_sources.sqlite`。

每次执行 `run_sql` 时，`MultiSourceSqlRunner` 根据 `conversation_id` 查找当前数据源：SQLite 使用只读 URI 和 `PRAGMA query_only`，DuckDB 使用 `read_only=True`；只允许单条 `SELECT`，并限制返回行数。切换只影响当前对话。

删除操作不是删除聊天记录，而是删除注册信息、所有相关对话绑定，以及磁盘上的数据库和原始上传目录。Chinook 也可以物理删除；删除后可再次从官网安装。下载过程先写入 `.part`，验证 SQLite 完整性和预期 11 张表后再原子替换正式文件。

## Git 交付边界

`.gitignore` 会排除 `.env`、`.vanna_data/`、`*.sqlite`、`*.db`、DuckDB、虚拟环境和缓存。因此提交的是可重新安装的源码与示例配置，不包含用户数据库、个人 Key、主加密密钥或测试时生成的数据。Chinook 只是前端可选体验项，不是启动依赖。

MySQL、PostgreSQL、AnalyticDB/VPC 和 RAG 向量库入口目前明确标记为“未完成”，不会伪装成可用连接器。

## 验证

```bash
.venv/bin/python -m pytest -q \
  tests/test_showcase_app.py \
  tests/test_data_sources.py \
  tests/test_credentials.py
```

测试使用临时目录创建第二个数据源与 Chinook 模拟下载，验证导入、按对话切换、只读查询、物理删除和重新安装；测试数据不会进入最终项目运行目录。
