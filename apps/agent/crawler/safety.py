"""Politeness and safety policy for crawling real websites.

The policy is deliberately honest: it identifies itself, obeys robots.txt,
rate-limits per host, enforces page/time caps, never takes destructive actions
by default, and *reports* walls (captcha, login, consent) instead of trying to
get past them. There is no evasion of any kind here.
"""

from __future__ import annotations

import re
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.parse import urlsplit
from urllib.robotparser import RobotFileParser

from apps.agent.audit_models import BlockedNote
from apps.agent.contracts import Action, CaptureBundle

__all__ = ["USER_AGENT", "SafetyPolicy"]

USER_AGENT = "StateScoutAuditor/0.1"

_DESTRUCTIVE = re.compile(
    r"\b(log\s?out|sign\s?out|delete|remove|purchase|buy|pay|confirm\s+order|"
    r"place\s+order|unsubscribe|deactivate|close\s+account|cancel\s+subscription|"
    r"erase|destroy|wipe)\b",
    re.IGNORECASE,
)

_CAPTCHA = re.compile(
    r"g-recaptcha|recaptcha/api|h-captcha|hcaptcha\.com|unusual traffic|"
    r"verify (that )?you are (a )?human|verify you.re human|are you a robot|cf-challenge",
    re.IGNORECASE,
)
_CONSENT = re.compile(
    r"onetrust-consent-sdk|cybotcookiebotdialog|didomi-popup|truste-consent|"
    r"cookie[- ]?(consent|banner|wall)|we use cookies|this (web)?site uses cookies",
    re.IGNORECASE,
)
_PASSWORD_INPUT = re.compile(r"""<input[^>]+type\s*=\s*["']?password""", re.IGNORECASE)
_LOGIN_HINT = re.compile(r"\b(log\s?in|sign\s?in)\b", re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")

Fetcher = Callable[[str], tuple[int, str]]


def _fetch_robots(url: str) -> tuple[int, str]:
    """Return (status, body); raise OSError on connection failure."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status, resp.read(512_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def _origin(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower()


@dataclass
class SafetyPolicy:
    respect_robots: bool = True
    requests_per_second: float = 1.0
    max_pages: int = 50
    max_seconds: float = 300.0
    same_origin_only: bool = True
    allow_destructive: bool = False
    #: Injectable for tests.
    robots_fetcher: Fetcher = field(default=_fetch_robots, repr=False)
    clock: Callable[[], float] = field(default=time.monotonic, repr=False)
    sleeper: Callable[[float], None] = field(default=time.sleep, repr=False)

    def __post_init__(self) -> None:
        self._robots: dict[str, RobotFileParser | None] = {}
        self._last_request: dict[str, float] = {}
        self._pages = 0
        self._started: float | None = None
        self._start_origin: str | None = None
        self._notes: list[BlockedNote] = []
        self.warnings: list[str] = []
        self._lock = threading.Lock()

    # -- recording ---------------------------------------------------------

    def block(self, url: str, reason: str) -> str:
        """Record a blocked page (once per url+reason) and return the reason."""
        note = BlockedNote(url=url, reason=reason)
        if note not in self._notes:
            self._notes.append(note)
        return reason

    def blocked_notes(self) -> tuple[BlockedNote, ...]:
        return tuple(self._notes)

    # -- robots ------------------------------------------------------------

    def _robots_for(self, url: str) -> RobotFileParser | None:
        origin = _origin(url)
        if origin in self._robots:
            return self._robots[origin]
        parser: RobotFileParser | None = RobotFileParser()
        assert parser is not None
        try:
            status, body = self.robots_fetcher(f"{origin}/robots.txt")
            if status in (401, 403):
                parser.parse(["User-agent: *", "Disallow: /"])
            elif status >= 400:
                parser = None  # no robots.txt: everything allowed
            else:
                parser.parse(body.splitlines())
        except Exception as exc:
            self.warnings.append(f"robots.txt unavailable for {origin}: {type(exc).__name__}")
            parser = None
        self._robots[origin] = parser
        return parser

    def robots_allows(self, url: str) -> bool:
        if not self.respect_robots:
            return True
        parser = self._robots_for(url)
        return True if parser is None else parser.can_fetch(USER_AGENT, url)

    # -- gates ---------------------------------------------------------------

    def check_navigation(self, url: str) -> str | None:
        """Return a block reason (robots|cap) or None; records the note.

        Off-origin URLs under ``same_origin_only`` return ``"offsite"`` without
        a note (it is scope, not a wall).
        """
        with self._lock:
            now = self.clock()
            if self._started is None:
                self._started = now
            if self._start_origin is None:
                self._start_origin = _origin(url)
            if self.same_origin_only and _origin(url) != self._start_origin:
                return "offsite"
            if self._pages >= self.max_pages or now - self._started > self.max_seconds:
                return self.block(url, "cap")
            if not self.robots_allows(url):
                return self.block(url, "robots")
            return None

    def throttle(self, url: str) -> None:
        """Sleep so requests to one host stay under ``requests_per_second``."""
        if self.requests_per_second <= 0:
            return
        host = urlsplit(url).netloc.lower()
        gap = 1.0 / self.requests_per_second
        with self._lock:
            last = self._last_request.get(host)
            now = self.clock()
            wait = 0.0 if last is None else max(0.0, last + gap - now)
            self._last_request[host] = now + wait
        if wait:
            self.sleeper(wait)

    def record_page(self) -> None:
        with self._lock:
            self._pages += 1

    @property
    def pages(self) -> int:
        return self._pages

    # -- actions -------------------------------------------------------------

    def is_destructive(self, action: Action) -> bool:
        return bool(_DESTRUCTIVE.search(action.label) or _DESTRUCTIVE.search(action.target))

    def filter_actions(self, actions: tuple[Action, ...]) -> tuple[Action, ...]:
        if self.allow_destructive:
            return actions
        return tuple(a for a in actions if not self.is_destructive(a))

    # -- walls ---------------------------------------------------------------

    def detect_wall(self, bundle: CaptureBundle) -> str | None:
        """Classify a captured page as captcha|login_wall|consent_wall, else None.

        Heuristic and conservative; it never interacts with the page.
        """
        dom = bundle.dom or ""
        head = f"{bundle.title}\n{dom}"
        if _CAPTCHA.search(head):
            return "captcha"
        if _PASSWORD_INPUT.search(dom):
            text = _TAG.sub(" ", dom)
            if _LOGIN_HINT.search(bundle.title) or _LOGIN_HINT.search(text[:4000]):
                return "login_wall"
        if _CONSENT.search(dom):
            return "consent_wall"
        return None

    def check_bundle(self, bundle: CaptureBundle) -> str | None:
        """detect_wall + record the note."""
        reason = self.detect_wall(bundle)
        if reason:
            self.block(bundle.url, reason)
        return reason
