"""
ESPN scoreboard client — NFL (leaguewide), Bundesliga (Bayern Munich only),
MLB (Red Sox only), and men's Grand Slam tennis.

Uses ESPN's undocumented `site.api.espn.com` JSON API: free, no key required,
but unofficial and could change shape without notice — every fetch method
below is defensive (`.get()` with fallbacks throughout, try/except around the
whole thing) so a schema drift on one sport degrades to "fewer games" rather
than crashing the others. The tennis endpoint in particular is unverified —
see the warning on fetch_tennis_grand_slams().
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from transit_board.config import SportsConfig

log = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

_BAYERN_MATCH = "bayern"
_RED_SOX_ABBR = "BOS"

# Substring-matched against a tennis event's tournament/league name — same
# convention as layout.LINE_COLORS/ROUTE_COLORS (match by name, not by ID).
GRAND_SLAMS = ("australian open", "roland garros", "french open", "wimbledon", "us open")


@dataclass
class Competitor:
    name: str
    abbreviation: str
    score: str = ""
    logo_url: Optional[str] = None  # None for tennis (no stable roster) — real fallback path
    winner: bool = False


@dataclass
class Game:
    league: str  # "nfl" | "bundesliga" | "mlb" | "tennis"
    competitors: tuple[Competitor, Competitor]  # (away, home) for team sports; (p1, p2) for tennis
    status: str  # ESPN's own vocabulary, reused directly: "pre" | "in" | "post"
    status_detail: str  # pre-formatted short string: "Q3 8:41", "3rd Set", "Final"
    start_time: datetime  # tz-aware UTC
    end_time: Optional[datetime]  # always None from the provider — loop.py fills this in
    # (ESPN doesn't reliably expose a "finished at" timestamp for a `post` event, so rather than
    # trust an unverified field, loop.py._refresh_sports records the first time each event_id is
    # observed as "post" and uses that as the completion time for the post-game display window).
    event_id: str
    tournament: str = ""  # tennis only — e.g. "Wimbledon"


def _abbreviate(name: str, width: int = 4) -> str:
    """Fallback abbreviation when ESPN doesn't give us one: last word (surname
    for a tennis player, last word of a team name), truncated/uppercased."""
    parts = name.split()
    word = parts[-1] if parts else name
    return word[:width].upper()


def _parse_espn_date(raw: Optional[str]) -> datetime:
    if not raw:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def _parse_competitor(raw: dict) -> Competitor:
    entity = raw.get("team") or raw.get("athlete") or {}
    name = entity.get("displayName") or entity.get("shortDisplayName") or entity.get("name") or "?"
    abbr = entity.get("abbreviation") or _abbreviate(name)
    logo_url = entity.get("logo")
    if not logo_url:
        logos = entity.get("logos") or []
        if logos:
            logo_url = logos[0].get("href")
    return Competitor(
        name=str(name),
        abbreviation=str(abbr)[:4].upper(),
        score=str(raw.get("score", "") or ""),
        logo_url=logo_url,
        winner=bool(raw.get("winner", False)),
    )


def _parse_team_event(event: dict, league: str) -> Game:
    status = event.get("status", {}).get("type", {})
    state = status.get("state", "pre")
    detail = status.get("shortDetail") or status.get("detail") or ""

    comp = (event.get("competitions") or [{}])[0]
    competitors_raw = comp.get("competitors", [])
    home = next((c for c in competitors_raw if c.get("homeAway") == "home"), None)
    away = next((c for c in competitors_raw if c.get("homeAway") == "away"), None)
    if home is None or away is None:
        if len(competitors_raw) == 2:
            away, home = competitors_raw[0], competitors_raw[1]
        else:
            raise ValueError(f"expected 2 home/away competitors, got {len(competitors_raw)}")

    return Game(
        league=league,
        competitors=(_parse_competitor(away), _parse_competitor(home)),
        status=state,
        status_detail=detail,
        start_time=_parse_espn_date(event.get("date")),
        end_time=None,
        event_id=str(event.get("id", "")),
    )


def _parse_team_events(data: dict, league: str) -> list[Game]:
    games: list[Game] = []
    for event in data.get("events", []):
        try:
            games.append(_parse_team_event(event, league))
        except Exception as exc:
            log.warning("Skipping malformed %s event: %s", league, exc)
    return games


def _event_tournament_name(event: dict) -> str:
    """Best-effort tournament-name lookup across a few plausible field shapes
    — unverified against the live tennis payload, see fetch_tennis_grand_slams."""
    for getter in (
        lambda e: (e.get("tournament") or {}).get("name"),
        lambda e: (e.get("league") or {}).get("name"),
        lambda e: (e.get("season") or {}).get("name"),
        lambda e: e.get("shortName"),
        lambda e: e.get("name"),
    ):
        try:
            val = getter(event)
        except Exception:
            val = None
        if val:
            return str(val)
    return ""


def _is_grand_slam(tournament_name: str) -> bool:
    lower = tournament_name.lower()
    return any(slam in lower for slam in GRAND_SLAMS)


def _parse_tennis_event(event: dict, tournament: str) -> Game:
    status = event.get("status", {}).get("type", {})
    state = status.get("state", "pre")
    detail = status.get("shortDetail") or status.get("detail") or ""

    comp = (event.get("competitions") or [{}])[0]
    competitors_raw = (comp.get("competitors") or [])[:2]
    if len(competitors_raw) != 2:
        raise ValueError("expected 2 competitors for a singles match")

    parsed = [_parse_competitor(c) for c in competitors_raw]
    return Game(
        league="tennis",
        competitors=(parsed[0], parsed[1]),
        status=state,
        status_detail=detail,
        start_time=_parse_espn_date(event.get("date")),
        end_time=None,
        event_id=str(event.get("id", "")),
        tournament=tournament,
    )


def _parse_tennis_events(data: dict) -> list[Game]:
    games: list[Game] = []
    for event in data.get("events", []):
        try:
            tournament = _event_tournament_name(event)
            if not _is_grand_slam(tournament):
                continue
            games.append(_parse_tennis_event(event, tournament))
        except Exception as exc:
            log.warning("Skipping malformed tennis event: %s", exc)
    return games


class SportsClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(base_url=ESPN_BASE, timeout=10.0)

    async def _get(self, path: str) -> dict:
        r = await self._http.get(path)
        r.raise_for_status()
        return r.json()

    async def fetch_nfl(self) -> list[Game]:
        try:
            data = await self._get("/football/nfl/scoreboard")
            return _parse_team_events(data, "nfl")
        except Exception as exc:
            log.warning("NFL fetch failed: %s", exc)
            return []

    async def fetch_bundesliga_bayern(self) -> list[Game]:
        try:
            data = await self._get("/soccer/ger.1/scoreboard")
            games = _parse_team_events(data, "bundesliga")
            return [g for g in games if any(_BAYERN_MATCH in c.name.lower() for c in g.competitors)]
        except Exception as exc:
            log.warning("Bundesliga fetch failed: %s", exc)
            return []

    async def fetch_mlb_red_sox(self) -> list[Game]:
        try:
            data = await self._get("/baseball/mlb/scoreboard")
            games = _parse_team_events(data, "mlb")
            return [g for g in games if any(c.abbreviation == _RED_SOX_ABBR for c in g.competitors)]
        except Exception as exc:
            log.warning("MLB fetch failed: %s", exc)
            return []

    async def fetch_tennis_grand_slams(self) -> list[Game]:
        """
        UNVERIFIED: this planning/implementation environment has no outbound
        network access, so this endpoint path and the tennis JSON shape
        assumed by _parse_tennis_event/_event_tournament_name have not been
        confirmed against the live ESPN API. Verify with curl/browser before
        relying on this — try `/tennis/atp/scoreboard` first (ATP as a proxy
        for "men's"); if that 404s, ESPN may scope tennis by tournament slug
        instead (e.g. `/tennis/wimbledon/scoreboard`). Whatever the real shape
        turns out to be, this method's job stays the same: return Games for
        Grand-Slam singles matches only, and fail soft (log + empty list) —
        NFL/Bundesliga/MLB must keep working even if this is wrong.
        """
        try:
            data = await self._get("/tennis/atp/scoreboard")
            return _parse_tennis_events(data)
        except Exception as exc:
            log.warning("Tennis fetch failed (endpoint unverified, see docstring): %s", exc)
            return []

    async def fetch_all(self, cfg: "SportsConfig") -> list[Game]:
        fetchers = []
        if cfg.nfl_enabled:
            fetchers.append(self.fetch_nfl())
        if cfg.bayern_enabled:
            fetchers.append(self.fetch_bundesliga_bayern())
        if cfg.red_sox_enabled:
            fetchers.append(self.fetch_mlb_red_sox())
        if cfg.tennis_enabled:
            fetchers.append(self.fetch_tennis_grand_slams())
        if not fetchers:
            return []

        results = await asyncio.gather(*fetchers, return_exceptions=True)
        games: list[Game] = []
        for result in results:
            if isinstance(result, Exception):
                log.warning("Sports fetch task failed: %s", result)
            else:
                games.extend(result)
        return games

    async def aclose(self) -> None:
        await self._http.aclose()


def relevant_games(
    games: list[Game], cfg: "SportsConfig", now: Optional[datetime] = None
) -> list[Game]:
    """
    Filter to games worth showing right now: live, or finished within
    cfg.post_game_window_minutes. Never includes "pre" (upcoming) games.

    *now* must be tz-aware UTC (matching Game.start_time/end_time) — do not
    pass loop.py's naive local `datetime.now()` used for idle/forecast timing.
    """
    now = now or datetime.now(timezone.utc)
    enabled = {
        "nfl": cfg.nfl_enabled,
        "bundesliga": cfg.bayern_enabled,
        "mlb": cfg.red_sox_enabled,
        "tennis": cfg.tennis_enabled,
    }
    window_secs = cfg.post_game_window_minutes * 60

    kept = []
    for g in games:
        if not enabled.get(g.league, True):
            continue
        if g.status == "pre":
            continue
        if g.status == "post":
            if g.end_time is None or (now - g.end_time).total_seconds() > window_secs:
                continue
        kept.append(g)

    kept.sort(key=lambda g: (g.status != "in", g.start_time))
    return kept


# ---------------------------------------------------------------------------
# Dev-mode mock data
# ---------------------------------------------------------------------------


def mock_games(now: Optional[datetime] = None) -> list[Game]:
    """
    Fake games for --dev mode, covering all 4 sports with mixed live/final
    status, plus one upcoming and one stale-finished game so the relevance
    filter's exclusion path is visible too (not just its inclusion path).

    All logo_url fields are None — --dev mode must never touch the network,
    so mock data exercises the widget's text-abbreviation fallback path; the
    real logo fetch+cache path is only exercised by a real (non-dev) run.

    With default config (post_game_window_minutes=60, hybrid_compact_max_games=2)
    the full set below yields 6 relevant games — comfortably over the hybrid
    threshold, so `make dev --force-sports` shows the full-takeover/row-tier
    path out of the box. Disable sports.* toggles in config.toml down to ~2
    relevant games to preview the hybrid/card-tier paths instead.
    """
    now = now or datetime.now(timezone.utc)

    def rel(minutes: int) -> datetime:
        return now + timedelta(minutes=minutes)

    return [
        Game(
            "nfl",
            (Competitor("Bills", "BUF", "24"), Competitor("Jets", "NYJ", "17", winner=True)),
            "in",
            "Q4 2:14",
            rel(-140),
            None,
            "mock-nfl-1",
        ),
        Game(
            "nfl",
            (Competitor("Cowboys", "DAL", "20"), Competitor("Eagles", "PHI", "27", winner=True)),
            "in",
            "Q3 8:41",
            rel(-110),
            None,
            "mock-nfl-2",
        ),
        Game(
            "nfl",
            (Competitor("49ers", "SF", "31", winner=True), Competitor("Rams", "LAR", "13")),
            "post",
            "Final",
            rel(-200),
            rel(-20),
            "mock-nfl-3",
        ),
        Game(
            "bundesliga",
            (
                Competitor("Bayern Munich", "FCB", "2"),
                Competitor("Dortmund", "BVB", "1", winner=True),
            ),
            "in",
            "67'",
            rel(-67),
            None,
            "mock-bundesliga-1",
        ),
        Game(
            "mlb",
            (Competitor("Red Sox", "BOS", "4", winner=True), Competitor("Yankees", "NYY", "3")),
            "post",
            "Final",
            rel(-210),
            rel(-15),
            "mock-mlb-1",
        ),
        Game(
            "tennis",
            (Competitor("Alcaraz", "ALCA", "2"), Competitor("Sinner", "SINN", "1", winner=True)),
            "in",
            "3rd Set",
            rel(-95),
            None,
            "mock-tennis-1",
            tournament="Wimbledon",
        ),
        # Irrelevant: upcoming (filtered out — "pre" is never shown)
        Game(
            "nfl",
            (Competitor("Chiefs", "KC", ""), Competitor("Broncos", "DEN", "")),
            "pre",
            "8:20 PM",
            rel(180),
            None,
            "mock-nfl-4",
        ),
        # Irrelevant: finished well outside the default 60-min window
        Game(
            "mlb",
            (Competitor("Red Sox", "BOS", "6"), Competitor("Orioles", "BAL", "9", winner=True)),
            "post",
            "Final",
            rel(-400),
            rel(-180),
            "mock-mlb-2",
        ),
    ]
