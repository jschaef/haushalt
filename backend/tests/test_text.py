from haushalt_api.text import article_key, normalize, normalize_store


def test_normalize_drops_sizes_and_punctuation():
    assert normalize("JA! Frischmilch 3,5% 1L") == "ja frischmilch 3 5"
    assert normalize("Mineralwasser 6x1,5L") == normalize("Mineralwasser 6 x 1,5 l")
    assert normalize("Käse Gouda 400g") == "kaese gouda"


def test_normalize_store():
    assert normalize_store("REWE Markt GmbH") == "rewe"
    assert normalize_store("Rewe") == "rewe"
    assert normalize_store("dm-drogerie markt") == "dm drogerie"
    assert normalize_store("GmbH") == "gmbh"


def test_article_key_keeps_the_size():
    assert article_key("JA! Frischmilch 3,5% 1L") == "ja frischmilch 3.5 1 l"
    assert article_key("ja frischmilch 3.5 % 1 l") == article_key("JA! Frischmilch 3,5% 1L")
    assert article_key("Milch 1L") != article_key("Milch 0,5L")
    assert article_key("Mineralwasser 6x1,5L") == "mineralwasser 6 x 1.5 l"
    assert article_key("Käse Gouda 400g.") == "kaese gouda 400 g"
