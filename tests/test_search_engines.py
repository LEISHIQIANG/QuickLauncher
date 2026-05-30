from core.search_engines import SearchAction, build_search_url, parse_search_action


def test_google_bing_and_baidu_prefixes():
    assert parse_search_action("g test").engine == "google"
    assert parse_search_action("bing test").engine == "bing"
    assert parse_search_action("bd test").engine == "baidu"


def test_all_engine_prefixes():
    assert parse_search_action("y test").engine == "yandex"
    assert parse_search_action("e test").engine == "bing"
    assert parse_search_action("google test").engine == "google"
    assert parse_search_action("baidu test").engine == "baidu"


def test_empty_or_unknown_prefix_returns_none():
    assert parse_search_action("") is None
    assert parse_search_action("g") is None
    assert parse_search_action("unknown test") is None


def test_parse_search_action_with_none():
    assert parse_search_action(None) is None


def test_parse_search_action_with_whitespace():
    assert parse_search_action("   ") is None
    assert parse_search_action("  g  ") is None


def test_parse_search_action_extracts_keyword():
    action = parse_search_action("g python tutorial")
    assert action.keyword == "python tutorial"
    assert action.engine == "google"


def test_search_url_encodes_chinese_and_spaces():
    action = parse_search_action("bd 中文 space")
    url = build_search_url(action)

    assert "中文" not in url
    assert "%E4%B8%AD%E6%96%87%20space" in url
    assert url.startswith("https://www.baidu.com/s?wd=")


def test_build_search_url_with_none():
    assert build_search_url(None) == ""


def test_search_action_dataclass():
    action = SearchAction(engine="google", keyword="test", url_template="https://example.com?q={query}")
    assert action.engine == "google"
    assert action.keyword == "test"
    assert action.url_template == "https://example.com?q={query}"
