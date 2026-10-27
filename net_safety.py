"""Guards for fetching URLs that untrusted people supply (applied-channel links)."""
import ipaddress
import socket
from urllib.parse import urljoin, urlsplit

import requests

MAX_BYTES = 1_000_000
MAX_REDIRECTS = 5


def host_is(host, domain):
    """True for the domain itself or a subdomain, never for look-alikes
    such as "evilgreenhouse.io"."""
    host = (host or "").lower().rstrip(".")
    return host == domain or host.endswith("." + domain)


def is_public_url(url):
    """http(s) only, and every address the host resolves to must be globally
    routable (no loopback, private, link-local, or carrier-grade NAT ranges).
    DNS can change between this check and the request, so this narrows the
    exposure rather than eliminating it."""
    parts = urlsplit(url or "")
    if parts.scheme.lower() not in ("http", "https") or not parts.hostname:
        return False
    try:
        addresses = {info[4][0].split("%")[0] for info in socket.getaddrinfo(parts.hostname, None)}
    except (OSError, UnicodeError):
        return False
    return bool(addresses) and all(ipaddress.ip_address(a).is_global for a in addresses)


def safe_get_text(url, headers=None, timeout=20):
    """Fetch a page as text, or None. Each redirect hop is re-checked and the
    body is capped at MAX_BYTES. Returns (status_code, text)."""
    for _ in range(MAX_REDIRECTS + 1):
        if not is_public_url(url):
            return None
        response = requests.get(url, headers=headers, timeout=timeout,
                                allow_redirects=False, stream=True)
        try:
            if response.is_redirect and response.headers.get("Location"):
                url = urljoin(url, response.headers["Location"])
                continue
            body = b""
            for chunk in response.iter_content(chunk_size=16384):
                body += chunk
                if len(body) >= MAX_BYTES:
                    break
            return response.status_code, body[:MAX_BYTES].decode(
                response.encoding or "utf-8", errors="replace")
        finally:
            response.close()
    return None
