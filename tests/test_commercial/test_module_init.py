"""测试商业模块初始化。"""


class TestCommercialInit:
    def test_import_commercial(self):
        """commercial 包可正常导入。"""
        import commercial
        assert commercial.__name__ == "commercial"

    def test_init_commercial(self):
        """init_commercial 可正常调用，不抛异常。"""
        from commercial import init_commercial
        import commercial
        commercial._initialized = False
        init_commercial()
        assert commercial._initialized

    def test_import_submodules(self):
        """子模块均可正常导入。"""
        from commercial.api.base_client import ApiClient, ApiError
        from commercial.errors import CommercialError
        assert ApiClient
        assert ApiError
        assert CommercialError
