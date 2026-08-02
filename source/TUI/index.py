from pyperclip import PyperclipException, copy, paste
from rich.text import Text
from textual import on, work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import HorizontalScroll, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, Link, RichLog

from ..application import XHS
from ..module import (
    ERROR,
    GENERAL,
    LICENCE,
    MASTER,
    PROJECT,
    PROMPT,
    REPOSITORY,
    WARNING,
)
from ..translation import _
from .monitor import Monitor

__all__ = ["Index"]


class Index(Screen):
    BINDINGS = [
        Binding(key="Q", action="quit", description=_("退出程序")),
        Binding(key="U", action="update", description=_("检查更新")),
        Binding(key="S", action="settings", description=_("程序设置")),
        Binding(key="R", action="record", description=_("下载记录")),
        Binding(key="M", action="monitor", description=_("开启监听")),
        Binding(key="A", action="about", description=_("关于项目")),
        Binding(key="ctrl+c", action="copy_text", description="复制"),
    ]

    def __init__(
        self,
        app: XHS,
    ):
        super().__init__()
        self.xhs = app
        self.url = None
        self.tip = None
        self.failed_urls: list[str] = []
        self.copy_failed = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            Label(Text(_("开源协议: ") + LICENCE, style=MASTER)),
            Link(
                Text(
                    _("项目地址: ") + REPOSITORY,
                    style=MASTER,
                ),
                url=REPOSITORY,
                tooltip=_("点击访问"),
            ),
            Label(
                Text(_("请输入小红书图文/视频作品链接"), style=PROMPT),
                classes="prompt",
            ),
            Input(placeholder=_("多个链接之间使用空格分隔")),
            HorizontalScroll(
                Button(_("下载作品文件"), id="deal"),
                Button(_("读取剪贴板"), id="paste"),
                Button("复制日志", id="copy_log"),
                Button(_("清空输入框"), id="reset"),
                Button("复制失败链接", id="copy_failed"),
            ),
        )
        yield RichLog(
            markup=True,
            wrap=True,
            auto_scroll=True,
            id="main_log",
        )
        yield Footer()

    def on_mount(self) -> None:
        self.title = PROJECT
        self.url = self.query_one(Input)
        self.tip = self.query_one(RichLog)
        self.copy_failed = self.query_one("#copy_failed", Button)
        self.copy_failed.display = False
        self.xhs.print.func = self.tip
        self.tip.write(
            Text(_("免责声明\n") + f"\n{'>' * 50}", style=MASTER),
            scroll_end=True,
        )
        self.xhs.manager.print_proxy_tip()

    @on(Button.Pressed, "#deal")
    async def deal_button(self):
        if self.url.value:
            self.deal()
        else:
            self.tip.write(
                Text(_("未输入任何小红书作品链接"), style=WARNING),
                scroll_end=True,
            )
            self.tip.write(
                Text(">" * 50, style=GENERAL),
                scroll_end=True,
            )

    @on(Button.Pressed, "#reset")
    def reset_button(self):
        self.query_one(Input).value = ""

    @on(Button.Pressed, "#paste")
    def paste_button(self):
        self.query_one(Input).value = paste()

    def _copy_to_clipboard(self, text: str, success_message: str) -> None:
        if not text:
            self.app.notify("暂无可复制内容", severity="warning")
            return
        try:
            copy(text)
        except PyperclipException:
            self.app.notify("复制失败，请检查系统剪贴板", severity="error")
        else:
            self.app.notify(success_message)

    def _get_log_text(self) -> str:
        if not self.tip:
            return ""
        return "\n".join(line.text.rstrip() for line in self.tip.lines).strip()

    def action_copy_text(self) -> None:
        selected_text = self.get_selected_text()
        text = selected_text.strip() if selected_text else self._get_log_text()
        message = "已复制选中内容" if selected_text else "已复制主界面日志"
        self._copy_to_clipboard(text, message)

    @on(Button.Pressed, "#copy_log")
    def copy_log_button(self) -> None:
        self.action_copy_text()

    @on(Button.Pressed, "#copy_failed")
    def copy_failed_button(self):
        if not self.failed_urls:
            return
        self._copy_to_clipboard(
            "\n".join(self.failed_urls),
            f"已复制 {len(self.failed_urls)} 个失败链接",
        )

    @work(exclusive=True)
    async def deal(self):
        await self.app.push_screen("loading")
        result = await self.xhs.extract(
            self.url.value,
            True,
            data=False,
        )
        self.failed_urls = list(dict.fromkeys(self.xhs.last_failed_urls))
        self.copy_failed.display = bool(self.failed_urls)
        if any(result):
            self.url.value = ""
        else:
            self.tip.write(
                Text(_("下载小红书作品文件失败"), style=ERROR),
                animate=True,
                scroll_end=True,
            )
        self.tip.write(
            Text(">" * 50, style=GENERAL),
            scroll_end=True,
        )
        await self.app.action_back()

    async def action_quit(self) -> None:
        await self.app.action_quit()

    async def action_update(self) -> None:
        await self.app.run_action("update")

    async def action_settings(self):
        await self.app.run_action("settings")

    async def action_monitor(self):
        await self.app.push_screen(
            Monitor(
                self.xhs,
            )
        )

    async def action_about(self):
        await self.app.push_screen("about")

    async def action_record(self):
        await self.app.push_screen("record")
