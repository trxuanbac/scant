import pytest
import pandas as pd
from app.services.agent.spreadsheet_agent import (
    spreadsheet_agent,
    DeterministicSpreadsheetEngine,
)


def test_deterministic_engine_kpi_and_provenance():
    # Mock sales dataframe
    data = {
        "region": ["Bắc", "Trung", "Nam", "Bắc", "Nam"],
        "revenue": [100.0, 150.0, 200.0, 120.0, 180.0],
        "profit": [20.0, 35.0, 50.0, 25.0, 40.0],
        "orders": [10, 15, 20, 12, 18],
    }
    df = pd.DataFrame(data)

    # 1. Inspect & Profile
    insp = DeterministicSpreadsheetEngine.inspect_dataframe(df)
    assert insp["num_rows"] == 5
    assert insp["num_cols"] == 4

    profile = DeterministicSpreadsheetEngine.profile_data(df)
    assert profile["duplicate_rows_count"] == 0
    assert profile["numeric_summary"]["revenue"]["mean"] == 150.0

    # 2. Calculate KPIs with Provenance
    kpis = DeterministicSpreadsheetEngine.calculate_kpis(
        df=df,
        dataset_name="sales_q2_2026.xlsx",
        kpi_specs=[
            {"name": "Tổng Doanh Thu", "column": "revenue", "op": "sum"},
            {"name": "Lợi Nhuận Trung Bình", "column": "profit", "op": "avg"},
        ]
    )

    assert len(kpis) == 2
    assert kpis[0]["value"] == 750.0
    assert kpis[0]["provenance"]["dataset"] == "sales_q2_2026.xlsx"
    assert kpis[0]["provenance"]["computed_deterministically"] is True
    assert kpis[1]["value"] == 34.0

    # 3. Group and Aggregate
    grouped = DeterministicSpreadsheetEngine.aggregate_and_group(df, group_col="region", val_col="revenue", op="sum")
    records = {r["category"]: r["value"] for r in grouped["grouped_data"]}
    assert records["Bắc"] == 220.0
    assert records["Nam"] == 380.0


@pytest.mark.asyncio
async def test_spreadsheet_agent_narrative(deterministic_ai_provider):
    df = pd.DataFrame({
        "department": ["IT", "Marketing", "Sales", "HR"],
        "budget": [50000.0, 30000.0, 80000.0, 20000.0],
        "spend": [45000.0, 28000.0, 76000.0, 18000.0],
    })

    result = await spreadsheet_agent.analyze_and_narrate(
        df=df,
        dataset_name="dept_budget.csv",
        user_query="Đánh giá tình hình giải ngân ngân sách các phòng ban"
    )

    assert "narrative" in result
    assert len(result["narrative"]) > 0
    assert result["provenance_count"] >= 2
    assert len(result["kpis"]) >= 2
