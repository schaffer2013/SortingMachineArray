from __future__ import annotations

from dataclasses import dataclass, field
import math

from sorter.adapters.hardware.marlin_transport import MarlinTransport, RecordingMarlinTransport
from sorter.domain.models import MachinePose


@dataclass
class MarlinMotionAdapter:
    serial_port: str = "COM3"
    baud_rate: int = 115200
    transport: MarlinTransport | None = None
    xy_feedrate_mm_per_min: int = 6000
    z_feedrate_mm_per_min: int = 1200
    c_feedrate_mm_per_min: int = 1200
    z_home_mm: float = 250.0
    c_home_mm: float = 85.0
    total_distance_mm: float = field(init=False, default=0.0)

    def __post_init__(self) -> None:
        self._pose = MachinePose()
        if self.transport is None:
            self.transport = RecordingMarlinTransport()

    def home_axes(self) -> None:
        self._send("G28 Z")
        self._send("G28 C")
        self._send("G28 X Y")
        self._pose = MachinePose(z_mm=self.z_home_mm, c_mm=self.c_home_mm)

    def move_xy(self, x_mm: float, y_mm: float) -> None:
        self._send("G90")
        self._send(f"G1 X{_format_mm(x_mm)} Y{_format_mm(y_mm)} F{self.xy_feedrate_mm_per_min}")
        self.total_distance_mm += math.dist((self._pose.x_mm, self._pose.y_mm), (x_mm, y_mm))
        self._pose.x_mm = x_mm
        self._pose.y_mm = y_mm

    def move_z(self, z_mm: float) -> None:
        self._send("G90")
        self._send(f"G1 Z{_format_mm(z_mm)} F{self.z_feedrate_mm_per_min}")
        self._pose.z_mm = z_mm

    def move_c(self, c_mm: float) -> None:
        self._send("G90")
        self._send(f"G1 C{_format_mm(c_mm)} F{self.c_feedrate_mm_per_min}")
        self._pose.c_mm = c_mm

    def move_zc(self, z_mm: float, c_mm: float) -> None:
        self._send("G90")
        self._send(f"G1 Z{_format_mm(z_mm)} C{_format_mm(c_mm)} F{self.z_feedrate_mm_per_min}")
        self._pose.z_mm = z_mm
        self._pose.c_mm = c_mm

    def get_pose(self) -> MachinePose:
        return self._pose

    def wait_until_idle(self) -> None:
        self._send("M400")

    def _send(self, command: str) -> None:
        if self.transport is None:
            raise RuntimeError("Marlin motion transport is not configured")
        self.transport.send_command(command)


def _format_mm(value: float) -> str:
    return f"{float(value):.3f}"
