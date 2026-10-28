"""把文档中的「争点」统一改为「争议点」。"""
from pathlib import Path

ROOT = Path(r"D:\Users\92182\Documents\deepseek-harness\default-workspace")
TARGETS = [ROOT / "diligence-platform" / "DESIGN-issue-workbench.md"]

for path in TARGETS:
    text = path.read_text(encoding="utf-8")
    count = text.count("争点")
    if count:
        path.write_text(text.replace("争点", "争议点"), encoding="utf-8", newline="")
    print(f"{path.name}: replaced {count}")
