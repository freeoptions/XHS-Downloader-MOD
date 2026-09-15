from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, ScrollableContainer
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Header, Input, Label, Select

from ..module import IMPERSONATE
from ..translation import _

__all__ = ["Setting"]


class Setting(Screen):
    IMAGE_FORMATS = ("AUTO", "PNG", "WEBP", "JPEG", "HEIC")
    LANGUAGES = ("zh_CN", "en_US")
    VIDEO_PREFERENCES = ("resolution", "bitrate", "size")
    NOTE_FORMATS = ("", "txt", "md", "all")

    BINDINGS = [
        Binding(key="Q", action="quit", description=_("退出程序")),
        Binding(key="B", action="index", description=_("返回首页")),
    ]

    def __init__(
        self,
        data: dict,
    ):
        super().__init__()
        self.data = self.__normalize_data(data)

    @classmethod
    def __normalize_data(cls, data: dict) -> dict:
        """把旧版或手动编辑的配置转换成控件可接受的值。"""
        normalized = data.copy()
        text_defaults = {
            "work_path": r"E:\@imFile-Download",
            "folder_name": "XHS-Download",
            "name_format": "发布时间 作者昵称 作品标题",
            "user_agent": "",
            "cookie": "",
            "proxy": "",
        }
        for key, default in text_defaults.items():
            value = normalized.get(key, default)
            normalized[key] = default if value is None else str(value)

        integer_defaults = {"timeout": 10, "chunk": 2097152, "max_retry": 5}
        for key, default in integer_defaults.items():
            value = normalized.get(key, default)
            normalized[key] = value if isinstance(value, int) else default

        boolean_defaults = {
            "record_data": True,
            "folder_mode": True,
            "video_download": True,
            "image_download": True,
            "live_download": True,
            "download_record": True,
            "author_archive": True,
            "write_mtime": True,
            "script_server": False,
        }
        for key, default in boolean_defaults.items():
            value = normalized.get(key, default)
            normalized[key] = value if isinstance(value, bool) else default

        image_format = str(normalized.get("image_format", "PNG")).upper()
        normalized["image_format"] = (
            image_format if image_format in cls.IMAGE_FORMATS else "PNG"
        )
        normalized["language"] = cls.__valid_choice(
            normalized.get("language"), cls.LANGUAGES, "zh_CN"
        )
        normalized["video_preference"] = cls.__valid_choice(
            normalized.get("video_preference"),
            cls.VIDEO_PREFERENCES,
            "resolution",
        )
        normalized["note_format"] = cls.__valid_choice(
            normalized.get("note_format"), cls.NOTE_FORMATS, ""
        )
        mapping_data = normalized.get("mapping_data", {})
        normalized["mapping_data"] = (
            mapping_data if isinstance(mapping_data, dict) else {}
        )
        return normalized

    @staticmethod
    def __valid_choice(value, choices: tuple[str, ...], default: str) -> str:
        return value if value in choices else default

    def compose(self) -> ComposeResult:
        yield Header()
        yield ScrollableContainer(
            Label(
                _("作品数据 / 文件保存根路径"),
                classes="params",
            ),
            Input(
                self.data["work_path"],
                placeholder=_("程序根路径"),
                valid_empty=True,
                id="work_path",
            ),
            Label(
                _("作品文件储存文件夹名称"),
                classes="params",
            ),
            Input(
                self.data["folder_name"],
                placeholder="Download",
                id="folder_name",
            ),
            Label(
                _("作品文件名称格式"),
                classes="params",
            ),
            Input(
                self.data["name_format"],
                placeholder="发布时间 作者昵称 作品标题",
                valid_empty=True,
                id="name_format",
            ),
            Label(
                _("浏览器模拟目标"),
                classes="params",
            ),
            Input(
                self.data["impersonate"],
                placeholder=IMPERSONATE,
                valid_empty=True,
                id="impersonate",
            ),
            Label(
                _("小红书网页版 Cookie"),
                classes="params",
            ),
            Input(
                placeholder=self.__check_cookie(),
                valid_empty=True,
                id="cookie",
            ),
            Label(
                _("网络代理"),
                classes="params",
            ),
            Input(
                self.data["proxy"],
                placeholder=_("不使用代理"),
                valid_empty=True,
                id="proxy",
            ),
            Label(
                _("请求数据超时限制，单位：秒"),
                classes="params",
            ),
            Input(
                str(self.data["timeout"]),
                placeholder="10",
                type="integer",
                id="timeout",
            ),
            Label(
                _("下载文件时，每次从服务器获取的数据块大小，单位：字节"),
                classes="params",
            ),
            Input(
                str(self.data["chunk"]),
                placeholder="1048576",
                type="integer",
                id="chunk",
            ),
            Label(
                _("请求数据失败时，重试的最大次数"),
                classes="params",
            ),
            Input(
                str(self.data["max_retry"]),
                placeholder="5",
                type="integer",
                id="max_retry",
            ),
            Label(),
            Container(
                Checkbox(
                    _("记录作品详细数据"),
                    id="record_data",
                    value=self.data["record_data"],
                ),
                Checkbox(
                    _("作品归档保存模式"),
                    id="folder_mode",
                    value=self.data["folder_mode"],
                ),
                Checkbox(
                    _("视频作品下载开关"),
                    id="video_download",
                    value=self.data["video_download"],
                ),
                Checkbox(
                    _("图文作品下载开关"),
                    id="image_download",
                    value=self.data["image_download"],
                ),
                classes="horizontal-layout",
            ),
            Label(),
            Container(
                Checkbox(
                    _("动图文件下载开关"),
                    id="live_download",
                    value=self.data["live_download"],
                ),
                Checkbox(
                    _("作品下载记录开关"),
                    id="download_record",
                    value=self.data["download_record"],
                ),
                Checkbox(
                    _("作者归档保存模式"),
                    id="author_archive",
                    value=self.data["author_archive"],
                ),
                Checkbox(
                    _("更新文件修改时间"),
                    id="write_mtime",
                    value=self.data["write_mtime"],
                ),
                classes="horizontal-layout",
            ),
            Label(),
            Container(
                Checkbox(
                    _("视频封面下载开关"),
                    id="video_cover_download",
                    value=self.data["video_cover_download"],
                ),
                Checkbox(
                    _("脚本服务器开关"),
                    id="script_server",
                    value=self.data["script_server"],
                ),
                Checkbox(
                    _("下载文件使用代理"),
                    id="proxy_download",
                    value=self.data["proxy_download"],
                ),
                classes="horizontal-layout",
            ),
            Container(
                Label(
                    _("图片下载格式"),
                    classes="params",
                ),
                Label(
                    _("程序语言"),
                    classes="params",
                ),
                Label(
                    _("视频下载偏好"),
                    classes="params",
                ),
                Label(
                    _("作品信息格式"),
                    classes="params",
                ),
                classes="horizontal-layout",
            ),
            Label(),
            Container(
                Select.from_values(
                    self.IMAGE_FORMATS,
                    value=self.data["image_format"],
                    allow_blank=False,
                    id="image_format",
                ),
                Select.from_values(
                    self.LANGUAGES,
                    value=self.data["language"],
                    allow_blank=False,
                    id="language",
                ),
                Select.from_values(
                    self.VIDEO_PREFERENCES,
                    value=self.data["video_preference"],
                    allow_blank=False,
                    id="video_preference",
                ),
                Select(
                    [
                        (_("不保存"), ""),
                        ("TXT", "txt"),
                        ("MD", "md"),
                        ("ALL", "all"),
                    ],
                    value=self.data["note_format"],
                    allow_blank=False,
                    id="note_format",
                ),
                classes="horizontal-layout",
            ),
            Container(
                Button(
                    _("保存配置"),
                    id="save",
                ),
                Button(
                    _("放弃更改"),
                    id="abandon",
                ),
                classes="settings_button",
            ),
        )
        yield Footer()

    def __check_cookie(self) -> str:
        if self.data["cookie"]:
            return _("小红书网页版 Cookie，无需登录，参数已设置")
        return _("小红书网页版 Cookie，无需登录，参数未设置")

    def on_mount(self) -> None:
        self.title = _("程序设置")

    @on(Button.Pressed, "#save")
    def save_settings(self):
        self.dismiss(
            {
                "mapping_data": self.data.get("mapping_data", {}),
                "work_path": self.query_one("#work_path").value,
                "folder_name": self.query_one("#folder_name").value,
                "name_format": self.query_one("#name_format").value,
                "impersonate": self.query_one("#impersonate").value,
                "cookie": self.query_one("#cookie").value or self.data["cookie"],
                "proxy": self.query_one("#proxy").value or None,
                "timeout": self.__integer_value("#timeout", "timeout"),
                "chunk": self.__integer_value("#chunk", "chunk"),
                "max_retry": self.__integer_value("#max_retry", "max_retry"),
                "record_data": self.query_one("#record_data").value,
                "image_format": self.query_one("#image_format").value.lower(),
                "folder_mode": self.query_one("#folder_mode").value,
                "language": self.query_one("#language").value,
                "image_download": self.query_one("#image_download").value,
                "video_download": self.query_one("#video_download").value,
                "video_cover_download": self.query_one("#video_cover_download").value,
                "live_download": self.query_one("#live_download").value,
                "download_record": self.query_one("#download_record").value,
                "author_archive": self.query_one("#author_archive").value,
                "write_mtime": self.query_one("#write_mtime").value,
                "script_server": self.query_one("#script_server").value,
                "proxy_download": self.query_one("#proxy_download").value,
                "video_preference": self.query_one("#video_preference").value,
                "note_format": self.query_one("#note_format").value,
            }
        )

    def __integer_value(self, selector: str, key: str) -> int:
        value = self.query_one(selector, Input).value
        return int(value) if value else self.data[key]

    @on(Button.Pressed, "#abandon")
    def reset(self):
        self.dismiss(self.data)

    async def action_quit(self) -> None:
        await self.app.action_quit()

    async def action_index(self):
        await self.app.action_back()
