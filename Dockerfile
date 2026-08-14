FROM searxng/searxng:latest

USER root
# Downgrade python_socks 3.0.0 -> 2.2.0 (httpx_socks 0.10.0 is incompatible with 3.x:
# AnyioProxy got proxy_ssl / connect_tcp got dest_ssl TypeErrors)
RUN rm -rf /usr/local/searxng/.venv/lib/python3.14/site-packages/python_socks \
           /usr/local/searxng/.venv/lib/python3.14/site-packages/python_socks-*.dist-info
COPY wheels/ /tmp/wheels/
RUN python3 - <<'EOF'
import zipfile, glob
dest = "/usr/local/searxng/.venv/lib/python3.14/site-packages"
for whl in sorted(glob.glob("/tmp/wheels/*.whl")):
    with zipfile.ZipFile(whl) as z:
        z.extractall(dest)
    print("installed:", whl.split("/")[-1])
EOF

COPY client.py /usr/local/searxng/searx/network/client.py
COPY httpx_compat.py /usr/local/searxng/.venv/lib/python3.14/site-packages/httpx_compat.py
COPY duckduckgo.py /usr/local/searxng/searx/engines/duckduckgo.py
COPY engines_fix/qwant.py /usr/local/searxng/searx/engines/qwant.py
COPY engines_fix/solidtorrents.py /usr/local/searxng/searx/engines/solidtorrents.py
COPY engines_fix/unsplash.py /usr/local/searxng/searx/engines/unsplash.py
COPY engines_fix/batch1/360search.py /usr/local/searxng/searx/engines/360search.py
# parchlinuxb fork version: adds images/videos category support (ChinasoCategoryType)
COPY engines_fix/batch1/chinaso.py /usr/local/searxng/searx/engines/chinaso.py
COPY engines_fix/batch2/metacpan.py /usr/local/searxng/searx/engines/metacpan.py
COPY engines_fix/batch3/quark.py /usr/local/searxng/searx/engines/quark.py
COPY engines_fix/batch3/bitchute.py /usr/local/searxng/searx/engines/bitchute.py
COPY engines_fix/batch3/duckduckgo_extra.py /usr/local/searxng/searx/engines/duckduckgo_extra.py
COPY engines_fix/1337x.py /usr/local/searxng/searx/engines/1337x.py
COPY engines_fix/apkmirror.py /usr/local/searxng/searx/engines/apkmirror.py
COPY engines_fix/rumble.py /usr/local/searxng/searx/engines/rumble.py
COPY engines_fix/apple_maps.py /usr/local/searxng/searx/engines/apple_maps.py
COPY engines_fix/batch2/kickass.py /usr/local/searxng/searx/engines/kickass.py
COPY engines_fix/seznam.py /usr/local/searxng/searx/engines/seznam.py
COPY engines_fix/gmx.py /usr/local/searxng/searx/engines/gmx.py
# Mullvad Leta engine (from porespellar/return42 mod-sidecar line)
COPY engines_fix/mullvad_leta.py /usr/local/searxng/searx/engines/mullvad_leta.py
# 4get proxy search engine (from Aadniz fork, base_url+scraper set via settings.yml)
COPY engines_fix/4get.py /usr/local/searxng/searx/engines/4get.py
# Aparat (Iranian YouTube) + Abadis (Persian dictionary) from parchlinuxb fork
COPY engines_fix/aparat.py /usr/local/searxng/searx/engines/aparat.py
COPY engines_fix/abadis.py /usr/local/searxng/searx/engines/abadis.py
# searchcode_code + stract engines (return42 mod-sidecar line, modern EngineResults API)
COPY engines_fix/searchcode_code.py /usr/local/searxng/searx/engines/searchcode_code.py
COPY engines_fix/stract.py /usr/local/searxng/searx/engines/stract.py
# webapp.py: autocompleter GET+POST, escape(suggestions), opensearch POST default (Bnyro fork)
COPY engines_fix/webapp.py /usr/local/searxng/searx/webapp.py
# wolframalpha_noapi: Referer KeyError fix (.get() with fallback)
COPY engines_fix/wolframalpha_noapi.py /usr/local/searxng/searx/engines/wolframalpha_noapi.py
# Upstream open PRs cherry-picked (2026-08-14):
# PR #2652 startpage GET-request (CAPTCHA frequency reduction)
COPY engines_fix/startpage.py /usr/local/searxng/searx/engines/startpage.py
# PR #4827 sogou antispider graceful + URL resolution via multi_requests
COPY engines_fix/sogou.py /usr/local/searxng/searx/engines/sogou.py
# PR #6284 google_news DOM changes (title in a[target=_blank], metadata)
COPY engines_fix/google_news.py /usr/local/searxng/searx/engines/google_news.py
# PR #6123 icons8 icon search engine (Bnyro)
COPY engines_fix/icons8.py /usr/local/searxng/searx/engines/icons8.py
# httpx_socks 0.10.0 x python_socks 3.0.0 incompatibility fix:
# remove proxy_ssl from Proxy.create() calls (python_socks 3 dropped it)
COPY engines_fix/_async_proxy.py /usr/local/searxng/.venv/lib/python3.14/site-packages/httpx_socks/_async_proxy.py
# fix: snapshot iteration in ResultContainer.close() to avoid RuntimeError
# with late-arriving engine results (dictionary changed size during iteration)
COPY engines_fix/results.py /usr/local/searxng/searx/results.py
COPY favicons.toml /etc/searxng/favicons.toml
# bake in the custom settings (no host volume mount on Coolify)
COPY settings.yml /etc/searxng/settings.yml
# purge stale bytecode caches (base image ships pre-compiled .pyc that shadows patched sources)
RUN find /usr/local/searxng/searx -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
RUN find /usr/local/searxng/.venv/lib/python3.14/site-packages/httpx_socks -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true

USER searxng
