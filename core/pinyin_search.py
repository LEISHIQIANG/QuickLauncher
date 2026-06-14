"""Small built-in pinyin surfaces for shortcut search.

This is intentionally dependency-free. It covers common UI/app words and keeps
the API open for a future optional full pinyin backend.
"""

from __future__ import annotations

from functools import lru_cache

_PINYIN = {
    # Original keys
    "阿": "a",
    "安": "an",
    "百": "bai",
    "版": "ban",
    "帮": "bang",
    "包": "bao",
    "备": "bei",
    "本": "ben",
    "笔": "bi",
    "编": "bian",
    "表": "biao",
    "播": "bo",
    "不": "bu",
    "菜": "cai",
    "测": "ce",
    "查": "cha",
    "程": "cheng",
    "窗": "chuang",
    "磁": "ci",
    "打": "da",
    "代": "dai",
    "单": "dan",
    "导": "dao",
    "的": "de",
    "地": "di",
    "点": "dian",
    "电": "dian",
    "调": "diao",
    "动": "dong",
    "端": "duan",
    "多": "duo",
    "发": "fa",
    "分": "fen",
    "服": "fu",
    "复": "fu",
    "改": "gai",
    "工": "gong",
    "共": "gong",
    "管": "guan",
    "广": "guang",
    "归": "gui",
    "国": "guo",
    "海": "hai",
    "行": "hang",
    "好": "hao",
    "和": "he",
    "画": "hua",
    "换": "huan",
    "回": "hui",
    "辑": "ji",
    "件": "jian",
    "键": "jian",
    "检": "jian",
    "建": "jian",
    "接": "jie",
    "截": "jie",
    "径": "jing",
    "开": "kai",
    "控": "kong",
    "快": "kuai",
    "哩": "li",
    "理": "li",
    "览": "lan",
    "浏": "liu",
    "令": "ling",
    "录": "lu",
    "路": "lu",
    "码": "ma",
    "目": "mu",
    "名": "ming",
    "命": "ming",
    "脑": "nao",
    "内": "nei",
    "盘": "pan",
    "配": "pei",
    "频": "pin",
    "启": "qi",
    "器": "qi",
    "签": "qian",
    "清": "qing",
    "取": "qu",
    "全": "quan",
    "软": "ruan",
    "色": "se",
    "删": "shan",
    "设": "she",
    "升": "sheng",
    "时": "shi",
    "试": "shi",
    "视": "shi",
    "示": "shi",
    "收": "shou",
    "首": "shou",
    "数": "shu",
    "索": "suo",
    "台": "tai",
    "淘": "tao",
    "态": "tai",
    "特": "te",
    "提": "ti",
    "替": "ti",
    "图": "tu",
    "托": "tuo",
    "网": "wang",
    "文": "wen",
    "务": "wu",
    "系": "xi",
    "下": "xia",
    "项": "xiang",
    "像": "xiang",
    "新": "xin",
    "息": "xi",
    "序": "xu",
    "选": "xuan",
    "压": "ya",
    "验": "yan",
    "页": "ye",
    "音": "yin",
    "易": "yi",
    "应": "ying",
    "用": "yong",
    "游": "you",
    "语": "yu",
    "源": "yuan",
    "云": "yun",
    "远": "yuan",
    "运": "yun",
    "站": "zhan",
    "整": "zheng",
    "置": "zhi",
    "中": "zhong",
    "注": "zhu",
    "主": "zhu",
    "转": "zhuan",
    "桌": "zhuo",
    "自": "zi",
    "搜": "sou",
    "络": "luo",
    "具": "ju",
    "制": "zhi",
    "面": "mian",
    "板": "ban",
    # Added App/System high frequency words
    "微": "wei",
    "信": "xin",
    "支": "zhi",
    "付": "fu",
    "宝": "bao",
    "哔": "bi",
    "册": "ce",
    "钉": "ding",
    "东": "dong",
    "符": "fu",
    "京": "jing",
    "里": "li",
    "聊": "liao",
    "抖": "dou",
    "手": "shou",
    "歌": "ge",
    "谷": "gu",
    "雅": "ya",
    "虎": "hu",
    "任": "ren",
    "计": "ji",
    "算": "suan",
    "夹": "jia",
    "驱": "qu",
    "环": "huan",
    "境": "jing",
    "放": "fang",
    "照": "zhao",
    "相": "xiang",
    "机": "ji",
    "屏": "ping",
    "戏": "xi",
    "乐": "yue",
    "载": "zai",
    "装": "zhuang",
    "除": "chu",
    "火": "huo",
    "狐": "hu",
    "油": "you",
    "猴": "hou",
    "档": "dang",
    "据": "ju",
    "度": "du",
    "贴": "tie",
    "吧": "ba",
    "腾": "teng",
    "讯": "xun",
    "黑": "hei",
    "神": "shen",
    "悟": "wu",
    "空": "kong",
    "英": "ying",
    "雄": "xiong",
    "联": "lian",
    "盟": "meng",
    "魔": "mo",
    "世": "shi",
    "界": "jie",
    "第": "di",
    "三": "san",
    "方": "fang",
    "插": "cha",
    "式": "shi",
    "辅": "fu",
    "助": "zhu",
    # Expanded common UI/launcher characters
    "连": "lian",
    "记": "ji",
    "事": "shi",
    "终": "zhong",
    "统": "tong",
    "关": "guan",
    "于": "yu",
    "更": "geng",
    "属": "shu",
    "性": "xing",
    "投": "tou",
    "垃": "la",
    "圾": "ji",
    "重": "zhong",
    "退": "tui",
    "出": "chu",
    "高": "gao",
    "级": "ji",
    "防": "fang",
    "墙": "qiang",
    "诊": "zhen",
    "断": "duan",
    "修": "xiu",
    "片": "pian",
    "找": "zhao",
    "匹": "pi",
    "历": "li",
    "史": "shi",
    "扫": "sao",
    "描": "miao",
    "口": "kou",
    "库": "ku",
}


