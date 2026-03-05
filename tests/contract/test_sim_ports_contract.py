from sorter.adapters.sim.sim_world import SimWorld
from sorter.adapters.sim.sim_motion import SimMotionAdapter
from sorter.adapters.sim.sim_camera import SimCameraAdapter
from sorter.adapters.sim.sim_vacuum import SimVacuumAdapter
from sorter.adapters.sim.sim_lights import SimLightsAdapter
from pathlib import Path


def test_sim_adapters_expose_port_methods():
    root = Path(__file__).resolve().parents[2]
    world = SimWorld.from_fixture(root / "scenarios/fixtures/small_stack.json")

    motion = SimMotionAdapter(world)
    camera = SimCameraAdapter(world)
    vacuum = SimVacuumAdapter(world)
    lights = SimLightsAdapter(world)

    motion.home_axes()
    motion.move_xy(10, 20)
    motion.move_z(5)
    assert motion.get_pose().x_mm == 10

    pile = next(iter(world.snapshot.piles.values())).pile_id
    frame = camera.capture_top_card(pile)
    assert frame.pile_id == pile

    vacuum.on()
    assert vacuum.is_on() is True
    vacuum.off()
    assert vacuum.is_on() is False

    lights.set_status("running")
    assert lights.status == "running"
