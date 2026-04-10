"""
CryptoBot -- Market Scanning
Scanner cache, ticker universes, market data fetching (crypto assets),
market summary, live price lookups.
"""

import asyncio
import random
import numpy as np
from datetime import datetime
from typing import Optional

from loguru import logger

from api.utils import (
    _cache_get, _cache_set, _get_prices, _fmt_vol, _EXECUTOR,
    YF_AVAILABLE, SOURCE_LIMITER,
)
from api.state import WATCHLIST


# ── Ticker Universes ────────────────────────────────────

# Large Cap Crypto (Top 20 by market cap)
LARGE_CAP_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "MATIC-USD",
    "ATOM-USD", "UNI-USD", "LTC-USD", "BCH-USD", "NEAR-USD",
    "APT-USD", "SUI-USD", "FIL-USD", "ICP-USD", "HBAR-USD",
]

# Keep ASX_TICKERS as alias for backward compat with server.py references
ASX_TICKERS = LARGE_CAP_TICKERS

# ── DeFi & Mid-Cap Crypto ──────────────────────────────
PENNY_TICKERS = [
    # -- DeFi Blue Chips --
    "AAVE-USD", "MKR-USD", "CRV-USD", "LDO-USD", "SNX-USD",
    "ADT.AX", "MRR.AX", "AZL.AX", "CAD.AX", "CYL.AX",
    "KAI.AX", "TIE.AX", "ABR.AX", "JMS.AX", "VMS.AX",
    # -- Gold Juniors (20) --
    "SBM.AX", "DEG.AX", "GOR.AX", "SAR.AX", "MML.AX",
    "WAF.AX", "SLR.AX", "OGC.AX", "RED.AX", "RMS.AX",
    "RRL.AX", "PRU.AX", "CMM.AX", "RSG.AX", "MVR.AX",
    "MZZ.AX", "POZ.AX", "AQX.AX", "GCY.AX", "KCN.AX",
    # -- Lithium & Battery (20) --
    "SYA.AX", "CXO.AX", "GL1.AX", "LKE.AX", "AVZ.AX",
    "PLL.AX", "EUR.AX", "DEL.AX", "NVX.AX", "EV1.AX",
    "LAT.AX", "ESS.AX", "LRS.AX", "ASN.AX", "AML.AX",
    # -- Layer 1 Alts --
    "FTM-USD", "INJ-USD", "SEI-USD", "TIA-USD", "ALGO-USD",
    # -- Layer 2 --
    "ARB-USD", "OP-USD", "IMX-USD", "STRK-USD", "MANTA-USD",
    # -- Gaming/Metaverse --
    "AXS-USD", "SAND-USD", "MANA-USD", "GALA-USD", "ENJ-USD",
    # -- AI Tokens --
    "FET-USD", "RNDR-USD", "AGIX-USD", "OCEAN-USD", "TAO-USD",
    # -- Privacy --
    "XMR-USD", "ZEC-USD",
    # -- Exchange Tokens --
    "CRO-USD", "OKB-USD", "KCS-USD",
]

# Meme Coins (high volatility, GCR contrarian plays)
MEME_TICKERS = [
    "DOGE-USD", "SHIB-USD", "PEPE-USD", "WIF-USD", "BONK-USD",
    "FLOKI-USD", "MEME-USD", "TURBO-USD",
]

# Keep COMMODITY_TICKERS as alias for backward compat
COMMODITY_TICKERS = MEME_TICKERS

ALL_TICKERS = LARGE_CAP_TICKERS + PENNY_TICKERS + MEME_TICKERS
CORR_TICKERS = LARGE_CAP_TICKERS  # Use large caps for correlation heatmap

# ── Dynamic crypto universe ──────────────────────────────
_CRYPTO_FULL_UNIVERSE: list = []  # Populated on startup
# Backward compat alias
_ASX_FULL_UNIVERSE = _CRYPTO_FULL_UNIVERSE

