import logging
from dataclasses import dataclass

from sorter.config.settings import AppSettings
from sorter.adapters.recognition.policy_recognizer import PolicyRecognizerAdapter
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
from sorter.application.orchestrator import Orchestrator
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
        recognition_min_confidence=settings.recognition_min_confidence,
        startup_scan_max_retries=settings.startup_scan_max_retries,
        verification_max_retries=settings.verification_max_retries,
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
            pile_manager_path=root / "pile_manager.py",
            image_piles_path=root / "image_piles.json",
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
    if backend == "fuzzy_enigma":
        root = settings.project_root or settings.scenario_fixture.parents[2]
        primary = FuzzyEnigmaRecognizerAdapter(
            project_root=root,
            config_path=settings.card_engine_config_path,
            mode=settings.card_engine_mode,
            auto_track_results=settings.card_engine_auto_track_results,
            prefer_visual_small_pool=settings.card_engine_prefer_visual_small_pool,
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
