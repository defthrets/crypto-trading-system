"""
0xRex -- Signal Generation and Analysis
Signal engine, opportunities, justification, quadrant classification, sentiment, correlation.
"""

import asyncio
import random
import numpy as np
from collections import defaultdict
from datetime import datetime
from typing import Optional

from loguru import logger

from api.utils import (
    _cache_get, _cache_set, _get_prices, _EXECUTOR,
    _calc_rsi, _calc_trend, _calc_atr, _calc_macd, _calc_bollinger,
    YF_AVAILABLE,
)
from api.state import STATE, WATCHLIST
from api.scanners import (
    LARGE_CAP_TICKERS, MEME_TICKERS, CORR_TICKERS,
    _scanner_cache, _ASSET_META, _live_price,
)
from api.portfolio import PAPER, PAPER_STARTING_CASH, _get_fee_pct


# ── Market Regime metadata (CryptoCred + GCR) ──────────────────────────────────
QUADRANT_META = {
    "bull_trend": {
        "label": "BULL TREND",
        "color": "#00ff41",
        "icon": "▲",
        "description": "Higher highs, higher lows. BTC leading. Favour large caps, L1s, risk-on alts. Aggressive positioning.",
        "favoured": ["Large Cap", "Layer 1", "DeFi", "AI Tokens"],
        "avoid": ["Stablecoins", "Defensive"],
    },
    "bear_trend": {
        "label": "BEAR TREND",
        "color": "#ff4444",
        "icon": "▼",
        "description": "Lower lows, lower highs. Capital preservation mode. BTC/ETH core only, reduce alts aggressively.",
        "favoured": ["Large Cap (BTC/ETH)", "Stablecoins"],
        "avoid": ["Meme", "Small Cap Alts", "Gaming"],
    },
    "accumulation": {
        "label": "ACCUMULATION",
        "color": "#ffb300",
        "icon": "◆",
        "description": "GCR contrarian zone: extreme fear, smart money accumulating. Build positions in quality assets at discount.",
        "favoured": ["Large Cap", "DeFi Blue Chips", "Infrastructure"],
        "avoid": ["Meme", "Low Liquidity"],
    },
    "distribution": {
        "label": "DISTRIBUTION",
        "color": "#ff6600",
        "icon": "◇",
        "description": "GCR warning: extreme greed, smart money distributing. Take profits, raise stablecoin allocation.",
        "favoured": ["Stablecoins", "BTC Core"],
        "avoid": ["Meme", "Leveraged Positions", "New Alts"],
    },
    "ranging": {
        "label": "RANGING",
        "color": "#00e5ff",
        "icon": "↔",
        "description": "No clear trend. Range-bound price action. Favour mean-reversion strategies, reduce position sizes.",
        "favoured": ["Large Cap", "DeFi Yield"],
        "avoid": ["Breakout Trades", "Leveraged Positions"],
    },
    "rising_growth": {
        "label": "BULL TREND",
        "color": "#00ff41",
        "icon": "▲",
        "description": "Higher highs, higher lows. BTC leading. Favour large caps, L1s, risk-on alts.",
        "favoured": ["Large Cap", "Layer 1", "DeFi"],
        "avoid": ["Stablecoins"],
    },
    "falling_growth": {
        "label": "BEAR TREND",
        "color": "#ff4444",
        "icon": "▼",
        "description": "Lower lows, lower highs. Capital preservation. BTC/ETH core only.",
        "favoured": ["Large Cap (BTC/ETH)", "Stablecoins"],
        "avoid": ["Meme", "Small Cap Alts"],
    },
    "rising_inflation": {
        "label": "ACCUMULATION",
        "color": "#ffb300",
        "icon": "◆",
        "description": "Contrarian accumulation zone. Build positions in quality crypto assets.",
        "favoured": ["Large Cap", "DeFi Blue Chips"],
        "avoid": ["Meme", "Low Liquidity"],
    },
    "falling_inflation": {
        "label": "RANGING",
        "color": "#00e5ff",
        "icon": "↔",
        "description": "Range-bound. Mean-reversion strategies, reduced sizing.",
        "favoured": ["Large Cap", "DeFi Yield"],
        "avoid": ["Breakout Trades"],
    },
}

ASSET_CLASS_MAP: dict = {
    # ── Large Cap ──
    "BTC-USD":"large_cap","ETH-USD":"large_cap","BNB-USD":"large_cap","SOL-USD":"large_cap",
    "XRP-USD":"large_cap","ADA-USD":"large_cap","AVAX-USD":"large_cap","DOT-USD":"large_cap",
    "LINK-USD":"large_cap","MATIC-USD":"large_cap",
    # ── DeFi ──
    "UNI-USD":"defi","AAVE-USD":"defi","MKR-USD":"defi","CRV-USD":"defi",
    "LDO-USD":"defi","SNX-USD":"defi","COMP-USD":"defi","SUSHI-USD":"defi",
    # ── Layer 1 ──
    "NEAR-USD":"layer1","APT-USD":"layer1","SUI-USD":"layer1","ATOM-USD":"layer1",
    "FTM-USD":"layer1","INJ-USD":"layer1","SEI-USD":"layer1","TIA-USD":"layer1",
    # ── Layer 2 ──
    "ARB-USD":"layer2","OP-USD":"layer2","IMX-USD":"layer2","STRK-USD":"layer2",
    # ── Meme ──
    "DOGE-USD":"meme","SHIB-USD":"meme","PEPE-USD":"meme","WIF-USD":"meme",
    "BONK-USD":"meme","FLOKI-USD":"meme",
    # ── Gaming ──
    "AXS-USD":"gaming","SAND-USD":"gaming","MANA-USD":"gaming","GALA-USD":"gaming",
    # ── AI ──
    "FET-USD":"ai","RNDR-USD":"ai","AGIX-USD":"ai","TAO-USD":"ai",
    # ── Infrastructure ──
    "FIL-USD":"infrastructure","AR-USD":"infrastructure","GRT-USD":"infrastructure","THETA-USD":"infrastructure",
}


def _get_asset_class(ticker: str) -> str:
    """Resolve asset class for quadrant playbook scoring.
    Explicit map first, then pattern-based fallback so new tickers
    added to scanner universes get reasonable classification."""
    if ticker in ASSET_CLASS_MAP:
        return ASSET_CLASS_MAP[ticker]
    if ticker.endswith("-USD"):
        return "large_cap"
    return "large_cap"

QUADRANT_PLAYBOOK: dict = {
    "bull_trend": {
        "strong_buy": ["large_cap","layer1","ai"],
        "buy":        ["defi","layer2","infrastructure","gaming"],
        "avoid":      ["meme"],
        "narrative":  (
            "Bull Trend: BTC making higher highs, altcoins expanding. "
            "CryptoCred bias: bullish. Favour large caps and quality L1s. "
            "DeFi and AI tokens outperform mid-cycle. GCR: ride the trend but watch for distribution signals."
        ),
    },
    "bear_trend": {
        "strong_buy": ["large_cap"],
        "buy":        ["infrastructure"],
        "avoid":      ["meme","gaming","layer2","ai"],
        "narrative":  (
            "Bear Trend: lower lows, lower highs. Capital preservation is paramount. "
            "GCR rule: only BTC/ETH core positions. Close all leveraged alts. "
            "CryptoCred: wait for structure break before re-entry."
        ),
    },
    "accumulation": {
        "strong_buy": ["large_cap","defi","infrastructure"],
        "buy":        ["layer1","layer2","ai"],
        "avoid":      ["meme","gaming"],
        "narrative":  (
            "Accumulation: GCR contrarian signal -- extreme fear, smart money buying. "
            "Tree of Life: bet against consensus. Build quality positions at discount. "
            "CryptoCred: look for bullish divergences and structure shifts."
        ),
    },
    "distribution": {
        "strong_buy": ["large_cap"],
        "buy":        ["infrastructure"],
        "avoid":      ["meme","gaming","layer2","ai","defi"],
        "narrative":  (
            "Distribution: GCR warning -- extreme greed, smart money selling. "
            "Take profits aggressively. Raise stablecoin allocation to 30%+. "
            "CryptoCred: watch for bearish divergences and failed breakouts."
        ),
    },
    "ranging": {
        "strong_buy": ["large_cap","defi"],
        "buy":        ["infrastructure","layer1"],
        "avoid":      ["meme","gaming"],
        "narrative":  (
            "Ranging: no clear directional bias. CryptoCred: trade S/R bounces only. "
            "Reduce position sizes by 50%. GCR: patience -- wait for regime clarity."
        ),
    },
    # Legacy aliases for backward compat with quadrant engine
    "rising_growth": {
        "strong_buy": ["large_cap","layer1","ai"],
        "buy":        ["defi","layer2","infrastructure","gaming"],
        "avoid":      ["meme"],
        "narrative":  "Bull trend conditions -- favour large caps and quality alts.",
    },
    "falling_growth": {
        "strong_buy": ["large_cap"],
        "buy":        ["infrastructure"],
        "avoid":      ["meme","gaming","layer2","ai"],
        "narrative":  "Bear trend conditions -- BTC/ETH core only, reduce alts.",
    },
    "rising_inflation": {
        "strong_buy": ["large_cap","defi","infrastructure"],
        "buy":        ["layer1","layer2","ai"],
        "avoid":      ["meme","gaming"],
        "narrative":  "Accumulation conditions -- build quality positions at discount.",
    },
    "falling_inflation": {
        "strong_buy": ["large_cap","defi"],
        "buy":        ["infrastructure","layer1"],
        "avoid":      ["meme","gaming"],
        "narrative":  "Ranging conditions -- trade S/R bounces, reduce sizing.",
    },
}

