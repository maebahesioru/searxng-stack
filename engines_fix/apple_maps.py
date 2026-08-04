# SPDX-License-Identifier: AGPL-3.0-or-later
"""Apple Maps"""

from json import loads, dumps
from time import time
from urllib.parse import urlencode

from searx.network import get as http_get
from searx.network import post as http_post
from searx.engines.openstreetmap import get_key_label

about = {
    "website": 'https://www.apple.com/maps/',
    "wikidata_id": 'Q276101',
    "official_api_documentation": None,
    "use_official_api": True,
    "require_api_key": False,
    "results": 'JSON',
}

token = {'value': '', 'last_updated': None}

categories = ['map']
paging = False

# FlareSolverr instance (DDG's local.js blocks direct API access)
FLARESOLVERR_URL = "http://flaresolverr2:8191/v1"

search_url = "https://api.apple-mapkit.com/v1/search?{query}&mkjsVersion=5.72.53"


def obtain_token():
    update_time = time() - (time() % 1800)
    try:
        # use duckduckgo's mapkit token (via FlareSolverr - DDG blocks direct API access)
        flare_payload = dumps(
            {
                'cmd': 'request.get',
                'url': 'https://duckduckgo.com/local.js?get_mk_token=1',
                'maxTimeout': 25000,
                'session': 'mapkit',
            }
        )
        token_response = http_post(
            FLARESOLVERR_URL,
            data=flare_payload,
            headers={'Content-Type': 'application/json'},
            timeout=70.0,
        )
        jwt = token_response.json()['solution']['response']
        # the FlareSolverr response wraps the JWT in an HTML <pre> tag
        from lxml import html as lxml_html

        dom = lxml_html.fromstring(jwt)
        pre = dom.xpath('//pre')
        if pre:
            jwt = pre[0].text_content().strip()

        actual_token = http_get(
            'https://cdn.apple-mapkit.com/ma/bootstrap?apiVersion=2&mkjsVersion=5.72.53&poi=1',
            timeout=10.0,
            headers={'Authorization': 'Bearer ' + jwt},
        )
        token['value'] = loads(actual_token.text)['authInfo']['access_token']
        token['last_updated'] = update_time
    # pylint: disable=bare-except
    except Exception:  # pylint: disable=broad-exception-caught
        pass
    return token


def request(query, params):
    # also re-fetch when the token value is empty (previous fetch may have failed)
    if time() - (token['last_updated'] or 0) > 1800 or not token['value']:
        obtain_token()

    params['url'] = search_url.format(query=urlencode({'q': query, 'lang': params['language']}))

    params['headers'] = {'Authorization': 'Bearer ' + token['value']}

    return params


def response(resp):
    results = []

    resp_json = loads(resp.text)

    user_language = resp.search_params['language']

    for result in resp_json['results']:
        boundingbox = None
        if 'displayMapRegion' in result:
            box = result['displayMapRegion']
            boundingbox = [box['southLat'], box['northLat'], box['westLng'], box['eastLng']]

        links = []
        if 'telephone' in result:
            telephone = result['telephone']
            links.append(
                {
                    'label': get_key_label('phone', user_language),
                    'url': 'tel:' + telephone,
                    'url_label': telephone,
                }
            )
        if result.get('urls'):
            url = result['urls'][0]
            links.append(
                {
                    'label': get_key_label('website', user_language),
                    'url': url,
                    'url_label': url,
                }
            )

        results.append(
            {
                'template': 'map.html',
                'type': result.get('poiCategory'),
                'title': result['name'],
                'links': links,
                'latitude': result['center']['lat'],
                'longitude': result['center']['lng'],
                'url': result['placecardUrl'],
                'boundingbox': boundingbox,
                'geojson': {'type': 'Point', 'coordinates': [result['center']['lng'], result['center']['lat']]},
                'address': {
                    'name': result['name'],
                    'house_number': result.get('subThoroughfare'),
                    'road': result.get('thoroughfare'),
                    'locality': result.get('locality'),
                    'postcode': result.get('postCode'),
                    'country': result.get('country'),
                },
            }
        )

    return results
