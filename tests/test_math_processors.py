from core.chain_processors import execute_chain_processor


def test_num_input():
    res = execute_chain_processor("num_input", {"number": "42.0"})
    assert res.success is True
    assert res.message == "42"

    res = execute_chain_processor("num_input", {"number": " 3.14159 "})
    assert res.success is True
    assert res.message == "3.14159"

    res = execute_chain_processor("num_input", {"number": "not_a_number"})
    assert res.success is True
    assert res.message == "not_a_number"


def test_basic_math_operations():
    # Add
    res = execute_chain_processor("math_add", {"a": "10", "b": "5.5"})
    assert res.success is True
    assert res.message == "15.5"

    # Sub
    res = execute_chain_processor("math_sub", {"a": "10", "b": "2.5"})
    assert res.success is True
    assert res.message == "7.5"

    # Mul
    res = execute_chain_processor("math_mul", {"a": "3", "b": "4"})
    assert res.success is True
    assert res.message == "12"

    # Div
    res = execute_chain_processor("math_div", {"a": "10", "b": "4"})
    assert res.success is True
    assert res.message == "2.5"

    # Div by zero
    res = execute_chain_processor("math_div", {"a": "10", "b": "0"})
    assert res.success is False
    assert "零" in res.error

    # Pow
    res = execute_chain_processor("math_pow", {"base": "2", "exp": "3"})
    assert res.success is True
    assert res.message == "8"

    # Mod
    res = execute_chain_processor("math_mod", {"a": "10", "b": "3"})
    assert res.success is True
    assert res.message == "1"

    # Mod by zero
    res = execute_chain_processor("math_mod", {"a": "10", "b": "0"})
    assert res.success is False
    assert "零" in res.error


def test_series_generation():
    # Arithmetic Series
    res = execute_chain_processor("series_arith", {"start": "1", "step": "2.5", "count": "4"})
    assert res.success is True
    lines = res.message.split("\n")
    assert lines == ["1", "3.5", "6", "8.5"]

    # Geometric Series
    res = execute_chain_processor("series_geom", {"start": "1", "ratio": "3", "count": "3"})
    assert res.success is True
    lines = res.message.split("\n")
    assert lines == ["1", "3", "9"]


def test_list_operations():
    # List Create
    res = execute_chain_processor("list_create", {"a": "apple", "b": "banana\ncherry", "c": "date"})
    assert res.success is True
    assert res.message == "apple\nbanana\ncherry\ndate"

    # List Len
    res = execute_chain_processor("list_len", {"list": "apple\nbanana\ncherry"})
    assert res.success is True
    assert res.message == "3"

    # List Item - positive index
    res = execute_chain_processor("list_item", {"list": "apple\nbanana\ncherry", "index": "1"})
    assert res.success is True
    assert res.message == "banana"

    # List Item - negative index
    res = execute_chain_processor("list_item", {"list": "apple\nbanana\ncherry", "index": "-1"})
    assert res.success is True
    assert res.message == "cherry"

    # List Item - index out of range
    res = execute_chain_processor("list_item", {"list": "apple\nbanana", "index": "5"})
    assert res.success is False

    # List Rev
    res = execute_chain_processor("list_rev", {"list": "apple\nbanana\ncherry"})
    assert res.success is True
    assert res.message == "cherry\nbanana\napple"


