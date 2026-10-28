"""量化评分卡：按 rubric 计算五个维度得分。

设计原则：
- 权重由用户指定；条目分值与扣分系数是初始标定，可调。
- 没做过对应核查的条目记为 N/A，不计入分母，避免把"没查"当成"满分"或"零分"。
- 每条扣分都回指具体 finding 或材料事实，便于复核。
"""
from __future__ import annotations

import json
from pathlib import Path

RUBRIC_PATH = Path(__file__).resolve().parent / "rules" / "scoring.json"
GRADES = [(85, "A"), (70, "B"), (55, "C"), (0, "D")]


def load_rubric() -> dict:
    return json.loads(RUBRIC_PATH.read_text(encoding="utf-8-sig"))


def _match(findings: list[dict], codes: list[str]) -> list[dict]:
    wanted = set(codes)
    return [f for f in findings if f.get("code") in wanted]


def _deduct(findings: list[dict], ratios: dict) -> tuple[float, list[str]]:
    """多条命中按比例累加，封顶 1.0。返回 (扣分比例, 原因列表)。"""
    total = 0.0
    reasons: list[str] = []
    for f in findings:
        level = f.get("risk_level") or f.get("level") or "medium"
        total += ratios.get(level, 0.5)
        reasons.append(f"{f.get('code')} {f.get('title')}（{level}）")
    return min(total, 1.0), reasons


def score_project(
    rubric: dict,
    *,
    analyzed: bool,
    board: str,
    findings: list[dict],
    external_findings: list[dict],
    external_present: bool,
    required_materials: list[str],
    present_materials: list[str],
    missing_count: int,
    versions: dict,
    qc: dict | None,
) -> dict:
    dims: list[dict] = []
    total_earned = 0.0
    total_applicable = 0.0

    for dim in rubric["dimensions"]:
        if dim.get("boards") and board != "all" and board not in dim["boards"]:
            dims.append({
                "id": dim["id"], "name": dim["name"], "points": dim["points"],
                "earned": 0.0, "applicable": 0.0, "rate": None,
                "items": [{"id": i["id"], "name": i["name"], "points": float(i["points"]),
                           "earned": 0.0, "applicable": False, "status": "na",
                           "reasons": ["本项目未覆盖该板块"]} for i in dim["items"]],
            })
            continue
        dim_earned = 0.0
        dim_applicable = 0.0
        items: list[dict] = []

        for item in dim["items"]:
            points = float(item["points"])
            source = item["source"]
            earned = 0.0
            applicable = True
            status = "na"
            reasons: list[str] = []

            if source == "findings":
                if not analyzed:
                    applicable = False
                    reasons.append("未执行核查")
                else:
                    hits = _match(findings, item.get("codes", []))
                    ratio, reasons = _deduct(hits, item.get("deduct", {}))
                    earned = points * (1 - ratio)
                    status = "full" if ratio == 0 else ("zero" if ratio >= 1 else "partial")

            elif source == "external":
                if not external_present:
                    applicable = False
                    reasons.append("未做联网核查")
                else:
                    hits = _match(external_findings, item.get("codes", []))
                    ratio, reasons = _deduct(hits, item.get("deduct", {}))
                    earned = points * (1 - ratio)
                    status = "full" if ratio == 0 else ("zero" if ratio >= 1 else "partial")

            elif source == "materials":
                required = item.get("required", [])
                if not any(r in required_materials for r in required):
                    applicable = False
                    reasons.append("本板块不要求该材料")
                else:
                    have = [r for r in required if r in present_materials]
                    ratio = len(have) / len(required)
                    earned = points * ratio
                    status = "full" if ratio >= 1 else ("zero" if ratio == 0 else "partial")
                    if ratio < 1:
                        reasons.append("缺少：" + "、".join(r for r in required if r not in have))

            elif source == "materials_all":
                if not required_materials:
                    applicable = False
                    reasons.append("无应备材料清单")
                else:
                    ratio = 1 - (missing_count / len(required_materials))
                    ratio = max(0.0, min(1.0, ratio))
                    earned = points * ratio
                    status = "full" if ratio >= 1 else ("zero" if ratio == 0 else "partial")
                    if missing_count:
                        reasons.append(f"缺失 {missing_count}/{len(required_materials)} 项")

            elif source == "versions":
                groups = versions.get("groups", 0)
                if not groups:
                    applicable = False
                    reasons.append("无版本记录")
                else:
                    penalty = 0.0
                    if versions.get("conflict"):
                        penalty += 0.3
                        reasons.append("材料存在冲突记载")
                    if versions.get("versions", 0) > groups:
                        penalty += 0.5
                        reasons.append(f"{versions['versions']} 个版本 / {groups} 个材料组，需确认以哪版为准")
                    penalty = min(penalty, 1.0)
                    earned = points * (1 - penalty)
                    status = "full" if penalty == 0 else ("zero" if penalty >= 1 else "partial")

            elif source == "coverage":
                total = len(findings)
                if not total:
                    applicable = False
                    reasons.append("无结论可评")
                else:
                    cited = sum(1 for f in findings if f.get("has_citation"))
                    ratio = cited / total
                    earned = points * ratio
                    status = "full" if ratio >= 1 else ("zero" if ratio == 0 else "partial")
                    reasons.append(f"{cited}/{total} 条结论有原文锚点")

            elif source == "qc":
                if not qc:
                    applicable = False
                    reasons.append("未执行质检")
                else:
                    checked = qc.get("checked", 0)
                    failed = qc.get("failed", 0)
                    notices = len(qc.get("notices", []))
                    if not checked:
                        applicable = False
                        reasons.append("质检无有效结论")
                    else:
                        ratio = (checked - failed - 0.5 * notices) / checked
                        ratio = max(0.0, min(1.0, ratio))
                        earned = points * ratio
                        status = "full" if ratio >= 1 else ("zero" if ratio == 0 else "partial")
                        reasons.append(f"阻断 {failed}、材料缺失提示 {notices}、共 {checked}")

            if applicable:
                dim_applicable += points
                dim_earned += earned
                total_applicable += points
                total_earned += earned

            items.append({
                "id": item["id"], "name": item["name"], "points": points,
                "earned": round(earned, 1), "applicable": applicable,
                "status": status if applicable else "na", "reasons": reasons,
            })

        dims.append({
            "id": dim["id"], "name": dim["name"], "points": dim["points"],
            "earned": round(dim_earned, 1), "applicable": round(dim_applicable, 1),
            "rate": round(dim_earned / dim_applicable, 3) if dim_applicable else None,
            "items": items,
        })

    rate = total_earned / total_applicable if total_applicable else 0.0
    coverage = total_applicable / rubric["total"] if rubric["total"] else 0.0
    normalized = round(total_earned / rubric["total"] * 100, 1) if rubric["total"] else 0.0
    on_checked = round(rate * 100, 1)
    # 覆盖不足时不给等级，避免用局部核查冒充整体结论
    grade = next(g for threshold, g in GRADES if on_checked >= threshold) if coverage >= 0.8 else "—"

    return {
        "total_points": rubric["total"],
        "earned": round(total_earned, 1),
        "applicable": round(total_applicable, 1),
        "coverage": round(coverage, 3),
        "normalized": normalized,
        "on_checked": on_checked,
        "grade": grade,
        "dimensions": dims,
        "note": "按已核查项归一化；N/A 项不计入分母。分值系数为初始标定，需用结果数据校准。",
    }
