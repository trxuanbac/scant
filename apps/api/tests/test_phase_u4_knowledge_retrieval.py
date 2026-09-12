import pytest
from httpx import AsyncClient
from app.services.knowledge.chunker import document_chunker
from app.services.knowledge.retrieval_service import retrieval_service


def test_document_chunker_and_retrieval():
    long_text = (
        "Thị trường xe điện tại Việt Nam đang chứng kiến sự tăng trưởng vượt bậc trong năm 2026. "
        "Các chính sách ưu đãi thuế tiêu thụ đặc biệt và miễn lệ phí trước bạ tiếp tục tạo động lực mạnh mẽ. "
        "\n\n"
        "Về hạ tầng trạm sạc, mạng lưới trạm sạc công cộng đã phủ sóng hơn 80% các tuyến quốc lộ trọng điểm. "
        "Các nhà sản xuất nội địa đang dẫn đầu thị phần với hơn 70% doanh số xe bán ra toàn quốc. "
        "\n\n"
        "Tuy nhiên, thách thức lớn nhất vẫn là chi phí pin và thời gian sạc nhanh tại các đô thị loại 2 và 3."
    )

    chunks = document_chunker.chunk_text(long_text, chunk_size=20, overlap=5)
    assert len(chunks) >= 2

    docs = [{"id": "doc_1", "original_name": "BaoCaoThiTruongEV.pdf", "content_text": long_text}]
    results = retrieval_service.search_relevant_chunks("hạ tầng trạm sạc quốc lộ", docs, top_k=2)

    assert len(results) > 0
    assert "trạm sạc" in results[0]["text"]
    assert results[0]["relevance_score"] > 0


@pytest.mark.asyncio
async def test_knowledge_search_api_flow(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "analyst_rag@corp.com",
        "password": "Password123!",
        "name": "RAG Analyst"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Báo cáo Thị trường Năng lượng 2026",
        "type": "market_research"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    # Upload TXT knowledge file
    sample_content = b"Nang luong tai tao chiem 35% tong san luong dien quoc gia trong nam 2026."
    files = {"file": ("energy_report.txt", sample_content, "text/plain")}
    data = {"project_id": project_id, "document_type": "reference"}
    upload_res = await client.post("/api/v1/files/upload", data=data, files=files, headers=headers)
    assert upload_res.status_code == 200

    # Search knowledge base
    search_res = await client.get(f"/api/v1/files/project/{project_id}/search?query=tai+tao", headers=headers)
    assert search_res.status_code == 200
    search_data = search_res.json()
    assert len(search_data) > 0
    assert "tai tao" in search_data[0]["text"].lower()
