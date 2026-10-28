"""PDF 报告：用 PyMuPDF 内置中文字体直接排版，不依赖 LibreOffice / 外部服务。

取舍：docx 仍是主交付物；PDF 是「打印/归档」用的只读版本，因此不做合并单元格这类复杂表格，
     而是把每条结论展开成段落（编号、等级、事实、依据、建议、证据），保证每页可读。
"""
from __future__ import annotations

import re
from pathlib import Path

import fitz

W, H = 595, 842          # A4
M = 48                   # 页边距
CELL_PAD = 4
FONT = "china-ss"        # 内置简体无衬线字体（随 PyMuPDF 分发，无外部依赖）
LATIN = "helv"           # 内置 Helvetica：ASCII 用西文字体，避免被中文字体排成全角

LEVEL_CN = {"high": "高", "medium": "中", "low": "低"}
QC_CN = {"pass": "通过", "fail": "未通过", "insufficient": "材料缺失，无法验证"}

_CJK = re.compile(r"[\u2e80-\u9fff\uf900-\ufaff\ufe30-\ufe4f\uff00-\uffef]")
# 行首禁则：这些标点不允许独占行首，宁可让本行轻微超宽
_CLOSERS = "。，、；：）》」』】%！？"


def _is_cjk(ch: str) -> bool:
    return bool(_CJK.match(ch))


def _char_width(ch: str, size: float) -> float:
    return fitz.get_text_length(ch, fontname=FONT if _is_cjk(ch) else LATIN, fontsize=size)


def _text_width(text: str, size: float) -> float:
    return sum(_char_width(ch, size) for ch in text)


def _draw_mixed(page: "fitz.Page", x: float, y: float, text: str, size: float, color) -> None:
    """按字符把中英文切成两段分别绘制：中文用内置 CJK 字体，ASCII 用 Helvetica。"""
    if not text:
        return
    run = ""
    run_cjk = _is_cjk(text[0])
    for ch in text:
        cjk = _is_cjk(ch)
        if run and cjk != run_cjk:
            page.insert_text((x, y), run, fontname=FONT if run_cjk else LATIN,
                             fontsize=size, color=color)
            x += _text_width(run, size)
            run = ""
        run += ch
        run_cjk = cjk
    if run:
        page.insert_text((x, y), run, fontname=FONT if run_cjk else LATIN,
                         fontsize=size, color=color)


class _Flow:
    """极简排版器：按字符宽度折行 + 自动分页 + 页脚页码。"""

    def __init__(self) -> None:
        self.doc = fitz.open()
        self.page: fitz.Page | None = None

    def _new_page(self) -> None:
        self.page = self.doc.new_page(width=W, height=H)
        self.page.insert_font(fontname=FONT)
        self.y = M

    def start(self) -> None:
        self._new_page()

    def _wrap(self, text: str, size: float, width: float) -> list[str]:
        out: list[str] = []
        for raw in str(text).split("\n"):
            if not raw:
                out.append("")
                continue
            cur = ""
            cur_w = 0.0
            for ch in raw:
                w = _char_width(ch, size)
                if cur and cur_w + w > width:
                    if ch in _CLOSERS:
                        cur += ch
                        cur_w += w
                        continue
                    out.append(cur)
                    cur, cur_w = ch, w
                else:
                    cur += ch
                    cur_w += w
            out.append(cur)
        return out

    def text(self, text, size=10.0, color=(0.09, 0.09, 0.09), indent=0.0,
             gap=3.0, line_height=1.62, bold_tint=None) -> None:
        width = W - 2 * M - indent
        step = size * line_height
        for line in self._wrap(str(text), size, width):
            if self.y + step > H - M - 16:
                self._new_page()
            if line:
                _draw_mixed(self.page, M + indent, self.y + size, line, size, color)
            self.y += step
        self.y += gap

    def rule(self, gap_before=6, gap_after=8) -> None:
        self.y += gap_before
        if self.y > H - M - 16:
            self._new_page()
        self.page.draw_line(fitz.Point(M, self.y), fitz.Point(W - M, self.y),
                            color=(0.80, 0.79, 0.76), width=0.7)
        self.y += gap_after

    def table(self, headers, rows, widths, size=8.2,
              header_fill=(0.945, 0.937, 0.918), line_color=(0.82, 0.81, 0.78)) -> None:
        """带线框的表格：列宽按内容宽度比例分配，行高按最长单元格算，跨页自动重画表头。"""
        content = W - 2 * M
        cols = [content * w for w in widths]
        line_h = size * 1.5

        def cells_lines(cells):
            return [self._wrap(str(c), size, cols[i] - 2 * CELL_PAD) for i, c in enumerate(cells)]

        def height_of(lines):
            return max(1, max(len(x) for x in lines)) * line_h + 2 * CELL_PAD

        def draw_row(cells, lines, height, is_header=False):
            x = M
            if is_header:
                self.page.draw_rect(fitz.Rect(M, self.y, W - M, self.y + height),
                                    color=None, fill=header_fill)
            for i, _cell in enumerate(cells):
                self.page.draw_rect(fitz.Rect(x, self.y, x + cols[i], self.y + height),
                                    color=line_color, width=0.5)
                ty = self.y + CELL_PAD
                for line in lines[i]:
                    if line:
                        _draw_mixed(self.page, x + CELL_PAD, ty + size, line, size,
                                    (0.20, 0.20, 0.18) if is_header else (0.11, 0.11, 0.11))
                    ty += line_h
                x += cols[i]
            self.y += height

        head_lines = cells_lines(headers)
        head_h = height_of(head_lines)
        first_h = height_of(cells_lines(rows[0])) if rows else 0
        if self.y + head_h + first_h > H - M - 16:
            self._new_page()
        draw_row(headers, head_lines, head_h, is_header=True)
        for row in rows:
            lines = cells_lines(row)
            h = height_of(lines)
            if self.y + h > H - M - 16:
                self._new_page()
                draw_row(headers, head_lines, head_h, is_header=True)
            draw_row(row, lines, h)
        self.y += 6

    def finish(self, path: Path) -> Path:
        total = self.doc.page_count
        for idx, page in enumerate(self.doc, 1):
            _draw_mixed(page, W - M - 74, H - 28, f"第 {idx} / {total} 页", 8, (0.55, 0.54, 0.50))
            _draw_mixed(page, M, H - 28, "LawLens · 机器辅助整理，不构成法律意见", 8, (0.55, 0.54, 0.50))
        path.parent.mkdir(parents=True, exist_ok=True)
        self.doc.save(str(path))
        self.doc.close()
        return path


