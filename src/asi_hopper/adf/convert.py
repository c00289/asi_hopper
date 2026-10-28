"""ADF <-> Markdown.

``adf_to_markdown`` handles what Jira descriptions and comments actually contain: paragraphs,
headings, marks (strong, em, code, strike, link, underline), bullet / ordered / task lists, code
blocks, block quotes, rules, tables, panels, mentions, emoji, dates, status lozenges, inline cards,
hard breaks, and media placeholders. Unknown nodes degrade to their text, never to an exception.

``markdown_to_adf`` is the reverse, kept for ADF payloads built in Python and for the round-trip
tests (no verb writes to Jira; the write side is delayed indefinitely by owner decision):
headings, paragraphs, bullet / ordered / task lists, fenced code, block quotes, rules, and the
inline marks. It is deliberately small; anything it does not understand becomes a paragraph.
"""

from __future__ import annotations

import re
from typing import Any

# ----------------------------------------------------------------------------- ADF -> Markdown


def _marks(text: str, marks: list[dict[str, Any]] | None) -> str:
    if not marks or not text:
        return text
    for mark in marks:
        kind = mark.get("type")
        if kind == "code":
            text = f"`{text}`"
        elif kind == "strong":
            text = f"**{text}**"
        elif kind == "em":
            text = f"*{text}*"
        elif kind == "strike":
            text = f"~~{text}~~"
        elif kind == "underline":
            text = f"__{text}__"
        elif kind == "link":
            href = (mark.get("attrs") or {}).get("href", "")
            text = f"[{text}]({href})" if href else text
    return text


def _inline(nodes: list[dict[str, Any]] | None) -> str:
    out: list[str] = []
    for node in nodes or []:
        kind = node.get("type")
        attrs = node.get("attrs") or {}
        if kind == "text":
            out.append(_marks(node.get("text", ""), node.get("marks")))
        elif kind == "hardBreak":
            out.append("  \n")
        elif kind == "mention":
            out.append(attrs.get("text") or f"@{attrs.get('id', '')}")
        elif kind == "emoji":
            out.append(attrs.get("text") or attrs.get("shortName") or "")
        elif kind == "date":
            out.append(attrs.get("timestamp", ""))
        elif kind == "status":
            out.append(f"[{attrs.get('text', '')}]")
        elif kind == "inlineCard":
            url = attrs.get("url", "")
            out.append(f"<{url}>" if url else "")
        elif kind == "mediaInline":
            out.append(f"[media {attrs.get('id', '')}]")
        else:  # unknown inline node: keep any text it carries
            out.append(_inline(node.get("content")))
    return "".join(out)


def _blocks(nodes: list[dict[str, Any]] | None, depth: int = 0) -> list[str]:
    out: list[str] = []
    for node in nodes or []:
        out.extend(_block(node, depth))
    return out


def _list(node: dict[str, Any], depth: int, ordered: bool, task: bool = False) -> list[str]:
    lines: list[str] = []
    indent = "  " * depth
    for i, item in enumerate(node.get("content") or [], start=1):
        if task:
            state = (item.get("attrs") or {}).get("state")
            marker = "- [x]" if state == "DONE" else "- [ ]"
        else:
            marker = f"{i}." if ordered else "-"
        content = item.get("content") or []
        if task:
            lines.append(f"{indent}{marker} {_inline(content)}".rstrip())
            continue
        first, rest = (content[0] if content else {"type": "paragraph"}), content[1:]
        head = _block(first, depth + 1)
        lines.append(f"{indent}{marker} {head[0].lstrip() if head else ''}".rstrip())
        lines.extend(h for h in head[1:])
        for sub in rest:
            lines.extend(_block(sub, depth + 1))
    return lines


def _table(node: dict[str, Any]) -> list[str]:
    rows: list[list[str]] = []
    for row in node.get("content") or []:
        cells = []
        for cell in row.get("content") or []:
            cells.append(" ".join(_blocks(cell.get("content"))).replace("|", "\\|").replace("\n", " ").strip())
        rows.append(cells)
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * width]
    out.extend("| " + " | ".join(r) + " |" for r in rows[1:])
    return out


def _block(node: dict[str, Any], depth: int = 0) -> list[str]:
    kind = node.get("type")
    attrs = node.get("attrs") or {}
    content = node.get("content")
    indent = "  " * depth
    if kind == "paragraph":
        return [indent + _inline(content)]
    if kind == "heading":
        return [f"{'#' * int(attrs.get('level', 1))} {_inline(content)}"]
    if kind == "bulletList":
        return _list(node, depth, ordered=False)
    if kind == "orderedList":
        return _list(node, depth, ordered=True)
    if kind == "taskList":
        return _list(node, depth, ordered=False, task=True)
    if kind == "codeBlock":
        lang = attrs.get("language") or ""
        return [f"```{lang}", _inline(content), "```"]
    if kind == "blockquote":
        return [f"> {line}" for line in _blocks(content)]
    if kind == "rule":
        return ["---"]
    if kind == "table":
        return _table(node)
    if kind == "panel":
        label = str(attrs.get("panelType", "note")).capitalize()
        inner = _blocks(content)
        return [f"> **{label}:** {inner[0] if inner else ''}"] + [f"> {line}" for line in inner[1:]]
    if kind == "expand" or kind == "nestedExpand":
        title = attrs.get("title") or "Details"
        return [f"**{title}**"] + _blocks(content)
    if kind in {"mediaSingle", "mediaGroup"}:
        ids = [((m.get("attrs") or {}).get("id") or "") for m in content or []]
        return [f"[media {', '.join(i for i in ids if i)}]"]
    if kind == "doc":
        return _blocks(content)
    if kind == "text":
        return [indent + _marks(node.get("text", ""), node.get("marks"))]
    return _blocks(content)  # unknown container: flatten


