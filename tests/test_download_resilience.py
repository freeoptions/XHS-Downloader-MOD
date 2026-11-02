from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from curl_cffi import CurlHttpVersion
from curl_cffi.requests.exceptions import RequestException

from source.application.download import Download, _DownloadOutcome
from source.GUI.backend import GuiBackend, TaskState
from source.module.tools import retry as retry_request


class DownloadResilienceTest(IsolatedAsyncioTestCase):
    async def test_http_status_retry_classification(self):
        for status, expected in [(403, False), (404, False), (408, True), (429, True), (503, True)]:
            error = RequestException("status", response=SimpleNamespace(status_code=status))
            self.assertEqual(
                Download._Download__can_retry("https://example.test/file", "png", error),
                expected,
            )

    async def test_http2_retry_waits_and_only_changes_current_request(self):
        downloader = object.__new__(Download)
        downloader.retry = 3
        downloader.print = Mock()
        once = AsyncMock(side_effect=[
            _DownloadOutcome(False, http2_failed=True),
            _DownloadOutcome(False),
            _DownloadOutcome(True),
        ])
        downloader._Download__download_once = once
        with (
            patch("source.application.download.sleep", new=AsyncMock()) as sleep,
            patch("source.application.download.uniform", return_value=0),
            patch("source.application.download.logging"),
        ):
            result = await downloader._Download__download_with_retry(
                "https://example.test/file", Path("."), "file", "png", 0,
            )
        self.assertTrue(result)
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [2, 4])
        self.assertEqual(once.await_args_list[0].kwargs, {})
        self.assertEqual(once.await_args_list[1].kwargs["http_version"], CurlHttpVersion.V1_1)
        self.assertEqual(once.await_args_list[2].kwargs["http_version"], CurlHttpVersion.V1_1)

    async def test_permanent_failure_does_not_wait_or_retry(self):
        downloader = object.__new__(Download)
        downloader.retry = 5
        downloader.print = Mock()
        downloader._Download__download_once = AsyncMock(
            return_value=_DownloadOutcome(False, retryable=False)
        )
        with (
            patch("source.application.download.sleep", new=AsyncMock()) as sleep,
            patch("source.application.download.logging"),
        ):
            result = await downloader._Download__download_with_retry(
                "https://example.test/file", Path("."), "file", "png", 0,
            )
        self.assertFalse(result)
        sleep.assert_not_awaited()
        downloader._Download__download_once.assert_awaited_once()

    async def test_interrupted_buffer_is_saved_and_ignored_range_restarts(self):
        class Response:
            status_code = 200
            headers = {"content-length": "6"}

            def raise_for_status(self):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *_):
                pass

            async def aiter_content(self, _):
                yield b"new"
                raise RequestException("interrupted", code=28)

        with TemporaryDirectory() as directory:
            temp = Path(directory)
            (temp / "file.png").write_bytes(b"old")
            downloader = object.__new__(Download)
            downloader.temp = temp
            downloader.timeout = 30
            downloader.chunk = 1
            downloader.headers = {}
            downloader.print = Mock()
            downloader.client = SimpleNamespace(stream=Mock(return_value=Response()))
            with patch("source.application.download.logging"):
                result = await downloader._Download__download_once(
                    "https://example.test/file", temp, "file", "png", 0, None, None,
                )
            self.assertFalse(result)
            self.assertEqual((temp / "file.png").read_bytes(), b"new")
            options = downloader.client.stream.call_args.kwargs
            self.assertEqual(options["timeout"], (15, 30))
            self.assertEqual(options["headers"]["Range"], "bytes=3-")


class FailedIdsTest(IsolatedAsyncioTestCase):
    async def test_only_final_failures_are_copied_once_including_script_tasks(self):
        a, b, c = "a" * 24, "b" * 24, "c" * 24
        backend = object.__new__(GuiBackend)
        backend.tasks = {
            "1": TaskState("1", f"https://example.test/explore/{a}?token=secret", state="failed"),
            "2": TaskState("2", f"https://example.test/explore/{a}", state="failed"),
            "3": TaskState("3", "", state="failed", script_data={"noteId": b}),
            "4": TaskState("4", f"https://example.test/explore/{c}", state="success"),
            "5": TaskState("5", "https://example.test/invalid", state="failed"),
        }
        with patch("source.GUI.backend.copy") as copy:
            self.assertEqual(await backend.copy_failed_ids(), 2)
        copy.assert_called_once_with(f"{a}\n{b}")

    async def test_empty_failure_list_preserves_clipboard(self):
        backend = object.__new__(GuiBackend)
        backend.tasks = {}
        with patch("source.GUI.backend.copy") as copy:
            self.assertEqual(await backend.copy_failed_ids(), 0)
        copy.assert_not_called()


class RequestRetryTest(IsolatedAsyncioTestCase):
    async def test_request_retry_waits_and_stops_on_permanent_failure(self):
        class Request:
            retry = 5
            request_retryable = True
            attempts = 0

            @retry_request
            async def run(self):
                self.attempts += 1
                self.request_retryable = self.attempts < 2
                return ""

        request = Request()
        with patch("source.module.tools.sleep", new=AsyncMock()) as sleep:
            await request.run()
        self.assertEqual(request.attempts, 2)
        sleep.assert_awaited_once()
