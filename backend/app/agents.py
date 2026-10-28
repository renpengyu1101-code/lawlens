"""四个 Agent：意图识别 → 资料抽取 → 分析 → 质检。

未配置模型时走启发式实现（MOCK），界面标注"演示模式"。
无论哪种模式，结论都必须带证据锚点；质检对锚点做真实校验。
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from . import llm
from .llm import LLMError, chat_json

RULES_DIR = Path(__file__).resolve().parent / "rules"

# 材料类型 → 识别关键词（用于缺料检查）
MATERIAL_KEYWORDS = {
    "不动产权证": ["不动产权证", "不动产权证书", "房产证", "土地使用权证"],
    "土地使用权出让合同": ["出让合同", "土地出让", "国有建设用地使用权出让"],
    "租赁合同": ["租赁合同", "租赁协议", "房屋租赁"],
    "经营许可证": ["许可证", "经营许可", "资质证书", "备案回执", "批准证书"],
    "专利证书": ["专利证书", "发明专利", "实用新型专利", "专利号"],
    "商标注册证": ["商标注册证", "注册商标", "商标注册号"],
    "抵押或查封记录": ["抵押", "他项权", "查封", "冻结"],
    "股权结构文件": ["股权结构", "股东名册", "持股", "章程"],
    "劳动合同": ["劳动合同", "员工名册", "在职员工"],
    "社保缴纳明细": ["社保", "社会保险", "缴纳人数"],
    "劳务派遣协议": ["劳务派遣", "派遣"],
    "劳动争议文书": ["仲裁", "诉讼", "劳动争议"],
    "公司章程": ["公司章程", "章程", "注册资本"],
    "增资协议": ["增资", "投资协议"],
    "股东协议": ["股东协议", "对赌", "回购"],
    "出资凭证": ["实缴", "出资", "验资"],
    "工商变更记录": ["工商变更", "股权转让", "股东会决议"],
}

# 每个板块的必需材料（用于执行前的缺料检查）
BOARD_REQUIRED = {
    "asset": [
        ("不动产权证", "AST-01/AST-02 权属与权证完整性"),
        ("土地使用权出让合同", "AST-02 土地取得方式"),
        ("租赁合同", "AST-04 经营场所合法性"),
        ("经营许可证", "AST-05 资质有效性"),
        ("专利证书", "AST-06 知识产权权属"),
        ("商标注册证", "AST-06 商标权属"),
    ],
    "labor": [
        ("劳动合同", "LAB-01 书面劳动合同签订"),
        ("社保缴纳明细", "LAB-02 社保与公积金缴纳"),
        ("劳务派遣协议", "LAB-03 派遣用工合规"),
        ("劳动争议文书", "LAB-06 历史争议情况"),
    ],
    "equity": [
        ("公司章程", "EQT-01 出资与股权结构"),
        ("出资凭证", "EQT-01 认缴与实缴"),
        ("增资协议", "EQT-03 对赌与回购"),
        ("股东协议", "EQT-04/EQT-06 特殊权利"),
        ("工商变更记录", "EQT-05 股权变动程序"),
    ],
}

DEFAULT_REQUIRED = BOARD_REQUIRED["asset"]



def load_rules(board: str = "asset") -> dict:
    path = RULES_DIR / f"{board}.json"
    if not path.exists():
        return {"board": board, "checkpoints": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _doc_text(doc: dict) -> str:
    return doc.get("text") or ""


def _pages(text: str):
    """按 [[PAGE n]] 切页，返回 (page, page_text)。"""
    parts = re.split(r"\[\[PAGE (\d+)\]\]", text)
    if len(parts) == 1:
        yield 1, text
        return
    for i in range(1, len(parts), 2):
        page = int(parts[i])
        body = parts[i + 1] if i + 1 < len(parts) else ""
        yield page, body


# ---------------------------------------------------------------- Agent A
def build_task_spec(project: dict, docs: list[dict], rules: dict, cfg: dict | None = None) -> dict:
    """自然语言需求 → 结构化任务单（技术语言）。"""
    checks = [
        {"id": cp["id"], "topic": cp["topic"], "check_point": cp["check_point"]}
        for cp in rules.get("checkpoints", [])
    ]
    required = [{"type": t, "needed_for": why} for t, why in BOARD_REQUIRED.get(project["board"], [])]

    return {
        "board": project["board"],
        "subject": project.get("subject_name") or "",
        "objective": project.get("brief") or "核查核心资产权属与经营基础的合规风险",
        "checks": checks,
        "required_materials": required,
        "output": {"format": "风险清单 + 整改建议 + 报告（docx）", "evidence": "每条结论须附文件、页码、原文"},
        "mode": "llm" if llm.resolve(cfg)["enabled"] else "mock",
    }


def check_missing(spec: dict, docs: list[dict]) -> list[dict]:
    """缺料检查：在调用抽取/分析之前完成，避免无效调用。"""
    corpus = "\n".join([_doc_text(d) + " " + d["filename"] for d in docs])
    missing = []
    for item in spec["required_materials"]:
        kws = MATERIAL_KEYWORDS.get(item["type"], [])
        hit = any(kw in corpus for kw in kws)
        if not hit:
            missing.append({"material": item["type"], "needed_for": item["needed_for"]})
    return missing


# ---------------------------------------------------------------- Agent B
_PATTERNS = [
    ("权利人", re.compile(r"(?:专利权人|商标权人|著作权人|权利人|受让人|申请人)[^\n:：]{0,6}[:：]\s*([^\n，,；;]{2,50})")),
    ("证号", re.compile(r"(不动产权证号|权证号|专利号|商标注册号|证书编号)[^\n:：]{0,4}[:：]?\s*([A-Za-z0-9\-（）().\u4e00-\u9fa5]{4,40})")),
    ("面积", re.compile(r"(\d[\d,\.]{0,12})\s*(平方米|㎡|平米)")),
    ("金额", re.compile(r"([\d,]{3,}(?:\.\d+)?)\s*(元|万元)")),
    ("出租方", re.compile(r"出租方[^\n:：]{0,6}[:：]\s*([^\n，,；;]{2,50})")),
    ("承租方", re.compile(r"承租方[^\n:：]{0,6}[:：]\s*([^\n，,；;]{2,50})")),
    ("有效期", re.compile(r"(?:有效期|届满日期|到期日)[^\d]{0,6}(\d{4})[-年/\.](\d{1,2})[-月/\.](\d{1,2})")),
    # 劳动用工
    ("员工人数", re.compile(r"(?:在职)?(?:员工|职工)[^\d\n]{0,8}(\d{1,6})\s*人")),
    ("社保人数", re.compile(r"(?:社保|社会保险|缴纳)[^\d\n]{0,8}(\d{1,6})\s*人")),
    ("派遣人数", re.compile(r"派遣[^\d\n]{0,8}(\d{1,6})\s*人")),
    ("合同签订率", re.compile(r"签订率[^\d\n]{0,6}(\d{1,3}(?:\.\d+)?)\s*%")),
    # 股权
    ("注册资本", re.compile(r"注册资本[^\d\n]{0,8}([\d,\.]{1,15})\s*万元")),
    ("认缴出资", re.compile(r"认缴[^\d\n]{0,8}([\d,\.]{1,15})\s*万元")),
    ("实缴出资", re.compile(r"实缴[^\d\n]{0,8}([\d,\.]{1,15})\s*万元")),
    ("持股比例", re.compile(r"持股[^\d\n]{0,6}(\d{1,3}(?:\.\d+)?)\s*%")),
]

CONFLICT_FIELDS = {"权利人"}



def _line_of(text: str, start: int, end: int) -> str:
    left = text.rfind("\n", 0, start) + 1
    right = text.find("\n", end)
    right = len(text) if right == -1 else right
    return text[left:right].strip()


def _heuristic_extract(doc: dict) -> list[dict]:
    items: list[dict] = []
    for page, page_text in _pages(_doc_text(doc)):
        for field, pattern in _PATTERNS:
            for m in pattern.finditer(page_text):
                if field == "证号":
                    value = m.group(2).strip()
                elif field == "有效期":
                    value = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                else:
                    value = m.group(1).strip()
                items.append(
                    {
                        "field": field,
                        "value": value,
                        "document_id": doc["id"],
                        "filename": doc["filename"],
                        "page": page,
                        "quote": _line_of(page_text, m.start(), m.end()),
                        "confidence": 0.75,
                        "source": "regex",
                    }
                )
    # 关键词类标记
    flags = {
        "存在抵押": ["抵押", "他项权"],
        "存在查封": ["查封", "冻结"],
        "存在质押": ["质押"],
        "存在许可": ["许可使用", "独占许可", "排他许可"],
        "存在对赌": ["对赌", "业绩承诺"],
        "存在回购义务": ["回购"],
        "存在代持": ["代持", "代持协议"],
        "存在优先权": ["优先购买", "优先认购", "反稀释", "清算优先"],
        "存在劳动争议": ["仲裁", "诉讼", "劳动争议"],
        "存在竞业限制": ["竞业限制"],
    }
    for page, page_text in _pages(_doc_text(doc)):
        for field, kws in flags.items():
            for kw in kws:
                idx = page_text.find(kw)
                if idx >= 0:
                    items.append(
                        {
                            "field": field,
                            "value": "是",
                            "document_id": doc["id"],
                            "filename": doc["filename"],
                            "page": page,
                            "quote": _line_of(page_text, idx, idx + len(kw)),
                            "confidence": 0.7,
                            "source": "regex",
                        }
                    )
                    break
    return items


# ---------------------------------------------------------------- 字段词表（约束抽取，别让规则层失配）
# 规则层按固定字段名判定（见 _analyze_asset / _analyze_labor / _analyze_equity），
# 所以抽取必须产出这些名字；自由发挥的字段名会让结论直接漏掉。
FIELD_VOCAB = {
    "asset": [
        ("权利人", "权证、证书或合同上登记的权属人全称"),
        ("证号", "不动产权证号、专利号、商标注册号等证书编号"),
        ("面积", "不动产或场地面积，带单位"),
        ("金额", "合同中出现的金额，带单位"),
        ("出租方", "租赁合同的出租方全称"),
        ("承租方", "租赁合同的承租方全称"),
        ("有效期", "证书、许可证或合同的到期日"),
        ("存在抵押", "仅在材料明确记载抵押权时输出，值为「是」"),
        ("存在查封", "仅在材料明确记载查封时输出，值为「是」"),
        ("存在质押", "仅在材料明确记载质押时输出，值为「是」"),
    ],
    "labor": [
        ("员工人数", "在职员工总数，值为数字加「人」"),
        ("社保人数", "社保缴纳人数，值为数字加「人」"),
        ("派遣人数", "劳务派遣用工人数"),
        ("合同签订率", "书面劳动合同签订比例，值为百分比"),
        ("存在劳动争议", "仅在材料明确记载仲裁、诉讼或争议时输出，值为「是」"),
        ("存在竞业限制", "仅在材料明确记载竞业限制约定时输出，值为「是」"),
    ],
    "equity": [
        ("注册资本", "注册资本金额，带单位"),
        ("认缴出资", "股东认缴出资额"),
        ("实缴出资", "股东实缴出资额"),
        ("持股比例", "股东持股比例，值为百分比"),
        ("存在对赌", "仅在材料明确记载对赌或业绩承诺时输出，值为「是」"),
        ("存在回购义务", "仅在材料明确记载回购义务时输出，值为「是」"),
        ("存在代持", "仅在材料明确记载股权代持时输出，值为「是」"),
        ("存在优先权", "仅在材料明确记载优先购买/优先认购/领售等特殊权利时输出，值为「是」"),
    ],
}

# 模型换了说法时的兜底映射（顺序有意义：先具体后笼统）
FIELD_SYNONYMS = [
    ("代持", "存在代持"),
    ("对赌", "存在对赌"),
    ("业绩承诺", "存在对赌"),
    ("回购", "存在回购义务"),
    ("优先", "存在优先权"),
    ("领售", "存在优先权"),
    ("查封", "存在查封"),
    ("抵押", "存在抵押"),
    ("质押", "存在质押"),
    ("劳动争议", "存在劳动争议"),
    ("仲裁", "存在劳动争议"),
    ("竞业", "存在竞业限制"),
    ("签订率", "合同签订率"),
    ("社保", "社保人数"),
    ("派遣", "派遣人数"),
    ("员工", "员工人数"),
    ("职工", "员工人数"),
    ("在职", "员工人数"),
    ("认缴", "认缴出资"),
    ("实缴", "实缴出资"),
    ("注册资本", "注册资本"),
    ("持股", "持股比例"),
    ("股权比例", "持股比例"),
    ("出租", "出租方"),
    ("承租", "承租方"),
    ("权利人", "权利人"),
    ("所有权人", "权利人"),
    ("权属人", "权利人"),
    ("证号", "证号"),
    ("证书编号", "证号"),
    ("面积", "面积"),
    ("有效期", "有效期"),
    ("到期", "有效期"),
    ("金额", "金额"),
]


def _field_prompt(board: str) -> str:
    rows = FIELD_VOCAB.get(board)
    if rows is None:  # 旧项目 board 可能是 all 或空：给全部字段，别让抽取失去约束
        rows = [row for group in FIELD_VOCAB.values() for row in group]
    if not rows:
        return ""
    lines = "\n".join(f"- {name}：{hint}" for name, hint in rows)
    return (
        "\n\n字段名必须从下面这张表里选，用字要完全一致；确实归类不了的才用「其他:简短描述」。\n"
        f"{lines}\n"
        "凡是「存在××」这类字段：只有材料明确记载时才输出，值为「是」；材料没写就不要输出该字段，"
        "不要输出「否」或「无」。"
    )


def _canonical_field(board: str, raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        return ""
    if name.startswith("其他:"):
        return name
    allowed = {n for n, _ in FIELD_VOCAB.get(board, [])}
    if not allowed:  # board 不在词表里时，按全部字段判定
        allowed = {n for group in FIELD_VOCAB.values() for n, _ in group}
    if name in allowed:
        return name
    for keyword, target in FIELD_SYNONYMS:
        if keyword in name:
            return target
    return name


def _llm_extract(doc: dict, spec: dict, cfg: dict | None = None) -> list[dict]:
    text = _doc_text(doc)[:12000]
    board = spec.get("board", "asset")
    system = (
        "你是法律尽调资料抽取助手。只从给定文本中抽取事实，不得推测、补全或改写。"
        "每个字段必须给出原文片段 quote 与页码 page；找不到就返回空数组。"
        "输出 JSON：{\"items\":[{\"field\":\"\",\"value\":\"\",\"page\":1,\"quote\":\"\"}]}"
        + _field_prompt(board)
    )
    user = f"文件编号 {doc['id']}，文件名 {doc['filename']}。核查要点：{json.dumps(spec['checks'], ensure_ascii=False)}\n\n正文：\n{text}"
    data = _run_json(system, user, cfg)
    items = []
    for it in data.get("items", []):
        field = _canonical_field(board, str(it.get("field", "")))
        value = str(it.get("value", ""))[:200]
        if not field or not value:
            continue
        items.append(
            {
                "field": field[:40],
                "value": value,
                "document_id": doc["id"],
                "filename": doc["filename"],
                "page": it.get("page"),
                "quote": str(it.get("quote", ""))[:400],
                "confidence": 0.9,
                "source": "llm",
            }
        )
    return items


def extract(docs: list[dict], spec: dict, cfg: dict | None = None) -> dict:
    items: list[dict] = []
    for doc in docs:
        if not llm.resolve(cfg)["enabled"]:
            items.extend(_heuristic_extract(doc))
        else:
            try:
                items.extend(_llm_extract(doc, spec, cfg))
            except LLMError:
                items.extend(_heuristic_extract(doc))

    # 冲突：同字段出现多个不同取值
    conflicts = []
    by_field: dict[str, dict[str, list[dict]]] = {}
    for it in items:
        by_field.setdefault(it["field"], {}).setdefault(it["value"], []).append(it)
    for field, values in by_field.items():
        if field not in CONFLICT_FIELDS:
            continue
        if len(values) > 1:
            conflicts.append(
                {
                    "field": field,
                    "values": [{"value": v, "items": vs} for v, vs in values.items()],
                }
            )
    gaps = [] if items else [{"gap": "未抽取到任何字段", "hint": "可能为扫描件或版式异常，需人工录入"}]
    return {"items": items, "conflicts": conflicts, "gaps": gaps}


# ---------------------------------------------------------------- Agent C
def _finding(code, level, title, fact, advice, citations, rule=None) -> dict:
    return {
        "code": code,
        "risk_level": level,
        "title": title,
        "fact": fact,
        "rule_id": rule["id"] if rule else None,
        "rule_ref": (rule or {}).get("rule_ref"),
        "advice": advice,
        "citations": citations,
        "status": "open",
    }


def _cite(item: dict) -> dict:
    return {
        "document_id": item["document_id"],
        "page": item["page"],
        "quote": item["quote"],
        "filename": item["filename"],
    }


def analyze(project: dict, extracted: dict, rules: dict) -> list[dict]:
    """按板块分派：三个板块各有自己的判读规则（均来自办案经验，规范依据待补）。"""
    board = project.get("board")
    if board == "labor":
        return _analyze_labor(project, extracted, rules)
    if board == "equity":
        return _analyze_equity(project, extracted, rules)
    return _analyze_asset(project, extracted, rules)


_NUM_RE = re.compile(r"-?\d[\d,]*(?:\.\d+)?")
_DATE_RE = re.compile(r"(\d{4})\s*[-/年\.]\s*(\d{1,2})\s*[-/月\.]\s*(\d{1,2})")


def _num(items: list[dict]) -> float | None:
    """取第一个能解析的数值。模型常写成「486 人」「92.4%」「3,480 万元」，所以只取数字部分。"""
    for it in items:
        text = str(it.get("value") or "").replace(" ", "")
        match = _NUM_RE.search(text)
        if not match:
            continue
        try:
            return float(match.group().replace(",", ""))
        except ValueError:
            continue
    return None


def _sum(items: list[dict]) -> float | None:
    """把多条记录的数值加总——用于「逐股东列示出资」这类场景。"""
    total = 0.0
    found = False
    for it in items:
        text = str(it.get("value") or "").replace(" ", "")
        match = _NUM_RE.search(text)
        if not match:
            continue
        try:
            total += float(match.group().replace(",", ""))
            found = True
        except ValueError:
            continue
    return total if found else None


def _date_of(text: str):
    """从「2025-06-29」「2025年6月29日」「2023-06-30 至 2025-06-29」里取出日期（取最后一个）。"""
    matches = _DATE_RE.findall(str(text or ""))
    if not matches:
        return None
    year, month, day = matches[-1]
    try:
        return date(int(year), int(month), int(day))
    except ValueError:
        return None


def _analyze_labor(project: dict, extracted: dict, rules: dict) -> list[dict]:
    items = extracted["items"]
    cps = {cp["id"]: cp for cp in rules.get("checkpoints", [])}
    findings: list[dict] = []

    headcount = [i for i in items if i["field"] == "员工人数"]
    insured = [i for i in items if i["field"] == "社保人数"]
    dispatched = [i for i in items if i["field"] == "派遣人数"]
    signed = [i for i in items if i["field"] == "合同签订率"]
    disputes = [i for i in items if i["field"] == "存在劳动争议"]
    noncompete = [i for i in items if i["field"] == "存在竞业限制"]

    # LAB-01 劳动合同
    rate = _num(signed)
    if signed and rate is not None and rate < 100:
        findings.append(_finding(
            "LAB-01", "high", "劳动合同签订率不足",
            f"材料记载的书面劳动合同签订率为 {rate:g}%，未覆盖全部在职员工。",
            "补齐未签订人员的书面合同；核算未签期间可能产生的二倍工资差额，并在申报文件中说明整改情况。",
            [_cite(i) for i in signed], cps.get("LAB-01"),
        ))
    elif not signed:
        findings.append(_finding(
            "LAB-01", "medium", "未见劳动合同签订情况",
            "材料中未见书面劳动合同或签订率记录，无法确认全员签订。",
            "补充劳动合同台账或员工名册，注明签订日期与合同期限。",
            [{"document_id": None, "page": None, "quote": "", "filename": "(缺)"}],
            cps.get("LAB-01"),
        ))

    # LAB-02 社保
    head_n, insured_n = _num(headcount), _num(insured)
    if head_n and insured_n is not None and insured_n < head_n:
        findings.append(_finding(
            "LAB-02", "high", "社保缴纳人数少于在职人数",
            f"在职 {head_n:g} 人，社保缴纳 {insured_n:g} 人，差额 {head_n - insured_n:g} 人。",
            "逐人核对未缴、断缴原因；补缴或说明劳务关系性质，评估对成本与合规的影响。",
            [_cite(i) for i in headcount + insured], cps.get("LAB-02"),
        ))

    # LAB-03 派遣
    dispatch_n = _num(dispatched)
    if dispatch_n and head_n:
        ratio = dispatch_n / head_n * 100
        findings.append(_finding(
            "LAB-03", "medium", "存在劳务派遣用工",
            f"派遣人数 {dispatch_n:g} 人，占在职人数约 {ratio:.1f}%。",
            "核验派遣岗位是否为临时性、辅助性、替代性，以及用工比例是否符合法定上限（依据待补），必要时转为直接用工。",
            [_cite(i) for i in dispatched], cps.get("LAB-03"),
        ))

    # LAB-05 竞业限制
    if noncompete:
        findings.append(_finding(
            "LAB-05", "medium", "存在竞业限制安排",
            "材料显示已与员工约定竞业限制，需核验人员范围与补偿安排。",
            "确认限制人员是否限于高级管理、高级技术与保密义务人员，并按月支付补偿；否则条款可能无法执行。",
            [_cite(i) for i in noncompete], cps.get("LAB-05"),
        ))

    # LAB-06 争议
    if disputes:
        findings.append(_finding(
            "LAB-06", "medium", "存在劳动争议记录",
            "材料显示存在仲裁或诉讼记录，需核实处理结果与是否构成重大不利影响。",
            "逐案说明案由、金额、结果与整改；评估是否需在申报文件中披露。",
            [_cite(i) for i in disputes], cps.get("LAB-06"),
        ))

    return findings


def _analyze_equity(project: dict, extracted: dict, rules: dict) -> list[dict]:
    items = extracted["items"]
    cps = {cp["id"]: cp for cp in rules.get("checkpoints", [])}
    findings: list[dict] = []

    subscribed = [i for i in items if i["field"] == "认缴出资"]
    paid = [i for i in items if i["field"] == "实缴出资"]
    holding = [i for i in items if i["field"] == "持股比例"]
    vt = [i for i in items if i["field"] == "存在对赌"]
    buyback = [i for i in items if i["field"] == "存在回购义务"]
    nominee = [i for i in items if i["field"] == "存在代持"]
    privilege = [i for i in items if i["field"] == "存在优先权"]

    # EQT-01 出资
    sub_n, paid_n = _sum(subscribed), _sum(paid)
    if sub_n and paid_n is not None and paid_n < sub_n:
        findings.append(_finding(
            "EQT-01", "high", "注册资本未实缴到位",
            f"认缴 {sub_n:g} 万元，实缴 {paid_n:g} 万元，差额 {sub_n - paid_n:g} 万元。",
            "明确剩余出资的缴纳期限与资金来源；核对非货币出资的评估作价，必要时减资或补足。",
            [_cite(i) for i in subscribed + paid], cps.get("EQT-01"),
        ))

    # EQT-02 代持
    if nominee:
        findings.append(_finding(
            "EQT-02", "high", "存在股权代持",
            "材料显示存在股权代持安排，名义股东与实际出资人不一致。",
            "在申报前完成还原或解除，取得各方确认；说明代持形成原因及是否影响权属清晰。",
            [_cite(i) for i in nominee], cps.get("EQT-02"),
        ))

    # EQT-03 对赌与回购
    if vt or buyback:
        findings.append(_finding(
            "EQT-03", "high", "存在对赌或回购安排",
            "投资协议中载有业绩承诺、估值调整或回购义务，通常构成申报前需清理的事项。",
            "与投资人协商终止或由实际控制人承接；取得终止协议并确认不附恢复条件。",
            [_cite(i) for i in (vt + buyback)], cps.get("EQT-03"),
        ))

    # EQT-04 特殊权利
    if privilege:
        findings.append(_finding(
            "EQT-04", "medium", "存在优先权或反稀释安排",
            "股东协议中载有优先购买、优先认购、清算优先或反稀释条款。",
            "梳理各项特殊权利的触发条件与存续状态，评估对控制权与后续融资的影响。",
            [_cite(i) for i in privilege], cps.get("EQT-04"),
        ))

    # EQT-05 股权结构自洽
    # 只拿「章程 / 股东名册」这类完整列示的文档来求和：代持说明里会写「其中 5% 代持」，
    # 那是某股东持股的一部分，混进来必然超过 100%。
    registry = [i for i in holding
                if any(k in (i.get("filename") or "") for k in ("章程", "股东名册", "股权结构"))]
    source = registry or holding
    ratios = sorted({r for r in (_num([i]) for i in source) if r is not None})
    if len(ratios) >= 2 and abs(sum(ratios) - 100) > 0.5:
        findings.append(_finding(
            "EQT-05", "medium", "股东持股比例合计不等于 100%",
            f"抽取值合计 {sum(ratios):.2f}%，与 100% 存在差异，可能存在遗漏或抽取误差。",
            "以工商登记与章程为准核对完整股东名册，确认是否存在未披露的持股平台。",
            [_cite(i) for i in source], cps.get("EQT-05"),
        ))

    return findings


def _analyze_asset(project: dict, extracted: dict, rules: dict) -> list[dict]:
    subject = (project.get("subject_name") or "").strip()
    items = extracted["items"]
    cps = {cp["id"]: cp for cp in rules.get("checkpoints", [])}
    findings: list[dict] = []

    holders = [i for i in items if i["field"] == "权利人"]
    certs = [i for i in items if i["field"] == "证号"]
    mortgages = [i for i in items if i["field"] == "存在抵押"]
    seals = [i for i in items if i["field"] == "存在查封"]
    pledges = [i for i in items if i["field"] == "存在质押"]
    lessors = [i for i in items if i["field"] == "出租方"]
    expiries = [i for i in items if i["field"] == "有效期"]

    # AST-01 权属主体一致性
    if subject and holders:
        mismatch = [h for h in holders if subject not in h["value"]]
        if mismatch:
            findings.append(
                _finding(
                    "AST-01",
                    "high",
                    "核心资产权利人非拟上市主体",
                    f"权证记载的权利人为「{mismatch[0]['value']}」，与拟上市主体「{subject}」不一致，共 {len(mismatch)} 处。",
                    "核实是否存在代持、出资未到位或资产未注入；必要时办理权属变更或补充协议，并在申报文件中披露形成原因。",
                    [_cite(i) for i in mismatch],
                    cps.get("AST-01"),
                )
            )
    elif subject and not holders:
        findings.append(
            _finding(
                "AST-01",
                "medium",
                "未见权属登记信息",
                "已上传材料中未抽取到权利人字段，无法验证资产是否登记在拟上市主体名下。",
                "补充不动产权证、专利/商标证书的登记页，或提供登记机关查询记录。",
                [{"document_id": None, "page": None, "quote": "", "filename": "(缺)"}],
                cps.get("AST-01"),
            )
        )

    # AST-02 权证完整性
    if items and not certs:
        findings.append(
            _finding(
                "AST-02",
                "medium",
                "未见权证编号",
                "材料中出现资产描述，但未抽取到任何权证/证书编号，无法确认权属已登记。",
                "补充不动产权证书、专利/商标证书的登记页；如仅有出让合同与付款凭证，说明未办证原因及办理进度。",
                [{"document_id": None, "page": None, "quote": "", "filename": "(缺)"}],
                cps.get("AST-02"),
            )
        )

    # AST-03 权利负担
    for flag_items, level, label in ((mortgages, "medium", "抵押"), (seals, "high", "查封"), (pledges, "medium", "质押")):
        if flag_items:
            findings.append(
                _finding(
                    "AST-03",
                    level,
                    f"核心资产存在{label}",
                    f"材料显示标的资产存在{label}情形，共 {len(flag_items)} 处，可能影响持续使用与处置。",
                    f"取得{label}权人同意或解除安排；核算债务规模与违约可能性，在申报文件中充分披露。",
                    [_cite(i) for i in flag_items],
                    cps.get("AST-03"),
                )
            )

    # AST-04 租赁合法性
    if lessors:
        bad = [i for i in lessors if subject and subject not in i["value"]]
        if bad:
            findings.append(
                _finding(
                    "AST-04",
                    "high",
                    "经营场所出租方非产权人",
                    f"租赁合同记载的出租方为「{bad[0]['value']}」，非拟上市主体，存在无权出租或转租风险。",
                    "核验出租方产权证明与转租授权；无法补正的，评估搬迁成本与替代场地。",
                    [_cite(i) for i in bad],
                    cps.get("AST-04"),
                )
            )

    # AST-05 资质有效性
    today = date.today()
    expired = []
    for e in expiries:
        expiry = _date_of(e["value"])
        if expiry is not None and expiry < today:
            expired.append(e)
    if expired:
        findings.append(
            _finding(
                "AST-05",
                "high",
                "经营资质已过期",
                f"抽取到的有效期「{expired[0]['value']}」早于当前日期，资质处于失效状态。",
                "立即办理延续或重新申请；说明过期期间业务的合规安排及是否存在处罚。",
                [_cite(i) for i in expired],
                cps.get("AST-05"),
            )
        )

    # AST-06 知识产权
    if pledges:
        pass  # 已由 AST-03 覆盖
    conflicts = extracted["conflicts"]
    if conflicts:
        field = conflicts[0]["field"]
        values = "、".join(v["value"] for v in conflicts[0]["values"])
        findings.append(
            _finding(
                "AST-06",
                "medium",
                f"材料间「{field}」记载冲突",
                f"同一字段在不同材料中出现 {len(conflicts[0]['values'])} 个取值：{values}。",
                "以登记机关记录为准，逐一核对并统一口径；冲突未消除前不得据以出结论。",
                [
                    _cite(it)
                    for v in conflicts[0]["values"]
                    for it in v["items"][:1]
                ],
                cps.get("AST-06"),
            )
        )

    return findings


# ---------------------------------------------------------------- Agent D
def _norm(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def qc(project: dict, findings: list[dict], docs: list[dict], rules: dict) -> dict:
    """质检：逐条核查证据锚点是否真实存在于原文、规则是否存在。

    阻断项（fail）：引用的原文在文件中找不到、引用了不存在的核查要点、风险等级非法。
    提示项（insufficient）：材料缺失导致无法验证——如实标注，不冒充"已验证"。
    """
    docs_by_id = {d["id"]: _doc_text(d) for d in docs}
    rule_ids = {cp["id"] for cp in rules.get("checkpoints", [])}
    issues: list[dict] = []
    notices: list[dict] = []
    checked = 0

    for f in findings:
        checked += 1
        problem = None
        locatable = [c for c in f["citations"] if c.get("document_id") is not None]

        if not f["citations"]:
            problem = "结论缺少证据锚点"
        elif not locatable:
            notices.append({"code": f["code"], "title": f["title"], "reason": "材料缺失，无法定位原文，需补料后再核"})
            f["qc"] = "insufficient"
            continue
        else:
            for c in locatable:
                body = _norm(docs_by_id.get(c["document_id"], ""))
                if not c.get("quote") or _norm(c["quote"]) not in body:
                    problem = f"证据原文无法在文件中定位（文件 {c.get('filename')}，第 {c.get('page')} 页）"
                    break
        if f.get("rule_id") and f["rule_id"] not in rule_ids:
            problem = f"引用了不存在的核查要点 {f['rule_id']}"
        if f["risk_level"] not in {"high", "medium", "low"}:
            problem = "风险等级取值非法"

        f["qc"] = "pass" if not problem else "fail"
        if problem:
            issues.append({"code": f["code"], "title": f["title"], "reason": problem})

    return {
        "passed": len(issues) == 0,
        "checked": checked,
        "failed": len(issues),
        "issues": issues,
        "notices": notices,
        "note": "规范依据待补" if any(not f.get("rule_ref") for f in findings) else "",
    }


def _run_json(system: str, user: str, cfg: dict | None = None) -> dict:  # pragma: no cover - 网络路径
    import asyncio

    return asyncio.run(chat_json(system, user, cfg=cfg))

# ---------------------------------------------------------------- 港股上市评估专项材料
# 三维修查之外，做能不能上港股还需要这些；缺了不影响三维修查，但资格测试无法完成。
HK_REQUIRED = [
    ("近三年审计报告", "8.05 盈利测试：据此计算最近一年及前两年累计的股东应占盈利"),
    ("发行方案（含市值与发行比例）", "8.05 市值测试、8.08 公众持股 25% 门槛的测算依据"),
    ("股权结构表（发行前后）", "8.08 公众持股比例、控制权稳定性"),
    ("招股说明书草稿或章节", "11A 披露充分性核对"),
    ("保荐人委任文件", "3A 保荐人独立性与尽调责任"),
    ("重大诉讼与行政处罚清单", "8.04 适合上市判断"),
]

HK_KEYWORDS = {
    "近三年审计报告": ["审计报告", "審計報告", "财务报表", "財務報表", "年度报告"],
    "发行方案（含市值与发行比例）": ["发行方案", "發行方案", "发行价", "发行比例", "募资", "市值"],
    "股权结构表（发行前后）": ["股权结构", "股权結構", "发行前", "发行后", "股东名册"],
    "招股说明书草稿或章节": ["招股书", "招股章程", "上市文件", "招股說明書"],
    "保荐人委任文件": ["保荐人", "保薦人", "保荐协议"],
    "重大诉讼与行政处罚清单": ["重大诉讼", "行政处罚", "處罰", "立案"],
}


def check_hk_missing(docs: list[dict]) -> list[dict]:
    """港股上市评估专项材料缺料检查；返回 [{material, needed_for}]，与板块缺料同构。"""
    corpus = "\n".join([_doc_text(d) + " " + d["filename"] for d in docs])
    missing = []
    for name, why in HK_REQUIRED:
        kws = HK_KEYWORDS.get(name, [])
        if not any(kw in corpus for kw in kws):
            missing.append({"material": name, "needed_for": why})
    return missing

