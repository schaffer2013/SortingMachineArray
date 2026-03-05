from sorter.domain.models import CardMeta, CardInstance
from sorter.domain.sort_policy import SortPolicy


def test_sort_policy_orders_by_rarity_type_color_name():
    policy = SortPolicy()
    c1 = CardInstance(card_id="1", meta=CardMeta(name="Alpha", rarity="MYTHIC", card_type="artifact", color="colorless"))
    c2 = CardInstance(card_id="2", meta=CardMeta(name="Beta", rarity="OTHER", card_type="other", color="default"))

    assert policy.compare(c1, c2) is True
    assert policy.compare(c2, c1) is False


def test_rank_mapping_is_stable():
    policy = SortPolicy()
    cards = [
        CardInstance(card_id="2", meta=CardMeta(name="Beta", rarity="OTHER")),
        CardInstance(card_id="1", meta=CardMeta(name="Alpha", rarity="MYTHIC")),
    ]
    mapping = policy.rank_mapping(cards)
    assert mapping["Alpha"] < mapping["Beta"]
