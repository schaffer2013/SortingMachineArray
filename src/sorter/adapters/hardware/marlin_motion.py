from __future__ import annotations

from dataclasses import dataclass
import math

from sorter.domain.models import MachinePose


@dataclass
class MarlinMotionAdapter:
    serial_port: str = "COM3"
    baud_rate: int = 115200

    def __post_init__(self):
        self._pose = MachinePose()
        self.total_distance_mm = 0.0

    def home_axes(self) -> None:
        self._pose = MachinePose()

    def move_xy(self, x_mm: float, y_mm: float) -> None:
        self.total_distance_mm += math.dist((self._pose.x_mm, self._pose.y_mm), (x_mm, y_mm))
        self._pose.x_mm = x_mm
        self._pose.y_mm = y_mm

    def move_z(self, z_mm: float) -> None:
        self._pose.z_mm = z_mm

    def get_pose(self) -> MachinePose:
        return self._pose

    def wait_until_idle(self) -> None:
        return None
