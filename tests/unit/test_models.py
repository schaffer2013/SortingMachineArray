import math

from sorter.domain.enums import PileRole
from sorter.domain.models import PileId, PileState


def test_pile_state_distance_from_uses_xy_mm_coordinates():
    left = PileState(pile_id=PileId(0, 0), role=PileRole.FEEDER, capacity=10, x_mm=0.0, y_mm=0.0)
    right = PileState(pile_id=PileId(1, 0), role=PileRole.SORTING, capacity=10, x_mm=3.0, y_mm=4.0)

    assert math.isclose(left.distance_from(right), 5.0)
    assert math.isclose(right.distance_from(left), 5.0)
