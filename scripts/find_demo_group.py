"""打印演示用：最近一个含「不动产权证」材料组的 project_id 与 group_id。"""
import sqlite3
import sys
from pathlib import Path

db = Path(__file__).resolve().parent.parent / "backend" / "data" / "app.db"
conn = sqlite3.connect(db)
row = conn.execute(
    "SELECT g.id, g.project_id FROM document_groups g "
    "WHERE g.title LIKE ? ORDER BY g.id DESC LIMIT 1",
    ("%不动产权证%",),
).fetchone()
if row:
    print(f"{row[0]} {row[1]}")
else:
    print("0 0")
