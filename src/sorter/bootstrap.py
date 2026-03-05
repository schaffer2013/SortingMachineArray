from sorter.config.settings import AppSettings
from sorter.adapters.sim.sim_world import SimWorld
from sorter.adapters.sim.sim_motion import SimMotionAdapter
from sorter.adapters.sim.sim_camera import SimCameraAdapter
from sorter.adapters.sim.sim_vacuum import SimVacuumAdapter
from sorter.adapters.sim.sim_lights import SimLightsAdapter
from sorter.adapters.sim.sim_recognizer import SimRecognizerAdapter
from sorter.adapters.persistence.file_card_catalog import FileCardCatalog
from sorter.adapters.persistence.sqlite_run_store import SQLiteRunStore
from sorter.application.orchestrator import Orchestrator


def build_sim_orchestrator(settings: AppSettings) -> Orchestrator:
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
