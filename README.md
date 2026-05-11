# 0xrex — Autonomous Crypto Trading System

> Free, autonomous AI trading system for 50+ crypto assets. Built on the Ultra Ruleset synthesised from CryptoCred's TA Manual and GCR's Pearls of Wisdom.

![Status](https://img.shields.io/badge/status-operational-brightgreen)
![Price](https://img.shields.io/badge/price-FREE-22c55e)
![Open Source](https://img.shields.io/badge/open%20source-yes-22c55e)
![Platforms](https://img.shields.io/badge/platforms-Windows%20%7C%20Linux%20%7C%20macOS-orange)
![Stack](https://img.shields.io/badge/stack-Python%20%2B%20FastAPI%20%2B%20Chart.js-cyan)

---

## What Is It?

0xrex is a free, open-source autonomous crypto trading system built around CryptoCred's technical analysis framework and GCR's contrarian wisdom — synthesised into the **Ultra Ruleset** for crypto markets.

It scans 50+ crypto assets across major L1s, DeFi tokens, L2 tokens, and meme coins on 15-minute cycles, 24/7 UTC. It generates trade signals, manages risk, enforces GCR portfolio allocation rules, and runs autonomously from a single terminal-style UI (orange/black theme).

The system classifies markets into 5 regimes — Bull Trend, Bear Trend, Accumulation, Distribution, and Ranging — and scores every signal against the current regime so it naturally shifts toward the right positions for the conditions.

**100% free and open source. No subscriptions. No hidden fees. No paywalls.**

---

## Quick Start

```bash
git clone https://github.com/defthrets/crypto-trading-system.git
cd crypto-trading-system
pip install -r requirements.txt
python run_ui.bat   (or: python -m uvicorn main:app --port 8000)
# Open http://localhost:8000
```

---

## 7 Tabs

| Tab | What It Does |
|-----|-------------|
| **Dashboard** | Portfolio overview, equity curve, regime indicator, AI recommendations, activity feed |
| **Signals** | AI-generated trade signals with confidence scores, stop-loss, take-profit, CryptoCred justification |
| **Crypto Scanner** | 50+ crypto assets scanned on 15-min cycles — BTC, ETH, SOL, major L1s, DeFi, L2s, meme coins |
| **DeFi** | DeFi token analysis, yield opportunities, protocol risk scoring |
| **Meme Coins** | High-volatility meme coin scanner with GCR sentiment inversion filters |
| **Backtesting** | Walk-forward backtesting across historical periods and market regimes |
| **Settings** | Risk config, portfolio allocation rules, scan intervals, notifications, display options |

---

## Ultra Ruleset — Two Frameworks, One System

### CryptoCred Technical Analysis

The CryptoCred framework provides the structural backbone for all signal generation:

- **Market Structure** — Higher highs / higher lows (bullish) vs lower lows / lower highs (bearish) to establish directional bias
- **Directional Bias** — Only take trades in the direction of the prevailing structure
- **Support / Resistance Zones** — Key levels where price has previously reversed, used for entries and exits
- **Entry Triggers** — Confirmation candles, break-and-retest, engulfing patterns at S/R zones
- **RSI Divergence** — Bullish and bearish divergence as early reversal signals
- **Fibonacci Golden Zone** — 0.618-0.786 retracement as the optimal pullback entry region

### GCR Contrarian Wisdom (Pearls of Wisdom)

GCR's philosophy overlays a contrarian filter on every signal:

- **Tree of Life** — Bet against consensus; when everyone is bullish, prepare for the reversal
- **Reflexivity** — Narratives drive price which reinforces narratives; identify when loops are exhausting
- **Sentiment Inversion** — Extreme greed signals caution, extreme fear signals opportunity
- **Risk Scaling** — Size positions inversely to crowd confidence

---

## 5 Market Regimes

| Regime | Condition | 0xrex Favours |
|--------|-----------|---------------|
| **Bull Trend** | HH/HL structure, rising momentum | Large positions in BTC, ETH, high-beta alts |
| **Bear Trend** | LL/LH structure, falling momentum | Stablecoin heavy, small short positions, defensive sizing |
| **Accumulation** | Range-bound after downtrend, smart money loading | Gradual entries at support, DCA into majors |
| **Distribution** | Range-bound after uptrend, smart money unloading | Reduce exposure, tighten stops, increase stablecoin allocation |
| **Ranging** | No clear structure, choppy price action | Minimal activity, range-trade S/R levels only |

0xrex detects the current regime from live market data and scores every signal against it. A buy signal on a high-beta altcoin scores higher in a Bull Trend than in Distribution. A GCR sentiment inversion alert carries more weight when the regime is shifting.

---

## GCR Portfolio Allocation Rules

| Asset Class | Rule |
|-------------|------|
| **BTC** | Minimum 40% of portfolio |
| **ETH** | Minimum 20% of portfolio |
| **Altcoins** | Maximum 30% of portfolio |
| **Stablecoins** | Minimum 10% of portfolio (cash reserve) |

These rules are enforced at all times. The system will not generate signals that would violate allocation limits. In Bear Trend and Distribution regimes, stablecoin allocation automatically increases beyond the 10% floor.

---

## How It Works

1. **Regime Engine** detects the current market regime from live price structure and momentum indicators
2. **CryptoCred Signal Engine** generates signals from market structure, S/R zones, RSI divergence, and Fibonacci levels — scored against the current regime
3. **GCR Contrarian Filter** overlays sentiment inversion and reflexivity checks to filter out crowded trades
4. **Portfolio Allocator** sizes positions according to GCR allocation rules and correlation-based diversification
5. **Circuit Breaker** halts trading if daily loss or drawdown limits are hit
6. **Autonomous Agent** runs the full cycle on 15-min scan intervals, 24/7 UTC — scan, signal, size, execute, notify

---

## 50+ Crypto Assets

**Major L1s** — BTC, ETH, SOL, ADA, AVAX, DOT, ATOM, NEAR, SUI, APT, SEI, INJ, TIA

**DeFi Tokens** — UNI, AAVE, MKR, CRV, LDO, PENDLE, GMX, DYDX, SNX, COMP, SUSHI

**L2 Tokens** — ARB, OP, MATIC, STRK, ZK, MANTA, METIS, IMX

**Meme Coins** — DOGE, SHIB, PEPE, WIF, BONK, FLOKI, MEME, TURBO

**Other** — LINK, FIL, RENDER, GRT, FET, ONDO, TIA, JUP, PYTH

---

## Key Features

- **24/7 UTC Scheduling** — Crypto never sleeps, neither does 0xrex
- **15-Minute Scan Cycles** — Every asset re-evaluated on a 15-min loop
- **Correlation-Based Diversification** — Avoids overexposure to correlated assets
- **Circuit Breaker** — Auto-halts trading on drawdown or daily loss limits
- **Paper Trading** — Risk-free simulated trading with full analytics before going live
- **Real-Time WebSocket Updates** — Live price feeds and signal notifications pushed to the UI
- **Terminal UI** — Orange/black themed interface, 7 tabs, designed for focused trading

---

## Tech Stack

Python, FastAPI, Chart.js, yfinance, APScheduler, NumPy, Pandas, WebSocket

---

## Disclaimer

Educational and research purposes only. Not financial advice. Algorithmic signals are not guarantees. You can lose money trading crypto. Always do your own research. Past performance means nothing.

---

**Repo:** [github.com/defthrets/crypto-trading-system](https://github.com/defthrets/crypto-trading-system)

---
