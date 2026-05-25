"""商业模块异常定义。"""


class CommercialError(Exception):
    """商业模块基础异常。"""


class UpdateError(CommercialError):
    """更新错误。"""
