.. raw:: html

   <p align="right">
     <picture>
       <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-dark.svg">
       <img alt="jupiter.au" src="https://raw.githubusercontent.com/belikh/design/latest/packages/graphics/logo/jupiter-logo-light.svg" width="260">
     </picture>
   </p>

   <h1>Procurement MCP</h1>

.. meta::
   :description: An MCP server that searches Australian and Chinese marketplaces in one call and ranks offers by landed cost to a destination postcode, delivery time and seller trust.

An MCP server that searches Australian and Chinese marketplaces in one call and returns offers ranked by landed cost to a destination postcode (Brisbane 4000 by default), delivery time and seller trust.

Every source is a hosted API called with a key; the server contains no scrapers. A marketplace that returns nothing adds one diagnostic entry that says why.

`Install`_ · `Tools`_ · `Marketplaces`_ · `Delivery and landed cost`_ · `Ranking`_ · `Database`_ · `Develop`_

|

.. raw:: html

   <p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-dark.svg"><img alt="" src="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-light.svg" width="50%"></picture></p>


|

Install
-------

.. code-block:: sh

   uv sync                           # Python 3.12, pinned in .python-version
   cp .env.example .env              # add the keys you have
   uv run mcp dev server.py          # MCP Inspector
   uv run python server.py           # stdio
   MCP_HTTP_PORT=8765 uv run python server.py   # streamable HTTP at http://127.0.0.1:8765/mcp

The server needs ``mcp`` 2.3 or later. With no keys set, ``ozbargain`` and ``cheapies`` work and every other marketplace returns a ``missing_key`` diagnostic that names the variable to set.

|

Tools
-----

.. list-table::
   :header-rows: 1

   * - Tool
     - Purpose
   * - |search-l| |search-d| ``search_offers(query, marketplaces?, sort, qty, ship_to?, postcode?, max_results, query_zh?, est_weight_kg?, include_pickup, deadline_s?, ebay_auctions, ebay_seller_scope)``
     - Searches the marketplaces at once and returns offers ranked by ``sort`` (``cheapest``, ``fastest`` or ``best_value``), each with a delivery status and landed cost for the destination postcode.
   * - |file-l| |file-d| ``get_offer_detail(offer_id)``
     - Refreshes one offer. ``taobao``, ``tmall``, ``1688``, ``jd`` and ``pdd`` ids are fetched from TMAPI and ``ebay_au`` ids from eBay. For other marketplaces it returns the offer from the most recent search that held it.
   * - |image-l| |image-d| ``search_by_image(image_url, destination, max_results)``
     - Reverse image search. Takes a photo URL and returns matching listings from 1688, Alibaba, AliExpress or global retail sites. About $0.10 per search.
   * - |cart-l| |cart-d| ``latest_deals(sources?, query?, min_votes, max_results)``
     - The newest OzBargain (and optionally Cheapies) deals, most upvoted first.
   * - |link-l| |link-d| ``get_price_history(offer_id_or_asin, days, include_series)``
     - Amazon price history from Keepa: current, 30-day and 90-day average, lowest and highest.
   * - |cloud-l| |cloud-d| ``search_history(source, query_contains?, since_hours, limit, include_offers)``
     - Past searches from the Postgres log, or unexpired cached results.
   * - |pulse-l| |pulse-d| ``health()``
     - Which marketplaces can run, the key each one is missing, and its verification status. Shows no secrets.
   * - |chat-l| |chat-d| Prompt ``procurement_brief``
     - System prompt for procurement reasoning.

``search_offers`` result
~~~~~~~~~~~~~~~~~~~~~~~~

The list holds three kinds of entry, in this order. Each entry's ``kind`` field says which it is.

- ``offer``: a listing you can buy, ranked by ``sort``. At most ``max_results * 2`` are returned.
- ``comp``: a past sale price from ``ebay_sold``. Comps are not ranked.
- ``diagnostic``: one entry for every requested marketplace that returned no offers. ``diagnostic_code`` gives the reason.

