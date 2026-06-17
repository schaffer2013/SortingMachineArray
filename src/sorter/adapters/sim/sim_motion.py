from __future__ import annotations

import math

from sorter.adapters.sim.sim_world import SimWorld
from sorter.domain.models import MachinePose


class SimMotionAdapter:
    def __init__(self, world: SimWorld):
        self.world = world

    def home_axes(self) -> None:
        self.world.snapshot.pose.x_mm = 0.0
        self.world.snapshot.pose.y_mm = 0.0
        self.world.snapshot.pose.z_mm = 0.0
        self.world.snapshot.pose.c_mm = 0.0

    def move_xy(self, x_mm: float, y_mm: float) -> None:
        pose = self.world.snapshot.pose
        self.world.snapshot.run_state.metrics.distance_mm += math.dist(
            (pose.x_mm, pose.y_mm),
            (x_mm, y_mm),
        )
        self.world.snapshot.pose.x_mm = x_mm
        self.world.snapshot.pose.y_mm = y_mm

    def move_z(self, z_mm: float) -> None:
        self.world.snapshot.pose.z_mm = z_mm

    def move_c(self, c_mm: float) -> None:
        self.world.snapshot.pose.c_mm = c_mm

    def move_zc(self, z_mm: float, c_mm: float) -> None:
        self.world.snapshot.pose.z_mm = z_mm
        self.world.snapshot.pose.c_mm = c_mm

    def get_pose(self) -> MachinePose:
        return self.world.snapshot.pose

    def wait_until_idle(self) -> None:
        return None
