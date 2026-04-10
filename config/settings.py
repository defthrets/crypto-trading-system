"""
Central configuration for the Crypto Trading System.
Loads from .env and provides typed access to all settings.
"""

from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # --- Market Data APIs ---
    alpha_vantage_api_key: str | None = Field(default=None, alias="ALPHA_VANTAGE_API_KEY")

    # --- Crypto-Specific APIs ---
    coingecko_api_key: str | None = Field(default=None, alias="COINGECKO_API_KEY")
    coinmarketcap_api_key: str | None = Field(default=None, alias="COINMARKETCAP_API_KEY")
    glassnode_api_key: str | None = Field(default=None, alias="GLASSNODE_API_KEY")

    # --- News APIs ---
    finnhub_api_key: str | None = Field(default=None, alias="FINNHUB_API_KEY")
    newsapi_api_key: str | None = Field(default=None, alias="NEWSAPI_API_KEY")
    cryptopanic_api_key: str | None = Field(default=None, alias="CRYPTOPANIC_API_KEY")

    # --- Optional API-based Sentiment ---
    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    openai_api_key: str | None = Field(default=None, alias="OPENAI_API_KEY")

    # --- Notifications ---
    discord_webhook_url: str = Field(default="", alias="DISCORD_WEBHOOK_URL")
    telegram_bot_token: str = Field(default="", alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", alias="TELEGRAM_CHAT_ID")

    # --- Database ---
    database_url: str = Field(default="sqlite:///data/storage/trading.db", alias="DATABASE_URL")

    # --- Authentication ---
    auth_enabled: bool = Field(default=False, alias="CRYPTO_AUTH_ENABLED")
    jwt_secret: str = Field(default="", alias="CRYPTO_JWT_SECRET")

    # --- Risk Parameters (from Ultra Ruleset) ---
    max_daily_loss_pct: float = Field(default=5.0, alias="MAX_DAILY_LOSS_PCT")
    max_drawdown_pct: float = Field(default=15.0, alias="MAX_DRAWDOWN_PCT")
    max_portfolio_correlation: float = Field(default=0.4, alias="MAX_PORTFOLIO_CORRELATION")
    min_diversification_assets: int = Field(default=8, alias="MIN_DIVERSIFICATION_ASSETS")
    max_pos_size_pct: float = Field(default=8.0, alias="MAX_POS_SIZE_PCT")
    max_open_positions: int = Field(default=15, alias="MAX_OPEN_POSITIONS")
    max_risk_per_trade_pct: float = Field(default=2.0, alias="MAX_RISK_PER_TRADE_PCT")

    # --- GCR Core Allocation Rules ---
    btc_min_allocation_pct: float = Field(default=40.0, alias="BTC_MIN_ALLOCATION_PCT")
    eth_min_allocation_pct: float = Field(default=20.0, alias="ETH_MIN_ALLOCATION_PCT")
    altcoin_max_allocation_pct: float = Field(default=30.0, alias="ALTCOIN_MAX_ALLOCATION_PCT")
    stablecoin_min_pct: float = Field(default=10.0, alias="STABLECOIN_MIN_PCT")

    # --- Trading Mode ---
    trading_mode: str = Field(default="paper", alias="TRADING_MODE")

    # --- Paths ---
    project_root: Path = Path(__file__).parent.parent
    data_dir: Path = Path(__file__).parent.parent / "data"
    log_dir: Path = Path(__file__).parent.parent / "logs"

    # --- Crypto Market Parameters ---
    correlation_lookback_days: int = 180  # Crypto moves faster than tradfi
    correlation_update_hours: int = 12    # Update twice daily for 24/7 market
    risk_parity_rebalance_days: int = 3   # More frequent rebalancing
    walk_forward_train_months: int = 6    # Shorter cycles in crypto
    walk_forward_test_months: int = 2

    # --- Sentiment ---
    sentiment_batch_size: int = 16
    fear_greed_contrarian_low: int = Field(default=15, alias="FEAR_GREED_CONTRARIAN_LOW")
    fear_greed_contrarian_high: int = Field(default=85, alias="FEAR_GREED_CONTRARIAN_HIGH")


@lru_cache()
def get_settings() -> Settings:
    return Settings()
