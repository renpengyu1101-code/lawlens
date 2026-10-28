"""真模型连通性与 JSON 回环自检（不启动服务、不建项目）。

用法（在 diligence-platform 目录）：
    .venv\\Scripts\\python.exe scripts\\check_llm.py

读取顺序：进程环境变量 > 同目录上级的 .env。缺 Key 会直接失败，不会静默降级。
输出只显示模型名、耗时、返回字段数；不打印密钥。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:  # Windows 控制台默认 GBK，先切成 UTF-8，避免中文与符号打不出来
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        import os
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


async def main() -> int:
    load_env()
    from app import llm
    from app.config import DEEPSEEK_BASE_URL, DEEPSEEK_MODEL

    conn = llm.resolve(None)
    if not conn["enabled"]:
        print("✗ 未配置 DEEPSEEK_API_KEY（环境变量或 .env）")
        return 1

    print(f"端点：{conn['base']}  模型：{conn['model']}")

    t0 = time.time()
    try:
        models = await llm.ping(None)
        print(f"[OK] /models 可达（{time.time() - t0:.1f}s），可用模型 {len(models)} 个：{', '.join(models[:6])}")
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] /models 失败：{exc}")
        return 1

    system = "你是资料抽取器。只输出 JSON：{\"items\":[{\"field\":\"金额\",\"value\":\"1000万元\",\"page\":1}]}"
    user = "材料：本公司注册资本为 1000 万元人民币。请抽取。"
    t0 = time.time()
    try:
        data = await llm.chat_json(system, user, cfg=None)
    except Exception as exc:  # noqa: BLE001
        print(f"[FAIL] chat_json 失败：{exc}")
        return 1
    items = data.get("items") or []
    print(f"[OK] JSON 回环 OK（{time.time() - t0:.1f}s），items {len(items)} 条：{json.dumps(items[:2], ensure_ascii=False)}")
    print(f"（config 里的默认基址 {DEEPSEEK_BASE_URL}，默认模型 {DEEPSEEK_MODEL}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
