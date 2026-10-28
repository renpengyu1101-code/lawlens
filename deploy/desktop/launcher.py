"""LawLens 桌面版启动器：挑端口 → 起服务 → 自动打开浏览器。

打包说明：`python/` 是随包携带的便携解释器（含全部依赖），对方无需安装任何东西。
端口可用环境变量 DILIGENCE_PORT 指定；不指定时自动从 8000 往上找一个空闲端口。
"""
from __future__ import annotations

import os
import shutil
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENV = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"


def load_env() -> None:
    if not ENV.exists() and EXAMPLE.exists():
        shutil.copyfile(EXAMPLE, ENV)
        print("首次运行：已生成 .env。要接模型，请用记事本填入 DEEPSEEK_API_KEY 后重启。")
    if not ENV.exists():
        return
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def pick_port() -> int:
    want = os.getenv("DILIGENCE_PORT", "").strip()
    if want.isdigit():
        return int(want)
    for port in range(8000, 8020):
        if port_free(port):
            return port
    return 8000


def open_when_ready(port: int) -> None:
    """等服务真正起来再开浏览器，避免打开一个 502 页面。"""
    url = f"http://127.0.0.1:{port}"
    for _ in range(60):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=2) as resp:
                if resp.status == 200:
                    break
        except Exception:  # noqa: BLE001
            continue
    print(f"\n  浏览器已打开：{url}\n  若没弹出，手动复制上面地址。\n")
    try:
        webbrowser.open(url)
    except Exception:  # noqa: BLE001
        pass


def main() -> int:
    load_env()
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    sys.path.insert(0, str(ROOT / "backend"))

    port = pick_port()
    mode = "模型模式" if os.getenv("DEEPSEEK_API_KEY", "").strip() else "演示模式（未填 API Key）"

    print("=" * 60)
    print("  LawLens · 港股上市评估")
    print(f"  模式：{mode}")
    print(f"  地址：http://127.0.0.1:{port}")
    print("  关闭本窗口即停止服务")
    print("=" * 60)

    threading.Thread(target=open_when_ready, args=(port,), daemon=True).start()

    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
