"""The anatomy of a Markdown page body: sections, pipe tables, links, and the inline formatting facts.

Pure functions on the Markdown the Remote MCP Server renders for a Confluence page (``PageRecord.body``
when ``body_format`` is ``markdown``), standard library only. They know Markdown, not what a page is
about: a consumer builds its own page reader on them and cites a section by heading, anchor and hash.

The server's rendering flattens cell formatting: bold runs are glued to the text that follows them
(``**Label **text``), line breaks inside a cell vanish, and strikethrough wraps fragments. ``strike``,
``bold_runs`` and ``split_on_bold`` read that text as it is.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from functools import cached_property
from urllib.parse import parse_qs, urlparse

_HEADING = re.compile(r"^(#{1,6})[ \t]+(.*?)[ \t]*$")
_FENCE = re.compile(r"^(`{3,}|~{3,})")
_SEPARATOR_CELL = re.compile(r"^:?-+:?$")
_CELL_SPLIT = re.compile(r"(?<!\\)\|")
_LINK = re.compile(r"(?<!!)\[([^\]]*)\]\(\s*(\S+?)(?:\s+(?:\"[^\"]*\"|'[^']*'))?\s*\)")
_STRIKE = re.compile(r"~~(.+?)~~", re.DOTALL)
# a run opens with ** not followed by a third * (so ``*italic***bold **`` opens at the right star)
_BOLD = re.compile(r"\*\*(?!\*)(.+?)(?<!\*)\*\*", re.DOTALL)
_PAGE_ID_PATH = re.compile(r"/pages/(\d+)(?:/|$)")


@dataclass(frozen=True)
class Section:
    """One heading and the text under it, up to the next heading of any level.

    ``start`` is the line index of the heading (0 for the text before the first heading, which is a
    section of level 0 with an empty heading); ``end`` is the line index after the section's last line.
    ``text`` is the section's lines without the heading line, leading and trailing blank lines removed.
    """

    level: int
    heading: str
    anchor: str
    start: int
    end: int
    text: str

    @cached_property
    def sha256(self) -> str:
        """SHA-256 of ``text`` as UTF-8: the hash a citation names next to the page's body hash."""
        return hashlib.sha256(self.text.encode("utf-8")).hexdigest()

    @property
    def chars(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class Table:
    """A GitHub pipe table: the header cells, the body rows (each as wide as the header), and its line span."""

    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    start: int
    end: int

    @property
    def width(self) -> int:
        return len(self.header)


@dataclass(frozen=True)
class Link:
    """A Markdown link; ``page_id`` is the Confluence page id when the URL names one, else None."""

    label: str
    url: str
    page_id: str | None = None


def _lines(markdown: str) -> list[str]:
    return (markdown or "").splitlines()


def heading_anchor(heading: str) -> str:
    """The Confluence cloud heading anchor for a page URL: spaces to ``-``, other punctuation dropped.

    ``Context Table`` gives ``Context-Table``, ``Step 2: Related Links (draft)`` gives ``Step-2-Related-Links-draft``.
    """
    return re.sub(r"[^\w-]", "", heading.strip().replace(" ", "-"))


def sections(markdown: str) -> list[Section]:
    """Split a Markdown body on its ATX headings (``#`` to ``######``), ignoring headings inside code fences.

    Text before the first heading is a section with level 0 and heading ``""`` when it is not blank.
    """
    lines = _lines(markdown)
    marks: list[tuple[int, int, str]] = []  # (line index, level, heading)
    fence: str | None = None
    for index, line in enumerate(lines):
        opened = _FENCE.match(line.strip())
        if opened:
            if fence is None:
                fence = opened.group(1)[0]
            elif opened.group(1)[0] == fence:
                fence = None
            continue
        if fence is not None:
            continue
        match = _HEADING.match(line)
        if match:
            heading = re.sub(r"[ \t]+#+$", "", match.group(2)).strip()
            marks.append((index, len(match.group(1)), heading))

    out: list[Section] = []

    def _add(level: int, heading: str, start: int, body_start: int, end: int) -> None:
        text = "\n".join(lines[body_start:end]).strip("\n")
        if level == 0 and not text.strip():
            return
        out.append(Section(level, heading, heading_anchor(heading), start, end, text))

    first = marks[0][0] if marks else len(lines)
    _add(0, "", 0, 0, first)
    for n, (index, level, heading) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(lines)
        _add(level, heading, index, index + 1, end)
    return out


def find_section(found: Iterable[Section], heading: str) -> Section | None:
    """The section whose heading equals ``heading`` case-insensitively, else the first whose heading contains it."""
    wanted = heading.strip().casefold()
    if not wanted:
        return None
    candidates = list(found)
    for section in candidates:
        if section.heading.casefold() == wanted:
            return section
    for section in candidates:
        if wanted in section.heading.casefold():
            return section
    return None


def _cells(line: str) -> list[str]:
    text = line.strip()
    parts = _CELL_SPLIT.split(text)
    if text.startswith("|"):
        parts = parts[1:]
    if text.endswith("|") and not text.endswith("\\|"):
        parts = parts[:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def _is_separator(line: str) -> bool:
    cells = _cells(line)
    return bool(cells) and "|" in line and all(_SEPARATOR_CELL.match(c) for c in cells if c) and any(cells)


def _fit(cells: list[str], width: int) -> tuple[str, ...]:
    if len(cells) < width:
        cells = cells + [""] * (width - len(cells))
    elif len(cells) > width:
        cells = cells[: width - 1] + [" | ".join(cells[width - 1 :])]
    return tuple(cells)


def tables(text: str) -> list[Table]:
    """Every GitHub pipe table (header row, ``| --- |`` separator, body rows) in ``text``.

    Cells are stripped and ``\\|`` inside a cell becomes ``|``. A row shorter than the header is padded
    with empty cells; a longer one keeps the extras in its last cell, joined by `` | ``.
    """
    lines = _lines(text)
    out: list[Table] = []
    index = 0
    while index + 1 < len(lines):
        if "|" in lines[index] and _is_separator(lines[index + 1]) and not _is_separator(lines[index]):
            header = tuple(_cells(lines[index]))
            rows: list[tuple[str, ...]] = []
            end = index + 2
            while end < len(lines) and "|" in lines[end] and lines[end].strip():
                rows.append(_fit(_cells(lines[end]), len(header)))
                end += 1
            out.append(Table(header, tuple(rows), index, end))
            index = end
            continue
        index += 1
    return out


def page_id_of(url: str) -> str | None:
    """The Confluence page id in a URL (``pageId=<digits>`` or ``/pages/<digits>``), else None."""
    parsed = urlparse(url)
    query = parse_qs(parsed.query).get("pageId")
    if query and query[0].isdigit():
        return query[0]
    match = _PAGE_ID_PATH.search(parsed.path)
    return match.group(1) if match else None


def links(text: str) -> list[Link]:
    """Every ``[label](url)`` in ``text`` (images, ``![alt](src)``, are not links)."""
    return [Link(m.group(1).strip(), m.group(2), page_id_of(m.group(2))) for m in _LINK.finditer(text or "")]


def strike(text: str) -> tuple[str, bool]:
    """The text with its ``~~...~~`` markers removed, and whether any part of it was struck through."""
    clean, count = _STRIKE.subn(r"\1", text or "")
    return clean, count > 0


def bold_runs(text: str) -> list[str]:
    """The stripped texts inside ``**...**`` runs, in order (``**Label **`` yields ``Label``)."""
    return [m.group(1).strip() for m in _BOLD.finditer(text or "")]


def split_on_bold(text: str) -> list[tuple[str, str]]:
    """Cut ``text`` at each bold run into ``(label, following text)`` pairs.

    ``**A **one *[x]***B **two`` gives ``[("A", "one *[x]*"), ("B", "two")]``. Text before the first bold
    run, when there is any, comes first as a pair with an empty label. Call ``strike`` first when the
    struck markers should not be part of the labels.
    """
    matches = list(_BOLD.finditer(text or ""))
    out: list[tuple[str, str]] = []
    if not matches:
        return [("", text.strip())] if text and text.strip() else []
    lead = text[: matches[0].start()].strip()
    if lead:
        out.append(("", lead))
    for n, match in enumerate(matches):
        stop = matches[n + 1].start() if n + 1 < len(matches) else len(text)
        out.append((match.group(1).strip(), text[match.end() : stop].strip()))
    return out


def section_sha256(section: Section) -> str:
    """``section.sha256`` as a function, for callers that hold the dataclass by duck type."""
    return section.sha256


__all__ = [
    "Link",
    "Section",
    "Table",
    "bold_runs",
    "find_section",
    "heading_anchor",
    "links",
    "page_id_of",
    "section_sha256",
    "sections",
    "split_on_bold",
    "strike",
    "tables",
]
