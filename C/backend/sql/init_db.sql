-- ============================================================
-- Manufacturing MES Data Platform - Database Initialization
-- PostgreSQL DDL
-- ============================================================

-- 1. 生产工单表
CREATE TABLE IF NOT EXISTS production_orders (
    id              SERIAL PRIMARY KEY,
    product_id      INTEGER NOT NULL,
    product_name    VARCHAR(100),
    production_line VARCHAR(50)  NOT NULL,
    planned_quantity INTEGER NOT NULL,
    actual_quantity  INTEGER,
    start_time      TIMESTAMP   NOT NULL,
    end_time        TIMESTAMP,
    status          VARCHAR(20) DEFAULT 'pending',
    created_at      TIMESTAMP   DEFAULT NOW(),
    updated_at      TIMESTAMP   DEFAULT NOW()
);

COMMENT ON TABLE production_orders IS '生产工单表';
COMMENT ON COLUMN production_orders.id IS '主键ID';
COMMENT ON COLUMN production_orders.product_id IS '产品ID';
COMMENT ON COLUMN production_orders.product_name IS '产品名称';
COMMENT ON COLUMN production_orders.production_line IS '生产线';
COMMENT ON COLUMN production_orders.planned_quantity IS '计划产量';
COMMENT ON COLUMN production_orders.actual_quantity IS '实际产量';
COMMENT ON COLUMN production_orders.start_time IS '开始时间';
COMMENT ON COLUMN production_orders.end_time IS '结束时间';
COMMENT ON COLUMN production_orders.status IS '状态(pending/in_progress/completed/cancelled)';
COMMENT ON COLUMN production_orders.created_at IS '创建时间';
COMMENT ON COLUMN production_orders.updated_at IS '更新时间';

ALTER TABLE production_orders ADD CONSTRAINT chk_production_orders_status
    CHECK (status IN ('pending', 'in_progress', 'completed', 'cancelled'));

CREATE INDEX IF NOT EXISTS idx_production_orders_line ON production_orders(production_line);
CREATE INDEX IF NOT EXISTS idx_production_orders_status ON production_orders(status);
CREATE INDEX IF NOT EXISTS idx_production_orders_start_time ON production_orders(start_time);
CREATE INDEX IF NOT EXISTS idx_production_orders_product_id ON production_orders(product_id);


-- 2. 工序产量表
CREATE TABLE IF NOT EXISTS process_yields (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER        NOT NULL,
    process_name      VARCHAR(50)    NOT NULL,
    produced_quantity INTEGER        NOT NULL,
    qualified_quantity INTEGER        NOT NULL,
    production_date   DATE           NOT NULL,
    shift             VARCHAR(20),
    operator_name     VARCHAR(50),
    created_at        TIMESTAMP      DEFAULT NOW(),
    CONSTRAINT fk_process_yields_order
        FOREIGN KEY (order_id)
        REFERENCES production_orders(id)
        ON DELETE CASCADE
);

COMMENT ON TABLE process_yields IS '工序产量表';
COMMENT ON COLUMN process_yields.id IS '主键ID';
COMMENT ON COLUMN process_yields.order_id IS '关联工单ID';
COMMENT ON COLUMN process_yields.process_name IS '工序名称';
COMMENT ON COLUMN process_yields.produced_quantity IS '生产数量';
COMMENT ON COLUMN process_yields.qualified_quantity IS '合格数量';
COMMENT ON COLUMN process_yields.production_date IS '生产日期';
COMMENT ON COLUMN process_yields.shift IS '班次';
COMMENT ON COLUMN process_yields.operator_name IS '操作员姓名';
COMMENT ON COLUMN process_yields.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS idx_process_yields_order_id ON process_yields(order_id);
CREATE INDEX IF NOT EXISTS idx_process_yields_process_name ON process_yields(process_name);
CREATE INDEX IF NOT EXISTS idx_process_yields_production_date ON process_yields(production_date);