def test_programming_data_processors(tmp_path):
    res = execute_chain_processor("panel_node", {"text": "甲\n乙"})
    assert res.success is True
    assert res.payload["outputs"]["length"] == "3"
    assert res.payload["outputs"]["empty"] == "false"
    res = execute_chain_processor("panel_node", {"input": "上游内容", "text": "本地文本"})
    assert res.success is True
    assert res.message == "上游内容"

    res = execute_chain_processor("coalesce_value", {"value": "", "fallback": "兜底"})
    assert res.success is True
    assert res.message == "兜底"

    res = execute_chain_processor("text_split", {"text": "甲,乙,丙", "delimiter": ","})
    assert res.success is True
    assert res.payload["outputs"]["count"] == "3"
    assert res.message == "甲\n乙\n丙"

    res = execute_chain_processor("list_unique", {"list": "甲\n乙\n甲"})
    assert res.success is True
    assert res.message == "甲\n乙"

    res = execute_chain_processor("list_sort", {"list": "10\n2\n1", "mode": "数字"})
    assert res.success is True
    assert res.message == "1\n2\n10"

    res = execute_chain_processor("list_filter", {"list": "a.txt\nb.png\nc.txt", "contains": ".txt"})
    assert res.success is True
    assert res.message == "a.txt\nc.txt"

    res = execute_chain_processor("list_template", {"list": "甲\n乙", "template": "{序号}:{item}"})
    assert res.success is True
    assert res.message == "1:甲\n2:乙"

    res = execute_chain_processor("json_set", {"json": '{"a":1}', "path": "b.c", "value": "2"})
    assert res.success is True
    assert res.message == '{"a":1,"b":{"c":2}}'

    res = execute_chain_processor(
        "json_get", {"json": '{"items":[{"name":"甲"},{"name":"乙"}]}', "path": "items[1].name"}
    )
    assert res.success is True
    assert res.message == "乙"

    res = execute_chain_processor(
        "json_set",
        {"json": '{"items":[{"name":"甲"}]}', "path": "items[0].done", "value": "true"},
    )
    assert res.success is True
    assert res.message == '{"items":[{"name":"甲","done":true}]}'

    res = execute_chain_processor(
        "json_template",
        {"json": '{"user":{"name":"Ada"},"scores":[10,20]}', "template": "姓名:{user.name}; 第二项:{scores[1]}"},
    )
    assert res.success is True
    assert res.message == "姓名:Ada; 第二项:20"

    path = tmp_path / "data" / "a.txt"
    res = execute_chain_processor("file_write_text", {"path": str(path), "text": "hello"})
    assert res.success is True
    assert path.exists()
    assert res.payload["outputs"]["path"] == str(path)
    assert res.payload["outputs"]["exists"] == "true"
    assert res.payload["outputs"]["length"] == "5"
    res = execute_chain_processor("file_read_text", {"path": str(path)})
    assert res.success is True
    assert res.message == "hello"
    assert res.payload["outputs"]["filename"] == "a.txt"

    res = execute_chain_processor("file_write_text", {"path": str(path), "text": "\nworld", "mode": "追加"})
    assert res.success is True
    assert path.read_text(encoding="utf-8") == "hello\nworld"

    res = execute_chain_processor("file_path_input", {"path": str(path)})
    assert res.success is True
    assert res.payload["outputs"]["filename"] == "a.txt"

    folder = tmp_path / "logs"
    res = execute_chain_processor("folder_create", {"path": str(folder)})
    assert res.success is True
    assert folder.is_dir()
    assert res.payload["outputs"]["exists"] == "true"

    res = execute_chain_processor("path_split", {"path": str(path)})
    assert res.success is True
    assert res.payload["outputs"]["folder"].endswith("data")
    assert res.payload["outputs"]["stem"] == "a"
    assert res.payload["outputs"]["extension"] == ".txt"

    res = execute_chain_processor("sleep_node", {"input": "继续传递", "ms": "0"})
    assert res.success is True
    assert res.message == "继续传递"
    assert res.payload["outputs"]["ms"] == "0"


def test_midterm_list_data_processors():
    res = execute_chain_processor("list_concat", {"a": "甲\n乙", "b": "丙,丁", "c": '["戊","己"]'})
    assert res.success is True
    assert res.message == "甲\n乙\n丙\n丁\n戊\n己"
    assert res.payload["outputs"]["count"] == "6"

    res = execute_chain_processor("list_slice", {"list": "甲\n乙\n丙\n丁", "start": "1", "end": "3"})
    assert res.success is True
    assert res.message == "乙\n丙"

    res = execute_chain_processor(
        "list_zip",
        {"a": "A\nB\nC", "b": "1\n2", "template": "{序号}:{a}={b}"},
    )
    assert res.success is True
    assert res.message == "1:A=1\n2:B=2"

    res = execute_chain_processor("list_flatten", {"list": '[["a","b"],["c",["d"]]]'})
    assert res.success is True
    assert res.message == "a\nb\nc\nd"

    res = execute_chain_processor("list_join", {"list": "a\nb\nc", "delimiter": " | "})
    assert res.success is True
    assert res.message == "a | b | c"


def test_base_conversions():
    # Base convert dec -> bin
    res = execute_chain_processor("base_convert", {"number": "10", "from_base": "10", "to_base": "2"})
    assert res.success is True
    assert res.message == "1010"

    # Base convert bin -> hex
    res = execute_chain_processor("base_convert", {"number": "1010", "from_base": "2", "to_base": "16"})
    assert res.success is True
    assert res.message == "a"

    # Invalid base
    res = execute_chain_processor("base_convert", {"number": "10", "from_base": "1", "to_base": "10"})
    assert res.success is False

    # Dec to Hex
    res = execute_chain_processor("dec_to_hex", {"number": "255"})
    assert res.success is True
    assert res.message == "ff"

    # Hex to Dec
    res = execute_chain_processor("hex_to_dec", {"number": "0xff"})
    assert res.success is True
    assert res.message == "255"
