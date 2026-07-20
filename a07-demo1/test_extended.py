"""扩展回归测试 — 更多边界场景"""
import urllib.request, json, sys, time

BASE = "http://127.0.0.1:5173"
OK, FAIL, ERR = 0, 0, 0
errors = []

def test(name, method, path, body=None, check=None, timeout=30):
    global OK, FAIL, ERR
    try:
        data = json.dumps(body).encode() if body else None
        req = urllib.request.Request(f"{BASE}{path}", data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method=method)
        r = urllib.request.urlopen(req, timeout=timeout)
        resp = json.loads(r.read().decode()) if r.status != 204 else {}
        if check:
            ok, msg = check(resp)
            if ok: print(f"  ✓ {name}"); OK += 1
            else: print(f"  ✗ {name} — {msg}"); FAIL += 1; errors.append((name, msg))
        else: print(f"  ✓ {name}"); OK += 1
    except urllib.error.HTTPError as e:
        msg = e.read().decode()[:200]
        print(f"  ✗ {name} — HTTP {e.code}: {msg}")
        FAIL += 1; errors.append((name, f"HTTP {e.code}"))
    except Exception as e:
        print(f"  ✗ {name} — {e}")
        ERR += 1; errors.append((name, str(e)))

# ====== 1. 智能问析 — 更多场景 ======
print("\n── 智能问析-扩展 ──")
queries = [
    ("data_query", "各产线的产量对比"),
    ("data_query", "哪台设备故障最多"),
    ("data_query", "功能测试工序的不良原因"),
    ("data_query", "统计各种设备类型的数量"),
    ("data_query", "返修类型的不良分布"),
    ("data_query", "查看最近工单状态"),
    ("data_query", "各车间的不良率统计"),
    ("data_query", "上月产量最高的产品"),
    ("data_query", "A类产品的合格率趋势"),
    ("data_query", "波峰焊的良率与其他工序对比"),
    ("table_lookup", "查看产量表"),
    ("table_lookup", "不良表有哪些字段"),
    ("table_lookup", "库存表的结构"),
    ("table_lookup", "设备表"),
]
for exp, q in queries:
    def ck(et):
        def _ck(r):
            d = r.get("data",{})
            if et == "table_lookup":
                return (r["type"]=="table_lookup" and d.get("matched_table"), f"table={d.get('matched_table',{}).get('table_name','?')}")
            rr = d.get("result",{})
            return (r["type"]=="data_query" and rr.get("success") and rr.get("row_count",0)>0, f"ok={rr.get('success')} rows={rr.get('row_count',0)} sql_ok={bool(rr.get('success'))}")
        return _ck
    test(f"ask: {q[:25]}", "POST", "/api/agent/ask", body={"query": q}, check=ck(exp))

# ====== 2. 图表切换 ======
print("\n── 图表类型切换 ──")
rows = [{"工序":v,"良率":i*15+50} for i,v in enumerate(["SMT","回流焊","AOI","插件","波峰焊"])]
for ct in ["bar","barh","stacked","line","area","pie","donut","scatter"]:
    test(f"switch to {ct}", "POST", "/api/chart/generate",
         body={"columns":["工序","良率"],"rows":rows,"force_type":ct,"title":"test"},
         check=lambda r,t=ct: (r["type"]==t and len(r.get("svg",""))>500, f"svg:{len(r.get('svg',''))}"))

# ====== 3. 自定义图表 — 边界 ======
print("\n── 自定义图表-边界 ──")
custom_tests = [
    ("产量排行", "barh", "统计各产品产量排名"),
    ("良率趋势", "line", "各工序良率变化"),
    ("不良占比", "donut", "不良类型占比分布"),
    ("库存对比", "bar", "各产品库存量"),
    ("设备分布", "pie", "不同类型设备数量统计"),
    ("停机分析", "stacked", "计划与非计划停机对比"),
    ("质检结果", "bar", "质检合格与不合格数量"),
]
for title, ct, desc in custom_tests:
    test(f"custom: {title}", "POST", "/api/chart/custom",
         body={"title":title,"chart_type":ct,"description":desc},
         check=lambda r,c=ct: (r.get("chart",{}).get("type") in (c,"none") or r["chart"].get("svg"), f"{r['chart']['type']} rows:{len(r.get('data',{}).get('rows',[]))}"))

# ====== 4. 数据表操作 ======
print("\n── 数据表-扩展 ──")
for t in ["dim_process","mes_work_order","qms_inspection","eqp_downtime_record","dim_production_line"]:
    test(f"detail {t}", "GET", f"/api/metadata/tables/{t}",
         check=lambda r: (isinstance(r.get("fields"),list) and len(r["fields"])>=2, f"{len(r.get('fields',[]))} fields"))

test("404 for missing table (expected)", "GET", "/api/metadata/tables/nonexistent",
     check=lambda r: (r.get("detail",""), "got 404 as expected"))  # caught by HTTPError

# ====== 5. 并发/压力 ======
print("\n── 并发请求 ──")
import concurrent.futures
def quick_ask(q):
    try:
        d = json.dumps({"query":q}).encode()
        r = urllib.request.urlopen(urllib.request.Request(f"{BASE}/api/agent/ask", data=d,
            headers={"Content-Type":"application/json"}), timeout=15)
        resp = json.loads(r.read().decode())
        return resp["type"] in ("table_lookup","data_query")
    except: return False

with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
    futures = [ex.submit(quick_ask, q) for q in ["查机械表","分析良率","不良排行"]]
    results = [f.result() for f in futures]
all_ok = all(results)
test("concurrent 3 queries", "GET", "/api/health",
     check=lambda r: (all_ok, f"3/3 passed"))

# ====== 6. 错误恢复 ======
print("\n── 错误处理 ──")
test("bad SQL auto-fallback", "POST", "/api/agent/ask",
     body={"query":"asdfghjkl12345"},
     check=lambda r: (r["type"] in ("data_query","table_lookup"), f"type={r['type']}"))

test("empty query", "POST", "/api/agent/ask",
     body={"query":" "},
     check=lambda r: (r["type"] in ("data_query","table_lookup"), f"type={r['type']}"))

test("custom chart bad desc", "POST", "/api/chart/custom",
     body={"title":"bad","chart_type":"bar","description":"xyz123notexist456"},
     check=lambda r: (isinstance(r.get("data"),dict), "returns gracefully"))

# ====== Summary ======
print(f"\n{'='*50}")
print(f"RESULTS: ✓ {OK}  |  ✗ {FAIL}  |  Crash {ERR}  |  Total {OK+FAIL+ERR}")
if errors:
    print(f"\nFAILURES ({len(errors)}):")
    for name, msg in errors: print(f"  - {name}: {msg}")
    print(f"\n✗ SOME FAILED")
else:
    print(f"\n✓ ALL PASSED")
