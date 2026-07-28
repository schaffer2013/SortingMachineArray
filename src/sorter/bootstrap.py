import logging
from dataclasses import dataclass
from pathlib import Path

from sorter.config.settings import AppSettings
from sorter.adapters.recognition.policy_recognizer import PolicyRecognizerAdapter
from sorter.adapters.hardware.gpio_vacuum import GpioVacuumAdapter
from sorter.adapters.hardware.marlin_motion import MarlinMotionAdapter
from sorter.adapters.hardware.marlin_transport import MarlinSerialTransport
from sorter.adapters.hardware.neopixel_lights import NeoPixelLightsAdapter
from sorter.adapters.hardware.picamera2_camera import PiCamera2Adapter
from sorter.adapters.sim.sim_world import SimWorld
from sorter.adapters.sim.sim_motion import SimMotionAdapter
from sorter.adapters.sim.sim_camera import SimCameraAdapter
from sorter.adapters.sim.sim_vacuum import SimVacuumAdapter
from sorter.adapters.sim.sim_lights import SimLightsAdapter
from sorter.adapters.sim.sim_recognizer import SimRecognizerAdapter
from sorter.adapters.sim.sim_faulting_recognizer import SimFaultingRecognizerAdapter
from sorter.adapters.recognition.fuzzy_enigma_recognizer import FuzzyEnigmaRecognizerAdapter
from sorter.adapters.persistence.file_card_catalog import FileCardCatalog
from sorter.adapters.persistence.sim_card_list_loader import expand_and_shuffle_instances, load_sim_card_list
from sorter.adapters.persistence.sim_fixture_builder import build_runtime_fixture
from sorter.adapters.persistence.sim_image_sync import sync_simulated_images
from sorter.adapters.persistence.sqlite_run_store import SQLiteRunStore
from sorter.adapters.integrations.collection_service import HttpCollectionServiceAdapter, NullCollectionServiceAdapter
from sorter.application.orchestrator import Orchestrator
from sorter.config.calibration import CalibrationProfile
from sorter.domain.enums import PileRole
from sorter.domain.models import CardMeta, MachinePose, MachineSnapshot, PileId, PileState, RunState
from sorter.domain.ranking_service import RankingService
from sorter.domain.sort_policy_config import load_sort_policy_file


logger = logging.getLogger(__name__)


@dataclass
class SimRuntimeContext:
    world: SimWorld
    catalog: FileCardCatalog
    motion: SimMotionAdapter
    camera: SimCameraAdapter
    vacuum: SimVacuumAdapter
    lights: SimLightsAdapter
    recognizer: object
    run_store: SQLiteRunStore


@dataclass
class HardwareRuntimeContext:
    world: "HardwareWorld"
    catalog: FileCardCatalog
    motion: MarlinMotionAdapter
    camera: PiCamera2Adapter
    vacuum: GpioVacuumAdapter
    lights: NeoPixelLightsAdapter
    recognizer: object
    run_store: SQLiteRunStore
    transport: MarlinSerialTransport


