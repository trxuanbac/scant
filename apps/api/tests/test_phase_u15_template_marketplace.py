import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.entities import Template
from app.repositories.base import BaseRepository


@pytest.mark.asyncio
async def test_template_marketplace_api(client: AsyncClient, db_session: AsyncSession):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "tplauthor@corp.com",
        "password": "Password123!",
        "name": "Template Author"
    })
    token = reg_res.json()["access_token"]
    user_id = reg_res.json()["user"]["id"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Seed a base public template
    tpl_repo = BaseRepository[Template](Template)
    public_tpl = await tpl_repo.create(db_session, obj_in={
        "name": "Executive Strategy Brief",
        "category": "business",
        "description": "Mẫu báo cáo chiến lược doanh nghiệp cấp cao",
        "visibility": "public",
        "is_public": True,
        "is_system": True,
        "author_name": "Studio Official",
    })

    # 2. List public templates
    list_pub = await client.get("/api/v1/templates?scope=public", headers=headers)
    assert list_pub.status_code == 200
    templates = list_pub.json()
    assert len(templates) >= 1

    # 3. Duplicate template
    dup_res = await client.post(f"/api/v1/templates/{public_tpl.id}/duplicate", headers=headers)
    assert dup_res.status_code == 200
    cloned_id = dup_res.json()["cloned_id"]

    # 4. List my templates
    list_my = await client.get("/api/v1/templates?scope=my", headers=headers)
    assert list_my.status_code == 200
    my_templates = list_my.json()
    assert any(t["id"] == cloned_id for t in my_templates)

    # 5. Publish my template to Marketplace
    pub_res = await client.post(f"/api/v1/templates/{cloned_id}/publish", headers=headers)
    assert pub_res.status_code == 200
    assert pub_res.json()["visibility"] == "public"

    # 6. Unpublish
    unpub_res = await client.post(f"/api/v1/templates/{cloned_id}/unpublish", headers=headers)
    assert unpub_res.status_code == 200
    assert unpub_res.json()["visibility"] == "my"

    # 7. Record usage
    use_res = await client.post(f"/api/v1/templates/{public_tpl.id}/use", headers=headers)
    assert use_res.status_code == 200
