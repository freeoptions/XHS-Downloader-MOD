from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase

from source.module.recorder import IDRecorder


class IDRecorderTest(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        manager = SimpleNamespace(
            root=Path(self.directory.name),
            download_record=True,
        )
        self.first = IDRecorder(manager)
        self.second = IDRecorder(manager)
        await self.first.__aenter__()
        await self.second.__aenter__()

    async def asyncTearDown(self):
        await self.second.__aexit__(None, None, None)
        await self.first.__aexit__(None, None, None)
        self.directory.cleanup()

    async def test_clear_is_committed_and_visible_to_other_connection(self):
        await self.first.add("demo-1")
        await self.first.add("demo-2")

        removed = await self.first.clear()

        self.assertEqual(removed, 2)
        self.assertEqual(await self.first.count(), 0)
        self.assertEqual(await self.second.count(), 0)
        self.assertFalse(await self.second.select("demo-1"))
