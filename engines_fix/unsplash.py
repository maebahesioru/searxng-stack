"""Unsplash"""

from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl, quote
from json import loads
import hashlib
import re
import time

from searx.enginelib import EngineCache
from searx.exceptions import SearxEngineAccessDeniedException
from searx.network import get
from searx.utils import searxng_useragent

# about
about = {
    "website": 'https://unsplash.com',
    "wikidata_id": 'Q28233552',
    "official_api_documentation": 'https://unsplash.com/developers',
    "use_official_api": False,
    "require_api_key": False,
    "results": 'JSON',
}

base_url = 'https://unsplash.com/'
search_url = base_url + 'napi/search/photos?'
categories = ['images']
page_size = 20
paging = True

# Anubis proof-of-work: the auth cookie is valid for ~30 min, so re-solve
# before that (and whenever the server starts challenging again).
ANUBIS_REFRESH_SECONDS = 25 * 60

CACHE: EngineCache


def setup(engine_settings: dict) -> bool:
    global CACHE  # pylint: disable=global-statement
    CACHE = EngineCache(engine_settings["name"])
    return True


def _solve_anubis(url: str, user_agent: str) -> None:
    """Solve the Anubis PoW challenge and store the auth cookies in the
    session (the shared network client keeps them for subsequent requests)."""
    headers = {"User-Agent": user_agent}

    # the target redirects (302) to the Anubis challenge page which answers 401;
    # do not raise on the error status, we want the challenge JSON
    resp = get(url, headers=headers, timeout=15, raise_for_httperror=False)
    if resp.status_code != 401:
        # no challenge -> nothing to solve
        return

    m = re.search(r'id="anubis_challenge"[^>]*>(.*?)</script>', resp.text, re.S)
    if not m:
        raise SearxEngineAccessDeniedException("unsplash: Anubis challenge not found")

    challenge = loads(m.group(1)).get("challenge", {})
    random_data: str = challenge.get("randomData", "")
    difficulty: int = challenge.get("difficulty", 4)
    challenge_id: str = challenge.get("id", "")
    if not random_data or not challenge_id:
        raise SearxEngineAccessDeniedException("unsplash: invalid Anubis challenge")

    # fast algorithm: find nonce so that sha256(randomData + str(nonce))
    # starts with `difficulty` zero hex chars
    target = "0" * difficulty
    nonce = 0
    while True:
        digest = hashlib.sha256((random_data + str(nonce)).encode()).hexdigest()
        if digest.startswith(target):
            break
        nonce += 1

    pass_url = (
        f"{base_url}.within.website/x/cmd/anubis/api/pass-challenge"
        f"?id={challenge_id}&response={digest}&nonce={nonce}"
        f"&redir={quote(url, safe='')}&elapsedTime=100"
    )
    get(pass_url, headers=headers, timeout=15, allow_redirects=False, raise_for_httperror=False)


def request(query, params):
    params['url'] = search_url + urlencode({'query': query, 'page': params['pageno'], 'per_page': page_size})
    logger.debug("query_url --> %s", params['url'])

    # common user agents (e.g. Firefox, Chrome) are blocked
    # by Anubis (https://anubis.techaro.lol/)
    # so we pass the searxng user agent instead, which is not
    # commonly used by crawlers and hence not blocked
    user_agent = searxng_useragent()
    params["headers"]["User-Agent"] = user_agent

    # Anubis proof-of-work: solve when there is no (fresh) auth cookie cached
    solved_at = CACHE.get("anubis_solved_at")
    if not solved_at or time.time() - float(solved_at) > ANUBIS_REFRESH_SECONDS:
        try:
            _solve_anubis(params['url'], user_agent)
            CACHE.set("anubis_solved_at", str(time.time()))
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.debug("unsplash: anubis solve failed: %s", e)

    return params


def clean_url(url):
    parsed = urlparse(url)
    query = [(k, v) for (k, v) in parse_qsl(parsed.query) if k != 'ixid']

    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, urlencode(query), parsed.fragment))


def response(resp):
    if resp.status_code == 401:
        # Anubis is challenging again; force a re-solve on the next query
        CACHE.set("anubis_solved_at", "0")
        raise SearxEngineAccessDeniedException("unsplash: Anubis challenge (re-solve queued)")

    results = []
    json_data = loads(resp.text)

    if 'results' in json_data:
        for result in json_data['results']:
            results.append(
                {
                    'template': 'images.html',
                    'url': clean_url(result['links']['html']),
                    'thumbnail_src': clean_url(result['urls']['thumb']),
                    'img_src': clean_url(result['urls']['regular']),
                    'title': result.get('alt_description') or 'unknown',
                    'content': result.get('description') or '',
                }
            )

    return results
