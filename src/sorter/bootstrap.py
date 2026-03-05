from sorter.config.settings import AppSettings
from sorter.adapters.sim.sim_world import SimWorld
from sorter.adapters.sim.sim_motion import SimMotionAdapter
from sorter.adapters.sim.sim_camera import SimCameraAdapter
from sorter.adapters.sim.sim_vacuum import SimVacuumAdapter
from sorter.adapters.sim.sim_lights import SimLightsAdapter
from sorter.adapters.sim.sim_recognizer import SimRecognizerAdapter
from sorter.adapters.persistence.file_card_catalog import FileCardCatalog
from sorter.adapters.persistence.sim_image_sync import sync_simulated_images
from sorter.adapters.persistence.sqlite_run_store import SQLiteRunStore
from sorter.application.orchestrator import Orchestrator


def build_sim_orchestrator(settings: AppSettings) -> Orchestrator:
    if settings.auto_image_sync:
        root = settings.project_root or settings.scenario_fixture.parents[2]
        summary = sync_simulated_images(
            project_root=root,
            fixture_path=settings.scenario_fixture,
            image_dir=root / "SimulatedCardImages",
            log_path=root / "data" / "logs" / "simulated_cards.log",
            pile_manager_path=root / "pile_manager.py",
            image_piles_path=root / "image_piles.json",
            auto_fetch=True,
        )
        if summary.missing_after > 0:
            raise RuntimeError(
                f"Image sync incomplete: {summary.missing_after} card images still missing. See {summary.log_path}"
            )

    world = SimWorld.from_fixture(settings.scenario_fixture, settings.random_seed)
    catalog = FileCardCatalog(settings.card_catalog_path)
    run_store = SQLiteRunStore(settings.sqlite_path)
    return Orchestrator(
        motion=SimMotionAdapter(world),
        camera=SimCameraAdapter(world),
        vacuum=SimVacuumAdapter(world),
        lights=SimLightsAdapter(world),
        recognizer=SimRecognizerAdapter(world, catalog),
        catalog=catalog,
        run_store=run_store,
        world=world,
    )
