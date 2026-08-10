# 变更记录

## 2026-07-30

### OverviewPage.vue 总览页改版

| 序号 | 修改内容 | 说明 |
|------|---------|------|
| 1 | 添加动态问候头部 | 根据北京时间（UTC+8）动态显示问候语 + 智能体名称 "Oripio"。时段：05:00-12:00 morning / 12:00-13:00 noon / 13:00-18:00 afternoon / 18:00-05:00 evening |
| 2 | 移除顶部三大核心入口 | 删除了"智能问析""数据资源""业务知识"三个入口卡片 |
| 3 | 重排数据底座概览四项 | 顺序改为：数据表 → 字段总数 → 表间关系 → 分析主题 |
| 4 | 四张卡片点击弹窗 | 每张卡片支持点击弹出详情弹窗，数据懒加载（首次点击时请求） |
| 5 | 数据表弹窗 | 展示所有表名、字段数、数据行数 |
| 6 | 字段总数弹窗 | 按表分组展示所有字段，主键用 🔑 标记，显示字段类型 |
| 7 | 表间关系知识图谱 | 使用 vis-network 渲染力导向图，节点按业务域着色（dim蓝/mes绿/qms红/eqp橙/inv青/metadata紫），支持拖拽缩放 |
| 8 | 分析主题弹窗 | 展示所有分析指标名称、描述、计算公式、涉及表 |

### 新增文件

| 文件 | 说明 |
|------|------|
| `src/components/ModalDialog.vue` | 通用弹窗组件（支持 Teleport、遮罩、关闭按钮、自定义宽高） |
| `src/components/KnowledgeGraph.vue` | 知识图谱可视化组件（封装 vis-network，含表名中文化映射） |
| `CHANGELOG.md` | 变更记录文件 |

### backend/routers/tables.py

| 序号 | 修改内容 | 说明 |
|------|---------|------|
| 9 | 新增 `topic_count` 字段 → 改为固定 4 | 原先从 `metadata_metrics` 统计（10 个），现固定为 4 大分析主题 |
| 10 | 新增 `GET /api/tables/topics` 接口 → 改为预定义 4 大类 | 返回 4 大主题：生产分析、质量分析、设备分析、库存分析，含图标/描述/涉及表/相关指标 |
| 11 | 移除 `metadata_metrics` 查询依赖 | topics 端点不再依赖数据库连接，使用硬编码常量 |

### 新增依赖

| 包名 | 用途 |
|------|------|
| vis-network | 知识图谱力导向图渲染 |
| vis-data | vis-network 数据管理 |

## 2026-08-01

### 总览页智能问析入口

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 在数据底座概览下方新增自然语言问析入口，提供输入框、开始分析按钮和两个真实项目典型问题 |
| `vue_first/src/pages/OverviewPage.vue` | 新增智能问析结果区域，使用 SVG 折线图展示工序不良数量或工序良率，并同步显示各工序数值 |
| `vue_first/backend/routers/tables.py` | 新增 `GET /api/tables/analysis-examples` 接口，基于 `mes_process_output` 和 `dim_process` 真实聚合数据返回分析结果 |
| `vue_first/src/pages/DataPage.vue` | 将未使用的 `row` 参数标记为 `_row`，修复 TypeScript 构建阻塞，不改变原有交互 |
| `vue_first/src/components/KnowledgeGraph.vue` | 兼容当前 vis-network 类型定义，修复构建类型错误，不改变图谱行为 |

### 本次典型问题

1. `近一个月各工序的不良数量趋势如何？`
2. `各工序的产量和良率表现如何？`

### 验证结果

- 两个示例接口均返回 8 个真实工序数据序列。
- `npm run build` 已通过。

## 2026-08-01（去对话指引位置调整）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 将“去对话”指引条从智能问析入口下方移到分析结果之后 |
| `vue_first/src/pages/OverviewPage.vue` | 指引条仅在出现分析结果且加载完成时显示，符合“先看结果、再引导去对话”的逻辑 |

### 说明

