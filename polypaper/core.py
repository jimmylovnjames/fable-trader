from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import requests

GAMMA = "https://gamma-api.polymarket.com/markets"
CLOB = "https://clob.polymarket.com/book"
MIN_ASK, MAX_ASK = 0.01, 0.10   # underdog price range (backtest used mids of 0.5c-10c)
MIN_VOL, MAX_VOL = 10_000, 250_000
HOURS = (4, 30)
STAKE = 1.0             # paper dollars per bet

SPORTS = re.compile(r" vs\.?| o/u|exact score|win on|spread|halftime|score first|both teams|draw", re.I)


def category(question: str) -> str:
    q = question.lower()
    if "temperature" in q:
        return "weather"
    if re.search(r"price of|bitcoin|ethereum|solana|xrp|up or down", q):
        return "crypto"
    if SPORTS.search(question):
        return "sports"
    return "other"


def fee_rate(m: dict, cat: str) -> float:
    """Taker fee rate per Polymarket docs (fee = shares * rate * p * (1-p)). Unknown categories get the
    highest common rate (0.05) so the test errs against the hypothesis."""
    if not m.get("feesEnabled"):
        return 0.0
    return 0.01 if cat in ("weather", "crypto") else 0.05


@dataclass
class Bet:
    market_id: str
    question: str
    category: str
    side: str            # outcome name bought
    side_index: int      # index into outcomes
    ask: float
    ask_size: float      # shares available at the ask
    shares: float
    fee: float
    volume: float
    end: str
    placed_at: str
    status: str = "open"           # open | settled
    payout: float | None = None
    won: float | None = None       # 1, 0, or 0.5 for 50/50 resolutions


@dataclass
class Book:
    bets: list[Bet] = field(default_factory=list)

    @classmethod
    def load(cls, path: Path) -> "Book":
        if not path.exists():
            return cls()
        return cls([Bet(**b) for b in json.loads(path.read_text())["bets"]])

    def save(self, path: Path) -> None:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"bets": [asdict(b) for b in self.bets]}, indent=1))
        tmp.replace(path)


def candidate_markets(now, get=requests.get) -> list[dict]:
    out, off = [], 0
    while off < 2000:
        r = get(GAMMA, params=dict(closed="false", active="true", limit=100, offset=off,
                                   volume_num_min=MIN_VOL, volume_num_max=MAX_VOL,
                                   end_date_min=(now + _h(HOURS[0])).isoformat(),
                                   end_date_max=(now + _h(HOURS[1])).isoformat()), timeout=60)
        batch = r.json() if r.status_code == 200 else []
        if not isinstance(batch, list) or not batch:
            break
        out += batch
        off += 100
    return out


def _h(n):
    import pandas as pd
    return pd.Timedelta(hours=n)


def best_ask(token_id: str, get=requests.get) -> tuple[float, float] | None:
    r = get(CLOB, params=dict(token_id=token_id), timeout=30)
    if r.status_code != 200:
        return None
    asks = r.json().get("asks") or []
    if not asks:
        return None
    a = min(asks, key=lambda x: float(x["price"]))
    return float(a["price"]), float(a["size"])


def pick_underdog(m: dict) -> tuple[int, str] | None:
    """Index of the underdog outcome if one side's mid is <= MAX_ASK, else None."""
    try:
        outs, toks = json.loads(m["outcomes"]), json.loads(m["clobTokenIds"])
        bid, ask = float(m["bestBid"]), float(m["bestAsk"])
    except (KeyError, TypeError, ValueError):
        return None
    if len(outs) != 2 or len(toks) != 2:
        return None
    mid = (bid + ask) / 2
    if mid <= MAX_ASK:
        return 0, toks[0]
    if mid >= 1 - MAX_ASK:
        return 1, toks[1]
    return None


def scan(book: Book, now, get=requests.get) -> list[Bet]:
    have = {b.market_id for b in book.bets}
    new = []
    for m in candidate_markets(now, get):
        if str(m["id"]) in have:
            continue
        pick = pick_underdog(m)
        if not pick:
            continue
        idx, token = pick
        ba = best_ask(token, get)
        if not ba:
            continue
        ask, size = ba
        if not MIN_ASK <= ask <= MAX_ASK or size * ask < STAKE:
            continue
        cat = category(m["question"])
        shares = STAKE / ask
        fee = shares * fee_rate(m, cat) * ask * (1 - ask)
        b = Bet(str(m["id"]), m["question"], cat, json.loads(m["outcomes"])[idx], idx, ask, size, shares,
                round(fee, 5), float(m.get("volumeNum") or 0), m["endDate"], now.isoformat())
        book.bets.append(b)
        new.append(b)
        have.add(b.market_id)
    return new


def settle(book: Book, get=requests.get) -> list[Bet]:
    done = []
    for b in book.bets:
        if b.status != "open":
            continue
        r = get(f"{GAMMA}/{b.market_id}", timeout=30)
        if r.status_code != 200:
            continue
        m = r.json()
        if not m.get("closed"):
            continue
        try:
            px = [float(x) for x in json.loads(m["outcomePrices"])]
        except (KeyError, TypeError, ValueError):
            continue
        if sorted(px) not in ([0.0, 1.0], [0.5, 0.5]):
            continue  # closed but not yet resolved
        b.won = px[b.side_index]
        b.payout = b.shares * b.won
        b.status = "settled"
        done.append(b)
    return done


def report(book: Book) -> str:
    lines = [f"{'category':10s}{'bets':>6s}{'settled':>8s}{'wins':>6s}{'expected':>9s}{'z':>6s}"
             f"{'staked':>8s}{'fees':>7s}{'payout':>8s}{'ROI':>8s}"]
    cats = sorted({b.category for b in book.bets}, key=lambda c: (c != "sports", c))
    for cat in cats + ["ALL"]:
        bs = [b for b in book.bets if cat in ("ALL", b.category)]
        s = [b for b in bs if b.status == "settled"]
        wins = sum(b.won for b in s)
        exp = sum(b.ask for b in s)
        var = sum(b.ask * (1 - b.ask) for b in s)
        z = (wins - exp) / math.sqrt(var) if var > 0 else 0.0
        staked = STAKE * len(s)
        fees = sum(b.fee for b in s)
        pay = sum(b.payout for b in s)
        roi = (pay - staked - fees) / staked if staked else 0.0
        lines.append(f"{cat:10s}{len(bs):6d}{len(s):8d}{wins:6.1f}{exp:9.1f}{z:6.2f}"
                     f"{staked:8.0f}{fees:7.2f}{pay:8.2f}{roi * 100:7.1f}%")
    lines.append("z > 2 on sports after 300+ settled bets would be the first real evidence; until then, no money.")
    return "\n".join(lines)
