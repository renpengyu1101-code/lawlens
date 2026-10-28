"""复核触发规则（律师复核闸门）。

三类触发条件，命中任一即要求律师复核：
  A. 材料版本 / 时间线 / 矛盾观点 / 证据缺失
  B. 关键法律依据 / 责任主体 / 核心结论是否成立
  C. 整改、协商或争议处理方案 / 金额计算口径

原则：每个触发都给出具体原因与可回溯证据，不做"因为模型不确定"这种空泛判断。
"""
from __future__ import annotations

CATEGORY = {
    "A": "材料版本、时间线与证据",
    "B": "法律依据、责任主体与结论",
    "C": "处理方案与金额口径",
}


def _cite(item: dict, limit: int = 80) -> str:
    return f"《{item.get('filename', '?')}》p{item.get('page', '?')}：{(item.get('quote') or '')[:limit]}"


def evaluate(project: dict, findings: list[dict], extracted: dict,
             qc_result: dict, version_stats: dict) -> list[dict]:
    """返回触发项列表；空列表表示无需复核。"""
    triggers: list[dict] = []

    def add(code: str, title: str, detail: str, evidence: list[str]) -> None:
        triggers.append({
            "code": code,
            "category": CATEGORY[code[0]],
            "title": title,
            "detail": detail,
            "evidence": evidence[:5],
        })

    # ---------------- A 材料版本 / 时间线 / 矛盾 / 证据 ----------------
    groups = version_stats.get("groups", 0)
    versions = version_stats.get("versions", 0)
    if versions > groups:
        add("A1", "同一材料存在多个版本",
            f"共 {groups} 个材料组、{versions} 个版本；需确认以哪一版为准，以及版本切换对结论的影响。",
            [f"多版本材料组 {versions - groups} 个"])

    conflicts = extracted.get("conflicts") or []
    if conflicts:
        field = conflicts[0]["field"]
        values = "、".join(v["value"] for v in conflicts[0]["values"])[:120]
        add("A2", "材料之间存在矛盾记载",
            f"字段「{field}」在不同材料中出现多个取值：{values}。需确认哪一份为准。",
            [_cite(it) for v in conflicts[0]["values"] for it in v["items"][:1]])

    notices = qc_result.get("notices") or []
    missing_evidence = [f for f in findings if not any(c.get("document_id") for c in f["citations"])]
    if notices or missing_evidence:
        add("A3", "证据缺失或需要补充",
            f"有 {len(missing_evidence)} 条结论没有原文锚点，另有 {len(notices)} 条因材料缺失无法验证。"
            "需补充材料后再核。",
            [f"{f['code']} {f['title']}" for f in missing_evidence[:3]])

    if qc_result.get("failed"):
        add("A4", "质检存在阻断项",
            f"质检阻断 {qc_result['failed']} 条（证据原文无法定位或规则缺失），不能直接采信。",
            [f"{i['code']}：{i['reason']}" for i in qc_result.get("issues", [])[:3]])

    # ---------------- B 法律依据 / 责任主体 / 结论 ----------------
    no_basis = [f for f in findings if not f.get("rule_ref")]
    if no_basis:
        add("B1", "结论缺少可核实的法律依据",
            f"{len(no_basis)} 条结论引用的核查要点尚未挂接规范依据（条文/规则出处），"
            "需律师确认结论是否成立。",
            [f"{f['code']} {f['title']}" for f in no_basis[:3]])

    if not (project.get("subject_name") or "").strip():
        add("B2", "责任主体未明确",
            "项目未填写拟上市主体全称，无法判断权属、义务与责任归属。",
            ["项目 subject_name 为空"])

    high = [f for f in findings if f["risk_level"] == "high"]
    if high:
        add("B3", "存在高风险结论，需确认是否成立",
            f"共 {len(high)} 条高风险结论，涉及是否构成上市障碍，需律师逐条确认。",
            [f"{f['code']} {f['title']}" for f in high[:3]])

    # ---------------- C 处理方案 / 金额口径 ----------------
    actionable = [f for f in findings if (f.get("advice") or "").strip()]
    if actionable:
        add("C1", "整改或处置方案待确认",
            f"{len(actionable)} 条结论给出了整改建议，需确定采用整改、协商还是争议处理，并明确责任人与时限。",
            [f"{f['code']}：{f['advice'][:40]}" for f in actionable[:3]])

    amount_items = [i for i in extracted.get("items", [])
                    if i["field"] in {"金额", "认缴出资", "实缴出资", "注册资本"}]
    if amount_items:
        add("C2", "金额计算口径待确认",
            f"抽取到 {len(amount_items)} 处金额类数据，需确认口径（含税/不含税、认缴/实缴、"
            "是否含违约金与利息）。",
            [_cite(i) for i in amount_items[:3]])

    return triggers
