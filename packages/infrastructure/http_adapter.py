"""HTTP adapter that can be used by the 1.6.6 desktop shell during migration."""
from __future__ import annotations

from datetime import date, datetime

import httpx


class BanboosApiClient:
    def __init__(self, base_url: str, timeout: float = 20.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _get(self, path: str, params: dict | None = None) -> dict:
        response = httpx.get(self.base_url + path, params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def health(self) -> dict:
        return self._get("/health")

    def nodes(self, province: str | None = None, query: str | None = None) -> list[dict]:
        return self._get("/api/v1/nodes", {"province": province, "q": query})["items"]

    def price_summary(self, node_id: int, market: str, start_date: date, end_date: date) -> dict:
        return self._get("/api/v1/price/summary", dict(node_id=node_id, market=market,
                         start_date=start_date.isoformat(), end_date=end_date.isoformat()))

    def weather_summary(self, node_id: int, start_time: datetime | None = None,
                        end_time: datetime | None = None) -> dict:
        params = {"node_id": node_id}
        if start_time:
            params["start_time"] = start_time.isoformat()
        if end_time:
            params["end_time"] = end_time.isoformat()
        return self._get("/api/v1/weather/summary", params)
