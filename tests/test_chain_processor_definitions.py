import json

from core.chain_contracts import input_port_specs_for_node, output_port_specs_for_node
from core.chain_processors import execute_chain_processor, processor_definition, processor_definitions
from core.data_models import ShortcutItem, ShortcutType


def test_legacy_processor_module_is_registry_facade():
    import core.chain.registry as registry
    import core.chain_processors as legacy

    assert legacy.PROCESSOR_DEFINITIONS is registry.PROCESSOR_DEFINITIONS
    assert legacy.EXTERNAL_PROCESSOR_DEFINITIONS is registry.EXTERNAL_PROCESSOR_DEFINITIONS
    assert legacy.EXTERNAL_PROCESSOR_HANDLERS is registry.EXTERNAL_PROCESSOR_HANDLERS
    assert legacy.processor_definitions is registry.processor_definitions
    assert legacy.processor_definition is registry.processor_definition
    assert legacy.execute_chain_processor is registry.execute_chain_processor


KNOWN_PORT_KINDS = {"any", "text", "json", "file", "folder", "url", "list", "number", "bool"}
KNOWN_PARAM_KINDS = KNOWN_PORT_KINDS | {"textarea", "choice", "password"}
KNOWN_PORT_ROLES = {"primary", "data", "status", "diagnostic", "collection", "metadata", "stream", "control", "parameter"}


def test_all_processors_have_complete_schema():
    definitions = processor_definitions()
    ids = [definition.id for definition in definitions]

    assert ids
    assert len(ids) == len(set(ids))

    for definition in definitions:
        assert definition.id
        assert definition.title
        assert definition.category
        assert definition.description
        assert definition.inputs or definition.outputs
        assert definition.outputs
        assert definition.safety.level in {"safe", "caution", "dangerous"}
        assert definition.safety.capability.startswith("chain.")
        assert definition.examples

        input_ids = [port.id for port in definition.inputs]
        output_ids = [port.id for port in definition.outputs]
        param_ids = [param.id for param in definition.params]
        assert len(input_ids) == len(set(input_ids)), definition.id
        assert len(output_ids) == len(set(output_ids)), definition.id
        assert len(param_ids) == len(set(param_ids)), definition.id
        assert set(param_ids).issubset(set(input_ids)), definition.id
        assert all(port.kind in KNOWN_PORT_KINDS for port in definition.inputs), definition.id
        assert all(port.kind in KNOWN_PORT_KINDS for port in definition.outputs), definition.id
        assert all(port.role in KNOWN_PORT_ROLES for port in definition.inputs), definition.id
        assert all(port.role in KNOWN_PORT_ROLES for port in definition.outputs), definition.id
        assert all(param.kind in KNOWN_PARAM_KINDS for param in definition.params), definition.id

        json.dumps(definition.to_dict(), ensure_ascii=False)


def test_processor_definition_lookup_and_risk_flags():
    http_get = processor_definition("http_get")
    python_cell = processor_definition("python_cell")
    file_write = processor_definition("file_write_text")

    assert http_get is not None
    assert http_get.safety.level == "caution"
    assert http_get.safety.network is True
    assert python_cell is not None
    assert python_cell.safety.executes_code is True
    assert python_cell.safety.requires_confirmation is True
    assert file_write is not None
    assert file_write.safety.writes_files is True


def test_processor_definition_ids_have_execution_branch():
    # Unknown processors fail clearly; every defined processor should at least
    # be recognized by the dispatcher even if its default args fail validation.
    for definition in processor_definitions():
        result = execute_chain_processor(definition.id, {})
        assert result.error != "Unknown processor", definition.id


def test_processor_contract_specs_are_schema_driven():
    sleep = processor_definition("sleep_node")
    assert sleep is not None

    input_specs = {spec.id: spec for spec in input_port_specs_for_node({"node_type": "processor", "processor_id": "sleep_node"}, {})}
    output_specs = {spec.id: spec for spec in output_port_specs_for_node({"node_type": "processor", "processor_id": "sleep_node"}, {})}

    assert input_specs["ms"].kind == "number"
    assert input_specs["ms"].label == "毫秒"
    assert output_specs["ms"].kind == "number"


def test_shortcut_standard_output_specs_have_clear_types_and_descriptions():
    shortcut = ShortcutItem(id="cmd", name="Cmd", type=ShortcutType.COMMAND, capture_output=True)
    specs = {
        spec.id: spec
        for spec in output_port_specs_for_node({"node_type": "shortcut", "shortcut_id": "cmd"}, {"cmd": shortcut})
    }

    assert specs["success"].kind == "bool"
    assert specs["success"].label == "成功状态"
    assert specs["success"].role == "status"
    assert "1/true" in specs["success"].description
    assert specs["output"].label == "主输出"
    assert specs["output"].role == "primary"
    assert specs["stdout"].kind == "text"
    assert specs["stdout"].role == "stream"
    assert specs["stderr"].label == "标准错误"
    assert specs["stderr"].role == "diagnostic"
    assert specs["exit_code"].kind == "number"
    assert specs["exit_code"].role == "status"
    assert specs["files.0"].kind == "file"
    assert specs["files.0"].role == "collection"
    assert specs["folders.0"].kind == "folder"
    assert specs["folders.0"].role == "collection"
    assert specs["urls.0"].kind == "url"
    assert specs["urls.0"].role == "collection"
    assert "第 0 项" in specs["urls.0"].description


