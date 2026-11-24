import argparse
import logging
from pathlib import Path

import pandas as pd

from .core import Book, report, scan, settle


def main() -> int:
    p = argparse.ArgumentParser(prog="polypaper", description="Paper forward test of Polymarket underdogs")
    p.add_argument("cmd", choices=["scan", "settle", "report", "run"])
    p.add_argument("--state", default="polymarket_paper.json")
    a = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    path = Path(a.state)
    book = Book.load(path)
    if a.cmd in ("scan", "run"):
        new = scan(book, pd.Timestamp.now("UTC"))
        for b in new:
            logging.info("paper bet: %s @ %.3f [%s] %s", b.side, b.ask, b.category, b.question[:70])
        logging.info("%d new paper bets", len(new))
    if a.cmd in ("settle", "run"):
        done = settle(book)
        for b in done:
            logging.info("settled: %s -> %s [%s] %s", b.side, b.won, b.category, b.question[:70])
    if a.cmd != "report":
        book.save(path)
    print(report(book))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
