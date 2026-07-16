import os
import random
import psycopg2
from psycopg2.extras import execute_values
from datetime import datetime, timedelta
from faker import Faker

fake = Faker("zh_CN")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "mes_db"),
    "user": os.environ.get("DB_USER", "mes_user"),
    "password": os.environ.get("DB_PASS", "mes_pass"),
}

PRODUCTS = [
    (1001, "变速箱壳体"), (1002, "发动机缸盖"), (1003, "制动盘"),
    (1004, "转向节"), (1005, "曲轴"), (1006, "连杆"),
    (1007, "活塞"), (1008, "凸轮轴"),
]

PRODUCTION_LINES = ["A线", "B线", "C线", "D线"]

PROCESS_NAMES = ["冲压", "焊接", "涂装", "总装", "精加工", "热处理", "打磨", "检测"]

DEFECT_TYPES = ["尺寸偏差", "表面缺陷", "材质问题", "装配不良", "焊接缺陷", "涂层不均", "硬度不足"]

EQUIPMENT = [
    (1, "冲压机A"), (2, "冲压机B"), (3, "冲压机C"),
    (4, "焊接机器人A"), (5, "焊接机器人B"), (6, "焊接机器人C"),
    (7, "数控机床A"), (8, "数控机床B"), (9, "数控机床C"), (10, "数控机床D"),
    (11, "涂装线A"), (12, "涂装线B"),
    (13, "总装线A"), (14, "总装线B"),
    (15, "检测设备A"), (16, "检测设备B"),
]

DOWNTIME_REASONS = ["机械故障", "电气故障", "模具更换", "计划保养", "物料短缺", "操作失误", "质量问题停机"]

MATERIALS = [
    (1, "钢板2mm", "RM-001", "kg"),
    (2, "铝锭", "RM-002", "kg"),
    (3, "密封圈", "RM-003", "个"),
    (4, "螺栓M10", "RM-004", "个"),
    (5, "轴承6205", "RM-005", "个"),
    (6, "齿轮油", "RM-006", "L"),
    (7, "冷却液", "RM-007", "L"),
    (8, "包装箱", "RM-008", "个"),
    (9, "传感器", "RM-009", "个"),
    (10, "液压油", "RM-010", "L"),
]

WAREHOUSES = ["原料仓A", "原料仓B", "半成品仓", "成品仓", "备件仓"]

DATE_START = datetime(2026, 4, 1)
DATE_END = datetime(2026, 7, 15)
TOTAL_SECONDS = (DATE_END - DATE_START).total_seconds()

TARGET_ROWS = 500

random.seed(42)
fake.seed_instance(42)


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def random_datetime(start, end):
    delta = end - start
    random_seconds = random.uniform(0, delta.total_seconds())
    return start + timedelta(seconds=random_seconds)


def truncate_all(cursor):
    tables = [
        "quality_inspections",
        "process_yields",
        "equipment_downtimes",
        "inventory",
        "production_orders",
    ]
    for table in tables:
        cursor.execute(f"TRUNCATE TABLE {table} CASCADE")
    print("[OK] 已清空所有数据表")


def generate_production_orders(cursor):
    print("[生成] 正在生成 production_orders ...")
    orders = []
    for _ in range(TARGET_ROWS):
        product_id, product_name = random.choice(PRODUCTS)
        production_line = random.choice(PRODUCTION_LINES)
        planned_qty = random.randint(500, 5000)
        actual_qty = int(planned_qty * random.uniform(0.85, 1.05))
        start_time = random_datetime(DATE_START, DATE_END)
        end_time = start_time + timedelta(days=random.randint(1, 7))
        now = datetime.now()
        if end_time > now:
            if start_time > now:
                status = "pending"
            else:
                status = "in_progress"
        else:
            status = random.choice(["completed", "completed", "completed", "cancelled"])
        created_at = start_time - timedelta(hours=random.randint(1, 24))
        updated_at = end_time if end_time <= now else start_time + timedelta(hours=random.randint(1, 48))
        orders.append((
            product_id, product_name, production_line,
            planned_qty, actual_qty,
            start_time, end_time, status,
            created_at, updated_at,
        ))

    sql = """
        INSERT INTO production_orders
            (product_id, product_name, production_line,
             planned_quantity, actual_quantity,
             start_time, end_time, status,
             created_at, updated_at)
        VALUES %s RETURNING id
    """
    template = "(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"

    order_ids = []
    batch_size = 100
    for i in range(0, len(orders), batch_size):
        batch = orders[i:i + batch_size]
        execute_values(cursor, sql, batch, template=template, page_size=batch_size)
        order_ids.extend([row[0] for row in cursor.fetchall()])

    print(f"[OK] 已生成 {len(order_ids)} 条 production_orders")
    return order_ids, orders


