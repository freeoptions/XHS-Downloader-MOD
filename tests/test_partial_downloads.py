import asyncio
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase, TestCase
from unittest.mock import AsyncMock, Mock, patch

from source.application.app import XHS
from source.application.download import Download
from source.module.deferred_retry import DeferredRetryState, defer_retries
from source.module.partial_downloads import PartialDownloads
from source.translation import _


class PartialDirectoryTest(TestCase):
    def test_partial_post_moves_and_completed_retry_returns_to_normal(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            normal = root / "author" / "post"
            normal.mkdir(parents=True)
            (normal / "post.png").write_bytes(b"cover")
            store = PartialDownloads(root, True)
            partial = store.finalize(normal, "post", False)
            self.assertEqual(partial, root / "author" / "部分下载成功" / "post")
            self.assertFalse(normal.exists())
            self.assertEqual(store.prepare(normal, "post"), partial)
            (partial / "post.mp4").write_bytes(b"video")
            self.assertEqual(store.finalize(partial, "post", True), normal)
            self.assertEqual((normal / "post.png").read_bytes(), b"cover")
            self.assertEqual((normal / "post.mp4").read_bytes(), b"video")
            self.assertFalse(partial.exists())

    def test_empty_or_metadata_only_post_is_not_classified_as_partial(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "post"
            path.mkdir()
            store = PartialDownloads(root, True)
            self.assertEqual(store.finalize(path, "post", False), path)
            (path / "post.txt").write_text("metadata")
            self.assertEqual(store.finalize(path, "post", False), path)
            self.assertFalse((root / "部分下载成功").exists())

    def test_existing_destination_preserves_both_conflicting_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "post"
            path.mkdir()
            (path / "post_1.png").write_bytes(b"new")
            target = root / "部分下载成功" / "post"
            target.mkdir(parents=True)
            (target / "post_1.png").write_bytes(b"old")
            store = PartialDownloads(root, True)
            store.finalize(path, "post", False)
            self.assertEqual({p.read_bytes() for p in target.iterdir()}, {b"new", b"old"})
            self.assertFalse(path.exists())
            store.prepare(path, "post")
            # 已有部分目录会被直接复用，不创建新的正常目录。
            self.assertFalse(path.exists())

    def test_flat_mode_moves_only_current_post_and_restores_for_retry(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ["post_1.png", "post.txt", "other_1.png", "post_other.png"]:
                (root / name).write_bytes(name.encode())
            store = PartialDownloads(root, False)
            partial = store.finalize(root, "post", False)
            self.assertEqual({p.name for p in partial.iterdir()}, {"post_1.png", "post.txt"})
            self.assertTrue((root / "other_1.png").exists())
            self.assertTrue((root / "post_other.png").exists())
            self.assertEqual(store.prepare(root, "post"), root)
            self.assertTrue((root / "post_1.png").exists())
            self.assertFalse(partial.exists())

    def test_path_outside_download_root_is_rejected(self):
        with TemporaryDirectory() as directory:
            root = Path(directory) / "downloads"
            root.mkdir()
            with self.assertRaises(ValueError):
                PartialDownloads(root, True).finalize(Path(directory), "post", False)


class PartialRecordTest(IsolatedAsyncioTestCase):
    def make_xhs(self, path, results):
        xhs = object.__new__(XHS)
        xhs.CLEANER = SimpleNamespace(filter_name=lambda value: value)
        xhs._XHS__naming_rules = Mock(return_value="post")
        xhs.downloader = SimpleNamespace(
            generate_path=Mock(return_value=path),
            run=AsyncMock(return_value=results),
            finalize_partial=AsyncMock(),
        )
        xhs._XHS__add_record = AsyncMock()
        xhs.note_generator = SimpleNamespace(save_note_info=AsyncMock())
        xhs.save_data = AsyncMock()
        container = {
            "作者ID": "author", "作者昵称": "name", "作品ID": "id",
            "下载地址": ["one", "two"], "动图地址": [None, None],
            "作品类型": "图文", "时间戳": 0, "封面地址": None,
        }
        return xhs, container, SimpleNamespace(success=0, fail=0, skip=0)

    async def test_partial_download_is_not_written_to_success_history(self):
        path = Path("unused")
        xhs, container, stats = self.make_xhs(path, [True, False])
        await xhs._XHS__download_files(container, True, None, stats)
        self.assertEqual(stats.fail, 1)
        xhs._XHS__add_record.assert_not_awaited()
        xhs.downloader.finalize_partial.assert_awaited_once_with(path, "post", False)

    async def test_all_files_success_writes_history(self):
        xhs, container, stats = self.make_xhs(Path("unused"), [True, True])
        await xhs._XHS__download_files(container, True, None, stats)
        xhs._XHS__add_record.assert_awaited_once_with("id")
        self.assertEqual(stats.success, 1)

    async def test_gui_archiving_is_deferred_until_queue_finalizes(self):
        path = Path("unused")
        xhs, container, stats = self.make_xhs(path, [True, False])
        state = DeferredRetryState()
        with defer_retries(state):
            await xhs._XHS__download_files(container, True, None, stats)
        xhs.downloader.finalize_partial.assert_not_awaited()
        self.assertFalse(state.partial_outcomes[(path, "post")])
        xhs._XHS__add_record.assert_not_awaited()

    async def test_download_waits_for_other_files_after_one_raises(self):
        downloader = object.__new__(Download)
        downloader.print = Mock()
        downloader._Download__ready_download_image = Mock(return_value=[
            ("bad", "post_1", "png"), ("good", "post_2", "png"),
        ])
        finished = []

        async def transfer(url, *args):
            if url == "bad":
                raise OSError("test error")
            await asyncio.sleep(0)
            finished.append(url)
            return True

        downloader._Download__download_with_fallback = transfer
        with patch("source.application.download.logging"):
            result = await downloader.run([], [], None, Path("unused"), "post", _("图文"), 0)
        self.assertEqual(result, [False, True])
        self.assertEqual(finished, ["good"])
