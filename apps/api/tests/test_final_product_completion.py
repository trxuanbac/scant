import pytest
from httpx import AsyncClient
from app.services.auth.google_auth_service import google_auth_service


@pytest.mark.asyncio
async def test_google_auth_token_verification():
    # Empty token rejected
    is_valid, user_info, err = await google_auth_service.verify_id_token("")
    assert is_valid is False
    assert err is not None


@pytest.mark.asyncio
async def test_user_profile_preferences_and_password_update(client: AsyncClient):
    # 1. Register User
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "enterprise_user@corp.com",
        "password": "Password123!",
        "name": "Enterprise User"
    })
    assert reg_res.status_code == 200
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Update Profile (preferred_locale, theme, document_language)
    prof_res = await client.put("/api/v1/auth/profile", json={
        "name": "Enterprise Director",
        "preferred_locale": "en",
        "theme": "dark",
        "document_language": "en"
    }, headers=headers)
    assert prof_res.status_code == 200
    data = prof_res.json()
    assert data["name"] == "Enterprise Director"
    assert data["preferred_locale"] == "en"
    assert data["theme"] == "dark"
    assert data["document_language"] == "en"

    # 3. Change Password
    # Wrong old password -> must fail
    fail_res = await client.put("/api/v1/auth/change-password", json={
        "old_password": "WrongPassword!",
        "new_password": "NewStrongPassword123!"
    }, headers=headers)
    assert fail_res.status_code == 400

    # Correct old password -> success
    pass_res = await client.put("/api/v1/auth/change-password", json={
        "old_password": "Password123!",
        "new_password": "NewStrongPassword123!"
    }, headers=headers)
    assert pass_res.status_code == 200

    # 4. Check Linked Accounts
    acc_res = await client.get("/api/v1/auth/accounts", headers=headers)
    assert acc_res.status_code == 200
    accs = acc_res.json()
    assert len(accs) >= 1
    assert accs[0]["provider"] == "password"


@pytest.mark.asyncio
async def test_brand_kit_database_persistence(client: AsyncClient):
    # Register user
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "brandkit_user@corp.com",
        "password": "Password123!",
        "name": "Brand Kit User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Get default Brand Kit
    get_res = await client.get("/api/v1/brand-kit", headers=headers)
    assert get_res.status_code == 200
    assert "primary_color" in get_res.json()

    # 2. Update Brand Kit with custom colors and typography
    put_res = await client.put("/api/v1/brand-kit", json={
        "primary_color": "#0f172a",
        "secondary_color": "#2563eb",
        "primary_font": "Plus Jakarta Sans",
        "heading_font": "Plus Jakarta Sans",
        "header_text": "ENTERPRISE • QUARTERLY REPORT",
        "confidentiality_notice": "CONFIDENTIAL"
    }, headers=headers)
    assert put_res.status_code == 200
    updated = put_res.json()
    assert updated["primary_color"] == "#0f172a"
    assert updated["primary_font"] == "Plus Jakarta Sans"

    # 3. Reload from database
    reload_res = await client.get("/api/v1/brand-kit", headers=headers)
    assert reload_res.status_code == 200
    assert reload_res.json()["header_text"] == "ENTERPRISE • QUARTERLY REPORT"


@pytest.mark.asyncio
async def test_google_oauth_first_login_returning_login_and_account_linking(client: AsyncClient, monkeypatch):
    from app.services.auth.google_auth_service import GoogleUserInfo

    # 1. Simulate Google OAuth First-time Login
    async def mock_verify_first(id_token: str, expected_client_id=None):
        return True, GoogleUserInfo(
            google_sub="google-sub-1001",
            email="google_user1@gmail.com",
            email_verified=True,
            name="Google First User",
            picture="https://google.com/photo1.jpg"
        ), None

    monkeypatch.setattr(google_auth_service, "verify_id_token", mock_verify_first)

    # First login -> creates new user + workspace + auth_account
    login1_res = await client.post("/api/v1/auth/google", json={"credential": "mock-valid-id-token"})
    assert login1_res.status_code == 200
    token1 = login1_res.json()["access_token"]
    user1 = login1_res.json()["user"]
    assert user1["email"] == "google_user1@gmail.com"
    assert user1["google_sub"] == "google-sub-1001"
    assert user1["name"] == "Google First User"

    # 2. Simulate Returning Google User Login with same google_sub
    login2_res = await client.post("/api/v1/auth/google", json={"credential": "mock-valid-id-token"})
    assert login2_res.status_code == 200
    user2 = login2_res.json()["user"]
    # Same user ID, no duplicate created
    assert user2["id"] == user1["id"]

    # 3. Simulate Safe Account Linking:
    # Existing user registered with password
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "existing_dev@company.com",
        "password": "Password123!",
        "name": "Dev User"
    })
    assert reg_res.status_code == 200
    existing_user_id = reg_res.json()["user"]["id"]

    # Dev user logs in with Google with matching verified email
    async def mock_verify_link(id_token: str, expected_client_id=None):
        return True, GoogleUserInfo(
            google_sub="google-sub-9999",
            email="existing_dev@company.com",
            email_verified=True,
            name="Dev User (Google)",
            picture="https://google.com/dev_photo.jpg"
        ), None

    monkeypatch.setattr(google_auth_service, "verify_id_token", mock_verify_link)

    link_res = await client.post("/api/v1/auth/google", json={"credential": "mock-link-token"})
    assert link_res.status_code == 200
    linked_user = link_res.json()["user"]
    # Safely linked to existing user ID, without duplicate
    assert linked_user["id"] == existing_user_id
    assert linked_user["google_sub"] == "google-sub-9999"

    # Verify linked accounts list
    acc_res = await client.get("/api/v1/auth/accounts", headers={"Authorization": f"Bearer {link_res.json()['access_token']}"})
    assert acc_res.status_code == 200
    providers = [a["provider"] for a in acc_res.json()]
    assert "password" in providers
    assert "google" in providers
