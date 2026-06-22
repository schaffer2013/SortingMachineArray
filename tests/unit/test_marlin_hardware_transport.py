from __future__ import annotations

import pytest

from sorter.adapters.hardware.marlin_motion import MarlinMotionAdapter
from sorter.adapters.hardware.marlin_transport import (
    MarlinCommandError,
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
    motion.move_zc(1.0, -1.0)
    lights.set_status("running")
    motion.wait_until_idle()

    assert transport.command_log == [
        "G28 Z",
        "G28 C",
        "G28 X Y",
        "G1 X10.000 Y20.000 F6000",
        "G1 Z3.500 F1200",
        "G1 C1.250 F1200",
        "G1 Z1.000 C-1.000 F1200",
        "M150 R0 U16 B0",
        "M400",
    ]
    assert motion.get_pose().x_mm == 10
    assert motion.get_pose().y_mm == 20
    assert motion.get_pose().z_mm == 1.0
    assert motion.get_pose().c_mm == -1.0
    assert lights.last_command == "M150 R0 U16 B0"


def test_neopixel_lights_can_send_indexed_pixels() -> None:
    transport = RecordingMarlinTransport()
    lights = NeoPixelLightsAdapter(transport=transport)
    pixels = [[0, 0, 0] for _ in range(16)]
    pixels[3] = [12, 34, 56]

    lights.set_pixels(pixels, profile_name="single-led")

    assert transport.command_log[0] == "M150 I0 R0 U0 B0"
    assert transport.command_log[3] == "M150 I3 R12 U34 B56"
    assert transport.command_log[-1] == "M150 I15 R0 U0 B0"
    assert lights.last_profile == "single-led"
    assert lights.last_rgb == (12, 34, 56)


def test_home_axes_reports_z_and_c_at_configured_max() -> None:
    motion = MarlinMotionAdapter(z_home_mm=245.0, c_home_mm=41.5)

    motion.home_axes()

    assert motion.get_pose().x_mm == 0.0
    assert motion.get_pose().y_mm == 0.0
    assert motion.get_pose().z_mm == 245.0
    assert motion.get_pose().c_mm == 41.5


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

    with pytest.raises(MarlinCommandError, match="Marlin rejected") as exc_info:
        transport.send_command("G1 X1")

    assert exc_info.value.responses == ["Error:Printer halted"]
