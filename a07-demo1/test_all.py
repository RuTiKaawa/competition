"""全功能回归测试"""
import urllib.request, json, sys

BASE = "http://127.0.0.1:5173"
OK, FAIL, ERR = 0, 0, 0

def test(name, method, path, body=None, check=None):
    global OK, FAIL, ERR
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{BASE}{path}", data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method)
        r = urllib.request.urlopen(req, timeout=30)
        resp = json.loads(r.read().decode()) if r.status != 204 else {}
        if check:
            ok, msg = check(resp)
            if ok:
                print(f"  ✓ {name}  — {msg}")
                OK += 1
            else:
                print(f"  ✗ {name}  — {msg}")
                FAIL += 1
        else:
            print(f"  ✓ {name}")
            OK += 1
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:200]
        print(f"  ✗ {name}  — HTTP {e.code}: {body}")
        FAIL += 1
    except Exception as e:
        print(f"  ✗ {name}  — {e}")
        ERR += 1

# ====== 1. Health ======
print("\n── 基础 ──")
test("health", "GET", "/api/health", check=lambda r: (r["status"]=="ok", "ok"))

# ====== 2. Dashboard ======
print("\n── 仪表盘 ──")
test("KPI", "GET", "/api/dashboard",
     check=lambda r: (len(r["stats"])==5, f"stats={r['stats']}"))

test("charts", "GET", "/api/dashboard/charts",
     check=lambda r: (len(r["charts"])>=2, f"{len(r['charts'])} charts"))

# ====== 3. Database Connection ======
print("\n── 数据库连接 ──")
test("status", "GET", "/api/db/status",
     check=lambda r: (r.get("connected"), f"connected={r.get('connected')}"))

test("list connections", "GET", "/api/db/connections",
     check=lambda r: ("connections" in r, f"{len(r['connections'])} connections"))

test("test conn", "POST", "/api/db/test-connection",
     body={"host":"localhost","port":5432,"user":"postgres","password":"123456","dbname":"postgres","name":"test"},
     check=lambda r: (r.get("success"), r.get("message","")))

test("save conn", "POST", "/api/db/connections",
     body={"host":"localhost","port":5432,"user":"postgres","password":"123456","dbname":"postgres","name":"AutoTest"},
     check=lambda r: (r.get("saved"), "saved"))

test("switch conn", "POST", "/api/db/switch/AutoTest",
     check=lambda r: (r.get("success"), r.get("version","")))

test("delete test conn", "DELETE", "/api/db/connections/AutoTest",
     check=lambda r: (r.get("deleted"), "deleted"))

# ====== 4. Tables ======
print("\n── 数据库表 ──")
test("list tables", "GET", "/api/metadata/tables",
     check=lambda r: (len(r.get("tables",[]))==10, f"{len(r.get('tables',[]))} tables"))

for t in ["dim_equipment","mes_process_output","qms_defect_detail","inv_inventory_snapshot"]:
    test(f"detail {t}", "GET", f"/api/metadata/tables/{t}",
         check=lambda r, tn=t: (isinstance(r.get("fields"), list) and len(r["fields"])>0, f"{len(r.get('fields',[]))} fields"))

# ====== 5. Agent Ask ======
print("\n── 智能问析 ──")
ask_tests = [
    ("table_lookup", "查机械表"),
    ("table_lookup", "查产品表"),
    ("table_lookup", "查不良表"),
    ("data_query", "分析各工序良率"),
    ("data_query", "不良类型排行"),
    ("data_query", "库存低于安全库存的产品"),
    ("data_query", "列出所有设备"),
    ("data_query", "最近设备停机记录"),
]
for exp, q in ask_tests:
    def make_check(expected_type):
        def check(r):
            ok = r.get("type") == expected_type
            d = r.get("data",{})
            if expected_type == "table_lookup":
                ok = ok and d.get("matched_table") is not None
                return (ok, f"type={r['type']} table={d.get('matched_table',{}).get('table_name','?')}")
            else:
                rs = d.get("result",{})
                suc = rs.get("success",False)
                rows = rs.get("row_count",0)
                return (ok and suc, f"type={r['type']} ok={suc} rows={rows}")
        return check
    test(f"ask: {q}", "POST", "/api/agent/ask",
         body={"query": q},
         check=make_check(exp))

# ====== 6. Chart API ======
print("\n── 图表生成 ──")
chart_types = ["bar","barh","stacked","line","area","pie","donut","scatter"]
for ct in chart_types:
    test(f"generate {ct}", "POST", "/api/chart/generate",
         body={"columns":["类别","数值"],"rows":[{"类别":v,"数值":i*10+10} for i,v in enumerate("ABCDE")],"force_type":ct,"title":"test"},
         check=lambda r, t=ct: (r["type"]==t, f"{r['type']} svg:{len(r.get('svg',''))}"))

test("recommend type", "POST", "/api/chart/recommend-type",
     body={"query":"产品销量排名","columns":["产品","销量"],"rows":[{"产品":"A","销量":100}]},
     check=lambda r: (r.get("recommended") in chart_types, r.get("recommended","?")))

# ====== 7. Custom Chart ======
print("\n── 自定义图表 ──")
test("custom: 缺陷分布", "POST", "/api/chart/custom",
     body={"title":"缺陷分析","chart_type":"pie","description":"统计缺陷类型分布"},
     check=lambda r: (r.get("chart",{}).get("type") in ["pie","none"], f"{r['chart']['type']} rows:{len(r['data']['rows'])}"))

test("custom: 产品统计", "POST", "/api/chart/custom",
     body={"title":"产品统计","chart_type":"bar","description":"产品分类统计"},
     check=lambda r: (isinstance(r.get("data"),dict), f"rows:{len(r.get('data',{}).get('rows',[]))}"))

test("custom: 设备状态", "POST", "/api/chart/custom",
     body={"title":"设备状态","chart_type":"barh","description":"统计各设备状态分布"},
     check=lambda r: (r.get("data",{}).get("rows"), f"rows:{len(r.get('data',{}).get('rows',[]))}"))

# ====== Summary ======
print(f"\n{'='*40}")
print(f"Total: {OK+FAIL+ERR}  |  ✓ {OK}  |  ✗ {FAIL}  |  Crash {ERR}")
if FAIL == 0 and ERR == 0:
    print("ALL PASSED ✓")
else:
    print("SOME FAILED ✗")
