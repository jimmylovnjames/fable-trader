# fable-trader

A hands-off crypto spot trader for small accounts. It holds BTC and ETH while they
trend up and moves to cash when they don't. Long-only, no leverage, one decision a day.

**It starts in paper mode.** Nothing touches real money until you add API keys and pass `--live`.

## What it does

Every day after the 00:00 UTC candle closes, for each asset:

1. **Trend score**: fraction of the 20/50/100/200-day moving averages the price is above (0 to 1).
2. **Volatility scaling**: shrinks the position when 30-day volatility is above the 60% target.
3. **Weight** = score x scale / number of assets, total capped at 100% of the account.
4. Trades only if a weight is off by more than 10% of equity (keeps fees down).
5. **Kill switch**: if the account falls 50% from its peak, it sells everything and stops until you run `reset`.

## Backtest

`python -m fabletrader backtest` reproduces this from Binance public data (BTC+ETH, signal on the
close, filled at the next open, 0.5% cost per side, $100 start, kill switch off):

| 2018-03 to 2026-11 | CAGR | Volatility | Sharpe | Max drawdown |
|---|---|---|---|---|
| fable-trader | 30.9% | 34.4% | 0.95 | -46.2% |
| Buy and hold (50/50) | 21.0% | 66.3% | 0.63 | -79.1% |

| Year | Strategy | Buy and hold |
|---|---|---|
| 2018 | -23.0% | -72.6% |
| 2019 | 64.0% | 58.0% |
| 2020 | 191.6% | 332.9% |
| 2021 | 68.5% | 143.3% |
| 2022 | -29.4% | -66.8% |
| 2023 | 51.0% | 123.0% |
| 2024 | 43.7% | 82.9% |
| 2025 | 3.0% | -8.7% |
| 2026 (to Nov) | 1.3% | -19.4% |

Read this honestly:

- **It is a drawdown reducer, not a money printer.** It lags badly in strong bull years and
  earns its keep in bear markets. It still lost 23% and 29% in its two worst years.
- **Most of the return came from 2019-2021.** Since 2022 it has made roughly 9% a year.
- **Past results do not predict future ones.** The parameters were picked up front and nearby
  values give similar results (Sharpe 0.92-1.07), but BTC and ETH were chosen knowing they survived.
- **You can lose money.** Only fund it with money you can afford to lose.

## Ideas tested and rejected

Both are reproducible from `research/` (they download their own data).

- **Buy dips / sell bounces on small tokens** (`research/range_trading.py`): 10,280 hourly trades on
  22 tokens since 2023. It wins 63% of the time but averages +0.05% per trade before fees. After
  Kraken fees it lost money on all 22 tokens in every year. The bounces are smaller than the round-trip
  fee, and an occasional −30% "dip" wipes out dozens of wins.
- **This trend bot on a basket of altcoins** (`research/altcoin_basket.py`): 8–13% CAGR against about 30% for
  BTC+ETH, with the same ~−46% drawdowns. The 8% comes from a point-in-time top-20 that includes coins that
  later died (LUNA, FTT and others); a basket hand-picked today looks about 5 points a year better only because
  it contains survivors. Blending in altcoins lowered both return and Sharpe, and the basket version needs $500+
  to trade at all.

- **Fast trading on meme coins, DeFi tokens and new listings** (`research/fast_trading.py`, `new_listings.py`,
  `fade_perps.py`): hourly data on 300+ coins since 2023, delisted coins included.
  - Buying new listings: about 70% are lower 30 days later; every group listed since 2021 averaged −54% to −75% after a year, apart from 2023.
  - Chasing pumps and buying 24h/48h breakouts: about 0% to −5% per trade *before* fees, worse after.
  - Shorting pumps with perpetual futures: looks good on spot prices, but real funding (~0.6% per trade on
    new listings) erases it. A $100 account simulation ends at $4–$21 depending on the stop-loss.
- **Polymarket** (`research/fetch_polymarket.py`, `polymarket_calibration.py`): 10,000 resolved yes/no markets sampled
  from 131,800 with $10k+ volume since January 2025, priced 1–168 hours before their scheduled end.
  - Buying "safe" favorites (90¢+) loses 0.4–4% per dollar: favorites win *less* often than their price says.
  - Long shots (10¢ or less) in markets with $250k+ volume lose 30–58% per dollar.
  - Long shots in thin markets (under $250k) look profitable even at the real asking price (about 1.25× the
    midpoint, measured on live order books), mostly in sports. But the result was negative in 2025, positive only in 2026,
    and roughly 2 standard deviations after many slices of the data, so it is **unproven**. `polypaper/` forward-tests it with paper bets.
  - Sports markets have charged takers `0.05 × shares × p × (1 − p)` since April 2026 (about 4.75% of the stake at 5¢).
