"""Script and style source is not UI: it must never become element text or map summary."""

from __future__ import annotations

from apps.agent.contracts import CaptureBundle
from apps.agent.perception.dom import extract_dom_elements
from apps.agent.perception.semantic_map import build_semantic_map

JS = "if(e==38||e==35)break a;b=-1}if(b<0)return null"
PAGE = (
    f"<html><head><style>.x{{color:red}} a{{margin:-1px}}</style><script>{JS}</script></head>"
    f"<body><a href='/home' id='h'>Home</a><button>Buy</button>"
    f"<template><b>tpl</b></template><noscript>enable js</noscript>"
    f"<script>var s='<a>fake</a>';{JS}</script></body></html>"
)


def test_script_style_and_template_are_not_elements() -> None:
    tags = {e.tag for e in extract_dom_elements(PAGE)}
    assert not tags & {"script", "style", "template"}
    assert {"a", "button"} <= tags


def test_script_source_never_appears_in_any_element_text() -> None:
    assert all(JS not in e.text and "margin" not in e.text for e in extract_dom_elements(PAGE))


def test_semantic_map_summary_and_names_exclude_script_source() -> None:
    ax = {
        "role": "RootWebArea",
        "name": "p",
        "children": [{"role": "link", "name": "Home"}, {"role": "button", "name": "Buy"}],
    }
    smap = build_semantic_map(CaptureBundle("http://a.test/", PAGE, ax), "guest", "s")
    assert "e==38" not in smap.summary
    assert all("e==38" not in (e.name or "") for e in smap.elements)
    assert {e.name for e in smap.elements} >= {"Home", "Buy"}
