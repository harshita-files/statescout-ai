# StockWatch

A polished, dynamic stock-market dashboard that is **deliberately flawed**. It is a test target
for StateScout: multi-page, cyclic navigation, volatile content and flaky endpoints.
Stdlib only (`http.server`); frontend is vanilla HTML/CSS/JS, no CDN, no build step.

## Run

```bash
python test-apps/stockwatch/server.py --port 8765                 # live, random
python test-apps/stockwatch/server.py --port 8765 --seed 7        # deterministic prices, flakiness, promos
python test-apps/stockwatch/server.py --tick-interval 0 --debug   # frozen prices; /api/_tick?n=N advances
```

Open <http://127.0.0.1:8765/>. Sign in at `/login` as guest, trader or admin (no password).

## Pages and states

`/markets` (sort, search, sector filter), `/watchlist`, `/portfolio`, `/trade`, `/news`, `/news/<id>`,
`/settings`, `/admin`, `/login`, `/about`, `/stock/<SYM>` (hash tabs `#overview #chart #financials`,
candle/line toggle). Live updates via SSE (`/api/stream`, polling fallback), ticker tape, flashes.

Non-determinism: `/api/quote` fails or returns partial data ~20% of calls; `/api/promo` shows a
random promo modal ~35% of page loads; prices random-walk every tick.

## Seeded flaws

Documented in `expected.json` (`id`, `description`, `page`, `rule_text`, `severity`): SW-01 to SW-10.
Anything not listed there is a bug in the app. The integration test is
`tests/integration/stockwatch/test_stockwatch.py`.
