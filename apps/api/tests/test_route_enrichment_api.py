import io

import openpyxl
import pytest
import httpx

from app.api.v1 import route_enrichment
from app.core.config import settings
from app.services.data.google_routes import GoogleRoutesClient
from app.services.data.route_enrichment import RouteMeasurement, Waypoint


def make_workbook():
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Kho đi", "Lộ trình", "Link ggmap", "km 1 chiều DP đo"])
    sheet.append(["BN Mega SOC", "Hub A", None, None])
    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


@pytest.mark.asyncio
async def test_google_routes_uses_verified_waypoints_and_distance_meters():
    def handler(request):
        assert request.url == "https://routes.googleapis.com/directions/v2:computeRoutes"
        assert request.headers["x-goog-api-key"] == "test-key"
        assert request.headers["x-goog-fieldmask"] == "routes.distanceMeters,routes.legs.distanceMeters"
        import json
        body = json.loads(request.content)
        assert body["travelMode"] == "DRIVE"
        assert body["routingPreference"] == "TRAFFIC_AWARE"
        assert body["optimizeWaypointOrder"] is False
        assert body["intermediates"][0]["location"]["latLng"]["latitude"] == 21.12
        return httpx.Response(200, json={"routes": [{"distanceMeters": 25432, "legs": [{"distanceMeters": 12000}, {"distanceMeters": 13432}]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        routes = GoogleRoutesClient("test-key", http_client)
        result = await routes.compute_distance_meters([
            Waypoint("A", 21.0, 105.0), Waypoint("B", 21.12, 106.0), Waypoint("C", 21.2, 106.2)
        ])
    assert result == RouteMeasurement(25432, (12000, 13432))


@pytest.mark.asyncio
async def test_google_routes_rejects_invalid_key_as_provider_failure():
    from app.services.data.google_routes import RoutesProviderError

    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(403))) as http_client:
        routes = GoogleRoutesClient("bad-key", http_client)
        with pytest.raises(RoutesProviderError, match="API key"):
            await routes.compute_distance_meters([Waypoint("A", 21, 105), Waypoint("B", 22, 106)])


@pytest.mark.asyncio
async def test_google_routes_keeps_round_trip_destination_and_all_legs():
    def handler(request):
        import json
        body = json.loads(request.content)
        assert body["origin"] == body["destination"]
        assert [point["location"]["latLng"]["latitude"] for point in body["intermediates"]] == [21.1, 21.2]
        assert body["optimizeWaypointOrder"] is False
        return httpx.Response(200, json={"routes": [{"distanceMeters": 45000, "legs": [
            {"distanceMeters": 10000}, {"distanceMeters": 15000}, {"distanceMeters": 20000},
        ]}]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
        measured = await GoogleRoutesClient("test-key", http_client).compute_distance_meters([
            Waypoint("A", 21.0, 105.0), Waypoint("B", 21.1, 105.1),
            Waypoint("C", 21.2, 105.2), Waypoint("A", 21.0, 105.0),
        ])
    assert measured == RouteMeasurement(45000, (10000, 15000, 20000))


@pytest.mark.asyncio
async def test_google_routes_rejects_missing_final_leg():
    from app.services.data.route_enrichment import RouteValidationError

    async with httpx.AsyncClient(transport=httpx.MockTransport(
        lambda _: httpx.Response(200, json={"routes": [{"distanceMeters": 25000, "legs": [
            {"distanceMeters": 10000}, {"distanceMeters": 15000},
        ]}]})
    )) as http_client:
        with pytest.raises(RouteValidationError, match="thiếu chặng"):
            await GoogleRoutesClient("test-key", http_client).compute_distance_meters([
                Waypoint("A", 21.0, 105.0), Waypoint("B", 21.1, 105.1),
                Waypoint("C", 21.2, 105.2), Waypoint("A", 21.0, 105.0),
            ])


@pytest.mark.asyncio
async def test_looker_report_requires_machine_readable_source(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_ROUTES_API_KEY", "test-key")
    response = await client.post(
        "/api/v1/data/route-enrichment/export",
        data={"source_url": "https://datastudio.google.com/reporting/report-id/page/page-id"},
        files={"file": ("routes.xlsx", make_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 422
    assert "Google Sheet" in response.json()["detail"]


@pytest.mark.asyncio
async def test_missing_google_routes_key_fails_before_measurement(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_ROUTES_API_KEY", "")
    response = await client.post(
        "/api/v1/data/route-enrichment/export",
        data={"source_url": "https://docs.google.com/spreadsheets/d/example"},
        files={"file": ("routes.xlsx", make_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 503
    assert "GOOGLE_MAPS_ROUTES_API_KEY" in response.json()["detail"]


@pytest.mark.asyncio
async def test_export_downloads_measured_copy(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_ROUTES_API_KEY", "test-key")

    async def load_source(url):
        assert url == "https://docs.google.com/spreadsheets/d/example"
        return b"name,lat,lng\nBN Mega SOC,21.0738,105.97838\nHub A,21.12,106.01\n", "hubs.csv", "text/csv"

    async def measure(self, waypoints):
        assert [point.name for point in waypoints] == ["BN Mega SOC", "Hub A"]
        return RouteMeasurement(25432, (25432,))

    monkeypatch.setattr(route_enrichment.url_dataset_loader, "load", load_source)
    monkeypatch.setattr(route_enrichment.GoogleRoutesClient, "compute_distance_meters", measure)
    response = await client.post(
        "/api/v1/data/route-enrichment/export",
        data={"source_url": "https://docs.google.com/spreadsheets/d/example"},
        files={"file": ("routes.xlsx", make_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    assert response.headers["x-routes-completed"] == "1"
    output = openpyxl.load_workbook(io.BytesIO(response.content))
    assert output.active["D2"].value == 25.4
    assert "maps/dir" in output.active["C2"].value


@pytest.mark.asyncio
async def test_configured_looker_report_resolves_to_its_source_table(client, monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_MAPS_ROUTES_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ROUTE_LOOKER_REPORT_ID", "report-id")
    monkeypatch.setattr(settings, "ROUTE_LOOKER_SOURCE_URL", "https://docs.google.com/spreadsheets/d/real-source")
    loaded = []

    async def load_source(url):
        loaded.append(url)
        return b"name,lat,lng\nBN Mega SOC,21.0738,105.97838\nHub A,21.12,106.01\n", "hubs.csv", "text/csv"

    async def measure(self, waypoints):
        return RouteMeasurement(20000, (20000,))

    monkeypatch.setattr(route_enrichment.url_dataset_loader, "load", load_source)
    monkeypatch.setattr(route_enrichment.GoogleRoutesClient, "compute_distance_meters", measure)
    response = await client.post(
        "/api/v1/data/route-enrichment/export",
        data={"source_url": "https://datastudio.google.com/reporting/report-id/page/page-id"},
        files={"file": ("routes.xlsx", make_workbook(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
    )
    assert response.status_code == 200
    assert loaded == ["https://docs.google.com/spreadsheets/d/real-source"]


def test_looker_report_mapping_accepts_google_account_redirect_path(monkeypatch):
    monkeypatch.setattr(settings, "ROUTE_LOOKER_REPORT_ID", "report-id")
    monkeypatch.setattr(settings, "ROUTE_LOOKER_SOURCE_URL", "https://docs.google.com/spreadsheets/d/real-source")
    assert route_enrichment._mapped_looker_source(
        "https://datastudio.google.com/u/0/reporting/report-id/page/page-id"
    ) == "https://docs.google.com/spreadsheets/d/real-source"
