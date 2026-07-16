import os
import json
import psycopg2
from psycopg2.extras import execute_values

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "mes_db"),
    "user": os.environ.get("DB_USER", "mes_user"),
    "password": os.environ.get("DB_PASS", "mes_pass"),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


KNOWLEDGE_OBJECTS = [
    ("产线",
     "生产车间中的生产线，包括A线、B线、C线、D线，每条产线配备不同类型的设备，负责不同产品的生产任务",
     "生产资源", "production_orders, equipment_downtimes"),
    ("工序",
     "生产过程中的操作步骤，如冲压、焊接、涂装、总装、精加工、热处理、打磨、检测，每个工序有特定的工艺要求和质量标准",
     "生产流程", "process_yields"),
    ("产品",
     "生产制造的成品或半成品，如变速箱壳体、发动机缸盖、制动盘、转向节、曲轴、连杆、活塞、凸轮轴",
     "生产对象", "production_orders, quality_inspections"),
    ("设备",
     "生产过程中使用的机器设备，如冲压机、焊接机器人、数控机床、涂装线、总装线、检测设备等",
     "生产资源", "equipment_downtimes"),
    ("工单",
     "生产任务的载体，记录生产计划与实际执行情况，包含产品信息、计划产量、实际产量、时间安排和状态",
     "生产管理", "production_orders"),
    ("物料",
     "生产所需的原材料、辅料和零部件，包括钢板、铝锭、密封圈、螺栓、轴承、润滑油等",
     "物料管理", "inventory"),
    ("仓库",
     "存储物料和成品的场所，包括原料仓A/B、半成品仓、成品仓、备件仓",
     "物料管理", "inventory"),
    ("质检",
     "对产品进行质量检验的过程和结果记录，包含检验结果、缺陷类型、检验员信息等",
     "质量管理", "quality_inspections"),
    ("停机",
     "设备因故障、保养、模具更换等原因停止运行的事件记录，包含停机时长、原因和处理人",
     "设备管理", "equipment_downtimes"),
    ("班次",
     "生产排班制度，包括白班和夜班，不同班次有不同的操作人员和生产任务安排",
     "生产管理", "process_yields"),
    ("操作员",
     "执行生产操作的一线工人，负责具体工序的生产作业，记录在工序产量表中",
     "人员管理", "process_yields"),
    ("检验员",
     "负责质量检验的专业人员，对产品进行质量检测并记录检验结果",
     "质量管理", "quality_inspections"),
    ("缺陷",
     "产品质量问题的分类，包括尺寸偏差、表面缺陷、材质问题、装配不良、焊接缺陷、涂层不均、硬度不足",
     "质量管理", "quality_inspections"),
    ("产量",
     "生产数量的统计数据，包括计划产量、实际产量、工序产量，是衡量生产效率的核心指标",
     "生产指标", "production_orders, process_yields"),
    ("良率",
     "产品质量合格率的指标，计算公式为合格数量除以生产总数，是质量管理的核心KPI",
     "质量指标", "process_yields, quality_inspections"),
    ("安全库存",
     "为防止缺料而设置的最低库存水平，当实际库存低于此值时触发补货预警",
     "库存指标", "inventory"),
    ("计划产量",
     "生产计划中设定的目标产量，是生产排程的核心参数，用于指导生产和考核完成情况",
     "生产指标", "production_orders"),
    ("实际产量",
     "生产实际完成的数量，与计划产量对比可计算计划完成率，反映生产执行效果",
     "生产指标", "production_orders"),
]