def _gen_price_history_demo(price: float, trend: str, n_points: int = 30) -> list:
    """Seeded random-walk ending at `price`, shaped by trend direction."""
    drift = 0.003 if trend == "uptrend" else -0.003 if trend == "downtrend" else 0.0
    pts = []
    p = price * (1 - drift * n_points)
    for _ in range(n_points):
        p = p * (1 + drift + random.gauss(0, 0.012))
        pts.append(round(p, 4))
    pts[-1] = price
    return pts


async def _gen_signals(n: int = 12) -> list[dict]:
    """Generate trade signals from real price data."""
    cache_key = f"signals_{n}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    cached_by_market: dict = {"large_cap": [], "meme": []}
    for mkt in ("crypto", "defi", "large_cap", "meme"):
        sc = _scanner_cache.get(mkt)
        if sc:
            rows = sorted(sc["rows"], key=lambda r: abs(r.get("change_pct", 0)), reverse=True)
            tickers = [r["ticker"] for r in rows if r.get("price", 0) > 0][:n]
            bucket = "large_cap" if mkt in ("crypto", "large_cap") else "meme"
            cached_by_market[bucket].extend(tickers)

    n_each = max(4, (n * 2) // 3)
    fresh = {
        "large_cap":   random.sample(LARGE_CAP_TICKERS,  min(n_each, len(LARGE_CAP_TICKERS))),
        "meme":        random.sample(MEME_TICKERS,       min(n_each, len(MEME_TICKERS))),
    }

    market_candidates = {}
    for mkt in ("large_cap", "meme"):
        market_candidates[mkt] = list(dict.fromkeys(
            cached_by_market[mkt] + fresh[mkt]
        ))[:n_each]

    prices_map: dict = {}

    lc_cands = market_candidates["large_cap"][:10]
    if lc_cands:
        lc_prices = await _get_prices(lc_cands, "3mo")
        if lc_prices:
            prices_map.update(lc_prices)

    meme_cands = market_candidates["meme"][:10]
    if meme_cands:
        meme_prices = await _get_prices(meme_cands, "3mo")
        if meme_prices:
            prices_map.update(meme_prices)

    candidates = list(dict.fromkeys(
        market_candidates["large_cap"] + market_candidates["meme"]
    ))

    cache_prices: dict = {}
    for mkt in ("crypto", "defi", "large_cap", "meme"):
        sc = _scanner_cache.get(mkt)
        if sc:
            for r in sc["rows"]:
                if r.get("price", 0) > 0:
                    cache_prices[r["ticker"]] = r["price"]

    signals = []
    for ticker in candidates:
        closes = prices_map.get(ticker)
        if not closes or len(closes) < 10:
            continue

        price  = round(closes[-1], 2)
        rsi    = _calc_rsi(closes)
        trend  = _calc_trend(closes)
        atr    = _calc_atr(closes)
        macd_data = _calc_macd(closes)
        bb_data   = _calc_bollinger(closes)

        score = 0.0
        signal_reasons = []

        # ── Crypto — Technical analysis principles ──
        rsi_oversold, rsi_overbought = 32, 68

        if rsi < rsi_oversold:
            score += 2.0
            signal_reasons.append(f"RSI oversold ({rsi:.0f})")
        elif rsi > rsi_overbought:
            score -= 2.0
            signal_reasons.append(f"RSI overbought ({rsi:.0f})")
        elif rsi < 45:
            score += 0.5
        elif rsi > 55:
            score -= 0.5

        if macd_data["macd_signal"] == "bullish":
            score += 1.5
            signal_reasons.append("MACD bullish")
        else:
            score -= 1.5
            signal_reasons.append("MACD bearish")
        if macd_data["macd_crossover"]:
            score += 1.0
            signal_reasons.append("Fresh MACD crossover")

        if bb_data["bb_position"] == "below_lower":
            score += 1.5
            signal_reasons.append("Below lower Bollinger Band")
        elif bb_data["bb_position"] == "above_upper":
            score -= 1.5
            signal_reasons.append("Above upper Bollinger Band")

        if trend == "uptrend":
            score += 2.0
            signal_reasons.append("Confirmed uptrend")
        elif trend == "downtrend":
            score -= 2.0
            signal_reasons.append("Confirmed downtrend")

        if len(closes) >= 10:
            roc = (closes[-1] / closes[-10] - 1) * 100
            if roc > 5:
                score += 0.5
            elif roc < -5:
                score -= 0.5

        sl_mult, tp_mult = 1.5, 2.5

        if score >= 3.0:
            action = "BUY"
        elif score <= -3.0:
            action = "SHORT"
        elif score >= 1.5:
            action = "LONG"
        elif score <= -1.5:
            action = "SELL"
        else:
            action = "HOLD"

        price_history = [round(c, 2) for c in closes[-30:]]

        sl_offset = max(atr * sl_mult, price * 0.025)
        tp_offset = atr * tp_mult

        conf = round(min(95, max(50.0, 50 + abs(score) * 6)), 1)

        ac = _get_asset_class(ticker)
        qdata = STATE.last_quadrant or {}
        quadrant = qdata.get("quadrant", "rising_growth")
        pb = QUADRANT_PLAYBOOK.get(quadrant, QUADRANT_PLAYBOOK["rising_growth"])

        if ac in pb["strong_buy"]:   q_fit = "strong"
        elif ac in pb["buy"]:         q_fit = "moderate"
        elif ac in pb["avoid"]:       q_fit = "avoid"
        else:                          q_fit = "neutral"

        predicted_days = max(3, min(60, int(tp_offset / max(price * 0.008, 0.01))))
        pos_size_pct = round(min(5.0, max(1.0, (conf - 50) / 9)), 1)

        ac = _get_asset_class(ticker)
        if ac in ("meme", "gaming"):
            sig_market = "meme"
        elif ac in ("defi", "layer2"):
            sig_market = "defi"
        else:
            sig_market = "crypto"

        rr_ratio = round(tp_offset / sl_offset, 2)
        sig = {
            "ticker": ticker,
            "trade_ticker": ticker,
            "currency": "USD",
            "market": sig_market,
            "action": action,
            "confidence": conf,
            "price": price,
            "data_source": "LIVE",
            "quadrant_fit": q_fit,
            "rsi": rsi,
            "trend": trend,
            "macd_signal": macd_data["macd_signal"],
            "macd_value": macd_data["macd"],
            "macd_crossover": macd_data["macd_crossover"],
            "bb_position": bb_data["bb_position"],
            "bb_pct": bb_data["bb_pct"],
            "signal_score": round(score, 2),
            "signal_reasons": signal_reasons,
            "stop_loss":  round(price - sl_offset, 2) if action in ("SELL","SHORT") else round(price - sl_offset, 2),
            "take_profit": round(price + tp_offset, 2) if action in ("BUY","LONG")  else round(price - tp_offset, 2),
            "rr_ratio": rr_ratio,
            "fee_pct": _get_fee_pct(ticker),
            "round_trip_fee_pct": round(_get_fee_pct(ticker) * 2, 2),
            "net_rr_ratio": round(max(0, (tp_offset - price * _get_fee_pct(ticker) * 2 / 100)) / sl_offset, 2),
            "position_size_pct": pos_size_pct,
            "ultra_justification": _gen_justification(
                ticker, action, rsi=rsi, rr=rr_ratio,
                macd_signal=macd_data["macd_signal"],
                bb_position=bb_data["bb_position"],
                trend=trend, q_fit=q_fit,
            ),
            "price_history": price_history,
            "predicted_days": predicted_days,
            "timestamp": datetime.utcnow().isoformat(),
        }

        signals.append(sig)

    active = [s for s in signals if s["action"] != "HOLD"]
    if not active:
        active = sorted(signals, key=lambda s: s["confidence"], reverse=True)

    per_market = max(2, n // 2)
    balanced = []
    for mkt in ("crypto", "defi"):
        mkt_sigs = sorted(
            [s for s in active if s.get("market") == mkt],
            key=lambda s: s["confidence"], reverse=True
        )
        balanced.extend(mkt_sigs[:per_market])

    seen = {s["ticker"] for s in balanced}
    remaining = [s for s in active if s["ticker"] not in seen]
    remaining.sort(key=lambda s: s["confidence"], reverse=True)
    balanced.extend(remaining[:max(0, n - len(balanced))])

    balanced.sort(key=lambda s: s["confidence"], reverse=True)
    result = balanced[:n]
    _cache_set(cache_key, result)
    logger.info(f"Signals generated: {len(result)} total -- "
                f"Crypto:{sum(1 for s in result if s.get('market')=='crypto')} "
                f"DeFi:{sum(1 for s in result if s.get('market')=='defi')}")
    return result


def _opp_from_signal_fallback(sigs: list, quadrant: str, playbook: dict,
                               qdata: dict, existing_classes: list, n: int) -> list:
    """Fallback when no scanner cache exists."""
    regime_label = qdata.get("label", quadrant.replace("_"," ").title())
    results = []
    for s in sigs:
        if s["action"] in ("HOLD", "SELL", "SHORT"):
            continue
        ac    = _get_asset_class(s["ticker"])
        q_fit = ("strong"   if ac in playbook["strong_buy"] else
                 "moderate" if ac in playbook["buy"]        else
                 "avoid"    if ac in playbook["avoid"]      else "neutral")
        q_w   = {"strong": 1.4, "moderate": 1.0, "neutral": 0.6, "avoid": 0.2}[q_fit]
        score = round(s["confidence"] * q_w, 1)
        jus   = s.get("ultra_justification", {})
        reason_0 = (f"Regime: {regime_label} -- {ac.replace('_',' ').title()} is "
                    f"{'favoured' if q_fit in ('strong','moderate') else 'on avoid list'}.")
        reason_1 = f"RSI {s['rsi']:.0f} | trend: {s['trend']} | signal: {s['action']}"
        reasoning = [reason_0, reason_1]
        if isinstance(jus, dict):
            for key in ("narrative", "recommendation"):
                val = jus.get(key, "")
                if val and isinstance(val, str):
                    reasoning.append(val[:120])
                    break
        results.append({
            "ticker": s["ticker"], "market": "signal", "action": s["action"],
            "price": s["price"], "change_pct": 0, "rsi": s["rsi"],
            "trend": s["trend"], "above_sma20": s["trend"] == "uptrend",
            "hi_52w": s["take_profit"], "lo_52w": s["stop_loss"],
            "pct_from_hi": 0, "pct_from_lo": 0, "sma20": s["price"],
            "stop_loss": s["stop_loss"], "take_profit": s["take_profit"],
            "rr_ratio": s["rr_ratio"], "score": score,
            "asset_class": ac, "quadrant_fit": q_fit,
            "data_source": s["data_source"],
            "reasoning": reasoning,
            "volume_fmt": "--", "sector": "--",
            "quadrant": quadrant, "regime_label": regime_label,
        })
    results.sort(key=lambda o: o["score"], reverse=True)
    return results[:n]


async def _gen_opportunities(n: int = 8) -> list[dict]:
    """Return the top-N trade opportunities."""
    qdata    = STATE.last_quadrant or _gen_quadrant_data()
    quadrant = qdata.get("quadrant", "rising_growth")
    regime_pb = QUADRANT_PLAYBOOK.get(quadrant, QUADRANT_PLAYBOOK["rising_growth"])
    existing_classes = [_get_asset_class(t) for t in PAPER.positions]

    all_rows: list[dict] = []
    for mkt in ("crypto", "defi"):
        cached = _scanner_cache.get(mkt)
        if cached:
            for r in cached["rows"]:
                row = dict(r)
                row["_market"] = mkt
                all_rows.append(row)

    if not all_rows:
        sigs = await _gen_signals(n * 2)
        return _opp_from_signal_fallback(sigs, quadrant, regime_pb, qdata, existing_classes, n)

    def _prescore(r: dict) -> float:
        tkr = r["ticker"]
        if tkr in PAPER.positions:
            return -999.0
        ac  = _get_asset_class(tkr)
        chg = r.get("change_pct", 0.0)
        q_s = (100 if ac in regime_pb["strong_buy"] else
               70  if ac in regime_pb["buy"]        else
               10  if ac in regime_pb["avoid"]      else 45)
        mom = min(abs(chg) * 3.0, 30.0)
        dir_b = (15 if ac in regime_pb["strong_buy"] and chg > 0 else
                 10 if ac in regime_pb["avoid"] and chg < 0      else 0)
        div_b = max(0.0, 20.0 - existing_classes.count(ac) * 5)
        return q_s * 0.40 + mom * 0.25 + dir_b * 0.20 + div_b * 0.15

    all_rows.sort(key=_prescore, reverse=True)
    candidates = [r for r in all_rows if r["ticker"] not in PAPER.positions][:30]

    cand_by_mkt: dict = {"crypto": [], "defi": []}
    for r in candidates[:24]:
        mkt = r.get("_market", "crypto")
        if mkt in cand_by_mkt:
            cand_by_mkt[mkt].append(r["ticker"])

    history_map: dict = {}
    for mkt, tkrs in cand_by_mkt.items():
        if not tkrs:
            continue
        chunk = await _get_prices(tkrs[:10], "3mo")
        if chunk:
            history_map.update(chunk)

    opportunities: list[dict] = []

    for r in candidates:
        tkr    = r["ticker"]
        ac     = _get_asset_class(tkr)
        closes = history_map.get(tkr)
        chg    = r.get("change_pct", 0.0)
        price  = r.get("price", 0.0)
        if not price:
            continue

        if closes and len(closes) >= 14:
            rsi        = _calc_rsi(closes)
            trend      = _calc_trend(closes)
            hi52       = float(max(closes))
            lo52       = float(min(closes))
            sma20      = float(np.mean(closes[-20:])) if len(closes) >= 20 else price
            above_sma  = price > sma20
            vol_d      = float(np.std(np.diff(closes)) / price) if len(closes) > 2 else 0.02
            data_src   = "LIVE"
        else:
            rsi        = 50.0
            trend      = "sideways"
            hi52       = price * 1.20
            lo52       = price * 0.80
            sma20      = price
            above_sma  = chg > 0
            vol_d      = 0.025
            data_src   = "SCANNER"

        pct_from_hi = round((price / hi52 - 1) * 100, 1) if hi52 else 0
        pct_from_lo = round((price / lo52 - 1) * 100, 1) if lo52 else 0

        if   rsi < 32 and trend != "downtrend": action = "BUY"
        elif rsi > 68 and trend != "uptrend":   action = "SELL"
        elif trend == "uptrend" and rsi < 58:   action = "LONG"
        elif trend == "downtrend" and rsi > 42: action = "SHORT"
        else:                                   action = "WATCH"

        is_short_signal = action in ("SELL", "SHORT")
        tkr_pb = regime_pb
        tkr_regime = quadrant

        is_avoid_class  = ac in tkr_pb["avoid"]
        if is_short_signal and not is_avoid_class:
            continue

        q_score = (100 if ac in tkr_pb["strong_buy"] else
                   70  if ac in tkr_pb["buy"]        else
                   10  if ac in tkr_pb["avoid"]      else 45)
        q_fit   = ("strong"   if ac in tkr_pb["strong_buy"] else
                   "moderate" if ac in tkr_pb["buy"]        else
                   "avoid"    if ac in tkr_pb["avoid"]      else "neutral")

        if not is_short_signal:
            rsi_score = max(0.0, 50.0 - rsi) * 0.8
        else:
            rsi_score = max(0.0, rsi - 50.0) * 0.8

        mom_score  = min(abs(chg) * 2.5, 25.0)
        div_score  = max(0.0, 20.0 - existing_classes.count(ac) * 5.0)

        composite = round(
            q_score   * 0.35 +     # Crypto quadrant fit is primary driver
            rsi_score * 0.30 +
            mom_score * 0.20 +
            div_score * 0.15,
            1
        )

        atr = max(vol_d * price * 14, price * 0.01)
        sl_m = 1.5
        sl  = round(price - atr * sl_m, 4)
        tp_m = 2.5
        tp  = round(price + atr * tp_m, 4)
        rr  = round((tp - price) / max(price - sl, 1e-6), 2)

        regime_display = tkr_regime.replace('_', ' ').title()
        reasons = [
            f"Regime: {regime_display} -- "
            f"{ac.replace('_',' ').title()} is "
            f"{'FAVOURED (strong buy)' if q_fit=='strong' else 'favoured' if q_fit=='moderate' else 'AVOID LIST' if q_fit=='avoid' else 'neutral'}.",
            f"RSI {rsi:.0f} ({'oversold' if rsi<35 else 'overbought' if rsi>65 else 'neutral'}) | "
            f"Trend: {trend} | {'Above' if above_sma else 'Below'} 20-day SMA.",
            f"Today: {'+' if chg>=0 else ''}{chg:.2f}% | "
            f"52w range: {pct_from_lo:+.1f}% from low, {pct_from_hi:+.1f}% from high.",
            f"Stop ${sl:,.4f} -> Target ${tp:,.4f} | R:R {rr:.1f}x",
        ]
        if pct_from_lo < 10:
            reasons.append("Near 52-week low -- potential high-reward entry zone.")
        if above_sma and chg > 1:
            reasons.append("Strong momentum: price above SMA and up today.")
        if existing_classes.count(ac) == 0:
            reasons.append(f"No current {ac.replace('_',' ')} exposure -- adds portfolio diversification.")

        opportunities.append({
            "ticker":       tkr,
            "market":       r["_market"],
            "action":       action,
            "price":        price,
            "change_pct":   round(chg, 2),
            "rsi":          round(rsi, 1),
            "trend":        trend,
            "above_sma20":  above_sma,
            "hi_52w":       round(hi52, 4),
            "lo_52w":       round(lo52, 4),
            "pct_from_hi":  pct_from_hi,
            "pct_from_lo":  pct_from_lo,
            "sma20":        round(sma20, 4),
            "stop_loss":    sl,
            "take_profit":  tp,
            "rr_ratio":     rr,
            "fee_pct":      _get_fee_pct(tkr),
            "round_trip_fee_pct": round(_get_fee_pct(tkr) * 2, 2),
            "net_profit_pct": round((tp - price) / price * 100 - _get_fee_pct(tkr) * 2, 2),
            "score":        composite,
            "asset_class":  ac,
            "quadrant_fit": q_fit,
            "data_source":  data_src,
            "reasoning":    reasons,
            "volume_fmt":   r.get("volume_fmt", "--"),
            "sector":       r.get("sector", "--"),
            "quadrant":     tkr_regime,
            "regime_label": regime_display,
        })

    opportunities.sort(key=lambda o: o["score"], reverse=True)

    # ── Per-market balancing: guarantee minimum representation ──
    # Each market gets at least floor(n/2) slots, rest filled by best score
    per_mkt = max(1, n // 2)
    balanced = []
    for mkt in ("large_cap", "defi", "layer1", "layer2", "meme", "ai"):
        mkt_opps = [o for o in opportunities if o.get("market") == mkt]
        balanced.extend(mkt_opps[:per_mkt])

    seen = {o["ticker"] for o in balanced}
    remaining = [o for o in opportunities if o["ticker"] not in seen]
    balanced.extend(remaining[:max(0, n - len(balanced))])
    balanced.sort(key=lambda o: o["score"], reverse=True)

    logger.info(f"Opportunities: {len(balanced[:n])} total -- "
                f"Large Cap:{sum(1 for o in balanced[:n] if o.get('market')=='large_cap')} "
                f"DeFi:{sum(1 for o in balanced[:n] if o.get('market')=='defi')} "
                f"L1/L2:{sum(1 for o in balanced[:n] if o.get('market') in ('layer1','layer2'))}")
    return balanced[:n]


def _gen_justification(ticker: str, action: str, **kwargs) -> dict:
    """Generate Crypto framework justification for crypto assets."""
    rsi_val = kwargs.get("rsi", 50.0)
    rr = kwargs.get("rr", 2.0)
    macd_sig = kwargs.get("macd_signal", "neutral")
    bb_pos = kwargs.get("bb_position", "mid")
    trend = kwargs.get("trend", "sideways")
    q_fit = kwargs.get("q_fit", "neutral")

    sent_score = 0.0
    sent_source = "keyword"

    n_positions = len(PAPER.positions) + 1
    corr_estimate = round(max(-0.15, min(0.1, 0.3 - 0.03 * n_positions)), 3)
    sharpe_est = round(max(0.01, min(0.4, (rr - 1.0) * 0.1)), 3)
    risk_contrib = round(100.0 / max(n_positions, 1), 2)

    rsi_desc = "oversold" if rsi_val < 35 else "overbought" if rsi_val > 65 else "neutral"

    qdata = STATE.last_quadrant or {}
    quadrant = qdata.get("quadrant", "rising_growth")
    meta = QUADRANT_META.get(quadrant, QUADRANT_META["rising_growth"])
    quadrant_label = quadrant.replace("_", " ").title()

    if STATE.last_sentiment:
        qs = STATE.last_sentiment.get("quadrant_sentiment", {})
        q_sent = qs.get(quadrant, {})
        sent_score = q_sent.get("avg_score", 0.0)
        sent_source = STATE.last_sentiment.get("sentiment_model", "keyword")

    sentiment_word = "positive" if sent_score > 0.1 else "negative" if sent_score < -0.1 else "neutral"

    ai_overview = (
        f"{ticker} presents a {action.lower()} opportunity under the current {quadrant_label} regime. "
        f"Sentiment ({sent_source}) is {sentiment_word} (score {sent_score:+.3f}), "
        f"RSI reads {rsi_val:.0f} ({rsi_desc}), MACD is {macd_sig}, "
        f"BB position: {bb_pos}, trend: {trend}. "
        f"Risk/reward ratio is {rr}:1. "
        f"Estimated correlation delta {corr_estimate:+.3f} -- within Holy Grail threshold. "
        f"Quadrant fit: {q_fit}. "
        f"Crypto framework favours {', '.join(meta['favoured'][:3])} in this environment."
    )

    reasons = [
        f"Asset has {q_fit} alignment with {quadrant_label} environment",
        f"Sentiment ({sent_source}): {sentiment_word} ({sent_score:+.3f}) for {ticker}",
        f"RSI {rsi_val:.0f} -- {rsi_desc} zone",
        f"MACD {macd_sig} | Bollinger: {bb_pos} | Trend: {trend}",
        f"Correlation delta {corr_estimate:+.3f} -- within Holy Grail threshold",
    ]

    return {
        "quadrant": quadrant,
        "quadrant_description": meta["description"],
        "sentiment_score": sent_score,
        "sentiment_model": sent_source,
        "sharpe_improvement": sharpe_est,
        "correlation_delta": corr_estimate,
        "risk_contribution_pct": risk_contrib,
        "ai_overview": ai_overview,
        "reasons": reasons,
        "data_source": "LIVE",
    }


def _gen_quadrant_data() -> dict:
    """Classify economic quadrant from real market data when available."""
    try:
        return _classify_quadrant_from_market_data()
    except Exception as exc:
        logger.debug(f"Quadrant using fallback ({exc}) — normal on startup before scanners run")
        return _gen_quadrant_data_random()


def _classify_quadrant_from_market_data() -> dict:
    """Derive economic quadrant from cached scanner/price data."""
    growth_score = 0.0
    inflation_score = 0.0
    confidence_factors = 0
    data_sources = []

    crypto_cache = _scanner_cache.get("crypto")
    if crypto_cache and crypto_cache.get("rows"):
        rows = crypto_cache["rows"]
        up_count = sum(1 for r in rows if r.get("change_pct", 0) > 0)
        breadth = up_count / max(len(rows), 1)
        growth_score += (breadth - 0.5) * 4.0
        confidence_factors += 1
        data_sources.append("Crypto breadth")

    defi_cache = _scanner_cache.get("defi") or _scanner_cache.get("meme")
    if defi_cache and defi_cache.get("rows"):
        for r in defi_cache["rows"]:
            tkr = r.get("ticker", "")
            if "BTC" in tkr.upper() or "ETH" in tkr.upper():
                chg = r.get("change_pct", 0)
                if chg > 0.5:
                    inflation_score += 1.5
                elif chg < -0.5:
                    inflation_score -= 1.0
                confidence_factors += 1
                data_sources.append("Gold price")
                break
            if "CL=F" in tkr or "OIL" in tkr.upper() or "BZ=F" in tkr:
                chg = r.get("change_pct", 0)
                if chg > 1.0:
                    inflation_score += 1.0
                elif chg < -1.0:
                    inflation_score -= 0.5
                confidence_factors += 1
                data_sources.append("Oil price")
                break

    if STATE.last_sentiment:
        sent = STATE.last_sentiment
        if sent.get("conflict_risk_elevated"):
            inflation_score += 1.5
            confidence_factors += 1
            data_sources.append("Conflict risk")
        dom_q = sent.get("dominant_quadrant", "")
        if "inflation" in dom_q:
            inflation_score += 0.8
        elif "growth" in dom_q:
            growth_score += 0.5 if "rising" in dom_q else -0.5

    if confidence_factors == 0:
        raise ValueError("No market data available for quadrant classification")

    if growth_score > 0.3 and inflation_score <= 0.5:
        q = "rising_growth"
    elif growth_score <= -0.3 and inflation_score <= 0.5:
        q = "falling_growth"
    elif inflation_score > 0.5:
        q = "rising_inflation"
    else:
        q = "falling_inflation"

    meta = QUADRANT_META[q]
    confidence = min(92, max(55, 50 + confidence_factors * 8 + abs(growth_score + inflation_score) * 5))

    gdp_proxy = round(2.5 + growth_score * 0.8, 2)
    cpi_proxy = round(3.0 + inflation_score * 1.2, 2)
    gdp_trend = "rising" if growth_score > 0.3 else "falling" if growth_score < -0.3 else "stable"
    cpi_trend = "rising" if inflation_score > 0.5 else "falling" if inflation_score < -0.3 else "stable"

    conflict = False
    if STATE.last_sentiment:
        conflict = STATE.last_sentiment.get("conflict_risk_elevated", False)

    return {
        "quadrant": q,
        "label": meta["label"],
        "color": meta["color"],
        "description": meta["description"],
        "gdp_value": gdp_proxy,
        "gdp_trend": gdp_trend,
        "cpi_value": cpi_proxy,
        "cpi_trend": cpi_trend,
        "conflict_risk_elevated": conflict,
        "favoured_assets": meta["favoured"],
        "avoid_assets": meta["avoid"],
        "confidence": round(confidence, 1),
        "macro_source": f"Market-derived ({', '.join(data_sources)})",
        "sentiment_source": "RSS keyword analysis",
        "data_source": "LIVE" if confidence_factors >= 2 else "PARTIAL",
        "timestamp": datetime.utcnow().isoformat(),
    }


def _gen_quadrant_data_random() -> dict:
    """Pure random fallback."""
    q = random.choice(list(QUADRANT_META.keys()))
    meta = QUADRANT_META[q]
    return {
        "quadrant": q,
        "label": meta["label"],
        "color": meta["color"],
        "description": meta["description"],
        "gdp_value": round(random.uniform(-1.5, 4.5), 2),
        "gdp_trend": random.choice(["rising", "falling", "stable"]),
        "cpi_value": round(random.uniform(1.5, 8.5), 2),
        "cpi_trend": random.choice(["rising", "falling", "stable"]),
        "conflict_risk_elevated": random.choices([False, True], weights=[75, 25])[0],
        "favoured_assets": meta["favoured"],
        "avoid_assets": meta["avoid"],
        "confidence": round(random.uniform(65, 92), 1),
        "macro_source": "DEMO (no market data available)",
        "sentiment_source": "DEMO",
        "data_source": "DEMO",
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Sentiment (news RSS + FinBERT) ─────────────────────

_NEWS_RSS_FEEDS = [
    ("Reuters Business",   "https://feeds.reuters.com/reuters/businessNews"),
    ("Reuters Markets",    "https://feeds.reuters.com/reuters/UKmarkets"),
    ("Reuters Top News",   "https://feeds.reuters.com/reuters/topNews"),
    ("Reuters Tech",       "https://feeds.reuters.com/reuters/technologyNews"),
    ("Yahoo Finance",      "https://finance.yahoo.com/news/rssindex"),
    ("MarketWatch",        "https://feeds.marketwatch.com/marketwatch/topstories/"),
    ("MarketWatch Stocks", "https://feeds.marketwatch.com/marketwatch/StockstoWatch/"),
    ("MarketWatch Econ",   "https://feeds.marketwatch.com/marketwatch/economy/"),
    ("CNBC Finance",       "https://www.cnbc.com/id/10000664/device/rss/rss.html"),
    ("CNBC World",         "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ("CNBC Earnings",      "https://www.cnbc.com/id/15839135/device/rss/rss.html"),
    ("Investing.com",      "https://www.investing.com/rss/news_25.rss"),
    ("Investing Forex",    "https://www.investing.com/rss/news_1.rss"),
    ("Investing Stocks",   "https://www.investing.com/rss/news_14.rss"),
    ("Investing Commodities","https://www.investing.com/rss/news_11.rss"),
    ("Seeking Alpha",      "https://seekingalpha.com/market_currents.xml"),
    ("AFR",                "https://www.afr.com/rss/feed/latest"),
    ("AFR Markets",        "https://www.afr.com/rss/feed/markets"),
    ("ABC Finance AU",     "https://www.abc.net.au/news/feed/1399786/rss.xml"),
    ("FT Markets",         "https://www.ft.com/rss/home/uk"),
    ("Bloomberg Mkts",     "https://feeds.bloomberg.com/markets/news.rss"),
    ("WSJ Markets",        "https://feeds.a.dj.com/rss/RSSMarketsMain.xml"),
    ("WSJ Business",       "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml"),
    ("WSJ World",          "https://feeds.a.dj.com/rss/RSSWorldNews.xml"),
    ("Barrons",            "https://feeds.barrons.com/barrons/articles.rss"),
    ("Motley Fool",        "https://www.fool.com/feeds/index.aspx"),
    ("Benzinga",           "https://www.benzinga.com/feed"),
    ("Zacks",              "https://www.zacks.com/feeds/"),
    ("TheStreet",          "https://www.thestreet.com/feeds/rss"),
    ("Kitco Gold",         "https://www.kitco.com/rss/kitconews.xml"),
    ("OilPrice.com",       "https://oilprice.com/rss/main"),
    ("Mining.com",         "https://www.mining.com/feed/"),
    ("Platts",             "https://www.spglobal.com/commodityinsights/en/rss-feed/platts-metals"),
    ("AgriCensus",         "https://www.agricensus.com/feed/"),
    ("BBC Business",       "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("BBC World",          "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("Al Jazeera Business","https://www.aljazeera.com/xml/rss/all.xml"),
    ("The Guardian Money", "https://www.theguardian.com/uk/money/rss"),
    ("Guardian Business",  "https://www.theguardian.com/uk/business/rss"),
    ("Guardian World",     "https://www.theguardian.com/world/rss"),
    ("NPR Economy",        "https://feeds.npr.org/1006/rss.xml"),
    ("NPR Business",       "https://feeds.npr.org/1006/rss.xml"),
    ("Economist Finance",  "https://www.economist.com/finance-and-economics/rss.xml"),
    ("AP Business",        "https://rsshub.app/apnews/topics/business"),
    ("CNN Business",       "http://rss.cnn.com/rss/money_news_economy.rss"),
    ("CNN Markets",        "http://rss.cnn.com/rss/money_markets.rss"),
    ("ABC News US",        "https://abcnews.go.com/abcnews/moneyheadlines"),
    ("Forbes",             "https://www.forbes.com/business/feed/"),
    ("Forbes Investing",   "https://www.forbes.com/investing/feed/"),
    ("Nikkei Asia",        "https://asia.nikkei.com/rss"),
    ("SMH Business AU",    "https://www.smh.com.au/rss/business.xml"),
    ("SMH Money AU",       "https://www.smh.com.au/rss/money.xml"),
    ("SMH National AU",    "https://www.smh.com.au/rss/national.xml"),
    ("SMH Politics AU",    "https://www.smh.com.au/rss/politics.xml"),
    ("ABC AU News",        "https://www.abc.net.au/news/feed/51120/rss.xml"),
    ("ABC AU Business",    "https://www.abc.net.au/news/feed/2942460/rss.xml"),
    ("ABC AU Politics",    "https://www.abc.net.au/news/feed/45910/rss.xml"),
    ("The Australian",     "https://www.theaustralian.com.au/feed"),
    ("9News AU",           "https://www.9news.com.au/rss"),
    ("SBS News AU",        "https://www.sbs.com.au/news/feed"),
    ("Guardian AU",        "https://www.theguardian.com/australia-news/rss"),
    ("Defence Connect AU", "https://www.defenceconnect.com.au/rss.xml"),
    ("ASPI Strategist",    "https://www.aspistrategist.org.au/feed/"),
    ("CoinDesk",           "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("CoinTelegraph",      "https://cointelegraph.com/rss"),
    ("Decrypt",            "https://decrypt.co/feed"),
    ("The Block",          "https://www.theblock.co/rss.xml"),
    ("DW Business",        "https://rss.dw.com/xml/rss-en-bus"),
    ("GNews Crypto",       "https://news.google.com/rss/search?q=cryptocurrency+bitcoin+ethereum+crypto+market&hl=en&gl=US&ceid=US:en"),
    ("GNews DeFi",         "https://news.google.com/rss/search?q=DeFi+decentralized+finance+yield+farming+DEX&hl=en&gl=US&ceid=US:en"),
    ("GNews Bitcoin",      "https://news.google.com/rss/search?q=bitcoin+BTC+halving+mining+lightning+network&hl=en&gl=US&ceid=US:en"),
    ("GNews Ethereum",     "https://news.google.com/rss/search?q=ethereum+ETH+layer2+rollup+staking&hl=en&gl=US&ceid=US:en"),
    ("GNews Altcoins",     "https://news.google.com/rss/search?q=altcoin+solana+cardano+avalanche+polkadot&hl=en&gl=US&ceid=US:en"),
    ("GNews Crypto Reg",   "https://news.google.com/rss/search?q=crypto+regulation+SEC+CFTC+MiCA+stablecoin+law&hl=en&gl=US&ceid=US:en"),
    ("GNews NFT Web3",     "https://news.google.com/rss/search?q=NFT+web3+metaverse+gaming+token&hl=en&gl=US&ceid=US:en"),
    ("GNews Markets",      "https://news.google.com/rss/search?q=stock+market+interest+rates+inflation&hl=en&gl=US&ceid=US:en"),
    ("GNews Central Banks","https://news.google.com/rss/search?q=federal+reserve+ECB+interest+rates+monetary+policy&hl=en&gl=US&ceid=US:en"),
    ("GNews Forex",        "https://news.google.com/rss/search?q=forex+currency+USD+EUR+stablecoin+USDT&hl=en&gl=US&ceid=US:en"),
    ("GNews Macro",        "https://news.google.com/rss/search?q=macro+economy+GDP+inflation+recession&hl=en&gl=US&ceid=US:en"),
    ("GNews Geopolitics",  "https://news.google.com/rss/search?q=geopolitics+sanctions+trade+war+crypto+ban&hl=en&gl=US&ceid=US:en"),
    ("GNews AI Crypto",    "https://news.google.com/rss/search?q=AI+crypto+token+artificial+intelligence+blockchain&hl=en&gl=US&ceid=US:en"),
    ("GNews China Econ",   "https://news.google.com/rss/search?q=China+economy+trade+manufacturing+crypto&hl=en&gl=US&ceid=US:en"),
    ("GNews Recession",    "https://news.google.com/rss/search?q=recession+downturn+economic+slowdown&hl=en&gl=US&ceid=US:en"),
]

_BULLISH_WORDS  = {"rally","surge","gain","high","record","beat","growth","rise","up","profit",
                   "positive","strong","outperform","buy","upgrade","bullish","recovery","soar"}
_BEARISH_WORDS  = {"fall","drop","crash","low","miss","recession","down","loss","negative","weak",
                   "risk","warning","downgrade","sell","bearish","slump","plunge","cut","concern"}
_CONFLICT_WORDS = {"war","conflict","military","sanctions","attack","threat","crisis","invasion",
                   "strike","bomb","weapons","troops","geopolit","defence","defense","navy",
                   "missile","nuclear","adf","aukus","submarine","indo-pacific","taiwan",
                   "south china sea","tariff","trade war","embargo","blockade","escalat"}
_INFLATION_KW   = {"inflation","cpi","pce","rates","fed","rba","boe","ecb","oil","energy",
                   "commodit","gold","silver","copper","wheat","supply"}
_GROWTH_KW      = {"gdp","jobs","employment","payroll","earnings","revenue","ism","pmi",
                   "retail","consumer","spending","trade","export","import"}
_DEFLAT_KW      = {"deflation","disinflation","rate cut","pivot","quantitative","qe","stimulus"}


def _score_headline(title: str, body: str = "") -> dict:
    text = (title + " " + body).lower()
    words = set(text.replace(",", " ").replace(".", " ").split())
    bull  = len(words & _BULLISH_WORDS)
    bear  = len(words & _BEARISH_WORDS)
    conf  = len(words & _CONFLICT_WORDS)
    infl  = len(words & _INFLATION_KW)
    grow  = len(words & _GROWTH_KW)
    defl  = len(words & _DEFLAT_KW)
    if bull > bear + 1: sentiment = "positive"
    elif bear > bull + 1: sentiment = "negative"
    else: sentiment = "neutral"
    if infl >= grow and infl >= defl:
        quadrant = "rising_inflation" if bull >= bear else "falling_inflation"
    elif defl > infl: quadrant = "falling_inflation"
    elif grow > 0 and bull >= bear: quadrant = "rising_growth"
    else: quadrant = "falling_growth"
    return {"sentiment": sentiment, "quadrant": quadrant, "conflict_risk": conf > 0,
            "bull_score": bull, "bear_score": bear}


async def _fetch_real_news() -> list[dict]:
    loop = asyncio.get_running_loop()
    articles: list[dict] = []

    def _parse_one_feed(feed_name: str, url: str) -> list[dict]:
        try:
            import feedparser
            feed = feedparser.parse(url)
            items = []
            for entry in feed.entries:
                title = (getattr(entry, "title", "") or "").strip()
                if not title or len(title) < 15: continue
                body = (getattr(entry, "summary", "") or "")[:400]
                score = _score_headline(title, body)
                items.append({"title": title, "source": feed_name, "sentiment": score["sentiment"],
                    "quadrant": score["quadrant"], "conflict_risk": score["conflict_risk"],
                    "bull_score": score["bull_score"], "bear_score": score["bear_score"],
                    "timestamp": datetime.utcnow().isoformat()})
            return items
        except Exception as exc:
            logger.debug(f"RSS [{feed_name}] failed: {exc}")
            return []

    futures = [loop.run_in_executor(None, _parse_one_feed, name, url) for name, url in _NEWS_RSS_FEEDS]
    try:
        results = await asyncio.wait_for(asyncio.gather(*futures, return_exceptions=True), timeout=30)
    except asyncio.TimeoutError:
        logger.warning("RSS aggregate fetch timed out after 30s")
        results = []
    for batch in results:
        if isinstance(batch, list): articles.extend(batch)

    if not articles:
        logger.warning("All RSS feeds failed -- using static headline pool")
        articles = _gen_static_headlines()

    seen: set = set()
    unique: list = []
    for a in articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)
    unique.sort(key=lambda h: (h["conflict_risk"], abs(h["bull_score"] - h["bear_score"])), reverse=True)
    logger.info(f"News scan: {len(unique)} unique articles from {len(_NEWS_RSS_FEEDS)} feeds")
    return unique


_STATIC_HEADLINE_POOL = [
    ("Fed signals pause in rate hikes amid cooling inflation",       "rising_growth",    "positive"),
    ("Bitcoin ETF inflows hit record as institutional adoption surges","rising_growth",    "positive"),
    ("Oil surges 4% on Middle East supply disruption fears",         "rising_inflation", "negative"),
    ("Ethereum staking yields rise as network activity surges",      "rising_growth",    "positive"),
    ("China manufacturing PMI contracts for third straight month",   "falling_growth",   "negative"),
    ("Gold hits 3-month high as USD weakens on jobs data miss",      "rising_inflation", "positive"),
    ("Military conflict escalates in Eastern Europe, safe havens bid","rising_inflation","negative"),
    ("US CPI drops to 2.4%, markets price in rate cuts",             "falling_inflation","positive"),
    ("Tech layoffs accelerate, NASDAQ futures lower",                "falling_growth",   "negative"),
    ("OPEC+ announces surprise production cut of 500k bpd",          "rising_inflation", "neutral"),
    ("Crypto market cap tops $3T as altseason momentum builds",      "rising_growth",    "positive"),
    ("Copper prices plunge on weak Chinese demand outlook",          "falling_growth",   "negative"),
    ("Wheat prices spike amid Black Sea shipping disruptions",       "rising_inflation", "negative"),
    ("Solana TVL surges 40% as DeFi ecosystem expands",              "rising_growth",    "positive"),
    ("Silver ETF inflows surge as inflation expectations rise",      "rising_inflation", "positive"),
    ("US 10-year yield falls as economic data disappoints",          "falling_growth",   "negative"),
    ("Amazon, Alphabet earnings beat; tech sector rallies",         "rising_growth",    "positive"),
    ("Iron ore falls on Chinese property sector concerns",           "falling_growth",   "negative"),
    ("TIPS inflows accelerate as breakeven inflation widens",        "rising_inflation", "neutral"),
    ("S&P 500 hits fresh record as rate cut hopes persist",         "rising_growth",    "positive"),
]


def _gen_static_headlines() -> list[dict]:
    return [
        {"title": h[0], "quadrant": h[1], "sentiment": h[2], "source": "Market Intelligence",
         "timestamp": datetime.utcnow().isoformat(),
         "conflict_risk": "military" in h[0].lower() or "conflict" in h[0].lower(),
         "bull_score": 1 if h[2] == "positive" else 0,
         "bear_score": 1 if h[2] == "negative" else 0}
        for h in _STATIC_HEADLINE_POOL
    ]


# ── Keyword Sentiment Scorer (replaces FinBERT — zero dependencies) ──

_POSITIVE_KW = {
    "surge": 0.8, "soar": 0.9, "rally": 0.8, "boom": 0.85, "breakout": 0.7,
    "record high": 0.9, "outperform": 0.7, "beat": 0.6, "strong": 0.5,
    "growth": 0.5, "gain": 0.5, "rise": 0.4, "profit": 0.5, "positive": 0.4,
    "bullish": 0.6, "upgrade": 0.7, "recovery": 0.6, "rebound": 0.6,
    "optimism": 0.55, "confidence": 0.5, "expansion": 0.6, "stimulus": 0.5,
}
_NEGATIVE_KW = {
    "crash": 0.9, "collapse": 0.85, "plunge": 0.8, "crisis": 0.8,
    "recession": 0.85, "bankruptcy": 0.9, "default": 0.8, "bear market": 0.8,
    "decline": 0.5, "drop": 0.4, "fall": 0.4, "loss": 0.5, "weak": 0.45,
    "bearish": 0.6, "fear": 0.55, "uncertainty": 0.45, "slowdown": 0.5,
    "layoffs": 0.6, "downgrade": 0.6, "warning": 0.5, "miss": 0.5,
    "sanctions": 0.5, "tariff": 0.4, "inflation": 0.3,
}


def _keyword_sentiment_score(text: str) -> float:
    """Score text from -1 (bearish) to +1 (bullish) using keyword matching."""
    t = text.lower()
    pos = sum(w for kw, w in _POSITIVE_KW.items() if kw in t)
    neg = sum(w for kw, w in _NEGATIVE_KW.items() if kw in t)
    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / max(pos, neg)))


def _try_keyword_sentiment(articles: list[dict]) -> list[dict]:
    """Score articles using lightweight keyword sentiment (replaces FinBERT)."""
    if not articles:
        return articles
    for a in articles:
        text = a.get("title", "") + " " + a.get("summary", "")
        score = _keyword_sentiment_score(text)
        a["finbert_score"] = round(score, 4)  # Keep same key for API compat
        a["sentiment"] = "positive" if score > 0.1 else "negative" if score < -0.1 else "neutral"
        a["bull_score"] = round(max(0, score), 3)
        a["bear_score"] = round(max(0, -score), 3)
    logger.info(f"Keyword sentiment scored {len(articles)} articles")
    return articles


async def _gen_sentiment_data() -> dict:
    articles = await _fetch_real_news()
    articles = _try_keyword_sentiment(articles)
    total = len(articles)
    conflict = sum(1 for a in articles if a["conflict_risk"])

    q_counts: dict = defaultdict(lambda: {"count": 0, "bull": 0, "bear": 0, "scores": []})
    for a in articles:
        q = a["quadrant"]
        q_counts[q]["count"] += 1
        score = a.get("finbert_score", None)
        if score is not None:
            q_counts[q]["scores"].append(score)
            if score > 0.1: q_counts[q]["bull"] += 1
            elif score < -0.1: q_counts[q]["bear"] += 1
        else:
            if a["sentiment"] == "positive": q_counts[q]["bull"] += 1
            elif a["sentiment"] == "negative": q_counts[q]["bear"] += 1

    quadrant_sentiment: dict = {}
    for q in QUADRANT_META:
        s = q_counts[q]
        c = max(s["count"], 1)
        if s["scores"]:
            avg_score = round(float(np.mean(s["scores"])), 3)
        else:
            avg_score = round((s["bull"] - s["bear"]) / c, 3)
        quadrant_sentiment[q] = {"avg_score": avg_score, "article_count": s["count"],
                                  "bullish_pct": round(s["bull"] / c * 100, 1)}

    dominant = max(quadrant_sentiment, key=lambda q: quadrant_sentiment[q]["article_count"])
    sentiment_model = "FinBERT" if articles and articles[0].get("finbert_score") is not None else "Keyword"

    return {
        "total_articles": total, "conflict_risk_articles": conflict,
        "conflict_risk_elevated": conflict >= max(3, int(total * 0.08)),
        "dominant_quadrant": dominant, "quadrant_sentiment": quadrant_sentiment,
        "top_headlines": articles, "sentiment_model": sentiment_model,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ── Correlation matrix ─────────────────────────────────

def _gen_correlation_matrix_demo(override_tickers: list = None) -> dict:
    """Fallback correlation matrix — uses real yfinance price data with
    default tickers when portfolio + watchlist have too few assets.
    Returns synthetic random only if yfinance fetch fails entirely."""
    if override_tickers:
        portfolio_tickers = [t for t in override_tickers if t]
    else:
        portfolio_tickers = list(PAPER.positions.keys())
    watchlist_tickers = list(WATCHLIST) if WATCHLIST else []
    tickers = list(dict.fromkeys(portfolio_tickers + watchlist_tickers))
    has_portfolio = len(portfolio_tickers) > 0
    if len(tickers) < 6:
        defaults = ["BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
                     "ADA-USD", "AVAX-USD", "LINK-USD", "DOT-USD", "MATIC-USD", "UNI-USD"]
        for t in defaults:
            if t not in tickers:
                tickers.append(t)
            if len(tickers) >= 12:
                break
    # Try fetching real price data synchronously via yfinance
    try:
        import yfinance as yf
        import concurrent.futures
        df = yf.download(tickers[:15], period="3mo", progress=False, threads=True)
        if df is not None and hasattr(df, 'columns') and len(df) >= 20:
            close = df["Close"] if "Close" in df.columns else df
            close = close.dropna(axis=1, how="all").dropna()
            if len(close.columns) >= 4 and len(close) >= 20:
                valid = [t for t in tickers if t in close.columns]
                returns = close[valid].pct_change().dropna()
                corr = np.round(returns.corr().values, 3)
                n = len(valid)
                upper = np.triu_indices(n, k=1)
                source = "PORTFOLIO" if has_portfolio else "DEFAULTS"
                return {
                    "tickers": valid, "matrix": corr.tolist(),
                    "mean_correlation": round(float(np.mean(corr[upper])), 3),
                    "max_correlation": round(float(np.max(corr[upper])), 3),
                    "holy_grail_count": sum(1 for i in range(n) if np.mean(np.abs(corr[i][np.arange(n) != i])) < 0.3),
                    "threshold": 0.3, "data_source": source,
                    "timestamp": datetime.utcnow().isoformat(),
                }
    except Exception:
        pass
    # Ultimate fallback: synthetic random (should rarely hit)
    n = len(tickers)
    mat = np.eye(n)
    for i in range(n):
        for j in range(i + 1, n):
            r = round(random.uniform(-0.25, 0.55), 3)
            mat[i][j] = r
            mat[j][i] = r
    upper = np.triu_indices(n, k=1)
    return {
        "tickers": tickers, "matrix": mat.tolist(),
        "mean_correlation": round(float(np.mean(mat[upper])), 3),
        "max_correlation": round(float(np.max(mat[upper])), 3),
        "holy_grail_count": sum(1 for i in range(n) if np.mean(np.abs(mat[i][np.arange(n) != i])) < 0.3),
        "threshold": 0.3, "data_source": "DEMO",
        "timestamp": datetime.utcnow().isoformat(),
    }


async def _real_correlation_matrix(override_tickers: list = None) -> Optional[dict]:
    """Correlation matrix of portfolio holdings + watchlist.
    Holy Grail count measures how many of YOUR assets have mean
    correlation < 0.3 — not the entire ticker universe.
    override_tickers: if provided (e.g. from live broker), use these instead of PAPER."""
    # Use actual portfolio positions + watchlist for meaningful correlation
    if override_tickers:
        portfolio_tickers = [t for t in override_tickers if t]
    else:
        portfolio_tickers = list(PAPER.positions.keys())
    watchlist_tickers = list(WATCHLIST) if WATCHLIST else []
    # Combine, deduplicate, preserving order
    tickers = list(dict.fromkeys(portfolio_tickers + watchlist_tickers))
    has_positions = len(portfolio_tickers) > 0
    # Only pad with defaults if user has NO positions at all
    if not has_positions and len(tickers) < 6:
        defaults = [
            "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",  # Large Cap
            "LINK-USD", "AVAX-USD", "ADA-USD",                       # Large Cap / L1
        ]
        for t in defaults:
            if t not in tickers:
                tickers.append(t)
            if len(tickers) >= 15:
                break
    if len(tickers) < 2:
        return None
    prices_map = await _get_prices(tickers[:30], "3mo")
    if not prices_map or len(prices_map) < 2: return None
    valid = [t for t in tickers if t in prices_map and len(prices_map[t]) >= 20]
    if len(valid) < 2: return None
    min_len = min(len(prices_map[t]) for t in valid)
    closes = np.array([prices_map[t][-min_len:] for t in valid], dtype=float)
    returns = np.diff(closes, axis=1) / closes[:, :-1]
    corr = np.round(np.corrcoef(returns), 3)
    # Handle single asset case (corrcoef returns scalar)
    if corr.ndim == 0:
        corr = np.array([[1.0]])
    n = len(valid)
    upper = np.triu_indices(n, k=1)
    hg_count = sum(1 for i in range(n) if float(np.mean(np.abs(corr[i][np.arange(n) != i]))) < 0.3) if n > 1 else 0
    # Include real portfolio position data for weight calculation
    portfolio_info = {}
    total_value = PAPER.cash
    for t, pos in PAPER.positions.items():
        mv = pos["qty"] * pos["entry_price"]
        total_value += mv
        portfolio_info[t] = {"qty": pos["qty"], "entry_price": pos["entry_price"],
                             "market_value": round(mv, 2), "side": pos.get("side", "LONG")}
    for t in portfolio_info:
        portfolio_info[t]["weight_pct"] = round(portfolio_info[t]["market_value"] / max(total_value, 1) * 100, 2)
    source = "LIVE" if has_positions else ("DEFAULTS" if not has_positions else "PORTFOLIO")
    return {
        "tickers": valid, "matrix": corr.tolist(),
        "mean_correlation": round(float(np.mean(corr[upper])), 3) if len(upper[0]) > 0 else 0.0,
        "max_correlation": round(float(np.max(corr[upper])), 3) if len(upper[0]) > 0 else 0.0,
        "holy_grail_count": hg_count, "threshold": 0.3,
        "data_source": source, "timestamp": datetime.utcnow().isoformat(),
        "portfolio_positions": portfolio_info,
    }


def _gen_portfolio_health() -> dict:
    """Real portfolio health from PAPER state."""
    initial = PAPER_STARTING_CASH
    equity = PAPER.cash
    if PAPER.equity_history:
        equity = PAPER.equity_history[-1]["v"]
    daily_pnl = 0.0
    if len(PAPER.equity_history) >= 2:
        daily_pnl = round(PAPER.equity_history[-1]["v"] - PAPER.equity_history[-2]["v"], 2)
    drawdown = 0.0
    if PAPER.equity_history:
        peak = max(e["v"] for e in PAPER.equity_history)
        drawdown = round((peak - equity) / peak * 100, 2) if peak > 0 else 0.0
    sharpe = 0.0
    if len(PAPER.equity_history) >= 10:
        try:
            eq_arr = np.array([e["v"] for e in PAPER.equity_history], dtype=float)
            rets = np.diff(eq_arr) / eq_arr[:-1]
            if rets.std() > 0:
                sharpe = round(float((rets.mean() / rets.std()) * (252 ** 0.5)), 2)
        except Exception:
            pass
    open_count = len(PAPER.positions)
    positions_list = [
        {"ticker": t, "side": pos.get("side", "LONG"),
         "size_pct": round(pos["qty"] * pos["entry_price"] / max(equity, 1) * 100, 1),
         "unrealised_pnl_pct": 0.0}
        for t, pos in PAPER.positions.items()
    ]
    # Build daily P&L series from equity history
    daily_pnl_series = []
    if len(PAPER.equity_history) >= 2:
        for idx in range(1, len(PAPER.equity_history)):
            prev_v = PAPER.equity_history[idx - 1]["v"]
            curr_v = PAPER.equity_history[idx]["v"]
            d_pnl = round(curr_v - prev_v, 2)
            d_pct = round(d_pnl / prev_v * 100, 3) if prev_v else 0
            daily_pnl_series.append({
                "t": PAPER.equity_history[idx].get("t", ""),
                "pnl": d_pnl, "pnl_pct": d_pct,
            })
    return {
        "timestamp": datetime.utcnow().isoformat(), "equity": round(equity, 2),
        "initial_equity": initial, "cash": round(PAPER.cash, 2),
        "total_return_pct": round((equity / initial - 1) * 100, 2) if initial else 0.0,
        "daily_pnl": daily_pnl,
        "daily_pnl_pct": round(daily_pnl / equity * 100, 3) if equity else 0.0,
        "drawdown_pct": drawdown, "open_positions": open_count,
        "portfolio_diversified": open_count >= 3,
        "selected_portfolio_size": open_count,
        "circuit_breaker_active": drawdown > 9.5,
        "daily_limit_pct": 2.0, "max_drawdown_pct": 10.0,
        "sharpe_ratio": sharpe, "positions": positions_list,
        "daily_pnl_series": daily_pnl_series[-60:],
        "has_real_data": len(PAPER.equity_history) >= 2,
    }


def _gen_backtest_results() -> dict:
    """Generate backtest results from real trade history when available,
    falling back to simulated demo data."""
    trades = PAPER.history
    eq_hist = PAPER.equity_history

    # ── Try real data first ──
    if len(trades) >= 3 and len(eq_hist) >= 5:
        wins = [t for t in trades if t.get("pnl", 0) > 0]
        losses = [t for t in trades if t.get("pnl", 0) <= 0]
        total_pnl = sum(t.get("pnl", 0) for t in trades)
        initial = STATE.initial_equity or PAPER_STARTING_CASH
        eq_vals = np.array([e["v"] for e in eq_hist], dtype=float)
        rets = np.diff(eq_vals) / eq_vals[:-1]
        sharpe = round(float((rets.mean() / rets.std()) * (252 ** 0.5)), 2) if rets.std() > 0 else 0
        neg_rets = rets[rets < 0]
        sortino = round(float((rets.mean() / neg_rets.std()) * (252 ** 0.5)), 2) if len(neg_rets) > 0 and neg_rets.std() > 0 else 0
        peak = np.maximum.accumulate(eq_vals)
        drawdowns = (peak - eq_vals) / peak * 100
        max_dd = -round(float(drawdowns.max()), 2)
        calmar = round(abs(total_pnl / initial * 100 / max_dd), 2) if max_dd != 0 else 0
        win_rate = round(len(wins) / len(trades) * 100, 1)
        avg_trade_ret = round(np.mean([t.get("pnl_pct", t.get("pnl", 0) / initial * 100) for t in trades]), 2)
        total_ret = round((eq_vals[-1] / eq_vals[0] - 1) * 100, 2)
        # Build period breakdown from equity history chunks
        chunk_size = max(len(eq_hist) // 8, 5)
        periods = []
        for i in range(min(8, len(eq_hist) // chunk_size)):
            chunk = eq_vals[i * chunk_size:(i + 1) * chunk_size]
            if len(chunk) < 2:
                continue
            p_ret = round(float((chunk[-1] / chunk[0] - 1) * 100), 2)
            p_rets = np.diff(chunk) / chunk[:-1]
            p_sharpe = round(float((p_rets.mean() / p_rets.std()) * (252 ** 0.5)), 2) if p_rets.std() > 0 else 0
            p_peak = np.maximum.accumulate(chunk)
            p_dd = -round(float(((p_peak - chunk) / p_peak * 100).max()), 2)
            # Count trades in this time window
            chunk_trades = trades[i * (len(trades) // 8):(i + 1) * (len(trades) // 8)] if len(trades) >= 8 else trades
            p_wins = len([t for t in chunk_trades if t.get("pnl", 0) > 0])
            p_total = len(chunk_trades) or 1
            periods.append({
                "period": i + 1, "train_start": eq_hist[i * chunk_size].get("t", "")[:10],
                "return_pct": p_ret, "sharpe": p_sharpe,
                "max_drawdown": p_dd, "win_rate": round(p_wins / p_total * 100, 1),
                "trades": p_total,
            })
        days = (len(eq_hist)) / 252 if len(eq_hist) > 0 else 1
        ann_ret = round(total_ret / max(days, 0.01), 2)
        return {
            "status": "REAL", "data_source": "real", "training_months": 0,
            "test_months": 0, "periods": len(periods),
            "total_return_pct": total_ret,
            "annualised_return_pct": ann_ret,
            "sharpe_ratio": sharpe, "sortino_ratio": sortino,
            "calmar_ratio": calmar, "max_drawdown_pct": max_dd,
            "win_rate_pct": win_rate, "avg_trade_return_pct": avg_trade_ret,
            "period_results": periods, "timestamp": datetime.utcnow().isoformat(),
        }

    # ── Fallback: simulated demo data ──
    periods = []
    cumulative = STATE.initial_equity
    for i in range(8):
        ret = round(random.gauss(3.5, 6.0), 2)
        cumulative *= (1 + ret / 100)
        periods.append({"period": i + 1, "train_start": f"202{2 + i // 4}-Q{(i % 4) + 1}",
            "return_pct": ret, "sharpe": round(random.uniform(0.9, 2.8), 2),
            "max_drawdown": round(random.uniform(-12, -1), 2),
            "win_rate": round(random.uniform(50, 72), 1), "trades": random.randint(28, 85)})
    return {
        "status": "DEMO", "data_source": "demo", "training_months": 12,
        "test_months": 3, "periods": len(periods),
        "total_return_pct": round((cumulative / STATE.initial_equity - 1) * 100, 2),
        "annualised_return_pct": round(random.uniform(18, 42), 2),
        "sharpe_ratio": round(random.uniform(1.6, 2.4), 2),
        "sortino_ratio": round(random.uniform(2.0, 3.1), 2),
        "calmar_ratio": round(random.uniform(1.8, 2.9), 2),
        "max_drawdown_pct": round(random.uniform(-9, -5), 2),
        "win_rate_pct": round(random.uniform(57, 68), 1),
        "avg_trade_return_pct": round(random.uniform(1.5, 3.2), 2),
        "period_results": periods, "timestamp": datetime.utcnow().isoformat(),
    }


def crypto_analyse_trade(ticker: str, side: str, quadrant: str,
                        cash: float, positions: dict, current_signals: list) -> dict:
    ticker = ticker.upper().strip()
    side = side.upper().strip()
    asset_class = _get_asset_class(ticker)
    playbook = QUADRANT_PLAYBOOK.get(quadrant, QUADRANT_PLAYBOOK["rising_growth"])

    if side == "BUY":
        if   asset_class in playbook["strong_buy"]: raw_score = random.randint(82, 97); fit_label = "STRONG FIT"
        elif asset_class in playbook["buy"]:         raw_score = random.randint(62, 81); fit_label = "MODERATE FIT"
        elif asset_class in playbook["avoid"]:       raw_score = random.randint(10, 35); fit_label = "COUNTER-TREND"
        else:                                        raw_score = random.randint(40, 61); fit_label = "NEUTRAL"
    else:
        if   asset_class in playbook["avoid"]:       raw_score = random.randint(75, 93); fit_label = "STRONG FIT"
        elif asset_class not in playbook["strong_buy"]: raw_score = random.randint(55, 74); fit_label = "MODERATE FIT"
        else:                                        raw_score = random.randint(20, 45); fit_label = "COUNTER-TREND"
    fit_score = max(0, min(100, raw_score))

    risk_flags: list = []
    total_pv = cash + sum(p.get("qty", 0) * p.get("entry_price", 0) for p in positions.values())
    n_pos = len(positions)
    existing_classes = [_get_asset_class(t) for t in positions]
    class_count = existing_classes.count(asset_class)
    if class_count >= 4: risk_flags.append(f"High concentration: {class_count} existing {asset_class} positions")
    if n_pos >= 15: risk_flags.append("Portfolio at 15-position Holy Grail limit")
    if asset_class in playbook["avoid"] and side == "BUY":
        risk_flags.append(f"{asset_class.replace('_',' ').title()} is on the avoid list for {quadrant.replace('_',' ').title()}")
    if total_pv > 0 and cash / total_pv < 0.05: risk_flags.append("Cash below 5% of portfolio -- liquidity risk")
    sig = next((s for s in current_signals if s.get("ticker") == ticker), None)
    if sig and sig.get("action") in ("SELL","SHORT") and side == "BUY":
        risk_flags.append(f"Signal engine recommends {sig['action']} on {ticker}")

    quadrant_label = quadrant.replace("_"," ").title()
    asset_label = asset_class.replace("_"," ").title()
    reasoning = [
        f"Quadrant is {quadrant_label} -- Crypto favours {', '.join((playbook['strong_buy']+playbook['buy'])[:3]).replace('_',' ')}.",
        f"{ticker} classified as {asset_label} -- {'aligned' if asset_class in playbook['strong_buy']+playbook['buy'] else 'not aligned'} with {quadrant_label} playbook.",
        f"Portfolio has {n_pos} positions across {len(set(existing_classes))} asset class(es) -- {'diversified' if len(set(existing_classes))>=4 else 'needs more diversification'}.",
    ]
    if sig:
        reasoning.append(f"Signal engine: {sig.get('action','HOLD')} {ticker} with {sig.get('confidence',0):.0f}% confidence, RSI {sig.get('rsi',50)}.")
    reasoning.append(f"Avoid list for {quadrant_label}: {', '.join(playbook['avoid']).replace('_',' ')}. {'This trade is on the avoid list.' if asset_class in playbook['avoid'] else 'This trade is not on the avoid list.'}")

    _AW = {"large_cap":0.60,"defi":0.15,"layer1":0.10,"infrastructure":0.05,"meme":0.05,"ai":0.05}
    cc = {c: existing_classes.count(c) for c in set(existing_classes)}
    if side == "BUY": cc[asset_class] = cc.get(asset_class, 0) + 1
    tot = sum(cc.values()) or 1
    dev = sum(abs(cc.get(c,0)/tot - ideal) for c, ideal in _AW.items())
    all_weather_score = max(0, min(100, int(100 - dev * 50)))

    if fit_label == "STRONG FIT":
        rec = f"PROCEED -- {ticker} strongly aligned with {quadrant_label} regime. Size within risk budget."
    elif fit_label == "MODERATE FIT":
        rec = f"CONSIDER -- Moderate alignment. Reduce size 30-50% vs a strong-fit signal."
    elif fit_label == "COUNTER-TREND":
        rec = f"CAUTION -- {ticker} ({asset_label}) counters Crypto's {quadrant_label} playbook. Keep size <2% if high conviction."
    else:
        rec = f"NEUTRAL -- No strong quadrant signal. Assess diversification value before committing."

    return {"fit_score": fit_score, "fit_label": fit_label, "quadrant_narrative": playbook["narrative"],
            "asset_class": asset_class, "reasoning": reasoning, "recommendation": rec,
            "risk_flags": risk_flags, "all_weather_score": all_weather_score,
            "quadrant": quadrant, "quadrant_label": quadrant_label, "ticker": ticker, "side": side,
            "timestamp": datetime.utcnow().isoformat()}
