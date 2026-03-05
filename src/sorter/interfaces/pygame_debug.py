from __future__ import annotations

import pygame
import threading

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile


class PygameDebugUI:
    def __init__(self, orchestrator: Orchestrator, calibration: CalibrationProfile, slow_ms: int = 0):
        self.orchestrator = orchestrator
        self.calibration = calibration
        self.base_slow_ms = max(0, slow_ms)
        self.slow_enabled = self.base_slow_ms > 0
        pygame.init()
        self.window = pygame.display.set_mode((1100, 700))
        pygame.display.set_caption("Sorter Debug UI")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, 24)
        self.header_font = pygame.font.Font(None, 32)
        self.stop_event = threading.Event()
        self.run_thread: threading.Thread | None = None
        self.last_result: dict | None = None
        self.last_error: str | None = None
        self.image_cache: dict[str, pygame.Surface] = {}
        self.start_btn = pygame.Rect(30, 20, 120, 40)
        self.stop_btn = pygame.Rect(170, 20, 120, 40)
        self.slow_btn = pygame.Rect(310, 20, 180, 40)

    def run(self):
        running = True
        while running:
            self.clock.tick(30)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.start_btn.collidepoint(event.pos):
                        self._start_run()
                    elif self.stop_btn.collidepoint(event.pos):
                        self._stop_run()
                    elif self.slow_btn.collidepoint(event.pos):
                        self.slow_enabled = not self.slow_enabled

            self.window.fill((30, 30, 30))
            self._draw_controls()
            self._draw_snapshot()
            pygame.display.flip()

        self._stop_run()
        if self.run_thread and self.run_thread.is_alive():
            self.run_thread.join(timeout=1.0)
        pygame.quit()

    def _start_run(self) -> None:
        if self.run_thread and self.run_thread.is_alive():
            return
        self.stop_event.clear()
        self.last_result = None
        self.last_error = None
        self.run_thread = threading.Thread(target=self._run_worker, daemon=True)
        self.run_thread.start()

    def _stop_run(self) -> None:
        self.stop_event.set()

    def _run_worker(self) -> None:
        try:
            self.last_result = self.orchestrator.run_once(
                self.calibration,
                should_stop=lambda: self.stop_event.is_set(),
                per_command_delay_s=(self.base_slow_ms / 1000.0) if self.slow_enabled else 0.0,
            )
        except Exception as exc:
            self.last_error = str(exc)

    def _draw_controls(self) -> None:
        pygame.draw.rect(self.window, (20, 140, 20), self.start_btn)
        pygame.draw.rect(self.window, (160, 40, 40), self.stop_btn)
        pygame.draw.rect(self.window, (60, 80, 160), self.slow_btn)
        self.window.blit(self.font.render("Start", True, (255, 255, 255)), (68, 32))
        self.window.blit(self.font.render("Stop", True, (255, 255, 255)), (210, 32))
        slow_label = f"Slow: {'ON' if self.slow_enabled else 'OFF'} ({self.base_slow_ms}ms)"
        self.window.blit(self.font.render(slow_label, True, (255, 255, 255)), (322, 32))

        state = "IDLE"
        if self.run_thread and self.run_thread.is_alive():
            state = "RUNNING"
        elif self.last_result:
            state = self.last_result.get("status", "DONE")
        self.window.blit(self.header_font.render(f"State: {state}", True, (220, 220, 220)), (520, 28))

        if self.last_result:
            run_id = self.last_result.get("run_id", "-")
            seq = self.last_result.get("seq", "-")
            self.window.blit(self.font.render(f"Run: {run_id}", True, (200, 200, 200)), (30, 76))
            self.window.blit(self.font.render(f"Moves: {seq}", True, (200, 200, 200)), (30, 100))
        if self.last_error:
            self.window.blit(self.font.render(f"Error: {self.last_error}", True, (255, 120, 120)), (30, 124))

    def _draw_snapshot(self) -> None:
        snapshot = self.orchestrator.world.snapshot
        if not snapshot.piles:
            return

        area_left, area_top = 30, 160
        area_width, area_height = 1020, 510

        pile_ids = [pile.pile_id for pile in snapshot.piles.values()]
        max_x = max(p.x_index for p in pile_ids)
        max_y = max(p.y_index for p in pile_ids)
        cell_w = max(120, area_width // (max_x + 1))
        cell_h = max(100, area_height // (max_y + 1))

        role_color = {
            "FEEDER": (60, 120, 220),
            "SORTING": (90, 90, 90),
            "COLLECTION": (30, 140, 60),
            "TEMP": (130, 100, 30),
            "BLACKHOLE": (110, 40, 110),
        }

        for pile in snapshot.piles.values():
            px = area_left + pile.pile_id.x_index * cell_w + 8
            py = area_top + pile.pile_id.y_index * cell_h + 8
            rect = pygame.Rect(px, py, cell_w - 16, cell_h - 16)
            color = role_color.get(pile.role.value, (100, 100, 100))
            pygame.draw.rect(self.window, color, rect, border_radius=8)
            pygame.draw.rect(self.window, (220, 220, 220), rect, width=2, border_radius=8)

            top_id = pile.top_card_id()
            top_name = "(empty)"
            if top_id:
                meta = self.orchestrator.world.card_by_id.get(top_id)
                top_name = meta.name if meta else top_id
            image_path = self.orchestrator.world.top_card_image_path(pile.pile_id)
            if image_path:
                surface = self._get_image_surface(image_path)
                if surface is not None:
                    scaled = pygame.transform.smoothscale(surface, (70, 98))
                    self.window.blit(scaled, (px + rect.width - 82, py + 10))

            self.window.blit(self.font.render(f"Pile {pile.pile_id.as_key()}", True, (255, 255, 255)), (px + 10, py + 10))
            self.window.blit(self.font.render(pile.role.value, True, (240, 240, 240)), (px + 10, py + 34))
            self.window.blit(self.font.render(f"Count: {pile.num_cards()}", True, (240, 240, 240)), (px + 10, py + 58))
            self.window.blit(self.font.render(f"Top: {top_name[:22]}", True, (240, 240, 240)), (px + 10, py + 82))

        pose = snapshot.pose
        pose_text = f"Pose x={pose.x_mm:.1f} y={pose.y_mm:.1f} z={pose.z_mm:.1f} vacuum={pose.vacuum_on}"
        self.window.blit(self.font.render(pose_text, True, (220, 220, 220)), (30, 640))

    def _get_image_surface(self, image_path: str) -> pygame.Surface | None:
        cached = self.image_cache.get(image_path)
        if cached is not None:
            return cached
        try:
            surface = pygame.image.load(image_path)
            self.image_cache[image_path] = surface
            return surface
        except pygame.error:
            return None
