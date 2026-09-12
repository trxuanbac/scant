import pytest
from httpx import AsyncClient
from app.services.data.connectors import get_connector, CSVConnector, PostgreSQLConnector, MySQLConnector, RESTAPIConnector
from app.services.data.smart_mapping_service import smart_mapping_service
from app.services.data.dependency_graph_service import dependency_graph_service


@pytest.mark.asyncio
async def test_connectors_unit():
    # PostgreSQL Connector
    pg = get_connector("postgresql", {"host": "localhost", "port": 5432, "database": "sales_db"})
    assert isinstance(pg, PostgreSQLConnector)
    test_res = await pg.test_connection()
    assert test_res["status"] == "connected"
    schema = await pg.get_schema()
    assert "tables" in schema
    preview = await pg.preview(limit=2)
    assert len(preview) == 2

    # MySQL Connector
    my = get_connector("mysql", {"host": "localhost", "database": "warehouse"})
    assert isinstance(my, MySQLConnector)
    my_schema = await my.get_schema()
    assert "columns" in my_schema

    # REST Connector
    rest = get_connector("rest", {"url": "https://api.example.com/v1/metrics"})
    assert isinstance(rest, RESTAPIConnector)
    rest_schema = await rest.get_schema()
    assert rest_schema["endpoint"] == "https://api.example.com/v1/metrics"


def test_smart_mapping_memory():
    cols1 = ["Doanh thu", "Chi phí", "Lợi nhuận thuần", "Khu vực"]
    mapping = smart_mapping_service.infer_canonical_mapping(cols1)
    assert mapping["Doanh thu"] == "revenue"
    assert mapping["Chi phí"] == "cost"
    assert mapping["Lợi nhuận thuần"] == "profit"
    assert mapping["Khu vực"] == "region"

    fp1 = smart_mapping_service.compute_fingerprint(cols1)
    fp2 = smart_mapping_service.compute_fingerprint(["Khu vực", "Doanh thu", "Chi phí", "Lợi nhuận thuần"])
    assert fp1 == fp2  # deterministic fingerprint regardless of column ordering


def test_dependency_graph_invalidation():
    report_id = "rep-001"
    # DAG: dataset_1 -> kpi_revenue -> chart_revenue -> section_exec_summary
    #      dataset_1 -> chart_sales
    #      dataset_2 -> section_appendix
    dependency_graph_service.register_dependency(report_id, "dataset_1", "kpi_revenue")
    dependency_graph_service.register_dependency(report_id, "kpi_revenue", "chart_revenue")
    dependency_graph_service.register_dependency(report_id, "chart_revenue", "section_exec_summary")
    dependency_graph_service.register_dependency(report_id, "dataset_1", "chart_sales")
    dependency_graph_service.register_dependency(report_id, "dataset_2", "section_appendix")

    stale = dependency_graph_service.invalidate_source(report_id, "dataset_1")
    assert "kpi_revenue" in stale
    assert "chart_revenue" in stale
    assert "section_exec_summary" in stale
    assert "chart_sales" in stale
    assert "section_appendix" not in stale  # unaffected section remains clean!


@pytest.mark.asyncio
async def test_data_connectors_api(client: AsyncClient):
    reg_res = await client.post("/api/v1/auth/register", json={
        "email": "dataengineer@corp.com",
        "password": "Password123!",
        "name": "Data Engineer"
    })
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Test Connector
    conn_res = await client.post("/api/v1/data/connectors/test", json={
        "connector_type": "postgresql",
        "config": {"host": "prod-db.corp.internal", "database": "finance"}
    }, headers=headers)
    assert conn_res.status_code == 200
    assert conn_res.json()["status"] == "connected"

    # 2. Smart Mapping API
    map_res = await client.post("/api/v1/data/mapping/infer", json={
        "columns": ["Sales Amount", "Total Cost", "Order Date"]
    }, headers=headers)
    assert map_res.status_code == 200
    m_data = map_res.json()
    assert m_data["mapping"]["Sales Amount"] == "revenue"
    assert m_data["mapping"]["Total Cost"] == "cost"
    assert m_data["mapping"]["Order Date"] == "date"

    # 3. Dependency Graph API
    dep_reg = await client.post("/api/v1/data/dependency/register", json={
        "report_id": "rep-test-100",
        "source_node": "erp_dataset",
        "target_node": "section_3_financials"
    }, headers=headers)
    assert dep_reg.status_code == 200

    dep_inv = await client.post("/api/v1/data/dependency/invalidate", json={
        "report_id": "rep-test-100",
        "source_node": "erp_dataset"
    }, headers=headers)
    assert dep_inv.status_code == 200
    assert "section_3_financials" in dep_inv.json()["stale_nodes"]
