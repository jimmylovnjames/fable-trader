"""Paper-only forward test of one Polymarket hypothesis. Places no real orders.

Hypothesis (fixed before collecting data, 2026-11-24): in thin markets (<$250k volume) ending within
4-30h, the underdog side priced 1-10c wins more often than its ask price implies, net of taker fees.
Primary test: sports. Weather and everything else are tracked separately as secondary.
Backtest basis: research/polymarket_calibration.py (suggestive, ~2 sigma, after many slices).
"""
