from scripts.validate_provenance import validate


def test_dependency_and_native_provenance_is_complete():
    assert validate() == []
