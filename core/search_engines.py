"""Built-in web search engine actions."""

from dataclasses import dataclass
from urllib.parse import quote


@dataclass(frozen=True)
class SearchAction:
    engine: str
    keyword: str
    url_template: str


_ENGINES = {
    "g": ("google", "https://www.google.com/search?q={query}"),
    "b": ("baidu", "https://www.baidu.com/s?wd={query}"),
    "y": ("yandex", "https://yandex.com/search/?text={query}"),
    "e": ("bing", "https://www.bing.com/search?q={query}"),
    "google": ("google", "https://www.google.com/search?q={query}"),
    "bing": ("bing", "https://www.bing.com/search?q={query}"),
    "bd": ("baidu", "https://www.baidu.com/s?wd={query}"),
    "baidu": ("baidu", "https://www.baidu.com/s?wd={query}"),
}


def parse_search_action(text: str) -> SearchAction | None:
    value = (text or "").strip()
    if not value:
        return None
    parts = value.split(None, 1)
    if len(parts) != 2:
        return None
    prefix, keyword = parts[0].strip().lower(), parts[1].strip()
    if not keyword or prefix not in _ENGINES:
        return None
    engine, template = _ENGINES[prefix]
    return SearchAction(engine=engine, keyword=keyword, url_template=template)


def build_search_url(action: SearchAction) -> str:
    if action is None:
        return ""
    return action.url_template.replace("{query}", quote(action.keyword, safe=""))
