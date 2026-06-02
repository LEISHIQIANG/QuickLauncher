"""Action-chain data migrations."""


def migrate_chain_data(chain_data: dict, from_schema: int, to_schema: int = 1) -> dict:
    data = dict(chain_data or {})
    data.setdefault("schema_version", int(to_schema or 1))
    return data

