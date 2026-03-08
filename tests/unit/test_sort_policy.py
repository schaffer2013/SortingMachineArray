from pathlib import Path

from sorter.domain.models import CardMeta
from sorter.domain.ranking_service import RankingService
from sorter.domain.sort_policy_config import load_sort_policy_file


def test_default_policy_orders_by_primary_bucket_then_alpha():
    root = Path(__file__).resolve().parents[2]
    policy = load_sort_policy_file(root / "config/sort_policies/default_color_then_alpha.json")
    ranking = RankingService(policy).compile(
        {
            "c1": CardMeta(name="Zed", colors=["w"]),
            "c2": CardMeta(name="Axe", colors=["u"]),
            "c3": CardMeta(name="Bee", colors=[]),
            "c4": CardMeta(name="Aaa", colors=["w"]),
            "c5": CardMeta(name="Lotus", is_land=True),
            "c6": CardMeta(name="Plains", is_land=True, is_basic_land=True),
        }
    )

    assert ranking.card_id_to_rank["c4"] < ranking.card_id_to_rank["c1"]
    assert ranking.card_id_to_rank["c1"] < ranking.card_id_to_rank["c2"]
    assert ranking.card_id_to_rank["c2"] < ranking.card_id_to_rank["c3"]
    assert ranking.card_id_to_rank["c3"] < ranking.card_id_to_rank["c5"]
    assert ranking.card_id_to_rank["c5"] < ranking.card_id_to_rank["c6"]


def test_threshold_bucket_policy_market_price_over_5_first():
    root = Path(__file__).resolve().parents[2]
    policy = load_sort_policy_file(root / "config/sort_policies/over_5_then_default.json")
    ranking = RankingService(policy).compile(
        {
            "a": CardMeta(name="Alpha", market_price_usd=7.0),
            "b": CardMeta(name="Bravo", market_price_usd=5.0),
            "c": CardMeta(name="Charlie", market_price_usd=4.9),
            "d": CardMeta(name="Delta", market_price_usd=None),
        }
    )

    assert ranking.card_id_to_rank["a"] < ranking.card_id_to_rank["c"]
    assert ranking.card_id_to_rank["b"] < ranking.card_id_to_rank["c"]
    assert ranking.card_id_to_rank["c"] < ranking.card_id_to_rank["d"]


def test_numeric_policy_orders_by_mana_value_then_alpha():
    root = Path(__file__).resolve().parents[2]
    policy = load_sort_policy_file(root / "config/sort_policies/mana_value_then_alpha.json")
    ranking = RankingService(policy).compile(
        {
            "m5": CardMeta(name="Mana Five", mana_value=5),
            "m2": CardMeta(name="Mana Two", mana_value=2),
            "m1": CardMeta(name="Mana One", mana_value=1),
            "mx": CardMeta(name="No Mana", mana_value=None),
        }
    )

    assert ranking.card_id_to_rank["m1"] < ranking.card_id_to_rank["m2"]
    assert ranking.card_id_to_rank["m2"] < ranking.card_id_to_rank["m5"]
    assert ranking.card_id_to_rank["m5"] < ranking.card_id_to_rank["mx"]


def test_explain_card_returns_facts_derived_key_and_rank():
    root = Path(__file__).resolve().parents[2]
    policy = load_sort_policy_file(root / "config/sort_policies/default_color_then_alpha.json")
    ranking = RankingService(policy).compile({"id1": CardMeta(name="Alpha", colors=["w"], rarity="rare")})

    explanation = ranking.explain_card("id1")
    assert explanation is not None
    assert explanation.factual_fields["name"] == "Alpha"
    assert explanation.derived_fields["primary_bucket"] == "white"
    assert isinstance(explanation.sort_key, tuple)
    assert explanation.ordinal_rank == 1


def test_equal_sort_keys_share_the_same_rank():
    root = Path(__file__).resolve().parents[2]
    policy = load_sort_policy_file(root / "config/sort_policies/default_color_then_alpha.json")
    ranking = RankingService(policy).compile(
        {
            "dup_a": CardMeta(name="Lightning Bolt"),
            "dup_b": CardMeta(name="Lightning Bolt"),
            "other": CardMeta(name="Counterspell"),
        }
    )

    assert ranking.card_id_to_rank["dup_a"] == ranking.card_id_to_rank["dup_b"]
