"""
Market Regime Engine — Replaces traditional Quadrant Engine.

Classifies the current crypto market regime using:
  - BTC market structure (CryptoCred: HH/HL vs LL/LH analysis)
  - Moving average positioning (50/200 SMA golden/death cross)
  - Sentiment analysis (Fear & Greed, news, social)
  - On-chain signals (exchange flows, whale activity)
  - GCR contrarian indicators (funding rates, consensus detection)

Regime determines which assets to favour/avoid and risk scaling.
"""

import pandas as pd
import numpy as np
from loguru import logger
from typing import Optional

from data.ingestion.market_data import MarketDataFetcher
from engines.sentiment_engine import SentimentEngine
from config.ruleset import MARKET_REGIMES
from config.assets import get_assets_by_regime


class RegimeEngine:
    """
    Classifies the crypto market regime and provides asset recommendations
    based on CryptoCred's market structure + GCR's contrarian framework.
    """

    REGIME_DESCRIPTIONS = {
        regime: data["description"]
        for regime, data in MARKET_REGIMES.items()
    }
    REGIME_DESCRIPTIONS["unknown"] = (
        "REGIME UNCLEAR: Insufficient data. Use neutral positioning. "
        "GCR: 'Reduce trading under unfavorable conditions.'"
    )

    def __init__(self):
        self.fetcher = MarketDataFetcher()
        self.sentiment = SentimentEngine()
        self._current_regime: Optional[str] = None
        self._btc_structure: Optional[dict] = None
        self._sentiment_summary: Optional[dict] = None
        self._regime_context: Optional[dict] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self) -> dict:
        """
        Full regime classification pipeline:
          1. Analyse BTC market structure (CryptoCred method)
          2. Check MA positioning (50/200 golden/death cross)
          3. Get sentiment summary
          4. Apply GCR contrarian filters
          5. Reconcile into a single regime verdict

        Returns full context dict for signal generation.
        """
        logger.info("Classifying crypto market regime...")

        # Step 1: BTC market structure analysis
        btc_structure = self._analyse_btc_structure()

        # Step 2: MA-based trend classification
        ma_regime = self._classify_by_ma()

        # Step 3: Sentiment
        try:
            self._sentiment_summary = self.sentiment.get_market_sentiment_summary()
            sentiment_regime = self._map_sentiment_to_regime(self._sentiment_summary)
        except Exception as e:
            logger.warning(f"Sentiment classification failed: {e}")
            sentiment_regime = "unknown"
            self._sentiment_summary = {}

        # Step 4: GCR contrarian overlay
        contrarian_signal = self._gcr_contrarian_check(self._sentiment_summary)

        # Step 5: Reconcile — structure is primary, MA is secondary, sentiment is tie-breaker
        structure_regime = btc_structure.get("regime", "unknown")

        if structure_regime != "unknown":
            final_regime = structure_regime
        elif ma_regime != "unknown":
            final_regime = ma_regime
        elif sentiment_regime != "unknown":
            final_regime = sentiment_regime
        else:
            final_regime = "ranging"

        # GCR override: if contrarian signal is strong, it overrides
        if contrarian_signal.get("override"):
            logger.warning(f"GCR CONTRARIAN OVERRIDE: {contrarian_signal['reason']}")
            final_regime = contrarian_signal["suggested_regime"]

        self._current_regime = final_regime
        self._btc_structure = btc_structure

        regime_data = MARKET_REGIMES.get(final_regime, {})
        result = {
            "regime": final_regime,
            "description": self.REGIME_DESCRIPTIONS.get(final_regime, ""),
            "bias": regime_data.get("bias", "neutral"),
            "risk_scaling": regime_data.get("risk_scaling", "minimal"),
            "structure_regime": structure_regime,
            "ma_regime": ma_regime,
            "sentiment_regime": sentiment_regime,
            "btc_structure": btc_structure,
            "contrarian_signal": contrarian_signal,
            "sentiment_summary": self._sentiment_summary,
            "favoured_types": regime_data.get("favored", []),
            "avoid_types": regime_data.get("avoid", []),
            "recommended_tickers": list(get_assets_by_regime(final_regime).keys()),
        }

        self._regime_context = result
        logger.info(
            f"Regime classified: {final_regime} "
            f"(structure={structure_regime}, ma={ma_regime}, "
            f"sentiment={sentiment_regime}, contrarian={contrarian_signal.get('signal', 'none')})"
        )
        return result

    def get_asset_regime_fit(self, ticker: str, asset_info: dict) -> dict:
        """
        Score how well a single asset fits the current regime.

        Returns:
            {"fit": "strong|moderate|weak|avoid", "score": 0-100, "reason": str}
        """
        if self._current_regime is None:
            return {"fit": "unknown", "score": 50, "reason": "Regime not yet classified."}

        asset_bias = asset_info.get("regime_bias", "unknown")
        asset_type = asset_info.get("type", "unknown")
        current = self._current_regime
        regime_data = MARKET_REGIMES.get(current, {})
        favored_types = regime_data.get("favored", [])
        avoid_types = regime_data.get("avoid", [])

        # All-weather assets (BTC, ETH) always moderate+
        if asset_bias == "all_weather":
            fit, score = "strong", 85
            reason = f"{ticker} is an all-weather core holding."
        elif asset_bias == current:
            fit, score = "strong", 90
            reason = f"{ticker} is directly aligned with {current} regime."
        elif any(ft in asset_type for ft in favored_types):
            fit, score = "moderate", 65
            reason = f"{ticker} type ({asset_type}) is favoured in {current}."
        elif any(av in asset_type for av in avoid_types):
            fit, score = "avoid", 15
            reason = f"{ticker} type ({asset_type}) is unfavoured in {current}."
        else:
            fit, score = "weak", 40
            reason = f"{ticker} has neutral regime alignment for {current}."

        return {"fit": fit, "score": score, "reason": reason}

    def get_current_regime(self) -> Optional[str]:
        return self._current_regime

    def get_regime_context(self) -> Optional[dict]:
        return self._regime_context

    def get_narrative(self) -> str:
        """Human-readable description of the current market regime."""
        if not self._current_regime:
            return "Market regime not yet determined. Run classify() first."

        btc = self._btc_structure or {}
        sentiment = self._sentiment_summary or {}

        lines = [
            f"=== CRYPTO REGIME ENGINE — CURRENT STATE ===",
            f"Regime: {self._current_regime.upper().replace('_', ' ')}",
            f"",
            f"BTC Trend: {btc.get('trend', 'N/A')}",
            f"BTC Structure: {btc.get('structure', 'N/A')}",
            f"BTC vs 200 SMA: {'Above' if btc.get('above_200sma') else 'Below'}",
            f"BTC vs 50 SMA: {'Above' if btc.get('above_50sma') else 'Below'}",
            f"Golden Cross: {btc.get('golden_cross', 'N/A')}",
            f"",
            f"Market Sentiment: {sentiment.get('dominant_sentiment', 'N/A')}",
            f"Fear & Greed: {sentiment.get('fear_greed_index', 'N/A')}",
            f"",
            self.REGIME_DESCRIPTIONS.get(self._current_regime, ""),
        ]
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private — BTC Market Structure (CryptoCred Method)
    # ------------------------------------------------------------------

    def _analyse_btc_structure(self) -> dict:
        """
        CryptoCred market structure analysis on BTC.
        Identifies higher highs/lows vs lower lows/highs.
        """
        try:
            df = self.fetcher.get_historical_data("BTC-USD", period="1y", interval="1d")
            if df.empty or len(df) < 50:
                return {"regime": "unknown", "structure": "insufficient_data"}
        except Exception as e:
            logger.error(f"BTC data fetch failed: {e}")
            return {"regime": "unknown", "structure": "fetch_error"}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        # Swing high/low detection (20-bar lookback)
        swing_highs = self._find_swing_points(high, lookback=20, swing_type="high")
        swing_lows = self._find_swing_points(low, lookback=20, swing_type="low")

        # Determine structure
        structure = "unknown"
        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]  # Higher high
            hl = swing_lows[-1] > swing_lows[-2]     # Higher low
            ll = swing_lows[-1] < swing_lows[-2]     # Lower low
            lh = swing_highs[-1] < swing_highs[-2]   # Lower high

            if hh and hl:
                structure = "bullish"
            elif ll and lh:
                structure = "bearish"
            elif hh and not hl:
                structure = "weakening_bull"
            elif ll and not lh:
                structure = "weakening_bear"
            else:
                structure = "ranging"

        # MA analysis
        latest = float(close.iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])
        sma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else sma50
        above_50 = latest > sma50
        above_200 = latest > sma200
        golden_cross = sma50 > sma200

        # Trend classification
        if latest > sma50 > sma200:
            trend = "strong_uptrend"
        elif latest > sma50 and not golden_cross:
            trend = "recovering"
        elif latest < sma50 < sma200:
            trend = "strong_downtrend"
        elif latest < sma50 and golden_cross:
            trend = "weakening"
        else:
            trend = "sideways"

        # Map to regime
        if structure == "bullish" and trend in ("strong_uptrend", "recovering"):
            regime = "bull_trend"
        elif structure == "bearish" and trend in ("strong_downtrend",):
            regime = "bear_trend"
        elif structure in ("weakening_bear", "ranging") and trend == "recovering":
            regime = "accumulation"
        elif structure in ("weakening_bull",) and trend == "weakening":
            regime = "distribution"
        elif structure == "ranging":
            regime = "ranging"
        else:
            regime = "unknown"

        return {
            "regime": regime,
            "structure": structure,
            "trend": trend,
            "above_50sma": above_50,
            "above_200sma": above_200,
            "golden_cross": golden_cross,
            "btc_price": latest,
            "sma50": round(sma50, 2),
            "sma200": round(sma200, 2),
        }

    def _find_swing_points(self, series: pd.Series, lookback: int = 20, swing_type: str = "high") -> list[float]:
        """Find swing highs or swing lows in a price series."""
        swings = []
        values = series.values
        for i in range(lookback, len(values) - lookback):
            window = values[i - lookback:i + lookback + 1]
            if swing_type == "high" and values[i] == window.max():
                swings.append(float(values[i]))
            elif swing_type == "low" and values[i] == window.min():
                swings.append(float(values[i]))
        return swings

    def _classify_by_ma(self) -> str:
        """Simple MA-based regime classification as fallback."""
        try:
            df = self.fetcher.get_historical_data("BTC-USD", period="1y", interval="1d")
            if df.empty or len(df) < 200:
                return "unknown"

            close = df["Close"]
            latest = float(close.iloc[-1])
            sma50 = float(close.rolling(50).mean().iloc[-1])
            sma200 = float(close.rolling(200).mean().iloc[-1])

            if latest > sma50 > sma200:
                return "bull_trend"
            elif latest < sma50 < sma200:
                return "bear_trend"
            else:
                return "ranging"
        except Exception:
            return "unknown"

    def _map_sentiment_to_regime(self, sentiment: dict) -> str:
        """Map sentiment data to a regime suggestion."""
        fear_greed = sentiment.get("fear_greed_index", 50)
        dominant = sentiment.get("dominant_sentiment", "neutral")

        if fear_greed <= 20:
            return "accumulation"  # Extreme fear = GCR buy signal
        elif fear_greed >= 80:
            return "distribution"  # Extreme greed = GCR sell signal
        elif dominant == "bullish" and fear_greed > 55:
            return "bull_trend"
        elif dominant == "bearish" and fear_greed < 45:
            return "bear_trend"
        return "unknown"

    def _gcr_contrarian_check(self, sentiment: dict) -> dict:
        """
        GCR's Tree of Life: bet against consensus when sentiment is extreme.
        Returns override signal if consensus is overwhelming.
        """
        fear_greed = sentiment.get("fear_greed_index", 50)

        # Extreme fear — GCR contrarian buy
        if fear_greed <= 10:
            return {
                "signal": "extreme_fear_buy",
                "override": True,
                "suggested_regime": "accumulation",
                "reason": (
                    "GCR PEARL: Extreme fear (F&G={fear_greed}). "
                    "'Take on more risk when the market starts turning the corner.'"
                ),
            }

        # Extreme greed — GCR contrarian sell
        if fear_greed >= 90:
            return {
                "signal": "extreme_greed_sell",
                "override": True,
                "suggested_regime": "distribution",
                "reason": (
                    "GCR PEARL: Extreme greed (F&G={fear_greed}). "
                    "'When retail imagine catalysts will enrich them, market makers "
                    "use the final liquidity to offload positions.'"
                ),
            }

        return {"signal": "none", "override": False}
