"""Tests for the trading fee model."""

import pytest


class TestGetFeePct:
    def test_crypto_fees(self):
        """Crypto tickers (-USD suffix) get 0.10% fee."""
        from api.server import _get_fee_pct
        assert _get_fee_pct("BTC-USD") == 0.10
        assert _get_fee_pct("ETH-USD") == 0.10
    def test_commodity_fees(self):
        """Commodity tickers get 0.10% fee."""
        from api.server import _get_fee_pct, MEME_TICKERS
        if MEME_TICKERS:
            ticker = MEME_TICKERS[0]
            assert _get_fee_pct(ticker) == 0.10

    def test_default_fees(self):
        """Unknown tickers get the default fee rate."""
        from api.server import _get_fee_pct, TRADING_FEES
        assert _get_fee_pct("UNKNOWN_TICKER_XYZ") == TRADING_FEES["default"]


class TestCalcFee:
    def test_fee_calculation(self):
        """_calc_fee returns correct dollar amount."""
        from api.server import _calc_fee
        # 10 units @ $100, Crypto fee 0.10% => $1.00
        fee = _calc_fee("BTC-USD", 10, 100.0)
        expected = round(10 * 100.0 * 0.10 / 100, 4)
        assert fee == expected
    def test_round_trip_fees(self, paper_portfolio):
        """Both buy and sell legs incur fees on a round trip."""
        initial_cash = paper_portfolio.cash

        paper_portfolio.place_order("BTC-USD", "BUY", 10, 50.0)
        paper_portfolio.place_order("BTC-USD", "SELL", 10, 50.0)

        # Cash should be reduced by total fees (buy + sell)
        trade = paper_portfolio.history[0]
        assert trade["fees"] > 0
        assert paper_portfolio.cash < initial_cash