async def _fetch_asx_listed_companies() -> list:
    """Fetch the full crypto asset list. Falls back to static tickers."""
    global _CRYPTO_FULL_UNIVERSE, _ASX_FULL_UNIVERSE
    _CRYPTO_FULL_UNIVERSE = ALL_TICKERS[:]
    _ASX_FULL_UNIVERSE = _CRYPTO_FULL_UNIVERSE
    logger.info(f"Using crypto ticker list ({len(_CRYPTO_FULL_UNIVERSE)} tickers)")
    return _CRYPTO_FULL_UNIVERSE

def get_asx_universe() -> list:
    """Return the full crypto universe (backward compat name)."""
    return _CRYPTO_FULL_UNIVERSE if _CRYPTO_FULL_UNIVERSE else ALL_TICKERS


# ── Asset metadata ──────────────────────────────────────
_ASSET_META = {
    # Large Cap
    "BTC-USD":   {"name": "Bitcoin",          "cat": "Large Cap",  "sector": "Store of Value"},
    "ETH-USD":   {"name": "Ethereum",         "cat": "Large Cap",  "sector": "Smart Contracts"},
    "BNB-USD":   {"name": "Binance Coin",     "cat": "Large Cap",  "sector": "Exchange"},
    "SOL-USD":   {"name": "Solana",           "cat": "Large Cap",  "sector": "Layer 1"},
    "XRP-USD":   {"name": "XRP",              "cat": "Large Cap",  "sector": "Payments"},
    "ADA-USD":   {"name": "Cardano",          "cat": "Large Cap",  "sector": "Layer 1"},
    "AVAX-USD":  {"name": "Avalanche",        "cat": "Large Cap",  "sector": "Layer 1"},
    "DOT-USD":   {"name": "Polkadot",         "cat": "Large Cap",  "sector": "Layer 1"},
    "LINK-USD":  {"name": "Chainlink",        "cat": "Large Cap",  "sector": "Oracle"},
    "MATIC-USD": {"name": "Polygon",          "cat": "Large Cap",  "sector": "Layer 2"},
    "ATOM-USD":  {"name": "Cosmos",           "cat": "Large Cap",  "sector": "Interop"},
    "UNI-USD":   {"name": "Uniswap",          "cat": "Large Cap",  "sector": "DEX"},
    "LTC-USD":   {"name": "Litecoin",         "cat": "Large Cap",  "sector": "Payments"},
    "BCH-USD":   {"name": "Bitcoin Cash",     "cat": "Large Cap",  "sector": "Payments"},
    "NEAR-USD":  {"name": "NEAR Protocol",    "cat": "Large Cap",  "sector": "Layer 1"},
    "APT-USD":   {"name": "Aptos",            "cat": "Large Cap",  "sector": "Layer 1"},
    "SUI-USD":   {"name": "Sui",              "cat": "Large Cap",  "sector": "Layer 1"},
    "FIL-USD":   {"name": "Filecoin",         "cat": "Large Cap",  "sector": "Storage"},
    "ICP-USD":   {"name": "Internet Computer", "cat": "Large Cap", "sector": "Layer 1"},
    "HBAR-USD":  {"name": "Hedera",           "cat": "Large Cap",  "sector": "Layer 1"},
    # DeFi
    "AAVE-USD":  {"name": "Aave",             "cat": "DeFi",       "sector": "Lending"},
    "MKR-USD":   {"name": "Maker",            "cat": "DeFi",       "sector": "Stablecoin"},
    "CRV-USD":   {"name": "Curve DAO",        "cat": "DeFi",       "sector": "DEX"},
    "LDO-USD":   {"name": "Lido DAO",         "cat": "DeFi",       "sector": "Staking"},
    "SNX-USD":   {"name": "Synthetix",        "cat": "DeFi",       "sector": "Derivatives"},
    # Layer 1 Alts
    "FTM-USD":   {"name": "Fantom",           "cat": "Layer 1",    "sector": "Smart Contracts"},
    "INJ-USD":   {"name": "Injective",        "cat": "Layer 1",    "sector": "DeFi Chain"},
    "ALGO-USD":  {"name": "Algorand",         "cat": "Layer 1",    "sector": "Smart Contracts"},
    # Layer 2
    "ARB-USD":   {"name": "Arbitrum",         "cat": "Layer 2",    "sector": "Rollup"},
    "OP-USD":    {"name": "Optimism",         "cat": "Layer 2",    "sector": "Rollup"},
    "IMX-USD":   {"name": "Immutable X",      "cat": "Layer 2",    "sector": "Gaming"},
    # AI Tokens
    "FET-USD":   {"name": "Fetch.ai",         "cat": "AI",         "sector": "AI Agent"},
    "RNDR-USD":  {"name": "Render",           "cat": "AI",         "sector": "GPU Compute"},
    # Gaming
    "AXS-USD":   {"name": "Axie Infinity",    "cat": "Gaming",     "sector": "GameFi"},
    "SAND-USD":  {"name": "The Sandbox",      "cat": "Gaming",     "sector": "Metaverse"},
    "GALA-USD":  {"name": "Gala Games",       "cat": "Gaming",     "sector": "GameFi"},
    # Meme Coins (GCR contrarian)
    "DOGE-USD":  {"name": "Dogecoin",         "cat": "Meme",       "sector": "Meme Coin"},
    "SHIB-USD":  {"name": "Shiba Inu",        "cat": "Meme",       "sector": "Meme Coin"},
    "PEPE-USD":  {"name": "Pepe",             "cat": "Meme",       "sector": "Meme Coin"},
    "WIF-USD":   {"name": "dogwifhat",        "cat": "Meme",       "sector": "Meme Coin"},
    "BONK-USD":  {"name": "Bonk",             "cat": "Meme",       "sector": "Meme Coin"},
    "FLOKI-USD": {"name": "Floki Inu",        "cat": "Meme",       "sector": "Meme Coin"},
}


