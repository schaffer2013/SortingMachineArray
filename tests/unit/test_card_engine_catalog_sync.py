from __future__ import annotations

from types import SimpleNamespace

from sorter.adapters.persistence.card_engine_catalog_sync import (
    CardEngineCatalogSyncRequest,
    resolve_catalog_card,
)


class FakeQuery:
    def __init__(self, *, identity: dict[str, object] | None, printed_by_id=None, oracle_by_id=None):
        self.identity = identity
        self.printed_by_id = printed_by_id or {}
        self.oracle_by_id = oracle_by_id or {}

    def resolve_card_identity(self, **kwargs):
        return self.identity

    def get_printed_card(self, scryfall_id: str):
        return self.printed_by_id.get(scryfall_id)

    def get_oracle_card(self, oracle_id: str):
        return self.oracle_by_id.get(oracle_id)


def test_resolve_catalog_card_prefers_identifier_first_printing():
    oracle = SimpleNamespace(
        oracle_id="oracle-elspeth",
        type_line="Legendary Planeswalker — Elspeth",
        colors=("W",),
        color_identity=("W",),
    )
    printing = SimpleNamespace(
        scryfall_id="73A065E3-B530-4E62-AB3C-4F6F908184EC",
        oracle_id="F78AF825-023A-42E9-8374-5C52303A1417",
        name="Elspeth, Storm Slayer",
        set_code="TDM",
        collector_number="11",
        image_url="https://cards.example/elspeth.jpg",
        rarity="Mythic",
        colors=("W",),
        color_identity=("W",),
        type_line="Legendary Planeswalker — Elspeth",
    )
    query = FakeQuery(
        identity={"oracle": oracle, "printing": printing},
        printed_by_id={printing.scryfall_id: printing},
        oracle_by_id={printing.oracle_id: oracle},
    )

    card = resolve_catalog_card(
        query,
        CardEngineCatalogSyncRequest(
            scryfall_id=printing.scryfall_id,
            name="Elspeth, Storm Slayer",
        ),
    )

    assert card["scryfall_id"] == "73a065e3-b530-4e62-ab3c-4f6f908184ec"
    assert card["oracle_id"] == "f78af825-023a-42e9-8374-5c52303a1417"
    assert card["rarity"] == "mythic"
    assert card["image_url"] == "https://cards.example/elspeth.jpg"
    assert card["card_types"] == ["planeswalker"]
    assert card["supertypes"] == ["legendary"]
    assert card["colors"] == ["w"]
    assert card["color_identity"] == ["w"]


def test_resolve_catalog_card_selects_lowest_collector_when_multiple_printings_match():
    oracle = SimpleNamespace(
        oracle_id="oracle-split",
        type_line="Creature — Human Warrior // Instant — Adventure",
        colors=("G",),
        color_identity=("G",),
    )
    showcase = SimpleNamespace(
        scryfall_id="bb6b2759-c315-42cb-8842-dc4f0f42c01d",
        oracle_id="oracle-split",
        name="Garenbrig Carver // Shield's Might",
        set_code="ELD",
        collector_number="298",
        rarity="Common",
        colors=("G",),
        color_identity=("G",),
        type_line="Creature — Human Warrior // Instant — Adventure",
    )
    normal = SimpleNamespace(
        scryfall_id="194b7a1c-291a-470e-9a40-61b72a46793b",
        oracle_id="oracle-split",
        name="Garenbrig Carver // Shield's Might",
        set_code="ELD",
        collector_number="156",
        rarity="Common",
        colors=("G",),
        color_identity=("G",),
        type_line="Creature — Human Warrior // Instant — Adventure",
    )
    query = FakeQuery(
        identity={"oracle": oracle, "printings": [showcase, normal]},
        oracle_by_id={"oracle-split": oracle},
    )

    card = resolve_catalog_card(
        query,
        CardEngineCatalogSyncRequest(
            name="Garenbrig Carver // Shield's Might",
            set_code="ELD",
        ),
    )

    assert card["scryfall_id"] == "194b7a1c-291a-470e-9a40-61b72a46793b"
    assert card["set_code"] == "eld"
    assert card["card_types"] == ["creature", "instant"]


def test_resolve_catalog_card_extracts_image_url_from_raw_payload_faces():
    oracle = SimpleNamespace(
        oracle_id="oracle-double-face",
        type_line="Sorcery",
        colors=("U",),
        color_identity=("U",),
    )
    printing = SimpleNamespace(
        scryfall_id="5d9c1372-df08-4c4d-85b4-ccad9e88e6df",
        oracle_id="oracle-double-face",
        name="Commit // Memory",
        set_code="AKH",
        collector_number="211",
        rarity="Rare",
        colors=("U",),
        color_identity=("U",),
        type_line="Sorcery",
        _json={
            "card_faces": [
                {"image_uris": {"normal": "https://cards.example/commit-memory-front.jpg"}},
            ]
        },
    )
    query = FakeQuery(
        identity={"oracle": oracle, "printing": printing},
        printed_by_id={printing.scryfall_id: printing},
        oracle_by_id={printing.oracle_id: oracle},
    )

    card = resolve_catalog_card(query, CardEngineCatalogSyncRequest(name="Commit // Memory"))

    assert card["image_url"] == "https://cards.example/commit-memory-front.jpg"
