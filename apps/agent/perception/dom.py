"""Deterministic extraction of relevant DOM evidence."""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser


@dataclass(frozen=True, slots=True)
class DOMElement:
    """Relevant evidence extracted from one HTML element."""

    tag: str
    element_id: str | None = None
    classes: tuple[str, ...] = ()
    role: str | None = None
    aria_label: str | None = None
    href: str | None = None
    disabled: bool = False
    hidden: bool = False
    text: str = ""


class _DOMParser(HTMLParser):
    """Small HTML parser that keeps only UI-relevant evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[DOMElement] = []
        self._current: DOMElement | None = None
        self._text: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        attributes = dict(attrs)

        classes = tuple(value for value in (attributes.get("class") or "").split() if value)

        style = (attributes.get("style") or "").replace(" ", "").lower()

        self._current = DOMElement(
            tag=tag,
            element_id=attributes.get("id"),
            classes=classes,
            role=attributes.get("role"),
            aria_label=attributes.get("aria-label"),
            href=attributes.get("href"),
            disabled="disabled" in attributes,
            hidden="hidden" in attributes or "display:none" in style,
        )
        self._text = []

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._current is None:
            return

        element = DOMElement(
            tag=self._current.tag,
            element_id=self._current.element_id,
            classes=self._current.classes,
            role=self._current.role,
            aria_label=self._current.aria_label,
            href=self._current.href,
            disabled=self._current.disabled,
            hidden=self._current.hidden,
            text=" ".join(" ".join(self._text).split()),
        )

        self.elements.append(element)
        self._current = None
        self._text = []


def extract_dom_elements(dom: str) -> tuple[DOMElement, ...]:
    """Extract UI-relevant evidence from serialized HTML."""
    parser = _DOMParser()
    parser.feed(dom)
    parser.close()
    return tuple(parser.elements)