KNOWLEDGE_INDICATORS = [
    ("良率",
     "(合格数量 / 生产总数) × 100%",
     "反映生产过程中产品质量合格的比例，是衡量制造质量水平的核心指标。良率越高说明生产过程越稳定，质量控制越有效",
     "百分比", "质量指标"),
    ("设备OEE",
     "可用率 × 表现性 × 质量指数",
     "设备综合效率（Overall Equipment Effectiveness），全面衡量设备利用情况的指标，世界级制造水平OEE应达到85%以上",
     "百分比", "设备指标"),
    ("可用率",
     "(计划运行时间 - 停机时间) / 计划运行时间 × 100%",
     "衡量设备在计划生产时间内实际可用程度的指标，反映设备可靠性和维护水平",
     "百分比", "设备指标"),
    ("表现性",
     "实际产量 / (计划运行时间 × 理论节拍) × 100%",
     "衡量设备实际运行速度与理论设计速度的比值，反映设备运行效率",
     "百分比", "设备指标"),
    ("质量指数",
     "合格数量 / 生产总数 × 100%",
     "衡量设备生产过程产出品质量水平的指标，是OEE的三大组成部分之一",
     "百分比", "设备指标"),
    ("停机率",
     "停机时长 / 计划生产时长 × 100%",
     "反映设备因故障或其他原因停止生产的时间占比，停机率越高说明设备稳定性越差",
     "百分比", "设备指标"),
    ("计划完成率",
     "实际产量 / 计划产量 × 100%",
     "衡量生产计划执行程度的指标，反映生产组织能力和执行效率",
     "百分比", "生产指标"),
    ("库存周转率",
     "出库数量 / 平均库存",
     "衡量库存管理效率的指标，周转率越高说明库存流动性越好，资金占用越少",
     "次数", "库存指标"),
    ("缺陷率",
     "缺陷数量 / 检验总数 × 100%",
     "反映产品检验中发现缺陷的比例，是衡量质量水平的反向指标，缺陷率越低越好",
     "百分比", "质量指标"),
    ("返工率",
     "返工数量 / 检验总数 × 100%",
     "反映需要返工处理的产品比例，返工率过高说明首次通过率不足，制程能力有待提升",
     "百分比", "质量指标"),
    ("单位时间产量",
     "实际产量 / 生产时长",
     "衡量单位时间内生产产出的指标，反映生产效率和产线产能利用情况",
     "件/小时", "生产指标"),
    ("物料损耗率",
     "损耗数量 / 领用数量 × 100%",
     "反映生产过程中物料消耗和浪费情况的指标，是成本控制的关键参数",
     "百分比", "物料指标"),
]

KNOWLEDGE_RULES = [
    ("停机超30分钟需预警",
     "设备单次停机时长 > 30 分钟",
     "设备单次停机超过30分钟时，系统自动发送预警通知给设备管理人员和生产主管，要求跟进处理并记录停机原因",
     "warning", "设备管理"),
    ("连续3天产量下降标记异常",
     "同一产线连续3天 actual_quantity 持续下降",
     "同一产线连续3天实际产量持续下降时，系统标记为生产异常，生成异常报告并通知生产经理进行原因分析",
     "error", "生产管理"),
    ("良率低于95%触发质量警报",
     "单日良率 < 95%",
     "当日良率低于95%时触发质量异常警报，通知质量部门进行专项分析，排查工艺参数和设备状态",
     "error", "质量管理"),
    ("库存低于安全库存需补货",
     "quantity < safety_stock",
     "物料库存数量低于安全库存时，系统自动生成补货建议单，推荐补货数量 = 安全库存 - 当前库存 + 预计消耗量",
     "warning", "库存管理"),
    ("检验不合格品需隔离处理",
     "inspection_result = 'fail'",
     "质量检验不合格的产品必须立即移入不合格品隔离区，记录缺陷原因和处理方案，防止混入合格品",
     "critical", "质量管理"),
    ("计划产量偏差超20%需说明",
     "ABS(actual_quantity - planned_quantity) / planned_quantity > 0.20",
     "实际产量与计划产量偏差超过20%时，系统要求工单负责人填写偏差说明，记录偏差原因及改进措施",
     "warning", "生产管理"),
]

KNOWLEDGE_THEMES = [
    ("生产分析",
     "分析生产计划完成情况、产量趋势、产线效率，帮助企业了解生产能力、发现生产瓶颈、优化排产计划",
     json.dumps([
         "各产线本月计划完成率是多少？",
         "最近一周产量趋势如何？",
         "哪条产线效率最高？",
         "本月产量环比变化情况？",
         "各产品实际产量与计划产量对比？",
         "本季度产量最高的产品是哪几个？",
     ], ensure_ascii=False),
     "生产管理"),
    ("质量分析",
     "分析产品质量状况、缺陷分布、良率趋势，帮助企业发现问题根源、提升产品质量水平、降低质量成本",
     json.dumps([
         "各产品良率排名？",
         "最常见的缺陷类型是什么？",
         "本月质量趋势如何？",
         "哪个工序良率最低？",
         "返工率最高的产品是哪些？",
         "各检验员的合格率对比？",
     ], ensure_ascii=False),
     "质量管理"),
    ("设备分析",
     "分析设备运行状态、停机分布、OEE指标，帮助企业优化设备维护计划、降低停机损失、提升设备综合效率",
     json.dumps([
         "设备停机率排行？",
         "最常见的停机原因是什么？",
         "各设备OEE指标如何？",
         "本月计划保养完成情况？",
         "哪台设备故障率最高？",
         "各产线设备综合效率对比？",
     ], ensure_ascii=False),
     "设备管理"),
    ("库存分析",
     "分析库存水平、周转情况、安全库存预警，帮助企业优化库存结构、减少资金占用、保障物料供应",
     json.dumps([
         "哪些物料库存低于安全库存？",
         "各仓库库存分布情况？",
         "库存周转率趋势如何？",
         "需要补货的物料有哪些？",
         "库存金额最高的物料排名？",
         "各物料库存周转天数对比？",
     ], ensure_ascii=False),
     "库存管理"),
]