- 点击“开始分析”出现结果后，结果下方显示“想深入了解某个业务问题？去对话 →”指引。
- `npm run build` 已通过。

## 2026-08-01（总览页智能问析指引条）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 在智能问析入口下方新增指引条：提示用户“想深入了解业务问题可进入智能问析随时提问” |
| `vue_first/src/pages/OverviewPage.vue` | 指引条带“去对话”按钮和箭头图标，点击跳转到智能分析界面 |

### 说明

- 指引条文案：想深入了解某个业务问题？/ 如果还想和 Oripio 继续对话，了解更多业务知识，可以进入智能问析随时提问。
- 点击“去对话 →”后通过已有的 `navigate` 事件跳转到智能分析页。
- `npm run build` 已通过。

## 2026-08-01（后端端口切换为 8009 + 一键问题验证生效）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/vite.config.ts` | 前端 API 代理端口从 8002 调整为 8009（8002 端口存在无法清理的残留进程） |
| `vue_first/backend/routers/tables.py` | 一键问题过滤逻辑已在干净端口 8009 上验证生效 |

### 8009 验证结果

- 各工序的缺陷数量如何？→ 8 个工序柱状图
- 各工序的良率如何？→ 8 个工序柱状图
- 各工序的产量如何？→ 8 个工序柱状图
- 设备的停机时长如何？→ 12 台设备柱状图
- 库存的可用数量如何？→ 3 个仓库柱状图
- 缺陷数量的变化趋势如何？→ 45 个时间点折线图
- 产量的变化趋势如何？→ 45 个时间点折线图

每个一键问题都有真实数据，点击直接出图，无弱智问题。

- `npm run build` 已通过。

## 2026-08-01（一键问题只保留可直接出结果的项）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 将分析核心提取为可复用函数，接口和快捷问题共用同一套分析逻辑 |
| `vue_first/backend/routers/tables.py` | 快捷问题改为“先生成候选问题，再逐个跑真实分析，只保留能产出非空结果的问题” |
| `vue_first/backend/routers/tables.py` | 移除会触发“需要补充指标/无法识别”的弱智模板问题，一键选项点击后必然直接出图 |

### 当前一键问题

- 各工序的缺陷数量如何？→ 柱状图
- 各工序的良率如何？→ 柱状图
- 各工序的产量如何？→ 柱状图
- 设备的停机时长如何？→ 柱状图
- 库存的可用数量如何？→ 柱状图
- 缺陷数量的变化趋势如何？→ 折线图
- 产量的变化趋势如何？→ 折线图

### 验证结果

- 接口返回 7 个可执行问题，每个都有非空 series。
- `npm run build` 已通过。

## 2026-08-01（智能问析图表类型与去字段名）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 趋势类问题（含“变化/趋势/最近/周期”）按时间字段聚合，返回折线趋势数据 |
| `vue_first/backend/routers/tables.py` | 对比类问题（如“良率”“排名”）按业务维度分组，返回柱状对比数据 |
| `vue_first/backend/routers/tables.py` | 结果中不再返回字段名，标题、单位、计算说明全部为业务语言 |
| `vue_first/src/pages/OverviewPage.vue` | 根据结果类型自动切换：趋势用折线图，对比用柱状图 |
| `vue_first/src/pages/OverviewPage.vue` | 移除“分析说明”技术堆砌，只展示业务标题、数值和单位 |

### 展示效果

