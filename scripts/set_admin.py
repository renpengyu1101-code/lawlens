"""运维脚本：重设管理员账号与密码。

用法（在 diligence-platform 目录）：
    .venv\\Scripts\\python.exe scripts\\set_admin.py admin '新密码'
    .venv\\Scripts\\python.exe scripts\\set_admin.py          # 读 .env / 环境变量里的 DILIGENCE_ADMIN_*

拒绝把密码设成 123456 这类默认值；确实要设需显式加 --allow-weak。
"""
import os
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.config import DB_PATH  # noqa: E402
from app.security import hash_password  # noqa: E402

WEAK = {"123456", "password", "admin", "111111", "000000"}


def load_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"'))


def main() -> int:
    load_env()
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    allow_weak = "--allow-weak" in sys.argv

    email = (args[0] if len(args) > 0 else os.getenv("DILIGENCE_ADMIN_EMAIL", "admin")).strip()
    password = args[1] if len(args) > 1 else (os.getenv("DILIGENCE_ADMIN_PASSWORD") or "").strip()

    if not password:
        raise SystemExit("没有提供新密码，也没有 DILIGENCE_ADMIN_PASSWORD")
    if len(password) < 8:
        raise SystemExit("密码至少 8 位")
    if password in WEAK and not allow_weak:
        raise SystemExit(f"拒绝把密码设为 {password}；确实需要请加 --allow-weak")

    if not Path(DB_PATH).exists():
        raise SystemExit(f"数据库不存在：{DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id, email FROM users WHERE role = 'admin' ORDER BY id LIMIT 1").fetchone()
    if row is None:
        raise SystemExit("未找到管理员账号")
    conn.execute("UPDATE users SET email = ?, pwd_hash = ? WHERE id = ?", (email, hash_password(password), row[0]))
    conn.commit()
    print(f"已更新管理员：id={row[0]} 邮箱={email}（密码已重设，未回显）")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