.. list-table::
   :header-rows: 1

   * - ``diagnostic_code``
     - Meaning
   * - ``missing_key``
     - The marketplace's key is not set. The title names the variable.
   * - ``timeout``
     - No reply before the deadline. The upstream call was cancelled.
   * - ``upstream_error``
     - The source replied with an error, or its reply could not be read.
   * - ``quota``
     - An Apify actor reported its free runs or credit as used up.
   * - ``unsubscribed``
     - TMAPI answered 401: the API is not subscribed in the TMAPI console.
   * - ``degraded``
     - The source needs extra setup. Gumtree needs ``GUMTREE_COOKIES``.
   * - ``unsupported``
     - No source exists for this marketplace, or the name is unknown.
   * - ``no_results``
     - The source ran and matched nothing.
   * - ``not_deliverable``
     - Offers were found and left out because they do not deliver to the destination.

All marketplaces run at once under one deadline (``PROCUREMENT_DEADLINE_S``, default 55 seconds, or the ``deadline_s`` argument). Apify actor lanes take 30 to 90 seconds, so a search that includes them can report ``timeout`` for the slowest. Raise the deadline if your MCP client allows tool calls longer than 60 seconds. A search with a ``timeout``, ``upstream_error`` or ``quota`` diagnostic is not cached.

Pass ``query_zh`` with the query in Chinese for ``taobao``, ``tmall``, ``1688`` and ``jd``. Those sites match Chinese text far better than English, and the server does not translate.

|

Marketplaces
------------

``status`` is what ``health()`` reports. ``verified`` means a live run in this repository's history returned offers that the parser matched. ``unverified`` means the lane is written from the source's documentation or from field notes in the code, and has not been run since the 2026-11 rewrite because no keys were available.

.. list-table::
   :header-rows: 1

   * - Marketplace
     - Source
     - Key
     - Status
   * - ``ebay_au``
     - eBay Browse API, ``EBAY_AU`` marketplace
     - ``EBAY_APP_ID``, ``EBAY_CERT_ID``
     - unverified
   * - ``ebay_sold``
     - Apify ``caffein.dev/ebay-sold-listings`` on ebay.com.au. Returns comps.
     - ``APIFY_TOKEN``
     - unverified
   * - ``amazon_au``
     - Apify ``junglee/free-amazon-product-scraper``
     - ``APIFY_TOKEN``
     - unverified
   * - ``woolworths``, ``coles``, ``aldi``
     - Apify dromb actors, with unit prices and specials
     - ``APIFY_TOKEN``
     - unverified
   * - ``facebook``
     - SociaVault Facebook Marketplace search around the destination
     - ``SOCIAVAULT_API_KEY``
     - unverified
   * - ``gumtree``
     - Apify ``crawlerbros/gumtree-scraper``
     - ``APIFY_TOKEN``, ``GUMTREE_COOKIES``
     - degraded
   * - ``ozbargain``
     - OzBargain RSS feed
     - none
     - verified
   * - ``cheapies``
     - Cheapies RSS feed (New Zealand; left out of AU results)
     - none
     - verified
   * - ``taobao``, ``tmall``
     - Apify ``zen-studio/taobao-search-scraper``. One run serves both.
     - ``APIFY_TOKEN``
     - unverified
   * - ``jd``
     - Apify ``zen-studio/jd-com-search-scraper``
     - ``APIFY_TOKEN``
     - unverified
   * - ``1688``
     - TMAPI ``/1688/search/items``, else Apify ``zen-studio/1688-wholesale-scraper``
     - ``TMAPI_TOKEN`` or ``APIFY_TOKEN``
     - unverified
   * - ``pdd``
     - none for search. TMAPI item detail works through ``get_offer_detail``.
     - ``TMAPI_TOKEN``
     - unsupported
   * - ``aliexpress``
     - none yet
     -
     - unsupported

To verify the lanes you hold keys for, and record their responses as test fixtures:

.. code-block:: sh

   uv run python scripts/live_smoke.py --record        # every marketplace
   uv run python scripts/live_smoke.py ebay_au jd      # a subset

Each Apify lane starts one actor run, which spends Apify credits.

