"""外部接口单测：用 httpx.MockTransport 校验签名、解析与错误处理。

不访问真实网络，也不需要真实 Key。
运行：python scripts/test_external.py
"""
from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app import external  # noqa: E402

REAL_CLIENT = httpx.Client  # 打补丁前先抓住真实类，避免递归

KEY = "testkey"
SECRET = "testsecret"


class QccTest(unittest.TestCase):
    def setUp(self) -> None:
        self.requests: list[httpx.Request] = []
        self.payload: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(200, json=self.payload)

        self.transport = httpx.MockTransport(handler)
        self._orig = external.httpx.Client
        external.httpx.Client = lambda **kw: REAL_CLIENT(transport=self.transport, **{k: v for k, v in kw.items() if k != "transport"})

    def tearDown(self) -> None:
        external.httpx.Client = self._orig

    def test_signature_and_parse(self) -> None:
        self.payload = {
            "Status": "200",
            "Result": {
                "Name": "澜川精密制造有限公司",
                "CreditCode": "91441900TEST0001X",
                "OperName": "陈某",
                "Status": "存续",
                "RegistCapi": "2000万元",
                "IsOnStock": "0",
            },
        }
        data = external.qcc_basic("澜川精密制造有限公司", KEY, SECRET)

        req = self.requests[0]
        self.assertEqual(req.url.params["key"], KEY)
        self.assertEqual(req.url.params["keyword"], "澜川精密制造有限公司")
        token = req.headers["Token"]
        timespan = req.headers["Timespan"]
        expected = hashlib.md5(f"{KEY}{timespan}{SECRET}".encode()).hexdigest().upper()
        self.assertEqual(token, expected)
        self.assertEqual(len(token), 32)

        self.assertEqual(data["facts"]["name"], "澜川精密制造有限公司")
        self.assertEqual(data["facts"]["legal_person"], "陈某")

    def test_api_error_raises(self) -> None:
        self.payload = {"Status": "201", "Message": "接口未开通"}
        with self.assertRaises(external.ExternalError) as ctx:
            external.qcc_basic("X公司", KEY, SECRET)
        self.assertIn("接口未开通", str(ctx.exception))

    def test_missing_credentials(self) -> None:
        with self.assertRaises(external.ExternalError):
            external.qcc_basic("X公司", "", "")


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self._orig = external.httpx.Client

    def tearDown(self) -> None:
        external.httpx.Client = self._orig

    def _patch(self, payload: dict) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload))
        external.httpx.Client = lambda **kw: REAL_CLIENT(transport=transport, **{k: v for k, v in kw.items() if k != "transport"})

    def test_tavily(self) -> None:
        self._patch({"results": [{"title": "T", "url": "https://example.com/a", "content": "snippet"}]})
        items = external.web_search("澜川精密", "tavily", "tvly-x")
        self.assertEqual(items[0]["url"], "https://example.com/a")

    def test_serper(self) -> None:
        self._patch({"organic": [{"title": "S", "link": "https://example.com/b", "snippet": "x"}]})
        items = external.web_search("澜川精密", "serper", "k")
        self.assertEqual(items[0]["url"], "https://example.com/b")

    def test_unknown_provider(self) -> None:
        with self.assertRaises(external.ExternalError):
            external.web_search("q", "unknown", "k")


class AnalyzeTest(unittest.TestCase):
    def test_status_abnormal(self) -> None:
        qcc = {"facts": {"status": "吊销", "is_listed": "0", "former_names": []}, "source": "s"}
        found = external.analyze("X", qcc, [])
        codes = [f["code"] for f in found]
        self.assertIn("EXT-01", codes)

    def test_negative_hint(self) -> None:
        searches = [{"query": "q", "provider": "tavily", "results": [
            {"title": "某公司被列为失信被执行人", "url": "https://example.com/c", "snippet": ""},
        ]}]
        found = external.analyze("X", None, searches)
        self.assertEqual(found[0]["code"], "EXT-10")
        self.assertEqual(found[0]["source_url"], "https://example.com/c")


if __name__ == "__main__":
    unittest.main(verbosity=2)
