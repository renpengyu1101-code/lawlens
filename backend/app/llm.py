"""DeepSeek（OpenAI 兼容）调用封装。

密钥来源优先级：请求级配置（用户在设置页填写）> 环境变量。
两者都没有时进入演示模式（规则启发式），界面会显著标注，不伪装成模型输出。
"""
from __future__ import annotations

import json
import re

import httpx

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, MOCK_MODE


class LLMError(RuntimeError):
    pass


def resolve(cfg: dict | None = None) -> dict:
    """合并请求级配置与环境变量，返回实际使用的连接参数。"""
    cfg = cfg or {}
    key = (cfg.get("key") or DEEPSEEK_API_KEY or "").strip()
    return {
        "key": key,
        "model": (cfg.get("model") or DEEPSEEK_MODEL).strip(),
        "base": (cfg.get("base") or DEEPSEEK_BASE_URL).strip().rstrip("/"),
        "enabled": bool(key),
    }


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def parse_json(text: str) -> dict:
    body = _strip_fence(text)
    try:
        return json.loads(body)
    except json.JSONDecodeError:
        start, end = body.find("{"), body.rfind("}")
        if start >= 0 and end > start:
            return json.loads(body[start : end + 1])
        raise LLMError("模型返回的不是合法 JSON")


async def ping(cfg: dict | None = None) -> list[str]:
    """轻量连通性测试：列出可用模型。不返回密钥本身。"""
    conn = resolve(cfg)
    if not conn["enabled"]:
        raise LLMError("未填写 API Key")
    headers = {"Authorization": f"Bearer {conn['key']}"}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(f"{conn['base']}/models", headers=headers)
    if resp.status_code != 200:
        raise LLMError(f"HTTP {resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return [m.get("id", "") for m in data.get("data", [])][:20]


async def chat_json(system: str, user: str, *, temperature: float = 0.2, cfg: dict | None = None) -> dict:
    conn = resolve(cfg)
    if not conn["enabled"]:
        raise LLMError("未配置 API Key（mock 模式）")
    payload = {
        "model": conn["model"],
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    headers = {"Authorization": f"Bearer {conn['key']}"}
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(f"{conn['base']}/chat/completions", json=payload, headers=headers)
    if resp.status_code != 200:
        raise LLMError(f"模型调用失败 HTTP {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise LLMError("模型响应结构异常") from exc
    return parse_json(content)
