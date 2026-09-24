"""Google Routes API adapter for verified spreadsheet waypoints."""

import httpx

from app.services.data.route_enrichment import RouteMeasurement, RouteValidationError, Waypoint


class RoutesProviderError(Exception):
    """Credentials, quota, or service failure that affects the whole export."""


class GoogleRoutesClient:
    URL = "https://routes.googleapis.com/directions/v2:computeRoutes"

    def __init__(self, api_key: str, http_client: httpx.AsyncClient):
        self.api_key = api_key
        self.http_client = http_client

    async def compute_distance_meters(self, waypoints: list[Waypoint]) -> RouteMeasurement:
        if len(waypoints) < 2 or len(waypoints) > 25:
            raise ValueError("Tuyến cần từ 2 đến 25 điểm dừng đã xác minh.")

        def location(point: Waypoint) -> dict:
            return {"location": {"latLng": {"latitude": point.latitude, "longitude": point.longitude}}}

        body = {
            "origin": location(waypoints[0]),
            "destination": location(waypoints[-1]),
            "intermediates": [location(point) for point in waypoints[1:-1]],
            "travelMode": "DRIVE",
            "routingPreference": "TRAFFIC_AWARE",
            "optimizeWaypointOrder": False,
            "languageCode": "vi",
            "units": "METRIC",
        }
        try:
            response = await self.http_client.post(
                self.URL,
                json=body,
                headers={
                    "X-Goog-Api-Key": self.api_key,
                    "X-Goog-FieldMask": "routes.distanceMeters,routes.legs.distanceMeters",
                },
            )
        except httpx.TimeoutException as exc:
            raise ValueError("Google Routes quá thời gian phản hồi.") from exc
        except httpx.RequestError as exc:
            raise ValueError("Không kết nối được Google Routes.") from exc
        if response.status_code in (401, 403):
            raise RoutesProviderError("Google Routes từ chối API key hoặc quyền truy cập.")
        if response.status_code == 429:
            raise RoutesProviderError("Đã vượt hạn mức Google Routes; hãy thử lại sau.")
        if response.status_code >= 500:
            raise RoutesProviderError(f"Google Routes tạm lỗi HTTP {response.status_code}.")
        if response.status_code >= 400:
            raise ValueError(f"Google Routes trả lỗi HTTP {response.status_code}.")
        try:
            route = response.json()["routes"][0]
            meters = route["distanceMeters"]
            legs = tuple(leg["distanceMeters"] for leg in route["legs"])
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise RouteValidationError("Google Routes không trả về đủ quãng đường từng chặng.") from exc
        if not isinstance(meters, (int, float)) or meters < 0 or any(not isinstance(leg, (int, float)) for leg in legs):
            raise RouteValidationError("Google Routes trả về quãng đường không hợp lệ.")
        if len(legs) != len(waypoints) - 1:
            raise RouteValidationError("Google Routes trả về thiếu chặng của tuyến.")
        return RouteMeasurement(round(meters), tuple(round(leg) for leg in legs))
