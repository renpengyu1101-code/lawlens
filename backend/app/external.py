"""外部信息核查：企查查工商接口 + 互联网搜索。

接口契约（已核对官方文档）：
- 企查查：GET https://api.qichacha.com/ECIV4/GetBasicDetailsByName?key=&keyword=
  Header Token = MD5(key + Timespan + SecretKey).upper()，Timespan 为 Unix 秒。
  返回 {Status, Message, Result}，Status 为 "200" 表示成功。
- 搜索：Tavily / Serper / Bocha 三种，均为 POST + Bearer 或 X-API-KEY。

定位：外部信息一律视为「线索」，不是已核实事实；返回结构里强制带 source_url 与 fetched_at。
"""
from __future__ import annotations

import hashlib
import time
from datetime import datetime, timedelta, timezone

import httpx

QCC_BASE = "https://api.qichacha.com"
TZ = timezone(timedelta(hours=8))

# 外部信息里出现这些词，作为「值得关注」的线索（不代表成立）
NEGATIVE_HINTS = {
    "失信": "失信被执行",
    "被执行": "被执行人",
    "限制高消费": "限制高消费",
    "行政处罚": "行政处罚",
    "立案": "立案",
    "调查": "调查",
    "诉讼": "诉讼",
    "仲裁": "仲裁",
    "召回": "产品召回",
    "处罚": "处罚",
    "冻结": "股权冻结",
    "经营异常": "经营异常",
    "欠税": "欠税",
}


class ExternalError(RuntimeError):
    def __init__(self, message: str, kind: str = "unknown"):
        super().__init__(message)
        self.kind = kind


def now_iso() -> str:
    return datetime.now(TZ).isoformat(timespec="seconds")


def _sign(key: str, secret: str) -> tuple[str, str]:
    timespan = str(int(time.time()))
    token = hashlib.md5(f"{key}{timespan}{secret}".encode()).hexdigest().upper()
    return token, timespan


def qcc_basic(name: str, key: str, secret: str, base: str = QCC_BASE) -> dict:
    """查企业工商基本信息。返回 {facts, raw, source}。"""
    if not key or not secret:
        raise ExternalError("未配置企查查 key/secret", "config")
    token, timespan = _sign(key, secret)
    url = f"{base.rstrip('/')}/ECIV4/GetBasicDetailsByName"
    try:
        with httpx.Client(timeout=20) as client:
            resp = client.get(url, params={"key": key, "keyword": name},
                              headers={"Token": token, "Timespan": timespan})
    except httpx.HTTPError as exc:
        raise ExternalError(f"网络错误：{exc}", "network") from exc

    if resp.status_code == 401:
        raise ExternalError("企查查鉴权失败（401）：key/secret 或签名有误", "auth")
    if resp.status_code == 403:
        raise ExternalError("企查查拒绝访问（403）：接口可能未开通或无权限", "permission")
    if resp.status_code != 200:
        raise ExternalError(f"企查查返回 HTTP {resp.status_code}: {resp.text[:200]}", "http")

    data = resp.json()
    status = str(data.get("Status", ""))
    if status != "200":
        msg = data.get("Message") or data.get("Result") or "查询失败"
        raise ExternalError(f"企查查返回：{msg}", "api")

    result = data.get("Result") or {}
    if not result:
        raise ExternalError(f"未查到企业：{name}", "no_result")

    facts = {
        "name": result.get("Name"),
        "credit_code": result.get("CreditCode"),
        "legal_person": result.get("OperName"),
        "status": result.get("Status"),
        "start_date": result.get("StartDate"),
        "reg_capital": result.get("RegistCapi") or result.get("RegisteredCapital"),
        "paid_capital": result.get("RecCap") or result.get("PaidUpCapital"),
        "address": result.get("Address"),
        "industry": result.get("EconKind"),
        "is_listed": result.get("IsOnStock"),
        "stock_code": result.get("StockNumber"),
        "stock_type": result.get("StockType"),
        "former_names": [x.get("Name") for x in (result.get("OriginalName") or []) if isinstance(x, dict)],
    }
    return {"facts": facts, "raw": result, "source": f"{base}/ECIV4/GetBasicDetailsByName"}


