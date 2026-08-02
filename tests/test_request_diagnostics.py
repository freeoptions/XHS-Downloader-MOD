from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from urllib.parse import quote

from httpx import Request, Response

from source.application.request import Html


class RequestDiagnosticsTest(TestCase):
    def setUp(self):
        self.html = Html.__new__(Html)
        self.html.last_response = {}

    def test_platform_error_is_extracted_without_query_leak(self):
        message = "当前笔记暂时无法浏览"
        secret = "secret-xsec-token"
        request = Request(
            "GET",
            "https://www.xiaohongshu.com/404"
            f"?error_code=300031&error_msg={quote(message)}"
            f"&redirectPath=/explore/demo?xsec_token={secret}",
        )
        response = Response(
            200,
            request=request,
            text=(
                "<html><head><title>小红书 - 你访问的页面不见了</title></head>"
                "<body><script>window.__INITIAL_STATE__={noteDetailMap:{}}</script>"
                "</body></html>"
            ),
        )

        self.html._record_response(response, cookie_used=True)
        diagnostic = self.html.last_response_diagnostic()

        self.assertIn("平台返回错误 300031", diagnostic)
        self.assertIn(message, diagnostic)
        self.assertIn("最终页面 https://www.xiaohongshu.com/404", diagnostic)
        self.assertIn("携带 Cookie：是", diagnostic)
        self.assertNotIn("xsec_token", diagnostic)
        self.assertNotIn(secret, diagnostic)

    def test_missing_initial_state_is_classified(self):
        request = Request("GET", "https://www.xiaohongshu.com/explore/demo")
        response = Response(
            200,
            request=request,
            text="<html><head><title>安全验证</title></head><body></body></html>",
        )

        self.html._record_response(response, cookie_used=False)
        diagnostic = self.html.last_response_diagnostic()

        self.assertIn("页面未包含作品初始状态", diagnostic)
        self.assertIn("页面标题：安全验证", diagnostic)
        self.assertIn("携带 Cookie：否", diagnostic)
        self.assertIn("作品字段标记：无", diagnostic)

    def test_query_is_removed_from_safe_url(self):
        safe = self.html._safe_url(
            "https://www.xiaohongshu.com/explore/demo?xsec_token=secret"
        )

        self.assertEqual(safe, "https://www.xiaohongshu.com/explore/demo")

    def test_failure_log_contains_no_url_secret(self):
        with TemporaryDirectory() as directory:
            self.html.failure_log_path = Path(directory) / "request_failures.log"
            diagnostic = (
                "平台返回错误 300031；最终页面 "
                "https://www.xiaohongshu.com/404"
            )

            saved = self.html.save_failure_diagnostic("demo?id=bad", diagnostic)
            content = self.html.failure_log_path.read_text(encoding="utf-8")

        self.assertTrue(saved)
        self.assertIn("| demoidbad |", content)
        self.assertIn("平台返回错误 300031", content)
        self.assertNotIn("xsec_token", content)
