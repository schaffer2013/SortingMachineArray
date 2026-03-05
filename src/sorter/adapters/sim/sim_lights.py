from __future__ import annotations

from sorter.adapters.sim.sim_world import SimWorld


class SimLightsAdapter:
    def __init__(self, world: SimWorld):
        self.world = world
        self.status = "idle"

    def set_status(self, status: str) -> None:
        self.status = status
