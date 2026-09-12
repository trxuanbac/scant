import pytest
from httpx import AsyncClient
from app.repositories.user_repo import user_repo


@pytest.mark.asyncio
async def test_admin_console_access_control(client: AsyncClient, db_session):
    # 1. Normal User (Non-Admin)
    reg_normal = await client.post("/api/v1/auth/register", json={
        "email": "employee@saas.com",
        "password": "Password123!",
        "name": "Normal Employee"
    })
    normal_token = reg_normal.json()["access_token"]
    normal_headers = {"Authorization": f"Bearer {normal_token}"}

    # Normal user trying to access /admin -> must get 403 Forbidden
    forbidden_res = await client.get("/api/v1/admin/dashboard", headers=normal_headers)
    assert forbidden_res.status_code == 403

    # 2. Super Admin User
    reg_admin = await client.post("/api/v1/auth/register", json={
        "email": "root_admin@saas.com",
        "password": "Password123!",
        "name": "Root SuperAdmin"
    })
    admin_token = reg_admin.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # Elevate to superuser in DB
    admin_user = await user_repo.get_by_email(db_session, "root_admin@saas.com")
    await user_repo.update(db_session, db_obj=admin_user, obj_in={"is_superuser": True})

    # Super Admin accessing dashboard -> 200 OK
    dash_res = await client.get("/api/v1/admin/dashboard", headers=admin_headers)
    assert dash_res.status_code == 200
    metrics = dash_res.json()
    assert any(metric["key"] == "total_users" for metric in metrics["metrics"])
    assert "unavailable" in metrics

    # Super Admin lists users
    users_res = await client.get("/api/v1/admin/users", headers=admin_headers)
    assert users_res.status_code == 200
    assert len(users_res.json()["items"]) >= 2

    # Super Admin updates user plan
    target_id = reg_normal.json()["user"]["id"]
    patch_res = await client.patch(f"/api/v1/admin/users/{target_id}", json={
        "plan_tier": "enterprise", "reason": "Approved enterprise upgrade"
    }, headers=admin_headers)
    assert patch_res.status_code == 200
    assert patch_res.json()["plan"] == "enterprise"

    # AI Ops status
    ops_res = await client.get("/api/v1/admin/system/health", headers=admin_headers)
    assert ops_res.status_code == 200
    assert "database" in ops_res.json()
