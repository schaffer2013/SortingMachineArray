from __future__ import annotations

from dataclasses import dataclass, field
import threading
from typing import Protocol


class MarlinTransport(Protocol):
    """Shared command channel for Marlin/G-code backed hardware adapters."""

    def send_command(self, command: str, *, wait_for_ok: bool = True) -> list[str]: ...

    def close(self) -> None: ...


class SerialConnection(Protocol):
    def write(self, data: bytes) -> int | None: ...
    def flush(self) -> None: ...
    def readline(self) -> bytes: ...
    def close(self) -> None: ...


class MarlinCommandError(RuntimeError):
    def __init__(self, command: str, line: str, responses: list[str]):
        super().__init__(f"Marlin rejected {command!r}: {line}")
        self.command = command
        self.line = line
        self.responses = responses


@dataclass
class MarlinSerialTransport:
    """PySerial-backed Marlin command transport shared by hardware adapters.

    Marlin exposes one command interpreter on the controller serial connection.
    Motion commands and peripheral commands such as `M150` should therefore be
    serialized through one transport instance instead of each adapter opening an
    independent connection.
    """

    serial_port: str = "COM3"
    baud_rate: int = 115200
    timeout_seconds: float = 2.0
    connection: SerialConnection | None = None
    command_log: list[str] = field(default_factory=list)
    command_lock: threading.Lock = field(default_factory=threading.Lock)

    def open(self) -> SerialConnection:
        if self.connection is None:
            import serial

            self.connection = serial.Serial(
                self.serial_port,
                self.baud_rate,
                timeout=self.timeout_seconds,
            )
        return self.connection

    def send_command(self, command: str, *, wait_for_ok: bool = True) -> list[str]:
        clean_command = command.strip()
        if not clean_command:
            raise ValueError("Marlin command cannot be empty")

        with self.command_lock:
            connection = self.open()
            self.command_log.append(clean_command)
            connection.write(f"{clean_command}\n".encode("ascii"))
            connection.flush()

            if not wait_for_ok:
                return []
            return self._read_until_ok(connection, clean_command)

    def close(self) -> None:
        if self.connection is None:
            return
        self.connection.close()
        self.connection = None

    def _read_until_ok(self, connection: SerialConnection, command: str) -> list[str]:
        responses: list[str] = []
        while True:
            raw_line = connection.readline()
            if raw_line == b"":
                raise TimeoutError(f"Timed out waiting for Marlin ok after {command!r}")
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line:
                continue
            responses.append(line)
            normalized = line.lower()
            if normalized == "ok" or normalized.startswith("ok "):
                return responses
            if normalized.startswith("error"):
                raise MarlinCommandError(command, line, responses)


@dataclass
class RecordingMarlinTransport:
    """In-memory Marlin transport for tests, smoke checks, and dry runs."""

    command_log: list[str] = field(default_factory=list)
    responses: list[str] = field(default_factory=lambda: ["ok"])
    closed: bool = False

    def send_command(self, command: str, *, wait_for_ok: bool = True) -> list[str]:
        clean_command = command.strip()
        if not clean_command:
            raise ValueError("Marlin command cannot be empty")
        self.command_log.append(clean_command)
        if wait_for_ok:
            return list(self.responses)
        return []

    def close(self) -> None:
        self.closed = True
