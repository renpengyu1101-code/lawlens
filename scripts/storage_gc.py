"""存储清理脚本：默认只报告（dry-run），加 --apply 才删。

用法（在项目根目录）：
    python scripts/storage_gc.py                 # 看看有多少孤立文件
    python scripts/storage_gc.py --apply         # 真正删除
    python scripts/storage_gc.py --json          # 机器可读输出

「孤立文件」= 磁盘上存在，但 documents / document_versions / reports 三张表都不引用的文件。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app import storage  # noqa: E402


def mb(n: int | float) -> str:
    return f"{n / 1024 / 1024:.2f} MB"


def main() -> int:
    ap = argparse.ArgumentParser(description="LawLens 存储清理")
    ap.add_argument("--apply", action="store_true", help="真正删除孤立文件")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    if args.json:
        data = storage.collect(apply=args.apply) if args.apply else storage.scan()
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0

    data = storage.scan()
    print(f"数据目录：{data['data_dir']}")
    print(f"总占用：{mb(data['total_bytes'])}（材料 {mb(data['upload']['bytes'])} / "
          f"报告 {mb(data['reports']['bytes'])}）")
    print(f"孤立文件：{data['orphan_count']} 个，{mb(data['orphan_bytes'])}")
    if data["stray_project_dirs"]:
        print(f"已删除项目遗留目录：{len(data['stray_project_dirs'])} 个")
    for item in data["orphans"][:20]:
        print(f"  - {item['path']}（{mb(item['bytes'])}）")
    if data["orphan_count"] > 20:
        print(f"  … 另有 {data['orphan_count'] - 20} 个")

    if not args.apply:
        print("\n这是预演。加 --apply 才会删除。")
        return 0

    result = storage.collect(apply=True)
    print(f"\n已删除 {len(result['deleted'])} 个文件，释放 {mb(result['freed_bytes'])}，"
          f"清理空目录 {result['removed_dirs']} 个")
    if result["failed"]:
        print(f"删除失败 {len(result['failed'])} 个：")
        for item in result["failed"][:10]:
            print(f"  - {item['path']}：{item['error']}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