.. raw:: html

   <details>
   <summary><b>Source notes</b></summary>

- **Deal feeds.** ``ozbargain`` and ``cheapies`` read the sites' RSS feeds, which hold about the latest 100 deals. A search keeps deals whose title, brand or tags contain every query word. Each deal carries votes, comments, clicks and expiry, and the first dollar amount in its title as the price.
- **Grocery.** Offers carry ``unit_price_aud``, ``unit`` and ``regular_price_aud``. ``price_aud`` holds the special price when there is one. The ``cheapest`` sort uses unit price, so a $4.50 2 L bottle beats a $3.10 1 L bottle. Results pass a relevance filter: every query word must appear in the name, brand or category.
- **eBay.** ``price_aud`` is set only when eBay reports the amount in AUD. Other currencies go to ``price_native`` with ``currency``. ``shipping.cost_aud`` is set only when eBay states a cost for the buyer's postcode.
- **TMAPI.** The 1688 endpoints are ``/1688/search/items`` and ``/1688/item_detail``. ``/alibaba/...`` is Alibaba.com, which this server does not use. TMAPI's docs pass the key as an ``apikey`` header; the server sends that header and the ``apiToken`` query parameter until one is confirmed with a key.
- **Tmall.** Taobao actor items flagged ``isTmall`` are labelled ``tmall``. If the actor's items carry no such flag, ``tmall`` returns an ``unsupported`` diagnostic and the listings stay under ``taobao``.
- **Keepa.** ``get_price_history`` needs ``KEEPA_API_KEY`` and ``KEEPA_DOMAIN``. Keepa's official clients list domain ids 1 to 12 (12 is Brazil) and no Australian id, so the server sets no default. Prices are read as integer cents; ``-1`` means no offer.
- **Amazon Product Advertising API 5.0** is deprecated in favour of the Creators API, which requires 10 qualifying sales in the past 30 days. The server uses the Apify actor.
- **Costco** is left out. Every Costco actor on the Apify store targets costco.com (US, USD).

.. raw:: html

   </details>

|

Delivery and landed cost
------------------------

The destination defaults to Brisbane: ``SHIP_TO_COUNTRY=AU``, ``SHIP_TO_POSTCODE=4000``. ``search_offers`` takes ``ship_to`` and ``postcode`` to override them for one call. Pickup searches centre on ``SHIP_TO_LAT`` and ``SHIP_TO_LNG``.

Each offer has ``shipping.delivery`` and ``shipping.delivery_basis``, which states what the status rests on.

.. list-table::
   :header-rows: 1

   * - ``delivery``
     - Applies to
   * - ``direct``
     - ``ebay_au`` items for which eBay lists a shipping option to the postcode; ``amazon_au``, ``woolworths``, ``coles``; ``ozbargain`` deals whose title says "Delivered"
   * - ``pickup``
     - ``gumtree``, ``facebook``, ``aldi``. Drop these with ``include_pickup=false``.
   * - ``via_forwarder``
     - ``taobao``, ``tmall``, ``1688``, ``jd``, ``pdd``: sellers ship within China only
   * - ``no``
     - ``cheapies`` (New Zealand retailers). Left out of results and counted in a ``not_deliverable`` diagnostic.
   * - ``unknown``
     - The source does not say. Ranked after an equal offer with a known status.

``landed_aud`` is the total for ``qty`` delivered, and ``landed_breakdown`` lists its parts. ``landed_basis`` says how firm it is:

- ``exact``: item price plus the shipping cost the source stated, or a pickup listing.
- ``item_only``: the source stated no shipping cost, so the total leaves it out.
- ``estimated``: a China offer with a freight forwarder estimate.

The forwarder estimate is::

   freight = max(FORWARDER_MIN_CHARGE_AUD, weight_kg * qty * FORWARDER_RATE_AUD_PER_KG)
   landed  = (goods + China domestic leg + freight) * (1 + FORWARDER_FEE_PCT) * (1 + GST_RATE)

