"""口令哈希、会话 cookie 与依赖注入。"""
from __future__ import annotations

import hashlib
import hmac
import secrets

from fastapi import Depends, HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from .config import COOKIE_NAME, SECRET_KEY, SESSION_MAX_AGE
from .db import connect

_serializer = URLSafeTimedSerializer(SECRET_KEY, salt="diligence-session")
_ITER = 200_000


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), _ITER).hex()
    return f"pbkdf2${_ITER}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, iters, salt, digest = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(calc, digest)
    except (ValueError, TypeError):
        return False


def _pwd_tag(pwd_hash: str) -> str:
    """会话版本标记：随口令哈希变化，改密后旧 cookie 自动失效。"""
    return hashlib.sha256((pwd_hash or "").encode()).hexdigest()[:12]


def issue_token(user_id: int, pwd_hash: str = "") -> str:
    return _serializer.dumps({"uid": user_id, "v": _pwd_tag(pwd_hash)})


def read_token(request: Request) -> dict | None:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return None
    try:
        data = _serializer.loads(raw, max_age=SESSION_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid")
    if not isinstance(uid, int):
        return None
    return {"uid": uid, "v": data.get("v", "")}


def get_current_user(request: Request) -> dict:
    payload = read_token(request)
    if payload is None:
        raise HTTPException(status_code=401, detail="未登录")
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (payload["uid"],)).fetchone()
    if row is None:
        raise HTTPException(status_code=401, detail="会话无效")
    if "is_active" in row.keys() and row["is_active"] == 0:
        raise HTTPException(status_code=401, detail="账号已停用")
    if payload["v"] != _pwd_tag(row["pwd_hash"]):
        raise HTTPException(status_code=401, detail="会话已失效，请重新登录")
    return dict(row)


def get_optional_user(request: Request) -> dict | None:
    payload = read_token(request)
    if payload is None:
        return None
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (payload["uid"],)).fetchone()
    if row is None or payload["v"] != _pwd_tag(row["pwd_hash"]):
        return None
    if "is_active" in row.keys() and row["is_active"] == 0:
        return None
    return dict(row)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