-- 3. 质量检验表
CREATE TABLE IF NOT EXISTS quality_inspections (
    id                SERIAL PRIMARY KEY,
    order_id          INTEGER        NOT NULL,
    product_id        INTEGER        NOT NULL,
    inspection_result VARCHAR(20)    NOT NULL,
    defect_type       VARCHAR(50),
    inspection_date   DATE           NOT NULL,
    inspector         VARCHAR(50),
    defect_quantity   INTEGER        DEFAULT 0,
    remark            TEXT,
    created_at        TIMESTAMP      DEFAULT NOW(),
    CONSTRAINT fk_quality_inspections_order
        FOREIGN KEY (order_id)
        REFERENCES production_orders(id)
        ON DELETE CASCADE
);

COMMENT ON TABLE quality_inspections IS '质量检验表';
COMMENT ON COLUMN quality_inspections.id IS '主键ID';
COMMENT ON COLUMN quality_inspections.order_id IS '关联工单ID';
COMMENT ON COLUMN quality_inspections.product_id IS '产品ID';
COMMENT ON COLUMN quality_inspections.inspection_result IS '检验结果(pass/fail/rework)';
COMMENT ON COLUMN quality_inspections.defect_type IS '缺陷类型';
COMMENT ON COLUMN quality_inspections.inspection_date IS '检验日期';
COMMENT ON COLUMN quality_inspections.inspector IS '检验员';
COMMENT ON COLUMN quality_inspections.defect_quantity IS '缺陷数量';
COMMENT ON COLUMN quality_inspections.remark IS '备注';
COMMENT ON COLUMN quality_inspections.created_at IS '创建时间';

ALTER TABLE quality_inspections ADD CONSTRAINT chk_quality_inspections_result
    CHECK (inspection_result IN ('pass', 'fail', 'rework'));

CREATE INDEX IF NOT EXISTS idx_quality_inspections_order_id ON quality_inspections(order_id);
CREATE INDEX IF NOT EXISTS idx_quality_inspections_product_id ON quality_inspections(product_id);
CREATE INDEX IF NOT EXISTS idx_quality_inspections_date ON quality_inspections(inspection_date);
CREATE INDEX IF NOT EXISTS idx_quality_inspections_result ON quality_inspections(inspection_result);


-- 4. 设备停机表
CREATE TABLE IF NOT EXISTS equipment_downtimes (
    id                SERIAL PRIMARY KEY,
    equipment_id      INTEGER        NOT NULL,
    equipment_name    VARCHAR(100)   NOT NULL,
    downtime_start    TIMESTAMP      NOT NULL,
    downtime_end      TIMESTAMP,
    downtime_reason   VARCHAR(100),
    production_line   VARCHAR(50),
    downtime_duration INTEGER,
    resolved_by       VARCHAR(50),
    created_at        TIMESTAMP      DEFAULT NOW()
);

COMMENT ON TABLE equipment_downtimes IS '设备停机表';
COMMENT ON COLUMN equipment_downtimes.id IS '主键ID';
COMMENT ON COLUMN equipment_downtimes.equipment_id IS '设备ID';
COMMENT ON COLUMN equipment_downtimes.equipment_name IS '设备名称';
COMMENT ON COLUMN equipment_downtimes.downtime_start IS '停机开始时间';
COMMENT ON COLUMN equipment_downtimes.downtime_end IS '停机结束时间';
COMMENT ON COLUMN equipment_downtimes.downtime_reason IS '停机原因';
COMMENT ON COLUMN equipment_downtimes.production_line IS '所属产线';
COMMENT ON COLUMN equipment_downtimes.downtime_duration IS '停机时长(分钟)';
COMMENT ON COLUMN equipment_downtimes.resolved_by IS '处理人';
COMMENT ON COLUMN equipment_downtimes.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS idx_equipment_downtimes_equip_id ON equipment_downtimes(equipment_id);
CREATE INDEX IF NOT EXISTS idx_equipment_downtimes_line ON equipment_downtimes(production_line);
CREATE INDEX IF NOT EXISTS idx_equipment_downtimes_start ON equipment_downtimes(downtime_start);


