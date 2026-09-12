import pytest
import pandas as pd
from app.services.research.research_search_service import research_search_service
from app.services.citations.source_verification_service import source_verification_service
from app.services.citations.evidence_service import evidence_service
from app.services.citations.citation_service import citation_service
from app.services.citations.citation_formatter import CitationFormatter


@pytest.mark.live
@pytest.mark.asyncio
async def test_multi_provider_search_anti_hallucination():
    """Verify search returns real data and never hallucinated results for gibberish."""
    gibberish_query = "xyzqqq999zzznonexistentpaper12345"
    results = await research_search_service.search_all(query=gibberish_query, limit=5)
    assert len(results) == 0, "System must not hallucinate fake papers for non-existent queries!"


@pytest.mark.live
@pytest.mark.asyncio
async def test_source_verification_scoring():
    """Verify 100-point formula and domain trust categorization."""
    # Test valid academic DOI
    valid_doi = "10.1038/nature12373"
    res = await source_verification_service.verify_source_metadata(
        doi=valid_doi,
        title="Test Nature Paper",
        authors="Nature Author",
        publisher="Nature Publishing Group",
    )
    assert res.verification_score > 40
    assert "doi_resolved" in res.checklist
    assert res.domain_trust in ["ACADEMIC", "OFFICIAL", "GENERAL_WEB", "UNKNOWN"]

    # Test broken URL
    broken_url = "https://this-domain-definitely-does-not-exist-123456789.org/test"
    broken_res = await source_verification_service.verify_url(broken_url)
    assert broken_res.verification_status == "BROKEN_SOURCE"
    assert broken_res.verification_score == 0


def test_evidence_text_chunking():
    """Verify paragraph splitting and character offsets."""
    text = (
        "Báo cáo này phân tích tình hình thị trường năng lượng tái tạo tại Việt Nam trong năm 2026.\n\n"
        "Theo số liệu từ Tập đoàn Điện lực, công suất điện mặt trời và điện gió đã tăng trưởng 24% so với cùng kỳ.\n\n"
        "Các chính sách hỗ trợ giá FIT và cơ chế mua bán điện trực tiếp (DPPA) đang tạo động lực lớn cho nhà đầu tư."
    )
    chunks = evidence_service.extract_evidence_from_text(text=text, evidence_type="WEB_TEXT")
    assert len(chunks) == 3
    for c in chunks:
        assert len(c["quote"]) >= 20
        assert c["start_offset"] is not None
        assert c["end_offset"] > c["start_offset"]
        assert c["normalized_text"]


