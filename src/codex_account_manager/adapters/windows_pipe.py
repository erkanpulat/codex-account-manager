"""Bounded cancellable framing for trusted Windows named-pipe handles."""

from __future__ import annotations

import json
import struct
import threading
import time

from codex_account_manager.core.errors import AppServerError, LocalResponseTooLargeError


class FramedPipe:
    def __init__(
        self,
        handle,
        cancelled: threading.Event,
        timeout: float,
        max_frame: int,
        *,
        max_received: int | None = None,
    ):
        self.handle = handle
        self.cancelled = cancelled
        self.deadline = time.monotonic() + timeout
        self.max_frame = max_frame
        self.max_received = max_received
        self.received = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.handle.Close()

    def transfer(self, value: bytes | int) -> bytes:
        import pywintypes
        import win32con
        import win32event
        import win32file

        handle, cancelled, deadline = self.handle, self.cancelled, self.deadline
        operation = pywintypes.OVERLAPPED()
        operation.hEvent = win32event.CreateEvent(None, True, False, None)
        buffer = win32file.AllocateReadBuffer(value) if isinstance(value, int) else value
        submitted = False
        try:
            if cancelled.is_set() or time.monotonic() >= deadline:
                raise AppServerError("Local operation cancelled.")
            if isinstance(value, int):
                win32file.ReadFile(handle, buffer, operation)
            else:
                win32file.WriteFile(handle, buffer, operation)
            submitted = True
            while win32event.WaitForSingleObject(operation.hEvent, 50) == win32con.WAIT_TIMEOUT:
                if cancelled.is_set() or time.monotonic() >= deadline:
                    win32file.CancelIo(handle)
                    raise AppServerError("Local delivery could not be confirmed.")
            count = win32file.GetOverlappedResult(handle, operation, True)
            if not count:
                raise AppServerError("The local channel was closed.")
            if not isinstance(value, int) and count != len(value):
                raise AppServerError("Local delivery could not be confirmed.")
            return bytes(buffer[:count])
        finally:
            # Do not release a buffer while a cancelled read still references it.
            if submitted:
                try:
                    win32file.CancelIo(handle)
                except pywintypes.error:
                    pass
                try:
                    win32file.GetOverlappedResult(handle, operation, True)
                except pywintypes.error:
                    pass
            operation.hEvent.Close()

    def read_exact(self, count: int) -> bytes:
        data = bytearray()
        while len(data) < count:
            data.extend(self.transfer(min(count - len(data), 64 * 1024)))
        return bytes(data)

    def send(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        if len(body) > self.max_frame:
            raise AppServerError("Local request is too large.")
        self.transfer(struct.pack("<I", len(body)) + body)

    def receive(self) -> dict:
        length = struct.unpack("<I", self.read_exact(4))[0]
        if length == 0:
            raise AppServerError("Invalid local frame length.")
        if length > self.max_frame:
            raise LocalResponseTooLargeError(
                f"Local frame exceeds the allowed size ({length} > {self.max_frame} bytes)."
            )
        if self.max_received is not None and self.received + length > self.max_received:
            raise LocalResponseTooLargeError("Local response exceeded the total read budget.")
        self.received += length
        value = json.loads(self.read_exact(length))
        if not isinstance(value, dict):
            raise AppServerError("Invalid local response.")
        return value
