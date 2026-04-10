"""
Crypto AI Agent — The Autonomous Orchestrator.

This is the brain of the system. It coordinates all engines and
produces actionable, justified trade decisions based on:
  - CryptoCred TA: Market structure, directional bias, S/R, entries
  - GCR Pearls: Contrarian psychology, reflexivity, cycle timing
  - Real-time crypto market data + sentiment
  - Correlation & position sizing constraints
  - Technical signals with multi-timeframe analysis

Ultra Ruleset Principles Encoded:
  CryptoCred: "Be systematic — never emotional."
  GCR: "The views of most people are often wrong, and real
        opportunities are hidden in the opposite direction of consensus."

  1. Always establish directional bias before trading (CryptoCred).
  2. Know the market regime — bull, bear, accumulation, distribution (CryptoCred + GCR).
  3. Be contrarian at extremes — bet against consensus when sentiment is extreme (GCR).
  4. Risk management is non-negotiable — stops before entry (GCR + CryptoCred).
  5. BTC/ETH are core positions — alts cannot survive independently (GCR).
"""

import asyncio
from datetime import datetime
from loguru import logger
from typing import Optional

from engines.correlation_engine import CorrelationEngine
from engines.risk_parity_engine import RiskParityEngine
from engines.sentiment_engine import SentimentEngine
from engines.regime_engine import RegimeEngine
from trading.signal_generator import SignalGenerator, TradeSignal
from trading.execution import ExecutionEngine
from trading.circuit_breaker import CircuitBreaker
from config.assets import get_core_assets
from config.settings import get_settings
from config.ruleset import (
    RISK_MANAGEMENT_RULES,
    GCR_CONTRARIAN_RULES,
    META_RULES,
)


