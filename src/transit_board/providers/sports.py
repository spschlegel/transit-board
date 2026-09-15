"""
ESPN scoreboard client — NFL (leaguewide), Bundesliga (Bayern Munich only),
MLB (Red Sox only), and men's Grand Slam tennis.

Uses ESPN's undocumented `site.api.espn.com` JSON API: free, no key required,
but unofficial and could change shape without notice — every fetch method
below is defensive (`.get()` with fallbacks throughout, try/except around the
whole thing) so a schema drift on one sport degrades to "fewer games" rather
than crashing the others.

All four endpoint shapes below (NFL/Bundesliga/MLB scoreboards and the tennis
scoreboard) have been confirmed against the live API. Tennis is structurally
different from the other three: a top-level tennis "event" is a whole
*tournament* (e.g. "US Open"), not a single match — see the comment above
_parse_tennis_grouping() for the real nesting.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Optional

import httpx

if TYPE_CHECKING:
    from transit_board.config import SportsConfig

log = logging.getLogger(__name__)

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports"

_BAYERN_MATCH = "bayern"
_RED_SOX_ABBR = "BOS"

# Defensive ceiling for relevant_games(): no real NFL/Bundesliga/MLB game
# runs anywhere near this long (even an extra-innings MLB marathon), so a
# "post" game whose kickoff is older than this is never eligible, regardless
# of first-seen-post bookkeeping state — see relevant_games()'s docstring.
_MAX_GAME_AGE_HOURS = 8

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
    game_score: str = ""  # tennis only: games won in the *current* set (score is sets won)


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


def _sets_won(linescores: list[dict]) -> str:
    """Tennis has no top-level competitor "score" field, only per-set
    "linescores" (each with a "winner" bool) — collapse that into a compact
    "sets won" count, the tennis equivalent of a team sport's score."""
    won = sum(1 for ls in linescores if ls.get("winner"))
    return str(won)


def _parse_competitor(raw: dict) -> Competitor:
    entity = raw.get("team") or raw.get("athlete") or {}
    name = entity.get("displayName") or entity.get("shortDisplayName") or entity.get("name") or "?"
    abbr = entity.get("abbreviation") or _abbreviate(name)
    logo_url = entity.get("logo")
    if not logo_url:
        logos = entity.get("logos") or []
        if logos:
            logo_url = logos[0].get("href")

    score = raw.get("score")
    if score in (None, ""):
        linescores = raw.get("linescores")
        score = _sets_won(linescores) if linescores else ""

    return Competitor(
        name=str(name),
        abbreviation=str(abbr)[:4].upper(),
        score=str(score or ""),
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


def _is_grand_slam(tournament: dict) -> bool:
    # ESPN tags the 4 majors with major=True directly — confirmed against the
    # live API (US Open example had "major": true). Name-substring match is
    # kept as a fallback in case that flag is ever missing/unreliable.
    if tournament.get("major") is True:
        return True
    return any(slam in str(tournament.get("name", "")).lower() for slam in GRAND_SLAMS)


def _current_set_score(raw: dict) -> str:
    """Games won *in the set currently being played* (the last linescores
    entry) — distinct from Competitor.score, which is total sets won. Only
    meaningful while a match is live; returns "" once there's no set in
    progress (no linescores at all, e.g. match hasn't started)."""
    linescores = raw.get("linescores") or []
    if not linescores:
        return ""
    value = linescores[-1].get("value")
    if value is None:
        return ""
    return str(int(value)) if float(value).is_integer() else str(value)


def _parse_tennis_match(match: dict, tournament_name: str) -> Game:
    status = match.get("status", {}).get("type", {})
    state = status.get("state", "pre")
    detail = status.get("shortDetail") or status.get("detail") or ""

    competitors_raw = (match.get("competitors") or [])[:2]
    if len(competitors_raw) != 2:
        raise ValueError(f"expected 2 competitors for a singles match, got {len(competitors_raw)}")

    parsed = [
        replace(_parse_competitor(c), game_score=_current_set_score(c)) for c in competitors_raw
    ]
    return Game(
        league="tennis",
        competitors=(parsed[0], parsed[1]),
        status=state,
        status_detail=detail,
        start_time=_parse_espn_date(match.get("date") or match.get("startDate")),
        end_time=None,
        event_id=str(match.get("id", "")),
        tournament=tournament_name,
    )


def _parse_tennis_events(data: dict) -> list[Game]:
    """
    Confirmed shape: a top-level "event" here is a whole tournament (e.g.
    "US Open", spanning weeks, major=true for the 4 Slams), NOT a single
    match — unlike the NFL/Bundesliga/MLB scoreboards where an "event" is one
    game. Individual matches live three levels down: tournament["groupings"]
    is a list of {"grouping": {"slug": "mens-singles", ...}, "competitions":
    [...]}, one grouping per discipline (mens-singles/womens-singles/mixed-
    doubles/etc — no separate "gender" field, the discipline slug is it), and
    each grouping's "competitions" list holds the actual matches (same
    status/competitors/date shape as a team-sport competition, except a tennis
    competitor has no "score" field — see _sets_won()).
    """
    games: list[Game] = []
    for tournament in data.get("events", []):
        try:
            if not _is_grand_slam(tournament):
                continue
            tournament_name = str(tournament.get("name", ""))
            for grouping in tournament.get("groupings", []):
                if (grouping.get("grouping") or {}).get("slug") != "mens-singles":
                    continue
                for match in grouping.get("competitions", []):
                    try:
                        games.append(_parse_tennis_match(match, tournament_name))
                    except Exception as exc:
                        log.warning("Skipping malformed tennis match: %s", exc)
        except Exception as exc:
            log.warning("Skipping malformed tennis tournament: %s", exc)
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
        The /tennis/atp/scoreboard endpoint returns whatever tournament(s)
        are currently relevant (in progress / imminent) rather than a full
        season list — confirmed live: during the US Open it returned exactly
        that one tournament. _parse_tennis_events() filters to majors
        (major=True) and men's singles matches within them; see its docstring
        for the tournament -> groupings -> competitions nesting.
        """
        try:
            data = await self._get("/tennis/atp/scoreboard")
            return _parse_tennis_events(data)
        except Exception as exc:
            log.warning("Tennis fetch failed: %s", exc)
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

    Tennis is an exception to the post-game window: a Slam draw can have
    ~250 matches with most of them "post" at any given moment (see
    providers/sports.py's tennis parsing notes), so a finished tennis match
    is dropped immediately rather than lingering for post_game_window_minutes
    like a team-sport score would.

    A "post" team-sport game also has to have started within
    _MAX_GAME_AGE_HOURS to be eligible at all, independent of the
    first-seen-post bookkeeping loop.py maintains — confirmed live, ESPN's
    scoreboard endpoints keep returning finished games for days (an NFL
    scoreboard fetch returned a game 5 days past kickoff), so this is a hard
    backstop against a multi-day-old game ever being treated as "just
    finished", regardless of any bookkeeping edge case.

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
    max_age_secs = _MAX_GAME_AGE_HOURS * 3600

    kept = []
    for g in games:
        if not enabled.get(g.league, True):
            continue
        if g.status == "pre":
            continue
        if g.league == "tennis" and g.status != "in":
            continue
        if g.status == "post":
            if g.end_time is None or (now - g.end_time).total_seconds() > window_secs:
                continue
            if (now - g.start_time).total_seconds() > max_age_secs:
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
            (
                Competitor("Alcaraz", "ALCA", "2", game_score="4"),
                Competitor("Sinner", "SINN", "1", winner=True, game_score="5"),
            ),
            "in",
            "3rd",
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
