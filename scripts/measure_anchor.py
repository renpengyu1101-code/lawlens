"""测量锚定率与溯源率（基于库里已有项目，不需要重新跑模型）。

口径
  锚定率  = 至少带一条有效锚点的结论数 / 结论总数
            （有效锚点 = citation.document_id 指向本项目的材料）
  溯源率  = 能在原文中定位到引文的锚点数 / 锚点总数
            （定位 = 去掉空白后，引文出现在该材料的正文里；并核对页码一致）
  结论级溯源率 = 全部锚点都能定位的结论数 / 带锚点的结论数

用法：
  python scripts/measure_anchor.py            # 默认 backend/data/app.db
  python scripts/measure_anchor.py path.db
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.parsers import page_of_offset  # noqa: E402

DB = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "backend" / "data" / "app.db"


def norm(text: str) -> str:
    """去掉所有空白与常见标点差异，用于宽松匹配。"""
    text = re.sub(r"\s+", "", text or "")
    return text.replace("「", "").replace("」", "").replace("“", "").replace("”", "")


def locate(quote: str, doc_text: str) -> tuple[bool, int | None]:
    """返回 (是否能在原文中找到, 所在页码)。"""
    q = norm(quote)
    if len(q) < 4:
        return False, None
    body = norm(doc_text)
    pos = body.find(q)
    if pos < 0:
        # 允许引文被截断（报告里最多存 300 字）
        head = q[:30]
        pos = body.find(head) if len(head) >= 8 else -1
        if pos < 0:
            return False, None
    # norm 后的偏移与原文偏移不同，这里用引文首句在原文里重新定位
    raw = (quote or "").strip()[:20]
    raw_pos = doc_text.find(raw)
    page = page_of_offset(doc_text, raw_pos) if raw_pos >= 0 else None
    return True, page


def main() -> int:
    if not DB.exists():
        print(f"数据库不存在：{DB}")
        return 1
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    projects = [r["id"] for r in conn.execute("SELECT id FROM projects ORDER BY id")]
    total_findings = total_anchored = 0
    total_cites = located_cites = page_ok = 0
    findings_all_located = 0
    per_project = []

    for pid in projects:
        docs = {r["id"]: (r["text"] or "") for r in conn.execute(
            "SELECT id, text FROM documents WHERE project_id = ?", (pid,))}
        finds = list(conn.execute("SELECT id, code, qc FROM findings WHERE project_id = ?", (pid,)))
        if not finds or not docs:
            continue
        p_find = len(finds)
        p_anchored = 0
        p_all_ok = 0
        for f in finds:
            cites = list(conn.execute(
                "SELECT document_id, page, quote FROM citations WHERE finding_id = ?", (f["id"],)))
            valid = [c for c in cites if c["document_id"] in docs]
            if valid:
                p_anchored += 1
            ok_count = 0
            for c in valid:
                found, page = locate(c["quote"], docs[c["document_id"]])
                if found:
                    ok_count += 1
                    located_cites += 1
                    if c["page"] and page and int(c["page"]) == int(page):
                        page_ok += 1
                total_cites += 1
            if valid and ok_count == len(valid):
                p_all_ok += 1
        total_findings += p_find
        total_anchored += p_anchored
        findings_all_located += p_all_ok
        per_project.append((pid, p_find, p_anchored, p_all_ok))

    print(f"数据库：{DB}")
    print(f"有结论的项目：{len(per_project)} 个")
    print()
    print(f"结论总数：{total_findings}")
    print(f"锚定率（有有效锚点的结论）：{total_anchored}/{total_findings} = "
          f"{(total_anchored / total_findings * 100 if total_findings else 0):.1f}%")
    print()
    print(f"锚点总数：{total_cites}")
    print(f"溯源率（引文能在原文定位）：{located_cites}/{total_cites} = "
          f"{(located_cites / total_cites * 100 if total_cites else 0):.1f}%")
    print(f"其中页码一致：{page_ok}/{located_cites} = "
          f"{(page_ok / located_cites * 100 if located_cites else 0):.1f}%")
    print()
    print(f"结论级溯源率（该结论全部锚点都能定位）：{findings_all_located}/{total_anchored} = "
          f"{(findings_all_located / total_anchored * 100 if total_anchored else 0):.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
