import os
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


METADATA_ROWS = [
    ("production_orders", "生产工单表",
     "id", "int", "主键ID",
     "1, 2, 3", "自动递增主键"),
    ("production_orders", "生产工单表",
     "product_id", "int", "产品ID",
     "1001, 1002, 1003", "关联产品主数据"),
    ("production_orders", "生产工单表",
     "product_name", "varchar", "产品名称，如变速箱壳体、发动机缸盖",
     "变速箱壳体, 发动机缸盖, 制动盘", "产品中文名称"),
    ("production_orders", "生产工单表",
     "production_line", "varchar", "产线名称，如A线、B线、C线、D线",
     "A线, B线, C线", "生产车间产线标识"),
    ("production_orders", "生产工单表",
     "planned_quantity", "int", "计划产量（件）",
     "2000, 3500, 5000", "生产计划中设定的目标产量"),
    ("production_orders", "生产工单表",
     "actual_quantity", "int", "实际产量（件）",
     "1950, 3420, 5100", "生产实际完成的数量"),
    ("production_orders", "生产工单表",
     "start_time", "timestamp", "生产开始时间",
     "2026-04-01 08:00:00, 2026-05-10 09:00:00", "工单开始生产的时间"),
    ("production_orders", "生产工单表",
     "end_time", "timestamp", "生产结束时间",
     "2026-04-03 17:00:00, 2026-05-12 18:00:00", "工单完成生产的时间"),
    ("production_orders", "生产工单表",
     "status", "varchar", "工单状态（pending=待生产/in_progress=生产中/completed=已完成/cancelled=已取消）",
     "completed, in_progress, pending", "工单当前所处的状态"),
    ("production_orders", "生产工单表",
     "created_at", "timestamp", "创建时间",
     "2026-04-01 00:00:00", "记录创建的时间戳"),
    ("production_orders", "生产工单表",
     "updated_at", "timestamp", "更新时间",
     "2026-04-03 17:00:00", "记录最后更新的时间戳"),

    ("process_yields", "工序产量表",
     "id", "int", "主键ID",
     "1, 2, 3", "自动递增主键"),
    ("process_yields", "工序产量表",
     "order_id", "int", "关联工单ID",
     "1, 15, 230", "外键关联 production_orders.id"),
    ("process_yields", "工序产量表",
     "process_name", "varchar", "工序名称，如冲压、焊接、涂装、总装、精加工、热处理、打磨、检测",
     "冲压, 焊接, 涂装, 总装", "生产过程中的操作步骤名称"),
    ("process_yields", "工序产量表",
     "produced_quantity", "int", "生产数量（件）",
     "1950, 1920, 3400", "该工序生产的总数量"),
    ("process_yields", "工序产量表",
     "qualified_quantity", "int", "合格数量（件）",
     "1850, 1820, 3250", "该工序检验合格的数量"),
    ("process_yields", "工序产量表",
     "production_date", "date", "生产日期",
     "2026-04-01, 2026-05-10", "工序执行的日期"),
    ("process_yields", "工序产量表",
     "shift", "varchar", "班次（白班/夜班）",
     "白班, 夜班", "生产排班类型"),
    ("process_yields", "工序产量表",
     "operator_name", "varchar", "操作员姓名",
     "张伟, 李娜, 王强", "执行该工序的操作人员姓名"),

    ("quality_inspections", "质量检验表",
     "id", "int", "主键ID",
     "1, 2, 3", "自动递增主键"),
    ("quality_inspections", "质量检验表",
     "order_id", "int", "关联工单ID",
     "1, 15, 230", "外键关联 production_orders.id"),
    ("quality_inspections", "质量检验表",
     "product_id", "int", "产品ID",
     "1001, 1003, 1005", "被检验产品的ID"),
    ("quality_inspections", "质量检验表",
     "inspection_result", "varchar", "检验结果（pass=合格/fail=不合格/rework=返工）",
     "pass, fail, rework", "质量检验的最终判定结果"),
    ("quality_inspections", "质量检验表",
     "defect_type", "varchar", "缺陷类型，如尺寸偏差、表面缺陷、材质问题、装配不良、焊接缺陷、涂层不均、硬度不足、无缺陷",
     "尺寸偏差, 表面缺陷, 无缺陷", "产品质量缺陷的分类"),
    ("quality_inspections", "质量检验表",
     "inspection_date", "date", "检验日期",
     "2026-04-02, 2026-05-11", "执行质量检验的日期"),
    ("quality_inspections", "质量检验表",
     "inspector", "varchar", "检验员姓名",
     "赵芳, 陈明, 刘洋", "负责质量检验的人员姓名"),
    ("quality_inspections", "质量检验表",
     "defect_quantity", "int", "缺陷数量（件）",
     "0, 15, 50", "检验中发现的不合格品数量"),
    ("quality_inspections", "质量检验表",
     "remark", "varchar", "备注信息",
     "尺寸偏差问题，需隔离报废, 表面缺陷问题，需返工处理", "检验备注或处理建议"),

    ("equipment_downtimes", "设备停机表",
     "id", "int", "主键ID",
     "1, 2, 3", "自动递增主键"),
    ("equipment_downtimes", "设备停机表",
     "equipment_id", "varchar", "设备ID",
     "EQ-001, EQ-004, EQ-007", "设备唯一标识编码"),
    ("equipment_downtimes", "设备停机表",
     "equipment_name", "varchar", "设备名称，如冲压机A、焊接机器人B、数控机床A、涂装线A、总装线A、检测设备A",
     "冲压机A, 焊接机器人B, 数控机床A", "设备的名称标识"),
    ("equipment_downtimes", "设备停机表",
     "downtime_start", "timestamp", "停机开始时间",
     "2026-04-05 10:30:00, 2026-05-15 14:00:00", "设备停止运行的起始时间"),
    ("equipment_downtimes", "设备停机表",
     "downtime_end", "timestamp", "停机结束时间",
     "2026-04-05 12:45:00, 2026-05-15 15:20:00", "设备恢复运行的结束时间"),
    ("equipment_downtimes", "设备停机表",
     "downtime_reason", "varchar", "停机原因，如机械故障、电气故障、模具更换、计划保养、物料短缺、操作失误、质量问题停机",
     "机械故障, 模具更换, 计划保养", "导致设备停机的原因分类"),
    ("equipment_downtimes", "设备停机表",
     "production_line", "varchar", "所属产线",
     "A线, B线, C线", "设备所在的生产线"),
    ("equipment_downtimes", "设备停机表",
     "downtime_duration", "int", "停机时长（分钟）",
     "30, 75, 135", "从停机开始到恢复的持续时长"),
    ("equipment_downtimes", "设备停机表",
     "resolved_by", "varchar", "处理人姓名",
     "周杰, 吴敏, 郑涛", "负责处理停机事件的人员"),

    ("inventory", "库存表",
     "id", "int", "主键ID",
     "1, 2, 3", "自动递增主键"),
    ("inventory", "库存表",
     "material_id", "int", "物料ID",
     "1, 2, 3", "物料唯一标识"),
    ("inventory", "库存表",
     "material_name", "varchar", "物料名称，如钢板2mm、铝锭、密封圈、螺栓M10、轴承6205、齿轮油、冷却液、包装箱、传感器、液压油",
     "钢板2mm, 铝锭, 密封圈", "物料的名称描述"),
    ("inventory", "库存表",
     "material_code", "varchar", "物料编码，如RM-001",
     "RM-001, RM-002, RM-003", "物料的编码标识"),
    ("inventory", "库存表",
     "warehouse", "varchar", "仓库名称，如原料仓A、原料仓B、半成品仓、成品仓、备件仓",
     "原料仓A, 成品仓, 备件仓", "物料存放的仓库位置"),
    ("inventory", "库存表",
     "quantity", "int", "库存数量",
     "500, 3200, 8500", "当前仓库中的物料数量"),
    ("inventory", "库存表",
     "safety_stock", "int", "安全库存",
     "50, 150, 300", "为防止缺料而设定的最低库存水平"),
    ("inventory", "库存表",
     "unit", "varchar", "单位",
     "kg, 个, L", "物料的计量单位"),

    ("production_orders", "生产工单表",
     "_table_relation", "relationship", "关联关系",
     "process_yields.order_id → production_orders.id", "工序产量通过order_id关联生产工单"),
    ("production_orders", "生产工单表",
     "_table_relation2", "relationship", "关联关系",
     "quality_inspections.order_id → production_orders.id", "质量检验通过order_id关联生产工单"),

    ("process_yields", "工序产量表",
     "_table_relation", "relationship", "关联关系",
     "process_yields.order_id → production_orders.id", "工序产量通过order_id关联生产工单"),

    ("quality_inspections", "质量检验表",
     "_table_relation", "relationship", "关联关系",
     "quality_inspections.order_id → production_orders.id", "质量检验通过order_id关联生产工单"),

    ("equipment_downtimes", "设备停机表",
     "_table_relation", "relationship", "关联关系",
     "equipment_downtimes.production_line 可与 production_orders.production_line 关联", "设备停机通过产线与生产工单关联"),

    ("inventory", "库存表",
     "_table_relation", "relationship", "关联关系",
     "inventory.material_id 可与生产BOM物料主数据关联", "库存通过物料ID与物料主数据关联"),
]


