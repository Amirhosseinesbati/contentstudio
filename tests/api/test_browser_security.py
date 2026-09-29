import asyncio

from contentstudio.browser_security import browser_write_guard
from fastapi import Request
from fastapi.responses import JSONResponse


def _guard_status(path: str, headers: dict[str, str]) -> int:
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in headers.items()]
    raw_headers.append((b"host", b"testserver"))
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": path,
            "scheme": "http",
            "headers": raw_headers,
            "server": ("testserver", 80),
            "client": ("127.0.0.1", 54000),
            "query_string": b"",
        }
    )

    async def next_handler(_: Request):
        return JSONResponse({"ok": True})

    return asyncio.run(browser_write_guard(request, next_handler)).status_code


def test_cross_site_and_sibling_site_browser_writes_are_rejected():
    for site in ("cross-site", "same-site", "none"):
        assert _guard_status(
            "/api/v1/change", {"Sec-Fetch-Site": site, "Origin": "http://evil.test"}
        ) == 403


def test_same_origin_and_internal_service_routes_remain_available():
    assert _guard_status("/api/v1/change", {"Sec-Fetch-Site": "same-origin"}) == 200
    assert _guard_status("/api/v1/change", {"Origin": "http://testserver"}) == 200
    assert _guard_status("/api/v1/change", {"Origin": "http://evil.test"}) == 403
    assert _guard_status("/internal/workflows/change", {"Sec-Fetch-Site": "cross-site"}) == 200