# ── Scanner cache ──────────────────────────────────────
_scanner_cache: dict = {}   # market -> {"ts": float, "rows": list}
_CACHE_TTL = 300            # 5 minutes — prices don't change that fast


async def _live_price(ticker: str) -> Optional[float]:
    """Get the most recent price for a ticker.
    Priority: scanner cache -> yfinance -> demo seed.
    """
    # 1. Scanner cache (fastest -- already in memory)
    cached_ms = _cache_get("market_summary")
    if cached_ms:
        for item in cached_ms:
            if item.get("ticker") == ticker and item.get("price") is not None:
                return float(item["price"])

    # 2. yfinance fallback
    prices = await _get_prices([ticker], "5d")
    if prices and ticker in prices and prices[ticker]:
        return float(prices[ticker][-1])

    # 3. Demo seed (never None -- prevents order failure on unknown tickers)
    seed = abs(hash(ticker)) % 10000
    rng = random.Random(seed)
    return round(rng.uniform(10, 300), 2)


async def _prices_for_positions(tickers: list) -> dict:
    """Return {ticker: price} for all open position tickers."""
    if not tickers:
        return {}
    result = {}

    # 1. Batch-fetch tickers via yfinance download
    remaining = [t for t in tickers if t not in result]
    if remaining and YF_AVAILABLE:
        try:
            loop = asyncio.get_running_loop()

            def _batch_yf():
                import yfinance as _yf_batch
                import pandas as _pd_batch
                try:
                    single = len(remaining) == 1
                    raw = _yf_batch.download(
                        remaining if not single else remaining[0],
                        period="5d", auto_adjust=True, progress=False,
                        threads=True, timeout=10,
                    )
                    if raw is None or raw.empty:
                        return {}
                    prices = {}
                    if single:
                        # Single ticker: flat columns
                        if "Close" in raw.columns:
                            col = raw["Close"].dropna()
                            if not col.empty:
                                prices[remaining[0]] = float(col.iloc[-1])
                    elif isinstance(raw.columns, _pd_batch.MultiIndex):
                        # Multi-ticker: level 0 = Price, level 1 = Ticker
                        if "Close" in raw.columns.get_level_values(0):
                            close = raw["Close"]
                            for t in remaining:
                                if t in close.columns:
                                    col = close[t].dropna()
                                    if not col.empty:
                                        prices[t] = float(col.iloc[-1])
                    return prices
                except Exception:
                    return {}

            batch_prices = await asyncio.wait_for(
                loop.run_in_executor(_EXECUTOR, _batch_yf), timeout=12.0)
            result.update(batch_prices)
        except (asyncio.TimeoutError, Exception):
            pass

    # 3. Individual fallback for any tickers still missing
    still_missing = [t for t in tickers if t not in result]
    for t in still_missing:
        p = await _live_price(t)
        if p is not None:
            result[t] = p
    return result


