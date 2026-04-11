"""
Signal Generator — CryptoCred TA + GCR Contrarian Crypto Signals.

Combines:
  - CryptoCred: Market structure, directional bias, S/R, entry triggers
  - CryptoCred: RSI, MACD, Bollinger Bands, Fibonacci, Ichimoku, ATR
  - GCR: Contrarian sentiment inversion, consensus fading
  - Regime alignment (replaces market regime)
  - Correlation gate (portfolio diversification)

Each signal is classified: BUY / SELL / SHORT / HOLD with confidence score.
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime
from loguru import logger
from typing import Optional

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False
    logger.warning("ta library not available — using manual indicator calculations.")

from data.ingestion.market_data import MarketDataFetcher
from config.assets import get_all_assets
from config.ruleset import (
    CONFIDENCE_WEIGHTS,
    DIRECTIONAL_BIAS_RULES,
    INDICATOR_RULES,
    RISK_MANAGEMENT_RULES,
    GCR_CONTRARIAN_RULES,
    ENTRY_RULES,
    EXIT_RULES,
)


@dataclass
class TradeSignal:
    """A single trade signal with full CryptoCred + GCR justification."""
    ticker: str
    action: str          # "BUY" | "SELL" | "SHORT" | "COVER" | "HOLD"
    direction: str       # "long" | "short" | "neutral"
    confidence: float    # 0.0 - 1.0
    price: float
    timestamp: str

    # Context — regime replaces quadrant
    quadrant: str = ""          # regime name (kept as 'quadrant' for API compat)
    quadrant_fit: str = ""      # regime fit (kept for API compat)
    sentiment_score: float = 0.0
    sentiment_label: str = "neutral"
    conflict_risk: bool = False

    # CryptoCred TA signals
    rsi: float = 0.0
    macd_signal: str = ""
    bb_position: str = ""
    trend: str = ""
    atr: float = 0.0

    # CryptoCred directional bias
    directional_bias: str = ""  # "bullish" | "bearish" | "neutral"
    market_structure: str = ""  # "HH/HL" | "LL/LH" | "ranging"

    # Risk metrics
    suggested_stop_loss: float = 0.0
    suggested_take_profit: float = 0.0
    risk_reward_ratio: float = 0.0
    position_size_pct: float = 0.0

    # GCR contrarian flag
    gcr_contrarian: bool = False
    gcr_signal: str = ""

    # Reasons (replaces options_strategy for crypto)
    options_strategy: Optional[str] = None  # Kept for API compat
    reasons: list[str] = field(default_factory=list)


class SignalGenerator:
    """
    Generates crypto signals using CryptoCred TA + GCR contrarian framework.
    Applies Ultra Ruleset with Ultra Ruleset as the filter layer.
    """

    def __init__(self, regime_engine=None, sentiment_engine=None, correlation_engine=None):
        self.fetcher = MarketDataFetcher()
        self.regime_engine = regime_engine
        self.sentiment_engine = sentiment_engine
        self.correlation_engine = correlation_engine
        self._assets = get_all_assets()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate_signal(
        self,
        ticker: str,
        current_portfolio: Optional[list[str]] = None,
        interval: str = "1d",
    ) -> Optional[TradeSignal]:
        """Generate a trade signal for a single crypto asset."""
        asset_info = self._assets.get(ticker, {})

        # Fetch price data
        df = self.fetcher.get_historical_data(ticker, period="1y", interval=interval)
        if df.empty or len(df) < 50:
            logger.debug(f"Insufficient data for {ticker}")
            return None

        latest_price = float(df["Close"].iloc[-1])

        # CryptoCred: Technical analysis
        tech = self._compute_technicals(df)

        # CryptoCred: Directional bias
        bias = self._compute_directional_bias(df, tech)

        # CryptoCred: Market structure
        structure = self._analyse_market_structure(df)

        # Regime alignment (replaces quadrant)
        regime_fit = "unknown"
        current_regime = "unknown"
        if self.regime_engine and self.regime_engine.get_current_regime():
            fit_result = self.regime_engine.get_asset_regime_fit(ticker, asset_info)
            regime_fit = fit_result.get("fit", "unknown")
            current_regime = self.regime_engine.get_current_regime()
            if regime_fit == "avoid":
                logger.debug(f"Skipping {ticker}: regime says AVOID.")
                return None

        # Sentiment
        sentiment_score = 0.0
        sentiment_label = "neutral"
        if self.sentiment_engine:
            try:
                sent = self.sentiment_engine.get_ticker_sentiment(ticker)
                sentiment_score = sent.get("score", 0.0)
                sentiment_label = sent.get("sentiment", "neutral")
            except Exception:
                pass

        # Determine action using Ultra Ruleset scoring
        action, confidence, reasons, gcr_contrarian, gcr_signal = self._determine_action(
            tech, bias, structure, sentiment_score, regime_fit, asset_info
        )

        if action == "HOLD" and confidence < 0.55:
            return None

        # Correlation gate
        if (
            current_portfolio
            and self.correlation_engine
            and action in ("BUY", "COVER")
        ):
            if self.correlation_engine.would_breach_threshold(current_portfolio, ticker):
                reasons.append("BLOCKED: Would breach portfolio correlation threshold.")
                action = "HOLD"
                confidence = 0.0

        # CryptoCred: ATR-based stop loss (2x ATR from entry)
        atr = tech.get("atr", latest_price * 0.03)  # 3% default for crypto volatility
        stop_loss = (
            latest_price - 2 * atr if action in ("BUY", "COVER")
            else latest_price + 2 * atr
        )
        # Targets: 3x ATR for 1.5:1 R:R minimum
        take_profit = (
            latest_price + 3 * atr if action in ("BUY", "COVER")
            else latest_price - 3 * atr
        )
        rr = abs(take_profit - latest_price) / abs(latest_price - stop_loss) if abs(latest_price - stop_loss) > 0 else 0

        return TradeSignal(
            ticker=ticker,
            action=action,
            direction="long" if action in ("BUY", "COVER") else "short" if action == "SHORT" else "neutral",
            confidence=round(confidence, 4),
            price=latest_price,
            timestamp=datetime.utcnow().isoformat(),
            quadrant=current_regime,
            quadrant_fit=regime_fit,
            sentiment_score=sentiment_score,
            sentiment_label=sentiment_label,
            rsi=tech.get("rsi", 0),
            macd_signal=tech.get("macd_signal", ""),
            bb_position=tech.get("bb_position", ""),
            trend=tech.get("trend", ""),
            atr=round(atr, 4),
            directional_bias=bias,
            market_structure=structure,
            suggested_stop_loss=round(stop_loss, 4),
            suggested_take_profit=round(take_profit, 4),
            risk_reward_ratio=round(rr, 2),
            position_size_pct=round(self._kelly_position_size(confidence, rr), 2),
            gcr_contrarian=gcr_contrarian,
            gcr_signal=gcr_signal,
            reasons=reasons,
        )

    def scan_universe(
        self,
        current_portfolio: Optional[list[str]] = None,
        top_n: int = 10,
    ) -> list[TradeSignal]:
        """Scan all crypto assets and return top N signals by confidence."""
        signals = []
        for ticker in self._assets:
            try:
                signal = self.generate_signal(ticker, current_portfolio)
                if signal and signal.action != "HOLD":
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Signal generation failed for {ticker}: {e}")

        signals.sort(key=lambda s: s.confidence, reverse=True)
        logger.info(f"Universe scan complete: {len(signals)} actionable signals found.")
        return signals[:top_n]

    def suggest_new_opportunities(self, exclude: Optional[list[str]] = None) -> list[TradeSignal]:
        """Identify crypto assets NOT in portfolio with strong signals."""
        exclude = exclude or []
        candidates = [t for t in self._assets if t not in exclude]

        signals = []
        for ticker in candidates:
            try:
                signal = self.generate_signal(ticker, exclude)
                if signal and signal.confidence >= 0.65 and signal.action != "HOLD":
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"Error scanning {ticker}: {e}")

        signals.sort(key=lambda s: s.confidence * s.risk_reward_ratio, reverse=True)
        return signals[:5]

    # ------------------------------------------------------------------
    # CryptoCred: Directional Bias
    # ------------------------------------------------------------------

    def _compute_directional_bias(self, df: pd.DataFrame, tech: dict) -> str:
        """
        CryptoCred directional bias using multiple tools:
        1. MA crossover (50/200)
        2. Market structure (HH/HL vs LL/LH)
        3. Price relative to key MAs
        """
        close = df["Close"]
        latest = float(close.iloc[-1])

        # MA-based bias
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50

        ma_bias = "neutral"
        if latest > ma50 > ma200:
            ma_bias = "bullish"
        elif latest < ma50 < ma200:
            ma_bias = "bearish"

        # Trend confirmation
        trend = tech.get("trend", "sideways")
        if trend == "uptrend" and ma_bias == "bullish":
            return "bullish"
        elif trend == "downtrend" and ma_bias == "bearish":
            return "bearish"
        elif ma_bias != "neutral":
            return ma_bias

        return "neutral"

    # ------------------------------------------------------------------
    # CryptoCred: Market Structure
    # ------------------------------------------------------------------

    def _analyse_market_structure(self, df: pd.DataFrame) -> str:
        """CryptoCred: Identify HH/HL (bullish) vs LL/LH (bearish) structure."""
        high = df["High"].values
        low = df["Low"].values

        if len(high) < 40:
            return "insufficient_data"

        # Find recent swing highs and lows (10-bar lookback)
        swing_highs = []
        swing_lows = []
        lookback = 10

        for i in range(lookback, len(high) - lookback):
            window_h = high[i - lookback:i + lookback + 1]
            window_l = low[i - lookback:i + lookback + 1]
            if high[i] == window_h.max():
                swing_highs.append(float(high[i]))
            if low[i] == window_l.min():
                swing_lows.append(float(low[i]))

        if len(swing_highs) >= 2 and len(swing_lows) >= 2:
            hh = swing_highs[-1] > swing_highs[-2]
            hl = swing_lows[-1] > swing_lows[-2]
            ll = swing_lows[-1] < swing_lows[-2]
            lh = swing_highs[-1] < swing_highs[-2]

            if hh and hl:
                return "HH/HL"  # Bullish structure
            elif ll and lh:
                return "LL/LH"  # Bearish structure

        return "ranging"

    # ------------------------------------------------------------------
    # Technicals (same as 0xrex but with crypto adjustments)
    # ------------------------------------------------------------------

    def _compute_technicals(self, df: pd.DataFrame) -> dict:
        """Compute all technical indicators per CryptoCred framework."""
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        result = {}

        # RSI (CryptoCred: confirmation tool, not standalone)
        result["rsi"] = self._rsi(close, 14)

        # RSI Divergence detection
        result["rsi_divergence"] = self._detect_rsi_divergence(close, result["rsi"])

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        result["macd"] = float(macd.iloc[-1])
        result["macd_signal"] = "bullish" if macd.iloc[-1] > signal.iloc[-1] else "bearish"
        result["macd_crossover"] = (
            macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] <= signal.iloc[-2]
        )
        result["macd_histogram"] = float(macd.iloc[-1] - signal.iloc[-1])

        # Bollinger Bands
        sma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper = sma20 + 2 * std20
        lower = sma20 - 2 * std20
        latest = float(close.iloc[-1])
        if latest > upper.iloc[-1]:
            result["bb_position"] = "above_upper"
        elif latest < lower.iloc[-1]:
            result["bb_position"] = "below_lower"
        else:
            result["bb_position"] = "mid"
        result["bb_pct"] = float(
            (latest - lower.iloc[-1]) / (upper.iloc[-1] - lower.iloc[-1] + 1e-9)
        )
        # BB squeeze detection
        bb_width = (upper - lower) / sma20
        result["bb_squeeze"] = float(bb_width.iloc[-1]) < float(bb_width.rolling(120).mean().iloc[-1]) * 0.5

        # ATR
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        result["atr"] = float(tr.rolling(14).mean().iloc[-1])

        # Trend: 50/200 MA crossover
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else ma50
        if close.iloc[-1] > ma50 > ma200:
            result["trend"] = "uptrend"
        elif close.iloc[-1] < ma50 < ma200:
            result["trend"] = "downtrend"
        else:
            result["trend"] = "sideways"

        # EMA 9/21 for fast trend (CryptoCred)
        ema9 = float(close.ewm(span=9).mean().iloc[-1])
        ema21 = float(close.ewm(span=21).mean().iloc[-1])
        result["ema9_above_21"] = ema9 > ema21

        # Volume confirmation
        avg_vol = float(volume.rolling(20).mean().iloc[-1])
        result["volume_surge"] = float(volume.iloc[-1]) > avg_vol * 1.5

        # Momentum (Rate of Change 10)
        result["roc_10"] = float((close.iloc[-1] / close.iloc[-10] - 1) * 100)

        # Fibonacci: distance from recent swing high/low
        period = min(60, len(close))
        recent_high = float(close.tail(period).max())
        recent_low = float(close.tail(period).min())
        if recent_high != recent_low:
            fib_pct = (latest - recent_low) / (recent_high - recent_low)
            result["fib_retracement"] = round(1 - fib_pct, 3)  # 0 = at high, 1 = at low
            result["in_golden_zone"] = 0.618 <= result["fib_retracement"] <= 0.786
        else:
            result["fib_retracement"] = 0.5
            result["in_golden_zone"] = False

        # Distance from highs/lows
        period = min(365, len(close))
        result["pct_from_high"] = float(
            (close.iloc[-1] / close.tail(period).max() - 1) * 100
        )
        result["pct_from_low"] = float(
            (close.iloc[-1] / close.tail(period).min() - 1) * 100
        )

        return result

    def _rsi(self, close: pd.Series, period: int = 14) -> float:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / (loss + 1e-9)
        rsi = 100 - (100 / (1 + rs))
        return round(float(rsi.iloc[-1]), 2)

    def _detect_rsi_divergence(self, close: pd.Series, current_rsi: float) -> str:
        """Detect RSI divergence (CryptoCred: high-probability reversal signal)."""
        if len(close) < 30:
            return "none"

        # Compare last two swing lows/highs in price vs RSI
        rsi_series = self._rsi_series(close, 14)
        if rsi_series is None or len(rsi_series) < 20:
            return "none"

        # Simplified: compare current vs 14-bar ago
        price_now = float(close.iloc[-1])
        price_prev = float(close.iloc[-14])
        rsi_now = current_rsi
        rsi_prev = float(rsi_series.iloc[-14])

        if price_now < price_prev and rsi_now > rsi_prev:
            return "bullish"  # Price lower low, RSI higher low
        elif price_now > price_prev and rsi_now < rsi_prev:
            return "bearish"  # Price higher high, RSI lower high

        return "none"

    def _rsi_series(self, close: pd.Series, period: int = 14) -> Optional[pd.Series]:
        delta = close.diff()
        gain = delta.clip(lower=0).rolling(period).mean()
        loss = (-delta.clip(upper=0)).rolling(period).mean()
        rs = gain / (loss + 1e-9)
        return 100 - (100 / (1 + rs))

    # ------------------------------------------------------------------
    # Ultra Ruleset Scoring Engine
    # ------------------------------------------------------------------

    def _determine_action(
        self,
        tech: dict,
        bias: str,
        structure: str,
        sentiment_score: float,
        regime_fit: str,
        asset_info: dict,
    ) -> tuple[str, float, list[str], bool, str]:
        """
        Score using CryptoCred TA + GCR contrarian weights.
        Returns (action, confidence, reasons, gcr_contrarian, gcr_signal).
        """
        reasons = []
        score = 0.0
        gcr_contrarian = False
        gcr_signal = ""
        W = CONFIDENCE_WEIGHTS

        rsi = tech.get("rsi", 50)
        macd_signal = tech.get("macd_signal", "")
        bb_pos = tech.get("bb_position", "mid")
        trend = tech.get("trend", "sideways")
        roc = tech.get("roc_10", 0)
        volume_surge = tech.get("volume_surge", False)
        macd_crossover = tech.get("macd_crossover", False)
        rsi_div = tech.get("rsi_divergence", "none")
        in_golden = tech.get("in_golden_zone", False)
        bb_squeeze = tech.get("bb_squeeze", False)
        ema9_above = tech.get("ema9_above_21", False)

        # ── CryptoCred: Market Structure ──
        if structure == "HH/HL":
            score += W["market_structure_alignment"]
            reasons.append("CryptoCred: Bullish market structure (HH/HL).")
        elif structure == "LL/LH":
            score -= W["market_structure_alignment"]
            reasons.append("CryptoCred: Bearish market structure (LL/LH).")

        # ── CryptoCred: Directional Bias ──
        if bias == "bullish":
            score += W["directional_bias_match"]
            reasons.append("CryptoCred: Bullish directional bias — dips for buying.")
        elif bias == "bearish":
            score -= W["directional_bias_match"]
            reasons.append("CryptoCred: Bearish directional bias — rallies for selling.")

        # ── CryptoCred: RSI ──
        if rsi < INDICATOR_RULES["rsi"]["oversold"]:
            score += 2.0
            reasons.append(f"RSI oversold ({rsi:.1f}) — CryptoCred reversal signal.")
        elif rsi > INDICATOR_RULES["rsi"]["overbought"]:
            score -= 2.0
            reasons.append(f"RSI overbought ({rsi:.1f}) — CryptoCred reversal signal.")
        elif rsi < 45:
            score += 0.5
        elif rsi > 55:
            score -= 0.5

        # RSI Divergence (CryptoCred: high-probability)
        if rsi_div == "bullish":
            score += 1.5
            reasons.append("CryptoCred: Bullish RSI divergence — reversal signal.")
        elif rsi_div == "bearish":
            score -= 1.5
            reasons.append("CryptoCred: Bearish RSI divergence — reversal signal.")

        # ── CryptoCred: MACD ──
        if macd_signal == "bullish":
            score += 1.5
            reasons.append("MACD above signal line — bullish momentum.")
        else:
            score -= 1.5
            reasons.append("MACD below signal line — bearish momentum.")

        if macd_crossover:
            score += 1.0
            reasons.append("Fresh MACD bullish crossover — CryptoCred entry trigger.")

        # ── CryptoCred: Bollinger Bands ──
        if bb_pos == "below_lower":
            score += 1.5
            reasons.append("Price below lower BB — oversold condition.")
        elif bb_pos == "above_upper":
            score -= 1.5
            reasons.append("Price above upper BB — overbought condition.")

        if bb_squeeze:
            reasons.append("CryptoCred: BB squeeze detected — impending breakout.")

        # ── CryptoCred: Fibonacci Golden Zone ──
        if in_golden:
            score += W["fibonacci_zone"]
            reasons.append("CryptoCred: Price in Fibonacci golden zone (0.618-0.786).")

        # ── CryptoCred: Trend ──
        if trend == "uptrend":
            score += 2.0
            reasons.append("Confirmed uptrend (price > MA50 > MA200).")
        elif trend == "downtrend":
            score -= 2.0
            reasons.append("Confirmed downtrend (price < MA50 < MA200).")

        # Fast EMA confirmation
        if ema9_above and trend == "uptrend":
            score += 0.5
            reasons.append("EMA 9 above EMA 21 — fast momentum confirms.")

        # ── CryptoCred: Volume ──
        if volume_surge:
            score = score * 1.2
            reasons.append("Volume surge confirms move — CryptoCred confirmation.")
        elif not volume_surge and abs(score) > 3:
            score += W["low_volume_penalty"]
            reasons.append("WARNING: Strong signal but NO volume confirmation.")

        # ── Sentiment ──
        score += sentiment_score * 2.0
        if abs(sentiment_score) > 0.1:
            sentiment_dir = "positive" if sentiment_score > 0 else "negative"
            reasons.append(f"Crypto sentiment is {sentiment_dir} ({sentiment_score:+.3f}).")

        # ── Regime fit (replaces quadrant) ──
        regime_boost = {"strong": 1.5, "moderate": 0.5, "weak": -0.5, "avoid": -3.0}
        score += regime_boost.get(regime_fit, 0)
        if regime_fit in ("strong", "moderate"):
            reasons.append(f"Asset has {regime_fit} regime alignment.")

        # ── GCR Contrarian: Sentiment Inversion ──
        if sentiment_score < -0.5:
            # Extreme negative sentiment = GCR contrarian buy opportunity
            gcr_boost = W["sentiment_contrarian"] * 0.5
            score += gcr_boost
            gcr_contrarian = True
            gcr_signal = "contrarian_buy"
            reasons.append(
                "GCR PEARL: Extreme negative sentiment — contrarian buy opportunity. "
                "'Real opportunities are hidden in the opposite direction of consensus.'"
            )
        elif sentiment_score > 0.5:
            # Extreme positive sentiment = GCR contrarian sell warning
            gcr_penalty = W["consensus_trade_penalty"]
            score += gcr_penalty
            gcr_contrarian = True
            gcr_signal = "contrarian_sell"
            reasons.append(
                "GCR WARNING: Extreme positive consensus — 'When retail imagine catalysts "
                "will enrich them, market makers use the final liquidity to offload.'"
            )

        # ── Momentum ──
        if roc > 5:
            score += 0.5
        elif roc < -5:
            score -= 0.5

        # ── CryptoCred: Bias alignment penalty ──
        # If trading AGAINST directional bias, apply heavy penalty
        if bias == "bearish" and score > 0:
            score += W["against_bias_penalty"]
            reasons.append("CryptoCred: Trading against bearish bias — confidence reduced.")
        elif bias == "bullish" and score < 0:
            score += abs(W["against_bias_penalty"])  # This reduces the negative score
            reasons.append("CryptoCred: Trading against bullish bias — confidence reduced.")

        # Convert score to action
        confidence = min(abs(score) / 12.0, 1.0)
        if score >= 3.0:
            action = "BUY"
        elif score <= -3.0:
            action = "SHORT"
        elif score >= 1.5:
            action = "BUY"
            confidence *= 0.8
        elif score <= -1.5:
            action = "SELL"
            confidence *= 0.8
        else:
            action = "HOLD"
            confidence = 0.0

        return action, confidence, reasons, gcr_contrarian, gcr_signal

    def _kelly_position_size(self, confidence: float, rr: float) -> float:
        """
        Kelly Criterion (half-Kelly for safety) per CryptoCred risk management.
        Capped at max_pos_size from Ultra Ruleset.
        """
        max_size = RISK_MANAGEMENT_RULES["position_sizing"]["kelly_cap_pct"]
        p = confidence
        q = 1 - p
        b = max(rr, 0.1)
        kelly = (p * b - q) / b
        half_kelly = max(kelly * 0.5, 0.01)
        return min(half_kelly * 100, max_size)
