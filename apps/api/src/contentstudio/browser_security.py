"""Reject cross-origin browser writes before cookie-authenticated API handlers run."""

from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse

from .config import get_settings

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _origin_matches_request(request: Request, origin: str) -> bool:
    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    if parsed.path or parsed.query or parsed.fragment or parsed.username or parsed.password:
        return False
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme).lower()
    host = request.headers.get("host", "").lower()
    return f"{parsed.scheme}://{parsed.netloc.lower()}" == f"{scheme}://{host}"


async def browser_write_guard(request: Request, call_next):
    if request.method in SAFE_METHODS or not request.url.path.startswith("/api/v1/"):
        return await call_next(request)

    # Fetch Metadata is browser-set and cannot be forged by a sibling site.
    site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    if site is not None:
        allowed = site == "same-origin"
    elif origin is not None:
        allowed = _origin_matches_request(request, origin)
    else:
        # CLI calls without browser metadata work in DEMO. CONNECTED browser
        # writes must provide an origin even if a legacy browser omits metadata.
        allowed = get_settings().mode != "connected"
    if not allowed:
        return JSONResponse({"detail": "Cross-origin write rejected"}, status_code=403)
    return await call_next(request)
