from core.chain.processor_loader import ProcessorLoader
from core.chain.processor_registry import ProcessorRegistry


def test_discover_from_package_uses_pkgutil_modules(tmp_path, monkeypatch):
    package_dir = tmp_path / "sample_processors"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "alpha.py").write_text(
        "\n".join(
            [
                "from core.chain.definitions import ChainProcessorDefinition",
                "PROCESSORS = {",
                "    'sample_alpha': ChainProcessorDefinition(",
                "        id='sample_alpha',",
                "        title='Sample Alpha',",
                "        inputs=['input'],",
                "        outputs=['output'],",
                "        category='文本处理',",
                "    )",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    (package_dir / "_private.py").write_text(
        "\n".join(
            [
                "from core.chain.definitions import ChainProcessorDefinition",
                "PROCESSORS = {",
                "    'sample_private': ChainProcessorDefinition(",
                "        id='sample_private',",
                "        title='Sample Private',",
                "        inputs=['input'],",
                "        outputs=['output'],",
                "    )",
                "}",
            ]
        ),
        encoding="utf-8",
    )
    nested_dir = package_dir / "nested"
    nested_dir.mkdir()
    (nested_dir / "__init__.py").write_text("", encoding="utf-8")

    monkeypatch.syspath_prepend(str(tmp_path))
    registry = ProcessorRegistry()
    loader = ProcessorLoader(registry)

    assert loader.discover_from_package("sample_processors") == 1
    assert registry.has_processor("sample_alpha")
    assert not registry.has_processor("sample_private")
    assert loader.discover_from_package("sample_processors") == 0


def test_discover_core_chain_package_does_not_treat_paths_as_module_infos(caplog):
    registry = ProcessorRegistry()
    loader = ProcessorLoader(registry)

    count = loader.discover_from_package("core.chain")

    assert isinstance(count, int)
    assert "has no attribute 'name'" not in caplog.text
