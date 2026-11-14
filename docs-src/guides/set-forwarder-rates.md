---
title: Set forwarder rates
summary: Replace the placeholder freight rates so that landed cost for Chinese offers matches your forwarder's rate card.
order: 40
icon: sliders
audience: users
status: draft
---

Offers from `taobao`, `tmall`, `1688`, `jd` and `pdd` ship within China only. Their `landed_aud` holds an estimate of a [[term:Forwarder]]'s charge. The defaults are placeholders: 12 AUD per kg, a 15 AUD minimum and a 0.5 kg item.

## Steps

1. Read these four numbers from your forwarder's rate card.

   | Setting | Default | Meaning |
   | --- | --- | --- |
   | `FORWARDER_RATE_AUD_PER_KG` | `12.0` | Freight per kg, China to Australia. |
   | `FORWARDER_MIN_CHARGE_AUD` | `15.0` | The smallest freight charge for one shipment. |
   | `FORWARDER_FEE_PCT` | `0.0` | The forwarder's service fee as a fraction: `0.05` is 5 %. |
   | `FORWARDER_DEFAULT_WEIGHT_KG` | `0.5` | The weight of one item when a search gives no `est_weight_kg`. |

2. Set them in `.env`.

   ```sh title=".env"
   FORWARDER_RATE_AUD_PER_KG=9.5
   FORWARDER_MIN_CHARGE_AUD=20
   FORWARDER_FEE_PCT=0.05
   ```

3. Restart the server and call `health`. `forwarder_estimate` shows the values in use.

4. Pass `est_weight_kg` on each search of Chinese marketplaces. Search results carry no weight, so the estimate otherwise uses the default.

## Currency

`CNY_TO_AUD` (default `0.215`) and `NZD_TO_AUD` (default `0.92`) are fixed settings. The server fetches no live rates. Update them when the rates move.

:::see-also
- [[concepts/landed-cost]]
- [[reference/settings]]
:::
