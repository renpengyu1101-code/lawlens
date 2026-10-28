"""打印某项目的评分结果，便于人工核对。用法：python scripts/check_score.py <project_id>"""
import sys

import httpx

pid = sys.argv[1] if len(sys.argv) > 1 else "58"
c = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30)
c.post("/api/auth/login", json={"email": "admin", "password": "123456"})
r = c.get(f"/api/projects/{pid}/score")
print("HTTP", r.status_code)
if r.status_code != 200:
    print(r.text)
    raise SystemExit(1)

d = r.json()
print(f"总分 {d['normalized']} 等级 {d['grade']} 已得分 {d['earned']}/{d['applicable']} 覆盖率 {d['coverage']}")
for dim in d["dimensions"]:
    print(f"  {dim['id']} {dim['name']}: {dim['earned']}/{dim['applicable']} rate={dim['rate']}")
    for it in dim["items"]:
        if it["status"] != "full":
            reasons = "；".join(it["reasons"][:2])
            print(f"     - {it['id']} {it['name']} {it['earned']}/{it['points']} [{it['status']}] {reasons}")
