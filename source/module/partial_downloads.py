"""完整与部分下载目录之间的安全归档，不覆盖已有文件。"""

from pathlib import Path


class PartialDownloads:
    NAME = "部分下载成功"
    MEDIA = {".png", ".jpg", ".jpeg", ".webp", ".avif", ".heic",
             ".mp4", ".mov", ".m4a", ".mp3"}

    def __init__(self, root: Path, folder_mode: bool):
        self.root = root.resolve()
        self.folder_mode = folder_mode

    def _check(self, path: Path) -> None:
        if path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise ValueError("作品归档路径超出下载目录或包含符号链接")

    @staticmethod
    def _unique(path: Path) -> Path:
        candidate = path
        index = 1
        while candidate.exists():
            candidate = path.with_name(f"{path.stem}__保留副本_{index}{path.suffix}")
            index += 1
        return candidate

    def _merge(self, source: Path, target: Path) -> None:
        self._check(source)
        self._check(target)
        if not source.exists():
            return
        # 移动之前检查整个作品目录，避免跟随意外的目录链接。
        for entry in source.rglob("*"):
            self._check(entry)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            source.rename(target)
            return
        if not target.is_dir():
            raise ValueError("归档目标不是目录")
        for entry in list(source.iterdir()):
            destination = target / entry.name
            if entry.is_dir() and destination.is_dir():
                self._merge(entry, destination)
            else:
                self._check(destination)
                entry.rename(self._unique(destination))
        source.rmdir()  # 仅移除搬空的作品目录，不递归删除任何文件。

    @staticmethod
    def _belongs(path: Path, filename: str) -> bool:
        stem = path.stem
        return stem == filename or (
            stem.startswith(filename + "_") and stem[len(filename) + 1:].isdigit()
        )

    def prepare(self, normal: Path, filename: str) -> Path:
        self._check(normal)
        parent = normal.parent if self.folder_mode else normal
        partial = parent / self.NAME / filename
        self._check(partial)
        if partial.is_dir():
            if self.folder_mode and not normal.exists():
                return partial
            self._merge(partial, normal)
        return normal

    def finalize(self, path: Path, filename: str, complete: bool) -> Path:
        self._check(path)
        if self.folder_mode:
            in_partial = path.parent.name == self.NAME
            parent = path.parent.parent if in_partial else path.parent
            normal = parent / filename
            partial = parent / self.NAME / filename
            target = normal if complete else partial
            if not path.is_dir() or path == target:
                return path
            if not complete and not any(
                p.is_file() and p.suffix.lower() in self.MEDIA for p in path.iterdir()
            ):
                return path
            self._merge(path, target)
            return target
        # 关闭按作品分文件夹时，只移动当前作品文件，不能搬走作者目录。
        if complete or not path.is_dir():
            return path
        files = [p for p in path.iterdir() if p.is_file() and self._belongs(p, filename)]
        if not any(p.suffix.lower() in self.MEDIA for p in files):
            return path
        target = path / self.NAME / filename
        self._check(target)
        target.mkdir(parents=True, exist_ok=True)
        for file in files:
            file.rename(self._unique(target / file.name))
        return target