def test_corrected_processor_port_kinds_for_connection_contracts():
    cases = [
        ("bool_value", "input", "value", "bool"),
        ("json_get", "input", "path", "text"),
        ("json_get", "output", "output", "any"),
        ("json_set", "input", "path", "text"),
        ("text_slice", "input", "start", "number"),
        ("regex_extract", "input", "group", "number"),
        ("loop_counter", "input", "step", "number"),
        ("loop_counter", "output", "output", "list"),
        ("series_arith", "output", "output", "list"),
        ("series_geom", "output", "output", "list"),
        ("list_create", "output", "first", "text"),
        ("list_len", "output", "output", "number"),
        ("list_contains", "output", "output", "bool"),
        ("list_join", "output", "output", "text"),
        ("hex_to_dec", "output", "output", "number"),
        ("path_split", "output", "output", "file"),
        ("path_exists", "output", "output", "bool"),
    ]

    for processor_id, direction, port_id, expected_kind in cases:
        node = {"node_type": "processor", "processor_id": processor_id}
        specs = input_port_specs_for_node(node, {}) if direction == "input" else output_port_specs_for_node(node, {})
        by_id = {spec.id: spec for spec in specs}
        assert by_id[port_id].kind == expected_kind, (processor_id, direction, port_id)


def test_http_processor_outputs_include_status_and_headers(monkeypatch):
    class FakeHeaders:
        def items(self):
            return [("Content-Type", "application/json")]

    class FakeResponse:
        status = 201
        headers = FakeHeaders()

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"ok":true}'

        def getcode(self):
            return self.status

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=10: FakeResponse())

    result = execute_chain_processor("http_get", {"url": "example.com"})

    assert result.success is True
    assert result.payload["outputs"]["output"] == '{"ok":true}'
    assert result.payload["outputs"]["status_code"] == "201"
    assert result.payload["raw_outputs"]["headers"] == {"Content-Type": "application/json"}


def test_sampled_processor_outputs_match_declared_contract(tmp_path):
    sample_args = _sample_processor_args(tmp_path)
    sampled_ids = set(sample_args)
    intentionally_unsampled = {
        "python_cell",
        "http_get",
        "http_post",
        "http_download",
        "img_resize",
        "img_convert",
        "img_watermark",
        "img_crop",
        "img_rotate",
    }
    try:
        from core.chain.enhanced_definitions import get_enhanced_definitions as _ge
        intentionally_unsampled |= set(_ge().keys())
    except Exception:
        pass
    try:
        from core.chain.extended_definitions import get_extended_definitions as _ge2
        intentionally_unsampled |= set(_ge2().keys())
    except Exception:
        pass
    all_ids = {definition.id for definition in processor_definitions()}
    unsampled_registered_ids = intentionally_unsampled & all_ids
    assert all_ids == sampled_ids | unsampled_registered_ids, (
        f"Missing sample args or intentionally_unsampled for: "
        f"{all_ids - sampled_ids - unsampled_registered_ids}"
    )

    for definition in processor_definitions():
        if definition.id in intentionally_unsampled:
            continue
        result = execute_chain_processor(definition.id, sample_args[definition.id])
        assert result.success is True, definition.id
        payload = result.payload if isinstance(result.payload, dict) else {}
        outputs = dict(payload.get("outputs") or {})
        raw_outputs = dict(payload.get("raw_outputs") or {})
        for port in definition.outputs:
            assert port.id in outputs, (definition.id, port.id, outputs)
            assert port.id in raw_outputs, (definition.id, port.id, raw_outputs)
            assert _raw_value_matches_kind(raw_outputs[port.id], port.kind), (
                definition.id,
                port.id,
                port.kind,
                raw_outputs[port.id],
            )


