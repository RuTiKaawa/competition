import statistics
import os
import tempfile
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from database import get_db, quote_ident, import_csv_to_db, import_database_source, collect_import_candidate_files
from pydantic import BaseModel
from typing import Any, Optional, List

router = APIRouter(prefix="/api/tables", tags=["数据表"])


def _column_type_for_mysql(db: Session, table_name: str, column_name: str) -> str:
    """获取 MySQL 列的完整类型定义（用于 MODIFY COLUMN 保持类型不变）"""
    inspector = inspect(db.get_bind())
    for col in inspector.get_columns(table_name):
        if col["name"] == column_name:
            col_type = str(col["type"])
            nullable = "" if col.get("nullable") else " NOT NULL"
            default = ""
            if col.get("default") is not None:
                default = f" DEFAULT {col['default']}"
            return f"{col_type}{nullable}{default}"
    raise HTTPException(status_code=404, detail=f"字段 '{column_name}' 不存在于表 '{table_name}' 中")


# ========== CSV / SQLite / ZIP / URL 数据导入 ==========

@router.post("/import-csv")
async def import_csv(
    request: Request,
    files: List[UploadFile] = File(default=[]),
    table_name: str = Form(""),
    source_type: Optional[str] = Form("file"),
    source_url: Optional[str] = Form(None),
):
    """支持上传 CSV、SQLite、ZIP、文件夹或直接使用远程 URL 导入"""
    try:
        if source_type == "url" and source_url:
            result = import_database_source(source_url, target_table_name=table_name or None)
            return {"success": True, **result}

        uploaded_files = list(files or [])
        if not uploaded_files:
            form = await request.form()
            uploaded_files = [file for file in form.getlist("file") if hasattr(file, "filename")]

        if not uploaded_files:
            raise ValueError("没有收到任何上传文件")

        if len(uploaded_files) == 1:
            upload_file = uploaded_files[0]
            if hasattr(upload_file, "filename"):
                filename = os.path.basename(upload_file.filename or "uploaded")
                content = await upload_file.read()
            else:
                filename = getattr(upload_file, "filename", "uploaded") or "uploaded"
                content = upload_file.read() if hasattr(upload_file, "read") else b""

            suffix = os.path.splitext(filename)[1].lower()
            with tempfile.TemporaryDirectory() as tmp_dir:
                temp_path = os.path.join(tmp_dir, filename or "uploaded")
                os.makedirs(os.path.dirname(temp_path), exist_ok=True)
                with open(temp_path, "wb") as tmp:
                    tmp.write(content)

                if suffix == ".csv":
                    result = import_csv_to_db(temp_path, table_name or (os.path.splitext(os.path.basename(temp_path))[0]))
                else:
                    result = import_database_source(temp_path, target_table_name=table_name or None)
            return {"success": True, **result}

        with tempfile.TemporaryDirectory() as tmp_dir:
            for upload_file in uploaded_files:
                if not hasattr(upload_file, "filename"):
                    continue
                filename = upload_file.filename or "uploaded"
                filename = filename.replace("\\", "/").strip("/") or "uploaded"
                if any(part in {"", ".", ".."} for part in filename.split("/")):
                    raise ValueError("上传文件名包含不安全的路径")
                content = await upload_file.read()
                dest_path = os.path.join(tmp_dir, filename)
                os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                with open(dest_path, "wb") as tmp:
                    tmp.write(content)

            candidates = collect_import_candidate_files(tmp_dir)
            if not candidates:
                raise ValueError("文件夹中没有找到可导入的 CSV/SQLite/ZIP 文件")

            effective_table_name = (table_name or None) if len(candidates) == 1 else None
            imported = []
            for path in candidates:
                imported.append(import_database_source(path, target_table_name=effective_table_name))
            return {"success": True, "mode": "folder", "files": imported}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"导入失败: {str(exc)}")


def get_dynamic_topics(db: Session, inspector) -> list[dict]:
    """根据当前数据库结构推导 Agent 实际具备的分析能力。"""
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_"))
    ]
    schema = {
        table: inspector.get_columns(table)
        for table in tables
    }
    labels = {table: table for table in tables}
    try:
        metadata_columns = {column["name"] for column in inspector.get_columns("metadata_tables")}
        if {"table_name", "table_chinese_name"}.issubset(metadata_columns):
            result = db.execute(text("SELECT table_name, table_chinese_name FROM metadata_tables"))
            labels.update({row[0]: row[1] or row[0] for row in result})
    except Exception:
        pass

    def matches(*words: str) -> list[tuple[str, str]]:
        found = []
        for table, columns in schema.items():
            table_text = table.lower()
            for column in columns:
                column_name = column["name"].lower()
                if any(word.lower() in table_text or word.lower() in column_name for word in words):
                    found.append((table, column["name"]))
        return found

    def topic(topic_id: str, name: str, icon: str, description: str, evidence, metrics, questions):
        related_tables = sorted({table for table, _ in evidence})
        return {
            "id": topic_id,
            "name": name,
            "icon": icon,
            "description": description,
            "related_tables": related_tables,
            "related_metrics": metrics,
            "supported_questions": questions,
            "evidence": [{"table": table, "field": field} for table, field in evidence[:12]],
            "table_labels": {table: labels.get(table, table) for table in related_tables},
        }

    topics = []
    numeric_types = ("INT", "NUMERIC", "DECIMAL", "REAL", "DOUBLE", "FLOAT", "MONEY")
    numeric_fields = [
        (table, column["name"])
        for table, columns in schema.items()
        for column in columns
        if any(kind in str(column["type"]).upper() for kind in numeric_types)
    ]
    time_fields = matches("date", "time", "day", "month", "year", "日期", "时间")

    if numeric_fields:
        topics.append(topic(
            "aggregation", "指标统计与排名", "📊",
            "系统可以对当前数据库中的数值字段进行求和、计数、平均值、分组排名和占比分析。",
            numeric_fields, ["数量", "总和", "平均值", "排名", "占比"],
            ["哪些对象的数值最高？", "各类别的数量和占比是多少？"],
        ))
    if time_fields and numeric_fields:
        topics.append(topic(
            "trend", "趋势变化分析", "📈",
            "系统检测到时间字段和数值字段，可以按日期或时间周期分析变化趋势。",
            time_fields + numeric_fields, ["同比", "环比", "趋势", "峰值"],
            ["最近一段时间的变化趋势如何？", "哪个时间段变化最明显？"],
        ))

    capability_rules = [
        ("quality", "质量与缺陷分析", "✅", ("defect", "quality", "inspection", "fail", "不良", "缺陷", "质量", "检验"), "缺陷数量、不良率、检验结果和问题分布"),
        ("production", "生产与产出分析", "🏭", ("production", "output", "process", "work_order", "产量", "生产", "工序", "工单"), "产出、工序表现和生产执行情况"),
        ("equipment", "设备运行分析", "⚙️", ("equipment", "machine", "downtime", "alarm", "设备", "停机", "报警"), "设备状态、停机时长和运行异常"),
        ("inventory", "库存与存量分析", "📦", ("inventory", "stock", "warehouse", "库存", "物料", "仓库"), "库存水位、安全线和存量变化"),
    ]
    for topic_id, name, icon, words, capability in capability_rules:
        evidence = matches(*words)
        if evidence:
            topics.append(topic(
                topic_id, name, icon,
                f"基于当前数据库中的字段证据，系统可以分析{capability}。",
                evidence, [capability], [f"分析{capability}的关键变化？", f"哪些记录最需要关注？"],
            ))

    if not topics:
        topics.append(topic(
            "data-overview", "数据概览分析", "🔎",
            "系统可以读取当前数据库结构，查看表、字段、数据量和基础分布。",
            [(table, column["name"]) for table, columns in schema.items() for column in columns[:2]],
            ["表数量", "字段数量", "数据行数"], ["当前数据库有哪些数据？", "各数据表规模如何？"],
        ))
    return topics