- “缺陷数量关键变化” → 折线图：缺陷数量变化趋势（按日期，单位：件）
- “各工序的良率” → 柱状图：各工序良率对比（功能测试 99.2%）
- 结果不再出现 `defect_qty`、`SUM(...)` 等字段名

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（智能问析业务化结果）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 新增分组编码到中文业务名映射：工序代码 PR06 → 功能测试、产品、设备、产线等关联表翻译 |
| `vue_first/backend/routers/tables.py` | 新增指标业务映射：defect_qty → 缺陷数量（件）、standard_yield_rate → 良率（%）、downtime_minutes → 停机时长（分钟）等 |
| `vue_first/backend/routers/tables.py` | 分析结果标题改为业务语言：各工序缺陷数量变化、各工序良率对比、各工序产量对比 |
| `vue_first/backend/routers/tables.py` | 良率数值按百分比显示（0.992 → 99.2%），其余指标保留小数 |
| `vue_first/src/pages/OverviewPage.vue` | 结果区改为业务化展示：中文标题、中文横轴标签、带单位的数值 |
| `vue_first/src/pages/OverviewPage.vue` | “分析说明”简化为业务人话：分析内容、计算方式、分组方式，移除字段名/SQL 堆砌 |

### 展示效果

- 标题不再是 `defect_qty 变化分析`，而是 `各工序缺陷数量变化`
- 横轴不再是 `PR06、PR07`，而是 `功能测试、老化测试`
- 数值带单位：`19041 件`、`99.2%`
- 说明变成“各工序的缺陷数量 / 按工序分组”这样的人话

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（智能问析可解释性修正）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 增加分析意图门槛：无法从问题识别指标时返回澄清，不再强行选择第一个数值字段 |
| `vue_first/backend/routers/tables.py` | 增加趋势问题校验：没有明确指标时要求用户补充产量、不良数量、良率、停机时长或库存数量 |
| `vue_first/backend/routers/tables.py` | 增加可解释分析信息：识别意图、数据表、字段用途、计算公式、分组方式和当前限制 |
| `vue_first/backend/routers/tables.py` | 质量/缺陷问题优先使用 defect、inspection、defect_type、inspection_result、process_id 等字段；良率使用平均值而不是求和 |
| `vue_first/src/pages/OverviewPage.vue` | 分析结果增加“我是这样分析的”区域，展示完整的数据依据和计算口径 |

### 行为变化

- “最近一段时间的变化趋势如何？”会提示补充要观察的指标，不再返回 `process_seq` 等无关结果。
- “请分析各工序的良率”会展示 `standard_yield_rate`、分组字段和 `AVG` 计算口径。
- 质量问题会优先使用缺陷/检验相关字段，并说明实际执行的主指标。

### 验证结果

- 构建通过：`npm run build`。

## 2026-08-01（总览页动态智能问析）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | `GET /api/tables/analysis-examples` 改为根据当前数据库可分析能力动态生成快捷问题，不再固定两个制造业示例 |
| `vue_first/backend/routers/tables.py` | 新增 `POST /api/tables/analyze`，接收用户自然语言问题，根据当前数据库表结构、字段语义和数据执行聚合分析 |
| `vue_first/backend/routers/tables.py` | 增加问题意图匹配：库存、停机、设备、产量、不良、工序等关键词会优先选择对应字段和关联 ID 分组 |
| `vue_first/src/pages/OverviewPage.vue` | 输入框和快捷问题统一调用动态分析接口，用户任意输入都会触发后端分析并返回结果图示 |
| `vue_first/src/pages/OverviewPage.vue` | 增加分析加载状态、失败说明和动态结果数量，移除固定“8 个工序”等示例文案 |

### 当前验证

- 库存问题会按 `available_qty` 聚合。
- 设备停机问题会按 `downtime_minutes` 和 `equipment_id` 聚合。
- 各工序不良问题会按 `defect_qty` 和 `process_id` 聚合。
- 各工序产量问题会按 `good_qty + defect_qty` 和 `process_id` 聚合。
- `npm run build` 已通过。

### 当前边界

当前 `/analyze` 是可解释的基础分析器，已实现“用户问题 → 当前数据库字段 → SQL 聚合 → 图示结果”闭环；后续接入 LLM Agent 时，可以替换问题意图解析和 SQL 生成层，而不需要重做总览页交互。

