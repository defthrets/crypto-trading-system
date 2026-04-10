"""
Crypto asset universe definitions.
Organized by market regime categories (replaces traditional quadrants).
"""

from config.ruleset import MARKET_REGIMES

# ═══════════════════════════════════════════════════════════════
#  LARGE CAP — BTC, ETH, and top-10 by market cap
# ═══════════════════════════════════════════════════════════════

LARGE_CAP = {
    "BTC-USD": {
        "name": "Bitcoin",
        "type": "large_cap",
        "category": "store_of_value",
        "regime_bias": "all_weather",
    },
    "ETH-USD": {
        "name": "Ethereum",
        "type": "large_cap",
        "category": "smart_contract_platform",
        "regime_bias": "all_weather",
    },
    "BNB-USD": {
        "name": "Binance Coin",
        "type": "large_cap",
        "category": "exchange_token",
        "regime_bias": "bull_trend",
    },
    "SOL-USD": {
        "name": "Solana",
        "type": "large_cap",
        "category": "layer1",
        "regime_bias": "bull_trend",
    },
    "XRP-USD": {
        "name": "XRP",
        "type": "large_cap",
        "category": "payment",
        "regime_bias": "bull_trend",
    },
    "ADA-USD": {
        "name": "Cardano",
        "type": "large_cap",
        "category": "layer1",
        "regime_bias": "accumulation",
    },
    "AVAX-USD": {
        "name": "Avalanche",
        "type": "large_cap",
        "category": "layer1",
        "regime_bias": "bull_trend",
    },
    "DOT-USD": {
        "name": "Polkadot",
        "type": "large_cap",
        "category": "layer1",
        "regime_bias": "accumulation",
    },
    "LINK-USD": {
        "name": "Chainlink",
        "type": "large_cap",
        "category": "oracle",
        "regime_bias": "bull_trend",
    },
    "MATIC-USD": {
        "name": "Polygon",
        "type": "large_cap",
        "category": "layer2",
        "regime_bias": "bull_trend",
    },
}

# ═══════════════════════════════════════════════════════════════
#  DEFI BLUE CHIPS
# ═══════════════════════════════════════════════════════════════

DEFI_TOKENS = {
    "UNI-USD": {
        "name": "Uniswap",
        "type": "defi_blue_chip",
        "category": "dex",
        "regime_bias": "bull_trend",
    },
    "AAVE-USD": {
        "name": "Aave",
        "type": "defi_blue_chip",
        "category": "lending",
        "regime_bias": "bull_trend",
    },
    "MKR-USD": {
        "name": "Maker",
        "type": "defi_blue_chip",
        "category": "stablecoin_protocol",
        "regime_bias": "all_weather",
    },
    "CRV-USD": {
        "name": "Curve DAO",
        "type": "defi_blue_chip",
        "category": "dex",
        "regime_bias": "bull_trend",
    },
    "LDO-USD": {
        "name": "Lido DAO",
        "type": "defi_blue_chip",
        "category": "liquid_staking",
        "regime_bias": "bull_trend",
    },
    "SNX-USD": {
        "name": "Synthetix",
        "type": "defi_blue_chip",
        "category": "derivatives",
        "regime_bias": "bull_trend",
    },
}

# ═══════════════════════════════════════════════════════════════
#  LAYER 1 ALTERNATIVES
# ═══════════════════════════════════════════════════════════════

LAYER1_ALTS = {
    "NEAR-USD": {
        "name": "NEAR Protocol",
        "type": "layer1",
        "category": "smart_contract_platform",
        "regime_bias": "bull_trend",
    },
    "APT-USD": {
        "name": "Aptos",
        "type": "layer1",
        "category": "smart_contract_platform",
        "regime_bias": "bull_trend",
    },
    "SUI-USD": {
        "name": "Sui",
        "type": "layer1",
        "category": "smart_contract_platform",
        "regime_bias": "bull_trend",
    },
    "ATOM-USD": {
        "name": "Cosmos",
        "type": "layer1",
        "category": "interoperability",
        "regime_bias": "bull_trend",
    },
    "FTM-USD": {
        "name": "Fantom",
        "type": "layer1",
        "category": "smart_contract_platform",
        "regime_bias": "bull_trend",
    },
    "INJ-USD": {
        "name": "Injective",
        "type": "layer1",
        "category": "defi_chain",
        "regime_bias": "bull_trend",
    },
}