class CryptoAgent:
    """
    Autonomous crypto trading agent powered by CryptoCred + GCR Ultra Ruleset.

    Lifecycle:
      boot()       -> initialise all engines
      run_cycle()  -> one full decision cycle (called by scheduler)
      shutdown()   -> clean teardown
    """

    def __init__(self, initial_equity: float = 100_000.0):
        self.settings = get_settings()
        self.initial_equity = initial_equity

        # Engines
        self.correlation_engine = CorrelationEngine()
        self.risk_parity_engine = RiskParityEngine()
        self.sentiment_engine = SentimentEngine()
        self.regime_engine = RegimeEngine()

        # Trading
        self.circuit_breaker = CircuitBreaker(initial_equity)
        self.execution_engine = ExecutionEngine(self.circuit_breaker, initial_equity)
        self.signal_generator = SignalGenerator(
            regime_engine=self.regime_engine,
            sentiment_engine=self.sentiment_engine,
            correlation_engine=self.correlation_engine,
        )

        # State
        self._booted = False
        self._current_regime_context: Optional[dict] = None
        self._current_weights: dict[str, float] = {}
        self._selected_portfolio: list[str] = []
        self._notifier = None

        self._cycle_count = 0
        self._last_correlation_update: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def boot(self):
        """Initialise all engines."""
        logger.info("=" * 60)
        logger.info("  CRYPTO AUTONOMOUS TRADING SYSTEM — BOOTING")
        logger.info("  Powered by CryptoCred TA + GCR Pearls of Wisdom")
        logger.info("=" * 60)

        # Step 1: Sentiment model (optional — keyword fallback exists)
        logger.info("Step 1/4: Loading sentiment model...")
        try:
            self.sentiment_engine.load_model()
        except Exception as e:
            logger.error(f"Sentiment model load failed, using keyword fallback: {e}")

        # Step 2: Market regime classification
        logger.info("Step 2/4: Classifying market regime (CryptoCred structure analysis)...")
        try:
            self._current_regime_context = self.regime_engine.classify()
            logger.info(self.regime_engine.get_narrative())
        except Exception as e:
            logger.error(f"Regime classification failed: {e}")
            self._current_regime_context = {
                "regime": "unknown",
                "description": "Boot failed — neutral positioning per GCR rule.",
            }

        # Step 3: Correlation matrix
        logger.info("Step 3/4: Building correlation matrix...")
        try:
            self._refresh_correlations()
        except Exception as e:
            logger.error(f"Correlation matrix build failed: {e}")

        # Step 4: Position weights
        logger.info("Step 4/4: Computing position weights...")
        try:
            self._refresh_weights()
        except Exception as e:
            logger.error(f"Weight computation failed: {e}")

        self._booted = True
        logger.info("CRYPTO AGENT READY. Entering autonomous mode.")
        logger.info(f"META RULE: {META_RULES['patience']}")

    def attach_notifier(self, notifier):
        """Inject the notification manager after construction."""
        self._notifier = notifier

    # ------------------------------------------------------------------
    # Main Cycle
    # ------------------------------------------------------------------

    def run_cycle(self) -> dict:
        """
        One full decision cycle. Called by the APScheduler job.
        """
        if not self._booted:
            self.boot()

        self._cycle_count += 1
        cycle_start = datetime.utcnow()
        logger.info(f"\n{'='*60}")
        logger.info(f"  CRYPTO CYCLE #{self._cycle_count} — {cycle_start.isoformat()}")
        logger.info(f"{'='*60}")

        # 1. Circuit Breaker Check
        can_trade, halt_reason = self.circuit_breaker.can_trade()
        if not can_trade:
            alert = {
                "type": "CIRCUIT_BREAKER",
                "message": f"Trading HALTED: {halt_reason}",
                "timestamp": cycle_start.isoformat(),
            }
            self._send_notification(alert)
            return alert

        # 2. Refresh market regime (CryptoCred structure + GCR contrarian)
        logger.info("Refreshing market regime classification...")
        self._current_regime_context = self.regime_engine.classify()
        current_regime = self._current_regime_context.get("regime", "unknown")

        # GCR Meta Rule: reduce trading under unfavorable conditions
        if current_regime == "unknown":
            logger.warning("META RULE (GCR): Regime unclear — reducing activity.")

        # 3. Refresh correlation matrix (every 24h)
        hours_since_update = self._hours_since_correlation_update()
        if hours_since_update >= self.settings.correlation_update_hours:
            logger.info("Refreshing correlation matrix (24h interval)...")
            self._refresh_correlations()
            self._refresh_weights()

        # 4. Scan crypto universe for signals
        logger.info("Scanning universe for trade signals...")
        current_tickers = list(self.execution_engine.get_open_positions().keys())
        signals = self.signal_generator.scan_universe(
            current_portfolio=current_tickers,
            top_n=10,
        )

        # 5. Scan for new opportunities
        logger.info("Scanning for new opportunities (GCR contrarian + CryptoCred setups)...")
        new_opportunities = self.signal_generator.suggest_new_opportunities(
            exclude=current_tickers
        )

        # 6. Execute signals (paper or live)
        executed_orders = []
        for signal in signals:
            order = self.execution_engine.execute_signal(signal)
            if order and order.status == "filled":
                executed_orders.append(order)

        # 7. Portfolio health report
        portfolio_health = self._generate_portfolio_health()

        # 8. Compile cycle summary
        cycle_summary = {
            "type": "CYCLE_COMPLETE",
            "cycle": self._cycle_count,
            "timestamp": cycle_start.isoformat(),
            "regime": current_regime,
            "regime_description": self._current_regime_context.get("description", ""),
            "regime_bias": self._current_regime_context.get("bias", "neutral"),
            "risk_scaling": self._current_regime_context.get("risk_scaling", "minimal"),
            "contrarian_signal": self._current_regime_context.get("contrarian_signal", {}),
            "signals_found": len(signals),
            "new_opportunities": len(new_opportunities),
            "orders_executed": len(executed_orders),
            "portfolio_health": portfolio_health,
            "top_signals": [self._signal_to_dict(s) for s in signals[:5]],
            "new_opportunities_detail": [self._signal_to_dict(s) for s in new_opportunities[:3]],
            "circuit_breaker": self.circuit_breaker.get_status(),
        }

        # 9. Send notifications
        self._send_notification(cycle_summary)

        logger.info(
            f"Cycle #{self._cycle_count} complete | "
            f"Signals: {len(signals)} | Executed: {len(executed_orders)} | "
            f"Regime: {current_regime}"
        )
        return cycle_summary

    # ------------------------------------------------------------------
    # Specialised Reports
    # ------------------------------------------------------------------

    def run_portfolio_health_report(self) -> dict:
        health = self._generate_portfolio_health()
        self._send_notification({"type": "HEALTH_REPORT", **health})
        return health

    def run_sentiment_alert(self) -> dict:
        logger.info("Running sentiment alert scan...")
        summary = self.sentiment_engine.get_market_sentiment_summary()

        # GCR contrarian check on sentiment
        fear_greed = summary.get("fear_greed_index", 50)
        if fear_greed <= 15 or fear_greed >= 85:
            gcr_signal = "CONTRARIAN" if fear_greed <= 15 else "DISTRIBUTION"
            alert = {
                "type": "SENTIMENT_ALERT",
                "message": (
                    f"GCR CONTRARIAN SIGNAL: Fear & Greed at {fear_greed}. "
                    f"{'Extreme fear — accumulation opportunity.' if fear_greed <= 15 else 'Extreme greed — distribution warning.'}"
                ),
                "fear_greed": fear_greed,
                "gcr_signal": gcr_signal,
                "sentiment_summary": summary,
                "timestamp": datetime.utcnow().isoformat(),
            }
            self._send_notification(alert)
            return alert

        return {"type": "SENTIMENT_SCAN", "status": "normal", **summary}

    def run_walk_forward_backtest(self, tickers: Optional[list[str]] = None) -> dict:
        from backtesting.walk_forward import WalkForwardOptimizer
        logger.info("Starting walk-forward backtest...")
        wf = WalkForwardOptimizer()
        report = wf.run(tickers=tickers, initial_equity=self.initial_equity)
        summary = report.summary()
        notification = {
            "type": "BACKTEST_REPORT",
            "timestamp": datetime.utcnow().isoformat(),
            **summary,
        }
        self._send_notification(notification)
        return summary

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _refresh_correlations(self):
        tickers = list(get_core_assets().keys())
        self.correlation_engine.refresh(tickers)
        self._last_correlation_update = datetime.utcnow()

        self._selected_portfolio = self.correlation_engine.get_low_correlation_assets(
            target_count=self.settings.min_diversification_assets,
            max_corr=self.settings.max_portfolio_correlation,
        )
        logger.info(
            f"Portfolio selected: {len(self._selected_portfolio)} assets "
            f"with correlation < {self.settings.max_portfolio_correlation}"
        )

    def _refresh_weights(self):
        if not self._selected_portfolio:
            return
        self._current_weights = self.risk_parity_engine.compute_weights(
            self._selected_portfolio
        )
        logger.info(
            f"Position weights computed for {len(self._current_weights)} assets."
        )

    def _generate_portfolio_health(self) -> dict:
        cb_status = self.circuit_breaker.get_status()
        positions = self.execution_engine.get_open_positions()
        port_tickers = list(positions.keys())

        corr_stats = {}
        if port_tickers and len(port_tickers) >= 2:
            corr_stats = self.correlation_engine.get_portfolio_correlation_stats(port_tickers)

        sharpe_info = {}
        if port_tickers and self._current_weights:
            sharpe_info = self.risk_parity_engine.compute_sharpe_contribution(
                self._current_weights, port_tickers
            )

        # GCR portfolio rule check
        btc_allocation = self._current_weights.get("BTC-USD", 0) * 100
        eth_allocation = self._current_weights.get("ETH-USD", 0) * 100
        core_rules = RISK_MANAGEMENT_RULES["portfolio_rules"]
        btc_ok = btc_allocation >= core_rules["btc_core_allocation_pct"]
        eth_ok = eth_allocation >= core_rules["eth_core_allocation_pct"]

        return {
            "timestamp": datetime.utcnow().isoformat(),
            "equity": cb_status["current_equity"],
            "daily_pnl_pct": cb_status["daily_pnl_pct"],
            "drawdown_pct": cb_status["drawdown_pct"],
            "open_positions": len(positions),
            "portfolio_assets": port_tickers,
            "correlation_stats": corr_stats,
            "sharpe_info": sharpe_info,
            "risk_weights": self._current_weights,
            "selected_portfolio_size": len(self._selected_portfolio),
            "btc_allocation_pct": round(btc_allocation, 2),
            "eth_allocation_pct": round(eth_allocation, 2),
            "gcr_btc_core_met": btc_ok,
            "gcr_eth_core_met": eth_ok,
            "circuit_breaker_active": cb_status["trading_halted"],
            "current_regime": self._current_regime_context.get("regime", "unknown") if self._current_regime_context else "unknown",
        }

    def _hours_since_correlation_update(self) -> float:
        if self._last_correlation_update is None:
            return float("inf")
        delta = datetime.utcnow() - self._last_correlation_update
        return delta.total_seconds() / 3600

    def _send_notification(self, data: dict):
        if self._notifier:
            try:
                self._notifier.send(data)
            except Exception as e:
                logger.error(f"Notification failed: {e}")

    @staticmethod
    def _signal_to_dict(signal: TradeSignal) -> dict:
        return {
            "ticker": signal.ticker,
            "action": signal.action,
            "confidence": signal.confidence,
            "price": signal.price,
            "regime_fit": signal.quadrant_fit,
            "sentiment": signal.sentiment_label,
            "rsi": signal.rsi,
            "trend": signal.trend,
            "stop_loss": signal.suggested_stop_loss,
            "take_profit": signal.suggested_take_profit,
            "rr_ratio": signal.risk_reward_ratio,
            "position_size_pct": signal.position_size_pct,
            "reasons": signal.reasons,
        }
