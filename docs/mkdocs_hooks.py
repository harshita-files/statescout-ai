"""MkDocs build hooks for the documentation portal (``docs/portal``).

1. **Includes.** A portal page line ``--8<-- "path/in/repo.md"`` is replaced by
   that file's content, so module READMEs, ADRs and schema docs are published
   from where they live instead of being copied (and drifting). Relative links
   in the included file are rewritten for the page it now appears on: to the
   portal page that includes the target, when there is one, else to the file
   on GitHub. A missing include fails the build.

2. **House style.** The site uses no emoji and no em dashes. Text the portal does
   not own (included files, code docstrings, API descriptions, the demo page) is
   normalised as it is rendered, so the source files stay untouched: em dashes
   become hyphens, emoji are removed, and a check mark used as a table value
   becomes "Yes".

3. **Generated pages.** ``openapi.json`` is generated from
   ``services.api.main.app`` for the REST reference, and ``demo/exploration-graph.html``
   from ``apps.agent.orchestrator.demo_visual`` for the demonstrations page.
   Importing the app opens no database connection (that happens only in its
   lifespan, which never runs), and the demo runs offline on scripted fakes.
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]

INCLUDE = re.compile(r'^--8<-- "([^"]+)"[ \t]*$', re.MULTILINE)
INLINE_LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
REFERENCE_LINK = re.compile(r"^(\[[^\]]+\]:[ \t]*)(\S+)", re.MULTILINE)

EM_DASH = re.compile(chr(0x2014) + "|&mdash;|&#8212;|&#x2014;")

#: Code-point ranges of pictographs, dingbats and symbols with emoji presentation,
#: plus the variation selector, keycap and joiner that build emoji sequences.
_EMOJI_RANGES = (
    (0x1F000, 0x1FAFF),
    (0x2300, 0x23FF),
    (0x2600, 0x27BF),
    (0x2B00, 0x2BFF),
    (0x25B6, 0x25B6),
    (0x25C0, 0x25C0),
    (0x25FB, 0x25FE),
    (0x2934, 0x2935),
    (0x3030, 0x3030),
    (0x303D, 0x303D),
    (0x3297, 0x3297),
    (0x3299, 0x3299),
    (0x200D, 0x200D),
    (0x20E3, 0x20E3),
    (0xFE0F, 0xFE0F),
)
EMOJI = re.compile("[" + "".join(f"{chr(lo)}-{chr(hi)}" for lo, hi in _EMOJI_RANGES) + "]")
#: A heavy check mark used as a table value, e.g. a "Required" column.
CHECK_MARK = re.compile(chr(0x2714) + chr(0xFE0F) + "?")

#: repository path of an included file -> the portal page that includes it
_included_by: dict[str, str] = {}


def plain(text: str, *, check_mark: str = "") -> str:
    """Apply the house style: hyphens for em dashes, no emoji."""
    text = EM_DASH.sub("-", text)
    text = CHECK_MARK.sub(check_mark, text)
    return EMOJI.sub("", text)


def on_config(config: Any, **_: Any) -> Any:
    for key in ("site_name", "site_description", "copyright"):
        if config.get(key):
            config[key] = plain(config[key])
    return config


def on_files(files: Any, config: Any, **_: Any) -> Any:
    _included_by.clear()
    for file in files.documentation_pages():
        text = Path(file.abs_src_path).read_text(encoding="utf-8")
        for source in INCLUDE.findall(text):
            _included_by.setdefault(source, file.src_uri)
    return files


def on_page_markdown(markdown: str, page: Any, config: Any, **_: Any) -> str:
    branch = config.extra.get("source_branch", "main")
    repo_url = config.repo_url.rstrip("/")

    def expand(match: re.Match[str]) -> str:
        source = match.group(1)
        path = REPO_ROOT / source
        if not path.is_file():
            raise FileNotFoundError(f"{page.file.src_uri}: included file not found: {source}")
        text = path.read_text(encoding="utf-8")

        def rewrite(target: str) -> str:
            if re.match(r"^([a-z][a-z0-9+.-]*:|#|/)", target, re.IGNORECASE):
                return target  # absolute URL, mailto:, in-page anchor, site-absolute
            target_path, _, anchor = target.partition("#")
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(source), target_path))
            if resolved == source:  # a link into the same document
                return f"#{anchor}" if anchor else target
            portal_page = _included_by.get(resolved)
            if portal_page:
                here = posixpath.dirname(page.file.src_uri)
                link = posixpath.relpath(portal_page, here)
                # GitHub keeps "--" where a heading had an em dash; MkDocs' slugs
                # collapse it to "-".
                anchor = re.sub(r"-{2,}", "-", anchor)
            else:
                kind = "tree" if (REPO_ROOT / resolved).is_dir() else "blob"
                link = f"{repo_url}/{kind}/{branch}/{resolved}"
            return f"{link}#{anchor}" if anchor else link

        text = INLINE_LINK.sub(lambda m: m.group(1) + rewrite(m.group(2)) + m.group(3), text)
        return REFERENCE_LINK.sub(lambda m: m.group(1) + rewrite(m.group(2)), text)

    return plain(INCLUDE.sub(expand, markdown), check_mark="Yes")


def on_page_content(html: str, page: Any, **_: Any) -> str:
    # Catches what the markdown pass cannot see: rendered code docstrings, and the
    # table-of-contents entries their headings add.
    def clean(items: Any) -> None:
        for item in items:
            item.title = plain(item.title)
            clean(item.children)

    clean(page.toc)
    return plain(html)


def on_post_build(config: Any, **_: Any) -> None:
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    from apps.agent.orchestrator.demo_visual import render
    from services.api.main import app

    site = Path(config.site_dir)
    spec = json.dumps(app.openapi(), indent=2, ensure_ascii=False)
    (site / "openapi.json").write_text(plain(spec) + "\n", encoding="utf-8")

    demo = site / "demo" / "exploration-graph.html"
    demo.parent.mkdir(parents=True, exist_ok=True)
    demo.write_text(plain(_site_theme(render())), encoding="utf-8")


#: The site's GitHub dark palette, pinned onto the embedded demo page. The page
#: otherwise follows the visitor's light/dark preference and its own colours.
DEMO_THEME = (
    "<style>:root{--bg:#0d1117;--fg:#e6edf3;--mut:#8b949e;--card:#161b22;"
    "--line:#3fb950;--cyc:#d29922;--bad:#f85149;--ok:#3fb950}</style>"
)
#: Arrowhead fills hard-coded in the demo's SVG markers -> the same palette.
DEMO_MARKERS = {'fill="#3b82f6"': 'fill="#3fb950"', 'fill="#f59e0b"': 'fill="#d29922"'}


def _site_theme(page: str) -> str:
    for old, new in DEMO_MARKERS.items():
        page = page.replace(old, new)
    return page.replace("</head>", DEMO_THEME + "</head>", 1)