def truncate_knowledge(cursor):
    tables = ["knowledge_rules", "knowledge_indicators", "knowledge_objects", "knowledge_themes"]
    for table in tables:
        cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
    print("[OK] 已清空所有知识库表")


def insert_knowledge_objects(cursor):
    print("[生成] 正在插入 knowledge_objects ...")
    sql = """
        INSERT INTO knowledge_objects
            (object_name, description, object_type, related_tables)
        VALUES %s
    """
    template = "(%s, %s, %s, %s)"
    execute_values(cursor, sql, KNOWLEDGE_OBJECTS, template=template, page_size=len(KNOWLEDGE_OBJECTS))
    print(f"[OK] 已插入 {len(KNOWLEDGE_OBJECTS)} 条 knowledge_objects")
    return len(KNOWLEDGE_OBJECTS)


def insert_knowledge_indicators(cursor):
    print("[生成] 正在插入 knowledge_indicators ...")
    sql = """
        INSERT INTO knowledge_indicators
            (indicator_name, formula, description, unit, category)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s)"
    execute_values(cursor, sql, KNOWLEDGE_INDICATORS, template=template, page_size=len(KNOWLEDGE_INDICATORS))
    print(f"[OK] 已插入 {len(KNOWLEDGE_INDICATORS)} 条 knowledge_indicators")
    return len(KNOWLEDGE_INDICATORS)


def insert_knowledge_rules(cursor):
    print("[生成] 正在插入 knowledge_rules ...")
    adjusted = []
    for rule_name, rule_condition, action_desc, severity, category in KNOWLEDGE_RULES:
        rule_content = f"条件: {rule_condition}\n措施: {action_desc}"
        adjusted.append((rule_name, rule_content, severity, category))
    sql = """
        INSERT INTO knowledge_rules
            (rule_name, rule_content, severity, category)
        VALUES %s
    """
    template = "(%s, %s, %s, %s)"
    execute_values(cursor, sql, adjusted, template=template, page_size=len(adjusted))
    print(f"[OK] 已插入 {len(adjusted)} 条 knowledge_rules")
    return len(adjusted)


def insert_knowledge_themes(cursor):
    print("[生成] 正在插入 knowledge_themes ...")
    data = [(name, desc, qs) for name, desc, qs, _cat in KNOWLEDGE_THEMES]
    sql = """
        INSERT INTO knowledge_themes
            (theme_name, description, question_templates)
        VALUES %s
    """
    template = "(%s, %s, %s)"
    execute_values(cursor, sql, data, template=template, page_size=len(data))
    print(f"[OK] 已插入 {len(data)} 条 knowledge_themes")
    return len(data)


def main():
    print("=" * 60)
    print("  MES 数据平台 - 知识库初始化脚本")
    print("=" * 60)
    print(f"  数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    print(f"  目标表: knowledge_objects, knowledge_indicators,")
    print(f"          knowledge_rules, knowledge_themes")
    print(f"  预计插入:")
    print(f"    - knowledge_objects:   {len(KNOWLEDGE_OBJECTS)} 条")
    print(f"    - knowledge_indicators: {len(KNOWLEDGE_INDICATORS)} 条")
    print(f"    - knowledge_rules:     {len(KNOWLEDGE_RULES)} 条")
    print(f"    - knowledge_themes:    {len(KNOWLEDGE_THEMES)} 条")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        truncate_knowledge(cursor)
        conn.commit()

        obj_count = insert_knowledge_objects(cursor)
        conn.commit()

        ind_count = insert_knowledge_indicators(cursor)
        conn.commit()

        rule_count = insert_knowledge_rules(cursor)
        conn.commit()

        theme_count = insert_knowledge_themes(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM knowledge_objects")
        ko = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM knowledge_indicators")
        ki = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM knowledge_rules")
        kr = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM knowledge_themes")
        kt = cursor.fetchone()[0]

        print()
        print("=" * 60)
        print("  知识库初始化完成！统计如下：")
        print("=" * 60)
        print(f"  knowledge_objects:     {ko} 条")
        print(f"  knowledge_indicators:  {ki} 条")
        print(f"  knowledge_rules:       {kr} 条")
        print(f"  knowledge_themes:      {kt} 条")
        print(f"  总计:                   {ko + ki + kr + kt} 条")
        print()
        print("  知识主题详情:")
        for theme in KNOWLEDGE_THEMES:
            questions = json.loads(theme[2])
            print(f"    [{theme[0]}] {len(questions)} 个问答模板")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 知识库初始化失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
