import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from curl_cffi import CurlHttpVersion

from source.application.app import XHS
from source.application.download import Download, _DownloadOutcome
from source.GUI.backend import GuiBackend, TaskState
from source.module.deferred_retry import (
    DEFERRED_RETRY, DeferredRetryState, defer_retries,
)
from source.module.tools import retry as retry_request


class GuiDeferredRetryTest(IsolatedAsyncioTestCase):
    async def exercise_worker(self, add_during_wait=False, cancel_during_wait=False):
        backend = object.__new__(GuiBackend)
        backend.task_queue = asyncio.Queue()
        backend.tasks = {key: TaskState(key, key) for key in ["fail", "ok", "404"]}
        backend.xhs = SimpleNamespace(
            manager=SimpleNamespace(retry=5),
            downloader=SimpleNamespace(finalize_deferred=AsyncMock()),
        )
        backend.add_log = Mock()
        for key in backend.tasks:
            backend.task_queue.put_nowait(key)
        order, delays = [], []
        finished = asyncio.Event()

        async def process(task):
            state = DEFERRED_RETRY.get()
            self.assertIs(state, task.retry_state)
            order.append((task.task_id, state.retrying))
            task.can_retry = task.task_id == "fail"
            task.state = "failed" if task.task_id in {"fail", "404"} else "success"
            if state.retrying:
                task.state = "success"
                finished.set()

        async def wait(awaitable, delay):
            delays.append(delay)
            self.assertTrue(backend.tasks["fail"].waiting_retry)
            self.assertEqual(backend.tasks["fail"].state, "pending")
            if add_during_wait and "new" not in backend.tasks:
                backend.tasks["new"] = TaskState("new", "new")
                backend.task_queue.put_nowait("new")
                return await awaitable
            awaitable.close()
            if cancel_during_wait:
                await backend.cancel_task("fail")
                finished.set()
            raise TimeoutError

        backend._process_task = process
        with patch("source.GUI.backend.asyncio.wait_for", side_effect=wait):
            worker = asyncio.create_task(backend._worker_loop())
            try:
                async with asyncio.timeout(1):
                    await finished.wait()
                await asyncio.sleep(0)
            finally:
                worker.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await worker
        self.assertTrue(all(20 <= delay <= 40 for delay in delays))
        self.assertTrue(backend.task_queue.empty())
        # 队列计数必须平衡，不能因延迟重试多调用 task_done。
        async with asyncio.timeout(1):
            await backend.task_queue.join()
        return order, backend

    async def test_all_first_pass_tasks_finish_before_retry(self):
        order, backend = await self.exercise_worker()
        self.assertEqual(order, [("fail", False), ("ok", False), ("404", False), ("fail", True)])
        self.assertEqual(backend.tasks["fail"].state, "success")

    async def test_new_task_during_wait_takes_priority(self):
        order, _ = await self.exercise_worker(add_during_wait=True)
        self.assertEqual(order, [("fail", False), ("ok", False), ("404", False), ("new", False), ("fail", True)])

    async def test_waiting_retry_can_be_cancelled(self):
        order, backend = await self.exercise_worker(cancel_during_wait=True)
        self.assertEqual(order, [("fail", False), ("ok", False), ("404", False)])
        self.assertEqual(backend.tasks["fail"].state, "cancelled")


class NestedRetryTest(IsolatedAsyncioTestCase):
    async def test_request_does_not_retry_inside_gui_task(self):
        class Request:
            retry = 5
            calls = 0

            @retry_request
            async def run(self):
                self.calls += 1
                return ""

        request = Request()
        with defer_retries(DeferredRetryState()):
            with patch("source.module.tools.sleep", new=AsyncMock()) as sleep:
                await request.run()
        self.assertEqual(request.calls, 1)
        sleep.assert_not_awaited()
        self.assertIsNone(DEFERRED_RETRY.get())

    async def test_read_failure_is_returned_without_per_post_wait(self):
        xhs = object.__new__(XHS)
        xhs._retry_failed_reads = AsyncMock()
        xhs._is_not_found_failure = Mock(return_value=False)

        async def fail(*args, count, **kwargs):
            count.fail += 1
            return {}

        xhs._XHS__deal_extract = AsyncMock(side_effect=fail)
        with defer_retries(DeferredRetryState()):
            stats = SimpleNamespace(all=1, success=0, fail=0, skip=0)
            await xhs._process_batch(["failed-url"], True, None, False, stats)
        xhs._retry_failed_reads.assert_not_awaited()
        self.assertEqual(xhs.last_failed_urls, ["failed-url"])

    async def test_http2_hint_survives_until_end_of_queue(self):
        downloader = object.__new__(Download)
        downloader.retry = 5
        downloader.print = Mock()
        once = AsyncMock(side_effect=[
            _DownloadOutcome(False, http2_failed=True), _DownloadOutcome(True),
        ])
        downloader._Download__download_once = once
        state = DeferredRetryState()
        with (
            defer_retries(state),
            patch("source.application.download.sleep", new=AsyncMock()) as sleep,
            patch("source.application.download.logging"),
        ):
            self.assertFalse(await downloader._Download__download_with_retry(
                "https://example.test/file", Path("."), "file", "png", 0,
            ))
            self.assertEqual(once.await_count, 1)
            state.retrying = True
            self.assertTrue(await downloader._Download__download_with_retry(
                "https://example.test/file", Path("."), "file", "png", 0,
            ))
        sleep.assert_not_awaited()
        self.assertEqual(once.await_args_list[1].kwargs["http_version"], CurlHttpVersion.V1_1)

    async def test_png_fallback_is_deferred_until_retry_pass(self):
        downloader = object.__new__(Download)
        downloader.print = Mock()
        downloader.temp = Path(".")
        downloader.manager = SimpleNamespace(delete=Mock())
        attempts = AsyncMock(side_effect=[
            _DownloadOutcome(False, png_conversion_failed=True),
            _DownloadOutcome(False, png_conversion_failed=True),
            _DownloadOutcome(True),
        ])
        downloader._Download__download_with_retry = attempts
        state = DeferredRetryState()
        args = ("https://ci.xiaohongshu.com/image?imageView2/format/png", Path("."), "file", "png", 0)
        with defer_retries(state), patch("source.application.download.logging"):
            self.assertFalse(await downloader._Download__download_with_fallback(*args))
            self.assertEqual(attempts.await_count, 1)
            state.retrying = True
            self.assertTrue(await downloader._Download__download_with_fallback(*args))
        self.assertEqual(attempts.await_count, 3)
