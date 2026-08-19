from types import MethodType, SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, call, patch

from source.application.app import XHS


class RetryQueueTest(IsolatedAsyncioTestCase):
    async def test_failed_reads_are_retried_after_first_pass(self):
        xhs = object.__new__(XHS)
        xhs.last_failed_urls = []
        logs = []
        attempts = {}
        call_order = []

        def capture_log(_, message, style=None):
            logs.append((message, style))

        async def fake_deal_extract(
            _,
            url,
            download,
            index,
            data,
            cookie=None,
            proxy=None,
            request_timeout=None,
            count=None,
        ):
            attempts[url] = attempts.get(url, 0) + 1
            call_order.append((url, request_timeout))
            if url == "recover" and attempts[url] == 1:
                count.fail += 1
                return {}
            if url == "always-fail":
                count.fail += 1
                return {}
            count.success += 1
            return {"url": url}

        xhs.logging = MethodType(capture_log, xhs)
        xhs._XHS__deal_extract = MethodType(fake_deal_extract, xhs)
        statistics = SimpleNamespace(all=3, success=0, fail=0, skip=0)

        with (
            patch("source.application.app.uniform", side_effect=[55.0, 12.0]),
            patch("source.application.app.sleep", new=AsyncMock()) as sleep_mock,
        ):
            result = await xhs._process_batch(
                ["ok", "recover", "always-fail"],
                True,
                None,
                False,
                statistics,
            )

        self.assertEqual(
            call_order,
            [
                ("ok", None),
                ("recover", None),
                ("always-fail", None),
                ("recover", 20),
                ("always-fail", 20),
            ],
        )
        self.assertEqual(sleep_mock.await_args_list, [call(55.0), call(12.0)])
        self.assertEqual(statistics.success, 2)
        self.assertEqual(statistics.fail, 1)
        self.assertEqual(statistics.skip, 0)
        self.assertEqual(result[1], {"url": "recover"})
        self.assertEqual(xhs.last_failed_urls, ["always-fail"])
        self.assertTrue(any("55.0 秒" in message for message, _ in logs))
        self.assertTrue(any("恢复 1 个，仍失败 1 个" in message for message, _ in logs))

    async def test_download_failure_is_not_added_to_read_retry_queue(self):
        xhs = object.__new__(XHS)
        xhs.last_failed_urls = []
        xhs.logging = MethodType(lambda *_: None, xhs)

        async def fake_deal_extract(
            _,
            url,
            download,
            index,
            data,
            cookie=None,
            proxy=None,
            request_timeout=None,
            count=None,
        ):
            count.fail += 1
            return {"url": url, "读取成功": True}

        xhs._XHS__deal_extract = MethodType(fake_deal_extract, xhs)
        statistics = SimpleNamespace(all=1, success=0, fail=0, skip=0)

        with patch("source.application.app.sleep", new=AsyncMock()) as sleep_mock:
            await xhs._process_batch(
                ["download-fail"],
                True,
                None,
                False,
                statistics,
            )

        sleep_mock.assert_not_awaited()
        self.assertEqual(statistics.fail, 1)
        self.assertEqual(xhs.last_failed_urls, ["download-fail"])

    async def test_404_read_failure_is_kept_but_not_retried(self):
        xhs = object.__new__(XHS)
        xhs.last_failed_urls = []
        xhs.html = SimpleNamespace(
            last_response={
                "final_path": "https://www.xiaohongshu.com/404",
            },
        )
        xhs.logging = MethodType(lambda *_: None, xhs)

        async def fake_deal_extract(
            _,
            url,
            download,
            index,
            data,
            cookie=None,
            proxy=None,
            request_timeout=None,
            count=None,
        ):
            count.fail += 1
            return {}

        xhs._XHS__deal_extract = MethodType(fake_deal_extract, xhs)
        statistics = SimpleNamespace(all=1, success=0, fail=0, skip=0)

        with patch("source.application.app.sleep", new=AsyncMock()) as sleep_mock:
            await xhs._process_batch(
                ["404-failure"],
                True,
                None,
                False,
                statistics,
            )

        sleep_mock.assert_not_awaited()
        self.assertEqual(statistics.fail, 1)
        self.assertEqual(xhs.last_failed_urls, ["404-failure"])