## 2026-08-01（分析主题语义与关系图谱完善）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 将分析主题从“表所属业务域”改为“当前数据库可支持的分析能力” |
| `vue_first/backend/routers/tables.py` | 根据表名、字段名、时间字段、数值字段和字段类型推导指标统计、趋势变化、质量缺陷、生产产出、设备运行、库存存量等主题 |
| `vue_first/backend/routers/tables.py` | 每个主题返回能力描述、可分析指标、支持提问、证据字段和关联表，避免静态制造业主题误导其他数据库 |
| `vue_first/backend/routers/tables.py` | 表关系接口补充外键、业务关系、推导关系类型及关系描述；无显式外键时可根据同名主键/ID 字段推导低置信关系 |
| `vue_first/src/pages/OverviewPage.vue` | 分析主题弹窗改为展示“可以分析、支持提问、能力依据字段” |
| `vue_first/src/components/KnowledgeGraph.vue` | 关系边展示源字段 → 目标字段，悬停显示关系类型；孤立表明确标记“独立表” |

### 验证结果

- 当前数据库动态识别出 6 类分析能力，而非固定 4 类表分类。
- 关系接口返回 14 个表节点、15 条关系。
- `npm run build` 已通过。

## 2026-08-01（数据底座动态化与数据库切换）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 新增 `get_dynamic_topics`，优先按 `metadata_tables.business_domain` 动态分类，没有元数据时按表名前缀推导 |
| `vue_first/backend/routers/tables.py` | `overview.topic_count` 不再固定为 4，改为当前数据库动态主题数量 |
| `vue_first/backend/routers/tables.py` | `GET /api/tables/topics` 改为返回当前数据库动态主题、关联表和字段数量 |
| `vue_first/backend/routers/tables.py` | `GET /api/tables/relationships` 返回所有表节点、字段数量、连接状态和真实关系，包含无外键的孤立表 |
| `vue_first/src/components/KnowledgeGraph.vue` | 移除固定制造业表名映射，使用后端动态标签；改为从左到右分层布局，显示字段数和连接状态 |
| `vue_first/src/pages/OverviewPage.vue` | 关系图弹窗改为更宽的可读布局，并增加关系明细列表 |
| `vue_first/backend/database.py` | 新增可替换 Engine、连接测试和运行时切换连接池能力 |
| `vue_first/backend/main.py` | 新增 `/api/database/config`、`/api/database/test`、`/api/database/switch` 接口 |
| `vue_first/src/pages/SettingsPage.vue` | 将静态数据库设置改为可测试连接、可切换数据库的真实表单 |
| `vue_first/src/App.vue` | 数据库切换成功后自动返回总览，触发新数据库数据刷新 |

### 验证结果

- 当前数据库动态返回：14 张表、105 个字段、15 条关系、5 个主题。
- 关系接口返回 14 个表节点和 15 条关系。
- 使用当前数据库参数完成运行时切换测试，接口返回“数据库已切换”。
- `npm run build` 已通过。

### 当前边界

- 数据库切换当前实现 PostgreSQL，后续可扩展 MySQL 方言和驱动。
- 生产、质量、设备、库存的“业务关注点”和智能问析示例仍是制造业模板逻辑；通用数据库底座、表字段、行数、关系和主题分类已经动态化。

## 2026-08-01（当前业务关注点）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/backend/routers/tables.py` | 新增 `GET /api/tables/attention-points` 接口，基于真实数据库聚合发现业务关注点 |
| `vue_first/backend/routers/tables.py` | 增加四条统计规则：近 30 天不良数量最高工序、近 30 天良率最低工序、近 30 天停机时长最高设备、最新快照库存安全线检查 |
| `vue_first/src/pages/OverviewPage.vue` | 在“快速掌握业务知识”下方新增“当前业务关注点”区域 |
| `vue_first/src/pages/OverviewPage.vue` | 展示业务分类、问题描述、判断规则，并支持点击“继续分析”跳转智能问析 |

### 当前展示规则

- 质量：按工序汇总近 30 天 `defect_qty`，取最高值
- 生产：按工序计算 `good_qty / (good_qty + defect_qty)`，取最低值
- 设备：按设备汇总近 30 天 `downtime_minutes`，取最高值
- 库存：检查最新快照中 `available_qty < safety_stock_qty`