# ═══════════════════════════════════════════════════════════════
#  LAYER 2 / SCALING
# ═══════════════════════════════════════════════════════════════

LAYER2_TOKENS = {
    "ARB-USD": {
        "name": "Arbitrum",
        "type": "layer2",
        "category": "rollup",
        "regime_bias": "bull_trend",
    },
    "OP-USD": {
        "name": "Optimism",
        "type": "layer2",
        "category": "rollup",
        "regime_bias": "bull_trend",
    },
}

# ═══════════════════════════════════════════════════════════════
#  MEME / HIGH VOLATILITY (GCR contrarian plays)
# ═══════════════════════════════════════════════════════════════

MEME_TOKENS = {
    "DOGE-USD": {
        "name": "Dogecoin",
        "type": "meme",
        "category": "meme_coin",
        "regime_bias": "bull_trend",
    },
    "SHIB-USD": {
        "name": "Shiba Inu",
        "type": "meme",
        "category": "meme_coin",
        "regime_bias": "bull_trend",
    },
    "PEPE-USD": {
        "name": "Pepe",
        "type": "meme",
        "category": "meme_coin",
        "regime_bias": "bull_trend",
    },
    "WIF-USD": {
        "name": "dogwifhat",
        "type": "meme",
        "category": "meme_coin",
        "regime_bias": "bull_trend",
    },
}

# ═══════════════════════════════════════════════════════════════
#  STABLECOINS (for allocation tracking)
# ═══════════════════════════════════════════════════════════════

STABLECOINS = {
    "USDT": {"name": "Tether", "type": "stablecoin", "category": "stablecoin", "regime_bias": "bear_trend"},
    "USDC": {"name": "USD Coin", "type": "stablecoin", "category": "stablecoin", "regime_bias": "bear_trend"},
}


def get_all_assets() -> dict:
    """Return the full crypto asset universe."""
    all_assets = {}
    all_assets.update(LARGE_CAP)
    all_assets.update(DEFI_TOKENS)
    all_assets.update(LAYER1_ALTS)
    all_assets.update(LAYER2_TOKENS)
    all_assets.update(MEME_TOKENS)
    return all_assets


# Core subset for low-memory systems
CORE_TICKERS = [
    # Large caps (5)
    "BTC-USD", "ETH-USD", "SOL-USD", "BNB-USD", "XRP-USD",
    # DeFi (3)
    "UNI-USD", "AAVE-USD", "LINK-USD",
    # L1 alts (2)
    "AVAX-USD", "NEAR-USD",
    # Meme (1)
    "DOGE-USD",
]


def get_core_assets() -> dict:
    """Return a reduced ~11 asset universe for memory-constrained systems."""
    full = get_all_assets()
    return {t: full[t] for t in CORE_TICKERS if t in full}


def get_tradeable_assets() -> dict:
    """Return all assets excluding stablecoins (for signal generation)."""
    return get_all_assets()


def get_assets_by_regime(regime: str) -> dict:
    """Filter assets by market regime."""
    return {
        ticker: info
        for ticker, info in get_all_assets().items()
        if info.get("regime_bias") == regime or info.get("regime_bias") == "all_weather"
    }


def get_assets_by_type(asset_type: str) -> dict:
    """Filter assets by type (large_cap, defi_blue_chip, layer1, etc.)."""
    return {
        ticker: info
        for ticker, info in get_all_assets().items()
        if info.get("type") == asset_type
    }
