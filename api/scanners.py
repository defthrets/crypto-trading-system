"""
0xRex -- Market Scanning
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


# ── Default Crypto Universe ─────────────────────────────
# Default ticker list shown when no exchange API is connected.
# When an exchange is connected, scanner filters to that exchange's available pairs.

CRYPTO_TICKERS = [
    # ── Large Cap (Top 20) ──
    "BTC-USD", "ETH-USD", "BNB-USD", "SOL-USD", "XRP-USD",
    "ADA-USD", "AVAX-USD", "DOT-USD", "LINK-USD", "MATIC-USD",
    "ATOM-USD", "UNI-USD", "LTC-USD", "BCH-USD", "NEAR-USD",
    "APT-USD", "SUI-USD", "FIL-USD", "ICP-USD", "HBAR-USD",
    # ── Layer 1 ──
    "FTM-USD", "INJ-USD", "SEI-USD", "TIA-USD", "ALGO-USD",
    "EGLD-USD", "FLOW-USD", "MINA-USD", "KAVA-USD", "ROSE-USD",
    "ONE-USD", "ZIL-USD", "CELO-USD", "KDA-USD", "IOTX-USD",
    "CFX-USD", "VET-USD", "THETA-USD", "IOTA-USD", "XTZ-USD",
    "EOS-USD", "NEO-USD", "WAVES-USD", "QTUM-USD", "ZEN-USD",
    "TON-USD", "KAS-USD", "STX-USD", "RUNE-USD", "ASTR-USD",
    # ── Layer 2 ──
    "ARB-USD", "OP-USD", "IMX-USD", "STRK-USD", "MANTA-USD",
    "METIS-USD", "SKL-USD", "BOBA-USD", "CELR-USD",
    # ── DeFi ──
    "AAVE-USD", "MKR-USD", "CRV-USD", "LDO-USD", "SNX-USD",
    "COMP-USD", "SUSHI-USD", "1INCH-USD", "BAL-USD", "YFI-USD",
    "DYDX-USD", "GMX-USD", "PENDLE-USD", "JUP-USD", "RAY-USD",
    "CAKE-USD", "JOE-USD", "OSMO-USD",
    # ── Infrastructure & Storage ──
    "AR-USD", "STORJ-USD", "SC-USD", "HNT-USD", "ANKR-USD",
    "GRT-USD", "BAND-USD", "API3-USD", "COTI-USD", "RLC-USD",
    "NKN-USD", "POWR-USD", "LPT-USD", "FLUX-USD", "KSM-USD",
    "PYTH-USD", "WLD-USD", "ONDO-USD", "ETHFI-USD",
    # ── AI Tokens ──
    "FET-USD", "RNDR-USD", "AGIX-USD", "OCEAN-USD", "TAO-USD",
    "AKT-USD", "AIOZ-USD",
    # ── Gaming / Metaverse ──
    "AXS-USD", "SAND-USD", "MANA-USD", "GALA-USD", "ENJ-USD",
    "ILV-USD", "MAGIC-USD", "PIXEL-USD", "PORTAL-USD", "RONIN-USD",
    # ── Meme Coins ──
    "DOGE-USD", "SHIB-USD", "PEPE-USD", "WIF-USD", "BONK-USD",
    "FLOKI-USD", "MEME-USD", "TURBO-USD", "NEIRO-USD", "PEOPLE-USD",
    "BOME-USD", "MEW-USD", "NOT-USD",
    # ── Exchange Tokens ──
    "CRO-USD", "OKB-USD", "KCS-USD", "GT-USD", "MX-USD",
    # ── Privacy ──
    "XMR-USD", "ZEC-USD", "DASH-USD",
    # ── Stablecoins / Yield (for reference) ──
    "ENA-USD", "MNT-USD",
]

# Backward compat aliases
ALL_TICKERS = CRYPTO_TICKERS
LARGE_CAP_TICKERS = CRYPTO_TICKERS[:20]
CORR_TICKERS = LARGE_CAP_TICKERS  # Use large caps for correlation heatmap
PENNY_TICKERS = CRYPTO_TICKERS    # Legacy alias
MEME_TICKERS = CRYPTO_TICKERS     # Legacy alias

# ── Exchange-specific ticker lists ──────────────────────
# Populated when exchange APIs are connected. Empty = use defaults.
# Keys match broker names from api/brokers.py BROKER_MAP.
EXCHANGE_TICKERS: dict[str, list[str]] = {
    "binance": [], "coinbase": [], "kraken": [], "bybit": [],
    "okx": [], "kucoin": [], "gateio": [], "dydx": [], "hyperliquid": [],
}


def get_scanner_tickers(connected_brokers: list[str] = None) -> list[str]:
    """Return tickers for the scanner based on connected exchanges.
    - No exchanges connected: return full default list (CRYPTO_TICKERS)
    - Exchanges connected with known ticker lists: union of exchange lists
    - Exchanges connected but no ticker list: return defaults
    """
    if not connected_brokers:
        return CRYPTO_TICKERS
    exchange_tickers = []
    for name in connected_brokers:
        tlist = EXCHANGE_TICKERS.get(name, [])
        if tlist:
            exchange_tickers.extend(tlist)
    if not exchange_tickers:
        return CRYPTO_TICKERS  # No exchange has a populated list yet
    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in exchange_tickers:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique


# ── Dynamic crypto universe ──────────────────────────────
_CRYPTO_FULL_UNIVERSE: list = []  # Populated on startup

async def _fetch_crypto_listed_assets() -> list:
    """Fetch the full crypto asset list. Falls back to static tickers."""
    global _CRYPTO_FULL_UNIVERSE, _CRYPTO_FULL_UNIVERSE
    _CRYPTO_FULL_UNIVERSE = ALL_TICKERS[:]
    _CRYPTO_FULL_UNIVERSE = _CRYPTO_FULL_UNIVERSE
    logger.info(f"Using crypto ticker list ({len(_CRYPTO_FULL_UNIVERSE)} tickers)")
    return _CRYPTO_FULL_UNIVERSE

def get_crypto_universe() -> list:
    """Return the full crypto universe (backward compat name)."""
    return _CRYPTO_FULL_UNIVERSE if _CRYPTO_FULL_UNIVERSE else ALL_TICKERS


# ── Asset metadata ──────────────────────────────────────
_ASSET_META = {
    # ── Large Cap ──
    "BTC-USD":   {"name": "Bitcoin",           "cat": "Large Cap",      "sector": "Store of Value"},
    "ETH-USD":   {"name": "Ethereum",          "cat": "Large Cap",      "sector": "Smart Contracts"},
    "BNB-USD":   {"name": "Binance Coin",      "cat": "Large Cap",      "sector": "Exchange"},
    "SOL-USD":   {"name": "Solana",            "cat": "Large Cap",      "sector": "Layer 1"},
    "XRP-USD":   {"name": "XRP",               "cat": "Large Cap",      "sector": "Payments"},
    "ADA-USD":   {"name": "Cardano",           "cat": "Large Cap",      "sector": "Layer 1"},
    "AVAX-USD":  {"name": "Avalanche",         "cat": "Large Cap",      "sector": "Layer 1"},
    "DOT-USD":   {"name": "Polkadot",          "cat": "Large Cap",      "sector": "Layer 1"},
    "LINK-USD":  {"name": "Chainlink",         "cat": "Large Cap",      "sector": "Oracle"},
    "MATIC-USD": {"name": "Polygon",           "cat": "Large Cap",      "sector": "Layer 2"},
    "ATOM-USD":  {"name": "Cosmos",            "cat": "Large Cap",      "sector": "Interop"},
    "UNI-USD":   {"name": "Uniswap",           "cat": "Large Cap",      "sector": "DEX"},
    "LTC-USD":   {"name": "Litecoin",          "cat": "Large Cap",      "sector": "Payments"},
    "BCH-USD":   {"name": "Bitcoin Cash",      "cat": "Large Cap",      "sector": "Payments"},
    "NEAR-USD":  {"name": "NEAR Protocol",     "cat": "Large Cap",      "sector": "Layer 1"},
    "APT-USD":   {"name": "Aptos",             "cat": "Large Cap",      "sector": "Layer 1"},
    "SUI-USD":   {"name": "Sui",               "cat": "Large Cap",      "sector": "Layer 1"},
    "FIL-USD":   {"name": "Filecoin",          "cat": "Large Cap",      "sector": "Infrastructure"},
    "ICP-USD":   {"name": "Internet Computer",  "cat": "Large Cap",     "sector": "Layer 1"},
    "HBAR-USD":  {"name": "Hedera",            "cat": "Large Cap",      "sector": "Layer 1"},
    # ── Layer 1 ──
    "FTM-USD":   {"name": "Fantom",            "cat": "Layer 1",        "sector": "Layer 1"},
    "INJ-USD":   {"name": "Injective",         "cat": "Layer 1",        "sector": "DeFi"},
    "SEI-USD":   {"name": "Sei",               "cat": "Layer 1",        "sector": "Layer 1"},
    "TIA-USD":   {"name": "Celestia",          "cat": "Layer 1",        "sector": "Layer 1"},
    "ALGO-USD":  {"name": "Algorand",          "cat": "Layer 1",        "sector": "Layer 1"},
    "EGLD-USD":  {"name": "MultiversX",        "cat": "Layer 1",        "sector": "Layer 1"},
    "FLOW-USD":  {"name": "Flow",              "cat": "Layer 1",        "sector": "Layer 1"},
    "MINA-USD":  {"name": "Mina Protocol",     "cat": "Layer 1",        "sector": "Layer 1"},
    "KAVA-USD":  {"name": "Kava",              "cat": "Layer 1",        "sector": "DeFi"},
    "ROSE-USD":  {"name": "Oasis Network",     "cat": "Layer 1",        "sector": "Privacy"},
    "ONE-USD":   {"name": "Harmony",           "cat": "Layer 1",        "sector": "Layer 1"},
    "ZIL-USD":   {"name": "Zilliqa",           "cat": "Layer 1",        "sector": "Layer 1"},
    "CELO-USD":  {"name": "Celo",              "cat": "Layer 1",        "sector": "Payments"},
    "KDA-USD":   {"name": "Kadena",            "cat": "Layer 1",        "sector": "Layer 1"},
    "IOTX-USD":  {"name": "IoTeX",             "cat": "Layer 1",        "sector": "Infrastructure"},
    "CFX-USD":   {"name": "Conflux",           "cat": "Layer 1",        "sector": "Layer 1"},
    "VET-USD":   {"name": "VeChain",           "cat": "Layer 1",        "sector": "Infrastructure"},
    "THETA-USD": {"name": "Theta Network",     "cat": "Layer 1",        "sector": "Infrastructure"},
    "IOTA-USD":  {"name": "IOTA",              "cat": "Layer 1",        "sector": "Infrastructure"},
    "XTZ-USD":   {"name": "Tezos",             "cat": "Layer 1",        "sector": "Layer 1"},
    "EOS-USD":   {"name": "EOS",               "cat": "Layer 1",        "sector": "Layer 1"},
    "NEO-USD":   {"name": "NEO",               "cat": "Layer 1",        "sector": "Layer 1"},
    "WAVES-USD": {"name": "Waves",             "cat": "Layer 1",        "sector": "Layer 1"},
    "QTUM-USD":  {"name": "Qtum",              "cat": "Layer 1",        "sector": "Layer 1"},
    "ZEN-USD":   {"name": "Horizen",           "cat": "Layer 1",        "sector": "Privacy"},
    "TON-USD":   {"name": "Toncoin",           "cat": "Layer 1",        "sector": "Layer 1"},
    "KAS-USD":   {"name": "Kaspa",             "cat": "Layer 1",        "sector": "Layer 1"},
    "STX-USD":   {"name": "Stacks",            "cat": "Layer 1",        "sector": "Layer 1"},
    "RUNE-USD":  {"name": "THORChain",         "cat": "Layer 1",        "sector": "DEX"},
    "ASTR-USD":  {"name": "Astar",             "cat": "Layer 1",        "sector": "Layer 1"},
    # ── Layer 2 ──
    "ARB-USD":   {"name": "Arbitrum",          "cat": "Layer 2",        "sector": "Layer 2"},
    "OP-USD":    {"name": "Optimism",          "cat": "Layer 2",        "sector": "Layer 2"},
    "IMX-USD":   {"name": "Immutable X",       "cat": "Layer 2",        "sector": "Gaming"},
    "STRK-USD":  {"name": "StarkNet",          "cat": "Layer 2",        "sector": "Layer 2"},
    "MANTA-USD": {"name": "Manta Network",     "cat": "Layer 2",        "sector": "Layer 2"},
    "METIS-USD": {"name": "Metis",             "cat": "Layer 2",        "sector": "Layer 2"},
    "SKL-USD":   {"name": "SKALE",             "cat": "Layer 2",        "sector": "Layer 2"},
    "BOBA-USD":  {"name": "Boba Network",      "cat": "Layer 2",        "sector": "Layer 2"},
    "CELR-USD":  {"name": "Celer Network",     "cat": "Layer 2",        "sector": "Layer 2"},
    # ── DeFi ──
    "AAVE-USD":  {"name": "Aave",              "cat": "DeFi",           "sector": "Lending"},
    "MKR-USD":   {"name": "Maker",             "cat": "DeFi",           "sector": "Lending"},
    "CRV-USD":   {"name": "Curve DAO",         "cat": "DeFi",           "sector": "DEX"},
    "LDO-USD":   {"name": "Lido DAO",          "cat": "DeFi",           "sector": "DeFi"},
    "SNX-USD":   {"name": "Synthetix",         "cat": "DeFi",           "sector": "DeFi"},
    "COMP-USD":  {"name": "Compound",          "cat": "DeFi",           "sector": "Lending"},
    "SUSHI-USD": {"name": "SushiSwap",         "cat": "DeFi",           "sector": "DEX"},
    "1INCH-USD": {"name": "1inch",             "cat": "DeFi",           "sector": "DEX"},
    "BAL-USD":   {"name": "Balancer",          "cat": "DeFi",           "sector": "DEX"},
    "YFI-USD":   {"name": "yearn.finance",     "cat": "DeFi",           "sector": "DeFi"},
    "DYDX-USD":  {"name": "dYdX",              "cat": "DeFi",           "sector": "DEX"},
    "GMX-USD":   {"name": "GMX",               "cat": "DeFi",           "sector": "DEX"},
    "PENDLE-USD":{"name": "Pendle",            "cat": "DeFi",           "sector": "DeFi"},
    "JUP-USD":   {"name": "Jupiter",           "cat": "DeFi",           "sector": "DEX"},
    "RAY-USD":   {"name": "Raydium",           "cat": "DeFi",           "sector": "DEX"},
    "CAKE-USD":  {"name": "PancakeSwap",       "cat": "DeFi",           "sector": "DEX"},
    "JOE-USD":   {"name": "Trader Joe",        "cat": "DeFi",           "sector": "DEX"},
    "OSMO-USD":  {"name": "Osmosis",           "cat": "DeFi",           "sector": "DEX"},
    # ── Infrastructure ──
    "AR-USD":    {"name": "Arweave",           "cat": "Infrastructure",  "sector": "Infrastructure"},
    "STORJ-USD": {"name": "Storj",             "cat": "Infrastructure",  "sector": "Infrastructure"},
    "SC-USD":    {"name": "Siacoin",           "cat": "Infrastructure",  "sector": "Infrastructure"},
    "HNT-USD":   {"name": "Helium",            "cat": "Infrastructure",  "sector": "Infrastructure"},
    "ANKR-USD":  {"name": "Ankr",              "cat": "Infrastructure",  "sector": "Infrastructure"},
    "GRT-USD":   {"name": "The Graph",         "cat": "Infrastructure",  "sector": "Infrastructure"},
    "BAND-USD":  {"name": "Band Protocol",     "cat": "Infrastructure",  "sector": "Oracle"},
    "API3-USD":  {"name": "API3",              "cat": "Infrastructure",  "sector": "Oracle"},
    "COTI-USD":  {"name": "COTI",              "cat": "Infrastructure",  "sector": "Payments"},
    "RLC-USD":   {"name": "iExec",             "cat": "Infrastructure",  "sector": "Infrastructure"},
    "NKN-USD":   {"name": "NKN",               "cat": "Infrastructure",  "sector": "Infrastructure"},
    "POWR-USD":  {"name": "Powerledger",       "cat": "Infrastructure",  "sector": "Infrastructure"},
    "LPT-USD":   {"name": "Livepeer",          "cat": "Infrastructure",  "sector": "Infrastructure"},
    "FLUX-USD":  {"name": "Flux",              "cat": "Infrastructure",  "sector": "Infrastructure"},
    "KSM-USD":   {"name": "Kusama",            "cat": "Infrastructure",  "sector": "Infrastructure"},
    "PYTH-USD":  {"name": "Pyth Network",      "cat": "Infrastructure",  "sector": "Oracle"},
    "WLD-USD":   {"name": "Worldcoin",         "cat": "Infrastructure",  "sector": "Infrastructure"},
    "ONDO-USD":  {"name": "Ondo Finance",      "cat": "Infrastructure",  "sector": "DeFi"},
    "ETHFI-USD": {"name": "ether.fi",          "cat": "Infrastructure",  "sector": "DeFi"},
    # ── AI ──
    "FET-USD":   {"name": "Fetch.ai",          "cat": "AI",             "sector": "AI"},
    "RNDR-USD":  {"name": "Render",            "cat": "AI",             "sector": "AI"},
    "AGIX-USD":  {"name": "SingularityNET",    "cat": "AI",             "sector": "AI"},
    "OCEAN-USD": {"name": "Ocean Protocol",    "cat": "AI",             "sector": "AI"},
    "TAO-USD":   {"name": "Bittensor",         "cat": "AI",             "sector": "AI"},
    "AKT-USD":   {"name": "Akash Network",     "cat": "AI",             "sector": "AI"},
    "AIOZ-USD":  {"name": "AIOZ Network",      "cat": "AI",             "sector": "AI"},
    # ── Gaming ──
    "AXS-USD":   {"name": "Axie Infinity",     "cat": "Gaming",         "sector": "Gaming"},
    "SAND-USD":  {"name": "The Sandbox",       "cat": "Gaming",         "sector": "Gaming"},
    "MANA-USD":  {"name": "Decentraland",      "cat": "Gaming",         "sector": "Gaming"},
    "GALA-USD":  {"name": "Gala Games",        "cat": "Gaming",         "sector": "Gaming"},
    "ENJ-USD":   {"name": "Enjin Coin",        "cat": "Gaming",         "sector": "Gaming"},
    "ILV-USD":   {"name": "Illuvium",          "cat": "Gaming",         "sector": "Gaming"},
    "MAGIC-USD": {"name": "MAGIC",             "cat": "Gaming",         "sector": "Gaming"},
    "PIXEL-USD": {"name": "Pixels",            "cat": "Gaming",         "sector": "Gaming"},
    "PORTAL-USD":{"name": "Portal",            "cat": "Gaming",         "sector": "Gaming"},
    "RONIN-USD": {"name": "Ronin",             "cat": "Gaming",         "sector": "Gaming"},
    # ── Meme ──
    "DOGE-USD":  {"name": "Dogecoin",          "cat": "Meme",           "sector": "Meme"},
    "SHIB-USD":  {"name": "Shiba Inu",         "cat": "Meme",           "sector": "Meme"},
    "PEPE-USD":  {"name": "Pepe",              "cat": "Meme",           "sector": "Meme"},
    "WIF-USD":   {"name": "dogwifhat",         "cat": "Meme",           "sector": "Meme"},
    "BONK-USD":  {"name": "Bonk",              "cat": "Meme",           "sector": "Meme"},
    "FLOKI-USD": {"name": "Floki Inu",         "cat": "Meme",           "sector": "Meme"},
    "MEME-USD":  {"name": "Memecoin",          "cat": "Meme",           "sector": "Meme"},
    "TURBO-USD": {"name": "Turbo",             "cat": "Meme",           "sector": "Meme"},
    "NEIRO-USD": {"name": "Neiro",             "cat": "Meme",           "sector": "Meme"},
    "PEOPLE-USD":{"name": "ConstitutionDAO",   "cat": "Meme",           "sector": "Meme"},
    "BOME-USD":  {"name": "BOOK OF MEME",      "cat": "Meme",           "sector": "Meme"},
    "MEW-USD":   {"name": "cat in a dogs world","cat": "Meme",          "sector": "Meme"},
    "NOT-USD":   {"name": "Notcoin",           "cat": "Meme",           "sector": "Meme"},
    # ── Exchange ──
    "CRO-USD":   {"name": "Cronos",            "cat": "Exchange",       "sector": "Exchange"},
    "OKB-USD":   {"name": "OKB",               "cat": "Exchange",       "sector": "Exchange"},
    "KCS-USD":   {"name": "KuCoin Token",      "cat": "Exchange",       "sector": "Exchange"},
    "GT-USD":    {"name": "Gate Token",        "cat": "Exchange",       "sector": "Exchange"},
    "MX-USD":    {"name": "MEXC Token",        "cat": "Exchange",       "sector": "Exchange"},
    # ── Privacy ──
    "XMR-USD":   {"name": "Monero",            "cat": "Privacy",        "sector": "Privacy"},
    "ZEC-USD":   {"name": "Zcash",             "cat": "Privacy",        "sector": "Privacy"},
    "DASH-USD":  {"name": "Dash",              "cat": "Privacy",        "sector": "Privacy"},
    # ── Other ──
    "ENA-USD":   {"name": "Ethena",            "cat": "DeFi",           "sector": "DeFi"},
    "MNT-USD":   {"name": "Mantle",            "cat": "Layer 2",        "sector": "Layer 2"},
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
    """Fetch OHLCV for crypto markets via yfinance."""
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
    ("BTC-USD",  "Bitcoin",       "crypto",     68_500.0,   1.42),
    ("ETH-USD",  "Ethereum",      "crypto",      3_850.0,   2.15),
    ("BNB-USD",  "BNB",           "crypto",        610.0,   0.72),
    ("SOL-USD",  "Solana",        "crypto",        175.0,   3.20),
    ("XRP-USD",  "XRP",           "crypto",          0.62, -0.33),
    ("ADA-USD",  "Cardano",       "crypto",          0.48,  1.15),
    ("AVAX-USD", "Avalanche",     "crypto",         38.50,  0.45),
    ("DOT-USD",  "Polkadot",      "crypto",          7.20, -0.18),
    ("LINK-USD", "Chainlink",     "crypto",         15.80,  0.62),
    ("MATIC-USD","Polygon",       "crypto",          0.85, -1.80),
    ("UNI-USD",  "Uniswap",       "crypto",         12.40,  1.20),
    ("ATOM-USD", "Cosmos",        "crypto",          9.60, -0.55),
    ("LTC-USD",  "Litecoin",      "crypto",         85.30,  0.35),
    ("^GSPC",    "S&P 500",       "index",       5_674.0,  -0.31),
    ("^DJI",     "Dow Jones",     "index",      42_150.0,   0.18),
    ("^IXIC",    "Nasdaq",        "index",      18_320.0,  -0.45),
    ("^N225",    "Nikkei 225",    "index",      38_750.0,   0.55),
    ("^FTSE",    "FTSE 100",      "index",       8_210.0,  -0.22),
    ("^VIX",     "VIX Fear",      "index",         18.4,   -3.20),
    ("USDT-USD", "Tether",        "stablecoin",      1.0,   0.01),
    ("USDC-USD", "USD Coin",      "stablecoin",      1.0,   0.00),
    ("DOGE-USD", "Dogecoin",      "meme",            0.16,  2.35),
    ("SHIB-USD", "Shiba Inu",     "meme",            0.000028, -1.20),
    ("PEPE-USD", "Pepe",          "meme",            0.000012,  0.92),
    ("AAVE-USD", "Aave",          "defi",          105.0,   1.50),
    ("MKR-USD",  "Maker",         "defi",         1_580.0, -0.65),
    ("FET-USD",  "Fetch.ai",      "ai",              2.30,  3.40),
    ("RNDR-USD", "Render",        "ai",              8.50,   0.40),
]
