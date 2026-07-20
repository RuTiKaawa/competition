"""数据库表元数据 — 完整 10 张制造业务表"""

TABLES = [
    {
        "table_name": "mes_process_output",
        "table_alias": "工序产量表",
        "category": "fact",
        "description": "按工单、工序、产线、日期记录投入、合格、不良、返工数量,是产量与良率分析的核心事实表。",
        "row_count": 2752,
        "keywords": ["产量", "良率", "工序", "合格", "不良", "投入", "返工", "生产", "产出"],
        "related_tables": ["mes_work_order", "dim_product", "dim_process", "dim_production_line"],
        "fields": [
            {"name": "output_id", "type": "bigint", "key": "PK", "description": "产量记录ID,主键", "sample": "10234"},
            {"name": "work_order_id", "type": "varchar", "key": "FK", "description": "工单ID → mes_work_order", "sample": "WO-2026-0142"},
            {"name": "product_id", "type": "varchar", "key": "FK", "description": "产品ID → dim_product", "sample": "P005"},
            {"name": "process_id", "type": "varchar", "key": "FK", "description": "工序ID → dim_process", "sample": "PR06"},
            {"name": "line_id", "type": "varchar", "key": "FK", "description": "产线ID → dim_production_line", "sample": "L01"},
            {"name": "stat_date", "type": "date", "key": "", "description": "统计日期", "sample": "2026-07-15"},
            {"name": "input_qty", "type": "integer", "key": "", "description": "投入数量", "sample": "320"},
            {"name": "good_qty", "type": "integer", "key": "", "description": "合格数量", "sample": "312"},
            {"name": "defect_qty", "type": "integer", "key": "", "description": "不良数量", "sample": "8"},
            {"name": "shift_code", "type": "char", "key": "", "description": "班次 (D白班/N夜班)", "sample": "D"},
        ],
    },
    {
        "table_name": "mes_work_order",
        "table_alias": "生产工单表",
        "category": "fact",
        "description": "记录所有生产工单的创建、计划、执行状态,是生产任务调度和执行跟踪的基础表。",
        "row_count": 344,
        "keywords": ["工单", "生产", "排产", "计划", "执行", "工单状态"],
        "related_tables": ["mes_process_output", "dim_product", "dim_production_line"],
        "fields": [
            {"name": "work_order_id", "type": "varchar", "key": "PK", "description": "工单ID,主键", "sample": "WO-2026-0142"},
            {"name": "product_id", "type": "varchar", "key": "FK", "description": "产品ID → dim_product", "sample": "P005"},
            {"name": "line_id", "type": "varchar", "key": "FK", "description": "产线ID → dim_production_line", "sample": "L01"},
            {"name": "plan_qty", "type": "integer", "key": "", "description": "计划产量", "sample": "500"},
            {"name": "actual_qty", "type": "integer", "key": "", "description": "实际产量", "sample": "488"},
            {"name": "start_date", "type": "date", "key": "", "description": "计划开始日期", "sample": "2026-07-14"},
            {"name": "end_date", "type": "date", "key": "", "description": "计划完成日期", "sample": "2026-07-16"},
            {"name": "status", "type": "varchar", "key": "", "description": "工单状态(进行中/已完成/已取消)", "sample": "进行中"},
        ],
    },
    {
        "table_name": "qms_inspection",
        "table_alias": "质量检验表",
        "category": "fact",
        "description": "记录各工序的质量抽检结果,包含抽检数、合格数、不良数和检验结论。",
        "row_count": 1376,
        "keywords": ["质量", "检验", "抽检", "合格率", "质检", "检测", "检验结果"],
        "related_tables": ["mes_work_order", "dim_product", "dim_process"],
        "fields": [
            {"name": "inspection_id", "type": "bigint", "key": "PK", "description": "检验记录ID", "sample": "5001"},
            {"name": "work_order_id", "type": "varchar", "key": "FK", "description": "工单ID → mes_work_order", "sample": "WO-2026-0142"},
            {"name": "product_id", "type": "varchar", "key": "FK", "description": "产品ID → dim_product", "sample": "P005"},
            {"name": "process_id", "type": "varchar", "key": "FK", "description": "工序ID → dim_process", "sample": "PR06"},
            {"name": "sample_qty", "type": "integer", "key": "", "description": "抽检数量", "sample": "50"},
            {"name": "defect_qty", "type": "integer", "key": "", "description": "不良数量", "sample": "2"},
            {"name": "inspection_date", "type": "date", "key": "", "description": "检验日期", "sample": "2026-07-15"},
            {"name": "result", "type": "varchar", "key": "", "description": "检验结论(合格/不合格)", "sample": "合格"},
        ],
    },
    {
        "table_name": "qms_defect_detail",
        "table_alias": "不良明细表",
        "category": "fact",
        "description": "记录每一条不良品的详细信息,包括不良类型、严重等级、责任工序和处置方式。",
        "row_count": 2115,
        "keywords": ["不良", "缺陷", "不良品", "不良类型", "缺陷分析", "质量", "故障", "次品"],
        "related_tables": ["mes_work_order", "dim_product", "dim_process"],
        "fields": [
            {"name": "defect_id", "type": "bigint", "key": "PK", "description": "不良记录ID", "sample": "8001"},
            {"name": "work_order_id", "type": "varchar", "key": "FK", "description": "工单ID", "sample": "WO-2026-0142"},
            {"name": "product_id", "type": "varchar", "key": "FK", "description": "产品ID", "sample": "P005"},
            {"name": "process_id", "type": "varchar", "key": "FK", "description": "责任工序ID", "sample": "PR06"},
            {"name": "defect_type", "type": "varchar", "key": "", "description": "不良类型(功能失效/参数超差/焊接不良等)", "sample": "功能失效"},
            {"name": "severity", "type": "varchar", "key": "", "description": "严重等级(critical/major/minor)", "sample": "major"},
            {"name": "disposal", "type": "varchar", "key": "", "description": "处置方式(返工/报废/让步)", "sample": "返工"},
        ],
    },
    {
        "table_name": "eqp_downtime_record",
        "table_alias": "设备停机记录表",
        "category": "fact",
        "description": "记录所有设备的停机事件,包括计划/非计划停机、停机原因和持续时长。",
        "row_count": 336,
        "keywords": ["设备", "停机", "宕机", "故障", "维护", "设备状态", "运行", "停机时长"],
        "related_tables": ["dim_equipment", "dim_production_line"],
        "fields": [
            {"name": "downtime_id", "type": "bigint", "key": "PK", "description": "停机记录ID", "sample": "2001"},
            {"name": "equipment_id", "type": "varchar", "key": "FK", "description": "设备ID → dim_equipment", "sample": "EQ-CNC-03"},
            {"name": "line_id", "type": "varchar", "key": "FK", "description": "产线ID", "sample": "L03"},
            {"name": "start_time", "type": "datetime", "key": "", "description": "停机开始时间", "sample": "2026-07-15 09:12:00"},
            {"name": "end_time", "type": "datetime", "key": "", "description": "停机结束时间", "sample": "2026-07-15 10:30:00"},
            {"name": "downtime_minutes", "type": "integer", "key": "", "description": "停机持续分钟数", "sample": "78"},
            {"name": "is_planned", "type": "boolean", "key": "", "description": "是否计划停机", "sample": "false"},
            {"name": "reason", "type": "varchar", "key": "", "description": "停机原因", "sample": "刀具磨损更换"},
        ],
    },
    {
        "table_name": "inv_inventory_snapshot",
        "table_alias": "库存快照表",
        "category": "fact",
        "description": "每日库存快照数据,记录各物料/产品在各仓库的库存水平,用于库存预警分析。",
        "row_count": 1004,
        "keywords": ["库存", "仓库", "物料", "存储", "安全库存", "预警", "呆滞", "周转"],
        "related_tables": ["dim_product"],
        "fields": [
            {"name": "snapshot_id", "type": "bigint", "key": "PK", "description": "快照记录ID", "sample": "3001"},
            {"name": "product_id", "type": "varchar", "key": "FK", "description": "产品/物料ID → dim_product", "sample": "P005"},
            {"name": "warehouse_code", "type": "varchar", "key": "", "description": "仓库编码", "sample": "WH-A1"},
            {"name": "available_qty", "type": "integer", "key": "", "description": "可用库存", "sample": "120"},
            {"name": "frozen_qty", "type": "integer", "key": "", "description": "冻结库存", "sample": "15"},
            {"name": "safety_stock_qty", "type": "integer", "key": "", "description": "安全库存阈值", "sample": "200"},
            {"name": "snapshot_date", "type": "date", "key": "", "description": "快照日期", "sample": "2026-07-15"},
        ],
    },
    {
        "table_name": "dim_product",
        "table_alias": "产品主数据表",
        "category": "master",
        "description": "产品/物料主数据,包括产品编码、名称、规格、类型、单位等基础信息。",
        "row_count": 30,
        "keywords": ["产品", "物料", "型号", "规格", "产品信息", "机械", "零部件", "成品"],
        "related_tables": ["mes_process_output", "mes_work_order", "qms_inspection", "qms_defect_detail", "inv_inventory_snapshot"],
        "fields": [
            {"name": "product_id", "type": "varchar", "key": "PK", "description": "产品ID,主键", "sample": "P005"},
            {"name": "product_code", "type": "varchar", "key": "", "description": "产品编码", "sample": "CTRL-05-N"},
            {"name": "product_name", "type": "varchar", "key": "", "description": "产品名称", "sample": "控制器05·标准版"},
            {"name": "category", "type": "varchar", "key": "", "description": "产品分类(机械/电子/电气/结构件)", "sample": "电子"},
            {"name": "spec", "type": "varchar", "key": "", "description": "规格型号", "sample": "V3.2-标准"},
            {"name": "unit", "type": "varchar", "key": "", "description": "单位", "sample": "个"},
            {"name": "is_active", "type": "boolean", "key": "", "description": "是否有效", "sample": "true"},
        ],
    },
    {
        "table_name": "dim_process",
        "table_alias": "工序主数据表",
        "category": "master",
        "description": "工序基础信息,定义各道工序的名称、顺序、标准良率等。",
        "row_count": 8,
        "keywords": ["工序", "流程", "工艺", "SMT", "焊接", "检测", "测试", "包装", "装配"],
        "related_tables": ["mes_process_output", "qms_inspection", "qms_defect_detail"],
        "fields": [
            {"name": "process_id", "type": "varchar", "key": "PK", "description": "工序ID", "sample": "PR06"},
            {"name": "process_name", "type": "varchar", "key": "", "description": "工序名称", "sample": "功能测试"},
            {"name": "process_seq", "type": "integer", "key": "", "description": "工序顺序号", "sample": "6"},
            {"name": "is_critical", "type": "boolean", "key": "", "description": "是否关键工序", "sample": "true"},
            {"name": "std_yield_rate", "type": "decimal", "key": "", "description": "标准良率(%)", "sample": "97.0"},
            {"name": "department", "type": "varchar", "key": "", "description": "负责部门", "sample": "品保部"},
        ],
    },
    {
        "table_name": "dim_production_line",
        "table_alias": "产线主数据表",
        "category": "master",
        "description": "产线基础信息,包括产线名称、所属车间、主管、当前状态。",
        "row_count": 6,
        "keywords": ["产线", "车间", "生产线", "主管", "线体"],
        "related_tables": ["mes_process_output", "mes_work_order", "eqp_downtime_record"],
        "fields": [
            {"name": "line_id", "type": "varchar", "key": "PK", "description": "产线ID", "sample": "L01"},
            {"name": "line_name", "type": "varchar", "key": "", "description": "产线名称", "sample": "一车间-1号线"},
            {"name": "workshop", "type": "varchar", "key": "", "description": "所属车间", "sample": "一车间"},
            {"name": "supervisor", "type": "varchar", "key": "", "description": "产线主管", "sample": "主管1"},
            {"name": "status", "type": "varchar", "key": "", "description": "当前状态(运行中/维护中/空闲)", "sample": "运行中"},
            {"name": "active_orders", "type": "integer", "key": "", "description": "在产工单数", "sample": "3"},
        ],
    },
    {
        "table_name": "dim_equipment",
        "table_alias": "设备主数据表",
        "category": "master",
        "description": "生产设备的基础信息,包括设备名称、类型、所属产线、购置日期等。",
        "row_count": 48,
        "keywords": ["设备", "机器", "装备", "机械", "CNC", "机床", "仪器", "设备台账"],
        "related_tables": ["eqp_downtime_record", "dim_production_line"],
        "fields": [
            {"name": "equipment_id", "type": "varchar", "key": "PK", "description": "设备ID", "sample": "EQ-CNC-03"},
            {"name": "equipment_name", "type": "varchar", "key": "", "description": "设备名称", "sample": "CNC加工中心#03"},
            {"name": "equipment_type", "type": "varchar", "key": "", "description": "设备类型(CNC/注塑机/贴片机/机械臂等)", "sample": "CNC"},
            {"name": "line_id", "type": "varchar", "key": "FK", "description": "所属产线ID", "sample": "L03"},
            {"name": "model", "type": "varchar", "key": "", "description": "设备型号", "sample": "VMC850E"},
            {"name": "purchase_date", "type": "date", "key": "", "description": "购置日期", "sample": "2024-03-15"},
            {"name": "status", "type": "varchar", "key": "", "description": "设备状态(运行/停机/维修)", "sample": "运行"},
        ],
    },
]

