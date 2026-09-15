from datetime import datetime
from html import unescape
from re import DOTALL, IGNORECASE, search, sub
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from curl_cffi.requests import get
from curl_cffi.requests.exceptions import RequestException

from ..module import ERROR, logging, retry, sleep_time
from ..translation import _

if TYPE_CHECKING:
    from ..module import Manager

__all__ = ["Html"]


class Html:
    TITLE_PATTERN = r"<title[^>]*>(.*?)</title>"

    def __init__(
        self,
        manager: "Manager",
    ):
        self.manager = manager
        self.print = manager.print
        self.retry = manager.retry
        self.client = manager.request_client
        self.timeout = manager.timeout
        self.proxy = manager.proxy
        self.impersonate = manager.impersonate
        self.last_response: dict[str, object] = {}
        self.failure_log_path = manager.root.joinpath(
            "Logs",
            "request_failures.log",
        )
        self.failure_log_announced = False

    @retry
    async def request_url(
        self,
        url: str,
        content=True,
        cookie: str | None = None,
        proxy: str | None = None,
        **kwargs,
    ) -> str:
        if not url.startswith("http"):
            url = f"https://{url}"
        default_cookie_used = bool(self.client.cookies) if not proxy else False
        cookie_used = bool(cookie) or default_cookie_used
        headers = self.manager.get_headers(url)
        try:
            if cookie:
                response = self.__request_url_with_cookie(
                    url,
                    headers,
                    cookie,
                    proxy=proxy,
                    **kwargs,
                )
            else:
                response = await self.__request_url_get(
                    url,
                    headers,
                    proxy=proxy,
                    **kwargs,
                )
            self._record_response(response, cookie_used)
            await sleep_time()
            response.raise_for_status()
            return response.text if content else str(response.url)
        except RequestException as error:
            self._record_request_error(url, error, cookie_used)
            logging(
                self.print,
                _("网络异常，{0} 请求失败: {1}").format(
                    self._safe_url(url),
                    self._error_summary(error),
                ),
                ERROR,
            )
            return ""

    def _record_response(self, response: Any, cookie_used: bool = False) -> None:
        text = response.text
        final_url = str(response.url)
        query = parse_qs(urlsplit(final_url).query)
        self.last_response = {
            "status_code": response.status_code,
            "final_path": self._safe_url(final_url),
            "redirect_count": len(response.history),
            "response_bytes": len(response.content),
            "content_type": response.headers.get("content-type", ""),
            "page_title": self._extract_title(text),
            "error_code": self._query_value(query, "error_code"),
            "error_message": self._query_value(query, "error_msg"),
            "has_initial_state": "window.__INITIAL_STATE__" in text,
            "has_note_data": "noteDetailMap" in text or "noteData" in text,
            "cookie_used": cookie_used,
            "network_error": "",
        }

    def _record_request_error(
        self,
        url: str,
        error: Exception,
        cookie_used: bool,
    ) -> None:
        if response := getattr(error, "response", None):
            self._record_response(response, cookie_used)
        else:
            self.last_response = {
                "status_code": None,
                "final_path": self._safe_url(url),
                "redirect_count": 0,
                "response_bytes": 0,
                "content_type": "",
                "page_title": "",
                "error_code": "",
                "error_message": "",
                "has_initial_state": False,
                "has_note_data": False,
                "cookie_used": cookie_used,
                "network_error": self._error_summary(error),
            }

    def last_response_diagnostic(self) -> str:
        info = self.last_response
        if not info:
            return "未取得响应信息"

        reason = self._diagnostic_reason(info)
        details = [
            f"HTTP {info['status_code']}"
            if info.get("status_code") is not None
            else "未收到 HTTP 响应",
            f"最终页面 {info.get('final_path') or '未知'}",
            f"跳转 {info.get('redirect_count', 0)} 次",
            f"响应 {self._format_size(info.get('response_bytes', 0))}",
            f"携带 Cookie：{'是' if info.get('cookie_used') else '否'}",
            f"初始状态：{'有' if info.get('has_initial_state') else '无'}",
            f"作品字段标记：{'有' if info.get('has_note_data') else '无'}",
        ]
        if title := info.get("page_title"):
            details.append(f"页面标题：{title}")
        return f"{reason}；{'；'.join(details)}"

    def save_failure_diagnostic(self, item_id: str, diagnostic: str) -> bool:
        safe_id = sub(r"[^a-zA-Z0-9_-]", "", item_id)[:64] or "unknown"
        line = f"{datetime.now():%Y-%m-%d %H:%M:%S} | {safe_id} | {diagnostic}\n"
        try:
            self.failure_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.failure_log_path.open("a", encoding="utf-8") as file:
                file.write(line)
            return True
        except OSError as error:
            logging(
                self.print,
                f"写入失败诊断日志失败：{type(error).__name__}",
                ERROR,
            )
            return False

    @staticmethod
    def _diagnostic_reason(info: dict[str, object]) -> str:
        if error := info.get("network_error"):
            return f"网络请求异常（{error}）"
        code = str(info.get("error_code") or "")
        message = str(info.get("error_message") or "")
        if code or message:
            label = f"平台返回错误 {code}" if code else "平台返回错误"
            return f"{label}（{message}）" if message else label
        if info.get("status_code") and int(info["status_code"]) >= 400:
            return "平台返回 HTTP 错误"
        if str(info.get("final_path") or "").endswith("/404"):
            return "页面跳转到不可访问页"
        if not info.get("response_bytes"):
            return "响应内容为空"
        if not info.get("has_initial_state"):
            return "页面未包含作品初始状态，可能是验证页或页面结构已变化"
        if not info.get("has_note_data"):
            return "页面包含初始状态但没有作品详情，作品可能已删除、私密或链接令牌失效"
        return "页面中存在作品数据标记，但解析结果为空，可能是页面结构已变化"

    @classmethod
    def _extract_title(cls, text: str) -> str:
        if not (
            matched := search(cls.TITLE_PATTERN, text, flags=IGNORECASE | DOTALL)
        ):
            return ""
        return sub(r"\s+", " ", unescape(matched.group(1))).strip()[:80]

    @staticmethod
    def _query_value(query: dict[str, list[str]], key: str) -> str:
        return values[0].strip()[:160] if (values := query.get(key)) else ""

    @staticmethod
    def _safe_url(url: str) -> str:
        parsed = urlsplit(str(url))
        if parsed.scheme and parsed.netloc:
            return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        return parsed.path or str(url).split("?", 1)[0]

    @staticmethod
    def _error_summary(error: Exception) -> str:
        status = getattr(getattr(error, "response", None), "status_code", None)
        return (
            f"{type(error).__name__}，HTTP {status}"
            if status is not None
            else type(error).__name__
        )

    @staticmethod
    def _format_size(value: object) -> str:
        size = int(value or 0)
        if size < 1024:
            return f"{size} B"
        if size < 1024 * 1024:
            return f"{size / 1024:.1f} KiB"
        return f"{size / 1024 / 1024:.2f} MiB"

    @staticmethod
    def format_url(url: str) -> str:
        return bytes(url, "utf-8").decode("unicode_escape")

    def __request_url_with_cookie(
            self,
            url: str,
            headers: dict,
            cookie: str,
            proxy: str | None = None,
            **kwargs,
    ):
        timeout = kwargs.pop("timeout", self.timeout)
        return get(
            url,
            headers=headers,
            cookies=self.manager.cookie_str_to_dict(cookie),
            timeout=timeout,
            verify=False,
            allow_redirects=True,
            proxy=self.proxy if proxy is None else proxy,
            impersonate=self.impersonate,
            **kwargs,
        )

    async def __request_url_get(
        self,
        url: str,
        headers: dict,
        proxy: str | None = None,
        **kwargs,
    ):
        return await self.client.get(
            url,
            headers=headers,
            proxy=self.proxy if proxy is None else proxy,
            **kwargs,
        )
