"""
State fingerprinting for StateScout AI — Track D.

Produces a deterministic SHA-256 fingerprint for any UI state, keyed on
(normalized DOM, URL, AX-tree).  Normalization strips volatile attributes
(session ids, CSRF tokens, dynamic form ids, timestamps) so that semantically
identical states always hash identically, regardless of per-request noise.
"""

import hashlib
import re

# ---------------------------------------------------------------------------
# Patterns for attributes whose *values* are volatile / per-session
# ---------------------------------------------------------------------------

# Attribute names that always carry dynamic values and should be removed
# entirely from the DOM string before hashing.
DYNAMIC_ATTR_NAMES: set[str] = {
    "nonce",
    "data-reactid",
    "data-testid-random",
    # Session / auth tokens — common patterns in real apps
    "data-session",
    "data-csrf",
    "data-token",
    "data-request-id",
    "data-tracking-id",
}

# Build a single compiled regex that matches any of the above attributes
# and their quoted values, including any leading whitespace.
#   e.g. ' data-session="sess_abc123"'  →  removed
_DYNAMIC_ATTR_RE = re.compile(
    r'\s+(?:' + '|'.join(re.escape(a) for a in DYNAMIC_ATTR_NAMES) + r')="[^"]*"',
    re.IGNORECASE,
)

# Attribute *values* that look like auto-generated hex/alphanumeric IDs.
# Covers two forms:
#   1. Pure hex values:         id="3f9a1bcc"          (8+ hex chars)
#   2. Prefixed hex values:     id="form-3f9a1b"        (any prefix + dash + 4+ hex chars)
# Both patterns appear in real apps for auto-generated form/component ids.
_HEX_ID_ATTR_RE = re.compile(
    r'\s+(?:id|data-[\w-]*)="(?:[a-f0-9]{8,}|[\w]+-[a-f0-9]{4,})"',
    re.IGNORECASE,
)

# Values prefixed with a token-style prefix like "sess_…", "csrf_…", "tok_…"
# These appear in attribute values, e.g. data-session="sess_abc123xyz".
_PREFIXED_TOKEN_RE = re.compile(
    r'\b(?:sess|csrf|tok|req|trk)_[A-Za-z0-9_-]+\b',
)

# Long numeric timestamps (10+ digits) embedded anywhere in the DOM string.
_TIMESTAMP_RE = re.compile(r'\d{10,}')

# Collapse runs of whitespace (normalises indented HTML).
_WHITESPACE_RE = re.compile(r'\s+')


def normalize_state(dom: str, url: str, ax_tree: str) -> str:
    """
    Return a canonical string representation of a UI state.

    Strips all volatile / per-session noise so that two representations of
    the *same* logical UI state always produce the same string, regardless of
    dynamically generated ids, CSRF tokens, session values, or timestamps.

    Parameters
    ----------
    dom:
        Raw HTML snippet for the page (or the relevant subtree).
    url:
        The full URL of the page (scheme + path + query, no fragment).
    ax_tree:
        Accessibility-tree summary string produced by Track A's crawler.

    Returns
    -------
    str
        Normalized composite string ``"{url}|{dom}|{ax_tree}"``.
    """
    # 1. Remove known dynamic attribute names and their values completely
    dom = _DYNAMIC_ATTR_RE.sub('', dom)

    # 2. Remove hex-looking id / data-* attribute values
    dom = _HEX_ID_ATTR_RE.sub('', dom)

    # 3. Remove prefixed token values (sess_…, csrf_…, etc.) from text nodes
    dom = _PREFIXED_TOKEN_RE.sub('', dom)

    # 4. Strip long numeric timestamps
    dom = _TIMESTAMP_RE.sub('', dom)

    # 5. Collapse whitespace (handles indented / multi-line HTML)
    dom = _WHITESPACE_RE.sub(' ', dom).strip()

    # 6. Strip spaces that appear immediately inside tag boundaries.
    #    e.g. "<h1> Home </h1>" (from indented HTML) → "<h1>Home</h1>"
    dom = re.sub(r'>\s+', '>', dom)
    dom = re.sub(r'\s+<', '<', dom)

    return f"{url}|{dom}|{ax_tree}"


def fingerprint(dom: str, url: str, ax_tree: str) -> str:
    """
    Return a deterministic SHA-256 fingerprint for a UI state.

    Parameters
    ----------
    dom, url, ax_tree:
        Same as :func:`normalize_state`.

    Returns
    -------
    str
        64-character lowercase hex string (SHA-256 digest).
    """
    normalized = normalize_state(dom, url, ax_tree)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def fingerprint_bundle(bundle: object) -> str:
    """Return a fingerprint for a CaptureBundle (GraphPort.fingerprint contract).

    This is the entry point the orchestrator uses.  It unpacks dom, url, and
    ax_tree from the bundle and delegates to :func:`fingerprint`.

    The ``ax_tree`` field on a real ``CaptureBundle`` may be a dict (raw CDP
    JSON) or a string summary.  We serialize it to a stable string before
    hashing so the fingerprint is deterministic regardless of which form Track
    A delivers.

    Parameters
    ----------
    bundle:
        Any object with ``url: str``, ``dom: str``, and ``ax_tree`` attributes.
        Typed as ``object`` to avoid importing ``CaptureBundle`` here and
        creating a circular dependency; the caller (GraphStore / main.py) holds
        the concrete type.
    """
    import json as _json

    url: str = getattr(bundle, "url", "")
    dom: str = getattr(bundle, "dom", "")
    ax_raw = getattr(bundle, "ax_tree", "")
    if isinstance(ax_raw, (dict, list)):
        ax_tree = _json.dumps(ax_raw, sort_keys=True, ensure_ascii=False)
    else:
        ax_tree = str(ax_raw)
    return fingerprint(dom, url, ax_tree)
