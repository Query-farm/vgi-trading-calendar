"""Shared helpers for per-object discovery/description metadata (vgi-lint strict).

The ``vgi-lint`` strict profile expects these on **every** function and table.
Each function/table surfaces them in its ``Meta.tags``:

- ``vgi.title`` (VGI124)          -- human-friendly display name. Must not
  normalize-equal the machine name, or VGI125 fires.
- ``vgi.doc_llm`` (VGI112)         -- a Markdown narrative aimed at an LLM/agent.
- ``vgi.doc_md`` (VGI113)          -- a Markdown narrative aimed at human docs.
- ``vgi.keywords`` (VGI126/VGI138) -- a JSON array of search terms / synonyms.

``keywords_array(text)`` turns a human-authored comma-separated keyword string
into the JSON array string the linter requires (VGI138). Per-object
``vgi.source_url`` is intentionally *not* emitted: VGI139 wants ``source_url``
only on the catalog object, so functions/schemas omit it.
"""

from __future__ import annotations

import json


def keywords_array(keywords: str) -> str:
    """Serialize a comma-separated keyword string as a JSON array string.

    ``vgi.keywords`` must be a JSON array of strings (VGI138), so this splits on
    commas, trims whitespace, drops empties, and JSON-encodes the result.
    """
    items = [k.strip() for k in keywords.split(",") if k.strip()]
    return json.dumps(items)


def object_tags(
    title: str,
    doc_llm: str,
    doc_md: str,
    keywords: str,
    relative_path: str,
) -> dict[str, str]:
    """Build the standard per-object discovery/description tags.

    ``relative_path`` is the implementing file relative to ``vgi_trading_calendar/``; it
    is accepted for call-site compatibility but no per-object ``vgi.source_url``
    is emitted (VGI139 keeps ``source_url`` on the catalog only).
    """
    del relative_path  # per-object source_url dropped (VGI139)
    return {
        "vgi.title": title,
        "vgi.doc_llm": doc_llm,
        "vgi.doc_md": doc_md,
        "vgi.keywords": keywords_array(keywords),
    }
