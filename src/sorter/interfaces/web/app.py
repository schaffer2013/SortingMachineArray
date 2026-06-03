from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, UTC
from io import BytesIO
from pathlib import Path
import json
import sqlite3
import tempfile
import threading
import time
from typing import Any

from flask import Flask, Response, jsonify, render_template, request, send_file
from PIL import Image, ImageDraw

from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.models import PileState
from sorter.ports.camera import Frame


class WebRuntime:
    def __init__(
        self,
        orchestrator: Orchestrator,
        calibration: CalibrationProfile,
        slow_ms: int = 0,
        light_profiles_path: Path | None = None,
        calibration_path: Path | None = None,
    ):
        self.orchestrator = orchestrator
        self.calibration = calibration
        self.slow_ms = max(0, slow_ms)
        self.stop_event = threading.Event()
        self.run_thread: threading.Thread | None = None
        self.last_result: dict[str, Any] | None = None
        self.last_error: str | None = None
        self.last_manual_recognition: dict[str, Any] | None = None
        self.machine_initialized = False
        self.light_profiles_path = light_profiles_path
        self.calibration_path = calibration_path
        self.light_profiles = self._load_light_profiles()
        self.lock = threading.RLock()

    def start_run(self) -> dict[str, Any]:
        with self.lock:
            if self.run_thread and self.run_thread.is_alive():
                return {"ok": False, "message": "Run already active"}
            if not self.machine_initialized:
                return {"ok": False, "message": "Initialize machine before starting a run"}
            self.stop_event.clear()
            self.last_result = None
            self.last_error = None
            self.run_thread = threading.Thread(target=self._run_worker, daemon=True)
            self.run_thread.start()
            return {"ok": True, "message": "Run started"}

    def stop_run(self) -> None:
        self.stop_event.set()

    def _run_worker(self) -> None:
        try:
            result = self.orchestrator.run_once(
                self.calibration,
                should_stop=lambda: self.stop_event.is_set(),
                per_command_delay_s=self.slow_ms / 1000.0,
            )
            with self.lock:
                self.last_result = result
        except Exception as exc:  # pragma: no cover - surfaced to UI
            with self.lock:
                self.last_error = str(exc)

    def status(self) -> dict[str, Any]:
        snapshot = self.orchestrator.world.snapshot
        run_state = snapshot.run_state
        with self.lock:
            active = bool(self.run_thread and self.run_thread.is_alive())
            if active:
                lifecycle = "RUNNING"
            elif self.last_result:
                lifecycle = str(self.last_result.get("status", "DONE"))
            else:
                lifecycle = "IDLE"
            return {
                "lifecycle": lifecycle,
                "phase": run_state.phase,
                "active_command": run_state.active_command,
                "pose": asdict(snapshot.pose),
                "metrics": asdict(run_state.metrics),
                "vacuum_on": bool(self.orchestrator.vacuum.is_on()),
                "lights_status": getattr(self.orchestrator.lights, "status", getattr(self.orchestrator.lights, "last_status", "unknown")),
                "lights_profile": getattr(self.orchestrator.lights, "last_profile", None),
                "lights_rgb": list(getattr(self.orchestrator.lights, "last_rgb", ())),
                "last_result": self.last_result,
                "last_error": self.last_error,
                "last_recognition": getattr(self.orchestrator, "last_recognition", None),
                "last_manual_recognition": self.last_manual_recognition,
                "machine_initialized": self.machine_initialized,
                "calibration": self.calibration_payload(),
            }

    def calibration_payload(self) -> dict[str, Any]:
        return self.calibration.to_json_dict()

    def update_calibration(self, payload: dict[str, Any]) -> dict[str, Any]:
        allowed_fields = {
            "camera_offset_x_mm",
            "camera_offset_y_mm",
            "camera_offset_z_mm",
            "min_xy_travel_z_mm",
            "safe_z_mm",
            "pick_z_mm",
            "place_z_mm",
        }
        updates = {key: payload[key] for key in allowed_fields if key in payload}
        if not updates:
            raise ValueError("No supported calibration fields provided")
        with self.lock:
            self.calibration = self.calibration.with_updates(**updates)
            if self.calibration_path is not None:
                self.calibration.save(self.calibration_path)
            return {"ok": True, "calibration": self.calibration_payload()}

    def snapshot(self) -> dict[str, Any]:
        snapshot = self.orchestrator.world.snapshot
        piles = sorted(
            snapshot.piles.values(),
            key=lambda pile: (pile.y_mm, pile.x_mm, pile.pile_id.as_key()),
        )
        return {
            "piles": [self._pile_payload(index, pile) for index, pile in enumerate(piles, start=1)],
            "pose": asdict(snapshot.pose),
            "run_state": {
                "phase": snapshot.run_state.phase,
                "active_command": snapshot.run_state.active_command,
                "metrics": asdict(snapshot.run_state.metrics),
            },
        }

    def _pile_payload(self, index: int, pile: PileState) -> dict[str, Any]:
        return {
            "number": index,
            "key": pile.pile_id.as_key(),
            "role": pile.role.value,
            "capacity": pile.capacity,
            "count": pile.num_cards() if pile.has_known_count() else None,
            "known_count": pile.has_known_count(),
            "observation_state": pile.observation.state.value,
            "top_card_name": pile.observation.top_card_name,
            "confidence": pile.observation.confidence,
            "x_mm": pile.x_mm,
            "y_mm": pile.y_mm,
            "image_available": bool(self.orchestrator.world.top_card_image_path(pile.pile_id)),
        }

    def initialize_machine(self) -> dict[str, Any]:
        with self.lock:
            travel_z_mm = self.orchestrator.initialize_machine(self.calibration)
            self.machine_initialized = True
            return {
                "ok": True,
                "message": f"Machine initialized and homed; vacuum Z at {travel_z_mm:.2f} mm travel clearance",
            }

    def control(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "initialize":
            return self.initialize_machine()
        if action == "home":
            self.orchestrator.motion.home_axes()
            snapshot = self.orchestrator.world.snapshot
            snapshot.pose.x_mm = 0.0
            snapshot.pose.y_mm = 0.0
            snapshot.pose.z_mm = 0.0
            self.machine_initialized = False
            return {"ok": True, "message": "Axes homed"}
        if action == "wait_idle":
            self.orchestrator.motion.wait_until_idle()
            return {"ok": True, "message": "Motion idle"}
        if action == "move_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_vac_xy_when_safe(self.calibration, x_mm, y_mm)
            return {"ok": True, "message": f"Moved vacuum XY to ({x_mm:.2f}, {y_mm:.2f})"}
        if action == "move_camera_xy":
            x_mm = float(payload["x_mm"])
            y_mm = float(payload["y_mm"])
            self.orchestrator.move_camera_to_vacuum_xy_when_safe(self.calibration, x_mm, y_mm)
            target_x_mm, target_y_mm = self.calibration.camera_baseline_xy_for_vacuum_target(x_mm, y_mm)
            return {
                "ok": True,
                "message": (
                    f"Moved camera over ({x_mm:.2f}, {y_mm:.2f}) "
                    f"using vacuum baseline ({target_x_mm:.2f}, {target_y_mm:.2f})"
                ),
            }
        if action == "move_z":
            z_mm = float(payload["z_mm"])
            self.orchestrator.move_vac_z(z_mm)
            return {"ok": True, "message": f"Moved vacuum Z to {z_mm:.2f}"}
        if action == "vacuum_on":
            self.orchestrator.vacuum.on()
            return {"ok": True, "message": "Vacuum enabled"}
        if action == "vacuum_off":
            self.orchestrator.vacuum.off()
            return {"ok": True, "message": "Vacuum disabled"}
        if action == "lights":
            status = str(payload.get("status", "idle"))
            self.orchestrator.lights.set_status(status)
            return {"ok": True, "message": f"Lights set to {status}"}
        if action == "light_profile":
            profile_name = str(payload["name"])
            profile = self.light_profiles.get(profile_name)
            if profile is None:
                raise ValueError(f"Unknown light profile: {profile_name}")
            self._apply_light_profile(profile_name, profile)
            return {"ok": True, "message": f"Applied light profile {profile_name}"}
        raise ValueError(f"Unsupported control action: {action}")

    def _load_light_profiles(self) -> dict[str, dict[str, int]]:
        default_profiles = {
            name: {"red": rgb[0], "green": rgb[1], "blue": rgb[2]}
            for name, rgb in getattr(self.orchestrator.lights, "STATUS_RGB", {}).items()
        }
        if not default_profiles:
            default_profiles = {
                "idle": {"red": 0, "green": 0, "blue": 16},
                "running": {"red": 0, "green": 16, "blue": 0},
                "warning": {"red": 16, "green": 8, "blue": 0},
                "fault": {"red": 16, "green": 0, "blue": 0},
            }
        if self.light_profiles_path is None or not self.light_profiles_path.exists():
            return default_profiles
        with self.light_profiles_path.open("r", encoding="utf-8") as handle:
            raw = json.load(handle)
        loaded = {
            str(item["name"]): {
                "red": int(item["red"]),
                "green": int(item["green"]),
                "blue": int(item["blue"]),
            }
            for item in raw.get("profiles", [])
        }
        return loaded or default_profiles

    def _save_light_profiles(self) -> None:
        if self.light_profiles_path is None:
            return
        self.light_profiles_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "profiles": [
                {"name": name, **channels}
                for name, channels in sorted(self.light_profiles.items())
            ]
        }
        with self.light_profiles_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
            handle.write("\n")

    def list_light_profiles(self) -> list[dict[str, int | str]]:
        return [{"name": name, **channels} for name, channels in sorted(self.light_profiles.items())]

    def create_light_profile(self, name: str, red: int, green: int, blue: int) -> dict[str, Any]:
        normalized_name = name.strip().lower()
        if not normalized_name:
            raise ValueError("Profile name is required")
        channels = {
            "red": _clamp_channel(red),
            "green": _clamp_channel(green),
            "blue": _clamp_channel(blue),
        }
        self.light_profiles[normalized_name] = channels
        self._save_light_profiles()
        return {"name": normalized_name, **channels}

    def _apply_light_profile(self, name: str, channels: dict[str, int]) -> None:
        setter = getattr(self.orchestrator.lights, "set_rgb", None)
        if callable(setter):
            setter(channels["red"], channels["green"], channels["blue"], profile_name=name)
            return
        self.orchestrator.lights.set_status(name)

    def validate_card(self, query: str) -> dict[str, Any]:
        normalized = query.strip().lower()
        cards = self.orchestrator.catalog.all_cards()
        exact = next((card for card in cards if card.name.lower() == normalized), None)
        suggestions = [
            card.name
            for card in cards
            if normalized and normalized in card.name.lower()
        ][:8]
        return {
            "valid": exact is not None,
            "match": asdict(exact) if exact else None,
            "suggestions": suggestions,
        }

    def recognize_uploaded_image(self, image_path: Path, request_payload: dict[str, Any]) -> dict[str, Any]:
        frame = Frame(
            frame_id=f"web-{int(time.time() * 1000)}",
            path=str(image_path),
            pile_id=None,
            metadata={"recognition_request": request_payload},
            captured_at_utc=datetime.now(UTC).isoformat(),
            camera_id="web_upload",
            source_mode="manual_web",
        )
        result = self.orchestrator.recognizer.recognize_top_card(frame)
        payload = asdict(result)
        self.last_manual_recognition = payload
        self.orchestrator.last_recognition = {
            "backend": result.backend,
            "requested_mode": result.requested_mode,
            "effective_mode": result.effective_mode,
            "fallback_used": result.fallback_used,
            "card_name": result.card_name,
            "confidence": result.confidence,
            "failure_code": result.failure_code,
            "review_reason": result.review_reason,
        }
        return payload

    def latest_camera_image(self) -> Image.Image:
        frame = None
        try:
            frame = self.orchestrator.camera.capture_frame()
        except Exception:
            frame = None

        if frame and frame.path:
            image_path = Path(frame.path)
            if image_path.exists():
                return Image.open(image_path).convert("RGB")

        snapshot = self.orchestrator.world.snapshot
        current_pile = next(
            (
                pile
                for pile in sorted(snapshot.piles.values(), key=lambda p: (p.y_mm, p.x_mm, p.pile_id.as_key()))
                if self.orchestrator.world.top_card_image_path(pile.pile_id)
            ),
            None,
        )
        if current_pile is not None:
            path = self.orchestrator.world.top_card_image_path(current_pile.pile_id)
            if path and Path(path).exists():
                return Image.open(path).convert("RGB")
        return self._placeholder_camera_image()

    def _placeholder_camera_image(self) -> Image.Image:
        image = Image.new("RGB", (960, 540), "#111827")
        draw = ImageDraw.Draw(image)
        draw.rectangle((28, 28, 932, 512), outline="#334155", width=3)
        draw.text((54, 72), "Camera preview unavailable", fill="#f8fafc")
        draw.text((54, 112), "The current adapter did not return a frame path.", fill="#cbd5e1")
        draw.text((54, 152), "In sim mode this falls back to card imagery; hardware streaming needs camera capture wiring.", fill="#94a3b8")
        return image

    def recent_runs(self, limit: int = 12) -> list[dict[str, Any]]:
        db_path = getattr(self.orchestrator.run_store, "db_path", None)
        if not db_path:
            return []
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, mode, scenario_name, status, started_at, finished_at, result_metrics_json
                FROM runs
                ORDER BY started_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "run_id": row["run_id"],
                "mode": row["mode"],
                "scenario_name": row["scenario_name"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "metrics": json.loads(row["result_metrics_json"]) if row["result_metrics_json"] else None,
            }
            for row in rows
        ]

    def capabilities(self) -> list[dict[str, str]]:
        return [
            {"name": "Automated sorting run", "status": "ready", "detail": "End-to-end in sim via the orchestrator."},
            {"name": "Live machine status", "status": "ready", "detail": "Phase, active command, pose, pile state, metrics."},
            {"name": "Motion control", "status": "ready", "detail": "Home, XY, Z, and idle-wait controls via MotionPort."},
            {"name": "Vacuum and lights", "status": "ready", "detail": "Manual I/O commands via VacuumPort and LightsPort."},
            {"name": "Card recognition", "status": "ready", "detail": "Manual image recognition plus review/fallback metadata."},
            {"name": "Card validation", "status": "ready", "detail": "Catalog-backed exact validation with suggestions."},
            {"name": "Run history", "status": "ready", "detail": "SQLite-backed recent run summaries and metrics."},
            {"name": "Camera preview", "status": "partial", "detail": "Web stream endpoint exists; current Pi adapter still needs real frame capture wiring."},
            {"name": "Operator review workflow", "status": "partial", "detail": "Recognition evidence exists; explicit correction/confirmation is a next hardware milestone."},
            {"name": "Hardware runtime", "status": "partial", "detail": "Adapters exist, but the repo currently documents sim as the supported end-to-end runtime."},
        ]


