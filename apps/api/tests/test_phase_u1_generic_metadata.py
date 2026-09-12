import pytest
from httpx import AsyncClient
from app.services.metadata.metadata_helper import metadata_helper


def test_metadata_helper_defaults_and_normalization():
    # 1. Test default fields for business report
    biz_fields = metadata_helper.get_default_fields_for_type("business_report")
    assert any(f.key == "company_name" for f in biz_fields)
    assert any(f.key == "author_name" for f in biz_fields)

    # 2. Test default fields for financial
    fin_fields = metadata_helper.get_default_fields_for_type("financial")
    assert any(f.key == "fiscal_year" for f in fin_fields)

    # 3. Test normalization of legacy data
    legacy = {"university": "BK Corp", "student_name": "Nguyen Lead"}
    normalized = metadata_helper.normalize_metadata(project_type="business_report", legacy_topic_details=legacy)
    assert len(normalized["custom_fields"]) >= 2
    assert any(f["key"] == "university" and f["value"] == "BK Corp" for f in normalized["custom_fields"])


@pytest.mark.asyncio
async def test_universal_project_api_crud(client: AsyncClient):
    # 1. Register & Auth
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "corp_analyst@enterprise.com",
        "password": "Password123!",
        "name": "Alex Nguyen"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Business Report Project with Custom Metadata
    biz_proj = {
        "name": "Báo cáo Chiến lược Thâm nhập Thị trường EV 2026",
        "type": "business_report",
        "description": "Báo cáo phân tích đối thủ và chiến lược mở rộng thị trường xe điện tại Đông Nam Á.",
        "metadata": {
            "document_type": "business_report",
            "audience": "Hội đồng Quản trị & Nhà đầu tư",
            "custom_fields": [
                {"key": "company_name", "label": "Tên Doanh Nghiệp", "type": "text", "required": True, "value": "VinFast Global"},
                {"key": "lead_author", "label": "Giám đốc Chiến lược", "type": "text", "required": True, "value": "Alex Nguyen"},
                {"key": "target_market", "label": "Thị trường Mục tiêu", "type": "select", "options": ["VN", "ID", "PH"], "value": "ID"},
                {"key": "projected_investment", "label": "Vốn đầu tư dự kiến", "type": "currency", "unit": "USD", "value": "50,000,000"},
            ]
        }
    }

    create_res = await client.post("/api/v1/projects", json=biz_proj, headers=headers)
    assert create_res.status_code == 201
    proj_data = create_res.json()
    assert proj_data["type"] == "business_report"
    assert proj_data["metadata_json"]["custom_fields"][0]["value"] == "VinFast Global"

    # 3. Retrieve Project Detail
    proj_id = proj_data["id"]
    get_res = await client.get(f"/api/v1/projects/{proj_id}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["metadata_json"]["audience"] == "Hội đồng Quản trị & Nhà đầu tư"
