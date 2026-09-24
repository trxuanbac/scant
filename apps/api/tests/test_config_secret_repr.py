from app.core.config import Settings


def test_settings_repr_does_not_print_provider_credentials():
    configured = Settings(_env_file=None, GEMINI_API_KEY="example-secret", GOOGLE_CLIENT_SECRET="oauth-secret", GOOGLE_MAPS_ROUTES_API_KEY="maps-secret")
    rendered = repr(configured)
    assert "example-secret" not in rendered
    assert "oauth-secret" not in rendered
    assert "maps-secret" not in rendered
