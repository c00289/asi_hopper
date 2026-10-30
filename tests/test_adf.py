from asi_hopper.adf import adf_to_markdown, markdown_to_adf

DOC = {
    "type": "doc",
    "version": 1,
    "content": [
        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": "Definition of Done"}]},
        {
            "type": "paragraph",
            "content": [
                {"type": "text", "text": "Reviewed per "},
                {"type": "text", "text": "QP-06", "marks": [{"type": "strong"}]},
                {"type": "text", "text": " in "},
                {
                    "type": "text",
                    "text": "Jama",
                    "marks": [{"type": "link", "attrs": {"href": "https://jama.example"}}],
                },
                {"type": "text", "text": "."},
            ],
        },
        {
            "type": "taskList",
            "attrs": {"localId": "l1"},
            "content": [
                {
                    "type": "taskItem",
                    "attrs": {"localId": "1", "state": "TODO"},
                    "content": [{"type": "text", "text": "Submit"}],
                },
                {
                    "type": "taskItem",
                    "attrs": {"localId": "2", "state": "DONE"},
                    "content": [{"type": "text", "text": "Approve"}],
                },
            ],
        },
        {
            "type": "bulletList",
            "content": [
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Zed"}]}],
                },
                {
                    "type": "listItem",
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Lou"}]}],
                },
            ],
        },
        {"type": "codeBlock", "attrs": {"language": "python"}, "content": [{"type": "text", "text": "print(1)"}]},
        {
            "type": "table",
            "content": [
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableHeader",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Reviewer"}]}],
                        },
                        {
                            "type": "tableHeader",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Role"}]}],
                        },
                    ],
                },
                {
                    "type": "tableRow",
                    "content": [
                        {
                            "type": "tableCell",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Rod"}]}],
                        },
                        {
                            "type": "tableCell",
                            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Chief Engineer"}]}],
                        },
                    ],
                },
            ],
        },
        {
            "type": "panel",
            "attrs": {"panelType": "warning"},
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": "Safety record"}]}],
        },
        {
            "type": "paragraph",
            "content": [
                {"type": "mention", "attrs": {"id": "123", "text": "@Roy"}},
                {"type": "text", "text": " please"},
            ],
        },
        {"type": "rule"},
        {"type": "unknownBlock", "content": [{"type": "text", "text": "kept"}]},
    ],
}


def test_adf_to_markdown_covers_the_subset() -> None:
    md = adf_to_markdown(DOC)
    assert "## Definition of Done" in md
    assert "Reviewed per **QP-06** in [Jama](https://jama.example)." in md
    assert "- [ ] Submit" in md and "- [x] Approve" in md
    assert "- Zed\n- Lou" in md
    assert "```python\nprint(1)\n```" in md
    assert "| Reviewer | Role |" in md and "| Rod | Chief Engineer |" in md
    assert "> **Warning:** Safety record" in md
    assert "@Roy please" in md
    assert "---" in md
    assert "kept" in md


def test_adf_to_markdown_handles_empty() -> None:
    assert adf_to_markdown(None) == ""
    assert adf_to_markdown({"type": "doc", "content": []}) == ""


def test_markdown_to_adf_round_trip() -> None:
    text = (
        "# Title\n\nSome **bold** and `code` with a [link](https://x.y).\n\n- one\n- two\n\n"
        "1. first\n2. second\n\n- [ ] todo\n- [x] done\n\n```sh\nls\n```\n\n> quoted\n\n---\n"
    )
    doc = markdown_to_adf(text)
    kinds = [n["type"] for n in doc["content"]]
    assert kinds == ["heading", "paragraph", "bulletList", "orderedList", "taskList", "codeBlock", "blockquote", "rule"]
    back = adf_to_markdown(doc)
    assert "# Title" in back
    assert "**bold**" in back and "`code`" in back and "[link](https://x.y)" in back
    assert "- one\n- two" in back
    assert "1. first\n2. second" in back
    assert "- [ ] todo\n- [x] done" in back
    assert "```sh\nls\n```" in back
    assert "> quoted" in back
