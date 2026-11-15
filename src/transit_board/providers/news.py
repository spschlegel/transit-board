"""
Breaking-news detector: no news API and no LLM, just agreement between outlets.

Polls the public RSS feeds of six major outlets, groups headlines that are
about the same story, and raises an alert only when a *new* story is picked
up by at least `min_outlets` different outlets within `uptake_hours` of the
first article. Speed of uptake is what separates breaking news from a big
story that spreads through the day: measured on live feeds, a SpaceX launch
and a ship collision both reached 4+ outlets, but over 6-10 hours.

Grouping is IDF-weighted word overlap (headline + description + URL slug, light
stemming), with average-link clustering so unrelated stories can't chain
together through one shared word. Thresholds were tuned against live feeds —
re-check them against real headlines before changing them.

Alerts already shown are persisted (`_cache/news_alerts.json`) so a restart
doesn't show the same story again.
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import math
import re
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import TYPE_CHECKING, Optional
from urllib.parse import urlparse

import httpx

if TYPE_CHECKING:
    from transit_board.config import NewsConfig

log = logging.getLogger(__name__)

FEEDS: dict[str, str] = {
    "bbc": "https://feeds.bbci.co.uk/news/rss.xml",
    "nyt": "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
    "npr": "https://feeds.npr.org/1001/rss.xml",
    "guardian": "https://www.theguardian.com/international/rss",
    "cbs": "https://www.cbsnews.com/latest/rss/main",
    "fox": "https://moxie.foxnews.com/google-publisher/latest.xml",
}

_HISTORY_PATH = Path(__file__).resolve().parent.parent / "_cache" / "news_alerts.json"
_LOOKBACK = timedelta(hours=36)  # items older than this are ignored (also the IDF corpus)
_FRESH = timedelta(hours=2)  # a story must have qualified this recently to alert
_SUPPRESS = timedelta(hours=48)  # don't re-alert a story similar to one shown this recently
_HISTORY_KEEP = timedelta(days=7)
_SIM_THRESHOLD = 10.0  # IDF-weighted overlap; ~2 rare shared words. Tuned on live feeds.

_STOP = frozenset(
    """a an the and or but of to in on at for from by with as is are was were be been being it its
    this that these those has have had will would could should can may might after before over under
    into about amid than then up down out new says say said how why what who when where which while
    not no yes more most other some any all us his her their they them he she you we our your just
    also first last year years day days week weeks time times man woman people one two three report
    reports news live update updates continue reading watch video photo photos image images getty
    here know get got make made take still now back very like top article articles story stories www
    com html index amp rss""".split()
)
_SPORT_PATH = re.compile(
    r"/(sport|sports|outkick-sports|football|soccer|cricket|tennis|golf|rugby|formula1|nfl|nba"
    r"|mlb|nhl)(/|-)",
    re.I,
)
# Show listings / episode pages: their descriptions list every topic of the day, so one item
# can glue unrelated stories together. Seen live on CBS ("11/14: CBS Saturday Morning").
_NOISE_TITLE = re.compile(
    r"^\d{1,2}/\d{1,2}(/\d{2,4})?:|\bguests for\b|^this week on\b|\bnews quiz\b|^(podcast|listen):",
    re.I,
)
_NOISE_PATH = re.compile(r"/video/\d{6}-")  # date-stamped show episodes
_SUFFIXES = ("ations", "ation", "ings", "ing", "edly", "ed", "es", "s")


# ── Data ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class NewsItem:
    outlet: str
    title: str
    pub: datetime  # tz-aware UTC
    tokens: frozenset[str]


@dataclass
class NewsAlert:
    headline: str
    outlets: list[str]
    qualified_at: datetime  # when the min_outlets-th outlet published (UTC)
    expires_at: Optional[datetime]  # UTC; None = held (--force-news)
    tokens: frozenset[str] = field(default_factory=frozenset)
    dismissed: bool = False

    @property
    def active(self) -> bool:
        if self.dismissed:
            return False
        return self.expires_at is None or datetime.now(timezone.utc) < self.expires_at

    @property
    def remaining_secs(self) -> Optional[int]:
        if self.expires_at is None:
            return None
        return max(0, int((self.expires_at - datetime.now(timezone.utc)).total_seconds()))


@dataclass(frozen=True)
class AlertRecord:
    at: datetime  # UTC, when we raised it
    headline: str
    tokens: frozenset[str]


def sample_alert(minutes: Optional[int]) -> NewsAlert:
    """A fake alert for previewing the layout (PWA test button, --force-news)."""
    now = datetime.now(timezone.utc)
    return NewsAlert(
        headline="Nationwide ground stop halts all US flights after FAA system outage",
        outlets=["bbc", "cbs", "npr", "nyt"],
        qualified_at=now,
        expires_at=None if minutes is None else now + timedelta(minutes=minutes),
    )


# ── Text → tokens ────────────────────────────────────────────────────────────


def _stem(w: str) -> str:
    for s in _SUFFIXES:
        if w.endswith(s) and len(w) - len(s) >= 4:
            return w[: -len(s)]
    return w


def _tokens(text: Optional[str]) -> set[str]:
    s = html.unescape(re.sub(r"<[^>]+>", " ", text or "")).lower()
    s = s.replace("’", "'").replace("f.a.a.", "faa").replace("u.s.", "us")
    s = re.sub(r"(\w)-(\w)", r"\1\2", s)  # nation-wide -> nationwide
    out: set[str] = set()
    for w in re.findall(r"[a-z][a-z0-9']*", s):
        w = w.strip("'")
        if w.endswith("'s"):
            w = w[:-2]
        if len(w) >= 3 and w not in _STOP:
            out.add(_stem(w))
    return out


def _slug_tokens(path: str) -> set[str]:
    # URL slugs are dense keywords ("faa-ground-stop-flights-resume"); opaque IDs are dropped.
    words = [p for p in re.split(r"[/\-_.]", path) if p.isalpha() and len(p) >= 3]
    return _tokens(" ".join(words))


def parse_feed(outlet: str, xml_text: str) -> list[NewsItem]:
    root = ET.fromstring(xml_text)
    items: list[NewsItem] = []
    for it in root.iter("item"):
        path = urlparse(it.findtext("link") or "").path
        if _SPORT_PATH.search(path) or _NOISE_PATH.search(path):
            continue
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(timezone.utc)
        except (TypeError, ValueError):
            continue
        title = html.unescape((it.findtext("title") or "").strip())
        if not title or _NOISE_TITLE.search(title):
            continue
        toks = _tokens(title) | _tokens(it.findtext("description")) | _slug_tokens(path)
        items.append(NewsItem(outlet, title, pub, frozenset(toks)))
    return items


def _clean_headline(title: str) -> str:
    # "'Can you believe it?': SpaceX catches..." -> "SpaceX catches..." (a pull quote reads
    # badly on a 76px panel). Only a short leading quote, so real quoted headlines survive.
    stripped = re.sub(r"^['\"‘“][^'\"’”]{1,60}['\"’”]:\s*", "", title)
    return stripped[:1].upper() + stripped[1:] if stripped else title


# ── Detection ────────────────────────────────────────────────────────────────


def _cluster(items: list[NewsItem], idf: dict[str, float]) -> list[list[NewsItem]]:
    def sim(a: NewsItem, b: NewsItem) -> float:
        return sum(idf[w] for w in a.tokens & b.tokens)

    clusters: list[list[NewsItem]] = []
    for it in sorted(items, key=lambda i: i.pub):
        best, best_s = None, 0.0
        for c in clusters:
            s = sum(sim(it, m) for m in c) / len(c)  # average link: no chaining via one word
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= _SIM_THRESHOLD:
            best.append(it)
        else:
            clusters.append([it])
    return clusters


def detect(
    items: list[NewsItem],
    cfg: "NewsConfig",
    history: list[AlertRecord],
    now: datetime,
) -> Optional[NewsAlert]:
    """Return a new alert if a story just qualified as breaking, else None."""
    items = [i for i in items if now - i.pub <= _LOOKBACK and i.outlet in cfg.outlets]
    if not items:
        return None

    n = len(items)
    df = Counter(w for i in items for w in i.tokens)
    idf = {w: math.log(n / c) for w, c in df.items()}
    unseen = math.log(n)  # weight for a history token absent from the current corpus

    def overlap(a: frozenset[str], b: frozenset[str]) -> float:
        return sum(idf.get(w, unseen) for w in a & b)

    recent_alerts = [h for h in history if now - h.at <= _SUPPRESS]
    candidates: list[tuple[int, datetime, list[NewsItem]]] = []
    for c in _cluster(items, idf):
        first_by_outlet: dict[str, datetime] = {}
        for i in c:
            if i.outlet not in first_by_outlet or i.pub < first_by_outlet[i.outlet]:
                first_by_outlet[i.outlet] = i.pub
        if len(first_by_outlet) < cfg.min_outlets:
            continue
        firsts = sorted(first_by_outlet.values())
        qualified_at = firsts[cfg.min_outlets - 1]
        if qualified_at - firsts[0] > timedelta(hours=cfg.uptake_hours):
            continue  # spread slowly: a big story, not breaking news
        if now - qualified_at > _FRESH:
            continue  # qualified a while ago (e.g. seen first at startup)
        sig = frozenset(w for w, k in Counter(w for i in c for w in i.tokens).items() if k >= 2)
        if any(overlap(sig, h.tokens) >= _SIM_THRESHOLD for h in recent_alerts):
            continue
        candidates.append((len(first_by_outlet), qualified_at, c))

    if not candidates:
        return None
    _, qualified_at, cluster = max(candidates, key=lambda t: (t[0], -t[1].timestamp()))
    early = [i for i in cluster if i.pub <= qualified_at] or cluster
    sig_counts = Counter(w for i in cluster for w in i.tokens)
    shared = {w for w, k in sig_counts.items() if k >= 2}

    def representativeness(i: NewsItem) -> tuple[float, int]:
        # The title that names the story best (most shared keywords), shorter on ties.
        return sum(idf[w] for w in _tokens(i.title) & shared if w in idf), -len(i.title)

    return NewsAlert(
        headline=_clean_headline(max(early, key=representativeness).title),
        outlets=sorted({i.outlet for i in cluster}),
        qualified_at=qualified_at,
        expires_at=now + timedelta(minutes=cfg.show_minutes),
        tokens=frozenset(w for w, _ in sig_counts.most_common(40)),
    )


# ── History persistence ──────────────────────────────────────────────────────


def load_history(path: Path = _HISTORY_PATH) -> list[AlertRecord]:
    try:
        raw = json.loads(path.read_text())
        return [
            AlertRecord(datetime.fromisoformat(r["at"]), r["headline"], frozenset(r["tokens"]))
            for r in raw
        ]
    except FileNotFoundError:
        return []
    except (ValueError, KeyError, TypeError) as exc:
        log.warning("Ignoring unreadable news history %s: %s", path, exc)
        return []


def save_history(history: list[AlertRecord], path: Path = _HISTORY_PATH) -> None:
    cutoff = datetime.now(timezone.utc) - _HISTORY_KEEP
    keep = [h for h in history if h.at >= cutoff]
    data = [
        {"at": h.at.isoformat(), "headline": h.headline, "tokens": sorted(h.tokens)} for h in keep
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    tmp.replace(path)


# ── Client ───────────────────────────────────────────────────────────────────


class NewsClient:
    def __init__(self) -> None:
        self._http = httpx.AsyncClient(
            timeout=10.0, follow_redirects=True, headers={"User-Agent": "transit-board/0.1"}
        )

    async def _fetch(self, outlet: str) -> list[NewsItem]:
        r = await self._http.get(FEEDS[outlet])
        r.raise_for_status()
        return await asyncio.to_thread(parse_feed, outlet, r.text)

    async def fetch_all(self, outlets: list[str]) -> tuple[list[NewsItem], dict[str, str]]:
        """All items from *outlets*, plus {outlet: error} for feeds that failed."""
        results = await asyncio.gather(*(self._fetch(o) for o in outlets), return_exceptions=True)
        items: list[NewsItem] = []
        errors: dict[str, str] = {}
        for outlet, res in zip(outlets, results):
            if isinstance(res, BaseException):
                errors[outlet] = f"{type(res).__name__}: {res}"
            else:
                items.extend(res)
        return items, errors

    async def aclose(self) -> None:
        await self._http.aclose()
