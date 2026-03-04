import os
from pathlib import Path


class InterProcessFileLock:
    """
    Cross-process file lock (non-blocking).
    - macOS/Linux: fcntl.flock
    - Windows: msvcrt.locking
    """

    def __init__(self, lock_path: str | Path):
        self.path = Path(lock_path).expanduser()
        self._fh = None

    def is_acquired(self) -> bool:
        return self._fh is not None

    def acquire(self) -> bool:
        if self._fh is not None:
            return True

        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = open(self.path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            try:
                fh.close()
            except Exception:
                pass
            return False

        self._fh = fh
        try:
            fh.seek(0)
            fh.truncate(0)
            fh.write(str(os.getpid()))
            fh.flush()
        except Exception:
            pass
        return True

    def release(self):
        fh = self._fh
        self._fh = None
        if fh is None:
            return

        try:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        except Exception:
            pass
        try:
            fh.close()
        except Exception:
            pass

    def read_owner_pid(self) -> int | None:
        try:
            raw = self.path.read_text(encoding="utf-8").strip()
            if raw.isdigit():
                return int(raw)
        except Exception:
            return None
        return None

