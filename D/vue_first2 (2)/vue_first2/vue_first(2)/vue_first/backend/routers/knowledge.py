"""
业务知识 API —— 从数据库动态获取表信息，组织为业务知识结构。
将数据库中的真实表名、字段名映射为业务对象、指标等，供前端知识库页面使用。
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import inspect, text
from database import get_db
from typing import List, Dict, Optional

router = APIRouter(prefix="/api/knowledge", tags=["业务知识"])


# ========== 场景配置：表名前缀 → 场景映射 ==========
SCENE_TABLE_PREFIXES = {
    "production": {
        "key": "production",
        "icon": "🏭",
        "name": "生产分析",
        "desc": "产量趋势、工序良率、工单执行",
        "prefixes": ["mes_", "dim_product", "dim_process", "dim_production_line", "work_order", "output"],
    },
    "quality": {
        "key": "quality",
        "icon": "✅",
        "name": "质量分析",
        "desc": "缺陷类型、检验结果、不良分布",
        "prefixes": ["qms_", "defect", "inspection", "quality", "test"],
    },
    "equipment": {
        "key": "equipment",
        "icon": "⚙️",
        "name": "设备分析",
        "desc": "停机时长、设备状态、运行效率",
        "prefixes": ["eqp_", "dim_equipment", "downtime", "machine"],
    },
    "inventory": {
        "key": "inventory",
        "icon": "📦",
        "name": "库存分析",
        "desc": "库存水位、物料周转、安全库存",
        "prefixes": ["inv_", "stock", "inventory", "warehouse"],
    },
}


# ========== 表图标映射（根据表名匹配） ==========
TABLE_ICON_RULES = [
    {"pattern": "dim_product", "icon": "📦", "label": "产品"},
    {"pattern": "dim_process", "icon": "⚡", "label": "工序"},
    {"pattern": "dim_production_line", "icon": "🏗️", "label": "产线"},
    {"pattern": "dim_equipment", "icon": "⚙️", "label": "设备"},
    {"pattern": "mes_work_order", "icon": "📋", "label": "工单"},
    {"pattern": "mes_process_output", "icon": "📊", "label": "工序产出"},
    {"pattern": "qms_inspection", "icon": "🔬", "label": "检验"},
    {"pattern": "qms_defect_detail", "icon": "⚠️", "label": "不良明细"},
    {"pattern": "eqp_downtime_record", "icon": "⏸️", "label": "停机记录"},
    {"pattern": "inv_inventory_snapshot", "icon": "📸", "label": "库存快照"},
]


def _get_icon_and_label(table_name: str) -> tuple:
    """根据表名返回对应图标和中文标签"""
    table_lower = table_name.lower()
    for rule in TABLE_ICON_RULES:
        if rule["pattern"] in table_lower:
            return rule["icon"], rule["label"]
    return "📋", table_name.replace("_", " ").title()


def _generate_table_desc(table_name: str, columns: List[Dict]) -> str:
    """根据表名和字段自动生成描述"""
    desc_parts = []
    for col in columns[:5]:
        if col.get("comment"):
            desc_parts.append(col["comment"])
    if desc_parts:
        return f"数据表 {table_name}，包含 {len(columns)} 个字段：{', '.join(desc_parts[:3])}"
    name_parts = table_name.replace("_", " ").title()
    return f"{name_parts} 数据表，共 {len(columns)} 个字段"


def _get_core_tables(db: Session) -> set:
    """从数据库获取核心表（通过是否有外键关联来判断）"""
    inspector = inspect(db.get_bind())
    core_tables = set()
    all_tables = inspector.get_table_names()

    for table in all_tables:
        if table.startswith("_") or table.startswith("pg_"):
            continue
        try:
            fk = inspector.get_foreign_keys(table)
            if fk:
                core_tables.add(table)
        except Exception:
            pass
    return core_tables


def _classify_table(table_name: str) -> Optional[str]:
    """根据表名判断所属场景，返回场景 key 或 None"""
    table_lower = table_name.lower()
    for key, scene in SCENE_TABLE_PREFIXES.items():
        for prefix in scene["prefixes"]:
            if table_lower == prefix or table_lower.startswith(prefix):
                return key
    return None


def _row_count(db: Session, table_name: str) -> int:
    try:
        result = db.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return int(result.scalar() or 0)
    except Exception:
        return 0


def _build_scene_object(db: Session, inspector, table_name: str) -> Dict:
    """把一张表组织成一个业务对象"""
    columns = inspector.get_columns(table_name)
    icon, label = _get_icon_and_label(table_name)
    pk_constraint = inspector.get_pk_constraint(table_name)
    pk_columns = set(pk_constraint.get("constrained_columns", []))
    core_tables = _get_core_tables(db)

    return {
        "table": table_name,
        "label": label,
        "icon": icon,
        "desc": _generate_table_desc(table_name, columns),
        "is_core": table_name in core_tables,
        "row_count": _row_count(db, table_name),
        "fields": [column["name"] for column in columns],
        "columns": [
            {
                "name": column["name"],
                "type": str(column["type"]),
                "nullable": column.get("nullable", True),
                "comment": column.get("comment", "") or "",
                "primary_key": column["name"] in pk_columns,
            }
            for column in columns
        ],
    }


# ========== 获取业务知识场景 ==========

@router.get("/scenes")
def get_knowledge_scenes(db: Session = Depends(get_db)):
    """从当前数据库动态组织业务场景，包含各场景下的业务对象（表）"""
    inspector = inspect(db.get_bind())
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_", "metadata_"))
    ]

    scenes: Dict[str, Dict] = {}
    for key, scene in SCENE_TABLE_PREFIXES.items():
        scenes[key] = {
            "key": key,
            "icon": scene["icon"],
            "name": scene["name"],
            "desc": scene["desc"],
            "objects": [],
        }

    for table_name in tables:
        scene_key = _classify_table(table_name)
        if scene_key is None:
            continue
        try:
            obj = _build_scene_object(db, inspector, table_name)
            scenes[scene_key]["objects"].append(obj)
        except Exception as e:
            print(f"组织业务对象 {table_name} 失败: {e}")

    # 移除空场景（当前库没有对应表时）
    result = {key: scene for key, scene in scenes.items() if scene["objects"]}
    return {"scenes": result}


# ========== 获取术语词典 ==========


def _normalize_term_name(name: str) -> str:
    return name.replace("_", " ").replace("id", "ID").strip()


def _infer_term_category(column_name: str, table_name: str) -> str:
    name = column_name.lower()
    table = table_name.lower()
    if any(k in name for k in ["defect", "fault", "reject", "bad", "inspection", "quality", "yield"]):
        return "质量"
    if any(k in name for k in ["order", "work_order", "production", "process", "output", "yield"]):
        return "生产"
    if any(k in name for k in ["downtime", "equipment", "machine", "maintenance", "uptime"]):
        return "设备"
    if any(k in name for k in ["stock", "inventory", "warehouse", "safety_stock", "material"]):
        return "库存"
    if table.startswith("qms_") or table.startswith("defect") or table.startswith("inspection"):
        return "质量"
    if table.startswith("mes_") or table.startswith("work_order") or table.startswith("output"):
        return "生产"
    if table.startswith("eqp_") or table.startswith("machine"):
        return "设备"
    if table.startswith("inv_") or table.startswith("stock") or table.startswith("inventory"):
        return "库存"
    return "通用"


def _term_english_alias(name: str) -> str:
    common = {
        "工序": "Process",
        "良率": "Yield",
        "缺陷": "Defect",
        "停机时长": "Downtime",
        "安全库存": "Safety Stock",
        "产品": "Product",
        "设备": "Equipment",
        "库存": "Inventory",
        "工单": "Work Order",
        "检验": "Inspection",
        "不良": "Defect",
    }
    if name in common:
        return common[name]
    return " ".join(w.capitalize() for w in name.replace("_", " ").split())


def _abbreviation(name: str) -> str:
    if name.lower().endswith("_id"):
        return name[:-3].upper() + " ID"
    parts = name.replace("_", " ").split()
    if len(parts) > 1:
        return ''.join(p[0].upper() for p in parts if p)
    return name.upper()


def _classify_knowledge_type(column_name: str, column_type: str, table_name: str) -> str:
    """将术语归类为：业务对象 / 业务指标 / 业务规则 / 分析主题"""
    name = column_name.lower()
    col_type = str(column_type).lower()

    # 业务指标：数值型字段，表示可度量、可统计的量
    metric_keywords = [
        "rate", "count", "amount", "qty", "quantity", "duration",
        "price", "cost", "value", "weight", "percent", "ratio", "score",
        "yield", "output", "total", "sum", "avg", "max", "min",
        "temperature", "speed", "pressure", "volume", "length",
    ]
    is_numeric = any(t in col_type for t in ["int", "float", "numeric", "decimal", "double", "real"])
    if is_numeric and any(k in name for k in metric_keywords):
        return "业务指标"

    # 业务规则：枚举/状态/标志字段，表示约束和判断逻辑
    rule_keywords = [
        "status", "type", "level", "flag", "state", "result", "grade",
        "category", "class", "stage", "phase", "mode", "reason",
        "is_", "has_", "check", "pass", "fail", "qualified",
    ]
    if any(k in name for k in rule_keywords):
        return "业务规则"

    # 业务对象：外键/ID字段，表示实体引用
    if name.endswith("_id") or name.endswith("_key"):
        return "业务对象"

    # 业务对象：维度表的主键或名称字段
    if table_name.startswith("dim_"):
        return "业务对象"

    # 默认归为业务指标或业务对象
    if is_numeric:
        return "业务指标"
    return "业务对象"


def _generate_rich_definition(column_name: str, column_type: str, knowledge_type: str, table_name: str, comment: str) -> str:
    """根据术语类型生成更丰富的解释"""
    if comment:
        return comment

    name_cn = column_name.replace("_", " ")
    type_str = str(column_type)

    if knowledge_type == "业务指标":
        return f"「{name_cn}」是一个业务指标，数据类型为 {type_str}，来源于表 {table_name}。该指标用于衡量和量化业务运行状况，可作为数据分析的KPI。"
    elif knowledge_type == "业务规则":
        return f"「{name_cn}」是一个业务规则字段，数据类型为 {type_str}，来源于表 {table_name}。该字段定义了业务判断标准或分类逻辑，用于数据筛选和条件分析。"
    elif knowledge_type == "业务对象":
        return f"「{name_cn}」是一个业务对象标识，数据类型为 {type_str}，来源于表 {table_name}。该字段用于关联和引用业务实体，是数据建模的核心维度。"
    else:
        return f"「{name_cn}」是一个分析主题相关概念，数据类型为 {type_str}，来源于表 {table_name}。该字段用于组织和归类分析内容。"


@router.get("/terms")
def get_knowledge_terms(db: Session = Depends(get_db)):
    """从数据库字段注释中提取术语词典；无注释时返回常见业务术语"""
    inspector = inspect(db.get_bind())
    terms = []
    seen = set()
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_", "metadata_"))
    ]

    for table_name in tables:
        try:
            columns = inspector.get_columns(table_name)
        except Exception:
            continue
        for column in columns:
            comment = (column.get("comment") or "").strip()
            term_name = column["name"]
            col_type = str(column["type"])
            ktype = _classify_knowledge_type(term_name, col_type, table_name)
            definition = _generate_rich_definition(term_name, col_type, ktype, table_name, comment)
            key = f"{term_name}：{definition[:30]}"
            if key in seen:
                continue
            seen.add(key)
            terms.append({
                "term": term_name,
                "definition": definition,
                "category": _infer_term_category(term_name, table_name),
                "knowledge_type": ktype,
                "data_type": col_type,
                "en": _term_english_alias(term_name),
                "abbreviation": _abbreviation(term_name),
                "mapped_table": table_name,
                "mapped_field": term_name,
            })

    if not terms:
        terms = [
            {"term": "工序", "definition": "产品生产过程中经过的加工环节，是生产管理的核心业务对象，每个工序有独立的编号、名称和工艺参数。", "category": "生产", "knowledge_type": "业务对象", "data_type": "VARCHAR", "en": "Process", "abbreviation": "GX", "mapped_table": "dim_process", "mapped_field": "process_id"},
            {"term": "良率", "definition": "合格产出数量占总产出数量的百分比，是制造业最核心的质量指标。良率越高说明生产过程越稳定，质量控制越有效。", "category": "质量", "knowledge_type": "业务指标", "data_type": "DECIMAL", "en": "Yield Rate", "abbreviation": "LY", "mapped_table": "mes_process_output", "mapped_field": "yield_rate"},
            {"term": "缺陷", "definition": "产品质量不符合要求的异常项，用于定义和分类生产过程中的不合格现象，是质量分析的基础规则维度。", "category": "质量", "knowledge_type": "业务规则", "data_type": "VARCHAR", "en": "Defect", "abbreviation": "QX", "mapped_table": "qms_defect_detail", "mapped_field": "defect_type"},
            {"term": "停机时长", "definition": "设备因故障、保养或换模等原因停止运行的时间长度（分钟），是设备效率分析的关键指标，直接影响产能计算。", "category": "设备", "knowledge_type": "业务指标", "data_type": "INTEGER", "en": "Downtime", "abbreviation": "TJSC", "mapped_table": "eqp_downtime_record", "mapped_field": "duration"},
            {"term": "安全库存", "definition": "为应对需求波动和供应不确定性而设定的最低库存水位，低于该水位将触发补货预警，是库存管理的核心规则。", "category": "库存", "knowledge_type": "业务规则", "data_type": "INTEGER", "en": "Safety Stock", "abbreviation": "AQKC", "mapped_table": "inv_inventory_snapshot", "mapped_field": "safety_stock"},
        ]

    return {"terms": terms}


# ========== 获取知识统计 ==========

@router.get("/stats")
def get_knowledge_stats(db: Session = Depends(get_db)):
    """统计业务知识库规模：场景数、表数、字段数、术语数"""
    inspector = inspect(db.get_bind())
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_", "metadata_"))
    ]
    total_columns = 0
    for table_name in tables:
        try:
            total_columns += len(inspector.get_columns(table_name))
        except Exception:
            pass

    scene_keys = set()
    for table_name in tables:
        key = _classify_table(table_name)
        if key:
            scene_keys.add(key)

    terms = get_knowledge_terms(db)["terms"]

    return {
        "scene_count": len(scene_keys),
        "table_count": len(tables),
        "column_count": total_columns,
        "term_count": len(terms),
    }


# ========== 获取表间关系（外键） ==========


@router.get("/relations")
def get_knowledge_relations(db: Session = Depends(get_db)):
    """扫描数据库外键，返回表与表之间的关系信息，供图谱展示使用"""
    inspector = inspect(db.get_bind())
    relations = []
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_", "metadata_"))
    ]

    for table_name in tables:
        try:
            fks = inspector.get_foreign_keys(table_name)
        except Exception:
            fks = []

        for fk in fks:
            constrained = fk.get("constrained_columns") or []
            referred = fk.get("referred_columns") or []
            referred_table = fk.get("referred_table") or fk.get("referred_schema")
            for i, src_col in enumerate(constrained):
                tgt_col = referred[i] if i < len(referred) else (referred[0] if referred else None)
                relations.append({
                    "source_table": table_name,
                    "source_column": src_col,
                    "target_table": referred_table,
                    "target_column": tgt_col,
                    "type": "foreign_key",
                    "description": fk.get("name") or f"{table_name}.{src_col} -> {referred_table}.{tgt_col}",
                })

    return {"relations": relations}


# ========== 知识图谱专用接口（含知识类型分类） ==========

def _classify_table_type(table_name: str) -> str:
    """根据表名前缀和数据特征判断表的整体知识类型"""
    if table_name.startswith("dim_"):
        return "业务对象"
    if any(table_name.startswith(p) for p in ["mes_work_order", "mes_process_output"]):
        return "业务指标"
    if any(table_name.startswith(p) for p in ["qms_defect", "qms_inspection"]):
        return "业务规则"
    if any(table_name.startswith(p) for p in ["eqp_downtime"]):
        return "业务指标"
    if any(table_name.startswith(p) for p in ["inv_"]):
        return "业务规则"
    return "业务对象"


def _gen_table_desc_rich(table_name: str, columns: list, table_type: str) -> str:
    """生成表的业务描述"""
    col_names = [c["name"] for c in columns[:5]]
    if table_type == "业务对象":
        return f"{table_name} 是一个业务对象表，记录了 {', '.join(col_names)} 等维度信息，是数据分析的实体基础。"
    elif table_type == "业务指标":
        return f"{table_name} 是一个业务指标表，包含 {', '.join(col_names)} 等度量字段，用于 KPI 监控和趋势分析。"
    elif table_type == "业务规则":
        return f"{table_name} 是一个业务规则表，包含 {', '.join(col_names)} 等分类/判定字段，用于数据筛选和异常识别。"
    return f"{table_name} 数据表，共 {len(columns)} 个字段。"


@router.get("/graph")
def get_knowledge_graph(db: Session = Depends(get_db)):
    """返回知识图谱数据：节点（含知识类型分类）+ 边（外键关系）"""
    inspector = inspect(db.get_bind())
    tables = [
        name for name in inspector.get_table_names()
        if not name.startswith(("_", "pg_", "metadata_"))
    ]

    # 构建节点
    nodes = []
    node_ids = set()
    for table_name in tables:
        try:
            columns = inspector.get_columns(table_name)
        except Exception:
            continue
        table_type = _classify_table_type(table_name)
        icon, label = _get_icon_and_label(table_name)
        row_count = _row_count(db, table_name)

        # 子字段分类
        sub_fields = []
        for c in columns:
            sub_fields.append({
                "name": c["name"],
                "type": str(c["type"]),
                "ktype": _classify_knowledge_type(c["name"], str(c["type"]), table_name),
            })

        nodes.append({
            "id": table_name,
            "name": table_name,
            "label": label,
            "icon": icon,
            "nodeType": table_type,
            "columns": len(columns),
            "rowCount": row_count,
            "connected": False,
            "subFields": sub_fields,
            "desc": _gen_table_desc_rich(table_name, columns, table_type),
        })
        node_ids.add(table_name)

    # 构建边（外键关系）
    edges = []
    for table_name in tables:
        try:
            fks = inspector.get_foreign_keys(table_name)
        except Exception:
            continue
        for fk in fks:
            src_cols = fk.get("constrained_columns", [])
            referred_table = fk.get("referred_table") or ""
            tgt_cols = fk.get("referred_columns", [])
            if not src_cols or not referred_table or not tgt_cols:
                continue
            src_col = src_cols[0]
            tgt_col = tgt_cols[0]
            edges.append({
                "source": table_name,
                "target": referred_table,
                "sourceColumn": src_col,
                "targetColumn": tgt_col,
                "type": "foreign_key",
                "label": f"{src_col} → {tgt_col}",
                "description": fk.get("name") or f"{table_name}.{src_col} → {referred_table}.{tgt_col}",
            })

    # 标记已连接节点
    connected = set()
    for e in edges:
        connected.add(e["source"])
        connected.add(e["target"])
    for node in nodes:
        node["connected"] = node["id"] in connected

    return {"nodes": nodes, "edges": edges}
