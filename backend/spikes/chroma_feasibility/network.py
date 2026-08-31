"""Socket guard used to detect hidden network access in the offline spike."""

from __future__ import annotations

import socket
from types import TracebackType
from typing import Self


class NetworkGuard:
    def __init__(self) -> None:
        self.used = False
        self._original = socket.socket.connect

    def __enter__(self) -> Self:
        def blocked_connect(_socket: socket.socket, _address: object) -> None:
            self.used = True
            raise OSError("network disabled by Chroma feasibility spike")

        socket.socket.connect = blocked_connect
        return self

    def __exit__(
        self,
        _exception_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        socket.socket.connect = self._original
