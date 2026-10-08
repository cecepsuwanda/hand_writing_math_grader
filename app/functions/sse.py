"""Server-Sent Events wire format (https://html.spec.whatwg.org/multipage/server-sent-events.html)."""

from __future__ import annotations

SSE_KEEPALIVE = ": keepalive\n\n"


def format_sse(event: str, data: str) -> str:
    """One SSE message; every payload line needs its own ``data:`` prefix."""
    if not event or any(ch in event for ch in "\r\n"):
        raise ValueError(f"invalid SSE event name: {event!r}")
    lines = data.splitlines() or [""]
    body = "".join(f"data: {line}\n" for line in lines)
    return f"event: {event}\n{body}\n"
