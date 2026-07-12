class TestServicesInit:
    def test_import_services(self):
        import services

        assert services.__name__ == "services"

    def test_init_services(self):
        import services
        from services import init_services

        services._initialized = False
        init_services()
        assert services._initialized

    def test_import_submodules(self):
        from services.api.base_client import ApiClient, ApiError
        from services.errors import ServicesError, UpdateError

        assert ApiClient
        assert ApiError
        assert ServicesError
        assert UpdateError