def adf_to_markdown(doc: dict[str, Any] | None) -> str:
    """Render an ADF document (or any node) as Markdown. Blocks are separated by blank lines."""
    if not doc:
        return ""
    if doc.get("type") == "doc":
        parts: list[str] = []
        for node in doc.get("content") or []:
            lines = _block(node)
            text = "\n".join(lines).rstrip()
            if text:
                parts.append(text)
        return "\n\n".join(parts) + ("\n" if parts else "")
    return "\n".join(_block(doc)).rstrip()


# ----------------------------------------------------------------------------- Markdown -> ADF

_INLINE_RE = re.compile(
    r"(\*\*(?P<strong>.+?)\*\*)|(`(?P<code>[^`]+)`)|(\[(?P<ltext>[^\]]+)\]\((?P<href>[^)]+)\))|(\*(?P<em>[^*]+)\*)|(_(?P<em2>[^_]+)_)"
)


def _text_node(text: str, marks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    node: dict[str, Any] = {"type": "text", "text": text}
    if marks:
        node["marks"] = marks
    return node


def _inline_nodes(text: str) -> list[dict[str, Any]]:
    nodes: list[dict[str, Any]] = []
    pos = 0
    for m in _INLINE_RE.finditer(text):
        if m.start() > pos:
            nodes.append(_text_node(text[pos : m.start()]))
        if m.group("strong") is not None:
            nodes.append(_text_node(m.group("strong"), [{"type": "strong"}]))
        elif m.group("code") is not None:
            nodes.append(_text_node(m.group("code"), [{"type": "code"}]))
        elif m.group("ltext") is not None:
            nodes.append(_text_node(m.group("ltext"), [{"type": "link", "attrs": {"href": m.group("href")}}]))
        else:
            nodes.append(_text_node(m.group("em") or m.group("em2") or "", [{"type": "em"}]))
        pos = m.end()
    if pos < len(text):
        nodes.append(_text_node(text[pos:]))
    return nodes or [_text_node("")]


def _paragraph(text: str) -> dict[str, Any]:
    return {"type": "paragraph", "content": _inline_nodes(text)}


_BULLET_RE = re.compile(r"^(\s*)[-*]\s+(?!\[[ xX]\])(.*)$")
_TASK_RE = re.compile(r"^(\s*)[-*]\s+\[([ xX])\]\s*(.*)$")
_ORDERED_RE = re.compile(r"^(\s*)\d+[.)]\s+(.*)$")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


def markdown_to_adf(text: str) -> dict[str, Any]:
    """Parse the Markdown subset into an ADF document."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    content: list[dict[str, Any]] = []
    i = 0
    para: list[str] = []

    def flush_para() -> None:
        if para:
            content.append(_paragraph(" ".join(s.strip() for s in para)))
            para.clear()

    task_counter = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            flush_para()
            i += 1
            continue
        if stripped.startswith("```"):
            flush_para()
            lang = stripped[3:].strip()
            buf: list[str] = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            node: dict[str, Any] = {"type": "codeBlock", "content": [_text_node("\n".join(buf))]}
            if lang:
                node["attrs"] = {"language": lang}
            content.append(node)
            continue
        if stripped in {"---", "***", "___"}:
            flush_para()
            content.append({"type": "rule"})
            i += 1
            continue
        m = _HEADING_RE.match(stripped)
        if m:
            flush_para()
            content.append(
                {"type": "heading", "attrs": {"level": len(m.group(1))}, "content": _inline_nodes(m.group(2))}
            )
            i += 1
            continue
        if stripped.startswith(">"):
            flush_para()
            quoted: list[str] = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quoted.append(lines[i].strip()[1:].strip())
                i += 1
            content.append({"type": "blockquote", "content": [_paragraph(" ".join(quoted))]})
            continue
        if _TASK_RE.match(line):
            flush_para()
            items: list[dict[str, Any]] = []
            while i < len(lines) and (tm := _TASK_RE.match(lines[i])):
                task_counter += 1
                state = "DONE" if tm.group(2).lower() == "x" else "TODO"
                items.append(
                    {
                        "type": "taskItem",
                        "attrs": {"localId": str(task_counter), "state": state},
                        "content": _inline_nodes(tm.group(3)),
                    }
                )
                i += 1
            content.append({"type": "taskList", "attrs": {"localId": f"list-{task_counter}"}, "content": items})
            continue
        if _BULLET_RE.match(line) or _ORDERED_RE.match(line):
            flush_para()
            ordered = bool(_ORDERED_RE.match(line))
            pattern = _ORDERED_RE if ordered else _BULLET_RE
            items = []
            while i < len(lines) and (lm := pattern.match(lines[i])):
                items.append({"type": "listItem", "content": [_paragraph(lm.group(2))]})
                i += 1
            content.append({"type": "orderedList" if ordered else "bulletList", "content": items})
            continue
        para.append(line)
        i += 1
    flush_para()
    return {"type": "doc", "version": 1, "content": content}