def _gb2312_initial(char: str) -> str | None:
    """Get the first letter of a Chinese character using GB2312 encoding."""
    try:
        gb_bytes = char.encode("gb2312")
        if len(gb_bytes) != 2:
            return None
        val = gb_bytes[0] * 256 + gb_bytes[1]
        if 45217 <= val <= 45252:
            return "a"
        if 45253 <= val <= 45760:
            return "b"
        if 45761 <= val <= 46317:
            return "c"
        if 46318 <= val <= 46825:
            return "d"
        if 46826 <= val <= 47009:
            return "e"
        if 47010 <= val <= 47296:
            return "f"
        if 47297 <= val <= 47613:
            return "g"
        if 47614 <= val <= 48118:
            return "h"
        if 48119 <= val <= 49061:
            return "j"
        if 49062 <= val <= 49323:
            return "k"
        if 49324 <= val <= 49895:
            return "l"
        if 49896 <= val <= 50370:
            return "m"
        if 50371 <= val <= 50613:
            return "n"
        if 50614 <= val <= 50621:
            return "o"
        if 50622 <= val <= 50905:
            return "p"
        if 50906 <= val <= 51386:
            return "q"
        if 51387 <= val <= 51445:
            return "r"
        if 51446 <= val <= 52217:
            return "s"
        if 52218 <= val <= 52697:
            return "t"
        if 52698 <= val <= 52979:
            return "w"
        if 52980 <= val <= 53688:
            return "x"
        if 53689 <= val <= 54480:
            return "y"
        if 54481 <= val <= 55289:
            return "z"
    except Exception:
        return None
    return None


_HAS_PYPINYIN = None
_HAS_XPINYIN = None
_xpinyin_instance = None


@lru_cache(maxsize=1024)
def _get_external_pinyin(text: str) -> list[str]:
    """Try to generate pinyin variants via external libraries if installed."""
    global _HAS_PYPINYIN, _HAS_XPINYIN, _xpinyin_instance

    if _HAS_PYPINYIN is not False:
        try:
            import pypinyin

            _HAS_PYPINYIN = True
            initials_list = pypinyin.pinyin(text, style=pypinyin.Style.FIRST_LETTER)
            initials = "".join(item[0] for item in initials_list if item).lower()
            full_list = pypinyin.pinyin(text, style=pypinyin.Style.NORMAL)
            full = "".join(item[0] for item in full_list if item).lower()

            variants = []
            if full:
                variants.append(full)
            if initials and initials != full:
                variants.append(initials)
            return variants
        except ImportError:
            _HAS_PYPINYIN = False
        except Exception:
            _HAS_PYPINYIN = False

    if _HAS_XPINYIN is not False:
        try:
            from xpinyin import Pinyin

            _HAS_XPINYIN = True
            if _xpinyin_instance is None:
                _xpinyin_instance = Pinyin()
            full = _xpinyin_instance.get_pinyin(text, splitter="").lower()
            initials = _xpinyin_instance.get_initials(text, splitter="").lower()

            variants = []
            if full:
                variants.append(full)
            if initials and initials != full:
                variants.append(initials)
            return variants
        except ImportError:
            _HAS_XPINYIN = False
        except Exception:
            _HAS_XPINYIN = False

    return []


def _normalize_search_text(text: str) -> str:
    return "".join(
        ch
        for ch in str(text)
        if "\u4e00" <= ch <= "\u9fff"
        or "\u3400" <= ch <= "\u4dbf"
        or "\uf900" <= ch <= "\ufa5f"
        or (ch.isascii() and ch.isalnum())
    )


@lru_cache(maxsize=2048)
def pinyin_variants(text: str) -> list[str]:
    """Return full-pinyin and initials variants for CJK text."""
    if not text:
        return []
    normalized = _normalize_search_text(text)

    # Check if there is any Chinese character (early return for non-CJK)
    has_cjk = False
    for ch in normalized:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" or "\uf900" <= ch <= "\ufa5f":
            has_cjk = True
            break
    if not has_cjk:
        return []

    # 1. Try professional external libraries first if available
    external = _get_external_pinyin(normalized)
    if external:
        return external

    # 2. Fall back to lightweight built-in dictionary
    full_parts: list[str] = []
    initials: list[str] = []
    has_mapped_cjk = False
    for ch in normalized:
        py = _PINYIN.get(ch)
        if py:
            has_mapped_cjk = True
            full_parts.append(py)
            initials.append(py[0])
        elif "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" or "\uf900" <= ch <= "\ufa5f":
            initial = _gb2312_initial(ch)
            if initial:
                has_mapped_cjk = True
                full_parts.append(initial)
                initials.append(initial)
        elif ch.isascii() and ch.isalnum():
            full_parts.append(ch.lower())
            initials.append(ch.lower())
    if not has_mapped_cjk:
        return []
    full = "".join(full_parts)
    short = "".join(initials)
    variants = []
    if full:
        variants.append(full)
    if short and short != full:
        variants.append(short)
    return variants
