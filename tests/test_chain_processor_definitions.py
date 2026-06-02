import json

from core.chain_processors import execute_chain_processor, processor_definition, processor_definitions


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