def generate_process_yields(cursor, order_ids, orders):
    print("[生成] 正在生成 process_yields ...")
    yields = []
    order_data_map = {oid: (idx,) for idx, oid in enumerate(order_ids)}

    for idx, order_id in enumerate(order_ids):
        _, _, _, _, actual_qty, _, _, _, _, _ = orders[idx]
        num_processes = random.randint(2, 5)
        selected_processes = random.sample(PROCESS_NAMES, num_processes)
        base_date = orders[idx][5]
        for pi, process_name in enumerate(selected_processes):
            produced_qty = int(actual_qty * random.uniform(0.92, 1.02))
            yield_rate = random.uniform(0.90, 0.99)
            qualified_qty = int(produced_qty * yield_rate)
            production_date = base_date + timedelta(days=pi)
            shift = random.choice(["白班", "夜班"])
            operator_name = fake.name()
            yields.append((
                order_id, process_name, produced_qty, qualified_qty,
                production_date, shift, operator_name,
            ))

    sql = """
        INSERT INTO process_yields
            (order_id, process_name, produced_quantity, qualified_quantity,
             production_date, shift, operator_name)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s, %s, %s)"

    batch_size = 200
    for i in range(0, len(yields), batch_size):
        batch = yields[i:i + batch_size]
        execute_values(cursor, sql, batch, template=template, page_size=batch_size)

    print(f"[OK] 已生成 {len(yields)} 条 process_yields")
    return yields


def generate_quality_inspections(cursor, order_ids, orders):
    print("[生成] 正在生成 quality_inspections ...")
    inspections = []

    for idx, order_id in enumerate(order_ids):
        product_id, product_name, _, _, actual_qty, _, _, _, _, _ = orders[idx]
        num_inspections = random.randint(1, 2)
        for _ in range(num_inspections):
            rand_val = random.random()
            if rand_val < 0.85:
                result = "pass"
                defect_type = "无缺陷"
                defect_qty = 0
            elif rand_val < 0.95:
                result = "fail"
                defect_type = random.choice(DEFECT_TYPES)
                defect_rate = random.uniform(0.02, 0.15)
                defect_qty = max(1, int(actual_qty * defect_rate))
            else:
                result = "rework"
                defect_type = random.choice(DEFECT_TYPES)
                defect_rate = random.uniform(0.02, 0.10)
                defect_qty = max(1, int(actual_qty * defect_rate))

            inspection_date = orders[idx][5] + timedelta(days=random.randint(0, 5))
            inspector = fake.name()
            remark = None
            if result != "pass":
                remark = f"{defect_type}问题，需{'返工处理' if result == 'rework' else '隔离报废'}"

            inspections.append((
                order_id, product_id, result, defect_type,
                inspection_date, inspector, defect_qty, remark,
            ))

    sql = """
        INSERT INTO quality_inspections
            (order_id, product_id, inspection_result, defect_type,
             inspection_date, inspector, defect_quantity, remark)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s, %s, %s, %s)"

    batch_size = 200
    for i in range(0, len(inspections), batch_size):
        batch = inspections[i:i + batch_size]
        execute_values(cursor, sql, batch, template=template, page_size=batch_size)

    print(f"[OK] 已生成 {len(inspections)} 条 quality_inspections")
    return inspections


