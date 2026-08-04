# SPDX-License-Identifier: AGPL-3.0-or-later
"""SolidTorrents"""

from datetime import datetime
from urllib.parse import urlencode
import random

from lxml import html

from searx.utils import (
    extract_text,
    eval_xpath,
    eval_xpath_getindex,
    eval_xpath_list,
)

about = {
    "website": 'https://www.solidtorrents.to/',
    "wikidata_id": None,
    "official_api_documentation": None,
    "use_official_api": False,
    "require_api_key": False,
    "results": 'HTML',
}

categories = ['files']
paging = True

# base_url can be overwritten by a list of URLs in the settings.yml
base_url = 'https://solidtorrents.to'


def request(query, params):
    if isinstance(base_url, list):
        params['base_url'] = random.choice(base_url)
    else:
        params['base_url'] = base_url
    search_url = params['base_url'] + '/search?{query}'
    query = urlencode({'q': query, 'page': params['pageno']})
    params['url'] = search_url.format(query=query)
    return params


def response(resp):
    results = []
    dom = html.fromstring(resp.text)

    # SolidTorrents was redesigned with Tailwind CSS (2025): the old
    # "li.search-result" markup is gone.  Result cards are now divs with a
    # magnet link inside.
    cards = eval_xpath(dom, '//div[contains(@class, "bg-white") and .//a[starts-with(@href, "magnet:")]]')

    for card in cards:
        magnet = eval_xpath_getindex(card, './/a[starts-with(@href, "magnet:")]/@href', 0, None)
        if magnet is None:
            continue
        title = eval_xpath_getindex(card, './/h3/a', 0, None)
        url = eval_xpath_getindex(card, './/h3/a/@href', 0, None)
        torrentfile = eval_xpath_getindex(card, './/a[starts-with(@href, "/download/")]/@href', 0, None)

        # category / size / date live in the "text-gray-600" stats row
        stats_div = eval_xpath(card, './/div[contains(@class, "text-gray-600")]')
        stats = []
        if stats_div:
            stats = eval_xpath_list(stats_div[0], './span', min_len=0)

        def _text(i):
            try:
                return extract_text(stats[i])
            except Exception:  # pylint: disable=broad-exception-caught
                return ''

        categ = _text(0)
        filesize = _text(1)
        date_str = _text(2)

        seeds = extract_text(
            eval_xpath_getindex(card, './/span[contains(@class, "text-green-600")]//span[@class="font-medium"]', 0, None)
        )
        leech = extract_text(
            eval_xpath_getindex(card, './/span[contains(@class, "text-red-600")]//span[@class="font-medium"]', 0, None)
        )

        params = {
            'seed': seeds,
            'leech': leech,
            'title': extract_text(title),
            'url': resp.search_params['base_url'] + url,
            'filesize': filesize,
            'magnetlink': magnet,
            'torrentfile': torrentfile,
            'metadata': categ,
            'template': "torrent.html",
        }

        try:
            # new date format is MM/DD/YYYY (old one was "Mar 18, 2024")
            params['publishedDate'] = datetime.strptime(date_str, '%m/%d/%Y')
        except (ValueError, TypeError):
            pass

        results.append(params)

    return results