# ========== 请求模型 ==========

class CommentUpdate(BaseModel):
    comment: str


class UpdateCellRequest(BaseModel):
    table_name: str
    column_name: str
    row_id: str
    id_column: str
    new_value: Optional[Any] = None


class AnalysisRequest(BaseModel):
    question: str


def build_dimension_label_map(db, inspector, group_column: str) -> dict:
    """将分组字段的编码值翻译成业务中文名，例如 PR06 -> 功能测试。"""
    mappings = [
        (("process_id", "process_code"), "dim_process", "process_id", "process_name"),
        (("product_id", "product_code"), "dim_product", "product_id", "product_name"),
        (("equipment_id", "equipment_code"), "dim_equipment", "equipment_id", "equipment_name"),
        (("line_id", "line_code"), "dim_production_line", "line_id", "line_name"),
    ]
    for group_fields, dim_table, key_field, name_field in mappings:
        if group_column not in group_fields:
            continue
        try:
            dim_columns = {column["name"] for column in inspector.get_columns(dim_table)}
            if {key_field, name_field}.issubset(dim_columns):
                q = quote_ident
                result = db.execute(text(f'SELECT {q(key_field)}, {q(name_field)} FROM {q(dim_table)}'))
                return {str(row[0]): str(row[1] or row[0]) for row in result}
        except Exception:
            pass
    return {}


METRIC_BUSINESS_MAP = {
    "defect_qty": ("缺陷数量", "件"),
    "good_qty": ("合格数量", "件"),
    "good_qty + defect_qty": ("产量", "件"),
    "downtime_minutes": ("停机时长", "分钟"),
    "standard_yield_rate": ("良率", "%"),
    "available_qty": ("可用库存", "件"),
    "input_qty": ("投入数量", "件"),
    "frozen_qty": ("冻结数量", "件"),
    "safety_stock_qty": ("安全库存", "件"),
    "sample_qty": ("抽样数量", "件"),
    "plan_qty": ("计划数量", "件"),
    "actual_qty": ("实际数量", "件"),
    "produce_qty": ("产出数量", "件"),
    "output_qty": ("产出数量", "件"),
    "quantity": ("数量", "件"),
}


def metric_business_name(column: str) -> tuple:
    """把指标字段名转成可读的中文业务名称与单位。"""
    if column in METRIC_BUSINESS_MAP:
        return METRIC_BUSINESS_MAP[column]
    lower = column.lower()
    if lower.endswith("_qty") or lower.endswith("_count") or lower == "quantity":
        return (column.replace("_qty", "").replace("_count", ""), "件")
    if lower.endswith("_amount"):
        return (column.replace("_amount", ""), "元")
    if lower.endswith("_minutes"):
        return (column.replace("_minutes", ""), "分钟")
    if lower.endswith("_rate"):
        return (column.replace("_rate", ""), "%")
    return (column, "数量")

DIMENSION_BUSINESS_MAP = {
    "process_id": "工序",
    "process_code": "工序",
    "product_id": "产品",
    "product_code": "产品",
    "equipment_id": "设备",
    "equipment_code": "设备",
    "line_id": "产线",
    "line_code": "产线",
    "warehouse_code": "仓库",
    "defect_type": "缺陷类型",
    "inspection_result": "检验结果",
    "order_status": "工单状态",
    "equipment_status": "设备状态",
    "shift_code": "班次",
    "work_order_no": "工单编号",
    "inspection_no": "检验编号",
    "product_name": "产品",
    "process_name": "工序",
    "equipment_name": "设备",
    "line_name": "产线",
    "warehouse_name": "仓库",
}


def dimension_business_name(column: str) -> str:
    """把分组字段名转成可读的中文业务维度名。"""
    if column in DIMENSION_BUSINESS_MAP:
        return DIMENSION_BUSINESS_MAP[column]
    lower = column.lower()
    if lower.endswith("_no"):
        return "编号"
    if lower.endswith("_code"):
        return "代码"
    if lower.endswith("_name"):
        return "名称"
    if lower.endswith("_type"):
        return "类型"
    if lower.endswith("_status"):
        return "状态"
    if lower.endswith("_category"):
        return "类别"
    return column


# ========== 获取所有表 ==========

@router.get("/")
def get_all_tables(db: Session = Depends(get_db)):
    """获取数据库中所有表及其字段信息"""
    inspector = inspect(db.get_bind())
    tables_info = []

    for table_name in inspector.get_table_names():
        # 跳过系统表
        if table_name.startswith("_") or table_name.startswith("pg_"):
            continue

        # 获取主键列名集合
        pk_constraint = inspector.get_pk_constraint(table_name)
        pk_columns = set(pk_constraint.get("constrained_columns", []))

        columns = []
        for column in inspector.get_columns(table_name):
            columns.append({
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column.get("nullable", True),
                "default": str(column.get("default", "")) if column.get("default") else "",
                "comment": column.get("comment", "") or "",
                "primary_key": column["name"] in pk_columns,
            })

        tables_info.append({
            "table_name": table_name,
            "columns": columns,
            "row_count": get_row_count(db, table_name),
        })

    return {"tables": tables_info}


# ========== 获取行数 ==========

def get_row_count(db: Session, table_name: str) -> int:
    """获取表的行数"""
    try:
        result = db.execute(text(f'SELECT COUNT(*) FROM {quote_ident(table_name)}'))
        return result.scalar()
    except Exception:
        return 0


# ========== 更新字段备注 ==========

@router.patch("/tables/{table_name}/columns/{column_name}/comment")
def update_column_comment(
    table_name: str,
    column_name: str,
    data: CommentUpdate,
    db: Session = Depends(get_db)
):
    """
    更新数据表字段的备注（PostgreSQL）
    """
    try:
        # 先验证字段是否存在
        inspector = inspect(db.get_bind())
        columns = inspector.get_columns(table_name)
        column_names = [col["name"] for col in columns]
        
        if column_name not in column_names:
            raise HTTPException(status_code=404, detail=f"字段 '{column_name}' 不存在于表 '{table_name}' 中")
        
        # 更新字段注释（PostgreSQL / MySQL 各自语法）
        from database import get_db_type
        if get_db_type() == "mysql":
            comment_sql = text(
                f'ALTER TABLE {quote_ident(table_name)} MODIFY COLUMN {quote_ident(column_name)} '
                f'{_column_type_for_mysql(db, table_name, column_name)} COMMENT :comment'
            )
        else:
            comment_sql = text(f'COMMENT ON COLUMN {quote_ident(table_name)}.{quote_ident(column_name)} IS :comment')
        db.execute(comment_sql, {"comment": data.comment})
        db.commit()
        
        return {"success": True, "comment": data.comment}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新备注失败: {str(e)}")


