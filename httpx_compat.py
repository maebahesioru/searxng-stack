"""httpx-compatible client wrapper backed by curl_cffi (Chrome TLS impersonation).

SearXNG's network layer expects httpx.AsyncClient / httpx.Response.
This module provides drop-in replacements backed by curl_cffi.requests.AsyncSession
with ``impersonate`` support (browser TLS fingerprint), which bypasses
fingerprint-based bot detection (DuckDuckGo, Brave, Startpage, ...).
"""
from __future__ import annotations

import typing as t

import httpx
from curl_cffi.requests import AsyncSession

if t.TYPE_CHECKING:
    from curl_cffi.requests import Response as CffiResponse


def _to_httpx_response(cffi: "CffiResponse", request: httpx.Request | None = None) -> httpx.Response:
    """Convert a curl_cffi Response into a real httpx.Response (content already read)."""
    if request is None:
        request = httpx.Request("GET", str(getattr(cffi, "url", "")))
    try:
        headers = dict(cffi.headers)
    except Exception:  # pylint: disable=broad-exception-caught
        headers = {}
    # curl_cffi returns already-decoded content; drop encoding headers so httpx
    # does not try to decompress a second time (zlib error: incorrect header check)
    for _k in ("Content-Encoding", "content-encoding", "Content-Length", "content-length"):
        headers.pop(_k, None)
    try:
        content = cffi.content
    except Exception:  # pylint: disable=broad-exception-caught
        content = b""
    return httpx.Response(
        status_code=cffi.status_code,
        headers=headers,
        content=content,
        request=request,
    )


class _StreamCM:
    """Async context manager emulating httpx.AsyncClient.stream()."""

    def __init__(self, coro: t.Awaitable["CffiResponse"]):
        self._coro = coro
        self.response: httpx.Response | None = None

    async def __aenter__(self) -> httpx.Response:
        cffi = await self._coro
        self.response = _to_httpx_response(cffi)
        return self.response

    async def __aexit__(self, *exc: t.Any) -> None:
        return None

    async def __aiter__(self):
        if self.response is None:
            return
        yield self.response.content


class AsyncClient:
    """httpx.AsyncClient-compatible wrapper around curl_cffi AsyncSession."""

    def __init__(self, impersonate: str | None = None, **kwargs: t.Any):
        self._impersonate = impersonate
        # Accept (and ignore) httpx-only kwargs; keep the ones curl_cffi understands
        self._kwargs = {
            k: v
            for k, v in kwargs.items()
            if k in ("verify", "timeout", "max_redirects", "limits", "trust_env", "proxy")
        }
        self._session: AsyncSession | None = None
        self._cookies: t.Any = None
        self._closed = False

    @property
    def is_closed(self) -> bool:
        return self._closed

    def _get_session(self) -> AsyncSession:
        if self._session is None:
            opts = dict(self._kwargs)
            self._session = AsyncSession(impersonate=self._impersonate, **opts)
            if self._cookies:
                try:
                    self._session.cookies.update(dict(self._cookies))
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
        return self._session

    @property
    def cookies(self) -> t.Any:
        return self._cookies

    @cookies.setter
    def cookies(self, value: t.Any) -> None:
        self._cookies = value
        if self._session is not None:
            try:
                self._session.cookies.update(dict(value or {}))
            except Exception:  # pylint: disable=broad-exception-caught
                pass

    async def request(self, method: str, url: str, **kwargs: t.Any) -> httpx.Response:
        # httpx-only kwargs that curl_cffi does not accept
        kwargs.pop("follow_redirects", None)
        kwargs.pop("extensions", None)
        cookies = kwargs.pop("cookies", None)
        if cookies is not None:
            kwargs["cookies"] = dict(cookies)
        print(f"[httpx_compat] {method} {url[:110]}", flush=True)
        cffi = await self._get_session().request(method, url, **kwargs)
        return _to_httpx_response(cffi, httpx.Request(method, str(getattr(cffi, "url", url))))

    async def get(self, url: str, **kwargs: t.Any) -> httpx.Response:
        return await self.request("GET", url, **kwargs)

    def stream(self, method: str, url: str, **kwargs: t.Any) -> _StreamCM:
        kwargs.pop("follow_redirects", None)
        kwargs.pop("extensions", None)
        return _StreamCM(self._get_session().stream(method, url, **kwargs))

    async def aclose(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
        self._closed = True

    async def __aenter__(self) -> "AsyncClient":
        return self

    async def __aexit__(self, *exc: t.Any) -> None:
        await self.aclose()
