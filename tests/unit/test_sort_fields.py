from sorter.domain.models import CardMeta
from sorter.domain.sort_fields import primary_bucket, type_bucket


def test_primary_bucket_basic_land_before_land_logic():
    assert primary_bucket(CardMeta(name="Plains", is_land=True, is_basic_land=True)) == "basic_land"
    assert primary_bucket(CardMeta(name="Dual", is_land=True, is_basic_land=False)) == "nonbasic_land"


def test_primary_bucket_maps_colors_and_multicolor_and_colorless():
    assert primary_bucket(CardMeta(name="WhiteCard", colors=["w"])) == "white"
    assert primary_bucket(CardMeta(name="BlueCard", colors=["u"])) == "blue"
    assert primary_bucket(CardMeta(name="GreenCard", colors=["g"])) == "green"
    assert primary_bucket(CardMeta(name="MultiCard", colors=["g", "u"])) == "multicolor"
    assert primary_bucket(CardMeta(name="Colorless", colors=[])) == "colorless"


def test_type_bucket_prefers_land_and_known_types():
    assert type_bucket(CardMeta(name="Forest", is_land=True, is_basic_land=True)) == "basic_land"
    assert type_bucket(CardMeta(name="Triome", is_land=True, is_basic_land=False)) == "nonbasic_land"
    assert type_bucket(CardMeta(name="Bear", card_types=["creature"])) == "creature"
    assert type_bucket(CardMeta(name="Bolt", card_types=["instant"])) == "instant"
    assert type_bucket(CardMeta(name="Odd", card_types=["contraption"])) == "other"