def _sample_processor_args(tmp_path):
    text_path = tmp_path / "data" / "input.txt"
    text_path.parent.mkdir(parents=True, exist_ok=True)
    text_path.write_text("hello", encoding="utf-8")
    output_path = tmp_path / "data" / "output.txt"
    folder_path = tmp_path / "logs"
    return {
        "panel_node": {"text": "甲"},
        "text_input": {"text": "甲"},
        "assert_not_empty": {"text": "甲", "message": "不能为空"},
        "coalesce_value": {"value": "", "fallback": "兜底"},
        "type_convert": {"value": "1", "type": "text"},
        "conditional_branch": {"value": "甲", "compare": "==", "target": "甲"},
        "logger_node": {"text": "日志", "level": "info"},
        "sleep_node": {"input": "继续", "ms": "0"},
        "bool_value": {"value": "true"},
        "bool_not": {"value": "false"},
        "bool_and": {"a": "true", "b": "true"},
        "bool_or": {"a": "false", "b": "true"},
        "bool_xor": {"a": "true", "b": "false"},
        "compare_value": {"a": "3", "operator": "大于", "b": "2"},
        "if_else": {"condition": "true", "true_value": "甲", "false_value": "乙"},
        "loop_repeat": {"input": "甲", "count": "2", "delimiter": ","},
        "loop_counter": {"start": "1", "end": "3", "step": "1", "delimiter": "\n"},
        "text_template": {"template": "{a}-{b}", "a": "甲", "b": "乙"},
        "text_replace": {"text": "甲乙", "find": "乙", "replace": "丙"},
        "text_slice": {"text": "甲乙丙", "start": "1", "end": "3"},
        "regex_extract": {"text": "id=42", "pattern": r"id=(\d+)", "group": "1"},
        "text_case": {"text": "abc", "mode": "upper"},
        "text_join": {"delimiter": "-", "a": "甲", "b": "乙"},
        "text_len": {"text": "甲乙"},
        "text_split": {"text": "甲,乙", "delimiter": ","},
        "text_lines": {"text": "甲\n乙"},
        "json_get": {"json": '{"items":[{"name":"甲"}]}', "path": "items[0].name"},
        "json_set": {"json": '{"a":1}', "path": "b", "value": "2"},
        "url_encode": {"text": "甲 乙", "mode": "encode"},
        "json_parse": {"json_str": '{"a":1}'},
        "json_template": {"json": '{"user":{"name":"Ada"}}', "template": "{user.name}"},
        "num_input": {"number": "42"},
        "math_add": {"a": "1", "b": "2"},
        "math_sub": {"a": "3", "b": "1"},
        "math_mul": {"a": "2", "b": "3"},
        "math_div": {"a": "4", "b": "2"},
        "math_pow": {"base": "2", "exp": "3"},
        "math_mod": {"a": "5", "b": "2"},
        "series_arith": {"start": "1", "step": "1", "count": "3"},
        "series_geom": {"start": "1", "ratio": "2", "count": "3"},
        "list_create": {"a": "甲", "b": "乙"},
        "list_item": {"list": "甲\n乙", "index": "1"},
        "list_len": {"list": "甲\n乙"},
        "list_rev": {"list": "甲\n乙"},
        "list_unique": {"list": "甲\n乙\n甲"},
        "list_sort": {"list": "2\n1", "mode": "数字"},
        "list_filter": {"list": "a.txt\nb.png", "contains": ".txt"},
        "list_contains": {"list": "甲\n乙", "value": "甲"},
        "list_template": {"list": "甲\n乙", "template": "{item}"},
        "list_concat": {"a": "甲", "b": "乙"},
        "list_slice": {"list": "甲\n乙\n丙", "start": "1", "end": "3"},
        "list_zip": {"a": "甲\n乙", "b": "1\n2", "template": "{a}:{b}"},
        "list_flatten": {"list": '[["甲"],["乙"]]'},
        "list_join": {"list": "甲\n乙", "delimiter": ","},
        "base_convert": {"number": "10", "from_base": "10", "to_base": "2"},
        "dec_to_hex": {"number": "255"},
        "hex_to_dec": {"number": "ff"},
        "file_path_input": {"path": str(text_path)},
        "folder_path_input": {"path": str(text_path.parent)},
        "path_join": {"a": str(tmp_path), "b": "data", "c": "input.txt"},
        "path_split": {"path": str(text_path)},
        "path_exists": {"path": str(text_path)},
        "folder_create": {"path": str(folder_path)},
        "file_read_text": {"path": str(text_path), "encoding": "utf-8"},
        "file_write_text": {"path": str(output_path), "text": "hello", "encoding": "utf-8", "mode": "overwrite"},
    }


def _raw_value_matches_kind(value, kind: str) -> bool:
    if kind == "any":
        return True
    if kind == "text":
        return isinstance(value, str)
    if kind == "number":
        if isinstance(value, int | float) and not isinstance(value, bool):
            return True
        try:
            float(str(value))
            return True
        except Exception:
            return False
    if kind == "bool":
        if isinstance(value, bool):
            return True
        return str(value).strip().lower() in {"true", "false", "1", "0", "是", "否", "真", "假"}
    if kind == "list":
        return isinstance(value, list)
    if kind == "json":
        if isinstance(value, dict | list):
            return True
        try:
            json.loads(str(value))
            return True
        except Exception:
            return False
    if kind in {"file", "folder", "url"}:
        return isinstance(value, str)
    return False
