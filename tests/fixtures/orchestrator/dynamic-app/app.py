"""A seeded, stdlib-only SIMULATION of a dynamic web app (not a real browser).

It implements `CrawlerPort` plus the experimental `NetworkObservations.drain()` so it
plugs into `Ports` next to `FakePerception` / `FakeGraph`. Everything random comes
from two `random.Random` streams seeded from `SEED`, so a crawl is reproducible:

* the *render* stream drives ads, the visitor counter, relative times, feed items,
  randomised CSS classes and the flaky element;
* the *outcome* stream drives the stochastic actions (70/30 and ~5%).

Dynamic features (ground truth in `expected.json`):

1. rotating ad block              4. infinite-scroll feed, new items per visit
2. live visitor counter           5. randomised CSS class names (CSS-in-JS style)
3. relative timestamps            6. SPA modal at an unchanged URL ("/")

Logical states are named in `LOGICAL_STATES`. A capture advertises its logical state
only through `screenshot_path` (`/sim/screenshots/<logical>.png`), which is how the
experiment maps discovered state ids back to ground truth. The orchestrator never
reads it.
"""

from __future__ import annotations

import hashlib
import random
import re
from dataclasses import dataclass
from typing import Final

from apps.agent.contracts import (
    Action,
    ActionError,
    ActionKind,
    CaptureBundle,
    ExpectationNode,
    ExpectationSet,
    JSONValue,
    NavigationError,
)

SEED: Final = 7
BASE_URL: Final = "http://dyn.test"
SEED_URL: Final = f"{BASE_URL}/"

#: Probability the flaky forbidden element is rendered on the products page.
FLAKY_RENDER_PROBABILITY: Final = 0.4
#: "Add to cart": P(cart). The remainder lands on the sold-out page.
ADD_TO_CART_SUCCESS: Final = 0.7
#: "Checkout": P(error page). The remainder lands on the thank-you page.
CHECKOUT_ERROR: Final = 0.05
FEED_BATCH: Final = 3

LOGICAL_STATES: Final[tuple[str, ...]] = (
    "home",
    "home-modal",
    "products",
    "sold-out",
    "cart",
    "thanks",
    "error",
    "feed",
    "settings",
)

_URLS: Final[dict[str, str]] = {
    "home": "/",
    "home-modal": "/",
    "products": "/products",
    "sold-out": "/products/sold-out",
    "cart": "/cart",
    "thanks": "/thanks",
    "error": "/error",
    "feed": "/feed",
    "settings": "/settings",
}
_PATH_TO_LOGICAL: Final[dict[str, str]] = {
    path: name for name, path in _URLS.items() if name != "home-modal"
}
_TITLES: Final[dict[str, str]] = {
    "home": "Home",
    "home-modal": "Home",
    "products": "Products",
    "sold-out": "Sold out",
    "cart": "Cart",
    "thanks": "Thank you",
    "error": "Error",
    "feed": "Feed",
    "settings": "Settings",
}
_BODY: Final[dict[str, str]] = {
    "home": "<h1>Welcome</h1><p>Browse our catalogue</p>",
    "home-modal": "<h1>Welcome</h1><p>Browse our catalogue</p>",
    "products": "<h1>Products</h1><ul><li>Widget</li><li>Gadget</li></ul>",
    "sold-out": "<h1>Sold out</h1><p>That item is no longer available</p>",
    "cart": "<h1>Your cart</h1><p>One widget</p>",
    "thanks": "<h1>Thank you</h1><p>Your order is confirmed</p>",
    "error": "<h1>Something went wrong</h1><p>Please try again</p>",
    "feed": "<h1>Feed</h1>",
    "settings": '<h1>Settings</h1><div data-tag="debug-panel">Debug panel</div>',
}

