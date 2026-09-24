from types import SimpleNamespace

import pytest

from app.services.agent.report_research_contracts import ImagePlanItem
from app.services.assets.auto_report_image_service import auto_report_image_service
from app.services.exports.docx_exporter import DocxExporter


def paragraph(text: str):
    return {"type": "paragraph", "content": [{"type": "text", "text": text}]}


def test_image_plan_skips_front_matter_and_uses_explicit_marker():
    sections = [
        SimpleNamespace(id="intro", title="LỜI MỞ ĐẦU", level=1, plain_text="Mở đầu", content_json={}),
        SimpleNamespace(
            id="architecture",
            title="Kiến trúc hệ thống",
            level=1,
            plain_text=(
                "Nội dung phân tích kiến trúc.\n\n"
                "[[IMAGE:title=Sơ đồ kiến trúc;prompt=kiến trúc điện toán đám mây]]"
            ),
            content_json={},
        ),
        SimpleNamespace(id="refs", title="TÀI LIỆU THAM KHẢO", level=1, plain_text="", content_json={}),
    ]

    plan = auto_report_image_service.plan(sections, "Điện toán đám mây")

    assert len(plan) == 1
    assert plan[0].section_id == "architecture"
    assert plan[0].query == "kiến trúc điện toán đám mây"
    assert plan[0].caption == "Sơ đồ kiến trúc"


def test_image_plan_automatically_selects_a_relevant_section_without_marker():
    sections = [
        SimpleNamespace(id="overview", title="1. Tổng quan thị trường", level=1, plain_text="Phân tích quy mô và bối cảnh.", content_json={}),
        SimpleNamespace(id="risk", title="2. Rủi ro", level=1, plain_text="Phân tích rủi ro.", content_json={}),
        SimpleNamespace(id="refs", title="TÀI LIỆU THAM KHẢO", level=1, plain_text="", content_json={}),
    ]

    plan = auto_report_image_service.plan(sections, "Thị trường xe điện Việt Nam")

    assert len(plan) == 1
    assert plan[0].section_id == "overview"
    assert "Thị trường xe điện Việt Nam" in plan[0].query
    assert plan[0].purpose.startswith("Tự động")


def test_automatic_image_plan_removes_report_boilerplate_from_search_query():
    sections = [
        SimpleNamespace(
            id="overview",
            title="CHƯƠNG 1: TỔNG QUAN VỀ ĐỀ TÀI",
            level=1,
            position=1,
            plain_text="Tổng quan.",
            content_json={},
        ),
    ]

    plan = auto_report_image_service.plan(
        sections,
        "Báo cáo thử nghiệm về chuyển đổi số tại Việt Nam",
    )

    assert len(plan) == 1
    assert plan[0].query == "chuyển đổi số tại Việt Nam"


def test_image_search_builds_an_english_fallback_for_vietnamese_topics():
    assert auto_report_image_service._english_fallback_query(
        "Phân tích thị trường xe điện Việt Nam"
    ) == "Vietnam electric vehicle market"


def test_image_candidate_relevance_rejects_unrelated_title():
    assert auto_report_image_service._candidate_score(
        "kiến trúc điện toán đám mây",
        {"title": "Công thức nấu cà phê", "sourceDomain": "food.example"},
    ) == 0


@pytest.mark.asyncio
async def test_unrelated_search_results_are_not_imported(monkeypatch):
    section = SimpleNamespace(
        id="section-1",
        title="Kiến trúc",
        plain_text="Nội dung.\n\n[[IMAGE:title=Sơ đồ;prompt=kiến trúc điện toán đám mây]]",
        content_json={"type": "doc", "content": [paragraph("Nội dung."), paragraph("[[IMAGE:title=Sơ đồ;prompt=kiến trúc điện toán đám mây]]")]},
    )
    imported = []

    async def fake_search(_query, license_mode="all", max_results=12):
        return {"provider": "openverse", "results": [{"id": "wrong", "title": "Công thức nấu cà phê", "imageUrl": "https://example.org/wrong.png", "thumbnailUrl": "https://example.org/thumb.png"}]}

    async def fake_import(_db, **kwargs):
        imported.append(kwargs["result"]["id"])
        return SimpleNamespace(id="wrong")

    async def fake_update(_db, db_obj, obj_in):
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(id="plan", section_id="section-1", query="kiến trúc điện toán đám mây", purpose="Minh họa", caption="Sơ đồ", alt_text="Sơ đồ"),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert result.status == "skipped"
    assert imported == []


