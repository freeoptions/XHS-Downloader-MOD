from textual.app import App

from ..application import XHS
from ..module import (
    ROOT,
    VOLUME,
    Settings,
)
from .index import Index
from .loading import Loading
from .record import Record
from .setting import Setting

__all__ = ["XHSDownloader"]


class XHSDownloader(App):
    CSS_PATH = ROOT.joinpath("static/XHS-Downloader.tcss")
    SETTINGS = Settings(VOLUME)

    def __init__(self):
        super().__init__()
        self.parameter: dict
        self.APP: XHS
        self.__initialization()

    async def __aenter__(self):
        await self.APP.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        await self.APP.__aexit__(exc_type, exc_value, traceback)

    def __initialization(self) -> None:
        self.parameter = self.SETTINGS.run()
        self.APP = XHS(
            **self.parameter,
            _print=False,
        )

    async def on_mount(self) -> None:
        self.theme = "nord"
        self.install_screen(
            Index(
                self.APP,
            ),
            name="index",
        )
        self.install_screen(Loading(), name="loading")
        self.install_screen(
            Record(
                self.APP,
            ),
            name="record",
        )
        await self.push_screen("index")

    async def action_settings(self):
        async def save_settings(data: dict) -> None:
            self.SETTINGS.update(data)
            await self.refresh_screen()

        await self.push_screen(Setting(self.parameter), save_settings)

    async def refresh_screen(self):
        await self.action_back()
        await self.close_database()
        await self.APP.close()
        self.__initialization()
        await self.__aenter__()
        await self.APP.switch_script_server()
        self.uninstall_screen("index")
        self.uninstall_screen("loading")
        self.uninstall_screen("record")
        self.install_screen(
            Index(
                self.APP,
            ),
            name="index",
        )
        self.install_screen(Loading(), name="loading")
        self.install_screen(
            Record(
                self.APP,
            ),
            name="record",
        )
        await self.push_screen("index")

    async def close_database(self):
        await self.APP.id_recorder.cursor.close()
        await self.APP.id_recorder.database.close()
        await self.APP.data_recorder.cursor.close()
        await self.APP.data_recorder.database.close()
