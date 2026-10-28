"""文档版本、段落切分、跨版本对齐与差异计算。

设计要点：
- 段落用 uid 标识，跨版本尽量保持不变，这样「段落 92」这类引用在版本更新后仍然有效。
- 对齐采用文本相似度（difflib），阈值 0.7；对不上的视为新增/删除。
- 版本只增不改，is_current 单指针。
"""
from __future__ import annotations

import difflib
import re
import uuid

PAGE_MARK = re.compile(r"^\[\[PAGE (\d+)\]\]$")


def split_paragraphs(text: str) -> list[dict]:
    """把带 [[PAGE n]] 标记的正文切成段落，记录页码与字符偏移。"""
    out: list[dict] = []
    page = 1
    offset = 0
    for raw in (text or "").split("\n"):
        stripped = raw.strip()
        marker = PAGE_MARK.match(stripped)
        if marker:
            page = int(marker.group(1))
            offset += len(raw) + 1
            continue
        if stripped:
            out.append(
                {
                    "page": page,
                    "text": stripped,
                    "char_start": offset,
                    "char_end": offset + len(raw),
                }
            )
        offset += len(raw) + 1
    return out


def align_to_previous(new_paras: list[dict], prev_paras: list[dict], threshold: float = 0.7) -> list[dict]:
    """为新版本段落分配稳定 uid：能与旧版段落对上的沿用旧 uid。"""
    used: set[int] = set()
    result: list[dict] = []
    for para in new_paras:
        best_idx = -1
        best_ratio = 0.0
        for idx, prev in enumerate(prev_paras):
            if idx in used:
                continue
            ratio = difflib.SequenceMatcher(None, para["text"], prev["text"]).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = idx
        if best_idx >= 0 and best_ratio >= threshold:
            used.add(best_idx)
            uid = prev_paras[best_idx]["uid"]
        else:
            uid = uuid.uuid4().hex[:12]
        result.append({**para, "uid": uid})
    return result


def diff_versions(old_paras: list[dict], new_paras: list[dict]) -> list[dict]:
    """按 uid 计算差异：added / removed / changed。"""
    old_map = {p["uid"]: p for p in old_paras}
    new_map = {p["uid"]: p for p in new_paras}
    items: list[dict] = []

    for para in new_paras:
        prev = old_map.get(para["uid"])
        if prev is None:
            items.append({"kind": "added", "right": para})
        elif prev["text"].strip() != para["text"].strip():
            items.append({
                "kind": "changed",
                "left": prev,
                "right": para,
                "ratio": round(difflib.SequenceMatcher(None, prev["text"], para["text"]).ratio(), 3),
            })

    for para in old_paras:
        if para["uid"] not in new_map:
            items.append({"kind": "removed", "left": para})

    return items


def summarize(items: list[dict]) -> dict:
    counts = {"added": 0, "removed": 0, "changed": 0}
    for item in items:
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    counts["total"] = len(items)
    return counts