@pytest.mark.asyncio
async def test_automatic_image_search_retries_with_translated_query(monkeypatch, tmp_path):
    section = SimpleNamespace(
        id="section-1",
        title="Tổng quan thị trường",
        plain_text="Nội dung.",
        content_json={"type": "doc", "content": [paragraph("Nội dung.")]},
    )
    queries = []
    imported = []
    local_image = tmp_path / "ev.jpg"
    local_image.write_bytes(b"local image fixture")

    async def fake_search(query, license_mode="all", max_results=12):
        queries.append(query)
        if query == "Vietnam electric vehicle market":
            return {
                "provider": "openverse",
                "results": [{
                    "id": "ev",
                    "title": "Vietnam electric vehicle",
                    "imageUrl": "https://example.org/ev.jpg",
                    "thumbnailUrl": "https://example.org/ev-thumb.jpg",
                    "sourcePageUrl": "https://example.org/ev",
                }],
            }
        return {
            "provider": "openverse",
            "results": [{
                "id": "weak-vietnamese-result",
                "title": "Việt Nam",
                "imageUrl": "https://example.org/vietnam.jpg",
                "thumbnailUrl": "https://example.org/vietnam-thumb.jpg",
                "sourcePageUrl": "https://example.org/vietnam",
            }],
        }

    async def fake_import(_db, **kwargs):
        imported.append(kwargs["result"]["id"])
        return SimpleNamespace(
            id="asset-ev",
            width=1000,
            storage_path=str(local_image),
            source_domain="example.org",
            source_page_url="https://example.org/ev",
            license="CC BY",
            attribution="Example",
        )

    async def fake_update(_db, db_obj, obj_in):
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(
            id="plan-ev",
            section_id="section-1",
            query="Phân tích thị trường xe điện Việt Nam",
            purpose="Tự động minh họa nội dung mục Tổng quan thị trường",
            caption="Thị trường xe điện",
            alt_text="Thị trường xe điện Việt Nam",
        ),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert queries == ["Phân tích thị trường xe điện Việt Nam", "Vietnam electric vehicle market"]
    assert imported == ["ev"]
    assert result.status == "inserted"


@pytest.mark.asyncio
async def test_image_without_source_page_is_not_imported(monkeypatch):
    section = SimpleNamespace(
        id="section-1",
        title="Thị trường xe điện",
        plain_text="Nội dung.",
        content_json={"type": "doc", "content": [paragraph("Nội dung.")]},
    )
    imported = []

    async def fake_search(_query, license_mode="all", max_results=12):
        return {
            "provider": "openverse",
            "results": [{
                "id": "no-provenance",
                "title": "Electric vehicle market",
                "imageUrl": "https://cdn.example.org/ev.jpg",
                "thumbnailUrl": "https://cdn.example.org/ev-thumb.jpg",
                "sourcePageUrl": None,
            }],
        }

    async def fake_import(_db, **kwargs):
        imported.append(kwargs["result"]["id"])
        return SimpleNamespace(id="asset-without-provenance")

    async def fake_update(_db, db_obj, obj_in):
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(
            id="plan-no-provenance",
            section_id="section-1",
            query="electric vehicle market",
            purpose="Minh họa thị trường",
            caption="Thị trường xe điện",
            alt_text="Thị trường xe điện",
        ),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert result.status == "skipped"
    assert imported == []


@pytest.mark.asyncio
async def test_image_import_skips_asset_without_existing_local_file(monkeypatch, tmp_path):
    section = SimpleNamespace(
        id="section-1",
        title="Thị trường xe điện",
        plain_text="Nội dung.",
        content_json={"type": "doc", "content": [paragraph("Nội dung.")]},
    )
    local_image = tmp_path / "downloaded-ev.jpg"
    local_image.write_bytes(b"local image fixture")
    attempts = []

    async def fake_search(_query, license_mode="all", max_results=12):
        return {
            "provider": "openverse",
            "results": [
                {
                    "id": "stale",
                    "title": "Electric vehicle market",
                    "imageUrl": "https://cdn.example.org/stale.jpg",
                    "thumbnailUrl": "https://cdn.example.org/stale-thumb.jpg",
                    "sourcePageUrl": "https://source.example.org/stale",
                },
                {
                    "id": "local",
                    "title": "Electric vehicle market",
                    "imageUrl": "https://cdn.example.org/local.jpg",
                    "thumbnailUrl": "https://cdn.example.org/local-thumb.jpg",
                    "sourcePageUrl": "https://source.example.org/local",
                },
            ],
        }

    async def fake_import(_db, **kwargs):
        result = kwargs["result"]
        attempts.append(result["id"])
        return SimpleNamespace(
            id=f"asset-{result['id']}",
            width=1000,
            storage_path=(
                str(tmp_path / "missing.jpg")
                if result["id"] == "stale"
                else str(local_image)
            ),
            source_domain="source.example.org",
            source_page_url=result["sourcePageUrl"],
            license="CC BY",
            attribution="Example",
        )

    async def fake_update(_db, db_obj, obj_in):
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(
            id="plan-local",
            section_id="section-1",
            query="electric vehicle market",
            purpose="Minh họa thị trường",
            caption="Thị trường xe điện",
            alt_text="Thị trường xe điện",
        ),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert attempts == ["stale", "local"]
    assert result.status == "inserted"
    assert result.asset.id == "asset-local"