### 验证结果

- 当前接口返回 4 条关注点，覆盖质量、生产、设备、库存四个业务域。
- `npm run build` 已通过。

## 2026-08-01（总览页内容清理）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 删除“快速掌握业务知识”以下的旧内容：最近 7 天产量趋势、业务统计卡片、设备状态、工单状态和库存预警 |
| `vue_first/src/pages/OverviewPage.vue` | 清理旧图表和状态卡片对应的无用计算属性与状态映射，保留数据底座概览、智能问析、业务知识入口及弹窗功能 |

### 当前保留结构

1. 动态问候头部
2. 数据底座概览
3. 智能问析入口与分析结果
4. 快速掌握业务知识

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（快速掌握业务知识导航）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 将“快速开始分析”改名为“快速掌握业务知识” |
| `vue_first/src/pages/OverviewPage.vue` | 生产分析、质量分析、设备分析、库存分析卡片不再跳转智能问析页，改为发出对应业务知识主题导航事件 |
| `vue_first/src/App.vue` | 新增业务知识场景状态和导航处理，将目标场景传递给 `KnowledgePage` |
| `vue_first/src/pages/KnowledgePage.vue` | 新增 `initialScene` 属性，进入页面后自动选中生产、质量、设备或库存对应内容 |

### 导航效果

- 点击“生产分析” → 进入业务知识页并定位生产分析
- 点击“质量分析” → 进入业务知识页并定位质量分析
- 点击“设备分析” → 进入业务知识页并定位设备分析
- 点击“库存分析” → 进入业务知识页并定位库存分析

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（智能问析结果图表调整）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 将原“问题 → 分析维度 → 工序节点”层级树调整为参考图风格的结果柱状图 |
| `vue_first/src/pages/OverviewPage.vue` | 按分析结果从高到低展示工序，柱体高度按真实数值比例渲染 |
| `vue_first/src/pages/OverviewPage.vue` | 增加悬停提示，展示工序名称和具体指标数值；保留底部明细数据 |

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（智能问析结果展示调整）

| 文件 | 修改内容 |
|------|---------|
| `vue_first/src/pages/OverviewPage.vue` | 将智能问析结果由折线图改为树状图，结构为“用户问题 → 分析维度 → 各工序结果” |
| `vue_first/src/pages/OverviewPage.vue` | 保留真实数据库聚合结果，按工序展示不良数量或良率，并支持横向滚动查看完整结果 |
| `vue_first/src/pages/OverviewPage.vue` | 删除折线图专用 SVG 坐标和计算逻辑，避免保留无用代码 |

### 验证结果

- `npm run build` 已通过。

## 2026-08-01（当前业务关注点动态化 + 就地分析）

### 背景

用户反馈：点击总览页的“当前业务关注点”会跳转到智能分析界面，感觉没必要；且关注点不应是静态的，切换数据库后应根据新数据库信息动态找出对应的业务关注点。

### 后端 `vue_first/backend/routers/tables.py`

| 序号 | 修改内容 |
|------|---------|
| 1 | 重写 `GET /api/tables/attention-points`：不再硬编码 `mes_process_output/dim_process/eqp_downtime_record/inv_inventory_snapshot` 四张制造业表，改为扫描当前数据库全部表的数值字段与文本字段动态生成 |
| 2 | 新增“最高值”关注点规则：对每张表的数值字段（优先 `qty/amount/count/total/defect/downtime` 等语义），按可读文本字段分组求 SUM，取最高值 |
| 3 | 新增“趋势上升”关注点规则：对含时间字段的表，对比最近几个周期均值与整体均值，生成“近期上升”关注点，并按表去重（`handled_trend_tables`） |
| 4 | 修复分组字段可读性：`text_fields` 生成条件补充 `no` 关键词，使 `inspection_no`、`work_order_no` 等编号字段可被选中为分组维度，避免回退到 `*_id` |
| 5 | 新增 `dimension_business_name()`：把分组字段名转成可读中文（`_no→编号`、`_code→代码`、`_name→名称`、`_type→类型`、`_status→状态` 等），并补充 `shift_code→班次`、`work_order_no→工单编号`、`inspection_no→检验编号` 等映射 |
| 6 | 新增 `metric_business_name()`：把指标字段名转成中文与单位（`sample_qty→抽样数量/件`、`plan_qty→计划数量/件`、`*_amount→元`、`*_minutes→分钟`、`*_rate→%` 等），并补充常见指标映射 |
| 7 | 修复 `ValueError: too many values to unpack`：`for t, c` 改为 `for t, c, _typ` |