-- 5. 库存表
CREATE TABLE IF NOT EXISTS inventory (
    id            SERIAL PRIMARY KEY,
    material_id   INTEGER          NOT NULL,
    material_name VARCHAR(100)     NOT NULL,
    material_code VARCHAR(50),
    warehouse     VARCHAR(50),
    quantity      DECIMAL(12,2)    NOT NULL DEFAULT 0,
    safety_stock  DECIMAL(12,2),
    unit          VARCHAR(20)      DEFAULT 'pcs',
    last_updated  TIMESTAMP        DEFAULT NOW(),
    created_at    TIMESTAMP        DEFAULT NOW(),
    CONSTRAINT uq_inventory_material_warehouse
        UNIQUE (material_id, warehouse)
);

COMMENT ON TABLE inventory IS '库存表';
COMMENT ON COLUMN inventory.id IS '主键ID';
COMMENT ON COLUMN inventory.material_id IS '物料ID';
COMMENT ON COLUMN inventory.material_name IS '物料名称';
COMMENT ON COLUMN inventory.material_code IS '物料编码';
COMMENT ON COLUMN inventory.warehouse IS '仓库';
COMMENT ON COLUMN inventory.quantity IS '库存数量';
COMMENT ON COLUMN inventory.safety_stock IS '安全库存';
COMMENT ON COLUMN inventory.unit IS '单位';
COMMENT ON COLUMN inventory.last_updated IS '最后更新时间';
COMMENT ON COLUMN inventory.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS idx_inventory_material_id ON inventory(material_id);
CREATE INDEX IF NOT EXISTS idx_inventory_warehouse ON inventory(warehouse);
CREATE INDEX IF NOT EXISTS idx_inventory_material_code ON inventory(material_code);


-- 6. 元数据配置表
CREATE TABLE IF NOT EXISTS metadata_config (
    id               SERIAL PRIMARY KEY,
    table_name       VARCHAR(100)  NOT NULL,
    table_comment    VARCHAR(200),
    field_name       VARCHAR(100)  NOT NULL,
    field_type       VARCHAR(50),
    field_comment    VARCHAR(300),
    sample_values    TEXT,
    relationship_desc VARCHAR(300),
    created_at       TIMESTAMP     DEFAULT NOW()
);

COMMENT ON TABLE metadata_config IS '元数据配置表';
COMMENT ON COLUMN metadata_config.id IS '主键ID';
COMMENT ON COLUMN metadata_config.table_name IS '表名';
COMMENT ON COLUMN metadata_config.table_comment IS '表注释';
COMMENT ON COLUMN metadata_config.field_name IS '字段名';
COMMENT ON COLUMN metadata_config.field_type IS '字段类型';
COMMENT ON COLUMN metadata_config.field_comment IS '字段注释';
COMMENT ON COLUMN metadata_config.sample_values IS '样例值';
COMMENT ON COLUMN metadata_config.relationship_desc IS '关系描述';
COMMENT ON COLUMN metadata_config.created_at IS '创建时间';

CREATE INDEX IF NOT EXISTS idx_metadata_config_table ON metadata_config(table_name);
CREATE INDEX IF NOT EXISTS idx_metadata_config_field ON metadata_config(field_name);


-- 7. 业务对象表
CREATE TABLE IF NOT EXISTS knowledge_objects (
    id             SERIAL PRIMARY KEY,
    object_name    VARCHAR(100)  NOT NULL,
    object_type    VARCHAR(50),
    description    TEXT,
    related_tables TEXT,
    attributes     JSONB,
    created_at     TIMESTAMP     DEFAULT NOW(),
    updated_at     TIMESTAMP     DEFAULT NOW()
);

