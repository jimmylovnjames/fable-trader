import json

import pandas as pd
import pytest

from polypaper.core import Book, category, fee_rate, pick_underdog, report, scan, settle

NOW = pd.Timestamp("2026-11-24T12:00:00Z")


def market(bid, ask, q="Arsenal vs. Chelsea: O/U 4.5", fees=True, mid="1"):
    return {"id": mid, "question": q, "outcomes": json.dumps(["Yes", "No"]), "clobTokenIds": json.dumps(["T0", "T1"]),
            "bestBid": bid, "bestAsk": ask, "feesEnabled": fees, "volumeNum": 50_000,
            "endDate": "2026-11-25T00:00:00Z"}


class Resp:
    def __init__(self, data, code=200):
        self._d, self.status_code = data, code

    def json(self):
        return self._d


def fake_get(markets, books, resolved=None):
    def get(url, params=None, timeout=None):
        if url.endswith("/markets"):
            return Resp(markets if params["offset"] == 0 else [])
        if url.endswith("/book"):
            return Resp(books.get(params["token_id"], {"asks": []}))
        mid = url.rsplit("/", 1)[1]
        return Resp((resolved or {}).get(mid, {"closed": False}))
    return get


def test_category_and_fees():
    assert category("Arsenal vs. Chelsea: O/U 4.5") == "sports"
    assert category("Will the highest temperature in Paris be 16°C on May 1?") == "weather"
    assert category("Will Bitcoin reach $66,000 on November 24?") == "crypto"
    assert category("Will Ludwig finish GTA VI by November 24?") == "other"
    assert fee_rate({"feesEnabled": True}, "sports") == 0.05
    assert fee_rate({"feesEnabled": True}, "weather") == 0.01
    assert fee_rate({"feesEnabled": False}, "sports") == 0.0


def test_pick_underdog_both_sides():
    assert pick_underdog(market(0.04, 0.06)) == (0, "T0")   # YES is the underdog
    assert pick_underdog(market(0.94, 0.96)) == (1, "T1")   # NO is the underdog
    assert pick_underdog(market(0.40, 0.42)) is None


def test_scan_uses_real_ask_fee_and_filters():
    ms = [market(0.04, 0.06, mid="1"), market(0.94, 0.96, mid="2")]
    books = {"T0": {"asks": [{"price": "0.07", "size": "100"}, {"price": "0.06", "size": "50"}]},
             "T1": {"asks": [{"price": "0.05", "size": "100"}]}}
    book = Book()
    new = scan(book, NOW, fake_get(ms, books))
    by_id = {b.market_id: b for b in new}
    assert set(by_id) == {"1", "2"}
    b1 = by_id["1"]
    assert b1.ask == 0.06 and b1.shares == pytest.approx(1 / 0.06)
    assert b1.fee == pytest.approx(round(1 / 0.06 * 0.05 * 0.06 * 0.94, 5))  # docs: shares * rate * p * (1 - p)
    assert by_id["2"].side == "No" and by_id["2"].ask == 0.05
    assert scan(book, NOW, fake_get(ms, books)) == []        # never re-bets a market


def test_skips_thin_ask_and_out_of_range():
    ms = [market(0.04, 0.06)]
    assert scan(Book(), NOW, fake_get(ms, {"T0": {"asks": [{"price": "0.06", "size": "5"}]}})) == []    # $0.30 < $1
    assert scan(Book(), NOW, fake_get(ms, {"T0": {"asks": [{"price": "0.15", "size": "500"}]}})) == []  # above 10c
    assert scan(Book(), NOW, fake_get(ms, {"T0": {"asks": [{"price": "0.005", "size": "900"}]}})) == []  # below 1c


def test_settle_and_report(tmp_path):
    ms = [market(0.04, 0.06, mid="1"), market(0.94, 0.96, mid="2")]
    books = {"T0": {"asks": [{"price": "0.05", "size": "100"}]}, "T1": {"asks": [{"price": "0.05", "size": "100"}]}}
    book = Book()
    scan(book, NOW, fake_get(ms, books))
    resolved = {"1": {"closed": True, "outcomePrices": json.dumps(["1", "0"])},    # underdog YES won
                "2": {"closed": True, "outcomePrices": json.dumps(["1", "0"])}}    # underdog NO lost
    done = settle(book, fake_get([], {}, resolved))
    assert {b.market_id: b.won for b in done} == {"1": 1.0, "2": 0.0}
    assert next(b for b in book.bets if b.market_id == "1").payout == pytest.approx(20.0)
    p = tmp_path / "s.json"
    book.save(p)
    assert len(Book.load(p).bets) == 2
    assert "sports" in report(book)
