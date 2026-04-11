"""
0xrex — Binance Public API Client
Real-time crypto market data via Binance REST API (no key required).
Replaces yfinance for all crypto price data.
"""

import asyncio
import time
from typing import Optional

import aiohttp
from loguru import logger

_BASE = "https://api.binance.com/api/v3"
_session: Optional[aiohttp.ClientSession] = None

# ── Ticker conversion ─────────────────────────────────────

def to_binance_symbol(ticker: str) -> str:
    """Convert internal format to Binance symbol: BTC-USD -> BTCUSDT"""
    t = ticker.upper().strip()
    if t.endswith("-USD"):
        return t.replace("-USD", "") + "USDT"
    if t.endswith("-USDT"):
        return t.replace("-USDT", "") + "USDT"
    return t + "USDT"


def from_binance_symbol(symbol: str) -> str:
    """Convert Binance symbol to internal format: BTCUSDT -> BTC-USD"""
    s = symbol.upper()
    if s.endswith("USDT"):
        return s[:-4] + "-USD"
    return s + "-USD"


def is_crypto_ticker(ticker: str) -> bool:
    """True for tickers that should go through Binance (not indices/FX)."""
    t = ticker.upper()
    if t.startswith("^") or "=" in t or t.startswith("DX-"):
        return False
    if t.endswith("-USD") or t.endswith("-USDT"):
        return True
    return False


# Known stablecoins that don't trade as XXXUSDT on Binance
_STABLECOIN_PRICES = {"USDT-USD": 1.0, "USDC-USD": 1.0, "DAI-USD": 1.0, "BUSD-USD": 1.0}

# ── Session management ────────────────────────────────────

async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        _session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            headers={"Accept": "application/json"},
        )
    return _session


async def close_session():
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


# ── Internal fetch with retry ─────────────────────────────

async def _fetch_json(url: str, params: dict = None, retries: int = 2) -> Optional[dict | list]:
    """GET JSON from Binance with retry on transient errors."""
    session = await _get_session()
    for attempt in range(retries + 1):
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    return await resp.json()
                if resp.status == 429:
                    wait = min(2 ** attempt * 2, 10)
                    logger.warning(f"Binance rate limited, retrying in {wait}s")
                    await asyncio.sleep(wait)
                    continue
                body = await resp.text()
                logger.warning(f"Binance {resp.status}: {body[:200]}")
                return None
        except (aiohttp.ClientError, asyncio.TimeoutError) as e:
            if attempt < retries:
                await asyncio.sleep(1)
                continue
            logger.warning(f"Binance fetch failed: {e}")
            return None
    return None


# ── Price endpoints ───────────────────────────────────────

async def binance_price(ticker: str) -> Optional[float]:
    """Get current price for a single ticker."""
    if ticker in _STABLECOIN_PRICES:
        return _STABLECOIN_PRICES[ticker]
    symbol = to_binance_symbol(ticker)
    data = await _fetch_json(f"{_BASE}/ticker/price", {"symbol": symbol})
    if data and "price" in data:
        return float(data["price"])
    return None


# Cache for all-prices (refreshed every 30s max)
_all_prices_cache: dict = {}
_all_prices_ts: float = 0


async def binance_prices_batch(tickers: list[str]) -> dict[str, float]:
    """Get prices for multiple tickers in a single API call."""
    global _all_prices_cache, _all_prices_ts

    # Use cached all-prices if fresh (< 30s)
    now = time.time()
    if now - _all_prices_ts > 30 or not _all_prices_cache:
        data = await _fetch_json(f"{_BASE}/ticker/price")
        if data:
            _all_prices_cache = {item["symbol"]: float(item["price"]) for item in data}
            _all_prices_ts = now

    result = {}
    for t in tickers:
        if t in _STABLECOIN_PRICES:
            result[t] = _STABLECOIN_PRICES[t]
            continue
        sym = to_binance_symbol(t)
        if sym in _all_prices_cache:
            result[t] = _all_prices_cache[sym]
    return result


# ── 24hr stats ────────────────────────────────────────────

_all_24hr_cache: list = []
_all_24hr_ts: float = 0