COMMENT ON TABLE knowledge_objects IS '业务对象表';
COMMENT ON COLUMN knowledge_objects.id IS '主键ID';
COMMENT ON COLUMN knowledge_objects.object_name IS '对象名称';
COMMENT ON COLUMN knowledge_objects.object_type IS '对象类型';
COMMENT ON COLUMN knowledge_objects.description IS '描述';
COMMENT ON COLUMN knowledge_objects.related_tables IS '关联表';
COMMENT ON COLUMN knowledge_objects.attributes IS '属性(JSONB)';
COMMENT ON COLUMN knowledge_objects.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_objects.updated_at IS '更新时间';


-- 8. 业务指标表
CREATE TABLE IF NOT EXISTS knowledge_indicators (
    id             SERIAL PRIMARY KEY,
    indicator_name VARCHAR(100)  NOT NULL,
    formula        TEXT,
    description    TEXT,
    unit           VARCHAR(50),
    category       VARCHAR(50),
    related_tables TEXT,
    created_at     TIMESTAMP     DEFAULT NOW(),
    updated_at     TIMESTAMP     DEFAULT NOW()
);

COMMENT ON TABLE knowledge_indicators IS '业务指标表';
COMMENT ON COLUMN knowledge_indicators.id IS '主键ID';
COMMENT ON COLUMN knowledge_indicators.indicator_name IS '指标名称';
COMMENT ON COLUMN knowledge_indicators.formula IS '计算公式';
COMMENT ON COLUMN knowledge_indicators.description IS '描述';
COMMENT ON COLUMN knowledge_indicators.unit IS '单位';
COMMENT ON COLUMN knowledge_indicators.category IS '分类';
COMMENT ON COLUMN knowledge_indicators.related_tables IS '关联表';
COMMENT ON COLUMN knowledge_indicators.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_indicators.updated_at IS '更新时间';


-- 9. 业务规则表
CREATE TABLE IF NOT EXISTS knowledge_rules (
    id          SERIAL PRIMARY KEY,
    rule_name   VARCHAR(100)  NOT NULL,
    rule_content TEXT,
    severity    VARCHAR(20),
    category    VARCHAR(50),
    is_active   BOOLEAN       DEFAULT true,
    created_at  TIMESTAMP     DEFAULT NOW(),
    updated_at  TIMESTAMP     DEFAULT NOW()
);

COMMENT ON TABLE knowledge_rules IS '业务规则表';
COMMENT ON COLUMN knowledge_rules.id IS '主键ID';
COMMENT ON COLUMN knowledge_rules.rule_name IS '规则名称';
COMMENT ON COLUMN knowledge_rules.rule_content IS '规则内容';
COMMENT ON COLUMN knowledge_rules.severity IS '严重程度';
COMMENT ON COLUMN knowledge_rules.category IS '分类';
COMMENT ON COLUMN knowledge_rules.is_active IS '是否启用';
COMMENT ON COLUMN knowledge_rules.created_at IS '创建时间';
COMMENT ON COLUMN knowledge_rules.updated_at IS '更新时间';


-- 10. 分析主题表
CREATE TABLE IF NOT EXISTS knowledge_themes (
    id                 SERIAL PRIMARY KEY,
    theme_name         VARCHAR(100)  NOT NULL,
    description        TEXT,
    question_templates JSONB,
    created_at         TIMESTAMP     DEFAULT NOW()
);

COMMENT ON TABLE knowledge_themes IS '分析主题表';
COMMENT ON COLUMN knowledge_themes.id IS '主键ID';
COMMENT ON COLUMN knowledge_themes.theme_name IS '主题名称';
COMMENT ON COLUMN knowledge_themes.description IS '描述';
COMMENT ON COLUMN knowledge_themes.question_templates IS '问题模板(JSONB)';
COMMENT ON COLUMN knowledge_themes.created_at IS '创建时间';
