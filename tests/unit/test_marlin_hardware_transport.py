from __future__ import annotations

import pytest

from sorter.adapters.hardware.marlin_motion import MarlinMotionAdapter
from sorter.adapters.hardware.marlin_transport import (
    MarlinSerialTransport,
    RecordingMarlinTransport,
)
from sorter.adapters.hardware.neopixel_lights import NeoPixelLightsAdapter


class FakeSerialConnection:
    def __init__(self, responses: list[bytes] | None = None):
        self.responses = responses or []
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> int:
        self.writes.append(data)
        return len(data)

    def flush(self) -> None:
        return None

    def readline(self) -> bytes:
        if not self.responses:
            return b""
        return self.responses.pop(0)

    def close(self) -> None:
        self.closed = True


def test_motion_and_lights_share_one_marlin_transport() -> None:
    transport = RecordingMarlinTransport()
    motion = MarlinMotionAdapter(transport=transport)
    lights = NeoPixelLightsAdapter(transport=transport)

    motion.home_axes()
    motion.move_xy(10, 20)
    motion.move_z(3.5)
    motion.move_c(1.25)
    lights.set_status("running")
    motion.wait_until_idle()

    assert transport.command_log == [
        "G28",
        "G1 X10.000 Y20.000 F6000",
        "G1 Z3.500 F1200",
        "G1 C1.250 F1200",
        "M150 R0 U16 B0",
        "M400",
    ]
    assert motion.get_pose().x_mm == 10
    assert motion.get_pose().y_mm == 20
    assert motion.get_pose().z_mm == 3.5
    assert motion.get_pose().c_mm == 1.25
    assert lights.last_command == "M150 R0 U16 B0"


def test_marlin_serial_transport_writes_commands_and_waits_for_ok() -> None:
    connection = FakeSerialConnection([b"echo:busy\n", b"ok\n"])
    transport = MarlinSerialTransport(connection=connection)

    responses = transport.send_command("G28")

    assert connection.writes == [b"G28\n"]
    assert responses == ["echo:busy", "ok"]
    assert transport.command_log == ["G28"]


def test_marlin_serial_transport_raises_on_error_response() -> None:
    connection = FakeSerialConnection([b"Error:Printer halted\n"])
    transport = MarlinSerialTransport(connection=connection)

    with pytest.raises(RuntimeError, match="Marlin rejected"):
        transport.send_command("G1 X1")