@dataclass
class HardwareWorld:
    scenario_name: str
    seed: int
    snapshot: MachineSnapshot
    coords: dict[str, tuple[float, float]]
    card_by_id: dict[str, CardMeta]
    compiled_ranking: object | None = None
    held_card_id: str | None = None
    last_frame_by_pile: dict[str, str] | None = None

    @staticmethod
    def from_calibration(calibration: CalibrationProfile) -> "HardwareWorld":
        piles: dict[str, PileState] = {}
        coords: dict[str, tuple[float, float]] = {}
        for index, (x_mm, y_mm) in enumerate(calibration.pile_positions_mm):
            pile_id = PileId(x_index=index, y_index=0)
            role = _default_hardware_pile_role(index)
            pile = PileState(
                pile_id=pile_id,
                role=role,
                capacity=85,
                x_mm=float(x_mm),
                y_mm=float(y_mm),
                card_stack=[],
                discovered=(role != PileRole.FEEDER),
                stack_count_known=(role != PileRole.FEEDER),
            )
            piles[pile_id.as_key()] = pile
            coords[pile_id.as_key()] = (float(x_mm), float(y_mm))
        return HardwareWorld(
            scenario_name="hardware",
            seed=0,
            snapshot=MachineSnapshot(piles=piles, pose=MachinePose(), run_state=RunState(phase="IDLE")),
            coords=coords,
            card_by_id={},
            last_frame_by_pile={},
        )

    def rank_lookup(self) -> dict[str, int]:
        if self.compiled_ranking is None:
            return {}
        return self.compiled_ranking.card_id_to_rank

    def set_compiled_ranking(self, compiled_ranking) -> None:
        self.compiled_ranking = compiled_ranking

    def explain_card(self, card_id_or_name: str) -> dict | None:
        if self.compiled_ranking is None:
            return None
        explanation = self.compiled_ranking.explain_card(card_id_or_name)
        if explanation is None:
            return None
        return {
            "card_id": explanation.card_id,
            "card_name": explanation.card_name,
            "factual_fields": explanation.factual_fields,
            "derived_fields": explanation.derived_fields,
            "sort_key": explanation.sort_key,
            "ordinal_rank": explanation.ordinal_rank,
        }

    def pick_from(self, pile_id: PileId) -> None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None or not pile.card_stack:
            raise RuntimeError("Cannot pick from an unknown or empty hardware pile")
        self.held_card_id = pile.card_stack.pop()
        pile.mark_unknown(source="hardware_pick")
        self.snapshot.pose.holding_card_id = self.held_card_id

    def place_to(self, pile_id: PileId) -> None:
        if self.held_card_id is None:
            raise RuntimeError("No held card to place")
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            raise RuntimeError("Destination pile missing")
        pile.card_stack.append(self.held_card_id)
        card_name = self.card_by_id.get(self.held_card_id, CardMeta(name=self.held_card_id)).name
        pile.mark_top_card_seen(card_name=card_name, confidence=1.0, source="hardware_placement", count_known=True)
        self.held_card_id = None
        self.snapshot.pose.holding_card_id = None

    def apply_recognition_observation(
        self,
        pile_id: PileId,
        *,
        recognized_name: str | None,
        confidence: float,
        frame_id: str | None = None,
        observed_at_utc: str | None = None,
        source: str = "recognizer",
    ) -> None:
        pile = self.snapshot.get_pile(pile_id)
        if pile is None:
            return
        if frame_id is not None and self.last_frame_by_pile is not None:
            self.last_frame_by_pile[pile_id.as_key()] = frame_id
        if recognized_name is None:
            pile.card_stack.clear()
            pile.mark_empty_confirmed(
                confidence=confidence,
                source=source,
                frame_id=frame_id,
                observed_at_utc=observed_at_utc,
            )
            return
        card_id = recognized_name
        self.card_by_id.setdefault(card_id, CardMeta(name=recognized_name))
        pile.card_stack = [card_id]
        pile.mark_top_card_seen(
            card_name=recognized_name,
            confidence=confidence,
            source=source,
            frame_id=frame_id,
            observed_at_utc=observed_at_utc,
            count_known=False,
        )

    def top_card_image_path(self, pile_id: PileId) -> str | None:
        return None


def build_sim_orchestrator(settings: AppSettings) -> Orchestrator:
    context = build_sim_runtime_context(settings)
    return Orchestrator(
        motion=context.motion,
        camera=context.camera,
        vacuum=context.vacuum,
        lights=context.lights,
        recognizer=context.recognizer,
        catalog=context.catalog,
        run_store=context.run_store,
        world=context.world,
        collection_service=_build_collection_service(settings),
        recognition_min_confidence=settings.recognition_min_confidence,
        startup_scan_max_retries=settings.startup_scan_max_retries,
        verification_max_retries=settings.verification_max_retries,
    )


def build_hardware_orchestrator(settings: AppSettings, calibration: CalibrationProfile) -> Orchestrator:
    context = build_hardware_runtime_context(settings, calibration)
    orchestrator = Orchestrator(
        motion=context.motion,
        camera=context.camera,
        vacuum=context.vacuum,
        lights=context.lights,
        recognizer=context.recognizer,
        catalog=context.catalog,
        run_store=context.run_store,
        world=context.world,
        collection_service=_build_collection_service(settings),
        recognition_min_confidence=settings.recognition_min_confidence,
        startup_scan_max_retries=settings.startup_scan_max_retries,
        verification_max_retries=settings.verification_max_retries,
    )
    setattr(orchestrator, "hardware_runtime", True)
    setattr(orchestrator, "hardware_transport", context.transport)
    return orchestrator


