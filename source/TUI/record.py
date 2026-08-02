from textual import on
from textual.app import ComposeResult
from textual.containers import Grid, HorizontalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label

from ..application import XHS
from ..translation import _

__all__ = ["Record"]


class Record(ModalScreen):
    def __init__(
        self,
        app: XHS,
    ):
        super().__init__()
        self.xhs = app

    def compose(self) -> ComposeResult:
        yield Grid(
            Label(_("请输入待删除的小红书作品链接或作品 ID"), classes="prompt"),
            Input(
                placeholder=_(
                    "支持输入作品 ID 或包含作品 ID 的作品链接，多个链接或 ID 之间使用空格分隔"
                ),
                id="id",
            ),
            HorizontalScroll(
                Button(
                    _("删除指定作品 ID"),
                    id="enter",
                ),
                Button("清空全部下载记录", id="clear_all"),
                Button(_("返回首页"), id="close"),
            ),
            id="record",
        )

    async def delete(self, text: str):
        text = await self.xhs.extract_links(
            text,
        )
        text = self.xhs.extract_id(text)
        await self.xhs.id_recorder.delete(text)
        self.app.notify(_("删除下载记录成功"))

    @on(Button.Pressed, "#enter")
    async def save_settings(self):
        text = self.query_one(Input)
        await self.delete(text.value)
        text.value = ""

    @on(Button.Pressed, "#clear_all")
    async def clear_all(self):
        count = await self.xhs.id_recorder.clear()
        remaining = await self.xhs.id_recorder.count()
        if remaining:
            self.app.notify(
                f"清空后仍有 {remaining} 条记录，可能有其他运行中的程序正在写入。"
                "请关闭其他 XHS-Downloader-MOD 窗口后重试。",
                title="清空未完成",
                severity="error",
                timeout=10,
            )
        elif count:
            self.app.notify(
                f"已清空全部下载记录，共 {count} 条。这里只清除记录，不删除已下载"
                "文件；再次下载时，同名文件仍会提示“文件已存在，跳过下载”。",
                title="清空完成",
                timeout=10,
            )
        else:
            self.app.notify(
                "下载记录原本就是空的。若仍提示“文件已存在”，说明命中的是硬盘上"
                "的同名文件，不是下载记录。",
                title="没有下载记录",
                timeout=8,
            )

    @on(Button.Pressed, "#close")
    def reset(self):
        self.dismiss()
