"""FastAPI 应用：认证、项目、上传、流水线、报告、管理后台。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sys
import time
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from . import agents, external, llm, review, rule_refs, scoring, subject, versions
from .config import (
    BOARD_SEQUENCE, BOARDS, COOKIE_NAME, CREDITS_PER_RUN, MAX_QC_ROUNDS, MAX_UPLOAD_MB,
    MOCK_MODE, MOCK_STEP_DELAY, REGISTER_BONUS, REPORT_DIR, ROOT_DIR, SECRET_KEY,
    SESSION_MAX_AGE, UPLOAD_DIR,
)
from .db import audit, connect, init_db, now
from .config import ALLOW_REGISTER, COOKIE_SECURE
from .parsers import parse_file
from .report import build_report
from .security import get_current_user, get_optional_user, hash_password, issue_token, require_admin, verify_password


app = FastAPI(title="LawLens（演示）", version="0.1.0")


@app.middleware("http")
async def cache_policy(request, call_next):
    """页面入口不缓存（避免旧 index.html 指向旧 bundle）；带 hash 的静态资源长缓存。"""
    response = await call_next(request)
    if request.url.path.startswith("/assets/"):
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
    else:
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SAFE_NAME = re.compile(r"[^0-9A-Za-z\u4e00-\u9fa5._\-（）()]+")


# ----------------------------------------------------------------- 启动
def _register_document_version(conn, project_id: int, doc_id: int, filename: str,
                               path: str, sha256: str, text: str,
                               user_id: int | None, doc_type: str = "其他", label: str = "V1") -> tuple[int, int]:
    """为一份材料建立「材料组 + 首版本 + 段落」。上传与历史迁移共用。"""
    gid = conn.execute(
        "INSERT INTO document_groups(project_id, doc_type, title, created_at) VALUES (?,?,?,?)",
        (project_id, doc_type, Path(filename).stem, now()),
    ).lastrowid
    vid = conn.execute(
        "INSERT INTO document_versions(group_id, source_document_id, label, storage_path, sha256,"
        " is_current, uploaded_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (gid, doc_id, label, path, sha256, 1, user_id, now()),
    ).lastrowid
    paras = versions.align_to_previous(versions.split_paragraphs(text), [])
    for i, para in enumerate(paras, 1):
        conn.execute(
            "INSERT INTO paragraphs(version_id, uid, ordinal, page, text, char_start, char_end)"
            " VALUES (?,?,?,?,?,?,?)",
            (vid, para["uid"], i, para["page"], para["text"], para["char_start"], para["char_end"]),
        )
    return gid, vid


def migrate_documents() -> None:
    """把历史 documents 迁进版本模型（每组 V1），并补齐段落。"""
    with connect() as conn:
        rows = conn.execute(
            "SELECT * FROM documents d WHERE NOT EXISTS"
            " (SELECT 1 FROM document_versions v WHERE v.source_document_id = d.id)"
        ).fetchall()
        for doc in rows:
            _register_document_version(
                conn, doc["project_id"], doc["id"], doc["filename"], doc["path"], doc["sha256"], doc["text"], None,
            )



def _loud(message: str) -> None:
    print("!" * 6 + " " + message, file=sys.stderr, flush=True)


def _seed_admin() -> None:
    """首次启动建管理员：没给密码就随机生成并打印一次，杜绝 admin/123456。"""
    with connect() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()
        if row["c"]:
            return
        email = os.getenv("DILIGENCE_ADMIN_EMAIL", "admin")
        pwd = (os.getenv("DILIGENCE_ADMIN_PASSWORD") or "").strip()
        generated = not pwd
        if generated:
            pwd = secrets.token_urlsafe(9)
        conn.execute(
            "INSERT INTO users(email, pwd_hash, role, credits, created_at) VALUES (?,?,?,?,?)",
            (email, hash_password(pwd), "admin", 99999, now()),
        )
        audit(conn, None, "seed_admin", email, "初始化管理员账号")
    if generated:
        _loud(f"已创建管理员 {email}，初始密码：{pwd}")
        _loud("这串密码只显示这一次，请登录后立即修改。")


def _warn_insecure_defaults() -> None:
    if SECRET_KEY == "dev-only-change-me":
        _loud("DILIGENCE_SECRET 仍是默认值：内网/公网试用前必须换成随机串（scripts/start.ps1 -Init 可生成）")
    with connect() as conn:
        admins = conn.execute("SELECT email, pwd_hash FROM users WHERE role = 'admin'").fetchall()
    for row in admins:
        if verify_password("123456", row["pwd_hash"]):
            _loud(f"管理员 {row['email']} 仍在使用默认密码 123456，请立即修改")


def _recover_stuck_runs() -> int:
    """进程重启后，上一次跑一半的项目会永远停在 running；这里归位并退还积分。"""
    with connect() as conn:
        rows = conn.execute("SELECT id, user_id FROM projects WHERE status = 'running'").fetchall()
        for row in rows:
            conn.execute("UPDATE projects SET status = 'failed', updated_at = ? WHERE id = ?", (now(), row["id"]))
            conn.execute(
                "INSERT INTO task_runs(project_id, stage, agent, status, detail, created_at) VALUES (?,?,?,?,?,?)",
                (row["id"], "error", "pipeline", "fail",
                 _detail_of("", "服务重启，任务中断；已退还积分，请重新发起"), now()),
            )
            conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (CREDITS_PER_RUN, row["user_id"]))
            conn.execute(
                "INSERT INTO credits_ledger(user_id, delta, reason, project_id, created_at) VALUES (?,?,?,?,?)",
                (row["user_id"], CREDITS_PER_RUN, "重启中断退还", row["id"], now()),
            )
    return len(rows)


@app.on_event("startup")
def startup() -> None:
    init_db()
    migrate_documents()
    _seed_admin()
    _warn_insecure_defaults()
    recovered = _recover_stuck_runs()
    if recovered:
        _loud(f"启动恢复：{recovered} 个项目停在「执行中」，已标记失败并退还积分")


# ----------------------------------------------------------------- 模型
class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class PasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(min_length=6, max_length=128)


class ApiConfigIn(BaseModel):
    key: str = ""
    model: str = ""
    base: str = ""


class ReviewDecisionIn(BaseModel):
    decision: str
    comment: str = ""


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    subject_name: str = ""
    brief: str = ""
    board: str = "all"          # 每次核查固定覆盖三个维度，保留该字段兼容旧数据
    is_demo: bool = False


class CreditsIn(BaseModel):
    delta: int
    reason: str = "管理员调整"


class RuleUpdateIn(BaseModel):
    rule_ref: dict | None = None
    verification_status: str | None = None


class FindingUpdateIn(BaseModel):
    status: str
    note: str = ""


# ----------------------------------------------------------------- 工具
def _user_out(row: dict) -> dict:
    return {"id": row["id"], "email": row["email"], "role": row["role"], "credits": row["credits"]}


def _own_project(conn, project_id: int, user: dict) -> dict:
    row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "项目不存在")
    if row["user_id"] != user["id"] and user["role"] != "admin":
        raise HTTPException(403, "无权访问该项目")
    return dict(row)


def _recalc_status(conn, project_id: int) -> None:
    conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now(), project_id))


# ----------------------------------------------------------------- 健康
@app.get("/api/health")
def health() -> dict:
    return {"ok": True, "mock_mode": MOCK_MODE, "boards": BOARDS, "register_open": ALLOW_REGISTER}


# ----------------------------------------------------------------- 认证
@app.post("/api/auth/register")
def register(payload: RegisterIn, response: Response) -> dict:
    if not ALLOW_REGISTER:
        raise HTTPException(403, "本环境未开放自助注册，请联系管理员开通账号")
    if not EMAIL_RE.match(payload.email):
        raise HTTPException(400, "邮箱格式不正确")
    with connect() as conn:
        exists = conn.execute("SELECT id FROM users WHERE email = ?", (payload.email,)).fetchone()
        if exists:
            raise HTTPException(409, "该邮箱已注册")
        cur = conn.execute(
            "INSERT INTO users(email, pwd_hash, role, credits, created_at) VALUES (?,?,?,?,?)",
            (payload.email, hash_password(payload.password), "user", REGISTER_BONUS, now()),
        )
        uid = cur.lastrowid
        conn.execute(
            "INSERT INTO credits_ledger(user_id, delta, reason, created_at) VALUES (?,?,?,?)",
            (uid, REGISTER_BONUS, "注册赠送", now()),
        )
        audit(conn, uid, "register", payload.email)
        row = dict(conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone())
    response.set_cookie(COOKIE_NAME, issue_token(uid), max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", secure=COOKIE_SECURE)
    return {"user": _user_out(row)}


@app.post("/api/auth/login")
def login(payload: LoginIn, response: Response) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email,)).fetchone()
        if row is None or not verify_password(payload.password, row["pwd_hash"]):
            raise HTTPException(401, "邮箱或密码错误")
        audit(conn, row["id"], "login", payload.email)
        data = dict(row)
    response.set_cookie(COOKIE_NAME, issue_token(data["id"]), max_age=SESSION_MAX_AGE, httponly=True, samesite="lax", secure=COOKIE_SECURE)
    return {"user": _user_out(data)}


@app.post("/api/auth/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME)
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: dict = Depends(get_current_user)) -> dict:
    return {"user": _user_out(user), "mock_mode": MOCK_MODE}


@app.post("/api/auth/password")
def change_password(payload: PasswordIn, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
        if row is None or not verify_password(payload.old_password, row["pwd_hash"]):
            raise HTTPException(400, "原密码不正确")
        conn.execute("UPDATE users SET pwd_hash = ? WHERE id = ?",
                     (hash_password(payload.new_password), user["id"]))
        audit(conn, user["id"], "change_password", f"user:{user['id']}")
    return {"ok": True}


@app.get("/api/credits")
def my_credits(limit: int = 20, user: dict = Depends(get_current_user)) -> dict:
    """当前用户的积分余额与最近流水（积分查询弹窗用）。"""
    limit = max(1, min(limit, 100))
    with connect() as conn:
        row = conn.execute("SELECT credits FROM users WHERE id = ?", (user["id"],)).fetchone()
        rows = conn.execute(
            "SELECT delta, reason, project_id, created_at FROM credits_ledger"
            " WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user["id"], limit)).fetchall()
    return {
        "credits": row["credits"] if row else 0,
        "items": [{
            "delta": r["delta"],
            "reason": r["reason"],
            "project_id": r["project_id"],
            "created_at": r["created_at"],
        } for r in rows],
    }


@app.get("/api/subjects")
def list_subjects(user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT subject_name AS subject, COUNT(*) AS projects, MAX(updated_at) AS updated_at"
            " FROM projects WHERE user_id = ? AND subject_name <> ''"
            " GROUP BY subject_name ORDER BY updated_at DESC", (user["id"],)).fetchall()
        out = []
        for row in rows:
            boards = [x["board"] for x in conn.execute(
                "SELECT DISTINCT board FROM projects WHERE user_id = ? AND subject_name = ?",
                (user["id"], row["subject"])).fetchall()]
            out.append({**dict(row), "boards": boards})
    return {"subjects": out}


@app.get("/api/subjects/score")
def subject_score(name: str, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        projects = [dict(x) for x in conn.execute(
            "SELECT * FROM projects WHERE user_id = ? AND subject_name = ? ORDER BY id",
            (user["id"], name)).fetchall()]
        if not projects:
            raise HTTPException(404, "没有该主体的项目")
        return subject.score_subject(conn, name, projects)


@app.get("/api/projects/{project_id}/score")
def project_score(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    """按评分卡计算五个维度得分。未核查项记 N/A，不计入分母。"""
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        findings = [dict(r) for r in conn.execute(
            "SELECT * FROM findings WHERE project_id = ?", (project_id,)).fetchall()]
        for f in findings:
            f["has_citation"] = conn.execute(
                "SELECT 1 FROM citations WHERE finding_id = ? AND document_id IS NOT NULL LIMIT 1",
                (f["id"],)).fetchone() is not None
        docs = [dict(r) for r in conn.execute(
            "SELECT filename, text FROM documents WHERE project_id = ?", (project_id,)).fetchall()]
        qc_row = conn.execute(
            "SELECT detail FROM qc_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        ext_row = conn.execute(
            "SELECT findings FROM external_checks WHERE project_id = ? ORDER BY id DESC LIMIT 1",
            (project_id,)).fetchone()
        groups = conn.execute(
            "SELECT COUNT(*) AS c FROM document_groups WHERE project_id = ?", (project_id,)).fetchone()["c"]
        versions = conn.execute(
            "SELECT COUNT(*) AS c FROM document_versions v JOIN document_groups g ON g.id = v.group_id"
            " WHERE g.project_id = ?", (project_id,)).fetchone()["c"]

    required = [t for t, _ in agents.BOARD_REQUIRED.get(project["board"], [])]
    corpus = "\n".join((d["text"] or "") + " " + d["filename"] for d in docs)
    present = [t for t in required if any(k in corpus for k in agents.MATERIAL_KEYWORDS.get(t, []))]
    missing = json.loads(project["missing"]) if project.get("missing") else []
    external_findings = json.loads(ext_row["findings"]) if ext_row else []
    qc = json.loads(qc_row["detail"]) if qc_row else None

    return scoring.score_project(
        scoring.load_rubric(),
        analyzed=project["status"] in {"done", "pending_review", "needs_rework"},
        board=project["board"],
        findings=findings,
        external_findings=external_findings,
        external_present=bool(ext_row),
        required_materials=required,
        present_materials=present,
        missing_count=len(missing),
        versions={"groups": groups, "versions": versions,
                  "conflict": any(f["code"] in {"AST-06"} for f in findings)},
        qc=qc,
    )


@app.post("/api/projects/{project_id}/external-check")
def external_check(project_id: int, request: Request, user: dict = Depends(get_current_user)) -> dict:
    """按主体名称查询企查查 + 互联网搜索。密钥由请求头传入，不落库。"""
    with connect() as conn:
        project = _own_project(conn, project_id, user)

    name = (project.get("subject_name") or "").strip()
    if not name:
        raise HTTPException(400, "请先在项目中填写拟上市主体全称")

    qcc_key = (request.headers.get("x-qcc-key") or "").strip()
    qcc_secret = (request.headers.get("x-qcc-secret") or "").strip()
    provider = (request.headers.get("x-search-provider") or "").strip()
    search_key = (request.headers.get("x-search-key") or "").strip()

    result = external.run_check(
        name,
        (qcc_key, qcc_secret) if qcc_key and qcc_secret else None,
        (provider, search_key) if provider and search_key else None,
    )

    if not result["qcc"] and not result["searches"]:
        raise HTTPException(400, "未获取到外部数据：" + "；".join(result["warnings"]))

    with connect() as conn:
        conn.execute(
            "INSERT INTO external_checks(project_id, subject, payload, findings, warnings, created_at)"
            " VALUES (?,?,?,?,?,?)",
            (project_id, name,
             json.dumps({"qcc": result["qcc"], "searches": result["searches"]}, ensure_ascii=False),
             json.dumps(result["findings"], ensure_ascii=False),
             json.dumps(result["warnings"], ensure_ascii=False), now()),
        )
        audit(conn, user["id"], "external_check", f"project:{project_id}",
              f"{name} findings={len(result['findings'])}")
    return result


@app.post("/api/reviews/{review_id}/decision")
def review_decision(review_id: int, payload: ReviewDecisionIn, admin: dict = Depends(require_admin)) -> dict:
    if payload.decision not in {"approved", "rejected"}:
        raise HTTPException(400, "decision 只能是 approved 或 rejected")
    with connect() as conn:
        row = conn.execute("SELECT * FROM review_requests WHERE id = ?", (review_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "复核单不存在")
        if row["status"] != "pending":
            raise HTTPException(409, "该复核单已处理")
        status = "approved" if payload.decision == "approved" else "rejected"
        conn.execute(
            "UPDATE review_requests SET status = ?, reviewer_id = ?, comment = ?, decided_at = ? WHERE id = ?",
            (status, admin["id"], payload.comment, now(), review_id),
        )
        project_status = "done" if status == "approved" else "needs_rework"
        conn.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?",
                     (project_status, now(), row["project_id"]))
        audit(conn, admin["id"], "review_decision", f"review:{review_id}",
              f"{status} project:{row['project_id']} {payload.comment[:80]}")
    return {"ok": True, "status": status, "project_status": project_status}


@app.post("/api/llm/ping")
async def llm_ping(payload: ApiConfigIn, user: dict = Depends(get_current_user)) -> dict:
    """测试 API Key 是否可用；只回显模型列表，不回显密钥。"""
    try:
        models = await llm.ping(payload.model_dump())
        return {"ok": True, "models": models}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)[:200]}



# ----------------------------------------------------------------- 项目
@app.get("/api/projects")
def list_projects(user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.*, (SELECT COUNT(*) FROM documents d WHERE d.project_id = p.id) AS doc_count,"
            " (SELECT COUNT(*) FROM findings f WHERE f.project_id = p.id) AS finding_count"
            " FROM projects p WHERE p.user_id = ? ORDER BY p.id DESC",
            (user["id"],),
        ).fetchall()
    return {"projects": [dict(r) for r in rows]}


@app.post("/api/projects")
def create_project(payload: ProjectIn, user: dict = Depends(get_current_user)) -> dict:
    if payload.board not in BOARDS:
        raise HTTPException(400, "板块不存在")
    with connect() as conn:
        ts = now()
        cur = conn.execute(
            "INSERT INTO projects(user_id, board, title, subject_name, brief, status, is_demo, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (user["id"], payload.board, payload.title, payload.subject_name, payload.brief,
             "draft", 1 if payload.is_demo else 0, ts, ts),
        )
        pid = cur.lastrowid
        audit(conn, user["id"], "create_project", f"project:{pid}", payload.title)
    return {"id": pid}


@app.get("/api/projects/{project_id}")
def get_project(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        docs = [dict(r) for r in conn.execute(
            "SELECT id, filename, pages, status, created_at FROM documents WHERE project_id = ? ORDER BY id",
            (project_id,)).fetchall()]
        findings = [dict(r) for r in conn.execute(
            "SELECT * FROM findings WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()]
        for f in findings:
            f["citations"] = [dict(c) for c in conn.execute(
                "SELECT c.*, d.filename FROM citations c LEFT JOIN documents d ON d.id = c.document_id"
                " WHERE c.finding_id = ?", (f["id"],)).fetchall()]
            f["rule_name"] = None
        qc_row = conn.execute(
            "SELECT * FROM qc_runs WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        report_row = conn.execute(
            "SELECT * FROM reports WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        ext_row = conn.execute(
            "SELECT * FROM external_checks WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
        review_row = conn.execute(
            "SELECT r.*, u.email AS reviewer FROM review_requests r LEFT JOIN users u ON u.id = r.reviewer_id"
            " WHERE r.project_id = ? ORDER BY r.id DESC LIMIT 1", (project_id,)).fetchone()
    external_data = None
    if ext_row:
        external_data = dict(ext_row)
        try:
            external_data["payload"] = json.loads(external_data["payload"])
            external_data["findings"] = json.loads(external_data["findings"])
            external_data["warnings"] = json.loads(external_data["warnings"])
        except json.JSONDecodeError:
            pass
    review_data = None
    if review_row:
        review_data = dict(review_row)
        try:
            review_data["triggers"] = json.loads(review_data["triggers"])
        except json.JSONDecodeError:
            review_data["triggers"] = []
    return {
        "project": project,
        "documents": docs,
        "findings": findings,
        "missing": json.loads(project["missing"]) if project.get("missing") else [],
        "task_spec": json.loads(project["task_spec"]) if project.get("task_spec") else None,
        "qc": dict(qc_row) if qc_row else None,
        "review": review_data,
        "external": external_data,
        "report": {"available": bool(report_row), "version": report_row["version"] if report_row else None},
    }


@app.post("/api/projects/{project_id}/documents")
def upload_documents(project_id: int, files: list[UploadFile] = File(...), user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        project = _own_project(conn, project_id, user)
    if project["status"] == "running":
        raise HTTPException(409, "任务执行中，暂不能上传")

    target = UPLOAD_DIR / f"project-{project_id}"
    target.mkdir(parents=True, exist_ok=True)
    saved = []
    for upload in files:
        raw = upload.file.read()
        if len(raw) > MAX_UPLOAD_MB * 1024 * 1024:
            raise HTTPException(413, f"单文件不得超过 {MAX_UPLOAD_MB}MB：{upload.filename}")
        safe = SAFE_NAME.sub("_", Path(upload.filename or "file").name)
        dest = target / safe
        counter = 1
        while dest.exists():
            dest = target / f"{Path(safe).stem}-{counter}{Path(safe).suffix}"
            counter += 1
        dest.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        text, pages, status = parse_file(dest)
        with connect() as conn:
            cur = conn.execute(
                "INSERT INTO documents(project_id, filename, path, sha256, text, pages, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (project_id, dest.name, str(dest), digest, text, pages, status, now()),
            )
            doc_id = cur.lastrowid
            _register_document_version(conn, project_id, doc_id, dest.name, str(dest), digest, text, user["id"])
            audit(conn, user["id"], "upload", f"project:{project_id}", f"{dest.name} ({status})")
            _recalc_status(conn, project_id)
        saved.append({"id": doc_id, "filename": dest.name, "pages": pages, "status": status})
    return {"documents": saved}


def _version_owner(conn, version_id: int, user: dict) -> dict:
    row = conn.execute(
        "SELECT v.*, g.project_id FROM document_versions v"
        " JOIN document_groups g ON g.id = v.group_id WHERE v.id = ?",
        (version_id,),
    ).fetchone()
    if row is None:
        raise HTTPException(404, "版本不存在")
    _own_project(conn, row["project_id"], user)
    return dict(row)


def _paragraphs(conn, version_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM paragraphs WHERE version_id = ? ORDER BY ordinal", (version_id,)).fetchall()]


@app.get("/api/projects/{project_id}/versions")
def list_versions(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        _own_project(conn, project_id, user)
        groups = [dict(g) for g in conn.execute(
            "SELECT * FROM document_groups WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()]
        for group in groups:
            group["versions"] = [dict(v) for v in conn.execute(
                "SELECT v.*, (SELECT COUNT(*) FROM paragraphs p WHERE p.version_id = v.id) AS paragraph_count"
                " FROM document_versions v WHERE v.group_id = ? ORDER BY v.id", (group["id"],)).fetchall()]
    return {"groups": groups}


@app.post("/api/projects/{project_id}/versions")
def upload_version(
    project_id: int,
    file: UploadFile = File(...),
    group_id: int | None = Form(None),
    label: str = Form(""),
    doc_type: str = Form("其他"),
    user: dict = Depends(get_current_user),
) -> dict:
    """上传新版本：段落对齐到上一版，保持 uid 稳定，并把当前版指针移过来。"""
    with connect() as conn:
        _own_project(conn, project_id, user)

    target = UPLOAD_DIR / f"project-{project_id}" / "versions"
    target.mkdir(parents=True, exist_ok=True)
    safe = SAFE_NAME.sub("_", Path(file.filename or "file").name)
    dest = target / safe
    counter = 1
    while dest.exists():
        dest = target / f"{Path(safe).stem}-{counter}{Path(safe).suffix}"
        counter += 1
    raw = file.file.read()
    dest.write_bytes(raw)
    digest = hashlib.sha256(raw).hexdigest()
    text, pages, status = parse_file(dest)

    with connect() as conn:
        if group_id:
            group = conn.execute(
                "SELECT * FROM document_groups WHERE id = ? AND project_id = ?", (group_id, project_id)).fetchone()
            if group is None:
                raise HTTPException(404, "材料组不存在")
            gid = group["id"]
        else:
            gid = conn.execute(
                "INSERT INTO document_groups(project_id, doc_type, title, created_at) VALUES (?,?,?,?)",
                (project_id, doc_type, Path(safe).stem, now()),
            ).lastrowid

        prev = conn.execute(
            "SELECT * FROM document_versions WHERE group_id = ? ORDER BY id DESC LIMIT 1", (gid,)).fetchone()
        prev_paras = _paragraphs(conn, prev["id"]) if prev else []
        paras = versions.align_to_previous(versions.split_paragraphs(text), prev_paras)

        version_label = label.strip()
        if not version_label:
            count = conn.execute(
                "SELECT COUNT(*) AS c FROM document_versions WHERE group_id = ?", (gid,)).fetchone()["c"]
            version_label = f"V{count + 1}"

        vid = conn.execute(
            "INSERT INTO document_versions(group_id, source_document_id, label, storage_path, sha256,"
            " is_current, uploaded_by, created_at) VALUES (?,?,?,?,?,?,?,?)",
            (gid, None, version_label, str(dest), digest, 1, user["id"], now()),
        ).lastrowid
        conn.execute("UPDATE document_versions SET is_current = 0 WHERE group_id = ? AND id <> ?", (gid, vid))

        for i, para in enumerate(paras, 1):
            conn.execute(
                "INSERT INTO paragraphs(version_id, uid, ordinal, page, text, char_start, char_end)"
                " VALUES (?,?,?,?,?,?,?)",
                (vid, para["uid"], i, para["page"], para["text"], para["char_start"], para["char_end"]),
            )

        # 让流水线始终读当前版本：同一材料组复用一条 documents 记录
        src = prev["source_document_id"] if prev else None
        if src:
            conn.execute(
                "UPDATE documents SET filename = ?, path = ?, sha256 = ?, text = ?, pages = ?, status = ? WHERE id = ?",
                (dest.name, str(dest), digest, text, pages, status, src),
            )
            conn.execute("UPDATE document_versions SET source_document_id = ? WHERE id = ?", (src, vid))
        else:
            src = conn.execute(
                "INSERT INTO documents(project_id, filename, path, sha256, text, pages, status, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (project_id, dest.name, str(dest), digest, text, pages, status, now()),
            ).lastrowid
            conn.execute("UPDATE document_versions SET source_document_id = ? WHERE id = ?", (src, vid))

        audit(conn, user["id"], "upload_version", f"group:{gid}", f"{version_label} {dest.name}")

    diff = versions.diff_versions(prev_paras, paras) if prev_paras else []
    return {
        "version_id": vid,
        "group_id": gid,
        "label": version_label,
        "paragraphs": len(paras),
        "diff": versions.summarize(diff) if prev_paras else None,
    }


@app.get("/api/versions/{version_id}")
def get_version(version_id: int, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        version = _version_owner(conn, version_id, user)
        paras = _paragraphs(conn, version_id)
    return {"version": version, "paragraphs": paras}


@app.get("/api/versions/{version_id}/diff/{other_id}")
def diff_versions(version_id: int, other_id: int, user: dict = Depends(get_current_user)) -> dict:
    """version_id 为旧版，other_id 为新版。"""
    with connect() as conn:
        old = _version_owner(conn, version_id, user)
        new = _version_owner(conn, other_id, user)
        if old["project_id"] != new["project_id"]:
            raise HTTPException(400, "两个版本不属于同一项目")
        old_paras = _paragraphs(conn, version_id)
        new_paras = _paragraphs(conn, other_id)
    items = versions.diff_versions(old_paras, new_paras)
    return {
        "from": {"id": version_id, "label": old["label"]},
        "to": {"id": other_id, "label": new["label"]},
        "summary": versions.summarize(items),
        "items": items,
    }


@app.post("/api/projects/{project_id}/run")
def run_project(project_id: int, background: BackgroundTasks, request: Request, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        if project["status"] == "running":
            raise HTTPException(409, "任务正在执行")
        docs = conn.execute("SELECT id FROM documents WHERE project_id = ?", (project_id,)).fetchone()
        if docs is None:
            raise HTTPException(400, "请先上传材料")
        # 原子扣减积分
        cur = conn.execute(
            "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
            (CREDITS_PER_RUN, user["id"], CREDITS_PER_RUN),
        )
        if cur.rowcount == 0:
            raise HTTPException(402, "积分不足，请联系管理员充值")
        conn.execute(
            "INSERT INTO credits_ledger(user_id, delta, reason, project_id, created_at) VALUES (?,?,?,?,?)",
            (user["id"], -CREDITS_PER_RUN, "核查任务", project_id, now()),
        )
        conn.execute("UPDATE projects SET status = ?, updated_at = ? WHERE id = ?", ("running", now(), project_id))
        remaining = conn.execute("SELECT credits FROM users WHERE id = ?", (user["id"],)).fetchone()["credits"]
        audit(conn, user["id"], "run_project", f"project:{project_id}", f"-{CREDITS_PER_RUN} 积分")

    cfg = {
        "key": (request.headers.get("x-llm-key") or "").strip() or None,
        "model": (request.headers.get("x-llm-model") or "").strip() or None,
        "base": (request.headers.get("x-llm-base") or "").strip() or None,
    }
    background.add_task(execute_pipeline, project_id, user["id"], cfg)
    return {"status": "running", "credits": remaining}


@app.get("/api/rules")
def list_rules(q: str = "", code: str = "", limit: int = 20,
               user: dict = Depends(get_current_user)) -> dict:
    """内置港股上市规则：章节清单、按条号取原文、按主题检索。"""
    limit = max(1, min(limit, 50))
    base = {"stats": rule_refs.stats(), "bindings": rule_refs.RULE_BINDINGS}
    if code:
        return {**base, "clause": rule_refs.by_code(code)}
    if q:
        return {**base, "clauses": rule_refs.lookup(q, limit=limit)}
    return {**base, "chapters": rule_refs.chapters()}


@app.get("/api/projects/{project_id}/progress")
def project_progress(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    """核查进度：逐步返回，前端据此显示「当前核查维度 + 正在做的事」。"""
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        rows = conn.execute(
            "SELECT id, stage, agent, status, detail, created_at FROM task_runs"
            " WHERE project_id = ? ORDER BY id", (project_id,)).fetchall()

    steps = []
    for row in rows:
        board, text = "", row["detail"] or ""
        try:
            parsed = json.loads(row["detail"] or "{}")
            if isinstance(parsed, dict) and ("text" in parsed or "board" in parsed):
                board = parsed.get("board", "") or ""
                text = parsed.get("text", "") or ""
        except (ValueError, TypeError):
            pass  # 旧数据是纯文本，原样展示
        steps.append({
            "id": row["id"], "stage": row["stage"], "agent": row["agent"],
            "status": row["status"], "board": board, "text": text,
            "created_at": row["created_at"],
        })

    current = next((s for s in reversed(steps) if s["status"] == "running"), None)
    with connect() as conn:
        findings = conn.execute("SELECT COUNT(*) AS c FROM findings WHERE project_id = ?",
                                (project_id,)).fetchone()["c"]
    return {
        "status": project["status"],
        "board": project["board"],
        "boards": [BOARDS[k] for k in BOARD_SEQUENCE],
        "steps": steps,
        "total": len(steps),
        "done": sum(1 for s in steps if s["status"] in ("ok", "warn", "skip")),
        "findings": findings,
        "current": current,
    }


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    """删除项目及其全部派生数据（风险、证据、报告、步骤、材料）。只允许本人操作。"""
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        docs = [dict(r) for r in conn.execute(
            "SELECT path FROM documents WHERE project_id = ?", (project_id,)).fetchall()]
        reports = [dict(r) for r in conn.execute(
            "SELECT path FROM reports WHERE project_id = ?", (project_id,)).fetchall()]
        conn.execute("DELETE FROM citations WHERE finding_id IN (SELECT id FROM findings WHERE project_id = ?)", (project_id,))
        conn.execute("DELETE FROM findings WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM qc_runs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM review_requests WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM task_runs WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM external_checks WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM paragraphs WHERE version_id IN ("
                     "SELECT id FROM document_versions WHERE group_id IN ("
                     "SELECT id FROM document_groups WHERE project_id = ?))", (project_id,))
        conn.execute("DELETE FROM document_versions WHERE group_id IN ("
                     "SELECT id FROM document_groups WHERE project_id = ?)", (project_id,))
        conn.execute("DELETE FROM document_groups WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM documents WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM reports WHERE project_id = ?", (project_id,))
        conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
        audit(conn, user["id"], "delete_project", f"project:{project_id}", project["title"])
    for row in docs + reports:
        try:
            Path(row["path"]).unlink(missing_ok=True)
        except OSError:
            pass
    return {"ok": True, "deleted": project_id}


@app.post("/api/projects/{project_id}/reset")
def reset_project(project_id: int, user: dict = Depends(get_current_user)) -> dict:
    with connect() as conn:
        project = _own_project(conn, project_id, user)
        for pid in [project_id]:
            conn.execute("DELETE FROM findings WHERE project_id = ?", (pid,))
            conn.execute("DELETE FROM qc_runs WHERE project_id = ?", (pid,))
            conn.execute("DELETE FROM reports WHERE project_id = ?", (pid,))
        conn.execute("UPDATE projects SET status = 'draft', task_spec = NULL, missing = NULL, updated_at = ? WHERE id = ?",
                     (now(), project_id))
    return {"ok": True}


@app.get("/api/projects/{project_id}/report")
def download_report(project_id: int, user: dict = Depends(get_current_user)):
    with connect() as conn:
        _own_project(conn, project_id, user)
        row = conn.execute(
            "SELECT * FROM reports WHERE project_id = ? ORDER BY id DESC LIMIT 1", (project_id,)).fetchone()
    if row is None or not Path(row["path"]).exists():
        raise HTTPException(404, "报告尚未生成")
    return FileResponse(row["path"], filename=f"核查报告-项目{project_id}-v{row['version']}.docx",
                        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.patch("/api/findings/{finding_id}")
def update_finding(finding_id: int, payload: FindingUpdateIn, user: dict = Depends(get_current_user)) -> dict:
    if payload.status not in {"open", "accepted", "rejected", "fixed"}:
        raise HTTPException(400, "状态非法")
    with connect() as conn:
        row = conn.execute("SELECT * FROM findings WHERE id = ?", (finding_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "结论不存在")
        _own_project(conn, row["project_id"], user)
        conn.execute("UPDATE findings SET status = ? WHERE id = ?", (payload.status, finding_id))
        audit(conn, user["id"], "revise_finding", f"finding:{finding_id}", f"{payload.status} {payload.note}")
    return {"ok": True}


# ----------------------------------------------------------------- 流水线
def _detail_of(board_label: str, text: str) -> str:
    return json.dumps({"board": board_label, "text": text}, ensure_ascii=False)


def _open_step(project_id: int, stage: str, agent: str, board_label: str, text: str) -> int:
    """写一条 running 步骤，前端轮询时看到的就是「正在做什么」。"""
    with connect() as conn:
        cur = conn.execute(
            "INSERT INTO task_runs(project_id, stage, agent, status, detail, created_at) VALUES (?,?,?,?,?,?)",
            (project_id, stage, agent, "running", _detail_of(board_label, text), now()),
        )
        return cur.lastrowid


def _close_step(step_id: int, status: str, board_label: str, text: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE task_runs SET status = ?, detail = ? WHERE id = ?",
                     (status, _detail_of(board_label, text), step_id))


def _beat() -> None:
    """演示模式下的停顿：让每一步在前端可见；接真实模型时不需要。"""
    if MOCK_MODE and MOCK_STEP_DELAY > 0:
        time.sleep(MOCK_STEP_DELAY)


def execute_pipeline(project_id: int, user_id: int, cfg: dict | None = None) -> None:
    try:
        with connect() as conn:
            project = dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
            docs = [dict(r) for r in conn.execute(
                "SELECT * FROM documents WHERE project_id = ?", (project_id,)).fetchall()]

        findings_all: list[dict] = []
        items_all: list[dict] = []
        conflicts_all: list[dict] = []
        missing_all: list[dict] = []
        notices: list[str] = []
        qc_checks: list[dict] = []
        specs: list[dict] = []
        checked: list[str] = []
        skipped: list[str] = []
        qc_passed = True
        failed_total = 0

        # 三个维度依次核查，每一步都留痕，前端据此渲染动态进度
        for key in BOARD_SEQUENCE:
            label = BOARDS[key]
            board_project = {**project, "board": key}
            rules = agents.load_rules(key)

            step = _open_step(project_id, "intent", "A-语言识别", label, f"解析「{label}」的核查要点")
            _beat()
            spec = agents.build_task_spec(board_project, docs, rules, cfg)
            missing = agents.check_missing(spec, docs)
            specs.append(spec)
            _close_step(step, "ok", label, f"识别 {len(spec['checks'])} 项核查要点")

            if missing:
                step = _open_step(project_id, "materials", "B-资料", label, "检查该维度所需材料")
                _beat()
                kinds = "、".join(m["material"] for m in missing)
                _close_step(step, "skip", label, f"材料不全，跳过该维度：{kinds}")
                missing_all.extend(missing)
                skipped.append(label)
                continue

            step = _open_step(project_id, "extract", "B-资料", label, "逐页抽取字段并标注出处")
            _beat()
            extracted = agents.extract(docs, spec, cfg)
            _close_step(step, "ok", label,
                        f"抽取 {len(extracted['items'])} 项，冲突 {len(extracted['conflicts'])} 组")
            items_all.extend(extracted["items"])
            conflicts_all.extend(extracted["conflicts"])

            qc_result: dict = {}
            findings: list[dict] = []
            for round_no in range(1, MAX_QC_ROUNDS + 1):
                step = _open_step(project_id, "analyze", "C-分析", label,
                                  "按要点判读风险等级" if round_no == 1 else f"第 {round_no} 轮：按质检意见重新判读")
                _beat()
                findings = agents.analyze(board_project, extracted, rules)
                _close_step(step, "ok", label, f"识别风险 {len(findings)} 条")

                step = _open_step(project_id, "qc", "D-质检", label, "逐条回原文核对结论与引用")
                _beat()
                qc_result = agents.qc(board_project, findings, docs, rules)
                passed = bool(qc_result.get("passed"))
                _close_step(step, "ok" if passed else "warn", label,
                            "质检通过" if passed else f"阻断 {qc_result.get('failed', 0)} 条，退回重检")
                with connect() as conn:
                    conn.execute(
                        "INSERT INTO qc_runs(project_id, round, passed, detail, created_at) VALUES (?,?,?,?,?)",
                        (project_id, round_no, 1 if passed else 0,
                         json.dumps(qc_result, ensure_ascii=False), now()),
                    )
                if passed:
                    break

            qc_passed = qc_passed and bool(qc_result.get("passed"))
            failed_total += int(qc_result.get("failed", 0) or 0)
            notices.extend(qc_result.get("notices", []) or [])
            qc_checks.extend(qc_result.get("checks", []) or [])
            findings_all.extend(findings)
            checked.append(label)

        if not checked:
            with connect() as conn:
                conn.execute("UPDATE projects SET status = 'awaiting_materials', missing = ?, updated_at = ?"
                             " WHERE id = ?",
                             (json.dumps(missing_all, ensure_ascii=False), now(), project_id))
            return

        with connect() as conn:
            conn.execute("DELETE FROM citations WHERE finding_id IN (SELECT id FROM findings WHERE project_id = ?)",
                         (project_id,))
            conn.execute("DELETE FROM findings WHERE project_id = ?", (project_id,))
            for f in findings_all:
                cur = conn.execute(
                    "INSERT INTO findings(project_id, code, risk_level, title, fact, rule_id, rule_ref, advice, status, qc, created_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (project_id, f["code"], f["risk_level"], f["title"], f["fact"], f.get("rule_id"),
                     f.get("rule_ref") and json.dumps(f["rule_ref"], ensure_ascii=False), f["advice"],
                     f.get("status", "open"), f.get("qc"), now()),
                )
                fid = cur.lastrowid
                for c in f["citations"]:
                    if c.get("document_id") is None:
                        continue
                    conn.execute(
                        "INSERT INTO citations(finding_id, document_id, page, quote) VALUES (?,?,?,?)",
                        (fid, c["document_id"], c.get("page"), c.get("quote", "")[:500]),
                    )

        merged_spec = dict(specs[0]) if specs else {}
        merged_spec.update({
            "board": "all",
            "boards": [BOARDS[k] for k in BOARD_SEQUENCE],
            "checks": [c for s in specs for c in s.get("checks", [])],
            "required_materials": [m for s in specs for m in s.get("required_materials", [])],
        })
        merged_extracted = {"items": items_all, "conflicts": conflicts_all}
        merged_qc = {"passed": qc_passed, "failed": failed_total, "notices": notices, "checks": qc_checks}

        # 港股上市评估专项材料：缺了不阻断三维修查，但资格测试做不了，需要提醒补件
        hk_missing = agents.check_hk_missing(docs)
        step = _open_step(project_id, "hk", "F-港股", "上市评估", "核对港股上市评估专项材料")
        _beat()
        if hk_missing:
            _close_step(step, "warn", "上市评估",
                        "缺 " + "、".join(m["material"] for m in hk_missing))
            missing_all.extend(hk_missing)
        else:
            _close_step(step, "ok", "上市评估", "上市专项材料齐全")

        step = _open_step(project_id, "report", "E-报告", "汇总", "汇总结论、生成可下载报告")
        _beat()

        with connect() as conn:
            conn.execute("UPDATE projects SET task_spec = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(merged_spec, ensure_ascii=False), now(), project_id))
            count = conn.execute("SELECT COUNT(*) AS c FROM reports WHERE project_id = ?", (project_id,)).fetchone()["c"]
            version = count + 1
            path = REPORT_DIR / f"project-{project_id}-v{version}.docx"
            project = dict(conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone())
            stats = conn.execute(
                "SELECT (SELECT COUNT(*) FROM document_groups WHERE project_id = ?) AS groups,"
                " (SELECT COUNT(*) FROM document_versions v JOIN document_groups g ON g.id = v.group_id"
                "  WHERE g.project_id = ?) AS versions",
                (project_id, project_id),
            ).fetchone()
            triggers = review.evaluate(project, findings_all, merged_extracted, merged_qc, dict(stats))

            build_report(path, project, docs, findings_all, merged_spec, merged_qc, missing_all,
                         "资产权属 / 劳动用工 / 投资退出（三维度全面核查）", triggers)
            conn.execute("INSERT INTO reports(project_id, path, version, created_at) VALUES (?,?,?,?)",
                         (project_id, str(path), version, now()))

            if triggers:
                conn.execute("DELETE FROM review_requests WHERE project_id = ? AND status = 'pending'", (project_id,))
                conn.execute(
                    "INSERT INTO review_requests(project_id, triggers, status, created_at) VALUES (?,?,?,?)",
                    (project_id, json.dumps(triggers, ensure_ascii=False), "pending", now()),
                )
                new_status = "pending_review"
                detail = f"findings={len(findings_all)} triggers={len(triggers)}"
            else:
                new_status = "done"
                detail = f"findings={len(findings_all)} triggers=0"

            conn.execute("UPDATE projects SET status = ?, missing = ?, updated_at = ? WHERE id = ?",
                         (new_status, json.dumps(missing_all, ensure_ascii=False), now(), project_id))
            audit(conn, user_id, "pipeline_done", f"project:{project_id}", detail)

        _close_step(step, "ok", "汇总",
                    f"完成：{len(findings_all)} 条风险（{'、'.join(checked)}）")
    except Exception as exc:  # noqa: BLE001
        with connect() as conn:
            conn.execute("UPDATE projects SET status = 'failed', updated_at = ? WHERE id = ?", (now(), project_id))
            conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (CREDITS_PER_RUN, user_id))
            conn.execute(
                "INSERT INTO credits_ledger(user_id, delta, reason, project_id, created_at) VALUES (?,?,?,?,?)",
                (user_id, CREDITS_PER_RUN, "任务失败退还", project_id, now()),
            )
            conn.execute(
                "INSERT INTO task_runs(project_id, stage, agent, status, detail, created_at) VALUES (?,?,?,?,?,?)",
                (project_id, "error", "pipeline", "fail", _detail_of("", str(exc)[:500]), now()),
            )
            audit(conn, user_id, "pipeline_failed", f"project:{project_id}", str(exc)[:300])


# ----------------------------------------------------------------- 管理后台
@app.get("/api/admin/overview")
def admin_overview(admin: dict = Depends(require_admin)) -> dict:
    with connect() as conn:
        users = conn.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
        projects = conn.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"]
        runs = conn.execute("SELECT COUNT(*) AS c FROM task_runs").fetchone()["c"]
        findings = conn.execute("SELECT COUNT(*) AS c FROM findings").fetchone()["c"]
        credits = conn.execute("SELECT COALESCE(SUM(credits),0) AS c FROM users").fetchone()["c"]
    return {"users": users, "projects": projects, "task_steps": runs, "findings": findings,
            "credits_total": credits, "mock_mode": MOCK_MODE}


@app.get("/api/admin/users")
def admin_users(admin: dict = Depends(require_admin)) -> dict:
    with connect() as conn:
        rows = conn.execute("SELECT id, email, role, credits, created_at FROM users ORDER BY id").fetchall()
    return {"users": [dict(r) for r in rows]}


@app.post("/api/admin/users/{user_id}/credits")
def admin_credits(user_id: int, payload: CreditsIn, admin: dict = Depends(require_admin)) -> dict:
    with connect() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "用户不存在")
        conn.execute("UPDATE users SET credits = credits + ? WHERE id = ?", (payload.delta, user_id))
        conn.execute("INSERT INTO credits_ledger(user_id, delta, reason, created_at) VALUES (?,?,?,?)",
                     (user_id, payload.delta, payload.reason, now()))
        audit(conn, admin["id"], "adjust_credits", f"user:{user_id}", f"{payload.delta} {payload.reason}")
        credits = conn.execute("SELECT credits FROM users WHERE id = ?", (user_id,)).fetchone()["credits"]
    return {"ok": True, "credits": credits}


@app.get("/api/admin/projects")
def admin_projects(admin: dict = Depends(require_admin)) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT p.*, u.email FROM projects p JOIN users u ON u.id = p.user_id ORDER BY p.id DESC LIMIT 200"
        ).fetchall()
    return {"projects": [dict(r) for r in rows]}


@app.get("/api/admin/audit")
def admin_audit(admin: dict = Depends(require_admin)) -> dict:
    with connect() as conn:
        rows = conn.execute(
            "SELECT a.*, u.email FROM audit_log a LEFT JOIN users u ON u.id = a.actor_id ORDER BY a.id DESC LIMIT 100"
        ).fetchall()
    return {"logs": [dict(r) for r in rows]}


@app.get("/api/admin/rules")
def admin_rules(admin: dict = Depends(require_admin)) -> dict:
    return {"rules": agents.load_rules("asset")}


@app.put("/api/admin/rules/{rule_id}")
def admin_update_rule(rule_id: str, payload: RuleUpdateIn, admin: dict = Depends(require_admin)) -> dict:
    path = Path(agents.RULES_DIR) / "asset.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    hit = None
    for cp in data.get("checkpoints", []):
        if cp["id"] == rule_id:
            hit = cp
            break
    if hit is None:
        raise HTTPException(404, "核查要点不存在")
    if payload.rule_ref is not None:
        hit["rule_ref"] = payload.rule_ref
    if payload.verification_status:
        hit["verification_status"] = payload.verification_status
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    with connect() as conn:
        audit(conn, admin["id"], "update_rule", rule_id, json.dumps(payload.model_dump(), ensure_ascii=False)[:300])
    return {"ok": True, "rule": hit}


# ----------------------------------------------------------------- 前端静态托管
_DIST = ROOT_DIR / "frontend" / "dist"
if _DIST.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=str(_DIST), html=True), name="web")
else:
    @app.get("/")
    def placeholder() -> dict:
        return {"msg": "后端已启动；前端尚未构建（frontend/dist 不存在）。API 文档见 /docs"}
