"""Deterministic extraction of relevant DOM evidence."""

from __future__ import annotations

from dataclasses import dataclass, replace
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
    #: Declared decorative by the author; see `UIElement.decorative`.
    decorative: bool = False
    #: An image's `alt` text, which is its accessible name.
    alt: str | None = None
    #: For `<input>`: its `type` and `value`, which name a button-like input.
    input_type: str | None = None
    value: str | None = None
    #: For a form field: the name its label gives it (`aria-labelledby`, a
    #: `<label for>` or a wrapping `<label>`, then `title`, then `placeholder`).
    #: Empty when nothing names it; its `id` is never a name.
    label: str | None = None


#: Containers whose content is code or inert markup, never rendered UI. Their text (page
#: JavaScript, CSS) must not become element text, a semantic-map summary, or audit evidence.
_NON_UI = frozenset({"script", "style", "template", "noscript"})
#: Void elements of the document head. They are never rendered UI, and recording
#: `<link rel="stylesheet">` let the correlator read the *tag* `link` as the
#: accessibility *role* `link`: a phantom unnamed hyperlink on every page.
_METADATA = frozenset({"link", "meta", "base"})


#: Elements with no content and no end tag. The browser serialises them as
#: `<input ...>` without a slash, so they must be recorded at their start tag:
#: waiting for an end tag let the next element overwrite them.
_VOID = frozenset({"input", "img", "area", "embed", "source", "track", "br", "hr", "wbr", "col"})

#: Input types that are buttons, named by their value or alt, not by a label.
_BUTTON_INPUTS = frozenset({"submit", "button", "reset", "image"})


def is_form_field(element: DOMElement) -> bool:
    """A control the user fills in, which a label must name."""
    if element.tag in {"select", "textarea"}:
        return True
    return element.tag == "input" and element.input_type not in _BUTTON_INPUTS


def _is_decorative(tag: str, attributes: dict[str, str | None]) -> bool:
    """The author asked assistive technology to skip this element."""
    if tag == "img" and "alt" in attributes and not (attributes.get("alt") or "").strip():
        return True
    if (attributes.get("role") or "").strip().lower() in {"presentation", "none"}:
        return True
    return (attributes.get("aria-hidden") or "").strip().lower() == "true"


class _DOMParser(HTMLParser):
    """Small HTML parser that keeps only UI-relevant evidence."""

    def __init__(self) -> None:
        super().__init__()
        self.elements: list[DOMElement] = []
        self._current: DOMElement | None = None
        self._text: list[str] = []
        self._skip = 0
        # Label evidence, resolved once the whole document is read.
        self._open_labels: list[tuple[str | None, list[str], list[int]]] = []
        self._seq = 0
        self._current_seq = -1
        self.label_for: dict[str, list[str]] = {}
        self.wrapped: dict[int, str] = {}
        self.fallback: dict[int, tuple[str | None, str | None, str | None]] = {}
        self.seq_of: list[int] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        if tag in _NON_UI:
            self._skip += 1
            return
        if self._skip or tag in _METADATA:
            return
        attributes = dict(attrs)
        self._seq += 1
        if tag == "label":
            self._open_labels.append((attributes.get("for"), [], []))
        elif tag in {"input", "select", "textarea"}:
            for _, _, fields in self._open_labels:
                fields.append(self._seq)
            self.fallback[self._seq] = (
                attributes.get("aria-labelledby"),
                attributes.get("title"),
                attributes.get("placeholder"),
            )
        input_type = (attributes.get("type") or "").strip().lower() if tag == "input" else None

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
            hidden="hidden" in attributes
            or "display:none" in style
            or "visibility:hidden" in style
            or input_type == "hidden",
            decorative=_is_decorative(tag, attributes),
            alt=attributes.get("alt"),
            input_type=input_type,
            value=attributes.get("value"),
        )
        self._current_seq = self._seq
        self._text = []
        if tag in _VOID:
            self._record()

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        for _, text, _ in self._open_labels:
            text.append(data)
        if self._current is not None:
            self._text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag in _NON_UI:
            self._skip = max(0, self._skip - 1)
            return
        if self._skip:
            return
        if tag == "label" and self._open_labels:
            target, text, fields = self._open_labels.pop()
            name = " ".join(" ".join(text).split())
            if target:
                self.label_for.setdefault(target, []).append(name)
            for seq in fields:
                self.wrapped.setdefault(seq, name)
        self._record()

    def _record(self) -> None:
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
            decorative=self._current.decorative,
            alt=self._current.alt,
            input_type=self._current.input_type,
            value=self._current.value,
        )

        self.elements.append(element)
        self.seq_of.append(self._current_seq)
        self._current = None
        self._text = []


def extract_dom_elements(dom: str) -> tuple[DOMElement, ...]:
    """Extract UI-relevant evidence from serialized HTML."""
    parser = _DOMParser()
    parser.feed(dom)
    parser.close()
    text_by_id = {e.element_id: e.text for e in parser.elements if e.element_id}
    out: list[DOMElement] = []
    for element, seq in zip(parser.elements, parser.seq_of, strict=True):
        if is_form_field(element):
            element = replace(element, label=_field_label(element, seq, parser, text_by_id))
        out.append(element)
    return tuple(out)


def _field_label(
    element: DOMElement, seq: int, parser: _DOMParser, text_by_id: dict[str, str]
) -> str:
    labelledby, title, placeholder = parser.fallback.get(seq, (None, None, None))
    if labelledby:
        named = " ".join(text_by_id.get(i, "") for i in labelledby.split()).strip()
        if named:
            return named
    native = [parser.wrapped.get(seq, "")]
    if element.element_id:
        native += parser.label_for.get(element.element_id, [])
    joined = " ".join(n for n in native if n).strip()
    return joined or (title or "").strip() or (placeholder or "").strip()