def _build_collection_service(settings: AppSettings):
    if not settings.collection_service_url:
        return NullCollectionServiceAdapter()
    return HttpCollectionServiceAdapter(
        base_url=settings.collection_service_url,
        collection_id=settings.collection_id,
        api_key=settings.collection_api_key,
        timeout_seconds=settings.collection_timeout_seconds,
    )


def build_hardware_runtime_context(settings: AppSettings, calibration: CalibrationProfile) -> HardwareRuntimeContext:
    root = settings.project_root or Path.cwd()
    catalog = FileCardCatalog(settings.card_catalog_path)
    world = HardwareWorld.from_calibration(calibration)
    policy_config = load_sort_policy_file(settings.sort_policy_path)
    catalog_cards = {card.name: card for card in catalog.all_cards()}
    world.set_compiled_ranking(
        RankingService(
            policy_config,
            allow_external_enrichment=settings.allow_external_card_enrichment,
        ).compile(catalog_cards)
    )
    transport = MarlinSerialTransport(
        serial_port=_env_text("SORTER_MARLIN_SERIAL_PORT", "/dev/ttyACM0"),
        baud_rate=int(_env_text("SORTER_MARLIN_BAUD_RATE", "115200")),
        timeout_seconds=float(_env_text("SORTER_MARLIN_TIMEOUT_SECONDS", "60")),
    )
    motion = MarlinMotionAdapter(
        transport=transport,
        z_home_mm=calibration.z_home_mm,
        c_home_mm=calibration.c_home_mm,
    )
    camera = PiCamera2Adapter(capture_dir=root / _env_text("SORTER_CAMERA_CAPTURE_DIR", "data/vision/captures"))
    vacuum = GpioVacuumAdapter(
        relay_pin=int(_env_text("SORTER_VACUUM_RELAY_PIN", "17")),
        active_high=_env_text("SORTER_VACUUM_ACTIVE_HIGH", "1").lower() in {"1", "true", "yes", "on"},
    )
    lights = NeoPixelLightsAdapter(transport=transport)
    recognizer = _build_hardware_recognizer(settings, catalog)
    run_store = SQLiteRunStore(settings.sqlite_path)
    return HardwareRuntimeContext(
        world=world,
        catalog=catalog,
        motion=motion,
        camera=camera,
        vacuum=vacuum,
        lights=lights,
        recognizer=recognizer,
        run_store=run_store,
        transport=transport,
    )


def build_sim_runtime_context(settings: AppSettings) -> SimRuntimeContext:
    root = settings.project_root or settings.scenario_fixture.parents[2]
    catalog = FileCardCatalog(settings.card_catalog_path)
    runtime_fixture_path = _resolve_runtime_fixture(settings, catalog)

    if settings.auto_image_sync:
        summary = sync_simulated_images(
            project_root=root,
            fixture_path=runtime_fixture_path,
            image_dir=root / "SimulatedCardImages",
            log_path=root / "data" / "logs" / "simulated_cards.log",
            sim_card_list_path=settings.sim_card_list_path,
            auto_fetch=settings.sim_image_auto_fetch,
        )
        if summary.missing_after > 0:
            logger.warning(
                "Image sync incomplete: %s card images still missing. Continuing without them. See %s",
                summary.missing_after,
                summary.log_path,
            )

    world = SimWorld.from_fixture(runtime_fixture_path, settings.random_seed)
    for card_id, card_meta in list(world.card_by_id.items()):
        catalog_meta = catalog.get_card_meta(card_meta.name)
        if catalog_meta is not None:
            world.card_by_id[card_id] = catalog_meta

    policy_config = load_sort_policy_file(settings.sort_policy_path)
    compiled_ranking = RankingService(
        policy_config,
        allow_external_enrichment=settings.allow_external_card_enrichment,
    ).compile(world.card_by_id)
    world.set_compiled_ranking(compiled_ranking)

    motion = SimMotionAdapter(world)
    camera = SimCameraAdapter(world)
    vacuum = SimVacuumAdapter(world)
    lights = SimLightsAdapter(world)
    recognizer = _build_recognizer(settings, world, catalog)
    run_store = SQLiteRunStore(settings.sqlite_path)
    return SimRuntimeContext(
        world=world,
        catalog=catalog,
        motion=motion,
        camera=camera,
        vacuum=vacuum,
        lights=lights,
        recognizer=recognizer,
        run_store=run_store,
    )


