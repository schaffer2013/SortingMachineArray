from sorter.adapters.persistence.file_card_catalog import _normalize_card_meta


def test_normalize_card_meta_reads_scryfall_id_fields():
    meta = _normalize_card_meta(
        {
            "name": "Snapcaster Mage",
            "id": "AAAAAAAA-BBBB-CCCC-DDDD-EEEEEEEEEEEE",
            "oracle_id": "ffffffff-1111-2222-3333-444444444444",
        }
    )

    assert meta.scryfall_id == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    assert meta.oracle_id == "ffffffff-1111-2222-3333-444444444444"