@pytest.mark.asyncio
async def test_imported_web_image_becomes_stored_tiptap_node(monkeypatch):
    section = SimpleNamespace(
        id="section-1",
        title="Kiến trúc",
        plain_text="Nội dung chính.\n\n[[IMAGE:title=Sơ đồ;prompt=cloud architecture]]",
        content_json={"type": "doc", "content": [paragraph("Nội dung chính."), paragraph("[[IMAGE:title=Sơ đồ;prompt=cloud architecture]]")]},
    )
    asset = SimpleNamespace(
        id="asset-1",
        width=1200,
        source_domain="source.example",
        source_page_url="https://source.example/article",
        license="CC BY",
        attribution="Tác giả A",
    )

    async def fake_search(_query, license_mode="all", max_results=12):
        return {
            "provider": "openverse",
            "results": [
                {
                    "id": "image-1",
                    "title": "Cloud architecture diagram",
                    "imageUrl": "https://cdn.example/image.png",
                    "thumbnailUrl": "https://cdn.example/thumb.png",
                    "sourcePageUrl": "https://source.example/article",
                    "sourceDomain": "source.example",
                    "license": "CC BY",
                    "attribution": "Tác giả A",
                }
            ],
        }

    async def fake_import(_db, **_kwargs):
        return asset

    saved = {}

    async def fake_update(_db, db_obj, obj_in):
        saved.update(obj_in)
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(
            id="plan-1",
            section_id="section-1",
            query="cloud architecture",
            purpose="Minh họa kiến trúc",
            caption="Sơ đồ kiến trúc",
            alt_text="Sơ đồ kiến trúc đám mây",
        ),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    image_nodes = [node for node in result.content_json["content"] if node["type"] == "image"]
    assert result.status == "inserted"
    assert result.asset.id == "asset-1"
    assert len(image_nodes) == 1
    assert image_nodes[0]["attrs"]["assetId"] == "asset-1"
    assert image_nodes[0]["attrs"]["sourceUrl"] == "https://source.example/article"
    assert "[[IMAGE:" not in saved["plain_text"]


@pytest.mark.asyncio
async def test_image_import_tries_next_candidate_after_failure(monkeypatch):
    section = SimpleNamespace(
        id="section-1",
        title="Thị trường",
        plain_text="Nội dung.",
        content_json={"type": "doc", "content": [paragraph("Nội dung.")]},
    )
    attempts = []

    async def fake_search(_query, license_mode="all", max_results=12):
        return {
            "provider": "openverse",
            "results": [
                {"id": "bad", "title": "Thị trường", "imageUrl": "https://bad.example/a.png", "thumbnailUrl": "https://bad.example/t.png"},
                {"id": "good", "title": "Thị trường", "imageUrl": "https://good.example/a.png", "thumbnailUrl": "https://good.example/t.png"},
            ],
        }

    async def fake_import(_db, **kwargs):
        attempts.append(kwargs["result"]["id"])
        if kwargs["result"]["id"] == "bad":
            raise ValueError("bad image")
        return SimpleNamespace(id="asset-good", width=800, source_domain="good.example", source_page_url=None, license=None, attribution=None)

    async def fake_update(_db, db_obj, obj_in):
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.import_search_result", fake_import)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(id="plan-1", section_id="section-1", query="thị trường", purpose="Minh họa", caption="Thị trường", alt_text="Thị trường"),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert attempts == ["bad", "good"]
    assert result.asset.id == "asset-good"


@pytest.mark.asyncio
async def test_missing_image_result_removes_internal_marker(monkeypatch):
    section = SimpleNamespace(
        id="section-1",
        title="Kiến trúc",
        plain_text="Nội dung.\n\n[[IMAGE:title=Sơ đồ;prompt=cloud architecture]]",
        content_json={"type": "doc", "content": [paragraph("Nội dung."), paragraph("[[IMAGE:title=Sơ đồ;prompt=cloud architecture]]")]},
    )
    saved = {}

    async def fake_search(_query, license_mode="all", max_results=12):
        return {"provider": "openverse", "results": []}

    async def fake_update(_db, db_obj, obj_in):
        saved.update(obj_in)
        return db_obj

    monkeypatch.setattr("app.services.assets.auto_report_image_service.image_service.search_web_images", fake_search)
    monkeypatch.setattr("app.services.assets.auto_report_image_service.section_repo.update", fake_update)

    result = await auto_report_image_service.import_and_insert(
        object(),
        ImagePlanItem(id="plan-1", section_id="section-1", query="cloud architecture", purpose="Minh họa", caption="Sơ đồ", alt_text="Sơ đồ"),
        project_id="project-1",
        report_id="report-1",
        user_id="user-1",
        section=section,
    )

    assert result.status == "skipped"
    assert "[[IMAGE:" not in result.plain_text
    assert "[[IMAGE:" not in str(saved["content_json"])


def test_docx_image_source_line_keeps_page_attribution_and_license():
    asset = SimpleNamespace(
        source_domain="source.example",
        source_page_url="https://source.example/article",
        license="CC BY",
        attribution="Tác giả A",
    )

    text = DocxExporter._image_source_text({}, asset)

    assert "source.example" in text
    assert "https://source.example/article" in text
    assert "Tác giả A" in text
    assert "CC BY" in text
