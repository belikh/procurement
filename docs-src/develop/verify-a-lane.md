---
title: Verify a lane
summary: Run one live search per marketplace with scripts/live_smoke.py and record the replies as test fixtures.
order: 30
icon: pulse
audience: developers
status: draft
---

`scripts/live_smoke.py` runs one live `search_offers` call per [[term:Marketplace]] and prints one row for each. Use it after you add a key or change a lane.

:::warning Apify credits
Each Apify lane starts one actor run, which spends Apify credits. Name the marketplaces you want to check to avoid running all of them.
:::

## Run

```sh title="Live check"
uv run python scripts/live_smoke.py                 # every marketplace
uv run python scripts/live_smoke.py ebay_au jd      # a subset
uv run python scripts/live_smoke.py --record        # also save the replies
```

The script searches for "wireless mouse", and for "full cream milk 2l" on `woolworths`, `coles` and `aldi`.

```text title="Output for ozbargain and cheapies"
marketplace     outcome      offers priced  diag    sec  note
ozbargain       diagnostic        0      0     1    0.1  [ozbargain] no match for 'wireless mouse'
cheapies        diagnostic        0      0     1    0.3  [cheapies] no match for 'wireless mouse'

0/2 marketplaces returned offers in 0.5s
no offers and no diagnostic: none
```

| Column | Meaning |
| --- | --- |
| `outcome` | `offers`, `diagnostic`, `empty` (neither) or `raised` (the tool raised an exception). |
| `offers`, `priced` | The number of offers, and how many have a `price_aud`. |
| `diag` | The number of diagnostics. |
| `sec` | Seconds the search took. |
| `note` | The first diagnostic's title. |

The last line names every marketplace that returned neither offers nor a diagnostic. It prints `none` when the server works as designed.

## Record fixtures

`--record` writes each upstream reply to `tests/fixtures/<marketplace>/NN.json` and a summary to `tests/fixtures/MANIFEST.json`.

The recorder drops query strings and headers. It replaces the value of every configured secret found in a body with `REDACTED`. A secret is an environment variable of 8 or more characters whose name contains `TOKEN`, `KEY`, `SECRET`, `CERT`, `COOKIES` or `DATABASE_URL`.

Read a recorded file before you commit it. Listings can hold seller names and other personal data.

## Mark a lane verified

1. Run the script for the marketplace and confirm the outcome is `offers`.
2. Record the reply and add a parser test in `tests/test_lanes.py` that reads the fixture.
3. Set `status="verified"` on the lane's `LaneSpec` in `procurement/lanes/__init__.py`.
4. Change the status in `docs-src/reference/marketplaces.md` and in `README.rst`.

:::see-also
- [[reference/marketplaces]]
- [[develop/add-a-marketplace]]
:::
