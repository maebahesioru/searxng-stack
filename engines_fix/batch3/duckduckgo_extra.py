# SPDX-License-Identifier: AGPL-3.0-or-later
"""
DuckDuckGo Extra (images, videos, news) - FlareSolverr edition
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The i.js/v.js/news.js APIs block datacenter IPs at the network level, so all
requests go through FlareSolverr (a headless-Chrome Cloudflare/JS challenge
solver) using a persistent browser session.  The vqd token is also fetched
through the same browser session so the UA fingerprint matches.
"""

import typing as t

from datetime import datetime
from urllib.parse import urlencode
from urllib.parse import quote_plus

from searx.utils import get_embeded_stream_url, html_to_text, extr
from searx.network import post

from searx.engines.duckduckgo import fetch_traits  # pylint: disable=unused-import
from searx.engines.duckduckgo import get_ddg_lang, get_vqd, set_vqd

if t.TYPE_CHECKING:
    from searx.extended_types import SXNG_Response
    from searx.search.processors import OnlineParams

# about
about = {
    "website": "https://duckduckgo.com/",
    "wikidata_id": "Q12805",
    "use_official_api": False,
    "require_api_key": False,
    "results": "JSON (via FlareSolverr browser)",
}
language_support = True

# engine dependent config
categories = []
ddg_category = ""
"""The category must be any of ``images``, ``videos`` and ``news``
"""
paging = True
safesearch = True

safesearch_cookies = {0: "-2", 1: None, 2: "1"}
safesearch_args = {0: "1", 1: None, 2: "1"}

search_path_map = {"images": "i", "videos": "v", "news": "news"}

_HTTP_User_Agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
send_accept_language_header = False

# FlareSolverr instance - headless browser that solves the JS challenge
FLARESOLVERR_URL = "http://flaresolverr3:8191/v1"


def init(engine_settings: dict[str, t.Any]):

    if engine_settings["ddg_category"] not in ["images", "videos", "news"]:
        raise ValueError(f"Unsupported DuckDuckGo category: {engine_settings['ddg_category']}")


def _flare_session() -> str:
    return "ddg_" + ddg_category


def fetch_vqd(
    query: str,
    params: "OnlineParams",
):

    logger.debug("fetch_vqd: request value from html.duckduckgo.com via FlareSolverr")
    resp = post(
        url=FLARESOLVERR_URL,
        json={
            "cmd": "request.get",
            "url": f"https://html.duckduckgo.com/html/?q={quote_plus(query)}&iar=images",
            "maxTimeout": 25000,
            "session": _flare_session(),
        },
        timeout=70,
        raise_for_httperror=False,
    )

    value = ""
    if resp.status_code == 200:
        try:
            html_text = resp.json()["solution"]["response"]
            value = extr(html_text, 'name="vqd" value="', '"')
        except Exception:  # pylint: disable=broad-exception-caught
            value = ""
        if value:
            logger.debug("vqd value via FlareSolverr: '%s'", value)
        else:
            logger.error("vqd: can't parse value from ddg response (return empty string)")
            return ""
    else:
        logger.error("vqd: got HTTP %s from FlareSolverr", resp.status_code)

    if value:
        set_vqd(query=query, value=value, params=params)
    else:
        logger.error("none vqd value: HTTP %s", resp.status_code)
    return value


def request(query: str, params: "OnlineParams") -> None:

    if len(query) >= 500:
        # DDG does not accept queries with more than 499 chars
        params["url"] = None
        return

    # HTTP headers
    # ============

    headers = params["headers"]
    # The vqd value is generated from the query and the UA header. To be able to
    # reuse the vqd value, the UA header must be static.
    headers["User-Agent"] = _HTTP_User_Agent
    vqd = get_vqd(query=query, params=params) or fetch_vqd(query=query, params=params)

    headers["Accept"] = "*/*"
    headers["Referer"] = "https://duckduckgo.com/"
    headers["Host"] = "duckduckgo.com"

    # DDG XHTMLRequest
    # ================

    eng_region: str = traits.get_region(
        params["searxng_locale"],
        traits.all_locale,
    )  # pyright: ignore[reportAssignmentType]

    eng_lang: str = get_ddg_lang(traits, params["searxng_locale"]) or "wt-wt"

    args: dict[str, str | int] = {
        "o": "json",
        "q": query,
        "u": "bing",
        "l": eng_region,
        "bpia": "1",
        "vqd": vqd,
        "a": "h_",
    }

    params["cookies"]["ad"] = eng_lang  # zh_CN
    params["cookies"]["ah"] = eng_region  # "us-en,de-de"
    params["cookies"]["l"] = eng_region  # "hk-tzh"

    args["ct"] = "EN"
    if params["searxng_locale"] != "all":
        args["ct"] = params["searxng_locale"].split("-")[0].upper()

    if params["pageno"] > 1:
        args["s"] = (params["pageno"] - 1) * 100

    safe_search = safesearch_cookies.get(params["safesearch"])
    if safe_search is not None:
        params["cookies"]["p"] = safe_search  # "-2", "1"
        args["p"] = safe_search

    api_url = f"https://duckduckgo.com/{search_path_map[ddg_category]}.js?{urlencode(args)}"

    params["method"] = "POST"
    params["url"] = FLARESOLVERR_URL
    params["headers"]["Content-Type"] = "application/json"
    params["data"] = __import__("json").dumps(
        {
            "cmd": "request.get",
            "url": api_url,
            "maxTimeout": 25000,
            "session": _flare_session(),
        }
    )

    logger.debug("param headers: %s", params["headers"])
    logger.debug("param data: %s", params["data"])
    logger.debug("param cookies: %s", params["cookies"])


def _image_result(result):
    return {
        'template': 'images.html',
        'url': result['url'],
        'title': result['title'],
        'content': '',
        'thumbnail_src': result['thumbnail'],
        'img_src': result['image'],
        'resolution': '%s x %s' % (result['width'], result['height']),
        'source': result['source'],
    }


def _video_result(result):
    images = result.get('images') or {}
    published = result.get('published')
    try:
        if isinstance(published, str):
            p_date = datetime.fromisoformat(published)
        else:
            p_date = datetime.fromtimestamp(int(published))
    except (ValueError, TypeError):
        p_date = None
    return {
        'template': 'videos.html',
        'url': result['content'],
        'title': result['title'],
        'content': '',
        'thumbnail': (images.get('medium') or images.get('large')) if images else None,
        'publishedDate': p_date,
    }


def _news_result(result):
    return {
        'url': result['url'],
        'title': result['title'],
        'content': html_to_text(result['excerpt']),
        'publishedDate': datetime.fromtimestamp(int(result['date'])),
    }


def response(resp: "SXNG_Response") -> list[dict]:

    if resp.status_code != 200:
        return []

    try:
        json_str = resp.json()["solution"]["response"]
        # FlareSolverr wraps the raw body in an HTML <pre> tag - unwrap it
        if json_str.lstrip().startswith("<"):
            from lxml import html as lxml_html

            dom = lxml_html.fromstring(json_str)
            pre = dom.xpath("//pre")
            if pre:
                json_str = pre[0].text_content()
        search_res = __import__("json").loads(json_str)
    except Exception:  # pylint: disable=broad-exception-caught
        return []

    results = []

    for result in search_res.get("results", []):
        if ddg_category == "images":
            results.append(_image_result(result))
        elif ddg_category == "videos":
            results.append(_video_result(result))
        else:
            results.append(_news_result(result))

    return results
