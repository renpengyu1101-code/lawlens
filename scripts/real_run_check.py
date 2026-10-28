"""真实模型端到端核查（走 HTTP API，不碰 UI）。

用法（在 diligence-platform 目录，需先启动一个实例并配置 DEEPSEEK_API_KEY）：
    .venv\\Scripts\\python.exe scripts\\real_run_check.py --base http://127.0.0.1:8020 --filter 资产

--filter 按文件名前缀筛选材料，用于控制第一次真跑的调用量与费用。
输出：每一步的时间线、总耗时、风险条数、带锚点的结论数、报告大小。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import httpx

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples" / "虚构材料-澜川精密-2026-10"
TERMINAL = {"done", "pending_review", "failed", "awaiting_materials"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8200")
    ap.add_argument("--filter", default="", help="只上传文件名包含该子串的材料")
    ap.add_argument("--dir", default="", help="材料目录（默认 samples/虚构材料-澜川精密-2026-10）")
    ap.add_argument("--ext", default="docx,pdf", help="只上传这些扩展名")
    ap.add_argument("--timeout", type=int, default=900)
    args = ap.parse_args()

    src = Path(args.dir) if args.dir else SAMPLES
    exts = {("." + e.strip().lstrip(".")).lower() for e in args.ext.split(",") if e.strip()}
    files = sorted(p for p in src.glob("*") if p.suffix.lower() in exts and args.filter in p.name)
    if not files:
        print(f"[FAIL] 没有匹配的材料：{src} *{args.filter}*")
        return 1
    print(f"材料 {len(files)} 份：{[f.name for f in files]}")

    email = f"real{int(time.time())}@example.com"
    with httpx.Client(base_url=args.base, timeout=120) as c:
        r = c.post("/api/auth/register", json={"email": email, "password": "demo123456"})
        if r.status_code != 200:
            print(f"[FAIL] 注册 {r.status_code}: {r.text[:200]}")
            return 1

        r = c.post("/api/projects", json={
            "title": f"真模型核查（{args.filter or '全部'}）",
            "subject_name": "澜川精密科技有限公司",
            "brief": "核查资产权属、劳动用工与股权退出安排",
            "board": "all",
            "is_demo": True,
        })
        r.raise_for_status()
        pid = r.json()["id"]
        print(f"项目 #{pid}")

        for f in files:
            with f.open("rb") as fh:
                up = c.post(f"/api/projects/{pid}/documents",
                            files=[("files", (f.name, fh.read(), "application/octet-stream"))])
            if up.status_code != 200:
                print(f"[FAIL] 上传 {f.name} {up.status_code}: {up.text[:200]}")
                return 1
        print(f"上传完成，开始核查…")

        t0 = time.time()
        r = c.post(f"/api/projects/{pid}/run", headers={})
        if r.status_code != 200:
            print(f"[FAIL] 发起核查 {r.status_code}: {r.text[:300]}")
            return 1

        seen = set()
        status = "running"
        while time.time() - t0 < args.timeout:
            time.sleep(2)
            prog = c.get(f"/api/projects/{pid}/progress").json()
            status = prog["status"]
            for s in prog["steps"]:
                key = s["id"]
                if key in seen or s["status"] == "running":
                    continue
                seen.add(key)
                print(f"  [{time.time() - t0:6.1f}s] {s['status']:5} {s['agent']:8} "
                      f"{(s['board'] or '-'):12} {s['text'][:60]}")
            if status in TERMINAL:
                break
        elapsed = time.time() - t0

        detail = c.get(f"/api/projects/{pid}").json()
        findings = detail.get("findings") or []
        with_cite = [f for f in findings if any(x.get("document_id") for x in (f.get("citations") or []))]
        report = c.get(f"/api/projects/{pid}/report")

    print("")
    print(f"状态：{status}  总耗时：{elapsed:.1f}s")
    print(f"风险：{len(findings)} 条，其中带原文锚点 {len(with_cite)} 条")
    for f in findings[:6]:
        print(f"  - [{f.get('risk_level')}] {f.get('code')} {f.get('title')[:40]}")
    print(f"报告：HTTP {report.status_code}，{len(report.content)} 字节")
    if findings and len(with_cite) < len(findings):
        print("[WARN] 有结论没有原文锚点，需检查提示词")
    return 0 if status in {"done", "pending_review"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
