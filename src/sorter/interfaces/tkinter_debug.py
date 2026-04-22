from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import threading
import time
import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.enums import PileObservationState
from sorter.ports.camera import Frame

MAGIC_CARD_WIDTH_MM = 63.0
DIME_DIAMETER_MM = 17.91
MAGIC_CARD_HEIGHT_MM = 88.0
DASHBOARD_BG = "#181b21"
BOARD_BG = "#22262e"
BOARD_GRID = "#3a404a"
LABEL_BG = "#1f232b"
SUMMARY_BG = "#262b33"
SUMMARY_BORDER = "#58606b"
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


class _RecognitionProgressSink:
    def __init__(self, ui: "TkDebugUI") -> None:
        self._ui = ui

    def update(self, message: str) -> None:
        self._ui._record_recognition_progress(message)


class TkDebugUI:
    def __init__(self, orchestrator: Orchestrator, calibration: CalibrationProfile, slow_ms: int = 0):
        self.orchestrator = orchestrator
        self.calibration = calibration
        self.base_slow_ms = max(0, slow_ms)
        self.slow_enabled = self.base_slow_ms > 0
        self.stop_event = threading.Event()
        self.run_thread: threading.Thread | None = None
        self.last_result: dict | None = None
        self.last_error: str | None = None

        self.pose_anim = PoseAnimationSegment()
        pose = self.orchestrator.world.snapshot.pose
        self.last_pose_target = (pose.x_mm, pose.y_mm, pose.z_mm)

        self._raw_image_cache: dict[str, Image.Image] = {}
        self._scaled_image_cache: dict[tuple[str, int, int], ImageTk.PhotoImage] = {}
        self._canvas_image_refs: list[ImageTk.PhotoImage] = []
        self._alarm_events: list[str] = []
        self._recognition_progress_messages: list[str] = []

        self.root = tk.Tk()
        self.root.title("Sorter Control Console")
        self.root.geometry("1280x860")
        self.root.minsize(1080, 720)
        self.root.configure(bg=DASHBOARD_BG)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        self.state_var = tk.StringVar(value="State: IDLE")
        self.substate_var = tk.StringVar(value="Substate: -")
        self.recognizer_var = tk.StringVar(value="Recognizer: -")
        self.run_var = tk.StringVar(value="Run: -")
        self.moves_var = tk.StringVar(value="Moves: -")
        self.error_var = tk.StringVar(value="Error: -")

        self._build_top_controls()
        self._build_pages()

    def _build_top_controls(self) -> None:
        top = ttk.Frame(self.root, padding=(10, 10, 10, 6))
        top.pack(side=tk.TOP, fill=tk.X)

        ttk.Button(top, text="Start Run", command=self._start_run).grid(row=0, column=0, padx=4)
        ttk.Button(top, text="Stop Run", command=self._stop_run).grid(row=0, column=1, padx=4)

        self.slow_var = tk.BooleanVar(value=self.slow_enabled)
        ttk.Checkbutton(top, text=f"Slow ({self.base_slow_ms}ms)", variable=self.slow_var, command=self._toggle_slow).grid(
            row=0,
            column=2,
            padx=8,
        )

        ttk.Label(top, textvariable=self.state_var).grid(row=0, column=3, padx=12, sticky=tk.W)
        ttk.Label(top, textvariable=self.substate_var).grid(row=0, column=4, padx=12, sticky=tk.W)
        ttk.Label(top, textvariable=self.recognizer_var).grid(row=0, column=5, padx=12, sticky=tk.W)

        ttk.Label(top, textvariable=self.run_var).grid(row=1, column=0, columnspan=2, padx=4, sticky=tk.W)
        ttk.Label(top, textvariable=self.moves_var).grid(row=1, column=2, columnspan=2, padx=4, sticky=tk.W)
        ttk.Label(top, textvariable=self.error_var, foreground="#d16b6b").grid(
            row=1,
            column=4,
            columnspan=2,
            padx=4,
            sticky=tk.W,
        )

    def _build_pages(self) -> None:
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        self.main_page = ttk.Frame(self.notebook)
        self.hardware_page = ttk.Frame(self.notebook)
        self.recognition_page = ttk.Frame(self.notebook)
        self.alarm_page = ttk.Frame(self.notebook)

        self.notebook.add(self.main_page, text="Main View")
        self.notebook.add(self.hardware_page, text="Hardware")
        self.notebook.add(self.recognition_page, text="Recognition")
        self.notebook.add(self.alarm_page, text="Alarms")

        self._build_main_page()
        self._build_hardware_page()
        self._build_recognition_page()
        self._build_alarm_page()

    def _build_main_page(self) -> None:
        self.main_page.columnconfigure(0, weight=3)
        self.main_page.columnconfigure(1, weight=2)
        self.main_page.rowconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self.main_page,
            background=DASHBOARD_BG,
            highlightthickness=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=(8, 6), pady=8)

        summary_box = ttk.LabelFrame(self.main_page, text="Pile Summary", padding=8)
        summary_box.grid(row=0, column=1, sticky="nsew", padx=(6, 8), pady=8)
        summary_box.rowconfigure(0, weight=1)
        summary_box.columnconfigure(0, weight=1)

        self.summary_text = ScrolledText(summary_box, wrap=tk.WORD, height=20)
        self.summary_text.grid(row=0, column=0, sticky="nsew")
        self.summary_text.configure(state=tk.DISABLED)

    def _build_hardware_page(self) -> None:
        panel = ttk.Frame(self.hardware_page, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)

        motion_box = ttk.LabelFrame(panel, text="Motion", padding=8)
        motion_box.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(0, weight=1)

        ttk.Button(motion_box, text="Home Axes", command=self._hw_home_axes).grid(row=0, column=0, padx=4, pady=4, sticky=tk.W)
        ttk.Button(motion_box, text="Wait Until Idle", command=self._hw_wait_idle).grid(row=0, column=1, padx=4, pady=4, sticky=tk.W)

        ttk.Label(motion_box, text="X (mm)").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Label(motion_box, text="Y (mm)").grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
        self.hw_x_var = tk.StringVar(value="100")
        self.hw_y_var = tk.StringVar(value="100")
        ttk.Entry(motion_box, textvariable=self.hw_x_var, width=12).grid(row=2, column=0, sticky=tk.W, padx=4)
        ttk.Entry(motion_box, textvariable=self.hw_y_var, width=12).grid(row=2, column=1, sticky=tk.W, padx=4)
        ttk.Button(motion_box, text="Move XY", command=self._hw_move_xy).grid(row=2, column=2, padx=4, pady=4, sticky=tk.W)

        ttk.Label(motion_box, text="Z (mm)").grid(row=3, column=0, sticky=tk.W, padx=4, pady=4)
        self.hw_z_var = tk.StringVar(value="5")
        ttk.Entry(motion_box, textvariable=self.hw_z_var, width=12).grid(row=4, column=0, sticky=tk.W, padx=4)
        ttk.Button(motion_box, text="Move Z", command=self._hw_move_z).grid(row=4, column=1, padx=4, pady=4, sticky=tk.W)

        vacuum_box = ttk.LabelFrame(panel, text="Vacuum and Lights", padding=8)
        vacuum_box.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        ttk.Button(vacuum_box, text="Vacuum On", command=self._hw_vacuum_on).grid(row=0, column=0, padx=4, pady=4, sticky=tk.W)
        ttk.Button(vacuum_box, text="Vacuum Off", command=self._hw_vacuum_off).grid(row=0, column=1, padx=4, pady=4, sticky=tk.W)

        ttk.Label(vacuum_box, text="Light Status").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        self.light_status_var = tk.StringVar(value="idle")
        ttk.Entry(vacuum_box, textvariable=self.light_status_var, width=16).grid(row=1, column=1, padx=4, pady=4, sticky=tk.W)
        ttk.Button(vacuum_box, text="Set Lights", command=self._hw_set_lights).grid(row=1, column=2, padx=4, pady=4, sticky=tk.W)

    def _build_recognition_page(self) -> None:
        panel = ttk.Frame(self.recognition_page, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)

        panel.columnconfigure(0, weight=1)
        panel.columnconfigure(1, weight=1)
        panel.rowconfigure(2, weight=1)

        image_box = ttk.LabelFrame(panel, text="Single Card Recognition", padding=8)
        image_box.grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=6)
        image_box.columnconfigure(1, weight=1)

        self.recognition_image_var = tk.StringVar(value="")
        ttk.Label(image_box, text="Image").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(image_box, textvariable=self.recognition_image_var).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(image_box, text="Browse", command=self._pick_recognition_image).grid(row=0, column=2, padx=4, pady=4)

        self.engine_var = tk.StringVar(value="moss_machine")
        self.mode_var = tk.StringVar(value="greenfield")
        ttk.Label(image_box, text="Engine").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(
            image_box,
            textvariable=self.engine_var,
            values=("moss_machine", "fuzzy_enigma", "sim_truth"),
            state="normal",
            width=16,
        ).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Button(image_box, text="Apply Engine", command=self._apply_engine_backend).grid(row=1, column=2, padx=4, pady=4)

        ttk.Label(image_box, text="Mode").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Combobox(
            image_box,
            textvariable=self.mode_var,
            values=("greenfield", "tracked_pool", "expected_card"),
            state="normal",
            width=16,
        ).grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)

        expected_box = ttk.LabelFrame(panel, text="Expected Card Hints", padding=8)
        expected_box.grid(row=1, column=0, sticky="ew", padx=6, pady=6)

        self.expected_name_var = tk.StringVar(value="")
        self.expected_set_var = tk.StringVar(value="")
        self.expected_collector_var = tk.StringVar(value="")
        ttk.Label(expected_box, text="Card Name").grid(row=0, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(expected_box, textvariable=self.expected_name_var, width=28).grid(row=0, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Label(expected_box, text="Set Code").grid(row=1, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(expected_box, textvariable=self.expected_set_var, width=12).grid(row=1, column=1, sticky=tk.W, padx=4, pady=4)
        ttk.Label(expected_box, text="Collector #").grid(row=2, column=0, sticky=tk.W, padx=4, pady=4)
        ttk.Entry(expected_box, textvariable=self.expected_collector_var, width=12).grid(row=2, column=1, sticky=tk.W, padx=4, pady=4)

        option_box = ttk.LabelFrame(panel, text="Recognition Options", padding=8)
        option_box.grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        self.prefer_small_pool_var = tk.BooleanVar(value=False)
        self.use_tracked_pool_var = tk.BooleanVar(value=False)
        self.track_result_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(option_box, text="Prefer visual small pool", variable=self.prefer_small_pool_var).grid(
            row=0,
            column=0,
            sticky=tk.W,
            padx=4,
            pady=4,
        )
        ttk.Checkbutton(option_box, text="Use tracked pool", variable=self.use_tracked_pool_var).grid(
            row=1,
            column=0,
            sticky=tk.W,
            padx=4,
            pady=4,
        )
        ttk.Checkbutton(option_box, text="Track result", variable=self.track_result_var).grid(
            row=2,
            column=0,
            sticky=tk.W,
            padx=4,
            pady=4,
        )
        ttk.Button(option_box, text="Recognize Image", command=self._run_single_recognition).grid(
            row=3,
            column=0,
            sticky=tk.W,
            padx=4,
            pady=8,
        )

        output_box = ttk.LabelFrame(panel, text="Recognition Output", padding=8)
        output_box.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        output_box.rowconfigure(0, weight=1)
        output_box.columnconfigure(0, weight=1)

        self.recognition_output = ScrolledText(output_box, wrap=tk.WORD, height=14)
        self.recognition_output.grid(row=0, column=0, sticky="nsew")

    def _build_alarm_page(self) -> None:
        panel = ttk.Frame(self.alarm_page, padding=12)
        panel.pack(fill=tk.BOTH, expand=True)
        panel.rowconfigure(1, weight=1)
        panel.columnconfigure(0, weight=1)

        ttk.Label(
            panel,
            text="Alarm Feed (errors, review states, hardware command faults)",
        ).grid(row=0, column=0, sticky=tk.W, pady=(0, 8))

        self.alarm_output = ScrolledText(panel, wrap=tk.WORD)
        self.alarm_output.grid(row=1, column=0, sticky="nsew")

        ttk.Button(panel, text="Clear Alarms", command=self._clear_alarms).grid(row=2, column=0, sticky=tk.W, pady=8)

    def run(self) -> None:
        self._refresh_loop()
        self.root.mainloop()

    def _on_close(self) -> None:
        self._stop_run()
        if self.run_thread and self.run_thread.is_alive():
            self.run_thread.join(timeout=1.0)
        self.root.destroy()

    def _toggle_slow(self) -> None:
        self.slow_enabled = bool(self.slow_var.get())

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
            if isinstance(self.last_result, dict) and self.last_result.get("status") == "REVIEW_REQUIRED":
                self._add_alarm("WARN", "Review required after run")
        except Exception as exc:
            self.last_error = str(exc)
            self._add_alarm("ERROR", f"Run failed: {exc}")

    def _refresh_loop(self) -> None:
        self._refresh_status_labels()
        self._draw_snapshot()
        self.root.after(33, self._refresh_loop)

    def _refresh_status_labels(self) -> None:
        state = "IDLE"
        if self.run_thread and self.run_thread.is_alive():
            state = "RUNNING"
        elif self.last_result:
            state = str(self.last_result.get("status", "DONE"))

        self.state_var.set(f"State: {state}")
        self.substate_var.set(f"Substate: {self._substate_label()}")

        recognizer_lines = self._recognizer_status_lines()
        self.recognizer_var.set(recognizer_lines[0] if recognizer_lines else "Recognizer: -")

        if self.last_result:
            self.run_var.set(f"Run: {self.last_result.get('run_id', '-')}")
            self.moves_var.set(f"Moves: {self.last_result.get('seq', '-')}")
        else:
            self.run_var.set("Run: -")
            self.moves_var.set("Moves: -")

        if self.last_error:
            self.error_var.set(f"Error: {self.last_error}")
        else:
            self.error_var.set("Error: -")

    def _draw_snapshot(self) -> None:
        snapshot = self.orchestrator.world.snapshot
        self.canvas.delete("all")
        self._canvas_image_refs.clear()

        if not snapshot.piles:
            self._set_summary_text("No piles in snapshot.")
            return

        try:
            rank_lookup = self.orchestrator.world.discovered_rank_lookup()
        except Exception:
            rank_lookup = {}

        self._update_animation_from_pose()
        anim_x_mm, anim_y_mm, anim_z_mm = self._animated_pose_xyz()

        canvas_w = max(600, self.canvas.winfo_width())
        canvas_h = max(420, self.canvas.winfo_height())

        board_left = 20
        board_top = 20
        board_w = int(canvas_w * 0.72)
        board_h = max(360, canvas_h - 40)

        summary_left = board_left + board_w + 14
        summary_top = board_top
        summary_w = max(200, canvas_w - summary_left - 20)
        summary_h = board_h

        self.canvas.create_rectangle(
            board_left,
            board_top,
            board_left + board_w,
            board_top + board_h,
            fill=BOARD_BG,
            outline=BOARD_GRID,
            width=2,
        )
        self.canvas.create_rectangle(
            summary_left,
            summary_top,
            summary_left + summary_w,
            summary_top + summary_h,
            fill=SUMMARY_BG,
            outline=SUMMARY_BORDER,
            width=1,
        )

        layout = self._board_layout(board_left, board_top, board_w, board_h)

        ordered_piles = sorted(
            snapshot.piles.values(),
            key=lambda pile: (*self._pile_reference_xy(pile), pile.pile_id.as_key()),
        )
        display_numbers = self._pile_display_numbers(ordered_piles)

        for pile in ordered_piles:
            x1, y1, x2, y2 = self._pile_card_rect(pile, layout)
            self.canvas.create_rectangle(x1, y1, x2, y2, fill="#5b6474", outline="#e6e6e6", width=2)

            image_path = self.orchestrator.world.top_card_image_path(pile.pile_id)
            if pile.has_observed_top_card() and image_path:
                tk_img = self._get_card_image(image_path, x2 - x1, y2 - y1)
                if tk_img is not None:
                    self.canvas.create_image((x1 + x2) // 2, (y1 + y2) // 2, image=tk_img)
                    self._canvas_image_refs.append(tk_img)
                else:
                    self._draw_unknown_card_preview(x1, y1, x2, y2)
            else:
                self._draw_unknown_card_preview(x1, y1, x2, y2)

            self.canvas.create_rectangle(x1, y1, x2, y2, outline="#ededed", width=2)
            self._draw_pile_badge(pile, x1, y1, x2, display_numbers)

        self._draw_held_card(anim_x_mm, anim_y_mm, anim_z_mm, layout)
        self._draw_end_effector(anim_x_mm, anim_y_mm, layout)
        self._draw_camera_reticle(anim_x_mm, anim_y_mm, layout)
        self._draw_pile_summary_text(ordered_piles, rank_lookup, display_numbers)

    def _set_summary_text(self, content: str) -> None:
        self.summary_text.configure(state=tk.NORMAL)
        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert(tk.END, content)
        self.summary_text.configure(state=tk.DISABLED)

    def _draw_pile_summary_text(self, piles, rank_lookup: dict[str, int], display_numbers: dict[str, int]) -> None:
        lines: list[str] = []
        for index, pile in enumerate(piles):
            top_id = pile.top_card_id() if pile.has_observed_top_card() else None
            top_name = self._top_label(pile)
            top_rank_text = self._top_rank_label(pile, top_id, rank_lookup)
            count_text = self._count_label(pile)
            pile_number = display_numbers.get(pile.pile_id.as_key(), index + 1)
            lines.append(f"Pile {pile_number} ({pile.role.value})")
            lines.append(f"  Count: {count_text}")
            lines.append(f"  Rank: {top_rank_text}")
            lines.append(f"  Top: {top_name}")
            lines.append("")
        self._set_summary_text("\n".join(lines).strip())

    def _get_card_image(self, image_path: str, width: int, height: int) -> ImageTk.PhotoImage | None:
        key = (image_path, width, height)
        cached = self._scaled_image_cache.get(key)
        if cached is not None:
            return cached

        raw = self._raw_image_cache.get(image_path)
        if raw is None:
            try:
                raw = Image.open(image_path).convert("RGB")
                self._raw_image_cache[image_path] = raw
            except OSError:
                return None

        try:
            resized = raw.resize((max(1, width), max(1, height)), Image.Resampling.LANCZOS)
        except Exception:
            return None

        tk_img = ImageTk.PhotoImage(resized)
        self._scaled_image_cache[key] = tk_img
        return tk_img

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

    def _recognizer_status_lines(self) -> list[str]:
        recognizer = getattr(self.orchestrator, "recognizer", None)
        configured = self._configured_recognizer_status(recognizer)
        lines = [f"Recognizer: {configured['sorter_backend']}"]
        if configured["card_engine_backend"] is not None:
            engine_line = (
                f"Card engine: requested={configured['card_engine_backend']} "
                f"mode={configured['card_engine_mode']} "
                f"fallback={'on' if configured['card_engine_fallback'] else 'off'}"
            )
            lines.append(engine_line)
        if configured["policy_fallback_backend"] is not None:
            lines.append(f"Policy fallback: {configured['policy_fallback_backend']}")

        last_recognition = getattr(self.orchestrator, "last_recognition", None)
        if isinstance(last_recognition, dict) and last_recognition:
            backend = last_recognition.get("backend") or "unknown"
            mode = last_recognition.get("effective_mode") or last_recognition.get("requested_mode") or "-"
            suffix = " via fallback" if last_recognition.get("fallback_used") else ""
            lines.append(f"Last scan: backend={backend} mode={mode}{suffix}")
        else:
            lines.append("Last scan: none yet")
        return lines

    def _configured_recognizer_status(self, recognizer) -> dict[str, object]:
        primary = getattr(recognizer, "primary", recognizer)
        fallback = getattr(recognizer, "fallback", None)
        sorter_backend = getattr(primary, "sorter_backend", None)
        if not isinstance(sorter_backend, str) or not sorter_backend:
            sorter_backend = type(primary).__name__
        card_engine_backend = getattr(primary, "card_engine_requested_backend", None)
        if not isinstance(card_engine_backend, str) or not card_engine_backend:
            card_engine_backend = None
        card_engine_mode = getattr(primary, "card_engine_mode", None)
        if not isinstance(card_engine_mode, str) or not card_engine_mode:
            card_engine_mode = None
        return {
            "sorter_backend": sorter_backend,
            "card_engine_backend": card_engine_backend,
            "card_engine_mode": card_engine_mode,
            "card_engine_fallback": bool(getattr(primary, "card_engine_backend_fallback", False)),
            "policy_fallback_backend": getattr(fallback, "sorter_backend", None),
        }

    def _end_effector_radius_px(self, layout: dict[str, float] | None = None) -> int:
        width_px = self._card_size_px(layout)[0] if layout is not None else 70
        diameter_px = width_px * (DIME_DIAMETER_MM / MAGIC_CARD_WIDTH_MM)
        return max(4, round(diameter_px / 2))

    def _pile_reference_xy(self, pile) -> tuple[float, float]:
        pile_slot_number = self._pile_slot_number(pile)
        if pile_slot_number is None:
            return (pile.x_mm, pile.y_mm)
        index = pile_slot_number - 1
        if index < 0 or index >= len(self.calibration.pile_positions_mm):
            return (pile.x_mm, pile.y_mm)
        return self.calibration.pile_positions_mm[index]

    def _pile_display_numbers(self, piles) -> dict[str, int]:
        return {pile.pile_id.as_key(): index + 1 for index, pile in enumerate(piles)}

    def _pile_slot_number(self, target_pile) -> int | None:
        snapshot = getattr(self.orchestrator.world, "snapshot", None)
        if snapshot is None:
            return None
        ordered_piles = sorted(
            snapshot.piles.values(),
            key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()),
        )
        for index, pile in enumerate(ordered_piles, start=1):
            if pile.pile_id.as_key() == target_pile.pile_id.as_key():
                return index
        return None

    def _board_layout(self, board_left: int, board_top: int, board_w: int, board_h: int) -> dict[str, float]:
        coords = [self._pile_reference_xy(pile) for pile in self.orchestrator.world.snapshot.piles.values()]
        if not coords:
            return {
                "board_left": float(board_left),
                "board_top": float(board_top),
                "board_width": float(board_w),
                "board_height": float(board_h),
                "draw_left": float(board_left + 20),
                "draw_top": float(board_top + 30),
                "draw_width": float(board_w - 40),
                "draw_height": float(board_h - 60),
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

        draw_left = board_left + 20
        draw_top = board_top + BOARD_TOP_PADDING_PX
        draw_width = board_w - 40
        draw_height = board_h - (BOARD_TOP_PADDING_PX + 22)
        scale = min(draw_width / world_width_mm, draw_height / world_height_mm)

        return {
            "board_left": float(board_left),
            "board_top": float(board_top),
            "board_width": float(board_w),
            "board_height": float(board_h),
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

    def _pile_card_rect(self, pile, layout: dict[str, float]) -> tuple[int, int, int, int]:
        width_px, height_px = self._card_size_px(layout)
        ref_x_mm, ref_y_mm = self._pile_reference_xy(pile)
        screen_x, screen_y = self._pile_center_to_screen(ref_x_mm, ref_y_mm, layout)
        return (
            int(screen_x - (width_px / 2)),
            int(screen_y - (height_px / 2)),
            int(screen_x + (width_px / 2)),
            int(screen_y + (height_px / 2)),
        )

    def _draw_unknown_card_preview(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.canvas.create_rectangle(x1, y1, x2, y2, fill="#454c58", outline="#9098a3", width=2)
        self.canvas.create_text((x1 + x2) // 2, (y1 + y2) // 2, text="?", fill="#e0e0e0", font=("Segoe UI", 18, "bold"))

    def _draw_pile_badge(self, pile, x1: int, y1: int, x2: int, display_numbers: dict[str, int]) -> None:
        pile_number = display_numbers.get(pile.pile_id.as_key(), 0)
        label_text = f"Pile {pile_number} {pile.role.value}"
        center_x = (x1 + x2) // 2
        badge_y = y1 - PILE_BADGE_GAP_PX
        self.canvas.create_text(center_x, badge_y, text=label_text, fill="#f0f0f0", font=("Segoe UI", 10, "bold"))

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

    def _draw_held_card(self, x_mm: float, y_mm: float, z_mm: float, layout: dict[str, float]) -> None:
        pose = self.orchestrator.world.snapshot.pose
        held_card_id = pose.holding_card_id or self.pose_anim.held_card_id
        if not pose.vacuum_on or held_card_id is None:
            return

        image_path = self.orchestrator.world.image_by_card_id.get(held_card_id)
        if image_path is None:
            return

        z_factor = max(0.82, min(1.0, 1.0 - (z_mm / 220.0)))
        x1, y1, x2, y2 = self._held_card_rect(x_mm, y_mm, z_factor, layout)
        tk_img = self._get_card_image(image_path, x2 - x1, y2 - y1)
        if tk_img is None:
            return
        self.canvas.create_image((x1 + x2) // 2, (y1 + y2) // 2, image=tk_img)
        self._canvas_image_refs.append(tk_img)

    def _draw_end_effector(self, x_mm: float, y_mm: float, layout: dict[str, float]) -> None:
        screen_x, screen_y = self._pose_to_screen(x_mm, y_mm, layout)
        pose = self.orchestrator.world.snapshot.pose
        radius = self._end_effector_radius_px(layout)
        fill_color = "#cf3131" if pose.vacuum_on else "#ffffff"
        self.canvas.create_oval(
            int(screen_x - radius),
            int(screen_y - radius),
            int(screen_x + radius),
            int(screen_y + radius),
            fill=fill_color,
            outline="#101010",
            width=2,
        )

    def _held_card_rect(self, x_mm: float, y_mm: float, z_factor: float, layout: dict[str, float]) -> tuple[int, int, int, int]:
        screen_x, screen_y = self._pose_to_screen(x_mm, y_mm, layout)
        width_px, height_px = self._card_size_px(layout)
        w = max(20, int(width_px * z_factor))
        h = max(28, int(height_px * z_factor))
        return (
            int(screen_x - (w / 2)),
            int(screen_y - (h / 2)),
            int(screen_x + (w / 2)),
            int(screen_y + (h / 2)),
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

    def _draw_camera_reticle(self, x_mm: float, y_mm: float, layout: dict[str, float]) -> None:
        camera_x_mm, camera_y_mm = self._camera_pose_mm(x_mm, y_mm)
        screen_x, screen_y = self._pose_to_screen(camera_x_mm, camera_y_mm, layout)
        radius = max(6, self._end_effector_radius_px(layout) - 2)
        color = "#6ad4ff" if self._is_imaging_substate() else "#7ab7d2"

        self.canvas.create_oval(
            int(screen_x - radius),
            int(screen_y - radius),
            int(screen_x + radius),
            int(screen_y + radius),
            outline=color,
            width=2,
        )
        self.canvas.create_line(
            int(screen_x - radius - 4),
            int(screen_y),
            int(screen_x + radius + 4),
            int(screen_y),
            fill=color,
            width=1,
        )
        self.canvas.create_line(
            int(screen_x),
            int(screen_y - radius - 4),
            int(screen_x),
            int(screen_y + radius + 4),
            fill=color,
            width=1,
        )

    def _pose_to_screen(self, x_mm: float, y_mm: float, layout: dict[str, float]) -> tuple[float, float]:
        if "min_x" not in layout:
            return (
                layout["board_left"] + (layout["board_width"] / 2),
                layout["board_top"] + (layout["board_height"] / 2),
            )
        return self._pile_center_to_screen(x_mm, y_mm, layout)

    def _hw_home_axes(self) -> None:
        self._hardware_call("Home axes", self.orchestrator.motion.home_axes)

    def _hw_wait_idle(self) -> None:
        self._hardware_call("Wait until idle", self.orchestrator.motion.wait_until_idle)

    def _hw_move_xy(self) -> None:
        try:
            x_mm = float(self.hw_x_var.get())
            y_mm = float(self.hw_y_var.get())
        except ValueError:
            self._add_alarm("ERROR", "Invalid X or Y value")
            return
        self._hardware_call(f"Move XY to ({x_mm:.2f}, {y_mm:.2f})", lambda: self.orchestrator.motion.move_xy(x_mm, y_mm))

    def _hw_move_z(self) -> None:
        try:
            z_mm = float(self.hw_z_var.get())
        except ValueError:
            self._add_alarm("ERROR", "Invalid Z value")
            return
        self._hardware_call(f"Move Z to {z_mm:.2f}", lambda: self.orchestrator.motion.move_z(z_mm))

    def _hw_vacuum_on(self) -> None:
        self._hardware_call("Vacuum ON", self.orchestrator.vacuum.on)

    def _hw_vacuum_off(self) -> None:
        self._hardware_call("Vacuum OFF", self.orchestrator.vacuum.off)

    def _hw_set_lights(self) -> None:
        status = self.light_status_var.get().strip() or "idle"
        self._hardware_call(f"Lights status {status}", lambda: self.orchestrator.lights.set_status(status))

    def _hardware_call(self, label: str, fn) -> None:
        try:
            fn()
            self._add_alarm("INFO", f"Hardware: {label}")
        except Exception as exc:
            self._add_alarm("ERROR", f"Hardware failed ({label}): {exc}")

    def _pick_recognition_image(self) -> None:
        selected = filedialog.askopenfilename(
            title="Select card image",
            filetypes=[("Image Files", "*.png *.jpg *.jpeg *.webp *.bmp"), ("All Files", "*.*")],
        )
        if selected:
            self.recognition_image_var.set(selected)

    def _apply_engine_backend(self) -> None:
        backend = self.engine_var.get().strip().lower()
        if not backend:
            self._add_alarm("ERROR", "Engine backend cannot be empty")
            return

        recognizer = getattr(self.orchestrator, "recognizer", None)
        primary = getattr(recognizer, "primary", recognizer)
        changed = False

        engine_obj = getattr(primary, "_recognizer", None)
        config = getattr(engine_obj, "config", None)
        if config is not None and hasattr(config, "recognition_backend"):
            setattr(config, "recognition_backend", backend)
            changed = True

        if hasattr(primary, "sorter_backend"):
            setattr(primary, "sorter_backend", backend)
            changed = True

        if hasattr(primary, "card_engine_requested_backend"):
            setattr(primary, "card_engine_requested_backend", backend)
            changed = True

        if changed:
            self._add_alarm("INFO", f"Recognition backend set to {backend}")
        else:
            self._add_alarm("WARN", f"Backend switch not supported by active recognizer ({type(primary).__name__})")

    def _run_single_recognition(self) -> None:
        image_path = self.recognition_image_var.get().strip()
        self._recognition_progress_messages = []
        if not image_path:
            self._set_recognition_output("Choose an image first.")
            return

        image_file = Path(image_path)
        if not image_file.exists():
            self._set_recognition_output(f"Image path does not exist: {image_path}")
            return

        request = {
            "mode": self.mode_var.get().strip() or "greenfield",
            "prefer_visual_small_pool": bool(self.prefer_small_pool_var.get()),
            "use_tracked_pool": bool(self.use_tracked_pool_var.get()),
            "track_result": bool(self.track_result_var.get()),
            "backend": self.engine_var.get().strip().lower() or None,
            "progress_callback": _RecognitionProgressSink(self),
        }

        expected_name = self.expected_name_var.get().strip()
        expected_set = self.expected_set_var.get().strip().lower()
        expected_collector = self.expected_collector_var.get().strip()
        if expected_name or expected_set or expected_collector:
            request["expected_card"] = {
                "name": expected_name or None,
                "set_code": expected_set or None,
                "collector_number": expected_collector or None,
            }

        frame = Frame(
            frame_id=f"manual-{int(time.time())}",
            path=str(image_file),
            pile_id=None,
            metadata={"recognition_request": request},
            source_mode="manual_ui",
        )

        recognizer = getattr(self.orchestrator, "recognizer", None)
        if recognizer is None:
            self._set_recognition_output("No recognizer attached to orchestrator.")
            return

        try:
            result = recognizer.recognize_top_card(frame)
        except Exception as exc:
            lines = [f"Recognition failed: {exc}"]
            if self._recognition_progress_messages:
                lines.extend(["", "Progress:"])
                lines.extend(self._recognition_progress_messages)
            self._set_recognition_output("\n".join(lines))
            self._add_alarm("ERROR", f"Recognition failed: {exc}")
            return

        self.orchestrator.last_recognition = {
            "backend": result.backend,
            "requested_mode": result.requested_mode,
            "effective_mode": result.effective_mode,
            "fallback_used": result.fallback_used,
        }

        lines: list[str] = []
        if self._recognition_progress_messages:
            lines.extend(["Progress:"])
            lines.extend(self._recognition_progress_messages)
            lines.append("")

        lines.extend([
            f"Name: {result.card_name}",
            f"Confidence: {result.confidence:.4f}",
            f"Backend: {result.backend}",
            f"Requested mode: {result.requested_mode}",
            f"Effective mode: {result.effective_mode}",
            f"Needs review: {result.needs_review}",
            f"Review reason: {result.review_reason}",
            f"Failure code: {result.failure_code}",
            "",
            "Alternatives:",
        ])
        if result.alternatives:
            for candidate in result.alternatives:
                lines.append(
                    f"  - {candidate.get('name')} score={candidate.get('score')} set={candidate.get('set_code')}"
                )
        else:
            lines.append("  (none)")

        self._set_recognition_output("\n".join(lines))
        self._add_alarm("INFO", "Single image recognition executed")

    def _record_recognition_progress(self, message: str) -> None:
        if not message:
            return
        self._recognition_progress_messages.append(message)
        self._set_recognition_output("Progress:\n" + "\n".join(self._recognition_progress_messages))
        self.root.update_idletasks()

    def _set_recognition_output(self, content: str) -> None:
        self.recognition_output.delete("1.0", tk.END)
        self.recognition_output.insert(tk.END, content)

    def _add_alarm(self, level: str, message: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        line = f"[{timestamp}] [{level}] {message}"
        self._alarm_events.append(line)
        self.alarm_output.insert(tk.END, line + "\n")
        self.alarm_output.see(tk.END)

    def _clear_alarms(self) -> None:
        self._alarm_events.clear()
        self.alarm_output.delete("1.0", tk.END)
