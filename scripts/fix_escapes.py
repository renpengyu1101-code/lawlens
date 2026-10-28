"""一次性修复：把源码里误写的字面量 `n 还原为换行。"""
from pathlib import Path

TARGETS = [
    Path(__file__).resolve().parent.parent / "backend" / "app" / "report.py",
    Path(__file__).resolve().parent.parent / "backend" / "app" / "main.py",
]

for path in TARGETS:
    text = path.read_text(encoding="utf-8")
    count = text.count("`n")
    if count:
        path.write_text(text.replace("`n", "\n"), encoding="utf-8", newline="")
    print(f"{path.name}: replaced {count}")
