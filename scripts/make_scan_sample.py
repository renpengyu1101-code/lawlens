"""生成「扫描件」样例 PDF（只有图像、没有文字层），用于验证 OCR。

用法：.venv\\Scripts\\python.exe scripts\\make_scan_sample.py
产物：samples/扫描件样例/*.pdf（来自 虚构材料-澜川精密 的资产类材料）
"""
from __future__ import annotations

from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # 旧版 PyMuPDF 只提供 fitz
    import fitz

ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = ROOT / "samples" / "虚构材料-澜川精密-2026-10"
OUT_DIR = ROOT / "samples" / "扫描件样例"
FONT_FILE = Path("C:/Windows/Fonts/msyh.ttc")
PICK = ["资产-01-不动产权证摘录", "资产-02-国有建设用地", "资产-03-房屋租赁合同",
        "资产-04-商标注册证", "资产-05-排污许可证", "资产-06-发明专利"]


def scan_one(src_docx: Path) -> Path:
    import docx

    document = docx.Document(str(src_docx))
    lines = [p.text.strip() for p in document.paragraphs if p.text.strip()]
    text = "\n".join(lines)
    if not text:
        raise RuntimeError(f"{src_docx.name} 没有文字")

    stage = OUT_DIR / "_stage.pdf"
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_font(fontname="msyh", fontfile=str(FONT_FILE))
    page.insert_textbox(fitz.Rect(56, 56, 539, 786), text, fontname="msyh", fontsize=11, lineheight=1.6)
    doc.save(str(stage))
    doc.close()

    src = fitz.open(str(stage))
    pix = src.load_page(0).get_pixmap(dpi=150)
    src.close()

    parts = src_docx.stem.split("-")
    tag = f"{parts[1]}-{parts[2]}" if len(parts) >= 3 else src_docx.stem
    out = OUT_DIR / f"{tag}-扫描.pdf"
    scan = fitz.open()
    page = scan.new_page(width=595, height=842)
    page.insert_image(page.rect, pixmap=pix)
    scan.save(str(out), deflate=True, garbage=3)
    scan.close()
    stage.unlink(missing_ok=True)
    return out


def main() -> int:
    if not SRC_DIR.exists():
        print(f"[FAIL] 找不到源目录 {SRC_DIR}")
        return 1
    if not FONT_FILE.exists():
        print(f"[FAIL] 找不到中文字体 {FONT_FILE}")
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    for prefix in PICK:
        hits = sorted(SRC_DIR.glob(f"{prefix}*.docx"))
        if not hits:
            print(f"[SKIP] 没有 {prefix}*")
            continue
        out = scan_one(hits[0])
        print(f"[OK] {out.name}  {out.stat().st_size // 1024} KB")
        done += 1
    print(f"\n共生成 {done} 份扫描件 → {OUT_DIR}")
    return 0 if done else 1


if __name__ == "__main__":
    raise SystemExit(main())
