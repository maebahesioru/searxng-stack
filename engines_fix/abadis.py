"""
    Abadis (dictionary)
"""

from searx.utils import extract_text, eval_xpath
from lxml import html

about = {
    "website": "https://abadis.ir/",
    "wikidata_id": "Q56690821",
    "use_official_api": False,
    "require_api_key": False,
    "results": "HTML",
    "language": "fa",
}

categories = ["dictionaries"]
paging = False

BASE_URL = "https://abadis.ir/"


def request(query, params):

    # Detect language
    localLang = params["searxng_locale"]
    match localLang.split("-"):
        case ["fa", *_] | ["ar", *_]:
            localLang = "fatofa/"
        case ["en", *_]:
            localLang = "entofa/"
        case _:
            localLang = False

    # Generate URL
    if not localLang:
        return None

    params["url"] = BASE_URL + localLang + query + "/"
    return params


def response(resp):
    results = []

    # Parse HTML
    dom = html.fromstring(resp.text)
    mainContent = eval_xpath(dom, "//main")
    if not mainContent:
        return results

    for content in mainContent:

        # Check result language
        if eval_xpath(content, '//div[@id="pho"]'):
            # Get LTR Result
            WORD = eval_xpath(content, '//div[@id="boxWrd"]/div/h1')
            IPA = eval_xpath(content, '//div[@id="boxWrd"]/div[2]')
            CONTENT = eval_xpath(
                content, 'div[contains(@t, "انگلیسی به انگلیسی")]/div[2]/article'
            )
        else:
            # Get RTL Result
            WORD = eval_xpath(content, '//div[@id="boxWrd"]/h1')
            IPA = eval_xpath(content, '//div[@id="boxWrd"]/div')
            CONTENT = eval_xpath(content, 'div[contains(@t, "لغت نامه دهخدا")]/div[2]')

    # Generate Result (template: dictionaries.html is parch-fork-only,
    # upstream SearXNG does not have it -> use default.html)
    result = {
        "url": resp.url,
        "title": extract_text(WORD),
        "content": extract_text(CONTENT)[:150] + "...",
    }
    ipa_text = extract_text(IPA)
    if ipa_text:
        result["ipa"] = ipa_text
    results.append(result)

    return results