def build_pdf(path: Path, project: dict, docs: list[dict], findings: list[dict],
              spec: dict, qc_result: dict, missing: list[dict],
              board_label: str = "资产权属与经营基础",
              triggers: list[dict] | None = None) -> Path:
    flow = _Flow()
    flow.start()

    # 标题
    flow.text(project.get("title", ""), size=17, gap=2, line_height=1.4)
    flow.text(f"{board_label}核查报告", size=10.5, color=(0.42, 0.41, 0.38), gap=6)
    if project.get("is_demo"):
        flow.text("【虚构测试样本 · 仅用于系统演示，不得用于任何真实交易或法律结论】",
                  size=9.5, color=(0.65, 0.16, 0.11), gap=4)
    flow.rule()

    # 元信息
    meta = [
        ("拟上市主体", project.get("subject_name") or "（未填写）"),
        ("业务板块", board_label),
        ("生成时间", str(project.get("updated_at", "")).replace("T", " ")[:19]),
        ("分析模式", "演示模式（未接模型，规则启发式）" if spec.get("mode") == "mock" else "模型分析（DeepSeek）"),
        ("材料数量", f"{len(docs)} 份"),
        ("质检结论", ("通过" if qc_result.get("passed") else "未通过")
         + f"（核查 {qc_result.get('checked', 0)} 条，阻断项 {qc_result.get('failed', 0)} 条）"),
    ]
    for k, v in meta:
        flow.text(f"{k}：{v}", size=9, color=(0.30, 0.30, 0.28), gap=1.2, line_height=1.5)
    flow.rule()

    # 一、核查范围
    flow.text("一、核查范围与任务单", size=12.5, gap=4)
    flow.text(f"核查目标：{spec.get('objective', '')}", size=9.5, gap=3)
    for cp in spec.get("checks", []):
        flow.text(f"· {cp['id']} {cp['topic']}：{cp['check_point']}", size=9, gap=1.2, indent=8)
    flow.y += 4

    # 二、材料
    flow.text("二、材料清单", size=12.5, gap=3)
    if docs:
        flow.table(
            ["序号", "文件名", "页数", "状态"],
            [[str(i), d["filename"], str(d.get("pages", "")), str(d.get("status", ""))]
             for i, d in enumerate(docs, 1)],
            [0.07, 0.63, 0.10, 0.20],
        )
    else:
        flow.text("（无）", size=9, gap=3)
    flow.y += 2

    # 三、缺料
    if missing:
        flow.text("三、缺失材料", size=12.5, gap=3)
        for m in missing:
            flow.text(f"· {m['material']} —— 用于 {m['needed_for']}", size=9, gap=0.8)
        flow.y += 4

    # 四、风险清单（表格）
    flow.text(f"四、风险清单（{len(findings)} 条）", size=12.5, gap=4)
    if findings:
        rows = []
        for f in findings:
            loc = "；".join(f"{c['filename']} p{c['page']}" for c in f["citations"] if c.get("document_id")) or "（材料缺失）"
            rows.append([
                f["code"],
                LEVEL_CN.get(f["risk_level"], f["risk_level"]),
                f["title"],
                loc,
                QC_CN.get(f.get("qc", ""), ""),
            ])
        flow.table(["编号", "等级", "结论", "证据定位", "质检"], rows, [0.10, 0.07, 0.40, 0.33, 0.10])
    else:
        flow.text("本次未识别出风险项。这不等于不存在风险，仅表示在现有材料与要点范围内未发现。", size=9.5, gap=3)

    # 五、逐项说明
    flow.rule()
    flow.text(f"五、逐项说明与整改建议（{len(findings)} 条）", size=12.5, gap=4)
    for idx, f in enumerate(findings, 1):
        flow.text(f"{idx}. [{f['code']}] {f['title']}（{LEVEL_CN.get(f['risk_level'], f['risk_level'])}风险）",
                  size=10.5, gap=2)
        flow.text(f"事实：{f['fact']}", size=9, gap=1.2, indent=10)
        flow.text(f"依据：{f.get('rule_id') or '—'} {f.get('rule_ref') or '（规范依据待补）'}",
                  size=9, color=(0.42, 0.41, 0.38), gap=1.2, indent=10)
        flow.text(f"建议：{f['advice']}", size=9, gap=1.2, indent=10)
        anchor = [c for c in f["citations"] if c.get("document_id")]
        if anchor:
            flow.text("证据：", size=9, color=(0.42, 0.41, 0.38), gap=0.8, indent=10)
            for c in anchor:
                flow.text(f"《{c['filename']}》第 {c['page']} 页：「{c['quote'][:260]}」",
                          size=8.5, color=(0.36, 0.35, 0.32), gap=0.8, indent=18)
        else:
            flow.text("证据：（无原文锚点：对应材料缺失，本条仅作补料提示）",
                      size=9, color=(0.42, 0.41, 0.38), gap=1, indent=10)
        flow.text(f"质检：{QC_CN.get(f.get('qc', ''), '未质检')}", size=8.5,
                  color=(0.42, 0.41, 0.38), gap=4, indent=10)

    # 六、质检
    flow.rule()
    flow.text("六、质检结论", size=12.5, gap=3)
    flow.text(f"共核查 {qc_result.get('checked', 0)} 条结论；阻断项 {qc_result.get('failed', 0)} 条；"
              f"结果：{'通过' if qc_result.get('passed') else '未通过'}。", size=9.5, gap=2)
    for issue in qc_result.get("issues", []):
        flow.text(f"· [{issue['code']}] {issue['title']}：{issue['reason']}", size=9, gap=0.8)
    for notice in qc_result.get("notices", []):
        flow.text(f"· [{notice['code']}] {notice['title']}：{notice['reason']}", size=9, gap=0.8)
    if qc_result.get("note"):
        flow.text(f"注：{qc_result['note']}", size=9, color=(0.42, 0.41, 0.38), gap=2)

    # 七、复核
    if triggers:
        flow.rule()
        flow.text("七、须律师复核的事项", size=12.5, gap=3)
        flow.text(f"本次核查触发 {len(triggers)} 项复核条件，律师确认前本报告不得作为最终结论。",
                  size=9, gap=3)
        for t in triggers:
            flow.text(f"· {t['code']} {t['title']}（{t['category']}）", size=9.5, gap=1)
            flow.text(t["detail"], size=9, color=(0.36, 0.35, 0.32), gap=1.2, indent=10)
            for ev in t.get("evidence", []):
                flow.text(f"– {ev}", size=8.5, color=(0.42, 0.41, 0.38), gap=0.8, indent=18)
            flow.y += 2

    # 八、声明
    flow.rule()
    flow.text("八、声明与限制", size=12.5, gap=3)
    for line in [
        "本报告为机器辅助整理结果，不构成法律意见，不替代律师专业判断。",
        "结论仅基于本次上传材料及其可提取文本；扫描件、缺页、未提供材料的核查项未完成。",
        "每条结论均附证据定位（文件、页码、原文片段）；未附定位的结论视为未验证。",
        "核查要点来源于团队办案经验；规范依据尚在核实中，未核实前不得据以对外作出法律结论。",
        "用户上传材料及其内容不向第三方公开。",
    ]:
        flow.text(f"{line}", size=9, gap=0.8)

    # 附：条文
    from . import rule_refs
    codes: list[str] = []
    for f in findings:
        for clause in rule_refs.bound_clauses(f.get("code", "")):
            if clause["code"] not in codes:
                codes.append(clause["code"])
    if codes:
        flow.rule()
        flow.text("附：所引上市规则条文", size=12.5, gap=3)
        flow.text("以下条文摘自港交所《主板上市规则》综合版，页码为 PDF 页序，供核对原文用。",
                  size=8.5, color=(0.42, 0.41, 0.38), gap=3)
        for code in codes:
            clause = rule_refs.by_code(code)
            if not clause:
                continue
            flow.text(f"第 {clause['code']} 条（p{clause['page']}）", size=9.5, gap=1.5)
            flow.text(clause["text"], size=8.8, color=(0.28, 0.27, 0.25), gap=2, indent=8)
            if clause.get("truncated"):
                flow.text("（该条正文在内置索引中被截断，引用前请回 PDF 原页核对完整条文）",
                          size=8, color=(0.55, 0.36, 0.20), gap=2, indent=8)

    return flow.finish(path)
