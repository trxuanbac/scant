from app.main import app


def test_retired_product_routes_are_not_mounted() -> None:
    paths = set(app.openapi()["paths"])

    assert "/api/v1/ai/inspect-stylometry" not in paths
    assert "/api/v1/ai/voice-to-report" not in paths
    assert not any(path.startswith("/api/v1/automations") for path in paths)
    assert not any(path.startswith("/api/v1/collaboration") for path in paths)


def test_focused_product_routes_remain_mounted() -> None:
    paths = set(app.openapi()["paths"])

    required_paths = {
        "/api/v1/projects",
        "/api/v1/reports",
        "/api/v1/research/direct-search",
        "/api/v1/sources/search",
        "/api/v1/data/profile/{file_id}",
        "/api/v1/health",
    }
    assert required_paths <= paths
