"""KVDatabase engine. Public API for the whole project."""

import os
import threading

from src.format import (
    HEADER_SIZE,
    CorruptFrameError,
    encode_header,
    encode_transaction,
    validate_header,
)


class DiskFullError(Exception):
    """Raised when a write would exceed max_bytes. Nothing was written."""


class KVDatabase:
    def __init__(self, path: str, max_bytes: int | None = None):
        if max_bytes is not None and (
            isinstance(max_bytes, bool) or not isinstance(max_bytes, int) or max_bytes < HEADER_SIZE
        ):
            raise ValueError(f"max_bytes must be at least {HEADER_SIZE}")

        self.path = path
        self.max_bytes = max_bytes
        self.index: dict[bytes, bytes | None] = {}
        self.valid_end = HEADER_SIZE
        self.lock = threading.Lock()
        self.fh = None
        self._unsafe = False
        self._open_and_recover()

    def _open_and_recover(self) -> None:
        self.fh = open(self.path, "a+b")
        try:
            self.fh.seek(0, os.SEEK_END)
            file_size = self.fh.tell()
            if file_size == 0:
                self.fh.write(encode_header())
                self.fh.flush()
                os.fsync(self.fh.fileno())
            else:
                self.fh.seek(0)
                validate_header(self.fh.read(HEADER_SIZE))

            from src.recovery import recover

            self.fh.seek(HEADER_SIZE)
            recovered_index, valid_end = recover(self.fh)
            self.fh.seek(0, os.SEEK_END)
            file_size = self.fh.tell()
            if not isinstance(valid_end, int) or not HEADER_SIZE <= valid_end <= file_size:
                raise CorruptFrameError("recovery returned an invalid end offset")
            if not isinstance(recovered_index, dict):
                raise CorruptFrameError("recovery returned an invalid index")
            for key, value in recovered_index.items():
                if not isinstance(key, bytes) or (
                    value is not None and not isinstance(value, bytes)
                ):
                    raise CorruptFrameError("recovery returned invalid index entries")

            if file_size != valid_end:
                self.fh.truncate(valid_end)
                self.fh.flush()
                os.fsync(self.fh.fileno())

            self.index = recovered_index
            self.valid_end = valid_end
            self.fh.seek(valid_end)
        except BaseException:
            self.fh.close()
            self.fh = None
            raise

    def _ensure_open(self) -> None:
        if self.fh is None:
            raise ValueError("database is closed")

    def _append(self, operations: list[tuple[str, bytes, bytes | None]]) -> None:
        frame = encode_transaction(operations)
        new_end = self.valid_end + len(frame)
        if self.max_bytes is not None and new_end > self.max_bytes:
            raise DiskFullError(
                f"transaction would exceed max_bytes ({new_end} > {self.max_bytes})"
            )

        self._ensure_open()
        if self._unsafe:
            raise RuntimeError("database must be reopened after a failed write")

        try:
            self.fh.seek(self.valid_end)
            remaining = memoryview(frame)
            while remaining:
                written = self.fh.write(remaining)
                if written is None or written <= 0:
                    raise OSError("database write made no progress")
                remaining = remaining[written:]
            self.fh.flush()
            os.fsync(self.fh.fileno())
        except BaseException:
            self._unsafe = True
            raise

        for kind, key, value in operations:
            self.index[key] = value if kind == "put" else None
        self.valid_end = new_end

    def put(self, key: bytes, value: bytes) -> None:
        with self.lock:
            self._append([("put", key, value)])

    def get(self, key: bytes) -> bytes | None:
        if not isinstance(key, bytes):
            raise TypeError("key must be bytes")
        if not 1 <= len(key) <= 1024:
            raise ValueError("key must be 1..1024 bytes")
        with self.lock:
            self._ensure_open()
            return self.index.get(key)

    def delete(self, key: bytes) -> None:
        with self.lock:
            self._append([("delete", key, None)])

    def batch(self, ops: list[tuple[str, bytes, bytes | None]]) -> None:
        if not isinstance(ops, list):
            raise TypeError("ops must be a list")
        with self.lock:
            self._append(ops)

    def compact(self) -> None:
        with self.lock:
            self._ensure_open()
            if self._unsafe:
                raise RuntimeError("database must be reopened after a failed write")
            from src.compaction import compact_database

            compact_database(self)

    def close(self) -> None:
        with self.lock:
            if self.fh is not None:
                try:
                    self.fh.close()
                finally:
                    self.fh = None

    def __enter__(self) -> "KVDatabase":
        self._ensure_open()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()
