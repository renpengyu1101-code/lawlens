"""端到端冒烟测试：注册 → 建项目 → 上传 → 流水线 → 报告 → 后台。

运行（在 backend 目录下）：python ../scripts/smoke_test.py
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BACKEND = ROOT / "backend"
SAMPLES = ROOT / "samples" / "虚构测试样本"
# 只清理本次运行使用的数据目录，绝不碰正在运行的服务所用的 backend/data
DATA = Path(os.environ.get("DILIGENCE_DATA_DIR") or (BACKEND / "data"))
os.environ["DILIGENCE_DATA_DIR"] = str(DATA)
sys.path.insert(0, str(BACKEND))

if DATA.exists():
    shutil.rmtree(DATA)

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

FAIL = []
TOTAL = 0


def check(cond: bool, msg: str) -> None:
    global TOTAL
    TOTAL += 1
    print(("  PASS " if cond else "  FAIL ") + msg)
    if not cond:
        FAIL.append(msg)


def main() -> int:
    with TestClient(app) as client:
        r = client.post("/api/auth/register", json={"email": "demo@example.com", "password": "demo123456"})
        check(r.status_code == 200, f"注册用户 HTTP {r.status_code}")
        check(r.json()["user"]["credits"] == 100, "注册赠送 100 积分")

        r = client.post("/api/projects", json={
            "title": "云澜智造 港股IPO 资产核查（演示）",
            "subject_name": "云澜智造科技有限公司",
            "brief": "核查核心资产权属、经营场所与资质，为港股申报做准备",
            "board": "asset",
            "is_demo": True,
        })
        check(r.status_code == 200, f"创建项目 HTTP {r.status_code}")
        pid = r.json()["id"]

        files = [("files", (p.name, p.read_bytes(),
                  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
                 for p in sorted(SAMPLES.glob("*.docx"))]
        check(len(files) == 7, f"样本文件数 {len(files)}")
        r = client.post(f"/api/projects/{pid}/documents", files=files)
        check(r.status_code == 200, f"上传材料 HTTP {r.status_code}")
        check(len(r.json()["documents"]) == 7, "7 份材料入库")

        r = client.post(f"/api/projects/{pid}/run")
        check(r.status_code == 200, f"发起任务 HTTP {r.status_code}")

        r = client.get(f"/api/projects/{pid}")
        detail = r.json()
        check(detail["project"]["status"] == "pending_review", f"任务进入待律师复核（实际 {detail['project']['status']}）")
        review = detail["review"]
        check(bool(review) and review["status"] == "pending", "生成待复核单")
        codes = {t["code"] for t in (review or {}).get("triggers", [])}
        check(len(codes) >= 3, f"触发复核条件 {sorted(codes)}")
        check("B1" in codes, "缺法律依据触发复核（B1）")
        check("C1" in codes, "整改方案待确认触发复核（C1）")
        check(len(detail["missing"]) == 0, "无缺失材料")

        findings = detail["findings"]
        codes = [f["code"] for f in findings]
        print("  识别风险：", ", ".join(codes))
        for expect in ("AST-01", "AST-03", "AST-04", "AST-05", "AST-06"):
            check(expect in codes, f"识别出 {expect}")
        check(all(f["qc"] in {"pass", "insufficient"} for f in findings), "所有结论通过质检（无阻断项）")
        check(all(f["citations"] for f in findings), "每条结论都带证据锚点")

        for f in findings:
            locs = "；".join(f"{c['filename']} p{c['page']}" for c in f["citations"] if c.get("document_id"))
            print(f"    [{f['code']}] {f['risk_level']:6} {f['title']} | qc={f['qc']} | {locs}")

        r = client.get(f"/api/projects/{pid}/report")
        check(r.status_code == 200 and len(r.content) > 5000, f"报告下载 HTTP {r.status_code}, {len(r.content)} bytes")
        out = SAMPLES.parent / "示例报告（虚构样本）.docx"
        out.write_bytes(r.content)
        print("  报告已保存：", out)

        r = client.get("/api/auth/me")
        credits = r.json()["user"]["credits"]
        check(credits == 90, f"扣除 10 积分（剩余 {credits}）")

        client.post("/api/auth/logout")
        r = client.get("/api/projects")
        check(r.status_code == 401, f"未登录访问项目列表被拒（HTTP {r.status_code}）")

        r = client.post("/api/auth/login", json={"email": "admin", "password": "123456"})
        check(r.status_code == 200, "管理员登录")
        decision = client.post(f"/api/reviews/{review['id']}/decision", json={"decision": "approved", "comment": "演示复核通过"})
        check(decision.status_code == 200 and decision.json()["project_status"] == "done", f"复核通过后项目转 done（{decision.json()}）")
        r = client.get("/api/admin/overview")
        check(r.status_code == 200 and r.json()["projects"] == 1, f"后台概览 {r.json()}")
        r = client.get("/api/admin/rules")
        check(r.status_code == 200 and len(r.json()["rules"]["checkpoints"]) == 6, "后台读取规则库 6 条")
        r = client.get("/api/admin/audit")
        check(r.status_code == 200 and len(r.json()["logs"]) >= 4, f"审计日志 {len(r.json()['logs'])} 条")

        # 普通用户无权访问后台
        client.post("/api/auth/login", json={"email": "demo@example.com", "password": "demo123456"})
        r = client.get("/api/admin/users")
        check(r.status_code == 403, f"普通用户访问后台被拒（HTTP {r.status_code}）")

        # 积分不足：管理员清零后再发起任务应被拒且不产生新任务
        client.post("/api/auth/login", json={"email": "admin", "password": "123456"})
        users = client.get("/api/admin/users").json()["users"]
        demo_uid = next(u["id"] for u in users if u["email"] == "demo@example.com")
        left = next(u["credits"] for u in users if u["id"] == demo_uid)
        client.post(f"/api/admin/users/{demo_uid}/credits", json={"delta": -left, "reason": "测试清零"})
        client.post("/api/auth/login", json={"email": "demo@example.com", "password": "demo123456"})
        r = client.post(f"/api/projects/{pid}/run")
        check(r.status_code == 402, f"积分不足被拒（HTTP {r.status_code}）")
        r = client.get(f"/api/projects/{pid}")
        check(r.json()["project"]["status"] == "done", "被拒任务未改变项目状态")

        # 三个板块
        boards = client.get("/api/health").json()["boards"]
        check(set(boards) == {"asset", "labor", "equity"}, f"三个板块注册：{list(boards.values())}")

        client.post("/api/auth/login", json={"email": "admin", "password": "123456"})
        client.post(f"/api/admin/users/{demo_uid}/credits", json={"delta": 100, "reason": "补充测试积分"})
        client.post("/api/auth/login", json={"email": "demo@example.com", "password": "demo123456"})

        def run_board(board: str, folder: Path, expect: list[str]) -> None:
            created = client.post("/api/projects", json={
                "title": f"{board} 板块演示",
                "subject_name": "云澜智造科技有限公司",
                "brief": "板块联调",
                "board": board,
                "is_demo": True,
            }).json()
            bid = created["id"]
            payload = [("files", (p.name, p.read_bytes(),
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"))
                       for p in sorted(folder.glob("*.docx"))]
            client.post(f"/api/projects/{bid}/documents", files=payload)
            client.post(f"/api/projects/{bid}/run")
            detail = client.get(f"/api/projects/{bid}").json()
            codes = [f["code"] for f in detail["findings"]]
            print(f"  {board} 识别：", ", ".join(codes))
            check(detail["project"]["status"] == "pending_review", f"{board} 板块跑通并进入复核")
            check(all(e in codes for e in expect), f"{board} 识别 {expect}")
            check(all(f["qc"] in {"pass", "insufficient"} for f in detail["findings"]), f"{board} 质检无阻断项")

        run_board("labor", SAMPLES.parent / "虚构测试样本-劳动用工", ["LAB-01", "LAB-02", "LAB-03", "LAB-06"])
        run_board("equity", SAMPLES.parent / "虚构测试样本-投资退出", ["EQT-01", "EQT-02", "EQT-03", "EQT-04"])

        # 版本能力：新版本 + 段落对齐 + 差异
        groups = client.get(f"/api/projects/{pid}/versions").json()["groups"]
        check(len(groups) == 7, f"材料组 {len(groups)} 个（迁移自历史材料）")
        target = next(g for g in groups if "不动产权证" in g["title"])
        v1 = target["versions"][0]
        check(len(target["versions"]) == 1 and v1["is_current"] == 1, "初始版本为 V1 且为当前版")

        import docx as _docx

        doc = _docx.Document()
        for line in [
            "不动产权证书",
            "权利人：云澜智造科技有限公司",
            "不动产权证号：粤（2021）深圳市不动产权第0012345号",
            "面积：13,500.00平方米",
            "附记：2023年3月就上述不动产办理抵押登记，抵押权人为示例银行深圳分行，被担保债权数额3,200万元。",
        ]:
            doc.add_paragraph(line)
        tmp = Path(DATA) / "v2.docx"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(tmp))

        with open(tmp, "rb") as fh:
            r = client.post(
                f"/api/projects/{pid}/versions",
                files={"file": ("不动产权证-v2.docx", fh.read(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
                data={"group_id": str(target["id"]), "label": "V2"},
            )
        check(r.status_code == 200, f"上传新版本 HTTP {r.status_code}")
        info = r.json()
        check(info["diff"] and info["diff"]["changed"] >= 1, f"上传时识别版本变更 {info.get('diff')}")
        v2 = info["version_id"]

        d = client.get(f"/api/versions/{v1['id']}/diff/{v2}").json()
        kinds = {i["kind"] for i in d["items"]}
        check("changed" in kinds, f"版本对比含变更项 {d['summary']}")

        p1 = client.get(f"/api/versions/{v1['id']}").json()["paragraphs"]
        p2 = client.get(f"/api/versions/{v2}").json()["paragraphs"]
        common = set(x["uid"] for x in p1) & set(x["uid"] for x in p2)
        check(len(common) >= 3, f"跨版本沿用段落 uid {len(common)} 条（定位可追溯）")

        # 主体总表：三个板块聚合成 100 分
        subs = client.get("/api/subjects").json()["subjects"]
        check(any(x["subject"] == "云澜智造科技有限公司" and len(x["boards"]) == 3 for x in subs), "主体总表聚合 3 个板块")
        ss = client.get("/api/subjects/score", params={"name": "云澜智造科技有限公司"}).json()
        check(len(ss["dimensions"]) == 5, "主体评分 5 个维度")
        check(ss["coverage"] >= 0.8 and ss["grade"] in {"A", "B", "C", "D"}, f"主体总分 {ss['on_checked']} 等级 {ss['grade']} 覆盖 {ss['coverage']}")

        # 评分卡
        sc = client.get(f"/api/projects/{pid}/score")
        check(sc.status_code == 200 and "normalized" in sc.json(), "评分接口可用")
        check(sc.json()["coverage"] < 1, f"单板块项目覆盖不足（{sc.json()['coverage']}），不定级（{sc.json()['grade']}）")

        # 外部数据源：未配置时必须明确报错，不能静默失败
        r = client.post(f"/api/projects/{pid}/external-check")
        check(r.status_code == 400 and "外部数据" in r.json().get("detail", ""), f"未配置外部 API 时明确报错（HTTP {r.status_code}）")

        # 修改密码
        r = client.post("/api/auth/password", json={"old_password": "demo123456", "new_password": "demo654321"})
        check(r.status_code == 200, f"修改密码 HTTP {r.status_code}")
        client.post("/api/auth/logout")
        r = client.post("/api/auth/login", json={"email": "demo@example.com", "password": "demo654321"})
        check(r.status_code == 200, "新密码可登录")
        r = client.post("/api/auth/password", json={"old_password": "demo123456", "new_password": "another123"})
        check(r.status_code == 400, "原密码错误被拒")

    print()
    if FAIL:
        print(f"共 {TOTAL} 项检查，{len(FAIL)} 项失败")
        return 1
    print(f"共 {TOTAL} 项检查，全部通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
