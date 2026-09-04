from __future__ import annotations

import html
import re


def safe_rich_text(text: str) -> str:
    """Render a small, safe Markdown subset after escaping model output."""
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", escaped)
    return escaped.replace("\n", "<br>")