# ========== 更新样例数据单元格 ==========

@router.patch("/data/update")
def update_cell(
    req: UpdateCellRequest,
    db: Session = Depends(get_db)
):
    """
    更新数据表中某个单元格的值（支持双击编辑样例数据）
    """
    try:
        table_name = req.table_name
        column_name = req.column_name
        id_column = req.id_column
        row_id = req.row_id
        new_value = req.new_value

        # 获取表结构信息，判断字段类型
        inspector = inspect(db.get_bind())
        columns = inspector.get_columns(table_name)
        
        # 找到目标列的类型
        col_type = None
        col_nullable = True
        for col in columns:
            if col["name"] == column_name:
                col_type = str(col["type"]).upper()
                col_nullable = col.get("nullable", True)
                break
        
        if col_type is None:
            raise HTTPException(status_code=404, detail=f"字段 '{column_name}' 不存在")

        # 根据类型格式化值
        if new_value is None or new_value == '':
            if not col_nullable:
                # 如果字段不允许为空，空值转为空字符串（数字类型转为0）
                if 'INT' in col_type or 'NUMERIC' in col_type or 'DECIMAL' in col_type:
                    formatted_value = '0'
                elif 'BOOL' in col_type:
                    formatted_value = 'false'
                else:
                    formatted_value = "''"
            else:
                formatted_value = 'NULL'
        elif 'INT' in col_type or 'NUMERIC' in col_type or 'DECIMAL' in col_type:
            # 数字类型
            try:
                formatted_value = str(float(new_value)) if '.' in str(new_value) else str(int(float(new_value)))
            except ValueError:
                formatted_value = '0'
        elif 'BOOL' in col_type:
            # 布尔类型
            val_str = str(new_value).lower()
            formatted_value = 'true' if val_str in ('true', 't', '1', 'yes', 'y') else 'false'
        elif 'DATE' in col_type or 'TIMESTAMP' in col_type:
            # 日期时间类型，加引号
            escaped = str(new_value).replace("'", "''")
            formatted_value = f"'{escaped}'"
        else:
            # 字符串类型，转义单引号
            escaped = str(new_value).replace("'", "''")
            formatted_value = f"'{escaped}'"
        
        # 构建 UPDATE SQL（表名/字段名按数据库类型加引号）
        sql = text(f"""
            UPDATE {quote_ident(table_name)} 
            SET {quote_ident(column_name)} = {formatted_value}
            WHERE {quote_ident(id_column)} = :row_id
        """)
        
        db.execute(sql, {"row_id": row_id})
        db.commit()
        
        # 返回更新后的值（便于前端同步）
        return {"success": True, "message": "更新成功", "new_value": new_value}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"更新失败: {str(e)}")


# ========== 总览数据 ==========

@router.get("/overview")
def get_overview(db: Session = Depends(get_db)):
    """获取总览页统计数据"""
    inspector = inspect(db.get_bind())
    
    # 1. 数据表总数（排除系统表）
    all_tables = [t for t in inspector.get_table_names() if not t.startswith("_") and not t.startswith("pg_")]
    table_count = len(all_tables)
    
    # 2. 字段总数
    total_columns = 0
    for table_name in all_tables:
        columns = inspector.get_columns(table_name)
        total_columns += len(columns)
    
    # 3. 总数据行数
    total_rows = 0
    for table_name in all_tables:
        try:
            result = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
            total_rows += result.scalar() or 0
        except Exception:
            pass
    
    # 4. 表间关系数量
    relationship_count = 0
    try:
        result = db.execute(text('SELECT COUNT(*) FROM metadata_relationships'))
        relationship_count = result.scalar() or 0
    except Exception:
        try:
            result = db.execute(text("""
                SELECT COUNT(*) 
                FROM information_schema.table_constraints 
                WHERE constraint_type = 'FOREIGN KEY'
            """))
            relationship_count = result.scalar() or 0
        except Exception:
            relationship_count = 0
    
    # 5. 分析主题数量：按当前数据库动态推导
    topic_count = len(get_dynamic_topics(db, inspector))
    
    # 6. 各业务场景的数据统计
    work_order_count = 0
    try:
        result = db.execute(text('SELECT COUNT(*) FROM mes_work_order'))
        work_order_count = result.scalar() or 0
    except Exception:
        pass
    
    inspection_count = 0
    try:
        result = db.execute(text('SELECT COUNT(*) FROM qms_inspection'))
        inspection_count = result.scalar() or 0
    except Exception:
        pass
    
    equipment_count = 0
    downtime_count = 0
    try:
        result = db.execute(text('SELECT COUNT(*) FROM dim_equipment'))
        equipment_count = result.scalar() or 0
        result = db.execute(text('SELECT COUNT(*) FROM eqp_downtime_record'))
        downtime_count = result.scalar() or 0
    except Exception:
        pass
    
    inventory_count = 0
    try:
        result = db.execute(text('SELECT COUNT(*) FROM inv_inventory_snapshot'))
        inventory_count = result.scalar() or 0
    except Exception:
        pass
    
    # 6. 设备状态分布
    equipment_status_dist = {}
    try:
        result = db.execute(text("""
            SELECT equipment_status, COUNT(*) 
            FROM dim_equipment 
            GROUP BY equipment_status
        """))
        for row in result:
            equipment_status_dist[row[0]] = row[1]
    except Exception:
        pass
    
    # 7. 最近7天产量趋势
    production_trend = []
    try:
        result = db.execute(text("""
            SELECT stat_date, 
                   SUM(good_qty + defect_qty) as total_output,
                   SUM(good_qty) as good_qty,
                   SUM(defect_qty) as defect_qty
            FROM mes_process_output
            WHERE stat_date >= CURRENT_DATE - INTERVAL '6 days'
            GROUP BY stat_date
            ORDER BY stat_date
        """))
        for row in result:
            production_trend.append({
                "date": str(row[0]),
                "total_output": row[1] or 0,
                "good_qty": row[2] or 0,
                "defect_qty": row[3] or 0
            })
    except Exception:
        pass
    
    # 8. 工单状态分布
    order_status_dist = {}
    try:
        result = db.execute(text("""
            SELECT order_status, COUNT(*) 
            FROM mes_work_order 
            GROUP BY order_status
        """))
        for row in result:
            order_status_dist[row[0]] = row[1]
    except Exception:
        pass
    
    # 9. 最近库存预警
    low_stock_products = []
    try:
        result = db.execute(text("""
            SELECT p.product_name, p.product_code, 
                   i.available_qty, i.safety_stock_qty,
                   (i.safety_stock_qty - i.available_qty) as shortage_qty
            FROM inv_inventory_snapshot i
            JOIN dim_product p ON i.product_id = p.product_id
            WHERE i.available_qty < i.safety_stock_qty
              AND i.snapshot_date = (
                  SELECT MAX(snapshot_date) FROM inv_inventory_snapshot
              )
            ORDER BY shortage_qty DESC
            LIMIT 5
        """))
        for row in result:
            low_stock_products.append({
                "product_name": row[0],
                "product_code": row[1],
                "available_qty": row[2] or 0,
                "safety_stock_qty": row[3] or 0,
                "shortage_qty": row[4] or 0
            })
    except Exception:
        pass
    
    return {
        "data": {
            "table_count": table_count,
            "total_columns": total_columns,
            "total_rows": total_rows,
            "relationship_count": relationship_count,
            "topic_count": topic_count,
            "work_order_count": work_order_count,
            "inspection_count": inspection_count,
            "equipment_count": equipment_count,
            "downtime_count": downtime_count,
            "inventory_count": inventory_count,
            "equipment_status_dist": equipment_status_dist,
            "order_status_dist": order_status_dist,
            "production_trend": production_trend,
            "low_stock_products": low_stock_products
        }
    }
