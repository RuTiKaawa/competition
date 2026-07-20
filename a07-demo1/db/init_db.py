"""初始化 PostgreSQL 数据库: 建表 + 插入示例数据"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from config import DB_CONFIG

SCHEMA_SQL = """
-- 维度表
CREATE TABLE IF NOT EXISTS dim_product (
    product_id   VARCHAR(20) PRIMARY KEY,
    product_code VARCHAR(30) NOT NULL,
    product_name VARCHAR(100) NOT NULL,
    category     VARCHAR(20),
    spec         VARCHAR(50),
    unit         VARCHAR(10) DEFAULT '个',
    is_active    BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS dim_process (
    process_id    VARCHAR(10) PRIMARY KEY,
    process_name  VARCHAR(50) NOT NULL,
    process_seq   INTEGER NOT NULL,
    is_critical   BOOLEAN DEFAULT FALSE,
    std_yield_rate DECIMAL(5,2),
    department    VARCHAR(30)
);

CREATE TABLE IF NOT EXISTS dim_production_line (
    line_id       VARCHAR(10) PRIMARY KEY,
    line_name     VARCHAR(50) NOT NULL,
    workshop      VARCHAR(30),
    supervisor    VARCHAR(20),
    status        VARCHAR(10) DEFAULT '运行中',
    active_orders INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS dim_equipment (
    equipment_id   VARCHAR(20) PRIMARY KEY,
    equipment_name VARCHAR(80) NOT NULL,
    equipment_type VARCHAR(20),
    line_id        VARCHAR(10),
    model          VARCHAR(50),
    purchase_date  DATE,
    status         VARCHAR(10) DEFAULT '运行'
);

-- 事实表
CREATE TABLE IF NOT EXISTS mes_work_order (
    work_order_id VARCHAR(20) PRIMARY KEY,
    product_id    VARCHAR(20) REFERENCES dim_product(product_id),
    line_id       VARCHAR(10) REFERENCES dim_production_line(line_id),
    plan_qty      INTEGER NOT NULL,
    actual_qty    INTEGER DEFAULT 0,
    start_date    DATE,
    end_date      DATE,
    status        VARCHAR(10) DEFAULT '进行中'
);

CREATE TABLE IF NOT EXISTS mes_process_output (
    output_id     BIGSERIAL PRIMARY KEY,
    work_order_id VARCHAR(20) REFERENCES mes_work_order(work_order_id),
    product_id    VARCHAR(20) REFERENCES dim_product(product_id),
    process_id    VARCHAR(10) REFERENCES dim_process(process_id),
    line_id       VARCHAR(10) REFERENCES dim_production_line(line_id),
    stat_date     DATE NOT NULL,
    input_qty     INTEGER NOT NULL,
    good_qty      INTEGER NOT NULL,
    defect_qty    INTEGER DEFAULT 0,
    shift_code    CHAR(1) DEFAULT 'D'
);

CREATE TABLE IF NOT EXISTS qms_inspection (
    inspection_id  BIGSERIAL PRIMARY KEY,
    work_order_id  VARCHAR(20) REFERENCES mes_work_order(work_order_id),
    product_id     VARCHAR(20) REFERENCES dim_product(product_id),
    process_id     VARCHAR(10) REFERENCES dim_process(process_id),
    sample_qty     INTEGER NOT NULL,
    defect_qty     INTEGER DEFAULT 0,
    inspection_date DATE,
    result         VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS qms_defect_detail (
    defect_id     BIGSERIAL PRIMARY KEY,
    work_order_id VARCHAR(20) REFERENCES mes_work_order(work_order_id),
    product_id    VARCHAR(20) REFERENCES dim_product(product_id),
    process_id    VARCHAR(10) REFERENCES dim_process(process_id),
    defect_type   VARCHAR(30),
    severity      VARCHAR(10),
    disposal      VARCHAR(10)
);

CREATE TABLE IF NOT EXISTS eqp_downtime_record (
    downtime_id      BIGSERIAL PRIMARY KEY,
    equipment_id     VARCHAR(20) REFERENCES dim_equipment(equipment_id),
    line_id          VARCHAR(10) REFERENCES dim_production_line(line_id),
    start_time       TIMESTAMP NOT NULL,
    end_time         TIMESTAMP,
    downtime_minutes INTEGER NOT NULL,
    is_planned       BOOLEAN DEFAULT FALSE,
    reason           VARCHAR(100)
);

CREATE TABLE IF NOT EXISTS inv_inventory_snapshot (
    snapshot_id      BIGSERIAL PRIMARY KEY,
    product_id       VARCHAR(20) REFERENCES dim_product(product_id),
    warehouse_code   VARCHAR(10),
    available_qty    INTEGER DEFAULT 0,
    frozen_qty       INTEGER DEFAULT 0,
    safety_stock_qty INTEGER DEFAULT 0,
    snapshot_date    DATE
);
"""

SEED_SQL = """
-- 产品主数据
INSERT INTO dim_product VALUES
('P001','FRM-01-A','机架总成#01','结构件','1200x800','个',TRUE),
('P002','PNL-02-B','控制面板#02','电子','V2.1-LCD','个',TRUE),
('P003','MTR-03-A','伺服电机#03','机械','1.5kW','个',TRUE),
('P004','PMP-04-C','液压泵#04','机械','HPT-80','台',TRUE),
('P005','CTRL-05-N','控制器05·标准版','电子','V3.2-标准','个',TRUE),
('P006','SNR-06-D','位移传感器#06','电子','LVDT-50','个',TRUE),
('P007','SNS-07-B','温度传感器#07','电子','PT100','个',TRUE),
('P008','VLV-08-E','电磁阀#08','机械','DN25','个',TRUE),
('P009','BRG-09-F','滚动轴承#09','机械','6205-2RS','套',TRUE),
('P010','SEAL-10-G','密封圈套件#10','结构件','NBR-套装','套',TRUE),
('P011','CBL-11-H','线束总成#11','电子','24P-1.5m','条',TRUE),
('P012','BRK-12-C','液压制动器#12','机械','DN50','个',TRUE)
ON CONFLICT DO NOTHING;

-- 工序主数据
INSERT INTO dim_process (process_id,process_name,process_seq,is_critical,std_yield_rate,department) VALUES
('PR01','SMT贴片',1,true,98.5,'SMT车间'),
('PR02','回流焊',2,false,98.0,'SMT车间'),
('PR03','AOI检测',3,true,99.0,'品保部'),
('PR04','插件装配',4,false,97.5,'装配车间'),
('PR05','波峰焊',5,false,97.0,'装配车间'),
('PR06','功能测试',6,true,97.0,'品保部'),
('PR07','老化测试',7,true,96.5,'品保部'),
('PR08','包装入库',8,false,99.5,'包装车间')
ON CONFLICT DO NOTHING;

-- 产线主数据
INSERT INTO dim_production_line VALUES
('L01','一车间-1号线','一车间','主管1','运行中',3),
('L02','二车间-2号线','二车间','主管2','运行中',2),
('L03','三车间-6号线','三车间','主管6','维护中',0),
('L04','一车间-4号线','一车间','主管3','运行中',2),
('L05','二车间-5号线','二车间','主管4','空闲',0),
('L06','三车间-7号线','三车间','主管5','运行中',1)
ON CONFLICT DO NOTHING;

-- 设备主数据
INSERT INTO dim_equipment VALUES
('EQ-CNC-03','CNC加工中心#03','CNC','L03','VMC850E','2024-03-15','运行'),
('EQ-INJ-02','注塑机#02','注塑机','L02','MA1200','2023-08-20','运行'),
('EQ-SMT-01','SMT贴片机#01','贴片机','L01','NXT-III','2022-06-10','维修'),
('EQ-ARM-05','六轴机械臂#05','机械臂','L04','ER50-1200','2025-01-12','运行'),
('EQ-WLD-02','激光焊接机#02','焊接机','L01','LWF-3000','2023-11-05','停机'),
('EQ-AOI-01','AOI光学检测仪#01','检测仪','L01','Zenith-α','2023-04-18','运行'),
('EQ-TST-04','多功能测试台#04','测试台','L06','MT8000','2024-07-22','运行'),
('EQ-HPT-01','液压机#01','液压机','L05','HP-200T','2022-09-30','空闲')
ON CONFLICT DO NOTHING;

-- 工单
INSERT INTO mes_work_order VALUES
('WO-2026-0142','P005','L01',500,488,'2026-07-14','2026-07-16','进行中'),
('WO-2026-0143','P003','L02',300,302,'2026-07-13','2026-07-15','已完成'),
('WO-2026-0144','P007','L03',450,420,'2026-07-14','2026-07-17','进行中'),
('WO-2026-0145','P012','L01',200,0,'2026-07-15','2026-07-18','已取消')
ON CONFLICT DO NOTHING;

-- 工序产量
INSERT INTO mes_process_output (work_order_id,product_id,process_id,line_id,stat_date,input_qty,good_qty,defect_qty,shift_code) VALUES
('WO-2026-0142','P005','PR01','L01','2026-07-15',500,494,6,'D'),
('WO-2026-0142','P005','PR02','L01','2026-07-15',494,486,8,'D'),
('WO-2026-0142','P005','PR03','L01','2026-07-15',486,481,5,'D'),
('WO-2026-0142','P005','PR04','L01','2026-07-15',481,470,11,'D'),
('WO-2026-0142','P005','PR05','L01','2026-07-15',470,458,12,'D'),
('WO-2026-0142','P005','PR06','L01','2026-07-15',458,442,16,'D'),
('WO-2026-0142','P005','PR07','L01','2026-07-15',442,428,14,'D'),
('WO-2026-0142','P005','PR08','L01','2026-07-15',428,425,3,'D'),
('WO-2026-0143','P003','PR01','L02','2026-07-14',300,297,3,'D'),
('WO-2026-0143','P003','PR02','L02','2026-07-14',297,292,5,'D'),
('WO-2026-0143','P003','PR03','L02','2026-07-14',292,290,2,'D'),
('WO-2026-0143','P003','PR04','L02','2026-07-14',290,283,7,'D'),
('WO-2026-0143','P003','PR05','L02','2026-07-14',283,275,8,'D'),
('WO-2026-0143','P003','PR06','L02','2026-07-14',275,266,9,'D'),
('WO-2026-0143','P003','PR07','L02','2026-07-14',266,257,9,'D'),
('WO-2026-0143','P003','PR08','L02','2026-07-14',257,255,2,'D'),
('WO-2026-0144','P007','PR01','L03','2026-07-15',450,445,5,'D'),
('WO-2026-0144','P007','PR02','L03','2026-07-15',445,438,7,'D'),
('WO-2026-0144','P007','PR03','L03','2026-07-15',438,434,4,'D'),
('WO-2026-0144','P007','PR04','L03','2026-07-15',434,422,12,'D'),
('WO-2026-0144','P007','PR05','L03','2026-07-15',422,409,13,'D'),
('WO-2026-0144','P007','PR06','L03','2026-07-15',409,394,15,'D'),
('WO-2026-0144','P007','PR07','L03','2026-07-15',394,380,14,'D'),
('WO-2026-0144','P007','PR08','L03','2026-07-15',380,378,2,'D');

-- 质量检验
INSERT INTO qms_inspection (work_order_id,product_id,process_id,sample_qty,defect_qty,inspection_date,result) VALUES
('WO-2026-0142','P005','PR03',50,2,'2026-07-15','合格'),
('WO-2026-0142','P005','PR06',50,4,'2026-07-15','合格'),
('WO-2026-0143','P003','PR03',40,1,'2026-07-14','合格'),
('WO-2026-0143','P003','PR06',40,3,'2026-07-14','合格'),
('WO-2026-0144','P007','PR03',30,1,'2026-07-15','合格'),
('WO-2026-0144','P007','PR06',30,5,'2026-07-15','不合格'),
('WO-2026-0142','P005','PR07',50,3,'2026-07-15','合格');

-- 不良明细
INSERT INTO qms_defect_detail (work_order_id,product_id,process_id,defect_type,severity,disposal) VALUES
('WO-2026-0142','P005','PR06','功能失效','major','返工'),
('WO-2026-0142','P005','PR06','参数超差','major','返工'),
('WO-2026-0142','P005','PR06','焊接不良','minor','返工'),
('WO-2026-0142','P005','PR06','功能失效','major','报废'),
('WO-2026-0142','P005','PR06','外观缺陷','minor','让步'),
('WO-2026-0143','P003','PR06','功能失效','critical','报废'),
('WO-2026-0143','P003','PR06','参数超差','major','返工'),
('WO-2026-0144','P007','PR06','功能失效','major','返工'),
('WO-2026-0144','P007','PR06','焊接不良','minor','返工'),
('WO-2026-0144','P007','PR06','元器件错','critical','报废');

-- 设备停机
INSERT INTO eqp_downtime_record (equipment_id,line_id,start_time,end_time,downtime_minutes,is_planned,reason) VALUES
('EQ-CNC-03','L03','2026-07-15 09:12:00','2026-07-15 10:30:00',78,FALSE,'刀具磨损更换'),
('EQ-INJ-02','L02','2026-07-14 14:30:00','2026-07-14 15:15:00',45,FALSE,'模具温度异常'),
('EQ-SMT-01','L01','2026-07-13 08:00:00','2026-07-13 10:00:00',120,TRUE,'月度保养'),
('EQ-ARM-05','L04','2026-07-12 16:20:00','2026-07-12 17:00:00',40,FALSE,'关节过载报警');

-- 库存快照
INSERT INTO inv_inventory_snapshot (product_id,warehouse_code,available_qty,frozen_qty,safety_stock_qty,snapshot_date) VALUES
('P001','WH-A1',350,30,200,'2026-07-15'),
('P002','WH-A1',180,10,150,'2026-07-15'),
('P003','WH-B1',420,0,300,'2026-07-15'),
('P004','WH-B2',65,5,100,'2026-07-15'),
('P005','WH-A1',120,15,200,'2026-07-15'),
('P006','WH-A2',280,0,150,'2026-07-15'),
('P007','WH-B1',310,20,250,'2026-07-15'),
('P008','WH-B2',95,0,150,'2026-07-15'),
('P009','WH-C1',500,0,200,'2026-07-15'),
('P010','WH-C1',800,0,300,'2026-07-15'),
('P011','WH-A2',150,0,100,'2026-07-15'),
('P012','WH-B2',85,0,150,'2026-07-15');
"""


def init():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute(SCHEMA_SQL)
        print("✓ 表结构已创建")
        cur.execute(SEED_SQL)
        print("✓ 示例数据已插入")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    init()
    print("数据库初始化完成！")
