from __future__ import annotations

from sorter.adapters.sim.sim_world import SimWorld


class SimVacuumAdapter:
    def __init__(self, world: SimWorld):
        self.world = world

    def on(self) -> None:
        self.world.snapshot.pose.vacuum_on = True

    def off(self) -> None:
        self.world.snapshot.pose.vacuum_on = False

    def is_on(self) -> bool:
        return self.world.snapshot.pose.vacuum_on
