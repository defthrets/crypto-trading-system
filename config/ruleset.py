"""
ULTRA RULESET — Unified Trading Framework
Synthesized from CryptoCred's TA Manual + GCR's Pearls of Wisdom.

This replaces traditional All Weather / Economic Machine principles
with a crypto-native methodology combining:
  - CryptoCred: Market structure, directional bias, S/R, entries, TA discipline
  - GCR: Contrarian psychology, reflexivity, cycle timing, risk scaling

The ruleset governs every decision the autonomous agent makes.
"""

# ═══════════════════════════════════════════════════════════════
#  SECTION 1 — MARKET REGIME CLASSIFICATION (replaces traditional quadrants)
# ═══════════════════════════════════════════════════════════════

MARKET_REGIMES = {
    "bull_trend": {
        "description": (
            "BULL TREND: Higher highs, higher lows confirmed on weekly. "
            "BTC dominance stable or rising. Altcoins rotating. "
            "Dips are for buying — resistance anticipated to break."
        ),
        "bias": "long",
        "favored": ["large_cap", "layer1", "defi_blue_chip", "meme_momentum"],
        "avoid": ["stablecoins_heavy", "short_positions"],
        "risk_scaling": "aggressive",  # GCR: take more risk at cycle turns
    },
    "bear_trend": {
        "description": (
            "BEAR TREND: Lower lows, lower highs on weekly. "
            "Rallies are for selling — support anticipated to fail. "
            "Capital preservation mode. GCR: 'Altcoins cannot survive independently.'"
        ),
        "bias": "short",
        "favored": ["btc_only", "stablecoins", "short_positions"],
        "avoid": ["altcoins", "leverage_longs", "low_cap"],
        "risk_scaling": "defensive",
    },
    "accumulation": {
        "description": (
            "ACCUMULATION: Market bottoming. Sentiment at max fear. "
            "GCR PEARL: 'Take on more risk when the market starts turning the corner.' "
            "CryptoCred: Watch for market structure shifts — first HH on daily."
        ),
        "bias": "cautious_long",
        "favored": ["btc", "eth", "battle_tested_l1", "contrarian_plays"],
        "avoid": ["leverage", "low_liquidity", "new_launches"],
        "risk_scaling": "contrarian_aggressive",  # GCR's signature move
    },
    "distribution": {
        "description": (
            "DISTRIBUTION: Market topping. Euphoria signals everywhere. "
            "GCR: 'When retail imagine catalysts will enrich them, market makers "
            "use the final liquidity to offload positions.' Scale out aggressively."
        ),
        "bias": "cautious_short",
        "favored": ["stablecoins", "btc_hedge", "short_alts"],
        "avoid": ["new_positions", "leverage_longs", "meme_coins"],
        "risk_scaling": "defensive_exit",
    },
    "ranging": {
        "description": (
            "RANGING: No clear trend. CryptoCred: Directional bias tools produce "
            "false positives frequently in ranging markets. Trade S/R levels only."
        ),
        "bias": "neutral",
        "favored": ["range_plays", "mean_reversion", "stablecoins"],
        "avoid": ["trend_following", "breakout_chasing"],
        "risk_scaling": "minimal",
    },
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 2 — DIRECTIONAL BIAS RULES (CryptoCred Core)
# ═══════════════════════════════════════════════════════════════

DIRECTIONAL_BIAS_RULES = {
    "primary_rule": (
        "NEVER trade without a directional bias. A bias is an explicit expectation "
        "of market direction functioning as a probability enhancer."
    ),
    "bullish_bias": {
        "rule": "In bullish bias: dips are for buying, resistance anticipated to fail.",
        "entry": "Buy pullbacks to support, broken resistance retests, and MA bounces.",
        "avoid": "Do NOT short in a bullish bias unless stringent counter-trend criteria met.",
    },
    "bearish_bias": {
        "rule": "In bearish bias: rallies are for selling, support anticipated to fail.",
        "entry": "Sell rallies into resistance, broken support retests, and MA rejections.",
        "avoid": "Do NOT long in a bearish bias unless stringent counter-trend criteria met.",
    },
    "bias_tools": [
        "MA crossover (50/200 for swing, 9/21 for intraday)",
        "Market structure (HH/HL = bullish, LL/LH = bearish)",
        "S/R structure breaks (close above resistance = bullish flip)",
        "Failed flip patterns (broken support failing as resistance = bullish)",
        "Price relative to key MAs (above 200 EMA = bullish context)",
    ],
    "bias_invalidation": (
        "Bias is invalidated when market structure shifts on the timeframe "
        "used to establish the bias. E.g., a bearish break of structure on "
        "the daily chart invalidates a daily bullish bias."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 3 — MARKET STRUCTURE RULES (CryptoCred Core)
# ═══════════════════════════════════════════════════════════════

MARKET_STRUCTURE_RULES = {
    "definition": (
        "Market structure is the sequence of highs and lows. "
        "Bullish = higher highs + higher lows. Bearish = lower lows + lower highs."
    ),
    "break_of_structure": {
        "bullish_bos": "Price makes a higher high, breaking above the previous swing high.",
        "bearish_bos": "Price makes a lower low, breaking below the previous swing low.",
        "confirmation": "Use significant swing points only. Obvious breaks work best.",
    },
    "multi_timeframe": {
        "rule": "Always analyse structure top-down: Weekly → Daily → 4H → 1H.",
        "priority": "Higher timeframe structure overrules lower timeframe signals.",
        "targets": "Derive targets from HTF charts, not intraday trouble areas.",
    },
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 4 — ENTRY & EXIT RULES (CryptoCred + GCR)
# ═══════════════════════════════════════════════════════════════

ENTRY_RULES = {
    "entry_triggers": [
        "Breakout above resistance with volume confirmation",
        "Pullback to support with bullish candlestick reversal pattern",
        "Retest of broken level (S/R flip) with holding confirmation",
        "MA bounce in trending market (21 EMA in strong trend, 50 SMA moderate)",
        "RSI divergence at key S/R level",
        "MACD bullish crossover aligned with directional bias",
        "Fibonacci 0.618-0.786 retracement in trending market",
    ],
    "entry_filters": {
        "bias_alignment": "Entry MUST align with directional bias or have exceptional R:R (3:1+).",
        "volume_confirmation": "Breakouts require volume surge > 1.5x 20-period average.",
        "multi_tf_confluence": "Entry on LTF must align with HTF structure and bias.",
        "gcr_contrarian_filter": (
            "GCR PEARL: If EVERYONE is expecting the same move, fade it. "
            "When consensus is overwhelming, the contrarian trade often wins."
        ),
    },
}

EXIT_RULES = {
    "take_profit": [
        "First trouble area (previous S/R level) for partial profit (50%)",
        "HTF target for remainder — let winners run with trailing stop",
        "Fibonacci extension levels (1.272, 1.618) for trend targets",
        "Round psychological numbers as secondary targets",
    ],
    "stop_loss": {
        "placement": (
            "CryptoCred: Stop loss goes below the most recent swing low (longs) "
            "or above the most recent swing high (shorts). NOT at arbitrary levels."
        ),
        "atr_method": "Alternative: 2x ATR from entry for volatility-adjusted stops.",
        "management": (
            "Move stop to breakeven after 1R profit. Trail stop below swing lows "
            "in an uptrend. Use intraday levels for stop adjustment."
        ),
        "invalidation_stop": "If the setup thesis is invalidated, exit immediately regardless of stop.",
    },
    "gcr_exit_wisdom": {
        "distribution_exits": (
            "GCR: Take profits systematically. Do NOT hold through distribution. "
            "When sentiment is euphoric, scale out aggressively."
        ),
        "sell_the_news": (
            "GCR PEARL: When most traders anticipate a sell-the-news event, "
            "it's probably better to stay invested. Fade the consensus."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 5 — TECHNICAL INDICATOR RULES (CryptoCred)
# ═══════════════════════════════════════════════════════════════

INDICATOR_RULES = {
    "rsi": {
        "oversold": 30,
        "overbought": 70,
        "bullish_divergence": "Price makes lower low, RSI makes higher low → reversal signal.",
        "bearish_divergence": "Price makes higher high, RSI makes lower high → reversal signal.",
        "trend_filter": "In uptrend, RSI tends to bounce off 40-50. In downtrend, rejected at 50-60.",
        "usage_rule": "RSI is a CONFIRMATION tool, not a standalone entry signal.",
    },
    "macd": {
        "bullish_crossover": "MACD line crosses above signal line — momentum shifting bullish.",
        "bearish_crossover": "MACD line crosses below signal line — momentum shifting bearish.",
        "histogram": "Expanding histogram = strengthening momentum. Contracting = weakening.",
        "divergence": "MACD divergence from price is a high-probability reversal signal.",
    },
    "fibonacci": {
        "key_levels": [0.236, 0.382, 0.5, 0.618, 0.786],
        "golden_zone": "0.618–0.786 retracement is the highest probability entry zone.",
        "extensions": [1.0, 1.272, 1.618, 2.0, 2.618],
        "rule": "Fib levels are zones, not exact prices. Confluence with S/R strengthens signal.",
    },
    "bollinger_bands": {
        "squeeze": "Narrow bands = low volatility = impending breakout.",
        "walk_the_band": "In strong trend, price rides upper/lower band — NOT a reversal signal.",
        "mean_reversion": "In ranging market, buy lower band, sell upper band.",
    },
    "moving_averages": {
        "ema_9_21": "Fast trend: 9 EMA crosses 21 EMA for momentum trades.",
        "sma_50": "Medium trend anchor. Price above = bullish context.",
        "sma_200": "Long-term trend. Price above = bull market. Golden/death cross with SMA 50.",
        "dynamic_sr": "MAs act as dynamic support/resistance in trending markets.",
    },
    "ichimoku": {
        "cloud_bias": "Price above cloud = bullish. Price below = bearish. Inside = neutral.",
        "tk_cross": "Tenkan crosses Kijun above cloud = strong buy. Below cloud = strong sell.",
        "future_cloud": "Green future cloud = bullish outlook. Red = bearish.",
    },
    "volume": {
        "confirmation": "Valid breakouts require volume > 1.5x 20-period average.",
        "divergence": "Rising price + falling volume = weakening trend, potential reversal.",
        "climax": "Extreme volume spike at S/R = potential exhaustion / reversal.",
    },
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 6 — RISK MANAGEMENT (CryptoCred + GCR Hybrid)
# ═══════════════════════════════════════════════════════════════

RISK_MANAGEMENT_RULES = {
    "position_sizing": {
        "max_risk_per_trade_pct": 2.0,      # Max 2% equity risk per trade
        "max_portfolio_risk_pct": 10.0,      # Max 10% total open risk
        "kelly_criterion": True,              # Use half-Kelly for sizing
        "kelly_cap_pct": 8.0,                # Never exceed 8% single position
        "leverage_rule": (
            "CryptoCred: Leverage amplifies, it does NOT change the quality of a trade. "
            "Use leverage to right-size positions, not to over-bet."
        ),
    },
    "stop_loss_discipline": {
        "rule": "GCR: Sets stops BEFORE trades execute. Losses are PLANNED.",
        "max_loss_per_trade_pct": 2.0,
        "daily_loss_limit_pct": 5.0,
        "weekly_loss_limit_pct": 10.0,
    },
    "portfolio_rules": {
        "btc_eth_core": (
            "GCR PEARL: For most crypto investors, holding BTC and ETH "
            "will do best in the long run. Always maintain core positions."
        ),
        "btc_core_allocation_pct": 40,        # Minimum BTC allocation
        "eth_core_allocation_pct": 20,        # Minimum ETH allocation
        "altcoin_max_allocation_pct": 30,     # Max altcoin exposure
        "stablecoin_min_pct": 10,             # Always keep dry powder
        "max_single_altcoin_pct": 5.0,        # No single alt > 5%
    },
    "circuit_breaker": {
        "daily_loss_halt_pct": 5.0,           # Halt trading if -5% daily
        "drawdown_halt_pct": 15.0,            # Halt if -15% from peak
        "consecutive_loss_halt": 5,           # Halt after 5 consecutive losses
        "cooldown_hours": 24,                 # Wait 24h after circuit breaker
    },
    "gcr_risk_scaling": {
        "accumulation_phase": (
            "GCR: When market sentiment is at maximum fear and structure "
            "shows signs of bottoming, INCREASE risk allocation. "
            "This is where generational wealth is built."
        ),
        "distribution_phase": (
            "GCR: When euphoria peaks and retail is leverage-longing, "
            "reduce risk to minimum. Scale into stables and shorts."
        ),
    },
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 7 — GCR CONTRARIAN FRAMEWORK
# ═══════════════════════════════════════════════════════════════

GCR_CONTRARIAN_RULES = {
    "tree_of_life": (
        "GCR's 'Tree of Life' is simply the willingness to bet against "
        "the consensus view. When everyone agrees on direction, the move "
        "is likely already priced in. Real edge is in the opposite trade."
    ),
    "reflexivity": (
        "Drawn from Soros: Market participant biases influence prices, "
        "which then reshape expectations in a self-reinforcing cycle. "
        "Identify these feedback loops to front-run reversals."
    ),
    "sentiment_inversion_rules": {
        "extreme_fear": "BUY signal — crowd is capitulating, smart money accumulating.",
        "extreme_greed": "SELL signal — crowd is euphoric, distribution phase.",
        "consensus_long": "Caution — when everyone is bullish, who is left to buy?",
        "consensus_short": "Caution — when everyone is bearish, who is left to sell?",
    },
    "incentive_analysis": (
        "GCR: Focus on 'who profits' rather than hype. Study volumes, "
        "smart money flows, and token unlock schedules. Understand the "
        "incentive mechanisms before entering any position."
    ),
    "token_unlock_rule": (
        "GCR: Heavily short assets with large future token unlocks. "
        "Locked investor tokens create guaranteed selling pressure."
    ),
    "altcoin_dependency": (
        "GCR: 'Altcoins cannot survive independently' without BTC strength. "
        "Never go heavy on alts when BTC is weak or trending down."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 8 — CRYPTO-SPECIFIC RULES
# ═══════════════════════════════════════════════════════════════

CRYPTO_SPECIFIC_RULES = {
    "market_hours": "Crypto trades 24/7. Key sessions: Asia (UTC 00-08), EU (08-16), US (16-24).",
    "funding_rate": {
        "positive_high": "Longs paying shorts — market overleveraged long, potential pullback.",
        "negative_high": "Shorts paying longs — market overleveraged short, potential squeeze.",
        "threshold": 0.01,  # >0.01% per 8h = elevated
    },
    "open_interest": {
        "rising_oi_rising_price": "New money entering longs — trend continuation likely.",
        "rising_oi_falling_price": "New money entering shorts — bearish pressure.",
        "falling_oi_rising_price": "Short squeeze — may be unsustainable.",
        "falling_oi_falling_price": "Long liquidation — may be capitulation.",
    },
    "btc_dominance": {
        "rising": "Risk-off: money flowing from alts to BTC. Reduce altcoin exposure.",
        "falling": "Risk-on: money flowing from BTC to alts. Alt season potential.",
        "threshold_high": 60.0,  # Above = BTC dominant, alts weak
        "threshold_low": 40.0,   # Below = alt season confirmed
    },
    "liquidation_cascades": (
        "GCR: Market makers use retail liquidity cascades to offload positions. "
        "Large liquidation events create contrarian buying opportunities."
    ),
    "on_chain_signals": [
        "Exchange inflows rising = selling pressure incoming",
        "Exchange outflows rising = accumulation, bullish",
        "Whale wallet accumulation = smart money buying",
        "Stablecoin supply on exchanges = dry powder, potential buying pressure",
    ],
}


# ═══════════════════════════════════════════════════════════════
#  SECTION 9 — TRADING SYSTEM META-RULES (CryptoCred + GCR)
# ═══════════════════════════════════════════════════════════════

META_RULES = {
    "systematic_execution": (
        "CryptoCred: Be systematic — never emotional. Every trade must have "
        "a predefined entry, stop loss, take profit, and position size BEFORE execution."
    ),
    "trade_journaling": (
        "GCR: Analyze both wins AND losses to identify improvement areas. "
        "The system must log every decision with full justification."
    ),
    "patience": (
        "GCR PEARL: Wait for optimal entry/exit conditions rather than trading constantly. "
        "CryptoCred: No trade is better than a bad trade."
    ),
    "edge_identification": (
        "GCR: Look for unique areas to press edge. The edge comes from "
        "understanding what others don't — token mechanics, liquidation levels, "
        "sentiment extremes, and incentive misalignment."
    ),
    "cycle_awareness": (
        "GCR called the 2021 top precisely. 'I am confident we are at the tail end "
        "of the cycle.' Always know where you are in the macro cycle."
    ),
    "reduce_in_uncertainty": (
        "GCR: 'Reduce trading under unfavorable conditions.' "
        "When the market is unclear, do less. Capital preservation > forced trades."
    ),
    "long_term_conviction": (
        "GCR: Money printing won't stop. Long-term holders outperform traders "
        "as monetary policies continue. Always maintain a core BTC/ETH position."
    ),
}


# ═══════════════════════════════════════════════════════════════
#  CONFIDENCE SCORING WEIGHTS
# ═══════════════════════════════════════════════════════════════

CONFIDENCE_WEIGHTS = {
    # CryptoCred TA Weights
    "market_structure_alignment": 2.5,    # HTF structure (most important)
    "directional_bias_match": 2.0,        # Bias alignment
    "sr_level_proximity": 1.5,            # Near key S/R level
    "entry_trigger_quality": 1.5,         # Clean entry trigger
    "volume_confirmation": 1.0,           # Volume backing the move
    "indicator_confluence": 1.0,          # RSI + MACD + BB agreement
    "fibonacci_zone": 1.0,               # In golden zone (0.618-0.786)
    "multi_tf_alignment": 1.5,           # Multiple timeframes agree

    # GCR Contrarian Weights
    "sentiment_contrarian": 2.0,          # Against consensus at extremes
    "funding_rate_signal": 1.0,           # Funding rate extreme
    "liquidation_opportunity": 1.5,       # Post-liquidation cascade
    "token_unlock_pressure": 1.0,         # Upcoming unlock = short bias
    "btc_dominance_alignment": 1.0,       # BTC dom trend alignment
    "reflexivity_loop": 1.5,             # Self-reinforcing narrative

    # Penalty Weights (negative)
    "against_bias_penalty": -3.0,         # Trading against directional bias
    "low_volume_penalty": -1.5,           # Breakout without volume
    "overleveraged_market_penalty": -2.0, # Extreme funding / OI
    "consensus_trade_penalty": -1.5,      # Everyone in the same trade
}
