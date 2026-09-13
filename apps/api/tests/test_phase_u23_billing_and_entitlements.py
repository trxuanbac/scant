import pytest
from httpx import AsyncClient
from app.services.billing.plan_definitions import get_plan_entitlements
from app.services.billing.entitlement_service import entitlement_service

def test_entitlement_gating():
    # 1. Free Tier Checks
    ok_prem, _ = entitlement_service.check_feature_access("free", "premium_models")
    assert ok_prem is False

    assert entitlement_service.is_export_format_allowed("free", "docx") is True
    assert entitlement_service.is_export_format_allowed("free", "pdf") is False

    # 2. Pro Tier Checks
    ok_pro_prem, _ = entitlement_service.check_feature_access("pro", "premium_models")
    assert ok_pro_prem is True

    assert entitlement_service.is_export_format_allowed("pro", "pdf") is True


@pytest.mark.asyncio
async def test_billing_api(client: AsyncClient, monkeypatch):
    for name in ("PAYOS_CLIENT_ID", "PAYOS_API_KEY", "PAYOS_CHECKSUM_KEY"):
        monkeypatch.delenv(name, raising=False)
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "billable@company.com",
        "password": "Password123!",
        "name": "Billable User"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. List Plans
    plans_res = await client.get("/api/v1/billing/plans")
    assert plans_res.status_code == 200
    plans = plans_res.json()
    assert len(plans) >= 4

    # 2. My Entitlements
    ent_res = await client.get("/api/v1/billing/my-entitlements", headers=headers)
    assert ent_res.status_code == 200
    assert ent_res.json()["plan_tier"] == reg_res.json()["user"]["plan"]

    # 3. Create Checkout Session
    checkout_res = await client.post("/api/v1/billing/checkout", json={
        "plan_tier": "pro",
        "success_url": "http://localhost:3050/settings",
        "cancel_url": "http://localhost:3050/settings"
    }, headers=headers)
    assert checkout_res.status_code == 503  # Unconfigured provider must never fabricate checkout.
