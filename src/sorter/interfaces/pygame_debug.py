from __future__ import annotations

from dataclasses import dataclass
import time
import pygame
import threading

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.enums import PileObservationState, PileRole

MAGIC_CARD_WIDTH_MM = 63.0
DIME_DIAMETER_MM = 17.91
MAGIC_CARD_HEIGHT_MM = 88.0
DASHBOARD_BG = (24, 26, 32)
BOARD_BG = (34, 38, 46)
BOARD_GRID = (58, 64, 74)
LABEL_BG = (22, 24, 30)
SUMMARY_BG = (28, 31, 38)
SUMMARY_BORDER = (88, 94, 104)
PILE_BADGE_GAP_PX = 10
BOARD_TOP_PADDING_PX = 58


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

            self.window.fill(DASHBOARD_BG)
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

        substate_text = self._substate_label()
        self.window.blit(self.font.render(f"Substate: {substate_text}", True, (220, 220, 220)), (520, 62))

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
            rank_lookup = self.orchestrator.world.discovered_rank_lookup()
        except Exception:
            rank_lookup = {}

        self._update_animation_from_pose()
        anim_x_mm, anim_y_mm, anim_z_mm = self._animated_pose_xyz()

        board_rect = pygame.Rect(24, 150, 744, 500)
        summary_rect = pygame.Rect(board_rect.right + 16, board_rect.top, 292, board_rect.height)
        pygame.draw.rect(self.window, BOARD_BG, board_rect, border_radius=18)
        pygame.draw.rect(self.window, BOARD_GRID, board_rect, width=2, border_radius=18)
        pygame.draw.rect(self.window, SUMMARY_BG, summary_rect, border_radius=14)
        pygame.draw.rect(self.window, SUMMARY_BORDER, summary_rect, width=1, border_radius=14)

        layout = self._board_layout(board_rect)

        role_color = {
            "FEEDER": (60, 120, 220),
            "SORTING": (90, 90, 90),
            "COLLECTION": (30, 140, 60),
            "TEMP": (130, 100, 30),
            "BLACKHOLE": (110, 40, 110),
        }

        ordered_piles = sorted(
            snapshot.piles.values(),
            key=lambda pile: (*self._pile_reference_xy(pile), pile.pile_id.as_key()),
        )
        display_numbers = self._pile_display_numbers(ordered_piles)
        for pile in ordered_piles:
            rect = self._pile_card_rect(pile, layout)
            color = role_color.get(pile.role.value, (100, 100, 100))
            fill_color = tuple(min(255, channel + 18) for channel in color)
            pygame.draw.rect(self.window, fill_color, rect, border_radius=10)
            pygame.draw.rect(self.window, (230, 230, 230), rect, width=2, border_radius=10)

            top_id = pile.top_card_id() if pile.has_observed_top_card() else None
            top_name = self._top_label(pile)
            top_rank_text = self._top_rank_label(pile, top_id, rank_lookup)
            count_text = self._count_label(pile)
            image_path = self.orchestrator.world.top_card_image_path(pile.pile_id)
            if pile.has_observed_top_card() and image_path:
                surface = self._get_image_surface(image_path)
                if surface is not None:
                    scaled = pygame.transform.smoothscale(surface, (rect.width, rect.height))
                    self.window.blit(scaled, rect.topleft)
                    pygame.draw.rect(self.window, (230, 230, 230), rect, width=2, border_radius=10)
                else:
                    self._draw_unknown_card_preview(rect)
            else:
                self._draw_unknown_card_preview(rect)

            self._draw_pile_badge(pile, rect, display_numbers)

        self._draw_held_card(anim_x_mm, anim_y_mm, anim_z_mm, layout)
        self._draw_end_effector(anim_x_mm, anim_y_mm, layout)
        self._draw_camera_reticle(anim_x_mm, anim_y_mm, layout)
        self._draw_pile_summary_panel(ordered_piles, rank_lookup, summary_rect, display_numbers)

        pose = snapshot.pose
        pose_text = (
            f"Pose x={anim_x_mm:.1f} y={anim_y_mm:.1f} z={anim_z_mm:.1f} "
            f"vacuum={pose.vacuum_on}"
        )
        self.window.blit(self.font.render(pose_text, True, (220, 220, 220)), (30, 668))

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

    def _count_label(self, pile) -> str:
        if not pile.has_known_count():
            return "?"
        return str(pile.num_cards())

    def _top_label(self, pile) -> str:
        if pile.observation.state == PileObservationState.UNKNOWN:
            return "(unknown)"
        if pile.observation.state == PileObservationState.EMPTY_CONFIRMED:
            return "(empty)"
        return pile.observation.top_card_name or "(unknown)"

    def _top_rank_label(self, pile, top_id: str | None, rank_lookup: dict[str, int]) -> str:
        if not pile.has_observed_top_card() or top_id is None:
            return "-"
        rank_value = rank_lookup.get(top_id)
        return str(rank_value) if rank_value is not None else "-"

    def _substate_label(self) -> str:
        run_state = self.orchestrator.world.snapshot.run_state
        phase = str(run_state.phase).title()
        command = self._friendly_command_label(run_state.active_command)
        if command is None:
            return phase
        return f"{phase} / {command}"

    def _friendly_command_label(self, command_name: str | None) -> str | None:
        if not command_name:
            return None
        labels = {
            "StartupScan": "startup scan",
            "PlanNextMove": "planning next move",
            "NoMoveAvailable": "no move available",
            "MoveToDiscoveryXY": "moving to discovery",
            "MoveToVerificationXY": "moving to verification",
            "CaptureDiscovery": "imaging discovery pile",
            "CaptureFrame": "imaging",
            "RecognizeTopCard": "recognizing",
            "MoveToSourceXY": "moving to source",
            "MoveToDestXY": "moving to destination",
            "MoveZ": "moving z",
            "VacuumOn": "pulling vac",
            "VacuumOff": "releasing vac",
            "CaptureVerification": "imaging verification pile",
            "ReviewRequired": "review required",
            "StartupReviewRequired": "startup review required",
        }
        return labels.get(command_name, command_name)

    def _end_effector_radius_px(self, layout: dict[str, float] | None = None) -> int:
        width_px = self._card_size_px(layout)[0] if layout is not None else 70
        diameter_px = width_px * (DIME_DIAMETER_MM / MAGIC_CARD_WIDTH_MM)
        return max(4, round(diameter_px / 2))

    def _pile_reference_xy(self, pile) -> tuple[float, float]:
        return self.calibration.pile_xy_mm.get(pile.pile_id.as_key(), (pile.x_mm, pile.y_mm))

    def _pile_display_numbers(self, piles) -> dict[str, int]:
        return {
            pile.pile_id.as_key(): index + 1
            for index, pile in enumerate(piles)
        }

    def _board_layout(self, board_rect: pygame.Rect) -> dict[str, float]:
        coords = [self._pile_reference_xy(pile) for pile in self.orchestrator.world.snapshot.piles.values()]
        if not coords:
            return {
                "board_left": float(board_rect.left),
                "board_top": float(board_rect.top),
                "board_width": float(board_rect.width),
                "board_height": float(board_rect.height),
                "draw_left": float(board_rect.left + 20),
                "draw_top": float(board_rect.top + 30),
                "draw_width": float(board_rect.width - 40),
                "draw_height": float(board_rect.height - 60),
                "scale": 1.0,
            }

        x_values = [xy[0] for xy in coords]
        y_values = [xy[1] for xy in coords]
        min_x, max_x = min(x_values), max(x_values)
        min_y, max_y = min(y_values), max(y_values)

        margin_x_mm = MAGIC_CARD_WIDTH_MM * 0.28
        margin_y_mm = MAGIC_CARD_HEIGHT_MM * 0.28
        world_width_mm = max(1.0, (max_x - min_x) + (margin_x_mm * 2))
        world_height_mm = max(1.0, (max_y - min_y) + (margin_y_mm * 2))

        draw_left = board_rect.left + 20
        draw_top = board_rect.top + BOARD_TOP_PADDING_PX
        draw_width = board_rect.width - 40
        draw_height = board_rect.height - (BOARD_TOP_PADDING_PX + 22)
        scale = min(draw_width / world_width_mm, draw_height / world_height_mm)

        return {
            "board_left": float(board_rect.left),
            "board_top": float(board_rect.top),
            "board_width": float(board_rect.width),
            "board_height": float(board_rect.height),
            "draw_left": float(draw_left),
            "draw_top": float(draw_top),
            "draw_width": float(draw_width),
            "draw_height": float(draw_height),
            "min_x": float(min_x),
            "max_x": float(max_x),
            "min_y": float(min_y),
            "max_y": float(max_y),
            "margin_x_mm": float(margin_x_mm),
            "margin_y_mm": float(margin_y_mm),
            "scale": float(scale),
        }

    def _card_size_px(self, layout: dict[str, float] | None) -> tuple[int, int]:
        if layout is None:
            return 70, round(70 * (MAGIC_CARD_HEIGHT_MM / MAGIC_CARD_WIDTH_MM))
        width_px = max(32, round(MAGIC_CARD_WIDTH_MM * layout["scale"]))
        height_px = max(44, round(MAGIC_CARD_HEIGHT_MM * layout["scale"]))
        return width_px, height_px

    def _pile_center_to_screen(self, x_mm: float, y_mm: float, layout: dict[str, float]) -> tuple[float, float]:
        world_x = (x_mm - layout["min_x"]) + layout["margin_x_mm"]
        world_y = (y_mm - layout["min_y"]) + layout["margin_y_mm"]
        screen_x = layout["draw_left"] + (world_x * layout["scale"])
        screen_y = layout["draw_top"] + (world_y * layout["scale"])
        return screen_x, screen_y

    def _pile_card_rect(self, pile, layout: dict[str, float]) -> pygame.Rect:
        width_px, height_px = self._card_size_px(layout)
        ref_x_mm, ref_y_mm = self._pile_reference_xy(pile)
        screen_x, screen_y = self._pile_center_to_screen(ref_x_mm, ref_y_mm, layout)
        return pygame.Rect(
            int(screen_x - (width_px / 2)),
            int(screen_y - (height_px / 2)),
            width_px,
            height_px,
        )

    def _draw_unknown_card_preview(self, rect: pygame.Rect) -> None:
        pygame.draw.rect(self.window, (70, 70, 78), rect, border_radius=10)
        pygame.draw.rect(self.window, (150, 150, 158), rect, width=2, border_radius=10)
        question = self.header_font.render("?", True, (220, 220, 220))
        self.window.blit(question, (rect.centerx - (question.get_width() / 2), rect.centery - (question.get_height() / 2)))

    def _pile_badge_rect(self, pile, rect: pygame.Rect, display_numbers: dict[str, int]) -> pygame.Rect:
        pile_number = display_numbers.get(pile.pile_id.as_key(), 0)
        label = self.font.render(f"Pile {pile_number} {pile.role.value}", True, (245, 245, 245))
        badge_rect = pygame.Rect(0, 0, label.get_width() + 10, label.get_height() + 6)
        badge_rect.centerx = rect.centerx
        badge_rect.bottom = rect.top - PILE_BADGE_GAP_PX
        return badge_rect

    def _draw_pile_badge(self, pile, rect: pygame.Rect, display_numbers: dict[str, int]) -> None:
        pile_number = display_numbers.get(pile.pile_id.as_key(), 0)
        label = self.font.render(f"Pile {pile_number} {pile.role.value}", True, (245, 245, 245))
        badge_rect = self._pile_badge_rect(pile, rect, display_numbers)
        pygame.draw.rect(self.window, LABEL_BG, badge_rect, border_radius=7)
        pygame.draw.rect(self.window, (110, 116, 126), badge_rect, width=1, border_radius=7)
        self.window.blit(label, (badge_rect.left + 5, badge_rect.top + 3))

    def _draw_pile_summary_panel(
        self,
        piles,
        rank_lookup: dict[str, int],
        summary_rect: pygame.Rect,
        display_numbers: dict[str, int],
    ) -> None:
        self.window.blit(self.font.render("Pile summary", True, (220, 220, 220)), (summary_rect.left + 12, summary_rect.top + 10))
        if not piles:
            return
        row_height = max(68, (summary_rect.height - 40) // len(piles))
        for index, pile in enumerate(piles):
            top = summary_rect.top + 36 + (index * row_height)
            row_rect = pygame.Rect(summary_rect.left + 10, top, summary_rect.width - 20, row_height - 8)
            pygame.draw.rect(self.window, LABEL_BG, row_rect, border_radius=10)
            pygame.draw.rect(self.window, (94, 100, 110), row_rect, width=1, border_radius=10)
            top_id = pile.top_card_id() if pile.has_observed_top_card() else None
            top_name = self._top_label(pile)
            top_rank_text = self._top_rank_label(pile, top_id, rank_lookup)
            count_text = self._count_label(pile)
            pile_number = display_numbers.get(pile.pile_id.as_key(), index + 1)
            line1 = self.font.render(f"Pile {pile_number}  {pile.role.value}", True, (240, 240, 240))
            line2 = self.font.render(f"Count {count_text}   Rank {top_rank_text}", True, (210, 210, 210))
            line3 = self.font.render(f"Top {top_name[:24]}", True, (210, 210, 210))
            self.window.blit(line1, (row_rect.left + 10, row_rect.top + 8))
            self.window.blit(line2, (row_rect.left + 10, row_rect.top + 28))
            self.window.blit(line3, (row_rect.left + 10, row_rect.top + 48))

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
        layout: dict[str, float],
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

        z_factor = max(0.82, min(1.0, 1.0 - (z_mm / 220.0)))
        rect = self._held_card_rect(x_mm, y_mm, z_factor, layout)
        card_surface = pygame.transform.smoothscale(surface, rect.size)
        self.window.blit(card_surface, rect.topleft)

    def _draw_end_effector(
        self,
        x_mm: float,
        y_mm: float,
        layout: dict[str, float],
    ) -> None:
        screen_x, screen_y = self._pose_to_screen(x_mm, y_mm, layout)
        pose = self.orchestrator.world.snapshot.pose
        radius = self._end_effector_radius_px(layout)
        center = (int(screen_x), int(screen_y))
        fill_color = (220, 40, 40) if pose.vacuum_on else (255, 255, 255)
        border_color = (0, 0, 0) if pose.vacuum_on else (255, 255, 255)

        pygame.draw.circle(self.window, fill_color, center, radius)
        pygame.draw.circle(self.window, border_color, center, radius, width=2)

    def _held_card_rect(
        self,
        x_mm: float,
        y_mm: float,
        z_factor: float,
        layout: dict[str, float],
    ) -> pygame.Rect:
        screen_x, screen_y = self._pose_to_screen(x_mm, y_mm, layout)
        width_px, height_px = self._card_size_px(layout)
        w = max(20, int(width_px * z_factor))
        h = max(28, int(height_px * z_factor))
        return pygame.Rect(
            int(screen_x - (w / 2)),
            int(screen_y - (h / 2)),
            w,
            h,
        )

    def _camera_pose_mm(self, x_mm: float, y_mm: float) -> tuple[float, float]:
        return (
            x_mm + self.calibration.camera_offset_x_mm,
            y_mm + self.calibration.camera_offset_y_mm,
        )

    def _is_imaging_substate(self) -> bool:
        active_command = self.orchestrator.world.snapshot.run_state.active_command
        return active_command in {
            "CaptureDiscovery",
            "CaptureFrame",
            "CaptureVerification",
            "RecognizeTopCard",
        }

    def _draw_camera_reticle(
        self,
        x_mm: float,
        y_mm: float,
        layout: dict[str, float],
    ) -> None:
        camera_x_mm, camera_y_mm = self._camera_pose_mm(x_mm, y_mm)
        screen_x, screen_y = self._pose_to_screen(camera_x_mm, camera_y_mm, layout)
        center = (int(screen_x), int(screen_y))
        radius = max(6, self._end_effector_radius_px(layout) - 2)
        color = (90, 220, 255) if self._is_imaging_substate() else (120, 180, 210)
        pygame.draw.circle(self.window, color, center, radius, width=2)
        pygame.draw.line(self.window, color, (center[0] - radius - 4, center[1]), (center[0] + radius + 4, center[1]), width=1)
        pygame.draw.line(self.window, color, (center[0], center[1] - radius - 4), (center[0], center[1] + radius + 4), width=1)

    def _pose_to_screen(
        self,
        x_mm: float,
        y_mm: float,
        layout: dict[str, float],
    ) -> tuple[float, float]:
        if "min_x" not in layout:
            return (
                layout["board_left"] + (layout["board_width"] / 2),
                layout["board_top"] + (layout["board_height"] / 2),
            )
        return self._pile_center_to_screen(x_mm, y_mm, layout)