# ========== 获取表间关系 ==========

@router.get("/attention-points")
def get_attention_points(db: Session = Depends(get_db)):
    """基于当前数据库的真实数据计算，动态诊断数据中存在的潜在问题，随连接的数据库变化而刷新。"""
    inspector = inspect(db.get_bind())
    points = []
    tables = [
        t for t in inspector.get_table_names()
        if not t.startswith(("_", "pg_", "metadata_"))
    ]
    schema = {t: inspector.get_columns(t) for t in tables}

    numeric_types = ("INT", "NUMERIC", "DECIMAL", "REAL", "DOUBLE", "FLOAT", "MONEY")
    numeric_fields = [
        (t, c["name"], str(c["type"]).upper())
        for t, cols in schema.items()
        for c in cols
        if any(x in str(c["type"]).upper() for x in numeric_types)
    ]
    time_fields = [
        (t, c["name"])
        for t, cols in schema.items()
        for c in cols
        if any(x in c["name"].lower() for x in ("date", "time", "day", "month"))
    ]
    text_fields = [
        (t, c["name"])
        for t, cols in schema.items()
        for c in cols
        if any(x in c["name"].lower() for x in ("name", "type", "category", "status", "code", "no"))
        or c["name"].lower().endswith("_id")
    ]

    quote = quote_ident

    metric_priority = ("qty", "amount", "count", "total", "defect", "downtime", "数量", "金额", "停机", "rate", "ratio")
    used_tables = set()
    tones = ["red", "orange", "amber", "cyan"]

    # 明确不作为业务指标的字段：主键 / 外键 / 序号 / 排序 / 版本等
    non_metric_tokens = ("_id", "_seq", "_no", "_order", "_sort", "_version", "_status_code")

    def is_metric_column(name: str) -> bool:
        lower = name.lower()
        if lower == "id" or any(lower.endswith(tok) for tok in non_metric_tokens):
            return False
        if lower in ("seq", "sequence", "ordinal", "sort_order", "version"):
            return False
        return True

    def pick_metric(table: str):
        cols = [c for t, c, _ in numeric_fields if t == table]
        business_cols = [c for c in cols if is_metric_column(c)]
        if not business_cols:
            return None
        return next((c for c in business_cols if any(w in c.lower() for w in metric_priority)), business_cols[0])

    def pick_group(table: str):
        group_candidates = [f for f in text_fields if f[0] == table]
        readable_candidates = [f for f in group_candidates if any(
            x in f[1].lower() for x in ("name", "type", "category", "status", "code", "no", "名称", "类型", "类别", "状态", "编号")
        ) and not f[1].lower().endswith("_id")]
        group_source = readable_candidates if readable_candidates else [f for f in group_candidates if not f[1].lower().endswith("_id")]
        if not group_source:
            group_source = group_candidates
        return group_source[0][1] if group_source else None

    # 各类诊断的配额：趋势 2 条、分布 2 条、质量 1 条、安全线 1 条、异常占比 2 条
    kind_quota = {"trend": 2, "volatility": 2, "concentration": 2, "imbalance": 2, "quality": 1, "safety": 1, "abnormal": 2}
    kind_count = {}

    def add_point(kind, table, tone, icon, title, detail, value, unit, rule, question):
        if len(points) >= 6:
            return False
        if kind_count.get(kind, 0) >= kind_quota.get(kind, 0):
            return False
        kind_count[kind] = kind_count.get(kind, 0) + 1
        points.append({
            "id": f"{kind}-{table}-{len(points)}",
            "category": table,
            "icon": icon,
            "tone": tone,
            "title": title,
            "detail": detail,
            "value": value,
            "unit": unit,
            "rule": rule,
            "question": question,
        })
        return True

    # ---------- 规则 1：时间趋势诊断（近期骤升 / 骤降 / 大幅波动） ----------
    quote = quote_ident
    for table, time_column in time_fields:
        if len(points) >= 6 or kind_count.get("trend", 0) + kind_count.get("volatility", 0) >= 2:
            break
        if table in used_tables:
            continue
        metric = pick_metric(table)
        if not metric:
            continue
        metric_business, metric_unit = metric_business_name(metric)
        try:
            rows = db.execute(text(
                f"SELECT {quote(time_column)}, SUM({quote(metric)}) AS value "
                f"FROM {quote(table)} GROUP BY {quote(time_column)} "
                f"ORDER BY {quote(time_column)}"
            )).fetchall()
            if len(rows) < 4:
                continue
            values = [float(r[1] or 0) for r in rows]
            if sum(values) == 0:
                continue
            overall_avg = sum(values) / len(values)
            recent = values[-3:]
            recent_avg = sum(recent) / len(recent)
            cv = statistics.pstdev(values) / overall_avg if overall_avg else 0
            if recent_avg > overall_avg * 1.25:
                if add_point(
                    "trend", table, "red", "📈",
                    f"{metric_business}近期骤升",
                    f"最近{len(recent)}个周期的{metric_business}均值为 {recent_avg:,.0f} {metric_unit}，较整体均值 {overall_avg:,.0f} {metric_unit} 上升 {((recent_avg / overall_avg) - 1) * 100:.0f}%，增长异常，需排查原因。",
                    round(recent_avg, 2), metric_unit,
                    f"对比最近{len(recent)}期与整体均值的{metric_business}，上升超过 25% 判定为骤升",
                    f"分析{metric_business}近期骤升的原因",
                ):
                    used_tables.add(table)
            elif recent_avg < overall_avg * 0.75:
                if add_point(
                    "trend", table, "orange", "📉",
                    f"{metric_business}近期骤降",
                    f"最近{len(recent)}个周期的{metric_business}均值为 {recent_avg:,.0f} {metric_unit}，较整体均值 {overall_avg:,.0f} {metric_unit} 下降 {((1 - recent_avg / overall_avg)) * 100:.0f}%，下滑明显，需排查原因。",
                    round(recent_avg, 2), metric_unit,
                    f"对比最近{len(recent)}期与整体均值的{metric_business}，下降超过 25% 判定为骤降",
                    f"分析{metric_business}近期骤降的原因",
                ):
                    used_tables.add(table)
            elif cv > 0.8:
                if add_point(
                    "volatility", table, "amber", "🎢",
                    f"{metric_business}波动剧烈",
                    f"{metric_business}的变异系数达到 {cv:.1f}，各周期数值波动很大，运行稳定性较差。",
                    round(cv, 2), "",
                    f"变异系数 = 标准差 / 均值，超过 0.8 判定为波动剧烈",
                    f"分析{metric_business}波动剧烈的原因",
                ):
                    used_tables.add(table)
        except Exception as e:
            print(f"趋势诊断 {table} 失败: {e}")

    # ---------- 规则 2：分布集中诊断（指标高度集中于单一分组 / 分组间差距悬殊） ----------
    for table in tables:
        if len(points) >= 6 or kind_count.get("concentration", 0) + kind_count.get("imbalance", 0) >= 2:
            break
        if table in used_tables:
            continue
        column = pick_metric(table)
        if not column:
            continue
        group_column = pick_group(table)
        if not group_column or group_column == column:
            continue
        metric_business, metric_unit = metric_business_name(column)
        dimension_business = dimension_business_name(group_column)
        label_map = build_dimension_label_map(db, inspector, group_column)
        try:
            rows = db.execute(text(
                f"SELECT {quote(group_column)}, SUM({quote(column)}) AS value "
                f"FROM {quote(table)} GROUP BY {quote(group_column)} "
                "ORDER BY value DESC"
            )).fetchall()
            if len(rows) < 3:
                continue
            total = sum(float(r[1] or 0) for r in rows)
            if total <= 0:
                continue
            top = float(rows[0][1] or 0)
            top_label = label_map.get(str(rows[0][0]), str(rows[0][0]))
            share = top / total * 100
            min_val = float(rows[-1][1] or 0)
            ratio = (top / min_val) if min_val > 0 else 0
            if share >= 50:
                if add_point(
                    "concentration", table, "orange", "⚖️",
                    f"{metric_business}高度集中",
                    f"{metric_business}中 {top_label} 占比高达 {share:.0f}%（共 {len(rows)} 个{dimension_business}），高度集中，一旦异常影响面大。",
                    round(share, 1), "%",
                    f"按{dimension_business}汇总{metric_business}，最高分组占比 ≥ 50% 判定为高度集中",
                    f"分析{metric_business}为何高度集中在{top_label}",
                ):
                    used_tables.add(table)
            elif ratio >= 8:
                if add_point(
                    "imbalance", table, "amber", "🔀",
                    f"{metric_business}分布失衡",
                    f"{metric_business}最高的{top_label}与最低分组相差约 {ratio:.0f} 倍，各{dimension_business}间差距悬殊。",
                    round(ratio, 1), "倍",
                    f"按{dimension_business}汇总{metric_business}，最高/最低 ≥ 8 倍判定为失衡",
                    f"分析各{dimension_business}的{metric_business}差距为何悬殊",
                ):
                    used_tables.add(table)
        except Exception as e:
            print(f"分布诊断 {table} 失败: {e}")

    # ---------- 规则 3：数据质量诊断（零值 / 空值占比过高） ----------
    for table, column, _ in numeric_fields:
        if len(points) >= 6 or kind_count.get("quality", 0) >= 1:
            break
        if table in used_tables or not is_metric_column(column):
            continue
        metric_business, _ = metric_business_name(column)
        try:
            total_row = db.execute(text(f'SELECT COUNT(*) FROM {quote(table)}')).scalar() or 0
            if total_row == 0:
                continue
            zero_count = db.execute(text(
                f'SELECT COUNT(*) FROM {quote(table)} WHERE {quote(column)} = 0 OR {quote(column)} IS NULL'
            )).scalar() or 0
            zero_share = zero_count / total_row * 100
            if zero_share >= 30:
                if add_point(
                    "quality", table, "amber", "⚠️",
                    f"{metric_business}数据缺失偏高",
                    f"{table} 中 {metric_business} 存在 {zero_share:.0f}% 的零值或空值（{zero_count} 条），数据可能未完整采集。",
                    round(zero_share, 1), "%",
                    f"统计 {metric_business} 为零或空的记录占比，≥ 30% 判定为数据缺失",
                    f"检查{metric_business}缺失数据的原因",
                ):
                    used_tables.add(table)
        except Exception as e:
            print(f"质量诊断 {table} 失败: {e}")

    # ---------- 规则 4：安全线诊断（可用量低于安全库存） ----------
    safety_pairs = []
    for table, cols in schema.items():
        col_names = {c["name"] for c in cols}
        for avail in ("available_qty", "available", "stock_qty", "qty_available"):
            for safe in ("safety_stock_qty", "safety_stock", "min_stock", "safe_stock"):
                if avail in col_names and safe in col_names:
                    safety_pairs.append((table, avail, safe))
                    break
            else:
                continue
            break
    for table, avail_col, safe_col in safety_pairs:
        if len(points) >= 6 or kind_count.get("safety", 0) >= 1:
            break
        if table in used_tables:
            continue
        avail_business, avail_unit = metric_business_name(avail_col)
        try:
            rows = db.execute(text(
                f"SELECT {quote(avail_col)}, {quote(safe_col)} FROM {quote(table)}"
            )).fetchall()
            low = [(float(r[0] or 0), float(r[1] or 0)) for r in rows if r[0] is not None and r[1] is not None and float(r[0]) < float(r[1])]
            if low:
                worst = min(low, key=lambda x: x[0] - x[1])
                add_point(
                    "safety", table, "red", "🛑",
                    "库存低于安全线",
                    f"存在 {len(low)} 条{avail_business}低于安全库存的记录，最严重的一条 {avail_business} {worst[0]:,.0f} {avail_unit} < 安全线 {worst[1]:,.0f} {avail_unit}，存在断供风险。",
                    round(worst[0], 2), avail_unit,
                    f"逐条检查 {avail_col} < {safe_col} 的记录，存在即告警",
                    "分析库存低于安全线的物料和原因",
                )
                used_tables.add(table)
        except Exception as e:
            print(f"安全线诊断 {table} 失败: {e}")

    # ---------- 规则 5：异常占比诊断（状态/结果类字段中异常值占比过高） ----------
    # 例如 inspection_result 中 fail 占比高、status 中异常状态占比高等
    abnormal_tokens = ("fail", "ng", "error", "abnormal", "reject", "不合格", "异常", "故障", "停机", "报警")
    status_like = ("result", "status", "state", "mark", "flag", "type", "code")
    for table, cols in schema.items():
        if len(points) >= 6 or kind_count.get("abnormal", 0) >= 2:
            break
        if table in used_tables:
            continue
        for col in cols:
            col_name = col["name"]
            lower_name = col_name.lower()
            col_type = str(col["type"]).upper()
            # 只看文本/枚举类字段（非时间、非大文本）
            if not any(tok in col_type for tok in ("CHAR", "TEXT", "VARCHAR", "ENUM")):
                continue
            if not any(tok in lower_name for tok in status_like):
                continue
            try:
                rows = db.execute(text(
                    f"SELECT {quote(col_name)}, COUNT(*) FROM {quote(table)} GROUP BY {quote(col_name)}"
                )).fetchall()
                total = sum(int(r[1] or 0) for r in rows)
                if total < 20:
                    continue
                bad = sum(
                    int(r[1] or 0) for r in rows
                    if any(tok in str(r[0]).lower() for tok in abnormal_tokens)
                )
                bad_share = bad / total * 100
                if bad_share >= 25:
                    col_business = dimension_business_name(col_name)
                    add_point(
                        "abnormal", table, "red", "🚨",
                        f"{col_business}异常占比偏高",
                        f"{table} 的{col_business}中，异常/不合格记录占 {bad_share:.0f}%（{bad}/{total} 条），异常比例偏高，需重点关注。",
                        round(bad_share, 1), "%",
                        f"统计 {col_name} 中异常值记录占比，≥ 25% 判定为异常偏高",
                        f"分析{table}异常占比偏高的原因",
                    )
                    used_tables.add(table)
                    break
            except Exception as e:
                print(f"异常占比诊断 {table}.{col_name} 失败: {e}")

    # ---------- 兜底：没有发现显著问题时的中性提示 ----------
    if not points:
        points.append({
            "id": "no-points",
            "category": "数据底座",
            "icon": "✅",
            "tone": "cyan",
            "title": "暂未发现明显异常",
            "detail": "对当前数据库的趋势、分布、数据完整性与安全线进行诊断后，未发现需要优先关注的显著问题。",
            "value": 0,
            "unit": "",
            "rule": "检查了趋势、分布、数据完整性与安全线四类规则",
            "question": "查看当前数据库的整体数据概况",
        })

    return {"points": points}