### 前端 `vue_first/src/pages/OverviewPage.vue`

| 序号 | 修改内容 |
|------|---------|
| 1 | `askAttentionPoint(point)` 不再跳转智能分析页，改为就地填充输入框并直接调用 `runAnalysis(point.question)`，点击关注点立即在本页展示分析结果 |
| 2 | 关注点数据继续通过 `loadAttentionPoints()` 从 `/api/tables/attention-points` 动态拉取，切换数据库后刷新 |

### 代理端口 `vue_first/vite.config.ts`

| 序号 | 修改内容 |
|------|---------|
| 1 | `/api` 代理目标从 8009 调整为 8010（8009 端口存在无法清理的残留进程，会服务旧代码；8010 为当前干净后端端口） |

### 当前关注点示例（a07_manufacturing 库）

- 检验编号抽样数量最高 | QI-20260713-01278 的抽样数量最高，为 200 件
- 缺陷类型缺陷数量最高 | 老化异常 的缺陷数量最高，为 719 件
- 工单编号计划数量最高 | MO-20260712-0313 的计划数量最高，为 2,000 件
- 班次投入数量最高 | D 的投入数量最高，为 1,599,642 件
- 停机时长近期上升 | 最近几个周期的停机时长均值为 73 分钟，高于整体均值 46 分钟
- 投入数量近期上升 | 最近几个周期的投入数量均值为 105,294 件，高于整体均值 70,822 件

### 验证结果

- `/api/tables/attention-points` 返回 6 条关注点，全部为业务语言，无字段名泄漏。
- 切换数据库后关注点会随新库字段动态变化。
- 点击关注点即在本页出分析图，不跳转智能分析页。
- `npm run build` 已通过。

## 2026-08-01（当前业务关注点解耦智能问析）

### 背景

用户反馈：当前业务关注点不需要和上方智能问析连接在一起——点击关注点不应触发分析、不填充输入框，作为独立的展示区块。

### 前端 `vue_first/src/pages/OverviewPage.vue`

| 序号 | 修改内容 |
|------|---------|
| 1 | 关注点卡片由可点击 `<button>` 改为纯展示 `<div>`，移除 `@click="askAttentionPoint(point)"` |
| 2 | 移除卡片悬停提示"查看分析 →"及 hover 上浮/阴影交互 |
| 3 | 删除 `askAttentionPoint` 函数，不再填充输入框、不再调用 `runAnalysis`，与上方智能问析完全解耦 |

### 展示效果

- 关注点只展示：图标、分类、标题、详情、判断规则。
- 点击关注点卡片无任何联动，不会触发智能分析。
- 数据仍动态来自 `/api/tables/attention-points`，切换数据库后照常刷新。

### 验证结果

- 页面刷新后关注点为不可点击的展示卡片。
- `npm run build` 已通过。

## 2026-08-01（当前业务关注点改为真实数据问题诊断）

### 背景

用户反馈：关注点不应只是"数值最高/均值上升"这类静态模板，而要根据表中真实数据计算、总结、判断数据实际存在什么问题，并且随数据库动态变化。

### 后端 `vue_first/backend/routers/tables.py`

