from asyncio import CancelledError, Semaphore, gather, sleep, to_thread, wait_for
from dataclasses import dataclass
from pathlib import Path
from random import uniform
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse

from aiofiles import open
from curl_cffi import CurlHttpVersion
from curl_cffi.requests.exceptions import RequestException

from ..expansion import CacheError

from ..module import (
    ERROR,
    INFO,
    FILE_SIGNATURES,
    FILE_SIGNATURES_LENGTH,
    MAX_WORKERS,
    WARNING,
    logging,
    # sleep_time,
)
from ..translation import _
from ..module.deferred_retry import DEFERRED_RETRY
from ..module.partial_downloads import PartialDownloads

if TYPE_CHECKING:
    from curl_cffi.requests import AsyncSession

    from ..module import Manager

__all__ = ["Download"]


@dataclass(frozen=True)
class _DownloadOutcome:
    success: bool
    png_conversion_failed: bool = False
    retryable: bool = True
    http2_failed: bool = False

    def __bool__(self) -> bool:
        return self.success


class Download:
    SEMAPHORE = Semaphore(MAX_WORKERS)
    WRITE_BUFFER_SIZE = 1024 * 1024 * 100
    PNG_CONVERSION_FALLBACK_STATUSES = frozenset(
        {
            400,
            404,
            415,
            422,
            *range(500, 600),
        }
    )
    CONTENT_TYPE_MAP = {
        "image/png": "png",
        "image/jpeg": "jpeg",
        "image/webp": "webp",
        "video/mp4": "mp4",
        "video/quicktime": "mov",
        "audio/mp4": "m4a",
        "audio/mpeg": "mp3",
    }

    def __init__(
        self,
        manager: "Manager",
    ):
        self.manager = manager
        self.print = manager.print
        self.folder = manager.folder
        self.temp = manager.temp
        self.chunk = manager.chunk
        self.client: "AsyncSession" = manager.download_client
        self.headers = manager.blank_headers
        self.timeout = max(30, manager.timeout)
        self.retry = manager.retry
        self.folder_mode = manager.folder_mode
        self.video_format = "mp4"
        self.live_format = "mp4"
        self.image_format = manager.image_format
        self.image_format_list = (
            "jpeg",
            "png",
            "webp",
            "avif",
            "heic",
        )
        self.image_download = manager.image_download
        self.video_download = manager.video_download
        self.video_cover_download = manager.video_cover_download
        self.live_download = manager.live_download
        self.author_archive = manager.author_archive
        self.write_mtime = manager.write_mtime

    async def run(
        self,
        urls: list,
        lives: list,
        index: list | tuple | None,
        path: Path,
        filename: str,
        type_: str,
        mtime: int,
        cover: str | None = None,
        progress: Callable[[dict], None] | None = None,
        task_id: str | None = None,
    ) -> list[Any]:
        if type_ == _("视频"):
            tasks = self.__ready_download_video(
                urls,
                path,
                filename,
            )
            tasks += self.__ready_download_cover(
                cover,
                path,
                filename,
            )
        elif type_ in {
            _("图文"),
            _("图集"),
        }:
            tasks = self.__ready_download_image(
                urls,
                lives,
                index,
                path,
                filename,
            )
        else:
            raise ValueError
        tasks = [
            self.__download_with_fallback(
                url,
                path,
                name,
                format_,
                mtime,
                progress,
                task_id,
            )
            for url, name, format_ in tasks
        ]
        results = await gather(*tasks, return_exceptions=True)
        for index, result in enumerate(results):
            if isinstance(result, CancelledError):
                raise result
            if isinstance(result, BaseException):
                logging(self.print, f"文件处理异常：{type(result).__name__}", ERROR)
                results[index] = False
                if deferred := DEFERRED_RETRY.get():
                    deferred.download_failed = True
        return results

    def generate_path(self, nickname: str, filename: str):
        if self.author_archive:
            folder = self.folder.joinpath(nickname)
            folder.mkdir(exist_ok=True)
        else:
            folder = self.folder
        path = self.manager.archive(folder, filename, self.folder_mode)
        path = PartialDownloads(self.folder, self.folder_mode).prepare(path, filename)
        path.mkdir(exist_ok=True)
        return path

    async def finalize_partial(self, path: Path, filename: str, complete: bool) -> None:
        try:
            target = await to_thread(
                PartialDownloads(self.folder, self.folder_mode).finalize,
                path, filename, complete,
            )
            if target != path:
                logging(self.print, f"作品文件已归档到：{target}", WARNING if not complete else INFO)
        except (OSError, ValueError) as error:
            # 移动失败保留现存文件，不能让归档错误终止整个下载队列。
            logging(self.print, f"作品文件归档失败，文件已保留：{type(error).__name__}", ERROR)

    async def finalize_deferred(self, state) -> None:
        for (path, filename), complete in list(state.partial_outcomes.items()):
            await self.finalize_partial(path, filename, complete)
        state.partial_outcomes.clear()

    def __ready_download_video(
        self,
        urls: list[str],
        path: Path,
        name: str,
    ) -> list:
        if not self.video_download:
            logging(self.print, _("视频作品下载功能已关闭，跳过下载"))
            return []
        if self.__check_exists_path(
            path,
            f"{name}.{self.video_format}",
        ):
            return []
        return [(urls[0], name, self.video_format)]

    def __ready_download_cover(
        self,
        url: str | None,
        path: Path,
        name: str,
    ) -> list:
        if not self.video_cover_download or not url:
            return []
        if not any(
            self.__check_exists_path(
                path,
                f"{name}.{s}",
            )
            for s in self.image_format_list
        ):
            return [(url, name, self.image_format)]
        return []

    def __ready_download_image(
        self,
        urls: list[str],
        lives: list[str],
        index: list | tuple | None,
        path: Path,
        name: str,
    ) -> list:
        tasks = []
        if not self.image_download:
            logging(self.print, _("图文作品下载功能已关闭，跳过下载"))
            return tasks
        for i, j in enumerate(zip(urls, lives), start=1):
            if index and i not in index:
                continue
            file = f"{name}_{i}"
            if not any(
                self.__check_exists_path(
                    path,
                    f"{file}.{s}",
                )
                for s in self.image_format_list
            ):
                tasks.append([j[0], file, self.image_format])
            if (
                not self.live_download
                or not j[1]
                or self.__check_exists_path(
                    path,
                    f"{file}.{self.live_format}",
                )
            ):
                continue
            tasks.append([j[1], file, self.live_format])
        return tasks

    def __check_exists_glob(
        self,
        path: Path,
        name: str,
    ) -> bool:
        if any(path.glob(name)):
            logging(self.print, _("{0} 文件已存在，跳过下载").format(name))
            return True
        return False

    def __check_exists_path(
        self,
        path: Path,
        name: str,
    ) -> bool:
        if path.joinpath(name).exists():
            logging(self.print, _("{0} 文件已存在，跳过下载").format(name))
            return True
        return False

    async def __download_with_fallback(
        self,
        url: str,
        path: Path,
        name: str,
        format_: str,
        mtime: int,
        progress: Callable[[dict], None] | None = None,
        task_id: str | None = None,
    ) -> bool:
        retry_options = (
            {"progress": progress, "task_id": task_id}
            if progress is not None or task_id is not None
            else {}
        )
        result = await self.__download_with_retry(
            url,
            path,
            name,
            format_,
            mtime,
            **retry_options,
        )
        if result:
            return True
        deferred = DEFERRED_RETRY.get()
        if deferred is not None and not deferred.retrying:
            # 第一轮只记录失败，不在当前帖子内重试或切换 PNG 地址。
            return False
        if not result.png_conversion_failed:
            logging(self.print, f"{name}：下载失败，已结束重试", ERROR)
            return False
        if not (auto_url := self.__generate_auto_url(url)):
            logging(self.print, f"{name}：下载失败，已结束重试", ERROR)
            return False

        self.manager.delete(self.temp.joinpath(f"{name}.{format_}"))
        logging(
            self.print,
            f"{name} 的 PNG 转换地址下载失败，仅该文件改用 AUTO 重试",
            WARNING,
        )
        success = bool(
            await self.__download_with_retry(
                auto_url,
                path,
                name,
                "auto",
                mtime,
                **retry_options,
            )
        )
        if not success:
            logging(self.print, f"{name}：下载失败，已结束重试", ERROR)
        return success

    async def __download_with_retry(
        self,
        url: str,
        path: Path,
        name: str,
        format_: str,
        mtime: int,
        progress: Callable[[dict], None] | None = None,
        task_id: str | None = None,
    ) -> _DownloadOutcome:
        deferred = DEFERRED_RETRY.get()
        png_conversion_failed = bool(deferred and url in deferred.png_failures)
        http1 = bool(deferred and url in deferred.http1_urls)
        retry_limit = 0 if deferred is not None else self.retry
        for attempt in range(retry_limit + 1):
            if attempt:
                delay = min(2 ** attempt, 20) + uniform(0, 1)
                logging(
                    self.print,
                    f"{name}：等待 {delay:.1f} 秒后重试（{attempt}/{self.retry}）",
                    WARNING,
                )
                if progress:
                    progress({
                        "task_id": task_id,
                        "filename": f"{name}.{format_}",
                        "state": "retrying",
                    })
                await sleep(delay)
            request_options = {"http_version": CurlHttpVersion.V1_1} if http1 else {}
            result = await self.__download_once(
                url,
                path,
                name,
                format_,
                mtime,
                progress,
                task_id,
                **request_options,
            )
            http1 |= result.http2_failed
            png_conversion_failed |= result.png_conversion_failed
            if result:
                return _DownloadOutcome(True, png_conversion_failed)
            if deferred is not None:
                deferred.download_failed = True
                deferred.retryable |= result.retryable
                if http1:
                    deferred.http1_urls.add(url)
                if png_conversion_failed:
                    deferred.png_failures.add(url)
            if not result.retryable:
                break
        if progress:
            progress({
                "task_id": task_id,
                "filename": f"{name}.{format_}",
                "state": "failed",
            })
        logging(self.print, f"{name}：当前地址尝试已结束", WARNING)
        return _DownloadOutcome(False, png_conversion_failed)

    async def __download_once(
        self,
        url: str,
        path: Path,
        name: str,
        format_: str,
        mtime: int,
        progress: Callable[[dict], None] | None,
        task_id: str | None,
        http_version: CurlHttpVersion | None = None,
    ):
        async with self.SEMAPHORE:
            headers = self.headers.copy()
            temp = self.temp.joinpath(f"{name}.{format_}")
            completed = self.__update_headers_range(
                headers,
                temp,
            )

            def report(state: str, total: int | None = None) -> None:
                if progress:
                    progress(
                        {
                            "task_id": task_id,
                            "filename": f"{name}.{format_}",
                            "completed_bytes": completed,
                            "total_bytes": total,
                            "state": state,
                        }
                    )

            try:
                async with self.client.stream(
                    "GET",
                    url,
                    headers=headers,
                    timeout=(min(self.timeout, 15), self.timeout),
                    **({"http_version": http_version} if http_version is not None else {}),
                ) as response:
                    # await sleep_time()
                    if response.status_code == 416:
                        raise CacheError(
                            _("文件 {0} 缓存异常，重新下载").format(temp.name),
                        )
                    response.raise_for_status()
                    # 服务器忽略 Range 时从头写入，避免完整文件追加到旧缓存。
                    if completed and response.status_code == 200:
                        completed = 0
                    # self.__create_progress(
                    #     bar,
                    #     int(
                    #         response.headers.get(
                    #             'content-length', 0)) or None,
                    # )
                    content_length = int(response.headers.get("content-length", 0) or 0)
                    total = completed + content_length if content_length else None
                    report("downloading", total)
                    buffer = bytearray()
                    async with open(temp, "ab" if completed else "wb") as f:
                        content = response.aiter_content(self.chunk)
                        try:
                            while True:
                                try:
                                    chunk = await wait_for(
                                        anext(content), timeout=self.timeout,
                                    )
                                except StopAsyncIteration:
                                    break
                                buffer.extend(chunk)
                                if len(buffer) >= self.WRITE_BUFFER_SIZE:
                                    await f.write(bytes(buffer))
                                    buffer.clear()
                                completed += len(chunk)
                                report("downloading", total)
                        finally:
                            # 超时或断开时也保存已收到的数据，供下次 Range 续传。
                            if buffer:
                                await f.write(bytes(buffer))
                    if total is not None and completed != total:
                        raise CacheError(f"文件 {name} 长度不完整，重新下载")
                real = await self.__suffix_with_file(
                    temp,
                    path,
                    name,
                    # suffix,
                    format_,
                )
                self.manager.move(
                    temp,
                    real,
                    mtime,
                    self.write_mtime,
                )
                report("completed", total)
                logging(self.print, _("文件 {0} 下载成功").format(real.name))
                return _DownloadOutcome(True)
            except TimeoutError as error:
                report("failed")
                logging(
                    self.print,
                    _("网络异常，{0} 下载超时（{1} 秒）").format(
                        name,
                        self.timeout,
                    ),
                    WARNING,
                )
                return _DownloadOutcome(
                    False,
                    self.__is_png_conversion_failure(url, format_, error),
                )
            except RequestException as error:
                report("failed")
                logging(
                    self.print,
                    _("网络异常，{0} 下载失败，错误信息: {1}").format(
                        name, self.__error_summary(error)
                    ),
                    WARNING,
                )
                return _DownloadOutcome(
                    False,
                    self.__is_png_conversion_failure(url, format_, error),
                    retryable=self.__can_retry(url, format_, error),
                    http2_failed=getattr(error, "code", None) in {16, 92},
                )
            except CacheError as error:
                report("failed")
                self.manager.delete(temp)
                logging(
                    self.print,
                    str(error),
                    ERROR,
                )
                return _DownloadOutcome(False)

    @staticmethod
    def __error_summary(error: Exception) -> str:
        status = getattr(getattr(error, "response", None), "status_code", None)
        return (
            f"{type(error).__name__}，curl {getattr(error, 'code', None)}，"
            f"HTTP {status}"
        )

    @classmethod
    def __can_retry(cls, url: str, format_: str, error: Exception) -> bool:
        status = getattr(getattr(error, "response", None), "status_code", None)
        return (
            status is None or status in {408, 429} or status >= 500
            or cls.__is_png_conversion_failure(url, format_, error)
        )

    @classmethod
    def __is_png_conversion_failure(
        cls,
        url: str,
        format_: str,
        error: Exception,
    ) -> bool:
        if format_.lower() != "png":
            return False
        link = urlparse(url)
        if isinstance(error, TimeoutError):
            return (
                link.hostname == "ci.xiaohongshu.com"
                and "imageview2/format/png" in link.query.lower()
            )
        status_code = getattr(getattr(error, "response", None), "status_code", None)
        return (
            link.hostname == "ci.xiaohongshu.com"
            and "imageview2/format/png" in link.query.lower()
            and status_code in cls.PNG_CONVERSION_FALLBACK_STATUSES
        )

    @staticmethod
    def __generate_auto_url(url: str) -> str:
        link = urlparse(url)
        if (
            link.hostname != "ci.xiaohongshu.com"
            or "imageview2/format/png" not in link.query.lower()
        ):
            return ""
        return f"https://sns-img-bd.xhscdn.com/{link.path.lstrip('/')}"

    @staticmethod
    def __create_progress(
        bar,
        total: int | None,
        completed=0,
    ):
        if bar:
            bar.update(total=total, completed=completed)

    @staticmethod
    def __update_progress(bar, advance: int):
        if bar:
            bar.advance(advance)

    @classmethod
    def __extract_type(cls, content: str) -> str:
        return cls.CONTENT_TYPE_MAP.get(content, "")

    async def __head_file(
        self,
        url: str,
        headers: dict[str, str],
        suffix: str,
    ) -> tuple[int, str]:
        """未使用"""
        response = await self.client.head(
            url,
            headers=headers,
        )
        # await sleep_time()
        response.raise_for_status()
        suffix = self.__extract_type(response.headers.get("Content-Type")) or suffix
        length = response.headers.get("Content-Length", 0)
        return int(length), suffix

    @staticmethod
    def __get_resume_byte_position(file: Path) -> int:
        return file.stat().st_size if file.is_file() else 0

    def __update_headers_range(
        self,
        headers: dict[str, str],
        file: Path,
    ) -> int:
        headers["Range"] = f"bytes={(p := self.__get_resume_byte_position(file))}-"
        return p

    async def __suffix_with_file(
        self,
        temp: Path,
        path: Path,
        name: str,
        default_suffix: str,
    ) -> Path:
        try:
            async with open(temp, "rb") as f:
                file_start = await f.read(FILE_SIGNATURES_LENGTH)
            for offset, signature, suffix in FILE_SIGNATURES:
                if file_start[offset : offset + len(signature)] == signature:
                    return path.joinpath(f"{name}.{suffix}")
        except Exception as error:
            logging(
                self.print,
                _("文件 {0} 格式判断失败，错误信息：{1}").format(
                    temp.name, repr(error)
                ),
                ERROR,
            )
        return path.joinpath(f"{name}.{default_suffix}")