# ── Scanner functions ───────────────────────────────────

async def _scan_yfinance(tickers: list, market: str) -> list:
    """Fetch OHLCV for ASX and commodity markets via yfinance."""
    if not YF_AVAILABLE:
        return []
    await SOURCE_LIMITER.acquire("yfinance")
    try:
        return await _scan_yfinance_inner(tickers, market)
    finally:
        SOURCE_LIMITER.release("yfinance")


async def _scan_yfinance_inner(tickers: list, market: str) -> list:
    import yfinance as yf
    loop = asyncio.get_running_loop()
    results: dict = {}

    # Batch large ticker lists — run sequentially with gap to avoid rate limits
    BATCH_SIZE = 150
    batches = [tickers[i:i+BATCH_SIZE] for i in range(0, len(tickers), BATCH_SIZE)]
    if len(batches) > 1:
        logger.info(f"[{market}] Scanning {len(tickers)} tickers in {len(batches)} concurrent batches")

    import pandas as _pd
    import time as _time

    def _bulk(batch_tickers, idx):
        try:
            raw = yf.download(
                batch_tickers, period="5d", interval="1d",
                auto_adjust=True, progress=False, threads=True,
            )
            return (batch_tickers, raw)
        except Exception as exc:
            logger.warning(f"yfinance bulk failed [{market}] batch {idx}: {exc}")
            return (batch_tickers, None)

    def _parse_bulk(batch, raw):
        """Parse a bulk download result into results dict."""
        if raw is None or raw.empty:
            return
        single = len(batch) == 1
        for ticker in batch:
            try:
                if single:
                    df = raw.dropna(subset=["Close"])
                    if len(df) < 2:
                        continue
                    price = float(df["Close"].iloc[-1])
                    prev = float(df["Close"].iloc[-2])
                    vol = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0
                else:
                    if not isinstance(raw.columns, _pd.MultiIndex):
                        continue
                    close_df = raw["Close"] if "Close" in raw.columns.get_level_values(0) else None
                    if close_df is None:
                        continue
                    if ticker not in close_df.columns:
                        continue
                    col = close_df[ticker].dropna()
                    if len(col) < 2:
                        continue
                    price = float(col.iloc[-1])
                    prev = float(col.iloc[-2])
                    vol_df = raw["Volume"] if "Volume" in raw.columns.get_level_values(0) else None
                    vol = float(vol_df[ticker].dropna().iloc[-1]) if vol_df is not None and ticker in vol_df.columns else 0

                chg_pct = (price - prev) / prev * 100 if prev else 0
                results[ticker] = (price, chg_pct, vol)
            except Exception as exc:
                logger.debug(f"Bulk parse [{ticker}]: {exc}")

    # Run batches SEQUENTIALLY with 1s gap to avoid Yahoo rate limits
    for i, batch in enumerate(batches):
        if i > 0:
            await asyncio.sleep(1)
        batch_tickers, raw = await loop.run_in_executor(None, _bulk, batch, i)
        _parse_bulk(batch_tickers, raw)

    # Retry missing tickers in one bulk download (not individual fetches)
    missing = [t for t in tickers if t not in results]
    if missing and len(missing) > 5:
        logger.info(f"[{market}] bulk retry for {len(missing)} missing tickers")
        await asyncio.sleep(2)  # Wait before retry
        _, retry_raw = await loop.run_in_executor(None, _bulk, missing, 99)
        _parse_bulk(missing, retry_raw)

    # Final individual fallback for stragglers (small batch only)
    still_missing = [t for t in tickers if t not in results]
    if still_missing and len(still_missing) <= 50:
        logger.info(f"[{market}] {len(still_missing)} tickers not found (delisted or no data)")

    # Build rows
    rows = []
    for ticker in tickers:
        meta = _ASSET_META.get(ticker, {"name": ticker, "sector": "--"})
        if ticker not in results:
            continue
        price, chg_pct, vol = results[ticker]
        rows.append({
            "ticker":       ticker,
            "name":         meta.get("name", ticker),
            "sector":       meta.get("sector", "--"),
            "price":        round(price, 4),
            "change":       round(price * chg_pct / 100, 4),
            "change_pct":   round(chg_pct, 2),
            "volume_fmt":   _fmt_vol(vol),
            "volume":       int(vol),
            "in_watchlist": ticker in WATCHLIST,
        })

    logger.info(f"yfinance [{market}]: {len(rows)}/{len(tickers)} tickers")
    return rows