Search results carry no weight, so ``weight_kg`` is the ``est_weight_kg`` argument or ``FORWARDER_DEFAULT_WEIGHT_KG``. The defaults in ``.env.example`` (12 AUD per kg, 0.5 kg, 15 AUD minimum) are placeholders. Set them from your forwarder's rate card before relying on the totals.

|

Ranking
-------

- **Buyable offers only.** Comps, diagnostics and offers with ``delivery: no`` are not ranked.
- **MOQ.** Offers whose ``moq`` exceeds ``qty`` go to the end in every sort.
- **cheapest.** Sorts by ``landed_aud``. Grocery offers sort by ``unit_price_aud``.
- **fastest.** Sorts by the later bound of ``shipping.eta_days``, then price. The ETA windows are fixed per marketplace, not read from the source.
- **best_value.** ``0.5 price + 0.25 speed + 0.25 trust``, less 0.05 when delivery is ``unknown``. Price uses landed cost per unit. Trust uses net deal-site votes when present, then ``seller.rating``, then ``source_reliability``.
- **Currency.** ``price_cny`` converts with ``CNY_TO_AUD`` (default 0.215) and Cheapies prices with ``NZD_TO_AUD`` (default 0.92). Both are fixed settings, not live rates.

|

Database
--------

When ``DATABASE_URL`` is set, the server caches search results and logs searches in Postgres (schema ``PROCUREMENT_PG_SCHEMA``, default ``procurement``). Without it the server keeps no state and ``search_history`` returns ``db_disabled``.

.. code-block:: sh

   # in .env
   DATABASE_URL=postgresql://procurement:__SET_ME__@10.1.1.3:5432/jupiter

   # apply once
   psql "$DATABASE_URL" -f migrations/001_procurement_cache.sql

The tables are ``search_cache`` and ``search_log``. The cache lifetime is ``PROCUREMENT_CACHE_TTL_S`` (default 3600 seconds). The cache key covers the query, marketplaces, sort, quantity, destination, weight and eBay options.

|

Develop
-------

.. code-block:: sh

   uv sync
   uv run ruff check .
   uv run pyright procurement server.py
   uv run pytest                     # no network, no keys
   uv run pytest -m live             # reserved for tests that call real sources

.. code-block:: text

   server.py              entry point; imports procurement.app
   procurement/
     app.py               assembles the server, main()
     instance.py          the MCPServer instance and database lifespan
     tools.py             the 7 tools and the prompt
     config.py            Settings, read from the environment and .env
     models.py            Offer, Shipping, Location, diagnostics
     lanes/               one module per source; __init__.py is the registry
     lanes/base.py        runs lanes at once under one deadline
     landed.py            delivery status and landed cost
     ranking.py           the three sorts
     keepa.py             price history
     http.py              retry and Apify actor runs
     db.py                Postgres cache and search log
     routes.py            eBay account-deletion notification routes
   scripts/live_smoke.py  one live search per marketplace; --record saves fixtures
   tests/                 pytest suite, HTTP mocked with respx
   migrations/            Postgres schema

To add a marketplace: write ``parse_x(items, ...)`` and ``search_x(ctx)`` in a lane module, raise ``LaneError`` for failures, and add a ``LaneSpec`` to ``procurement/lanes/__init__.py``.

|

Licence
-------

``pyproject.toml`` declares MIT.

|

.. raw:: html

   <p align="center"><picture><source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-dark.svg"><img alt="" src="https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/rule/end-light.svg" width="50%"></picture></p>


|

.. raw:: html

   <p align="right"><sub>jupiter.au</sub></p>

.. |search-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/search-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |search-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/search-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |image-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/image-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |image-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/image-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |file-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/file-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |file-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/file-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |pulse-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/pulse-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |pulse-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/pulse-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |chat-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/chat-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |chat-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/chat-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |cart-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/cart-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |cart-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/cart-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |cloud-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/cloud-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |cloud-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/cloud-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
.. |link-l| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/link-light.svg#gh-light-mode-only
   :width: 20
   :alt:
.. |link-d| image:: https://raw.githubusercontent.com/belikh/design/latest/packages/github/graphics/icon/link-dark.svg#gh-dark-mode-only
   :width: 20
   :alt:
