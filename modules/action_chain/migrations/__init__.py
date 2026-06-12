"""Action-chain data migrations."""

import copy
import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

# 迁移函数映射表：key = 源 schema 版本, value = 迁移到下一版本的函数
# 每个迁移函数接收 data (dict)，返回迁移后的 data (dict)，必须是幂等的。
# 新增迁移时在此注册，例如：
#   def _migrate_1_to_2(data: dict) -> dict:
#       data["new_field"] = data.pop("old_field", "default")
#       return data
#   _MIGRATIONS[1] = _migrate_1_to_2
_MIGRATIONS: dict[int, Callable[[dict], dict]] = {}

LATEST_SCHEMA = 1  # 随迁移注册同步更新


def migrate_chain_data(
    chain_data: dict,
    from_schema: int | None = None,
    to_schema: int = LATEST_SCHEMA,
) -> dict:
    """按版本链逐步迁移动作链数据。

    Parameters
    ----------
    chain_data : dict
        待迁移的动作链原始数据。
    from_schema : int | None
        数据当前的 schema 版本。为 None 时从数据中的
        ``schema_version`` 字段读取，缺省视为 1。
    to_schema : int
        目标 schema 版本，默认为 LATEST_SCHEMA。

    Returns
    -------
    dict
        迁移后的数据副本（原始数据不会被修改）。
    """
    data = copy.deepcopy(chain_data or {})

    current = int(from_schema if from_schema is not None else data.get("schema_version", 1))
    target = int(to_schema or LATEST_SCHEMA)

    if current > target:
        logger.warning("数据 schema_version=%d 高于目标 %d，跳过迁移", current, target)
        data["schema_version"] = target
        return data

    while current < target:
        step = _MIGRATIONS.get(current)
        if step is None:
            logger.warning("缺少 %d → %d 的迁移函数，停止迁移", current, current + 1)
            break
        try:
            data = step(data)
        except Exception:
            logger.exception("迁移步骤 %d → %d 失败", current, current + 1)
            break
        current += 1

    data["schema_version"] = current
    return data
