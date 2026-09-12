import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from app.main import app
from app.core.database import Base, get_db
from app.services.research.search_engine import search_engine
from app.services.research.source_ranker import source_ranker
from app.services.citations.citation_formatter import citation_formatter
from app.services.citations.claim_validator import claim_validator

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"
test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestAsyncSession = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with TestAsyncSession() as session:
        yield session
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function")
async def client(db_session: AsyncSession):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.mark.live
@pytest.mark.asyncio
async def test_search_and_ranking():
    provider = search_engine.get_search_provider()
    results = await provider.search("ASP.NET Core MVC architecture", max_results=5)
    assert len(results) > 0
    ranked = source_ranker.rank_sources(results)
    assert ranked[0]["reliability_score"] >= 0.90


def test_citation_formatter():
    in_text_ieee = citation_formatter.format_in_text(1, style="IEEE")
    assert in_text_ieee == "[1]"

    in_text_apa = citation_formatter.format_in_text(1, author="Smith, John", year="2024", style="APA")
    assert in_text_apa == "(Smith, 2024)"

    bib = citation_formatter.format_bibliography_entry(
        index=1,
        source={
            "title": "ASP.NET Core Architecture",
            "authors": "Microsoft Learn Team",
            "publisher": "Microsoft",
            "published_date": "2024",
            "url": "https://learn.microsoft.com"
        },
        style="IEEE"
    )
    assert "[1] Microsoft Learn Team" in bib


def test_anti_hallucination_claim_validation():
    sources_map = {
        1: {
            "id": "src_1",
            "title": "ASP.NET Core Documentation",
            "url": "https://learn.microsoft.com",
            "snippet": "ASP.NET Core is an open-source web framework.",
            "reliability_score": 0.98
        }
    }

    # Case 1: Valid claim mapped to genuine source [1]
    valid_text = "ASP.NET Core là framework mã nguồn mở hiệu năng cao của Microsoft [1]."
    val_res = claim_validator.validate_and_map_claims(valid_text, sources_map)
    assert val_res["is_verified"] is True
    assert len(val_res["verified_claims"]) == 1
    assert val_res["verified_claims"][0]["source_id"] == "src_1"

    # Case 2: Hallucinated claim [99] not in sources_map
    hallucinated_text = "Tính năng này đã được chứng minh tăng tốc độ 500% [99]."
    halluc_res = claim_validator.validate_and_map_claims(hallucinated_text, sources_map)
    assert halluc_res["is_verified"] is False
    assert "[99]" in halluc_res["unverified_citations"]


@pytest.mark.live
@pytest.mark.asyncio
async def test_research_api_flow(client: AsyncClient):
    # 1. Register & Project
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "researcher@test.com",
        "password": "Password123!",
        "name": "Hoang Van D"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    proj_res = await client.post("/api/v1/projects", json={
        "name": "Nghiên cứu ASP.NET Core MVC",
        "type": "academic"
    }, headers=headers)
    project_id = proj_res.json()["id"]

    # 2. Run Web Research
    res_search = await client.post(f"/api/v1/research/search?project_id={project_id}&query=ASP.NET%20Core%20MVC&mode=quick", headers=headers)
    assert res_search.status_code == 200
    search_data = res_search.json()
    assert search_data["sources_found"] > 0

    # 3. List Project Sources
    sources_res = await client.get(f"/api/v1/research/sources/project/{project_id}", headers=headers)
    assert sources_res.status_code == 200
    sources_list = sources_res.json()
    assert len(sources_list) >= 1
    assert sources_list[0]["reliability_score"] >= 0.8
