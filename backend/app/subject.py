"""按主体汇总评分：把同一家公司的资产 / 劳动 / 股权三个板块项目合成一张 100 分表。

规则：
- A/B/C 三个维度分别取自对应板块项目的评分；
- D/E 两个维度按该主体的全部项目合并计算（材料、版本、结论、质检、外部核查取并集）；
- 缺哪个板块，哪个维度记 N/A，不按满分或零分处理。
"""
from __future__ import annotations

import json

from . import agents, scoring

ACTIVE = {"done", "pending_review", "needs_rework"}
BOARD_DIM = {"asset": "A", "labor": "B", "equity": "C"}


def project_inputs(conn, project: dict) -> dict:
    pid = project["id"]
    findings = [dict(r) for r in conn.execute(
        "SELECT * FROM findings WHERE project_id = ?", (pid,)).fetchall()]
    for f in findings:
        f["has_citation"] = conn.execute(
            "SELECT 1 FROM citations WHERE finding_id = ? AND document_id IS NOT NULL LIMIT 1",
            (f["id"],)).fetchone() is not None

    docs = [dict(r) for r in conn.execute(
        "SELECT filename, text FROM documents WHERE project_id = ?", (pid,)).fetchall()]
    qc_row = conn.execute(
        "SELECT detail FROM qc_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    ext_row = conn.execute(
        "SELECT findings FROM external_checks WHERE project_id = ? ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    groups = conn.execute(
        "SELECT COUNT(*) AS c FROM document_groups WHERE project_id = ?", (pid,)).fetchone()["c"]
    versions = conn.execute(
        "SELECT COUNT(*) AS c FROM document_versions v JOIN document_groups g ON g.id = v.group_id"
        " WHERE g.project_id = ?", (pid,)).fetchone()["c"]

    required = [t for t, _ in agents.BOARD_REQUIRED.get(project["board"], [])]
    corpus = "\n".join((d["text"] or "") + " " + d["filename"] for d in docs)
    present = [t for t in required if any(k in corpus for k in agents.MATERIAL_KEYWORDS.get(t, []))]
    missing = json.loads(project["missing"]) if project.get("missing") else []

    return {
        "analyzed": project["status"] in ACTIVE,
        "findings": findings,
        "external_findings": json.loads(ext_row["findings"]) if ext_row else [],
        "external_present": bool(ext_row),
        "required_materials": required,
        "present_materials": present,
        "missing_count": len(missing),
        "versions": {"groups": groups, "versions": versions,
                     "conflict": any(f["code"] == "AST-06" for f in findings)},
        "qc": json.loads(qc_row["detail"]) if qc_row else None,
    }


def _na_dimension(dim: dict, reason: str) -> dict:
    return {
        "id": dim["id"], "name": dim["name"], "points": dim["points"],
        "earned": 0.0, "applicable": 0.0, "rate": None,
        "items": [{"id": i["id"], "name": i["name"], "points": float(i["points"]),
                   "earned": 0.0, "applicable": False, "status": "na", "reasons": [reason]}
                  for i in dim["items"]],
    }


def _merge(conn, projects: list[dict], rubric: dict) -> dict:
    """合并全部项目，用于计算 D / E 两个维度。"""
    findings: list[dict] = []
    required: list[str] = []
    present: list[str] = []
    groups = versions = missing = 0
    qc_total = {"checked": 0, "failed": 0, "notices": []}
    external_findings: list[dict] = []
    external_present = False

    for project in projects:
        data = project_inputs(conn, project)
        findings.extend(data["findings"])
        for t in data["required_materials"]:
            if t not in required:
                required.append(t)
        for t in data["present_materials"]:
            if t not in present:
                present.append(t)
        groups += data["versions"]["groups"]
        versions += data["versions"]["versions"]
        missing += data["missing_count"]
        if data["qc"]:
            qc_total["checked"] += data["qc"].get("checked", 0)
            qc_total["failed"] += data["qc"].get("failed", 0)
            qc_total["notices"].extend(data["qc"].get("notices", []))
        if data["external_present"]:
            external_present = True
            external_findings.extend(data["external_findings"])

    return scoring.score_project(
        rubric,
        analyzed=any(p["status"] in ACTIVE for p in projects),
        board="all",
        findings=findings,
        external_findings=external_findings,
        external_present=external_present,
        required_materials=required,
        present_materials=present,
        missing_count=missing,
        versions={"groups": groups, "versions": versions,
                  "conflict": any(f["code"] == "AST-06" for f in findings)},
        qc=qc_total if qc_total["checked"] else None,
    )


def score_subject(conn, subject: str, projects: list[dict]) -> dict:
    rubric = scoring.load_rubric()
    by_board: dict[str, dict] = {}
    for p in sorted(projects, key=lambda x: x["id"]):
        by_board.setdefault(p["board"], p)

    dims: list[dict] = []
    for board in ("asset", "labor", "equity"):
        dim_id = BOARD_DIM[board]
        dim_def = next(d for d in rubric["dimensions"] if d["id"] == dim_id)
        project = by_board.get(board)
        if project is None:
            dims.append(_na_dimension(dim_def, "未建立该板块项目"))
            continue
        result = scoring.score_project(rubric, board=board, **project_inputs(conn, project))
        dims.append(next(d for d in result["dimensions"] if d["id"] == dim_id))

    merged = _merge(conn, projects, rubric)
    dims.extend(d for d in merged["dimensions"] if d["id"] in {"D", "E"})

    total_points = rubric["total"]
    earned = sum(d["earned"] for d in dims)
    applicable = sum(d["applicable"] for d in dims)
    coverage = applicable / total_points if total_points else 0
    on_checked = (earned / applicable * 100) if applicable else 0.0
    normalized = earned / total_points * 100 if total_points else 0.0
    grade = "—"
    if coverage >= 0.8:
        grade = next(g for threshold, g in scoring.GRADES if on_checked >= threshold)

    return {
        "subject": subject,
        "total_points": total_points,
        "earned": round(earned, 1),
        "applicable": round(applicable, 1),
        "coverage": round(coverage, 3),
        "on_checked": round(on_checked, 1),
        "normalized": round(normalized, 1),
        "grade": grade,
        "boards": sorted(by_board),
        "dimensions": dims,
        "note": "A/B/C 取自对应板块项目，D/E 按全部项目合并；缺失板块记 N/A，不计入分母。",
    }
