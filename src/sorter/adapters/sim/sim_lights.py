from __future__ import annotations

from sorter.adapters.sim.sim_world import SimWorld


class SimLightsAdapter:
    def __init__(self, world: SimWorld):
        self.world = world
        self.status = "idle"
        self.last_profile = "idle"
        self.last_rgb = (0, 0, 16)

    def set_status(self, status: str) -> None:
        self.status = status
        self.last_profile = status

    def set_rgb(self, red: int, green: int, blue: int, *, profile_name: str | None = None) -> None:
        self.last_profile = profile_name or "custom"
        self.status = self.last_profile
        self.last_rgb = tuple(max(0, min(255, int(value))) for value in (red, green, blue))

    def set_pixels(self, pixels: list[list[int]] | list[tuple[int, int, int]], *, profile_name: str | None = None) -> None:
        self.last_profile = profile_name or "custom-pixels"
        self.status = self.last_profile
        self.last_pixels = [
            [max(0, min(255, int(pixel[0]))), max(0, min(255, int(pixel[1]))), max(0, min(255, int(pixel[2])))]
            for pixel in pixels
        ]
        lit_pixels = [pixel for pixel in self.last_pixels if any(pixel)]
        if len(lit_pixels) == 1:
            self.last_rgb = tuple(lit_pixels[0])