_ADS: Final[tuple[str, ...]] = (
    "Acme Rockets",
    "Globex Cloud Hosting",
    "Initech Staplers",
    "Umbrella Insurance",
    "Hooli Phones",
    "Soylent Snacks",
)
_FEED_TITLES: Final[tuple[str, ...]] = (
    "Kittens learn to code",
    "Local bakery wins award",
    "New bridge opens downtown",
    "Chess club hits record",
    "Weather turns mild",
    "Library extends hours",
    "Robot waiter goes viral",
    "Farmers market returns",
)
_ALNUM: Final = "abcdefghijklmnopqrstuvwxyz0123456789"


@dataclass(frozen=True, slots=True)
class Control:
    """One clickable control. `name` is the accessible name and the action label."""

    name: str
    role: str  # "link" -> navigate, "button" -> click

    @property
    def slug(self) -> str:
        return re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")

    @property
    def action_id(self) -> str:
        return hashlib.sha256(f"{self.role}|{self.name}|#{self.slug}".encode()).hexdigest()[:12]

    @property
    def kind(self) -> ActionKind:
        return "click" if self.role == "button" else "navigate"


_HOME = Control("Home", "link")
CONTROLS: Final[dict[str, tuple[Control, ...]]] = {
    "home": (
        Control("Products", "link"),
        Control("Feed", "link"),
        Control("Settings", "link"),
        Control("Help", "button"),
    ),
    "home-modal": (Control("Close", "button"),),
    "products": (_HOME, Control("Add to cart", "button"), Control("View cart", "link")),
    "sold-out": (Control("Back to products", "link"), _HOME),
    "cart": (Control("Checkout", "button"), Control("Continue shopping", "link")),
    "thanks": (_HOME,),
    "error": (Control("Retry", "button"), _HOME),
    "feed": (Control("Load more", "button"), _HOME),
    "settings": (_HOME,),
}

#: Static destination of every deterministic control. Stochastic ones are in `_Session.act`.
_STATIC_TARGET: Final[dict[tuple[str, str], str]] = {
    ("home", "Products"): "products",
    ("home", "Feed"): "feed",
    ("home", "Settings"): "settings",
    ("home", "Help"): "home-modal",
    ("home-modal", "Close"): "home",
    ("products", "Home"): "home",
    ("products", "View cart"): "cart",
    ("sold-out", "Back to products"): "products",
    ("sold-out", "Home"): "home",
    ("cart", "Continue shopping"): "products",
    ("thanks", "Home"): "home",
    ("error", "Retry"): "cart",
    ("error", "Home"): "home",
    ("feed", "Home"): "home",
    ("settings", "Home"): "home",
}

#: Raw network traffic per control (before sanitising). `{n}` is a fresh numeric id.
_RAW_CALLS: Final[dict[str, tuple[str, ...]]] = {
    "Products": ("GET /api/products?sort=new",),
    "Feed": ("GET /api/feed?cursor=0",),
    "Settings": ("GET /api/settings",),
    "Help": (),
    "Close": (),
    "Home": ("GET /api/home",),
    "Add to cart": ("POST /api/cart",),
    "View cart": ("GET /api/cart",),
    "Back to products": ("GET /api/products?sort=new",),
    "Continue shopping": ("GET /api/products?sort=new",),
    "Checkout": ("POST /api/checkout",),
    "Retry": ("GET /api/cart",),
    "Load more": ("GET /api/feed?cursor=1", "GET /api/feed?cursor=2"),
}
_HEARTBEAT: Final = "GET /api/visitors"


def normalise_endpoint(raw: str) -> str:
    """`METHOD /template`: drop the query string, template numeric path segments."""
    method, _, target = raw.partition(" ")
    path = target.split("?", 1)[0]
    segments = ["{id}" if seg.isdigit() else seg for seg in path.split("/")]
    return f"{method} {'/'.join(segments)}"


def action_labels() -> dict[str, str]:
    """`action_id` -> control name, for reports."""
    return {c.action_id: c.name for controls in CONTROLS.values() for c in controls}


def logical_of(bundle: CaptureBundle) -> str:
    """Ground-truth logical state of a capture (read from the screenshot path)."""
    path = bundle.screenshot_path or ""
    match = re.fullmatch(r"/sim/screenshots/([a-z-]+)\.png", path)
    if match is None:
        raise ValueError(f"capture carries no logical-state marker: {path!r}")
    return match.group(1)


