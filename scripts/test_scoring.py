"""评分卡单测：验证扣分、N/A 与覆盖不足不定级。

运行：python scripts/test_scoring.py
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import scoring  # noqa: E402

RUBRIC = scoring.load_rubric()


def run(board="asset", findings=None, **kw):
    base = dict(
        analyzed=True, board=board, findings=findings or [],
        external_findings=[], external_present=False,
        required_materials=["不动产权证"], present_materials=["不动产权证"],
        missing_count=0, versions={"groups": 1, "versions": 1, "conflict": False},
        qc={"checked": 5, "failed": 0, "notices": []},
    )
    base.update(kw)
    return scoring.score_project(RUBRIC, **base)


class ScoreTest(unittest.TestCase):
    def test_clean_asset_scores_full_on_covered_items(self) -> None:
        result = run()
        dim_a = next(d for d in result["dimensions"] if d["id"] == "A")
        self.assertEqual(dim_a["earned"], 20.0)
        dim_e = next(d for d in result["dimensions"] if d["id"] == "E")
        # E3（证据覆盖率）在没有结论时 N/A，故可得分上限为 8
        self.assertEqual(dim_e["earned"], 8.0)

    def test_high_finding_zeroes_item(self) -> None:
        result = run(findings=[{"code": "AST-01", "risk_level": "high", "title": "权属不一致"}])
        dim_a = next(d for d in result["dimensions"] if d["id"] == "A")
        item = next(i for i in dim_a["items"] if i["id"] == "A1")
        self.assertEqual(item["earned"], 0)
        self.assertEqual(item["status"], "zero")

    def test_uncovered_board_is_na(self) -> None:
        result = run()
        dim_b = next(d for d in result["dimensions"] if d["id"] == "B")
        self.assertEqual(dim_b["applicable"], 0)
        self.assertTrue(all(i["status"] == "na" for i in dim_b["items"]))

    def test_low_coverage_has_no_grade(self) -> None:
        result = run()
        self.assertLess(result["coverage"], 0.8)
        self.assertEqual(result["grade"], "—")

    def test_missing_materials_reduce_e1(self) -> None:
        result = run(missing_count=1)
        dim_e = next(d for d in result["dimensions"] if d["id"] == "E")
        e1 = next(i for i in dim_e["items"] if i["id"] == "E1")
        self.assertLess(e1["earned"], e1["points"])

    def test_external_status_abnormal(self) -> None:
        result = run(
            external_present=True,
            external_findings=[{"code": "EXT-01", "level": "high", "title": "登记状态异常"}],
        )
        dim_d = next(d for d in result["dimensions"] if d["id"] == "D")
        d1 = next(i for i in dim_d["items"] if i["id"] == "D1")
        self.assertEqual(d1["earned"], 0)

    def test_not_analyzed_assets_na(self) -> None:
        result = run(analyzed=False)
        dim_a = next(d for d in result["dimensions"] if d["id"] == "A")
        self.assertEqual(dim_a["applicable"], 0)
        self.assertEqual(result["grade"], "—")


if __name__ == "__main__":
    unittest.main(verbosity=2)