async def binance_24hr_stats_batch(tickers: list[str]) -> dict[str, dict]:
    """Get 24hr change, volume, high/low for multiple tickers in one call."""
    global _all_24hr_cache, _all_24hr_ts

    now = time.time()
    if now - _all_24hr_ts > 60 or not _all_24hr_cache:
        data = await _fetch_json(f"{_BASE}/ticker/24hr")
        if data:
            _all_24hr_cache = data
            _all_24hr_ts = now

    # Build lookup by symbol
    lookup = {item["symbol"]: item for item in _all_24hr_cache}

    result = {}
    for t in tickers:
        if t in _STABLECOIN_PRICES:
            result[t] = {"price": _STABLECOIN_PRICES[t], "change_pct": 0.0,
                         "volume": 0, "high": _STABLECOIN_PRICES[t], "low": _STABLECOIN_PRICES[t]}
            continue
        sym = to_binance_symbol(t)
        item = lookup.get(sym)
        if item:
            try:
                result[t] = {
                    "price": float(item["lastPrice"]),
                    "change_pct": float(item["priceChangePercent"]),
                    "volume": float(item["quoteVolume"]),
                    "high": float(item["highPrice"]),
                    "low": float(item["lowPrice"]),
                }
            except (ValueError, KeyError):
                pass
    return result


# ── OHLCV Klines ──────────────────────────────────────────

# Period → (interval, limit) mapping
_PERIOD_MAP = {
    "1d":  ("1h", 24),
    "5d":  ("1d", 5),
    "1mo": ("1d", 30),
    "3mo": ("1d", 90),
    "6mo": ("1d", 180),
    "1y":  ("1d", 365),
    "2y":  ("1d", 730),
    "5y":  ("1w", 260),
}

# Interval mapping from yfinance style to Binance style
_INTERVAL_MAP = {
    "1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "4h": "4h", "1d": "1d", "1wk": "1w", "1mo": "1M",
}


async def binance_klines(ticker: str, interval: str = "1d",
                         limit: int = 180, period: str = None) -> list[dict]:
    """Fetch OHLCV candlestick data for a single ticker.
    Returns list of {t, o, h, l, c, v} dicts.
    """
    if ticker in _STABLECOIN_PRICES:
        return []

    symbol = to_binance_symbol(ticker)

    # If period given, map to interval + limit
    if period and period in _PERIOD_MAP:
        interval, limit = _PERIOD_MAP[period]

    # Map yfinance-style intervals
    bn_interval = _INTERVAL_MAP.get(interval, interval)

    data = await _fetch_json(f"{_BASE}/klines", {
        "symbol": symbol, "interval": bn_interval, "limit": min(limit, 1000),
    })
    if not data:
        return []

    candles = []
    for k in data:
        candles.append({
            "t": int(k[0]),       # open time (ms)
            "o": float(k[1]),     # open
            "h": float(k[2]),     # high
            "l": float(k[3]),     # low
            "c": float(k[4]),     # close
            "v": float(k[5]),     # base asset volume
        })
    return candles


async def binance_klines_closes(tickers: list[str], period: str = "5d") -> dict[str, list[float]]:
    """Fetch closing prices for multiple tickers. Returns dict[ticker -> list[float]].
    Drop-in replacement for _yf_fetch_sync return format.
    """
    interval, limit = _PERIOD_MAP.get(period, ("1d", 90))
    result = {}

    # Fetch concurrently with bounded concurrency
    sem = asyncio.Semaphore(10)

    async def _fetch_one(ticker):
        async with sem:
            candles = await binance_klines(ticker, interval, limit)
            if candles:
                result[ticker] = [c["c"] for c in candles]

    crypto = [t for t in tickers if is_crypto_ticker(t) and t not in _STABLECOIN_PRICES]
    await asyncio.gather(*[_fetch_one(t) for t in crypto], return_exceptions=True)
    return result


# ── Exchange info (available pairs) ───────────────────────

_exchange_symbols: set[str] = set()
_exchange_info_ts: float = 0


async def binance_exchange_info() -> set[str]:
    """Fetch and cache available USDT trading pairs. Returns set of internal ticker format."""
    global _exchange_symbols, _exchange_info_ts

    now = time.time()
    if now - _exchange_info_ts > 3600 or not _exchange_symbols:
        data = await _fetch_json(f"{_BASE}/exchangeInfo")
        if data and "symbols" in data:
            _exchange_symbols = set()
            for s in data["symbols"]:
                if (s.get("quoteAsset") == "USDT"
                        and s.get("status") == "TRADING"):
                    _exchange_symbols.add(from_binance_symbol(s["symbol"]))
            _exchange_info_ts = now
            logger.info(f"Binance: {len(_exchange_symbols)} USDT pairs available")
    return _exchange_symbols