def create_web_app(
    orchestrator: Orchestrator,
    calibration: CalibrationProfile,
    slow_ms: int = 0,
    light_profiles_path: Path | None = None,
    calibration_path: Path | None = None,
) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    runtime = WebRuntime(
        orchestrator,
        calibration,
        slow_ms=slow_ms,
        light_profiles_path=light_profiles_path,
        calibration_path=calibration_path,
    )
    app.config["runtime"] = runtime

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/machine")
    def machine():
        return render_template("machine.html")

    @app.get("/recognition")
    def recognition():
        return render_template("recognition.html")

    @app.get("/runs")
    def runs():
        return render_template("runs.html")

    @app.get("/about")
    def about():
        return render_template("about.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(runtime.status())

    @app.get("/api/snapshot")
    def api_snapshot():
        return jsonify(runtime.snapshot())

    @app.get("/api/calibration")
    def api_calibration():
        return jsonify({"calibration": runtime.calibration_payload()})

    @app.post("/api/calibration")
    def api_update_calibration():
        try:
            return jsonify(runtime.update_calibration(request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.post("/api/run/start")
    def api_start():
        return jsonify(runtime.start_run())

    @app.post("/api/run/stop")
    def api_stop():
        runtime.stop_run()
        return jsonify({"ok": True, "message": "Stop requested"})

    @app.post("/api/control/<action>")
    def api_control(action: str):
        try:
            return jsonify(runtime.control(action, request.get_json(silent=True) or {}))
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/card/validate")
    def api_validate_card():
        return jsonify(runtime.validate_card(request.args.get("q", "")))

    @app.post("/api/recognition/run")
    def api_recognition_run():
        upload = request.files.get("image")
        if upload is None or not upload.filename:
            return jsonify({"ok": False, "message": "Image upload required"}), 400
        suffix = Path(upload.filename).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            temp_path = Path(handle.name)
        upload.save(temp_path)
        payload = {
            "mode": request.form.get("mode", "greenfield"),
            "backend": request.form.get("backend") or None,
            "prefer_visual_small_pool": request.form.get("prefer_visual_small_pool") == "true",
            "use_tracked_pool": request.form.get("use_tracked_pool") == "true",
            "track_result": request.form.get("track_result") == "true",
        }
        expected_name = request.form.get("expected_name", "").strip()
        expected_set = request.form.get("expected_set", "").strip()
        expected_collector = request.form.get("expected_collector", "").strip()
        if expected_name or expected_set or expected_collector:
            payload["expected_card"] = {
                "name": expected_name or None,
                "set_code": expected_set or None,
                "collector_number": expected_collector or None,
            }
        try:
            result = runtime.recognize_uploaded_image(temp_path, payload)
            return jsonify({"ok": True, "result": result})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 500

    @app.get("/api/runs")
    def api_runs():
        return jsonify({"runs": runtime.recent_runs()})

    @app.get("/api/capabilities")
    def api_capabilities():
        return jsonify({"capabilities": runtime.capabilities()})

    @app.get("/api/light-profiles")
    def api_light_profiles():
        return jsonify({"profiles": runtime.list_light_profiles()})

    @app.post("/api/light-profiles")
    def api_create_light_profile():
        payload = request.get_json(silent=True) or {}
        try:
            profile = runtime.create_light_profile(
                str(payload.get("name", "")),
                int(payload.get("red", 0)),
                int(payload.get("green", 0)),
                int(payload.get("blue", 0)),
            )
            return jsonify({"ok": True, "profile": profile})
        except Exception as exc:
            return jsonify({"ok": False, "message": str(exc)}), 400

    @app.get("/api/camera/frame.jpg")
    def camera_frame():
        image = runtime.latest_camera_image()
        buffer = BytesIO()
        image.save(buffer, format="JPEG", quality=88)
        buffer.seek(0)
        return send_file(buffer, mimetype="image/jpeg")

    @app.get("/camera/stream")
    def camera_stream():
        def generate():
            while True:
                image = runtime.latest_camera_image()
                buffer = BytesIO()
                image.save(buffer, format="JPEG", quality=82)
                payload = buffer.getvalue()
                yield (
                    b"--frame\r\n"
                    b"Content-Type: image/jpeg\r\n"
                    + f"Content-Length: {len(payload)}\r\n\r\n".encode("ascii")
                    + payload
                    + b"\r\n"
                )
                time.sleep(0.5)

        return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")

    return app


def _clamp_channel(value: int) -> int:
    return max(0, min(255, int(value)))
