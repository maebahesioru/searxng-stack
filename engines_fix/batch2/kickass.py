# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kickass Torrent (Videos, Music, Files) - via FlareSolverr (Cloudflare bypass)"""

import random
from json import dumps
from operator import itemgetter
from urllib.parse import quote, urljoin

from lxml import html
from searx.utils import (
    eval_xpath,
    eval_xpath_getindex,
    eval_xpath_list,
    extract_text,
    int_or_zero,
)

about = {
    "website": 'https://kickasstorrents.to',
    "wikidata_id": 'Q17062285',
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": 'HTML',
}

categories = ['files']
paging = True

# base_url can be overwritten by a list of URLs in the settings.yml
base_url = 'https://kickasstorrents.to'

# FlareSolverr instance (bypasses the Cloudflare JS challenge)
FLARESOLVERR_URL = 'http://flaresolverr:8191/v1'


def request(query, params):
    params['base_url'] = random.choice(base_url) if isinstance(base_url, list) else base_url
    target = params['base_url'] + f'/usearch/{quote(query)}/{params["pageno"]}/'
    params['method'] = 'POST'
    params['url'] = FLARESOLVERR_URL
    params['headers']['Content-Type'] = 'application/json'
    params['data'] = dumps(
        {
            'cmd': 'request.get',
            'url': target,
            'maxTimeout': 25000,
            'session': 'kickass',
        }
    )

    return params


def response(resp):
    results = []
    dom = html.fromstring(resp.json()['solution']['response'])

    search_res = eval_xpath_list(dom, '//table[contains(@class, "data")]//tr[descendant::a]', None)
    if search_res is None:
        return []

    for tag in search_res[1:]:
        result = {'template': 'torrent.html'}
        href = eval_xpath_getindex(tag, './/a[contains(@class, "cellMainLink")]/@href', 0, None)
        result['url'] = urljoin('https://kickasstorrents.to', href)
        result['title'] = extract_text(eval_xpath(tag, './/a[contains(@class, "cellMainLink")]'))
        result['content'] = extract_text(eval_xpath(tag, './/span[@class="font11px lightgrey block"]'))
        result['seed'] = int_or_zero(extract_text(eval_xpath(tag, './/td[contains(@class, "green")]')))
        result['leech'] = int_or_zero(extract_text(eval_xpath(tag, './/td[contains(@class, "red")]')))
        result['filesize'] = extract_text(eval_xpath(tag, './/td[contains(@class, "nobr")]'))

        results.append(result)

    # results sorted by seeder count
    results = sorted(results, key=itemgetter('seed'), reverse=True)

    return results