def generate_equipment_downtimes(cursor):
    print("[生成] 正在生成 equipment_downtimes ...")
    downtimes = []

    for _ in range(TARGET_ROWS):
        equipment_id, equipment_name = random.choice(EQUIPMENT)
        line_map = {
            "冲压机A": "A线", "冲压机B": "B线", "冲压机C": "C线",
            "焊接机器人A": "A线", "焊接机器人B": "B线", "焊接机器人C": "C线",
            "数控机床A": "A线", "数控机床B": "B线", "数控机床C": "C线", "数控机床D": "D线",
            "涂装线A": "A线", "涂装线B": "B线",
            "总装线A": "C线", "总装线B": "D线",
            "检测设备A": "C线", "检测设备B": "D线",
        }
        production_line = line_map.get(equipment_name, random.choice(PRODUCTION_LINES))
        downtime_start = random_datetime(DATE_START, DATE_END)
        duration_minutes = random.randint(10, 200)
        downtime_end = downtime_start + timedelta(minutes=duration_minutes)
        downtime_reason = random.choice(DOWNTIME_REASONS)
        resolved_by = fake.name()

        downtimes.append((
            equipment_id, equipment_name, downtime_start, downtime_end,
            downtime_reason, production_line, duration_minutes, resolved_by,
        ))

    sql = """
        INSERT INTO equipment_downtimes
            (equipment_id, equipment_name, downtime_start, downtime_end,
             downtime_reason, production_line, downtime_duration, resolved_by)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s, %s, %s, %s)"

    batch_size = 200
    for i in range(0, len(downtimes), batch_size):
        batch = downtimes[i:i + batch_size]
        execute_values(cursor, sql, batch, template=template, page_size=batch_size)

    print(f"[OK] 已生成 {len(downtimes)} 条 equipment_downtimes")
    return downtimes


def generate_inventory(cursor):
    print("[生成] 正在生成 inventory ...")
    inventory_records = []
    seen = set()

    for material_id, material_name, material_code, unit in MATERIALS:
        for _ in range(60):
            warehouse = random.choice(WAREHOUSES)
            key = (material_id, warehouse)
            if key in seen:
                continue
            seen.add(key)
            quantity = random.randint(100, 10000)
            safety_stock = random.randint(50, 500)
            inventory_records.append((
                material_id, material_name, material_code,
                warehouse, quantity, safety_stock, unit,
            ))

    random.shuffle(inventory_records)

    sql = """
        INSERT INTO inventory
            (material_id, material_name, material_code,
             warehouse, quantity, safety_stock, unit)
        VALUES %s
    """
    template = "(%s, %s, %s, %s, %s, %s, %s)"

    batch_size = 200
    for i in range(0, len(inventory_records), batch_size):
        batch = inventory_records[i:i + batch_size]
        execute_values(cursor, sql, batch, template=template, page_size=batch_size)

    print(f"[OK] 已生成 {len(inventory_records)} 条 inventory")
    return inventory_records


def main():
    print("=" * 60)
    print("  MES 数据平台 - 种子数据生成脚本")
    print("=" * 60)
    print(f"  数据库: {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']}")
    print(f"  时间范围: {DATE_START.date()} ~ {DATE_END.date()}")
    print(f"  每表目标行数: >= {TARGET_ROWS}")
    print("=" * 60)

    conn = get_connection()
    cursor = conn.cursor()

    try:
        truncate_all(cursor)
        conn.commit()

        order_ids, orders = generate_production_orders(cursor)
        conn.commit()

        generate_process_yields(cursor, order_ids, orders)
        conn.commit()

        generate_quality_inspections(cursor, order_ids, orders)
        conn.commit()

        generate_equipment_downtimes(cursor)
        conn.commit()

        generate_inventory(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) FROM production_orders")
        po_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM process_yields")
        py_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM quality_inspections")
        qi_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM equipment_downtimes")
        ed_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM inventory")
        inv_count = cursor.fetchone()[0]

        print()
        print("=" * 60)
        print("  数据生成完成！统计如下：")
        print("=" * 60)
        print(f"  production_orders:     {po_count} 条")
        print(f"  process_yields:        {py_count} 条")
        print(f"  quality_inspections:   {qi_count} 条")
        print(f"  equipment_downtimes:   {ed_count} 条")
        print(f"  inventory:             {inv_count} 条")
        print(f"  总计:                   {po_count + py_count + qi_count + ed_count + inv_count} 条")
        print("=" * 60)

    except Exception as e:
        conn.rollback()
        print(f"[ERROR] 数据生成失败: {e}")
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
