"""Cross-platform process lock; the operating system releases it on process death."""
import os
from pathlib import Path


class DataDirectoryLock:
    def __init__(self, root: Path):
        self.path = root / ".instance.lock"
        self.handle = None

    def acquire(self):
        if self.handle is not None:
            raise RuntimeError("Khóa instance đã được giữ bởi đối tượng này")
        handle = self.path.open("a+b")
        try:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError) as exc:
            handle.close()
            raise RuntimeError("Thư mục dữ liệu đang được một instance khác sử dụng") from exc
        self.handle = handle
        return self

    def release(self):
        if self.handle is None:
            return
        try:
            self.handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.handle.fileno(), fcntl.LOCK_UN)
        finally:
            self.handle.close()
            self.handle = None
