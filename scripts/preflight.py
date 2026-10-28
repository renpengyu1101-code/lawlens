"""真实材料预检：本地解析 + 三维度缺料判断（不调用模型、不上传、不花钱）。

用法（在 diligence-platform 目录）：
    .venv\\Scripts\\python.exe scripts\\preflight.py "D:\\材料\\*.pdf"
    .venv\\Scripts\\python.exe scripts\\preflight.py a.pdf b.docx c.txt

输出：
  1) 每份文件能否解析（扫描件会标 needs_ocr，系统没有 OCR）；
  2) 三个维度分别能不能跑（缺哪类材料）；
  3) 一句话结论：能跑几个维度。

注意：预检只在本机读文件。真正发起核查时，文档正文会发给模型服务商。
"""
from __future__ import annotations

import glob
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

from app import agents  # noqa: E402
from app.config import BOARD_SEQUENCE, BOARDS  # noqa: E402
from app.parsers import parse_file  # noqa: E402

STATUS_LABEL = {
    "parsed": "OK",
    "ocr": "OCR 识别",
    "needs_ocr": "未能识别文字（扫描件且 OCR 失败）",
    "failed": "解析失败",
    "unsupported": "不支持的格式",
}


def expand(patterns: list[str]) -> list[Path]:
    files: list[Path] = []
    for pattern in patterns:
        hits = glob.glob(pattern)
        if hits:
            files.extend(Path(h) for h in hits)
        else:
            files.append(Path(pattern))
    return [f for f in files if f.exists()]


def main() -> int:
    if len(sys.argv) < 2:
        print("用法：python scripts/preflight.py <文件或通配符> [...]")
        return 2

    files = expand(sys.argv[1:])
    if not files:
        print("[FAIL] 没有找到任何文件")
        return 1

    docs = []
    print(f"共 {len(files)} 份文件\n")
    print(f"{'文件':<44} {'页':>4} {'字符':>7}  状态")
    print("-" * 80)
    bad = 0
    for path in files:
        text, pages, status = parse_file(path)
        if status in {"failed", "needs_ocr", "unsupported"}:
            bad += 1
        print(f"{path.name[:44]:<44} {pages:>4} {len(text):>7}  {STATUS_LABEL.get(status, status)}")
        docs.append({"filename": path.name, "text": text})

    print("")
    runnable = []
    for board in BOARD_SEQUENCE:
        spec = {
            "board": board,
            "required_materials": [{"type": t, "needed_for": why} for t, why in agents.BOARD_REQUIRED[board]],
        }
        missing = agents.check_missing(spec, docs)
        name = BOARDS[board]
        if missing:
            kinds = "、".join(m["material"] for m in missing)
            print(f"[跳过] {name}：缺 {kinds}")
        else:
            runnable.append(name)
            print(f"[可跑] {name}")

    print("")
    if bad:
        print(f"[WARN] {bad} 份文件没有解析出文字，这些材料等于没提供（系统不做 OCR）")
    if runnable:
        print(f"结论：{len(runnable)} 个维度可以跑 —— {'、'.join(runnable)}")
        print("提示：正文会发送给模型服务商；涉密材料请先确认是否可以外发。")
        return 0
    print("结论：一个维度都跑不了，先补材料（缺料判断按文件名与正文关键词匹配）")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