@router.get("/relationships")
def get_table_relationships(db: Session = Depends(get_db)):
    """
    获取数据库中所有表间关系（外键关系 + 预定义业务关系）
    """
    inspector = inspect(db.get_bind())
    relationships = []
    table_labels = {}

    try:
        metadata_columns = {column["name"] for column in inspector.get_columns("metadata_tables")}
        if {"table_name", "table_chinese_name"}.issubset(metadata_columns):
            result = db.execute(text("SELECT table_name, table_chinese_name FROM metadata_tables"))
            table_labels = {row[0]: row[1] or row[0] for row in result}
    except Exception:
        pass
    
    # 1. 从 information_schema 获取外键关系
    try:
        # PostgreSQL 外键查询
        result = db.execute(text("""
            SELECT
                tc.table_name AS source_table,
                kcu.column_name AS source_column,
                ccu.table_name AS target_table,
                ccu.column_name AS target_column,
                tc.constraint_name AS constraint_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
            JOIN information_schema.constraint_column_usage ccu
                ON ccu.constraint_name = tc.constraint_name
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public'
            ORDER BY tc.table_name, kcu.ordinal_position
        """))
        
        for row in result:
            relationships.append({
    "source_table": row[0],
    "source_column": row[1],
    "target_table": row[2],
    "target_column": row[3],
    "type": "foreign_key",
    "constraint_name": row[4],
    "description": f"外键：{row[0]}.{row[1]} → {row[2]}.{row[3]}"
})
    except Exception as e:
        print(f"获取外键关系失败: {e}")
    
    # 2. 如果外键关系较少，补充预定义的业务关系
    if len(relationships) < 3:
        # 从 metadata_relationships 表读取
        try:
            result = db.execute(text("""
                SELECT from_table, from_field, to_table, to_field, relationship_type
                FROM metadata_relationships
                ORDER BY id
            """))
            for row in result:
                relationships.append({
                    "source_table": row[0],
                    "source_column": row[1],
                    "target_table": row[2],
                    "target_column": row[3],
                    "type": row[4] or "business",
                    "constraint_name": None,
                    "description": f"业务关系：{row[0]}.{row[1]} → {row[2]}.{row[3]}"
                })
        except Exception:
            pass
    
    table_names = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_"))
    ]

    # 对没有显式外键的数据库，基于同名 ID 字段补充低置信度的推导关系。
    known_pairs = {
        (r["source_table"], r["source_column"], r["target_table"], r["target_column"])
        for r in relationships
    }
    primary_keys = {
        table: set(inspector.get_pk_constraint(table).get("constrained_columns", []))
        for table in inspector.get_table_names()
        if not table.startswith(("_", "pg_"))
    }
    for source_table, source_columns in [(t, inspector.get_columns(t)) for t in table_names if t in locals()]:
        for source_column in source_columns:
            source_name = source_column["name"]
            if not (source_name.endswith("_id") or source_name == "id"):
                continue
            for target_table, target_columns in [(t, inspector.get_columns(t)) for t in primary_keys]:
                if source_table == target_table:
                    continue
                target_names = {column["name"] for column in target_columns}
                if source_name in target_names and source_name in primary_keys.get(target_table, set()):
                    pair = (source_table, source_name, target_table, source_name)
                    if pair not in known_pairs:
                        relationships.append({
                            "source_table": source_table,
                            "source_column": source_name,
                            "target_table": target_table,
                            "target_column": source_name,
                            "type": "inferred",
                            "constraint_name": None,
                            "description": f"推导关系：{source_table}.{source_name} → {target_table}.{source_name}",
                        })
                        known_pairs.add(pair)

    nodes = [
        {
            "id": table_name,
            "name": table_name,
            "label": table_labels.get(table_name, table_name),
            "columns": len(inspector.get_columns(table_name)),
            "connected": any(
                relation["source_table"] == table_name or relation["target_table"] == table_name
                for relation in relationships
            ),
        }
        for table_name in table_names
    ]

    return {"nodes": nodes, "relationships": relationships}