def _build_recognizer(settings: AppSettings, world: SimWorld, catalog: FileCardCatalog):
    backend = settings.recognizer_backend.strip().lower()
    recognition_faults = getattr(world, "recognition_faults", ())
    if backend == "sim_truth":
        recognizer = SimRecognizerAdapter(world, catalog)
        if recognition_faults:
            return SimFaultingRecognizerAdapter(recognizer, recognition_faults)
        return recognizer
    if backend in {"fuzzy_enigma", "moss_machine"}:
        root = settings.project_root or settings.scenario_fixture.parents[2]
        primary = FuzzyEnigmaRecognizerAdapter(
            project_root=root,
            config_path=settings.card_engine_config_path,
            mode=settings.card_engine_mode,
            auto_track_results=settings.card_engine_auto_track_results,
            prefer_visual_small_pool=settings.card_engine_prefer_visual_small_pool,
            card_engine_backend=backend,
        )
        fallback = SimRecognizerAdapter(world, catalog) if settings.fuzzy_enigma_sim_truth_fallback else None
        recognizer = PolicyRecognizerAdapter(
            primary,
            min_confidence=settings.recognition_min_confidence,
            fallback=fallback,
        )
        if recognition_faults:
            return SimFaultingRecognizerAdapter(recognizer, recognition_faults)
        return recognizer
    raise ValueError(f"Unsupported recognizer backend: {settings.recognizer_backend}")


def _build_hardware_recognizer(settings: AppSettings, catalog: FileCardCatalog):
    backend = settings.recognizer_backend.strip().lower()
    if backend == "sim_truth":
        raise ValueError("Hardware runtime cannot use SORTER_RECOGNIZER_BACKEND=sim_truth")
    if backend in {"fuzzy_enigma", "moss_machine"}:
        root = settings.project_root or Path.cwd()
        primary = FuzzyEnigmaRecognizerAdapter(
            project_root=root,
            config_path=settings.card_engine_config_path,
            mode=settings.card_engine_mode,
            auto_track_results=settings.card_engine_auto_track_results,
            prefer_visual_small_pool=settings.card_engine_prefer_visual_small_pool,
            card_engine_backend=backend,
        )
        return PolicyRecognizerAdapter(
            primary,
            min_confidence=settings.recognition_min_confidence,
            fallback=None,
        )
    raise ValueError(f"Unsupported hardware recognizer backend: {settings.recognizer_backend}")


def _default_hardware_pile_role(index: int) -> PileRole:
    if index == 0:
        return PileRole.FEEDER
    if index == 1:
        return PileRole.COLLECTION
    return PileRole.SORTING


def _env_text(key: str, default: str) -> str:
    import os

    value = os.getenv(key)
    if value is None or not value.strip():
        return default
    return value.strip()


def _resolve_runtime_fixture(settings: AppSettings, catalog: FileCardCatalog):
    if settings.sim_card_list_path is None:
        return settings.scenario_fixture
    if settings.generated_runtime_fixture_path is None:
        return settings.scenario_fixture

    suffix_map = {
        card.name: (_instance_identity_suffix(card))
        for card in catalog.all_cards()
    }
    config = load_sim_card_list(settings.sim_card_list_path)
    expanded_instances = expand_and_shuffle_instances(config, id_suffix_by_name=suffix_map)
    shuffled_cards = [entry.card_id for entry in expanded_instances]
    card_set_by_instance_id = {
        entry.card_id: entry.set_id
        for entry in expanded_instances
        if entry.set_id
    }
    return build_runtime_fixture(
        base_fixture_path=settings.scenario_fixture,
        shuffled_card_instance_ids=shuffled_cards,
        output_fixture_path=settings.generated_runtime_fixture_path,
        card_set_by_instance_id=card_set_by_instance_id,
    )


def _instance_identity_suffix(card) -> str:
    if card.scryfall_id:
        return card.scryfall_id
    if card.oracle_id:
        return card.oracle_id
    return _fallback_identity_suffix(card.name)


def _fallback_identity_suffix(name: str) -> str:
    return "".join(ch for ch in name.strip().lower() if ch.isalnum()) or "unknown"