def clear_metadata(cursor):
    cursor.execute("TRUNCATE TABLE metadata_config CASCADE")
    print("[OK] 已清空 metadata_config 表")


def insert_metadata(cursor):
    print("[生成] 正在插入 metadata_config ...")

    sql = """
        INSERT INTO metadata_config
            (table_name, table_comment, field_name, field_type, field_comment,
             sample_values, relationship_desc)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s, %s, %s)"

    execute_values(cursor, sql, METADATA_ROWS, template=template, page_size=len(METADATA_ROWS))

    print(f"[OK] 已插入 {len(METADATA_ROWS)} 条 metadata_config 数据")
    return len(METADATA_ROWS)


def main():
    print("=" * 60)
    print("  MES 数据平台 - 元数据配置初始化脚本")
    print("=" * 60)
    print(f"  数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    print(f"  目标表: metadata_config")
    print(f"  预计插入: {len(METADATA_ROWS)} 条记录")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        clear_metadata(cursor)
        conn.commit()

        count = insert_metadata(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM metadata_config")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT DISTINCT table_name FROM metadata_config ORDER BY table_name")
        tables = [row[0] for row in cursor.fetchall()]

        print()
        print("=" * 60)
        print("  元数据初始化完成！统计如下：")
        print("=" * 60)
        print(f"  metadata_config 总记录数: {total}")
        print(f"  涉及的表:")
        for t in tables:
            cursor.execute("SELECT COUNT(*) FROM metadata_config WHERE table_name = %s", (t,))
            print(f"    - {t}: {cursor.fetchone()[0]} 条")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 元数据初始化失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
