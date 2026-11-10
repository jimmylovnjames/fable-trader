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

- It works as soon as this branch is the repository's default branch. It paper-trades by default.
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
```
