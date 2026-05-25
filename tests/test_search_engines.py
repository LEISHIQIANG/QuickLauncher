from core.search_engines import build_search_url, parse_search_action


def test_google_bing_and_baidu_prefixes():
    assert parse_search_action("g test").engine == "google"
    assert parse_search_action("bing test").engine == "bing"
    assert parse_search_action("bd test").engine == "baidu"


def test_empty_or_unknown_prefix_returns_none():
    assert parse_search_action("") is None
    assert parse_search_action("g") is None
    assert parse_search_action("unknown test") is None


def test_search_url_encodes_chinese_and_spaces():
    action = parse_search_action("bd 中文 space")
    url = build_search_url(action)

    assert "中文" not in url
    assert "%E4%B8%AD%E6%96%87%20space" in url
    assert url.startswith("https://www.baidu.com/s?wd=")