- **pump.fun** (`research/collect_pumpfun.py`, `pumpfun_graduation.py`, `pumpfun_snipe.py`): every new coin
  recorded for 80 minutes on 2026-11-24, priced with GeckoTerminal minute candles.
  - Of the SOL-priced coins followed for 40 minutes, under 1% graduated, about 75% were back at or below the starting price,
    and about 2% ever reached a $20k market cap.
  - Buying at graduation: the median coin was down 89% an hour later and 96% a day later. 27 of 28 coins with clean data
    were down within 6 hours, and 96% had lost more than half within a day. All the excluded coins either had bad data or
    crashed in their first 15 minutes.
  - Sniping new coins: buying in the first minute and selling at +100%, at −50%, or after 30 minutes averaged
    **−10.7% per trade** (95% range −18% to −3%) and won 15% of trades. Every other exit tried lost 8–26% per trade:
    letting winners run, a +400% target, or just holding 5 or 30 minutes. Sample: 168 coins drawn by peak market cap
    from 976 and re-weighted (`pumpfun_snipe_exits.py`, `pumpfun_snipe_robust.py`). This replay already assumes
    fills at candle prices. Real bots that trade in the launch block get in ahead of you.

## Polymarket paper test

Paper only. It places no orders and needs no wallet or keys.

```bash
python -m polypaper run      # record new $1 paper bets on long shots (1-10¢) in thin markets ending in 4-30h,
                             # at the real best ask with Polymarket's taker fee, and settle resolved ones
python -m polypaper report   # wins vs. what the prices implied, by category
```

Run it a few times a day, for example from cron or a scheduled GitHub Action (not set up here). Results go to
`polymarket_paper.json`. Do not put money in unless sports shows z > 2 after 300+ settled bets. Polymarket's
international site blocks US users; check what is legal where you live before trading it.

## Quick start (paper)

```bash
pip install -r requirements.txt
python -m fabletrader backtest        # see the numbers yourself
python -m fabletrader run             # paper-trades $100 against live Kraken prices, forever
python -m fabletrader status
```

## Going live

1. Open an exchange account (default: [Kraken](https://www.kraken.com), works for US/EU, ~$5 minimum order).
   Fund it with **$100 or more**. Below ~$50 the minimum order size stops the bot from sizing positions properly.
2. Create an API key with **only** "Query funds" and "Create & modify orders". **Never enable withdrawals.**
3. `cp .env.example .env` and paste the key and secret.
4. `python -m fabletrader run --live`

Use an account dedicated to the bot: it treats all the quote currency and all BTC/ETH in the
account as its own. Deposits are fine; a withdrawal looks like a loss to the kill switch
(run `reset` afterwards).

Other exchanges: set `exchange` and `quote` in `config.yaml` (any [ccxt](https://github.com/ccxt/ccxt) id).
Only Kraken has been exercised here.

## Run it for free without a server

`.github/workflows/trade.yml` runs the bot once a day on GitHub Actions and commits `state.json` back.

- It paper-trades by default and is already running daily on this repository. GitHub often starts
  scheduled jobs hours late; that doesn't matter for a once-a-day strategy.
- To go live: add repository secrets `EXCHANGE_API_KEY` and `EXCHANGE_API_SECRET`, then set
  repository variable `LIVE` to `true`. Delete any paper `state.json` first.
- A failed run emails you. Keep the repository private: `state.json` holds your equity history.

Or with Docker on any always-on machine:

```bash
docker build -t fable-trader .
docker run -d --restart unless-stopped --env-file .env -v "$PWD/state:/app/state" \
  fable-trader -c config.yaml run --live
```

(set `state_file: state/state.json` in `config.yaml` for the Docker volume.)

## Commands

| Command | What it does |
|---|---|
| `run [--live] [--once] [--force]` | Trade. `--once` runs a single cycle (cron/CI). |
| `status [--live]` | Balances, positions, halt state. |
| `backtest [--start 2017-01-01] [--cash 100]` | Replay on history. |
| `reset` | Clear a kill-switch halt. |

## Costs

Kraken charges about 0.40% per market order at the lowest tier. The bot averages ~90 small
orders a year; that drag is already in the backtest. Avoid "instant buy" style apps that charge
1%+: at 1.2% per side the backtested CAGR drops to about 21%.

## Layout

```
fabletrader/strategy.py   target weights from daily closes
fabletrader/engine.py     weights -> orders (shared by backtest and live)
fabletrader/backtest.py   historical replay
fabletrader/broker.py     paper and live (ccxt) execution
fabletrader/bot.py        daily cycle, state, kill switch
tests/                    python -m pytest
polypaper/                paper forward test of the Polymarket long-shot idea
research/                 studies of rejected strategies (data downloads to research/data/, not committed)
```
