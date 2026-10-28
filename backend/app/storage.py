"""存储用量与垃圾回收。

原则：
- 配额按**项目**算（一个项目的材料 + 历史版本），避免单项目把磁盘吃满；
- 「孤立文件」= 磁盘上存在、但 documents / document_versions / reports 三张表都不引用的文件；
  上传中断、替换失败、人工拷贝都可能产生；
- 清理默认 dry-run，只有显式 apply 才删；删除前会再核一次引用，避免误删正在用的材料。
"""
from __future__ import annotations

import os
from pathlib import Path

from .config import DATA_DIR, REPORT_DIR, UPLOAD_DIR
from .db import connect


def _dir_usage(path: Path) -> tuple[int, int]:
    total = 0
    count = 0
    if not path.exists():
        return 0, 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
                count += 1
            except OSError:
                continue
    return total, count


def project_usage(project_id: int) -> tuple[int, int]:
    """项目目录（含 versions 子目录）的字节数与文件数。"""
    return _dir_usage(UPLOAD_DIR / f"project-{project_id}")


def _norm(path: str | os.PathLike) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def referenced_paths() -> set[str]:
    """数据库里真正在用的文件路径（统一成小写绝对路径比较）。"""
    refs: set[str] = set()
    with connect() as conn:
        for row in conn.execute("SELECT path FROM documents"):
            if row["path"]:
                refs.add(_norm(row["path"]))
        for row in conn.execute("SELECT storage_path FROM document_versions"):
            if row["storage_path"]:
                refs.add(_norm(row["storage_path"]))
        for row in conn.execute("SELECT path FROM reports"):
            if row["path"]:
                refs.add(_norm(row["path"]))
    return refs


def _walk_all():
    for base in (UPLOAD_DIR, REPORT_DIR):
        if not base.exists():
            continue
        for dirpath, _dirs, files in os.walk(base):
            for name in files:
                yield Path(dirpath) / name


def scan() -> dict:
    """用量总览 + 孤立文件清单（不删除）。"""
    refs = referenced_paths()
    upload_bytes = upload_files = 0
    report_bytes = report_files = 0
    orphans: list[dict] = []
    for path in _walk_all():
        try:
            size = path.stat().st_size
        except OSError:
            continue
        inside_reports = REPORT_DIR in path.parents
        if inside_reports:
            report_bytes += size
            report_files += 1
        else:
            upload_bytes += size
            upload_files += 1
        if _norm(path) not in refs:
            orphans.append({"path": str(path), "bytes": size})

    per_project: dict[int, dict] = {}
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, title, user_id FROM projects ORDER BY id").fetchall()
        owners = {r["id"]: r["title"] for r in rows}
        project_ids = [r["id"] for r in rows]
        doc_counts = {r["project_id"]: r["c"] for r in conn.execute(
            "SELECT project_id, COUNT(*) AS c FROM documents GROUP BY project_id")}
    for pid in project_ids:
        size, files = project_usage(pid)
        per_project[pid] = {
            "project_id": pid,
            "title": owners.get(pid, ""),
            "upload_bytes": size,
            "upload_files": files,
            "documents": doc_counts.get(pid, 0),
        }
    # 磁盘上存在、但项目已删除的目录
    stray_dirs = []
    if UPLOAD_DIR.exists():
        for child in UPLOAD_DIR.iterdir():
            if child.is_dir() and child.name.startswith("project-"):
                try:
                    pid = int(child.name.split("-", 1)[1])
                except (IndexError, ValueError):
                    continue
                if pid not in per_project:
                    size, files = _dir_usage(child)
                    stray_dirs.append({"dir": str(child), "bytes": size, "files": files})

    orphans.sort(key=lambda x: -x["bytes"])
    return {
        "data_dir": str(DATA_DIR),
        "upload": {"bytes": upload_bytes, "files": upload_files},
        "reports": {"bytes": report_bytes, "files": report_files},
        "total_bytes": upload_bytes + report_bytes,
        "projects": sorted(per_project.values(), key=lambda x: -x["upload_bytes"]),
        "orphans": orphans[:200],
        "orphan_count": len(orphans),
        "orphan_bytes": sum(o["bytes"] for o in orphans),
        "stray_project_dirs": stray_dirs,
    }


def collect(apply: bool = False) -> dict:
    """清理孤立文件与空目录。apply=False 时只报告。"""
    data = scan()
    refs = referenced_paths()          # 再取一次，缩小与扫描之间的时间窗
    deleted: list[dict] = []
    failed: list[dict] = []
    freed = 0
    for item in data["orphans"]:
        path = Path(item["path"])
        if _norm(path) in refs:
            continue
        if not apply:
            deleted.append({"path": str(path), "bytes": item["bytes"]})
            freed += item["bytes"]
            continue
        try:
            size = path.stat().st_size
            path.unlink()
            deleted.append({"path": str(path), "bytes": size})
            freed += size
        except OSError as exc:
            failed.append({"path": str(path), "error": str(exc)})

    removed_dirs = 0
    if apply:
        for base in (UPLOAD_DIR, REPORT_DIR):
            if not base.exists():
                continue
            for dirpath, dirs, _files in os.walk(base, topdown=False):
                for name in dirs:
                    target = Path(dirpath) / name
                    try:
                        if not any(target.iterdir()):
                            target.rmdir()
                            removed_dirs += 1
                    except OSError:
                        continue
            for stray in data["stray_project_dirs"]:
                target = Path(stray["dir"])
                try:
                    if target.exists() and not any(target.iterdir()):
                        target.rmdir()
                        removed_dirs += 1
                except OSError:
                    continue

    return {
        "applied": apply,
        "deleted": deleted,
        "failed": failed,
        "freed_bytes": freed,
        "removed_dirs": removed_dirs,
        "orphan_count": data["orphan_count"],
        "orphan_bytes": data["orphan_bytes"],
    }
