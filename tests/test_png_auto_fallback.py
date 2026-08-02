from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, call, patch

from httpx import HTTPStatusError, Request, Response

from source.application.download import Download, _DownloadOutcome


PNG_URL = (
    "https://ci.xiaohongshu.com/test/token"
    "?imageView2/format/png"
)
AUTO_URL = "https://sns-img-bd.xhscdn.com/test/token"


class PngAutoFallbackTest(IsolatedAsyncioTestCase):
    def create_downloader(self) -> Download:
        downloader = object.__new__(Download)
        downloader.temp = Path("D:/temporary")
        downloader.manager = SimpleNamespace(delete=Mock())
        downloader.print = Mock()
        downloader.image_format = "png"
        return downloader

    async def test_only_failed_png_file_falls_back_to_auto(self):
        downloader = self.create_downloader()
        retry = AsyncMock(
            side_effect=[
                _DownloadOutcome(False, png_conversion_failed=True),
                _DownloadOutcome(True),
            ]
        )
        downloader._Download__download_with_retry = retry

        with patch("source.application.download.logging") as log:
            result = await downloader._Download__download_with_fallback(
                PNG_URL,
                Path("D:/downloads"),
                "note_1",
                "png",
                0,
            )

        self.assertTrue(result)
        self.assertEqual(
            retry.await_args_list,
            [
                call(PNG_URL, Path("D:/downloads"), "note_1", "png", 0),
                call(AUTO_URL, Path("D:/downloads"), "note_1", "auto", 0),
            ],
        )
        downloader.manager.delete.assert_called_once_with(
            Path("D:/temporary/note_1.png")
        )
        log.assert_called_once()
        self.assertEqual(downloader.image_format, "png")

    async def test_regular_network_failure_does_not_fall_back(self):
        downloader = self.create_downloader()
        retry = AsyncMock(return_value=_DownloadOutcome(False))
        downloader._Download__download_with_retry = retry

        with patch("source.application.download.logging") as log:
            result = await downloader._Download__download_with_fallback(
                PNG_URL,
                Path("D:/downloads"),
                "note_1",
                "png",
                0,
            )

        self.assertFalse(result)
        retry.assert_awaited_once()
        downloader.manager.delete.assert_not_called()
        log.assert_not_called()

    async def test_retry_keeps_the_png_conversion_failure_reason(self):
        downloader = self.create_downloader()
        downloader.retry = 2
        once = AsyncMock(
            side_effect=[
                _DownloadOutcome(False, png_conversion_failed=True),
                _DownloadOutcome(False),
                _DownloadOutcome(False),
            ]
        )
        downloader._Download__download_once = once

        result = await downloader._Download__download_with_retry(
            PNG_URL,
            Path("D:/downloads"),
            "note_1",
            "png",
            0,
        )

        self.assertFalse(result)
        self.assertTrue(result.png_conversion_failed)
        self.assertEqual(once.await_count, 3)


class PngConversionFailureDetectionTest(TestCase):
    @staticmethod
    def status_error(status_code: int) -> HTTPStatusError:
        request = Request("GET", PNG_URL)
        response = Response(status_code, request=request)
        return HTTPStatusError(
            "PNG conversion failed",
            request=request,
            response=response,
        )

    def test_conversion_server_error_is_detected(self):
        self.assertTrue(
            Download._Download__is_png_conversion_failure(
                PNG_URL,
                "png",
                self.status_error(500),
            )
        )

    def test_rate_limit_is_not_treated_as_conversion_failure(self):
        self.assertFalse(
            Download._Download__is_png_conversion_failure(
                PNG_URL,
                "png",
                self.status_error(429),
            )
        )

    def test_non_png_request_is_not_treated_as_conversion_failure(self):
        self.assertFalse(
            Download._Download__is_png_conversion_failure(
                PNG_URL,
                "webp",
                self.status_error(500),
            )
        )