# 预定义的快速跳转规则: 关键词 → 表名
QUICK_JUMP_RULES = {
    "机械": "dim_equipment",
    "设备": "dim_equipment",
    "机器": "dim_equipment",
    "装备": "dim_equipment",
    "机床": "dim_equipment",
    "产品": "dim_product",
    "物料": "dim_product",
    "零部件": "dim_product",
    "工序": "dim_process",
    "工艺流程": "dim_process",
    "产线": "dim_production_line",
    "生产线": "dim_production_line",
    "车间": "dim_production_line",
    "产量": "mes_process_output",
    "良率": "mes_process_output",
    "合格": "mes_process_output",
    "不良": "qms_defect_detail",
    "缺陷": "qms_defect_detail",
    "工单": "mes_work_order",
    "生产任务": "mes_work_order",
    "质量": "qms_inspection",
    "检验": "qms_inspection",
    "质检": "qms_inspection",
    "停机": "eqp_downtime_record",
    "宕机": "eqp_downtime_record",
    "库存": "inv_inventory_snapshot",
    "仓库": "inv_inventory_snapshot",
    "呆滞": "inv_inventory_snapshot",
    "安全库存": "inv_inventory_snapshot",
}


def find_table_by_name(name: str) -> dict | None:
    """精确匹配表名"""
    for t in TABLES:
        if t["table_name"] == name:
            return t
    return None


def search_tables(query: str) -> list[dict]:
    """关键词搜索匹配的表,返回匹配度排序列表"""
    results = []
    query_lower = query.lower()
    for t in TABLES:
        score = 0
        # 表名匹配
        if query_lower in t["table_name"].lower():
            score += 10
        # 别名匹配
        if query_lower in t["table_alias"]:
            score += 8
        # 描述匹配
        if query_lower in t["description"]:
            score += 5
        # 关键词匹配
        for kw in t["keywords"]:
            if kw in query or query_lower in kw:
                score += 6
        if score > 0:
            results.append((score, t))
    results.sort(key=lambda x: x[0], reverse=True)
    return [r[1] for r in results]