# ── Market summary demo data ───────────────────────────
_MARKET_DEMO = [
    ("^AXJO",    "ASX 200",       "index",       7_985.0,   0.42),
    ("CBA.AX",   "CommBank",      "asx",          145.20,   0.72),
    ("BHP.AX",   "BHP Group",     "asx",           42.80,  -0.33),
    ("CSL.AX",   "CSL Ltd",       "asx",          285.60,   1.15),
    ("NAB.AX",   "NAB",           "asx",           38.50,   0.45),
    ("WBC.AX",   "Westpac",       "asx",           28.90,  -0.18),
    ("ANZ.AX",   "ANZ Bank",      "asx",           30.15,   0.62),
    ("FMG.AX",   "Fortescue",     "asx",           18.40,  -1.80),
    ("RIO.AX",   "Rio Tinto",     "asx",          115.30,  -0.55),
    ("WDS.AX",   "Woodside",      "asx",           26.70,   0.90),
    ("WES.AX",   "Wesfarmers",    "asx",           72.40,   0.35),
    ("MQG.AX",   "Macquarie",     "asx",          198.50,   1.20),
    ("TLS.AX",   "Telstra",       "asx",            3.95,  -0.25),
    ("^GSPC",    "S&P 500",       "index",       5_674.0,  -0.31),
    ("^DJI",     "Dow Jones",     "index",      42_150.0,   0.18),
    ("^IXIC",    "Nasdaq",        "index",      18_320.0,  -0.45),
    ("^N225",    "Nikkei 225",    "index",      38_750.0,   0.55),
    ("^FTSE",    "FTSE 100",      "index",       8_210.0,  -0.22),
    ("^VIX",     "VIX Fear",      "index",         18.4,   -3.20),
    ("AUD=X",    "AUD/USD",       "fx",            0.6312,  0.18),
    ("EURUSD=X", "EUR/USD",       "fx",            1.0845,  0.12),
    ("PMGOLD.AX","Perth Mint Gold","commodity",     24.50,   0.48),
    ("PLS.AX",   "Pilbara Lithium","commodity",      3.80,  -1.20),
    ("LYC.AX",   "Lynas Rare Earth","commodity",     7.40,   0.92),
    ("PDN.AX",   "Paladin Uranium","commodity",     12.30,   2.35),
    ("WHC.AX",   "Whitehaven Coal","commodity",      7.90,  -0.65),
    ("OOO.AX",   "Oil ETF (ASX)", "commodity",      5.60,  -0.55),
    ("S32.AX",   "South32",       "commodity",       3.20,   0.40),
]
