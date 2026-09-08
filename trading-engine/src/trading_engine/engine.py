"""
Main TradingEngine orchestrator.

Coordinates the five-stage pipeline:
1. Data Ingestion
2. Feature Engineering
3. Signal Generation
4. Portfolio Construction
5. Order Execution
"""

from typing import Dict, Any, Optional, List
import numpy as np

from .config import Config
from .data.market_data import MarketDataHandler
from .features.regime import RegimeClassifier
from .signals.ensemble import SignalEnsemble
from .risk.manager import RiskManager
from .portfolio.constructor import PortfolioConstructor
from .execution.engine import ExecutionEngine


class MarketState:
    """Container for current market state."""
    
    def __init__(
        self,
        order_books: Dict[str, Any],
        features: Dict[str, np.ndarray],
        regime_state: int,
        regime_probs: np.ndarray,
        variance_risk_premium: float,
        current_pnl: float,
        positions: Dict[str, float],
        collateral_utilization: float
    ):
        self.order_books = order_books
        self.features = features
        self.regime_state = regime_state
        self.regime_probs = regime_probs
        self.variance_risk_premium = variance_risk_premium
        self.current_pnl = current_pnl
        self.positions = positions
        self.collateral_utilization = collateral_utilization


class TradingEngine:
    """
    Main orchestrator for the statistical arbitrage trading system.
    
    Implements the five-stage pipeline with hard risk constraints
    and dynamic leverage scaling based on variance risk premium.
    """
    
    def __init__(self, config: Config):
        """
        Initialize the trading engine.
        
        Args:
            config: Configuration object with all parameters
        """
        self.config = config
        config.validate()
        
        # Initialize pipeline components
        self.data_handler = MarketDataHandler(config)
        self.regime_classifier = RegimeClassifier(config)
        self.signal_ensemble = SignalEnsemble(config)
        self.risk_manager = RiskManager(config)
        self.portfolio_constructor = PortfolioConstructor(config)
        self.execution_engine = ExecutionEngine(config)
        
        # State tracking
        self._current_pnl = 0.0
        self._positions: Dict[str, float] = {}
        self._is_observation_only = False
        self._daily_start_pnl = 0.0
        
    def get_market_state(self) -> MarketState:
        """
        Retrieve current market state from data layer.
        
        Returns:
            MarketState object with current market data
        """
        order_books = self.data_handler.get_order_books()
        features = self.data_handler.compute_features()
        
        regime_state, regime_probs = self.regime_classifier.classify(features)
        vrp = self.signal_ensemble.agent4.compute_vrp()
        
        return MarketState(
            order_books=order_books,
            features=features,
            regime_state=regime_state,
            regime_probs=regime_probs,
            variance_risk_premium=vrp,
            current_pnl=self._current_pnl,
            positions=self._positions,
            collateral_utilization=self.risk_manager.get_collateral_utilization()
        )
    
    def generate_signals(self, state: MarketState) -> Dict[str, np.ndarray]:
        """
        Generate trading signals from the four-agent ensemble.
        
        Args:
            state: Current market state
            
        Returns:
            Dictionary mapping instrument IDs to signal values
        """
        if self._is_observation_only:
            return {inst: np.zeros(4) for inst in state.order_books.keys()}
        
        signals = self.signal_ensemble.generate(state)
        return signals
    
    def construct_portfolio(
        self,
        signals: Dict[str, np.ndarray],
        state: MarketState
    ) -> Dict[str, float]:
        """
        Construct portfolio from signals with risk constraints.
        
        Args:
            signals: Agent signals per instrument
            state: Current market state
            
        Returns:
            Dictionary mapping instrument IDs to target positions
        """
        if self._is_observation_only:
            return {}
        
        target_positions = self.portfolio_constructor.construct(
            signals=signals,
            state=state,
            current_positions=self._positions
        )
        
        return target_positions
    
    def route_orders(
        self,
        portfolio: Dict[str, float],
        state: MarketState
    ) -> List[Dict[str, Any]]:
        """
        Route orders to venues via smart order router.
        
        Args:
            portfolio: Target positions
            state: Current market state
            
        Returns:
            List of order dictionaries
        """
        if self._is_observation_only:
            return []
        
        orders = self.execution_engine.route(portfolio, state)
        return orders
    
    def execute_cycle(self) -> Optional[List[Dict[str, Any]]]:
        """
        Execute one full pipeline cycle.
        
        Returns:
            List of orders to execute, or None if circuit breaker triggered
        """
        state = self.get_market_state()
        
        if self.risk_manager.check_circuit_breaker(state.current_pnl):
            self._trigger_circuit_breaker()
            return None
        
        signals = self.generate_signals(state)
        portfolio = self.construct_portfolio(signals, state)
        orders = self.route_orders(portfolio, state)
        
        return orders
    
    def _trigger_circuit_breaker(self) -> None:
        """
        Activate circuit breaker protocol.
        
        Immediately ceases order generation and liquidates to delta-neutral.
        """
        self._is_observation_only = True
        self.risk_manager.liquidate_all()
        print(f"CIRCUIT BREAKER TRIGGERED at PnL={self._current_pnl:.4f}")
    
    def update_pnl(self, pnl_change: float) -> None:
        """
        Update cumulative PnL.
        
        Args:
            pnl_change: PnL change from executed trades
        """
        self._current_pnl += pnl_change
        
        if self._current_pnl < self._daily_start_pnl + self.config.risk.max_daily_drawdown:
            self._trigger_circuit_breaker()
    
    def reset_daily(self) -> None:
        """Reset daily state for new trading session."""
        self._daily_start_pnl = self._current_pnl
        self._is_observation_only = False
    
    def liquidate_all(self) -> None:
        """Force liquidation of all positions."""
        self.risk_manager.liquidate_all()
        self._positions = {}
