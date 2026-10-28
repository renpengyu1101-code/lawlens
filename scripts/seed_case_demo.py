"""把虚构案件材料灌进运行中的服务，跑一次核查，并补一个 V2 版本用于演示对比。

用法：python scripts/seed_case_demo.py
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000"
CASE = Path(__file__).resolve().parent.parent / "samples" / "虚构材料-澜川精密-2026-10"
MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def main() -> None:
    with httpx.Client(base_url=BASE, timeout=60) as client:
        r = client.post("/api/auth/login", json={"email": "admin", "password": "123456"})
        r.raise_for_status()

        project = client.post("/api/projects", json={
            "title": "澜川精密 港股IPO 资产核查（虚构样本）",
            "subject_name": "澜川精密制造有限公司",
            "brief": "核查核心资产权属、租赁、资质与知识产权，为港股申报做准备",
            "board": "asset",
            "is_demo": True,
        }).json()
        pid = project["id"]
        print("project", pid)

        first = sorted(p for p in CASE.glob("*.docx") if "-V2" not in p.name)
        files = [("files", (p.name, p.read_bytes(), MIME)) for p in first]
        client.post(f"/api/projects/{pid}/documents", files=files).raise_for_status()
        print("uploaded", len(files), "documents")

        client.post(f"/api/projects/{pid}/run").raise_for_status()
        for _ in range(40):
            time.sleep(0.6)
            detail = client.get(f"/api/projects/{pid}").json()
            if detail["project"]["status"] in {"done", "failed", "awaiting_materials"}:
                break

        print("status", detail["project"]["status"], "missing", len(detail["missing"]))
        for f in detail["findings"]:
            loc = "；".join(f"{c['filename']} p{c['page']}" for c in f["citations"] if c.get("document_id"))
            print(f"  [{f['code']}] {f['risk_level']:6} {f['title']} | qc={f['qc']} | {loc}")

        groups = client.get(f"/api/projects/{pid}/versions").json()["groups"]
        target = next(g for g in groups if "不动产权证" in g["title"])
        v1 = target["versions"][0]["id"]
        v2_file = CASE / "资产-01-不动产权证摘录-V2.docx"
        up = client.post(
            f"/api/projects/{pid}/versions",
            files={"file": (v2_file.name, v2_file.read_bytes(), MIME)},
            data={"group_id": str(target["id"]), "label": "V2"},
        )
        up.raise_for_status()
        info = up.json()
        print("version upload:", info["label"], info["diff"])

        diff = client.get(f"/api/versions/{v1}/diff/{info['version_id']}").json()
        print("diff:", diff["summary"])
        for item in diff["items"]:
            if item["kind"] == "changed":
                print("  旧:", item["left"]["text"])
                print("  新:", item["right"]["text"])

        print("open: /#/app/p/" + str(pid))


if __name__ == "__main__":
    main()