| 序号 | 修改内容 |
|------|---------|
| 1 | 重写 `GET /api/tables/attention-points`：从"取最高值/均值上升"升级为**数据问题诊断**，基于真实数据计算判定潜在问题 |
| 2 | 新增 5 类动态诊断规则：时间趋势（近期骤升/骤降/波动剧烈）、分布集中（高度集中/失衡）、数据缺失（零值/空值占比）、安全线（可用量<安全库存）、异常占比（状态/结果字段中 fail/不合格 占比） |
| 3 | 诊断规则自动识别当前库的语义字段（时间字段、分组字段、数值指标、状态/结果字段），换库后规则跟随新库重新计算 |
| 4 | 使用类别配额（趋势2/分布2/质量1/安全线1/异常2）保证诊断类型多样，避免单一规则填满列表 |
| 5 | 排除元数据系统表（`metadata_*`）与 `id`/`*_id`/`*_seq`/`*_no`/`*_order` 等非业务指标字段，避免把主键/序号当作业务指标 |
| 6 | 新增 `is_metric_column` 判断，保证只对真正的业务数值指标做分布/质量诊断 |
| 7 | 顶部补充 `import statistics`，用于变异系数（波动）计算 |

### 当前诊断结果（a07_manufacturing 库，真实数据）

- 📈 停机时长近期骤升：最近 3 个周期均值 73 分钟，较整体 46 分钟上升 58%
- 📈 投入数量近期骤升：最近 3 个周期均值 105,294 件，较整体 70,822 件上升 49%
- ⚠️ 冻结数量数据缺失偏高：42% 零值或空值（425 条）
- 🚨 设备状态异常占比偏高：75%（36/48 条）
- 🚨 检验结果异常占比偏高：47%（653/1376 条不合格）

### 验证结果

- 关注点均为真实数据计算得出的潜在问题，业务语言表述，无字段名泄漏。
- 切换数据库后按新库 schema 与数据重新诊断。
- API 与页面均验证通过，`npm run build` 已通过。

## 2026-08-01（修复业务知识接口与页面异常）

### 背景

用户反馈"跑一下代码找出哪里错误"。排查发现：

1. `backend/routers/knowledge.py` 在磁盘上是 **0 字节空文件**（疑似被意外清空），导致 `/api/knowledge/scenes`、`/api/knowledge/terms` 接口 404，业务知识页加载失败。
2. 编辑器报告的 `def _get_core_tables(db: Session) -> s et:` 编译错误正是空文件导致的缓存/索引问题。

### 后端 `vue_first/backend/routers/knowledge.py`

| 序号 | 修改内容 |
|------|---------|
| 1 | 重建被清空的 `knowledge.py`，恢复完整业务知识 API |
| 2 | `GET /api/knowledge/scenes`：按表名前缀将当前库真实表动态归类到 4 大场景（生产/质量/设备/库存），每个对象含表名、图标、描述、是否核心、行数、字段列表与字段详情 |
| 3 | `GET /api/knowledge/terms`：从数据库字段注释提取术语词典，无注释时返回常见业务术语 |
| 4 | `GET /api/knowledge/stats`：统计场景数、表数、字段数、术语数 |

### 后端 `vue_first/backend/main.py`

| 序号 | 修改内容 |
|------|---------|
| 1 | 导入并注册 `knowledge.router`，新增 `/api/knowledge/*` 三个路由 |

### 前端 `vue_first/src/pages/KnowledgePage.vue`

| 序号 | 修改内容 |
|------|---------|
| 1 | 修复第 133 行 `{{ sc ene.desc }}` 空格错误 → `{{ scene.desc }}` |
| 2 | `API_BASE` 从硬编码 `http://127.0.0.1:8001/api` 改为相对路径 `/api`，与项目其他页面一致，走 Vite 代理访问后端 |

### 验证结果

- 后端启动正常，注册 `/api/knowledge/scenes`、`/api/knowledge/terms`、`/api/knowledge/stats`。
- 场景接口返回 4 个场景、10 张真实表；术语接口返回 5 个术语。
- 业务知识页正常展示：场景卡片、数据表列表（含行数/字段）、知识图谱、术语词典、分析模板。
- `npm run build` 已通过。