# ========== 获取单个表详情 ==========

# ========== 获取分析主题列表 ==========

@router.get("/analysis-examples")
def get_analysis_examples(db: Session = Depends(get_db)):
    """根据当前数据库生成快捷提问，且只保留点击后能直接产出结果的问题。"""
    inspector = inspect(db.get_bind())
    candidate_questions = [
        "各工序的缺陷数量如何？",
        "各工序的良率如何？",
        "各工序的产量如何？",
        "设备的停机时长如何？",
        "库存的可用数量如何？",
        "缺陷数量的变化趋势如何？",
        "产量的变化趋势如何？",
    ]
    examples = []
    for question in candidate_questions:
        result = _run_analysis(db, inspector, question)
        payload = result.get("result", {})
        # 只有能真实产出数据的才保留；跳过需要澄清、缺少字段、分析失败的情况
        if payload.get("series"):
            examples.append({
                "id": payload.get("id", "example"),
                "question": question,
                "title": payload.get("title", "分析结果"),
                "unit": payload.get("unit", "分析值"),
                "unit_label": payload.get("unit_label", ""),
                "chart_type": payload.get("chart_type", "bar"),
                "series": payload.get("series", []),
            })
    return {"examples": examples}


def _run_analysis(db, inspector, question: str) -> dict:
    """根据当前数据库结构执行可解释的基础自然语言分析。"""
    tables = [t for t in inspector.get_table_names() if not t.startswith(("_", "pg_"))]
    schema = {t: inspector.get_columns(t) for t in tables}
    all_columns = [(t, c["name"], str(c["type"]).upper()) for t in tables for c in schema[t]]

    numeric_types = ("INT", "NUMERIC", "DECIMAL", "REAL", "DOUBLE", "FLOAT", "MONEY")
    numeric = [(t, c, typ) for t, c, typ in all_columns if any(x in typ for x in numeric_types)]
    time_fields = [
        (t, c, typ) for t, c, typ in all_columns
        if any(word in c.lower() for word in ("date", "time", "day", "month", "year", "日期", "时间"))
    ]
    text_fields = [
        (t, c, typ)
        for t, c, typ in all_columns
        if any(x in c.lower() for x in ("name", "type", "category", "status", "code"))
        or c.lower().endswith("_id")
    ]
    keywords = question.lower()

    if not numeric:
        return {"result": {
            "id": "schema-overview", "question": question, "title": "当前数据库暂缺可聚合数值字段",
            "unit": "结果", "series": [], "explanation": "请提供包含数值字段的表后再进行统计分析。"
        }}

    intent_terms = {
        "产量": ("output", "good_qty", "input_qty", "产量", "产出"),
        "生产": ("output", "production", "process", "产量", "工序"),
        "不良": ("defect", "fail", "不良", "缺陷"),
        "质量": ("quality", "inspection", "defect", "质量", "检验"),
        "良率": ("good", "yield", "良率", "合格"),
        "停机": ("downtime", "minutes", "停机"),
        "设备": ("equipment", "machine", "设备"),
        "库存": ("inventory", "stock", "available", "库存"),
        "金额": ("amount", "price", "cost", "金额", "费用"),
    }
    question_terms = [term for key, terms in intent_terms.items() if key in keywords for term in terms]
    if "工序" in keywords:
        question_terms.extend(("process", "工序"))
    if "产线" in keywords or "生产线" in keywords:
        question_terms.extend(("line", "产线"))
    if "产品" in keywords:
        question_terms.extend(("product", "产品"))
    if "设备" in keywords:
        question_terms.extend(("equipment", "设备"))

    intent_names = []
    if any(word in keywords for word in ("产量", "产出", "生产", "工序")):
        intent_names.append("生产产出")
    if any(word in keywords for word in ("不良", "缺陷", "质量", "检验", "良率")):
        intent_names.append("质量表现")
    if any(word in keywords for word in ("设备", "停机", "报警", "运行")):
        intent_names.append("设备运行")
    if any(word in keywords for word in ("库存", "物料", "仓库", "安全库存")):
        intent_names.append("库存水位")
    if any(word in keywords for word in ("金额", "费用", "成本", "收入", "利润")):
        intent_names.append("金额统计")
    if any(word in keywords for word in ("趋势", "变化", "时间", "最近", "周期")):
        intent_names.append("趋势变化")

    if not intent_names:
        return {"result": {
            "id": "need-clarification", "question": question, "title": "还需要明确分析目标",
            "unit": "待确认", "series": [],
            "explanation": "我没有找到与当前数据库字段明确对应的业务意图，因此不会强行选择字段生成图表。请说明要分析的指标、对象或时间范围，例如“分析库存数量”“查看各工序不良数量”。",
            "analysis": {
                "intent": "未识别",
                "source_tables": [],
                "fields": [],
                "calculation": "未执行",
                "grouping": "未执行",
                "limitation": "问题缺少可匹配的分析目标。"
            }
        }}

    if any(word in keywords for word in ("趋势", "变化", "时间", "最近", "周期")) and not any(
        word in keywords for word in ("产量", "产出", "不良", "缺陷", "良率", "停机", "设备", "库存", "金额", "数量", "比例")
    ):
        return {"result": {
            "id": "need-metric", "question": question, "title": "趋势分析还缺少指标",
            "unit": "待确认", "series": [],
            "explanation": "你描述了时间变化，但没有说明要观察什么指标。请补充“产量、不良数量、良率、停机时长、库存数量”等指标。",
            "analysis": {
                "intent": "趋势变化",
                "source_tables": [], "fields": [], "calculation": "未执行",
                "grouping": "未执行", "limitation": "缺少要观察的业务指标。"
            }
        }}

    if any(word in keywords for word in ("趋势", "变化", "时间", "最近", "周期")) and not time_fields:
        return {"result": {
            "id": "missing-time-field", "question": question, "title": "当前数据库缺少时间字段",
            "unit": "无法生成趋势", "series": [],
            "explanation": "这个问题要求按时间观察变化，但当前数据库没有识别到日期或时间字段，因此不能生成趋势图。",
            "analysis": {
                "intent": "、".join(intent_names),
                "source_tables": [],
                "fields": [],
                "calculation": "未执行",
                "grouping": "按时间分组（不可用）",
                "limitation": "当前数据库没有可用的日期/时间字段。"
            }
        }}

    def score(item):
        table, column, _ = item
        table_text = table.lower()
        column_text = column.lower()
        base_score = sum(
            3 if term.lower() in column_text else 1 if term.lower() in table_text else 0
            for term in question_terms
        )
        if column_text.endswith("_id") or column_text == "id":
            base_score -= 0.5
        return base_score

    quality_requested = any(word in keywords for word in ("不良", "缺陷", "检验结果", "问题分布"))
    if quality_requested:
        quality_candidates = [
            item for item in numeric
            if any(word in f"{item[0]} {item[1]}".lower() for word in ("defect", "fail", "inspection", "quality", "不良", "缺陷", "检验"))
        ]
        preferred = sorted(quality_candidates or numeric, key=score, reverse=True)
    else:
        preferred = sorted(numeric, key=score, reverse=True)
    value_table, value_column, _ = preferred[0]

    # 对常见制造业问题使用已确认存在的字段表达式，避免把 output_id/input_qty 当作产量。
    if "产量" in keywords or "产出" in keywords:
        production_fields = {column for table, column, _ in numeric if table == value_table}
        if {"good_qty", "defect_qty"}.issubset(production_fields):
            value_column = "good_qty + defect_qty"
        elif "output_qty" in production_fields:
            value_column = "output_qty"
    elif "不良" in keywords or "缺陷" in keywords:
        defect_fields = {column for table, column, _ in numeric if table == value_table}
        if "defect_qty" in defect_fields:
            value_column = "defect_qty"
    elif "停机" in keywords:
        downtime_fields = {column for table, column, _ in numeric if table == value_table}
        if "downtime_minutes" in downtime_fields:
            value_column = "downtime_minutes"
    elif "良率" in keywords:
        yield_fields = {column for table, column, _ in numeric if table == value_table}
        if "standard_yield_rate" in yield_fields:
            value_column = "standard_yield_rate"
        elif {"good_qty", "defect_qty"}.issubset(yield_fields):
            value_column = "good_qty"
    group_candidates = [item for item in text_fields if item[0] == value_table and item[1] != value_column]
    if not group_candidates:
        group_candidates = text_fields
    if not group_candidates:
        return {"result": {
            "id": "numeric-summary", "question": question, "title": f"{value_table}.{value_column} 汇总",
            "unit": value_column, "series": [{"label": value_table, "value": 0}],
            "explanation": "当前数据库没有可用于分组展示的文本字段。"
        }}

    def group_score(item):
        table, column, _ = item
        text_value = f"{table} {column}".lower()
        preferred_words = ("process", "line", "product", "equipment", "warehouse", "category", "name", "status", "code", "工序", "产线", "产品", "设备", "仓库", "类别", "名称")
        result = sum(1 for word in preferred_words if word in text_value) + score((table, column, ""))
        if "工序" in keywords and "process" in column:
            result += 10
        if "产线" in keywords and "line" in column:
            result += 10
        if "设备" in keywords and "equipment" in column:
            result += 10
        if "停机" in keywords and column == "equipment_id":
            result += 10
        if "产品" in keywords and "product" in column:
            result += 10
        if quality_requested and column in ("defect_type", "defect_code", "inspection_result", "process_id", "responsible_process_id"):
            result += 20
        if quality_requested and column in ("shift_code", "output_id"):
            result -= 10
        if column in ("output_id", "inspection_id", "snapshot_id", "downtime_id"):
            result -= 10
        return result

    group_table, group_column, _ = sorted(group_candidates, key=group_score, reverse=True)[0]
    quote = quote_ident

    # 业务化翻译：指标名、单位、分组维度中文名、编码值 -> 中文名
    metric_business, metric_unit = metric_business_name(value_column)
    dimension_business = dimension_business_name(group_column)
    label_map = build_dimension_label_map(db, inspector, group_column)
    is_trend = any(word in keywords for word in ("趋势", "变化", "时间", "最近", "周期"))

    safe_value_expression = value_column if " + " in value_column else quote(value_column)
    aggregate_function = "AVG" if value_column == "standard_yield_rate" else "SUM"
    is_yield = aggregate_function == "AVG" and value_column == "standard_yield_rate"

    # 趋势类问题：优先按时间维度生成折线趋势图
    if is_trend:
        time_field = None
        for column_info in schema.get(value_table, []):
            column_name = column_info["name"].lower()
            if any(word in column_name for word in ("date", "time", "day", "month")):
                time_field = column_info["name"]
                break
        if time_field:
            trend_query = text(
                f"SELECT {quote(time_field)}, {aggregate_function}({safe_value_expression}) AS value "
                f"FROM {quote(value_table)} GROUP BY {quote(time_field)} "
                f"ORDER BY {quote(time_field)}"
            )
            try:
                trend_rows = db.execute(trend_query)
                trend_series = []
                for row in trend_rows:
                    raw_value = float(row[1] or 0)
                    display_value = round(raw_value * 100, 2) if is_yield else round(raw_value, 2)
                    trend_series.append({
                        "label": str(row[0])[:10],
                        "value": display_value,
                    })
                return {"result": {
                    "id": "trend-analysis", "chart_type": "trend",
                    "question": question,
                    "title": f"{metric_business}变化趋势",
                    "unit": metric_business, "unit_label": metric_unit,
                    "series": trend_series,
                    "explanation": f"按时间统计{metric_business}的变化趋势。",
                    "analysis": {
                        "metric": metric_business,
                        "dimension": "时间",
                        "unit_label": metric_unit,
                        "calculation": f"按日期统计{metric_business}",
                        "grouping": "按时间分组",
                        "limitation": "当前版本使用字段语义进行匹配，复杂问题后续由 Agent 进一步处理。"
                    }
                }}
            except Exception as exc:
                return {"result": {
                    "id": "analysis-error", "chart_type": "bar", "question": question,
                    "title": "暂时无法生成趋势图", "unit": "结果", "series": [],
                    "explanation": f"无法按时间统计：{exc}"
                }}

    query = text(
        f"SELECT {quote(group_column)}, {aggregate_function}({safe_value_expression}) AS value "
        f"FROM {quote(value_table)} GROUP BY {quote(group_column)} "
        "ORDER BY value DESC LIMIT 12"
    )
    try:
        rows = db.execute(query)
        series = []
        for row in rows:
            raw_value = float(row[1] or 0)
            display_value = round(raw_value * 100, 2) if is_yield else round(raw_value, 2)
            series.append({
                "label": label_map.get(str(row[0]), str(row[0])),
                "value": display_value,
            })
        title = f"各{dimension_business}{metric_business}对比"
        if aggregate_function == "AVG":
            calculation = f"各{dimension_business}{metric_business}取平均"
        else:
            calculation = f"各{dimension_business}{metric_business}求和"
        if value_column == "good_qty + defect_qty":
            calculation = "各工序产量 = 合格数量 + 不良数量"
        return {"result": {
            "id": "dynamic-analysis", "chart_type": "bar",
            "question": question, "title": title,
            "unit": metric_business, "unit_label": metric_unit, "series": series,
            "explanation": f"按{dimension_business}统计{metric_business}，并从高到低排列。",
            "analysis": {
                "intent": "、".join(intent_names),
                "source_tables": [value_table, group_table] if value_table != group_table else [value_table],
                "metric": metric_business,
                "dimension": dimension_business,
                "unit_label": metric_unit,
                "calculation": calculation,
                "grouping": f"按{dimension_business}分组",
                "limitation": "当前版本使用字段语义进行匹配，复杂问题后续由 Agent 进一步处理。"
            }
        }}
    except Exception as exc:
        return {"result": {
            "id": "analysis-error", "chart_type": "bar", "question": question,
            "title": "暂时无法完成这项分析",
            "unit": "结果", "series": [], "explanation": str(exc)
        }}


