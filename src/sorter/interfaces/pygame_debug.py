from __future__ import annotations

from dataclasses import dataclass
import time
import pygame
import threading

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile


@dataclass
class PoseAnimationSegment:
    active: bool = False
    held_card_id: str | None = None
    start_x_mm: float = 0.0
    start_y_mm: float = 0.0
    start_z_mm: float = 0.0
    end_x_mm: float = 0.0
    end_y_mm: float = 0.0
    end_z_mm: float = 0.0
    started_at: float = 0.0
    duration_s: float = 0.12


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
        self.pose_anim = PoseAnimationSegment()
        pose = self.orchestrator.world.snapshot.pose
        self.last_pose_target = (pose.x_mm, pose.y_mm, pose.z_mm)
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

        try:
            rank_lookup = self.orchestrator.world.rank_lookup()
        except Exception:
            rank_lookup = {}

        self._update_animation_from_pose()
        anim_x_mm, anim_y_mm, anim_z_mm = self._animated_pose_xyz()

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
            top_rank_text = "-"
            if top_id:
                meta = self.orchestrator.world.card_by_id.get(top_id)
                top_name = meta.name if meta else top_id
                rank_value = rank_lookup.get(top_id)
                top_rank_text = str(rank_value) if rank_value is not None else "-"
            image_path = self.orchestrator.world.top_card_image_path(pile.pile_id)
            if image_path:
                surface = self._get_image_surface(image_path)
                if surface is not None:
                    scaled = pygame.transform.smoothscale(surface, (70, 98))
                    self.window.blit(scaled, (px + rect.width - 82, py + 10))

            self.window.blit(self.font.render(f"Pile {pile.pile_id.as_key()}", True, (255, 255, 255)), (px + 10, py + 10))
            self.window.blit(self.font.render(pile.role.value, True, (240, 240, 240)), (px + 10, py + 34))
            self.window.blit(self.font.render(f"Count: {pile.num_cards()}  Rank: {top_rank_text}", True, (240, 240, 240)), (px + 10, py + 58))
            self.window.blit(self.font.render(f"Top: {top_name[:22]}", True, (240, 240, 240)), (px + 10, py + 82))

        self._draw_held_card(anim_x_mm, anim_y_mm, anim_z_mm, area_left, area_top, area_width, area_height)

        pose = snapshot.pose
        pose_text = (
            f"Pose x={anim_x_mm:.1f} y={anim_y_mm:.1f} z={anim_z_mm:.1f} "
            f"vacuum={pose.vacuum_on}"
        )
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

    def _update_animation_from_pose(self) -> None:
        pose = self.orchestrator.world.snapshot.pose
        target = (pose.x_mm, pose.y_mm, pose.z_mm)
        if target == self.last_pose_target:
            return

        now = time.perf_counter()
        if self.pose_anim.active:
            current_x, current_y, current_z = self._animated_pose_xyz(now)
        else:
            current_x, current_y, current_z = self.last_pose_target

        distance_xy = ((target[0] - current_x) ** 2 + (target[1] - current_y) ** 2) ** 0.5
        distance_z = abs(target[2] - current_z)
        duration_s = 0.12
        if distance_xy > 0:
            duration_s = min(0.45, max(0.14, distance_xy / 350.0))
        elif distance_z > 0:
            duration_s = 0.1

        self.pose_anim = PoseAnimationSegment(
            active=True,
            held_card_id=pose.holding_card_id if pose.vacuum_on else None,
            start_x_mm=current_x,
            start_y_mm=current_y,
            start_z_mm=current_z,
            end_x_mm=target[0],
            end_y_mm=target[1],
            end_z_mm=target[2],
            started_at=now,
            duration_s=duration_s,
        )
        self.last_pose_target = target

    def _animated_pose_xyz(self, now: float | None = None) -> tuple[float, float, float]:
        if not self.pose_anim.active:
            return self.last_pose_target

        at = now if now is not None else time.perf_counter()
        elapsed = max(0.0, at - self.pose_anim.started_at)
        duration = max(self.pose_anim.duration_s, 0.001)
        t = min(1.0, elapsed / duration)

        x_mm = self.pose_anim.start_x_mm + (self.pose_anim.end_x_mm - self.pose_anim.start_x_mm) * t
        y_mm = self.pose_anim.start_y_mm + (self.pose_anim.end_y_mm - self.pose_anim.start_y_mm) * t
        z_mm = self.pose_anim.start_z_mm + (self.pose_anim.end_z_mm - self.pose_anim.start_z_mm) * t

        if t >= 1.0:
            self.pose_anim.active = False
            return (self.pose_anim.end_x_mm, self.pose_anim.end_y_mm, self.pose_anim.end_z_mm)
        return (x_mm, y_mm, z_mm)

    def _draw_held_card(
        self,
        x_mm: float,
        y_mm: float,
        z_mm: float,
        area_left: int,
        area_top: int,
        area_width: int,
        area_height: int,
    ) -> None:
        pose = self.orchestrator.world.snapshot.pose
        held_card_id = pose.holding_card_id or self.pose_anim.held_card_id
        if not pose.vacuum_on or held_card_id is None:
            return

        image_path = self.orchestrator.world.image_by_card_id.get(held_card_id)
        if image_path is None:
            return

        surface = self._get_image_surface(image_path)
        if surface is None:
            return

        screen_x, screen_y = self._pose_to_screen(x_mm, y_mm, area_left, area_top, area_width, area_height)
        z_factor = max(0.82, min(1.0, 1.0 - (z_mm / 220.0)))
        w = int(70 * z_factor)
        h = int(98 * z_factor)
        card_surface = pygame.transform.smoothscale(surface, (w, h))
        self.window.blit(card_surface, (int(screen_x - (w / 2)), int(screen_y - h - 8)))

    def _pose_to_screen(
        self,
        x_mm: float,
        y_mm: float,
        area_left: int,
        area_top: int,
        area_width: int,
        area_height: int,
    ) -> tuple[float, float]:
        coords = list(self.orchestrator.world.coords.values())
        if not coords:
            return (area_left + area_width / 2, area_top + area_height / 2)

        x_values = [xy[0] for xy in coords]
        y_values = [xy[1] for xy in coords]
        min_x, max_x = min(x_values), max(x_values)
        min_y, max_y = min(y_values), max(y_values)
        span_x = max(1.0, max_x - min_x)
        span_y = max(1.0, max_y - min_y)

        norm_x = (x_mm - min_x) / span_x
        norm_y = (y_mm - min_y) / span_y

        pad = 20
        draw_w = max(1, area_width - (pad * 2))
        draw_h = max(1, area_height - (pad * 2))
        screen_x = area_left + pad + norm_x * draw_w
        screen_y = area_top + pad + norm_y * draw_h
        return (screen_x, screen_y)
