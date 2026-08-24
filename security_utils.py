"""Shared security helpers: SSRF checks, rate limiting, HTML sanitization."""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

import bleach

# ---------------------------------------------------------------------------
# SSRF / URL validation
# ---------------------------------------------------------------------------

_BLOCKED_HOSTS = {
    "localhost",
    "metadata.google.internal",
    "metadata.goog",
    "kubernetes.default",
    "kubernetes.default.svc",
}


def is_blocked_ip(hostname: str) -> bool:
    """True if hostname is literal-private or resolves to a non-public address."""
    if not hostname:
        return True
    host = hostname.strip("[]").lower()
    if host in _BLOCKED_HOSTS or host.endswith(".local") or host.endswith(".internal"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return _ip_is_unsafe(ip)
    except ValueError:
        pass
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return True
    for info in infos:
        try:
            if _ip_is_unsafe(ipaddress.ip_address(info[4][0])):
                return True
        except ValueError:
            continue
    return False


def _ip_is_unsafe(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return True
    return False


def validate_public_http_url(url: str, *, max_len: int = 2048) -> str | None:
    """Return an error message if URL is unsafe; None if OK."""
    if not url or len(url) > max_len:
        return "Invalid URL."
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        return "Only http and https URLs are allowed."
    if not parsed.hostname:
        return "Invalid URL."
    if parsed.username or parsed.password:
        return "URLs with credentials are not allowed."
    if is_blocked_ip(parsed.hostname):
        return "That host is not allowed."
    return None


def validate_resolved_url(url: str) -> bool:
    """Post-redirect check: True if the final URL is still public http(s)."""
    return validate_public_http_url(url) is None


# ---------------------------------------------------------------------------
# Rate limiting (in-process; good enough for single-box deploys)
# ---------------------------------------------------------------------------

_rate_lock = threading.Lock()
_rate_buckets: dict[str, deque[float]] = defaultdict(deque)


def rate_limit_exceeded(key: str, *, limit: int, window_sec: float) -> bool:
    """Return True if this key has exceeded `limit` events in `window_sec`."""
    now = time.monotonic()
    with _rate_lock:
        bucket = _rate_buckets[key]
        while bucket and now - bucket[0] > window_sec:
            bucket.popleft()
        if len(bucket) >= limit:
            return True
        bucket.append(now)
        return False


def client_key(remote_addr: str | None, suffix: str) -> str:
    return f"{remote_addr or 'unknown'}:{suffix}"


# ---------------------------------------------------------------------------
# HTML sanitization (paywall reader)
# ---------------------------------------------------------------------------

_ALLOWED_TAGS = frozenset({
    "p", "br", "hr", "pre", "code", "blockquote",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td",
    "figure", "figcaption", "img", "picture", "source",
    "div", "span", "section", "article", "header", "footer",
    "strong", "em", "b", "i", "u", "s", "sub", "sup", "mark",
    "a", "abbr", "cite", "q", "time",
})

_ALLOWED_ATTRS = {
    "*": ["class", "title", "lang", "dir"],
    "a": ["href", "title", "rel", "target"],
    "img": ["src", "alt", "title", "width", "height", "loading", "srcset", "sizes"],
    "source": ["src", "srcset", "type", "media", "sizes"],
    "td": ["colspan", "rowspan"],
    "th": ["colspan", "rowspan", "scope"],
    "time": ["datetime"],
}


def sanitize_article_html(html: str) -> str:
    """Strip scripts/handlers and dangerous URLs from reader HTML."""
    if not html:
        return ""
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=["http", "https", "mailto"],
        strip=True,
    )