@router.post("/analyze")
def analyze_question(request: AnalysisRequest, db: Session = Depends(get_db)):
    """根据当前数据库结构执行可解释的基础自然语言分析。"""
    inspector = inspect(db.get_bind())
    return _run_analysis(db, inspector, request.question.strip())


@router.get("/topics")
def get_analysis_topics(db: Session = Depends(get_db)):
    """获取当前数据库动态推导出的分析主题。"""
    inspector = inspect(db.get_bind())
    return {"topics": get_dynamic_topics(db, inspector)}


@router.get("/{table_name}")
def get_table_detail(table_name: str, db: Session = Depends(get_db)):
    """获取单个表的详细信息和样例数据"""
    inspector = inspect(db.get_bind())

    # 获取主键列名集合
    pk_constraint = inspector.get_pk_constraint(table_name)
    pk_columns = set(pk_constraint.get("constrained_columns", []))

    columns = []
    for column in inspector.get_columns(table_name):
        columns.append({
            "name": column["name"],
            "type": str(column["type"]),
            "nullable": column.get("nullable", True),
            "comment": column.get("comment", "") or "",
            "primary_key": column["name"] in pk_columns,
        })

    # 获取前 100 条样例数据
    sample_data = []
    try:
        result = db.execute(text(f'SELECT * FROM {quote_ident(table_name)} LIMIT 100'))
        sample_data = [dict(row._mapping) for row in result]
    except Exception as e:
        print(f"获取样例数据失败: {e}")

    return {
        "table_name": table_name,
        "columns": columns,
        "sample_data": sample_data,
    }