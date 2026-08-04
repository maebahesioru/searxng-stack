# SPDX-License-Identifier: AGPL-3.0-or-later
"""metacpan"""

from urllib.parse import urlunparse

# about
about = {
    "website": 'https://metacpan.org/',
    "wikidata_id": 'Q841507',
    "official_api_documentation": 'https://github.com/metacpan/metacpan-api/blob/master/docs/API-docs.md',
    "use_official_api": True,
    "require_api_key": False,
    "results": 'JSON',
}

# engine dependent config
page_size = 20  # Don't put this over 5000
categories = ["it", "packages"]
disabled = True
shortcut = "cpan"
paging = True

query_data_template = {
    'query': {
        'bool': {
            'must': [
                {
                    'multi_match': {
                        'type': 'most_fields',
                        'fields': ['documentation', 'documentation.*'],
                        'analyzer': 'camelcase',
                    }
                }
            ],
            'filter': [
                {'exists': {'field': 'documentation'}},
                {'term': {'status': 'latest'}},
                {'term': {'indexed': True}},
                {'term': {'authorized': True}},
            ],
        }
    },
    "sort": [
        {"_score": {"order": "desc"}},
        {"date": {"order": "desc"}},
    ],
    '_source': ['documentation', "abstract"],
    'size': page_size,
}
search_url = urlunparse(["https", "fastapi.metacpan.org", "/v1/file/_search", "", "", ""])


def request(query, params):
    params["url"] = search_url
    params["method"] = "POST"
    query_data = query_data_template
    query_data["query"]["bool"]["must"][0]["multi_match"]["query"] = query
    query_data["from"] = (params["pageno"] - 1) * page_size
    params["json"] = query_data
    return params


def response(resp):
    results = []

    search_results = resp.json()["hits"]["hits"]
    for result in search_results:
        fields = result["_source"]
        module = fields["documentation"]
        results.append(
            {
                "url": "https://metacpan.org/pod/" + module,
                "title": module,
                "content": fields.get("abstract", ""),
            }
        )

    return results
