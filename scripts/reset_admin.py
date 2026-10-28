"""重置管理员密码（部署/交付时用）。

    python scripts/reset_admin.py                    # 把 admin 重置为 325114
    python scripts/reset_admin.py --email boss --password 'xxx'
    python scripts/reset_admin.py --list             # 只看现有账号

管理员不存在时会直接创建（role=admin，积分 99999）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.db import connect, init_db, now  # noqa: E402
from app.security import hash_password  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="重置管理员密码")
    ap.add_argument("--email", default="admin")
    ap.add_argument("--password", default="325114")
    ap.add_argument("--list", action="store_true", help="列出账号后退出")
    args = ap.parse_args()

    init_db()
    with connect() as conn:
        if args.list:
            rows = conn.execute("SELECT id, email, role, credits FROM users ORDER BY id").fetchall()
            for r in rows:
                print(f"{r['id']:>3}  {r['email']:<28} {r['role']:<6} 积分 {r['credits']}")
            return 0

        row = conn.execute("SELECT id FROM users WHERE email = ?", (args.email,)).fetchone()
        if row:
            conn.execute(
                "UPDATE users SET pwd_hash = ?, role = 'admin', is_active = 1 WHERE id = ?",
                (hash_password(args.password), row["id"]),
            )
            print(f"已重置：{args.email} → 密码 {args.password}")
        else:
            conn.execute(
                "INSERT INTO users(email, pwd_hash, role, credits, is_active, created_at) VALUES (?,?,?,?,1,?)",
                (args.email, hash_password(args.password), "admin", 99999, now()),
            )
            print(f"已创建管理员：{args.email} → 密码 {args.password}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
