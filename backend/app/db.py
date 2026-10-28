"""SQLite 访问层：每次请求开连接，行工厂返回 dict 风格 Row。"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager

from .config import DB_PATH, DATA_DIR, UPLOAD_DIR, REPORT_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    pwd_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    credits INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS credits_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    reason TEXT NOT NULL,
    project_id INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    board TEXT NOT NULL,
    title TEXT NOT NULL,
    subject_name TEXT NOT NULL DEFAULT '',
    brief TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'draft',
    task_spec TEXT,
    missing TEXT,
    is_demo INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    text TEXT NOT NULL DEFAULT '',
    pages INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'parsed',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS findings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    code TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    title TEXT NOT NULL,
    fact TEXT NOT NULL,
    rule_id TEXT,
    rule_ref TEXT,
    advice TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    qc TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS citations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    finding_id INTEGER NOT NULL,
    document_id INTEGER NOT NULL,
    page INTEGER,
    quote TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS qc_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    round INTEGER NOT NULL,
    passed INTEGER NOT NULL,
    detail TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS task_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    agent TEXT NOT NULL,
    status TEXT NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    path TEXT NOT NULL,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_id INTEGER,
    action TEXT NOT NULL,
    target TEXT,
    detail TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_projects_user ON projects(user_id);
CREATE INDEX IF NOT EXISTS idx_docs_project ON documents(project_id);
CREATE INDEX IF NOT EXISTS idx_findings_project ON findings(project_id);
CREATE INDEX IF NOT EXISTS idx_citations_finding ON citations(finding_id);
CREATE TABLE IF NOT EXISTS document_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    doc_type TEXT NOT NULL DEFAULT '其他',
    title TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS document_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id INTEGER NOT NULL,
    source_document_id INTEGER,
    label TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    is_current INTEGER NOT NULL DEFAULT 1,
    uploaded_by INTEGER,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS paragraphs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL,
    uid TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    page INTEGER,
    text TEXT NOT NULL,
    char_start INTEGER,
    char_end INTEGER
);
CREATE INDEX IF NOT EXISTS idx_versions_group ON document_versions(group_id);
CREATE INDEX IF NOT EXISTS idx_para_version ON paragraphs(version_id);
CREATE TABLE IF NOT EXISTS review_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    triggers TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    reviewer_id INTEGER,
    comment TEXT,
    created_at TEXT NOT NULL,
    decided_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_review_project ON review_requests(project_id);
CREATE TABLE IF NOT EXISTS external_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    payload TEXT NOT NULL,
    findings TEXT NOT NULL,
    warnings TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    board TEXT NOT NULL,
    document_id INTEGER,
    filename TEXT,
    page INTEGER,
    field TEXT NOT NULL,
    value TEXT,
    quote TEXT,
    confidence REAL,
    source TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_extractions_project ON extractions(project_id);
"""


def _ensure_columns(conn) -> None:
    """轻量迁移：init_db 只建表不换结构，老库靠这里补列。"""
    cols = {row["name"] for row in conn.execute("PRAGMA table_info(users)")}
    if "is_active" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")   # 读写并发更稳；备份脚本用 SQLite .backup，兼容
        conn.executescript(SCHEMA)
        _ensure_columns(conn)


@contextmanager
def connect():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def now() -> str:
    from datetime import datetime, timezone, timedelta
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="seconds")


def audit(conn, actor_id, action, target=None, detail=None) -> None:
    conn.execute(
        "INSERT INTO audit_log(actor_id, action, target, detail, created_at) VALUES (?,?,?,?,?)",
        (actor_id, action, target, detail, now()),
    )
