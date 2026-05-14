"""MBTA V3 API client — fetches real-time departure predictions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

log = logging.getLogger(__name__)

MBTA_BASE = "https://api-v3.mbta.com"


@dataclass
class Departure:
    route: str  # Short name, e.g. "39", "Orange", "OL"
    headsign: str  # Trip destination / headsign
    minutes: int  # Minutes until departure (0 = boarding now)
    realtime: bool  # True = realtime prediction; False = schedule only


class MBTAClient:
    def __init__(self, api_key: str) -> None:
        headers: dict[str, str] = {}
        if api_key:
            headers["x-api-key"] = api_key
        self._http = httpx.AsyncClient(
            base_url=MBTA_BASE,
            headers=headers,
            timeout=10.0,
        )

    async def departures(self, stop_id: str, max_results: int = 3) -> list[Departure]:
        """Return up to *max_results* upcoming departures for *stop_id*."""
        try:
            r = await self._http.get(
                "/predictions",
                params={
                    "filter[stop]": stop_id,
                    "include": "route,trip",
                    "sort": "departure_time",
                    "page[limit]": max(max_results * 3, 9),
                },
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("MBTA fetch failed for stop %s: %s", stop_id, exc)
            return []

        data = r.json()
        included = data.get("included", [])
        routes = {x["id"]: x for x in included if x["type"] == "route"}
        trips = {x["id"]: x for x in included if x["type"] == "trip"}

        now = datetime.now(tz=timezone.utc)
        results: list[Departure] = []

        for pred in data.get("data", []):
            attr = pred.get("attributes", {})
            dep_iso = attr.get("departure_time") or attr.get("arrival_time")
            if not dep_iso:
                continue

            dep_dt = datetime.fromisoformat(dep_iso)
            minutes = int((dep_dt - now).total_seconds() / 60)
            if minutes < 0:
                continue

            rels = pred.get("relationships", {})

            route_id = ((rels.get("route") or {}).get("data") or {}).get("id", "")
            route_attrs = routes.get(route_id, {}).get("attributes", {})
            route_name = route_attrs.get("short_name") or route_attrs.get("long_name") or route_id

            trip_id = ((rels.get("trip") or {}).get("data") or {}).get("id", "")
            trip_attrs = trips.get(trip_id, {}).get("attributes", {})
            headsign = trip_attrs.get("headsign", "")

            sched_rel = attr.get("schedule_relationship") or ""
            realtime = sched_rel not in ("NO_DATA", "SCHEDULED", "")

            results.append(
                Departure(
                    route=route_name,
                    headsign=headsign,
                    minutes=minutes,
                    realtime=realtime,
                )
            )
            if len(results) >= max_results:
                break

        return results

    async def stop_coords(self, stop_id: str) -> tuple[float, float]:
        """Return (lat, lon) for *stop_id* from the MBTA stops API."""
        try:
            r = await self._http.get(f"/stops/{stop_id}")
            r.raise_for_status()
        except httpx.HTTPError as exc:
            log.warning("MBTA stops fetch failed for %s: %s", stop_id, exc)
            raise
        attrs = r.json()["data"]["attributes"]
        return float(attrs["latitude"]), float(attrs["longitude"])

    async def aclose(self) -> None:
        await self._http.aclose()


# ---------------------------------------------------------------------------
# Dev-mode mock data
# ---------------------------------------------------------------------------


def mock_departures(stop_id: str, stop_type: str, max_results: int = 3) -> list[Departure]:
    """Return plausible fake departures for --dev mode."""
    if stop_type == "bus":
        # Multiple routes mixed in chronological order — mirrors real multi-route stops
        pool = [
            Departure("39", "Forest Hills", 2, True),
            Departure("66", "Harvard", 5, True),
            Departure("39", "Forest Hills", 13, True),
            Departure("15", "Kane Sq", 18, False),
            Departure("66", "Harvard", 21, True),
            Departure("39", "Forest Hills", 28, False),
        ]
    else:
        pool = [
            Departure("OL", "Oak Grove", 3, True),
            Departure("OL", "Forest Hills", 7, True),
            Departure("OL", "Oak Grove", 14, True),
            Departure("OL", "Forest Hills", 21, False),
        ]
    return pool[:max_results]