def policy() -> ExpectationSet:
    return ExpectationSet(
        forbidden=(
            ExpectationNode(
                expectation_id="e-admin-link",
                polarity="must_not_exist",
                subject="admin-link",
                roles=("guest",),
                source_text="A guest must never see the admin link.",
            ),
            ExpectationNode(
                expectation_id="e-debug-panel",
                polarity="must_not_exist",
                subject="debug-panel",
                roles=("guest",),
                source_text="A guest must never see the debug panel.",
            ),
        )
    )


class DynamicApp:
    """`CrawlerPort` + `NetworkObservations` over the simulated app."""

    #: Read by the runner through `getattr(ports.network, "last_capture_ready", None)`.
    last_capture_ready: bool = True

    def __init__(self, seed: int = SEED) -> None:
        self.seed = seed
        self._render = random.Random(f"{seed}:render")
        self._outcome = random.Random(f"{seed}:outcome")
        self._pending: list[str] = []
        self._logical: str | None = None
        self._feed: list[str] = []
        self.closed = False
        #: Ground-truth bookkeeping, never read by the orchestrator.
        self.products_renders = 0
        self.products_renders_with_flaky = 0
        self.outcomes: list[tuple[str, str]] = []
        self.opens = 0
        self.acts = 0

    # -- rendering ---------------------------------------------------------

    def _cls(self, prefix: str) -> str:
        return f"{prefix}-" + "".join(self._render.choice(_ALNUM) for _ in range(6))

    def _new_feed_items(self) -> list[str]:
        return [
            f"{self._render.choice(_FEED_TITLES)} ({self._render.randint(1, 99)} likes)"
            for _ in range(FEED_BATCH)
        ]

    def _capture(self, logical: str) -> CaptureBundle:
        r = self._render
        visitors = f"{r.randint(40, 960)} people online"
        ad = f"Sponsored: {r.choice(_ADS)}"
        updated = f"Updated {r.randint(1, 59)} minutes ago"
        title = _TITLES[logical]

        anchors = "".join(
            f'<a id="{c.slug}" role="{c.role}">{c.name}</a>' for c in CONTROLS[logical]
        )
        if logical == "home-modal":
            dialog = (
                f'<div class="{self._cls("dlg")}" role="dialog" aria-modal="true">'
                f"<h2>Help</h2><p>Need assistance?</p>{anchors}</div>"
            )
            nav, extra = "", dialog
        else:
            nav, extra = anchors, ""

        body = _BODY[logical]
        ax_children: list[JSONValue] = [
            {"role": "status", "name": visitors},
            {"role": "complementary", "name": ad},
        ]
        for c in CONTROLS[logical]:
            ax_children.append({"role": c.role, "name": c.name, "selector": f"#{c.slug}"})
        if logical == "products":
            self.products_renders += 1
            if r.random() < FLAKY_RENDER_PROBABILITY:
                self.products_renders_with_flaky += 1
                body += (
                    f'<div class="{self._cls("promo")}" data-tag="admin-link">Admin console</div>'
                )
                ax_children.append({"role": "banner", "name": "Admin console"})
        if logical == "feed":
            items = "".join(f"<li>{text}</li>" for text in self._feed)
            body += f'<ul class="{self._cls("feed")}">{items}</ul>'
            ax_children.append(
                {
                    "role": "list",
                    "name": "feed",
                    "children": [{"role": "listitem", "name": text} for text in self._feed],
                }
            )
        ax_children.append({"role": "contentinfo", "name": updated})

        dom = (
            f"<html><head><title>{title}</title></head>"
            f'<body class="{self._cls("app")}">'
            f'<header class="{self._cls("hd")}"><span>{visitors}</span></header>'
            f'<aside class="{self._cls("ad")}"><span>{ad}</span></aside>'
            f'<nav class="{self._cls("nv")}">{nav}</nav>'
            f'<main class="{self._cls("mn")}">{body}{extra}</main>'
            f'<footer class="{self._cls("ft")}"><time>{updated}</time></footer>'
            "</body></html>"
        )
        ax_tree: JSONValue = {"role": "document", "name": title, "children": ax_children}
        return CaptureBundle(
            url=f"{BASE_URL}{_URLS[logical]}",
            dom=dom,
            ax_tree=ax_tree,
            screenshot_path=f"/sim/screenshots/{logical}.png",
            title=title,
        )

    def _arrive(self, logical: str) -> CaptureBundle:
        self._logical = logical
        if logical == "feed":
            self._feed = self._new_feed_items()
        return self._capture(logical)

    def sample(self, logical: str, times: int) -> list[tuple[str, JSONValue]]:
        """`times` fresh renders of one logical state, for offline volatility learning.

        Does not touch the session, the network buffer or the outcome stream.
        """
        out: list[tuple[str, JSONValue]] = []
        saved = (self._logical, list(self._feed))
        for _ in range(times):
            self._feed = self._new_feed_items() if logical == "feed" else []
            bundle = self._capture(logical)
            out.append((bundle.dom, bundle.ax_tree))
        self._logical, self._feed = saved
        return out

    # -- NetworkObservations ----------------------------------------------

    def drain(self) -> tuple[str, ...]:
        calls = tuple(self._pending)
        self._pending.clear()
        return calls

    def _emit(self, raw_calls: tuple[str, ...]) -> None:
        self._pending.extend(normalise_endpoint(raw) for raw in raw_calls)

    # -- CrawlerPort -------------------------------------------------------

    def open(self, url: str) -> CaptureBundle:
        if self.closed:
            raise NavigationError("crawler is closed")
        path = url[len(BASE_URL) :] if url.startswith(BASE_URL) else url
        logical = _PATH_TO_LOGICAL.get(path)
        if logical is None:
            raise NavigationError(f"no such page: {url}")
        self.opens += 1
        self._emit(("GET /api/page", _HEARTBEAT))
        return self._arrive(logical)

    def act(self, action: Action) -> CaptureBundle:
        if self.closed:
            raise ActionError("crawler is closed")
        if self._logical is None:
            raise ActionError(f"cannot act before opening a page: {action.action_id}")
        control = next(
            (c for c in CONTROLS[self._logical] if c.action_id == action.action_id), None
        )
        if control is None:
            raise ActionError(f"{action.action_id} is not available from {self._logical}")
        self.acts += 1

        raw = list(_RAW_CALLS[control.name])
        source = self._logical
        if (source, control.name) == ("products", "Add to cart"):
            target = "cart" if self._outcome.random() < ADD_TO_CART_SUCCESS else "sold-out"
            self.outcomes.append((control.name, target))
        elif (source, control.name) == ("cart", "Checkout"):
            target = "error" if self._outcome.random() < CHECKOUT_ERROR else "thanks"
            self.outcomes.append((control.name, target))
            if target == "thanks":
                raw.append(f"GET /api/orders/{self._outcome.randint(10000, 99999)}?expand=items")
        elif (source, control.name) == ("feed", "Load more"):
            self._feed = [*self._feed, *self._new_feed_items()]
            self._logical = "feed"
            raw.append(_HEARTBEAT)
            self._emit(tuple(raw))
            return self._capture("feed")
        else:
            target = _STATIC_TARGET[(source, control.name)]
        raw.append(_HEARTBEAT)
        self._emit(tuple(raw))
        return self._arrive(target)

    def enumerate_actions(self, bundle: CaptureBundle) -> tuple[Action, ...]:
        found = re.findall(r'<a id="([^"]+)" role="([^"]+)">([^<]+)</a>', bundle.dom)
        actions: list[Action] = []
        for slug, role, name in found:
            control = Control(name, role)
            verb = "click" if role == "button" else "follow"
            actions.append(
                Action(
                    action_id=control.action_id,
                    kind=control.kind,
                    target=f"#{slug}",
                    label=f'{verb} "{name}"',
                )
            )
        return tuple(actions)

    def close(self) -> None:
        self.closed = True
