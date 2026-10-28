"""港股上市规则内置库：条文检索、按条号取原文、核查项与条款的绑定。

数据来自 `app/rules_data/listing_rules.json`（3,137 条，主板 + GEM 综合版），
由 `analysis-library/build_rule_index.py` 从知识库 PDF 逐页抽取后随产品一起发布。

三条纪律：
1. 只索引、不解释——条文原文照抄，页码指向 PDF 页序；
2. 绑定（RULE_BINDINGS）只写已核到原文的条款，核不到就留空；
3. 报告里的「评估落点」是**待律师确认的判断入口**，不是法律意见。
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path

try:
    from zhconv import convert as _zh_convert

    def _to_simplified(text: str) -> str:
        return _zh_convert(text or "", "zh-cn")
except ImportError:  # 未装 zhconv 时退化为原文匹配（繁简会对不上）
    def _to_simplified(text: str) -> str:
        return text or ""

# 数据文件：优先环境变量指定，默认用内置副本
_ENV_PATH = os.getenv("DILIGENCE_RULE_INDEX")
INDEX_PATH = Path(_ENV_PATH) if _ENV_PATH else Path(__file__).resolve().parent / "rules_data" / "listing_rules.json"

_TOKEN = re.compile(r"[\u4e00-\u9fa5A-Za-z]{2,}")
_MIN_SCORE = 0.18

# ---------------------------------------------------------------- 核查项 ↔ 条款
# 键为规则库里的 checkpoint id；值为港交所条款号。
# 只列"该事项在港股评估里的落点"：多数内地法事项统一落到 8.04（適合上市），
# 因为上市规则并不直接规范内地社保/物权，但会影响"是否适合上市"的判断。
RULE_BINDINGS: dict[str, list[str]] = {
    "AST-01": ["8.04"], "AST-02": ["8.04"], "AST-03": ["8.04"],
    "AST-04": ["8.04"], "AST-05": ["8.04"], "AST-06": ["11A.01"],
    "LAB-01": ["8.04"], "LAB-02": ["8.04"], "LAB-03": ["8.04"],
    "LAB-05": ["8.04"], "LAB-06": ["8.04"],
    "EQT-01": ["8.04"], "EQT-02": ["8.04"], "EQT-03": ["8.04"], "EQT-04": ["8.04"],
    # 港规直接管的四项（核查项扩充后使用）
    "HK-01": ["8.05"], "HK-02": ["8.08"], "HK-03": ["14A.01"], "HK-04": ["3A.01"],
}

# 相似案例（来自负面清单 v1，编号对应 library.db negatives.id）
SIMILAR_CASES = [
    {"topic": "业绩恶化",
     "match": ["业绩下滑", "业绩恶化", "连续亏损", "转亏为盈", "利润下降", "盈利能力", "净利润下滑",
               "盈利测试", "营业记录", "应占盈利"],
     "cases": [28, 19, 27, 34], "clause": "8.05（p149，盈利测试）",
     "note": "营业记录期业绩恶化或未达盈利测试，是联交所拒绝/申请人撤回的常见原因"},
    {"topic": "实控人风险",
     "match": ["实际控制人", "实控人", "立案", "留置", "刑事", "被调查", "离婚"],
     "cases": [24, 22], "clause": "8.04（p149，适合上市）",
     "note": "实控人被立案、留置或婚姻纠纷致控制权不稳，直接影响适合上市"},
    {"topic": "保荐与中介",
     "match": ["保荐人", "保荐机构", "中介机构", "尽职调查", "独立性"],
     "cases": [21, 28], "clause": "第 3A 章（章节级，条号待补）",
     "note": "保荐人独立性/尽调不足曾被列为拒绝原因"},
    {"topic": "估值与发行窗口",
     "match": ["估值", "破净", "折价", "发行价", "市净率", "估值倒挂"],
     "cases": [19, 26, 33], "clause": "",
     "note": "估值与发行窗口属市场因素，不是合规缺陷，不应据此提高风险等级"},
    {"topic": "公众持股",
     "match": ["公众持股", "公众人士持有", "公众股东"],
     "cases": [], "clause": "8.08（p153，公开市场规定）",
     "note": "公众持股比例与市值门槛"},
    {"topic": "关连交易",
     "match": ["关联交易", "关连交易", "关联方"],
     "cases": [], "clause": "14A.01（p378，关连交易章）",
     "note": "关连交易的申报、公告与独立股东批准要求"},
    {"topic": "递表与审核周期",
     "match": ["递表", "审核周期", "排队", "申请失效"],
     "cases": [26, 31, 35], "clause": "",
     "note": "多次递表/申请失效通常反映准备度或窗口问题"},
]


def _bigrams(text: str) -> set[str]:
    grams: set[str] = set()
    for token in _TOKEN.findall(_to_simplified(text or "")):
        for i in range(len(token) - 1):
            grams.add(token[i:i + 2])
    return grams


@lru_cache(maxsize=1)
def _load() -> tuple[dict, list[dict], dict[tuple[str, str], dict]]:
    if not INDEX_PATH.exists():
        return {"path": str(INDEX_PATH), "exists": False}, [], {}
    rows = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    prepared: list[dict] = []
    by_code: dict[tuple[str, str], dict] = {}
    for row in rows:
        grams = _bigrams(row.get("text", ""))
        by_code.setdefault((row.get("board", ""), row["code"]), {**row, "_bigrams": grams})
        if grams:
            prepared.append({**row, "_bigrams": grams})
    meta = {"path": str(INDEX_PATH), "exists": True, "total": len(rows),
            "main": sum(1 for r in rows if r.get("board") == "主板"),
            "gem": sum(1 for r in rows if r.get("board") == "GEM")}
    return meta, prepared, by_code


def stats() -> dict:
    meta, rows, _ = _load()
    return {**meta, "searchable": len(rows)}


def chapters() -> list[dict]:
    _, rows, _ = _load()
    tally: dict[str, int] = {}
    for row in rows:
        key = row.get("chapter", "")
        tally[key] = tally.get(key, 0) + 1

    def _key(item):
        match = re.match(r"第\s*(\d+)", item[0])
        return (int(match.group(1)) if match else 999, item[0])

    return [{"chapter": k, "clauses": v} for k, v in sorted(tally.items(), key=_key)]


def by_code(code: str, board: str = "主板") -> dict | None:
    """按条号取原文。先查指定板块，查不到再跨板块找。"""
    _, _, index = _load()
    hit = index.get((board, code)) or next((v for (_, c), v in index.items() if c == code), None)
    if not hit:
        return None
    out = {k: hit[k] for k in ("code", "chapter", "board", "page", "text") if k in hit}
    # 索引构建时正文被截断到 300 字：如实标记，别让「原文」看起来完整
    out["truncated"] = len(hit.get("text") or "") >= 300
    return out


def format_clause(code: str, board: str = "主板", text_limit: int = 120) -> str:
    """渲染成「第 8.04 条（p149）：原文…」，取不到就返回短标记。"""
    hit = by_code(code, board)
    if not hit:
        return f"第 {code} 条（索引中未找到）"
    return f"第 {hit['code']} 条（p{hit['page']}）：{(hit['text'] or '')[:text_limit]}"


def bound_clauses(checkpoint_id: str) -> list[dict]:
    """核查项绑定的条款原文（只返回索引里真有原文的）。"""
    out = []
    for code in RULE_BINDINGS.get(checkpoint_id, []):
        hit = by_code(code)
        if hit:
            out.append(hit)
    return out


def lookup(text: str, limit: int = 2, board: str = "主板") -> list[dict]:
    """按条文正文做主题检索（繁简归一）。"""
    _, rows, _ = _load()
    query = _bigrams(text)
    if len(query) < 2:
        return []
    scored = []
    for row in rows:
        if board and row.get("board") != board:
            continue
        shared = query & row["_bigrams"]
        if len(shared) < 2:
            continue
        score = len(shared) / len(query)
        if score < _MIN_SCORE:
            continue
        scored.append((score, row))
    scored.sort(key=lambda x: (-x[0], x[1]["page"]))
    out, seen = [], set()
    for score, row in scored:
        if row["code"] in seen:
            continue
        seen.add(row["code"])
        out.append({"code": row["code"], "chapter": row.get("chapter", ""), "page": row["page"],
                    "text": row["text"][:160], "score": round(score, 3)})
        if len(out) >= limit:
            break
    return out


def lookup_similar(text: str, limit: int = 2) -> list[dict]:
    """按主题找相似失败案例与相关条款。"""
    haystack = _to_simplified(text or "")
    hits = []
    for row in SIMILAR_CASES:
        matched = [kw for kw in row["match"] if _to_simplified(kw) in haystack]
        if not matched:
            continue
        # 两个以上关键词，或单个足够具体的词（≥4 字，如「公众持股」）才标注
        if len(matched) < 2 and not any(len(_to_simplified(k)) >= 4 for k in matched):
            continue
        hits.append({**row, "matched": matched})
        if len(hits) >= limit:
            break
    return hits