def test_excel_range_evidence_calculation(tmp_path):
    """Verify genuine Excel cell range calculation and evidence quote generation."""
    test_file = tmp_path / "test_salary.xlsx"
    df = pd.DataFrame({
        "STT": [1, 2, 3, 4, 5],
        "Ten": ["Nguyen Van A", "Tran Thi B", "Le Van C", "Pham Thi D", "Hoang Van E"],
        "Luong": [15000000, 22000000, 18500000, 30000000, 25000000],
    })
    with pd.ExcelWriter(test_file, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Bang_luong", index=False)

    # Calculate SUM of Luong column (C2:C6 in 1-based indexing)
    res_sum = evidence_service.calculate_excel_evidence(
        file_path=str(test_file),
        sheet_name="Bang_luong",
        cell_range="C2:C6",
        operation="SUM",
    )
    assert res_sum["operation"] == "SUM"
    assert "110,500,000" in res_sum["calculation_result"] or "110500000" in res_sum["calculation_result"]
    assert "Bang_luong" in res_sum["quote"]

    # Calculate COUNT
    res_count = evidence_service.calculate_excel_evidence(
        file_path=str(test_file),
        sheet_name="Bang_luong",
        cell_range="C2:C6",
        operation="COUNT",
    )
    assert "5 giá trị" in res_count["calculation_result"]

    # Calculate AVG
    res_avg = evidence_service.calculate_excel_evidence(
        file_path=str(test_file),
        sheet_name="Bang_luong",
        cell_range="C2:C6",
        operation="AVG",
    )
    assert "22,100,000" in res_avg["calculation_result"] or "22100000" in res_avg["calculation_result"]


def test_evidence_support_evaluation():
    """Verify evidence support level assessment."""
    claim_strong = "Tổng quỹ lương tháng 8 đạt 110,500,000 đồng với mức tăng 24%."
    evidence_strong = "Theo bảng lương tháng 8, tổng chi trả quỹ lương là 110,500,000 đồng, ghi nhận mức tăng 24% so với tháng trước."
    eval_strong = citation_service.evaluate_evidence_support(claim_strong, evidence_strong)
    assert eval_strong["support_level"] in ["STRONG", "MODERATE"]
    assert "110,500,000" in eval_strong["matched_numbers"] or "24%" in eval_strong["matched_numbers"] or len(eval_strong["matched_numbers"]) > 0

    claim_unrelated = "Giá dầu thô trên thị trường New York giảm 5%."
    evidence_unrelated = "Lượng khách du lịch đến Nha Trang tăng trưởng mạnh trong quý 3."
    eval_unrelated = citation_service.evaluate_evidence_support(claim_unrelated, evidence_unrelated)
    assert eval_unrelated["support_level"] in ["WEAK", "UNSUPPORTED"]


def test_citation_formatter():
    """Verify academic citation styles: IEEE, APA, Harvard, BibTeX."""
    source_sample = {
        "title": "Quantum Computing and Post-Quantum Cryptography",
        "authors": "Nguyen, V. A. and Smith, J.",
        "publisher": "IEEE Transactions on Information Theory",
        "published_date": "2025",
        "url": "https://doi.org/10.1109/TIT.2025.12345",
        "doi": "10.1109/TIT.2025.12345",
    }
    # IEEE
    ieee_bib = CitationFormatter.format_bibliography_entry(1, source_sample, style="IEEE")
    assert "[1]" in ieee_bib
    assert "Quantum Computing" in ieee_bib

    # APA
    apa_in_text = CitationFormatter.format_in_text(1, author="Nguyen", year="2025", style="APA")
    assert apa_in_text == "(Nguyen, 2025)"

    # BibTeX
    bibtex = CitationFormatter.format_bibtex(1, source_sample)
    assert "@article{" in bibtex
    assert "title = {Quantum Computing and Post-Quantum Cryptography}" in bibtex


from httpx import AsyncClient


@pytest.mark.live
@pytest.mark.asyncio
async def test_sources_api_e2e(client: AsyncClient):
    """End-to-end verification of Source Library, Evidence, and Citation APIs."""
    # 1. Register & Login User
    reg_resp = await client.post("/api/v1/auth/register", json={
        "email": "source_tester@ai-studio.vn",
        "password": "SecurePassword123!",
        "name": "Research Lead",
    })
    assert reg_resp.status_code == 200
    token = reg_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Project
    proj_resp = await client.post("/api/v1/projects", json={
        "name": "Dự Án Nghiên Cứu Xe Điện 2026",
        "type": "research",
        "description": "Nghiên cứu thị trường và công nghệ xe điện tại Việt Nam",
    }, headers=headers)
    assert proj_resp.status_code == 201
    project_id = proj_resp.json()["id"]

    # 3. Add Source via URL
    url_resp = await client.post(f"/api/v1/projects/{project_id}/sources/url", json={
        "url": "https://learn.microsoft.com/en-us/dotnet/core/whats-new/dotnet-9/overview",
        "title": "What's new in .NET 9",
        "notes": "Tài liệu chính thức từ Microsoft Learn",
    }, headers=headers)
    assert url_resp.status_code == 200
    src_data = url_resp.json()["source"]
    assert src_data["title"]
    assert src_data["verification_status"] in ["VERIFIED", "PARTIALLY_VERIFIED"]
    source_id = src_data["id"]

    # 4. List Sources with live stats
    list_resp = await client.get(f"/api/v1/projects/{project_id}/sources", headers=headers)
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["stats"]["total_sources"] >= 1
    assert len(list_data["sources"]) >= 1

    # 5. Add Evidence Chunk
    ev_resp = await client.post(f"/api/v1/sources/{source_id}/evidences", json={
        "evidence_type": "WEB_TEXT",
        "quote": ".NET 9 delivers significant improvements in cloud-native apps and performance.",
        "section_title": "Performance Overview",
    }, headers=headers)
    assert ev_resp.status_code == 200
    evidence_id = ev_resp.json()["evidence"]["id"]

    # 6. Verify Claim Support
    verify_support_resp = await client.post("/api/v1/citations/verify-support", json={
        "claim_text": ".NET 9 cải thiện hiệu năng đáng kể cho cloud-native apps.",
        "evidence_text": ".NET 9 delivers significant improvements in cloud-native apps and performance.",
    }, headers=headers)
    assert verify_support_resp.status_code == 200
    assert verify_support_resp.json()["support_level"] in ["STRONG", "MODERATE"]

    # 7. Safe Delete Check (Uncited source deletes safely)
    del_resp = await client.delete(f"/api/v1/sources/{source_id}", headers=headers)
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True

