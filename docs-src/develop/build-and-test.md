---
title: Build and test
summary: Set up a checkout, run the linter, the type checker and the 65 tests, and find your way in the code.
order: 10
icon: git-branch
audience: developers
status: draft
---

## Commands

```sh title="Check a change"
uv sync
uv run ruff check .
uv run pyright procurement server.py
uv run pytest
```

`uv run pytest` needs no network and no keys: HTTP is mocked with `respx`. It prints:

```text title="Output"
65 passed in 4.59s
```

| Command | Result |
| --- | --- |
| `uv run ruff check .` | Lint. Line length 100. Prints `All checks passed!`. |
| `uv run pyright procurement server.py` | Type check in strict mode. Prints `0 errors, 0 warnings, 0 informations`. |
| `uv run pytest` | The test suite, without tests marked `live`. |
| `uv run pytest -m live` | Reserved for tests that call live sources and spend credits. |
| `uv run mcp dev server.py` | The MCP Inspector, to call tools by hand. |

## Layout

```text title="Files"
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
docs-src/              the source of these pages
```

## Tests

| File | Covers |
| --- | --- |
| `tests/test_search.py` | `search_offers` from call to result. |
| `tests/test_run_lanes.py` | The deadline, groups and one outcome per lane. |
| `tests/test_lanes.py` | The parser of each lane. |
| `tests/test_envelopes.py` | Apify error envelopes and the `quota` code. |
| `tests/test_landed.py` | Delivery status and landed cost. |
| `tests/test_rank.py` | The three sorts. |
| `tests/test_deals.py` | The deal feed parser and the query word filter. |
| `tests/test_detail.py` | `get_offer_detail`. |
| `tests/test_env_docs.py` | `.env.example` against the settings in `config.py`. |

## Documentation

The pages are Markdown in `docs-src/`. `jupiter-docs` generates `docs/*.md` and the site from them. Change a page in the same commit as the code it describes.

```sh title="Check and build the pages"
npx jupiter-docs check
npx jupiter-docs build --md
```

:::see-also
- [[develop/add-a-marketplace]]
- [[develop/verify-a-lane]]
:::
