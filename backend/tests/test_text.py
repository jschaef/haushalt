from haushalt_api.text import normalize, normalize_store


def test_normalize_drops_sizes_and_punctuation():
    assert normalize("JA! Frischmilch 3,5% 1L") == "ja frischmilch 3 5"
    assert normalize("Mineralwasser 6x1,5L") == normalize("Mineralwasser 6 x 1,5 l")
    assert normalize("Käse Gouda 400g") == "kaese gouda"


def test_normalize_store():
    assert normalize_store("REWE Markt GmbH") == "rewe"
    assert normalize_store("Rewe") == "rewe"
    assert normalize_store("dm-drogerie markt") == "dm drogerie"
    assert normalize_store("GmbH") == "gmbh"