def web_search(query: str, provider: str, key: str, *, count: int = 6) -> list[dict]:
    """调用搜索服务，统一返回 [{title, url, snippet}]。"""
    provider = (provider or "").strip().lower()
    if not provider:
        raise ExternalError("未配置搜索服务商（tavily/serper/bocha）", "config")
    if not key:
        raise ExternalError("未配置搜索 API Key", "config")

    try:
        with httpx.Client(timeout=25) as client:
            if provider == "tavily":
                resp = client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "max_results": count, "search_depth": "basic"},
                    headers={"Authorization": f"Bearer {key}"},
                )
            elif provider == "serper":
                resp = client.post(
                    "https://google.serper.dev/search",
                    json={"q": query, "num": count},
                    headers={"X-API-KEY": key},
                )
            elif provider == "bocha":
                resp = client.post(
                    "https://api.bochaai.com/v1/web-search",
                    json={"query": query, "count": count, "summary": True},
                    headers={"Authorization": f"Bearer {key}"},
                )
            else:
                raise ExternalError(f"不支持的搜索服务商：{provider}", "config")
    except httpx.HTTPError as exc:
        raise ExternalError(f"网络错误：{exc}", "network") from exc

    if resp.status_code in (401, 403):
        raise ExternalError(f"搜索服务鉴权失败（{resp.status_code}）", "auth")
    if resp.status_code != 200:
        raise ExternalError(f"搜索服务返回 HTTP {resp.status_code}: {resp.text[:200]}", "http")

    data = resp.json()
    items: list[dict] = []
    if provider == "tavily":
        for r in data.get("results", []):
            items.append({"title": r.get("title", ""), "url": r.get("url", ""),
                          "snippet": (r.get("content") or "")[:300]})
    elif provider == "serper":
        for r in data.get("organic", []):
            items.append({"title": r.get("title", ""), "url": r.get("link", ""),
                          "snippet": (r.get("snippet") or "")[:300]})
    else:  # bocha
        pages = (data.get("data") or {}).get("webPages", {}).get("value", []) or []
        for r in pages:
            items.append({"title": r.get("name", ""), "url": r.get("url", ""),
                          "snippet": (r.get("snippet") or r.get("summary") or "")[:300]})
    return [i for i in items if i["url"]]


def analyze(name: str, qcc: dict | None, searches: list[dict]) -> list[dict]:
    """把外部结果转成「线索」。每一条都带来源 URL 与未核实提示。"""
    findings: list[dict] = []
    stamp = now_iso()

    if qcc:
        f = qcc["facts"]
        status = (f.get("status") or "").strip()
        if status and status not in {"存续", "在业", "开业", "正常", "在营"}:
            findings.append({
                "code": "EXT-01", "level": "high", "title": f"工商登记状态异常：{status}",
                "detail": f"企查查登记状态为「{status}」，需核实是否影响主体资格与持续经营。",
                "source_url": qcc["source"], "snippet": f"Status={status}", "fetched_at": stamp,
            })
        if f.get("former_names"):
            findings.append({
                "code": "EXT-02", "level": "low", "title": "存在曾用名",
                "detail": "曾用名：" + "、".join(f["former_names"][:5]) + "。需核对历史材料是否使用旧名称。",
                "source_url": qcc["source"], "snippet": "、".join(f["former_names"][:5]), "fetched_at": stamp,
            })
        if f.get("is_listed") == "1":
            findings.append({
                "code": "EXT-03", "level": "low", "title": "已上市/挂牌",
                "detail": f"企查查显示已上市（{f.get('stock_type') or ''} {f.get('stock_code') or ''}）。",
                "source_url": qcc["source"], "snippet": f"IsOnStock=1 {f.get('stock_code') or ''}", "fetched_at": stamp,
            })

    for block in searches:
        for item in block["results"]:
            text = f"{item['title']} {item['snippet']}"
            hits = [label for kw, label in NEGATIVE_HINTS.items() if kw in text]
            if not hits:
                continue
            findings.append({
                "code": "EXT-10", "level": "medium",
                "title": f"外部信息提及：{hits[0]}",
                "detail": f"搜索「{block['query']}」命中相关内容，需回原始来源核实是否与本主体相关。",
                "source_url": item["url"], "snippet": item["snippet"][:200], "fetched_at": stamp,
            })
    return findings


def run_check(name: str, qcc_creds: tuple[str, str] | None,
              search_cfg: tuple[str, str] | None) -> dict:
    """执行一次外部核查。任一渠道缺失就跳过并给出提示，不阻断另一渠道。"""
    warnings: list[str] = []
    qcc_data = None
    if qcc_creds and qcc_creds[0] and qcc_creds[1]:
        try:
            qcc_data = qcc_basic(name, qcc_creds[0], qcc_creds[1])
        except ExternalError as exc:
            warnings.append(f"企查查：{exc}")
    else:
        warnings.append("企查查：未配置 key/secret，已跳过")

    queries = [
        f"{name} 诉讼 处罚 失信",
        f"{name} 港股 IPO 上市",
        f"{name} 监管 处罚 经营异常",
    ]
    searches: list[dict] = []
    if search_cfg and search_cfg[0] and search_cfg[1]:
        for q in queries:
            try:
                searches.append({"query": q, "provider": search_cfg[0],
                                 "results": web_search(q, search_cfg[0], search_cfg[1])})
            except ExternalError as exc:
                warnings.append(f"搜索（{q}）：{exc}")
                break
    else:
        warnings.append("搜索：未配置服务商或 Key，已跳过")

    findings = analyze(name, qcc_data, searches)
    return {"qcc": qcc_data, "searches": searches, "findings": findings, "warnings": warnings}
