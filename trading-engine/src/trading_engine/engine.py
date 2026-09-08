"""
Main Trading Engine orchestrator.

Coordinates all system components in the five-stage pipeline:
Data Ingestion → Feature Engineering → Signal Generation → 
Portfolio Construction → Order Execution
"""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from .config import Config
from .data.market_data import MarketDataHandler
from .features.regime import RegimeClassifier
from .signals.ensemble import AgentEnsemble
from .risk.manager import RiskManager
from .portfolio.constructor import PortfolioConstructor
from .execution.engine import ExecutionEngine


logger = logging.getLogger(__name__)


class TradingEngine:
    """
    Main trading engine orchestrating the five-stage pipeline.
    
    Attributes:
        config: System configuration parameters
        market_data: Market data ingestion and normalization
        regime_classifier: HMM-based regime classification
        signal_ensemble: 4-agent signal generation ensemble
        risk_manager: Risk management and circuit breakers
        portfolio_constructor: Portfolio construction and sizing
        execution_engine: Smart order routing and execution
    """
    
    def __init__(self, config: Optional[Config] = None):
        """
        Initialize the trading engine.
        
        Args:
            config: Configuration object. Uses defaults if None.
        """
        self.config = config or Config.default()
        self._running = False
        self._pnl_cumulative = 0.0
        self._pnl_daily = 0.0
        
        # Initialize pipeline components
        logger.info("Initializing market data handler...")
        self.market_data = MarketDataHandler(self.config)
        
        logger.info("Initializing regime classifier...")
        self.regime_classifier = RegimeClassifier(self.config)
        
        logger.info("Initializing signal ensemble...")
        self.signal_ensemble = AgentEnsemble(self.config)
        
        logger.info("Initializing risk manager...")
        self.risk_manager = RiskManager(self.config)
        
        logger.info("Initializing portfolio constructor...")
        self.portfolio_constructor = PortfolioConstructor(
            self.config, 
            self.risk_manager
        )
        
        logger.info("Initializing execution engine...")
        self.execution_engine = ExecutionEngine(self.config)
        
        logger.info("Trading engine initialized successfully.")
    
    def run(self) -> None:
        """
        Start the main trading loop.
        
        This method blocks until stop() is called or a circuit breaker triggers.
        """
        logger.info("Starting trading engine...")
        self._running = True
        
        try:
            while self._running:
                self._step()
        except KeyboardInterrupt:
            logger.info("Interrupted by user.")
        finally:
            self.stop()
    
    def _step(self) -> None:
        """Execute one iteration of the trading pipeline."""
        try:
            # Stage 1: Data Ingestion
            market_data = self.market_data.get_latest()
            
            # Stage 2: Feature Engineering & Regime Classification
            features = self.market_data.compute_features(market_data)
            regime_state = self.regime_classifier.classify(features)
            
            # Check regime gate - force de-leveraging in Fractured state
            if regime_state == 2:  # Fractured/Illiquid
                logger.warning("Fractured regime detected - forcing de-leveraging")
                self.risk_manager.force_deleveraging()
            
            # Stage 3: Signal Generation
            signals = self.signal_ensemble.generate_signals(
                market_data, 
                features, 
                regime_state
            )
            
            # Stage 4: Portfolio Construction (with risk constraints)
            target_portfolio = self.portfolio_constructor.construct(
                signals, 
                regime_state,
                self._pnl_daily
            )
            
            # Stage 5: Order Execution
            orders = self.execution_engine.generate_orders(target_portfolio)
            fills = self.execution_engine.execute(orders)
            
            # Update P&L
            self._update_pnl(fills)
            
            # Check circuit breaker
            if self._pnl_daily <= self.config.risk.daily_drawdown_limit:
                logger.critical(
                    f"Circuit breaker triggered! Daily PnL: {self._pnl_daily:.4f}"
                )
                self.trigger_liquidation()
                
        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)
    
    def _update_pnl(self, fills: Dict[str, Any]) -> None:
        """Update cumulative and daily P&L from fills."""
        # Simplified P&L calculation
        pnl_change = fills.get('realized_pnl', 0.0)
        self._pnl_cumulative += pnl_change
        self._pnl_daily += pnl_change
    
    def trigger_liquidation(self) -> None:
        """
        Trigger hard-stop circuit breaker.
        
        Immediately ceases order generation, liquidates positions
        to delta-neutral, and enters Observation Only state.
        """
        logger.critical("TRIGGERING HARD-STOP CIRCUIT BREAKER")
        
        # Stop generating new orders
        self._running = False
        
        # Liquidate all positions to delta-neutral
        self.execution_engine.liquidate_all()
        
        # Enter observation-only state
        self.risk_manager.set_observation_mode(True)
        
        logger.info("System entered Observation Only state until next settlement.")
    
    def stop(self) -> None:
        """Gracefully stop the trading engine."""
        logger.info("Stopping trading engine...")
        self._running = False
        self.execution_engine.close()
        logger.info("Trading engine stopped.")
    
    def get_status(self) -> Dict[str, Any]:
        """
        Get current engine status.
        
        Returns:
            Dictionary containing operational status, P&L, and risk metrics.
        """
        return {
            "running": self._running,
            "pnl_cumulative": self._pnl_cumulative,
            "pnl_daily": self._pnl_daily,
            "regime_state": self.regime_classifier.current_state,
            "gross_exposure": self.risk_manager.get_gross_exposure(),
            "net_exposure": self.risk_manager.get_net_exposure(),
            "leverage": self.risk_manager.get_current_leverage(),
            "observation_mode": self.risk_manager.is_observation_mode(),
            "timestamp": datetime.utcnow().isoformat()
        }
